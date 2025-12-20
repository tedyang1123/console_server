from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainClientSocket
from src.server_control.server_ansi_parser import ConsoleAnsiEscapeParser
from src.server_control.server_control_menu import SERVER_CONTROL_PROMPT, ServerControlAccessModeMenu, \
    ServerControlMgmtModeMenu, ServerControlMenu, server_control_mgmt_mode_menu, server_control_access_mode_menu, \
    server_control_port_access_menu


class ServerControlMode:
    def __init__(self, trans_func_dict, logger_system):
        self._trans_func_dict = trans_func_dict
        self._tx_func = self._trans_func_dict["tx_func"]
        self._rx_func = self._trans_func_dict["rx_func"]
        self._rx_ready_func = self._trans_func_dict["rx_ready_func"]
        self._logger_system = logger_system

        self._logger = self._logger_system.get_logger()
        self._input_buffer = ""
        self._input_pending_buffer = ""
        self._enable_escape_key = False
        self._ansi_escape_parser = ConsoleAnsiEscapeParser()
        self._menu_str = ""
        self.next_menu = None

    def _clear_screen(self):
        return chr(27) + "[2J" + chr(27) + "[3J" + chr(27) + "[1;1H"

    def _clear_line(self):
        return chr(27) + "[1K"

    def _move_cursor_back(self, times):
        return chr(27) + "[{}D".format(times)

    def _parse_escape_ascii_value(self, ascii_val):
        if ascii_val == 0x1b:
            # ESC
            self._enable_escape_key = True
            rc = RcCode.SUCCESS
        else:
            # ESC, read remaining char
            self._ssh_pending_data = self._input_pending_buffer + chr(ascii_val)
            result, self._ssh_pending_data = self._ansi_escape_parser.data_parse(self._ssh_pending_data)
            if result == RcCode.DATA_NOT_FOUND or result == result.SUCCESS:
                self._enable_escape_key = False
                self._ssh_pending_data = ""
            rc = RcCode.SUCCESS
        return rc

    def _parse_system_control_ascii_value(self, ascii_val):
        rc = RcCode.FAILURE
        match ascii_val:
            case 0x0a | 0x0d:
                # Read newline
                process_data = self._input_buffer.rstrip()
                match process_data:
                    case 'Q' | 'q':
                        self._tx_func('\r\n')
                        self._input_buffer = ''
                        rc = RcCode.EXIT_MENU
                    case "":
                        self._tx_func(self._clear_screen())
                        self._tx_func(self._menu_str)
                        self._tx_func(SERVER_CONTROL_PROMPT)
                        self._input_buffer = ''
                        rc = RcCode.SUCCESS
                    case _:
                        rc = RcCode.DATA_NOT_FOUND
            case 0x08 | 0x7F:
                # Read backspace
                if self._input_buffer != "":
                    self._input_buffer = self._input_buffer[:-1]
                    self._tx_func("\b \b")
                rc = RcCode.SUCCESS
        return rc

    def _save_user_input(self, ascii_val):
        self._input_buffer = self._input_buffer + chr(ascii_val)
        self._tx_func(chr(ascii_val))
        return RcCode.SUCCESS

    def init_control_mode(self):
        self._tx_func(self._clear_screen())
        self._tx_func(self._menu_str)
        self._tx_func(SERVER_CONTROL_PROMPT)
        return RcCode.SUCCESS


class ServerControlMgmtMode(ServerControlMode):
    def __init__(self, trans_func_dict, logger_system):
        ServerControlMode.__init__(self, trans_func_dict, logger_system)
        self._menu_str = server_control_mgmt_mode_menu
        self._prompt_len = len(SERVER_CONTROL_PROMPT)

    def _parser_request_cmd(self):
        process_data = self._input_buffer.rstrip()
        self._logger.warning("Process request {}".format(process_data))
        try:
            # If data is an integer, check if value is in the range.
            # If value is in the mode range,
            # 1. Set the next mode.
            # 2. Return CHANGE_MODE to notify the handler to change the mode
            input_id = int(process_data, 10)
            match input_id:
                case ServerControlMgmtModeMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU
                    rc = RcCode.CHANGE_MENU
                case ServerControlMgmtModeMenu.SERVER_CONTROL_PORT_CONFIG_MENU:
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU
                    rc = RcCode.CHANGE_MENU
                case ServerControlMgmtModeMenu.SERVER_CONTROL_USER_MGMT_MENU:
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_USER_MGMT_MENU
                    rc = RcCode.CHANGE_MENU
                case ServerControlMgmtModeMenu.SERVER_CONTROL_NET_MGMT_MENU:
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_NET_MGMT_MENU
                    rc = RcCode.CHANGE_MENU
                case ServerControlMgmtModeMenu.SERVER_CONTROL_SYSTEM_MGMT_MENU:
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_SYSTEM_MGMT_MENU
                    rc = RcCode.CHANGE_MENU
                case _:
                    self._tx_func(self._clear_screen())
                    self._tx_func(self._menu_str)
                    self._tx_func(SERVER_CONTROL_PROMPT)
                    rc = RcCode.SUCCESS
        except ValueError:
            self._logger.warning("Data is not a integer data.")
            self._tx_func(self._clear_screen())
            self._tx_func(self._menu_str)
            self._tx_func(SERVER_CONTROL_PROMPT)
            rc = RcCode.SUCCESS
        self._input_buffer = ""
        return rc

    def run_system(self):
        if self._rx_ready_func():
            read_str = self._rx_func(5)
            for ascii_val in read_str:
                rc = RcCode.FAILURE
                if ascii_val == 0x1b or self._enable_escape_key:
                    rc = self._parse_escape_ascii_value(ascii_val)
                if rc != RcCode.SUCCESS:
                    rc = self._parse_system_control_ascii_value(ascii_val)
                    if rc == RcCode.EXIT_MENU:
                        return rc
                    if rc == RcCode.DATA_NOT_FOUND:
                        rc = self._parser_request_cmd()
                        if rc == RcCode.CHANGE_MENU:
                            return rc
                if rc != RcCode.SUCCESS:
                    _ = self._save_user_input(ascii_val)
        return RcCode.SUCCESS


