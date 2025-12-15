import logging
import socket
import threading

import select

from src.common.rc_code import RcCode
from src.ssh_server.ssh_server_authenticator import SshServerPassWdAuthenticator, SshKeyHandler
from src.ssh_server.ssh_server_handler import SshServerHandler


class SshServerSubsystem(threading.Thread):
    def __init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, daemon_id, polling_interval,
                 ssh_key_handler, ssh_authenticator):
        threading.Thread.__init__(self)
        self._ssh_ip_addr = ssh_ip_addr
        self._ssh_port_list = ssh_port_list
        self._subsystem_id = subsystem_id
        self._num_of_client = num_of_client
        self._daemon_id = daemon_id
        self._running = False
        self._server_epoll = None
        self._polling_interval = polling_interval
        self._ssh_key_handler = ssh_key_handler
        self._authenticator = ssh_authenticator

        # Store the server socket
        # {
        #       server_port_id: {
        #           "socket": Socket,
        #           "socket_fd": int
        #       }
        # }
        self._ssh_subsystem_sock = {}
        self._server_handler_list = []

        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._logger = logging.getLogger(__name__ + " {}".format(self._subsystem_id))
        self._screen_handler = logging.StreamHandler()
        self._screen_handler.setLevel(logging.WARNING)
        self._screen_handler.setFormatter(self._formatter)

        self._file_handler = logging.FileHandler('/var/log/ssh-server.log')
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(self._formatter)

        self._logger.setLevel(logging.DEBUG)

        self._logger.addHandler(self._screen_handler)
        self._logger.addHandler(self._file_handler)
        self._logger.propagate = False

    def _init_server_socket(self, port_id):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self._ssh_ip_addr, port_id))
        except OSError:
            self._logger.warning("can not init server socket.")
            return RcCode.FAILURE, None
        return RcCode.SUCCESS, server_socket

    def _start_server_socket(self, port_id):
        try:
            self._ssh_subsystem_sock[port_id].listen(self._num_of_client)
        except OSError:
            self._logger.warning("Can not listen server socket.")
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _init_server(self):
        for ssh_port in self._ssh_port_list:
            rc, server_socket = self._init_server_socket(ssh_port)
            if rc != RcCode.SUCCESS:
                return rc
            self._ssh_subsystem_sock[ssh_port] = {}
            self._ssh_subsystem_sock[ssh_port]["socket"] = server_socket
            self._ssh_subsystem_sock[ssh_port]["socket_fd"] = server_socket.fileno()
        return RcCode.SUCCESS

    def _start_server(self):
        for ssh_port in self._ssh_port_list:
            rc = self._start_server_socket(ssh_port)
            if rc != RcCode.SUCCESS:
                return rc
        return RcCode.SUCCESS

    def _clean_client(self, max_client=5, force=False):
        self._next_client_idx = 0
        num_exist_client = len(self._server_handler_list)
        if num_exist_client == 0:
            return
        for i in range(max_client):
            client_handler = self._server_handler_list[(i + self._next_client_idx) % num_exist_client]
            if client_handler.init:
                continue
            del_it = False
            if client_handler.started and client_handler.running and force:
                client_handler.running = False
                del_it = True
            elif client_handler.started and not client_handler.running:
                del_it = True
            if del_it:
                client_handler.join()
                self._server_handler_list.remove(client_handler)
                del client_handler
                break
            self._next_client_idx = self._next_client_idx + 1

    def run(self):
        rc = self._init_server()
        if rc != RcCode.SUCCESS:
            return

        rc = self._start_server()
        if rc != RcCode.SUCCESS:
            return

        self._running = True
        self._logger.info("SSH server is running.........")
        try:
            self._server_epoll = select.epoll()
            for server_port_id in self._ssh_subsystem_sock:
                self._server_epoll.register(self._ssh_subsystem_sock[server_port_id]["socket_fd"], select.EPOLLIN)
            while self._running:
                events = self._server_epoll.poll(timeout=self._polling_interval)
                for file_no, event in events:
                    find_socket = False
                    server_socket = None
                    for server_port_id in self._ssh_subsystem_sock:
                        if self._ssh_subsystem_sock[server_port_id]["socket_fd"] == file_no:
                            find_socket = True
                            server_socket = self._ssh_subsystem_sock[server_port_id]["socket"]
                            break
                    if find_socket:
                        client_sock = server_socket.accept()
                        self._logger.info("A new client arrived. {}".format(client_sock[0].getpeername()))
                        server_handler = SshServerHandler(client_sock[0],
                                                          self._ssh_key_handler, ssh_server_class=self._authenticator)
                        server_handler.start()
                        self._logger.info("A new thread to service the client {}".format(client_sock[0].getpeername()))
                        self._server_handler_list.append(server_handler)
                        continue
                self._clean_client()

            for server_port_id in self._ssh_subsystem_sock:
                self._ssh_subsystem_sock[server_port_id]["socket"].close()
                self._server_epoll.unregister(self._ssh_subsystem_sock[server_port_id]["socket_fd"])
        except OSError:
            self._logger.warning("Socket error occurs.")


class SshServerAuthSubSystem(threading.Thread, SshServerSubsystem):
    def __init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, daemon_id, polling_interval):
        threading.Thread.__init__(self)
        SshServerSubsystem.__init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, daemon_id,
                                    polling_interval, SshKeyHandler, SshServerPassWdAuthenticator)


class SshServerNoAuthSubSystem(threading.Thread, SshServerSubsystem):
    def __init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, daemon_id, polling_interval):
        threading.Thread.__init__(self)
        SshServerSubsystem.__init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, daemon_id,
                                    polling_interval, SshKeyHandler, SshServerPassWdAuthenticator)
