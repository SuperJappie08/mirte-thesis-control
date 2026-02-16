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
from collections.abc import Iterable
from pathlib import Path
import pickle
from typing import Any, Literal, Optional, Self, TYPE_CHECKING

import matplotlib.pyplot as plt

from .export_utils import extract_configuration
from .utils import get_nested_dict

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

    def __init__(
        self,
        save_path: Optional[Path] = None,
        configuration: Optional[str] = None,
        config_mode: Literal['capture', 'load'] = 'capture',
        *,
        force_display: bool = False,
        default_format: Optional[str] = 'pgf',
        config: Optional[dict[str, Any]] = None,
        key_stack: Optional[list[str]] = None,
    ):
        self._save_path = save_path.expanduser().absolute() if save_path is not None else None
        self._configuration = configuration

        self.__force_display = force_display

        if default_format is None:
            self.__default_format = 'pgf' if mpl2tkz is None else 'tikz'
        else:
            self.__default_format = default_format
        logger.debug("Using default format '%s'", self.default_format)

        assert (config is None) == (key_stack is None)
        self.__config_mode: Literal['capture', 'load'] = config_mode
        self.__config = config if config is not None else {}
        self.__key_stack = key_stack if key_stack is not None else []

    def __get_dict(self) -> dict[str, Any]:
        return get_nested_dict(self.__config, *self.__key_stack)

    def get(self, key: str | Iterable[str], default: Optional[Any] = None, /) -> Optional[Any]:
        if isinstance(key, str):
            return self.__get_dict().get(key, default)
        else:
            keys = list(key)
            return get_nested_dict(self.__get_dict(), *keys[:-1]).get(keys[-1], default)

    def __getitem__(self, key: str | Iterable[str]) -> Any:
        if isinstance(key, str):
            return self.__get_dict()[key]
        else:
            keys = list(key)
            return get_nested_dict(self.__get_dict(), *keys[:-1])[keys[-1]]

    def __setitem__(self, key: str | Iterable[str], value: Any):
        if isinstance(key, str):
            self.__get_dict()[key] = value
        else:
            keys = list(key)
            get_nested_dict(self.__get_dict(), *keys[:-1])[keys[-1]] = value

    def __delitem__(self, key: str | Iterable[str]):
        if isinstance(key, str):
            del self.__get_dict()[key]
        else:
            keys = list(key)
            del get_nested_dict(self.__get_dict(), *keys[:-1])[keys[-1]]

    @property
    def capturing_config(self) -> bool:
        return self.__config_mode == 'capture'

    def save_config(self):
        assert self.save_path is not None, 'Only able to save plot config when saving'

        plot_config_path = self.save_path / 'plot-config.pkl'
        logger.info("Writing plot config to '%s'", plot_config_path)

        with plot_config_path.open('bw') as f:
            pickle.dump(self.__config, f)

    def load_config(self, plot_config_path: Path):
        assert not self.capturing_config, 'Only able to save plot config when saving'
        assert plot_config_path.exists() and plot_config_path.is_file(), \
            f"Supplied plot config '{plot_config_path}' is not a file"

        logger.info("Reading plot config from '%s'", plot_config_path)

        with plot_config_path.open('br') as f:
            self.__config = pickle.load(f)

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
    def force_display(self) -> bool:
        return self.__force_display

    @property
    def display_plots(self) -> bool:
        return self._save_path is None or self.force_display

    @property
    def save_plots(self) -> bool:
        return self._save_path is not None and not self.force_display

    @property
    def save_path(self) -> Optional[Path]:
        return self._save_path

    @property
    def default_format(self) -> str:
        return self.__default_format

    def output(
        self, fig: 'Figure', /,
        fname: str, block: Optional[bool] = None, *,
        file_format: Optional[str] = None,
    ) -> None:
        if self.display_plots:
            old_fig = plt.gcf()
            plt.figure(fig)
            logger.info("Displaying Figure '%s'", fname)
            connect_mpl_keyboard_handler(fig)
            if not self.force_display:
                plt.show(block=block)
            plt.figure(old_fig)
        else:
            assert self.save_path is not None
            self.save_path.mkdir(parents=True, exist_ok=True)
            assert self.save_path.is_dir(), 'Plot save path must be a directory'
            if file_format is None:
                file_format = self.default_format

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
            if not self.force_display:
                plt.show(block=block)
            else:
                plt.close('all')

    def __truediv__(self, subfolder) -> Self:
        temp_dict = self.__get_dict()

        key_stack = self.__key_stack.copy()

        if self.configuration is not None:
            if self.capturing_config and subfolder in temp_dict:
                logger.warning("Key '%s' already exists", '.'.join((*key_stack, subfolder)))
            else:
                temp_dict[subfolder] = temp_dict.get(subfolder, {})
            key_stack += [subfolder]

        return self.__class__(
            save_path=self.save_path / subfolder if self.save_path is not None else self.save_path,
            configuration=self.configuration,
            config_mode=self.__config_mode,
            force_display=self.force_display,
            default_format=self.default_format,
            config=self.__config,
            key_stack=key_stack,
        )

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(save_path={self.save_path!r}, ' \
                f'configuration={self.configuration!r}, force_display={self.force_display!r}, ' \
                f'default_format={self.default_format!r}, config={self.__config!r}, '\
                f'key_stack={self.__key_stack!r})'
