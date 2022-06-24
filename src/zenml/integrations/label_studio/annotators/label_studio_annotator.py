#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Implementation of the Label Studio annotation integration."""

import os
import subprocess
import sys
import webbrowser
from typing import ClassVar, List, Optional

from label_studio_sdk import Client

from zenml.annotators.base_annotator import BaseAnnotator
from zenml.exceptions import ProvisioningError
from zenml.integrations.label_studio import LABEL_STUDIO_ANNOTATOR_FLAVOR
from zenml.integrations.label_studio.steps.label_studio_export_step import (
    AnnotationInputArtifact,
    LabelStudioRecords,
)
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.utils import io_utils, networking_utils

logger = get_logger(__name__)

DEFAULT_LABEL_STUDIO_PORT = 8093


class LabelStudioAnnotator(BaseAnnotator):
    """Class to interact with the Label Studio annotation interface.

    Attributes:
        api_key: The API key to use for authentication.
        port: The port to use for the annotation interface.
        project_name: The name of the project to interact with.
    """

    port: int = DEFAULT_LABEL_STUDIO_PORT
    api_key: str
    project_name: Optional[str]

    FLAVOR: ClassVar[str] = LABEL_STUDIO_ANNOTATOR_FLAVOR

    def get_url(self) -> str:
        """Gets the URL of the annotation interface."""
        return f"http://localhost:{self.port}"

    def get_datasets(self) -> List[str]:
        """Gets the datasets currently available for annotation."""

    @property
    def root_directory(self) -> str:
        """Returns path to the root directory.

        Returns:
            Path to the root directory.
        """
        return os.path.join(
            io_utils.get_global_config_directory(),
            "annotators",
            str(self.uuid),
        )

    @property
    def _pid_file_path(self) -> str:
        """Returns path to the daemon PID file.

        Returns:
            Path to the daemon PID file.
        """
        return os.path.join(self.root_directory, "label_studio_daemon.pid")

    @property
    def _log_file(self) -> str:
        """Path of the daemon log file.

        Returns:
            Path to the daemon log file.
        """
        return os.path.join(self.root_directory, "label_studio_daemon.log")

    @property
    def is_provisioned(self) -> bool:
        """If the component provisioned resources to run locally.

        Returns:
            True if the component provisioned resources to run locally.
        """
        return fileio.exists(self.root_directory)

    @property
    def is_running(self) -> bool:
        """If the component is running locally.

        Returns:
            True if the component is running locally, False otherwise.
        """
        if sys.platform != "win32":
            from zenml.utils.daemon import check_if_daemon_is_running

            if not check_if_daemon_is_running(self._pid_file_path):
                return False
        else:
            # Daemon functionality is not supported on Windows, so the PID
            # file won't exist. This if clause exists just for mypy to not
            # complain about missing functions
            pass

        return True

    def provision(self) -> None:
        """Spins up the annotation server backend."""
        fileio.makedirs(self.root_directory)

    def deprovision(self) -> None:
        """Spins down the annotation server backend."""
        if fileio.exists(self._log_file):
            fileio.remove(self._log_file)

    def resume(self) -> None:
        """Resumes the annotation interface."""
        if self.is_running:
            logger.info("Local kubeflow pipelines deployment already running.")
            return

        self.start_annotator_daemon()

    def suspend(self) -> None:
        """Suspends the annotation interface."""
        if not self.is_running:
            logger.info("Local annotation server is not running.")
            return

        self.stop_annotator_daemon()

    def start_annotator_daemon(self) -> None:
        """Starts the annotation server backend."""
        command = [
            "label-studio",
            "start",
            "--no-browser",
            "--port",
            f"{self.port}",
        ]

        if sys.platform == "win32":
            logger.warning(
                "Daemon functionality not supported on Windows. "
                "In order to access the Label Studio server locally, "
                "please run '%s' in a separate command line shell.",
                self.port,
                " ".join(command),
            )
        elif not networking_utils.port_available(self.port):
            raise ProvisioningError(
                f"Unable to port-forward Label Studio to local "
                f"port {self.port} because the port is occupied. In order to "
                f"access Label Studio locally, please "
                f"change the configuration to use an available "
                f"port or stop the other process currently using the port."
            )
        else:
            from zenml.utils import daemon

            def _daemon_function() -> None:
                """Forwards the port of the Kubeflow Pipelines Metadata pod ."""
                subprocess.check_call(command)

            daemon.run_as_daemon(
                _daemon_function,
                pid_file=self._pid_file_path,
                log_file=self._log_file,
            )
            logger.info(
                "Started Label Studio daemon (check the daemon"
                "logs at `%s` in case you're not able to access the annotation "
                "interface).",
                self._log_file,
            )

    def stop_annotator_daemon(self) -> None:
        """Stops the annotation server backend."""
        if fileio.exists(self._pid_file_path):
            if sys.platform == "win32":
                # Daemon functionality is not supported on Windows, so the PID
                # file won't exist. This if clause exists just for mypy to not
                # complain about missing functions
                pass
            else:
                from zenml.utils import daemon

                daemon.stop_daemon(self._pid_file_path)
                fileio.remove(self._pid_file_path)

    def launch(self) -> None:
        """Launches the annotation interface."""
        if self._connection_available():
            webbrowser.open(self.get_url(), new=1, autoraise=True)
        else:
            logger.warning(
                "Could not launch annotation interface"
                "because the connection could not be established."
            )

    def _connection_available(self) -> bool:
        ls = Client(url=self.get_url(), api_key=self.api_key)
        try:
            result = ls.check_connection()
            return result.get("status") == "UP"
        except Exception:
            logger.error(
                "Connection error: No connection was able to be established to the Label Studio backend."
            )
            return False

    def add_dataset(self, dataset_name: str) -> None:
        """Registers a dataset for annotation."""

    def delete_dataset(self, dataset_name: str) -> None:
        """Deletes a dataset from the annotation interface."""

    def get_dataset(self, dataset_name: str) -> None:
        """Gets the dataset with the given name."""

    def get_annotations(self, dataset_name: str) -> None:
        """Gets the annotations for the given dataset."""

    def tag_dataset(self, dataset_name: str, tag: str) -> None:
        """Tags the dataset with the given name with the given tag."""

    def untag_dataset(self, dataset_name: str, tag: str) -> None:
        """Untags the dataset with the given name with the given tag."""

    def get_labeled_data(self, dataset_name: str) -> None:
        """Gets the labeled data for the given dataset."""

    def get_unlabeled_data(self, dataset_name: str) -> None:
        """Gets the unlabeled data for the given dataset."""

    def export_data(
        self, data: AnnotationInputArtifact, export_config
    ) -> LabelStudioRecords:
        """Exports the data for the given identifier."""

    def import_data(self, identifier: str, import_config) -> None:
        """Imports the data for the given identifier."""

    def register_dataset_for_annotation(
        self, name: str, tags: List[str]
    ) -> None:
        """Registers a dataset for annotation."""
        # create a project if it doesn't exist