#!/usr/bin/env python3
"""
Nuitka打包脚本，用于构建AGV监控系统可执行文件
"""

import subprocess
import sys
from pathlib import Path


def build_with_nuitka():
    """
    使用Nuitka构建可执行文件
    """
    # 获取项目根目录
    project_dir = Path(__file__).parent
    main_py = project_dir / "main.py"

    # 检查主文件是否存在
    if not main_py.exists():
        print(f"错误：找不到主文件 {main_py}")
        sys.exit(1)

    # 构建命令参数
    nuitka_cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--verbose",  # 显示详细输出
        "--standalone",  # 创建独立的应用程序
        "--plugin-enable=pyzmq",  # 启用pyzmq插件
        "--include-data-dir=web/dist=./web/dist",  # 包含web/dist目录
        "--include-data-dir=util/data=./util/data",  # 包含util/data目录
        """--include-data-files=util/config.toml=./util/config.toml""",  # 包含config.toml文件
        "--output-dir=dist",  # 输出目录
        "--follow-imports",
        # "--lto=yes",  # 跟踪所有导入并启用LTO优化
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
        result = subprocess.run(nuitka_cmd, check=True, capture_output=True, text=True)
        print("构建成功！")
        print(result.stdout)

        # 显示输出文件位置
        dist_dir = project_dir / "dist"
        if dist_dir.exists():
            print(f"\n输出目录: {dist_dir.absolute()}")
            for item in dist_dir.iterdir():
                print(f"- {item}")

    except subprocess.CalledProcessError as e:
        print(f"构建失败: {e}")
        print(f"错误输出: {e.stderr}")
        sys.exit(1)
    except Exception as e:
        print(f"发生未知错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build_with_nuitka()
