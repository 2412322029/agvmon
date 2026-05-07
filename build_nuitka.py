#!/usr/bin/env python3
"""
Nuitka打包脚本，用于构建AGV监控系统可执行文件
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def build_with_nuitka():
    """
    使用Nuitka构建可执行文件
    """
    # 获取项目根目录
    project_dir = Path(__file__).parent
    main_py = project_dir / "main.py"
    venv_dir = project_dir / ".venv"

    # 检查主文件是否存在
    if not main_py.exists():
        print(f"错误：找不到主文件 {main_py}")
        sys.exit(1)

    libdmtx_dll = venv_dir / "Lib" / "site-packages" / "pylibdmtx" / "libdmtx-64.dll"

    nuitka_cmd = [
        sys.executable,
        "-m",
        "nuitka",
        # "--verbose",  # 显示详细输出
        "--standalone",  # 创建独立的应用程序
        "--plugin-enable=pyzmq",  # 启用pyzmq插件
        "--include-data-dir=web/dist=./web/dist",  # 包含web/dist目录
        "--include-data-dir=static=./static",  # 包含static目录
        "--include-data-dir=util/data/cache=./util/data/cache",  # 包含cache目录
        "--include-data-dir=util/data/fake=./util/data/fake",  # 包含fake目录
        "--include-data-dir=util/data/map_img=./util/data/map_img",  # 包含map_img目录
        "--include-data-dir=util/data/robot_img=./util/data/robot_img",  # 包含robot_img目录
        "--include-data-files=util/config.toml=./util/config.toml",  # 包含config.toml文件
        "--include-data-files=util/data/Alarminfo.json=./util/data/Alarminfo.json",  # 包含Alarminfo.json
        "--include-data-files=util/data/AmrStatusInfo.json=./util/data/AmrStatusInfo.json",  # 包含AmrStatusInfo.json
        "--output-dir=dist",  # 输出目录
        # "--follow-imports",
        # "--show-memory",  # 显示内存使用
        # "--lto=yes",  # 启用LTO优化
        "--nofollow-import-to=tkinter",  # 不跟踪tkinter导入
        "--nofollow-import-to=ttk",  # 不跟踪ttk导入
        "--output-filename=agvmon.exe",  # 输出文件名
        # "--windows-console-mode=attach",  # Windows控制台模式
        str(main_py),  # 主文件路径,
    ]

    print("开始构建AGV监控系统可执行文件...")
    print(f"构建命令: {' '.join(nuitka_cmd)}")

    try:
        # 执行Nuitka构建命令
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

            # 尝试查找7z命令
            seven_zip = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
            if not seven_zip:
                # 常见安装路径
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
