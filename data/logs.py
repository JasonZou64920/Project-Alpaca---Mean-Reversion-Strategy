# one logging setup for the whole system - structured lines into logs/
import logging
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "logs")

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name):
    """Logger that writes to logs/system.log and the console.

    Data updates, signals, orders, fills and snapshots all go through here so
    the log file reads as one chronological record of what the system did.
    Credentials are never passed to any log call.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:   # already set up (streamlit reruns, repeated imports)
        return logger
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(os.path.join(LOG_DIR, "system.log"))
    fh.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(sh)
    return logger
