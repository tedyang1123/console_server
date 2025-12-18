import socket
import threading
import time

import select

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.ssh_server.ssh_server_authenticator import SshServerNoneAuthenticator, SshServerPassWdAuthenticator, SshKeyHandler
from src.ssh_server.ssh_server_handler import SshServerNoneAuthHandler, SshServerPassWdAuthHandler


class SshServerSubsystem(threading.Thread, LoggerSystem):
    def __init__(self, ssh_ip_addr, ssh_port_id_list, subsystem_id, num_of_client, thread_stop_event):
        threading.Thread.__init__(self)

        # Save the variable
        self._ssh_ip_addr = ssh_ip_addr
        self._ssh_port_id_list = ssh_port_id_list
        self._subsystem_id = subsystem_id
        self._num_of_client = num_of_client
        self._thread_stop_event = thread_stop_event

        # Server running status
        self.running = False

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

    def _init_server_socket(self, port_id):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self._ssh_ip_addr, port_id))
        except OSError:
            self._logger.error("can not init server socket.")
            return RcCode.FAILURE, None
        return RcCode.SUCCESS, server_socket

    def _start_server_socket(self, port_id):
        try:
            self._ssh_subsystem_sock[port_id]["socket"].listen(self._num_of_client)
        except OSError:
            self._logger.error("Can not listen server socket.")
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _init_server(self):
        # Init the logger system,
        rc = self.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info("Socket port list {}.".format(self._ssh_port_id_list))
        for ssh_port_id in self._ssh_port_id_list:
            rc, server_socket = self._init_server_socket(ssh_port_id)
            if rc != RcCode.SUCCESS:
                self._logger.error("Can not linit socket for port {}.".format(ssh_port_id))
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
                if server_handler.clear == True:
                    del_it = True
                elif server_handler.started and server_handler.running and force:
                    server_handler.running = False
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
    
    def clean_subsystem(self):
        # Main process has stop, clean the server epoll and socket.
        for ssh_port_id in self._ssh_port_id_list:
            self._ssh_subsystem_sock[ssh_port_id]["socket"].close()
            self._server_epoll_dict[ssh_port_id].unregister(self._ssh_subsystem_sock[ssh_port_id]["socket_fd"])
        return RcCode.SUCCESS

    def run(self):
        # Init subsystem
        rc = self._init_server()
        if rc != RcCode.SUCCESS:
            self._logger.error("Error occurs")
            return

        # Start the subsystem
        rc = self._start_server()
        if rc != RcCode.SUCCESS:
            return

        self.running = True
        self._logger.info("SSH subserver {} is running.........".format(self._subsystem_id))
        try:
            # Create epoll to monitor server list
            for ssh_port_id in self._ssh_port_id_list:
                server_epoll = select.epoll()
                server_epoll.register(self._ssh_subsystem_sock[ssh_port_id]["socket_fd"], select.EPOLLIN)
                self._server_epoll_dict[ssh_port_id] = server_epoll

            # Main process to handle the client event
            while self.running:
                for ssh_port_id in self._ssh_port_id_list:
                    rc = self._process_server_socket_event(ssh_port_id)
                    if rc != RcCode.SUCCESS:
                        self.running = False
                    self._clean_client(ssh_port_id)
        except OSError:
            self._logger.error("Socket error occurs.")


class _SshServerSubSystemWorker(threading.Thread, LoggerSystem):
    def __init__(self, work_id):
        threading.Thread.__init__(self)
        LoggerSystem.__init__(self, "ssh_work_{}".format(work_id))
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
                if server_handler.shutdown:
                    if not server_handler.clear:
                        self._logger.info("server handler {} has stopped.".format(server_handler.handler_id))
                        server_handler.close_client()
                elif server_handler.running and server_handler.complete:
                    rc = server_handler.handler()
                    if rc == RcCode.EXIT_PROCESS:
                        server_handler.shutdown = True
                    elif rc != RcCode.SUCCESS:
                        self._logger.error("server handler {} process event fail".format(server_handler.handler_id))
                        break
            time.sleep(0.01)


