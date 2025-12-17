from src.common.rc_code import RcCode


class SshServerNetworkMgr:
    def __init__(self, num_of_ssh_port):
        self._ssh_port_direct_port_dict = {}
        for ssh_port_id in range(num_of_ssh_port):
            self._ssh_port_direct_port_dict[ssh_port_id] = 2300 + ssh_port_id

    def set_ssh_port_direct_access_serial_port(self, port, ssh_port):
        self._ssh_port_direct_port_dict[port] = ssh_port
        return RcCode.SUCCESS

    def remove_ssh_port_direct_access_serial_port(self, port):
        self._ssh_port_direct_port_dict[port] = None
        return RcCode.SUCCESS

    def get_ssh_port_direct_access_serial_port(self, port):
        return RcCode.SUCCESS, self._ssh_port_direct_port_dict[port]

    def set_ssh_server_ip_address(self, ip_addr=None, net_maks=None, dhcp=None):
        return RcCode.SUCCESS

    def get_ssh_server_ip_address(self):
        return RcCode.SUCCESS, "127.0.0.1", "255.0.0.0"
