import errno
import os
import socket

from src.common.rc_code import RcCode


class UnixDomainServerSocket:
    def __init__(self, max_client, uds_server_file_path, logger_system):
        self._uds_server_file_path = uds_server_file_path
        self._max_client = max_client
        self._logger_system = logger_system
        self._logger = logger_system.get_logger()

        self._uds_socket = None

    def uds_server_socket_fd_get(self):
        if self._uds_socket is None:
            return -1
        return self._uds_socket.fileno()

    def uds_server_socket_init(self, blocking=True):
        if os.path.exists(self._uds_server_file_path):
            os.remove(self._uds_server_file_path)
        self._logger.info(
            self._logger_system.set_logger_rc_code(
                "Create server UDSsocket using path {}".format(self._uds_server_file_path)))
        try:
            self._uds_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._uds_socket.bind(self._uds_server_file_path)
            self._uds_socket.listen(self._max_client)
            self._uds_socket.setblocking(blocking)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_server_socket_accept(self, blocking=True):
        try:
            client_socket = self._uds_socket.accept()
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Accept a new client {}.".format(client_socket[0].getpeername())))
            if not blocking:
                client_socket[0].setblocking(False)
        except OSError:
            return RcCode.FAILURE, None
        return RcCode.SUCCESS, client_socket[0]

    def uds_server_socket_close(self):
        try:
            self._logger.info(self._logger_system.set_logger_rc_code("Server socket close."))
            self._uds_socket.close()
        except OSError:
            self._logger.info(self._logger_system.set_logger_rc_code("Can not close the server socket"))
        return RcCode.SUCCESS


class UnixDomainConnectedClientSocket:
    def __init__(self, client_socket, logger_system):
        self._client_socket = client_socket
        self._logger_system = logger_system
        self._logger = logger_system.get_logger()

    def uds_client_socket_fd_get(self):
        if self._client_socket is None:
            return -1
        return self._client_socket.fileno()

    def uds_client_socket_send(self, data):
        try:
            self._logger.info(self._logger_system.set_logger_rc_code("Send message {}".format(data)))
            self._client_socket.sendall(data)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_recv(self, max_size):
        wait = True
        data = b""
        while wait:
            try:
                data = self._client_socket.recv(max_size)
                wait = False
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    return RcCode.DATA_NOT_READY, e
                return RcCode.FAILURE, e
        return RcCode.SUCCESS, data

    def uds_client_socket_close(self):
        try:
            self._logger.info(self._logger_system.set_logger_rc_code("Client socket close."))
            self._client_socket.close()
        except OSError:
            self._logger.info(self._logger_system.set_logger_rc_code("Can not close the client socket"))
        return RcCode.SUCCESS


class UnixDomainClientSocket:
    def __init__(self, logger_system, uds_client_file_path=""):
        self._logger_system = logger_system
        self._uds_client_file_path = uds_client_file_path

        self._logger = logger_system.get_logger()
        self._uds_socket = None

    def uds_client_socket_init(self, blocking=True):
        if self._uds_client_file_path != "" and os.path.exists(self._uds_client_file_path):
            os.remove(self._uds_client_file_path)
        try:
            self._uds_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if self._uds_client_file_path != "":
                self._uds_socket.bind(self._uds_client_file_path)
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Create client UDS socket using path {}".format(self._uds_client_file_path)))
            if not blocking:
                self._uds_socket.setblocking(False)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_set_blocking(self, blocking=True):
        try:
            self._uds_socket.setblocking(blocking)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_connect(self, uds_server_file_path):
        try:
            self._uds_socket.connect(uds_server_file_path)
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Connect with server client {}.".format(self._uds_socket.getpeername())))
        except OSError as e:
            print(e)
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_send(self, data):
        try:
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Send the data {} to host {}".format(data, self._uds_socket.getpeername())))
            if isinstance(data, str):
                self._uds_socket.sendall(bytes(data, 'utf-8'))
            else:
                self._uds_socket.sendall(data)
        except OSError as e:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def uds_client_socket_recv(self, max_size):
        wait = True
        data = b""
        while wait:
            try:
                data = self._uds_socket.recv(max_size)
                wait = False
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    return RcCode.DATA_NOT_READY, e
                return RcCode.FAILURE, e
        return RcCode.SUCCESS, data

    def uds_client_socket_close(self):
        try:
            self._logger.info(self._logger_system.set_logger_rc_code("Client socket close."))
            self._uds_socket.close()
        except OSError:
            self._logger.info(self._logger_system.set_logger_rc_code("Can not close the client socket"))
        return RcCode.SUCCESS