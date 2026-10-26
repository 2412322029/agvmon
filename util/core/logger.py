import logging
import os
import pathlib
import sys

from loguru import logger

from util.core.config import cfg
from util.core.paths import APP_LOG_DIR

__all__ = ["logger"]

log_path = pathlib.Path(APP_LOG_DIR)
log_path.mkdir(exist_ok=True)

# logging 包的目录路径，用于判断帧是否在 logging 内部
_logging_dir = os.path.dirname(logging.__file__)


class InterceptHandler(logging.Handler):
    """将标准库 logging 重定向到 Loguru，正确显示原始调用方"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 向上遍历调用栈，跳过 emit 自身 + logging 包全部内部帧 + loguru 帧
        frame = logging.currentframe()
        depth = 0
        while frame:
            fname = frame.f_code.co_filename
            if (fname == __file__  # emit 自身
                    or fname.startswith(_logging_dir)  # logging 包内部
                    or 'loguru' in fname):  # loguru 内部
                frame = frame.f_back
                depth += 1
            else:
                break

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _setup_logger(file_name: str = "main.log") -> None:
    logger.remove()

    # 控制台 — Loguru 默认格式（自带彩色）
    logger.add(
        sys.stdout,
        level=cfg.get("log_level"),
        colorize=True,
    )

    # 文件 — 每天轮转，保留 5 天
    # 文件可能被其他进程占用或被安全软件拦截（Windows 表现为 Errno 13），
    # 此时降级为仅控制台输出，不能让 env show 这类 CLI 子命令启动失败。
    try:
        logger.add(
            log_path / file_name,
            level=cfg.get("log_level"),
            rotation="1 day",
            retention=5,
            encoding="utf-8",
        )
    except OSError as e:
        # 文件 sink 建失败时走已就绪的控制台 sink，黄色醒目提示，不影响 CLI 启动
        logger.opt(colors=True).warning(
            "⚠ 警告：日志文件无法写入，本次仅输出到控制台\n"
            f"<yellow>    文件: {log_path / file_name}</yellow>\n"
            f"<yellow>    原因: {e}</yellow>\n"
            f"<yellow>    排查: 是否有其他 agvmon/python 进程（含 WSL 内）占用该文件，"
            f"或安全软件是否拦截该目录</yellow>"
        )

    # 将标准 logging 全部重定向到 Loguru
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(0)

    # 抑制 uvicorn 自带的 logger handler，避免重复输出
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


_setup_logger("main.log")
