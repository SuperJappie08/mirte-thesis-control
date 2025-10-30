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
from decimal import Decimal
import itertools
import math
from pathlib import Path
from pprint import pprint  # noqa: F401
from typing import cast, Optional, TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rosbag2_py import StorageFilter
from rosbag2_py import StorageOptions
from tqdm.auto import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from . import arguments
from . import CONTROLLER_MANAGER_DIAGNOSTIC_NAME_MAPPING
from . import create_config
from . import DataConsistencyChecker
from . import DiagnosticsCollector
from . import open_rosbag
from . import plot_utils
from . import PlotOutputManager
from . import read_messages
from . import StatisticsCollector
from . import SYSTEM_DIAGNOSTIC_NAME_MAPPING
from . import utils

if TYPE_CHECKING:
    from types import ModuleType

    from builtin_interfaces.msg import Time as MsgTime
    from controller_manager_msgs.msg import ControllerManagerActivity
    from controller_manager_msgs.msg import NamedLifecycleState
    from rosbag2_py import BagMetadata

    logging: ModuleType

try:
    import colorlog
    logging = colorlog
except ImportError:
    import logging


logger = logging.getLogger(__name__)


STEP_COMMAND_KEY = 'step.step_command'
T_STEP_KEY = 'step.t_step'
INITIAL_COMMAND_KEY = 'step.initial_commmand'
RECORDING_DURATION_KEY = 'recording_duration'

MIRTE_HW_ID = 'Mirte-867B16'

AVG_CPU_LOAD_COL = f'{MIRTE_HW_ID}.cpu-monitor.CPU Load Average'
AVG_RAM_LOAD_COL = f'{MIRTE_HW_ID}.ram-monitor.RAM Load Average'


def get_trial_data(data_folder: Path) -> tuple[int, list[Decimal], pd.DataFrame]:
    logger.info("Checking which trials are run in '%s'", data_folder)

    param_df = pd.DataFrame(columns=['t_step', 'initial_command', 'recording_duration'])
    param_df.index.name = 'step_command'

    trials: dict[Decimal, int] = {}
    for rosbag_path in tqdm(sorted(data_folder.glob('*')), desc='Bags'):
        with open_rosbag(StorageOptions(uri=str(rosbag_path))) as reader:
            step_command = Decimal(reader.get_metadata().custom_data[STEP_COMMAND_KEY])

            param_df.loc[step_command, 't_step'] = \
                Decimal(reader.get_metadata().custom_data[T_STEP_KEY])
            param_df.loc[step_command, 'initial_command'] = \
                Decimal(reader.get_metadata().custom_data[INITIAL_COMMAND_KEY])

            recording_duration = reader.get_metadata().custom_data.get(RECORDING_DURATION_KEY)
            param_df.loc[step_command, 'recording_duration'] = \
                Decimal(recording_duration) if recording_duration is not None else None

            trials[step_command] = trials.get(step_command, 0) + 1

    assert len(set(trials.values())) == 1, 'All trials should be run an equal amount of times'
    max_trials = set(trials.values()).pop()
    trial_idxs = list(trials.keys())

    param_df = param_df.sort_index().copy(deep=True)

    return max_trials, trial_idxs, param_df


