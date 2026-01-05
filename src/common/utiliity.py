import subprocess
import json

from collections import OrderedDict
from src.common.rc_code import RcCode


def run_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return RcCode.FAILURE, None
    return RcCode.SUCCESS, result


def load_data_from_json(driver_config_file):
    try:
        data = json.load(open(driver_config_file, encoding='UTF-8'), object_pairs_hook=OrderedDict)
    except json.JSONDecodeError:
        return RcCode.INVALID_VALUE, None
    except OSError:
        return RcCode.FILE_ACCESS_FAIL, None
    return RcCode.SUCCESS, data

TEST_MODE = False

