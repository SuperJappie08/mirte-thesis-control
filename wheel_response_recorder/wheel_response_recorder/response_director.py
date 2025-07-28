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

import threading
import time
import platform
import itertools

from datetime import datetime
from pathlib import Path
from deprecated import deprecated
from contextlib import AbstractContextManager

from tqdm.contrib.itertools import product as tqdm_product

import rclpy
import rclpy.callback_groups
import rclpy.client
import rclpy.executors
import rclpy.node
import rclpy.parameter_client

from rcl_interfaces.msg import ParameterDescriptor, ParameterType
from rclpy.logging import RcutilsLogger as Logger

import rosbag2_py
from controller_manager.controller_manager_services import (
    list_hardware_components,
    switch_controllers,
)

from controller_manager_msgs.srv import SwitchController, ListHardwareComponents

from wheel_response_recorder.parameter_iterator import ParameterIterator
from wheel_response_recorder.response_director_parameters import (
    response_director as response_director_parameters,
)


def wait_for_node(
    node: rclpy.node.Node,
    logger: Logger,
    other_node_name: str,
    timeout: float = -1.0,
) -> None:
    other_node = (
        other_node_name
        if other_node_name.startswith("/")
        else node.get_namespace().lstrip("/") + "/" + other_node_name
    )
    logger.info(f"Waiting for node '{other_node}'")
    if not node.wait_for_node(other_node, timeout=timeout):
        raise TimeoutError(
            f"Timed out waiting for node '{other_node}' after {timeout} seconds"
        )


@deprecated(
    reason="Probably better to use 'controller_manager.controller_services.service_caller'"
)
def retry_call(
    executor: rclpy.executors.Executor,
    logger: Logger,
    client: rclpy.client.Client,
    request,
    retries: int = 3,
    timeout_sec: float = 5.0,
):
    if not client.wait_for_service(timeout_sec=timeout_sec):
        raise TimeoutError(
            f"Time out reached waiting for '{client.service_name}' service"
        )

    try_number = 0

    while try_number <= retries or retries < 0:
        future = client.call_async(request)

        executor.spin_until_future_complete(future, timeout_sec)

        if future.done():
            if (result := future.result()) is not None:
                return result
            else:
                raise future.exception()
        future.cancel()
        logger.warning(
            f"[{try_number}/{retries}] Failed to call service '{client.service_name}' within {timeout_sec} seconds."
        )
        try_number += 1
    logger.error(f"Failed to call service '{client.name}' within {retries} tries")
    raise RuntimeError(f"Failed to call service '{client.name}' within {retries} tries")


class ControllerContext(AbstractContextManager):
    def __init__(
        self,
        node: rclpy.node.Node,
        controller: str,
        controller_manager_name: str = "controller_manager",
    ):
        self._node = node
        self._controller_manager_name = controller_manager_name
        self._logger = node.get_logger().get_child("controller_switcher")
        self._controller_name = controller
        self._lock = threading.Lock()

    def __enter__(self):
        assert self._lock.acquire()
        self._logger.info(f"Activating controller '{self._controller_name}'")
        result: SwitchController.Response = switch_controllers(
            node=self._node,
            controller_manager_name=self._controller_manager_name,
            activate_controllers=[self._controller_name],
            deactivate_controllers=[],
            strictness=SwitchController.Request.FORCE_AUTO,
            activate_asap=True,
            timeout=0,
        )

        assert result.ok
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        self._logger.info(f"Deactivating controller '{self._controller_name}'")
        result: SwitchController.Response = switch_controllers(
            node=self._node,
            controller_manager_name=self._controller_manager_name,
            activate_controllers=[],
            deactivate_controllers=[self._controller_name],
            strictness=SwitchController.Request.FORCE_AUTO,
            activate_asap=True,
            timeout=0,
        )

        self._lock.release()
        assert result.ok
        return super().__exit__(exc_type, exc_value, traceback)


SRV_POSTFIX: str = "/_service_event"


