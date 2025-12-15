import re
import subprocess

from src.common.rc_code import RcCode
from src.console_server.console_server_port import console_server

setup_banner = ("Wellcome to the Terminal Server\r\n"
                  "----------------------------------------------------------------------------------\r\n"
                  "{console_port:<80}\r\n"
                  "----------------------------------------------------------------------------------\r\n"
                  "Write \"exit\" to quit.\r\n"
                  "Write \"kill-<PORT-ID>\" to kill the process which occupied the specified serial port\r\n"
                  "Write \"baudrate-<PORT-ID>-<RATE>\" to configure the baudrate\r\n"
                  "Write \"description-<PORT-ID>-<MSG>\" to set the description for port\r\n"
                  "Write \"CTL-t\" to return to the terminal mode from serial port mode.\r\n"
                  "\r\n")


mgmt_banner = ("Wellcome to the Terminal Server\r\n"
                  "----------------------------------------------------------------------------------\r\n"
                  "{console_port:<80}\r\n"
                  "----------------------------------------------------------------------------------\r\n"
                  "Write \"exit\" to quit.\r\n"
                  "Write \"dump-config\" to dump the startup-config\r\n"
                  "Write \"save-config\" tp save the running config to startup-config\r\n"
                  "Write \"reload-config\" to reload the startup-config to running-config\r\n"
                  "Write \"addport\" to add a new port to the menu\r\n"
                  "Write \"delport\" to delete a the port from the menu\r\n"
                  "Write \"usbid\" to configure the USB mode ID\r\n"
                  "Write \"adduser-<USERNAME>-<PASSWORD>\" to create an user\r\n"
                  "Write \"deluser-<USERNAME>\" to delete an user.\r\n"
                  "\r\n")


class ConsoleAnsiEscapeParser:
    def __init__(self, ssh_channel):
        self._ssh_channel = ssh_channel
        self._csi_sequence_str = r'\[([0-9]*)(;?)([0-9]*)([@A-Z\[\\\]\^_`a-z\{\|\}~])'

    def data_parse(self, data_str):
        rc = RcCode.FAILURE
        remaining_str = data_str
        if data_str == '[':
            rc = RcCode.DATA_NOT_READY
        else:
            group = re.match(self._csi_sequence_str, data_str, re.M | re.I)
            if group is not None:
                if group[4] == "":
                    rc = RcCode.DATA_NOT_READY
                else:
                    remaining_str = data_str.replace(group[0], "")
                    if group[4] == "A":
                        rc = RcCode.SUCCESS
                    elif group[4] == "B":
                        rc = RcCode.SUCCESS
                    elif group[4] == "C":
                        rc = RcCode.SUCCESS
                    elif group[4] == "D":
                        rc = RcCode.SUCCESS
                    else:
                        rc = RcCode.DATA_NOT_FOUND
        return rc, remaining_str


class ConsoleServerMenu:
    def open_port(self, port_id):
        return console_server.open_com_port(port_id)

    def close_port(self, port_id):
        return console_server.close_com_port(port_id)

    def set_usb_node(self, port_id, node):
        return console_server.set_usb_node(port_id, node)

    def set_baud_rate(self, port_id, baud_rate):
        return console_server.set_com_port_baud_rate(port_id, baud_rate)

    def set_user_name(self, port_id, user_name):
        return console_server.set_com_port_user(port_id, user_name)

    def set_description(self, port_id, description):
        return console_server.set_com_port_description(port_id, description)

    def dump_serial_config(self):
        return console_server.dump_serial_config()

    def save_serial_config(self):
        return console_server.save_serial_config()

    def reload_serial_config(self):
        return console_server.reload_serial_config()

    def get_num_of_port(self):
        return console_server.get_num_of_port()

    def create_serial_port(self, port_id):
        return console_server.create_serial_port(port_id)

    def destroy_serial_port(self, port_id):
        return console_server.destroy_serial_port(port_id)

    def add_linux_user(self, username, password):
        try:
            subprocess.run(['useradd','-m', '-p',  password, username])
        except subprocess.CalledProcessError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def del_linux_user(self, username):
        try:
            subprocess.call(["userdel", "-r", username])
        except subprocess.CalledProcessError:
            return RcCode.FAILURE
        return RcCode.SUCCESS