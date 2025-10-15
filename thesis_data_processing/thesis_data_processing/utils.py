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

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builtin_interfaces.msg import Time

# LIFECYCLE_ACTIVE_ID is hard-coded, but if the messages are available, it will be verified.
try:
    LIFECYCLE_ACTIVE_ID: int = 3
    from lifecycle_msgs.msg import State

    assert LIFECYCLE_ACTIVE_ID == State.PRIMARY_STATE_ACTIVE
except ImportError:
    pass


def as_time(stamp: 'Time') -> Decimal:
    return Decimal(f'{stamp.sec}.{stamp.nanosec:0>9}')
