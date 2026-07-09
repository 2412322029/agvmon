import asyncio
import inspect
import logging
import os
import re
import sys
import tarfile
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

# Allow running this file directly from the project root
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from util.agv_protocol_parser import AGVProtocolParser
from util.config import cfg

logger = logging.getLogger(__name__)
_parser = AGVProtocolParser()
PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+).*?"
    r"task_key\s*=\s*'([^']*)'.*?"
    r"action_type\s*=\s*'([^']*)'.*?"
    r"(?:task_step\s*=\s*'([^']*)'.*?)?"
    r"request\s*=\s*'([^']*)'.*?"
    r"response\s*=\s*'([^']*)'.*?"
    r"result\s*=\s*'([^']*)'"
)

WCSLOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wcslog")
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
MAX_FILES = 20

# Timestamp-only regex for extracting first/last time from log lines
_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")

WCS_LOG_BASE = cfg.get("rcms.wcs_log_base")


async def list_wcs_logs(client: httpx.AsyncClient | None = None) -> list[dict]:
    """List default.log files (including .1, .2, ...) from WCS log server.

    Returns a list of dicts with keys: filename, time (datetime), download_url.
    Sorted by time descending (newest first).
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    try:
        resp = await client.get(f"{WCS_LOG_BASE}/logs")
        resp.raise_for_status()
        html = resp.text

        sections = re.findall(r'<div id="section">(.*?)</div>', html, re.DOTALL)
        if len(sections) < 2:
            raise ValueError("Could not parse log listing page")

        # Section 1: filenames — strip <a> links (dump, log_bak), keep plain text names
        s1 = re.sub(r'<a[^>]*>.*?</a>', '', sections[0])
        filenames = re.findall(r'([A-Za-z][^\s<>]*\.log(?:\.\d+)?)', s1)

        # Section 2: timestamps and download hrefs
        items = re.findall(
            r'(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*?href="(/logs/download/[^"]+)"',
            sections[1], re.DOTALL,
        )

        now = datetime.now()
        results = []
        for i, fname in enumerate(filenames):
            if not fname.startswith("default.log"):
                continue
            if i >= len(items):
                break
            time_str, href = items[i]
            # Infer year: if MM-DD is in the future, use previous year
            parsed = datetime.strptime(time_str, "%m-%d %H:%M:%S")
            year = now.year
            if parsed.month > now.month or (parsed.month == now.month and parsed.day > now.day):
                year -= 1
            dt = parsed.replace(year=year)
            results.append({
                "filename": fname,
                "time": dt,
                "download_url": f"{WCS_LOG_BASE}{href}",
            })

        results.sort(key=lambda r: r["time"], reverse=True)
        return results
    finally:
        if own_client:
            await client.aclose()


async def download_wcs_log(filename: str, save_dir: str | None = None,
                           client: httpx.AsyncClient | None = None,
                           progress_cb: Callable[[int, int], Any] | None = None) -> str:
    """Download a WCS log file to *save_dir* (defaults to util/data/wcslog/).

    If *progress_cb* is given, it is called as ``progress_cb(downloaded, total)``
    periodically during the download.  Both sync and async callbacks are supported.
    """
    if save_dir is None:
        save_dir = WCSLOG_DIR
    os.makedirs(save_dir, exist_ok=True)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    try:
        url = f"{WCS_LOG_BASE}/logs/download/{filename}"
        dest = os.path.join(save_dir, filename)
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        if inspect.iscoroutinefunction(progress_cb):
                            await progress_cb(downloaded, total)
                        else:
                            progress_cb(downloaded, total)
        # Rename to HH:MM:SS—HH:MM:SS_default.log based on log timestamps
        time_range = _get_log_time_range(dest)
        if time_range:
            start, end = time_range
            start_time = _ts_to_time_str(start)
            end_time = _ts_to_time_str(end)
            new_name = f"{start_time}—{end_time}_default.log"
            new_dest = os.path.join(save_dir, new_name)
            if not os.path.exists(new_dest):
                try:
                    os.rename(dest, new_dest)
                    dest = new_dest
                except OSError:
                    pass
        return dest
    finally:
        if own_client:
            await client.aclose()


async def _get_logbak_url(client: httpx.AsyncClient) -> str | None:
    """Extract the *log_bak* directory URL from section 0 of the main /logs page.

    Returns the full URL (e.g. ``http://172.27.6.45:8096/logs*log_bak``)
    or ``None`` if not found.
    """
    resp = await client.get(f"{WCS_LOG_BASE}/logs")
    resp.raise_for_status()
    html = resp.text
    sections = re.findall(r'<div id="section">(.*?)</div>', html, re.DOTALL)
    if not sections:
        return None
    # Section 0 ends with: <a href="/logs*log_bak">log_bak</a>
    m = re.search(r'''<a[^>]*href=["']([^"']*log_bak[^"']*)["']''', sections[0])
    if m:
        href = m.group(1)
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"{WCS_LOG_BASE}{href}"
        return f"{WCS_LOG_BASE}/{href}"
    return None


async def list_wcs_logbak(client: httpx.AsyncClient | None = None) -> list[dict]:
    """List compressed log archives from the *log_bak* directory.

    Returns a list of dicts with keys: *filename*, *time* (datetime),
    *download_url*.  Sorted by time descending (newest first).
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    try:
        logbak_url = await _get_logbak_url(client)
        if logbak_url is None:
            logger.warning("log_bak URL not found on main page, using fallback")
            logbak_url = f"{WCS_LOG_BASE}/logs*log_bak"

        resp = await client.get(logbak_url)
        resp.raise_for_status()
        html = resp.text

        sections = re.findall(r'<div id="section">(.*?)</div>', html, re.DOTALL)
        if len(sections) < 2:
            raise ValueError(f"Could not parse log_bak listing page at {logbak_url}")

        # Section 0: filenames only (no <a> links, plain <br>FILENAME&nbsp;...)
        # Strip all HTML tags to leave only text, then extract non-empty tokens
        s0_text = re.sub(r'<[^>]+>', ' ', sections[0])
        s0_text = re.sub(r'&nbsp;', ' ', s0_text)
        filenames = s0_text.split()

        # Section 1: timestamps and download hrefs (absolute URLs)
        # Format: <br>MM-DD HH:MM:SS&nbsp;...<a href="http://.../download/FILE">download</a>
        items = re.findall(
            r'''(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*?href=["']([^"']+/download/[^"']+)["']''',
            sections[1], re.DOTALL,
        )

        # Fallback: if absolute hrefs not found, try relative /logs/download/ pattern
        if not items:
            items = re.findall(
                r'''(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*?href=["'](/logs/download/[^"']+)["']''',
                sections[1], re.DOTALL,
            )

        now = datetime.now()
        results: list[dict] = []
        for i, fname in enumerate(filenames):
            if i >= len(items):
                break
            time_str, href = items[i]
            parsed = datetime.strptime(time_str, "%m-%d %H:%M:%S")
            year = now.year
            if parsed.month > now.month or (parsed.month == now.month and parsed.day > now.day):
                year -= 1
            dt = parsed.replace(year=year)
            # Use href as-is if absolute, else prepend base
            if href.startswith("http"):
                download_url = href
            else:
                download_url = f"{WCS_LOG_BASE}{href}"
            results.append({
                "filename": fname,
                "time": dt,
                "download_url": download_url,
            })

        results.sort(key=lambda r: r["time"], reverse=True)
        return results
    finally:
        if own_client:
            await client.aclose()


async def download_wcs_logbak(filename: str, save_dir: str | None = None,
                               client: httpx.AsyncClient | None = None,
                               progress_cb: Callable[[int, int], Any] | None = None) -> str:
    """Download a compressed log archive from the *log_bak* directory.

    Similar to :func:`download_wcs_log` but with a longer default timeout
    (60 s) for larger archive files.
    """
    if save_dir is None:
        save_dir = WCSLOG_DIR
    os.makedirs(save_dir, exist_ok=True)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    try:
        # log_bak download URL uses *log_bak path
        url = f"{WCS_LOG_BASE}/logs*log_bak/download/{filename}"
        dest = os.path.join(save_dir, filename)
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        if inspect.iscoroutinefunction(progress_cb):
                            await progress_cb(downloaded, total)
                        else:
                            progress_cb(downloaded, total)
        return dest
    finally:
        if own_client:
            await client.aclose()


def _get_log_time_range(filepath: str) -> tuple[str, str] | None:
    """Extract the first and last timestamp from a WCS log file.

    Returns ``(first_ts, last_ts)`` as raw timestamp strings
    (e.g. ``'2024-01-15 10:30:45.123456'``), or ``None``.
    """
    first_ts: str | None = None
    last_ts: str | None = None

    # First timestamp — scan from beginning
    with open(filepath, encoding="GBK", errors="replace") as f:
        for line in f:
            m = _TS_RE.search(line)
            if m:
                first_ts = m.group(1)
                break

    if first_ts is None:
        return None

    # Last timestamp — scan tail of file (last 64 KB)
    try:
        fsize = os.path.getsize(filepath)
    except OSError:
        return None
    if fsize == 0:
        return None

    with open(filepath, "rb") as f:
        tail_size = min(65536, fsize)
        f.seek(fsize - tail_size)
        tail = f.read(tail_size).decode("GBK", errors="replace")
        matches = _TS_RE.findall(tail)
        if matches:
            last_ts = matches[-1]

    if last_ts is None:
        return None
    return (first_ts, last_ts)


def _ts_to_time_str(ts: str) -> str:
    """Convert ``'2024-01-15 10:30:45.123456'`` → ``'20240115_103045123456'``."""
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
    return dt.strftime("%Y%m%d_%H%M%S")


# ── tar.bz2 selective extraction ─────────────────────────────────────

_DEFAULT_LOG_PAT = re.compile(r"^default\.log(?:\.\d+)?$")


class _ProgressReader:
    """Wrap a file object to report bytes-read progress via a callback.

    Implements enough of the ``IOBase`` interface to satisfy ``bz2.BZ2File``.
    """

    def __init__(self, fp, total: int, cb: Callable[[int, int], Any] | None):
        self._fp = fp
        self._total = total
        self._cb = cb
        self._read = 0
        self._last_report = 0

    def read(self, size: int = -1) -> bytes:
        data = self._fp.read(size)
        self._read += len(data)
        if self._cb and (self._read - self._last_report >= 131072 or not data):
            self._last_report = self._read
            try:
                self._cb(self._read, self._total)
            except Exception:
                logger.warning("Progress callback failed", exc_info=True)
        return data

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray) -> int:
        data = self.read(len(b))
        if not data:
            return 0
        b[:len(data)] = data
        return len(data)

    def seekable(self) -> bool:
        return False

    def close(self) -> None:
        self._fp.close()


