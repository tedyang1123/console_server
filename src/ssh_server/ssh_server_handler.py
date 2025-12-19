import os
import threading
import paramiko

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.server_control.server_control import ServerControlAccessMode, ServerControlMgmtMode, \
    ServerControlSerialAccessMode, ServerControlPortAccessMode
from src.server_control.server_control_menu import ServerControlMenu, SERVER_CONTROL_MENU_DICT


class SshServerSessionHandler(threading.Thread, LoggerSystem):
    def __init__(self, client_sock, ssh_key_handler, channel_timeout=30, ssh_authenticator_server_class=None, logger_name="ssh_server_handler"):
        threading.Thread.__init__(self)
        LoggerSystem.__init__(self, logger_name)
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


class SshServerPassWdAuthSessionHandler(SshServerSessionHandler):
    def __init__(self, handler_id, ssh_server_mgr_dict, client_sock, ssh_key_handler, channel_timeout=30,
                 ssh_authenticator_server_class=None):
        self.handler_id = handler_id
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        SshServerSessionHandler.__init__(self, client_sock, ssh_key_handler, channel_timeout, ssh_authenticator_server_class, "ssh_passwd_auth_handler")
        self._ssh_user_menu_mode = None
        self._username = os.getlogin()
        self._current_menu = None
        self._login = False
        self._server_control_mode = None
        self._is_admin = False
        self._reinit = False
    
    def _login_system(self, reinit=False):
        rc, user_info_dict = self._ssh_server_mgr_dict["ssh_server_account_mgr"].get_account_info(self._username)
        if rc != RcCode.SUCCESS:
            self._logger.error("Can not get the number of the serial port on this system.")
            return rc

        self._is_admin = user_info_dict["is_admin"]
        if self._is_admin:
            if not self._reinit:
                self._current_menu = ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU
            self._logger.warning("Current menu is {}".format(self._current_menu))
            self._channel.send(SERVER_CONTROL_MENU_DICT[self._current_menu])
            if not self._reinit:
                self._server_control_mode = ServerControlMgmtMode(self._channel)
        else:
            if not self._reinit:
                self._current_menu = ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU
            self._channel.send(SERVER_CONTROL_MENU_DICT[self._current_menu])
            if not self._reinit:
                self._server_control_mode = ServerControlAccessMode(self._channel)

        rc = self._server_control_mode.init_control_mode()
        if rc != RcCode.SUCCESS:
            self._logger.info("Init control mode fail")
            return rc

        self._reinit = False

        self._logger.warning("New Clinet is login the SSH Password server")
        return RcCode.SUCCESS

    def handler(self, *args, **kwargs):
        if not self._login:
            rc = self._login_system()
            if rc != RcCode.SUCCESS:
                self._logger.error("login system fail. rc: {}".format(rc))
                return rc
            self._login = True
        rc = self._server_control_mode.run_system()
        if rc == RcCode.CHANGE_MENU:
            if self._current_menu is None:
                self._logger.warning("No next menu available")
                return RcCode.DATA_NOT_FOUND
            # Change the mode
            if self._is_admin:
                match self._server_control_mode.next_menu:
                    case ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU:
                        self._logger.warning("Change to Mgmt mode menu")
                        self._current_menu = self._server_control_mode.next_menu
                        self._server_control_mode = ServerControlMgmtMode(self._channel)
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.warning("Change to Port Access mode menu")
                        num_of_serial_port = self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port()
                        self._current_menu = self._server_control_mode.next_menu
                        self._server_control_mode = ServerControlPortAccessMode(self._channel, num_of_serial_port)
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.warning("Change to Serial Port Access mode menu")
                        self._current_menu = self._server_control_mode.next_menu
                        serial_port_id = self._server_control_mode.serial_port_id
                        self._server_control_mode = ServerControlSerialAccessMode(self.handler_id, self._channel, serial_port_id)
            else:
                match self._server_control_mode.next_menu:
                    case ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU:
                        self._logger.warning("Change to Access mode menu")
                        self._current_menu = self._server_control_mode.next_menu
                        self._server_control_mode = ServerControlAccessMode(self._channel)
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.warning("Change to Port Access mode menu")
                        self._current_menu = self._server_control_mode.next_menu
                        num_of_serial_port = self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port()
                        self._server_control_mode = ServerControlPortAccessMode(self._channel, num_of_serial_port)
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.warning("Change to Serial Port Access mode menu")
                        self._current_menu = self._server_control_mode.next_menu
                        serial_port_id = self._server_control_mode.serial_port_id
                        self._server_control_mode = ServerControlSerialAccessMode(self.handler_id, self._channel, serial_port_id)
            self._reinit = True
            self._login = False
        elif rc == RcCode.EXIT_MENU:
            if self._is_admin:
                match self._current_menu:
                    case ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU:
                        # The top menu
                        self._logger.info("Exit Mgmt mode menu")
                        return RcCode.EXIT_PROCESS
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.info("Exit Port Access mode menu, into the Mgmt mode menu")
                        self._server_control_mode = ServerControlMgmtMode(self._channel)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.info("Exit Serial Port mode menu, into the Port Access mode menu")
                        num_of_serial_port = self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port()
                        self._server_control_mode = ServerControlPortAccessMode(self._channel, num_of_serial_port)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU
            else:
                match self._current_menu:
                    case ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU:
                        # The top menu
                        self._logger.info("Exit Access mode menu")
                        return RcCode.EXIT_PROCESS
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.info("Exit Port Access mode menu, into the Access mode menu")
                        self._server_control_mode = ServerControlAccessMode(self._channel)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.info("Exit Serial Port mode menu, into the Port Access mode menu")
                        num_of_serial_port = self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port()
                        self._server_control_mode = ServerControlPortAccessMode(self._channel, num_of_serial_port)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU
            self._reinit = True
            self._login = False
        return RcCode.SUCCESS


class SshServerNoneAuthSessionHandler(SshServerSessionHandler):
    def __init__(self, handler_id, ssh_server_mgr_dict, ssh_server_port, client_sock, ssh_key_handler,
                 channel_timeout=30, ssh_authenticator_server_class=None):
        self.handler_id = handler_id
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        self._ssh_server_port = ssh_server_port
        SshServerSessionHandler.__init__(self, client_sock, ssh_key_handler, channel_timeout, ssh_authenticator_server_class, "ssh_none_auth_handler-{}".format(handler_id))
        self._username = os.getlogin()
        self._login = False
        self._server_control_mode = None
    
    def _login_system(self):
        serial_port = (
            self._ssh_server_mgr_dict["ssh_server_network_mgr"].get_serial_port_by_ssh_port(self._ssh_server_port))
        self._server_control_mode = ServerControlSerialAccessMode(self.handler_id, self._channel, serial_port)
        rc = self._server_control_mode.init_control_mode()
        if rc != RcCode.SUCCESS:
            self._logger.error("Init the log system and socket fail. rc: {}".format(rc))
            return rc
        self._logger.info("New Clinet is login the SSH No Password server. "
                          "Open serial port {}. rc: {}".format(serial_port, rc))
        return RcCode.SUCCESS

    def handler(self, *args, **kwargs):
        if not self._login:
            rc = self._login_system()
            if rc != RcCode.SUCCESS:
                self._logger.error("login system fail. rc: {}".format(rc))
                return rc
            self._login = True
        rc = self._server_control_mode.run_system()
        if rc == RcCode.EXIT_MENU:
            rc = RcCode.EXIT_PROCESS
        if rc != RcCode.SUCCESS:
            self._logger.error("Run system fail. rc: {}".format(rc))
            return rc
        return RcCode.SUCCESS
