# Copyright 2026 Jasper van Brakel
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

import pytest

from thesis_data_processing import PlotOutputManager

CONFIGURATION = 'TEST CONFIG'


@pytest.fixture
def plt_mgr_none():
    return PlotOutputManager(save_path=None, configuration=CONFIGURATION)


@pytest.fixture
def plt_mgr_none_force():
    return PlotOutputManager(save_path=None, force_display=True, configuration=CONFIGURATION)


@pytest.fixture
def plt_mgr_path(tmp_path_factory):
    return PlotOutputManager(
        save_path=tmp_path_factory.mktemp('output'),
        configuration=CONFIGURATION,
    )


@pytest.fixture
def plt_mgr_path_force(tmp_path_factory):
    return PlotOutputManager(
        save_path=tmp_path_factory.mktemp('output'),
        force_display=True,
        configuration=CONFIGURATION,
    )


def test_plt_mgr_mode_none(plt_mgr_none):
    assert not plt_mgr_none.force_display
    assert plt_mgr_none.display_plots
    assert not plt_mgr_none.save_plots
    assert plt_mgr_none.save_path is None


def test_plt_mgr_mode_none_force(plt_mgr_none_force):
    assert plt_mgr_none_force.force_display
    assert plt_mgr_none_force.display_plots
    assert not plt_mgr_none_force.save_plots
    assert plt_mgr_none_force.save_path is None


def test_plt_mgr_mode_path(plt_mgr_path):
    assert not plt_mgr_path.force_display
    assert not plt_mgr_path.display_plots
    assert plt_mgr_path.save_plots
    assert plt_mgr_path.save_path is not None


def test_plt_mgr_mode_path_force(plt_mgr_path_force):
    assert plt_mgr_path_force.force_display
    assert plt_mgr_path_force.display_plots
    assert not plt_mgr_path_force.save_plots
    assert plt_mgr_path_force.save_path is not None
