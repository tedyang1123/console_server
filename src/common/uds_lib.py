import errno
import json
import os
import socket

from src.common.rc_code import RcCode


def serialize_data(data_dict):
    return json.dumps(data_dict)

def deserialize_data(data_str):
    return json.loads(data_str)


class UnixDomainServerSocket:
    def __init__(self, max_client, uds_server_file_path, logger_system):
        self._uds_server_file_path = uds_server_file_path
        self._max_client = max_client
        self._logger_system = logger_system
        self._logger = logger_system.get_logger()

        self._uds_socket = None

    def uds_server_socket_fd_get(self):
        if self._uds_socket is None:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._uds_socket.fileno()

    def uds_server_socket_init(self):
        if os.path.exists(self._uds_server_file_path):
            os.remove(self._uds_server_file_path)
        self._logger.info(
            self._logger_system.set_logger_rc_code(
                "Create server UDSsocket using path {}".format(self._uds_server_file_path)))
        try:
            self._uds_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._uds_socket.bind(self._uds_server_file_path)
            self._uds_socket.listen(self._max_client)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_server_socket_accept(self):
        try:
            client_socket = self._uds_socket.accept()
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Accept a new client {}.".format(client_socket[0].getpeername())))
        except OSError:
            return RcCode.FAILURE, None
        return RcCode.SUCCESS, client_socket

    def uds_server_socket_close(self):
        try:
            self._logger.info(self._logger_system.set_logger_rc_code("Server socket close."))
            self._uds_socket.close()
        except OSError:
            self._logger.info(self._logger_system.set_logger_rc_code("Can not close the server socket"))
        return RcCode.SUCCESS

    def uds_client_socket_send(self, client_socket, data):
        try:
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Send the data {} to host {}".format(data, client_socket[0].getpeername())))
            if isinstance(data, str):
                client_socket[0].sendall(bytes(data, 'utf-8'))
            else:
                client_socket[0].sendall(data)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_recv(self, client_socket, max_size):
        wait = True
        data = ""
        while wait:
            try:
                data = client_socket[0].recv(max_size)
                wait = False
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    return RcCode.DATA_NOT_READY
                return RcCode.FAILURE, None
        data_str = ""
        for data_byte in data:
            try:
                data_str = data_str + chr(data_byte)
            except UnicodeDecodeError:
                data_str = data_str + "."
        self._logger.info(
            self._logger_system.set_logger_rc_code(
                "Receive the data {} from host {}".format(data, client_socket[0].getpeername())))
        return RcCode.SUCCESS, data_str

    def uds_client_socket_close(self, client_socket):
        try:
            self._logger.info(self._logger_system.set_logger_rc_code("Client socket close."))
            client_socket[0].close()
        except OSError:
            self._logger.info(self._logger_system.set_logger_rc_code("Can not close the client socket"))
        return RcCode.SUCCESS


class UnixDomainClientSocket:
    def __init__(self, logger_system, uds_client_file_path=""):
        self._logger_system = logger_system
        self._uds_client_file_path = uds_client_file_path

        self._logger = logger_system.get_logger()
        self._uds_socket = None

    def uds_client_socket_init(self, non_blocking=False):
        if self._uds_client_file_path != "" and os.path.exists(self._uds_client_file_path):
            os.remove(self._uds_client_file_path)
        try:
            self._uds_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if self._uds_client_file_path != "":
                self._uds_socket.bind(self._uds_client_file_path)
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Create client UDS socket using path {}".format(self._uds_client_file_path)))
            if non_blocking:
                self._uds_socket.setblocking(False)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_connect(self, uds_server_file_path):
        try:
            self._uds_socket.connect(uds_server_file_path)
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Connect with server client {}.".format(self._uds_socket.getpeername())))
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_send(self, data):
        try:
            self._logger_system.set_logger_rc_code(
                "Send the data {} to host {}".format(data, self._uds_socket.getpeername()))
            if isinstance(data, str):
                self._uds_socket.sendall(bytes(data, 'utf-8'))
            else:
                self._uds_socket.sendall(data)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_recv(self, max_size):
        wait = True
        data = ""
        while wait:
            try:
                data = self._uds_socket.recv(max_size)
                wait = False
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    return RcCode.DATA_NOT_READY, None
                return RcCode.FAILURE, None
        data_str = ""
        for data_byte in data:
            try:
                data_str = data_str + chr(data_byte)
            except UnicodeDecodeError:
                data_str = data_str + "."
            except Exception as e:
                self._logger.info(self._logger_system.set_logger_rc_code(e))
        self._logger.info(
            self._logger_system.set_logger_rc_code(
                "Receive the data {} from host {}".format(data, self._uds_socket.getpeername())))
        return RcCode.SUCCESS, data_str

    def uds_client_socket_close(self):
        try:
            self._logger.info(self._logger_system.set_logger_rc_code("Client socket close."))
            self._uds_socket.close()
        except OSError:
            self._logger.info(self._logger_system.set_logger_rc_code("Can not close the client socket"))
        return RcCode.SUCCESS