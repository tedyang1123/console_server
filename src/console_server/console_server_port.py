import logging
import os
import threading
import time
from serial import Serial, SerialException
from src.common.rc_code import RcCode


class ConsoleServerSerialPort(threading.Thread):
    def __init__(self, port_id):
        super().__init__()
        self._serial_port_id = port_id
        self._serial_config = {}
        self._init_logger_system()
        self._current_user = 0
        self._serial_port_description = ""

    def __del__(self):
        self.close_com_port()

    def _init_logger_system(self):
        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._logger = logging.getLogger(__name__ + " {}".format(self._serial_port_id))
        self._screen_handler = logging.StreamHandler()
        self._screen_handler.setLevel(logging.WARNING)
        self._screen_handler.setFormatter(self._formatter)

        self._file_handler = logging.FileHandler("/var/log/console-server.log")
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(self._formatter)

        self._logger.setLevel(logging.DEBUG)

        self._logger.addHandler(self._screen_handler)
        self._logger.addHandler(self._file_handler)
        self._logger.propagate = False

    def test_com_port_read(self, port_id):
        if self._serial_config["port_path"] == "" or \
                not os.path.exists(self._serial_config["port_path"]):
            return RcCode.DEVICE_NOT_FOUND
        return RcCode.SUCCESS

    def create_serial_port(self):
        self._serial_config = {
            "com_port": Serial(),
            "dev_port": "",
            "baud_rate": 115200,
            "usb_id": ""
        }
        return RcCode.SUCCESS

    def open_com_port(self):
        # Port has been open by other user
        if self._current_user > 0:
            return RcCode.SUCCESS

        # Test if the serial exists.
        rc = self.test_com_port_read(self._serial_port_id)
        if rc != RcCode.SUCCESS:
            return RcCode.DEVICE_NOT_FOUND

        # Apply the serial config to serial port object
        try:
            self._serial_config["com_port"].baudrate = self._serial_config["baud_rate"]
            self._serial_config["com_port"].timeout = 0
            self._serial_config["com_port"].port = self._serial_config["dev_port"]
            self._serial_config["com_port"].rts = False
            self._serial_config["com_port"].dtr = False
            self._serial_config["com_port"].open()
        except SerialException:
            self._logger.warning("The port {} can not open".format(self._serial_port_id))
            self._logger.warning("The dev port path is {}".format(self._serial_config["dev_port"]))
            return RcCode.DEVICE_NOT_FOUND

        # Check if serial port has been opened.
        cnt = 0
        while not self._serial_config["com_port"].is_open and cnt < 5:
            time.sleep(1)
            cnt = cnt + 1
        if cnt >= 5:
            self._logger.warning("The port {} is not ready.".format(self._serial_port_id))
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def close_com_port(self):
        # There are some users to access this serial port. Do not close it.
        if self._current_user > 1:
            return RcCode.SUCCESS

        # Close the serial port.
        try:
            self._serial_config["com_port"].close()
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning("The port {} can not close".format(self._serial_port_id))
            rc = RcCode.DEVICE_NOT_FOUND
        return rc

    def set_com_port_description(self, description):
        self._serial_port_description = description
        return RcCode.SUCCESS

    def read_com_port_data(self, buf_size=50):
        data = None
        try:
            data = self._serial_config["com_port"].read(size=buf_size)
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning("Can not access port {}".format(self._serial_port_id))
            rc = RcCode.FAILURE
        return rc, data

    def write_com_port_data(self, data):
        try:
            self._serial_config["com_port"].write(data)
            self._serial_config["com_port"].flush()
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning("Can not access port {}".format(self._serial_port_id))
            rc = RcCode.FAILURE
        return rc

    def in_buffer_is_waiting(self):
        count = 0
        try:
            count = self._serial_config["com_port"].in_waiting
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning("Can not access port {}".format(self._serial_port_id))
            rc = RcCode.FAILURE
        return rc, True if count else False

    def output_buffer_is_waiting(self):
        count = 0
        try:
            count = self._serial_config["com_port"].out_waiting
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning("Can not access port {}".format(self._serial_port_id))
            rc = RcCode.FAILURE
        return rc, True if count else False

    def is_open_com_port(self):
        try:
            state = self._serial_config["com_port"].is_open
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning("Can not access port {}".format(self._serial_port_id))
            state = False
            rc = RcCode.FAILURE
        return rc, state

    def set_com_port_baud_rate(self, rate):
        if rate > 230400 or (rate % 1200) != 0:
            self._logger.warning("Invalid baudrate {}".format(self._serial_port_id))
            return RcCode.INVALID_VALUE
        self._serial_config["baud_rate"] = rate

        try:
            # Close the serial port
            self._serial_config["com_port"].close()

            # Apply the new baud rate
            self._serial_config["com_port"].baud_rate = rate

            # Open the serial to apply the new baud rate
            self._serial_config["com_port"].open()

            # Check if the port has been open
            cnt = 0
            while not self._serial_config["com_port"].is_open and cnt < 5:
                time.sleep(1)
                cnt = cnt + 1
            if cnt >= 5:
                self._logger.warning("The port {} is not ready.".format(self._serial_port_id))
                return RcCode.FAILURE
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning("The port {} can not close".format(self._serial_port_id))
            rc = RcCode.DEVICE_NOT_FOUND
        return rc

