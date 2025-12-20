import copy
import re
import threading
import time

import select

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainServerSocket
from src.common.utiliity import TEST_MODE
from src.console_server.console_server_port import ConsoleServerSerialPort

MAX_MSG_SIZE = 30
MAX_CLIENT = 24


class SerialPortDict:
    def __init__(self):
        self._serial_port_dict = {}

    def add_serial_port(self, serial_port_id, serial_port_obj, description, baud_rate):
        if serial_port_id in self._serial_port_dict:
            return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id] = {}
        self._serial_port_dict[serial_port_id]["serial_port_obj"] = serial_port_obj
        self._serial_port_dict[serial_port_id]["description"] = description
        self._serial_port_dict[serial_port_id]["baud_rate"] = baud_rate
        self._serial_port_dict[serial_port_id]["fd_dict"] = {}
        return RcCode.SUCCESS

    def get_serial_port(self, serial_port_id):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._serial_port_dict[serial_port_id]

    def del_serial_port(self, serial_port_id):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_dict[serial_port_id]
        return RcCode.SUCCESS

    def get_serial_port_info(self, serial_port_id, field=None):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field not in self._serial_port_dict[serial_port_id]:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS,self._serial_port_dict[serial_port_id]
        return RcCode.SUCCESS, self._serial_port_dict[serial_port_id][field]

    def add_serial_port_fd_info(self, serial_port_id, socket_fd, status, socket_obj):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if socket_fd in self._serial_port_dict[serial_port_id]["fd_dict"]:
            return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id]["fd_dict"][socket_fd] = {}
        self._serial_port_dict[serial_port_id]["fd_dict"][socket_fd]["status"] = status
        self._serial_port_dict[serial_port_id]["fd_dict"][socket_fd]["socket_obj"] = socket_obj
        return RcCode.SUCCESS

    def del_serial_port_fd_info(self, serial_port_id, socket_fd):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if socket_fd not in self._serial_port_dict[serial_port_id]["fd_dict"]:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_dict[serial_port_id]["fd_dict"][socket_fd]
        return RcCode.SUCCESS

    def get_serial_port_fd_info(self, serial_port_id, socket_fd, field=None):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field not in self._serial_port_dict[serial_port_id]["fd_dict"][socket_fd]:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS, self._serial_port_dict[serial_port_id]["fd_dict"][socket_fd]
        return RcCode.SUCCESS, self._serial_port_dict[serial_port_id]["fd_dict"][socket_fd][field]

    def get_serial_port_dict_all(self):
        return RcCode.SUCCESS, self._serial_port_dict


class ClientRequestInfoDict:
    def __init__(self):
        self._client_request_info_dict = {}

    def add_client_request_info(self, socket_fd, socket_obj):
        if socket_fd in self._client_request_info_dict:
            return RcCode.DATA_EXIST
        self._client_request_info_dict[socket_fd] = {}
        self._client_request_info_dict[socket_fd]["socket_obj"] = socket_obj
        return RcCode.SUCCESS

    def del_client_request_info(self, socket_fd):
        if socket_fd not in self._client_request_info_dict:
            return RcCode.DATA_NOT_FOUND
        del self._client_request_info_dict[socket_fd]
        return RcCode.SUCCESS

    def get_client_request_info(self, socket_fd, field=None):
        if socket_fd not in self._client_request_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS, self._client_request_info_dict[socket_fd]
        return RcCode.SUCCESS, self._client_request_info_dict[socket_fd][field]

    def get_client_request_info_all(self):
        return RcCode.SUCCESS, self._client_request_info_dict


class ClientServiceInfoDict:
    def __init__(self):
        self._client_service_info_dict = {}

    def add_client_service_info(self, socket_fd, socket_obj, serial_port_id):
        if socket_fd in self._client_service_info_dict:
            return RcCode.DATA_EXIST
        self._client_service_info_dict[socket_fd] = {}
        self._client_service_info_dict[socket_fd]["socket_obj"] = socket_obj
        self._client_service_info_dict[socket_fd]["serial_port_id"] = serial_port_id
        return RcCode.SUCCESS

    def del_client_service_info(self, socket_fd):
        if socket_fd not in self._client_service_info_dict:
            return RcCode.DATA_NOT_FOUND
        del self._client_service_info_dict[socket_fd]
        return RcCode.SUCCESS

    def get_client_service_info(self, socket_fd, field=None):
        if socket_fd not in self._client_service_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS, self._client_service_info_dict[socket_fd]
        return RcCode.SUCCESS, self._client_service_info_dict[socket_fd][field]

    def get_client_server_info_all(self):
        return RcCode.SUCCESS, self._client_service_info_dict


