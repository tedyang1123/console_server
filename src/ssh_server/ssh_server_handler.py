import os
import threading
import paramiko

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.server_control.server_control_handler import ServerControlHandlerMenuMode, ServerControlHandlerDirectAccessMode


class SshServerSessionHandler(threading.Thread):
    def __init__(self, handler_id, client_sock, ssh_key_handler, channel_timeout=30, ssh_authenticator_server_class=None):
        self._handler_id = handler_id
        self._username = os.getlogin()
        self._client_sock = client_sock
        self._key_handler = ssh_key_handler
        self._channel_timeout = channel_timeout
        self._ssh_authenticator_server_class = ssh_authenticator_server_class

        threading.Thread.__init__(self)
        self.name = "SshServerSessionHandler_{}".format(self._handler_id)

        self._logger_system = LoggerSystem(self.name)
        self._logger = self._logger_system.get_logger()

        self._transporter = None
        self._server = None
        self._channel = None
        self.init = True
        self.started = False
        self.running = False
        self.complete = False
        self.shutdown = False
        self.clear = False

    def create_transporter(self):
        if self.started:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("SSH server does not start."))
            return RcCode.FAILURE
        try:
            self._transporter = paramiko.Transport(self._client_sock)
            self._transporter.load_server_moduli()
            self._transporter.add_server_key(self._key_handler.get_server_private_key())
        except Exception:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Can not create SSH transport."))
            return RcCode.FAILURE
        self.started = True
        return RcCode.SUCCESS

    def serve_client(self):
        if not self.started:
            self._logger.warning(self._logger_system.set_logger_rc_code("SSH server does not start."))
            return RcCode.FAILURE
        self._server = self._ssh_authenticator_server_class(self._key_handler, self._logger_system)
        try:
            self._transporter.start_server(server=self._server)
        except paramiko.SSHException:
            self._logger.warning(self._logger_system.set_logger_rc_code("Can not enable SSH serve."))
            return RcCode.FAILURE
        except Exception:
            self._logger.warning(self._logger_system.set_logger_rc_code("Internal error."))
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
        self.clear = True

    def handler(self, *args, **kwargs):
        raise NotImplementedError

    def run(self):
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return

        self._logger.info(self._logger_system.set_logger_rc_code("Create transport..."))
        rc = self.create_transporter()
        if rc != RcCode.SUCCESS:
            self._logger.warning(self._logger_system.set_logger_rc_code("Create transport fail..."))
            return

        self._logger.info(self._logger_system.set_logger_rc_code("Enable ssh service..."))
        rc = self.serve_client()
        if rc != RcCode.SUCCESS:
            self._logger.warning(self._logger_system.set_logger_rc_code("Enable ssh service fail..."))
            self.close_client()
            return

        self._logger.info(self._logger_system.set_logger_rc_code("Open SSH channel..."))
        rc = self.open_channel()
        if rc != RcCode.SUCCESS:
            self._logger.warning(self._logger_system.set_logger_rc_code("Open SSH channel fail..."))
            self.close_client()
            return

        self.init = False
        self._logger.info(self._logger_system.set_logger_rc_code("Wait ssh verification..."))
        self._server.thread_event.wait(10)
        if not self._server.thread_event.is_set():
            self._logger.warning(self._logger_system.set_logger_rc_code("Wait ssh verification fail..."))
            self.close_client()
            return

        self._logger.info(self._logger_system.set_logger_rc_code("SSH client init DONE !!"))
        self.complete = True


class SshServerPassWdAuthSessionHandler(SshServerSessionHandler):
    def __init__(self, handler_id, ssh_server_mgr_dict, client_sock, ssh_key_handler, channel_timeout=30,
                 ssh_authenticator_server_class=None):
        self.handler_id = handler_id
        self._ssh_server_mgr_dict = ssh_server_mgr_dict

        SshServerSessionHandler.__init__(
            self, handler_id, client_sock, ssh_key_handler, channel_timeout, ssh_authenticator_server_class)
        self.name = "SshServerPassWdAuthSessionHandler_{}".format(self.handler_id)

        self._logger_system = LoggerSystem(self.name)
        self._logger = self._logger_system.get_logger()

        self.in_queue = False
        self._server_control_intf = None

    def run(self):
        super().run()
        self._server_control_intf = ServerControlHandlerMenuMode(
            self._logger_system,
            self._ssh_server_mgr_dict,
            {
                "tx_func": self._channel.send,
                "rx_func": self._channel.recv,
                "rx_ready_func": self._channel.recv_ready
            })

    def handler(self, *args, **kwargs):
        return self._server_control_intf.handler()


class SshServerNoneAuthSessionHandler(SshServerSessionHandler):
    def __init__(self, handler_id, ssh_server_mgr_dict, ssh_server_port, client_sock, ssh_key_handler,
                 channel_timeout=30, ssh_authenticator_server_class=None):
        self.handler_id = handler_id
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        self._ssh_server_port = ssh_server_port

        SshServerSessionHandler.__init__(
            self, handler_id, client_sock, ssh_key_handler, channel_timeout, ssh_authenticator_server_class)
        self.name = "SshServerNoneAuthSessionHandler_{}".format(handler_id)

        self._logger_system = LoggerSystem(self.name)
        self._logger = self._logger_system.get_logger()

        self._server_control_intf = None

    def run(self):
        super().run()
        self._server_control_intf = ServerControlHandlerDirectAccessMode(
            self._logger_system,
            self._ssh_server_mgr_dict,
            self._ssh_server_port,
            {
                "tx_func": self._channel.send,
                "rx_func": self._channel.recv,
                "rx_ready_func": self._channel.recv_ready,
            })

    def handler(self, *args, **kwargs):
        return self._server_control_intf.handler()