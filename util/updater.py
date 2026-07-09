"""
Update management for Nuitka-packaged AGVmon.

Talks to the AGVmon Update Server (update_server.py):
- GET  /api/update/latest.json          -> check for updates
- GET  /api/update/download/<filename>  -> download ZIP
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

import httpx


# -- Version utilities --

def parse_version(v: str) -> tuple:
    """Parse '0.1.0.88' -> (0, 1, 0, 88)."""
    return tuple(int(x) for x in v.split("."))


def compare_versions(a: str, b: str) -> int:
    """Compare version strings. -1 if a<b, 0 if equal, 1 if a>b."""
    pa, pb = parse_version(a), parse_version(b)
    max_len = max(len(pa), len(pb))
    pa = pa + (0,) * (max_len - len(pa))
    pb = pb + (0,) * (max_len - len(pb))
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


# -- App root detection --

def get_app_root() -> Path:
    """App root: exe directory when frozen, cwd in dev mode."""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.executable).parent
    return Path.cwd()


# -- Update manager --

class UpdateManager:
    """Manages the update lifecycle: check, download, apply."""

    def __init__(self):
        self.app_root = get_app_root()
        self.download_dir = self.app_root / "updates"
        self._downloaded_zip: Optional[Path] = None
        self._latest_info: Optional[dict] = None
        self._status = "idle"
        self._status_message = ""

    # -- config helpers --

    def _get_config(self) -> dict:
        try:
            from util.config import cfg

            return {
                "update_url": (
                    cfg.get("update.update_url")
                    or os.environ.get("UPDATE_URL", "")
                ),
                "channel": cfg.get("update.channel") or "stable",
                "auto_check": (
                    cfg.get("update.auto_check")
                    if cfg.get("update.auto_check") is not None
                    else True
                ),
            }
        except Exception:
            return {
                "update_url": os.environ.get("UPDATE_URL", ""),
                "channel": "stable",
                "auto_check": True,
            }

    def _manifest_url(self, config: dict) -> str:
        base = config["update_url"].rstrip("/")
        channel = config.get("channel", "stable")
        name = "latest.json" if channel == "stable" else f"latest-{channel}.json"
        return f"{base}/agvmon/api/update/{name}"

    def _download_url(self, config: dict, filename: str) -> str:
        base = config["update_url"].rstrip("/")
        return f"{base}/agvmon/api/update/download/{filename}"

    # -- public API --

    @property
    def status(self) -> str:
        return self._status

    @property
    def status_message(self) -> str:
        return self._status_message

    @property
    def latest_info(self) -> Optional[dict]:
        return self._latest_info

    # -- check --

    async def check(self) -> dict:
        """Check update server for a newer version."""
        from util.__version__ import version as current_ver

        self._status = "checking"
        config = self._get_config()
        result = {"current_version": current_ver, "update_available": False}

        if not config["update_url"]:
            self._status = "idle"
            self._status_message = "update server not configured"
            result["error"] = self._status_message
            return result

        manifest_url = self._manifest_url(config)

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(manifest_url)
                if resp.status_code == 404:
                    self._status = "idle"
                    result["error"] = "no version available"
                    return result
                if resp.status_code != 200:
                    self._status = "error"
                    self._status_message = f"server returned {resp.status_code}"
                    result["error"] = self._status_message
                    return result
                latest = resp.json()
        except httpx.RequestError as e:
            self._status = "error"
            self._status_message = f"cannot reach update server: {e}"
            result["error"] = self._status_message
            return result
        except json.JSONDecodeError:
            self._status = "error"
            self._status_message = "invalid manifest format"
            result["error"] = self._status_message
            return result

        result["latest"] = latest
        result["latest_version"] = latest.get("version", "")

        if latest.get("version") and compare_versions(latest["version"], current_ver) > 0:
            result["update_available"] = True
            self._latest_info = latest
            self._status = "update_available"
            self._status_message = f"new version v{latest['version']} available"
        else:
            self._status = "idle"
            self._status_message = "already up to date"

        return result

    # -- download --

    async def download(self):
        """Download ZIP from update server. Yields progress events for SSE."""
        if not self._latest_info:
            yield {"event": "error", "message": "please check for updates first"}
            return

        self._status = "downloading"
        config = self._get_config()

        filename = self._latest_info.get("url", "")
        url = self._download_url(config, filename)
        expected_sha256 = self._latest_info.get("sha256", "")
        expected_size = self._latest_info.get("size", 0)

        self.download_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name or "update.zip"
        dest = self.download_dir / safe_name

        try:
            async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        self._status = "error"
                        self._status_message = f"download failed: HTTP {resp.status_code}"
                        yield {"event": "error", "message": self._status_message}
                        return

                    total = int(resp.headers.get("content-length", 0)) or expected_size
                    downloaded = 0
                    sha256_hasher = hashlib.sha256()

                    with open(dest, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
                            sha256_hasher.update(chunk)
                            downloaded += len(chunk)
                            pct = round(downloaded / total * 100, 1) if total else 0
                            yield {
                                "event": "progress",
                                "downloaded": downloaded,
                                "total": total,
                                "percent": pct,
                            }

            if expected_sha256:
                actual_sha256 = sha256_hasher.hexdigest()
                if actual_sha256 != expected_sha256:
                    dest.unlink(missing_ok=True)
                    self._status = "error"
                    self._status_message = "checksum mismatch, please re-download"
                    yield {"event": "error", "message": self._status_message}
                    return

            self._downloaded_zip = dest
            self._status = "ready"
            self._status_message = "update downloaded, ready to restart"
            yield {"event": "complete", "file": safe_name, "path": str(dest)}

        except httpx.RequestError as e:
            self._status = "error"
            self._status_message = f"download failed: {e}"
            yield {"event": "error", "message": self._status_message}
            if dest.exists():
                dest.unlink(missing_ok=True)

    # -- apply --

    def apply(self) -> dict:
        """Extract ZIP to staging, write bat, launch updater, then exit."""
        if not (getattr(sys, "frozen", False) or "__compiled__" in globals()):
            return {"status": "error", "message": "apply only supported in Nuitka-frozen exe"}

        if not self._downloaded_zip or not self._downloaded_zip.exists():
            return {"status": "error", "message": "no downloaded update package"}

        self._status = "applying"
        staging = self.download_dir / ".staging"

        if staging.exists():
            shutil.rmtree(staging)

        try:
            staging.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(self._downloaded_zip, "r") as zf:
                for member in zf.namelist():
                    if member.endswith("/") or member.endswith("\\"):
                        continue
                    target = staging / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # Validate extraction
            exe = staging / "agvmon.exe"
            file_count = sum(1 for _ in staging.rglob("*") if _.is_file())
            if not exe.exists() or file_count < 5:
                shutil.rmtree(staging)
                self._status = "error"
                msg = f"update package invalid: {file_count} files extracted"
                self._status_message = msg
                return {"status": "error", "message": msg}

            # Write update.bat
            self.download_dir.mkdir(parents=True, exist_ok=True)
            bat_path = self.download_dir / "update.bat"
            bat_path.write_text(_BAT_SCRIPT, encoding="gbk")

            # Launch as detached process
            CREATE_NEW = 0x00000200
            DETACHED = 0x00000008
            flags = (CREATE_NEW | DETACHED) if sys.platform == "win32" else 0

            subprocess.Popen(
                ["cmd", "/c", "start", "AGVmon Update", "/min", str(bat_path)],
                creationflags=flags,
                cwd=str(self.app_root),
                close_fds=True,
            )

            self._status_message = "update prepared, restarting..."
            return {"status": "applying", "message": self._status_message}

        except OSError as e:
            self._status = "error"
            self._status_message = f"apply failed: {e}"
            return {"status": "error", "message": self._status_message}


# -- Batch script (copy from staging, no destructive moves) --

_BAT_SCRIPT = """@echo off
title AGVmon Update
cd /d "%~dp0"
echo ============================================
echo   AGVmon Updater
echo ============================================
if not exist ".staging\\agvmon.exe" (
    echo ERROR: Update package not found
    pause >nul
    del "%~f0" 2>nul
    exit /b 1
)
echo Waiting for main process to exit...
timeout /t 3 /nobreak >nul
echo Installing update...
robocopy ".staging" ".." /E /IS /IT /NP /NDL /NJH /NJS /R:3 /W:2
set ROBO_ERR=%errorlevel%
if %ROBO_ERR% geq 8 (
    echo ERROR: Install failed (code %ROBO_ERR%)
    pause >nul
    del "%~f0" 2>nul
    exit /b 1
)
echo Cleaning up staging...
rmdir /s /q ".staging" 2>nul
echo Starting new version...
start "" "..\\agvmon.exe"
echo Update complete.
timeout /t 2 /nobreak >nul
del "%~f0" 2>nul
"""


# -- Singleton --

_updater: Optional[UpdateManager] = None


def get_updater() -> UpdateManager:
    global _updater
    if _updater is None:
        _updater = UpdateManager()
    return _updater
