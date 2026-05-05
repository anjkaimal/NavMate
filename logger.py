import logging
from logging.handlers import RotatingFileHandler
from config import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT

_fmt_file = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
_fmt_stderr = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fh = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_fmt_file)

    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(_fmt_stderr)

    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger
