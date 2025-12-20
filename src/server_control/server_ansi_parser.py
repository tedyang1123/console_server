import re

from src.common.rc_code import RcCode


class ConsoleAnsiEscapeParser:
    def __init__(self):
        self._csi_sequence_str = r'\[([0-9]*)(;?)([0-9]*)([@A-Z\[\\\]\^_`a-z\{\|\}~])'

    def data_parse(self, data_str):
        rc = RcCode.FAILURE
        remaining_str = data_str
        if data_str == '[':
            rc = RcCode.DATA_NOT_READY
        else:
            group = re.match(self._csi_sequence_str, data_str, re.M | re.I)
            if group is not None:
                if group[4] == "":
                    rc = RcCode.DATA_NOT_READY
                else:
                    remaining_str = data_str.replace(group[0], "")
                    if group[4] == "A":
                        rc = RcCode.SUCCESS
                    elif group[4] == "B":
                        rc = RcCode.SUCCESS
                    elif group[4] == "C":
                        rc = RcCode.SUCCESS
                    elif group[4] == "D":
                        rc = RcCode.SUCCESS
                    else:
                        rc = RcCode.DATA_NOT_FOUND
        return rc, remaining_str