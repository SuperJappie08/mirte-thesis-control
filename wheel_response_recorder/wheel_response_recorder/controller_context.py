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

import contextlib
import threading
from typing import Generator

from controller_manager.controller_manager_services import switch_controllers
from controller_manager_msgs.srv import SwitchController
from deprecated import deprecated
from rclpy.node import Node


@deprecated(category=PendingDeprecationWarning, reason="use 'active_controller' instead")
class ControllerContext(contextlib.AbstractContextManager):
    def __init__(
        self,
        node: Node,
        controller: str,
        controller_manager: str = 'controller_manager',
    ):
        self._node = node
        self._controller_manager_name = controller_manager
        self._logger = node.get_logger().get_child('controller_switcher')
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


@contextlib.contextmanager
def active_controller(
        node: Node, controller: str,
        controller_manager: str = 'controller_manager') -> Generator[None, None, None]:
    logger = node.get_logger().get_child('controller_switcher')
    logger.info(f"Activating controller '{controller}'")
    result: SwitchController.Response = switch_controllers(
        node=node,
        controller_manager_name=controller_manager,
        activate_controllers=[controller],
        deactivate_controllers=[],
        strictness=SwitchController.Request.FORCE_AUTO,
        activate_asap=True,
        timeout=0,
    )
    assert result.ok

    try:
        yield
    finally:
        logger.info(f"Deactivating controller '{controller}'")
        result: SwitchController.Response = switch_controllers(
            node=node,
            controller_manager_name=controller_manager,
            activate_controllers=[],
            deactivate_controllers=[controller],
            strictness=SwitchController.Request.FORCE_AUTO,
            activate_asap=True,
            timeout=0,
        )

        assert result.ok
