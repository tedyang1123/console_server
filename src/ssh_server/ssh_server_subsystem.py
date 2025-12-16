import logging
import socket
import threading

import select

from src.common.rc_code import RcCode
from src.ssh_server.ssh_server_authenticator import SshServerNoneAuthenticator, SshServerPassWdAuthenticator, SshKeyHandler
from src.ssh_server.ssh_server_handler import SshServerHandler, SshServerNoneAuthHandler, SshServerPassWdAuthHandler


class SshServerSubsystem(threading.Thread):
    def __init__(self, ssh_ip_addr, ssh_port_id_list, subsystem_id, num_of_client):
        threading.Thread.__init__(self)

        # Save the variable
        self._ssh_ip_addr = ssh_ip_addr
        self._ssh_port_id_list = ssh_port_id_list
        self._subsystem_id = subsystem_id
        self._num_of_client = num_of_client

        # Server running status
        self._running = False

        # {
        #       ssh_port_id: EPOLL
        # }
        self._server_epoll_dict = {}

        # Store the server socket
        # {
        #       server_port_id: {
        #           "socket": Socket,
        #           "socket_fd": int
        #       }
        # }
        self._ssh_subsystem_sock = {}

        # Save the socket information
        # {
        #       ssh_port_id: [ssh_server_handler1, ...]
        # }
        self._server_handler_dict = {}

        # logger
        self._logger = logging.getLogger(__name__ + " {}".format(self._subsystem_id))

    def _init_logger_system(self):
        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
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

        return RcCode.SUCCESS

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
        # Init the logger system,
        rc = self._init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc

        for ssh_port_id in self._ssh_port_id_list:
            rc, server_socket = self._init_server_socket(ssh_port_id)
            if rc != RcCode.SUCCESS:
                return rc
            self._ssh_subsystem_sock[ssh_port_id] = {}
            self._ssh_subsystem_sock[ssh_port_id]["socket"] = server_socket
            self._ssh_subsystem_sock[ssh_port_id]["socket_fd"] = server_socket.fileno()

            self._server_handler_dict[ssh_port_id] = []
        return RcCode.SUCCESS

    def _start_server(self):
        for ssh_port_id in self._ssh_port_id_list:
            rc = self._start_server_socket(ssh_port_id)
            if rc != RcCode.SUCCESS:
                return rc
        return RcCode.SUCCESS

    def _clean_client(self, server_port_id, max_ssh_server_handler=5, force=False):
        num_exist_client = len(self._server_handler_dict)
        if num_exist_client == 0:
            return

        #
        # In the method, we only remove a client from the list.
        # We only check max_client server_handler in the method.
        #

        # process the specified server socket handler
        server_handler_list = self._server_handler_dict[server_port_id]
        count = 0
        for server_handler in server_handler_list:
            if not server_handler.init:
                del_it = False
                if server_handler.started and server_handler.running and force:
                    server_handler.running = False
                    del_it = True
                elif server_handler.started and not server_handler.running:
                    del_it = True
                if del_it:
                    server_handler.join()
                    server_handler_list.remove(server_handler)
                    break
            count = count + 1
            if count >= max_ssh_server_handler:
                break

    def _process_server_socket_event(self, server_epoll):
        raise NotImplemented

    def run(self):
        # Init subsystem
        rc = self._init_server()
        if rc != RcCode.SUCCESS:
            return

        # Start the subsystem
        rc = self._start_server()
        if rc != RcCode.SUCCESS:
            return

        self._running = True
        self._logger.info("SSH server is running.........")
        try:
            # Create epoll to monitor server list
            for ssh_port_id in self._ssh_port_id_list:
                server_epoll = select.epoll()
                server_epoll.register(self._ssh_subsystem_sock[ssh_port_id]["socket_fd"], select.EPOLLIN)
                self._server_epoll_dict[ssh_port_id] = server_epoll

            # Main process to handle the client event
            while self._running:
                for ssh_port_id in self._ssh_port_id_list:
                    rc = self._process_server_socket_event(ssh_port_id)
                    if rc != RcCode.SUCCESS:
                        self._running = False
                    self._clean_client(ssh_port_id)

            # Main process has stop, clean the server epoll and socket.
            for ssh_port_id in self._ssh_port_id_list:
                self._ssh_subsystem_sock[ssh_port_id]["socket"].close()
                self._server_epoll_dict[ssh_port_id].unregister(self._ssh_subsystem_sock[ssh_port_id]["socket_fd"])
        except OSError:
            self._logger.warning("Socket error occurs.")


class SshServerPassWdAuthSubSystemWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self._server_handler_list = []
        self._server_handler_list_lock = threading.Lock()
        self._running = False

    def add_server_handler(self, server_handler):
        with self._server_handler_list_lock:
            self._server_handler_list.append(server_handler)
        return RcCode.SUCCESS

    def delete_server_handler(self, server_handler):
        with self._server_handler_list_lock:
            self._server_handler_list.remove(server_handler)
        return RcCode.SUCCESS

    def run(self):
        self._running = True
        while self._running:
            for server_handler in self._server_handler_list:
                rc = server_handler.handler()
                if rc != RcCode.SUCCESS:
                    self._running = False


class SshServerPassWdAuthSubSystem(SshServerSubsystem):
    def __init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, polling_interval):
        self._ssh_key_handler = SshKeyHandler(server_pri_key_file='~/.ssh/id_rsa')
        self._polling_interval = polling_interval
        SshServerSubsystem.__init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client)
        self._worker_list = []
        for group_id in range(8):
            worker = SshServerPassWdAuthSubSystemWorker()
            self._worker_list.append(worker)
        self._next_worker_id = 0

    def _process_server_socket_event(self, server_port_id):
        events = self._server_epoll_dict[server_port_id](timeout=self._polling_interval)
        for file_no, event in events:
            if server_port_id == file_no:
                # A new client wants to connect the sever. Create a SSH server handler for this client
                client_sock = self._ssh_subsystem_sock[server_port_id]["socket"].accept()
                self._logger.info("A new client arrived. {}".format(client_sock[0].getpeername()))
                server_handler = SshServerPassWdAuthHandler(client_sock[0],
                                                            self._ssh_key_handler,
                                                            ssh_authenticator_server_class=SshServerPassWdAuthenticator)
                server_handler.start()
                self._logger.info("A new thread to service the client {}".format(client_sock[0].getpeername()))
                self._server_handler_dict[server_port_id].append(server_handler)
                continue
        for server_port_id in self._server_handler_dict:
            server_handler_list = self._server_handler_dict[server_port_id]
            exit_flag = False
            for server_handler in server_handler_list:
                if server_handler.running and server_handler.complete:
                    rc = self._worker_list[self._next_worker_id].add_server_handler(server_handler)
                    if rc != RcCode.SUCCESS:
                        exit_flag = True
                        break
                elif not server_handler.running and server_handler.complete:
                    rc = self._worker_list[self._next_worker_id].delete_server_handler(server_handler)
                    if rc != RcCode.SUCCESS:
                        exit_flag = True
                        break
            if exit_flag:
                break
        return RcCode.SUCCESS


class SshServerNoneAuthSubSystem(SshServerSubsystem):
    def __init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, polling_interval):
        self._ssh_key_handler = SshKeyHandler(server_pri_key_file='~/.ssh/id_rsa')
        self._polling_interval = polling_interval
        SshServerSubsystem.__init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client)

    def _process_server_socket_event(self, server_port_id):
        events = self._server_epoll_dict[server_port_id](timeout=self._polling_interval)
        for file_no, event in events:
            if server_port_id == file_no:
                # A new client wants to connect the sever. Create a SSH server handler for this client
                client_sock = self._ssh_subsystem_sock[server_port_id]["socket"].accept()
                self._logger.info("A new client arrived. {}".format(client_sock[0].getpeername()))
                server_handler = SshServerNoneAuthHandler(client_sock[0],
                                                         self._ssh_key_handler,
                                                         ssh_authenticator_server_class=SshServerNoneAuthenticator)
                server_handler.start()
                self._logger.info("A new thread to service the client {}".format(client_sock[0].getpeername()))
                self._server_handler_dict[server_port_id] = server_handler
                continue
        for server_port_id in self._server_handler_dict:
            server_handler_list = self._server_handler_dict[server_port_id]
            for server_handler in server_handler_list:
                if server_handler.complete:
                    rc = server_handler.handler()
                    if rc != RcCode.SUCCESS:
                        break
        return RcCode.SUCCESS
