import os

from src.common.rc_code import RcCode
from src.server_control.server_control import ServerControlMgmtMode, ServerControlAccessMode, \
    ServerControlPortAccessMode, ServerControlSerialAccessMode, ServerControlPortConfigMode
from src.server_control.server_control_menu import ServerControlMenu, SERVER_CONTROL_MENU_DICT


class ServerControlHandlerMenuMode:
    def __init__(self, logger_system, ssh_server_mgr_dict, trans_func_dict):
        self._logger_system = logger_system
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        self._trans_func_dict = trans_func_dict
        self._tx_func = self._trans_func_dict["tx_func"]
        self._rx_func = self._trans_func_dict["rx_func"]
        self._rx_ready_func = self._trans_func_dict["rx_ready_func"]
        self._logger = self._logger_system.get_logger()

        self._is_admin = False

        self._username = os.getlogin()

        self._server_control_mode = None
        self._current_menu = None

        self._login = False
        self._reinit = False

    def _login_system(self, reinit=False):
        rc, user_info_dict = self._ssh_server_mgr_dict["ssh_server_account_mgr"].get_account_info(self._username)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the number of the serial port on this system."))
            return rc

        self._is_admin = user_info_dict["is_admin"]
        if self._is_admin:
            if not self._reinit:
                self._current_menu = ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU
            self._tx_func(SERVER_CONTROL_MENU_DICT[self._current_menu])
            if not self._reinit:
                self._server_control_mode = ServerControlMgmtMode(self._trans_func_dict, self._logger_system)
        else:
            if not self._reinit:
                self._current_menu = ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU
            self._tx_func(SERVER_CONTROL_MENU_DICT[self._current_menu])
            if not self._reinit:
                self._server_control_mode = ServerControlAccessMode(self._trans_func_dict, self._logger_system)

        rc = self._server_control_mode.init_control_mode()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Init control mode fail"))
            return rc

        self._reinit = False

        self._logger.info(self._logger_system.set_logger_rc_code("New client is login the SSH menu {}".format(self._current_menu)))
        return RcCode.SUCCESS

    def handler(self, *args, **kwargs):
        if not self._login:
            self._logger.info(self._logger_system.set_logger_rc_code("Start to login server to control menu."))
            rc = self._login_system()
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("login system fail. rc: {}".format(rc)))
                return rc
            self._logger.info(self._logger_system.set_logger_rc_code("login server to control menu completely."))
            self._login = True

        rc = self._server_control_mode.run_system()
        if rc == RcCode.CHANGE_MENU:
            self._logger.info(self._logger_system.set_logger_rc_code("Receive the change menu signal."))
            if self._current_menu is None:
                self._logger.warning(self._logger_system.set_logger_rc_code("No next menu available"))
                return RcCode.DATA_NOT_FOUND
            # Change the mode
            if self._is_admin:
                match self._server_control_mode.next_menu:
                    case ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU:
                        self._logger.warning(self._logger_system.set_logger_rc_code("Change to Mgmt mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        self._server_control_mode = ServerControlMgmtMode(self._trans_func_dict, self._logger_system)
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.warning(self._logger_system.set_logger_rc_code("Change to Port Access mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlPortAccessMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.warning(self._logger_system.set_logger_rc_code(
                            "Change to Serial Port Access mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        serial_port_id = self._server_control_mode.serial_port_id
                        self._server_control_mode = ServerControlSerialAccessMode(
                            self._trans_func_dict, serial_port_id, self._logger_system)
                    case ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU:
                        self._logger.warning(self._logger_system.set_logger_rc_code(
                            "Change to Serial Port config mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlPortConfigMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
            else:
                self._logger.info(self._logger_system.set_logger_rc_code("Receive the exit menu signal."))
                match self._server_control_mode.next_menu:
                    case ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU:
                        self._logger.warning(self._logger_system.set_logger_rc_code("Change to Access mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlAccessMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.warning(
                            self._logger_system.set_logger_rc_code("Change to Port Access mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlPortAccessMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.warning(
                            self._logger_system.set_logger_rc_code("Change to Serial Port Access mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        serial_port_id = self._server_control_mode.serial_port_id
                        self._server_control_mode = (
                            ServerControlSerialAccessMode(self._trans_func_dict, serial_port_id, self._logger_system))
                    case ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU:
                        self._logger.warning(self._logger_system.set_logger_rc_code(
                            "Change to Serial Port config mode menu"))
                        self._current_menu = self._server_control_mode.next_menu
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlPortConfigMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
            self._reinit = True
            self._login = False
        elif rc == RcCode.EXIT_MENU:
            if self._is_admin:
                match self._current_menu:
                    case ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU:
                        # The top menu
                        self._logger.info(self._logger_system.set_logger_rc_code("Exit Mgmt mode menu"))
                        return RcCode.EXIT_PROCESS
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Exit Port Access mode menu, into the Mgmt mode menu"))
                        self._server_control_mode = ServerControlMgmtMode(self._trans_func_dict, self._logger_system)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Exit Serial Port mode menu, into the Port Access mode menu"))
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlPortAccessMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU
                    case ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Exit Serial Port mode menu, into the Port config mode menu"))
                        self._server_control_mode = ServerControlMgmtMode(
                            self._trans_func_dict, self._logger_system)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU
            else:
                match self._current_menu:
                    case ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU:
                        # The top menu
                        self._logger.info(self._logger_system.set_logger_rc_code("Exit Access mode menu"))
                        return RcCode.EXIT_PROCESS
                    case ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Exit Port Access mode menu, into the Access mode menu"))
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlAccessMode(self._trans_func_dict, self._logger_system)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU
                    case ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Exit Serial Port mode menu, into the Port Access mode menu"))
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlPortAccessMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU
                    case ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Exit Serial Port mode menu, into the Port config mode menu"))
                        num_of_serial_port = (
                            self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"].get_num_of_serial_port())
                        self._server_control_mode = ServerControlAccessMode(
                            self._trans_func_dict, num_of_serial_port, self._logger_system)
                        self._current_menu = ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU
            self._reinit = True
            self._login = False
        return RcCode.SUCCESS

class ServerControlHandlerDirectAccessMode:
    def __init__(self, logger_system, ssh_server_mgr_dict, server_port, trans_func_dict):
        self._logger_system = logger_system
        self._ssh_server_mgr_dict = ssh_server_mgr_dict
        self._server_port = server_port
        self._trans_func_dict = trans_func_dict
        self._logger = self._logger_system.get_logger()

        self._server_control_mode = None
        self._current_menu = None

        self._login = False

    def _login_system(self):
        serial_port = (
            self._ssh_server_mgr_dict["ssh_server_network_mgr"].get_serial_port_by_ssh_port(self._server_port))
        self._server_control_mode = ServerControlSerialAccessMode(
            self._ssh_server_mgr_dict, serial_port, self._logger_system)
        rc = self._server_control_mode.init_control_mode()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Init the log system and socket fail.", rc=rc))
            return rc
        self._logger.info(
            self._logger_system.set_logger_rc_code(
                "New Clinet is login the SSH No Password server. Open serial port {}.", rc=rc))
        return RcCode.SUCCESS

    def handler(self, *args, **kwargs):
        if not self._login:
            rc = self._login_system()
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("login system fail.", rc=rc))
                return rc
            self._login = True
        rc = self._server_control_mode.run_system()
        if rc == RcCode.EXIT_MENU:
            rc = RcCode.EXIT_PROCESS
            return rc
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Run system fail.", rc=rc))
            return rc
        return RcCode.SUCCESS