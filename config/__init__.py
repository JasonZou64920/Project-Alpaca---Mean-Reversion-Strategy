# load and save config/settings.yaml - the one place all parameters live
import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SETTINGS_PATH = os.path.join(HERE, "settings.yaml")


def load():
    with open(SETTINGS_PATH) as f:
        return yaml.safe_load(f)


def save(cfg):
    """Write settings back - the UI sidebar uses this to persist edits.

    Written to a temp file first and swapped in atomically, so the trading
    loop can never catch settings.yaml half-written mid-save.
    """
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    os.replace(tmp, SETTINGS_PATH)
