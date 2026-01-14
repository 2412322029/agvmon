import logging
import os
import pathlib
import sys
from logging.handlers import TimedRotatingFileHandler

from .config import cfg

log_path = pathlib.Path(os.path.join(os.path.dirname(__file__), "../log"))
if not log_path.exists():
    log_path.mkdir()

# 定义颜色代码
class ColorCodes:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # 背景颜色
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"

# 创建彩色日志格式类
class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.level_colors = {
            logging.DEBUG: ColorCodes.CYAN,
            logging.INFO: ColorCodes.GREEN,
            logging.WARNING: ColorCodes.YELLOW,
            logging.ERROR: ColorCodes.RED,
            logging.CRITICAL: ColorCodes.BG_RED + ColorCodes.WHITE
        }
    
    def format(self, record):
        # 调用父类的format方法获取格式化后的输出
        formatted_output = super().format(record)
        
        # 只对日志级别名称应用颜色
        levelname = record.levelname
        if record.levelno in self.level_colors:
            # 查找并替换级别名称
            colored_levelname = f"{self.level_colors[record.levelno]}{levelname}{ColorCodes.RESET}"
            formatted_output = formatted_output.replace(levelname, colored_levelname)
        
        return formatted_output

# 创建普通日志格式（用于文件日志）
file_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(funcName)s(line %(lineno)d) - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 创建彩色日志格式（用于控制台日志）
console_formatter = ColoredFormatter(
    "%(asctime)s - %(name)s - %(funcName)s(line %(lineno)d) - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def init_logger(file_name="main.log"):
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    # 创建带时间轮换的文件处理器
    file_handler = TimedRotatingFileHandler(
        filename=log_path / file_name,
        when="D",
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.getLevelName(cfg.get("log_level")))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return root_logger

logger = init_logger("main.log")
