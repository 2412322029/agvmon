"""
Update management for Nuitka-packaged AGVmon.

Talks to the AGVmon Update Server (update_server.py):
- GET  /api/update/latest.json          → check for updates
- GET  /api/update/download/<filename>  → download ZIP
"""

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

import httpx

# ── Version utilities ──────────────────────────────────────────

def parse_version(v: str) -> tuple:
    """Parse '0.1.0.88' -> (0, 1, 0, 88)."""
    return tuple(int(x) for x in v.split("."))


def compare_versions(a: str, b: str) -> int:
    """
    Compare two version strings.
    Returns -1 if a < b, 0 if equal, 1 if a > b.
    Pads shorter version with zeros.
    """
    pa, pb = parse_version(a), parse_version(b)
    max_len = max(len(pa), len(pb))
    pa = pa + (0,) * (max_len - len(pa))
    pb = pb + (0,) * (max_len - len(pb))
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


# ── App root detection ────────────────────────────────────────

def get_app_root() -> Path:
    """
    Determine the app root directory.

    In Nuitka standalone mode (sys.frozen), sys.executable is the exe path,
    root = the directory containing agvmon.exe.

    In development mode, uses current working directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


# ── Update manager ────────────────────────────────────────────

class UpdateManager:
    """Manages the update lifecycle: check, download, apply."""

    def __init__(self):
        self.app_root = get_app_root()
        self.download_dir = self.app_root / "updates"
        self._downloaded_zip: Optional[Path] = None
        self._latest_info: Optional[dict] = None
        self._status = "idle"
        self._status_message = ""

    # ── config helpers ──

    def _get_config(self) -> dict:
        """Read update config from cfg, fallback to env vars."""
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

    # ── public API ──

    @property
    def status(self) -> str:
        return self._status

    @property
    def status_message(self) -> str:
        return self._status_message

    @property
    def latest_info(self) -> Optional[dict]:
        return self._latest_info

    # ── check ─────────────────────────────────────────────────

    async def check(self) -> dict:
        """Check update server for a newer version."""
        from util.__version__ import version as current_ver

        self._status = "checking"

        config = self._get_config()
        result = {
            "current_version": current_ver,
            "update_available": False,
        }

        if not config["update_url"]:
            self._status = "idle"
            self._status_message = "更新服务器未配置"
            result["error"] = self._status_message
            return result

        manifest_url = self._manifest_url(config)

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(manifest_url)
                if resp.status_code == 404:
                    self._status = "idle"
                    self._status_message = "暂无可用版本"
                    result["error"] = self._status_message
                    return result
                if resp.status_code != 200:
                    self._status = "error"
                    self._status_message = f"服务器返回 {resp.status_code}"
                    result["error"] = self._status_message
                    return result
                latest = resp.json()
        except httpx.RequestError as e:
            self._status = "error"
            self._status_message = f"无法连接到更新服务器: {e}"
            result["error"] = self._status_message
            return result
        except json.JSONDecodeError:
            self._status = "error"
            self._status_message = "版本清单格式错误"
            result["error"] = self._status_message
            return result

        result["latest"] = latest
        result["latest_version"] = latest.get("version", "")

        if latest.get("version") and compare_versions(
            latest["version"], current_ver
        ) > 0:
            result["update_available"] = True
            self._latest_info = latest
            self._status = "update_available"
            self._status_message = f"发现新版本 v{latest['version']}"
        else:
            self._status = "idle"
            self._status_message = "已是最新版本"

        return result

    # ── download ──────────────────────────────────────────────

    async def download(self):
        """
        Download the update ZIP from update server.
        Async generator yielding progress dicts.

        Yields: {"event": "progress"/"complete"/"error", ...}
        """
        if not self._latest_info:
            yield {"event": "error", "message": "请先检查更新"}
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
            async with httpx.AsyncClient(
                timeout=600, follow_redirects=True
            ) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        self._status = "error"
                        self._status_message = f"下载失败: HTTP {resp.status_code}"
                        yield {"event": "error", "message": self._status_message}
                        return

                    total = (
                        int(resp.headers.get("content-length", 0)) or expected_size
                    )
                    downloaded = 0
                    sha256_hasher = hashlib.sha256()

                    with open(dest, "wb") as f:
                        async for chunk in resp.aiter_bytes(
                            chunk_size=1024 * 1024
                        ):
                            f.write(chunk)
                            sha256_hasher.update(chunk)
                            downloaded += len(chunk)
                            pct = (
                                round(downloaded / total * 100, 1) if total else 0
                            )
                            yield {
                                "event": "progress",
                                "downloaded": downloaded,
                                "total": total,
                                "percent": pct,
                            }

            # Verify SHA256
            if expected_sha256:
                actual_sha256 = sha256_hasher.hexdigest()
                if actual_sha256 != expected_sha256:
                    dest.unlink(missing_ok=True)
                    self._status = "error"
                    self._status_message = "文件校验失败，请重新下载"
                    yield {"event": "error", "message": self._status_message}
                    return

            self._downloaded_zip = dest
            self._status = "ready"
            self._status_message = "更新已下载，可以重启应用"
            yield {
                "event": "complete",
                "file": safe_name,
                "path": str(dest),
            }

        except httpx.RequestError as e:
            self._status = "error"
            self._status_message = f"下载失败: {e}"
            yield {"event": "error", "message": self._status_message}
            if dest.exists():
                dest.unlink(missing_ok=True)

    # ── apply ─────────────────────────────────────────────────

    def apply(self) -> dict:
        """
        Extract ZIP to staging directory, write batch file, launch updater.

        After this call, the process exits so the batch file can swap
        directories and restart the new version.
        """
        if not getattr(sys, "frozen", False):
            return {"status": "error", "message": "Dev mode: apply is only supported in Nuitka-frozen exe"}

        if not self._downloaded_zip or not self._downloaded_zip.exists():
            return {"status": "error", "message": "未找到下载的更新包"}

        self._status = "applying"

        staging = self.download_dir / ".staging"

        if staging.exists():
            shutil.rmtree(staging)

        try:
            staging.mkdir(parents=True, exist_ok=True)

            # Extract zip to staging
            # Zip files are at root level (7z a -tzip zip_path dist\main.dist\*)
            with zipfile.ZipFile(self._downloaded_zip, "r") as zf:
                for member in zf.namelist():
                    if member.endswith("/") or member.endswith("\\"):
                        continue
                    target = staging / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # Write update.bat in updates/ (bat runs from here, modifies parent)
            self.download_dir.mkdir(parents=True, exist_ok=True)
            bat_path = self.download_dir / "update.bat"
            bat_path.write_text(self._generate_bat_script(), encoding="gbk")

            # Launch batch as detached process
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008

            subprocess.Popen(
                ["cmd", "/c", "start", "AGVmon Update", "/min", str(bat_path)],
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
                if sys.platform == "win32"
                else 0,
                cwd=str(self.app_root),
                close_fds=True,
            )

            self._status_message = "更新已准备，系统即将重启"
            return {"status": "applying", "message": self._status_message}

        except OSError as e:
            self._status = "error"
            self._status_message = f"应用更新失败: {e}"
            return {"status": "error", "message": self._status_message}

    # ── batch script ──────────────────────────────────────────

    @staticmethod
    def _generate_bat_script() -> str:
        """Generate the swap-and-restart batch script (English for compatibility)."""
        return """@echo off
