import multiprocessing
import select
import time

from src.common.logger_system import LoggerSystem
from src.common.msg import ReplyMsg, RequestMsg, msg_deserialize, msg_serialize
from src.common.msg_queue import BiMsgQueue
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainServerSocket
from src.console_server.processing.console_server_handler import ConsolerServerHandler


VALID_BAUDRATE = [50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 
                  230400, 460800, 500000, 576000, 921600, 1000000, 1152000, 1500000, 2000000, 2500000, 3000000, 3500000, 4000000]


MAX_HANDLER_PROCESS =  8


class _ConsoleServer:
    def __init__(self):
        self._client_socket_dict = {}
        self._process_handler_dict = {}
        self._process_queue_dict = {}
        self._serial_port_group_dict = {}
        self._serial_port_dict = {}

    def add_client_socket(self, client_socket):
        socket_fd = client_socket.fileno()
        if socket_fd in self._client_socket_dict:
            return RcCode.DATA_EXIST
        self._client_socket_dict[socket_fd] = {}
        self._client_socket_dict[socket_fd]["socket_obj"] = client_socket
        return RcCode.SUCCESS
    
    def del_client_socket(self, client_socket_fd):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND
        del self._client_socket_dict[client_socket_fd]
        return RcCode.SUCCESS

    def get_client_socket(self, client_socket_fd):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_EXIST
        return RcCode.SUCCESS, self._client_socket_dict[client_socket_fd]["socket_obj"]
    
    def add_client_request(self, client_socket_fd, request):
        if client_socket_fd not in self._client_socket_dict:
            return RcCode.DATA_NOT_FOUND
        self._client_socket_dict[client_socket_fd]["request"]  = request
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
        if process_id not in self._process_handler_dict:
            return RcCode.DATA_NOT_FOUND, None
        if process_id is not None:
            return self._process_handler_dict[process_id]
        return RcCode.SUCCESS, self._process_handler_dict

    def get_process_queue(self, process_id=None):
        if process_id not in self._process_handler_dict:
            return RcCode.DATA_NOT_FOUND, None
        if process_id is not None:
            return RcCode.SUCCESS, self._process_queue_dict[process_id]
        return RcCode.SUCCESS, self._process_queue_dict
    
    def set_handler_init_status(self, process_id, status):
        if process_id not in self._process_handler_dict:
            return RcCode.DATA_NOT_FOUND
        self._process_handler_dict[process_id]["init_done"] = True
        return RcCode.SUCCESS
    
    def get_handler_init_status(self, process_id):
        if process_id not in self._process_handler_dict:
            return RcCode.DATA_NOT_FOUND
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

    def add_serial_port(self, serial_port_id, baud_rate, alias_name):
        if serial_port_id in self._serial_port_dict:
            return RcCode.DATA_EXIST
        self._process_handler_dict[serial_port_id] = {
            "baud_rate": 115200,
            "alias_name": alias_name
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
        if field not in ["baud_rate", "alias_name"]:
            return RcCode.INVALID_VALUE
        self._serial_port_dict[serial_port_id][field] = data
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

        self._db = _ConsoleServer()

    def init_console_server(self):
        # init the logger system
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger = self._logger_system.get_logger()

        # Init the Unix doamin server socket
        self._uds_server_mgmt_socket = UnixDomainServerSocket(self._max_client, self._server_mgmt_socket_file_path, self._logger_system)
        rc = self._uds_server_mgmt_socket.uds_server_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not init the server socket.", rc=rc))
        rc, server_socket_fd = self._uds_server_mgmt_socket.uds_server_socket_fd_get()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not get the server socket FD.", rc=rc))
            return rc
        self._server_mgmt_socket_fd = server_socket_fd
            
        # Init the epoll
        self._server_mgmt_epoll = select.epoll()
        self._server_mgmt_epoll.register(self._server_mgmt_socket_fd, select.EPOLLIN)

        # Init handler process
        serial_port_group = [
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {}
        ]
        for serial_port_id in range(1, self._num_of_serial_port + 1):
            serial_port_group[(serial_port_id - 1) % MAX_HANDLER_PROCESS][serial_port_id] = {"dev_tty_id": serial_port_id - 1, "baud_rate": 115200}
        
        for process_id in range(0, MAX_HANDLER_PROCESS):
            self._logger.info(
                self._logger_system.set_logger_rc_code("Init the handler to service port {}".format(",".join(map(str, serial_port_group[process_id]))), rc=rc))
            msg_queue = BiMsgQueue()
            process_handler = ConsolerServerHandler(process_id, msg_queue.remote_peer_send_msg, msg_queue.remote_peer_receive_msg)
            rc = self._db.add_process_handler(process_id, process_handler, msg_queue)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not add the handler to the DB.", rc=rc))
                return rc
            process_handler.start()
            
            request = RequestMsg("init_serial_port", data={"serial_port_config": serial_port_group[process_id]})
            rc = msg_queue.local_peer_send_msg(request)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not send the port initialize request.", rc=rc))
                return rc
        self._logger.info(
            self._logger_system.set_logger_rc_code("Waiting the handler to process event", rc=rc))
        
        count = 0
        while count < 5:
            for process_id in range(0, MAX_HANDLER_PROCESS):
                rc, status = self._db.get_handler_init_status(process_id)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
                    return rc

                rc, processs_msg_queue = self._db.get_process_queue(process_id)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
                    return rc
                if not status:
                    rc, reply = processs_msg_queue.local_peer_receive_msg()
                    if rc != RcCode.SUCCESS:
                        continue
                    if reply.request == "init_serial_port" and self.result == "OK":
                        rc, status = self._db.set_handler_init_status(process_id, True)
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code("Can not set the process init status.", rc=rc))
                            return rc
            count = count + 1
            time.sleep(1)

        # Check all process has init done
        failed_process_id_list = []
        for process_id in range(0, MAX_HANDLER_PROCESS):
            rc, status = self._db.get_handler_init_status(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
                return rc

            if not status:
                failed_process_id_list.append(process_id)
        if len(failed_process_id_list):
            self._logger.error(
                self._logger_system.set_logger_rc_code("Handler {} init fail.".format(failed_process_id_list), rc=rc))
            return RcCode.FAILURE

        self._logger.info(self._logger_system.set_logger_rc_code("Init consoel server complete."))
        return RcCode.SUCCESS
    
    def _reply_client_message(self, client_socket, request, result, data):
        # Create reply message
        reply_msg = ReplyMsg(request, result, data)
        rc, msg_dict = reply_msg.get_msg()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not convert the data to the dictionary.", rc=rc))
            return rc
        
        # Message serialize
        rc, msg_str = msg_serialize(msg_dict)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not serialize the data.", rc=rc))
            return rc
        
        # Send the total size of the message by socket
        data_len = len(msg_str)
        data_byte = data_len.to_bytes(4, byteorder='little')
        rc = self._uds_server_mgmt_socket.uds_client_socket_send(client_socket, data_byte)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not serialize the data.", rc=rc))
            return rc
        
        # Send the message by socket
        rc = self._uds_server_mgmt_socket.uds_client_socket_send(client_socket, msg_str)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not serialize the data.", rc=rc))
            return rc
        return RcCode.SUCCESS
    
    def process_message_queue_event(self):
        rc, processs_msg_queue_dict = self._db.get_process_queue()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
            return rc
        for process_id in processs_msg_queue_dict:
            msg_queue = processs_msg_queue_dict[process_id]

            # Receive the reply from the handler
            rc, client_reply = msg_queue.local_peer_receive_msg()
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not receive the meesage from the remote handler.", rc=rc))
                return rc

            # Resolve the replay message received from the handler
            handler_reply = ReplyMsg()
            rc = handler_reply.set_msg(client_reply)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not parse the reply message.", rc=rc))
                return rc
            
            # Get the socket object
            rc, client_socket_obj = self._db.get_client_socket(handler_reply.socket_fd)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not find the socket in the DB.", rc=rc))
                return rc

            # Get the source request
            rc, requst_msg = self._db.get_client_request(handler_reply.socket_fd)
            if rc != RcCode.SUCCESS:
                self._logger.info(self._logger_system.set_logger_rc_code("Verify the data failed.", rc=rc))
                rc = self._reply_client_message(client_socket_obj, handler_reply.request, "failed", "Verify the data failed.")
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc
                return RcCode.SUCCESS

            # Check if the request data is the same with the handler reply
            if requst_msg.request != handler_reply.requst_msg or requst_msg.socket_fd != handler_reply.socket_fd or \
                requst_msg.serial_port_id != handler_reply:
                self._logger.info(self._logger_system.set_logger_rc_code(".", rc=rc))
                rc = self._reply_client_message(client_socket_obj, handler_reply.request, "failed", "Invalid serial prot number.")
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc
                return RcCode.SUCCESS

            # Reply the message to the user
            rc = self._reply_client_message(client_socket_obj, requst_msg.request, requst_msg.result, requst_msg.data)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc
        return RcCode.SUCCESS

    def _handler_server_message(self, msg_str, client_socket_obj):
        client_socket_fd = client_socket_obj.fileno()
        # Resolve the replay message received from the user
        rc, msg_dict = msg_deserialize(msg_str)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not serialize the data.", rc=rc))
            return rc
        client_request = RequestMsg()
        rc = client_request.set_reply_msg(msg_dict)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Invalid message format.", rc=rc))
            return rc
        
        # Dispath the request
        match client_request.request:
            case "connect_serial_port":
                # Get the client socket
                rc, socket_obj = self._db.get_client_socket(client_socket_fd)
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not find the client socket object.", rc=rc))
                    return rc

                # Check the seiral port ID is valid
                if client_request.serial_port_id > self._num_of_serial_port:
                    self._logger.info(self._logger_system.set_logger_rc_code("Invalid serial prot number.", rc=rc))
                    rc = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Invalid serial prot number.")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc
                    return RcCode.SUCCESS
                
                # Add the socket obj information
                client_request.data["socket_obj"] = socket_obj

                # Send the request to the handler
                handler_request = RequestMsg(client_request.request, client_request.serial_port_id, client_socket_fd, client_request.data)
                rc = self._msg_queue.local_peer_send_msg(handler_request)
                if rc!= RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not send the meesage to the remote handler.", rc=rc))
                    rc_reply_msg = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Can not send the meesage to remote handler.")
                    if rc_reply_msg != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc_reply_msg
                    return rc

                # Store the request sending to the handler
                rc = self._db.add_client_request(client_socket_fd, handler_request)
                if rc!= RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
                    rc_reply_msg = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Can not add the client request in the DB.")
                    if rc_reply_msg != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc_reply_msg
                    return rc
            case "config_baud_rate":
                # Check the seiral port ID is valid
                if client_request.serial_port_id > self._num_of_serial_port:
                    self._logger.info(self._logger_system.set_logger_rc_code("Invalid serial prot number.", rc=rc))
                    rc = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Invalid serial prot number.")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc
                    return RcCode.SUCCESS

                # Check the seiral port ID is valid
                try:
                    baud_rate = client_request.data["baud_rate"]
                except KeyError:
                    self._logger.info(self._logger_system.set_logger_rc_code("Invalid the data of the serial prot ID.", rc=rc))
                    rc = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Invalid the data of the serial prot ID.")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc
                    return RcCode.INVALID_VALUE
                if baud_rate not in VALID_BAUDRATE:
                    self._logger.info(self._logger_system.set_logger_rc_code("Not supported baud rate.", rc=rc))
                    rc = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Not supported baud rate.")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc
                    return RcCode.SUCCESS
                
                # Send the request to the handler
                handler_request = RequestMsg(client_request.request, client_request.serial_port_id, client_socket_fd, client_request.data)
                rc = self._msg_queue.local_peer_send_msg(handler_request)
                if rc!= RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not send the meesage to the remote handler.", rc=rc))
                    rc_reply_msg = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Can not send the meesage to remote handler.")
                    if rc_reply_msg != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc_reply_msg
                    return rc
                
                # Store the request sending to the handler
                rc = self._db.add_client_request(client_socket_fd, handler_request)
                if rc!= RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
                    rc_reply_msg = self._reply_client_message(client_socket_obj, client_request.request, "failed", "Can not add the client request in the DB.")
                    if rc_reply_msg != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                        return rc_reply_msg
                    return rc
            case "get_port_config":
                rc, serial_port_dict = self._db.get_serial_port()
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not get the serial ports.", rc=rc))
                    return rc
                rc, reply_str = msg_serialize(serial_port_dict)
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not serialize serial port config.", rc=rc))
                    return rc
                rc_reply_msg = self._reply_client_message(client_socket_obj, client_request.request, "OK", reply_str)
                if rc_reply_msg != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc_reply_msg
                return rc

        return RcCode.SUCCESS
    
    def _close_client_socket(self, client_socket_obj):
        self._server_mgmt_epoll.unregister(client_socket_obj.fileno())
        rc = self._uds_server_socket.uds_client_socket_close(client_socket_obj)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not close the client socket.", rc=rc))
            return rc

        rc = self._db.del_client_socket(client_socket_obj.fileno())
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not delete the client socket from the socket.", rc=rc))
            return rc
        return RcCode.SUCCESS

    def process_server_socket_event(self):
        events = self._server_mgmt_epoll.poll(0.01)
        for socket_fd, event in events:
            if socket_fd == self._server_mgmt_socket_fd:
                rc, client_socket_obj = self._uds_server_socket.uds_server_socket_accept()
                if rc != RcCode.SUCCESS:
                    # Ignore this event, process next event.
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code(
                            "A clinet connected with server failed.", rc=rc))
                    continue

                # Register the socket to EPOLL to monitor event
                socket_fd = client_socket_obj.fileno()
                self._server_mgmt_epoll.register(socket_fd, select.EPOLLIN)

                # Save the socket in the DB
                rc = self._db.add_client_socket(client_socket_obj)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not add the client socket in the DB.", rc=rc))
                    self._server_mgmt_epoll.unregister(socket_fd)
                    rc = self._uds_server_socket.uds_client_socket_close(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not close the client socket.", rc=rc))
                        return rc
            elif event & select.EPOLLIN:
                # Get the socket object
                rc, client_socket_obj = self._db.get_client_socket(socket_fd)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not find the socket in the DB.", rc=rc))
                    self._server_mgmt_epoll.unregister(socket_fd)
                    continue

                # Receive the data from the socket
                rc, data = self._uds_server_mgmt_socket.uds_client_socket_recv(client_socket_obj, 1024)
                if rc != RcCode.SUCCESS or data == "":
                    # 1. Can not receive the data from the socket. Close socket and remove the socket from the DB.
                    # 2. Socket has closed. Close socket and remove the socket from the DB.
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not receive the data from the socket.", rc=rc))
                    rc = self._close_client_socket(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        return rc
                    
                # Process the data
                rc = self._handler_server_message(data, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    # Can not receive the data from the socket. Close socket and remove the socket from the DB.
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not receive the data from the socket.", rc=rc))
                    rc = self._close_client_socket(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        return rc
        return RcCode.SUCCESS

    def daemon_main(self):
        rc = self.process_message_queue_event()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Process the data reading from message queue failed.", rc=rc))
            return rc
        
        rc - self.process_server_socket_event()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Process the data reading from socket failed.", rc=rc))
            return rc

        return RcCode.SUCCESS

    def run(self):
        # initialize the server first
        rc = self.init_console_server()
        if rc != RcCode.SUCCESS:
            return

        # Daemon main process
        while True:
            rc = self.daemon_main()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The daemon occurs the error.", rc=rc))