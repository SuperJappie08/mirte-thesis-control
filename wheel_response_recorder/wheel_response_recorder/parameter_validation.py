#!/usr/bin/env python3
# Copyright 2025, Jasper van Brakel
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

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rclpy.parameter import Parameter


def gt_or_nan(param, value):
    if math.isnan(param.value) or param.value > value:
        return ''
    return "Parameter '{}' with the value {} must be NAN or greater than {}".format(
        param.name,
        param.value,
        value,
    )


def single_nan_or_normals(param: 'Parameter'):
    if len(param.value) == 0:
        return (
            f"Parameter '{param.name}' must be a non-empty array."
            ' (Either a single NAN or multiple normal values (not NAN or INF))'
        )
    elif len(param.value) == 1 and not (
        math.isnan(param.value[0]) or math.isfinite(param.value[0])
    ):
        return (
            f"Parameter '{param.name}' must be an array of a single NAN value or real values"
            ' (not NAN or INF)'
        )
    elif len(param.value) > 1 and any(not math.isfinite(value) for value in param.value):
        return (
            f"Parameter '{param.name}' must be an array or real values (not NAN or INF)."
            ' (or a single NAN)'
        )
    return ''
