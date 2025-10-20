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

from typing import Optional, TYPE_CHECKING

import rclpy
import rclpy.task
from std_srvs.srv import Trigger

if TYPE_CHECKING:
    from rclpy.executors import Executor
    from rclpy.node import Node


class ContinueService:

    def __init__(self, node: 'Node'):
        self._service = node.create_service(Trigger, '~/continue', self._continue_srv_callback)
        self._ready: bool = False
        self._future: Optional[rclpy.task.Future] = None
        self._logger = node.get_logger().get_child('continue_service')

    def _continue_srv_callback(
            self,
            request: Trigger.Request,
            response: Trigger.Response) -> Trigger.Response:
        if not self.ready:
            response.success = False
            response.message = 'The continue service is not ready'
        else:
            self._future.set_result(None)
            self._ready = False
            response.success = True

        return response

    @property
    def ready(self) -> bool:
        return self._ready

    def wait_for_ready(self, executor: 'Executor', *, timeout_sec: Optional[float] = None) -> bool:
        self._ready = True
        self._future = rclpy.task.Future()

        self._logger.warning("Waiting for call on '%s'" % self._service.service_name)

        executor.spin_until_future_complete(self._future, timeout_sec)

        return self._future.done()
