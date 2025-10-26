# Copyright 2025 Jasper van Brakel
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

from collections.abc import Container, Iterable, Mapping
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    logging: ModuleType

try:
    import colorlog
    logging = colorlog
except ImportError:
    import logging

logger = logging.getLogger(__name__)


class DataConsistencyChecker(Container):
    """A class to check if multiple data sources are consistent."""

    def __init__(self, excluded_keys: Optional[Iterable[str]] = None) -> None:
        self._excluded_keys: set[str] = set(excluded_keys) if excluded_keys else set()
        self._data: dict[str, Any] = {}

    def __contains__(self, x) -> bool:
        if x in self.excluded_keys:
            return False
        return x not in self._excluded_keys and x in self._data

    @property
    def excluded_keys(self) -> frozenset[str]:
        return frozenset(self._excluded_keys)

    def check(self, new_data: Mapping[str, Any]) -> bool:
        for key, value in new_data.items():
            if key in self.excluded_keys:
                continue
            if key in self:
                if self._data[key] != value:
                    logger.critical(
                        "Found conflicting key '%s'. Expected: '%s', but found '%s'",
                        key,
                        str(self._data[key]),
                        str(value),
                    )
                    return False
            else:
                logger.info(
                    "Inserting '%s' with value '%s' into the checker",
                    key,
                    str(value) if len(str(value)) <= 25 else '...',
                )
                self._data[key] = value
        return True
