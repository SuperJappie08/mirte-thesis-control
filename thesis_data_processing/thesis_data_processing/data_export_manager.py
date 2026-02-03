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

from pathlib import Path
import pickle
from typing import Any, Callable, Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    logging: ModuleType

try:
    import colorlog
    logging = colorlog
except ImportError:
    import logging

logger = logging.getLogger(__name__)


ExportTargets = Literal['pickle', 'pkl', 'tex']


class DataExportManager:
    """A helper class to export extracted data."""

    def __init__(
        self,
        export_path: Optional[Path] = None,
        plt_save_path: Optional[Path] = None,
        export_prefix: str = '',
    ):
        self.__export_path = export_path

        if self.__export_path is None and plt_save_path is not None:
            self.__export_path = plt_save_path / 'data'

        if self.__export_path is not None:
            self.__export_path = self.__export_path.expanduser().absolute()

        self.__converter: dict[str, Callable[[str, Any, Any], str]] = {}
        self.__datasets: dict[str, dict[Any, Any]] = {}
        self.__exported: dict[str, bool] = {}
        self.__export_prefix = export_prefix

    def register_dataset(self, dataset: str, tex_converter: Callable[[str, Any, Any], str]):
        self.__converter[dataset] = tex_converter

    @property
    def export_prefix(self) -> str:
        return self.__export_prefix

    @property
    def has_any_datasets(self) -> bool:
        return len(self.__converter) > 0

    @property
    def do_export(self) -> bool:
        return self.has_any_datasets and self.export_path is not None

    @property
    def export_path(self) -> Optional[Path]:
        return self.__export_path

    def dataset_exists(self, dataset: str) -> bool:
        return dataset in self.__datasets

    def dataset_exported(self, dataset: str) -> bool:
        return self.__exported.get(dataset, False)

    def get_dataset(self, dataset: str) -> dict:
        if not self.dataset_exists(dataset):
            logger.info("Creating new dataset '%s'", dataset)
            self.__datasets[dataset] = {}

        if self.dataset_exported(dataset):
            logger.error("Dataset '%s' was already exported and possibly gets modified!", dataset)

        return self.__datasets[dataset]

    def export(self, dataset: str, filetype: ExportTargets = 'pickle'):
        if not self.do_export:
            return
        assert self.export_path is not None
        assert dataset in self.__datasets, f"Dataset '{dataset}' does not exist"

        self.export_path.mkdir(parents=True, exist_ok=True)

        if filetype == 'pickle' or filetype == 'pkl':
            with (self.export_path / f'{dataset}.pkl').open(mode='wb') as f:
                logger.info("Exporting '%s' to '%s'", dataset, f.name)
                pickle.dump(self.get_dataset(dataset), f)
        elif filetype == 'tex':
            converter = self.__converter.get(dataset)
            assert converter is not None, f"Missing tex converter for dataset '{dataset}'"

            with (self.export_path / f'{dataset}.tex').open('w') as f:
                logger.info("Exporting '%s' to '%s'", dataset, f.name)

                f.write(f'%% DATASET EXPORT: {dataset} - {self.export_prefix} \n\n')
                dataset_dict = self.get_dataset(dataset)

                for (key, value) in sorted(dataset_dict.items()):
                    f.write(converter(self.export_prefix, key, value))
                    f.write('\n')
        else:
            logger.error("Unknown export type '%s'", filetype)

        self.__exported[dataset] = True

    def export_all(self, filetype: Optional[ExportTargets] = None, *, force_all: bool = False):
        if (not self.do_export) or filetype is None:
            return

        for dataset in self.__datasets:
            if force_all or not self.dataset_exported(dataset):
                self.export(dataset=dataset, filetype=filetype)
