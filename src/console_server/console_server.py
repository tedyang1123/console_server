import errno
import json
import logging
import os
import socket
import threading
import time

import select

from src.common.rc_code import RcCode
from src.console_server.console_server_handler import ConsoleServerHandler


class ConsoleServer(threading.Thread):
    def __init__(self, num_of_port, max_client=10, max_server_msg_size=1024):
        super().__init__()
        self._num_of_port = num_of_port
        self._console_server_handler_daemon_list = []
        self._serial_port_config_list = []
        self._uds_file_name = "server_mgmt.sock"
        self._max_client = max_client
        self._server_sock = None
        self._server_mgmt_sock_epoll = None
        self._client_sock_info_dict = {}
        self._max_server_msg_size = max_server_msg_size

        # Create 8 port group
        # [1, 9, 17 ...]
        # [2, 10, 18 ...]
        # [3, 11, 19 ...]
        # ...
        # [7, 15, 23 ...]
        # [8, 16, 24 ...]
        self._serial_port_group_list = [
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            []
        ]
        self._running = False

        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._logger = logging.getLogger(__name__)
        self._screen_handler = logging.StreamHandler()
        self._screen_handler.setLevel(logging.WARNING)
        self._screen_handler.setFormatter(self._formatter)

        self._file_handler = logging.FileHandler("/var/log/console-server.log")
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(self._formatter)

        self._logger.setLevel(logging.DEBUG)

        self._logger.addHandler(self._screen_handler)
        self._logger.addHandler(self._file_handler)
        self._logger.propagate = False

    def __del__(self):
        for sock_fd in self._client_sock_info_dict:
            self._uds_socket_close(self._client_sock_info_dict[sock_fd])

    def _uds_socket_init(self):
        if os.path.exists(self._uds_file_name):
            os.remove(self._uds_file_name)
        try:
            self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server_sock.bind(self._uds_file_name)
            self._server_sock.listen(self._max_client)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _uds_socket_connect(self):
        try:
            client_sock, _ = self._server_sock.accept()
        except OSError:
            return RcCode.FAILURE, None
        return RcCode.SUCCESS, client_sock

    def _uds_socket_send(self, sock, data):
        try:
            sock.sendall(data)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _uds_socket_recv(self, sock, max_size):
        wait = True
        data = ""
        while wait:
            try:
                data = sock.recv(max_size)
                wait = False
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    continue
                return RcCode.FAILURE, None
        return RcCode.SUCCESS, data

    def _uds_socket_close(self, sock):
        try:
            sock.close()
        except OSError:
            pass
        return RcCode.SUCCESS

    def _init_server(self):
        for i in range(self._num_of_port):
            serial_port_config_dict = {
                "port_id": i + 1,
                "port_name": "COM{}".format(i + 1),
                "baud_rate": 115200,
                "description": ""
            }
            self._serial_port_config_list.append(serial_port_config_dict)

        # Separate the port to different port group
        for i in range(self._num_of_port):
            self._serial_port_group_list[(i % 8)].append(self._serial_port_config_list[i])

        # Create the daemon for each port group
        daemon_id = 1
        for serial_port_list in self._serial_port_group_list:
            # Create the daemon and put it in the list
            daemon_event = threading.Event()
            handler_daemon = ConsoleServerHandler(serial_port_list, daemon_event, daemon_id)
            handler_daemon.start()
            daemon_event.wait() 
            if not handler_daemon.is_running():
                self._logger.warning("Sub-daemon has stopped.")
                return RcCode.FAILURE
            self._console_server_handler_daemon_list.append(handler_daemon)
            self._logger.warning("Start Sub-daemon completely.")
            daemon_id = daemon_id + 1

        rc = self._uds_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Initialize the server socket for console server management system failed.")
            return rc

        self._logger.warning("Server initialize completely.")
        return RcCode.SUCCESS

    def client_msg_handle(self, request, client_sock):
        match request:
            case "port_config":
                port_config_str_ = json.dumps(self._serial_port_config_list)
                rc = self._uds_socket_send(client_sock, port_config_str_)
                if rc != RcCode.SUCCESS:
                    return rc
            case "shutdown":
                self._running = False
            case _:
                rc = self._uds_socket_send(client_sock, "Failed")
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS

    def daemon_main(self):
        # Create the epoll to monitor the server socket
        self._server_mgmt_sock_epoll = select.epoll()
        self._server_mgmt_sock_epoll.register(self._server_sock.fileno(), select.EPOLLIN)

        self._running = True
        rc = RcCode.SUCCESS
        while self._running:
            events = self._server_mgmt_sock_epoll.poll(0.01)
            for sock_fd, event in events:
                if sock_fd == self._server_sock.fileno():
                    # Connect with the new client.
                    rc, client_sock = self._uds_socket_connect()
                    if rc != RcCode.SUCCESS:
                        # Ignore this event, process next event.
                        continue
                    client_sock_fd = client_sock.fileno()
                    self._client_sock_info_dict[client_sock_fd] = {}
                    self._client_sock_info_dict[client_sock_fd]["socket"] = client_sock
                elif event & select.EPOLLIN:
                    client_sock_info = self._client_sock_info_dict[sock_fd]

                    # Receive the client message
                    rc, data = self._uds_socket_recv(client_sock_info["socket"], self._max_server_msg_size)
                    if rc != RcCode.SUCCESS:
                        # Can not receive the data from the socket due to any error.
                        # Close this socket and remove this socket from the socket dictionary.
                        # Remove the socket from the EPOLL list.
                        # Process the next event.
                        client_sock_info["socket"].close()
                        del client_sock_info
                        self._server_mgmt_sock_epoll.unregister(sock_fd)
                        continue

                    rc = self.client_msg_handle(data, client_sock_info["socket"])
                    if rc != RcCode.SUCCESS:
                        break
                elif event & select.EPOLLHUP:
                    # Client disconnects the socket.
                    # Clear the socket information for request list and epoll.
                    # Remove the socket from the EPOLL list.
                    client_sock_info = self._client_sock_info_dict[sock_fd]
                    client_sock_info.close()
                    del client_sock_info
                    self._server_mgmt_sock_epoll.unregister(sock_fd)
        return rc

    def run(self):
        # Initialize the console server including the serial port and server management socket.
        rc = self._init_server()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Initialize the server fail.")
            return

        # Start main flow
        rc = self.daemon_main()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Console server management system has stopped.")

        # Daemon has stopped. Release the resource.
        for sock_fd in self._client_sock_info_dict:
            self._uds_socket_close(self._client_sock_info_dict[sock_fd])
        self._uds_socket_close(self._server_sock)

        self._logger.warning("Console server management system shutdown.")
