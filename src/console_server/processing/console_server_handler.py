import multiprocessing
import select

from src.common.logger_system import LoggerSystem
from src.common.msg import ReplyMsg, RequestMsg, msg_serialize
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainConnectedClientSocket
from src.console_server.processing.console_server_port import ConsoleServerSerialPort


class _ConsolerServerHandkerDb:
    def __init__(self):
        self._serial_port_info_dict = {}
        self._socket_dict = {}
        self._client_socket_epoll = select.epoll()
    
    def add_serial_port(self, serial_port_id, serial_port_obj):
        if serial_port_id in self._serial_port_info_dict:
            return RcCode.DATA_EXIST
        self._serial_port_info_dict[serial_port_id] = {"serial_port_obj": serial_port_obj, "fd_dict": {}}
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
    
    def add_serial_port_access_socket(self, serial_port_id, uds_client_socket_obj):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        socket_fd = uds_client_socket_obj.uds_client_socket_fd_get()
        if socket_fd in self._serial_port_info_dict[serial_port_id]:
            return RcCode.DATA_EXIST
        if socket_fd in self._socket_dict:
            return RcCode.DATA_EXIST
        socket_fd_dict = self._serial_port_info_dict[serial_port_id]["fd_dict"]
        socket_fd_dict[socket_fd] = uds_client_socket_obj
        self._socket_dict[socket_fd] = {"socket_obj": uds_client_socket_obj, "serial_port_id": serial_port_id}
        self._client_socket_epoll.register(socket_fd, select.EPOLLIN)
        return RcCode.SUCCESS
    
    def del_serial_port_access_socket(self, serial_port_id, socket_fd):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND
        if socket_fd not in self._serial_port_info_dict[serial_port_id]:
            return RcCode.DATA_NOT_FOUND
        socket_fd_dict = self._serial_port_info_dict[serial_port_id]["fd_dict"]
        self._client_socket_epoll.unregister(socket_fd)
        del socket_fd_dict[socket_fd]
        del self._socket_dict[socket_fd]
        return RcCode.SUCCESS
    
    def get_serial_port_access_socket(self, serial_port_id, socket_fd):
        if serial_port_id not in self._serial_port_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if socket_fd not in self._serial_port_info_dict[serial_port_id]:
            return RcCode.DATA_NOT_FOUND, None
        socket_fd_dict = self._serial_port_info_dict[serial_port_id]["fd_dict"]
        return RcCode.SUCCESS, socket_fd_dict[serial_port_id]
    
    def get_client_socket(self):
        return RcCode.SUCCESS, self._socket_dict
    
    def get_client_epoll(self):
        return RcCode.SUCCESS, self._client_socket_epoll
    
    def get_serial_port_info(self):
        return RcCode.SUCCESS, self._serial_port_info_dict


MAX_MSG_SIZE = 1024


