from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode


class SshServerSerialPortMgr(LoggerSystem):
    def __init__(self, num_of_serial_port):
        LoggerSystem.__init__(self, "ssh_serial_port_mgr")
        self._num_of_serial_port = num_of_serial_port
        self._serial_port_dict = {}
        for serial_port_id in range(num_of_serial_port):
            self._serial_port_dict[serial_port_id] = {}
            self._serial_port_dict[serial_port_id]['read_only'] = []
            self._serial_port_dict[serial_port_id]['admin_only'] = []

    def get_num_of_serial_port(self):
        return self._num_of_serial_port

    def set_serial_port_read_only(self, port, username):
        if username == "admin":
            return RcCode.PERMISSION_DENIED
        self._serial_port_dict[port]['read_only'].append(username)
        return RcCode.SUCCESS

    def set_serial_port_admin_only(self, port, username):
        if username == "admin":
            return RcCode.PERMISSION_DENIED
        self._serial_port_dict[port]['admin_only'].append(username)
        return RcCode.SUCCESS

    def set_serial_port_normal(self, port, username):
        if username == "admin":
            return RcCode.PERMISSION_DENIED
        if username not in self._serial_port_dict[port]['read_only']:
            self._serial_port_dict[port]['read_only'].remove(username)
        elif username in self._serial_port_dict[port]['admin_only']:
            self._serial_port_dict[port]['admin_only'].remove(username)
        return RcCode.SUCCESS