class ServerControlAccessMode(ServerControlMode):
    def __init__(self, trans_func_dict, logger_system):
        ServerControlMode.__init__(self, trans_func_dict, logger_system)
        self._menu_str = server_control_access_mode_menu
        self._prompt_len = len(SERVER_CONTROL_PROMPT)

    def _parser_request_cmd(self):
        process_data = self._input_buffer.rstrip()
        try:
            # If data is an integer, check if value is in the range.
            # If value is in the mode range,
            # 1. Set the next mode.
            # 2. Return CHANGE_MODE to notify the handler to change the mode
            input_id = int(process_data, 10)
            match input_id:
                case ServerControlAccessModeMenu.SERVER_CONTROL_PORT_ACCESS_MENU:
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU
                    rc = RcCode.CHANGE_MENU
                case _:
                    self._tx_func(self._clear_screen())
                    self._tx_func(self._menu_str)
                    self._tx_func(SERVER_CONTROL_PROMPT)
                    rc = RcCode.SUCCESS
        except ValueError:
            self._tx_func(self._clear_screen())
            self._tx_func(self._menu_str)
            self._tx_func(SERVER_CONTROL_PROMPT)
            rc = RcCode.SUCCESS
        self._input_buffer = ""
        return rc

    def run_system(self):
        rc = RcCode.SUCCESS
        if (self._rx_ready_func is None or
                self._rx_ready_func()):
            read_str = self._rx_func(5)
            for ascii_val in read_str:
                rc = RcCode.FAILURE
                if ascii_val == 0x1b or self._enable_escape_key:
                    rc = self._parse_escape_ascii_value(ascii_val)
                if rc != RcCode.SUCCESS:
                    rc = self._parse_system_control_ascii_value(ascii_val)
                    if rc == RcCode.EXIT_MENU:
                        return rc
                    if rc == RcCode.DATA_NOT_FOUND:
                        rc = self._parser_request_cmd()
                        if rc == RcCode.CHANGE_MENU:
                            return rc
                if rc != RcCode.SUCCESS:
                    rc = self._save_user_input(ascii_val)
        return rc


class ServerControlPortAccessMode(ServerControlMode):
    def __init__(self, trans_func_dict, num_of_serial_port_id, logger_system):
        self._trans_func_dict = trans_func_dict
        self._num_of_serial_port_id = num_of_serial_port_id
        ServerControlMode.__init__(self, trans_func_dict, logger_system)

        self._menu_str = server_control_port_access_menu
        self._prompt_len = len(SERVER_CONTROL_PROMPT)
        self.serial_port_id = -1

    def _parser_request_cmd(self):
        process_data = self._input_buffer.rstrip()
        try:
            serial_port_id = int(process_data)
            if 1 <= serial_port_id <= self._num_of_serial_port_id:
                self._logger.info("Valid serial port id.")
                self.next_menu = ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU
                self.serial_port_id = serial_port_id
                rc = RcCode.CHANGE_MENU
            else:
                self._tx_func(self._clear_screen())
                self._tx_func(self._menu_str)
                self._tx_func(SERVER_CONTROL_PROMPT)
                rc = RcCode.SUCCESS
        except ValueError:
            self._tx_func(self._clear_screen())
            self._tx_func(self._menu_str)
            self._tx_func(SERVER_CONTROL_PROMPT)
            rc = RcCode.SUCCESS
        self._input_buffer = ""
        return rc

    def run_system(self):
        rc = RcCode.SUCCESS
        if (self._rx_ready_func is None or
            self._rx_ready_func()):
            read_str = self._rx_func(5)
            for ascii_val in read_str:
                rc = RcCode.FAILURE
                if ascii_val == 0x1b or self._enable_escape_key:
                    rc = self._parse_escape_ascii_value(ascii_val)
                if rc != RcCode.SUCCESS:
                    rc = self._parse_system_control_ascii_value(ascii_val)
                    if rc == RcCode.EXIT_MENU:
                        return rc
                    if rc == RcCode.DATA_NOT_FOUND:
                        rc = self._parser_request_cmd()
                        if rc == RcCode.CHANGE_MENU:
                            return rc
                if rc != RcCode.SUCCESS:
                    rc = self._save_user_input(ascii_val)
        return rc


