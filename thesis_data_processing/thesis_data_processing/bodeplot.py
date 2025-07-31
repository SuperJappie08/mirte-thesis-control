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
import itertools
from pathlib import Path
from typing import cast, Optional, TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rosbag2_py import StorageFilter
from rosbag2_py import StorageOptions
from scipy.optimize import curve_fit
from tqdm.auto import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

if TYPE_CHECKING:
    from types import ModuleType

    from controller_manager_msgs.msg import ControllerManagerActivity
    from controller_manager_msgs.msg import NamedLifecycleState
    from rosbag2_py import BagMetadata

    logging: ModuleType

try:
    import colorlog

    logging = colorlog
except ImportError:
    import logging

# LIFECYCLE_ACTIVE_ID is hard-coded, but if the messages are available, it will be verified.
try:
    LIFECYCLE_ACTIVE_ID: int = 3
    from lifecycle_msgs.msg import State

    assert LIFECYCLE_ACTIVE_ID == State.PRIMARY_STATE_ACTIVE
except ImportError:
    pass


from . import DataConsistencyChecker
from . import open_rosbag
from . import read_messages
from . import StatisticsCollector

logger = logging.getLogger(__name__)

FREQUENCY_KEY = 'sinusoid.frequency'
AMPLITUDE_KEY = 'sinusoid.amplitude'
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
            '/controller_manager/activity',
        ],
        regex_to_exclude='.*/_service_event',
    )

    wheel_names: set[str] = {
        f'{fb_pos}_{side}_wheel_joint'
        for fb_pos, side in itertools.product(('front', 'rear'), ('left', 'right'))
    }

    names_to_keep: set[str] = {
        f'{interface}_interface.{wheel_name}/velocity'
        for interface, wheel_name in itertools.product(('command', 'state'), wheel_names)
    }

    bode_df: pd.DataFrame = pd.DataFrame(
        columns=pd.MultiIndex.from_product([wheel_names, ('gain', 'phase')]),
    )
    bode_df.index.name = 'frequency'

    for rosbag_path in tqdm(sorted(data_folder.glob('*')), desc='Bags'):
        logger.info("Processing '%s'", str(rosbag_path.stem))
        with (
            open_rosbag(StorageOptions(uri=str(rosbag_path))) as reader,
            logging_redirect_tqdm(tqdm_class=tqdm),
        ):
            metadata: 'BagMetadata' = reader.get_metadata()

            custom_metadata = deepcopy(metadata.custom_data)
            custom_metadata['ros_distro'] = metadata.ros_distro

            assert datachecker.check(custom_metadata), f"Bag '{rosbag_path.stem}' is inconsistent!"

            frequency = float(custom_metadata[FREQUENCY_KEY])
            amplitude = float(custom_metadata[AMPLITUDE_KEY])
            offset = float(custom_metadata[OFFSET_KEY])

            # total_msg_count = sum(
            #     topic_metadata.message_count
            #     for topic_metadata in metadata.topics_with_message_count
            #     if topic_metadata.topic_metadata.name in storage_filter.topics
            # )

            # NOTE: There is a default as fallback, since first preliminary recording did not store
            #       this data.
            controller_name = custom_metadata.get(
                'controller_name',
                'multi_wheel_response_controller',
            )

            statistics_collector = StatisticsCollector(
                '/controller_manager/introspection_data',
                only_names=names_to_keep,
            )

            accepting_data: bool = False
            for topic, msg, recv_time in read_messages(reader, storage_filter):
                # tqdm( ,total=total_msg_count, position=1, desc='Messages'):
                if topic.endswith('/activity'):
                    controller_status: 'NamedLifecycleState' = next(
                        filter(
                            lambda controller: controller.name == controller_name,
                            cast('ControllerManagerActivity', msg).controllers,
                        ),
                    )

                    # TODO: Maybe do this the time stamps instead to prevent different ordering
                    accepting_data = controller_status.state.id == LIFECYCLE_ACTIVE_ID
                    logger.info(
                        "%s recording data on '%s'",
                        'Started' if accepting_data else 'Stopped',
                        statistics_collector.base_topic,
                    )

                if topic.startswith(statistics_collector.base_topic) and (
                    accepting_data or topic.endswith('/names')
                ):
                    statistics_collector.process_msg(topic, msg, try_process=False)

            bag_df = statistics_collector.data.copy(True)
            bag_df.index = bag_df.index - bag_df.index.min()

            xdata = bag_df.index.to_numpy(dtype=np.float64)
            bode_df.loc[frequency] = {
                wheel_name: dict.fromkeys(('gain', 'phase'), np.nan) for wheel_name in wheel_names
            }

            for wheel_name in wheel_names:
                interface_name = f'state_interface.{wheel_name}/velocity'

                ydata = bag_df[interface_name].to_numpy(dtype=np.float64)

                angular_frequency = 2.0 * np.pi * frequency
                f = lambda x, gain, phase: (  # noqa: E731
                    gain * amplitude * np.sin(angular_frequency * x + phase) + offset
                )
                (gain, phase), _ = curve_fit(
                    f,
                    xdata[5:-5],
                    ydata[5:-5],
                    np.array([1.0, 0.0]),
                    bounds=([0.0, -2 * np.pi], [np.inf, 2 * np.pi]),
                )

                print(wheel_name, frequency, gain, amplitude, gain / amplitude)
                bode_df.loc[frequency, (wheel_name, 'gain')] = gain
                bode_df.loc[frequency, (wheel_name, 'phase')] = phase

                if False:
                    plt.plot(
                        xdata[5:-5],
                        bag_df[f'command_interface.{wheel_name}/velocity'].to_numpy(
                            dtype=np.float64
                        )[5:-5],
                        label='command',
                    )
                    plt.plot(xdata[5:-5], ydata[5:-5], label='measurement')
                    plt.plot(xdata[5:-5], f(xdata[5:-5], gain, phase), label='fit')
                    plt.xticks(xdata[5:-5:100])
                    plt.xlabel('Time (s)')
                    plt.ylabel('speed (rad/s)')
                    plt.legend()
                    plt.show()

    # FIXME: ADD DATA EXPORT MODES (So make plot, save plot, save data)
    for idx, wheel_name in enumerate(wheel_names):
        title_wheel_name = wheel_name.removesuffix('_joint').replace('_', ' ')
        fig, [ax_gain, ax_phase] = plt.subplots(2, 1, sharex=True)
        assert isinstance(ax_gain, plt.Axes)
        assert isinstance(ax_phase, plt.Axes)

        ax_gain.set_title(f'{title_wheel_name} -- Gain')
        ax_gain.set_xscale('log')
        ax_gain.set_yscale('log')
        ax_gain.grid(True, axis='both', which='both')
        # ax_gain.plot(
        #     bode_df.index.to_numpy(),
        #     np.log(bode_df.loc[:, (wheel_name, 'gain')].to_numpy())/np.log(20.0),
        #     '-o',
        # )
        ax_gain.plot(
            bode_df.index.to_numpy(),
            bode_df.loc[:, (wheel_name, 'gain')].to_numpy(),
            '-o',
        )

        ax_phase.set_title(f'{title_wheel_name} -- Phase')
        ax_phase.set_xscale('log')
        ax_phase.grid(True, axis='both', which='both')
        ax_phase.plot(bode_df.index, np.rad2deg(bode_df.loc[:, (wheel_name, 'phase')]), '-o')

        plt.show(block=(idx + 1 == len(wheel_names)))

    raise NotImplementedError()
