import os
import time

from src.common.msg import SetAliasNameRequest, SetBaudRateRequest, ConnectSerialPortRequest, GetPortConfigRequest, ReplyMsg, RequestMsg
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainClientSocket
from src.console_server.processing.console_server_definition import ConsoleServerEvent
from src.server_control.server_ansi_parser import ConsoleAnsiEscapeParser
from src.server_control.server_control_menu import SERVER_CONTROL_ALIAS_NAME_PROMPT, SERVER_CONTROL_GENERAL_PROMPT, \
    SERVER_CONTROL_ITEM_SELECT_PROMPT, ServerControlAccessModeMenu, ServerControlMgmtModeMenu, ServerControlMenu, \
    server_control_mgmt_mode_menu, server_control_access_mode_menu, server_control_port_access_menu, SERVER_CONTROL_PORT_CONFIG_PROMPT, \
    SERVER_CONTROL_USER_CONFIG_PROMPT, server_control_port_config_menu


class ServerControlMode:
    MAX_BUFFER_SIZE = 1024
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
        self._server_prompt = SERVER_CONTROL_GENERAL_PROMPT

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
                        self._tx_func(self._server_prompt)
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
        self._tx_func(self._server_prompt)
        return RcCode.SUCCESS

    def _send_uds_socket_request_data(self, client_socket_obj, request):
        rc, request_str = request.serialize()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not convert request to string."), rc=rc)
            return rc
        rc = client_socket_obj.uds_client_socket_send(request_str)
        if rc != RcCode.SUCCESS:
            self._logger.warning(self._logger_system.set_logger_rc_code("Can not send the message to server."))
            return rc
        return RcCode.SUCCESS

    def _receive_uds_socket_reply_data(self, client_socket_obj, request_msg):
        # Receive the reply for the message
        rc, data = client_socket_obj.uds_client_socket_recv(4)
        if rc == RcCode.DATA_NOT_READY:
            return RcCode.SUCCESS, None
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not receive the data size.", rc=rc))
            return rc, None
        receive_size = int.from_bytes(data, byteorder='little')

        # Receive the server reply
        data_str = ""
        while receive_size > 0:
            rc, reply_str = client_socket_obj.uds_client_socket_recv(receive_size)
            if rc == RcCode.DATA_NOT_READY:
                continue
            elif rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not send the message to server."))
                return rc, None
            if reply_str == b"":
                self._logger.warning(self._logger_system.set_logger_rc_code("Socket has closed."))
                client_socket_obj.uds_client_socket_close()
                return RcCode.EXIT_MENU, None
            data_str = data_str + reply_str.decode('utf-8')
            receive_size = receive_size - len(data_str)

        # Retrieve the data from request
        reply = ReplyMsg()
        rc = reply.deserialize(data_str)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not convert reply to object"))
            return rc, None

        # Check if request is correct
        if reply.request != request_msg:
            self._logger.error(self._logger_system.set_logger_rc_code("Receive the incorrect reply."))
            return RcCode.INVALID_VALUE, None
        elif reply.result != "OK":
            self._logger.warning(self._logger_system.set_logger_rc_code("Set baud rate failed due to invalid baud rate."))
            return RcCode.FAILURE, None
        return RcCode.SUCCESS, reply.data


