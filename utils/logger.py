import logging
import sys

_LOG_CONFIGURED = False

def get_logger(name: str = None) -> logging.Logger:
    global _LOG_CONFIGURED
    if not _LOG_CONFIGURED:
        fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(fmt)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.handlers.clear()
        root.addHandler(handler)
        _LOG_CONFIGURED = True
    return logging.getLogger(name or __name__)
