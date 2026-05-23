#!/usr/bin/env python3
"""
Nuitka打包脚本，用于构建AGV监控系统可执行文件
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


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


def build_with_nuitka():
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
    version_file = project_dir / "util" / "__version__.py"
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

    libdmtx_dll = venv_dir / "Lib" / "site-packages" / "pylibdmtx" / "libdmtx-64.dll"

    nuitka_cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--plugin-enable=pyzmq",
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
        "--output-dir=dist",
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=ttk --experimental=debug-report-traceback",
        "--output-filename=agvmon.exe",
        str(main_py),
    ]

    print("\n开始构建AGV监控系统可执行文件...")
    print(f"构建命令: {' '.join(nuitka_cmd)}")

    try:
        return_code = os.system(" ".join(nuitka_cmd))
        if return_code != 0:
            print(f"命令执行失败: {' '.join(nuitka_cmd)}\n退出代码: {return_code}")
            sys.exit(return_code)

        dist_dir = project_dir / "dist" / "main.dist"
        pylibdmtx_dir = dist_dir / "pylibdmtx"
        if not pylibdmtx_dir.exists():
            pylibdmtx_dir.mkdir(parents=True)
        if libdmtx_dll.exists() and dist_dir.exists():
            target_dll = pylibdmtx_dir / "libdmtx-64.dll"
            shutil.copy2(libdmtx_dll, target_dll)
            print(f"已复制 libdmtx-64.dll 到 {target_dll}")

        # 复制 util/tool 目录到输出
        tool_src = project_dir / "util" / "tool"
        tool_dst = dist_dir / "util" / "tool"
        if tool_src.exists() and dist_dir.exists():
            if tool_dst.exists():
                shutil.rmtree(tool_dst)
            shutil.copytree(tool_src, tool_dst)
            print(f"已复制 tool 目录到 {tool_dst}")

        if dist_dir.exists():
            print(f"\n输出目录: {dist_dir.absolute()}")
            for item in dist_dir.iterdir():
                print(f"- {item}")

        # 询问是否使用7z压缩
        compress = input("\n是否使用7z压缩 main.dist 目录？(y/N): ").strip().lower()
        if compress == "y":
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"agvmon_{timestamp}.zip"
            zip_path = project_dir / "dist" / zip_name

            seven_zip = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
            if not seven_zip:
                common_paths = [
                    "C:\\Program Files\\7-Zip\\7z.exe",
                    "C:\\Program Files (x86)\\7-Zip\\7z.exe",
                    os.path.expanduser("~\\scoop\\apps\\7zip\\current\\7z.exe"),
                ]
                for p in common_paths:
                    if os.path.exists(p):
                        seven_zip = p
                        break

            if not seven_zip:
                print("错误：未找到7z命令，请安装7-Zip并将其添加到PATH环境变量。")
            else:
                print(f"正在压缩 {dist_dir} 到 {zip_path} ...")
                result = subprocess.run(
                    [seven_zip, "a", "-tzip", "-mx=9", str(zip_path), str(dist_dir) + "\\*"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    size_mb = zip_path.stat().st_size / (1024 * 1024)
                    print(f"压缩完成：{zip_path} ({size_mb:.2f} MB)")
                else:
                    print(f"压缩失败：{result.stderr.strip() or result.stdout.strip()}")

    except Exception as e:
        print(f"发生未知错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build_with_nuitka()
