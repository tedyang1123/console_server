import multiprocessing
import select

from src.common.logger_system import LoggerSystem
from src.common.msg import ReplyMsg, RequestMsg, msg_serialize
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainConnectedClientSocket, UnixDomainServerSocket
from src.common.utiliity import TEST_MODE
from src.console_server.processing.console_server_event import ConsoleServerEvent
from src.console_server.processing.console_server_port import ConsoleServerSerialPort


class _ConsolerServerHandlerDb:
    def __init__(self):
        self._uds_server_socket_obj = None
        self._serial_port_info_dict = {}
        self._pending_conn_dict = {}
        self._server_socket_epoll = select.epoll()
        self._client_socket_dict = {}
        self._client_socket_epoll = select.epoll()
    
    def add_serial_port(self, serial_port_id, serial_port_obj):
        if serial_port_id in self._serial_port_info_dict:
            return RcCode.DATA_EXIST
        self._serial_port_info_dict[serial_port_id] = {
            "serial_port_obj": serial_port_obj, 
            "fd_dict": {}
        }
        return RcCode.SUCCESS
    
    def del_serial_port(self, serial_port_id):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_info_dict[serial_port_id]
        return RcCode.SUCCESS
    
    def get_serial_port(self, serial_port_id):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._serial_port_info_dict[serial_port_id]
    
    def add_serial_port_access_socket(self, serial_port_id, uds_client_socket_obj, username):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        socket_fd = uds_client_socket_obj.uds_client_socket_fd_get()
        if socket_fd in self._serial_port_info_dict[serial_port_id]:
            return RcCode.DATA_EXIST
        if socket_fd in self._client_socket_dict:
            return RcCode.DATA_EXIST
        socket_fd_dict = self._serial_port_info_dict[serial_port_id]["fd_dict"]
        socket_fd_dict[socket_fd] = uds_client_socket_obj
        self._client_socket_dict[socket_fd] = {
            "socket_obj": uds_client_socket_obj, 
            "serial_port_id": serial_port_id, 
            "username": username
        }
        self._client_socket_epoll.register(socket_fd, select.EPOLLIN)
        return RcCode.SUCCESS
    
    def del_serial_port_access_socket(self, serial_port_id, socket_fd):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND
        if socket_fd not in self._serial_port_info_dict[serial_port_id]["fd_dict"]:
            return RcCode.DATA_NOT_FOUND
        socket_fd_dict = self._serial_port_info_dict[serial_port_id]["fd_dict"]
        self._client_socket_epoll.unregister(socket_fd)
        del socket_fd_dict[socket_fd]
        del self._client_socket_dict[socket_fd]
        return RcCode.SUCCESS
    
    def get_serial_port_access_socket(self, serial_port_id, socket_fd):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if socket_fd not in self._serial_port_info_dict[serial_port_id]:
            return RcCode.DATA_NOT_FOUND, None
        socket_fd_dict = self._serial_port_info_dict[serial_port_id]["fd_dict"]
        return RcCode.SUCCESS, socket_fd_dict[serial_port_id]
    
    def get_client_socket(self):
        return RcCode.SUCCESS, self._client_socket_dict
    
    def get_client_epoll(self):
        return RcCode.SUCCESS, self._client_socket_epoll
    
    def get_serial_port_info(self):
        return RcCode.SUCCESS, self._serial_port_info_dict

    def add_server_socket(self, uds_server_socket_obj):
        if self._uds_server_socket_obj is not None:
            return RcCode.DATA_EXIST
        self._uds_server_socket_obj = uds_server_socket_obj
        self._server_socket_epoll.register(uds_server_socket_obj.uds_server_socket_fd_get(), select.EPOLLIN)
        return RcCode.SUCCESS

    def del_server_socket(self, uds_server_socket_obj):
        if self._uds_server_socket_obj is None:
            return RcCode.DATA_NOT_FOUND
        self._server_socket_epoll.unregister(uds_server_socket_obj.uds_client_socket_fd_get())
        self._uds_server_socket_obj = None
        return RcCode.SUCCESS

    def get_server_socket(self):
        if self._uds_server_socket_obj is None:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._uds_server_socket_obj

    def get_server_epoll(self):
        return RcCode.SUCCESS, self._server_socket_epoll

    def add_pending_connection(self, uds_connected_socket):
        socket_fd = uds_connected_socket.uds_client_socket_fd_get()
        if socket_fd in self._pending_conn_dict:
            return RcCode.DATA_EXIST
        self._pending_conn_dict[socket_fd] = uds_connected_socket
        self._server_socket_epoll.register(socket_fd, select.EPOLLIN)
        return RcCode.SUCCESS

    def del_pending_connection(self, client_socket_fd):
        if client_socket_fd not in self._pending_conn_dict:
            return RcCode.DATA_NOT_FOUND
        del self._pending_conn_dict[client_socket_fd]
        self._server_socket_epoll.unregister(client_socket_fd)
        return RcCode.SUCCESS

    def get_pending_connections(self, client_socket_fd=None):
        if client_socket_fd is None:
            return RcCode.SUCCESS, self._pending_conn_dict
        if client_socket_fd not in self._pending_conn_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._pending_conn_dict[client_socket_fd]


