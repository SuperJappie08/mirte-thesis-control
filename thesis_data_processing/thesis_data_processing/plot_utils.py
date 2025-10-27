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
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from typing import TypeAlias

    from matplotlib.axes import Axes
    from matplotlib.backend_bases import KeyEvent
    from matplotlib.collections import Collection
    from matplotlib.figure import FigureBase
    from matplotlib.legend import Legend
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.text import Text

    LegendItemHandle: TypeAlias = Line2D | Patch | Collection | Text


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
