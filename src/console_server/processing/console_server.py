import multiprocessing
import select
import time

from src.common.logger_system import LoggerSystem
from src.common.msg import ReplyMsg, RequestMsg, msg_deserialize, msg_serialize
from src.common.msg_queue import BiMsgQueue
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainServerSocket, UnixDomainConnectedClientSocket
from src.console_server.processing.console_server_handler import ConsolerServerHandler


VALID_BAUD_RATE = [50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800, 9600, 19200, 38400, 57600, 115200,
                   230400, 460800, 500000, 576000, 921600, 1000000, 1152000, 1500000, 2000000, 2500000, 3000000, 3500000, 4000000]


MAX_HANDLER_PROCESS =  8


class _ConsoleServer:
    def __init__(self):
        self._client_socket_dict = {}
        self._process_handler_dict = {}
        self._process_queue_dict = {}
        self._serial_port_group_dict = {}
        self._serial_port_dict = {}

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
            return RcCode.DATA_EXIST, None
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

    def add_serial_port(self, serial_port_id, baud_rate, alias_name, dev_tty):
        group_id = (serial_port_id - 1) % 8
        if group_id not in self._serial_port_group_dict:
            return RcCode.DATA_NOT_FOUND
        if serial_port_id in self._serial_port_dict:
            return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id] = {
            "baud_rate": baud_rate,
            "alias_name": alias_name,
            "dev_tty_id": dev_tty
        }
        self._serial_port_group_dict[group_id][serial_port_id] = self._serial_port_dict[serial_port_id]
        return RcCode.SUCCESS
    
    def del_serial_port(self, serial_port_id):
        group_id = (serial_port_id - 1) % 8
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_dict[serial_port_id]
        del self._serial_port_group_dict[group_id][serial_port_id]
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

        self._db = _ConsoleServer()

    def init_console_server(self):
        # init the logger system
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger = self._logger_system.get_logger()

        # Init the Unix domain server socket
        self._uds_server_mgmt_socket = UnixDomainServerSocket(
            self._max_client, self._server_mgmt_socket_file_path, self._logger_system)
        rc = self._uds_server_mgmt_socket.uds_server_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not init the server socket.", rc=rc))
        server_socket_fd = self._uds_server_mgmt_socket.uds_server_socket_fd_get()
        self._server_mgmt_socket_fd = server_socket_fd
            
        # Init the epoll
        self._server_mgmt_epoll = select.epoll()
        self._server_mgmt_epoll.register(self._server_mgmt_socket_fd, select.EPOLLIN)

        # Init handler process
        for group_id in range(8):
            rc = self._db.add_serial_port_group(group_id)
            if rc != RcCode.SUCCESS:
                return rc
        for serial_port_id in range(1, self._num_of_serial_port + 1):
            rc = self._db.add_serial_port(
                serial_port_id, 115200, "COM{}".format(serial_port_id), serial_port_id - 1)
            if rc != RcCode.SUCCESS:
                return rc
        
        for process_id in range(0, MAX_HANDLER_PROCESS):
            msg_queue = BiMsgQueue(tx_blocking=False, tx_timeout=None, rx_blocking=False, rx_timeout=None)
            rc = msg_queue.init_queue()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not init the message queue.", rc=rc))
                return rc
            process_handler = ConsolerServerHandler(process_id, msg_queue.remote_peer_send_msg, msg_queue.remote_peer_receive_msg)
            rc = self._db.add_process_handler(process_id, process_handler, msg_queue)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not add the handler to the DB.", rc=rc))
                return rc
            process_handler.start()

            rc, serial_port_group =  self._db.get_serial_port_group(process_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not get the serial port group from the DB.", rc=rc))
                return rc
            
            request = RequestMsg("init_serial_port", data={"serial_port_config": serial_port_group})
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
            break_check = True
            for process_id in range(0, MAX_HANDLER_PROCESS):
                rc, status = self._db.get_handler_init_status(process_id)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
                    return rc

                rc, process_msg_queue = self._db.get_process_queue(process_id)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
                    return rc
                if not status:
                    rc, reply = process_msg_queue.local_peer_receive_msg()
                    if rc != RcCode.SUCCESS:
                        self._logger.info(
                            self._logger_system.set_logger_rc_code("No message receive", rc=rc))
                    else:
                        if reply.request == "init_serial_port" and reply.result == "OK":
                            rc = self._db.set_handler_init_status(process_id, True)
                            if rc != RcCode.SUCCESS:
                                self._logger.error(
                                    self._logger_system.set_logger_rc_code("Can not set the process init status.", rc=rc))
                                return rc
                break_check = break_check and status
            if break_check:
                break
            count = count + 1
            time.sleep(1)

        self._logger.info(
            self._logger_system.set_logger_rc_code("Waiting the handler done!", rc=rc))

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

        self._logger.info(self._logger_system.set_logger_rc_code("Init console server complete."))
        return RcCode.SUCCESS
    
    def _reply_client_message(self, client_socket_obj, request, result, data):
        # Create reply message
        reply_msg = ReplyMsg(request, None, None, data, result)
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
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not serialize the data.", rc=rc))
            return rc

        # Send the message by socket
        rc = client_socket_obj.uds_client_socket_send(bytes(msg_str, 'utf-8'))
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not serialize the data.", rc=rc))
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("Reply client completely.", rc=rc))
        return RcCode.SUCCESS
    
    def process_message_queue_event(self):
        rc, process_msg_queue_dict = self._db.get_process_queue()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not find the process handler.", rc=rc))
            return rc
        for process_id in process_msg_queue_dict:
            msg_queue = process_msg_queue_dict[process_id]

            # Receive the reply from the handler
            rc, client_reply = msg_queue.local_peer_receive_msg()
            if rc != RcCode.SUCCESS:
                # No such data to read. Process next queue
                continue
            
            # Get the socket object
            rc, client_socket_obj = self._db.get_client_socket(client_reply.socket_fd)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not find the socket in the DB.", rc=rc))
                return rc

            # Get the source request
            rc, request_msg = self._db.get_client_request(client_reply.socket_fd)
            if rc != RcCode.SUCCESS:
                self._logger.info(self._logger_system.set_logger_rc_code("Get origin request fail.", rc=rc))
                rc = self._reply_client_message(client_socket_obj, client_reply.request, "failed", "Verify the data failed.")
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc
                return RcCode.SUCCESS

            # Check if the request data is the same with the handler reply
            if request_msg.request != client_reply.request or request_msg.socket_fd != client_reply.socket_fd or \
                request_msg.serial_port_id != client_reply.serial_port_id:
                rc = self._reply_client_message(
                    client_socket_obj, client_reply.request, "failed", "Invalid serial prot number.")
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc
                return RcCode.SUCCESS

            # Update DB if handler handles the request successful
            if client_reply.result != "OK":
                self._logger.error(self._logger_system.set_logger_rc_code("Handler the request failed.", rc=rc))
                rc = self._reply_client_message(
                    client_socket_obj, client_reply.request, "failed", "Handler the request failed.")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc
                return RcCode.SUCCESS
            match client_reply.request:
                case "config_baud_rate":
                    rc = self._db.modify_serial_port(
                        client_reply.serial_port_id, "baud_rate", client_reply.data["baud_rate"])
                    if rc != RcCode.SUCCESS:
                        self._logger.error(self._logger_system.set_logger_rc_code("Update the DB fail.", rc=rc))
                        rc = self._reply_client_message(
                            client_socket_obj, client_reply.request, "failed", "Update the DB fail.")
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                            return rc
                        return RcCode.SUCCESS

            # Delete the source request
            rc = self._db.del_client_request(client_reply.socket_fd)
            if rc != RcCode.SUCCESS:
                self._logger.info(self._logger_system.set_logger_rc_code("Delete origin request fail.", rc=rc))
                rc = self._reply_client_message(
                    client_socket_obj, client_reply.request, "failed", "Delete original request failed.")
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc
                return RcCode.SUCCESS

            # Reply the message to the user
            rc = self._reply_client_message(client_socket_obj, client_reply.request, client_reply.result, client_reply.data)
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc
        return RcCode.SUCCESS

    def _process_config_baud_rate_request(self, client_socket_fd, client_request, client_socket_obj):
        # Check the serial port ID is valid
        if client_request.serial_port_id > self._num_of_serial_port:
            self._logger.info(self._logger_system.set_logger_rc_code("Invalid serial prot number."))
            rc = self._reply_client_message(client_socket_obj, client_request.request, "failed",
                                            "Invalid serial prot number.")
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc
            return RcCode.SUCCESS

        # Check the serial port ID is valid
        try:
            baud_rate = client_request.data["baud_rate"]
        except KeyError:
            self._logger.info(self._logger_system.set_logger_rc_code("Invalid the data of the serial prot ID."))
            rc = self._reply_client_message(client_socket_obj, client_request.request, "failed",
                                            "Invalid the data of the serial prot ID.")
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc
            return RcCode.INVALID_VALUE
        if baud_rate not in VALID_BAUD_RATE:
            self._logger.warning(self._logger_system.set_logger_rc_code("Not supported baud rate."))
            rc = self._reply_client_message(
                client_socket_obj, client_request.request, "failed", "Not supported baud rate.")
            if rc != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc
            return RcCode.SUCCESS

        # Check the target handler
        process_id = (client_request.serial_port_id - 1) % 8
        rc, message_queue = self._db.get_process_queue(process_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not gert the message queue.", rc=rc)
            )
            return rc

        # Send the request to the handler
        handler_request = RequestMsg(client_request.request, client_request.serial_port_id, client_socket_fd,
                                     client_request.data)
        rc = message_queue.local_peer_send_msg(handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not send the meesage to the remote handler.", rc=rc))
            rc_reply_msg = self._reply_client_message(client_socket_obj, client_request.request, "failed",
                                                      "Can not send the meesage to remote handler.")
            if rc_reply_msg != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc_reply_msg
            return rc

        # Store the request sending to the handler
        rc = self._db.add_client_request(client_socket_fd, handler_request)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not add the client request in the DB.", rc=rc))
            rc_reply_msg = self._reply_client_message(client_socket_obj, client_request.request, "failed",
                                                      "Can not add the client request in the DB.")
            if rc_reply_msg != RcCode.SUCCESS:
                self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                return rc_reply_msg
            return rc
        return RcCode.SUCCESS

    def _handler_server_message(self, msg_str, client_socket_fd, client_socket_obj):
        self._logger.info(self._logger_system.set_logger_rc_code("Start process the request {}".format(msg_str)))
        # Resolve the replay message received from the user
        rc, msg_dict = msg_deserialize(msg_str)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not serialize the data.", rc=rc))
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("resolve the request"))
        client_request = RequestMsg()
        rc = client_request.set_msg(msg_dict)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Invalid message format.", rc=rc))
            return rc
        
        # Dispatch the request
        match client_request.request:
            case "config_baud_rate":
                rc = self._process_config_baud_rate_request(client_socket_fd, client_request, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Process \"config_baud_rate\" failed.", rc=rc))
                    return rc
            case "config_alias_name":
                pass
            case "get_port_config":
                rc, serial_port_dict = self._db.get_serial_port()
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not get the serial ports.", rc=rc))
                    return rc
                rc = self._reply_client_message(client_socket_obj, client_request.request, "OK", serial_port_dict)
                if rc != RcCode.SUCCESS:
                    self._logger.error(self._logger_system.set_logger_rc_code("Can not reply the message.", rc=rc))
                    return rc
                self._logger.info(self._logger_system.set_logger_rc_code("Send the result of the get_port_config done.", rc=rc))

        return RcCode.SUCCESS
    
    def _close_client_socket(self, client_socket_obj):
        # Remove the EPOLL
        self._server_mgmt_epoll.unregister(client_socket_obj.uds_client_socket_fd_get())

        # Delete the socket from the DB
        rc = self._db.del_client_socket(client_socket_obj.uds_client_socket_fd_get())
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

    def process_server_socket_event(self):
        events = self._server_mgmt_epoll.poll(0.01)
        for socket_fd, event in events:
            if socket_fd == self._server_mgmt_socket_fd:
                rc, client_socket_obj = self._uds_server_mgmt_socket.uds_server_socket_accept()
                if rc != RcCode.SUCCESS:
                    # Ignore this event, process next event.
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code(
                            "A client connected with server failed.", rc=rc))
                    continue
                self._logger.info(
                    self._logger_system.set_logger_rc_code("A client connected with server.", rc=rc))

                # Register the socket to EPOLL to monitor event
                socket_fd = client_socket_obj.fileno()
                self._server_mgmt_epoll.register(socket_fd, select.EPOLLIN)

                # Save the socket in the DB
                rc = self._db.add_client_socket(
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
            elif event & select.EPOLLIN:
                # Get the socket object
                rc, client_socket_obj = self._db.get_client_socket(socket_fd)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not find the socket in the DB.", rc=rc))
                    self._server_mgmt_epoll.unregister(socket_fd)
                    continue

                # Receive the data from the socket
                rc, data = client_socket_obj.uds_client_socket_recv(1024)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not receive the data from the socket", rc=rc))
                    rc = self._close_client_socket(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        return rc
                    continue

                # If the socket receive the data successful but no data can be processed, it means that socket has closed
                if data == b"":
                    self._logger.info(self._logger_system.set_logger_rc_code("Client socket has been closed", rc=rc))
                    rc = self._close_client_socket(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("Can not delete the socket", rc=rc))
                        return rc
                    continue

                # Process the data
                rc = self._handler_server_message(data.decode('utf-8'), socket_fd, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    # Can not receive the data from the socket. Close socket and remove the socket from the DB.
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not receive the data from the socket.", rc=rc))
                    rc = self._close_client_socket(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        return rc
        return RcCode.SUCCESS

    def daemon_main(self):
        # Communicate with the handler by message queue
        rc = self.process_message_queue_event()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Process the data reading from message queue failed.", rc=rc))
            return rc

        # Communicate with the user by socket
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