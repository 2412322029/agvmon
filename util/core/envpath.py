"""管理 agvmon.exe 所在目录与 Windows 用户 PATH 环境变量。

PATH 是目录列表，无法直接放单个 exe，所以本模块把 agvmon.exe 所在目录
作为一条 PATH 项写入/移出。只操作 HKCU\\Environment\\Path（用户级），
不需要管理员权限；写入时保留原注册表值类型（REG_SZ / REG_EXPAND_SZ），
写完广播 WM_SETTINGCHANGE，资源管理器此后新开的进程即可感知，
已打开的终端不受影响（需要重开窗口）。

本模块只依赖标准库，不 import 任何项目模块，由 main.py 的 env 子命令按需导入。
"""

import os
import sys
from pathlib import Path

_ENV_KEY = "Environment"  # HKCU 下的环境变量键


def _is_frozen() -> bool:
    """Nuitka 打包后 __compiled__ 注入到模块 globals；与 updater.py 同一判法。"""
    return bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()


def resolve_target_dir() -> Path:
    """返回应写入 PATH 的目录：打包后是 exe 所在目录，开发模式是 dist 构建目录。

    构建脚本把输出按平台分到 dist/windows|linux/main.dist（两平台互不覆盖），
    旧布局 dist/main.dist 作为回退保留——PATH 里已登记的旧目录仍能被 remove 清理。
    """
    if _is_frozen():
        return Path(sys.executable).parent

    from util.core.paths import PROJECT_ROOT

    exe_name = "agvmon.exe" if os.name == "nt" else "agvmon"
    sub = "windows" if os.name == "nt" else "linux"
    dist = Path(PROJECT_ROOT) / "dist" / sub / "main.dist"
    if (dist / exe_name).is_file():
        return dist
    legacy = Path(PROJECT_ROOT) / "dist" / "main.dist"  # 旧布局
    if (legacy / "agvmon.exe").is_file():
        return legacy
    raise RuntimeError(
        f"未找到打包产物 agvmon（预期位置: {dist}），请先运行 python build_nuitka.py"
    )


def _read_user_path():
    """读取 HKCU\\Environment 下的 PATH，返回 (实际值名, 值, 类型)。

    值名大小写在不同机器上可能是 Path/PATH，用枚举拿原名，写回时避免
    因大小写不一致产生重复值；不存在时返回 ("Path", "", None)。
    """
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY, 0, winreg.KEY_READ) as key:
        index = 0
        while True:
            try:
                name, value, vtype = winreg.EnumValue(key, index)
            except OSError:
                break
            if name.lower() == "path":
                return name, value, vtype
            index += 1
    return "Path", "", None


def _write_user_path(name: str, value: str, vtype) -> None:
    """写回 PATH，保留原值类型；新值默认 REG_EXPAND_SZ（与系统默认一致）。"""
    import winreg

    if vtype is None:
        vtype = winreg.REG_EXPAND_SZ
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, vtype, value)


def _norm(entry: str) -> str:
    """PATH 项比较用的归一化：去引号/空白、展开 %VAR%、忽略大小写和尾部反斜杠。"""
    import ntpath

    entry = entry.strip().strip('"')
    if not entry:
        return ""
    return ntpath.normcase(ntpath.normpath(ntpath.expandvars(entry)))


def _broadcast_change() -> None:
    """广播环境变量变更，让资源管理器新开的进程拿到新 PATH。"""
    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_size_t(0)
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            3000,
            ctypes.byref(result),
        )
    except Exception:
        # 广播失败只影响"立即生效"，不影响注册表写入结果
        pass


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("该命令仅支持 Windows")


def add() -> str:
    """把 agvmon.exe 所在目录加入用户 PATH（幂等，已存在则不动）。"""
    _require_windows()
    target = resolve_target_dir()
    name, value, vtype = _read_user_path()
    tnorm = _norm(str(target))
    if any(_norm(e) == tnorm for e in value.split(";")):
        return f"已在用户 PATH 中，无需重复添加: {target}"

    kept = value.rstrip(";")
    new_value = f"{kept};{target}" if kept else str(target)
    _write_user_path(name, new_value, vtype)
    _broadcast_change()
    return (
        f"已添加到用户 PATH（HKCU\\Environment\\{name}）: {target}\n"
        "重开终端窗口后即可直接使用 agvmon 命令"
    )


def in_user_path() -> bool:
    """agvmon.exe 所在目录是否已在用户 PATH 中（供 autostart 等模块复用）。"""
    target = str(resolve_target_dir())
    _, value, _ = _read_user_path()
    return any(_norm(e) == _norm(target) for e in value.split(";"))


def remove() -> str:
    """把 agvmon.exe 所在目录从用户 PATH 移除（幂等，不存在则不动）。"""
    _require_windows()
    target = resolve_target_dir()
    name, value, vtype = _read_user_path()
    tnorm = _norm(str(target))
    entries = value.split(";")
    kept = [e for e in entries if _norm(e) != tnorm]
    if len(kept) == len(entries):
        return f"用户 PATH 中没有该目录，无需移除: {target}"

    _write_user_path(name, ";".join(kept), vtype)
    _broadcast_change()
    return f"已从用户 PATH 移除: {target}"


def show() -> str:
    """查看目标目录、是否已在 PATH，以及当前用户 PATH 的完整内容（只读）。"""
    _require_windows()
    name, value, vtype = _read_user_path()

    try:
        target = str(resolve_target_dir())
        target_line = f"agvmon.exe 目录: {target}"
    except RuntimeError as e:
        target = None
        target_line = f"agvmon.exe 目录: 未找到（{e}）"

    vtype_name = {
        1: "REG_SZ",
        2: "REG_EXPAND_SZ",
        3: "REG_BINARY",
        4: "REG_DWORD",
    }.get(vtype, str(vtype) if vtype is not None else "未设置")
    entries = [e for e in value.split(";") if e.strip()]
    present = target is not None and any(_norm(e) == _norm(target) for e in entries)

    lines = [
        target_line,
        f"在用户 PATH 中: {'是' if present else '否'}",
        f"注册表值: HKCU\\Environment\\{name} ({vtype_name})",
        f"用户 PATH 共 {len(entries)} 项:",
    ]
    GREEN = "\033[32m"
    RESET = "\033[0m"

    for i, e in enumerate(entries, 1):
        if target and _norm(e) == _norm(target):
            lines.append(f"  {GREEN}{i:>2}. {e}  <- agvmon{RESET}")
        else:
            mark = "  <- agvmon" if target and _norm(e) == _norm(target) else ""
            lines.append(f"  {i:>2}. {e}{mark}")
    return "\n".join(lines)