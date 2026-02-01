import multiprocessing
import select
import time

from src.common.logger_system import LoggerSystem
from src.common.msg import ReplyMsg, RequestMsg, msg_deserialize, msg_serialize, check_all_required_parameter
from src.common.msg_queue import BiMsgQueue
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainServerSocket, UnixDomainConnectedClientSocket
from src.console_server.processing.console_server_definition import ConsoleServerEvent, UserRole, UserRolePriorityDict, \
    PriorityUserRole_dict, VALID_BAUD_RATE
from src.console_server.processing.console_server_handler import ConsolerServerHandler


MAX_HANDLER_PROCESS =  8


class _ConsoleServerOpDb:
    def __init__(self):
        self._client_socket_dict = {}
        self._process_handler_dict = {}
        self._process_queue_dict = {}
        self._serial_port_group_dict = {}
        self._serial_port_dict = {}
        self._group_dict = {}
        self._user_dict = {}

    def add_client_socket(self, client_socket_fd, client_socket):
        if client_socket_fd in self._client_socket_dict:
            return RcCode.DATA_EXIST
        self._client_socket_dict[client_socket_fd] = {}
        self._client_socket_dict[client_socket_fd]["socket_obj"] = client_socket
        return RcCode.SUCCESS

    def del_client_socket(self, client_socket_fd):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND
        del self._client_socket_dict[client_socket_fd]
        return RcCode.SUCCESS

    def get_client_socket(self, client_socket_fd):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._client_socket_dict[client_socket_fd]["socket_obj"]

    def add_client_request(self, client_socket_fd, request):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND
        self._client_socket_dict[client_socket_fd]["request"] = request
        return RcCode.SUCCESS

    def del_client_request(self, client_socket_fd):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND
        if "request" not in self._client_socket_dict[client_socket_fd]:
            return RcCode.DATA_NOT_FOUND
        del self._client_socket_dict[client_socket_fd]["request"]
        return RcCode.SUCCESS

    def get_client_request(self, client_socket_fd):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND, None
        if "request" not in self._client_socket_dict[client_socket_fd]:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._client_socket_dict[client_socket_fd]["request"]

    def update_client_request(self, client_socket_fd, request):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND
        if "request" not in self._client_socket_dict[client_socket_fd]:
            return RcCode.DATA_NOT_FOUND
        self._client_socket_dict[client_socket_fd]["request"] = request
        return RcCode.SUCCESS

    def add_process_handler(self, process_id, handler_obj, message_queue):
        if process_id in self._process_handler_dict:
            return RcCode.DATA_EXIST
        self._process_handler_dict[process_id] = {"handler": handler_obj, "init_done": False}
        self._process_queue_dict[process_id] = message_queue
        return RcCode.SUCCESS

    def del_process_handler(self, process_id):
        if process_id not in self._process_handler_dict:
            return RcCode.DATA_NOT_FOUND
        del self._process_handler_dict[process_id]
        del self._process_queue_dict[process_id]
        return RcCode.SUCCESS

    def get_process_handler(self, process_id=None):
        if process_id is not None:
            return self._process_handler_dict[process_id]
        return RcCode.SUCCESS, self._process_handler_dict

    def get_process_queue(self, process_id=None):
        if process_id is not None:
            return RcCode.SUCCESS, self._process_queue_dict[process_id]
        return RcCode.SUCCESS, self._process_queue_dict

    def set_handler_init_status(self, process_id, status):
        if process_id not in self._process_handler_dict:
            return RcCode.DATA_NOT_FOUND
        self._process_handler_dict[process_id]["init_done"] = status
        return RcCode.SUCCESS

    def get_handler_init_status(self, process_id):
        if process_id not in self._process_handler_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._process_handler_dict[process_id]["init_done"]

    def add_serial_port_group(self, group_id):
        if group_id in self._serial_port_group_dict:
            return RcCode.DATA_EXIST
        self._serial_port_group_dict[group_id] = {}
        return RcCode.SUCCESS

    def del_serial_port_group(self, group_id):
        if group_id not in self._serial_port_group_dict:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_group_dict[group_id]
        return RcCode.SUCCESS

    def get_serial_port_group(self, group_id=None):
        if group_id is not None:
            return RcCode.SUCCESS, self._serial_port_group_dict[group_id]
        return RcCode.SUCCESS, self._serial_port_group_dict

    def join_serial_port_group(self, serial_port_id, group_id, serial_port_config):
        if group_id not in self._serial_port_group_dict:
            return RcCode.DATA_NOT_FOUND
        if serial_port_id in self._serial_port_group_dict[group_id]:
            return RcCode.DATA_EXIST
        self._serial_port_group_dict[group_id][serial_port_id] = serial_port_config
        return RcCode.SUCCESS

    def modify_serial_port_group(self, serial_port_id, group_id, serial_port_config):
        if group_id not in self._serial_port_group_dict:
            return RcCode.DATA_NOT_FOUND
        if serial_port_id not in self._serial_port_group_dict[group_id]:
            return RcCode.DATA_NOT_FOUND
        self._serial_port_group_dict[group_id][serial_port_id] = serial_port_config
        return RcCode.SUCCESS

    def add_serial_port(self, serial_port_id, baud_rate, alias_name, dev_tty):
        if serial_port_id in self._serial_port_dict:
            return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id] = {
            "baud_rate": baud_rate,
            "alias_name": alias_name,
            "dev_tty_id": dev_tty,
            "group_list": []
        }
        return RcCode.SUCCESS

    def del_serial_port(self, serial_port_id):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_dict[serial_port_id]
        return RcCode.SUCCESS

    def get_serial_port(self, serial_port_id=None, field=None):
        if serial_port_id is None:
            return RcCode.SUCCESS, self._serial_port_dict
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field is not None:
            return RcCode.SUCCESS, self._serial_port_dict[serial_port_id][field]
        return RcCode.SUCCESS, self._serial_port_dict[serial_port_id]

    def modify_serial_port(self, serial_port_id, field, data):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if field not in self._serial_port_dict[serial_port_id]:
            return RcCode.DATA_NOT_FOUND
        self._serial_port_dict[serial_port_id][field] = data
        return RcCode.SUCCESS

    def add_user_account(self, username, role, group_name):
        if username in self._user_dict:
            return RcCode.DATA_EXIST
        if group_name not in self._group_dict:
            return RcCode.DATA_NOT_FOUND
        self._user_dict[username] = {"role": role, "group_list": [group_name]}
        return RcCode.SUCCESS

    def del_user_account(self, username):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        del self._user_dict[username]
        return RcCode.SUCCESS

    def get_user_account(self, username=None):
        if username is None:
            return RcCode.SUCCESS, self._user_dict
        if username not in self._user_dict:
            return RcCode.DATA_EXIST, None
        return RcCode.SUCCESS, self._user_dict[username]

    def get_user_account_role(self, username):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._user_dict[username]["role"]

    def modify_user_account_role(self, username, role):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        self._user_dict[username]["role"] = role
        return RcCode.SUCCESS

    def create_group(self, group_name, role):
        if group_name in self._group_dict:
            return RcCode.DATA_EXIST
        self._group_dict[group_name] = {"role": role}
        return RcCode.SUCCESS

    def destroy_group(self, group_name):
        if group_name not in self._group_dict:
            return RcCode.DATA_NOT_FOUND
        del self._group_dict[group_name]
        return RcCode.SUCCESS

    def get_group(self, group_name=None):
        if group_name is None:
            return RcCode.SUCCESS, self._group_dict
        if group_name not in self._group_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._group_dict[group_name]

    def user_join_group(self, username, group_name):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        group_list = self._user_dict[username]["group_list"]
        if group_name in group_list:
            return RcCode.DATA_EXIST
        group_list.append(group_name)
        return RcCode.SUCCESS

    def user_leave_group(self, username, group_name):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        group_list = self._user_dict[username]["group_list"]
        if group_name not in group_list:
            return RcCode.DATA_NOT_FOUND
        group_list.remove(group_name)
        return RcCode.SUCCESS

    def port_join_group(self, serial_port_id, group_name):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if group_name in self._serial_port_dict[serial_port_id]["group_list"]:
            return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id]["group_list"].append(group_name)
        return RcCode.SUCCESS

    def port_leave_group(self, serial_port_id, group_name):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if group_name in self._serial_port_dict[serial_port_id]["group_list"]:
            return RcCode.DATA_NOT_FOUND
        self._serial_port_dict[serial_port_id]["group_list"].remove(group_name)
        return RcCode.SUCCESS


