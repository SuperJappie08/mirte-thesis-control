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

from collections.abc import Callable, Iterable, Iterator, Sized
from dataclasses import dataclass
from dataclasses import field
from dataclasses import InitVar
from functools import partial
from itertools import repeat
import math
from typing import Any, Optional

import numpy as np


class ParamIter(Iterable[float], Sized):
    KEY: str = ''

    def __init__(self, subparams) -> None:
        if not self.KEY:
            raise ValueError('Need to override KEY')
        assert self.KEY == subparams.kind


class FixedParamIter(ParamIter):
    KEY = 'fixed'

    def __init__(self, subparams) -> None:
        super().__init__(subparams)
        assert hasattr(subparams, 'value')
        assert not math.isnan(getattr(subparams, 'value')), (
            f"The 'value' parameter should be non-nan for iterator type '{self.KEY}'"
        )
        self._value = subparams.value

    def __iter__(self) -> Iterator[float]:
        return iter((self._value,))

    def __len__(self) -> int:
        return 1


class RangeParamIter(ParamIter):
    DIST: Optional[Callable[[float, float, int], Any]] = None

    def __init__(self, subparams) -> None:
        super().__init__(subparams)

        if self.DIST is None:
            raise ValueError('Need to override DIST on RangeParamIter types')

        assert hasattr(subparams, 'start')
        assert not math.isnan(getattr(subparams, 'start')), (
            f"The 'start' parameter should be non-nan for iterator type '{self.KEY}'"
        )
        start = subparams.start

        assert hasattr(subparams, 'stop')
        assert not math.isnan(getattr(subparams, 'stop')), (
            f"The 'stop' parameter should be non-nan for iterator type '{self.KEY}'"
        )
        stop = subparams.stop

        assert hasattr(subparams, 'num_steps')
        assert getattr(subparams, 'num_steps') > 0, (
            f"The 'num_steps' parameter should be greater than 0 for a iterator type '{self.KEY}'"
        )
        num_steps = subparams.num_steps

        self._list = self.DIST(start, stop, num_steps)

    def __iter__(self) -> Iterator[float]:
        return iter(self._list)

    def __len__(self) -> int:
        return len(self._list)


class LinearParamIter(RangeParamIter):
    KEY = 'linear'
    DIST = partial(np.linspace, endpoint=True, dtype=float)


class LogParamIter(RangeParamIter):
    KEY = 'log'
    DIST = partial(np.logspace, endpoint=True, dtype=float)

    def __init__(self, subparams):
        assert hasattr(subparams, 'base')
        self.DIST = partial(self.DIST, base=subparams.base)

        super().__init__(subparams)


PARAMITER_RESOLVE = {
    FixedParamIter.KEY: FixedParamIter,
    LinearParamIter.KEY: LinearParamIter,
    LogParamIter.KEY: LogParamIter,
}


@dataclass(frozen=True)
class ParameterIterator(Iterable[tuple[str, float]], Sized):
    name: str
    subparams: InitVar[Any]
    kind: str = field(init=False)
    iterator: ParamIter = field(init=False)

    def __post_init__(self, subparams):
        assert hasattr(subparams, self.name)
        params = getattr(subparams, self.name)
        assert hasattr(params, 'kind')
        setattribute = object.__setattr__
        setattribute(self, 'kind', params.kind)
        try:
            setattribute(
                self,
                'iter',
                PARAMITER_RESOLVE[self.kind](params),
            )
        except AssertionError as exc:
            raise ValueError(
                f"Invalid Parameter value for iterator '{self.name}' of kind '{self.kind}'",
            ) from exc

    def __iter__(self):
        return zip(repeat(self.name), iter(self.iterator))

    def __len__(self) -> int:
        return len(self.iterator)
