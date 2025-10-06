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

from pathlib import Path
from typing import TYPE_CHECKING

import rclpy
import rclpy.node

if TYPE_CHECKING:
    from rclpy.logging import RcutilsLogger as Logger


def wait_for_node(
    node: rclpy.node.Node,
    logger: 'Logger',
    other_node_name: str,
    timeout: float = -1.0,
) -> None:
    other_node = (
        other_node_name
        if other_node_name.startswith('/')
        else node.get_namespace().lstrip('/') + '/' + other_node_name
    )
    logger.info(f"Waiting for node '{other_node}'")
    if not node.wait_for_node(other_node, timeout=timeout):
        raise TimeoutError(
            f"Timed out waiting for node '{other_node}' after {timeout} seconds",
        )


def setup_storage_location(logger: 'Logger', storage_location: str) -> Path:
    storage_location_path = Path(storage_location).expanduser().absolute()

    if storage_location_path.exists() and not storage_location_path.is_dir():
        logger.fatal(
            f"The storage path '{storage_location_path}' exists, but is not a folder!",
        )
        raise FileExistsError(
            f"The storage path '{storage_location_path}' exists, but is not a folder!",
        )

    if not storage_location_path.exists():
        logger.info(f'Creating folder {storage_location_path}')
        storage_location_path.mkdir(parents=True, exist_ok=True)

    return storage_location_path