class ConsolerServerHandler(multiprocessing.Process):
    def __init__(self, process_id, tx_queue_func, rx_queue_func):
        self._tx_queue_func = tx_queue_func
        self._rx_queue_func = rx_queue_func
        multiprocessing.Process.__init__(self)

        self._logger_system = LoggerSystem("ConsolerServerHandler_{}".format(process_id))
        self._logger = self._logger_system.get_logger()

        self._db = _ConsolerServerHandkerDb()

        self._is_server_running = True

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
    
    def _reply_queue_message(self, request, serial_port_id, socket_fd, data, result):
        reply_msg = ReplyMsg(request, serial_port_id, socket_fd, data, result)
        rc = self._tx_queue_func(reply_msg)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not send the reply to console server", rc=rc))
            return rc
        return RcCode.SUCCESS

    def init_console_server_handler(self):
        # init the logger system
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc
        self._logger = self._logger_system.get_logger()

        # Notify the console server that process has processed conpletely
        request_msg = RequestMsg("init_handler")
        rc = self._tx_queue_func(request_msg)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not send the request to console server", rc=rc))
            return rc

        self._logger.info(self._logger_system.set_logger_rc_code("Init consoel server handler complete."))
        return RcCode.SUCCESS
    
    def process_message_queue_data(self):
        rc, msg_dict = self._rx_queue_func()
        if rc == RcCode.QUEUE_ENPTY:
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Receive request no request".format(msg_dict.request)))
            # No such data to read from the queue
            return RcCode.SUCCESS
        elif rc != RcCode.SUCCESS:
            return rc

        # Preocess the request
        match msg_dict.request:
            case "init_serial_port":
                serial_port_config = msg_dict.data["serial_port_config"]
                self._logger.info(
                    self._logger_system.set_logger_rc_code(
                        "Initialize the serial port {} ".format(serial_port_config)))

                # Init the serial port
                for serial_port_id in serial_port_config:
                    rc = self._init_serial_port_object(serial_port_id, serial_port_config)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Initital the serial port {} failed.".format(serial_port_id), rc=rc))
                        rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, 
                                                "Can not initialize the serial port {}.".format(serial_port_id), "Failed")
                        if rc != RcCode.SUCCESS:
                            return rc
                    self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "Initialize the serial port {} successful.".format(serial_port_id)))

                # Notify the console server that serial ports init completely
                rc = self._reply_queue_message(msg_dict.request, -1, -1, None, "OK")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not notify the console server about the request {}.".format(msg_dict.request), rc=rc))
                    return rc
            case "connect_serial_port":
                serial_port_id = msg_dict.serial_port_id
                socket_obj = msg_dict.data["socket_obj"]

                # Add the serial por to DB
                rc = self._db.add_serial_port_access_socket(
                    serial_port_id, UnixDomainConnectedClientSocket(socket_obj, self._logger_system))
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Add the serial port {} to DB fail".format(serial_port_id), rc=rc))
                    rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, 
                                             "Can not add the socket to the DB.", "Failed")
                    if rc != RcCode.SUCCESS:
                        return rc

                # Notify the console server that serial port has connected
                rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, "", "OK")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not notify the console server about the request {}.".format(msg_dict.request), rc=rc))

                self._logger.info(
                    self._logger_system.set_logger_rc_code(
                        "Connect with serial port {} successful.".format(serial_port_id)))
            case "config_baud_rate":
                serial_port_id = msg_dict.serial_port_id
                baud_rate = msg_dict.data["baud_rate"]

                # Add the serial por to DB
                rc, serial_port_obj = self._db.get_serial_port(serial_port_id)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Get the serial port {} from the DB fail".format(serial_port_id), rc=rc))
                    rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, 
                                             "Can not get the serial port object the DB.", "Failed")
                    if rc != RcCode.SUCCESS:
                        return rc

                # Configure the baud rate and restart the serial port
                rc = serial_port_obj.set_com_port_baud_rate(baud_rate)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Set the baud rate top the serial port {} fail".format(serial_port_id), rc=rc))
                    rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, 
                                             "Can not get the serial port object the DB.", "Failed")
                    if rc != RcCode.SUCCESS:
                        return rc

                # Notify the console server that serial has configured the new baud rate
                rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, "", "OK")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not notify the console server about the request {}.".format(msg_dict.request), rc=rc))

                self._logger.info(
                    self._logger_system.set_logger_rc_code(
                        "Set the new baud rate to the serial port {} successful.".format(serial_port_id)))
            case _:
                # Notify the console server that the request is invalid
                rc = self._reply_queue_message(msg_dict.request, msg_dict.serial_port_id, msg_dict.socket_fd, "Invalid the request", "failed")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not notify the console server about the request {}.".format(msg_dict.request), rc=rc))
        return RcCode.SUCCESS
    
    def _close_client_socket(self, serial_port_id, uds_socket_obj):
        socket_fd = uds_socket_obj.uds_client_socket_fd_get()
        rc = uds_socket_obj.uds_client_socket_close()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not close the client socket.", rc=rc))
            return rc
        rc = self._db.del_serial_port_access_socket(serial_port_id, socket_fd)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not remove the socket form the DB.", rc=rc))
            return rc
        return RcCode.SUCCESS
    
    def _socket_data_handle(self, serial_port_id, msg):
        # Send the data to serial port
        rc, serial_port_obj = self._db.get_serial_port(serial_port_id)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not get the serial port object".format(serial_port_id), rc=rc))
            return rc
        
        # If serial port is busy, drop this data
        rc, status = serial_port_obj.output_buffer_is_waiting()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Serial port {} is busy.".format(serial_port_id), rc=rc))
            return rc
        if status:
            return RcCode.SUCCESS
        
        # Send the data to serial port
        rc = serial_port_obj.write_com_port_data(msg)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Serial port {} can not write the data.".format(serial_port_id), rc=rc))
            return rc
        return RcCode.SUCCESS

    def process_socket_data(self):
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

                # Receive the data from the socket
                rc, data = uds_client_socket_obj.uds_client_socket_recv(MAX_MSG_SIZE)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not receive the data from the socket", rc=rc))
                    rc = self._close_client_socket(serial_port_id, uds_client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        return rc
                    continue
                
                # If the socket receive the data successful but no data can be processed, it means that socket has closed
                if data == "":
                    self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "Client socket has been clodedt", rc=rc))
                    rc = self._close_client_socket(serial_port_id, uds_client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        return rc
                    continue

                # Send the data to serial port
                rc = self._socket_data_handle(serial_port_id)
                if rc != RcCode.SUCCESS:
                    rc = self._close_client_socket(serial_port_id, uds_client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        return rc
        return RcCode.SUCCESS
    
    def _serial_data_handle(self, serial_port_id, socket_dict,  msg):
        for socket_fd in socket_dict:
            rc = socket_dict[socket_fd].uds_client_socket_send(msg)
            if rc != RcCode.SUCCESS:
                rc, socket_fd = socket_dict[socket_fd].uds_client_socket_fd_get()
                if rc != RcCode.SUCCESS:
                    return rc
                rc = self._close_client_socket(serial_port_id)
                if rc != RcCode.SUCCESS:
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
                        "Serial port {} is busy.".format(serial_port_id), rc=rc))
                return rc
            if status:
                return RcCode.SUCCESS
            
            # receive the data to serial port
            rc, msg = serial_port_obj.read_com_port_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Serial port {} can not write the data.".format(serial_port_id), rc=rc))
                return rc
            
            rc = self._serial_data_handle(self, msg, serial_port_dict[serial_port_id]["fd_dict"])
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not broadcast the data reading from the serial port {} to client socket".format(serial_port_id), rc=rc))
                return rc
    
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

            rc = self.process_socket_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Process data reading from socket failed.", rc=rc))
                break

            rc = self.process_serial_port_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Process data reading from serial port failed.", rc=rc))
                break