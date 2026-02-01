import json
from src.common.rc_code import RcCode
from src.console_server.processing.console_server_definition import ConsoleServerEvent


class Msg:
    def __init__(self, request=None, serial_port_id=None, socket_fd=None, exec_user=None, data=None):
        self.request = request
        self.serial_port_id = serial_port_id
        self.socket_fd = socket_fd
        self.exec_user = exec_user
        self.data = data

    def set_msg(self, msg_dict):
        try:
            self.request = msg_dict["request"]
            self.serial_port_id = msg_dict["serial_port_id"]
            self.socket_fd = msg_dict["socket_fd"]
            self.exec_user = msg_dict["exec_user"]
            self.data = msg_dict["data"]
        except KeyError:
            return RcCode.INVALID_VALUE
        return RcCode.SUCCESS
    
    def get_msg(self):
        return RcCode.SUCCESS, {
            "request": self.request, "serial_port_id": self.serial_port_id,
            "socket_fd": self.socket_fd, "exec_user": self.exec_user, "data": self.data
        }


class RequestMsg(Msg):
    def __init__(self, request=None, serial_port_id=None, socket_fd=None, exec_user=None, data=None):
        Msg.__init__(self, request, serial_port_id, socket_fd, exec_user, data)

    def serialize(self):
        msg_str = json.dumps({
            "request": self.request, "serial_port_id": self.serial_port_id,
            "socket_fd": self.socket_fd, "exec_user": self.exec_user, "data": self.data
        })
        return RcCode.SUCCESS, msg_str

    def deserialize(self, msg_str):
        msg_dict = json.loads(msg_str)
        self.request = msg_dict["request"]
        self.serial_port_id = msg_dict["serial_port_id"]
        self.socket_fd = msg_dict["socket_fd"]
        self.exec_user = msg_dict["exec_user"]
        self.data = msg_dict["data"]
        return RcCode.SUCCESS

class ConnectSerialPortRequest(RequestMsg):
    def __init__(self, exec_user, serial_port_id):
        RequestMsg.__init__(self, ConsoleServerEvent.CONNECT_SERIAL_PORT, serial_port_id, None, exec_user)

class GetPortConfigRequest(RequestMsg):
    def __init__(self, exec_user, serial_port_id=None):
        RequestMsg.__init__(self, ConsoleServerEvent.GET_PORT_CONFIG, serial_port_id, None, exec_user)

class GetPortStatusRequest(RequestMsg):
    def __init__(self, exec_user, serial_port_id=None):
        RequestMsg.__init__(self, ConsoleServerEvent.GET_PORT_STATUS, serial_port_id, None, exec_user)

class SetAliasNameRequest(RequestMsg):
    def __init__(self, exec_user, serial_port_id, alias_name):
        RequestMsg.__init__(self, ConsoleServerEvent.SET_ALIAS_NAME, serial_port_id, None, exec_user, {"alias_name": alias_name})

class SetBaudRateRequest(RequestMsg):
    def __init__(self, exec_user, serial_port_id, baud_rate):
        RequestMsg.__init__(self, ConsoleServerEvent.SET_BAUD_RATE, serial_port_id, None, exec_user, {"baud_rate": baud_rate})

class CreateGroupRequest(RequestMsg):
    def __init__(self, exec_user, group_name, role):
        RequestMsg.__init__(self, ConsoleServerEvent.CREATE_GROUP, None, None, exec_user, {"group_name": group_name, "role": role})

class DestroyGroupRequest(RequestMsg):
    def __init__(self, exec_user, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.DESTROY_GROUP, None, None, exec_user, {"group_name": group_name})

class GetGroupConfigRequest(RequestMsg):
    def __init__(self, exec_user, group_name=None):
        if group_name is not None:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_GROUP_CONFIG, None, None, exec_user, {"group_name": group_name})
        else:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_GROUP_CONFIG, None, None, exec_user)