class ServerControlMgmtMode(ServerControlMode):
    def __init__(self, trans_func_dict, logger_system):
        ServerControlMode.__init__(self, trans_func_dict, logger_system)
        self._menu_str = server_control_mgmt_mode_menu
        self._prompt_len = len(self._server_prompt)

    def _parser_request_cmd(self):
        process_data = self._input_buffer.rstrip()
        self._logger.info("Process request {}".format(process_data))
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
                    self._tx_func(self._server_prompt)
                    rc = RcCode.SUCCESS
        except ValueError:
            self._logger.warning("Data is not a integer data.")
            self._tx_func(self._clear_screen())
            self._tx_func(self._menu_str)
            self._tx_func(self._server_prompt)
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
        self._prompt_len = len(self._server_prompt)

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
                    self._tx_func(self._server_prompt)
                    rc = RcCode.SUCCESS
        except ValueError:
            self._tx_func(self._clear_screen())
            self._tx_func(self._menu_str)
            self._tx_func(self._server_prompt)
            rc = RcCode.SUCCESS
        self._input_buffer = ""
        return rc

    def run_system(self):
        rc = RcCode.SUCCESS
        if self._rx_ready_func is None or self._rx_ready_func():
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
        self._prompt_len = len(self._server_prompt)
        self.serial_port_id = -1
        self._uds_mgmt_socket = UnixDomainClientSocket(self._logger_system)
        self._server_socket_mgmt_path = "/tmp/server_mgmt.sock"

        self._time_stamp = 0
        self._start_sync = False
        self._send_request = False
        self._receive_data = False
        self._receive_size = 0
        self._data_str = ""
        self._remaining_data = 0

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
                self._tx_func(self._server_prompt)
                rc = RcCode.SUCCESS
        except ValueError:
            self._tx_func(self._clear_screen())
            self._tx_func(self._menu_str)
            self._tx_func(self._server_prompt)
            rc = RcCode.SUCCESS
        self._input_buffer = ""
        return rc

    def init_control_mode(self):
        self._logger.info(
            self._logger_system.set_logger_rc_code("Init control mode for ServerControlSerialAccessMode"))
        rc = self._uds_mgmt_socket.uds_client_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Init socket fail."), rc=rc)
            return rc
        rc = self._uds_mgmt_socket.uds_client_socket_connect(self._server_socket_mgmt_path)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Connect the console server fail.", rc=rc))
            return rc
        self._tx_func(self._clear_screen())
        return super().init_control_mode()

    def _update_menu(self):
        rc = self._send_uds_socket_request_data(self._uds_mgmt_socket, GetPortConfigRequest())
        if rc != RcCode.SUCCESS:
            return rc

        # Receive the server reply
        rc, port_config_dict = self._receive_uds_socket_reply_data(self._uds_mgmt_socket, ConsoleServerEvent.GET_PORT_STATUS)
        if rc != RcCode.SUCCESS:
            return rc

        # Create the menu string
        menu_format_str = ""
        for i in range(1, int(self._num_of_serial_port_id / 2) + 1):
            first_part = str(i)
            second_part = str(int(i + self._num_of_serial_port_id / 2))
            menu_format_str = \
                menu_format_str + ("{:<2}. {:<5}                               |"
                                   "   {:<2}. {:<5}                           \r\n").format(
                    first_part, port_config_dict[first_part]['alias_name'], second_part,
                    port_config_dict[second_part]['alias_name'],
                )
        self._menu_str = server_control_port_access_menu.format(menu_format_str)

        self._tx_func(self._clear_screen())
        self._tx_func(self._menu_str)
        self._tx_func(self._server_prompt)
        self._logger.info(
            self._logger_system.set_logger_rc_code("Beauty the output completely."))
        return RcCode.SUCCESS

    def run_system(self):
        if self._time_stamp == 0 or (time.time() - self._time_stamp) > 10:
            self._start_sync = True
            self._time_stamp = time.time()

        if self._start_sync:
            self._logger.info(
                self._logger_system.set_logger_rc_code("Sync port config"))
            # Send the request to the server
            rc = self._update_menu()
            if rc != RcCode.SUCCESS:
                self._start_sync = False
                return rc
            self._start_sync = False

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

        self._server_socket_file_path = "/tmp/server_handler_{}.sock"

        self._uds_client_socket = UnixDomainClientSocket(self._logger_system)
        self._port_access_flow_complete = False
        self._send_request_complete = False
    
    def init_control_mode(self):
        self._logger.info(
            self._logger_system.set_logger_rc_code("Init control mode for ServerControlSerialAccessMode"))
        rc = self._uds_client_socket.uds_client_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Init socket fail."), rc=rc)
            return rc

        group_id = (self._serial_port_id - 1) % 8
        rc = self._uds_client_socket.uds_client_socket_connect(self._server_socket_file_path.format(group_id))
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Connect the console server fail.", rc=rc))
            return rc
        self._tx_func(self._clear_screen())
        return RcCode.SUCCESS

    def _handle_ssh_server_data(self):
        if self._rx_ready_func is None or self._rx_ready_func():
            self._logger.info("Start to read ssh channel")
            read_str = self._rx_func(1024)
            self._logger.info(self._logger_system.set_logger_rc_code("Read the data: {}".format(read_str)))
            for ascii_val in read_str:
                if ascii_val == 0x14:
                    self._logger.info("Receive the exit signal, close the socket.")
                    rc = self._uds_client_socket.uds_client_socket_close()
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("Can not close the client socket"), rc=rc)
                    return RcCode.EXIT_MENU
            self._logger.info("Get the data from the ssh server {}".format(bytes.hex(read_str)))
            rc = self._uds_client_socket.uds_client_socket_send(read_str)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not write the message to console.".format(
                        self._server_socket_file_path), rc=rc))
                return RcCode.FAILURE
        return RcCode.SUCCESS

    def _handle_console_server_data(self):
        rc, data = self._uds_client_socket.uds_client_socket_recv(self.MAX_BUFFER_SIZE)
        if rc == RcCode.SUCCESS:
            if data != "":
                try:
                    self._tx_func(data)
                except UnicodeDecodeError:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code("Can not decode the data", rc=rc))
                    self._tx_func('.')
        return RcCode.SUCCESS

    def _connect_serial_port(self):
        rc = self._send_uds_socket_request_data(
            self._uds_client_socket, 
            ConnectSerialPortRequest(self._serial_port_id, os.getlogin()))
        if rc != RcCode.SUCCESS:
            return rc

        rc, _  = self._receive_uds_socket_reply_data(self._uds_client_socket, ConsoleServerEvent.CONNECT_SERIAL_PORT)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS

    def run_system(self):
        # Start port process
        if not self._port_access_flow_complete:
            rc = self._uds_client_socket.uds_client_socket_set_blocking(True)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not set port to blocking", rc=rc))
                return rc
            rc = self._connect_serial_port()
            if rc != RcCode.SUCCESS:
                return rc
            self._port_access_flow_complete = True
            rc = self._uds_client_socket.uds_client_socket_set_blocking(False)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not set port to blocking", rc=rc))
                return rc
            return RcCode.SUCCESS

        # Event processes
        rc = self._handle_ssh_server_data()
        if rc == RcCode.EXIT_MENU:
            self._logger.info(self._logger_system.set_logger_rc_code("Receive stop event"))
            rc = self._uds_client_socket.uds_client_socket_close()
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not close the socket", rc=rc))
            return RcCode.EXIT_MENU
        elif rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Process SSH data fail. rc: {}".format(rc)))
            return rc

        rc = self._handle_console_server_data()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Process Console data fail. rc: {}".format(rc)))
            return rc
        return RcCode.SUCCESS