title AGVmon Update
echo.
echo ============================================
echo   AGVmon Updater
echo ============================================
echo.
echo Waiting for main process to exit...
timeout /t 3 /nobreak >nul
echo.
cd /d "%~dp0"
if not exist ".staging\\agvmon.exe" (
    echo Update package not found
    pause >nul
    del "%~f0" 2>nul
    exit /b 1
)
echo Backing up current version...
if exist ".old" rmdir /s /q ".old"
robocopy ".." ".old" /E /MOVE /XD "updates" "config.toml" >nul 2>&1
echo Installing update...
robocopy ".staging" ".." /E /MOVE /IS /IT >nul 2>&1
if errorlevel 8 (
    echo Install failed, rolling back...
    rmdir /s /q ".." 2>nul
    move /y ".old\\*" "..\\" >nul 2>&1
    rmdir /s /q ".old"
    echo Rollback complete
) else (
    echo Starting new version...
    start "" "..\\agvmon.exe"
    if errorlevel 1 (
        echo Launch failed, rolling back...
        rmdir /s /q ".." 2>nul
        move /y ".old\\*" "..\\" >nul 2>&1
        rmdir /s /q ".old"
        echo Rollback complete, please start manually
    ) else (
        echo Cleaning up...
        timeout /t 2 /nobreak >nul
        if exist ".old" rmdir /s /q ".old"
    )
)
echo.
echo Press any key to close...
pause >nul
del "%~f0" 2>nul
"""


# ── Singleton ─────────────────────────────────────────────────

_updater: Optional[UpdateManager] = None


def get_updater() -> UpdateManager:
    """Get or create the global UpdateManager instance."""
    global _updater
    if _updater is None:
        _updater = UpdateManager()
    return _updater
