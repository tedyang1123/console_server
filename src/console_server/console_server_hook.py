import time

from src.common.rc_code import RcCode
from src.console_server.console_server_definition import SSH_TERMINAL_MODE, COM_PORT_MODE
from src.console_server.console_server_serial import ConsoleServerSerialSystem
from src.console_server.console_server_setup import ConsoleServerSetupSystem
from src.console_server.console_server_util import ConsoleServerMenu
from src.ssh_server.ssh_server import SshServerHandler


MAX_SERIAL_PORT = 10


class ConsoleServerHook(SshServerHandler):
    def __init__(self, client_sock, ssh_key_handler, channel_timeout=30, ssh_server_class=None, log_handler=None):
        super().__init__(client_sock, ssh_key_handler, channel_timeout, ssh_server_class)
        self._console_server_menu = ConsoleServerMenu()
        self._ssh_read_data = ""
        self._ssh_pending_data = ""
        self._serial_port_id = 0
        self._enable_escape_key = False
        self._console_serve_mode = SSH_TERMINAL_MODE
        self._setup_system = None
        self._serial_system = None

    def _ssh_peer_monitor(self):
        if self._setup_system is None:
            self._setup_system = ConsoleServerSetupSystem(self._channel, self._logger, self._console_server_menu)
        return self._setup_system.run_system()

    def _console_port_monitor(self):
        if self._serial_system is None:
            self._serial_system = ConsoleServerSerialSystem(self._channel, self._logger)
        return self._serial_system.run_system()

    def handler(self, *args, **kwargs):
        while self.running:
            if self._console_serve_mode == COM_PORT_MODE:
                rc = self._console_port_monitor()
                if rc == RcCode.OPEN_TERMINAL:
                    self._console_serve_mode = SSH_TERMINAL_MODE
                if rc != RcCode.SUCCESS:
                    self._logger.warning("Console mode: SSH handler process fail rc = {}".format(rc))
                    self.running = False
            else:
                rc = self._ssh_peer_monitor()
                if rc == RcCode.OPEN_SERIAL:
                    self._console_serve_mode = COM_PORT_MODE
                elif rc != RcCode.SUCCESS and rc != RcCode.OPEN_SERIAL:
                    self._logger.warning("SSH mode: SSH handler process fail rc = {}".format(rc))
                    self.running = False
