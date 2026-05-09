import logging
import os
import re
import sys
from collections.abc import Iterator

from util.agv_protocol_parser import AGVProtocolParser

logger = logging.getLogger(__name__)
_parser = AGVProtocolParser()
PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+).*?"
    r"task_key\s*=\s*'([^']*)'.*?"
    r"action_type\s*=\s*'([^']*)'.*?"
    r"request\s*=\s*'([^']*)'.*?"
    r"response\s*=\s*'([^']*)'.*?"
    r"result\s*=\s*'([^']*)'"
)

WCSLOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wcslog")
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
MAX_FILES = 20


def _build_filter(shortcode: str | None) -> re.Pattern | None:
    if not shortcode:
        return None
    escaped = re.escape(shortcode)
    escaped = escaped.replace(r"x", r".")
    return re.compile(
        rf"<ReadDeviceState>,task_key = 'Detector_{escaped}", re.IGNORECASE
    )


def parse(filepath: str, shortcode: str | None = None) -> Iterator[dict]:
    filt = _build_filter(shortcode)
    with open(filepath, encoding="GBK", errors="replace") as f:
        for line in f:
            if filt and not filt.search(line):
                continue
            m = PATTERN.search(line)
            if m:
                yield {
                    "time": m.group(1),
                    "task_key": m.group(2),
                    "action_type": m.group(3),
                    "request": m.group(4),
                    "response": m.group(5),
                    "result": m.group(6),
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


def run(files: list[str] | None = None, code: str | None = None) -> None:
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
        for row in parse(fp, code):
            result_color = _G if row['result'].lower() == 'yes' else _RED
            print(
                f"{_TM}{row['time']}{_R} {_S}|{_R} "
                f"{_color_task_key(row['task_key']):<50} {_S}|{_R} "
                f"{_C}{row['action_type']:<10}{_R} {_S}|{_R} "
                f"{row['request'][:20]:<20}... {_S}|{_R} "
                f"{row['response'][:20]:<20}... {_S}|{_R} "
                f"{result_color}{row['result']}{_R}"
            )
            if row["task_key"].startswith("Detector_"):
                for line in _fmt_agv_cmd(row["request"]):
                    print(f"  req → {line}")
                if row['result'].lower() == 'yes':
                    yes_count += 1
                    for line in _fmt_eq_status(row["response"]):
                        print(f"  resp → {line}")
                count += 1
            print("──" * 70)
        print(f"  ({yes_count} responses yes in {count} matches for {fp })\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        run()
    else:
        args = sys.argv[1:]
        maybe_code = args[-1]
        files_from_args = [a for a in args if os.path.isfile(a)]
        code = maybe_code if maybe_code not in files_from_args else None
        if not files_from_args:
            print(f"Usage: python {sys.argv[0]} [logfile ...] [detector_code]")
            print("  Without args, scans ./data/wcslog/ for *default.log* files")
            print("  detector_code: optional, e.g. 528000 or 5280xx (xx = wildcard)")
            sys.exit(1)
        run(files_from_args, code)
