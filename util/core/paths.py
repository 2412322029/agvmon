"""集中管理依赖 __file__ 的资源路径。

本模块只依赖 os，不 import 任何项目模块——config.py 在导入时就会建 Redis
客户端，paths 必须比它更早可用且无副作用。

Nuitka standalone 下 __file__ 是按模块名还原的虚拟路径
（<dist>/util/core/paths.py），所以这里的层级在打包前后一致。

刻意不用 os.path.realpath/.resolve()：与原有 abspath 语义保持一致，避免
软链接/junction 解析改变打包后的取值。
"""

import os

_THIS = os.path.dirname(os.path.abspath(__file__))  # <root>/util/core
UTIL_DIR = os.path.dirname(_THIS)                   # <root>/util
PROJECT_ROOT = os.path.dirname(UTIL_DIR)            # <root>（开发时是仓库根，打包后是 dist 根）

DATA_DIR = os.path.join(UTIL_DIR, "data")
TOOL_DIR = os.path.join(UTIL_DIR, "tool")
APP_LOG_DIR = os.path.join(PROJECT_ROOT, "log")

# 注意：不要在这里提供 APP_ROOT。config.APP_ROOT 是"运行期数据根"（开发时为
# 当前工作目录、打包后为 exe 所在目录），与本模块的 PROJECT_ROOT（代码位置）
# 是两个不同的概念，合并会让换目录启动时 lua_script/ 与 config.toml 跑偏。
