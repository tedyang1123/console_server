import logging
import threading
import paramiko

from src.common.rc_code import RcCode


class SshServerHandler(threading.Thread):
    def __init__(self, client_sock, ssh_key_handler, channel_timeout=30, ssh_server_class=None):
        threading.Thread.__init__(self)
        self._client_sock = client_sock
        self._key_handler = ssh_key_handler
        self._channel_timeout = channel_timeout
        self._ssh_server_class = ssh_server_class

        self._transporter = None
        self._server = None
        self._channel = None
        self.init = True
        self.running = False
        self.started = False

        host, port = client_sock.getpeername()

        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._logger = logging.getLogger(__name__)
        self._screen_handler = logging.StreamHandler()
        self._screen_handler.setLevel(logging.WARNING)
        self._screen_handler.setFormatter(self._formatter)

        self._file_handler = logging.FileHandler('/var/log/ssh-server-{}:{}.log'.format(host, port))
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(self._formatter)

        self._logger.setLevel(logging.DEBUG)

        self._logger.addHandler(self._screen_handler)
        self._logger.addHandler(self._file_handler)
        self._logger.propagate = False

    def create_transporter(self):
        if self.started:
            self._logger.warning("SSH server does not start.")
            return RcCode.FAILURE
        try:
            self._transporter = paramiko.Transport(self._client_sock)
            self._transporter.load_server_moduli()
            self._transporter.add_server_key(self._key_handler.get_server_private_key())
        except Exception:
            self._logger.warning("Can not create SSH transport.")
            return RcCode.FAILURE
        self.started = True
        return RcCode.SUCCESS

    def serve_client(self):
        if not self.started:
            self._logger.warning("SSH server does not start.")
            return RcCode.FAILURE
        self._server = self._ssh_server_class(ssh_key_handler=self._key_handler)
        try:
            self._transporter.start_server(server=self._server)
        except paramiko.SSHException:
            self._logger.warning("Can not enable SSH serve.")
            return RcCode.FAILURE
        except Exception:
            self._logger.warning("Internal error.")
            return RcCode.FAILURE, None
        return RcCode.SUCCESS

    def open_channel(self):
        self._channel = self._transporter.accept(self._channel_timeout)
        if self._channel is None:
            return RcCode.FAILURE
        self.running = True
        return RcCode.SUCCESS

    def close_client(self):
        if self._channel is not None:
            self._channel.close()
        if self._transporter is not None:
            self._transporter.close()
        self._client_sock.close()

    def handler(self, *args, **kwargs):
        pass

    def run(self):
        self._logger.info("Create transport...")
        rc = self.create_transporter()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Create transport fail...")
            return

        self._logger.info("Enable ssh service...")
        rc = self.serve_client()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Enable ssh service fail...")
            self.close_client()
            return

        self._logger.info("Open SSH channel...")
        rc = self.open_channel()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Open SSH channel fail...")
            self.close_client()
            return

        self.init = False
        self._logger.info("Wait ssh verification...")
        self._server.thread_event.wait(10)
        if not self._server.thread_event.is_set():
            self._logger.warning("Wait ssh verification fail...")
            self.close_client()
            return
        self._logger.info("SSH client init DONE !!")

        self._logger.info("Start access the SSH message.")
        self.handler()
        self.close_client()
        self._logger.info("SSH client closed.")
