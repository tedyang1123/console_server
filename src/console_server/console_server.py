import json
import threading
import select

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainServerSocket
from src.console_server.console_server_handler import ConsoleServerHandler


class ConsoleServerPortConfigDict:
    def __init__(self):
        self._serial_port_group_list = {}

    def add_port_group(self, group_id):
        if group_id in self._serial_port_group_list:
            return RcCode.DATA_EXIST
        self._serial_port_group_list[group_id] = {}
        return RcCode.SUCCESS

    def del_port_group(self, group_id):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_group_list[group_id]
        return RcCode.SUCCESS

    def get_port_group(self, group_id):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._serial_port_group_list[group_id]

    def add_serial_port_config(self, group_id, serial_port_id, port_name, baud_rate, alias):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND
        if serial_port_id in self._serial_port_group_list[group_id]:
            return RcCode.DATA_EXIST
        self._serial_port_group_list[group_id][serial_port_id] = {}
        self._serial_port_group_list[group_id][serial_port_id]['port_name'] = port_name
        self._serial_port_group_list[group_id][serial_port_id]['baud_rate'] = baud_rate
        self._serial_port_group_list[group_id][serial_port_id]['alias'] = alias
        return RcCode.SUCCESS

    def del_serial_port_config(self, group_id, serial_port_id):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND
        if serial_port_id not in self._serial_port_group_list[group_id]:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_group_list[group_id][serial_port_id]
        return RcCode.SUCCESS

    def get_serial_port_config(self, group_id, serial_port_id, field=None):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND, None
        if serial_port_id not in self._serial_port_group_list[group_id]:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS, self._serial_port_group_list[group_id][serial_port_id]
        return RcCode.SUCCESS,  self._serial_port_group_list[group_id][serial_port_id][field]

    def get_serial_port_config_all(self):
        return RcCode.SUCCESS, self._serial_port_group_list


class ConsoleServerClientInfoDict:
    def __init__(self):
        self._client_info_dict = {}

    def add_client_info(self, socket_fd, socket_obj):
        if socket_fd in self._client_info_dict:
            return RcCode.DATA_EXIST
        self._client_info_dict[socket_fd] = {}
        self._client_info_dict[socket_fd]["socket_obj"] = socket_obj
        return RcCode.SUCCESS

    def del_client_info(self, socket_fd):
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND
        del self._client_info_dict[socket_fd]
        return RcCode.SUCCESS

    def get_client_info(self, socket_fd, field=None):
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS, self._client_info_dict[socket_fd]
        return  RcCode.SUCCESS, self._client_info_dict[socket_fd][field]

    def get_client_info_all(self):
        return RcCode.SUCCESS, self._client_info_dict


