#!/usr/bin/env python3
# Copyright 2025, Jasper van Brakel
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
import itertools
import platform
import threading
import time
from typing import Optional, TYPE_CHECKING

from controller_manager.controller_manager_services import list_hardware_components
from controller_manager_msgs.srv import ListHardwareComponents
from rcl_interfaces.msg import ParameterDescriptor
from rcl_interfaces.msg import ParameterType
import rclpy
import rclpy.callback_groups
import rclpy.parameter_client
import rosbag2_py
from tqdm.contrib.itertools import product as tqdm_product

from .continue_service import ContinueService
from .controller_context import active_controller
from .parameter_iterator import ParameterIterator
from .response_director_parameters import response_director as response_director_parameters
from .utils import setup_storage_location
from .utils import wait_for_node

if TYPE_CHECKING:
    from rclpy.logging import RcutilsLogger as Logger

SRV_POSTFIX: str = '/_service_event'


def main(args=None):
    rclpy.init(args=args, signal_handler_options=rclpy.SignalHandlerOptions.NO)

    with rclpy.get_global_executor() as exc:
        recorder = None
        record_thread = None
        try:
            node = rclpy.create_node('response_director')
            logger: 'Logger' = node.get_logger()
            exc.add_node(node)

            node.declare_parameter(
                name='recorded_services',
                value=rclpy.Parameter.Type.STRING_ARRAY,
                descriptor=ParameterDescriptor(
                    description='Services to record',
                    read_only=True,
                    type=ParameterType.PARAMETER_STRING_ARRAY,
                ),
            )

            node.declare_parameter(
                name='recorded_topics',
                value=rclpy.Parameter.Type.STRING_ARRAY,
                descriptor=ParameterDescriptor(
                    description='Extra topics to record',
                    read_only=True,
                    type=ParameterType.PARAMETER_STRING_ARRAY,
                ),
            )

            param_listener = response_director_parameters.ParamListener(node)
            params = param_listener.get_params()

            controller_manager = 'controller_manager'

            node_timeout = params.node_timeout

            if params.wait_for_telemetrix:
                wait_for_node(node, logger, 'io/telemetrix', timeout=node_timeout)
            wait_for_node(node, logger, controller_manager, timeout=node_timeout)
            wait_for_node(node, logger, params.controller_name, timeout=node_timeout)

            product = tqdm_product if params.progressbar else itertools.product

            parameter_iterators = sorted(
                (ParameterIterator(argument, params.signal) for argument in params.arguments),
                key=lambda iterator: iterator.name,
            )

            storage_location = setup_storage_location(logger, params.storage_location)

            custom_data = {'host': platform.node()}
            for key, value in platform.uname()._asdict().items():
                custom_data[f'uname.{key}'] = str(value)

            hw_components: ListHardwareComponents.Response = list_hardware_components(
                node,
                controller_manager,
            )
            custom_data['hw_interfaces'] = str(hw_components.component)

            custom_data['extra_notes'] = params.extra_notes

            custom_data['controller_name'] = params.controller_name

            # Store if recorded in manual mode since it can influence the data
            custom_data['manual_mode'] = str(params.manual_mode)

            recorder_options = rosbag2_py.RecordOptions()
            recorder_options.topics = list(
                set(
                    [
                        f'{params.controller_name}/transition_event',
                        f'{controller_manager}/activity',
                        f'{controller_manager}/introspection_data/full',
                        f'{controller_manager}/introspection_data/names',
                        f'{controller_manager}/introspection_data/values',
                        f'{controller_manager}/statistics/full',
                        f'{controller_manager}/statistics/names',
                        f'{controller_manager}/statistics/values',
                        '/diagnostics',
                        '/rosout',
                    ]
                    + list(filter(bool, params.recorded_topics)),
                ),
            )
            recorder_options.services = [
                (service if service.endswith(SRV_POSTFIX) else service + SRV_POSTFIX)
                for service in params.recorded_services if service
            ]
            recorder_options.disable_keyboard_controls = True
            recorder_options.start_paused = True

            param_callback_group = rclpy.callback_groups.MutuallyExclusiveCallbackGroup()
            param_client = rclpy.parameter_client.AsyncParameterClient(
                node,
                params.controller_name,
                callback_group=param_callback_group,
            )
            logger.info(f"Waiting for {params.controller_name}'s parameter services")
            param_client.wait_for_services()

            param_prefix = params.parameter_prefix

            continue_service: Optional[ContinueService] = None
            if params.manual_mode:
                continue_service = ContinueService(node)

            recorder = rosbag2_py.Recorder()
            record_thread = None
            for new_params in product(*parameter_iterators):
                param_future = param_client.set_parameters(
                    [
                        rclpy.Parameter(name=f'{param_prefix}.{name}', value=value)
                        for name, value in new_params
                    ],
                )

                exc.spin_until_future_complete(param_future)
                param_results = param_future.result()
                for result in param_results.results:
                    if not result.successful:
                        raise RuntimeError(f'Unable to set parameters: {result.reason}')

                # NOTE: START RECORDING

                date = None
                if len(storage_location.parts[-1]) > 15:
                    maybe_date = storage_location.parts[-1][-15:]
                    try:
                        datetime.fromisoformat(maybe_date[:10])
                        date = maybe_date
                    except ValueError:
                        pass

                prefix = None
                if date is None:
                    prefix = storage_location.parts[-1]
                else:
                    prefix = storage_location.parts[-1][:-16]

                if date is not None:
                    prefix = f"{date[:10].replace('-', '')}-{prefix}"

                # FIXME
                filename = '{}-{}-{}'.format(
                    datetime.now().time().isoformat(timespec='seconds').replace(':', ''),
                    prefix,
                    param_prefix,
                )

                for name, value in new_params:
                    filename += f'-{name}-{value:03.02E}'.replace('.', '_')

                for name, value in new_params:
                    custom_data[f'{param_prefix}.{name}'] = str(value)

                custom_data['recording_date'] = datetime.now().isoformat(
                    timespec='seconds',
                )

                measurement_duration_locals = {
                    'measurement_duration': params.measurement_duration,
                }
                measurement_duration_locals.update(new_params)
                recording_duration = eval(
                    params.measurement_duration_modifier,
                    measurement_duration_locals,
                )
                custom_data['recording_duration'] = str(recording_duration)

                storage_options = rosbag2_py.StorageOptions(
                    str(storage_location / filename),
                    storage_id='mcap',
                    storage_preset_profile='zstd_fast',
                    custom_data=custom_data.copy(),
                )

                if continue_service is not None:
                    continue_service.wait_for_ready(exc)

                record_thread = threading.Thread(
                    target=recorder.record,
                    args=(
                        storage_options,
                        recorder_options,
                    ),
                    daemon=True,
                )
                record_thread.start()
                # NOTE: Need to wait at least 1.5 seconds for rosbag recorder to discover
                #       all topics. Otherwise the the initial seconds will not be recorded!
                time.sleep(2)
                recorder.resume()

                if recording_duration != params.measurement_duration:
                    logger.warning(
                        'The measurement duration was modified by the modifier'
                        ' (Consider increasing the measurement time)\n'
                        f" [Original: '{params.measurement_duration}',"
                        f" modified by '{params.measurement_duration_modifier}',"
                        f" resulting: '{recording_duration}']",
                    )

                with active_controller(node, params.controller_name, controller_manager):
                    task = exc.create_task(time.sleep, recording_duration)
                    logger.info(
                        'Started recording with %s'
                        % ' '.join(sorted(f'{k} = {v}' for k, v in new_params)),
                    )

                    exc.spin_until_future_complete(task)
                    assert task.done()
                    recorder.pause()

                recorder.cancel()
                logger.info('Stopped Recording')
                record_thread.join()
        finally:
            if recorder is not None:
                recorder.cancel()
            if record_thread is not None:
                if record_thread.is_alive():
                    record_thread.join()
            node.destroy_node()

    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
