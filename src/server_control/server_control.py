import logging
import ansiparser

from src.common.rc_code import RcCode
from src.server_control.server_ansi_parser import ConsoleAnsiEscapeParser
from src.server_control.server_control_menu import SERVER_CONTROL_PROMPT, SERVER_CONTROL_ACCESS_MODE_MENU_DICT, \
    ServerControlAccessModeMenu, ServerControlMgmtModeMenu, SERVER_CONTROL_MGMT_MODE_MENU_DICT


class ServerControlMode:
    def __init__(self, channel):
        self._channel = channel
        self._input_buffer = ""
        self._input_pending_buffer = ""
        self._ansi_screen_parser = ansiparser.new_screen()
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

    def _parser_ascii_esc_value(self, ascii_val):
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

    def _parser_request_cmd(self):
        raise NotImplementedError()

    def _parser_ascii_value(self, ascii_val):
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
                        self._channel.send(self._clear_screen())
                        self._channel.send(self._menu_str)
                        self._channel.send(SERVER_CONTROL_PROMPT)

                        rc = self._parser_request_cmd()
                        if rc != RcCode.SUCCESS:
                            return rc
                        rc = RcCode.SUCCESS
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

    def init_screen(self):
        self._channel.send(self._clear_screen())
        self._channel.send(self._menu_str)
        self._channel.send(SERVER_CONTROL_PROMPT)


class ServerControlMgmtMode(ServerControlMode):
    def __init__(self, channel):
        super().__init__(channel)
        self._server_mode_menu = ServerControlMgmtModeMenu.SERVER_CONTROL_MGMT_MODE_MENU
        self._menu_str = SERVER_CONTROL_MGMT_MODE_MENU_DICT[self._server_mode_menu]
        self._prompt_len = len(SERVER_CONTROL_PROMPT)

    def _parser_request_cmd(self):
        rc = RcCode.FAILURE
        process_data = self._input_buffer.rstrip()

        # TBD: Implement the request execute detail
        match process_data:
            case _:
                rc = RcCode.SUCCESS
        return rc

    def run_system(self):
        if self._channel.recv_ready():
            read_str = self._channel.recv(5)
            for ascii_val in read_str:
                rc = RcCode.FAILURE
                if ascii_val == 0x1b or self._enable_escape_key:
                    rc = self._parser_ascii_esc_value(ascii_val)
                if rc != RcCode.SUCCESS:
                    rc = self._parser_ascii_value(ascii_val)
                    if rc == RcCode.EXIT_PROCESS or rc == RcCode.OPEN_SERIAL:
                        return rc
                if rc != RcCode.SUCCESS:
                    _ = self._save_user_input(ascii_val)
        return RcCode.SUCCESS


class ServerControlAccessMode(ServerControlMode):
    def __init__(self, channel):
        super().__init__(channel)
        self._server_mode_menu = ServerControlAccessModeMenu.SERVER_CONTROL_ACCESS_MODE_MENU
        self._menu_str = SERVER_CONTROL_ACCESS_MODE_MENU_DICT[self._server_mode_menu]
        self._prompt_len = len(SERVER_CONTROL_PROMPT)

    def _parser_request_cmd(self):
        rc = RcCode.FAILURE
        process_data = self._input_buffer.rstrip()

        # TBD: Implement the request execute detail
        match process_data:
            case _:
                rc = RcCode.SUCCESS
        return rc

    def run_system(self):
        if self._channel.recv_ready():
            read_str = self._channel.recv(5)
            for ascii_val in read_str:
                rc = RcCode.FAILURE
                if ascii_val == 0x1b or self._enable_escape_key:
                    rc = self._parser_ascii_esc_value(ascii_val)
                if rc != RcCode.SUCCESS:
                    rc = self._parser_ascii_value(ascii_val)
                    if rc == RcCode.EXIT_PROCESS or rc == RcCode.OPEN_SERIAL:
                        return rc
                if rc != RcCode.SUCCESS:
                    _ = self._save_user_input(ascii_val)
        return RcCode.SUCCESS
