import errno
import logging
import os
import socket

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.server_control.server_ansi_parser import ConsoleAnsiEscapeParser
from src.server_control.server_control_menu import SERVER_CONTROL_PROMPT, SERVER_CONTROL_ACCESS_MODE_MENU_DICT, \
    ServerControlAccessModeMenu, ServerControlMgmtModeMenu, SERVER_CONTROL_MGMT_MODE_MENU_DICT


class ServerControlMode(LoggerSystem):
    def __init__(self, channel):
        self._channel = channel
        self._input_buffer = ""
        self._input_pending_buffer = ""
        self._logger = logging.getLogger(__name__)
        self._enable_escape_key = False
        self._ansi_escape_parser = ConsoleAnsiEscapeParser(self._channel)
        self._menu_str = ""

    def _clear_screen(self):
        return chr(27) + "[2J" + chr(27) + "[3J" + chr(27) + "[1;1H"

    def _clear_line(self):
        return chr(27) + "[1K"

    def _move_cursor_back(self, times):
        return chr(27) + "[{}D".format(times)

    def _init_logger_system(self):
        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
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
        self._logger.warning("Get the data - {}.".format(ascii_val))
        match ascii_val:
            case 0x0a | 0x0d:
                # Read newline
                process_data = self._input_buffer.rstrip()
                match process_data:
                    case 'Q' | 'q':
                        self._channel.send('\r\n')
                        rc = RcCode.EXIT_PROCESS
                    case "":
                        self._channel.send(self._clear_screen())
                        self._channel.send(self._menu_str)
                        self._channel.send(SERVER_CONTROL_PROMPT)

                        rc = RcCode.SUCCESS
                    case _:
                        rc = RcCode.DATA_NOT_FOUND
                self._input_buffer = ''
            case 0x08:
                # Read backspace
                if self._input_buffer != "":
                    self._input_buffer = self._input_buffer[:-1]
                    self._channel.send("\b \b")
                rc = RcCode.SUCCESS
        return rc

    def _save_user_input(self, ascii_val):
        self._input_buffer = self._input_buffer + chr(ascii_val)
        self._channel.send(chr(ascii_val))
        return RcCode.SUCCESS

    def init_control_mode(self):
        self._channel.send(self._clear_screen())
        self._channel.send(self._menu_str)
        self._channel.send(SERVER_CONTROL_PROMPT)


class ServerControlMgmtMode(ServerControlMode):
    def __init__(self, channel):
        super().__init__(channel)
        LoggerSystem.__init__(self, "ssh_none_auth_handler")
        self._server_mode_menu = ServerControlMgmtModeMenu.SERVER_CONTROL_MGMT_MODE_MENU
        self._menu_str = SERVER_CONTROL_MGMT_MODE_MENU_DICT[self._server_mode_menu]
        self._prompt_len = len(SERVER_CONTROL_PROMPT)

    def _parser_request_cmd(self):
        rc = RcCode.FAILURE
        process_data = self._input_buffer.rstrip()

        # TBD: Implement the request execute detail
        match process_data:
            case _:
                self._channel.send(self._clear_screen())
                self._channel.send(self._menu_str)
                self._channel.send(SERVER_CONTROL_PROMPT)
                rc = RcCode.SUCCESS
        return rc

    def run_system(self):
        if self._channel.recv_ready():
            read_str = self._channel.recv(5)
            for ascii_val in read_str:
                rc = RcCode.FAILURE
                if ascii_val == 0x1b or self._enable_escape_key:
                    rc = self._parse_escape_ascii_value(ascii_val)
                if rc != RcCode.SUCCESS:
                    rc = self._parse_system_control_ascii_value(ascii_val)
                    if rc == RcCode.EXIT_PROCESS or rc == RcCode.OPEN_SERIAL_PORT:
                        return rc
                if rc == RcCode.DATA_NOT_FOUND:
                    rc = self._parser_request_cmd()
                if rc != RcCode.SUCCESS:
                    _ = self._save_user_input(ascii_val)
        return RcCode.SUCCESS


