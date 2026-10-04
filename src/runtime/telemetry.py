"""不记录原始请求或异常正文的结构化诊断事件。"""

import json
import logging
import os
import traceback
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

task_context = ContextVar("task_context", default={})
logger = logging.getLogger("reactor")
logger.addHandler(logging.NullHandler())


def configure_logging(path):
    path = path.with_name(f"{path.stem}.{os.getpid()}{path.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        return
    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def emit(event, **fields):
    logger.info(json.dumps({"event": event, **task_context.get(), **fields}, ensure_ascii=False))


def failure(event, exc):
    # 保留定位所需的栈帧，不记录异常消息、局部变量或源码中的敏感字面量。
    frames = [
        {"file": f.filename, "line": f.lineno, "function": f.name}
        for f in traceback.extract_tb(exc.__traceback__)
    ]
    emit(event, error_type=type(exc).__name__, frames=frames)