class SshServerPassWdAuthSubSystem(SshServerSubsystem):
    def __init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, polling_interval,
                 ssh_server_mgr_dict, thread_stop_event):
        self._ssh_key_handler = SshKeyHandler(server_pri_key_file='~/.ssh/id_rsa')
        self._polling_interval = polling_interval
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        SshServerSubsystem.__init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, thread_stop_event)
        LoggerSystem.__init__(self,"ssh_passwd_auth_subsystem_{}".format(subsystem_id))
        self._worker_list = []
        for work_id in range(8):
            worker = _SshServerSubSystemWorker(work_id)
            worker.start()
            self._worker_list.append(worker)
        self._next_worker_id = 0
        self._handler_num = 0

    def _process_server_socket_event(self, server_port_id):
        # Process the server event
        events = self._server_epoll_dict[server_port_id].poll(timeout=self._polling_interval)
        for file_no, _ in events:
            if self._ssh_subsystem_sock[server_port_id]["socket_fd"] == file_no:
                # A new client wants to connect the sever. Create an SSH server handler for this client
                client_sock = self._ssh_subsystem_sock[server_port_id]["socket"].accept()
                self._logger.warning("A new client arrived. {}".format(client_sock[0].getpeername()))

                # Create the SSH server handler to execute SSH connection
                server_handler = SshServerPassWdAuthHandler(self._handler_num,
                                                            self._ssh_server_mgr_dict,
                                                            client_sock[0],
                                                            self._ssh_key_handler,
                                                            ssh_authenticator_server_class=SshServerPassWdAuthenticator)
                server_handler.start()
                self._handler_num = self._handler_num + 1
                self._logger.warning("A new thread to service the client {}".format(client_sock[0].getpeername()))

                # Save the SSH server handler and wait SSH connection completely
                self._server_handler_dict[server_port_id].append(server_handler)
                continue

        # Process the SSH event
        for server_port_id in self._server_handler_dict:
            server_handler_list = self._server_handler_dict[server_port_id]
            exit_flag = False
            for server_handler in server_handler_list:
                if server_handler.running and server_handler.complete:
                    rc = self._worker_list[self._next_worker_id].add_server_handler(server_handler)
                    if rc != RcCode.SUCCESS:
                        exit_flag = True
                        break
                elif server_handler.shutdown:
                    rc = self._worker_list[self._next_worker_id].delete_server_handler(server_handler)
                    if rc != RcCode.SUCCESS:
                        exit_flag = True
                        break
                    server_handler.close_client()
            if exit_flag:
                break
            
        return RcCode.SUCCESS
        
    def clean_subsystem(self):
        # Close the server socket
        rc = SshServerSubsystem.clean_subsystem(self)
        if rc != RcCode.SUCCESS:
            return rc

        # Close the client socket
        for server_port_id in self._server_handler_dict:
            server_handler_list = self._server_handler_dict[server_port_id]
            for server_handler in server_handler_list:
                server_handler.close_client()
        return RcCode.SUCCESS


class SshServerNoneAuthSubSystem(SshServerSubsystem):
    def __init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, polling_interval,
                 ssh_server_mgr_dict, thread_stop_event):
        self._ssh_key_handler = SshKeyHandler(server_pri_key_file='~/.ssh/id_rsa')
        self._polling_interval = polling_interval
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        SshServerSubsystem.__init__(self, ssh_ip_addr, ssh_port_list, subsystem_id, num_of_client, thread_stop_event)
        LoggerSystem.__init__(self, "ssh_none_auth_subsystem_{}".format(subsystem_id))
        self._handler_num = 0

    def _process_server_socket_event(self, server_port_id):
        # Process the server event
        events = self._server_epoll_dict[server_port_id].poll(timeout=self._polling_interval)
        for file_no, _ in events:
            if self._ssh_subsystem_sock[server_port_id]["socket_fd"] == file_no:
                # A new client wants to connect the sever. Create a SSH server handler for this client
                client_sock = self._ssh_subsystem_sock[server_port_id]["socket"].accept()
                self._logger.info("A new client arrived. {}".format(client_sock[0].getpeername()))

                # Create the SSH server handler to execute SSH connection
                server_handler = SshServerNoneAuthHandler(self._handler_num,
                                                          self._ssh_server_mgr_dict,
                                                          server_port_id,
                                                          client_sock[0],
                                                          self._ssh_key_handler,
                                                          ssh_authenticator_server_class=SshServerNoneAuthenticator)
                server_handler.start()
                self._handler_num = self._handler_num + 1
                self._logger.info("A new thread to service the client {}".format(client_sock[0].getpeername()))

                # Save the SSH server handler and wait SSH connection completely
                self._server_handler_dict[server_port_id].append(server_handler)
                continue

        # Process the SSH event
        for server_port_id in self._server_handler_dict:
            server_handler_list = self._server_handler_dict[server_port_id]
            for server_handler in server_handler_list:
                if server_handler.shutdown:
                    if not server_handler.clear:
                        self._logger.info("server handler {} has stopped.".format(server_handler.handler_id))
                        server_handler.close_client()
                elif server_handler.running and server_handler.complete:
                    rc = server_handler.handler()
                    if rc == RcCode.EXIT_PROCESS:
                        server_handler.shutdown = True
                    elif rc != RcCode.SUCCESS:
                        self._logger.error("server handler {} process event fail".format(server_handler.handler_id))
                        break
        return RcCode.SUCCESS

    def clean_subsystem(self):
        # Close the server socket
        rc = SshServerSubsystem.clean_subsystem(self)
        if rc != RcCode.SUCCESS:
            return rc

        # Close the client socket
        for server_port_id in self._server_handler_dict:
            server_handler_list = self._server_handler_dict[server_port_id]
            for server_handler in server_handler_list:
                server_handler.close_client()
        return RcCode.SUCCESS