MAX_MSG_SIZE = 1024


class ConsolerServerHandler(multiprocessing.Process):
    def __init__(self, process_id, tx_queue_func, rx_queue_func):
        self._process_id = process_id
        self._tx_queue_func = tx_queue_func
        self._rx_queue_func = rx_queue_func
        multiprocessing.Process.__init__(self)

        self._logger_system = LoggerSystem("ConsolerServerHandler_{}".format(process_id))
        self._logger = self._logger_system.get_logger()

        self._db = _ConsolerServerHandlerDb()

        self._pending_client_socket_dict = {}

        self._is_server_running = True
    
    def _close_client_socket(self, serial_port_id, uds_socket_obj):
        socket_fd = uds_socket_obj.uds_client_socket_fd_get()
        rc = self._db.del_serial_port_access_socket(serial_port_id, socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not remove the socket associated with serial port {} form the DB.".format(serial_port_id), rc=rc))
            return rc
        rc = uds_socket_obj.uds_client_socket_close()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not close the client socket.", rc=rc))
            return rc
        return RcCode.SUCCESS
    
    def _send_queue_message(self, request=None, serial_port_id=None, socket_fd=None,  data=None, result=None):
        rc = self._tx_queue_func(ReplyMsg(request, serial_port_id, socket_fd, data, result))
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not send the request to console server", rc=rc))
            return rc
        return RcCode.SUCCESS

    ##########################################################################################################
    # Public API
    ##########################################################################################################
    
    def _init_service_server_socket(self):
        uds_server_socket_obj = UnixDomainServerSocket(
            20, "/tmp/server_handler_{}.sock".format(self._process_id), self._logger_system)
        rc = uds_server_socket_obj.uds_server_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not init the server socket.", rc=rc))
            return rc
        rc = self._db.add_server_socket(uds_server_socket_obj)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not add the server socket in the DB.", rc=rc))
            return rc
        return RcCode.SUCCESS

    def init_console_server_handler(self):
        # init the logger system
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger = self._logger_system.get_logger()

        # Init the server socket completely
        rc = self._init_service_server_socket()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("Init server socket complete."))

        # Notify the console server that process has processed completely
        rc = self._send_queue_message(request=ConsoleServerEvent.INIT_HANDLER, result="OK")
        if rc != RcCode.SUCCESS:
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("Notify the server that handler initialize completely."))

        self._logger.info(self._logger_system.set_logger_rc_code("Init consoel server handler complete."))
        return RcCode.SUCCESS
    
    ##########################################################################################################
    # Process Queue Data Relate API
    ##########################################################################################################
    
    def _reply_queue_message(self, request, serial_port_id, socket_fd, data, result):
        reply_msg = ReplyMsg(request, serial_port_id, socket_fd, data, result)
        rc = self._tx_queue_func(reply_msg)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not send the reply to console server", rc=rc))
            return rc
        return RcCode.SUCCESS

    def _init_serial_port_object(self, serial_port_id, serial_port_info):
        serial_port_info = serial_port_info[serial_port_id]
        dev_tty_id = serial_port_info["dev_tty_id"]
        baud_rate = serial_port_info["baud_rate"]

        # Create the serial port object
        serial_port_obj = ConsoleServerSerialPort(dev_tty_id, baud_rate, self._logger_system)
        rc = serial_port_obj.create_serial_port()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not initialize the serial port object.", rc=rc))
            return rc
        
        # Add the serial port object to the DB
        rc = self._db.add_serial_port(serial_port_id, serial_port_obj)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not add the serial port object to DB.", rc=rc))
            return rc
        return RcCode.SUCCESS
    
    def _process_init_serial_port_event(self, msg_dict):
        serial_port_config = msg_dict.data["serial_port_config"]
        self._logger.info(
            self._logger_system.set_logger_rc_code("Initialize the serial port {} ".format(serial_port_config)))

        # Init the serial port
        for serial_port_id in serial_port_config:
            rc = self._init_serial_port_object(serial_port_id, serial_port_config)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Initial the serial port {} failed.".format(serial_port_id), rc=rc))
                rc = self._reply_queue_message(
                    msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, 
                    "Can not initialize the serial port {}.".format(serial_port_id), "Failed")
                if rc != RcCode.SUCCESS:
                    return rc
            self._logger.info(
                self._logger_system.set_logger_rc_code("Initialize the serial port {} successful.".format(serial_port_id)))

        # Notify the console server that serial ports init completely
        rc = self._reply_queue_message(msg_dict.request, -1, -1, None, "OK")
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not notify the console server about the request {}.".format(msg_dict.request), rc=rc))
            return rc
        self._logger.info(self._logger_system.set_logger_rc_code("Notify the server that serial prot has initialized complete."))
        return RcCode.SUCCESS
    
    def _process_config_baud_rate(self, msg_dict):
        serial_port_id = msg_dict.serial_port_id
        baud_rate = msg_dict.data["baud_rate"]
        self._logger.info(
            self._logger_system.set_logger_rc_code("Process baud rate request for serial port {} ".format(serial_port_id)))

        # Add the serial por to DB
        rc, serial_port_dict = self._db.get_serial_port(serial_port_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Get the serial port {} from the DB fail".format(serial_port_id), rc=rc))
            rc = self._reply_queue_message(
                msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, "Can not get the serial port object the DB.", "Failed")
            if rc != RcCode.SUCCESS:
                return rc

        serial_port_obj = serial_port_dict["serial_port_obj"]

        # Configure the baud rate and restart the serial port
        rc = serial_port_obj.set_com_port_baud_rate(baud_rate)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Set the baud rate top the serial port {} fail".format(serial_port_id), rc=rc))
            rc = self._reply_queue_message(
                msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, "Can not get the serial port object the DB.", "Failed")
            if rc != RcCode.SUCCESS:
                return rc

        # Notify the console server that serial has configured the new baud rate
        rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, msg_dict.data, "OK")
        if rc != RcCode.SUCCESS:
            return rc

        self._logger.info(
            self._logger_system.set_logger_rc_code("Set the new baud rate to the serial port {} successful.".format(serial_port_id)))
        return RcCode.SUCCESS
    
    def process_message_queue_data(self):
        rc, msg_dict = self._rx_queue_func()
        if rc == RcCode.QUEUE_ENPTY:
            # No such data to read from the queue
            return RcCode.SUCCESS
        elif rc != RcCode.SUCCESS:
            return rc

        # Process the request
        match msg_dict.request:
            case ConsoleServerEvent.INIT_SERIAL_PORT:
                rc = self._process_init_serial_port_event(msg_dict)
                if rc != RcCode.SUCCESS:
                    return rc
            case ConsoleServerEvent.CONFIG_BAUD_RATE:
                rc = self._process_config_baud_rate(msg_dict)
                if rc != RcCode.SUCCESS:
                    return rc
            case _:
                # Notify the console server that the request is invalid
                rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, "Invalid the request", "failed")
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS
    
    ##########################################################################################################
    # Process Server Socket Data Relate API
    ##########################################################################################################

    def _reply_client_message(self, client_socket_obj, request, result, data):
        # Create reply message
        reply_msg = ReplyMsg(request, None, None, data, result)
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
        rc = client_socket_obj.uds_client_socket_send(data_byte)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not serialize the data.", rc=rc))
            return rc

        # Send the message by socket
        rc = client_socket_obj.uds_client_socket_send(bytes(msg_str, 'utf-8'))
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not serialize the data.", rc=rc))
            return rc
        return RcCode.SUCCESS

    def _update_request_information(self, pending_connection, serial_port_id, username):
        # Delete the pending connection
        rc = self._db.del_pending_connection(pending_connection.uds_client_socket_fd_get())
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Delete the pending connection from the DB fail".format(serial_port_id), rc=rc))
            if rc != RcCode.SUCCESS:
                return rc

        # Add the serial port to DB
        rc = self._db.add_serial_port_access_socket(serial_port_id, pending_connection, username)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Add the serial port {} to DB fail".format(serial_port_id), rc=rc))
            if rc != RcCode.SUCCESS:
                return rc
        return RcCode.SUCCESS

    def _connect_serial_port(self, pending_connection, request):
        serial_port_id = request.serial_port_id
        username = request.data["username"]

        # Update the request information in the DB
        rc = self._update_request_information(pending_connection, serial_port_id, username)
        if rc != RcCode.SUCCESS:
            return rc

        rc, serial_port_dict = self._db.get_serial_port(serial_port_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Get the serial port {} from the DB fail".format(serial_port_id), rc=rc))
            return rc
        serial_port_obj = serial_port_dict["serial_port_obj"]
        rc, status = serial_port_obj.is_open_com_port()
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not get the port status.", rc=rc))
            return rc
        if not status:
            rc = serial_port_obj.open_com_port() if not TEST_MODE else RcCode.SUCCESS
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code("Can not open serial port {}".format(serial_port_id), rc=rc))
                return rc

        rc = self._reply_client_message(pending_connection, request.request, "OK", None)
        if rc != RcCode.SUCCESS:
            return rc
        self._logger.info(
            self._logger_system.set_logger_rc_code("Connect with serial port {} successful.".format(request.serial_port_id)))
        return RcCode.SUCCESS

    def _process_server_socket_event(self, msg, pending_connection):
        request = RequestMsg()
        rc = request.deserialize(msg)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Invalid request format.", rc=rc))
            return rc

        match request.request:
            case ConsoleServerEvent.CONNECT_SERIAL_PORT:
                rc = self._connect_serial_port(pending_connection, request)
                if rc != RcCode.SUCCESS:
                    return rc
            case _:
                self._logger.warning(self._logger_system.set_logger_rc_code(
                    "Invalid request {}.".format(request.request)))
        return RcCode.SUCCESS

    def _close_pending_connection(self, pending_connection):
        socket_fd = pending_connection.uds_client_socket_fd_get()
        rc = self._db.del_pending_connection(socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not remove the socket form the DB.", rc=rc))
            return rc
        rc = pending_connection.uds_client_socket_close()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not close the client socket.", rc=rc))
            return rc
        return RcCode.SUCCESS

    def _accept_new_client(self, server_socket_obj):
        # A new client connected with the server
        rc, client_socket_obj = server_socket_obj.uds_server_socket_accept()
        if rc != RcCode.SUCCESS:
            # Ignore this event, process next event.
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("A new client {} arrived.".format(client_socket_obj.getpeername())))

        # Register the connection to DB
        rc = self._db.add_pending_connection(
            UnixDomainConnectedClientSocket(client_socket_obj, self._logger_system))
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not add the client socket to the DB.", rc=rc))
            return rc
        return RcCode.SUCCESS
    
    def _handle_server_socket_data(self, pending_connection):
        # Receive the data from the socket
        rc, data = pending_connection.uds_client_socket_recv(MAX_MSG_SIZE)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not receive the data from the socket", rc=rc))
            rc_reply_msg = self._close_pending_connection(pending_connection)
            if rc_reply_msg != RcCode.SUCCESS:
                return rc_reply_msg
            return RcCode.SUCCESS

        # If the socket receive the data successful but no data can be processed, it means that socket has been closed
        if data == "":
            self._logger.info(self._logger_system.set_logger_rc_code("Client socket has been closed", rc=rc))
            rc_reply_msg = self._close_pending_connection(pending_connection)
            if rc_reply_msg != RcCode.SUCCESS:
                return rc_reply_msg
            return RcCode.SUCCESS

        # Send the data to serial port
        rc = self._process_server_socket_event(data.decode('utf-8'), pending_connection)
        if rc != RcCode.SUCCESS:
            rc_reply_msg = self._close_pending_connection(pending_connection)
            if rc_reply_msg != RcCode.SUCCESS:
                return rc_reply_msg
        return RcCode.SUCCESS

    def process_server_socket_event(self):
        # Get the server socket
        rc, server_socket_obj = self._db.get_server_socket()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the server socket.", rc=rc))
            return rc

        # Get the server EPOLL
        rc, server_socket_epoll = self._db.get_server_epoll()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the server socket epoll.", rc=rc))
            return rc

        # Get the pending connection
        rc, pending_connection_dict = self._db.get_pending_connections()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the pending connection.", rc=rc))
            return rc

        # Receive the socket event
        events = server_socket_epoll.poll(0.01)
        for socket_fd, event in events:
            if socket_fd == server_socket_obj.uds_server_socket_fd_get():
                rc = self._accept_new_client(server_socket_obj)
                if rc != RcCode.SUCCESS:
                    return rc
            elif socket_fd in pending_connection_dict and event & select.EPOLLIN:
                rc = self._handle_server_socket_data(pending_connection_dict[socket_fd])
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS

    def _handle_client_socket_data(self, client_socket_obj, serial_port_id):
        self._logger.info("The new data has arrived.")

        # Receive the data from the socket
        rc, data = client_socket_obj.uds_client_socket_recv(MAX_MSG_SIZE)
        if rc != RcCode.SUCCESS:
            self._logger.error(self._logger_system.set_logger_rc_code("Can not receive the data from the socket", rc=rc))
            rc = self._close_client_socket(serial_port_id, client_socket_obj)
            if rc != RcCode.SUCCESS:
                return rc
            return RcCode.SUCCESS
        
        # If the socket receive the data successful but no data can be processed, it means that socket has closed
        if data == b"":
            self._logger.info(self._logger_system.set_logger_rc_code("Client socket has been closed", rc=rc))
            rc = self._close_client_socket(serial_port_id, client_socket_obj)
            if rc != RcCode.SUCCESS:
                return rc
            return RcCode.SUCCESS
        
        rc, permission = self._db.get_socket_write_permission(serial_port_id, client_socket_obj.uds_client_socket_fd_get())
        if rc != RcCode.SUCCESS:
            return rc
        if not permission:
            return RcCode.SUCCESS

        # Send the data to serial port
        rc = self._socket_data_handle(serial_port_id, data)
        if rc != RcCode.SUCCESS:
            rc = self._close_client_socket(serial_port_id, client_socket_obj)
            if rc != RcCode.SUCCESS:
                return rc
        return RcCode.SUCCESS

    def process_client_socket_data(self):
        rc, client_socket_dict = self._db.get_client_socket()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the client socket.", rc=rc))
            return rc
        
        rc, client_socket_epoll = self._db.get_client_epoll()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the client socket epoll.", rc=rc))
            return rc
        
        events = client_socket_epoll.poll(0.01)
        for socket_fd, event in events:
            if socket_fd in client_socket_dict and event & select.EPOLLIN:
                serial_port_id = client_socket_dict[socket_fd]["serial_port_id"]
                uds_client_socket_obj = client_socket_dict[socket_fd]["socket_obj"]

                rc = self._handle_client_socket_data(uds_client_socket_obj, serial_port_id)
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS
    
    ##########################################################################################################
    # Process Client Socket Data Relate API
    ##########################################################################################################
    
    def _handle_serial_port_data(self, serial_port_id, socket_dict,  msg):
        for socket_fd in socket_dict:
            rc = socket_dict[socket_fd].uds_client_socket_send(msg)
            if rc != RcCode.SUCCESS:
                rc, socket_fd = socket_dict[socket_fd].uds_client_socket_fd_get()
                if rc != RcCode.SUCCESS:
                    return rc
                rc = self._close_client_socket(serial_port_id, socket_dict[socket_fd])
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS
    
    def _socket_data_handle(self, serial_port_id, msg):
        # Send the data to serial port
        rc, serial_port_dict = self._db.get_serial_port(serial_port_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the serial port object".format(serial_port_id), rc=rc))
            return rc
        serial_port_obj = serial_port_dict["serial_port_obj"]
        
        # If serial port is busy, drop this data
        rc, status = serial_port_obj.output_buffer_is_waiting() if not TEST_MODE else (RcCode.SUCCESS, False)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Serial port {} is busy.".format(serial_port_id), rc=rc))
            return rc
        if status:
            return RcCode.SUCCESS
        
        # Send the data to serial port
        rc = serial_port_obj.write_com_port_data(msg) if not TEST_MODE else RcCode.SUCCESS
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Serial port {} can not write the data.".format(serial_port_id), rc=rc))
            return rc
        return RcCode.SUCCESS
    
    def process_serial_port_data(self):
        rc, serial_port_dict = self._db.get_serial_port_info()
        if rc != RcCode.SUCCESS:
            return rc
        
        for serial_port_id in serial_port_dict:
            serial_port_obj = serial_port_dict[serial_port_id]["serial_port_obj"]

            # If serial port is closed, get the next serial port
            rc, status = serial_port_obj.is_open_com_port()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not get serial port {} status".format(serial_port_id), rc=rc))
                return rc
            if not status:
                return RcCode.SUCCESS
        
            # If serial port is busy, drop this data
            rc, status = serial_port_obj.in_buffer_is_waiting()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Serial port {} has not data.".format(serial_port_id), rc=rc))
                return rc
            if not status:
                return RcCode.SUCCESS
            
            # receive the data to serial port
            rc, msg = serial_port_obj.read_com_port_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Serial port {} can not write the data.".format(serial_port_id), rc=rc))
                return rc
            
            rc = self._handle_serial_port_data(serial_port_id, serial_port_dict[serial_port_id]["fd_dict"], msg)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not broadcast the data reading from the serial port {} to client socket".format(serial_port_id), rc=rc))
                return rc
        return RcCode.SUCCESS
    
    ##########################################################################################################
    # Daemon Relate API
    ##########################################################################################################
    
    def run(self):
        rc = self.init_console_server_handler()
        if rc != RcCode.SUCCESS:
            return

        while self._is_server_running:
            rc = self.process_message_queue_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Process data reading from message queue failed.", rc=rc))
                break

            rc = self.process_server_socket_event()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Process data reading from server socket failed.", rc=rc))
                break

            rc = self.process_client_socket_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Process data reading from client socket failed.", rc=rc))
                break

            rc = self.process_serial_port_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Process data reading from serial port failed.", rc=rc))
                break
