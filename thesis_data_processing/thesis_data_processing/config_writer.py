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

from pathlib import Path
import stat
import sys
import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


def create_config(basepath: Path, data_folder: Path, args: 'Namespace'):
    basepath.mkdir(parents=True, exist_ok=True)

    config_path: Path = basepath / 'config'

    print(Path().absolute().resolve())
    if config_path.exists():
        do_continue = input(
            f"Export '{basepath}' already exists! Override [yN] ",
        ).lower().startswith('y')
        print()

        if not do_continue:
            exit()

    install_dir = Path(sys.argv[0])
    while install_dir.name != 'install':
        install_dir = install_dir.parent

    exec_path = Path(sys.argv[0])
    exc = exec_path.name
    pkg = exec_path.parent.name

    config_file = textwrap.dedent(
        r"""
        #!/usr/bin/env bash
        # datapath = {datapath}
        # {args!r}

        pushd {gen_location}
        source {install_dir}/setup.bash
        ros2 run {pkg} {executable} {datapath} {extra_args}
        popd
        """.format(
            install_dir=install_dir,
            pkg=pkg,
            gen_location=Path().absolute().resolve(),
            executable=exc,
            datapath=data_folder,
            args=args,
            extra_args=' '.join(sys.argv[2:]),
            )).lstrip()

    with config_path.open('w') as f:
        f.write(config_file)

    st = config_path.stat()
    config_path.chmod(st.st_mode | stat.S_IXGRP | stat.S_IXUSR)
