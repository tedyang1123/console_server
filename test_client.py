#!/usr/bin/env python3

import socket
import sys
import traceback

from src.common.logger_system import LoggerSystem
from src.common.msg import AddUserAccountRequest, ConfigAliasNameRequest, ConfigBaudRateRequest, ConnectSerialPortRequest, CreateGroupRequest, DelUserAccountRequest, DestroyGroupRequest, GetGroupRequest, GetPortConfigRequest, GetUserAccount, ModifyUserRole, PortJoinGroupRequest, PortLeaveGroupRequest, ReplyMsg, UserJoinGroupRequest, UserLeaveGroupRequest
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainClientSocket
from src.console_server.processing.console_server_definition import ConsoleServerEvent


class RpcClient:
    def __init__(self, server_path):
        self._server_path = server_path

    def send_command(self, data):
        client_socket_obj = UnixDomainClientSocket(LoggerSystem("TEST_CLIENT"))
        rc = client_socket_obj.uds_client_socket_init()
        if rc != RcCode.SUCCESS:
            print("Create socket fail")
            return rc
        
        rc = client_socket_obj.uds_client_socket_connect(self._server_path)
        if rc != RcCode.SUCCESS:
            print("Connect socket {} fail".format(self._server_path))
            return rc
        
        rc = client_socket_obj.uds_client_socket_send(data)
        if rc != RcCode.SUCCESS:
            print("Send data fail")
            return rc
        
        rc, data = client_socket_obj.uds_client_socket_recv(4)
        if rc == RcCode.DATA_NOT_READY:
            return RcCode.SUCCESS, None
        if rc != RcCode.SUCCESS:
            return rc, None
        receive_size = int.from_bytes(data, byteorder='little')

        # Receive the server reply
        data_str = ""
        while receive_size > 0:
            rc, reply_str = client_socket_obj.uds_client_socket_recv(receive_size)
            if rc == RcCode.DATA_NOT_READY:
                continue
            elif rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not send the message to server."))
                return rc, None
            if reply_str == b"":
                self._logger.warning(self._logger_system.set_logger_rc_code("Socket has closed."))
                client_socket_obj.uds_client_socket_close()
                break
            data_str = data_str + reply_str.decode('utf-8')
            receive_size = receive_size - len(data_str)

        # Retrieve the data from request
        reply = ReplyMsg()
        rc = reply.deserialize(data_str)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not convert reply to object"))
            return rc
        print("Request {} : Result : {}".format(reply.request, reply.result))
        match reply.request:
            case ConsoleServerEvent.GET_PORT_CONFIG | ConsoleServerEvent.GET_USER_ACCOUT | ConsoleServerEvent.GET_GROUP:
                print("Data:\n{}\n".format(reply.data))
        return RcCode.SUCCESS


def main(argv: list):
    if len(argv) < 2:
        print("Missing request")
        return
    request_cmd = argv[1]
    match request_cmd:
        case ConsoleServerEvent.CONNECT_SERIAL_PORT:
            if len(argv) < 3:
                print("Missing serial port ID")
                return
            serial_port_id = int(argv[2])
            if len(argv) < 4:
                print("Missing username")
                return
            username = argv[3]
            request = ConnectSerialPortRequest(serial_port_id, username)
            server_path = "/tmp/server_handler_{}.sock".format((serial_port_id - 1) % 8)
        case ConsoleServerEvent.GET_PORT_CONFIG:
            request = GetPortConfigRequest()
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.CONFIG_ALIAS_NAME:
            if len(argv) < 3:
                print("Missing serial port ID")
                return
            serial_port_id = int(argv[2])
            if len(argv) < 4:
                print("Missing alias")
                return
            alias_name = argv[3]
            request = ConfigAliasNameRequest(serial_port_id, alias_name)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.CONFIG_BAUD_RATE:
            if len(argv) < 3:
                print("Missing serial port ID")
                return
            serial_port_id = int(argv[2])
            if len(argv) < 4:
                print("Missing baud rate")
                return
            baud_rate = int(argv[3])
            request = ConfigBaudRateRequest(serial_port_id, baud_rate)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.CREATE_GROUP:
            if len(argv) < 3:
                print("Missing group name")
                return
            group_name = argv[2]
            role = "default"
            if len(argv) == 4:
                role = argv[2]
            request = CreateGroupRequest(group_name, role)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.DESTROY_GROUP:
            if len(argv) < 3:
                print("Missing group name")
                return
            group_name = argv[2]
            request = DestroyGroupRequest(group_name)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.GET_GROUP:
            request = GetGroupRequest()
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.ADD_USER_ACCOUNT:
            if len(argv) < 3:
                print("Missing username")
                return
            username = argv[2]
            if len(argv) < 4:
                print("Missing group name")
                return
            greoup_name = argv[3]
            role = "default"
            if len(argv) == 5:
                role = argv[4]
            request = AddUserAccountRequest(username, role, greoup_name)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.DEL_USER_ACCOUNT:
            if len(argv) < 3:
                print("Missing username")
                return
            username = argv[2]
            request = DelUserAccountRequest(username)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.MODIFY_USER_ROLE:
            if len(argv) < 3:
                print("Missing username")
                return
            username = argv[2]
            if len(argv) < 4:
                print("Missing role")
                return
            role = argv[3]
            request = ModifyUserRole(username, role)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.GET_USER_ACCOUT:
            username = None
            if len(argv) == 3:
                username = argv[2]
            request = GetUserAccount(username)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.USER_JOIN_GROUP:
            if len(argv) < 3:
                print("Missing username")
                return
            username = argv[2]
            if len(argv) < 4:
                print("Missing group name")
                return
            greoup_name = argv[3]
            request = UserJoinGroupRequest(username, greoup_name)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.USER_LEAVE_GROUP:
            if len(argv) < 3:
                print("Missing username")
                return
            username = argv[2]
            if len(argv) < 4:
                print("Missing group name")
                return
            greoup_name = argv[3]
            request = UserLeaveGroupRequest(username, greoup_name)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.PORT_JOIN_GROUP:
            if len(argv) < 3:
                print("Missing serial_port_id")
                return
            serial_port_id = int(argv[2])
            if len(argv) < 4:
                print("Missing group name")
                return
            greoup_name = argv[3]
            request = PortJoinGroupRequest(serial_port_id, greoup_name)
            server_path = "/tmp/server_mgmt.sock"
        case ConsoleServerEvent.PORT_LEAVE_GROUP:
            if len(argv) < 3:
                print("Missing serial_port_id")
                return
            serial_port_id = int(argv[2])
            if len(argv) < 4:
                print("Missing group name")
                return
            greoup_name = argv[3]
            request = PortLeaveGroupRequest(serial_port_id, greoup_name)
            server_path = "/tmp/server_mgmt.sock"
        case _:
            print("Invalid request")
            return

    client = RpcClient(server_path)
    rc, data_str = request.serialize()
    if rc != RcCode.SUCCESS:
        print("Can not convert the dictionary to string.")
        return
    rc = client.send_command(data_str)
    print("Result {}".format(RcCode.covert_rc_to_string(rc)))


if __name__ == '__main__':
    main(sys.argv)