class ServerControlAccessMode(ServerControlMode):
    def __init__(self, channel):
        super().__init__(channel)
        LoggerSystem.__init__(self, "ssh_none_auth_handler")
        self._server_mode_menu = ServerControlAccessModeMenu.SERVER_CONTROL_ACCESS_MODE_MENU
        self._menu_str = SERVER_CONTROL_ACCESS_MODE_MENU_DICT[self._server_mode_menu]
        self._prompt_len = len(SERVER_CONTROL_PROMPT)

    def _parser_request_cmd(self):
        rc = RcCode.FAILURE
        process_data = self._input_buffer.rstrip()

        # TBD: Implement the request execute detail
        match process_data:
            case _:
                self._channel.send(self._clear_screen())
                self._channel.send(self._menu_str)
                self._channel.send(SERVER_CONTROL_PROMPT)
                rc = RcCode.SUCCESS
        return rc

    def run_system(self):
        rc = RcCode.SUCCESS
        if self._channel.recv_ready():
            read_str = self._channel.recv(5)
            for ascii_val in read_str:
                rc = RcCode.FAILURE
                if ascii_val == 0x1b or self._enable_escape_key:
                    rc = self._parse_escape_ascii_value(ascii_val)
                if rc != RcCode.SUCCESS:
                    rc = self._parse_system_control_ascii_value(ascii_val)
                    if rc == RcCode.EXIT_PROCESS or rc == RcCode.OPEN_SERIAL_PORT:
                        return rc
                if rc != RcCode.SUCCESS:
                    rc = self._save_user_input(ascii_val)
        return rc


class ServerControlSerialAccessMode(ServerControlMode):
    def __init__(self, subsystem_id, channel, serial_port_id):
        ServerControlMode.__init__(self, channel)
        LoggerSystem.__init__(self, "ssh_none_auth_handler-{}".format(subsystem_id))
        self._channel = channel
        self._serial_port_id = serial_port_id
        self._server_socket_group_id = (self._serial_port_id % 8) + 1
        self._server_scok_file_path = "/tmp/server_{}.sock".format(self._server_socket_group_id)
        self._client_sock = None

    def _uds_socket_init(self):
        try:
            self._client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._client_sock.setblocking(False)
        except OSError as e:
            self._logger.warning(e)
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _uds_socket_connect(self):
        try:
            self._client_sock.connect(self._server_scok_file_path)
        except OSError as e:
            self._logger.warning(e)
        return RcCode.SUCCESS

    def _uds_socket_send(self, data):
        try:
            self._client_sock.sendall(data)
        except OSError as e:
            self._logger.warning(e)
        return RcCode.SUCCESS

    def _uds_socket_recv(self, max_size):
        wait = True
        data = ""
        while wait:
            try:
                data = self._client_sock.recv(max_size)
                wait = False
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    return RcCode.SUCCESS, ""
                return RcCode.FAILURE, None
        return RcCode.SUCCESS, str(data, encoding="utf-8")

    def _uds_socket_close(self):
        try:
            self._client_sock.close()
        except OSError:
            pass
        return RcCode.SUCCESS
    
    def init_control_mode(self):
        rc = self.init_logger_system()
        if rc != RcCode.SUCCESS:
            self._logger.error("Init logger system, fail. rc: {}".format(rc))
            return rc
        rc = self._uds_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error("Init socket, fail. rc: {}".format(rc))
            return rc
        rc = self._uds_socket_connect()
        if rc != RcCode.SUCCESS:
            self._logger.error("Connect the console server {} fail. rc: {}".format(rc))
            return rc
        self._channel.send(self._clear_screen())
        return RcCode.SUCCESS

    def _handle_ssh_server_data(self):
        if self._channel.recv_ready():
            read_str = self._channel.recv(5)
            self._logger.warning("Read the data: {}".format(read_str))
            for ascii_val in read_str:
                if ascii_val == 0x14:
                    rc = self._uds_socket_close()
                    if rc != RcCode.SUCCESS:
                        self._logger.error("Can not close the socket. rc: {}".format(rc))
                        return rc
                    return RcCode.EXIT_PROCESS
            rc = self._uds_socket_send(read_str)
            if rc != RcCode.SUCCESS:
                self._logger.error("Can not write the message to console rc: {}".format(self._server_scok_file_path, rc))
                return RcCode.FAILURE
        return RcCode.SUCCESS

    def _handle_console_server_data(self):
        rc, data = self._uds_socket_recv(1024)
        if rc == RcCode.SUCCESS:
            try:
                self._channel.send(data)
            except UnicodeDecodeError:
                self._logger.warning("Can not decode the data rc: {}".format(rc))
                self._channel.send('.')
        else:
            self._logger.warning("Can not receive the data. rc: {}".format(rc))
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def run_system(self):
        rc = self._handle_ssh_server_data()
        if rc != RcCode.SUCCESS:
            self._logger.error("Process SSH data fail. rc: {}".format(rc))
            return rc

        rc = self._handle_console_server_data()
        if rc != RcCode.SUCCESS:
            self._logger.error("Process Console data fail. rc: {}".format(rc))
            return rc
        return RcCode.SUCCESS
