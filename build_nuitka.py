#!/usr/bin/env python3
"""
Nuitka打包脚本，用于构建AGV监控系统可执行文件

跨平台（Windows / Linux）：
- Windows 用 MSVC 编译，产物 agvmon.exe；Linux 用默认 gcc/clang，产物 agvmon
- venv 布局、lupa 原生模块后缀（.pyd/.so）、7z 路径按平台自动适配
- 输出目录按平台分开，Windows/WSL 两边构建互不覆盖：
  Windows 在项目内 dist/windows；Linux 默认在 WSL 本地盘 ~/agvmon-build
  （/mnt/d 的 9P 文件系统会让 Nuitka 的海量小文件 I/O 慢一个量级；
  源码不复制，只有构建中间文件与产物落在本地盘）
- Linux 构建前置：build-essential（gcc、libc 头文件）、p7zip-full
"""

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

# 加载 .env 中的 WebDAV 配置
_dotenv_path = Path(__file__).parent / ".env"
if _dotenv_path.exists():
    load_dotenv(_dotenv_path)

# ---- 平台差异集中在这里 ----
IS_WINDOWS = os.name == "nt"
EXE_SUFFIX = ".exe" if IS_WINDOWS else ""          # 可执行文件后缀
PY_EXT_SUFFIX = ".pyd" if IS_WINDOWS else ".so"    # Python 扩展模块后缀
PLATFORM_TAG = "win64" if IS_WINDOWS else "linux64"  # 产物命名用平台标签


def get_output_dir(project_dir: Path) -> Path:
    """构建输出目录（main.build 中间文件与 main.dist 产物的落盘位置）。

    Windows 放项目内 dist/windows；Linux 不放 /mnt/d——9P 文件系统上
    Nuitka 的海量小文件读写慢一个量级，默认放 WSL 本地盘 ~/agvmon-build。
    源码不复制，只从原位置读取；重 I/O 全部落在本地盘。
    """
    if IS_WINDOWS:
        return project_dir / "dist" / "windows"
    return Path.home() / "agvmon-build" / "dist" / "linux"


def get_site_packages(venv_dir: Path):
    """定位 venv 的 site-packages。

    Windows 布局是 <venv>/Lib/site-packages，Linux 是
    <venv>/lib/pythonX.Y/site-packages，与运行本脚本的解释器无关。
    venv 目录里找不到时（如用了 UV_PROJECT_ENVIRONMENT=.venv-linux 之类的
    自定义环境名），退回用当前解释器的 site-packages——脚本经 uv run 在
    目标环境里执行时，这正是正确答案。
    """
    candidates = [
        venv_dir / "Lib" / "site-packages",
        *sorted(venv_dir.glob("lib/python*/site-packages")),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    import sysconfig

    p = Path(sysconfig.get_paths()["purelib"])
    if p.is_dir():
        return p
    return None


def get_version(project_dir):
    """自动生成版本号: pyproject.toml基版本 + git提交数"""
    base = "0.1.0"
    pp = project_dir / "pyproject.toml"
    if pp.exists():
        try:
            text = pp.read_text(encoding="utf-8")
            m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
            if m:
                base = m.group(1)
        except Exception:
            pass
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=project_dir, timeout=10,
        )
        if result.returncode == 0:
            count = result.stdout.strip()
            return f"{base}.{count}"
    except Exception:
        pass
    return base


