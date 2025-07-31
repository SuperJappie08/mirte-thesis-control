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

from pal_statistics_msgs.msg import StatisticsNames
import pytest

from thesis_data_processing import StatisticsCollector

TEST_TOPIC = '/test/topic'
INCLUDED = 'included'
EXCLUDED = 'excluded'


@pytest.fixture
def stats_collector():
    return StatisticsCollector(TEST_TOPIC)


@pytest.fixture
def filtered_stats_collector():
    return StatisticsCollector(TEST_TOPIC, only_names={INCLUDED})


def test_include_names_no_filter(stats_collector: StatisticsCollector):
    assert stats_collector._include_name(INCLUDED)
    assert stats_collector._include_name(EXCLUDED)


def test_include_names_filter(filtered_stats_collector: StatisticsCollector):
    assert filtered_stats_collector._include_name(INCLUDED)
    assert not filtered_stats_collector._include_name(EXCLUDED)


def test_name_versions(stats_collector: StatisticsCollector):
    assert stats_collector.names_versions is None

    stats_collector.process_msg(
        stats_collector.names_topic,
        StatisticsNames(names=['alice'], names_version=10),
    )

    assert stats_collector.names_versions is not None
    assert 10 in stats_collector.names_versions
    assert len(stats_collector.names_versions) == 1

    stats_collector.process_msg(
        stats_collector.names_topic,
        StatisticsNames(names=['alice', 'bob'], names_version=11),
    )

    assert 11 in stats_collector.names_versions
    assert len(stats_collector.names_versions) == 2
