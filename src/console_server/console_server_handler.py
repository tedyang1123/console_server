import logging
import os
import socket
import errno
import threading
import time

import select

from src.common.rc_code import RcCode
from src.console_server.console_server_port import ConsoleServerSerialPort


MAX_MSG_SIZE = 30
MAX_CLIENT = 24


class ConsoleServerHandler(threading.Thread):
    def __init__(self, serial_port_list, thread_event, daemon_id=0):
        super().__init__()

        self._daemon_id = daemon_id

        self._thread_event = thread_event

        self._serial_port_list = serial_port_list

        # Store the serial port object
        # {
        #       "serial_port_id": {
        #           "serial_port_obj": ConsoleServerSerialPort,
        #           "description": string
        #       }
        # }
        self._serial_port_dict = {}

        # The server socket to receive the client request.
        self._server_sock = None

        # File name for creating a Unix domain socket.
        self._uds_file_name = "/tmp/server_{}.sock".format(daemon_id)

        # list the sockets which sent the request to the server.
        self._server_request_sock_epoll = None

        # Store the socket for client to access the server.
        # {
        #       fd: {
        #           "socket": Socket,
        #           "request": str,
        #           "serial_port_id": int
        #       }
        # }
        self._server_request_sock_info_dict = {}

        # list the sockets which wants to access the serial port.
        self._client_event_sock_epoll = None

        # Store the socket for client to access the serial port.
        # {
        #       fd: {
        #           "socket": Socket,
        #           "serial_port_id": int
        #       }
        # }
        self._client_event_sock_info_dict = {}

        # Store the client information which connected with the specified serial port.
        # {
        #       serial_port_id: {
        #          fd: {
        #              "running": True/False,
        #              "socket": Socket
        #          }
        #       }
        # }
        # fd is an attribute, and it is an integer represented a file number of the socket.
        # running is an attribute, and it is a flag indicate that the socket is alive.
        # socket is an attribute, and it stores the socket object.
        # port_id is an attribute, and it stores the port ID.
        self._serial_port_client_map_dict = {}

        # Store the serial port which the client connect with.
        # {
        #       fd: {
        #           "serial_port_id": int
        #       }
        # }
        self._client_serial_port_map_dict = {}

        self._running = False

        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._logger = logging.getLogger(__name__)
        self._screen_handler = logging.StreamHandler()
        self._screen_handler.setLevel(logging.WARNING)
        self._screen_handler.setFormatter(self._formatter)

        self._file_handler = logging.FileHandler("/var/log/console-server.log")
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(self._formatter)

        self._logger.setLevel(logging.DEBUG)

        self._logger.addHandler(self._screen_handler)
        self._logger.addHandler(self._file_handler)
        self._logger.propagate = False

    def is_running(self):
        return self._running

    def _init_serial_port(self):
        for serial_port_dict in self._serial_port_list:
            serial_port_id = serial_port_dict["port_id"]
            serial_port_obj = ConsoleServerSerialPort(serial_port_id)
            rc = serial_port_obj.create_serial_port()
            if rc != RcCode.SUCCESS:
                self._logger.warning("Create serial port {} failed.".format(serial_port_id))
                return rc
            self._serial_port_dict[serial_port_id] = {}
            self._serial_port_dict[serial_port_id]["serial_port_obj"] = serial_port_obj
            self._serial_port_client_map_dict[serial_port_id] = {}
        return RcCode.SUCCESS

    def _check_serial_port_id(self, serial_port_id):
        for serial_port_dict in self._serial_port_list:
            port_id = serial_port_dict["port_id"]
            if port_id == serial_port_id:
                return True
        return False

    def _uds_socket_init(self):
        if os.path.exists(self._uds_file_name):
            os.remove(self._uds_file_name)
        try:
            self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server_sock.bind(self._uds_file_name)
            self._server_sock.listen(MAX_CLIENT)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _uds_socket_connect(self):
        try:
            client_sock, _ = self._server_sock.accept()
        except OSError:
            return RcCode.FAILURE, None
        return RcCode.SUCCESS, client_sock

    def _uds_socket_send(self, sock, data):
        try:
            sock.sendall(data)
        except OSError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def _uds_socket_recv(self, sock, max_size):
        wait = True
        data = ""
        while wait:
            try:
                data = sock.recv(max_size)
                wait = False
            except OSError as e:
                if e.errno != errno.EAGAIN:
                    continue
                return RcCode.FAILURE, None
        return RcCode.SUCCESS, data

    def _uds_socket_close(self, sock):
        try:
            sock.close()
        except OSError:
            pass
        return RcCode.SUCCESS

    def _server_socket_connet(self):
        rc, client_sock = self._uds_socket_connect()
        if rc != RcCode.SUCCESS:
            return rc, None
        return RcCode.SUCCESS, client_sock

    def _serial_port_message_broadcast(self, msg, serial_port):
        client_socket_dict = self._serial_port_client_map_dict[serial_port]
        for i in client_socket_dict:
            # Ignore the client which has been stopped.
            socket_info_dict = self._serial_port_client_map_dict[i]
            if not socket_info_dict["running"]:
                # Socket has been closed
                continue

            # Send the message to the other client
            rc = self._uds_socket_send(socket_info_dict["socket"], msg)
            if rc != RcCode.SUCCESS:
                # Can not send the data to the client.
                # Force close the socket and set the socket to not running.
                _ = self._uds_socket_close(socket_info_dict["socket"])
                socket_info_dict["running"] = False

        return RcCode.SUCCESS

    def _client_socket_message_broadcast(self, msg, serial_port, socket_no):
        client_socket_dict = self._serial_port_client_map_dict[serial_port]
        for fd in client_socket_dict:
            if fd == socket_no:
                # Socket is the source socket.
                continue
            socket_info_dict = self._serial_port_client_map_dict[fd]
            if not socket_info_dict["running"]:
                # Socket has been closed
                continue
            rc = self._uds_socket_send(socket_info_dict["socket"], msg)
            if rc != RcCode.SUCCESS:
                # Can not send the data to the client.
                # Force close the socket and set the socket to not running.
                _ = self._uds_socket_close(socket_info_dict["socket"])
                socket_info_dict["running"] = False

        # Send the data to serial port.
        serial_port_obj = self._serial_port_dict[serial_port]["serial_port_obj"]

        # Check if the serial port has been opened
        rc, state = serial_port_obj.is_open_com_port()
        if rc != RcCode.SUCCESS:
            return rc
        if not state:
            return RcCode.DEVICE_NOT_FOUND

        # Check if the message in the buffer has been sent.
        rc, state = serial_port_obj.output_buffer_is_waiting()
        if rc != RcCode.SUCCESS:
            return rc
        if state:
            return RcCode.DEVICE_BUSY

        # Write the message to the serial port.
        rc = serial_port_obj.write_com_port_data(msg)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS

    def _serial_port_client_map_clear(self, serial_port):
        close_client_fd_list = []

        # Find all sockets which have been closed
        client_socket_dict = self._serial_port_client_map_dict[serial_port]
        for fd in client_socket_dict:
            if not client_socket_dict[fd]["running"]:
                # Save the fd and we will delete it later
                close_client_fd_list.append(fd)

        # Delete the fd now
        for fd in close_client_fd_list:
            del client_socket_dict[fd]

        return RcCode.SUCCESS

    def _serial_port_access_register(self, sock, serial_port_id):
        fd = sock.fileno()
        self._serial_port_client_map_dict[fd] = {}
        client_socket_dict = self._serial_port_client_map_dict[serial_port_id]

        # Store the socket information
        client_socket_dict[fd] = {}
        client_socket_dict[fd]["socket"] = sock
        client_socket_dict[fd]["running"] = True
        client_socket_dict[fd]["port_id"] = serial_port_id
        self._client_serial_port_map_dict[fd] = serial_port_id

        return RcCode.SUCCESS

    def _serial_port_access_unregister(self, sock_fd, serial_port=-1):
        if serial_port != -1:
            # In this case we don't know the socket open which serial port.
            # We have to iterate the serial port map client table to find the specified socket.
            for port_id in self._serial_port_client_map_dict:
                client_socket_dict = self._serial_port_client_map_dict[port_id]
                for client_fd in client_socket_dict:
                    if sock_fd == client_fd:
                        client_socket_dict[client_fd]["running"] = False
        else:
            # Here we set the 'running' flag to False and later the clear process will kill.
            client_socket_dict = self._serial_port_client_map_dict[serial_port]
            client_socket_dict[sock_fd]["running"] = False
        return RcCode.SUCCESS

    def _server_event_handle(self, sock_fd, request_cmd):
        match request_cmd:
            case "connect" | "disconnect" | "baudrate" | "description":
                # Get the new request, init the request data variable.
                self._server_request_sock_info_dict[sock_fd] = {}
                # This is a valid request. We store it and wait the more information form the client.
                self._server_request_sock_info_dict[sock_fd]["request"] = request_cmd

                # Notify the client that command executed successful
                rc = self._uds_socket_send(self._server_request_sock_info_dict[sock_fd], "OK")
                if rc != RcCode.SUCCESS:
                    return rc
            case _:
                match self._server_request_sock_info_dict[sock_fd]["request"]:
                    case "connect":
                        try:
                            # Check if serial port ID is valid
                            serial_port_id = int(request_cmd)
                            if not self._check_serial_port_id(serial_port_id):
                                return RcCode.INVALID_VALUE

                            # Open the serial port
                            rc = self._serial_port_dict[serial_port_id]["serial_port_obj"].open_com_port()
                            if rc != RcCode.SUCCESS:
                                return rc

                            server_request_sock_info = self._server_request_sock_info_dict[sock_fd]

                            # Register a new client to access the serial port
                            rc = self._serial_port_access_register(server_request_sock_info["socket"], serial_port_id)
                            if rc != RcCode.SUCCESS:
                                return rc

                            # Move the socket from server request epoll pool to client event epoll pool
                            self._server_request_sock_epoll.unregister(sock_fd)
                            self._client_event_sock_epoll.register(sock_fd, select.EPOLLIN)

                            # Move the server request information to client event information
                            self._client_event_sock_info_dict[sock_fd] = {}
                            self._client_event_sock_info_dict[sock_fd]["socket"] = server_request_sock_info["socket"]
                            self._client_event_sock_info_dict[sock_fd]["serial_port_id"] = serial_port_id

                            # Notify the client that command executed successful
                            rc = self._uds_socket_send(server_request_sock_info["socket"], "OK")
                            if rc != RcCode.SUCCESS:
                                return rc

                            # Delete the socket information due to this socket has been moved to client event handler.
                            del server_request_sock_info
                        except ValueError:
                            self._uds_socket_send(self._server_request_sock_info_dict[sock_fd], "Failed")
                            return RcCode.INVALID_VALUE
                    case "disconnect":
                        server_request_sock_info = self._server_request_sock_info_dict[sock_fd]
                        try:
                            # Check if serial port ID is valid
                            serial_port_id = int(request_cmd)
                            if not self._check_serial_port_id(serial_port_id):
                                return RcCode.INVALID_VALUE

                            # Close the serial port
                            rc = self._serial_port_dict[serial_port_id]["serial_port_obj"].close_com_port()
                            if rc != RcCode.SUCCESS:
                                return rc

                            # Set the running state to false. We will clear this entry later
                            client_socket_dict = self._serial_port_client_map_dict[serial_port_id]
                            client_socket_dict[sock_fd]["running"] = False

                            # Remove the socket from the epoll pool
                            self._client_event_sock_epoll.unregister(sock_fd)

                            # Notify the client that command executed successful
                            rc = self._uds_socket_send(server_request_sock_info, "OK")
                            if rc != RcCode.SUCCESS:
                                return rc
                        except ValueError:
                            self._uds_socket_send(server_request_sock_info, "Failed")
                            return RcCode.INVALID_VALUE
                    case "baudrate":
                        server_request_sock_info = self._server_request_sock_info_dict[sock_fd]
                        if "serial_port_id" not in server_request_sock_info:
                            try:
                                # Get the first parameter. It is a port ID.
                                serial_port_id = int(request_cmd)
                                if not self._check_serial_port_id(serial_port_id):
                                    return RcCode.INVALID_VALUE

                                # Save the port ID.
                                server_request_sock_info["serial_port_id"] = serial_port_id

                                # Notify the client that command executed successful
                                rc = self._uds_socket_send(server_request_sock_info, "OK")
                                if rc != RcCode.SUCCESS:
                                    return rc
                            except ValueError:
                                self._uds_socket_send(server_request_sock_info, "Failed")
                                return RcCode.INVALID_VALUE
                        else:
                            try:
                                # Get the second parameter. It is a baud rate.
                                baud_rate = int(request_cmd)

                                # Set the new baud rate to the serial prot
                                serial_port_id = server_request_sock_info["serial_port_id"]
                                serial_port_obj = self._serial_port_dict[serial_port_id]["serial_port_obj"]
                                rc = serial_port_obj.set_com_port_baud_rate(baud_rate)
                                if rc != RcCode.SUCCESS:
                                    return rc

                                # Delete the port_id attribute
                                del server_request_sock_info["serial_port_id"]

                                # Update the baud rate in the serial port config
                                self._serial_port_list[serial_port_id]["baud_rate"] = baud_rate

                                # Notify the client that command executed successful
                                rc = self._uds_socket_send(server_request_sock_info, "OK")
                                if rc != RcCode.SUCCESS:
                                    return rc
                            except ValueError:
                                self._uds_socket_send(server_request_sock_info, "Failed")
                                return RcCode.INVALID_VALUE
                    case _:
                        return RcCode.INVALID_VALUE
        return RcCode.SUCCESS

    def _server_event_main_process(self):
        events = self._server_request_sock_epoll.poll(0.01)
        for sock_fd, event in events:
            if sock_fd == self._server_sock.fileno():
                # Connect with the new client.
                rc, client_sock = self._uds_socket_connect()
                if rc != RcCode.SUCCESS:
                    # Ignore this event, process next event.
                    continue

                # Initialize the variable for socket information
                client_sock_fd = client_sock.fileno()
                self._server_request_sock_info_dict[client_sock_fd] = {}
                self._server_request_sock_info_dict[client_sock_fd]["socket"] = client_sock
                self._server_request_sock_info_dict[client_sock_fd]["request"] = ""
            elif event & select.EPOLLIN:
                server_request_sock_info = self._server_request_sock_info_dict[sock_fd]

                # Receive the client message
                rc, data = self._uds_socket_recv(server_request_sock_info["socket"], MAX_MSG_SIZE)
                if rc != RcCode.SUCCESS:
                    # Can not receive the data from the socket due to any error.
                    # Close this socket and remove this socket from the socket dictionary.
                    # Remove the socket from the EPOLL list.
                    # Process the next event.
                    server_request_sock_info.close()
                    del server_request_sock_info
                    self._server_request_sock_epoll.unregister(sock_fd)
                    continue

                # Convert byte data to string and execute the request
                request_cmd = str(data, encoding='ascii')
                rc = self._server_event_handle(sock_fd, request_cmd)
                if rc != RcCode.SUCCESS:
                    # The message sent from the client is not valid, or any error occurs when processing the event.
                    # Close this socket and remove this socket from the socket dictionary.
                    # Remove the socket from the EPOLL list.
                    server_request_sock_info.close()
                    del self._server_request_sock_info_dict[sock_fd]
                    self._server_request_sock_epoll.unregister(sock_fd)
            elif event & select.EPOLLHUP:
                # Client disconnects the socket.
                # Clear the socket information for request list and epoll.
                # Remove the socket from the EPOLL list.
                self._server_request_sock_info_dict[sock_fd].close()
                del self._server_request_sock_info_dict[sock_fd]
                self._server_request_sock_epoll.unregister(sock_fd)
        return RcCode.SUCCESS

    def _client_request_main_process(self):
        # Read the data from the socket
        events = self._client_event_sock_epoll.poll(0.01)
        for sock_fd, event in events:
            if event & select.EPOLLIN:
                sock_info = self._client_event_sock_info_dict[sock_fd]

                # Receive the data from the client socket
                rc, data = self._uds_socket_recv(sock_info["socket"], MAX_MSG_SIZE)
                if rc != RcCode.SUCCESS:
                    # Can not receive the data from the socket due to any error.
                    # Close this socket and remove this socket from the socket dictionary.
                    # Remove the socket from the EPOLL list.
                    # Process the next event.
                    sock_info["socket"].close()
                    del self._client_event_sock_info_dict[sock_fd]
                    self._client_event_sock_epoll.unregister(sock_fd)
                    continue

                # Broadcast the data to other client and serial port.
                rc = self._client_socket_message_broadcast(data, sock_info["serial_port_id"], sock_fd)
                if rc != RcCode.SUCCESS:
                    return rc
            elif event & select.EPOLLHUP:
                # Client disconnects the socket.
                # Clear the socket information for request list and epoll.
                # Remove the socket from the EPOLL list.
                self._client_event_sock_info_dict[sock_fd]["socket"].close()
                del self._client_event_sock_info_dict[sock_fd]
                self._client_event_sock_epoll.unregister(sock_fd)
        return RcCode.SUCCESS

    def _serial_port_data_main_process(self):
        # Read the data from the serial port
        for serial_port_dict in self._serial_port_list:
            serial_port_id = serial_port_dict["port_id"]
            serial_port_obj = self._serial_port_dict[serial_port_id]["serial_port_obj"]

            # Check if the serial port has been opened
            rc, state = serial_port_obj.is_open_com_port()
            if rc != RcCode.SUCCESS:
                return rc
            if not state:
                return RcCode.DEVICE_NOT_FOUND

            # Check if there is the data waiting to read.
            rc, state = serial_port_obj.in_buffer_is_waiting()
            if rc != RcCode.SUCCESS:
                return rc
            if not state:
                continue

            # Read the data from the serial port
            rc, data = serial_port_obj.read_com_port_data()
            if rc != RcCode.SUCCESS:
                return rc

            # Broadcast the data to all clients.
            rc = self._serial_port_message_broadcast(data, serial_port_id)
            if rc != RcCode.SUCCESS:
                return rc

        return RcCode.SUCCESS

    def _daemon_main(self):
        rc = self._uds_socket_init()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Initialize the server socket for console server handler failed.")
            return rc

        # Create the epool to monitor the client request.
        self._server_request_sock_epoll = select.epoll()
        self._server_request_sock_epoll.register(self._server_sock.fileno(), select.EPOLLIN)
        self._client_event_sock_epoll = select.epoll()

        # Start the daemon and notify the caller that daemon has started.
        self._running = True
        self._thread_event.set()
        while self._running:
            # Process the server request.
            rc = self._server_event_main_process()
            if rc != RcCode.SUCCESS:
                self._logger.warning("Process the server event fail. rc: {}".format(rc))
                self._running = False
                break

            # Process the client event.
            rc = self._client_request_main_process()
            if rc != RcCode.SUCCESS:
                self._logger.warning("Process the client request fail. rc: {}".format(rc))
                self._running = False
                break

            # Process the serial port event
            _ = self._serial_port_data_main_process()
            if rc != RcCode.SUCCESS:
                self._logger.warning("Process the serial port data fail. rc: {}".format(rc))
                self._running = False
                break

            # Clear unused socket information
            for serial_port_dict in self._serial_port_list:
                serial_port_id = serial_port_dict["port_id"]
                rc = self._serial_port_client_map_clear(serial_port_id)
                if rc != RcCode.SUCCESS:
                    self._running = False
                    break
            time.sleep(0.01)
        return rc

    def run(self):
        rc = self._init_serial_port()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Initialize serial port fail.")
            return

        rc = self._daemon_main()
        if rc != RcCode.SUCCESS:
            self._logger.warning("Console server handler has stopped.")

        # Daemon has stopped. Release the resource.
        for sock_id in self._server_request_sock_info_dict:
            rc = self._uds_socket_close(self._server_request_sock_info_dict[sock_id]["socket"])
            if rc != RcCode.SUCCESS:
                self._logger.warning("Can not release the socket fd: {}".format(sock_id))

        for sock_id in self._client_event_sock_info_dict:
            self._uds_socket_close(self._client_event_sock_info_dict[sock_id]["socket"])
            if rc != RcCode.SUCCESS:
                self._logger.warning("Can not release the socket fd: {}".format(sock_id))

        rc = self._uds_socket_close(self._server_sock)
        if rc != RcCode.SUCCESS:
            self._logger.warning("Can not release the server socket.")

        for serial_port_id in self._serial_port_dict:
            rc = self._serial_port_dict[serial_port_id]["serial_port_obj"].close_com_port()
            if rc != RcCode.SUCCESS:
                self._logger.warning("Can not release the serial port {}.".format(serial_port_id))

        self._logger.warning("Console server handler shutdown.")
