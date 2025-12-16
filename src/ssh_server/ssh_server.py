import threading

from src.common.rc_code import RcCode
from src.ssh_server.ssh_mgr.ssh_server_account_mgr import SshServerAccountMgr
from src.ssh_server.ssh_mgr.ssh_server_network_mgr import SshServerNetworkMgr
from src.ssh_server.ssh_mgr.ssh_server_serial_port_mgr import SshServerSerialPortMgr
from src.ssh_server.ssh_server_subsystem import SshServerPassWdAuthSubSystem, SshServerNoneAuthSubSystem

NUM_OF_SERIAL_PORT = 48


class SshServer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self._ssh_server_account_mgr = None
        self._ssh_server_serial_port_mgr = None
        self._ssh_server_network_mgr = None
        self._ssh_passwd_auth_subsystem = None
        self._ssh_none_auth_subsystem = []
        self._ssh_port_list = []
        for i in range(8):
            self._ssh_port_list.append([])

    def __init_server(self):
        # Create SSH server account management
        self._ssh_server_account_mgr = SshServerAccountMgr()

        # Create SSH server serial port management
        self._ssh_server_serial_port_mgr = SshServerSerialPortMgr(NUM_OF_SERIAL_PORT)

        # Create SSH server network management
        self._ssh_server_network_mgr = SshServerNetworkMgr(NUM_OF_SERIAL_PORT)

        # Get the SSH server IP address
        rc, ip_addr = self._ssh_server_network_mgr.get_ssh_server_ip_address()
        if rc != RcCode.SUCCESS:
            return rc

        subsystem_id = 0

        # Create SSH server subsystem which verifies the user.
        self._ssh_passwd_auth_subsystem = SshServerPassWdAuthSubSystem(ip_addr, [2222], subsystem_id, 48 * 3, 0.01)
        self._ssh_passwd_auth_subsystem.start()
        subsystem_id = subsystem_id + 1

        # Create the SSH port list for the password auth subsystem
        for i in range(NUM_OF_SERIAL_PORT):
            ssh_port = self._ssh_server_network_mgr
            group_id = i % 8
            self._ssh_port_list[group_id].append(ssh_port)

        # Create SSH server subsystem which does not verify the user.
        for group_id in range(8):
            ssh_server_none_auth_subsystem = (
                SshServerNoneAuthSubSystem(ip_addr, self._ssh_port_list[group_id], subsystem_id,
                                           len(self._ssh_port_list[group_id]) * 3, 0.01))
            ssh_server_none_auth_subsystem.start()
            self._ssh_none_auth_subsystem.append(ssh_server_none_auth_subsystem)
            subsystem_id = subsystem_id + 1
        return RcCode.SUCCESS

    def run(self):
        pass