class _ConsoleServerConfigDb:
    def __init__(self):
        self._serial_port_dict = {}
        self._group_dict = {}
        self._user_dict = {}

    def add_serial_port(self, serial_port_id, baud_rate, alias_name):
        if serial_port_id in self._serial_port_dict:
            return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id] = {
            "baud_rate": baud_rate,
            "alias_name": alias_name,
            "group_list": []
        }
        return RcCode.SUCCESS
    
    def del_serial_port(self, serial_port_id):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_dict[serial_port_id]
        return RcCode.SUCCESS

    def get_serial_port(self, serial_port_id=None, field=None):
        if serial_port_id is None:
            return RcCode.SUCCESS, self._serial_port_dict
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field is not None:
            return RcCode.SUCCESS, self._serial_port_dict[serial_port_id][field]
        return RcCode.SUCCESS, self._serial_port_dict[serial_port_id]

    def modify_serial_port(self, serial_port_id, field, data):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if field not in self._serial_port_dict[serial_port_id]:
            return RcCode.DATA_NOT_FOUND
        self._serial_port_dict[serial_port_id][field] = data
        return RcCode.SUCCESS
    
    def add_user_account(self, username, role, group_name):
        if username in self._user_dict:
            return RcCode.DATA_EXIST
        if group_name not in self._group_dict:
            return RcCode.DATA_NOT_FOUND
        self._user_dict[username] = {"role": role, "group_list": [group_name]}
        return RcCode.SUCCESS
    
    def del_user_account(self, username):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        del self._user_dict[username]
        return RcCode.SUCCESS
    
    def get_user_account(self, username=None):
        if username is None:
            return RcCode.SUCCESS, self._user_dict
        if username not in self._user_dict:
            return RcCode.DATA_EXIST, None
        return RcCode.SUCCESS, self._user_dict[username]
    
    def get_user_account_role(self, username):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._user_dict[username]["role"]

    def get_user_group_list(self, username):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._user_dict[username]["group_list"]
    
    def modify_user_account_role(self, username, role):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        self._user_dict[username]["role"] = role
        return RcCode.SUCCESS
    
    def create_group(self, group_name, role):
        if group_name in self._group_dict:
            return RcCode.DATA_EXIST
        self._group_dict[group_name] = {"role": role}
        return RcCode.SUCCESS
    
    def destroy_group(self, group_name):
        if group_name not in self._group_dict:
            return RcCode.DATA_NOT_FOUND
        del self._group_dict[group_name]
        return RcCode.SUCCESS
    
    def get_group(self, group_name=None):
        if group_name is None:
            return RcCode.SUCCESS, self._group_dict
        if group_name not in self._group_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._group_dict[group_name]
    
    def user_join_group(self, username, group_name):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        group_list = self._user_dict[username]["group_list"]
        if group_name in group_list:
            return RcCode.DATA_EXIST
        group_list.append(group_name)
        return RcCode.SUCCESS
    
    def user_leave_group(self, username, group_name):
        if username not in self._user_dict:
            return RcCode.DATA_NOT_FOUND
        group_list = self._user_dict[username]["group_list"]
        if group_name not in group_list:
            return RcCode.DATA_NOT_FOUND
        group_list.remove(group_name)
        return RcCode.SUCCESS
    
    def port_join_group(self, serial_port_id, group_name):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if group_name in self._serial_port_dict[serial_port_id]["group_list"]:
            return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id]["group_list"].append(group_name)
        return RcCode.SUCCESS
    
    def port_leave_group(self, serial_port_id, group_name):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if group_name in self._serial_port_dict[serial_port_id]["group_list"]:
            return RcCode.DATA_NOT_FOUND
        self._serial_port_dict[serial_port_id]["group_list"].remove(group_name)
        return RcCode.SUCCESS


