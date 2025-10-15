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

from unittest.mock import NonCallableMock

import numpy as np

from wheel_response_recorder.parameter_iterator import FixedParamIter
from wheel_response_recorder.parameter_iterator import LinearParamIter
from wheel_response_recorder.parameter_iterator import ListParamIter
from wheel_response_recorder.parameter_iterator import LogParamIter


def test_fixed_param_iter():
    subparams = NonCallableMock(value=3.14, kind='fixed')

    iterator = FixedParamIter(subparams)
    assert iterator.KEY == 'fixed'
    assert len(iterator) == 1
    assert np.all(np.isclose(np.fromiter(iter(iterator), dtype=float), [3.14]))


def test_list_param_iter():
    subparams = NonCallableMock(values=[0, 3, 4, 3.21], kind='list')

    iterator = ListParamIter(subparams)
    assert iterator.KEY == 'list'
    assert len(iterator) == 4
    assert np.all(np.isclose(np.fromiter(iter(iterator), dtype=float), [0.0, 3.0, 4.0, 3.21]))


def test_linear_param_iter():
    subparams = NonCallableMock(start=-1, stop=2, num_steps=7, kind='linear')

    iterator = LinearParamIter(subparams)
    assert iterator.KEY == 'linear'
    assert len(iterator) == 7
    assert np.all(np.isclose(np.fromiter(iter(iterator), dtype=float),
                             [-1, -0.5, 0, 0.5, 1.0, 1.5, 2.0]))


def test_log_param_iter():
    subparams = NonCallableMock(start=-1, stop=2, num_steps=4, base=10.0, kind='log')

    iterator = LogParamIter(subparams)
    assert iterator.KEY == 'log'
    assert len(iterator) == 4
    assert np.all(np.isclose(np.fromiter(iter(iterator), dtype=float), [0.1, 1.0, 10, 100]))
