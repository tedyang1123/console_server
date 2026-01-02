import json
from src.common.rc_code import RcCode


class Msg:
    def __init__(self, request=None, serial_port_id=None, socket_fd=None, data=None):
        self.request = request
        self.serial_port_id = serial_port_id
        self.socket_fd = socket_fd
        self.data = data

    def set_msg(self, msg_dict):
        try:
            self.request = msg_dict["request"]
            self.serial_port_id = msg_dict["serial_port_id"]
            self.socket_fd = msg_dict["socket_fd"]
            self.data = msg_dict["data"]
        except KeyError:
            return RcCode.INVALID_VALUE
        return RcCode.SUCCESS
    
    def get_msg(self):
        return RcCode.SUCCESS, {
            "request": self.request, "serial_port_id": 
            self.serial_port_id, "socket_fd": self.socket_fd, "data": self.data
        }


class RequestMsg(Msg):
    def __init__(self, request=None, serial_port_id=None, socket_fd=None,  data=None):
        Msg.__init__(self, request, serial_port_id, socket_fd, data)

class ReplyMsg(Msg):
    def __init__(self, request=None, serial_port_id=None, socket_fd=None, data=None, result=None):
        Msg.__init__(self, request, serial_port_id, socket_fd,  data)
        self.result = result

    def set_msg(self, msg_dict):
        rc = super().set_msg(msg_dict)
        if rc != RcCode.SUCCESS:
            return rc
        try:
            self.result = msg_dict["result"]
        except KeyError:
            return RcCode.INVALID_VALUE
        return RcCode.SUCCESS
    
    def get_msg(self):
        rc, data_dict = super().get_msg
        if rc != RcCode.SUCCESS:
            return rc, None
        data_dict["result"] = self.resuit
        return RcCode.SUCCESS, data_dict


def msg_serialize(msg_dict):
    msg_str = json.dumps(msg_dict)
    return RcCode.SUCCESS, msg_str

def msg_deserialize(msg_str):
    msg_dict = json.load(msg_str)
    return RcCode.SUCCESS, msg_dict