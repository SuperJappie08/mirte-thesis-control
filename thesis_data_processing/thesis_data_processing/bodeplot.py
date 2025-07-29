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

import argparse
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import cast, Optional, TYPE_CHECKING

import numpy as np
from rosbag2_py import StorageFilter
from rosbag2_py import StorageOptions
from scipy.optimize import curve_fit
from tqdm.auto import tqdm

if TYPE_CHECKING:
    from types import ModuleType

    from rosbag2_py import BagMetadata

    logging: ModuleType

try:
    import colorlog as logging
except ImportError:
    import logging

from . import DataConsistencyChecker
from . import open_rosbag
from . import read_messages
from . import StatisticsCollector

logger = logging.getLogger(__name__)

FREQUENCY_KEY = 'sinusoid.frequency'
OFFSET_KEY = 'sinusoid.offset'


def main(args: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        'bodeplotter',
        description='Use on a folder of created data to make a bodeplot',
    )
    parser.add_argument(
        'folder',
        type=Path,
        help='The folder containing the rosbags',
        metavar='FOLDER',
    )

    parsed_args = parser.parse_args(args)
    data_folder: Path = cast(Path, parsed_args.folder).absolute()

    assert data_folder.is_dir(), "The speficied 'FOLDER' must be a folder containing rosbags"

    datachecker = DataConsistencyChecker(
        excluded_keys=('recording_duration', 'recording_date', FREQUENCY_KEY),
    )

    storage_filter = StorageFilter(
        topics=[
            '/controller_manager/introspection_data/names',
            '/controller_manager/introspection_data/values',
        ],
        regex_to_exclude='.*/_service_event',
    )

    for rosbag_path in sorted(data_folder.glob('*')):
        logger.info("Processing '%s'", str(rosbag_path.stem))
        with open_rosbag(StorageOptions(uri=str(rosbag_path))) as reader:
            metadata: 'BagMetadata' = reader.get_metadata()

            custom_metadata = deepcopy(metadata.custom_data)
            custom_metadata['ros_distro'] = metadata.ros_distro

            assert datachecker.check(custom_metadata), f"Bag '{rosbag_path.stem}' is inconsistent!"

            frequency = float(custom_metadata[FREQUENCY_KEY])
            offset = float(custom_metadata[OFFSET_KEY])

            total_msg_count = sum(
                topic_metadata.message_count
                for topic_metadata in metadata.topics_with_message_count
                if topic_metadata.topic_metadata.name in storage_filter.topics
            )

            statistics_collector = StatisticsCollector('/controller_manager/introspection_data')

            for topic, msg, recv_time in tqdm(
                read_messages(reader, storage_filter),
                total=total_msg_count,
            ):
                # print(topic, type(topic))
                # print(msg, type(msg))
                # print(recv_time, type(recv_time))

                statistics_collector.process_msg(topic, msg, try_process=True)

            print(statistics_collector.data)
            break

            xdata = 0
            ydata = 0

            angular_frequency = 2.0 * np.pi * frequency
            curve_fit(
                lambda x, gain, phase: gain * np.sin(angular_frequency * x + phase) + offset,
                xdata,
                ydata,
                np.zeros(2),
            )

    raise NotImplementedError()