def create_dataframes(
    data_folder: Path,
    wheel_names: set[str],
    command_interfaces: set[str],
    trials: set[Decimal],
    max_trials: int,
    names_to_keep: Optional[set[str]] = None,
    diagnostics_name_mapping: Optional[dict[str, str]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate dataframes for a series of step response trials.

    :param data_folder: Path to the folder containing the rosbags
    :type  data_folder: Path
    :param wheel_names: The names of the wheels to include
    :type  wheel_nanes: set[str]
    :param command_interfaces: The names of the command interfaces to include
    :type  command_interfaces: set[str]
    :param trials: The trial stepsizes
    :type  trials: set[Decimal]
    :param max_trials:  The amount that each trial step size has been tested
    :type  max_trials: int
    :param names_to_keep:  Names to keep when processing data. Defaults to None.
    :type  names_to_keep: Optional[set[str]], optional
    :param diagnostics_name_mapping:  Diagnostic name mapping. Defaults to None.
    :type  diagnostics_name_mapping: Optional[dict[str, str]], optional

    :returns: Data, Diagnostics
    :rtype: tuple[pd.DataFrame, pd.DataFrame]
    """
    datachecker = DataConsistencyChecker(
        excluded_keys=('recording_duration', 'recording_date', STEP_COMMAND_KEY),
    )

    storage_filter = StorageFilter(
        topics=[
            '/controller_manager/introspection_data/names',
            '/controller_manager/introspection_data/values',
            '/controller_manager/activity',
            '/diagnostics',
            '/rosout',
        ],
        regex_to_exclude='.*/_service_event',
    )

    # Hardcoded variations
    data_df: pd.DataFrame = pd.DataFrame(
        columns=pd.MultiIndex.from_product([
            wheel_names,
            sorted(trials),
            tuple(range(max_trials)),
            ('command', 'state'),
        ],
            names=['wheel', 'step size', 'trial number', 'signal'],
        ),
    )
    data_df.index.name = 'time'
    diagnostics_data_df: Optional[pd.DataFrame] = None

    trials_idxs: dict[Decimal, int] = {}
    with logging_redirect_tqdm(tqdm_class=tqdm):
        for rosbag_path in tqdm(sorted(data_folder.glob('*')), desc='Bags'):
            logger.info("Processing '%s'", str(rosbag_path.stem))
            with open_rosbag(StorageOptions(uri=str(rosbag_path))) as reader:
                metadata: 'BagMetadata' = reader.get_metadata()

                custom_metadata = deepcopy(metadata.custom_data)
                custom_metadata['ros_distro'] = metadata.ros_distro

                assert datachecker.check(custom_metadata), \
                    f"Bag '{rosbag_path.stem}' is inconsistent!"

                step_command = Decimal(custom_metadata[STEP_COMMAND_KEY])
                t_step = Decimal(custom_metadata[T_STEP_KEY])
                initial_command = Decimal(custom_metadata[INITIAL_COMMAND_KEY])

                controller_name = custom_metadata.get('controller_name',
                                                      'multi_wheel_step_controller')

                statistics_collector = StatisticsCollector(
                    '/controller_manager/introspection_data',
                    only_names=names_to_keep,
                )

                diagnostics_collector = DiagnosticsCollector(
                    name_mapping=diagnostics_name_mapping,
                )

                start_activity_time: 'Optional[MsgTime]' = None
                accepting_data: bool = False
                for topic, msg, recv_time in read_messages(reader, storage_filter):
                    if topic == '/rosout' and msg.name == 'controller_manager' and \
                            msg.msg == f'Activating controllers: [ {controller_name} ]':
                        start_activity_time = msg.stamp
                    elif topic.endswith('/activity'):
                        controller_status: 'NamedLifecycleState' = next(
                            filter(
                                lambda controller: controller.name == controller_name,
                                cast('ControllerManagerActivity', msg).controllers,
                            ),
                        )

                        # TODO: Maybe do this the time stamps instead to prevent different ordering
                        accepting_data = controller_status.state.id == utils.LIFECYCLE_ACTIVE_ID
                        logger.info(
                            "%s recording data on '%s'",
                            'Started' if accepting_data else 'Stopped',
                            statistics_collector.base_topic,
                        )
                    elif topic.startswith(statistics_collector.base_topic) and (
                        accepting_data or topic.endswith('/names')
                    ):
                        statistics_collector.process_msg(topic, msg, try_process=False)
                    elif topic == '/diagnostics':
                        diagnostics_collector.process_msg(msg, try_process=False)

                assert start_activity_time is not None

                bag_df = statistics_collector.data.copy(True)
                diagnostics_df = diagnostics_collector.data.copy(True)
                # First attempt to synchronize based on activation
                bag_df.index = bag_df.index - utils.as_time(start_activity_time)
                diagnostics_df.index = diagnostics_df.index - utils.as_time(start_activity_time)

                # NOTE: In order to average multiple measurements it is necessary to index them
                #       exactly. Therefore we assume that the first reported
                #       To achieve this its assumed all command velocities are the equal.
                some_command_interface = next(iter(command_interfaces))
                assert (bag_df[list(command_interfaces)]).eq(
                    bag_df.loc[:, some_command_interface], axis=0,
                ).all(1).all(), 'All command signals should have an equal t_step'

                measured_command_t_step = \
                    bag_df[bag_df[some_command_interface] != initial_command].index[0]
                bag_df.index = bag_df.index - measured_command_t_step + t_step
                bag_df.index = [
                    abs(round(idx, 2)) if round(idx, 2).is_zero() else round(idx, 2)
                    for idx in bag_df.index
                ]

                diagnostics_df.index = diagnostics_df.index - measured_command_t_step + t_step
                diagnostics_df.index = [
                    abs(round(idx, 2)) if round(idx, 2).is_zero() else round(idx, 2)
                    for idx in diagnostics_df.index
                ]

                # # Detect missing value messages.
                # if not (np.all(bag_df.index.diff()[1:].array == Decimal('0.05'))):
                #     print(bag_df[
                #         (bag_df.index.diff() != Decimal('0.05')) |
                #         np.roll(bag_df.index.diff() != Decimal('0.05'), 1) |
                #         np.roll(bag_df.index.diff() != Decimal('0.05'), -1)])

                trial_number = trials_idxs.get(step_command, 0)
                trials_idxs[step_command] = trial_number + 1

                trial_selector = (step_command, trial_number)
                for wheel_name in wheel_names:
                    wheel_selector = (wheel_name, *trial_selector)
                    logger.info("Processing '%s' @ step command %s # %d", *wheel_selector)

                    data_df.loc[:, (*wheel_selector, 'command')] = \
                        bag_df[f'command_interface.{wheel_name}/velocity']
                    data_df.loc[:, (*wheel_selector, 'state')] = \
                        bag_df[f'state_interface.{wheel_name}/velocity']

                if diagnostics_data_df is None:
                    diagnostics_data_df = pd.DataFrame(
                        columns=pd.MultiIndex.from_product([
                            sorted(trials),
                            tuple(range(max_trials)),
                            diagnostics_df.columns.array.copy(),
                        ],
                            names=['step size', 'trial number', 'data'],
                        ),
                        index=pd.Index([], name='time'),
                    )

                diagnostics_append_df = utils.create_empty_append_df(
                    column_iterable=[(step_command,), (trial_number,), diagnostics_df.columns],
                    target_df=diagnostics_data_df,
                    source_df=diagnostics_df,
                )

                for column in diagnostics_df.columns:
                    diagnostics_append_df.loc[:, (*trial_selector, column)] = \
                        diagnostics_df[column]

                diagnostics_data_df = utils.append_df(
                    target_df=diagnostics_data_df,
                    append_df=diagnostics_append_df,
                    selector=(*trial_selector, slice(None)),
                )

                assert diagnostics_df.count().sum() == \
                    diagnostics_data_df.loc[:, (*trial_selector, slice(None))].count().sum()

                diagnostics_data_df = diagnostics_data_df.copy()

    assert diagnostics_data_df is not None
    diagnostics_data_df = diagnostics_data_df.dropna(how='all').copy(deep=True)

    return data_df, diagnostics_data_df


# TODO: Take Y bounds as arguments
# TODO: Optional RAM
def plot_system_usage(
    param_df: pd.DataFrame,
    diagnostics_data_df: pd.DataFrame,
    plt_mgr: PlotOutputManager = PlotOutputManager(),
) -> None:
    PLOT_STEP_KWARGS = {
        'where': 'mid',
        'marker': '.',
    }

    for step_command in param_df.index.array:
        local_df = cast(pd.DataFrame, diagnostics_data_df[step_command]).dropna(how='all')

        t_step = cast(Decimal, param_df.loc[step_command, 't_step'])
        recording_duration = cast(Decimal, param_df.loc[step_command, 'recording_duration'])

        fig, [ax_cpu, ax_ram] = plt.subplots(2, sharex=True)
        assert isinstance(ax_cpu, plt.Axes)
        assert isinstance(ax_ram, plt.Axes)

        # CPU
        ax_cpu.set_title('Average CPU Load')

        ax_cpu.axvline(t_step, label='Step event', color='grey', linestyle='--')

        for trial_idx in local_df.columns.unique(0):
            local_cpu_series = cast(pd.Series, local_df[trial_idx][AVG_CPU_LOAD_COL])\
                .dropna(how='all')
            if local_cpu_series.index.array[0] < Decimal('0'):
                local_cpu_series.index.array[0] = Decimal('0')
            if local_cpu_series.index.array[-1] < recording_duration:
                local_cpu_series[recording_duration] = local_cpu_series.iloc[-1]
            ax_cpu.step(
                local_cpu_series.index,
                local_cpu_series.astype(np.float64),
                label=f'Trial {trial_idx + 1}',
                **PLOT_STEP_KWARGS,
            )

        ax_cpu.set_ylabel('CPU Load Average (%)')
        # ax_cpu.set_ylim(0, 100)
        # ax_cpu.tick_params('x', labelbottom=True)

        # RAM
        ax_ram.set_title('Average RAM Load')

        ax_ram.axvline(t_step, label='Step event', color='grey', linestyle='--')

        for trial_idx in local_df.columns.unique(0):
            local_ram_series = cast(pd.Series, local_df[trial_idx][AVG_RAM_LOAD_COL])\
                .dropna(how='all')
            if local_ram_series.index.array[0] < Decimal('0'):
                local_ram_series.index.array[0] = Decimal('0')
            if local_ram_series.index.array[-1] < recording_duration:
                local_ram_series[recording_duration] = local_ram_series.iloc[-1]
            ax_ram.step(
                local_ram_series.index,
                local_ram_series.astype(np.float64),
                label=f'Trial {trial_idx + 1}',
                **PLOT_STEP_KWARGS,
            )

        ax_ram.set_ylabel('RAM Load Average (%)')
        # ax_ram.set_ylim(0, 100)
        ax_ram.set_xlabel('Time (s)')

        if plt_mgr.display_plots:
            plt.suptitle(f'System usage - step size {step_command:01}')

        plot_utils.deduped_figure_legend(fig, loc='center right')
        figure_name = f'system-cpu-ram-{step_command}'
        plt_mgr.output(fig, fname=figure_name, block=False)


def main(args: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        'step_response',
        description='Use on a folder of created data to make analyze step response behavior.')
    parser.add_argument(
        'folder',
        type=Path, metavar='FOLDER',
        help='The folder containing the rosbags')

    plot_system_usage_group = parser.add_argument_group('Plot System Usage')
    plot_system_usage_group.add_argument(
        '-U', '--plot-system-usage',
        action='store_true', required=False,
        help='Enable system usage plots')

    arguments.add_global_plotting_arguments(parser)

    parsed_args = parser.parse_args(args)

    # Process arguments
    plt_mgr = PlotOutputManager(parsed_args.save_plots)

    # Plotting arguments
    do_plot_system_usage: bool = parsed_args.plot_system_usage

    # Data settings
    data_folder: Path = cast(Path, parsed_args.folder).expanduser().absolute()

    assert data_folder.is_dir(), "The specified 'FOLDER' must be a folder containing rosbags"
    plt_mgr /= data_folder.name[:-(utils.FULL_DATETIME_LENGTH + 1)]

    if plt_mgr.save_path is not None:
        create_config(
            basepath=plt_mgr.save_path,
            data_folder=data_folder,
            args=parsed_args,
        )

    wheel_names: set[str] = {
        f'{fb_pos}_{side}_wheel_joint'
        for fb_pos, side in itertools.product(('front', 'rear'), ('left', 'right'))
    }

    state_interfaces: set[str] = {
        f'state_interface.{wheel_name}/velocity'
        for wheel_name in wheel_names
    }

    command_interfaces: set[str] = {
        f'command_interface.{wheel_name}/velocity'
        for wheel_name in wheel_names
    }

    names_to_keep: set[str] = state_interfaces | command_interfaces

    max_trial, trials, param_df = get_trial_data(data_folder)

    diagnostics_name_mapping = {}
    diagnostics_name_mapping.update(CONTROLLER_MANAGER_DIAGNOSTIC_NAME_MAPPING)
    diagnostics_name_mapping.update(SYSTEM_DIAGNOSTIC_NAME_MAPPING)

    data_df, diagnostics_data_df = create_dataframes(
        data_folder=data_folder,
        wheel_names=wheel_names,
        command_interfaces=command_interfaces,
        trials=set(trials),
        max_trials=max_trial,
        names_to_keep=names_to_keep,
        diagnostics_name_mapping=diagnostics_name_mapping,
    )

    if do_plot_system_usage:
        if np.isin(
            diagnostics_data_df.columns.unique('data').array,
            [AVG_CPU_LOAD_COL, AVG_RAM_LOAD_COL],
        ).sum() == 2:
            logger.info('Plotting system usage data')
            plot_system_usage(
                param_df=param_df,
                diagnostics_data_df=diagnostics_data_df,
                plt_mgr=plt_mgr / 'diagnostics',
            )
        else:
            logger.error('Plotting of system usage data was requested, '
                         'however data is missing. SKIPPING!')

    for (step_command, wheel_name) in itertools.product(trials, wheel_names):
        logger.info('%s %s', wheel_name, step_command)
        trials_df: pd.DataFrame = data_df[wheel_name][step_command]

        # NOTE: Make a custom figure to enable plotting the command first
        fig, ax = plt.subplots()
        plt_kwargs = {
            'ax': ax,
            'use_index': True,
            'legend': False,
        }

        mean_command: pd.Series = trials_df.loc[:, (slice(None), 'command')].mean(axis=1)
        mean_command.plot.line(**plt_kwargs, label='Command', color='grey')

        trials_df.loc[:, (slice(None), 'state')].plot.line(**plt_kwargs, linestyle=':')
        for idx, line in enumerate(ax.get_lines()[1:], start=1):
            line.set_label(f'State {idx}')

        mean_state: pd.Series = trials_df.loc[:, (slice(None), 'state')].mean(axis=1)
        mean_state.plot.line(**plt_kwargs, label='State (avg)')

        plt.xlabel('Time (s)')
        plt.ylabel('Velocity (rad/s)')
        plt.legend()
        if plt_mgr.display_plots:
            plt.suptitle(wheel_name)
            plt.title(step_command)

        figure_name = f'{wheel_name.replace("_", "-")}-{step_command}'
        plt_mgr.output(fig, fname=figure_name, block=False)

    plt_mgr.show_all()

    # NOTE(SuperJappie08): Some data is missing, but it is not critical for this measurement
    data_dict = {
        (*k, vk): vv
        for k, v in data_df.to_dict().items()
        for vk, vv in v.items()
        if not math.isfinite(vv)
    }
    data_dict_unique_sorted = sorted(
        filter(
            lambda n: n[0][0] == sorted(wheel_names)[0] and n[0][3] == 'command',
            data_dict.items(),
        ),
        key=lambda n: n[0][-1],
    )

    assert len(data_dict) == 8*len(data_dict_unique_sorted), 'Unequally Missing data'
    # pprint(data_dict_unique_sorted, width=120)

    # TODO(SuperJappie08): Do something with the data, it is all there, it is packed a bit weird.
    if False:
        pprint(
            sorted((index, row.count()) for (index, row) in diagnostics_data_df.items()),
            width=160,
        )

    raise NotImplementedError()
