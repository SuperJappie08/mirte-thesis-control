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
from contextlib import contextmanager
from functools import cache
from typing import Any, Generator, TYPE_CHECKING

from rclpy.serialization import deserialize_message
from rosbag2_py import ConverterOptions
from rosbag2_py import SequentialReader
from rosbag2_py import StorageFilter
from rosidl_runtime_py.utilities import get_message

if TYPE_CHECKING:
    from rosbag2_py import StorageOptions
    from rosbag2_py import TopicMetadata


@contextmanager
def open_rosbag(
    storage_options: 'StorageOptions',
    convert_options: ConverterOptions = ConverterOptions(),
) -> Generator[SequentialReader, None, None]:
    reader = SequentialReader()
    try:
        reader.open(storage_options, convert_options)
        yield reader
    finally:
        reader.close()


@cache
def get_message_type(identifier: str) -> type:
    return get_message(identifier)


def read_messages(
    reader: SequentialReader,
    storage_filter: StorageFilter = StorageFilter(),
) -> Generator[tuple[str, Any, int], None, None]:
    reader.set_filter(storage_filter)

    topic_metadatas: list['TopicMetadata'] = reader.get_all_topics_and_types()

    # NOTE: Do not directly get the message type, as it might not be available.
    #       However this is fine when the filters are setup to ignore those messages
    type_map: dict[str, str] = {
        topic_metadata.name: topic_metadata.type for topic_metadata in topic_metadatas
    }

    while reader.has_next():
        (topic, data, recv_time) = reader.read_next()
        msg_type = get_message_type(type_map[topic])
        msg = deserialize_message(data, msg_type)
        yield (topic, msg, recv_time)
