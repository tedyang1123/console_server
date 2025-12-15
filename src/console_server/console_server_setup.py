import os
import time

from src.common.rc_code import RcCode
from src.console_server.console_server_port import console_server
from src.console_server.console_server_mgmt import ConsoleServerMgmtSystem
from src.console_server.console_server_util import ConsoleAnsiEscapeParser, setup_banner
from src.ssh_server.ssh_util.ansi_encoder import encode_console_clear_str, encode_console_prompt


class ConsoleServerSetupSystem:
    def __init__(self, channel, logger, console_menu):
        self._username = os.getlogin()
        self._channel = channel
        self._logger = logger
        self._mgmt_system = ConsoleServerMgmtSystem(self._channel, self._logger)
        self._console_server_menu = console_menu
        self._ansi_escape_parser = ConsoleAnsiEscapeParser(self._channel)
        self._ssh_read_data = ""
        self._ssh_pending_data = ""
        self._serial_port_id = 0
        self._enable_escape_key = False

    def _refresh_screen(self):
        self._channel.send(encode_console_clear_str())
        self._channel.send(setup_banner.format(console_port=console_server.get_port_state()))
        self._channel.send(encode_console_prompt())

    def _parser_ascii_esc_value(self, ascii_val):
        if ascii_val == 0x1b:
            # ESC
            self._enable_escape_key = True
            rc = RcCode.SUCCESS
        else:
            # ESC, read remaining char
            self._ssh_pending_data = self._ssh_pending_data + chr(ascii_val)
            result, self._ssh_pending_data = self._ansi_escape_parser.data_parse(self._ssh_pending_data)
            if result == RcCode.DATA_NOT_FOUND or result == result.SUCCESS:
                self._enable_escape_key = False
                self._ssh_pending_data = ""
            rc = RcCode.SUCCESS
        return rc

    def _parser_ascii_value(self, ascii_val):
        rc = RcCode.FAILURE
        match ascii_val:
            case 0x0a | 0x0d:
                # Read newline
                self._logger.warning("Get the data - {}.".format(self._ssh_read_data.strip()))
                process_data = self._ssh_read_data.rstrip()
                match process_data:
                    case "exit":
                        self._channel.send('\r\n')
                        rc = RcCode.EXIT_PROCESS
                    case "":
                        self._refresh_screen()
                        rc = RcCode.SUCCESS
                    case _:
                        rc = self._parser_request_cmd()
                self._ssh_read_data = ''
            case 0x08:
                # Read backspace
                if self._ssh_read_data != "":
                    self._ssh_read_data = self._ssh_read_data[:-1]
                    self._channel.send("\b \b")
                rc = RcCode.SUCCESS
        return rc

    def _parser_request_cmd(self):
        rc = RcCode.FAILURE
        match self._ssh_read_data:
            case "mgmt":
                rc = self._mgmt_system.run_system()
                self._refresh_screen()
            case "kill":
                try:
                    port_id = int(self._ssh_read_data.replace("kill-", ""))
                    rc = self._console_server_menu.close_port(port_id)
                    if rc != RcCode.SUCCESS and rc != RcCode.DEVICE_NOT_FOUND:
                        self._logger.warning("Can not close port rc = {}".format(rc))
                        return RcCode.FAILURE
                    rc = self._console_server_menu.set_user_name(port_id, "")
                    if rc != RcCode.SUCCESS:
                        self._logger.warning("Can not set the username rc = {}".format(rc))
                        return RcCode.FAILURE
                    self._refresh_screen()
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
            case "baudrate":
                str_list = self._ssh_read_data.split("-")
                try:
                    port_id = int(str_list[1])
                    if len(str_list) == 3:
                        rc = self._console_server_menu.set_baud_rate(port_id, int(str_list[2]))
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
                self._refresh_screen()
            case "description":
                str_list = self._ssh_read_data.split("-")
                try:
                    port_id = int(str_list[1])
                    if len(str_list) == 3:
                        rc = self._console_server_menu.set_description(port_id, str_list[2])
                    elif len(str_list) == 2:
                        rc = self._console_server_menu.set_description(port_id, "")
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
                self._refresh_screen()
            case _:
                try:
                    self._serial_port_id = int(self._ssh_read_data)
                    rc = self._console_server_menu.open_port(self._serial_port_id)
                    if rc == RcCode.SUCCESS or rc == RcCode.DEVICE_BUSY or rc == RcCode.DEVICE_NOT_FOUND or \
                            rc == RcCode.INVALID_VALUE:
                        self._channel.send(encode_console_clear_str())
                        if rc == RcCode.SUCCESS:
                            rc = self._console_server_menu.set_user_name(self._serial_port_id, self._username)
                            if rc == RcCode.SUCCESS:
                                rc = RcCode.OPEN_SERIAL
                        else:
                            if rc == RcCode.DEVICE_BUSY:
                                self._channel.send("Port has occupied by other user.")
                            if rc == RcCode.DEVICE_NOT_FOUND:
                                self._channel.send("Port not found.")
                            if rc == RcCode.INVALID_VALUE:
                                self._refresh_screen()
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    self._serial_port_id = 0
                    rc = RcCode.SUCCESS
                    self._refresh_screen()
        return rc

    def _save_user_input(self, ascii_val):
        self._ssh_read_data = self._ssh_read_data + chr(ascii_val)
        self._channel.send(chr(ascii_val))
        return RcCode.SUCCESS

    def run_system(self):
        self._refresh_screen()
        while True:
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
            time.sleep(0.1)
