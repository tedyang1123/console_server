import json
import time

from src.common.msg import ReplyMsg, RequestMsg, msg_deserialize, msg_serialize
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainClientSocket
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


class ServerControlMgmtMode(ServerControlMode):
    def __init__(self, trans_func_dict, logger_system):
        ServerControlMode.__init__(self, trans_func_dict, logger_system)
        self._menu_str = server_control_mgmt_mode_menu
        self._prompt_len = len(self._server_prompt)

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
        rc = self._uds_mgmt_socket.uds_client_socket_init(non_blocking=False)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Init socket fail."), rc=rc)
            return rc
        rc = self._uds_mgmt_socket.uds_client_socket_connect(self._server_socket_mgmt_path)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Connect the console server fail.", rc=rc))
            return rc
        self._tx_func(self._clear_screen())
        return super().init_control_mode()

    def run_system(self):
        if self._time_stamp == 0 or (time.time() - self._time_stamp) > 10:
            self._time_stamp = time.time()

        if self._start_sync:
            request = RequestMsg("get_port_config")
            rc, request_dict = request.get_msg()
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not create dictionary to store the request."), rc=rc)
                return rc
            rc, request_str = msg_serialize(request_dict)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not serialize the request."), rc=rc)
                return rc
            rc = self._uds_mgmt_socket.uds_client_socket_send(request_str)
            if rc != RcCode.SUCCESS:
                self._logger.warning(self._logger_system.set_logger_rc_code("Can not send the message to server."))
                return rc
            
            rc, reply_str = self._uds_mgmt_socket.uds_client_socket_recv(self.MAX_BUFFER_SIZE)
            if rc == RcCode.DATA_NOT_READY:
                return RcCode.SUCCESS
            elif rc != RcCode.SUCCESS:
                self._logger.warning(self._logger_system.set_logger_rc_code("Can not send the message to server."))
                return rc
            
            if reply_str == "":
                self._uds_mgmt_socket.uds_client_socket_close()
                return RcCode.EXIT_MENU
            rc, reply_dict = msg_deserialize(reply_str)
            if rc != RcCode.SUCCESS:
                self._logger.warning(self._logger_system.set_logger_rc_code("Can not deserialize the message."))
                return rc
            reply = ReplyMsg()
            rc = reply.set_msg(reply_dict)
            if rc != RcCode.SUCCESS:
                self._logger.warning(self._logger_system.set_logger_rc_code("Invalid message."))
                return rc
            if reply.request != "get_port_config":
                return RcCode.SUCCESS
            elif reply.result != "OK":
                self._logger.warning(self._logger_system.set_logger_rc_code(reply.data))
                return rc
            
            rc, data = self._uds_mgmt_socket.uds_client_socket_recv(4)
            if rc == RcCode.DATA_NOT_READY:
                return RcCode.SUCCESS
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not receive the data size.", rc=rc))
                return rc
            self._receive_size = int.from_bytes(data.encode('utf-8'), byteorder='little')
            self._logger.info(
                self._logger_system.set_logger_rc_code("Receive data length for port config completely."))
            self._receive_data = True
            


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

        self._server_socket_file_path = "server_mgmt.sock"

        self._uds_client_socket = UnixDomainClientSocket(self._logger_system)
        self._port_access_flow_complete = False
        self._send_request_conplete = False
    
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
            if not self._send_request_conplete:
                request = RequestMsg("connect_serial_port", self._serial_port_id)
                rc, request_str = msg_serialize(request)
                if rc != RcCode.SUCCESS:
                    self._logger.warning(self._logger_system.set_logger_rc_code("Can not serialize the message."))
                    return rc
                rc = self._uds_client_socket.uds_client_socket_send(request_str)
                if rc != RcCode.SUCCESS:
                    self._logger.warning(self._logger_system.set_logger_rc_code("Can not send the message to server."))
                    return rc
                self._send_request_conplete = True
            else:
                rc, reply_str = self._uds_client_socket.uds_client_socket_recv(self.MAX_BUFFER_SIZE)
                if rc == RcCode.DATA_NOT_READY:
                    return RcCode.SUCCESS
                elif rc != RcCode.SUCCESS:
                    self._logger.warning(self._logger_system.set_logger_rc_code("Can not send the message to server."))
                    return rc
                
                if reply_str == "":
                    self._uds_client_socket.uds_client_socket_close()
                    return RcCode.EXIT_MENU
                rc, reply_dict = msg_deserialize(reply_str)
                if rc != RcCode.SUCCESS:
                    self._logger.warning(self._logger_system.set_logger_rc_code("Can not deserialize the message."))
                    return rc
                reply = ReplyMsg()
                rc = reply.set_msg(reply_dict)
                if rc != RcCode.SUCCESS:
                    self._logger.warning(self._logger_system.set_logger_rc_code("Invalid message."))
                    return rc
                if reply.result != "OK":
                    self._logger.warning(self._logger_system.set_logger_rc_code(reply.data))
                    return rc
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
        self._baud_rate = -1
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

    def init_control_mode(self):
        self._logger.info(
            self._logger_system.set_logger_rc_code("Init control mode for ServerControlSerialAccessMode"))
        rc = self._uds_mgmt_socket.uds_client_socket_init(non_blocking=False)
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
                self._tx_func(self._clear_screen())
                self._tx_func(self._menu_str)
                self._tx_func(self._server_prompt)
                self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU
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
                    self._tx_func(self._clear_screen())
                    self._tx_func(self._menu_str)
                    self._tx_func(self._server_prompt)
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU
                    rc = RcCode.CHANGE_MENU
            except ValueError:
                self._logger.info("Not a integer {}.".format(process_data))
                self._tx_func(self._clear_screen())
                self._tx_func(self._menu_str)
                self._tx_func(self._server_prompt)
                self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU
                rc = RcCode.CHANGE_MENU
        else:
            if self._select_item_id in ["a", "A"]:
                self._logger.info("Get valid alisa name {}".format(process_data))
                self._server_socket_serial_port_path = self._server_socket_serial_port_path.format(self._serial_port_id)
                rc = self._uds_serial_port_socket.uds_client_socket_init()
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Init socket fail."), rc=rc)
                    return rc
                rc = self._uds_serial_port_socket.uds_client_socket_connect(self._server_socket_serial_port_path)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Connect the console server fail.", rc=rc))
                    return rc
                rc = self._uds_serial_port_socket.uds_client_socket_send("alias-{}-{}".format(self._serial_port_id, process_data))
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not write the data to the console server side.", rc=rc))
                    return rc
                rc, data = self._uds_serial_port_socket.uds_client_socket_recv(self.MAX_BUFFER_SIZE)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not receive the data from the console server side.", rc=rc))
                    return rc
                if data != "OK":
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not set the baud rate to the alisa name.", rc=rc))
            else:
                try:
                    baud_rate = int(process_data)
                    self._logger.info("Get valid baud rate {}".format(baud_rate))
                    self._server_socket_serial_port_path = self._server_socket_serial_port_path.format(self._serial_port_id)
                    rc = self._uds_serial_port_socket.uds_client_socket_init()
                    if rc != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Init socket fail."), rc=rc)
                        return rc
                    rc = self._uds_serial_port_socket.uds_client_socket_connect(self._server_socket_serial_port_path)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("Connect the console server fail.", rc=rc))
                        return rc
                    rc = self._uds_serial_port_socket.uds_client_socket_send(
                        "baudrate-{}-{}".format(self._serial_port_id, baud_rate))
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not write the data to the console server side.", rc=rc))
                        return rc
                    rc, data = self._uds_serial_port_socket.uds_client_socket_recv(self.MAX_BUFFER_SIZE)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not receive the data from the console server side.", rc=rc))
                        return rc
                    if data != "OK":
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not set the baud rate to the serial.", rc=rc))
                except ValueError:
                    self._logger.info("Not a integer {}.".format(process_data))
                    self._tx_func(self._clear_screen())
                    self._tx_func(self._menu_str)
                    self._tx_func(self._server_prompt)
                    self.next_menu = ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU

            self._config_step = self.CONFIG_STEP_INPUT_PORT_ID
            self._server_prompt = SERVER_CONTROL_ITEM_SELECT_PROMPT
            self._serial_port_id = -1
            self._baud_rate = -1
            rc = RcCode.CHANGE_MENU
        self._input_buffer = ""
        return rc

    def run_system(self):
        if self._time_stamp == 0 or (time.time() - self._time_stamp) > 10:
            self._start_sync = True
            self._send_request = True
            self._receive_data = False
            self._receive_size = 0
            self._data_str = ""
            self._remaining_data = 0
            self._time_stamp = time.time()

        if self._start_sync:
            if self._send_request:
                rc = self._uds_mgmt_socket.uds_client_socket_send("port_config")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not get the current port config.", rc=rc))
                    return rc

                self._logger.info(self._logger_system.set_logger_rc_code("Send request for port config completely."))
                self._send_request = False
            else:
                if not self._receive_data:
                    rc, data = self._uds_mgmt_socket.uds_client_socket_recv(4)
                    if rc == RcCode.DATA_NOT_READY:
                        return RcCode.SUCCESS
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("Can not receive the data size.", rc=rc))
                        return rc
                    self._receive_size = int.from_bytes(data.encode('utf-8'), byteorder='little')
                    self._logger.info(
                        self._logger_system.set_logger_rc_code("Receive data length for port config completely."))
                    self._receive_data = True
                else:
                    rc, data = self._uds_mgmt_socket.uds_client_socket_recv(self._receive_size)
                    if rc == RcCode.DATA_NOT_READY:
                        return RcCode.SUCCESS
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("Can not receive the data.", rc=rc))
                        return rc
                    self._data_str = self._data_str + data
                    remaining_data = self._remaining_data - len(data)

                    if remaining_data <= 0:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code("Receive data for port config completely."))
                        port_config_dict = json.loads(self._data_str)
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Convert the data from JSON string to dict. {}").format(port_config_dict))
                        menu_format_str = ""
                        for i in range(1, int(self._num_of_serial_port_id / 2) + 1):
                            first_part = str(i)
                            second_part = str(int(i + self._num_of_serial_port_id / 2))
                            menu_format_str =\
                                menu_format_str + ("{:<2}. {:<5}               - {:<10d}    |"
                                                   "   {:<2}. {:<5}               - {:<10d}\r\n").format(
                                    first_part, port_config_dict[first_part]['alias'], port_config_dict[first_part]['baud_rate'],
                                    second_part, port_config_dict[second_part]['alias'], port_config_dict[second_part]['baud_rate'],
                                )
                        self._menu_str = server_control_port_config_menu.format(menu_format_str)

                        self._tx_func(self._clear_screen())
                        self._tx_func(self._menu_str)
                        if self._config_step == self.CONFIG_SELECT_ITEM:
                            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT)
                        elif self._config_step == self.CONFIG_STEP_INPUT_PORT_ID:
                            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT + str(self._select_item_id) + "\r\n")
                            self._tx_func(SERVER_CONTROL_PORT_CONFIG_PROMPT)
                        else:
                            self._tx_func(SERVER_CONTROL_ITEM_SELECT_PROMPT + str(self._select_item_id) + "\r\n")
                            self._tx_func(SERVER_CONTROL_PORT_CONFIG_PROMPT + str(self._serial_port_id) + "\r\n")
                            self._tx_func(SERVER_CONTROL_USER_CONFIG_PROMPT)
                        self._logger.info(
                            self._logger_system.set_logger_rc_code("Beauty the output completely."))

                        self._start_sync = False
                return RcCode.SUCCESS

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