def list_tar_files(tar_path: str, pattern: str | re.Pattern | None = None) -> list[str]:
    """List files inside a ``.tar.bz2`` archive matching *pattern*.

    *pattern* can be a regex string or a compiled ``re.Pattern``.
    Defaults to ``^default\\.log(?:\\.\\d+)?$``.
    """
    if pattern is None:
        pat = _DEFAULT_LOG_PAT
    elif isinstance(pattern, str):
        pat = re.compile(pattern)
    else:
        pat = pattern

    names: list[str] = []
    with tarfile.open(tar_path, "r|bz2") as tar:
        while (member := tar.next()) is not None:
            if member.isfile() and pat.search(os.path.basename(member.name)):
                names.append(member.name)
    return names


def extract_tar_files(tar_path: str, dest_dir: str,
                      pattern: str | re.Pattern | None = None,
                      members: set[str] | None = None,
                      progress_cb: Callable[[int, int], Any] | None = None,
                      ) -> list[str]:
    """Extract matching files from a ``.tar.bz2`` archive to *dest_dir*.

    Pure-Python streaming via ``bz2.BZ2File`` → ``tarfile`` pipe.
    The bzip2 stream is decompressed exactly once, and matching members
    are written out as they are encountered.

    *progress_cb(read_bytes, total_bytes)* is called periodically during
    decompression so callers can show a progress bar.  Both sync and
    async callbacks are accepted.
    """
    os.makedirs(dest_dir, exist_ok=True)

    total = os.path.getsize(tar_path)
    raw_fp = open(tar_path, "rb")
    tracked = _ProgressReader(raw_fp, total, progress_cb)

    try:
        import bz2 as _bz2
        bz2_fp = _bz2.BZ2File(tracked, "rb")
    except Exception:
        # If BZ2File wrapper fails (e.g. missing file methods), log and fall back
        logger.warning("BZ2File(fileobj) failed, falling back to legacy (no progress)", exc_info=True)
        tracked.close()
        return _extract_tar_files_legacy(tar_path, dest_dir, pattern, members)

    extracted: list[str] = []
    member_set = members

    try:
        with tarfile.open(fileobj=bz2_fp, mode="r|") as tar:
            while (member := tar.next()) is not None:
                if not member.isfile():
                    continue
                name = os.path.basename(member.name)
                if member_set is not None:
                    if name not in member_set and member.name not in member_set:
                        continue
                elif pattern is not None:
                    pat_obj = re.compile(pattern) if isinstance(pattern, str) else pattern
                    if not pat_obj.search(name):
                        continue
                else:
                    if not _DEFAULT_LOG_PAT.search(name):
                        continue

                fobj = tar.extractfile(member)
                if fobj is None:
                    continue
                dest = os.path.join(dest_dir, name)
                with open(dest, "wb") as f:
                    while True:
                        chunk = fobj.read(4 * 1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                extracted.append(dest)
    finally:
        bz2_fp.close()

    return extracted


def _extract_tar_files_legacy(tar_path: str, dest_dir: str,
                               pattern, members) -> list[str]:
    """Fallback using tarfile's built-in bz2 mode (no progress tracking)."""
    extracted: list[str] = []
    member_set = members
    with tarfile.open(tar_path, "r|bz2") as tar:
        while (member := tar.next()) is not None:
            if not member.isfile():
                continue
            name = os.path.basename(member.name)
            if member_set is not None:
                if name not in member_set and member.name not in member_set:
                    continue
            elif pattern is not None:
                pat_obj = re.compile(pattern) if isinstance(pattern, str) else pattern
                if not pat_obj.search(name):
                    continue
            else:
                if not _DEFAULT_LOG_PAT.search(name):
                    continue
            fobj = tar.extractfile(member)
            if fobj is None:
                continue
            dest = os.path.join(dest_dir, name)
            with open(dest, "wb") as f:
                while True:
                    chunk = fobj.read(4 * 1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            extracted.append(dest)
    return extracted


def _build_filter(shortcode: str | None, taskid: str | None,
                  device_type: str | None) -> re.Pattern | None:
    """Build a regex to filter WCS log lines.

    task_key format: <device_type>_<shortcode>_<taskid>
    e.g. Detector_514000_9F59603FFD2E8_324FA059DD00_WCS

    All three parameters are optional and can be combined freely.
    """
    if not shortcode and not taskid and not device_type:
        return None

    # Segment 1: device type (Detector/Rotate/...) or any
    if device_type:
        key_pattern = re.escape(device_type)
    else:
        key_pattern = r"[^_]+"

    # Segment 2: shortcode (设备外设编号) or any
    if shortcode:
        escaped = re.escape(shortcode)
        escaped = escaped.replace(r"x", r".")  # x → wildcard
        key_pattern = rf"{key_pattern}_{escaped}"
    else:
        key_pattern = rf"{key_pattern}_[^_]+"

    # Remainder: taskid (任务id) or any trailing chars
    if taskid:
        escaped_taskid = re.escape(taskid)
        key_pattern = rf"{key_pattern}.*{escaped_taskid}"
    else:
        key_pattern = rf"{key_pattern}.*"

    return re.compile(
        rf">,task_key = '{key_pattern}'", re.IGNORECASE
    )


def parse(filepath: str, shortcode: str | None = None, trayid_hex: str | None = None,
          taskid: str | None = None, device_type: str | None = None) -> Iterator[dict]:
    filt = _build_filter(shortcode, taskid, device_type)
    with open(filepath, encoding="GBK", errors="replace") as f:
        for line in f:
            if filt and not filt.search(line):
                continue
            m = PATTERN.search(line)
            if not m:
                continue
            response = m.group(6)
            if trayid_hex and trayid_hex.lower() not in response.lower():
                continue
            yield {
                "time": m.group(1),
                "task_key": m.group(2),
                "action_type": m.group(3),
                "task_step": m.group(4) or "",
                "request": m.group(5),
                "response": response,
                "result": m.group(7),
            }


def _collect_default_files() -> list[str]:
    """Scan ./data/wcslog/ for *default.log* files, with size/name checks."""
    os.makedirs(WCSLOG_DIR, exist_ok=True)  # Ensure directory exists

    all_files = sorted(
        os.path.join(WCSLOG_DIR, f)
        for f in os.listdir(WCSLOG_DIR)
        if os.path.isfile(os.path.join(WCSLOG_DIR, f))
    )

    candidates = [f for f in all_files if "default.log" in os.path.basename(f)]
    if not candidates:
        logger.warning(f"No file containing 'default.log' found in {WCSLOG_DIR}")

    checked: list[str] = []
    for fp in candidates:
        if len(checked) >= MAX_FILES:
            print(f"Reached max file limit ({MAX_FILES}), skipping remaining files")
            break
        try:
            size = os.path.getsize(fp)
        except OSError:
            continue
        if size > MAX_FILE_SIZE:
            logger.warning(
                f"File exceeds 15MB, skipping: {os.path.basename(fp)} ({size / 1024 / 1024:.1f} MB)"
            )
            continue
        checked.append(fp)
    return checked


# ── ANSI color helpers ──────────────────────────────────────────────
_K = "\033[2m"      # dim → keys  (cmd=, layer=, port1=)
_T = "\033[92m"     # green → Chinese text
_H = "\033[93m"     # yellow → hex codes 01, 02
_P = "\033[94m"     # blue → port names
_I = "\033[95m"     # magenta → tray IDs
_S = "\033[90m"     # dark gray → separators
_C = "\033[96m"     # cyan → task_key, action_type
_G = "\033[92m"     # green → result=yes
_RED = "\033[91m"   # red → result=no/error
_TM = "\033[33m"    # yellow → timestamp
_SC = "\033[93m"    # bright yellow → shortcode in task_key
_R = "\033[0m"      # reset


def _color_task_key(key: str) -> str:
    """Highlight the shortcode part of 'Detector_XXXXXX_...' keys."""
    m = re.match(r"(Detector_)([^_]+)(_.*)", key)
    if m:
        return f"{_K}{m.group(1)}{_R}{_SC}{m.group(2)}{_R}{_K}{m.group(3)}{_R}"
    return f"{_C}{key}{_R}"


_AGV_FIELDS = ("port1", "port2", "agvArrived", "rollerAction",
               "agvTrayOk", "agvLeave", "traySize")


def _fmt_agv_cmd(hex_str: str) -> list[str]:
    """Decode an AGV command hex string, return formatted lines."""
    if not hex_str:
        return ["(empty)"]
    try:
        r = _parser.parse_agv_command(hex_str)
        if not r["isValid"]:
            return [f"AGV parse failed: {r.get('error', 'unknown')}"]
        c = r["command"]
        parts = [
            f"{_K}cmd={_R}{_T}{c['commandTypeText']}{_R}({_H}{c['commandType']:02x}{_R})",
            f"layer={c['layerText']}({c['layer']:02x})",
        ]
        if c["commandType"] == 0x02:  # 控制指令才显示后续字段
            for key in _AGV_FIELDS:
                f = c[key]
                parts.append(
                    f"{_K}{key}={_R}{_T}{f['text']}{_R}({_H}{f['code']:02x}{_R})"
                )
        if r["trayId"]:
            parts.append(f"{_K}trayId={_R}{_I}{r['trayId']}{_R}")
        if r["trayId2"]:
            parts.append(f"{_K}trayId2={_R}{_I}{r['trayId2']}{_R}")
        return ["  ".join(parts)]
    except Exception:
        return [f"({hex_str[:20]}...)"]


_STATUS_KEYS = ("readyStatus", "trayOkStatus", "onlineStatus",
                "trayPresentStatus", "rollerStartStatus",
                "manualOperation", "traySize")


def _fmt_eq_status(hex_str: str) -> list[str]:
    """Decode an EQ status hex string, return formatted lines with all port details."""
    if not hex_str:
        return ["(empty)"]
    try:
        r = _parser.parse_eq_status(hex_str)
        if not r["isValid"]:
            return [f"EQ parse failed: {r.get('error', 'unknown')}"]
        g = r["gratingStatus"]
        lo_s = g.get("lowerGrating", {})
        up_s = g.get("upperGrating", {})
        lo = f"{_T}{lo_s.get('text', '?')}{_R}({_K}{lo_s.get('code', 0):02x}{_R})"
        up = f"{_T}{up_s.get('text', '?')}{_R}({_K}{up_s.get('code', 0):02x}{_R})"
        lines = [f"{_K}ports={_R}{r['portCount']}  {_K}grating={_R}{lo}/{up}"]

        # header row
        sep = f"{_S} | {_R}"
        header = sep.join(
            f"{_K}{k}{_R}" for k in ("Port", *_STATUS_KEYS, "trayId")
        )
        lines.append(f"  {header}")

        # data rows
        for p in r["ports"]:
            s = p["status"]
            vals = [f"{_P}{p['portPosition']}{_R}"]
            for key in _STATUS_KEYS:
                st = s.get(key, {})
                vals.append(
                    f"{_T}{st.get('text', '?')}{_R}({_K}{st.get('code', 0):02x}{_R})"
                )
            vals.append(f"{_I}{p['trayId']}{_R}")
            lines.append(f"  {sep.join(vals)}")
        return lines
    except Exception:
        return [f"({hex_str[:20]}...)"]


def run(files: list[str] | None = None, code: str | None = None,
        taskid: str | None = None, device_type: str | None = None) -> None:
    """Parse WCS log files and print results. If files is empty, scans ./data/wcslog/."""
    file_list = list(files) if files else _collect_default_files()

    if not file_list:
        print("No files to parse.")
        return
    if len(file_list) > MAX_FILES:
        print(f"Too many files ({len(file_list)}), limiting to first {MAX_FILES}")
        file_list = file_list[:MAX_FILES]

    for fp in file_list:
        try:
            size = os.path.getsize(fp)
        except OSError:
            print(f"Cannot access file: {fp}")
            continue
        if size > MAX_FILE_SIZE:
            logger.warning(
                f"File exceeds 15MB, results may be truncated: "
                f"{os.path.basename(fp)} ({size / 1024 / 1024:.1f} MB)"
            )
        print(f"--- {os.path.basename(fp)} ---")
        count = 0
        yes_count = 0
        for row in parse(fp, code, taskid=taskid, device_type=device_type):
            result_color = _G if row['result'].lower() == 'yes' else _RED
            print(
                f"{_TM}{row['time']}{_R} {_S}|{_R} "
                f"{_color_task_key(row['task_key']):<50} {_S}|{_R} "
                f"{_C}{row['action_type']:<10}{_R} {_S}|{_R} "
                f"{row['request'][:20]:<20}... {_S}|{_R} "
                f"{row['response'][:20]:<20}... {_S}|{_R} "
                f"{result_color}{row['result']}{_R}"
            )
            for line in _fmt_agv_cmd(row["request"]):
                print(f"  req → {line}")
            if row['result'].lower() == 'yes':
                yes_count += 1
            for line in _fmt_eq_status(row["response"]):
                print(f"  resp → {line}")
            count += 1
            print("──" * 70)
        print(f"  ({yes_count} responses yes in {count} matches for {fp })\n")



def _print_progress(downloaded: int, total: int) -> None:
    """Simple console progress bar."""
    pct = downloaded / total * 100 if total > 0 else 0
    bar_len = 40
    filled = int(bar_len * downloaded / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  [{bar}] {pct:.0f}%  {downloaded / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB", end="")


async def _cmd_list() -> None:
    """List log files and log_bak archives."""
    print("Fetching log list...")
    logs = await list_wcs_logs()
    print(f"\n=== default.log files ({len(logs)}) ===")
    for item in logs:
        print(f"  {item['time'].strftime('%Y-%m-%d %H:%M')}  {item['filename']}")

    print("\nFetching log_bak archives...")
    try:
        bak = await list_wcs_logbak()
        print(f"\n=== log_bak archives ({len(bak)}) ===")
        for item in bak:
            size_hint = ""
            print(f"  {item['time'].strftime('%Y-%m-%d %H:%M')}  {item['filename']}{size_hint}")
    except Exception as e:
        print(f"  log_bak listing failed: {e}")


async def _cmd_download(filenames: list[str]) -> None:
    """Download one or more files.  Auto-detects log vs log_bak by extension."""
    for fname in filenames:
        if fname.endswith(".tar.bz2") or fname.endswith(".tar.gz") or fname.endswith(".zip"):
            # log_bak archive
            print(f"Downloading log_bak: {fname}")
            dest = await download_wcs_logbak(fname, progress_cb=_print_progress)
        else:
            # regular log file
            print(f"Downloading log: {fname}")
            dest = await download_wcs_log(fname, progress_cb=_print_progress)
        print(f"\n  → {dest}")


async def _cmd_download_all() -> None:
    """Download all default.log files."""
    logs = await list_wcs_logs()
    if not logs:
        print("No default.log files found.")
        return
    print(f"Downloading {len(logs)} default.log files...")
    for item in logs:
        fname = item["filename"]
        print(f"  {fname} ... ", end="")
        try:
            dest = await download_wcs_log(fname)
            print(dest)
        except Exception as e:
            print(f"FAILED: {e}")


def _print_usage() -> None:
    print(f"Usage: python {sys.argv[0]} <command> [args]")
    print("Commands:")
    print("  list              List available log files and log_bak archives")
    print("  download <file>   Download one or more files (auto-detect type)")
    print("  download-all      Download all default.log files")
    print("  parse [files]     Parse local log files (no args = scan ./data/wcslog/)")
    print()
    print("Examples:")
    print("  python parse_wcs_log.py list")
    print("  python parse_wcs_log.py download default.log")
    print("  python parse_wcs_log.py download wcs.log.bak20260708110639.tar.bz2")
    print("  python parse_wcs_log.py download-all")
    print("  python parse_wcs_log.py parse 5280xx")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        _print_usage()
    elif args[0] == "list":
        asyncio.run(_cmd_list())
    elif args[0] == "download":
        if len(args) < 2:
            print("Error: 'download' requires at least one filename.")
            _print_usage()
        else:
            asyncio.run(_cmd_download(args[1:]))
    elif args[0] == "download-all":
        asyncio.run(_cmd_download_all())
    elif args[0] == "parse":
        if len(args) < 2:
            run()
        else:
            parse_args = args[1:]
            maybe_code = parse_args[-1] if parse_args else None
            files_from_args = [a for a in parse_args if os.path.isfile(a)]
            code = maybe_code if maybe_code not in files_from_args else None
            if not files_from_args:
                print(f"Usage: python {sys.argv[0]} parse [logfile ...] [detector_code]")
                print("  Without file args, scans ./data/wcslog/ for *default.log* files")
                print("  detector_code: optional, e.g. 528000 or 5280xx (xx = wildcard)")
                sys.exit(1)
            run(files_from_args, code)
    else:
        _print_usage()