class GetGroupStatusRequest(RequestMsg):
    def __init__(self, exec_user, group_name=None):
        if group_name is not None:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_GROUP_STATUS, None, None, exec_user, {"group_name": group_name})
        else:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_GROUP_STATUS, None, None, exec_user)

class AddUserAccountRequest(RequestMsg):
    def __init__(self, exec_user, username, group_name, role=""):
        RequestMsg.__init__(self, ConsoleServerEvent.ADD_USER_ACCOUNT, None, None, exec_user, {"username": username, "role": role, "group_name": group_name})

class DelUserAccountRequest(RequestMsg):
    def __init__(self, exec_user, username):
        RequestMsg.__init__(self, ConsoleServerEvent.DEL_USER_ACCOUNT, None, None, exec_user, {"username": username, })

class ModifyUserRole(RequestMsg):
    def __init__(self, exec_user, username, role):
        if role is not None:
            RequestMsg.__init__(self, ConsoleServerEvent.MODIFY_USER_ROLE, None, None, exec_user, {"username": username, "role": role})
        else:
            RequestMsg.__init__(self, ConsoleServerEvent.MODIFY_USER_ROLE, None, None, exec_user, {"username": username, "role": ""})

class GetUserConfig(RequestMsg):
    def __init__(self, exec_user, username):
        if username is not None:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_USER_CONFIG, None, None, exec_user, {"username": username})
        else:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_USER_CONFIG, None, None, exec_user)

class GetUserStatus(RequestMsg):
    def __init__(self, exec_user, username):
        if username is not None:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_USER_STATUS, None, None, exec_user, {"username": username})
        else:
            RequestMsg.__init__(self, ConsoleServerEvent.GET_USER_STATUS, None, None, exec_user)

class UserJoinGroupRequest(RequestMsg):
    def __init__(self, exec_user, username, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.USER_JOIN_GROUP, None, None, exec_user, {"username": username, "group_name": group_name})

class UserLeaveGroupRequest(RequestMsg):
    def __init__(self, exec_user, username, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.USER_LEAVE_GROUP, None, None, exec_user, {"username": username, "group_name": group_name})

class PortJoinGroupRequest(RequestMsg):
    def __init__(self, exec_user, serial_port_id, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.PORT_JOIN_GROUP, serial_port_id, None, exec_user, {"group_name": group_name})

class PortLeaveGroupRequest(RequestMsg):
    def __init__(self, exec_user, serial_port_id, group_name):
        RequestMsg.__init__(self, ConsoleServerEvent.PORT_LEAVE_GROUP, serial_port_id, None, exec_user, {"group_name": group_name})

class ReplyMsg(Msg):
    def __init__(self, request=None, serial_port_id=None, socket_fd=None, exec_user=None, data=None, result=None):
        Msg.__init__(self, request, serial_port_id, socket_fd, exec_user, data)
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
            "socket_fd": self.socket_fd, "exec_user": self.exec_user, "data": self.data,
            "result": self.result
        })
        return RcCode.SUCCESS, sg_str

    def deserialize(self, msg_str):
        msg_dict = json.loads(msg_str)
        self.request = msg_dict["request"]
        self.serial_port_id = msg_dict["serial_port_id"]
        self.socket_fd = msg_dict["socket_fd"]
        self.data = msg_dict["data"]
        self.exec_user = msg_dict["exec_user"]
        self.result = msg_dict["result"]
        return RcCode.SUCCESS


def msg_serialize(msg_dict):
    msg_str = json.dumps(msg_dict)
    return RcCode.SUCCESS, msg_str

def msg_deserialize(msg_str):
    msg_dict = json.loads(msg_str)
    return RcCode.SUCCESS, msg_dict

def check_all_required_parameter(msg, key_list, required_exec_user=True, required_socket_fd=False, required_serial_port_id=False):
    for key in key_list:
        if key not in msg.data:
            return False
    if required_exec_user and msg.exec_user is None:
        return False
    if required_socket_fd and msg.socket_fd is None:
        return False
    if required_serial_port_id and msg.serial_port_id is None:
        return False
    return True