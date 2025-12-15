#!/usr/bin/env python3
import select
import socket
import sys
import threading
import logging

from src.common.rc_code import RcCode
from src.ssh_server.ssh_server_authenticator import SshAuthenticator
from src.ssh_server.ssh_server_handler import SshServerHandler


class SshServerDaemon(threading.Thread):
    def __init__(self, ssh_ip_addr="127.0.0.1", ssh_server_port=2222, num_of_client=100,
                 poll_interval=1, server_handler=SshServerHandler, ssh_key_handler=None):
        threading.Thread.__init__(self)
        self._ssh_ip_addr = ssh_ip_addr
        self._ssh_server_port = ssh_server_port
        self._num_of_client = num_of_client
        self._poll_interval = poll_interval

        self._key_handler = ssh_key_handler
        self._server_handler = server_handler

        self._server_handlers = []

        self._server_sock = None
        self._epoll = None

        self._running = False

        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._logger = logging.getLogger(__name__)
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

    def __del__(self):
        self._clean_client(force=True)
        if self._server_sock is not None:
            self._server_sock = None

    def _init_server(self):
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((self._ssh_ip_addr, self._ssh_server_port))
        except OSError:
            self._logger.warning("can not init server socket.")
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _start_server(self):
        try:
            self._server_sock.listen(self._num_of_client)
        except OSError:
            self._logger.warning("Can not listen server socket.")
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _clean_client(self, max_client=5, force=False):
        self._next_client_idx = 0
        num_exist_client = len(self._server_handlers)
        if num_exist_client == 0:
            return
        for i in range(max_client):
            client_handler = self._server_handlers[(i + self._next_client_idx) % num_exist_client]
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
                self._server_handlers.remove(client_handler)
                del client_handler
                break
            self._next_client_idx = self._next_client_idx + 1

    def run(self):
        self._init_server()
        self._start_server()
        self._running = True
        self._logger.info("SSH server is running.........")
        try:
            self._epoll = select.epoll()
            self._epoll.register(self._server_sock.fileno(), select.EPOLLIN)
            self._epoll.register(sys.stdin.fileno(), select.EPOLLIN)
            while self._running:
                events = self._epoll.poll(timeout=self._poll_interval)
                for file_no, event in events:
                    if file_no == self._server_sock.fileno():
                        client_sock = self._server_sock.accept()
                        self._logger.info("A new client arrived. {}".format(client_sock[0].getpeername()))
                        server_handler = self._server_handler(client_sock[0], self._key_handler,
                                                              ssh_server_class=SshAuthenticator)
                        server_handler.start()
                        self._logger.info("A new thread to service the client {}".format(client_sock[0].getpeername()))
                        self._server_handlers.append(server_handler)
                    elif file_no == sys.stdin.fileno():
                        pass
                self._clean_client()
            self._server_sock.close()
        except OSError:
            self._logger.warning("Socket error occurs.")
