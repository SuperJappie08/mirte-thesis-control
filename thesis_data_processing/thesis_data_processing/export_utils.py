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

from decimal import Decimal
from pathlib import PurePath as Path

from . import utils


def joint_name2plot(wheel_name: str) -> str:
    """
    Convert the joint name to a better plot title.

    :param wheel_name: The wheel joint name
    :type wheel_name: str
    :return: The plot title fragment
    :rtype: str
    """
    return ' '.join(s.capitalize() for s in wheel_name.split('_') if s != 'joint')


def convert_wheel_joint_to_tex(wheel_name: str) -> str:
    return ''.join(s.capitalize() for s in wheel_name.split('_') if s != 'joint')


def step_size_to_tex(step_size: Decimal) -> str:
    trail_type = ''
    if step_size < 0.0:
        trail_type += 'Neg'

    step_command = abs(step_size)

    if step_command == Decimal('3.0'):
        trail_type += 'Low'
    elif step_command == Decimal('4.5'):
        trail_type += 'Mid'
    elif step_command == Decimal('21.0'):
        trail_type += 'High'
    else:
        raise ValueError(f"Unknown step_command '{step_size}'")

    return trail_type


def frequency_to_tex(frequency: str) -> str:
    if frequency == 'R10':
        return 'Low'
    elif frequency == 'R20':
        return 'High'
    else:
        raise ValueError(f"Unknown frequency specifier '{frequency}'")


def extract_configuration(data_folder: Path) -> tuple[str, str]:
    """
    Extract the test configuration from the datapath.

    :param data_folder: The data_path containing the ROSBags
    :type data_folder: Path
    :return: A tuple of the mode abbreviation and the frequency identifier
    :rtype: tuple[str, str]
    """
    mode, frequency = data_folder.name[:-(utils.FULL_DATETIME_LENGTH + 1)].split('-')[-2:]
    return mode, frequency


def datafolder_to_tex_command_base(data_folder: Path) -> str:
    mode, frequency = extract_configuration(data_folder)
    return f'{mode.capitalize()}{frequency_to_tex(frequency)}'
