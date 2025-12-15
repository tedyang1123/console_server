import time

from src.common.rc_code import RcCode
from src.console_server.console_server_hook import  console_server
from src.console_server.console_server_util import ConsoleAnsiEscapeParser, ConsoleServerMenu, mgmt_banner
from src.ssh_server.ssh_util.ansi_encoder import encode_console_clear_str, encode_console_prompt


class ConsoleServerMgmtSystem:
    def __init__(self, channel, logger):
        self._channel = channel
        self._logger = logger
        self._console_server_menu = ConsoleServerMenu()
        self._ansi_escape_parser = ConsoleAnsiEscapeParser(self._channel)
        self._ssh_read_data = ""
        self._ssh_pending_data = ""
        self._serial_port_id = 0
        self._enable_escape_key = False

    def _refresh_screen(self):
        self._channel.send(encode_console_clear_str())
        self._channel.send(mgmt_banner.format(console_port=console_server.get_port_state()))
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
                self._logger.info("Get the data - {}.".format(self._ssh_read_data.strip()))
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
            case "dump-config":
                self._channel.send(encode_console_clear_str())
                self._channel.send(self._console_server_menu.dump_serial_config())
                rc = RcCode.SUCCESS
            case "save-config":
                self._channel.send(encode_console_clear_str())
                self._channel.send(self._console_server_menu.save_serial_config())
                rc = RcCode.SUCCESS
            case "reload-config":
                self._channel.send(encode_console_clear_str())
                self._channel.send(self._console_server_menu.reload_serial_config())
                rc = RcCode.SUCCESS
            case "adduser":
                self._channel.send(encode_console_clear_str())
                str_list = self._ssh_read_data.split("-")
                try:
                    rc = self._console_server_menu.add_linux_user(str_list[1], str_list[2])
                    if rc == RcCode.SUCCESS:
                        self._channel.send("Add user successful")
                    else:
                        self._channel.send("Add user fail")
                    rc = RcCode.SUCCESS
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
            case "deluser":
                self._channel.send(encode_console_clear_str())
                str_list = self._ssh_read_data.split("-")
                try:
                    num_port = int(str_list[1])
                    rc = self._console_server_menu.destroy_serial_port(num_port)
                    if rc == RcCode.SUCCESS:
                        self._channel.send("Port has deleted.")
                    else:
                        self._channel.send("Fail to delete port..")
                    rc = RcCode.SUCCESS
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
            case "addport":
                self._channel.send(encode_console_clear_str())
                str_list = self._ssh_read_data.split("-")
                try:
                    num_port = int(str_list[1])
                    rc = self._console_server_menu.create_serial_port(num_port)
                    if rc == RcCode.SUCCESS:
                        self._channel.send("Port has added.")
                    else:
                        self._channel.send("Fail to add port..")
                    rc = RcCode.SUCCESS
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
            case "delport":
                self._channel.send(encode_console_clear_str())
                str_list = self._ssh_read_data.split("-")
                try:
                    rc = self._console_server_menu.del_linux_user(str_list[1])
                    if rc == RcCode.SUCCESS:
                        self._channel.send("Delete user successful")
                    else:
                        self._channel.send("Delete user fail")
                    rc = RcCode.SUCCESS
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
            case "usbid":
                self._channel.send(encode_console_clear_str())
                str_list = self._ssh_read_data.split("-")
                try:
                    port_id = int(str_list[1])
                    if len(str_list) == 3:
                        rc = self._console_server_menu.set_usb_node(port_id, str_list[2])
                    elif len(str_list) == 2:
                        rc = self._console_server_menu.set_usb_node(port_id, "")
                    if rc == RcCode.SUCCESS:
                        self._channel.send("Set USB id successful")
                    else:
                        self._channel.send("Set USB id fail")
                    rc = RcCode.SUCCESS
                except ValueError:
                    self._logger.warning("Input invalid data.")
                    rc = RcCode.SUCCESS
            case _:
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
                    if ascii_val == 0x1b or self._enable_escape_key:  # ESC
                        rc = self._parser_ascii_esc_value(ascii_val)
                    if rc != RcCode.SUCCESS:
                        rc = self._parser_ascii_value(ascii_val)
                        if rc == RcCode.EXIT_PROCESS:
                            return RcCode.SUCCESS
                    if rc != RcCode.SUCCESS:
                        _ = self._save_user_input(ascii_val)
            time.sleep(0.1)
