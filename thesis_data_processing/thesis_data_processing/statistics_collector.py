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
# limitations under the License
from decimal import Decimal
from typing import assert_type, Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from types import ModuleType

    from pal_statistics_msgs.msg import StatisticsNames
    from pal_statistics_msgs.msg import StatisticsValues

    logging: ModuleType

try:
    import colorlog as logging
except ImportError:
    import logging

logger = logging.getLogger(__name__)


class StatisticsCollector:
    """A class to recombine 'statistics/names' and 'statistics/values'."""

    def __init__(self, base_topic: str) -> None:
        assert base_topic[-1] != '/', f"Invalid base topic '{base_topic}' must not end with '/'"
        assert not base_topic.endswith('/full'), (
            f"Invalid base topic '{base_topic}' must not end with '/full'"
        )
        assert not base_topic.endswith('/names'), (
            f"Invalid base topic '{base_topic}' must not end with '/names'"
        )
        assert not base_topic.endswith('/values'), (
            f"Invalid base topic '{base_topic}' must not end with '/values'"
        )
        self.__base_topic = base_topic
        self.__min_names_verion: Optional[int] = None
        self.__max_names_verion: Optional[int] = None
        self.__names: list[tuple['StatisticsNames', set[str]]] = []
        self.__values: list['StatisticsValues'] = []
        self.__data: pd.DataFrame = pd.DataFrame()  # columns=['time']
        self.__data.index.name = 'time'

        self.__processed_values_until: Optional[int] = None
        self.__processed_names_until: Optional[int] = None

    @property
    def base_topic(self) -> str:
        return self.__base_topic

    @property
    def names_topic(self) -> str:
        return f'{self.base_topic}/names'

    @property
    def values_topic(self) -> str:
        return f'{self.base_topic}/values'

    @property
    def min_names_version(self) -> Optional[int]:
        return self.__min_names_verion

    @property
    def max_names_version(self) -> Optional[int]:
        return self.__max_names_verion

    @property
    def topics(self) -> set[str]:
        return {self.names_topic, self.values_topic}

    def fully_processed(self) -> bool:
        if self.__processed_values_until is None and len(self.__values) == 0:
            return True
        else:
            return self.__processed_values_until == len(self.__values)

    @property
    def data(self) -> pd.DataFrame:
        if not self.fully_processed():
            assert self._update_dataframe()

        return self.__data

    def process_msg(
        self,
        topic: str,
        msg: 'StatisticsNames | StatisticsValues',
        try_process: bool = True,
    ):
        assert topic.startswith(self.base_topic), (
            "The provided topic '%s' is not part of this StatisticsCollector [base_topic = '%s']"
            % (topic, self.base_topic)
        )

        match topic.removeprefix(self.base_topic):
            case '/names':
                assert_type(msg, 'StatisticsNames')
                self._process_names_msg(msg)
            case '/values':
                assert_type(msg, 'StatisticsValues')
                self._process_values_msg(msg, try_process)
            case unknown_subtopic:
                raise ValueError(
                    "Unexpected topic '%s%s' (subtopic: '%s')"
                    % (self.base_topic, unknown_subtopic, unknown_subtopic),
                )

    def _process_names_msg(self, msg: 'StatisticsNames') -> None:
        if self.min_names_version is None:
            self.__min_names_verion = msg.names_version
            self.__max_names_verion = msg.names_version
            self.__names.append((msg, set()))
            self.__processed_names_until = 0
        elif self.max_names_version < msg.names_version:
            self.__max_names_verion = msg.names_version
            old_names = set(self.__names[-1][0].names)
            old_dropped = self.__names[-1][1]
            new_names = set(msg.names)

            not_returned = old_dropped - new_names

            self.__names.append((msg, not_returned | (old_names - new_names)))
        else:
            logger.warning(
                "Recieved new names for '%s', but the version has not increased. Skipping",
                self.base_topic,
            )
            return

        logger.info(
            "Recieved new names for '%s' with version %d",
            self.base_topic,
            self.max_names_version,
        )

    def _process_values_msg(self, msg: 'StatisticsValues', try_process: bool = True) -> None:
        # NOTE: Assert to make MyPy happy, and ensure assumptions are correct.
        assert self.min_names_version is not None
        assert self.max_names_version is not None

        if msg.names_version not in range(self.min_names_version, self.max_names_version + 1):
            logger.warning(
                "Recieved new values for '%s', with unknown names version. (%d not in [%d, %d])",
                self.base_topic,
                msg.names_version,
                self.min_names_version,
                self.max_names_version,
            )
            try_process = False

        self.__values.append(msg)
        if try_process:
            self._update_dataframe()

    def _update_dataframe(self) -> bool:
        """Update the internal DataFrame.

        Returns:
            bool: True if up-to-date
        """
        if self.__processed_values_until is None:
            if self.min_names_version is not None:
                self.__processed_values_until = 0
            else:
                logger.warning('Cannot process values without names, skipping')
                return False

        # NOTE: Assert to make MyPy happy, and ensure assumptions are correct.
        assert self.__processed_names_until is not None
        assert self.min_names_version is not None
        assert self.max_names_version is not None

        while self.__processed_values_until < len(self.__values):
            msg = self.__values[self.__processed_values_until]
            if msg.names_version not in range(self.min_names_version, self.max_names_version + 1):
                logger.warning(
                    'Skipping because of missing names version %d (recieved versions [%d, %d])',
                    msg.names_version,
                    self.min_names_version,
                    self.max_names_version,
                )
                return False

            if self.__processed_names_until <= msg.names_version - self.min_names_version:
                while self.__processed_names_until < len(self.__names):
                    if not self._update_dataframe_headers():
                        return False

            msg_time = Decimal(f'{msg.header.stamp.sec}.{msg.header.stamp.nanosec:0>9}')
            new_data = {name: float('nan') for name in self.__data.columns}
            new_data |= dict(
                zip(self.__names[msg.names_version - self.min_names_version][0].names, msg.values),
            )

            self.__data.loc[msg_time] = new_data
            self.__processed_values_until += 1

        return True

    def _update_dataframe_headers(self) -> bool:
        """Add new headers to the internal DataFrame.

        Returns:
            bool: True if up-to-date
        """
        if self.__processed_names_until is None:
            logger.error(
                "Cannot update columns for '%s', since no names are recieved yet.",
                self.base_topic,
            )
            return False
        if self.__processed_names_until >= len(self.__names):
            logger.warning(
                "Skipping updating columns of '%s', since they are up-to-date.",
                self.base_topic,
            )
            return True
        current_names_msgs, _ = self.__names[self.__processed_names_until]

        # if current_names_msgs
        for name in current_names_msgs.names:
            columns = self.__data.columns
            if name not in columns:
                self.__data.insert(len(columns), name, None)

        self.__processed_names_until += 1
        return True
