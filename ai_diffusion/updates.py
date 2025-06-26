# -*- coding: utf-8 -*-

import os
import shutil
import hashlib

from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple
from PyQt5.QtCore import QObject, pyqtSignal

from . import __version__, eventloop
from .network import RequestManager
from .properties import ObservableProperties, Property
from .util import ZipFile, client_logger as log


class UpdateState(Enum):
    unknown = 1
    checking = 2
    available = 3
    latest = 4
    downloading = 5
    installing = 6
    restart_required = 7
    failed_check = 8
    failed_update = 9


class UpdatePackage(NamedTuple):
    version: str
    url: str
    sha256: str


class AutoUpdate(QObject, ObservableProperties):
    default_api_url = os.getenv("INTERSTICE_URL", "https://api.interstice.cloud")

    state = Property(UpdateState.unknown)
    latest_version = Property("")
    error = Property("")

    state_changed = pyqtSignal(UpdateState)
    latest_version_changed = pyqtSignal(str)
    error_changed = pyqtSignal(str)

    def __init__(
        self,
        plugin_dir: Path | None = None,
        current_version: str | None = None,
        api_url: str | None = None,
    ):
        super().__init__()
        self.plugin_dir = plugin_dir or Path(__file__).parent.parent
        self.current_version = current_version or __version__
        self.api_url = api_url or self.default_api_url
        self._package: UpdatePackage | None = None
        self._temp_dir: TemporaryDirectory | None = None
        self._request_manager: RequestManager | None = None

        # token过期时间
        self.token_expired = 0

    def check(self):
        import asyncio
        return asyncio.run(
            self._handle_errors(
                self. _check, UpdateState.failed_check, "Failed to check for new plugin version"
            )
        )

    async def _check(self):
        if self.state is UpdateState.restart_required:
            return

        self.state = UpdateState.checking
        log.info(f"Checking for latest plugin version at {self.api_url}")
        #result = await self._net.get(
        #    f"{self.api_url}/plugin/latest?version={self.current_version}", timeout=10
        #)

        import urllib.request
        import json
        result = json.load(urllib.request.urlopen("https://antaai.oss-cn-hangzhou.aliyuncs.com/comfyui/krita/result.json"))
        if result['url'] == "":
            result['url'] = "https://antaai.oss-cn-hangzhou.aliyuncs.com/comfyui/krita/ai-diffusion-latest.zip"
        try:
            if (expired := result.get("expired")) and isinstance(expired, int):
                self.token_expired = expired
            else:
                self.token_expired = 0
        except Exception as e:
            log.error(f"Error getting token expired: {e}")
            self.token_expired = 0

        self.latest_version = result.get("version")
        if not self.latest_version:
            log.error(f"Invalid plugin update information: {result}")
            self.state = UpdateState.failed_check
            self.error = "Failed to retrieve plugin update information"
        elif self.latest_version == self.current_version:
            log.info("Plugin is up to date!")
            self.state = UpdateState.latest
        elif "url" not in result or "sha256" not in result:
            log.error(f"Invalid plugin update information: {result}")
            self.state = UpdateState.failed_check
            self.error = "Plugin update package is incomplete"
        else:
            log.info(f"New plugin version available: {self.latest_version}")
            self._package = UpdatePackage(
                version=self.latest_version,
                url=result["url"],
                sha256=result["sha256"],
            )
            self.state = UpdateState.available

    def run(self):
        return eventloop.run(
            self._handle_errors(self._run, UpdateState.failed_update, "Failed to update plugin")
        )

    async def _run(self):
        assert self.latest_version and self._package

        self._temp_dir = TemporaryDirectory()
        archive_path = Path(self._temp_dir.name) / f"krita_ai_diffusion-{self.latest_version}.zip"
        log.info(f"Downloading plugin update {self._package.url}")
        self.state = UpdateState.downloading
        archive_data = await self._net.download(self._package.url)

        sha256 = hashlib.sha256(archive_data).hexdigest()
        if sha256 != self._package.sha256 and self._package.sha256 != "":
            log.error(f"Update package hash mismatch: {sha256} != {self._package.sha256}")
            raise RuntimeError("Downloaded plugin package is corrupted or incomplete")

        archive_path.write_bytes(archive_data)
        source_dir = Path(self._temp_dir.name) / f"krita_ai_diffusion-{self.latest_version}"
        log.info(f"Extracting plugin archive into {source_dir}")
        self.state = UpdateState.installing
        
        import zipfile
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(source_dir)

        log.info(f"Installing new plugin version to {self.plugin_dir}")
        shutil.copytree(source_dir, self.plugin_dir, dirs_exist_ok=True)
        self.current_version = self.latest_version
        self.state = UpdateState.restart_required

    @property
    def is_available(self):
        return self.latest_version is not None and self.latest_version != self.current_version

    @property
    def _net(self):
        if self._request_manager is None:
            self._request_manager = RequestManager()
        return self._request_manager

    async def _handle_errors(self, func, error_state: UpdateState, message: str):
        try:
            return await func()
        except Exception as e:
            log.exception(e)
            self.error = f"{message}: {e}"
            self.state = error_state
            return None
