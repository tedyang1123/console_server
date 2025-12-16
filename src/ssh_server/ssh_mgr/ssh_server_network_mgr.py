from src.common.rc_code import RcCode


class SshServerNetworkMgr:
    def __init__(self, num_of_ssh_port):
        self._ssh_port_direct_port_dict = {}
        for port_id in num_of_ssh_port:
            self._ssh_port_direct_port_dict[port_id] = 2300 + port_id

    def set_ssh_direct_access_port(self, port, ssh_port):
        self._ssh_port_direct_port_dict[port] = ssh_port
        return RcCode.SUCCESS

    def remove_ssh_direct_access_port(self, port):
        self._ssh_port_direct_port_dict[port] = None
        return RcCode.SUCCESS

    def get_ssh_direct_access_port(self, port):
        return RcCode.SUCCESS, self._ssh_port_direct_port_dict[port]

    def set_ssh_server_ip_address(self, ip_addr=None, net_maks=None, dhcp=None):
        return RcCode.SUCCESS

    def get_ssh_server_ip_address(self):
        return RcCode.SUCCESS, "", ""
