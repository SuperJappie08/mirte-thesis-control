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

import enum
from itertools import chain
from operator import attrgetter
from typing import cast, Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from types import ModuleType

    from diagnostic_msgs.msg import DiagnosticArray
    from diagnostic_msgs.msg import DiagnosticStatus
    from diagnostic_msgs.msg import KeyValue

    logging: ModuleType

try:
    import colorlog
    logging = colorlog
except ImportError:
    import logging

from . import utils

logger = logging.getLogger(__name__)


@enum.verify(enum.CONTINUOUS)
@enum.unique
class DiagnosticsLevel(enum.Enum):
    OK = 0
    WARN = 1
    ERROR = 2
    STALE = 3


CONTROLLER_MANAGER_DIAGNOSTIC_NAME_MAPPING: dict[str, str] = {
    'controller_manager: Controller Manager Activity': 'cm-cm-activity',
    'controller_manager: Controllers Activity': 'cm-cr-activity',
    'controller_manager: Hardware Components Activity': 'cm-hw-activity',
}

SYSTEM_DIAGNOSTIC_NAME_MAPPING: dict[str, str] = {
    'cpu_monitor: CPU Information': 'cpu-monitor',
    'ram_monitor: RAM Information': 'ram-monitor',
}


class DiagnosticsCollector:
    """A class to collect diagnostics messages."""

    def __init__(
        self,
        name_mapping: Optional[dict[str, str]] = None,
        excluded_hardware_ids: Optional[set[str]] = None,
    ):
        self.__ignored_hw_ids = excluded_hardware_ids or set()
        self.__name_mapping = name_mapping or {}

        self.__raw_data: list['DiagnosticArray'] = []
        self.__data: pd.DataFrame = pd.DataFrame()
        self.__data.index.name = 'time'

        self.__processed_data_until: Optional[int] = None

    @property
    def hardware_ids(self) -> set[str]:
        raise NotImplementedError()

    @property
    def ignored_hardware_ids(self) -> set[str]:
        return self.__ignored_hw_ids

    def fully_processed(self) -> bool:
        if self.__processed_data_until is None and len(self.__raw_data) == 0:
            return True
        else:
            return self.__processed_data_until == len(self.__raw_data)

    @property
    def data(self) -> pd.DataFrame:
        if not self.fully_processed():
            assert self._update_dataframe()

        self.__data = self.__data.reindex(sorted(self.__data.columns), axis=1)

        return self.__data

    def process_msg(self, msg: 'DiagnosticArray', try_process: bool = True) -> None:
        self.__raw_data.append(msg)

        if try_process:
            self._update_dataframe()

    def _update_dataframe(self) -> bool:
        if self.__processed_data_until is None:
            self.__processed_data_until = 0

        while self.__processed_data_until < len(self.__raw_data):
            msg = self.__raw_data[self.__processed_data_until]
            msg_time = utils.as_time(msg.header.stamp)

            if not self._update_dataframe_headers():
                return False

            new_data = dict.fromkeys(self.__data.columns)

            for status in msg.status:
                assert not TYPE_CHECKING or isinstance(status, DiagnosticStatus)

                if status.hardware_id in self.ignored_hardware_ids:
                    continue

                hardware_id = cast(str, status.hardware_id)
                name = self._get_remapped_name(status.name)
                message = cast(str, status.message)

                new_data[f'{hardware_id}.{name}.message'] = message.strip()
                new_data[f'{hardware_id}.{name}.level'] = DiagnosticsLevel(status.level[0])

                for item in status.values:
                    assert not TYPE_CHECKING or isinstance(item, KeyValue)
                    key = cast(str, item.key)
                    value = cast(str, item.value)

                    new_data[f'{hardware_id}.{name}.{key}'] = value.strip()

            if new_data:
                self.__data.loc[msg_time] = new_data
            else:
                logger.info("Data for '/diagnostics' at %s was all ignored, skipping.", msg_time)
            self.__processed_data_until += 1

        return True

    def _update_dataframe_headers(self) -> bool:
        """
        Add new headers to the internal DataFrame.

        :returns bool: True if up-to-date
        """
        if self.__processed_data_until is None:
            logger.error(
                "Cannot update columns of '/diagnostics', since data has not been received yet.")
            return False
        if self.__processed_data_until >= len(self.__raw_data):
            logger.warning(
                "Skipping updating columns of '/diagnostics', since they are up-to-date.")
            return True
        current_msg = self.__raw_data[self.__processed_data_until]

        for status in current_msg.status:
            assert not TYPE_CHECKING or isinstance(status, DiagnosticStatus)

            hardware_id = cast(str, status.hardware_id)
            name = self._get_remapped_name(status.name)

            if hardware_id in self.ignored_hardware_ids:
                continue

            for key in chain(('message', 'level'), map(attrgetter('key'), status.values)):
                columns = self.__data.columns
                column_name = f'{hardware_id}.{name}.{key}'

                if column_name not in columns and self._include_entry(hardware_id, name, key):
                    self.__data.insert(len(columns), column_name, None)

        return True

    def _get_remapped_name(self, name: str) -> str:
        return self.__name_mapping.get(name, name)

    def _include_entry(self, hardware_id: str, name: str, key: str) -> bool:
        return hardware_id not in self.__ignored_hw_ids
