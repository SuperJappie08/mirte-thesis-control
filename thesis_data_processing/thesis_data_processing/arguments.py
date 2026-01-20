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


def add_global_data_export_arguments(parser: argparse.ArgumentParser) -> argparse._ArgumentGroup:
    group = parser.add_argument_group('Data Export')
    group.add_argument(
        '--export-path',
        action='store', required=False,
        type=Path, metavar='EXPORT_FOLDER',
        help='Path to save exported data to. '
        "Defaults to, save plot's DEST_FOLDER/data if available.")
    group.add_argument(
        '--export-target-type',
        choices=['pickle', 'pkl', 'tex'], required=False,
        help='Format to export data as. (Required when exporting)')
    group.add_argument(
        '--export-prefix',
        action='store', required=False,
        type=str, metavar='PREFIX',
        help='Prefix for exported tex commands')

    return group
