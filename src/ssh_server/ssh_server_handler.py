import logging
import os
import threading
import paramiko

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.server_control.server_control import ServerControlAccessMode, ServerControlMgmtMode, ServerControlSerialAccessMode
from src.server_control.server_control_menu import ServerControlMgmtModeMenu, ServerControlAccessModeMenu, \
    SERVER_CONTROL_MGMT_MODE_MENU_DICT, SERVER_CONTROL_ACCESS_MODE_MENU_DICT


class SshServerHandler(threading.Thread, LoggerSystem):
    def __init__(self, client_sock, ssh_key_handler, channel_timeout=30, ssh_authenticator_server_class=None):
        threading.Thread.__init__(self)
        self._username = os.getlogin()
        self._client_sock = client_sock
        self._key_handler = ssh_key_handler
        self._channel_timeout = channel_timeout
        self._ssh_authenticator_server_class = ssh_authenticator_server_class

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
        self._server = self._ssh_authenticator_server_class(ssh_key_handler=self._key_handler)
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
        self.clear = True

    def handler(self, *args, **kwargs):
        raise NotImplemented

    def run(self):
        self._logger.warning("Create transport...")
        rc = self.create_transporter()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Create transport fail...")
            return

        self._logger.warning("Enable ssh service...")
        rc = self.serve_client()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Enable ssh service fail...")
            self.close_client()
            return

        self._logger.warning("Open SSH channel...")
        rc = self.open_channel()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Open SSH channel fail...")
            self.close_client()
            return

        self.init = False
        self._logger.warning("Wait ssh verification...")
        self._server.thread_event.wait(10)
        if not self._server.thread_event.is_set():
            self._logger.warning("Wait ssh verification fail...")
            self.close_client()
            return

        self._logger.warning("SSH client init DONE !!")
        self.complete = True


class SshServerPassWdAuthHandler(SshServerHandler):
    def __init__(self, ssh_server_mgr_dict, client_sock, ssh_key_handler, channel_timeout=30, ssh_authenticator_server_class=None):
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        SshServerHandler.__init__(self, client_sock, ssh_key_handler, channel_timeout, ssh_authenticator_server_class)
        LoggerSystem.__init__(self, "ssh_passwd_auth_handler")
        self._ssh_user_menu_mode = None
        self._username = os.getlogin()
        self._ssh_menu = None
        self._login = False
        self._server_control_mode = None
    
    def _login_system(self):
        rc, user_info_dict = self._ssh_server_mgr_dict["ssh_server_account_mgr"].get_account_info(self._username)
        if rc != RcCode.SUCCESS:
            return rc

        is_admin = user_info_dict["is_admin"]
        if is_admin:
            self._ssh_menu = ServerControlMgmtModeMenu.SERVER_CONTROL_MGMT_MODE_MENU
            self._channel.send(SERVER_CONTROL_MGMT_MODE_MENU_DICT[self._ssh_menu])
            self._server_control_mode = ServerControlMgmtMode(self._channel)
        else:
            self._ssh_menu = ServerControlAccessModeMenu.SERVER_CONTROL_ACCESS_MODE_MENU
            self._channel.send(SERVER_CONTROL_ACCESS_MODE_MENU_DICT[self._ssh_menu])
            self._server_control_mode = ServerControlAccessMode(self._channel)
        self._server_control_mode.init_control_mode()

        self._logger.warning("New Clinet is login the SSH Password server")
        return RcCode.SUCCESS

    def handler(self, *args, **kwargs):
        if not self._login:
            rc = self._login_system()
            if rc != RcCode.SUCCESS:
                return rc
            self._login = True
        rc = self._server_control_mode.run_system()
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS


class SshServerNoneAuthHandler(SshServerHandler):
    def __init__(self, handler_id, ssh_server_mgr_dict, ssh_server_port, client_sock, ssh_key_handler, channel_timeout=30, ssh_authenticator_server_class=None):
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        self.handler_id = handler_id
        self._ssh_server_port = ssh_server_port
        SshServerHandler.__init__(self, client_sock, ssh_key_handler, channel_timeout, ssh_authenticator_server_class)
        LoggerSystem.__init__(self, "ssh_none_auth_handler-{}".format(handler_id))
        self._username = os.getlogin()
        self._login = False
        self._server_control_mode = None
    
    def _login_system(self):
        serial_port = self._ssh_server_mgr_dict["ssh_server_network_mgr"].get_serial_port_by_ssh_port(self._ssh_server_port)
        self._server_control_mode = ServerControlSerialAccessMode(self.handler_id, self._channel, serial_port)
        rc = self._server_control_mode.init_control_mode()
        if rc != RcCode.SUCCESS:
            self._logger.error("Init the log system and socket fail. rc: {}".format(rc))
            return rc
        self._logger.info("New Clinet is login the SSH No Password server. Open serial port {}. rc: {}".format(serial_port, rc))
        return RcCode.SUCCESS

    def handler(self, *args, **kwargs):
        if not self._login:
            rc = self._login_system()
            if rc != RcCode.SUCCESS:
                self._logger.error("login system fail. rc: {}".format(rc))
                return rc
            self._login = True
        rc = self._server_control_mode.run_system()
        if rc != RcCode.SUCCESS:
            self._logger.error("Run system fail. rc: {}".format(rc))
            return rc
        return RcCode.SUCCESS