class ServerControlSerialAccessMode(ServerControlMode):
    def __init__(self, trans_func_dict, serial_port_id, logger_system):
        self._trans_func_dict = trans_func_dict
        self._serial_port_id = serial_port_id
        ServerControlMode.__init__(self, trans_func_dict, logger_system)

        self._server_socket_group_id = ((self._serial_port_id - 1) % 8) + 1
        self._server_socket_file_path = "/tmp/server_{}.sock".format(self._server_socket_group_id)

        self._uds_client_socket = UnixDomainClientSocket(self._logger_system)
        self._port_access_flow_complete = False
        self._stop_port_process_flag = False
        
        # Negotiation with console server
        self._send_connect_request = False
        self._send_disconnect_request = False
        self._send_request_complete = False
        self._send_port_id_complete = False
    
    def init_control_mode(self):
        self._logger.info(
            self._logger_system.set_logger_rc_code("Init control mode for ServerControlSerialAccessMode"))
        rc = self._uds_client_socket.uds_client_socket_init(non_blocking=True)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Init socket fail."), rc=rc)
            return rc
        rc = self._uds_client_socket.uds_client_socket_connect(self._server_socket_file_path)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Connect the console server fail.", rc=rc))
            return rc
        self._tx_func(self._clear_screen())
        return RcCode.SUCCESS

    def _handle_ssh_server_data(self):
        if (self._rx_ready_func is None or
                self._rx_ready_func()):
            read_str = self._rx_func(5)
            self._logger.info(self._logger_system.set_logger_rc_code("Read the data: {}".format(read_str)))
            for ascii_val in read_str:
                if ascii_val == 0x14:
                    self._logger.info("Receive the exit signal, close the socket.")
                    rc = self._uds_client_socket.uds_client_socket_close()
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("Can not close the client socket"), rc=rc)
                    return RcCode.EXIT_MENU
            self._logger.info("Get the data from the ssh server")
            rc = self._uds_client_socket.uds_client_socket_send(read_str)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not write the message to console.".format(
                        self._server_socket_file_path), rc=rc))
                return RcCode.FAILURE
        return RcCode.SUCCESS

    def _handle_console_server_data(self):
        rc, data = self._uds_client_socket.uds_client_socket_recv(1024)
        if rc == RcCode.SUCCESS:
            if data != "":
                self._logger.info(self._logger_system.set_logger_rc_code("Read the data: {}".format(data)))
                try:
                    self._tx_func(data)
                except UnicodeDecodeError:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code("Can not decode the data rc: {}".format(rc)))
                    self._tx_func('.')
        return RcCode.SUCCESS

    def run_system(self):
        # Start port process
        if not self._port_access_flow_complete:
            if not self._send_request_complete :
                rc = self._uds_client_socket.uds_client_socket_send("connect-{}".format(self._serial_port_id))
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not write the data to the console server side".format(rc)))
                    return rc
                self._send_request_complete = True
            else:
                rc, data = self._uds_client_socket.uds_client_socket_recv(1024)
                if rc == RcCode.DATA_NOT_READY:
                    return RcCode.SUCCESS
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not read the data from the console server side", rc=rc))
                    return rc
                if rc == RcCode.SUCCESS and data == "":
                    return RcCode.EXIT_MENU
                elif data == "OK":
                    self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "Read OK from socket".format(data)))
                    self._port_access_flow_complete = True
                else:
                    self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "Receive unrecognized data {}".format(data)))
            return RcCode.SUCCESS
        
        # Event processes
        rc = self._handle_ssh_server_data()
        if rc == RcCode.EXIT_MENU:
            self._logger.warning(self._logger_system.set_logger_rc_code("Receive stop event"))
            return RcCode.EXIT_MENU
        elif rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Process SSH data fail. rc: {}".format(rc)))
            return rc

        rc = self._handle_console_server_data()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Process Console data fail. rc: {}".format(rc)))
            return rc
        return RcCode.SUCCESS
