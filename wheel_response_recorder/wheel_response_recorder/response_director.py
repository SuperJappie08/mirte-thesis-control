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

from typing import Optional
from contextlib import AbstractContextManager

from tqdm.contrib.itertools import product as tqdm_product

import rclpy
import rclpy.callback_groups
import rclpy.client
import rclpy.executors
import rclpy.node
import rclpy.parameter_client

from rclpy.logging import RcutilsLogger as Logger

import rosbag2_py
from controller_manager.controller_manager_services import (
    service_caller,
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
        executor: rclpy.executors.Executor | None = None,
        # logger: Logger,
        # client: rclpy.client.Client,
    ):
        self._node = node
        self._controller_manager_name = "controller_manager"
        self.executor = executor or node.executor
        self.logger = node.get_logger().get_child("controller_switcher")
        self.client = node.create_client(
            SwitchController, "controller_manager/switch_controller"
        )
        self.controller_name = controller
        self._lock = threading.Lock()

    def __enter__(self):
        assert self._lock.acquire()
        self.logger.info(f"Activating controller '{self.controller_name}'")
        result: SwitchController.Response = switch_controllers(
            node=self._node,
            controller_manager_name=self._controller_manager_name,
            activate_controllers=[self.controller_name],
            deactivate_controllers=[],
            strictness=SwitchController.Request.FORCE_AUTO,
            activate_asap=True,
            timeout=0
        )
        # retry_call(
        #     self.executor,
        #     self.logger,
        #     self.client,
        #     SwitchController.Request(
        #         activate_controllers=[self.controller_name],
        #         strictness=SwitchController.Request.FORCE_AUTO,
        #         activate_asap=True,
        #     ),
        # )

        assert result.ok
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        self.logger.info(f"Deactivating controller '{self.controller_name}'")
        result: SwitchController.Response = switch_controllers(
            node=self._node,
            controller_manager_name=self._controller_manager_name,
            activate_controllers=[],
            deactivate_controllers=[self.controller_name],
            strictness=SwitchController.Request.FORCE_AUTO,
            activate_asap=True,
            timeout=0,
        )
        # retry_call(
        #     self.executor,
        #     self.logger,
        #     self.client,
        #     SwitchController.Request(
        #         deactivate_controllers=[self.controller_name],
        #         strictness=SwitchController.Request.FORCE_AUTO,
        #     ),
        # )

        self._lock.release()
        assert result.ok
        return super().__exit__(exc_type, exc_value, traceback)


def main(args=None):
    rclpy.init(args=args, signal_handler_options=rclpy.SignalHandlerOptions.NO)
    # rclpy.executors.MultiThreadedExecutor()
    with rclpy.get_global_executor() as exc:
        try:
            node = rclpy.create_node("response_director")
            logger: Logger = node.get_logger()
            exc.add_node(node)

            param_listener = response_director_parameters.ParamListener(node)
            params = param_listener.get_params()

            # wait_for_node(node, logger, "io/telemetrix", timeout=params.node_timeout)
            # wait_for_node(node, logger, "controller_manager", timeout=params.node_timeout)
            # wait_for_node(node, logger, params.controller_name, timeout=params.node_timeout)

            product = tqdm_product if params.progressbar else itertools.product

            offset = ParameterIterator("offset", params.sinusoid)
            amplitude = ParameterIterator("amplitude", params.sinusoid)
            frequency = ParameterIterator("frequency", params.sinusoid)
            phase = ParameterIterator("phase", params.sinusoid)

            # set_controller_state_client = node.create_client(
            #     SwitchController, "controller_manager/switch_controller"
            # )
            controller_context_manager = ControllerContext(node, params.controller_name)

            # FIXME: LOCATION
            storage_options = rosbag2_py.StorageOptions(uri="/tmp/recordings")
            storage_options.custom_data["host"] = platform.node()

            hw_client = node.create_client(
                ListHardwareComponents, "controller_manager/list_hardware_components"
            )

            hw_components: ListHardwareComponents.Response = retry_call(
                exc, logger, hw_client, ListHardwareComponents.Request()
            )
            storage_options.custom_data["hw_interfaces"] = str(hw_components.component)

            recorder_options = rosbag2_py.RecordOptions()
            recorder_options.topics = list(
                set(
                    [
                        f"{params.controller_name}/transition_event",
                        "controller_manager/activity",
                        "controller_manager/introspection_data/full",
                        "controller_manager/introspection_data/names",
                        "controller_manager/introspection_data/values",
                        "/diagnostics",
                        "/rosout",
                    ]
                    + params.recorded_topics
                )
            )
            recorder_options.services = params.recorded_services
            recorder_options.disable_keyboard_controls = True

            param_callback_group = (
                rclpy.callback_groups.MutuallyExclusiveCallbackGroup()
            )
            param_client = rclpy.parameter_client.AsyncParameterClient(
                node, params.controller_name, callback_group=param_callback_group
            )
            logger.info(f"Waiting for {params.controller_name}'s parameter services")
            param_client.wait_for_services()

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

                # TODO: START RECORDING

                for name, value in new_params:
                    storage_options.custom_data[name] = str(value)

                # recorder = rosbag2_py.Recorder(storage_options, recorder_options)
                # exc.add_node(recorder)

                with controller_context_manager as controller_ctx:
                    task = exc.create_task(time.sleep, params.measurement_duration)
                    print("Start recording")
                    exc.spin_until_future_complete(task)
                    assert task.done()

                # print(o, a, f, p)
        finally:
            node.destroy_node()

    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
