from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode


class SshServerNetworkMgr(LoggerSystem):
    def __init__(self, num_of_serial_port):
        LoggerSystem.__init__(self, "ssh_network_mgr")
        self._ssh_port_direct_port_dict = {}
        for serial_port_id in range(1, num_of_serial_port + 1):
            self._ssh_port_direct_port_dict[serial_port_id] = 2300 + serial_port_id

    def set_ssh_port_direct_access_serial_port(self, serial_port, ssh_port):
        self._ssh_port_direct_port_dict[serial_port] = ssh_port
        return RcCode.SUCCESS

    def remove_ssh_port_direct_access_serial_port(self, serial_port):
        self._ssh_port_direct_port_dict[serial_port] = None
        return RcCode.SUCCESS

    def get_ssh_port_direct_access_serial_port(self, serial_port):
        return RcCode.SUCCESS, self._ssh_port_direct_port_dict[serial_port]
    
    def get_serial_port_by_ssh_port(self, ssh_port):
        for serial_port in self._ssh_port_direct_port_dict:
            if ssh_port == self._ssh_port_direct_port_dict[serial_port]:
                return serial_port
        return -1

    def set_ssh_server_ip_address(self, ip_addr=None, net_maks=None, dhcp=None):
        return RcCode.SUCCESS

    def get_ssh_server_ip_address(self):
        return RcCode.SUCCESS, "127.0.0.1", "255.0.0.0"
