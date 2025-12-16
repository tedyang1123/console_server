from src.common.rc_code import RcCode


class SshServerSerialPortMgr:
    def __init__(self, num_of_port):
        self._serial_port_dict = {}
        for port_id in num_of_port:
            self._serial_port_dict[port_id] = {}
            self._serial_port_dict[port_id]['read_only'] = []
            self._serial_port_dict[port_id]['admin_only'] = []

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