class ConsoleServerHandler(threading.Thread):
    def __init__(self, serial_port_config_dict, thread_event, daemon_id=0):
        self._serial_port_config_dict = serial_port_config_dict
        self._daemon_id = daemon_id
        self._thread_event = thread_event

        threading.Thread.__init__(self, name="ConsoleServerHandler_{}".format(daemon_id))

        self._logger_system = LoggerSystem(self.name)
        self._logger = self._logger_system.get_logger()

        self._uds_server_socket = UnixDomainServerSocket(
            MAX_CLIENT, "/tmp/server_{}.sock".format(daemon_id), self._logger_system)

        # list the sockets which sent the request to the server.
        self._client_request_socket_epoll = None

        # list the sockets which wants to access the serial port.
        self._client_service_socket_epoll = None

        self._client_request_info = ClientRequestInfoDict()
        self._client_service_info = ClientServiceInfoDict()

        self._serial_port_info = SerialPortDict()

        self._running = False

    def is_running(self):
        return self._running

    def _init_serial_port(self):
        for serial_port_id in self._serial_port_config_dict:
            serial_port_obj = ConsoleServerSerialPort(serial_port_id, self._logger_system)
            rc = serial_port_obj.create_serial_port()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Create serial port {} failed.".format(serial_port_id), rc=rc))
                return rc
            self._logger.info(
                self._logger_system.set_logger_rc_code(
                    "Create a serial port {} in the serial port info DB.".format(serial_port_id)))
            self._serial_port_info.add_serial_port(serial_port_id,serial_port_obj, "", 115200)
        return RcCode.SUCCESS

    def _serial_port_message_broadcast(self, msg, serial_port):
        self._logger.info(
            self._logger_system.set_logger_rc_code("Serial port sent the data and we will broadcast it other user."))
        rc, serial_port_fd_info = self._serial_port_info.get_serial_port_info(serial_port, "fd_dict")
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port does not exist in the serial port DB."))
            return rc
        for serial_port_fd in serial_port_fd_info:
            # Ignore the client which has been stopped.
            socket_info_dict = serial_port_fd_info[serial_port_fd]
            if not socket_info_dict["status"]:
                # Socket has been closed
                continue

            # Send the message to the other client
            rc = self._uds_server_socket.uds_client_socket_send(socket_info_dict["socket"], msg)
            if rc != RcCode.SUCCESS:
                # Can not send the data to the client.
                # Force close the socket and set the socket to not running.
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "We find a client {} has some errors. Close this socket".format(
                            socket_info_dict["socket"][0].getpeername())))
                rc = self._uds_server_socket.uds_client_socket_close(socket_info_dict["socket"])
                if rc != RcCode.SUCCESS:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code("We try to close the client {} but failed.".format(
                            socket_info_dict["socket"][0].getpeername())))
                socket_info_dict["status"] = False
        return RcCode.SUCCESS

    def _client_socket_message_broadcast(self, msg, serial_port_id, socket_no):
        self._logger.info(
            self._logger_system.set_logger_rc_code(
                "Control server sent the data and we will broadcast it other user and serial port."))
        rc, serial_port_fd_dict = self._serial_port_info.get_serial_port_info(serial_port_id, "fd_dict")
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port does not exist in the serial port DB."))
            return rc
        for serial_port_fd in serial_port_fd_dict:
            socket_info_dict = serial_port_fd_dict[serial_port_fd]
            socket_obj = socket_info_dict["socket_obj"]
            if socket_obj[0].fileno() == socket_no:
                # Socket is the source socket.
                continue
            if not socket_info_dict["status"]:
                # Socket has been closed
                continue

            rc = self._uds_server_socket.uds_client_socket_send(socket_obj, msg)
            if rc != RcCode.SUCCESS:
                # Can not send the data to the client.
                # Force close the socket and set the socket to not running.
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "We find a client {} has some errors. Close this socket".format(
                            socket_obj[0].getpeername())))
                rc = self._uds_server_socket.uds_client_socket_close(socket_obj)
                if rc != RcCode.SUCCESS:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code(
                            "We try to close the client {} but failed.".format(
                                socket_obj[0].getpeername())))
                socket_info_dict["status"] = False

        # Send the data to serial port.
        rc, serial_port_obj = self._serial_port_info.get_serial_port_info(serial_port_id, "serial_port_obj")
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "The serial port {} is not found.".format(serial_port_id), rc=rc))
            return rc

        if TEST_MODE:
            return RcCode.SUCCESS

        # Check if the serial port has been opened
        rc, state = serial_port_obj.is_open_com_port()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not get the serial port {} status.".format(serial_port_id), rc=rc))
            return rc
        if not state:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Serial port {} is not opened".format(serial_port_id)))
            return RcCode.DEVICE_NOT_FOUND

        # Check if the message in the buffer has been sent.
        rc, state = serial_port_obj.output_buffer_is_waiting()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not get the serial port {} output buffer status.".format(serial_port_id), rc=rc))
            return rc
        if state:
            self._logger.warning("Serial port {} is busy.".format(serial_port_id))
            return RcCode.DEVICE_BUSY

        # Write the message to the serial port.
        rc = serial_port_obj.write_com_port_data(msg)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not write the data to serial prot {}.".format(serial_port_id), rc=rc))
            return rc
        return RcCode.SUCCESS

    def serial_port_socket_clear(self, serial_port_id, clear_all=False):
        close_client_fd_list = []

        # Find all sockets which have been closed
        rc, serial_port_fd_dict = self._serial_port_info.get_serial_port_info(serial_port_id, "fd_dict")
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("The serial port does not exist in the serial port DB."))
            return rc
        for serial_port_fd in serial_port_fd_dict:
            if not serial_port_fd_dict[serial_port_fd]["status"]:
                # Save the fd and we will delete it later
                close_client_fd_list.append(serial_port_fd)

        # Delete the fd now
        for serial_port_fd in close_client_fd_list:
            del serial_port_fd_dict[serial_port_fd]

        return RcCode.SUCCESS

    def _serial_port_host_access_register(self, socket_obj, serial_port_id):
        socket_fd = socket_obj[0].fileno()
        rc = self._serial_port_info.add_serial_port_fd_info(serial_port_id, socket_fd, True, socket_obj)
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not register the new socket FD in the serial port group {}.".format(serial_port_id), rc=rc))
            return rc

        return RcCode.SUCCESS

    def _serial_port_host_access_unregister(self, socket_obj, serial_port_id=-1):
        socket_fd = socket_obj[0].fileno()
        if serial_port_id == -1:
            rc = RcCode.DATA_NOT_FOUND
            # In this case we don't know the socket connected with which serial port.
            # We have to iterate the serial port map client table to find the specified socket.
            for serial_port_id in self._serial_port_config_dict:
                rc = self._serial_port_info.del_serial_port_fd_info(serial_port_id, socket_fd)
                if rc != RcCode.SUCCESS:
                    return rc
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not unregister the new socket FD in the serial port group {}.".format(
                            serial_port_id), rc=rc))
            return rc
        else:
            # Here we set the 'running' flag to False and later the clear process will kill.
            rc = self._serial_port_info.del_serial_port_fd_info(serial_port_id, socket_fd)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not unregister the new socket FD in the serial port group {}.".format(
                            serial_port_id), rc=rc))
                return rc
        return RcCode.SUCCESS

    def _server_event_handle(self, socket_fd, request_cmd):
        # Match command format and execute the request

        #. Match connect connect
        group = re.match("connect-([0-9]+)", request_cmd)
        if group is not None:
            serial_port_id = int(group[1], 10)
            if serial_port_id not in self._serial_port_config_dict:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The port ID is not in the port list. The valid port id is {}".format(
                            self._serial_port_config_dict)))
                return RcCode.INVALID_VALUE

            self._logger.info(
                self._logger_system.set_logger_rc_code("The request is 'connect' and we start process it."))

            rc, serial_port_obj = self._serial_port_info.get_serial_port_info(serial_port_id, "serial_port_obj")
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The serial port {} is not found.".format(serial_port_id), rc))
                return rc
            rc = serial_port_obj.open_com_port()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The serial port {} can not be opened.".format(serial_port_id), rc))
                if not TEST_MODE:
                    return rc

            # Get the socket object from the server socket information DB
            rc, socket_obj = self._client_request_info.get_client_request_info(socket_fd, "socket_obj")
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not add the socket FD {} information to the server socket DB".format(
                            socket_obj[0].getpeername()), rc))
                return rc

            # Add socket to the serial port DB
            rc = self._serial_port_host_access_register(socket_obj, serial_port_id)
            if rc != RcCode.SUCCESS:
                self._logger_system.set_logger_rc_code(
                    "Can not register socket {} to serial port {}".format(
                        socket_obj[0].getpeername(), serial_port_id))
                return rc

            # Delete the socket information from the service information DB,
            # due to this socket connect with serial port.
            rc = self._client_request_info.del_client_request_info(socket_fd)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not remove the socket FD {} information from the server socket DB".format(
                            socket_obj[0].getpeername()), rc))
                return rc

            # Add the socket information to the request information DB,
            # due to this socket connect with serial port.
            rc = self._client_service_info.add_client_service_info(socket_fd, socket_obj, serial_port_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not add the socket FD {} information to the client socket DB".format(
                            socket_obj[0].getpeername()), rc))
                return rc

            # Move the socket from server request epoll pool to client event epoll pool
            self._client_request_socket_epoll.unregister(socket_fd)
            self._client_service_socket_epoll.register(socket_fd, select.EPOLLIN)

            self._logger.info(
                self._logger_system.set_logger_rc_code("The request is 'connect' and we process it completely."))

            # Notify the client that command executed successful
            rc = self._uds_server_socket.uds_client_socket_send(socket_obj, "OK")
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not reply the message to client. msg: {}, host: {}".format(
                            "OK", socket_obj[0].getpeername())))
                return rc

            self._logger.info(
                self._logger_system.set_logger_rc_code("The request has been processed 'connect' successfully."))
            return RcCode.SUCCESS

        group = re.match("baudrate-([0-9]+)-([0-9]+)", request_cmd)
        if group is not None:
            # Get the first parameter. It is a port ID.
            serial_port_id = int(group[1], 10)

            # Check if serial port ID is valid
            if serial_port_id not in self._serial_port_config_dict:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The port ID is not in the port list. The valid port id is {}".format(
                            self._serial_port_config_dict)))
                return RcCode.INVALID_VALUE


            # Get the second parameter. It is a baud rate.
            baud_rate = int(request_cmd)

            self._logger.info(
                self._logger_system.set_logger_rc_code("The request is 'baudrate' and we start process it."))

            # Get the socket object from the server socket information DB
            rc, socket_obj = self._client_request_info.get_client_request_info(socket_fd, "socket_obj")
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "Can not add the socket FD {} information to the server socket DB".format(
                            socket_obj[0].getpeername()), rc))
                return rc

            # Set the new baud rate to the serial prot
            rc, serial_port_obj = self._serial_port_info.get_serial_port_info(serial_port_id, "serial_port_obj")
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The serial port {} is not found.".format(serial_port_id), rc))
                return rc

            rc = serial_port_obj.close_com_port()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The serial port {} can not be opened.".format(serial_port_id), rc))
                return rc
            rc = serial_port_obj.open_com_port()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The serial port {} can not be opened.".format(serial_port_id), rc))
                return rc

            # Update the baud rate in the serial port config
            self._serial_port_config_dict[serial_port_id]["baud_rate"] = baud_rate

            self._logger.info(
                self._logger_system.set_logger_rc_code("The request is 'baudrate' and we process it DONE."))

            # Notify the client that command executed successful
            rc = self._uds_server_socket.uds_client_socket_send(socket_obj, "OK")
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not reply the message to client. msg: {}, host: {}".format(
                                "OK", socket_obj["socket"][0].getpeername())))
                return rc

            self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "The request has been processed 'baudrate' successfully."))
            return RcCode.SUCCESS

        # Get the socket object from the server socket information DB
        rc, socket_obj = self._client_request_info.get_client_request_info(socket_fd, "socket_obj")
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not add the socket FD {} information to the server socket DB".format(
                        socket_obj[0].getpeername()), rc))
            return rc

        self._logger.error("Invalid request {}".format(request_cmd))
        rc = self._uds_server_socket.uds_client_socket_send(socket_obj, "failed")
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Can not reply the message to client. msg: {}, host: {}".format(
                    "Failed", socket_obj[0].getpeername())))
            return rc
        return RcCode.INVALID_VALUE

    def _server_event_main_process(self):
        rc, server_socket_fd = self._uds_server_socket.uds_server_socket_fd_get()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not get the server socket FD.", rc=rc))
            return rc
        events = self._client_request_socket_epoll.poll(0.01)
        for socket_fd, event in events:
            if socket_fd == server_socket_fd:
                # Connect with the new client.
                rc, client_socket_obj = self._uds_server_socket.uds_server_socket_accept()
                if rc != RcCode.SUCCESS:
                    # Ignore this event, process next event.
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code(
                            "Can not connect with the client.", rc=rc))
                    continue

                self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "A new client arrived. {} fd: {}".format(client_socket_obj[0].getpeername(), client_socket_obj[0].fileno()),))

                # Initialize the variable for socket information
                client_sock_fd = client_socket_obj[0].fileno()

                # Add the socket information to the server socket information DB
                rc = self._client_request_info.add_client_request_info(client_sock_fd, client_socket_obj)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not remove the socket FD {} information from the server socket DB".format(
                                client_socket_obj[0].getpeername()), rc))
                    return rc
                self._client_request_socket_epoll.register(client_sock_fd, select.EPOLLIN)
            elif event & select.EPOLLIN:
                # Get the socket object from the server socket information DB
                rc, socket_obj = self._client_request_info.get_client_request_info(socket_fd, "socket_obj")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not add the socket FD {} information to the server socket DB".format(
                                socket_obj[0].getpeername()), rc))
                    return rc

                # Receive the client message
                rc, request_cmd = self._uds_server_socket.uds_client_socket_recv(socket_obj, MAX_MSG_SIZE)
                if rc != RcCode.SUCCESS:
                    # Can not receive the data from the socket due to any error.
                    # Close this socket and remove this socket from the socket dictionary.
                    # Remove the socket from the EPOLL list.
                    # Process the next event.

                    # Delete the socket information from the server socket information DB
                    rc = self._client_request_info.del_client_request_info(socket_fd)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not remove the socket FD {} information from the server socket DB".format(
                                    socket_obj[0].getpeername()), rc))
                        return rc

                    self._client_request_socket_epoll.unregister(socket_fd)

                    rc =self._uds_server_socket.uds_client_socket_close(socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not close the client socket {}".format(socket_obj.getpeername()), rc=rc))
                        return rc
                    continue

                # Convert byte data to string and execute the request
                self._logger.info("Receive the data from socket - {}".format(request_cmd))

                rc = self._server_event_handle(socket_fd, request_cmd)
                if rc != RcCode.SUCCESS:
                    # Delete the socket information from the server socket information DB
                    rc = self._client_request_info.del_client_request_info(socket_fd)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not remove the socket FD {} information from the server socket DB".format(
                                    socket_obj[0].getpeername()), rc))
                        return rc

                    self._client_request_socket_epoll.unregister(socket_fd)

                    rc =self._uds_server_socket.uds_client_socket_close(socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not close the client socket {}".format(socket_obj.getpeername()), rc=rc))
                        return rc
            elif event & select.EPOLLHUP:
                # Client disconnects the socket.
                # Clear the socket information for request list and epoll.
                # Remove the socket from the EPOLL list.

                # Get the socket object from the server socket information DB
                rc, socket_obj = self._client_request_info.get_client_request_info(socket_fd, "socket_obj")
                if rc != RcCode.DATA_NOT_FOUND and rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not add the socket FD {} information to the server socket DB".format(
                                socket_obj[0].getpeername()), rc))
                    return rc

                # Delete the socket information from the server socket information DB
                rc = self._client_request_info.del_client_request_info(socket_fd)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not remove the socket FD {} information from the server socket DB".format(
                                socket_obj[0].getpeername()), rc))
                    return rc

                self._client_request_socket_epoll.unregister(socket_fd)

                rc =self._uds_server_socket.uds_client_socket_close(socket_obj)
                if rc != RcCode.DATA_NOT_FOUND and rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not close the client socket {}".format(socket_obj.getpeername()), rc=rc))
                    return rc

                if rc == RcCode.DATA_NOT_FOUND:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code(
                            "The client socket {} is missing.".format(socket_obj.getpeername()), rc=rc))
        return RcCode.SUCCESS

    def _client_request_main_process(self):
        # Read the data from the socket
        events = self._client_service_socket_epoll.poll(0.01)
        for socket_fd, event in events:
            if event & select.EPOLLIN:
                # Get the socket object from the client socket information DB
                rc, client_socket_obj = self._client_service_info.get_client_service_info(socket_fd, "socket_obj")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "The client socket {} is not found.".format(socket_fd), rc))
                    return rc

                # Receive the data from the client socket
                rc, data = self._uds_server_socket.uds_client_socket_recv(client_socket_obj, MAX_MSG_SIZE)
                if rc != RcCode.SUCCESS:
                    # Can not receive the data from the socket due to any error.
                    # Close this socket and remove this socket from the socket dictionary.
                    # Remove the socket from the EPOLL list.
                    # Process the next event.
                    self._client_service_socket_epoll.unregister(socket_fd)
                    rc =self._uds_server_socket.uds_client_socket_close(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not close the client socket {}".format(client_socket_obj.getpeername()), rc=rc))
                        return rc
                    rc = self._client_service_info.del_client_service_info(socket_fd)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "The client socket {} is not found.".format(client_socket_obj), rc))
                        return rc
                    continue

                if data != "":
                    # Get the socket object from the client socket information DB
                    rc, serial_port_id = self._client_service_info.get_client_service_info(socket_fd, "serial_port_id")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "The client socket {} is not found.".format(socket_fd), rc))
                        return rc

                    # Broadcast the data to other client and serial port.
                    rc = self._client_socket_message_broadcast(data, serial_port_id, socket_fd)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("Process the message {} fail.".format(data), rc))
                        return rc
                else:
                    # Get the serial port ID from the service information DB
                    rc, serial_port_id = self._client_service_info.get_client_service_info(socket_fd, "serial_port_id")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("The client socket {} is not found.".format(
                                socket_fd), rc))
                        return rc

                    # Delete the socket information from the service information DB.
                    rc = self._client_service_info.del_client_service_info(socket_fd)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code("The client socket {} is not found.".format(
                                client_socket_obj), rc))
                        return rc

                    # Delete socket from the serial port DB
                    rc = self._serial_port_host_access_unregister(client_socket_obj, serial_port_id)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not unregister socket {} to serial port {}".format(
                                    client_socket_obj[0].getpeername(), serial_port_id), rc=rc))
                        return rc

                    rc, data = self._serial_port_info.get_serial_port_dict_all()

                    self._client_service_socket_epoll.unregister(socket_fd)

                    rc =self._uds_server_socket.uds_client_socket_close(client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not close the client socket {}".format(client_socket_obj.getpeername()), rc=rc))
                        return rc
            elif event & select.EPOLLHUP:
                # Client disconnects the socket.
                # Clear the socket information for request list and epoll.
                # Remove the socket from the EPOLL list.

                # Get the socket object from the service information DB
                rc, client_socket_obj = self._client_service_info.get_client_service_info(socket_fd, "socket_obj")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("The client socket {} is not found.".format(
                            socket_fd), rc))
                    return rc
                # Get the serial port ID from the service information DB
                rc, serial_port_id = self._client_service_info.get_client_service_info(socket_fd, "serial_port_id")
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("The client socket {} is not found.".format(
                            socket_fd), rc))
                    return rc

                # Delete the socket information from the service information DB.
                rc = self._client_service_info.del_client_service_info(socket_fd)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code("The client socket {} is not found.".format(
                            client_socket_obj), rc))
                    return rc

                # Delete socket from the serial port DB
                rc = self._serial_port_host_access_unregister(client_socket_obj, serial_port_id)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not unregister socket {} to serial port {}".format(
                                client_socket_obj[0].getpeername(), serial_port_id)))
                    return rc

                rc, data = self._serial_port_info.get_serial_port_dict_all()
                self._logger.info(data)

                self._client_service_socket_epoll.unregister(socket_fd)
    
                rc =self._uds_server_socket.uds_client_socket_close(client_socket_obj)
                if rc != RcCode.SUCCESS:
                    self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not close the client socket {}".format(client_socket_obj.getpeername()), rc=rc))
                    return rc
        return RcCode.SUCCESS

    def _serial_port_data_main_process(self):
        # Read the data from the serial port
        for serial_port_id in self._serial_port_config_dict:
            rc, serial_port_obj = self._serial_port_info.get_serial_port_info(serial_port_id, "serial_port_obj")
            if rc != RcCode.SUCCESS:
                self._logger.error(
                    self._logger_system.set_logger_rc_code(
                        "The serial port {} is not found.".format(serial_port_id), rc=rc))
                continue

            # Check if the serial port has been opened
            rc, state = serial_port_obj.is_open_com_port()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not get the serial port {} status.".format(serial_port_id), rc=rc))
                return rc
            if not state:
                return RcCode.DEVICE_NOT_FOUND

            # Check if there is the data waiting to read.
            rc, state = serial_port_obj.in_buffer_is_waiting()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not get the serial port {} input buffer status.".format(serial_port_id), rc=rc))
                return rc
            if not state:
                continue

            # Read the data from the serial port
            rc, data = serial_port_obj.read_com_port_data()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not read the data from the serial port {}.".format(serial_port_id), rc=rc))
                return rc

            # Broadcast the data to all clients.
            rc = self._serial_port_message_broadcast(data, serial_port_id)
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code(
                            "Can not broadcast the message read from the serial port {}.".format(
                                serial_port_id), rc=rc))
                return rc

        return RcCode.SUCCESS

    def _daemon_main(self):
        rc = self._uds_server_socket.uds_server_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code(
                    "Initialize the server socket for console server handler failed."))
            return rc

        # Create the epoll to monitor the client request.
        self._client_request_socket_epoll = select.epoll()
        rc, server_socket_fd = self._uds_server_socket.uds_server_socket_fd_get()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                        self._logger_system.set_logger_rc_code("Can not get the server socket FD.", rc=rc))
            return rc
        self._client_request_socket_epoll.register(server_socket_fd, select.EPOLLIN)
        self._client_service_socket_epoll = select.epoll()

        # Start the daemon and notify the caller that daemon has started.
        self._running = True
        self._thread_event.set()
        while self._running:
            # Process the server request.
            rc = self._server_event_main_process()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code("Process the server event fail.", rc=rc))
                self._running = False
                break

            # Process the client event.
            rc = self._client_request_main_process()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code("Process the client request fail.", rc=rc))
                self._running = False
                break

            # Process the serial port event
            _ = self._serial_port_data_main_process()
            if rc != RcCode.SUCCESS:
                self._logger.error(
                        self._logger_system.set_logger_rc_code("Process the serial port data fail.", rc=rc))
                self._running = False
                break

            time.sleep(0.01)
        return rc

    def run(self):
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return

        rc = self._init_serial_port()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                        self._logger_system.set_logger_rc_code("Initialize serial port fail."))
            return

        rc = self._daemon_main()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                        self._logger_system.set_logger_rc_code("Console server handler has stopped."))

        # Daemon has stopped. Release the resource.
        rc, client_request_info_dict = self._client_request_info.get_client_request_info_all()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                        self._logger_system.set_logger_rc_code("Get client request info fail."))
        else:
            for sock_id in client_request_info_dict:
                rc = self._uds_server_socket.uds_client_socket_close(client_request_info_dict[sock_id]["socket_obj"])
                if rc != RcCode.SUCCESS:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code("Can not release the socket fd: {}".format(sock_id)))

        rc, client_service_info_dict = self._client_service_info.get_client_server_info_all()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                        self._logger_system.set_logger_rc_code("Get client service info fail."))
        else:
            for sock_id in client_service_info_dict:
                rc = self._uds_server_socket.uds_client_socket_close(client_service_info_dict[sock_id]["socket_obj"])
                if rc != RcCode.SUCCESS:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code("Can not release the socket fd: {}".format(sock_id)))

        rc = self._uds_server_socket.uds_server_socket_close()
        if rc != RcCode.SUCCESS:
            self._logger.warning(
                self._logger_system.set_logger_rc_code("Can not release the server socket."))

        rc, serial_port_info_dict = self._serial_port_info.get_serial_port_dict_all()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Get serial port info fail."))
        else:
            for serial_port_id in serial_port_info_dict:
                rc = serial_port_info_dict[serial_port_id]["serial_port_obj"].close_com_port()
                if rc != RcCode.SUCCESS:
                    self._logger.warning(
                        self._logger_system.set_logger_rc_code(
                            "Can not release the serial port {}.".format(serial_port_id), rc=rc))

        self._logger.info(self._logger_system.set_logger_rc_code("Console server handler shutdown."))