class ServerControlPortConfigMode(ServerControlMode):
    CONFIG_SELECT_ITEM = 0
    CONFIG_STEP_INPUT_PORT_ID = 1
    CONFIG_STEP_INPUT_DATA = 2

    def __init__(self, trans_func_dict, num_of_serial_port_id, logger_system):
        self._num_of_serial_port_id = num_of_serial_port_id
        ServerControlMode.__init__(self, trans_func_dict, logger_system)
        self._menu_str = server_control_port_config_menu
        self._config_step = self.CONFIG_SELECT_ITEM
        self._server_prompt = SERVER_CONTROL_ITEM_SELECT_PROMPT
        self._select_item_id = -1
        self._serial_port_id = -1
        self._uds_serial_port_socket = UnixDomainClientSocket(self._logger_system)
        self._server_socket_serial_port_path = "/tmp/server_{}.sock"
        self._uds_mgmt_socket = UnixDomainClientSocket(self._logger_system)
        self._server_socket_mgmt_path = "/tmp/server_mgmt.sock"

        self._time_stamp = 0
        self._start_sync = False
        self._send_request = False
        self._receive_data = False
        self._receive_size = 0
        self._data_str = ""
        self._remaining_data = 0

    def _refresh_screen_menu(self):
        self._tx_func(self._clear_screen())
        self._tx_func(self._menu_str)
        self._tx_func(self._server_prompt)
        self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU

    def init_control_mode(self):
        self._logger.info(
            self._logger_system.set_logger_rc_code("Init control mode for ServerControlSerialAccessMode"))
        rc = self._uds_mgmt_socket.uds_client_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Init socket fail."), rc=rc)
            return rc
        rc = self._uds_mgmt_socket.uds_client_socket_connect(self._server_socket_mgmt_path)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Connect the console server fail.", rc=rc))
            return rc
        return super().init_control_mode()

    def _parser_request_cmd(self):
        process_data = self._input_buffer.rstrip()
        if self._config_step == self.CONFIG_SELECT_ITEM:
            if process_data in ["a", "A"] or process_data in ["b", "b"]:
                self._select_item_id = process_data
                self._server_prompt = SERVER_CONTROL_PORT_CONFIG_PROMPT
                self._logger.info("Get the valid select item ID {}.".format(self._select_item_id))
                self._config_step = self.CONFIG_STEP_INPUT_PORT_ID
                self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU
                self._tx_func("\r\n")
                self._tx_func(self._server_prompt)
                rc = RcCode.SUCCESS
            else:
                self._logger.info("Get the invalid select item ID {}.".format(self._select_item_id))
                self._refresh_screen_menu()
                rc = RcCode.CHANGE_MENU
        elif self._config_step == self.CONFIG_STEP_INPUT_PORT_ID:
            try:
                serial_port_id = int(process_data)
                if 1 <= serial_port_id <= self._num_of_serial_port_id:
                    self._serial_port_id = serial_port_id
                    if self._select_item_id in ["a", "A"]:
                        self._server_prompt = SERVER_CONTROL_ALIAS_NAME_PROMPT
                    else:
                        self._server_prompt = SERVER_CONTROL_USER_CONFIG_PROMPT
                    self._logger.info("Get the valid port ID {}.".format(serial_port_id))
                    self._config_step = self.CONFIG_STEP_INPUT_DATA
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU
                    self._tx_func("\r\n")
                    self._tx_func(self._server_prompt)
                    rc = RcCode.SUCCESS
                else:
                    self._logger.info("Get the invalid port ID {}.".format(serial_port_id))
                    self._refresh_screen_menu()
                    rc = RcCode.CHANGE_MENU
            except ValueError:
                self._logger.info("Not a integer {}.".format(process_data))
                self._refresh_screen_menu()
                rc = RcCode.CHANGE_MENU
        else:
            if self._select_item_id in ["a", "A"]:
                self._logger.info("Get valid alisa name {}".format(process_data))
                rc = self._send_uds_socket_request_data(
                    self._uds_mgmt_socket, SetAliasNameRequest(self._serial_port_id, process_data))
                if rc != RcCode.SUCCESS:
                    self._refresh_screen_menu()
                    self._config_step = self.CONFIG_SELECT_ITEM
                    self._server_prompt = SERVER_CONTROL_ITEM_SELECT_PROMPT
                    self._serial_port_id = -1
                    self._baud_rate = -1
                    return rc

                rc, _ = self._receive_uds_socket_reply_data(self._uds_mgmt_socket, ConsoleServerEvent.SET_ALIAS_NAME)
                if rc != RcCode.SUCCESS:
                    self._refresh_screen_menu()
                    self._config_step = self.CONFIG_SELECT_ITEM
                    self._server_prompt = SERVER_CONTROL_ITEM_SELECT_PROMPT
                    self._serial_port_id = -1
                    self._baud_rate = -1
                    return rc
            else:
                try:
                    baud_rate = int(process_data)
                    rc = self._send_uds_socket_request_data(
                        self._uds_mgmt_socket, SetBaudRateRequest(self._serial_port_id, baud_rate))
                    if rc != RcCode.SUCCESS:
                        self._refresh_screen_menu()
                        self._config_step = self.CONFIG_SELECT_ITEM
                        self._server_prompt = SERVER_CONTROL_ITEM_SELECT_PROMPT
                        self._serial_port_id = -1
                        self._baud_rate = -1
                        self._logger.info("Send the request failed..")
                        return rc

                    rc, reply = self._receive_uds_socket_reply_data(self._uds_mgmt_socket, ConsoleServerEvent.SET_BAUD_RATE)
                    if rc != RcCode.SUCCESS:
                        self._logger.info("Receive the request failed..")
                        self._config_step = self.CONFIG_SELECT_ITEM
                        self._server_prompt = SERVER_CONTROL_ITEM_SELECT_PROMPT
                        self._serial_port_id = -1
                        self._baud_rate = -1
                        self._refresh_screen_menu()
                except ValueError:
                    self._logger.warning("Not a integer {}.".format(process_data))
                    self._refresh_screen_menu()

            rc = RcCode.CHANGE_MENU
        self._input_buffer = ""
        return rc

    def _update_menu(self):
        rc = self._send_uds_socket_request_data(self._uds_mgmt_socket, GetPortConfigRequest())
        if rc != RcCode.SUCCESS:
            return rc

        # Receive the server reply
        rc, port_config_dict = self._receive_uds_socket_reply_data(self._uds_mgmt_socket, ConsoleServerEvent.GET_PORT_STATUS)
        if rc != RcCode.SUCCESS:
            return rc

        # Create the menu string
        menu_format_str = ""
        for i in range(1, int(self._num_of_serial_port_id / 2) + 1):
            first_part = str(i)
            second_part = str(int(i + self._num_of_serial_port_id / 2))
            menu_format_str = \
                menu_format_str + ("{:<2}. {:<5}               - {:<10d}    |"
                                   "   {:<2}. {:<5}               - {:<10d}\r\n").format(
                    first_part, port_config_dict[first_part]['alias_name'], port_config_dict[first_part]['baud_rate'],
                    second_part, port_config_dict[second_part]['alias_name'], port_config_dict[second_part]['baud_rate'],
                )
        self._menu_str = server_control_port_access_menu.format(menu_format_str)

        self._tx_func(self._clear_screen())
        self._tx_func(self._menu_str)
        if self._config_step == self.CONFIG_SELECT_ITEM:
            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT + self._input_buffer)
        elif self._config_step == self.CONFIG_STEP_INPUT_PORT_ID:
            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT + str(self._select_item_id) + "\r\n")
            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT + self._input_buffer)
        else:
            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT + str(self._select_item_id) + "\r\n")
            self._tx_func(SERVER_CONTROL_PORT_CONFIG_PROMPT + str(self._serial_port_id) + "\r\n")
            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT + self._input_buffer)
        self._logger.info(
            self._logger_system.set_logger_rc_code("Beauty the output completely."))
        return RcCode.SUCCESS

    def run_system(self):
        if self._time_stamp == 0 or (time.time() - self._time_stamp) > 10:
            self._start_sync = True
            self._time_stamp = time.time()

        if self._start_sync:
            self._logger.info(
                self._logger_system.set_logger_rc_code("Sync port config"))
            rc = self._update_menu()
            if rc != RcCode.SUCCESS:
                self._start_sync = False
                return rc
            self._start_sync = False

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
                        rc = self._uds_mgmt_socket.uds_client_socket_close()
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code("Can not close the management socket.", rc=rc))
                        return RcCode.EXIT_MENU
                    if rc == RcCode.DATA_NOT_FOUND:
                        rc = self._parser_request_cmd()
                        if rc == RcCode.CHANGE_MENU:
                            if self.next_menu != ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU:
                                rc = self._uds_mgmt_socket.uds_client_socket_close()
                                if rc != RcCode.SUCCESS:
                                    self._logger.error(
                                        self._logger_system.set_logger_rc_code(
                                            "Can not close the management socket.", rc=rc))
                            return RcCode.CHANGE_MENU
                if rc != RcCode.SUCCESS:
                    rc = self._save_user_input(ascii_val)
        return rc
