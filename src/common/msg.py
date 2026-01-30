import json
from src.common.rc_code import RcCode
from src.console_server.processing.console_server_definition import ConsoleServerEvent


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
            "request": self.request, "serial_port_id": self.serial_port_id,
            "socket_fd": self.socket_fd, "data": self.data
        }


class RequestMsg(Msg):
    def __init__(self, request=None, serial_port_id=None, socket_fd=None, data=None):
        Msg.__init__(self, request, serial_port_id, socket_fd, data)

    def serialize(self):
        msg_str = json.dumps({
            "request": self.request, "serial_port_id":
            self.serial_port_id, "socket_fd": self.socket_fd, "data": self.data
        })
        return RcCode.SUCCESS, msg_str

    def deserialize(self, msg_str):
        msg_dict = json.loads(msg_str)
        self.request = msg_dict["request"]
        self.serial_port_id = msg_dict["serial_port_id"]
        self.socket_fd = msg_dict["socket_fd"]
        self.data = msg_dict["data"]
        return RcCode.SUCCESS

class ConnectSerialPortRequest(RequestMsg):
    def __init__(self, serial_port_id, username):
        RequestMsg.__init__(self, ConsoleServerEvent.CONNECT_SERIAL_PORT, serial_port_id, None, {"username": username})

class GetPortConfigRequest(RequestMsg):
    def __init__(self):
        RequestMsg.__init__(self, ConsoleServerEvent.GET_PORT_CONFIG)

class ConfigAliasNameRequest(RequestMsg):
    def __init__(self, serial_port_id, alias_name):
        RequestMsg.__init__(self, ConsoleServerEvent.CONFIG_ALIAS_NAME, serial_port_id, None, {"alias_name": alias_name})

class ConfigBaudRateRequest(RequestMsg):
    def __init__(self, serial_port_id, baud_rate):
        RequestMsg.__init__(self, ConsoleServerEvent.CONFIG_BAUD_RATE, serial_port_id, None, {"baud_rate": baud_rate})

class CreateGroupRequest(RequestMsg):
    def __init__(self, group_name, role):
        RequestMsg.__init__(self, ConsoleServerEvent.CREATE_GROUP, None, None, {"group_name": group_name, "role": role})

class DestroyGroupRequest(RequestMsg):
    def __init__(self, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.DESTROY_GROUP, None, None, {"group_name": group_name})

class GetGroupRequest(RequestMsg):
    def __init__(self):
        RequestMsg.__init__(self, ConsoleServerEvent.GET_GROUP)

class AddUserAccountRequest(RequestMsg):
    def __init__(self, username, role, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.ADD_USER_ACCOUNT, None, None, {"username": username, "role": role, "group_name": group_name})

class DelUserAccountRequest(RequestMsg):
    def __init__(self, username):
        RequestMsg.__init__(self, ConsoleServerEvent.DEL_USER_ACCOUNT, None, None, {"username": username})

class ModifyUserRole(RequestMsg):
    def __init__(self, username, role):
        RequestMsg.__init__(self, ConsoleServerEvent.MODIFY_USER_ROLE, None, None, {"username": username, "role": role})

class GetUserAccount(RequestMsg):
    def __init__(self, username):
        if username is not None:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_USER_ACCOUT, None, None, {"username": username})
        else:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_USER_ACCOUT, None, None)

class UserJoinGroupRequest(RequestMsg):
    def __init__(self, username, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.USER_JOIN_GROUP, None, None, {"username": username, "group_name": group_name})

class UserLeaveGroupRequest(RequestMsg):
    def __init__(self, username, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.USER_LEAVE_GROUP, None, None, {"username": username, "group_name": group_name})

class PortJoinGroupRequest(RequestMsg):
    def __init__(self, serial_port_id, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.PORT_JOIN_GROUP, serial_port_id, None, {"group_name": group_name})

class PortLeaveGroupRequest(RequestMsg):
    def __init__(self, serial_port_id, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.PORT_LEAVE_GROUP, serial_port_id, None, {"group_name": group_name})

class ReplyMsg(Msg):
    def __init__(self, request=None, serial_port_id=None, socket_fd=None, data=None, result=None):
        Msg.__init__(self, request, serial_port_id, socket_fd, data)
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
        rc, data_dict = super().get_msg()
        if rc != RcCode.SUCCESS:
            return rc, None
        data_dict["result"] = self.result
        return RcCode.SUCCESS, data_dict

    def serialize(self):
        sg_str = json.dumps({
            "request": self.request, "serial_port_id": self.serial_port_id,
            "socket_fd": self.socket_fd, "data": self.data, "result": self.result
        })
        return RcCode.SUCCESS, sg_str

    def deserialize(self, msg_str):
        msg_dict = json.loads(msg_str)
        self.request = msg_dict["request"]
        self.serial_port_id = msg_dict["serial_port_id"]
        self.socket_fd = msg_dict["socket_fd"]
        self.data = msg_dict["data"]
        self.result = msg_dict["result"]
        return RcCode.SUCCESS


def msg_serialize(msg_dict):
    msg_str = json.dumps(msg_dict)
    return RcCode.SUCCESS, msg_str

def msg_deserialize(msg_str):
    msg_dict = json.loads(msg_str)
    return RcCode.SUCCESS, msg_dict
