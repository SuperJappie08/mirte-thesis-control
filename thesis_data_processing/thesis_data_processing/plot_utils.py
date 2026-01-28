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

from collections import OrderedDict
from pathlib import Path
from typing import Optional, Self, TYPE_CHECKING

import matplotlib.pyplot as plt

from .export_utils import extract_configuration

if TYPE_CHECKING:
    from types import ModuleType
    from typing import TypeAlias

    from matplotlib.axes import Axes
    from matplotlib.backend_bases import KeyEvent
    from matplotlib.collections import Collection
    from matplotlib.figure import Figure
    from matplotlib.figure import FigureBase
    from matplotlib.legend import Legend
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.text import Text

    LegendItemHandle: TypeAlias = Line2D | Patch | Collection | Text

    logging: ModuleType

try:
    import colorlog
    logging = colorlog
except ImportError:
    import logging

try:
    import matplot2tikz as mpl2tkz
except ImportError:
    mpl2tkz = None

logger = logging.getLogger(__name__)


def connect_mpl_keyboard_handler(fig: 'FigureBase'):
    fig.canvas.mpl_connect('key_press_event', mpl_keyboard_close_all)


def deduped_figure_legend(fig: 'FigureBase', **kwargs) -> 'Legend':
    entry_dict: OrderedDict[str, list[tuple['LegendItemHandle', 'Axes']]] = OrderedDict()

    for ax in fig.axes:
        assert not TYPE_CHECKING or isinstance(ax, Axes)
        for (handle, label) in zip(*ax.get_legend_handles_labels()):
            assert isinstance(label, str)
            assert not TYPE_CHECKING or isinstance(handle, (Line2D, Patch, Collection, Text))

            if label not in entry_dict:
                entry_dict[label] = [(handle, ax)]
            else:
                (other_handle, other_ax) = entry_dict[label][0]
                if other_handle.get_drawstyle() == handle.get_drawstyle():
                    entry_dict[label].append((handle, ax))
                else:
                    raise NotImplementedError('Some sort of renaming logic?')

    labels, handles = zip(*entry_dict.items())

    return fig.legend(handles=[handle[0][0] for handle in handles], labels=list(labels), **kwargs)


def mpl_keyboard_close_all(event: 'KeyEvent'):
    if event.key == 'ctrl+q':
        plt.close('all')


class PlotOutputManager:
    """A helper class to generate Plot outputs (display figures or export)."""

    def __init__(self, save_path: Optional[Path] = None, configuration: Optional[str] = None):
        self._save_path = save_path.expanduser().absolute() if save_path is not None else None
        self._configuration = configuration

    @property
    def configuration(self) -> Optional[str]:
        return self._configuration

    @configuration.setter
    def configuration(self, data_folder: Path):
        assert isinstance(data_folder, Path), 'Comfiguration must be set with a Path'
        assert self._configuration is None, 'Configuration was already set'
        mode_identifier, frequency_identifier = extract_configuration(data_folder)

        nice_mode: str
        match mode_identifier:
            case 'srv':
                nice_mode = 'Service-based'
            case 'mmt':
                nice_mode = 'Topic-based'
            case mode:
                logger.warning("Configuration '%s' does not have a plot conversion.", mode)
                nice_mode = mode

        self._configuration = f'{nice_mode} @ {frequency_identifier[1:]} Hz'

    @property
    def configuration_title(self) -> str:
        if self.configuration is None:
            return ''
        else:
            return f' - {self.configuration}'

    @property
    def display_plots(self) -> bool:
        return self._save_path is None

    @property
    def save_plots(self) -> bool:
        return self._save_path is not None

    @property
    def save_path(self) -> Optional[Path]:
        return self._save_path

    def output(
        self, fig: 'Figure', /,
        fname: str, block: Optional[bool] = None, *,
        file_format: Optional[str] = 'pgf',
    ) -> None:
        if self.display_plots:
            old_fig = plt.gcf()
            plt.figure(fig)
            logger.info("Displaying Figure '%s'", fname)
            connect_mpl_keyboard_handler(fig)
            plt.show(block=block)
            plt.figure(old_fig)
        else:
            assert self.save_path is not None
            self.save_path.mkdir(parents=True, exist_ok=True)
            assert self.save_path.is_dir(), 'Plot save path must be a directory'
            if file_format is None:
                file_format = 'pgf' if mpl2tkz is None else 'tikz'

            filename = f'{fname}.{file_format}'
            logger.info("Saving Figure to '%s'", self.save_path / filename)
            if file_format == 'tikz':
                assert mpl2tkz is not None
                mpl2tkz.clean_figure(fig=fig)
                mpl2tkz.save(figure=fig, filepath=self.save_path / filename)
            else:
                fig.savefig(self.save_path / filename, format=file_format)
                fig.canvas.draw_idle()  # Need this if 'transparent=True', to reset colors.
            plt.close(fig)

    def show_all(self, block: Optional[bool] = None) -> None:
        if self.display_plots:
            plt.show(block=block)

    def __truediv__(self, subfolder) -> Self:
        if self.display_plots:
            return self
        else:
            assert self.save_path is not None
            return self.__class__(self.save_path / subfolder, configuration=self.configuration)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(save_path={self.save_path!r}, ' \
                f'configuration={self.configuration!r})'