class ConsoleServer(threading.Thread):
    def __init__(self, num_of_serial_port, daemon_id, max_port_group=8, max_client=10, max_server_msg_size=1024):
        self._num_of_serial_port = num_of_serial_port
        self._daemon_id = daemon_id
        self._max_port_group = max_port_group
        self._max_client = max_client
        self._max_server_msg_size = max_server_msg_size
        threading.Thread.__init__(self, name="ConsoleServer_{}".format(daemon_id))

        self._logger_system = LoggerSystem(self.name)
        self._logger = self._logger_system.get_logger()
        self._uds_server_socket = UnixDomainServerSocket(
            max_client, "/tmp/server_mgmt.sock", self._logger_system)

        self._serial_port_config = ConsoleServerPortConfigDict()

        self._console_server_handler_list = []
        self._server_mgmt_sock_epoll = None
        self._client_info = ConsoleServerClientInfoDict()
        self._running = False

    def __del__(self):
        rc, client_info_dict = self._client_info.get_client_info_all()
        if rc != RcCode.SUCCESS:
            return
        for sock_fd in client_info_dict:
            self._uds_server_socket.uds_client_socket_close(client_info_dict[sock_fd]["socket_obj"])
        self._uds_server_socket.uds_server_socket_close()

    def _init_server(self):
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc

        for group_id in range(self._max_port_group):
            rc = self._serial_port_config.add_port_group(group_id)
            if rc != RcCode.SUCCESS:
                self._logger.info(
                    self._logger_system.set_logger_rc_code("Can not add the port group.", rc=rc))
                return rc

        for serial_port_id in range(1, self._num_of_serial_port + 1):
            group_id = (serial_port_id - 1) % 8
            rc = self._serial_port_config.add_serial_port_config(
                group_id, serial_port_id, "COM{}".format(serial_port_id), 115200, "COM{}".format(serial_port_id))
            if rc != RcCode.SUCCESS:
                self._logger.info(
                    self._logger_system.set_logger_rc_code(
                        "Can not add the port config for serial port {}.".format(serial_port_id), rc=rc))
                return rc

        # Create the daemon for each port group
        self._logger.info(
            self._logger_system.set_logger_rc_code("Create daemon to process serial ports"))
        daemon_id = 1
        for group_id in range(1, self._max_port_group + 1):
            rc, port_group = self._serial_port_config.get_port_group(group_id - 1)
            if rc != RcCode.SUCCESS:
                self._logger.info(
                    self._logger_system.set_logger_rc_code("Can not port group {}.".format(group_id), rc=rc))
                return rc

            # Create the daemon and put it in the list
            daemon_event = threading.Event()
            handler_daemon = ConsoleServerHandler(port_group, daemon_event, daemon_id)
            handler_daemon.start()
            daemon_event.wait()
            if not handler_daemon.is_running():
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Sub-daemon has stopped."))
                return RcCode.FAILURE
            self._console_server_handler_list.append(handler_daemon)
            self._logger.info(
                self._logger_system.set_logger_rc_code("Start Sub-daemon completely."))
            daemon_id = daemon_id + 1

        rc = self._uds_server_socket.uds_server_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Initialize the server socket for console server management system failed."))
            return rc

        self._logger.info(
            self._logger_system.set_logger_rc_code("Server initialize completely."))
        return RcCode.SUCCESS

    def client_msg_handle(self, request, client_sock):
        match request:
            case "port_config":
                rc, port_group_config_dict = self._serial_port_config.get_serial_port_config_all()
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not get the port config.", rc=rc))
                    return rc
                port_config_dict = {}
                for group_id in port_group_config_dict:
                    port_config_dict = port_config_dict | port_config_dict | port_group_config_dict[group_id]
                self._logger.info(
                    self._logger_system.set_logger_rc_code("Data is ready. {}".format(port_config_dict)))

                json_str = json.dumps(port_config_dict)
                rc = self._uds_server_socket.uds_client_socket_send(
                    client_sock, len(json_str).to_bytes(4, byteorder="little"))
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Send the data length {} failed.".format(len(json_str)), rc=rc))
                    return rc

                self._logger.info(
                    self._logger_system.set_logger_rc_code("Send the data {}.".format(json_str)))

                rc = self._uds_server_socket.uds_client_socket_send(client_sock, json_str)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Send the data {} failed.".format(json_str), rc=rc))
                    return rc
            case "shutdown":
                self._running = False
            case _:
                rc = self._uds_server_socket.uds_client_socket_send(client_sock, "Failed")
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS

    def daemon_main(self):
        # Create the epoll to monitor the server socket
        self._server_mgmt_sock_epoll = select.epoll()
        rc, server_socket_fd = self._uds_server_socket.uds_server_socket_fd_get()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the server socket FD.", rc=rc))
            return rc
        self._server_mgmt_sock_epoll.register(server_socket_fd, select.EPOLLIN)

        self._running = True
        rc = RcCode.SUCCESS
        while self._running:
            events = self._server_mgmt_sock_epoll.poll(0.01)
            for socket_fd, event in events:
                if socket_fd == server_socket_fd:
                    # Connect with the new client.
                    rc, client_socket_obj = self._uds_server_socket.uds_server_socket_accept()
                    if rc != RcCode.SUCCESS:
                        # Ignore this event, process next event.
                        continue
                    self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "A new client arrived. {}".format(client_socket_obj[0].getpeername())))
                    client_socket_fd = client_socket_obj[0].fileno()
                    rc = self._client_info.add_client_info(client_socket_fd, client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not add client information {}".format(
                                        client_socket_obj[0].getpeername()), rc=rc))
                        return rc
                    self._server_mgmt_sock_epoll.register(client_socket_fd, select.EPOLLIN)
                elif event & select.EPOLLIN:
                    rc, client_socket_obj = self._client_info.get_client_info(socket_fd, "socket_obj")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not get client information {}".format(socket_fd), rc=rc))
                        return rc

                    # Receive the client message
                    rc, data = self._uds_server_socket.uds_client_socket_recv(client_socket_obj, self._max_server_msg_size)
                    if rc != RcCode.SUCCESS:
                        # Can not receive the data from the socket due to any error.
                        # Close this socket and remove this socket from the socket dictionary.
                        # Remove the socket from the EPOLL list.
                        # Process the next event.
                        self._uds_server_socket.uds_client_socket_close(client_socket_obj)
                        rc = self._client_info.del_client_info(socket_fd)
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code(
                                            "Can not remove client {} information.".format(socket_fd), rc=rc))
                            return rc
                        self._server_mgmt_sock_epoll.unregister(socket_fd)
                        continue

                    rc = self.client_msg_handle(data, client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not client {} request.".format(client_socket_obj[0].getpeername()), rc=rc))
                        rc, client_socket_obj = self._client_info.get_client_info(socket_fd, "socket_obj")
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code(
                                    "Can not get client {} information.".format(socket_fd), rc=rc))
                            return rc
                        self._uds_server_socket.uds_client_socket_close(client_socket_obj)
                        rc = self._client_info.del_client_info(socket_fd)
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code(
                                    "Can not remove client {} information.".format(socket_fd), rc=rc))
                            return rc
                elif event & select.EPOLLHUP:
                    # Client disconnects the socket.
                    # Clear the socket information for request list and epoll.
                    # Remove the socket from the EPOLL list.

                    rc, client_socket_obj = self._client_info.get_client_info(socket_fd, "socket_obj")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not get client {} information.".format(socket_fd), rc=rc))
                        return rc
                    self._uds_server_socket.uds_client_socket_close(client_socket_obj)
                    rc = self._client_info.del_client_info(socket_fd)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not remove client {} information.".format(socket_fd), rc=rc))
                        return rc
                    self._server_mgmt_sock_epoll.unregister(socket_fd)
        return RcCode.SUCCESS

    def run(self):
        # Initialize the console server including the serial port and server management socket.
        rc = self._init_server()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Initialize the server fail."))
            return

        # Start main flow
        rc = self.daemon_main()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Console server management system has stopped.", rc=rc))

        # Daemon has stopped. Release the resource.
        rc, client_sock_dict = self._client_info.get_client_info_all()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get all of the client socket information.", rc=rc))
        for socket_fd in client_sock_dict:
            self._uds_server_socket.uds_client_socket_close(client_sock_dict[socket_fd]["socket_obj"])

        src, server_socket_fd = self._uds_server_socket.uds_server_socket_fd_get()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the server socket FD.", rc=rc))
            return
        else:
            rc = self._uds_server_socket.uds_server_socket_close()
            if rc != RcCode.SUCCESS:
                self._logger.warning(self._logger_system.set_logger_rc_code("Can not release the server socket."))

        self._logger.info(self._logger_system.set_logger_rc_code("Console server management system shutdown."))
