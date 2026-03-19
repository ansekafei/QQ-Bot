# core/logger.py
import logging
import os
from logging.handlers import RotatingFileHandler

os.makedirs("data", exist_ok=True)
LOG_FILE = "data/runtime.log"
DEBUG_LOG_FILE = "data/debug.log"

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',    # 蓝色
        'INFO': '\033[92m',     # 绿色
        'WARNING': '\033[93m',  # 黄色
        'ERROR': '\033[91m',    # 红色
        'CRITICAL': '\033[95m'  # 紫色
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        record.msg = f"{log_color}{record.msg}{self.RESET}"
        return super().format(record)

logger = logging.getLogger("AI_Bot")
logger.setLevel(logging.DEBUG)  # 根收集器设为 DEBUG

# 控制台输出 (只显示 INFO 以上)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(ColoredFormatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%m-%d %H:%M:%S'))

# 精简运行日志 (用于默认 WebUI 模式)
fh_runtime = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=2, encoding='utf-8')
fh_runtime.setLevel(logging.INFO)
fh_runtime.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%m-%d %H:%M:%S'))

# 完整抓包日志 (用于 WebUI Debug 模式)
fh_debug = RotatingFileHandler(DEBUG_LOG_FILE, maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
fh_debug.setLevel(logging.DEBUG)
fh_debug.setFormatter(logging.Formatter('%(asctime)s | [%(levelname)s] | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))

logger.handlers = []
logger.addHandler(ch)
logger.addHandler(fh_runtime)
logger.addHandler(fh_debug)
logger.propagate = False

def init_logger():
    # 兼容历史调用的空函数
    pass