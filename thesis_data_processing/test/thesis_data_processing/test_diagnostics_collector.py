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

from diagnostic_msgs.msg import DiagnosticStatus
import pytest

from thesis_data_processing import DiagnosticsCollector
from thesis_data_processing.diagnostics_collector import DiagnosticsLevel

EXCLUDED_HARDWARE_ID: str = 'excluded-hw-id'

INCLUDED: tuple[str, str, str] = ('included-hw-id', 'some-name', 'some-key')
EXCLUDED_BY_HW_ID: tuple[str, str, str] = (EXCLUDED_HARDWARE_ID, 'some-name', 'some-key')


@pytest.fixture
def diag_collector():  # TODO(SuperJappie08): Should also test with name mapping
    return DiagnosticsCollector()


@pytest.fixture
def diag_collector_hw_id_filter():  # TODO(SuperJappie08): Should also test with name mapping
    return DiagnosticsCollector(excluded_hardware_ids=[EXCLUDED_HARDWARE_ID])


def test_diagnostics_level_equivalence():
    assert DiagnosticStatus.OK[0] == DiagnosticsLevel.OK.value
    assert DiagnosticStatus.WARN[0] == DiagnosticsLevel.WARN.value
    assert DiagnosticStatus.ERROR[0] == DiagnosticsLevel.ERROR.value
    assert DiagnosticStatus.STALE[0] == DiagnosticsLevel.STALE.value


def test_include_entry_no_filter_no_mapping(diag_collector: DiagnosticsCollector):
    assert diag_collector._include_entry(*INCLUDED)
    assert diag_collector._include_entry(*EXCLUDED_BY_HW_ID)


def test_include_entry_hw_id_filter_no_mapping(diag_collector_hw_id_filter: DiagnosticsCollector):
    assert diag_collector_hw_id_filter._include_entry(*INCLUDED)
    assert not diag_collector_hw_id_filter._include_entry(*EXCLUDED_BY_HW_ID)
