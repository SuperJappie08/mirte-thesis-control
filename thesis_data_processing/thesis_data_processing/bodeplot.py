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
from pathlib import Path
from typing import cast, Literal, Optional, TYPE_CHECKING

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
    from typing import TypeAlias

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

from . import arguments
from . import create_config
from . import DataConsistencyChecker
from . import open_rosbag
from . import PlotOutputManager
from . import read_messages
from . import StatisticsCollector
from . import utils
from .conversions import gain2dB
from .export_utils import joint_name2plot

logger = logging.getLogger(__name__)

FREQUENCY_KEY = 'sinusoid.frequency'
AMPLITUDE_KEY = 'sinusoid.amplitude'
OFFSET_KEY = 'sinusoid.offset'
PHASE_OFFSET_KEY = 'sinusoid.phase'

TIME_DECIMAL_PLACES: int = 2

CORRECTION_FILE_PREFIX = 'step-freq-zero-correction-'

OffsetCompensationMethod: 'TypeAlias' = Literal['input', 'avg', 'avg-filtered', 'data']
OffsetCompensationData: 'TypeAlias' = Literal['input', 'avg', 'avg-filtered'] | pd.DataFrame


# TODO: Could make something generic that dynamically checks multiple keys
def get_trial_data(data_folder: Path) -> tuple[int, list[Decimal], pd.DataFrame]:
    logger.info("Checking which trials are run in '%s'", data_folder)

    param_df = pd.DataFrame(
        columns=['amplitude', 'phase offset', 'offset'],
    )
    param_df.index.name = 'frequency'

    trials: dict[Decimal, int] = {}
    for rosbag_path in tqdm(sorted(data_folder.glob('*')), desc='Bags'):
        with open_rosbag(StorageOptions(uri=str(rosbag_path))) as reader:
            frequency = Decimal(reader.get_metadata().custom_data[FREQUENCY_KEY])
            param_df.loc[frequency, 'amplitude'] = \
                Decimal(reader.get_metadata().custom_data[AMPLITUDE_KEY])
            param_df.loc[frequency, 'phase offset'] = \
                Decimal(reader.get_metadata().custom_data[PHASE_OFFSET_KEY])
            param_df.loc[frequency, 'offset'] = \
                Decimal(reader.get_metadata().custom_data[OFFSET_KEY])

            trials[frequency] = trials.get(frequency, 0) + 1

    assert len(set(trials.values())) == 1, 'All trials should be run an equal amount of times'
    max_trials = set(trials.values()).pop()
    trial_idxs = list(trials.keys())

    return max_trials, trial_idxs, param_df


def get_offset_compensation_data(
    compensation_mode: OffsetCompensationMethod,
    compensation_data_path: Optional[Path],
    data_foldername: str,
) -> OffsetCompensationData:
    if compensation_mode == 'data':
        if compensation_data_path is None:
            logger.critical("'CORRECTION_DATA' must be specified when using offset mode 'data'")
            exit(-1)

        assert compensation_data_path.is_file(), "The specified 'CORRECTION_DATA' must be a file"

        config_spec = '-'.join(data_foldername.rsplit('-')[-2:])
        filename = compensation_data_path.stem[:-(utils.FULL_DATETIME_LENGTH + 1)]
        if not (filename.startswith(CORRECTION_FILE_PREFIX) and filename.endswith(config_spec)):
            logger.warning(
                "The data file '%s' might not correspond with current configuration",
                compensation_data_path,
            )
            if not utils.prompt(
                f"The provided data '{filename}' does not correspond with "
                f"measurement ('{data_foldername}'). Continue anyway?",
                default=False,
            ):
                logger.critical('Aborting data processing')
                exit(-1)

        logger.info("Using offset compensation data from '%s'", compensation_data_path)

        return pd.read_pickle(compensation_data_path)
    else:
        logger.info("Using offset compensation mode '%s'", compensation_mode)
        if compensation_data_path is not None:
            logger.warning(
                "A correction data file was supplied, which is only used when the mode is 'data'. "
                "The mode specified mode is '%s'. IGNORING 'CORRECTION_DATA'!",
                compensation_mode,
            )

        return compensation_mode


