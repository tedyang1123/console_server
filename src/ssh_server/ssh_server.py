import threading

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.ssh_server.ssh_server_mgmt.ssh_server_account_mgr import SshServerAccountMgr
from src.ssh_server.ssh_server_mgmt.ssh_server_network_mgr import SshServerNetworkMgr
from src.ssh_server.ssh_server_mgmt.ssh_server_serial_port_mgr import SshServerSerialPortMgr
from src.ssh_server.ssh_server_subsystem import SshServerPassWdAuthSubSystem, SshServerNoneAuthSubSystem

MAX_PORT_GROUP = 8
NUM_OF_SERIAL_PORT = 48


class SshServer(threading.Thread):
    def __init__(self, daemon_id):
        self._daemon_id = daemon_id
        threading.Thread.__init__(self, name="SshServer_{}".format(daemon_id))

        self._logger_system = LoggerSystem(self.name)
        self._logger = self._logger_system.get_logger()

        self._ssh_server_account_mgr = None
        self._ssh_server_serial_port_mgr = None
        self._ssh_server_network_mgr = None
        self._ssh_passwd_auth_subsystem = None
        self._ssh_none_auth_subsystem_list = []
        self._ssh_port_list = []
        for i in range(8):
            self._ssh_port_list.append([])
        self._ssh_server_mgr_dict = {
        }
        self._subsystem_stop_event = threading.Event()

    def _init_ssh_server(self):
        # Init log system
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc

        # Create SSH server account management
        self._ssh_server_mgr_dict["ssh_server_account_mgr"] = SshServerAccountMgr()
        rc = self._ssh_server_mgr_dict["ssh_server_account_mgr"].init_account_system()
        if rc != RcCode.SUCCESS:
            self._logger(self._logger_system.set_logger_rc_code("Can not init the account manager", rc))
            return rc

        # Create SSH server serial port management
        self._ssh_server_mgr_dict["_ssh_server_serial_port_mgr"] = SshServerSerialPortMgr(NUM_OF_SERIAL_PORT)

        # Create SSH server network management
        self._ssh_server_mgr_dict["ssh_server_network_mgr"] = SshServerNetworkMgr(NUM_OF_SERIAL_PORT)

        # Get the SSH server IP address
        rc, ip_addr, _ = self._ssh_server_mgr_dict["ssh_server_network_mgr"].get_ssh_server_ip_address()
        if rc != RcCode.SUCCESS:
            self._logger(self._logger_system.set_logger_rc_code("Can not get the server IP address.", rc))
            return rc

        subsystem_id = 0

        # Create SSH server subsystem which verifies the user.
        self._ssh_passwd_auth_subsystem = SshServerPassWdAuthSubSystem(1,
                                                                       ip_addr,
                                                                       [2222],
                                                                       48 * 3,
                                                                       1,
                                                                       self._ssh_server_mgr_dict,
                                                                       self._subsystem_stop_event)
        self._ssh_passwd_auth_subsystem.start()
        subsystem_id = subsystem_id + 1

        # Create the SSH port list for the none auth subsystem
        for serial_port_id in range(1, NUM_OF_SERIAL_PORT + 1):
            rc, ssh_port = (
                self._ssh_server_mgr_dict["ssh_server_network_mgr"].get_ssh_port_direct_access_serial_port(serial_port_id))
            if rc != RcCode.SUCCESS:
                self._logger(
                    self._logger_system.set_logger_rc_code("Can not get port list of the direct access port.", rc))
                return rc
            group_id = serial_port_id % 8
            self._ssh_port_list[group_id].append(ssh_port)

        # Create SSH server subsystem which does not verify the user.
        for group_id in range(MAX_PORT_GROUP):
            ssh_server_none_auth_subsystem = (
                SshServerNoneAuthSubSystem(group_id,
                                           ip_addr,
                                           self._ssh_port_list[group_id],
                                           len(self._ssh_port_list[group_id]) * 3,
                                           0.01,
                                           self._ssh_server_mgr_dict,
                                           self._subsystem_stop_event))
            ssh_server_none_auth_subsystem.start()
            self._ssh_none_auth_subsystem_list.append(ssh_server_none_auth_subsystem)
            subsystem_id = subsystem_id + 1
        return RcCode.SUCCESS

    def run(self):
        rc = self._init_ssh_server()
        if rc != RcCode.SUCCESS:
            return rc
        
        self._subsystem_stop_event.wait()

        if self._ssh_passwd_auth_subsystem.running:
            self._ssh_passwd_auth_subsystem.running = False
            self._ssh_passwd_auth_subsystem.join()
        for ssh_none_auth_subsystem in self._ssh_none_auth_subsystem_list:
            ssh_none_auth_subsystem.running = False
            ssh_none_auth_subsystem.join()
