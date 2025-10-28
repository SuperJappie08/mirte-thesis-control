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

import argparse
from pathlib import Path


def positive_int(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError(f'{n} is not a positive integer. Must be larger than 0')
    return n


def add_global_plotting_arguments(parser: argparse.ArgumentParser):
    parser.add_argument(
        '--save-plots',
        action='store', required=False,
        type=Path, metavar='DEST_FOLDER',
        help='Path to save plots to. (Only saving when supplied)',
    )
