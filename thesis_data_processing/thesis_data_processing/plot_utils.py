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

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from matplotlib.backend_bases import KeyEvent
    from matplotlib.figure import FigureBase


def connect_mpl_keyboard_handler(fig: 'FigureBase'):
    fig.canvas.mpl_connect('key_press_event', mpl_keyboard_close_all)


def mpl_keyboard_close_all(event: 'KeyEvent'):
    if event.key == 'ctrl+q':
        plt.close('all')
