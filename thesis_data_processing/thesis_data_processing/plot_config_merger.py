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

import argparse
from collections.abc import Sequence
import copy
from pathlib import Path
import pickle
from typing import Any, Optional, TYPE_CHECKING

from thesis_data_processing.utils import prompt

if TYPE_CHECKING:
    from types import ModuleType

    logging: ModuleType

try:
    import colorlog
    logging = colorlog
except ImportError:
    import logging


logger = logging.getLogger(__name__)


def keys(d: dict[str, Any]) -> set[str]:
    result = set()

    for key, value in d.items():
        if isinstance(value, dict):
            result |= {f'{key}.{nested_key}' for nested_key in keys(value)}
        else:
            result.add(key)

    return result


def merge(target: dict[str, Any], src: dict[str, Any]):
    for key, value in src.items():
        if isinstance(value, dict):
            new_target = target.get(key, {})
            target[key] = new_target

            merge(new_target, value)
        else:
            if key.endswith('min'):
                target[key] = min(target.get(key, copy.deepcopy(value)), copy.deepcopy(value))
            elif key.endswith('max'):
                target[key] = max(target.get(key, copy.deepcopy(value)), copy.deepcopy(value))
            else:
                raise KeyError(f"Unknown Key '{key}'")


def main(args: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        'plot_config_merger',
        description='Merge plot configs')
    parser.add_argument(
        '--input',
        type=Path, nargs='+',
        required=True, metavar='INPUT',
        help='The input files to be merged (at least 2)')
    parser.add_argument(
        '--output', type=Path, required=True, metavar='OUTPUT',
        help='Output filepath for the merged plot config.')

    parsed_args = parser.parse_args(args=args)

    output_path: Path = parsed_args.output
    if output_path.exists():
        if not prompt(f"Export '{output_path}' already exists! Override", default=False):
            exit()

    input_data: dict[str, dict[str, Any]] = {}

    for path in parsed_args.input:
        assert isinstance(path, Path)

        with path.open('br') as f:
            input_data[str(path.parent)] = pickle.load(f)

    output_data: dict[str, Any] = {}

    for key, data in input_data.items():
        logger.info("Merging '%s'", key)
        merge(output_data, data)
        assert keys(data).issubset(keys(output_data))

    with output_path.open('bw') as f:
        pickle.dump(output_data, f)

    return 0
