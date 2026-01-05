import os
import time
from serial import Serial, SerialException

from src.common.rc_code import RcCode


class ConsoleServerSerialPort:
    def __init__(self, port_id, baud_rate, logger_system):
        self._serial_port_id = port_id
        self._baud_rate = baud_rate

        self._logger_system = logger_system
        self._logger = self._logger_system.get_logger()

        self._serial_config = {}
        self._current_user = 0
        self._serial_port_description = ""

    def __del__(self):
        self.close_com_port()

    def test_com_port_read(self, port_id):
        if self._serial_config["dev_port"] == "" or not os.path.exists(self._serial_config["dev_port"]):
            return RcCode.DEVICE_NOT_FOUND
        return RcCode.SUCCESS

    def create_serial_port(self):
        self._serial_config = {
            "com_port": Serial(),
            "dev_port": "/dev/ttyUSB{}".format(self._serial_port_id),
            "baud_rate": self._baud_rate
        }
        return RcCode.SUCCESS

    def open_com_port(self):
        # Port has been open by other user
        if self._current_user > 0:
            return RcCode.SUCCESS

        # Test if the serial exists.
        rc = self.test_com_port_read(self._serial_port_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port {} is not found.".format(self._serial_port_id)))
            return RcCode.DEVICE_NOT_FOUND

        # Apply the serial config to serial port object
        try:
            self._serial_config["com_port"].baudrate = self._serial_config["baud_rate"]
            self._serial_config["com_port"].timeout = 0
            self._serial_config["com_port"].port = self._serial_config["dev_port"]
            self._serial_config["com_port"].rts = False
            self._serial_config["com_port"].dtr = False
            self._serial_config["com_port"].open()
        except SerialException as e:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port {} can not open".format(self._serial_port_id)))
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "The dev port path is {}".format(self._serial_config["dev_port"])))
            self._logger.error(
                self._logger_system.set_logger_rc_code(e))
            return RcCode.DEVICE_NOT_FOUND

        # Check if serial port has been opened.
        cnt = 0
        while not self._serial_config["com_port"].is_open and cnt < 5:
            time.sleep(1)
            cnt = cnt + 1
        if cnt >= 5:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port {} is not ready.".format(self._serial_port_id)))
            return RcCode.FAILURE
        self._current_user = self._current_user + 1
        self._logger.info("Serial port {} is opened.".format(self._serial_port_id))
        return RcCode.SUCCESS

    def close_com_port(self):
        # There are some users to access this serial port. Do not close it.
        if self._current_user > 1:
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "The serial port {} is still in used".format(self._serial_port_id)))
            return RcCode.SUCCESS

        # Close the serial port.
        try:
            self._serial_config["com_port"].close()
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port {} can not close".format(self._serial_port_id)))
            rc = RcCode.DEVICE_NOT_FOUND
        self._current_user = self._current_user - 1
        self._logger.info("Serial port {} is cloded.".format(self._serial_port_id))
        return rc
    
    def reopen_com_port(self):
        # Close the serial port.
        try:
            self._logger.info(self._serial_config)
            self._serial_config["com_port"].close()
            self._serial_config["com_port"].baudrate = self._serial_config["baud_rate"]
            self._serial_config["com_port"].timeout = 0
            self._serial_config["com_port"].port = self._serial_config["dev_port"]
            self._serial_config["com_port"].rts = False
            self._serial_config["com_port"].dtr = False
            self._logger.info(self._serial_config["com_port"])
            self._serial_config["com_port"].open()
            rc = RcCode.SUCCESS
        except SerialException as e:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port {} can not open".format(self._serial_port_id)))
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "The dev port path is {}".format(self._serial_config["dev_port"])))
            self._logger.error(
                self._logger_system.set_logger_rc_code(e))
            return RcCode.DEVICE_NOT_FOUND

        # Check if serial port has been opened.
        cnt = 0
        while not self._serial_config["com_port"].is_open and cnt < 5:
            time.sleep(1)
            cnt = cnt + 1
        if cnt >= 5:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port {} is not ready.".format(self._serial_port_id)))
            return RcCode.FAILURE
        self._current_user = self._current_user + 1
        return rc

    def read_com_port_data(self, buf_size=1024):
        data = None
        try:
            data = self._serial_config["com_port"].read(size=buf_size)
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Can not access serial port {}".format(self._serial_port_id)))
            rc = RcCode.FAILURE
        return rc, data

    def write_com_port_data(self, data):
        try:
            self._logger.info("Write data from {} data {}".format(self._serial_config["dev_port"], data))
            self._serial_config["com_port"].write(data)
            self._serial_config["com_port"].flush()
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Can not access serial port {}".format(self._serial_port_id)))
            rc = RcCode.FAILURE
        return rc

    def in_buffer_is_waiting(self):
        count = 0
        try:
            count = self._serial_config["com_port"].in_waiting
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Can not access serial port {}".format(self._serial_port_id)))
            rc = RcCode.FAILURE
        return rc, True if count else False

    def output_buffer_is_waiting(self):
        count = 0
        try:
            count = self._serial_config["com_port"].out_waiting
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Can not access serial port {}".format(self._serial_port_id)))
            rc = RcCode.FAILURE
        return rc, True if count else False

    def is_open_com_port(self):
        try:
            state = self._serial_config["com_port"].is_open
            rc = RcCode.SUCCESS
        except OSError:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Can not access serial port {}".format(self._serial_port_id)))
            state = False
            rc = RcCode.FAILURE
        return rc, state

    def set_com_port_baud_rate(self, rate):
        if rate > 230400 or (rate % 1200) != 0:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Invalid baud rate {}".format(self._serial_port_id)))
            return RcCode.INVALID_VALUE
        self._serial_config["baud_rate"] = rate
        return RcCode.SUCCESS

