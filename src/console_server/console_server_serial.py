from src.common.rc_code import RcCode
from src.console_server.console_server_port import console_server
from src.console_server.console_server_util import ConsoleServerMenu


class ConsoleServerSerialSystem:
    def __init__(self, channel, logger):
        self._channel = channel
        self._logger = logger
        self._serial_port_id = 0
        self._console_server_menu = ConsoleServerMenu()

    def _handle_ssh_data(self):
        if self._channel.recv_ready():
            read_str = self._channel.recv(5)
            for ascii_val in read_str:
                if ascii_val == 0x14:
                    rc = console_server.close_com_port(self._serial_port_id)
                    if rc != RcCode.SUCCESS and rc != RcCode.DEVICE_NOT_FOUND:
                        self._logger.warning("Can not close the port rc = {}".format(rc))
                        return RcCode.FAILURE
                    rc = self._console_server_menu.set_user_name(self._serial_port_id, "")
                    if rc != RcCode.SUCCESS:
                        self._logger.warning(
                            "Can not set the user for port {} rc = {}".format(self._serial_port_id, rc))
                        return RcCode.FAILURE
                    return RcCode.OPEN_TERMINAL
            rc = console_server.write_com_port_data(self._serial_port_id, read_str)
            if rc != RcCode.SUCCESS:
                self._logger.warning("Can not write the message to console rc = {}".format(rc))
                return RcCode.FAILURE
        return RcCode.SUCCESS

    def _handle_serial_data(self):
        if self._serial_port_id > 0:
            rc, data_len = console_server.in_buffer_is_waiting(self._serial_port_id)
            if rc != RcCode.SUCCESS:
                return RcCode.FAILURE
            if data_len > 0:
                rc, msg = console_server.read_com_port_data(self._serial_port_id, data_len)
                if rc == RcCode.SUCCESS:
                    try:
                        self._channel.send(msg.decode())
                    except UnicodeDecodeError:
                        self._logger.warning("Can not decode the data rc = {}".format(rc))
                        self._channel.send('.')
                else:
                    return RcCode.FAILURE
        return RcCode.SUCCESS

    def run_system(self):
        while True:
            rc, exit_com = self._handle_ssh_data()
            if rc == RcCode.OPEN_TERMINAL:
                rc = RcCode.SUCCESS
                break
            if rc != RcCode.SUCCESS:
                return rc

            rc = self._handle_serial_data()
            if rc != RcCode.SUCCESS:
                return rc
        return rc