def main(args=None):
    rclpy.init(args=args, signal_handler_options=rclpy.SignalHandlerOptions.NO)
    # rclpy.executors.MultiThreadedExecutor()
    with rclpy.get_global_executor() as exc:
        recorder = None
        record_thread = None
        try:
            node = rclpy.create_node("response_director")
            logger: Logger = node.get_logger()
            exc.add_node(node)

            node.declare_parameter(
                name="recorded_services",
                value=rclpy.Parameter.Type.STRING_ARRAY,
                descriptor=ParameterDescriptor(
                    description="Services to record",
                    read_only=True,
                    type=ParameterType.PARAMETER_STRING_ARRAY,
                ),
            )

            node.declare_parameter(
                name="recorded_topics",
                value=rclpy.Parameter.Type.STRING_ARRAY,
                descriptor=ParameterDescriptor(
                    description="Extra topics to record",
                    read_only=True,
                    type=ParameterType.PARAMETER_STRING_ARRAY,
                ),
            )

            param_listener = response_director_parameters.ParamListener(node)
            params = param_listener.get_params()

            controller_manager_name = "controller_manager"

            node_timeout = params.node_timeout

            wait_for_node(node, logger, "io/telemetrix", timeout=node_timeout)
            wait_for_node(node, logger, controller_manager_name, timeout=node_timeout)
            wait_for_node(node, logger, params.controller_name, timeout=node_timeout)

            product = tqdm_product if params.progressbar else itertools.product

            offset = ParameterIterator("offset", params.sinusoid)
            amplitude = ParameterIterator("amplitude", params.sinusoid)
            frequency = ParameterIterator("frequency", params.sinusoid)
            phase = ParameterIterator("phase", params.sinusoid)

            controller_context_manager = ControllerContext(
                node,
                params.controller_name,
                controller_manager_name=controller_manager_name,
            )

            storage_location = Path(params.storage_location).expanduser().absolute()

            if storage_location.exists() and not storage_location.is_dir():
                logger.fatal(
                    f"The storage path '{storage_location}' exists, but is not a folder!"
                )
                raise FileExistsError(
                    f"The storage path '{storage_location}' exists, but is not a folder!"
                )

            if not storage_location.exists():
                logger.info(f"Creating folder {storage_location}")
                storage_location.mkdir(parents=True, exist_ok=True)

            custom_data = {"host": platform.node()}
            for key, value in platform.uname()._asdict().items():
                custom_data[f"uname.{key}"] = str(value)

            hw_components: ListHardwareComponents.Response = list_hardware_components(
                node, controller_manager_name
            )
            custom_data["hw_interfaces"] = str(hw_components.component)

            custom_data["extra_notes"] = params.extra_notes

            recorder_options = rosbag2_py.RecordOptions()
            recorder_options.topics = list(
                set(
                    [
                        f"{params.controller_name}/transition_event",
                        f"{controller_manager_name}/activity",
                        f"{controller_manager_name}/introspection_data/full",
                        f"{controller_manager_name}/introspection_data/names",
                        f"{controller_manager_name}/introspection_data/values",
                        "/diagnostics",
                        "/rosout",
                    ]
                    + params.recorded_topics
                )
            )
            recorder_options.services = list(
                (service if service.endswith(SRV_POSTFIX) else service + SRV_POSTFIX)
                for service in params.recorded_services
            )
            recorder_options.disable_keyboard_controls = True

            param_callback_group = (
                rclpy.callback_groups.MutuallyExclusiveCallbackGroup()
            )
            param_client = rclpy.parameter_client.AsyncParameterClient(
                node, params.controller_name, callback_group=param_callback_group
            )
            logger.info(f"Waiting for {params.controller_name}'s parameter services")
            param_client.wait_for_services()

            recorder = rosbag2_py.Recorder()
            record_thread = None
            for new_params in product(offset, amplitude, frequency, phase):
                param_future = param_client.set_parameters(
                    [
                        rclpy.Parameter(name=f"sinusoid.{name}", value=value)
                        for name, value in new_params
                    ]
                )

                exc.spin_until_future_complete(param_future)
                param_results = param_future.result()
                for result in param_results.results:
                    if not result.successful:
                        raise RuntimeError(f"Unable to set parameters: {result.reason}")

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
                filename = f"{datetime.now().time().isoformat(timespec='seconds').replace(':', '')}-{prefix}-sinusoid"

                for name, value in new_params:
                    filename += f"-{name}-{value:03.02E}".replace(".", "_")

                for name, value in new_params:
                    custom_data[f"sinusoid.{name}"] = str(value)

                custom_data["recording_date"] = datetime.now().isoformat(
                    timespec="seconds"
                )

                recording_duration = max(
                    params.measurement_duration, 2 / dict(new_params)["frequency"]
                )
                custom_data["recording_duration"] = str(recording_duration)

                storage_options = rosbag2_py.StorageOptions(
                    str(storage_location / filename),
                    storage_id="mcap",
                    storage_preset_profile="zstd_fast",
                    custom_data=custom_data.copy(),
                )

                record_thread = threading.Thread(
                    target=recorder.record,
                    args=(
                        storage_options,
                        recorder_options,
                    ),
                    daemon=True,
                )
                record_thread.start()

                if recording_duration > params.measurement_duration:
                    logger.warning(
                        "Extended the measurement time to record atleast 2 cycles! (Consider increasing the measurement time)"
                    )

                with controller_context_manager as controller_ctx:
                    task = exc.create_task(time.sleep, recording_duration)
                    logger.info(
                        f"Started recording with {' '.join(sorted(f'{k} = {v}' for k, v in new_params))}"
                    )

                    exc.spin_until_future_complete(task)
                    assert task.done()

                recorder.cancel()
                logger.info("Stopped Recording")
                record_thread.join()
        finally:
            if recorder is not None:
                recorder.cancel()
            if record_thread is not None:
                if record_thread.is_alive():
                    record_thread.join()
            node.destroy_node()

    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