def create_dataframes(
    data_folder: Path,
    wheel_names: set[str],
    trials: set[Decimal],
    names_to_keep: Optional[set[str]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    datachecker = DataConsistencyChecker(
        excluded_keys=('recording_duration', 'recording_date', FREQUENCY_KEY),
    )

    storage_filter = StorageFilter(
        topics=[
            '/controller_manager/introspection_data/names',
            '/controller_manager/introspection_data/values',
            '/controller_manager/activity',
            '/rosout',
        ],
        regex_to_exclude='.*/_service_event',
    )

    data_df: pd.DataFrame = pd.DataFrame(
        columns=pd.MultiIndex.from_product([
            wheel_names,
            sorted(trials),
            ('command', 'state'),
        ],
            names=['wheel', 'trial (frequency)', 'signal'],
        ),
        index=pd.Index([], dtype=object, name='time'),
        dtype=np.float64,
    )

    data_df.index.name = 'time'

    # TODO: Diagnostics DF

    with logging_redirect_tqdm(tqdm_class=tqdm):
        for rosbag_path in tqdm(sorted(data_folder.glob('*')), desc='Bags'):
            logger.info("Processing '%s'", str(rosbag_path.stem))
            with open_rosbag(StorageOptions(uri=str(rosbag_path))) as reader:
                metadata: 'BagMetadata' = reader.get_metadata()

                custom_metadata = deepcopy(metadata.custom_data)
                custom_metadata['ros_distro'] = metadata.ros_distro

                assert datachecker.check(custom_metadata), \
                    f"Bag '{rosbag_path.stem}' is inconsistent!"

                frequency = Decimal(custom_metadata[FREQUENCY_KEY])

                # NOTE: There is a default as fallback, since first preliminary recording did not
                #       store this data.
                controller_name = custom_metadata.get(
                    'controller_name',
                    'multi_wheel_response_controller',
                )

                statistics_collector = StatisticsCollector(
                    '/controller_manager/introspection_data',
                    only_names=names_to_keep,
                )

                start_activity_time: 'Optional[MsgTime]' = None
                accepting_data: bool = False
                for topic, msg, recv_time in read_messages(reader, storage_filter):
                    if topic == '/rosout' and msg.name == 'controller_manager' and \
                            msg.msg == f'Activating controllers: [ {controller_name} ]':
                        start_activity_time = msg.stamp

                    if topic.endswith('/activity'):
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

                    if topic.startswith(statistics_collector.base_topic) and (
                        accepting_data or topic.endswith('/names')
                    ):
                        statistics_collector.process_msg(topic, msg, try_process=False)

                assert start_activity_time is not None
                bag_df = statistics_collector.data.copy(True)
                bag_df.index = bag_df.index - utils.as_time(start_activity_time)

                # TODO: Could introduce better synchronization by command zero intersection.

                # NOTE(SuperJappie08): Rounding time does not work for this measurement.
                #                      It is also not necessary.

                append_df = utils.create_empty_append_df(
                    column_iterable=[sorted(wheel_names), (frequency,), ('command', 'state')],
                    target_df=data_df,
                    source_df=bag_df,
                    dtype=np.float64,
                )

                for wheel_name in wheel_names:
                    append_df.loc[:, (wheel_name, frequency, 'state')] = \
                        bag_df[f'state_interface.{wheel_name}/velocity']
                    append_df.loc[:, (wheel_name, frequency, 'command')] = \
                        bag_df[f'command_interface.{wheel_name}/velocity']

                data_df = utils.append_df(
                    target_df=data_df,
                    append_df=append_df,
                    selector=(slice(None), frequency, slice(None)),
                )

    data_df = data_df.dropna(how='all').copy(deep=True)

    return data_df, None


def fit_bode_data(
    wheel_names: set[str],
    param_df: pd.DataFrame,
    data_df: pd.DataFrame,
    phase_method,
    datarange_selector: slice = slice(None),
    offset_compensation_data: OffsetCompensationData = 'input',
    plt_mgr: PlotOutputManager = PlotOutputManager(),
    plot_all_frequencies: bool = False,
    plot_frequencies: Optional[np.ndarray] = None,
    remaining_plot_frequencies: list[float] = [],
    wheels_to_plot: str = 'all',
    debug_frequency_plot: bool = False,
) -> pd.DataFrame:

    bode_df = pd.DataFrame(
        columns=pd.MultiIndex.from_product([sorted(wheel_names), ('gain', 'phase')]),
        index=param_df.index.copy(deep=True),
        dtype=np.float64,
    )

    with logging_redirect_tqdm(tqdm_class=tqdm):
        previous_frequency: Optional[float] = None
        for frequency_key in tqdm(param_df.index):
            assert isinstance(frequency_key, Decimal)
            frequency = float(frequency_key)
            amplitude = float(param_df.loc[frequency_key, 'amplitude'])
            phase_offset = float(param_df.loc[frequency_key, 'phase offset'])
            offset_data = float(param_df.loc[frequency_key, 'offset'])

            do_plot = plot_frequencies is not None and (
                any(np.isclose(frequency, plot_frequencies)) or
                previous_frequency is not None and bool(remaining_plot_frequencies) and
                previous_frequency < frequency and frequency >= remaining_plot_frequencies[0])

            if do_plot:
                remaining_plot_frequencies.pop(0)

            previous_frequency = frequency

            for wheel_name in wheel_names:
                local_plt_mgr = plt_mgr / f'{wheel_name.replace("_", "-")}'
                local_df = cast(pd.DataFrame, data_df[wheel_name][frequency_key]).dropna(how='any')

                xdata = local_df.index.to_numpy(dtype=np.float64)
                ydata = local_df['state'].to_numpy(dtype=np.float64)

                sel_gain = (wheel_name, 'gain')
                sel_phase = (wheel_name, 'phase')

                offset = None
                match offset_compensation_data:
                    case _ if isinstance(offset_compensation_data, pd.DataFrame):
                        offset = \
                            offset_compensation_data[param_df['offset'][frequency_key]][wheel_name]
                    case 'input':
                        offset = offset_data
                    case 'avg':
                        offset = ydata.mean()
                    case 'avg-filtered':
                        lower_percentile = np.percentile(ydata, 25)
                        upper_percentile = np.percentile(ydata, 75)
                        iqr = (upper_percentile - lower_percentile)
                        offset = ydata[((lower_percentile - 1.5 * iqr) < ydata)
                                       & (ydata < (upper_percentile + 1.5 * iqr))].mean()

                assert offset is not None, 'Invalid offset componsation mode was provided'

                if phase_method == 'continuous':
                    initial_phase = (
                        0.0 if len(bode_df.loc[:, sel_phase].dropna()) < 2
                        else bode_df.loc[:, sel_phase].dropna().iat[-2]
                    )
                    max_phase = min(initial_phase + np.pi/2, 0)
                    min_phase = max_phase - 2*np.pi

                    if len(bode_df.loc[:, sel_phase]) < 2:
                        initial_phase = (max_phase + min_phase)/2
                else:
                    assert phase_method == 'zero'
                    initial_phase = 0.0
                    max_phase = np.pi
                    min_phase = -np.pi

                logger.debug(
                    "'%s' initial_phase %f [%f, %f] (range %f)",
                    wheel_name,
                    initial_phase,
                    min_phase,
                    max_phase,
                    max_phase-min_phase,
                )

                f = lambda x, gain, phase: (  # noqa: E731
                    # TODO(SuperJappie08): 20250916 Is phase shift location correct???
                    gain * amplitude * np.sin(frequency * 2.0 * np.pi * x + phase + phase_offset) \
                    + offset
                )
                (gain_scale, phase), _ = curve_fit(
                    f,
                    xdata[datarange_selector],
                    ydata[datarange_selector],
                    np.array([1.0, initial_phase]),
                    bounds=([0.0, min_phase], [np.inf, max_phase]),
                    nan_policy='omit',
                )

                bode_df.loc[frequency_key, sel_gain] = gain_scale
                bode_df.loc[frequency_key, sel_phase] = phase

                if (plot_all_frequencies or do_plot) and (
                        wheels_to_plot == 'all' or wheels_to_plot in wheel_name):
                    freq_plot_extra_fmt = {}
                    if debug_frequency_plot:
                        freq_plot_extra_fmt['marker'] = '.'

                    fig = plt.figure()
                    # TODO(SuperJappie08): Not Fully happy with this yet
                    plt.suptitle(f'{joint_name2plot(wheel_name)}{plt_mgr.configuration_title}')
                    plt.title(f'frequency = {frequency:.03} Hz, phase delay = {phase:.03} rad/s, '
                              f'gain = {gain_scale:.03}')
                    plt.plot(
                        xdata[datarange_selector],
                        local_df['command'].to_numpy(dtype=np.float64)[datarange_selector],
                        label='command',
                        **freq_plot_extra_fmt)
                    plt.plot(
                        xdata[datarange_selector],
                        ydata[datarange_selector],
                        label='measurement',
                        **freq_plot_extra_fmt)
                    plt.plot(
                        xdata[datarange_selector],
                        f(xdata[datarange_selector], gain_scale, phase),
                        label='fit',
                        **freq_plot_extra_fmt)

                    plt.xlabel('Time (s)')
                    plt.ylabel('speed (rad/s)')
                    plt.legend()

                    figure_name = f'{frequency_key}'

                    if local_plt_mgr.capturing_config:
                        local_plt_mgr[figure_name] = {
                            'ymin': plt.ylim()[0],
                            'ymax': plt.ylim()[1],
                        }
                    else:
                        plt.ylim(
                            bottom=local_plt_mgr.get((figure_name, 'ymin')),
                            top=local_plt_mgr.get((figure_name, 'ymax')),
                        )

                    local_plt_mgr.output(fig, fname=figure_name, block=False)

    return bode_df


def main(args: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        'bodeplotter',
        description='Use on a folder of created data to make a bodeplot')
    parser.add_argument(
        'folder',
        type=Path, metavar='FOLDER',
        help='The folder containing the rosbags')
    parser.add_argument(
        '-S', '--skip-samples',
        type=arguments.positive_int, required=False,
        help='Amount of samples to skip at the beginning and end. Can be omitted to use all data')

    plot_frequency_group = parser.add_argument_group('Frequency plot configuration')
    plot_frequency_select_group = plot_frequency_group.add_mutually_exclusive_group()
    plot_frequency_select_group.add_argument(
        '-f', '--plot-frequency',
        action='append', nargs='*',
        type=float, required=False,
        help='The frequencies of the trails to plot separately.')
    plot_frequency_select_group.add_argument(
        '-F', '--plot-all-frequencies', action='store_true',
        help='Plot the graphs at all frequencies.')
    plot_frequency_group.add_argument(
        '-w', '--plot-wheel',
        action='store', default='front_left',
        type=str, required=False,
        help=('Which wheels to plot the supplied frequencies for. '
              "'all' to plot all. Default is 'front_left'"))
    plot_frequency_group.add_argument(
        '-df', '--debug-frequency',
        action='store_true', required=False,
        help='Debug frequency plot style')

    bode_plot_group = parser.add_argument_group('Bode plot style')
    bode_plot_group.add_argument(
        '-d', '--drop-frequencies',
        type=arguments.positive_int, required=False,
        help='Amount of frequencies to drop starting from the end',
        default=1)  # Always dropping the last measurement as it is at least the nyquist frequency
    bode_plot_group.add_argument(
        '-m', '--magnitude-unit',
        choices=['dB', 'log'], default='dB',
        help='The units of the magnitude axis')
    bode_plot_group.add_argument(
        '-p', '--phase-unit',
        choices=['degrees', 'rad'], default='degrees',
        help='The units of the phase axis')
    bode_plot_group.add_argument(
        '-fu', '--frequency-unit',
        choices=['rad/s', 'Hz'], default='Hz',
        help='The units of the frequency axis')
    bode_plot_group.add_argument(
        '--phase-method',
        choices=['zero', 'continuous'], default='zero',
        help='How the phase is constraint during the calculations')

    offset_correction_group = parser.add_argument_group('Signal offset compensation')
    offset_correction_group.add_argument(
        '-ocm', '--offset-compensation-mode',
        choices=['input', 'avg', 'avg-filtered', 'data'], default='input',
        help='How to deal with an offset input signal.'
             " 'input': Match the offset of the input signal."
             " 'avg': Use the average of the signal as the offset."
             " 'avg-filtered': Use the average of the filtered signal."
             " 'data': Use external provided measurement data.")
    offset_correction_group.add_argument(
        '-cdf', '--correction-data-file',
        action='store', required=False,
        type=Path, metavar='CORRECTION_DATA',
        help="Correction data file for mode 'data'")

    arguments.add_global_plotting_arguments(parser)

    parsed_args = parser.parse_args(args)

    # Process arguments
    if parsed_args.save_only_plot_settings:
        assert parsed_args.save_plots is not None, \
            '--save-plots must also be provided when using --save-only-plot-settings'
        assert parsed_args.save_plot_settings, \
            '--save-plot-settings must also be provided when using --save-only-plot-settings'

    plt_mgr = PlotOutputManager(
        parsed_args.save_plots,
        force_display=parsed_args.save_only_plot_settings,
        config_mode='load' if parsed_args.load_plot_settings is not None else 'capture',
    )

    if parsed_args.load_plot_settings is not None:
        plot_settings_path: Path = parsed_args.load_plot_settings
        assert plot_settings_path.is_file(), \
            "The specified 'PLOT_SETTINGS' must be a valid plot settings file (pickle)"
        plt_mgr.load_config(plot_settings_path)

    datarange_selector = slice(
        parsed_args.skip_samples,
        -parsed_args.skip_samples if isinstance(parsed_args.skip_samples, int) else None,
    )

    # Frequency plot options
    plot_all_frequencies = parsed_args.plot_all_frequencies
    plot_frequencies = None
    remaining_plot_frequencies: list[float] = []
    if parsed_args.plot_frequency:
        plot_frequencies = np.asarray(
            sorted(itertools.chain.from_iterable(parsed_args.plot_frequency)), dtype=np.float64)
        remaining_plot_frequencies.extend(plot_frequencies.tolist())
    wheels_to_plot = parsed_args.plot_wheel
    debug_frequency_plot = parsed_args.debug_frequency

    if parsed_args.save_plot_settings and not (plot_all_frequencies and (wheels_to_plot == 'all')):
        logger.warning('Attempting to save plot values, while not all plots are enabled!')
        if not utils.prompt('Are you sure you want to continue?', default=False):
            exit()

    # Bode Plot Settings
    bodeplot_num_ignored_frequencies: int = parsed_args.drop_frequencies
    bodeplot_gain_scale: Literal['dB', 'log'] = parsed_args.magnitude_unit
    bodeplot_phase_scale: Literal['rad', 'degrees'] = parsed_args.phase_unit
    bodeplot_frequency_scale: Literal['rad/s', 'Hz'] = parsed_args.frequency_unit

    bodeplot_phase_method: Literal['zero', 'continuous'] = parsed_args.phase_method

    # Data settings
    data_folder: Path = cast(Path, parsed_args.folder).absolute()

    assert data_folder.is_dir(), "The specified 'FOLDER' must be a folder containing rosbags"
    plt_mgr /= data_folder.name[:-(utils.FULL_DATETIME_LENGTH + 1)]

    plt_mgr.configuration = data_folder  # type: ignore

    # Offset Compensation Settings
    offset_compensation_mode: OffsetCompensationMethod = parsed_args.offset_compensation_mode
    offset_compensation_data_path: Optional[Path] = (
        cast(Path, parsed_args.correction_data_file).expanduser().absolute()
        if parsed_args.correction_data_file is not None
        else None
    )

    offset_compensation_data: OffsetCompensationData = get_offset_compensation_data(
        compensation_mode=offset_compensation_mode,
        compensation_data_path=offset_compensation_data_path,
        data_foldername=data_folder.name[:-(utils.FULL_DATETIME_LENGTH + 1)],
    )

    # Save generation config
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

    names_to_keep: set[str] = {
        f'{interface}_interface.{wheel_name}/velocity'
        for interface, wheel_name in itertools.product(('command', 'state'), wheel_names)
    }

    max_trial, trials, param_df = get_trial_data(data_folder)

    data_df, diagnostics_data_df = create_dataframes(
        data_folder=data_folder,
        wheel_names=wheel_names,
        trials=set(trials),
        names_to_keep=names_to_keep,
    )

    bode_df = fit_bode_data(
        wheel_names=wheel_names,
        param_df=param_df,
        data_df=data_df,
        phase_method=bodeplot_phase_method,
        datarange_selector=datarange_selector,
        offset_compensation_data=offset_compensation_data,
        # Plotting parameters
        plt_mgr=plt_mgr / 'fit',
        plot_all_frequencies=plot_all_frequencies,
        plot_frequencies=plot_frequencies,
        remaining_plot_frequencies=remaining_plot_frequencies,
        wheels_to_plot=wheels_to_plot,
        debug_frequency_plot=debug_frequency_plot,
    )

    logger.info(f'\n{bode_df}')

    # FIXME: ADD DATA EXPORT MODES (So make plot, save plot, save data)
    for idx, wheel_name in enumerate(wheel_names):
        title_wheel_name = joint_name2plot(wheel_name)
        fig, [ax_gain, ax_phase] = plt.subplots(2, 1, sharex=True)
        assert isinstance(ax_gain, plt.Axes)
        assert isinstance(ax_phase, plt.Axes)

        fig.suptitle(f'Bode Plot - {title_wheel_name}{plt_mgr.configuration_title}')
        # TODO(SuperJappie08): Add subplot titles

        freq_selector = slice(None, -bodeplot_num_ignored_frequencies)
        frequency_axis = bode_df.index.to_numpy(dtype=np.float64)[freq_selector]

        # ax_gain.set_title('Magnitude Gain')
        ax_gain.set_xscale('log')
        ax_gain.grid(True, axis='both', which='both')

        match bodeplot_frequency_scale:
            case 'Hz':
                ax_phase.set_xlabel('Frequency [Hz]')
            case 'rad/s':
                frequency_axis = 2*np.pi*frequency_axis
                ax_phase.set_xlabel('Angular Frequency [rad/s]')

        match bodeplot_gain_scale:
            case 'log':
                ax_gain.set_yscale('log')
                ax_gain.set_ylabel('Magnitude Gain [-]')
                ax_gain.plot(
                    frequency_axis,
                    bode_df.loc[:, (wheel_name, 'gain')].to_numpy(dtype=np.float64)[freq_selector],
                    '-o',
                )
            case 'dB':
                ax_gain.set_yscale('linear')
                ax_gain.set_ylabel('Magnitude Gain [dB]')
                ax_gain.plot(
                    frequency_axis,
                    gain2dB(bode_df.loc[:, (wheel_name, 'gain')]
                            .to_numpy(dtype=np.float64))[freq_selector],
                    '-o',
                )
            case _:
                raise ValueError('Unknown plot Magnitude/Gain scale')

        # ax_phase.set_title(f'{title_wheel_name} -- Phase')
        ax_phase.set_xscale('log')
        ax_phase.grid(True, axis='both', which='both')
        match bodeplot_phase_scale:
            case 'rad':
                ax_phase.set_ylabel('Phase [rad]')
                ax_phase.plot(
                    frequency_axis,
                    bode_df.loc[:, (wheel_name, 'phase')]
                        .to_numpy(dtype=np.float64)[freq_selector],
                    '-o',
                )
            case 'degrees':
                ax_phase.set_ylabel('Phase [degrees]')
                ax_phase.plot(
                    frequency_axis,
                    np.rad2deg(
                        bode_df.loc[:, (wheel_name, 'phase')].to_numpy(dtype=np.float64),
                    )[freq_selector],
                    '-o',
                )
            case _:
                raise ValueError('Unknown plot Phase scale')

        figure_name = f'bode-{title_wheel_name.replace(" ", "-").lower()}'

        if plt_mgr.capturing_config:
            plt_mgr[figure_name, 'gain'] = {
                'ymin': ax_gain.get_ylim()[0],
                'ymax': ax_gain.get_ylim()[1],
            }
            plt_mgr[figure_name, 'phase'] = {
                'ymin': ax_phase.get_ylim()[0],
                'ymax': ax_phase.get_ylim()[1],
            }
        else:
            ax_gain.set_ylim(
                ymin=plt_mgr.get((figure_name, 'gain', 'ymin')),
                ymax=plt_mgr.get((figure_name, 'gain', 'ymax')),
            )
            ax_phase.set_ylim(
                ymin=plt_mgr.get((figure_name, 'phase', 'ymin')),
                ymax=plt_mgr.get((figure_name, 'phase', 'ymax')),
            )

        plt_mgr.output(fig, fname=figure_name, block=False)

    plt_mgr.show_all()

    if parsed_args.save_plot_settings:
        plt_mgr.save_config()

    return 0
