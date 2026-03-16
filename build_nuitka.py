#!/usr/bin/env python3
"""
Nuitka打包脚本，用于构建AGV监控系统可执行文件
"""

import os
import shutil
import sys
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

        if dist_dir.exists():
            print(f"\n输出目录: {dist_dir.absolute()}")
            for item in dist_dir.iterdir():
                print(f"- {item}")

    except Exception as e:
        print(f"发生未知错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build_with_nuitka()
