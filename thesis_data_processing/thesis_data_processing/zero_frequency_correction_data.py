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
from decimal import Decimal
import itertools
from pathlib import Path
from typing import cast, Optional, TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd

from . import arguments
from . import CONTROLLER_MANAGER_DIAGNOSTIC_NAME_MAPPING
from . import create_config
from . import PlotOutputManager
from . import step_response
from . import SYSTEM_DIAGNOSTIC_NAME_MAPPING
from . import utils

if TYPE_CHECKING:
    from types import ModuleType

    logging: ModuleType

try:
    import colorlog
    logging = colorlog
except ImportError:
    import logging


logger = logging.getLogger(__name__)


def get_average_step_run(data_df: pd.DataFrame) -> pd.DataFrame:
    """
    Average multi trial step response runs over their trial number.

    :param data_df: Path to the folder containing the rosbags
    :type  data_df: pd.DataFrame

    :returns: Averaged trials with same step size
    :rtype: pd.DataFrame
    """
    assert 'trial number' in data_df.columns.names, 'There must be a trial number sub column'

    avg_df = pd.DataFrame(
        columns=data_df.columns.droplevel('trial number').drop_duplicates(),
        index=data_df.index,
    )

    for (wheel_name, step_size, signal) in avg_df.columns:
        avg_df.loc[:, (wheel_name, step_size, signal)] = \
            data_df.loc[:, (wheel_name, step_size, slice(None), signal)].mean(axis=1)

    return avg_df


def get_cosinus_zero_gain(
    avg_df: pd.DataFrame,
    param_df: pd.DataFrame,
    wheel_names: set[str],
) -> pd.DataFrame:
    """
    Calculate the zero frequency cosine magnitude.

    :param avg_df: Averaged data per step size
    :type  avg_df: pd.DataFrame
    :param param_df: the step trial parameter data
    :type  param_df: pd.DataFrame
    :param wheel_names: The wheel names
    :type  wheel_names: set[str]

    :returns: The average zero frequency output per step size.
              (columns = [step_sizes], index = [wheel_names])
    :rtype: pd.DataFrame
    """
    zero_gain_df = pd.DataFrame(
        columns=sorted(wheel_names),
        index=param_df.index,
    )

    for step_command in param_df.index:
        for wheel_name in sorted(wheel_names):
            t_step = cast(Decimal, param_df.loc[step_command, 't_step'])
            rec_duration = cast(Decimal, param_df.loc[step_command, 'recording_duration'])

            step_df: pd.DataFrame = avg_df[wheel_name][step_command]

            assert rec_duration == step_df.index.max()
            rec_duration -= t_step
            step_df.index -= t_step

            buffer = rec_duration / 6

            usable_selector = (step_df.index >= buffer) & (step_df.index <= rec_duration - buffer)
            zero_gain_df[wheel_name][step_command] = step_df.loc[usable_selector, 'state'].mean()

    return zero_gain_df.T


def main(args: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        'zero_frequency_correction_data',
        description='Use on a data folder to extract the zero frequency gain/offset data.')
    parser.add_argument(
        'folder',
        type=Path, metavar='FOLDER',
        help='The folder containing the rosbags')
    parser.add_argument(
        '--save-output',
        action='store', required=False,
        type=Path, metavar='OUTPUT_FOLDER',
        help='Folder to save offset data file in. The filename is the bag filename')

    plot_step_response_group = parser.add_argument_group('Plot Average Step Respone')
    plot_step_response_group.add_argument(
        '-p', '--plot-step',
        action='store_true', required=False,
        help='Enable average step response plot')

    arguments.add_global_plotting_arguments(parser)

    parsed_args = parser.parse_args(args)

    # Process arguments
    plt_mgr = PlotOutputManager(parsed_args.save_plots)

    # Plotting arguments
    do_plot_step_response: bool = parsed_args.plot_step

    # Data settings
    data_folder: Path = cast(Path, parsed_args.folder).expanduser().absolute()

    output_path: Optional[Path] = (
        cast(Path, parsed_args.save_output).expanduser().absolute()
        if parsed_args.save_output is not None
        else None
    )

    assert data_folder.is_dir(), "The specified 'FOLDER' must be a folder containing rosbags"
    plt_mgr /= data_folder.name[:-(utils.FULL_DATETIME_LENGTH + 1)]

    if output_path is not None:
        output_path.mkdir(parents=True, exist_ok=True)
        assert output_path.is_dir(), "The save 'OUTPUT_FOLDER' must be a folder"
        output_path /= data_folder.name + '.pkl'

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

    max_trial, trials, param_df = step_response.get_trial_data(data_folder)

    diagnostics_name_mapping = {}
    diagnostics_name_mapping.update(CONTROLLER_MANAGER_DIAGNOSTIC_NAME_MAPPING)
    diagnostics_name_mapping.update(SYSTEM_DIAGNOSTIC_NAME_MAPPING)

    data_df, diagnostics_data_df = step_response.create_dataframes(
        data_folder=data_folder,
        wheel_names=wheel_names,
        command_interfaces=command_interfaces,
        trials=set(trials),
        max_trials=max_trial,
        names_to_keep=names_to_keep,
        diagnostics_name_mapping=diagnostics_name_mapping,
    )

    avg_df = get_average_step_run(data_df)

    zero_gain_df = get_cosinus_zero_gain(
        avg_df=avg_df,
        param_df=param_df,
        wheel_names=wheel_names,
    )

    if do_plot_step_response:
        for (step_command, wheel_name) in itertools.product(trials, wheel_names):
            logger.info('%s %s', wheel_name, step_command)
            trials_df: pd.DataFrame = avg_df[wheel_name][step_command]

            # NOTE: Make a custom figure to enable plotting the command first
            fig, ax = plt.subplots()
            assert isinstance(ax, plt.Axes)
            plt_kwargs = {
                'ax': ax,
                'use_index': True,
                'legend': False,
            }

            ax._get_lines.get_next_color()
            trials_df.loc[:, 'state'].plot.line(**plt_kwargs, label='State (avg)')

            trials_df.loc[:, 'command'].plot.line(**plt_kwargs, label='Command', color='grey')

            t_step = param_df.loc[step_command, 't_step']
            recording_duration = param_df.loc[step_command, 'recording_duration']
            buffer = (recording_duration - t_step) / 6

            ax.hlines(
                y=zero_gain_df[step_command][wheel_name],
                xmin=trials_df.index.get_loc(t_step + buffer),
                xmax=trials_df.index.get_loc(recording_duration - buffer),
                label='Zero Cosine Average',
                linewidths=2.0,
            )

            plt.xlabel('Time (s)')
            plt.ylabel('Velocity (rad/s)')
            plt.legend()
            if plt_mgr.display_plots:
                plt.suptitle(wheel_name)
                plt.title(step_command)

            figure_name = f'{wheel_name.replace("_", "-")}-{step_command}'
            plt_mgr.output(fig, fname=figure_name, block=False)

    print(zero_gain_df)

    if output_path is not None:
        logger.info("Writing data to '%s'", str(output_path))
        zero_gain_df.to_pickle(output_path)

    plt_mgr.show_all()

    return 0
