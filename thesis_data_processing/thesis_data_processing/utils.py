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

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Iterable

    from builtin_interfaces.msg import Time

# LIFECYCLE_ACTIVE_ID is hard-coded, but if the messages are available, it will be verified.
try:
    LIFECYCLE_ACTIVE_ID: int = 3
    from lifecycle_msgs.msg import State

    assert LIFECYCLE_ACTIVE_ID == State.PRIMARY_STATE_ACTIVE
except ImportError:
    pass

TIMESTAMP_LENGTH: int = 6
DATE_LENGTH: int = 8
FULL_DATETIME_LENGTH: int = TIMESTAMP_LENGTH + 1 + DATE_LENGTH


def as_time(stamp: 'Time') -> Decimal:
    return Decimal(f'{stamp.sec}.{stamp.nanosec:0>9}')


def create_empty_append_df(
    *,
    column_iterable: 'Iterable',
    target_df: pd.DataFrame,
    source_df: pd.DataFrame,
    **kwargs,
) -> pd.DataFrame:
    return pd.DataFrame(
        columns=pd.MultiIndex.from_product(
            column_iterable,
            names=target_df.columns.names.copy(),
        ),
        index=source_df.index.copy(),
        **kwargs,
    )


def append_df(
    *,
    target_df: pd.DataFrame,
    append_df: pd.DataFrame,
    selector: tuple,
) -> pd.DataFrame:
    overlapping_idxs = np.isin(append_df.index, target_df.index)
    target_df = pd.concat(
        (target_df, append_df.loc[~overlapping_idxs]),
        verify_integrity=True,
        sort=True,
        copy=True,
    ).sort_index()

    if overlapping_idxs.any():
        time_selector_dst = target_df.index.array[
                        np.isin(target_df.index, append_df.index[overlapping_idxs])]
        time_selector_src = append_df.index.array[overlapping_idxs]
        target_df.loc[time_selector_dst, selector] = \
            append_df.loc[time_selector_src, selector]

    assert target_df.loc[append_df.index, selector].equals(append_df)

    return target_df