def get_git_hash(project_dir):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=project_dir, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def get_git_short_hash(project_dir):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=project_dir, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def export_git_history(project_dir):
    """导出git提交历史到JSON"""
    try:
        result = subprocess.run(
            [
                "git", "log",
                "--date=format:%Y-%m-%d %H:%M:%S",
                "--format=---COMMIT_START---%n%H%n%h%n%ad%n%B",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=project_dir, timeout=30,
        )
        if result.returncode != 0:
            return []

        blocks = result.stdout.strip().split("---COMMIT_START---\n")
        commits = []
        for block in blocks:
            if not block.strip():
                continue
            lines = block.strip().split("\n", 3)
            if len(lines) >= 4:
                commits.append({
                    "hash": lines[0],
                    "short_hash": lines[1],
                    "time": lines[2],
                    "message": lines[3].strip(),
                })
        return commits
    except Exception:
        return []


def upload_to_webdav(local_path: Path, remote_name: str = None) -> bool:
    """上传文件到 WebDAV 服务器，配置从 .env 读取。"""
    url = os.environ.get("WEBDAV_URL", "")
    username = os.environ.get("WEBDAV_USERNAME", "")
    password = os.environ.get("WEBDAV_PASSWORD", "")
    remote_dir = os.environ.get("WEBDAV_REMOTE_DIR", "/")

    if not url:
        print("  跳过上传: WEBDAV_URL 未配置")
        return False

    remote_name = remote_name or local_path.name
    remote_path = f"{remote_dir.rstrip('/')}/{quote(remote_name, safe='')}"
    full_url = url.rstrip("/") + "/" + remote_path.lstrip("/")

    file_size = local_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(str(local_path))
    if mime_type is None:
        mime_type = "application/zip"

    print(f"  上传到 WebDAV: {full_url} ({file_size / 1024 / 1024:.2f} MB)")

    auth = httpx.BasicAuth(username, password) if username else None

    try:
        with open(local_path, "rb") as f:
            resp = httpx.put(
                full_url,
                content=f.read(),
                headers={"Content-Type": mime_type},
                auth=auth,
                timeout=300,
                follow_redirects=True,
            )
        if resp.status_code in (200, 201, 204):
            print(f"    ✓ 上传成功 [{resp.status_code}]")
            return True
        elif resp.status_code == 401:
            print("    ✗ 认证失败 (401)")
        elif resp.status_code == 507:
            print("    ✗ 存储空间不足 (507)")
        else:
            print(f"    ✗ 上传失败 [{resp.status_code}]: {resp.text[:200]}")
    except httpx.RequestError as e:
        print(f"    ✗ 网络错误: {e}")
    return False


def upload_to_update_server(
    zip_path: Path,
    version: str,
    build_time: str,
    git_hash: str,
    channel: str = "stable",
) -> bool:
    """上传 ZIP 到 AGVmon 更新服务器，按平台更新对应清单。"""
    update_url = os.environ.get("UPDATE_URL", "")
    api_key = os.environ.get("UPDATE_API_KEY", "")

    if not update_url:
        print("  跳过更新服务器上传: UPDATE_URL 未配置")
        return False

    print(f"\n上传到更新服务器: {update_url}")
    print(f"  文件: {zip_path.name}  ({zip_path.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"  版本: {version}  通道: {channel}  平台: {PLATFORM_TAG}")

    try:
        with open(zip_path, "rb") as f:
            resp = httpx.post(
                f"{update_url.rstrip('/')}/agvmon/api/update/upload",
                files={"file": (zip_path.name, f, "application/zip")},
                data={
                    "version": version,
                    "build_time": build_time,
                    "git_hash": git_hash,
                    "channel": channel,
                    "platform": PLATFORM_TAG,
                },
                headers={"X-API-Key": api_key},
                timeout=6000,
                follow_redirects=True,
            )
        if resp.status_code == 200:
            data = resp.json()
            print(f"    ✓ 上传成功 [{resp.status_code}]")
            print(f"    清单已更新: {', '.join(data.get('manifest_files', [])) or data.get('manifest_file', '?')}")
            return True
        elif resp.status_code == 401:
            print("    ✗ 认证失败 (401) — 检查 UPDATE_API_KEY")
        else:
            print(f"    ✗ 上传失败 [{resp.status_code}]: {resp.text[:200]}")
    except httpx.RequestError as e:
        print(f"    ✗ 网络错误: {e}")
    return False


def build_with_nuitka(
    skip_compress=False,
    skip_upload=False,
    skip_verify=False,
    channel="stable",
):
    """
    使用Nuitka构建可执行文件
    """
    project_dir = Path(__file__).parent
    main_py = project_dir / "main.py"
    venv_dir = project_dir / ".venv"

    if not main_py.exists():
        print(f"错误：找不到主文件 {main_py}")
        sys.exit(1)

    # 获取git信息
    version = get_version(project_dir)
    git_hash = get_git_hash(project_dir)
    git_short = get_git_short_hash(project_dir)
    build_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"Version: {version}")
    print(f"Git Hash: {git_short}")
    print(f"Build Time: {build_time}")

    # 更新 __version__.py
    version_file = project_dir / "util" / "core" / "__version__.py"
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(f'version = "{version}"\n')
        f.write(f'build_time = "{build_time}"\n')
        f.write(f'git_hash = "{git_short}"\n')
    print(f"已更新 {version_file}")

    # 导出git提交历史
    git_history = export_git_history(project_dir)
    history_path = project_dir / "util" / "data" / "git_history.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(git_history, f, ensure_ascii=False, indent=2)
    print(f"已导出 git 历史 ({len(git_history)} 条) 到 {history_path}")

    site_packages = get_site_packages(venv_dir)
    if site_packages is None:
        print(
            "错误：在 .venv 里找不到 site-packages"
            "（Windows: Lib/site-packages，Linux: lib/pythonX.Y/site-packages）"
        )
        sys.exit(1)

    # pylibdmtx 的原生库：Windows wheel 自带 libdmtx-64.dll，Linux wheel 通常不带
    libdmtx_files = sorted(site_packages.glob("pylibdmtx/libdmtx*"))
    lupa_dir = site_packages / "lupa"

    # 用户 Lua 脚本沙箱：lupa 的 Lua VM 是静态链进 .pyd 的（如 lua55.cp313-win_amd64.pyd），
    # 且 lupa/__init__ 用 os.listdir + __import__ 动态挑版本，静态分析理论上跟不到。
    # 实测 Nuitka 2.8.9 下 --include-package=lupa 就能把 7 个变体（lua51..lua55、
    # luajit20/21）全部收进 dist/lupa/ 并重命名为 lua55.pyd（lupa 的正则仍匹配）；
    # 显式 include-module 与 copy_lupa_native_files 是防 Nuitka 行为变化的兜底。
    lupa_args = ["--include-package=lupa", "--include-package-data=lupa"]
    lupa_variants = lupa_variant_modules(lupa_dir)
    if lupa_variants:
        lupa_args += [f"--include-module=lupa.{name}" for name in lupa_variants]
    print(f"lupa 变体模块: {', '.join(lupa_variants) if lupa_variants else '未找到（用户脚本功能可能不可用）'}")

    exe_name = f"agvmon{EXE_SUFFIX}"
    output_dir = get_output_dir(project_dir)

    nuitka_cmd = [sys.executable, "-m", "nuitka"]
    # --msvc 是 Windows 专用选项；Linux 用发行版默认编译器（gcc/clang）
    if IS_WINDOWS:
        nuitka_cmd.append("--msvc=latest")
    nuitka_cmd += [
        "--standalone",
        "--plugin-enable=pyzmq",
        *lupa_args,
        "--include-data-dir=web/dist=./web/dist",
        "--include-data-dir=static=./static",
        "--include-data-dir=util/data/cache=./util/data/cache",
        "--include-data-dir=util/data/fake=./util/data/fake",
        "--include-data-dir=util/data/map_img=./util/data/map_img",
        "--include-data-dir=util/data/robot_img=./util/data/robot_img",
        "--include-data-files=util/config.toml=./util/config.toml",
        "--include-data-files=util/data/Alarminfo.json=./util/data/Alarminfo.json",
        "--include-data-files=util/data/AmrStatusInfo.json=./util/data/AmrStatusInfo.json",
        "--include-data-files=util/data/git_history.json=./util/data/git_history.json",
        f"--output-dir={output_dir}",
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=ttk",
        "--experimental=debug-report-traceback",
        f"--output-filename={exe_name}",
        str(main_py),
    ]

    print("\n开始构建AGV监控系统可执行文件...")
    print(f"构建命令: {' '.join(nuitka_cmd)}")

    try:
        # 用参数列表直接跑，避免 os.system 拼串在带空格路径下的引号问题
        result = subprocess.run(nuitka_cmd)
        if result.returncode != 0:
            print(f"构建命令执行失败，退出代码: {result.returncode}")
            sys.exit(result.returncode)

        dist_dir = output_dir / "main.dist"

        # pylibdmtx 原生库：wheel 自带就复制（Windows: libdmtx-64.dll），
        # Linux wheel 通常不带，目标机需要系统包 libdmtx0b
        if dist_dir.exists():
            pylibdmtx_dir = dist_dir / "pylibdmtx"
            pylibdmtx_dir.mkdir(parents=True, exist_ok=True)
            for src in libdmtx_files:
                target = pylibdmtx_dir / src.name
                shutil.copy2(src, target)
                print(f"已复制 {src.name} 到 {target}")
            if not libdmtx_files:
                if IS_WINDOWS:
                    print("警告：venv 里没找到 pylibdmtx 的 libdmtx DLL，条码识别可能不可用")
                else:
                    print("提示：pylibdmtx 未自带 libdmtx，目标机需安装系统包：sudo apt install libdmtx0b")

        # 复制 util/tool 目录到输出；parsezlib_2_7_8.exe 是 Windows 专用二进制，
        # Linux 包不携带（Linux 侧 AGV 日志解析固定走纯 Python 实现，见 agvlog.py）
        tool_src = project_dir / "util" / "tool"
        tool_dst = dist_dir / "util" / "tool"
        if tool_src.exists() and dist_dir.exists():
            if tool_dst.exists():
                shutil.rmtree(tool_dst)
            if PLATFORM_TAG == "win64":
                shutil.copytree(tool_src, tool_dst)
            else:
                shutil.copytree(
                    tool_src, tool_dst,
                    ignore=shutil.ignore_patterns("parsezlib_2_7_8.exe"),
                )
                print("Linux 包不携带 parsezlib_2_7_8.exe（Windows 专用）")
            print(f"已复制 tool 目录到 {tool_dst}")

        if dist_dir.exists():
            print(f"\n输出目录: {dist_dir.absolute()}")
            for item in dist_dir.iterdir():
                print(f"- {item}")

        # lupa 原生模块兜底复制 + 产物内 Lua 沙箱冒烟验证
        copy_lupa_native_files(dist_dir, lupa_dir)
        if not skip_verify:
            if not verify_packaged_lua(dist_dir):
                print(
                    "\n构建中止：打包产物里的用户脚本（Lua）沙箱不可用，"
                    "不压缩、不上传。\n"
                    "  排查方向：lupa 是否已安装、产物 lupa/ 目录下是否有 lua55*.pyd/.so、"
                    "构建日志里 lupa 相关告警。\n"
                    "  确需跳过请加 --skip-verify。"
                )
                sys.exit(1)
        else:
            print("\n已跳过打包产物验证 (--skip-verify)")

        # 压缩
        zip_path = None
        if not skip_compress:
            zip_path = compress_dist(dist_dir, version, git_short)

        # 上传
        if zip_path and not skip_upload:
            # upload_to_webdav(zip_path)
            upload_to_update_server(zip_path, version, build_time, git_short, channel)

    except Exception as e:
        print(f"发生未知错误: {e}")
        sys.exit(1)


def lupa_variant_modules(lupa_dir: Path) -> list[str]:
    """枚举已安装 lupa 自带的 Lua 变体模块名（lua55 / lua54 / luajit21 ...）。

    lupa 一个 wheel 里同时带多个变体，每个都是扩展模块（Windows 形如
    ``lua55.cp313-win_amd64.pyd``，Linux 形如 ``lua55.cpython-313-x86_64-linux-gnu.so``），
    运行期由 ``lupa/__init__._import_newest_lib`` 动态挑最新的。
    这里按实际文件枚举，避免硬编码 lua55 在换 lupa/Python 版本后失效。
    """
    if not lupa_dir.exists():
        return []
    names, seen = [], set()
    for pattern in ("lua*.pyd", "lua*.so"):
        for path in sorted(lupa_dir.glob(pattern)):
            match = re.match(r"(lua[a-z]*\d*)[.\-]", path.name)
            if match and match.group(1) not in seen:
                seen.add(match.group(1))
                names.append(match.group(1))
    return names


def copy_lupa_native_files(dist_dir: Path, lupa_dir: Path) -> None:
    """兜底：把 lupa 的原生 Lua VM（各 .pyd/.so）按原名复制到 dist/lupa。

    lupa 的 ``__init__._import_newest_lib`` 用 ``os.listdir(package_dir)`` 找
    lupa 的扩展模块再 ``__import__``，属于运行期动态发现，Nuitka 的静态分析
    跟不全；显式 ``--include-module`` 之外再复制一份保证运行期一定能找到。

    实测 Windows 下 Nuitka 会把它收集到的扩展模块重命名为 ``lua55.pyd``（去掉
    ``.cp313-win_amd64`` 后缀），lupa 的正则依然能匹配；因此这里**只补 Nuitka 没
    收集到的变体**（按平台后缀或原全名判断），避免同目录出现同一变体的两份副本。
    """
    if not (lupa_dir.exists() and dist_dir.exists()):
        return
    target = dist_dir / "lupa"
    target.mkdir(parents=True, exist_ok=True)

    copied, skipped = [], []
    for pattern in ("*.pyd", "*.so"):
        for src in sorted(lupa_dir.glob(pattern)):
            match = re.match(r"(lua[a-z]*\d*)[.\-]", src.name)
            variant = match.group(1) if match else src.stem
            # Nuitka 收集后可能是去 ABI 后缀的短名（lua55.pyd / lua55.so），
            # 也可能保留原全名，两种都算已收集
            if (target / f"{variant}{PY_EXT_SUFFIX}").exists() or (target / src.name).exists():
                skipped.append(variant)
                continue
            shutil.copy2(src, target / src.name)
            copied.append(src.name)

    if copied:
        print(f"已补充复制 lupa 原生模块到 {target}: {', '.join(copied)}")
    if skipped:
        print(f"lupa 原生模块已由 Nuitka 收集，无需复制: {', '.join(sorted(set(skipped)))}")
    if not copied and not skipped:
        print(f"警告：{lupa_dir} 下没找到 lupa 的 .pyd/.so，用户脚本沙箱可能不可用")


def verify_packaged_lua(dist_dir: Path) -> bool:
    """直接调用打包产物里的 worker 子命令，验证 Lua 沙箱真的能跑。

    ``agvmon.exe run lua-worker`` 不启动服务器，只读 stdin 执行一次沙箱自检，
    因此可以安全地作为构建后的冒烟测试。
    """
    exe = dist_dir / f"agvmon{EXE_SUFFIX}"
    if not exe.exists():
        print(f"  跳过验证：找不到 {exe}")
        return False

    job = json.dumps(
        {
            "mode": "run",
            "script_id": "__build_verify__",
            "code": "print('verify') return {ok = true, lua = _VERSION, "
                    "escape = type(os.execute), json = json.encode({a = 1})}",
            "payload_json": '{"hello":"打包验证"}',
            "limits": {},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    print(f"\n验证打包产物中的 Lua 沙箱: {exe} run lua-worker")
    try:
        proc = subprocess.run(
            [str(exe), "run", "lua-worker"],
            input=job,
            capture_output=True,
            timeout=180,
            cwd=str(dist_dir),
        )
    except Exception as exc:
        print(f"  ✗ 无法运行打包产物: {type(exc).__name__}: {exc}")
        return False

    stdout = proc.stdout.decode("utf-8", errors="replace")
    lowered = stdout.lower()
    if (
        "not a valid win32 application" in lowered
        or "cannot execute binary file" in lowered
        or "no module named" in lowered
    ):
        print("  ✗ 产物报错，lupa 原生模块可能缺失")

    marker = "__AGVMON_LUA_RESULT__"
    for line in reversed(stdout.splitlines()):
        if line.strip().startswith(marker):
            try:
                result = json.loads(line.strip()[len(marker):].strip())
            except json.JSONDecodeError:
                break
            if result.get("ok"):
                print(f"  ✓ Lua 沙箱可用: {result.get('result')}")
                return True
            print(f"  ✗ 沙箱返回失败: {result.get('error')}")
            return False

    stderr = proc.stderr.decode("utf-8", errors="replace")[-1500:]
    print(f"  ✗ 未拿到沙箱结果（退出码 {proc.returncode}）")
    if stdout.strip():
        print(f"    stdout: {stdout.strip()[-800:]}")
    if stderr.strip():
        print(f"    stderr: {stderr.strip()}")
    return False


def find_7z():
    """查找 7z 可执行文件路径（Linux 上 p7zip-full / 7zip 提供 7z、7za 或 7zz）。"""
    seven_zip = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if seven_zip:
        return seven_zip
    if IS_WINDOWS:
        for p in [
            "C:\\Program Files\\7-Zip\\7z.exe",
            "C:\\Program Files (x86)\\7-Zip\\7z.exe",
            os.path.expanduser("~\\scoop\\apps\\7zip\\current\\7z.exe"),
        ]:
            if os.path.exists(p):
                return p
    return None


def compress_dist(dist_dir: Path, version: str, git_hash: str) -> Path | None:
    """7z 压缩 main.dist 目录，返回 zip 文件路径。zip 与产物同盘（dist_dir 上一级）。"""
    seven_zip = find_7z()
    if not seven_zip:
        print(
            "错误：未找到7z命令，请安装 7-Zip（Windows）或 p7zip-full"
            "（Linux: sudo apt install p7zip-full）并加入 PATH。"
        )
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 产物名带平台标签，Windows/Linux 包不会互相覆盖、更新服务器也能区分
    zip_name = f"agvmon_v{version}_{git_hash}_{timestamp}_{PLATFORM_TAG}.zip"
    zip_path = dist_dir.parent / zip_name

    print(f"\n正在压缩 {dist_dir} 到 {zip_path} ...")
    result = subprocess.run(
        # dist 目录内容打包到 zip 根（目录本身不作为一层），os.sep 保证跨平台
        [seven_zip, "a", "-tzip", "-mx=9", str(zip_path), str(dist_dir) + os.sep + "*"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"压缩完成：{zip_path} ({size_mb:.2f} MB)")
        return zip_path
    else:
        print(f"压缩失败：{result.stderr.strip() or result.stdout.strip()}")
        return None


def publish_zip(
    zip_path: Path,
    version: str = None,
    build_time: str = None,
    git_hash: str = None,
    channel: str = "stable",
):
    """上传已有的 ZIP 包，不重新构建。版本信息从文件名解析。"""
    if not zip_path.exists():
        print(f"错误：找不到文件 {zip_path}")
        sys.exit(1)

    # 从文件名解析: agvmon_v0.1.0.89_2265893_20260710_120000_win64.zip
    # （平台标签可选，兼容无标签的旧包）
    parsed = re.match(
        r"agvmon_v([\d.]+)_(\w+)_(\d{8}_\d{6})(?:_([a-z0-9]+))?\.zip", zip_path.name
    )
    if not parsed:
        print(f"错误：无法从文件名解析版本信息: {zip_path.name}")
        print("  期望格式: agvmon_v<version>_<hash>_<timestamp>[_win64|_linux64].zip")
        sys.exit(1)

    version = version or parsed.group(1)
    git_hash = git_hash or parsed.group(2)
    build_time = build_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"发布已有 ZIP: {zip_path.name}")
    print(f"  Version: {version}  Git: {git_hash}")
    print(f"  Channel: {channel}")

    # upload_to_webdav(zip_path)
    upload_to_update_server(zip_path, version, build_time, git_hash, channel)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nuitka 打包 + 上传")
    parser.add_argument("--skip-compress", action="store_true", help="跳过压缩")
    parser.add_argument("--skip-upload", action="store_true", help="跳过上传")
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="跳过打包产物中 Lua 沙箱的冒烟验证",
    )
    parser.add_argument(
        "--channel",
        choices=["stable", "beta"],
        default="stable",
        help="更新通道 (默认: stable)",
    )
    parser.add_argument(
        "--zip",
        type=Path,
        help="直接上传已有的 ZIP，跳过构建",
    )
    parser.add_argument("--version", help="版本号 (配合 --zip)")
    parser.add_argument("--build-time", help="构建时间 (配合 --zip)")
    parser.add_argument("--git-hash", help="Git 哈希 (配合 --zip)")
    args = parser.parse_args()

    if args.zip:
        publish_zip(
            zip_path=args.zip,
            version=args.version,
            build_time=args.build_time,
            git_hash=args.git_hash,
            channel=args.channel,
        )
    else:
        build_with_nuitka(
            skip_compress=args.skip_compress,
            skip_upload=args.skip_upload,
            skip_verify=args.skip_verify,
            channel=args.channel,
        )