class ConsoleServer(multiprocessing.Process):
    def __init__(self, daemon_id, max_client, num_of_serial_port):
        self._num_of_serial_port = num_of_serial_port
        self._daemon_id = daemon_id
        self._max_client = max_client
        multiprocessing.Process.__init__(self, name="ConsoleServer_{}".format(daemon_id))

        self._logger_system = LoggerSystem("ConsoleServer_{}".format(daemon_id))
        self._logger = None

        self._server_mgmt_socket_file_path = "/tmp/server_mgmt.sock"
        self._uds_server_mgmt_socket = None
        self._server_mgmt_socket_fd = -1

        self._server_mgmt_epoll = None

        self._config_db = _ConsoleServerConfigDb()

        self._op_db = _ConsoleServerOpDb()

        self._processing_time = 0.01

    def _reply_client_message(self, client_socket_obj, client_request, result, data):
        # Create reply message
        reply_msg = ReplyMsg(
            client_request.request, client_request.serial_port_id, client_request.socket_fd,
            client_request.exec_user, data, result)
        rc, msg_dict = reply_msg.get_msg()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not convert the data to the dictionary.", rc=rc))
            return rc

        # Message serialize
        rc, msg_str = msg_serialize(msg_dict)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not serialize the data.", rc=rc))
            return rc

        # Send the total size of the message by socket
        data_len = len(msg_str)
        data_byte = data_len.to_bytes(4, byteorder='little')
        rc = client_socket_obj.uds_client_socket_send(data_byte)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not serialize the data.", rc=rc))
            return rc

        # Send the message by socket
        rc = client_socket_obj.uds_client_socket_send(bytes(msg_str, 'utf-8'))
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not serialize the data.", rc=rc))
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("Reply client completely.", rc=rc))
        return RcCode.SUCCESS
    
    def _send_queue_message(self, process_id, handler_request):
        rc, message_queue = self._op_db.get_process_queue(process_id)
        if rc != RcCode.SUCCESS:
            return rc
        rc = message_queue.local_peer_send_msg(handler_request)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS

    def _receive_queue_message(self, process_id):
        # Get the message queue
        rc, msg_queue = self._op_db.get_process_queue(process_id)
        if rc != RcCode.SUCCESS:
            return rc, None
        rc, reply = msg_queue.local_peer_receive_msg()
        if rc != RcCode.SUCCESS:
            return rc, None
        return rc, reply

    ##########################################################################################################
    # Initialize Server Relate API
    ##########################################################################################################

    def _init_service_server_socket(self):
        # Init the Unix domain server socket
        self._uds_server_mgmt_socket = UnixDomainServerSocket(
            self._max_client, self._server_mgmt_socket_file_path, self._logger_system)
        rc = self._uds_server_mgmt_socket.uds_server_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not init the server socket.", rc=rc))
            return rc
        server_socket_fd = self._uds_server_mgmt_socket.uds_server_socket_fd_get()
        self._server_mgmt_socket_fd = server_socket_fd
            
        # Init the epoll
        self._server_mgmt_epoll = select.epoll()
        self._server_mgmt_epoll.register(self._server_mgmt_socket_fd, select.EPOLLIN)
        return RcCode.SUCCESS
    
    def _init_serial_port_group(self):
        # Init handler process
        for group_id in range(8):
            rc = self._op_db.add_serial_port_group(group_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "Failed to create the serial port group.", rc=rc))
                return rc
        return RcCode.SUCCESS
    
    def _init_console_handler(self):
        # Create the process the for the socket
        rc = RcCode.SUCCESS
        for process_id in range(0, MAX_HANDLER_PROCESS):
            # Create the message queue
            msg_queue = BiMsgQueue(tx_blocking=False, tx_timeout=None, rx_blocking=False, rx_timeout=None)
            rc = msg_queue.init_queue()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not init the message queue.", rc=rc))
                return rc
            
            # Create the console server handler
            process_handler = ConsolerServerHandler(process_id, msg_queue.remote_peer_send_msg, msg_queue.remote_peer_receive_msg)
            rc = self._op_db.add_process_handler(process_id, process_handler, msg_queue)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not add the handler to the DB.", rc=rc))
                return rc
            process_handler.start()
        return rc
    
    def _check_handler_init_complete(self):
        count = 0
        while True:
            break_check = True
            for process_id in range(0, MAX_HANDLER_PROCESS):
                # Check if the handler initialize completely.
                rc, status = self._op_db.get_handler_init_status(process_id)
                if rc != RcCode.SUCCESS:
                    return rc
                
                # If the handler does not initialize completely, receive message from the queue binding with the handler
                if status:
                    continue
                
                # Receive the message from the queue
                rc, reply = self._receive_queue_message(process_id)
                if rc != RcCode.SUCCESS:
                    status = False
                else:
                    # Check if handler has initialized completely
                    if reply.request == ConsoleServerEvent.INIT_HANDLER and reply.result == "OK":
                        self._logger.info(self._logger_system.set_logger_rc_code("Process {} has completed.".format(process_id), rc=rc))
                        rc = self._op_db.set_handler_init_status(process_id, True)
                        if rc != RcCode.SUCCESS:
                            return rc
                        status = True
                
                # Summary the process status
                break_check = break_check and status

            # Process initialize completely. Stop the loop
            if break_check:
                break
            else:
                # Update the counter
                count = count + 1
                time.sleep(1)

        self._logger.info(self._logger_system.set_logger_rc_code("Waiting completely."))

        # Check all process has init done
        failed_process_id_list = []
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, status = self._op_db.get_handler_init_status(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
                return rc
            if not status:
                failed_process_id_list.append(process_id)
        if len(failed_process_id_list) != 0:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Handler {} init fail.".format(failed_process_id_list)))
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def init_console_server(self):
        # init the logger system
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger = self._logger_system.get_logger()

        # Init the server socket
        rc = self._init_service_server_socket()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger.info(
            self._logger_system.set_logger_rc_code("Init server socket and EPOLL completely.", rc=rc))

        # Init the serial port group
        rc = self._init_serial_port_group()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger.info(
            self._logger_system.set_logger_rc_code("Init serial port group completely", rc=rc))

        # Init the server handler
        rc = self._init_console_handler()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger.info(
            self._logger_system.set_logger_rc_code("Waiting the handler to process event", rc=rc))
        
        # Check the server handler has initialized completely.
        rc = self._check_handler_init_complete()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("Init console server completely."))
        return RcCode.SUCCESS

    ##########################################################################################################
    # Initialize Serial Port Relate API
    ##########################################################################################################
    
    def _init_handle_serial_port(self):
        for serial_port_id in range(1, self._num_of_serial_port + 1):
            # Add the serial port in the config DB
            rc = self._config_db.add_serial_port(
                serial_port_id, 115200, "COM{}".format(serial_port_id))
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "Failed to create the serial port in the config DB.", rc=rc))
                return rc

            # Add the serial port in the group of the operation DB
            rc = self._op_db.join_serial_port_group(
                serial_port_id, (serial_port_id - 1) % 8, {"baud_rate": 115200, "dev_tty_id": 1})
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "Failed to join the port in the port group.", rc=rc))
                return rc

        # Create the process the for the socket
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, msg_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "The message queue for queue {} does not exist.".format(process_id), rc=rc))
                return rc

            # Get the serial port group and we will pass it to the handler
            rc, serial_port_group =  self._op_db.get_serial_port_group(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not get the serial port group from the DB.", rc=rc))
                return rc
            
            # Send message to the handler
            request = RequestMsg(ConsoleServerEvent.INIT_SERIAL_PORT, data={"serial_port_config": serial_port_group})
            rc = msg_queue.local_peer_send_msg(request)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not send the port initialize request.", rc=rc))
                return rc

        status_dict = {}
        for process_id in range(0, MAX_HANDLER_PROCESS):
            status_dict[process_id] = False
        count = 0
        while True:
            break_check = True
            for process_id in range(0, MAX_HANDLER_PROCESS):
                if status_dict[process_id]:
                    continue

                # Receive the message from the queue
                status = False
                rc, reply = self._receive_queue_message(process_id)
                if rc == RcCode.SUCCESS:
                    # Check if handler has initialized completely
                    if reply.request == ConsoleServerEvent.INIT_SERIAL_PORT and reply.result == "OK":
                        self._logger.info(self._logger_system.set_logger_rc_code(
                            "Process {} has completed.".format(process_id), rc=rc))
                        for serial_port_id in reply.data["serial_port_config"]:
                            rc = self._op_db.add_serial_port(
                                serial_port_id, 115200, "COM{}".format(serial_port_id), serial_port_id - 1)
                            if rc != RcCode.SUCCESS:
                                self._logger.error(self._logger_system.set_logger_rc_code(
                                    "Failed to create the serial port in the operation DB.", rc=rc))
                                return rc
                        status_dict[process_id] = True
                        status = True

                # Summary the process status
                break_check = break_check and status

            # Process initialize completely. Stop the loop
            if break_check:
                break
            else:
                # Update the counter
                count = count + 1
                time.sleep(1)
        return RcCode.SUCCESS

    ##########################################################################################################
    # Initialize Default Account API
    ##########################################################################################################

    def _init_handle_admin_user(self):
        # Update the DB
        rc = self._config_db.create_group("admin", "admin")
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not create the group in the config DB.", rc=rc))
            return rc

        # Update the DB
        rc = self._config_db.add_user_account("admin", "admin", "admin")
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the user in the DB.", rc=rc))
            return rc

        # Create the process the for the socket
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, msg_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The message queue for queue {} does not exist.".format(process_id), rc=rc))
                return rc

            # Send message to the handler
            request = RequestMsg(ConsoleServerEvent.INIT_DEFAULT_ACCOUNT, data={"username": "admin", "group_name": "admin", "role": "admin"})
            rc = msg_queue.local_peer_send_msg(request)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not send the port initialize request.", rc=rc))
                return rc

        status_dict = {}
        for process_id in range(0, MAX_HANDLER_PROCESS):
            status_dict[process_id] = False
        count = 0
        while True:
            break_check = True
            for process_id in range(0, MAX_HANDLER_PROCESS):
                if status_dict[process_id]:
                    continue

                # Receive the message from the queue
                status = False
                rc, reply = self._receive_queue_message(process_id)
                if rc == RcCode.SUCCESS:
                    # Check if handler has initialized completely
                    if reply.request == ConsoleServerEvent.INIT_DEFAULT_ACCOUNT and reply.result == "OK":
                        self._logger.info(
                            self._logger_system.set_logger_rc_code(
                                "Process {} has created the default account.".format(process_id), rc=rc))
                        status_dict[process_id] = True
                        status = True

                # Summary the process status
                break_check = break_check and status

            # Process initialize completely. Stop the loop
            if break_check:
                break
            else:
                # Update the counter
                count = count + 1
                time.sleep(1)

        # Update the DB
        rc = self._op_db.create_group("admin", "admin")
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not create the group in the config DB.", rc=rc))
            return rc

        # Update the DB
        rc = self._op_db.add_user_account("admin", "admin", "admin")
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the user in the DB.", rc=rc))
            return rc
        return RcCode.SUCCESS
    
    ##########################################################################################################
    # Process Message Queue Data Relate API
    ##########################################################################################################

    def _check_request_is_valid(self, reply, client_socket_obj):
        # Get the source request
        rc, request_msg = self._op_db.get_client_request(reply.socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Get origin request fail.", rc=rc))
            return self._reply_client_message(client_socket_obj, reply,
                                              "failed", "Verify the data failed.")

        # Check if the request data is the same with the handler reply
        if request_msg.request != reply.request or request_msg.socket_fd != reply.socket_fd or \
            request_msg.serial_port_id != reply.serial_port_id:
            return self._reply_client_message(client_socket_obj, reply,
                                            "failed", "Invalid serial prot number.")
        return RcCode.SUCCESS
    
    def _update_request_information(self, reply, client_socket_obj):
        # Update DB if handler handles the request successful
        if reply.result != "OK":
            self._logger.error(self._logger_system.set_logger_rc_code("Handler the request failed."))
            return self._reply_client_message(client_socket_obj, reply,
                                              "failed", "Handler the request failed.")

        # Delete the source request
        rc = self._op_db.del_client_request(reply.socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.info(self._logger_system.set_logger_rc_code("Delete origin request fail.", rc=rc))
            return self._reply_client_message(client_socket_obj, reply,
                                              "failed", "Delete original request failed.")
        return RcCode.SUCCESS
    
    def _update_process_reply_info(self, reply, client_socket_obj):
        # Get the source request
        rc, request = self._op_db.get_client_request(reply.socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Delete origin request fail.", rc=rc))
            return self._reply_client_message(client_socket_obj, reply,
                                              "failed", "Delete original request failed.")

        process_id = reply.data["process_id"]
        request.data["ready"][process_id] = True
        request.data["status"][process_id] = True if reply.result == "OK" else False
        return RcCode.SUCCESS
    
    def _check_process_reply_info(self, reply, client_socket_obj):
        # Get the source request
        rc, request = self._op_db.get_client_request(reply.socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.info(self._logger_system.set_logger_rc_code("Delete origin request fail.", rc=rc))
            return self._reply_client_message(client_socket_obj, reply,
                                              "failed", "Delete original request failed.")

        complete = True
        status = True
        for i in range(0, MAX_HANDLER_PROCESS):
            if not request.data["ready"][i]:
                complete = False
                status = False
                break
            status = status and request.data["status"][i]
        return RcCode.SUCCESS, complete, status

    def _handle_client_reply(self, reply):
        self._logger.info(self._logger_system.set_logger_rc_code("Receive the request {}.".format(reply.request)))
        # Do other action if request need
        match reply.request:
            case ConsoleServerEvent.SET_BAUD_RATE | \
                ConsoleServerEvent.PORT_JOIN_GROUP | ConsoleServerEvent.PORT_LEAVE_GROUP:
                # Get the socket object
                rc, client_socket_obj = self._op_db.get_client_socket(reply.socket_fd)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not find the socket in the DB for request {}.".format(reply.request), rc=rc))
                    return rc
                
                # Check if the request is valid
                rc = self._check_request_is_valid(reply, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    return rc
                
                # Update the DB
                rc = self._update_request_information(reply, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    return rc

                # Config the new baud rate in the DB
                rc = self._op_db.modify_serial_port(reply.serial_port_id, "baud_rate", reply.data["baud_rate"])
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code(
                        "Can not update the baud rate of the port in the operation DB.", rc=rc))
                    return rc
            case ConsoleServerEvent.CREATE_GROUP | ConsoleServerEvent.DESTROY_GROUP | \
                ConsoleServerEvent.ADD_USER_ACCOUNT | ConsoleServerEvent.DEL_USER_ACCOUNT | \
                ConsoleServerEvent.USER_JOIN_GROUP | ConsoleServerEvent.USER_LEAVE_GROUP | \
                ConsoleServerEvent.PORT_JOIN_GROUP | ConsoleServerEvent.PORT_LEAVE_GROUP:
                # Get the socket object
                rc, client_socket_obj = self._op_db.get_client_socket(reply.socket_fd)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not find the socket in the DB for request {}.".format(reply.request), rc=rc))
                    return rc
                
                # Check if the request is valid
                rc = self._check_request_is_valid(reply, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    return rc

                # Update DB if handler handles the request successful
                rc = self._update_process_reply_info(reply, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    return rc

                # Check the request status
                rc, complete, status = self._check_process_reply_info(reply, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    return rc
                if not complete:
                    # The process does not still process the request.
                    return RcCode.SUCCESS
                reply.result = "OK" if status else "Failed"
                del reply.data["ready"]
                del reply.data["status"]
                del reply.data["process_id"]

                match reply.request:
                    case ConsoleServerEvent.CREATE_GROUP:
                        # Update the DB
                        rc = self._op_db.create_group(reply.data["group_name"], reply.data["role"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "Can not create the group in the operation DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "Can not create the group in the operation DB.")
                    case ConsoleServerEvent.DESTROY_GROUP:
                        # Update the DB
                        rc = self._op_db.destroy_group(reply.data["group_name"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "Can not destroy the group in the operation DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "Can not destroy the group in the operation DB.")
                    case ConsoleServerEvent.ADD_USER_ACCOUNT:
                        # Update the DB
                        rc = self._op_db.add_user_account(reply.data["username"], reply.data["role"], reply.data["group_name"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "Can not add the user in the operation DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "Can not add the user in the operation DB.")
                    case ConsoleServerEvent.DEL_USER_ACCOUNT:
                        # Update the DB
                        rc = self._op_db.del_user_account(reply.data["username"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "Can not delete the user in the operation DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "Can not delete the user in the operation DB.")
                    case ConsoleServerEvent.USER_JOIN_GROUP:
                        # Update the DB
                        rc = self._op_db.user_join_group(reply.data["username"], reply.data["group_name"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "User can not join the group in the DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "User can not join the group in the operation DB.")
                    case ConsoleServerEvent.USER_LEAVE_GROUP:
                        # Update the DB
                        rc = self._op_db.user_leave_group(reply.data["username"], reply.data["group_name"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "User can not leave the group in the DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "User can not leave the group in the DB.")
                    case ConsoleServerEvent.PORT_JOIN_GROUP:
                        # Update the DB
                        rc = self._config_db.port_join_group(reply.serial_port_id, reply.data["group_name"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "Port can not join the group in the operation DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "Port can not join the group in the operation DB.")
                    case ConsoleServerEvent.PORT_LEAVE_GROUP:
                        # Update the DB
                        rc = self._op_db.port_leave_group(reply.serial_port_id, reply.data["group_name"])
                        if rc != RcCode.SUCCESS:
                            self._logger.error(self._logger_system.set_logger_rc_code(
                                "Port can not leave the group in the operation DB.", rc=rc))
                            return self._reply_client_message(client_socket_obj, reply,
                                                              "failed", "Port can not leave the group in the operation DB.")
            case _:
                return RcCode.INVALID_VALUE

        # Reply the message to the user
        rc = self._reply_client_message(client_socket_obj, reply, reply.result, reply.data)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def process_message_queue_event(self):
        # handle the reply message sent from handler
        for process_id in range(MAX_HANDLER_PROCESS):
            # Receive the reply from the handler
            rc, client_reply = self._receive_queue_message(process_id)
            if rc != RcCode.SUCCESS:
                # No such data to read. Process next queue
                continue

            # Handle the reply
            rc = self._handle_client_reply(client_reply)
            if rc != RcCode.SUCCESS:
                continue
        return RcCode.SUCCESS
    
    ##########################################################################################################
    # Process Socket Data Relate API
    ##########################################################################################################

    def _valid_baud_rate_config(self, client_request, client_socket_obj):
        # Check the serial port ID is valid
        if client_request.serial_port_id > self._num_of_serial_port:
            self._logger.info(self._logger_system.set_logger_rc_code("Invalid serial prot number."))
            rc = self._reply_client_message(
                client_socket_obj, client_request, "failed", "Invalid serial prot number.")
            if rc != RcCode.SUCCESS:
                return rc
            return RcCode.INVALID_VALUE

        # Check the serial port ID is valid
        try:
            baud_rate = client_request.data["baud_rate"]
        except KeyError:
            self._logger.info(self._logger_system.set_logger_rc_code("Invalid the data of the serial prot ID."))
            rc = self._reply_client_message(
                client_socket_obj, client_request, "failed", "Invalid the data of the serial prot ID.")
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc
            return RcCode.INVALID_VALUE
        if baud_rate not in VALID_BAUD_RATE:
            self._logger.warning(self._logger_system.set_logger_rc_code("Not supported baud rate."))
            rc = self._reply_client_message(client_socket_obj, client_request,
                                            "failed", "Not supported baud rate.")
            if rc != RcCode.SUCCESS:
                return rc
            return RcCode.INVALID_VALUE
        return RcCode.SUCCESS

    def _sync_user_role(self, username):
        # Get the user role
        rc, role = self._config_db.get_user_account_role(username)
        if rc != RcCode.SUCCESS:
            return rc, None, "Can not get the user role."
        if role != "":
            return RcCode.SUCCESS, role, None
        # Determine the role of the user
        rc, group_list = self._config_db.get_user_group_list(username)
        if rc != RcCode.SUCCESS:
            return rc, None, "Can not get the users from the config DB."
        group_priority = UserRolePriorityDict[UserRole.ROLE_INVALID]
        for group_name in group_list:
            rc, group = self._config_db.get_group(group_name)
            if rc != RcCode.SUCCESS:
                return rc, None, "Can not get the group from the config DB."
            priority = UserRolePriorityDict[group["role"]]
            if group_priority > priority:
                group_priority = priority
        role = PriorityUserRole_dict[group_priority]
        if role == UserRole.ROLE_INVALID:
            return RcCode.FAILURE, None, "Can not determine the role for the user."
        return RcCode.SUCCESS, role, ""

    def _process_config_baud_rate(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process baud rate request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["baud_rate"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        # Check if the baud rate is valid
        rc = self._valid_baud_rate_config(client_request, client_socket_obj)
        if rc == RcCode.INVALID_VALUE:
            return RcCode.SUCCESS
        if rc != RcCode.SUCCESS:
            return rc

        # Check the target handler
        process_id = (client_request.serial_port_id - 1) % 8
        rc, message_queue = self._op_db.get_process_queue(process_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not gert the message queue.", rc=rc))
            return rc

        # Config the new baud rate in the DB
        rc = self._config_db.modify_serial_port(
            client_request.serial_port_id, "baud_rate", client_request.data["baud_rate"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not update the baud rate of the port in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not update the baud rate of the port in the config DB.")

        # Send the request to the handler
        handler_request = RequestMsg(
            client_request.request, client_request.serial_port_id, client_socket_fd, client_request.data)
        rc = message_queue.local_peer_send_msg(handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not send the message to the remote handler.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not send the message to remote handler.")

        # Store the request sending to the handler
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process config baud rate request successful."))
        return RcCode.SUCCESS
    
    def _process_config_alias_name(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process config alias name request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["alias_name"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        rc = self._config_db.modify_serial_port(client_request.serial_port_id, "alias_name", client_request.data["alias_name"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not update the alias name of the port in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not update the alias name of the port in the config DB.")

        rc = self._op_db.modify_serial_port(client_request.serial_port_id, "alias_name", client_request.data["alias_name"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not update the alias name of the port in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not update the alias name of the port in the DB.")

        rc = self._reply_client_message(client_socket_obj, client_request, "OK", client_request.data)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process config alias name request successful."))
        return RcCode.SUCCESS

    def _process_get_port_config(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process get port config request"))

        rc, serial_port_dict = self._config_db.get_serial_port(client_request.serial_port_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not get the port config in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the port config in the DB.")

        rc = self._reply_client_message(client_socket_obj, client_request, "OK", serial_port_dict)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process get port config request successful."))
        return RcCode.SUCCESS
    
    def _process_get_port_status(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process get port config request"))

        rc, serial_port_dict = self._op_db.get_serial_port(client_request.serial_port_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not get the port operation in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the port operation in the DB.")

        rc = self._reply_client_message(client_socket_obj, client_request, "OK", serial_port_dict)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process get port config request successful."))
        return RcCode.SUCCESS

    def _process_create_group(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process create group request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["group_name", "role"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        # Check if role is valid
        if not UserRole.is_valid(client_request.data["role"]):
            self._logger.error(self._logger_system.set_logger_rc_code("Invalid user role {}.".format(client_request.data["role"])))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Invalid user role.")

        # Update the DB
        rc = self._config_db.create_group(client_request.data["group_name"], client_request.data["role"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not create the group in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not create the group in the config DB.")

        # Check the target handler
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, message_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not get the message queue.", rc=rc))
                return rc

            # Send the request to the handler
            handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, client_request.data)
            rc = message_queue.local_peer_send_msg(handler_request)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not send the meesage to the remote handler.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Can not send the message to remote handler.")

        # Create reply list
        new_data = client_request.data
        new_data["ready"] = {}
        new_data["status"] = {}
        for i in range(0, MAX_HANDLER_PROCESS):
            new_data["ready"][i] = False
            new_data["status"][i] = False

        # Store the request sending to the handler
        handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, new_data)
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process add group request successful."))
        return RcCode.SUCCESS
    
    def _process_destroy_group(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process destroy group request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["group_name"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        group_name = client_request.data["group_name"]

        # Check if the user has been deleted from the group
        rc, user_dict = self._op_db.get_user_account()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not get the users in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the users in the DB.")
        for username in user_dict:
            if group_name in user_dict[username]["group_list"]:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "The group still has the user.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "The group still has the user.")

        rc, port_list = self._op_db.get_serial_port()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not get the serial ports in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the serial ports in the DB.")
        for serial_port_id in port_list:
            if group_name in port_list[serial_port_id]["group_list"]:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "The group still has the serial port.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "The group still has the serial port.")

        # Update the DB
        rc = self._config_db.destroy_group(group_name)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "Can not destroy the group in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not destroy the group in the config DB.")

        # Check the target handler
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, message_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not get the message queue.", rc=rc))
                return rc

            # Send the request to the handler
            handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, client_request.data)
            rc = message_queue.local_peer_send_msg(handler_request)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "Can not send the message to the remote handler.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Can not send the message to remote handler.")

        # Create reply list
        new_data = client_request.data
        new_data["ready"] = {}
        new_data["status"] = {}
        for i in range(0, MAX_HANDLER_PROCESS):
            new_data["ready"][i] = False
            new_data["status"][i] = False

        # Store the request sending to the handler
        handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, new_data)
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process destroy group request successful."))
        return RcCode.SUCCESS

    def _process_get_group_config(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process get group request"))

        group_name = None \
            if client_request.data is None or "group_name" not in client_request.data \
            else client_request.data["group_name"]

        rc, group_dict = self._config_db.get_group(group_name)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not get the group in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the group in the config DB.")

        rc = self._reply_client_message(client_socket_obj, client_request, "OK", group_dict)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process get port config request successful."))
        return RcCode.SUCCESS
    
    def _process_get_group_status(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process get group request"))

        group_name = None \
            if client_request.data is None or "group_name" not in client_request.data \
            else client_request.data["group_name"]

        rc, group_dict = self._op_db.get_group(group_name)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not get the group in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the group in the DB.")

        rc = self._reply_client_message(client_socket_obj, client_request, "OK", group_dict)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process get port config request successful."))
        return RcCode.SUCCESS
    
    def _process_add_user_account(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process add user request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["role", "group_name"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        username = client_request.data["username"]
        group_name = client_request.data["group_name"]
        role = ""

        # Check if role is valid
        if client_request.data["role"] != "":
            if not UserRole.is_valid(client_request.data["role"]):
                self._logger.error(self._logger_system.set_logger_rc_code("Invalid user role."))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Invalid user role.")
            role = UserRole(client_request.data["role"])

        # Update the DB
        rc = self._config_db.add_user_account(username, role, group_name)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the user in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not add the user in the config DB.")

        # Determine the role of the user
        role = client_request.data["role"]
        if role == "":
            rc, group = self._config_db.get_group(group_name)
            if rc != RcCode.SUCCESS:
                return RcCode.SUCCESS
            client_request.data["role"] = group["role"]

        # Check the target handler
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, message_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not get the message queue.", rc=rc))
                return rc

            # Send the request to the handler
            handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, client_request.data)
            rc = message_queue.local_peer_send_msg(handler_request)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not send the message to the remote handler.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Can not send the message to remote handler.")

        # Create reply list
        new_data = client_request.data
        new_data["ready"] = {}
        new_data["status"] = {}
        for i in range(0, MAX_HANDLER_PROCESS):
            new_data["ready"][i] = False
            new_data["status"][i] = False

        # Store the request sending to the handler
        handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, new_data)
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process add user request successful."))
        return RcCode.SUCCESS
    
    def _process_del_user_account(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process delete user request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, []):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        # Update the DB
        rc = self._config_db.del_user_account(client_request.data["username"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not delete the user in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not delete the user in the config DB.")

        # Check the target handler
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, message_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not gert the message queue.", rc=rc))
                return rc

            # Send the request to the handler
            handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, client_request.data)
            rc = message_queue.local_peer_send_msg(handler_request)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code(
                    "Can not send the message to the remote handler.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Can not send the message to remote handler.")

        # Create reply list
        new_data = client_request.data
        new_data["ready"] = {}
        new_data["status"] = {}
        for i in range(0, MAX_HANDLER_PROCESS):
            new_data["ready"][i] = False
            new_data["status"][i] = False

        # Store the request sending to the handler
        handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, new_data)
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process delete user request successful."))
        return RcCode.SUCCESS
    
    def _process_modify_user_role(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process modify user role request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["role"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        username = client_request.data["username"]
        role = client_request.data["role"]

        # Check if role is valid
        if role != "":
            if not UserRole.is_valid(role):
                self._logger.error(self._logger_system.set_logger_rc_code("Invalid user role. {}".format(role)))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Invalid user role.")

        # Update the DB
        rc = self._config_db.modify_user_account_role(username, role)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not modify the user in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not modify the user in the config DB.")

        # The group list has changed. Sync the user role
        rc, role, msg = self._sync_user_role(username)
        if rc != RcCode.SUCCESS:
            return self._reply_client_message(client_socket_obj, client_request, "failed", msg)
        self._logger.info(self._logger_system.set_logger_rc_code("The new role {} applies to the operation DB".format(role)))

        # Check the role has changed
        rc, original_role = self._op_db.get_user_account_role(username)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the user role in the operation DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the user role in the operation DB.")
        if original_role != role:
            rc = self._op_db.modify_user_account_role(username, role)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not set the user role in the operation DB.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Can not set the user role in the operation DB.")

        client_request.data["role"] = role
        rc = self._reply_client_message(client_socket_obj, client_request, "OK", client_request.data)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process modify user role request successful."))
        return RcCode.SUCCESS

    def _process_get_user_config(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process get user request"))

        username = None \
            if client_request.data is None or "username" not in client_request.data \
            else client_request.data["username"]
        rc, user_account = self._config_db.get_user_account(username)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not get the user in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the user in the config DB.")

        rc = self._reply_client_message(client_socket_obj, client_request, "OK", user_account)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process new get port config request successful."))
        return RcCode.SUCCESS
    
    def _process_get_user_status(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process get user request"))

        username = None \
            if client_request.data is None or "username" not in client_request.data \
            else client_request.data["username"]
        rc, user_account = self._op_db.get_user_account(username)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not get the user in the operation DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the user in the operation DB.")

        rc = self._reply_client_message(client_socket_obj, client_request, "OK", user_account)
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Process new get port config request successful."))
        return RcCode.SUCCESS
    
    def _process_user_join_group(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process user join group request {}".format(client_request.data)))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["username", "group_name"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        username = client_request.data["username"]
        group_name = client_request.data["group_name"]

        # Update the DB
        rc = self._config_db.user_join_group(username, group_name)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("User can not join the group in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "User can not join the group in the config DB.")

        # The group list has changed. Sync the user role
        rc, role, msg = self._sync_user_role(username)
        if rc != RcCode.SUCCESS:
            return self._reply_client_message(client_socket_obj, client_request, "failed", msg)

        # Check the role has changed
        rc, original_role = self._op_db.get_user_account_role(username)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not get the user role in the operation DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not get the user role in the operation DB.")
        if original_role != role:
            rc = self._op_db.modify_user_account_role(username, role)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not set the user role in the operation DB.", rc=rc))
                return self._reply_client_message(client_socket_obj, client_request,
                                                  "failed", "Can not set the user role in the operation DB.")

        # Check the target handler
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, message_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not gert the message queue.", rc=rc))
                return rc

            # Send the request to the handler
            handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, client_request.data)
            rc = message_queue.local_peer_send_msg(handler_request)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not send the message to the remote handler.", rc=rc))
                return self._reply_client_message(
                    client_socket_obj, client_request, "failed", "Can not send the message to remote handler.")

        # Create reply list
        new_data = client_request.data
        new_data["ready"] = {}
        new_data["status"] = {}
        for i in range(0, MAX_HANDLER_PROCESS):
            new_data["ready"][i] = False
            new_data["status"][i] = False

        # Store the request sending to the handler
        handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, new_data)
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process user join group request successful."))
        return RcCode.SUCCESS

    def _process_user_leave_group(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process user leave group request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["username", "group_name"]):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        # Update the DB
        rc = self._config_db.user_leave_group(client_request.data["username"], client_request.data["group_name"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("User can not leave the group in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "User can not leave the group in the config DB.")

        # Check the target handler
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, message_queue = self._op_db.get_process_queue(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not gert the message queue.", rc=rc))
                return rc

            # Send the request to the handler
            handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, client_request.data)
            rc = message_queue.local_peer_send_msg(handler_request)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not send the message to the remote handler.", rc=rc))
                return self._reply_client_message(
                    client_socket_obj, client_request, "failed", "Can not send the message to remote handler.")

        # Create reply list
        new_data = client_request.data
        new_data["ready"] = {}
        new_data["status"] = {}
        for i in range(0, MAX_HANDLER_PROCESS):
            new_data["ready"][i] = False
            new_data["status"][i] = False

        # Store the request sending to the handler
        handler_request = RequestMsg(client_request.request, None, client_socket_fd, client_request.exec_user, new_data)
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(
                client_socket_obj, client_request, "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process user leave group request successful."))
        return RcCode.SUCCESS

    def _process_port_join_group(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process port join group request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["group_name"], required_serial_port_id=True):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        # Update the DB
        rc = self._config_db.port_join_group(client_request.serial_port_id, client_request.data["group_name"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Port can not join the group in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Port can not join the group in the config DB.")

        # Check the target handler
        process_id = (client_request.serial_port_id - 1) % 8
        rc, message_queue = self._op_db.get_process_queue(process_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not gert the message queue.", rc=rc))
            return rc

        # Send the request to the handler
        handler_request = RequestMsg(
            client_request.request, client_request.serial_port_id, client_socket_fd, client_request.data)
        rc = message_queue.local_peer_send_msg(handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not send the message to the remote handler.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not send the message to remote handler.")

        # Store the request sending to the handler
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(
                client_socket_obj, client_request, "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process port join group request successful."))
        return RcCode.SUCCESS

    def _process_port_leave_group(self, client_socket_fd, client_request, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Process port leave group request"))

        # Parse the message and check if the Required parameters are in the message
        if not check_all_required_parameter(client_request, ["group_name"], required_serial_port_id=True):
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Missing the required parameters.")

        # Update the DB
        rc = self._config_db.port_leave_group(client_request.serial_port_id, client_request.data["group_name"])
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Port can not leave the group in the config DB.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Port can not leave the group in the config DB.")

        # Check the target handler
        process_id = (client_request.serial_port_id - 1) % 8
        rc, message_queue = self._op_db.get_process_queue(process_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not gert the message queue.", rc=rc))
            return rc

        # Send the request to the handler
        handler_request = RequestMsg(
            client_request.request, client_request.serial_port_id, client_socket_fd, client_request.data)
        rc = message_queue.local_peer_send_msg(handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not send the message to the remote handler.", rc=rc))
            return self._reply_client_message(
                client_socket_obj, client_request, "failed", "Can not send the message to remote handler.")

        # Store the request sending to the handler
        rc = self._op_db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            return self._reply_client_message(
                client_socket_obj, client_request, "failed", "Can not add the client request in the DB.")

        self._logger.info(self._logger_system.set_logger_rc_code("Process port leave group request successful."))
        return RcCode.SUCCESS

    def _check_permission(self, username, request):
        rc, role = self._op_db.get_user_account_role(username)
        if rc != RcCode.SUCCESS:
            return rc, None

        result = False
        match request:
            case ConsoleServerEvent.CREATE_GROUP | ConsoleServerEvent.DESTROY_GROUP | \
                 ConsoleServerEvent.ADD_USER_ACCOUNT | ConsoleServerEvent.DEL_USER_ACCOUNT | \
                 ConsoleServerEvent.MODIFY_USER_ROLE | ConsoleServerEvent.USER_JOIN_GROUP | \
                 ConsoleServerEvent.USER_LEAVE_GROUP | ConsoleServerEvent.PORT_JOIN_GROUP | \
                 ConsoleServerEvent.PORT_LEAVE_GROUP | \
                 ConsoleServerEvent.GET_GROUP_CONFIG | ConsoleServerEvent.GET_GROUP_STATUS | \
                 ConsoleServerEvent.GET_USER_CONFIG | ConsoleServerEvent.GET_USER_STATUS:
                if role == UserRole.ROLE_ADMIN:
                    result = True
            case ConsoleServerEvent.SET_BAUD_RATE | ConsoleServerEvent.SET_ALIAS_NAME:
                if role == UserRole.ROLE_ADMIN or UserRole.ROLE_OPERATOR:
                    result = True
            case ConsoleServerEvent.GET_PORT_CONFIG | ConsoleServerEvent.GET_PORT_STATUS:
                result = True
        return RcCode.SUCCESS, result

    def _handler_server_message(self, msg_str, client_socket_fd, client_socket_obj):
        # Resolve the replay message received from the user
        self._logger.info(self._logger_system.set_logger_rc_code("Start process the request {}".format(msg_str)))
        rc, msg_dict = msg_deserialize(msg_str)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not serialize the data.", rc=rc))
            return self._reply_client_message(client_socket_obj, msg_str,
                                              "failed", "Can not serialize the data.")
        self._logger.info(self._logger_system.set_logger_rc_code("resolve the request"))
        client_request = RequestMsg()
        rc = client_request.set_msg(msg_dict)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Invalid message format.", rc=rc))
            return self._reply_client_message(client_socket_obj, msg_str,
                                              "failed", "Invalid message format.")

        # Check permission
        rc, result = self._check_permission(client_request.exec_user, client_request.request)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not check the user permission.", rc=rc))
            return self._reply_client_message(client_socket_obj, client_request,
                                              "failed", "Can not check the user permission.")

        if not result:
            self._logger.error(self._logger_system.set_logger_rc_code(
                "User {} does not have permission to execute the request {}".format(client_request.exec_user, client_request.request)))
            return self._reply_client_message(client_socket_obj, msg_str,
                                              "failed",
                                              "User {} does not have permission to execute the request {}".format(client_request.exec_user, client_request.request))

        call_func = None
        # Dispatch the request
        match client_request.request:
            case ConsoleServerEvent.SET_BAUD_RATE:
                call_func = self._process_config_baud_rate
            case ConsoleServerEvent.SET_ALIAS_NAME:
                call_func = self._process_config_alias_name
            case ConsoleServerEvent.GET_PORT_CONFIG:
                call_func = self._process_get_port_config
            case ConsoleServerEvent.GET_PORT_STATUS:
                call_func = self._process_get_port_status
            case ConsoleServerEvent.CREATE_GROUP:
                call_func = self._process_create_group
            case ConsoleServerEvent.DESTROY_GROUP:
                call_func = self._process_destroy_group
            case ConsoleServerEvent.GET_GROUP_CONFIG:
                call_func = self._process_get_group_config
            case ConsoleServerEvent.GET_GROUP_STATUS:
                call_func = self._process_get_group_status
            case ConsoleServerEvent.ADD_USER_ACCOUNT:
                call_func = self._process_add_user_account
            case ConsoleServerEvent.DEL_USER_ACCOUNT:
                call_func = self._process_del_user_account
            case ConsoleServerEvent.MODIFY_USER_ROLE:
                call_func = self._process_modify_user_role
            case ConsoleServerEvent.USER_JOIN_GROUP:
                call_func = self._process_user_join_group
            case ConsoleServerEvent.USER_LEAVE_GROUP:
                call_func = self._process_user_leave_group
            case ConsoleServerEvent.PORT_JOIN_GROUP:
                call_func = self._process_port_join_group
            case ConsoleServerEvent.PORT_LEAVE_GROUP:
                call_func = self._process_port_leave_group
            case ConsoleServerEvent.GET_USER_CONFIG:
                call_func = self._process_get_user_config
            case ConsoleServerEvent.GET_USER_STATUS:
                call_func = self._process_get_user_status
            case ConsoleServerEvent.INIT_HANDLER | ConsoleServerEvent.INIT_SERIAL_PORT | ConsoleServerEvent.CONNECT_SERIAL_PORT:
                return RcCode.PERMISSION_DENIED
        
        rc = call_func(client_socket_fd, client_request, client_socket_obj)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS

    def _close_client_socket(self, client_socket_obj):
        # Remove the EPOLL
        self._server_mgmt_epoll.unregister(client_socket_obj.uds_client_socket_fd_get())

        # Delete the socket from the DB
        rc = self._op_db.del_client_socket(client_socket_obj.uds_client_socket_fd_get())
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not delete the client socket from the socket.", rc=rc))
            return rc

        # Close the socket
        rc = client_socket_obj.uds_client_socket_close()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not close the client socket.", rc=rc))
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("Remove socket completely.", rc=rc))
        return RcCode.SUCCESS
    
    def _accept_client_socket(self):
        rc, client_socket_obj = self._uds_server_mgmt_socket.uds_server_socket_accept()
        if rc != RcCode.SUCCESS:
            # Ignore this event, process next event.
            self._logger.warning(
                self._logger_system.set_logger_rc_code(
                    "A client connected with server failed.", rc=rc))
            return RcCode.SUCCESS
        else:
            self._logger.info(
                self._logger_system.set_logger_rc_code("A client connected with server.", rc=rc))

        # Register the socket to EPOLL to monitor event
        socket_fd = client_socket_obj.fileno()
        self._server_mgmt_epoll.register(socket_fd, select.EPOLLIN)

        # Save the socket in the DB
        rc = self._op_db.add_client_socket(
            socket_fd, UnixDomainConnectedClientSocket(client_socket_obj, self._logger_system))
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not add the client socket in the DB.", rc=rc))
            self._server_mgmt_epoll.unregister(socket_fd)
            rc = self._uds_server_mgmt_socket.uds_client_socket_close(client_socket_obj)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not close the client socket.", rc=rc))
                return rc
        return RcCode.SUCCESS

    def _receive_client_data(self, socket_fd):
        # Get the socket object
        rc, client_socket_obj = self._op_db.get_client_socket(socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not find the socket in the DB.", rc=rc))
            self._server_mgmt_epoll.unregister(socket_fd)
            return RcCode.SUCCESS

        # Receive the data from the socket
        rc, data = client_socket_obj.uds_client_socket_recv(1024)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not receive the data from the socket", rc=rc))
            rc = self._close_client_socket(client_socket_obj)
            if rc != RcCode.SUCCESS:
                return rc
            return RcCode.SUCCESS

        # If the socket receive the data successful but no data can be processed, it means that socket has closed
        if data == b"":
            self._logger.info(self._logger_system.set_logger_rc_code("Client socket has been closed", rc=rc))
            rc = self._close_client_socket(client_socket_obj)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not delete the socket", rc=rc))
                return rc
            return RcCode.SUCCESS

        # Process the data
        rc = self._handler_server_message(data.decode('utf-8'), socket_fd, client_socket_obj)
        if rc != RcCode.SUCCESS:
            rc = self._close_client_socket(client_socket_obj)
            if rc != RcCode.SUCCESS:
                return rc
        return RcCode.SUCCESS

    def process_server_socket_event(self):
        events = self._server_mgmt_epoll.poll(self._processing_time)
        for socket_fd, event in events:
            if socket_fd == self._server_mgmt_socket_fd:
                rc = self._accept_client_socket()
                if rc != RcCode.SUCCESS:
                    return rc
            elif event & select.EPOLLIN:
                rc = self._receive_client_data(socket_fd)
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS
    
    ##########################################################################################################
    # Daemon Main Process
    ##########################################################################################################

    def daemon_main(self):
        # Communicate with the user by socket
        rc = self.process_server_socket_event()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Process the data reading from socket failed.", rc=rc))
            return rc

        # Communicate with the handler by message queue
        rc = self.process_message_queue_event()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Process the data reading from message queue failed.", rc=rc))
            return rc

        return RcCode.SUCCESS

    def run(self):
        # initialize the server first
        rc = self.init_console_server()
        if rc != RcCode.SUCCESS:
            return
        self._logger.info(self._logger_system.set_logger_rc_code("Init server completely.", rc=rc))
        
        rc = self._init_handle_serial_port()
        if rc != RcCode.SUCCESS:
            return
        self._logger.info(self._logger_system.set_logger_rc_code("Init serial port completely.", rc=rc))

        rc = self._init_handle_admin_user()
        if rc != RcCode.SUCCESS:
            return
        self._logger.info(self._logger_system.set_logger_rc_code("Init default account completely.", rc=rc))


        # Daemon main process
        while True:
            try:
                start_time = time.perf_counter()
                rc = self.daemon_main()
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("The daemon occurs the error.", rc=rc))
                end_time = time.perf_counter()
                self._processing_time = end_time - start_time
            except Exception as e:
                self._logger.critical(
                        self._logger_system.set_logger_rc_code(e))
