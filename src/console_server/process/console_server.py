import multiprocessing
import time

import select

from src.common.logger_system import LoggerSystem
from src.common.message_queue import BidirectionalMessageQueue
from src.common.message import MessageRequestMsg, MessageReplyMsg
from src.common.rc_code import RcCode
from src.common.uds_lib import UnixDomainServerSocket, serialize_data, deserialize_data
from src.console_server.process.common import SerialPortPair
from src.console_server.process.console_server_handler import ConsoleServerHandler
from src.console_server.process.console_server_port import ConsoleServerSerialPort


class _SerialPortConfigDict:
    def __init__(self):
        self._serial_port_group_list = {}

    def add_port_group(self, group_id):
        if group_id in self._serial_port_group_list:
            return RcCode.DATA_EXIST
        self._serial_port_group_list[group_id] = {}
        return RcCode.SUCCESS

    def del_port_group(self, group_id):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_group_list[group_id]
        return RcCode.SUCCESS

    def search_group_id(self, serial_port_id):
        for group_id in self._serial_port_group_list:
            for port_id in self._serial_port_group_list[group_id]:
                if port_id == serial_port_id:
                    return RcCode.SUCCESS, group_id
        return RcCode.DATA_NOT_FOUND, None

    def get_port_group(self, group_id):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND, None
        return RcCode.SUCCESS, self._serial_port_group_list[group_id]

    def add_serial_port_config(self, group_id, serial_port_id, port_name, baud_rate, alias_name):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND
        if serial_port_id in self._serial_port_group_list[group_id]:
            return RcCode.DATA_EXIST
        self._serial_port_group_list[group_id][serial_port_id] = {}
        self._serial_port_group_list[group_id][serial_port_id]['port_name'] = port_name
        self._serial_port_group_list[group_id][serial_port_id]['baud_rate'] = baud_rate
        self._serial_port_group_list[group_id][serial_port_id]['alias_name'] = alias_name
        return RcCode.SUCCESS

    def del_serial_port_config(self, group_id, serial_port_id):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND
        if serial_port_id not in self._serial_port_group_list[group_id]:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_group_list[group_id][serial_port_id]
        return RcCode.SUCCESS

    def get_serial_port_config(self, group_id, serial_port_id, field=None):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND, None
        if serial_port_id not in self._serial_port_group_list[group_id]:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS, self._serial_port_group_list[group_id][serial_port_id]
        return RcCode.SUCCESS,  self._serial_port_group_list[group_id][serial_port_id][field]

    def modify_serial_port_config(self, group_id, serial_port_id, field, value):
        if group_id not in self._serial_port_group_list:
            return RcCode.DATA_NOT_FOUND, None
        if serial_port_id not in self._serial_port_group_list[group_id]:
            return RcCode.DATA_NOT_FOUND, None
        self._serial_port_group_list[group_id][serial_port_id][field] = value
        return RcCode.SUCCESS

    def get_serial_port_config_all(self):
        return RcCode.SUCCESS, self._serial_port_group_list


class ConsoleServerClientInfoDict:
    def __init__(self):
        self._client_info_dict = {}

    def add_client_info(self, socket_fd, socket_obj):
        if socket_fd in self._client_info_dict:
            return RcCode.DATA_EXIST
        self._client_info_dict[socket_fd] = {}
        self._client_info_dict[socket_fd]["socket_obj"] = socket_obj
        return RcCode.SUCCESS

    def del_client_info(self, socket_fd):
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND
        del self._client_info_dict[socket_fd]
        return RcCode.SUCCESS

    def get_client_info(self, socket_fd, field=None):
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if socket_fd not in self._client_info_dict:
            return RcCode.DATA_NOT_FOUND, None
        if field is None:
            return RcCode.SUCCESS, self._client_info_dict[socket_fd]
        return  RcCode.SUCCESS, self._client_info_dict[socket_fd][field]

    def get_client_info_all(self):
        return RcCode.SUCCESS, self._client_info_dict


class ConsoleServer(multiprocessing.Process):
    def __init__(self, num_of_serial_port, daemon_id, max_port_group=8, max_client=10, max_server_msg_size=1024):
        self._num_of_serial_port = num_of_serial_port
        self._daemon_id = daemon_id
        self._max_port_group = max_port_group
        self._max_client = max_client
        self._max_server_msg_size = max_server_msg_size
        multiprocessing.Process.__init__(self, name="ConsoleServer_{}".format(daemon_id))

        self._serial_port_obj_dict = {}

        self._logger_system = LoggerSystem(self.name)
        self._logger = self._logger_system.get_logger()

        self._serial_port_config = _SerialPortConfigDict()

        self._server_mgmt_socket = None
        self._server_mgmt_sock_epoll = None
        self._process_handler_list = []
        self._client_info = ConsoleServerClientInfoDict()
        self._running = False

    def __del__(self):
        rc, client_info_dict = self._client_info.get_client_info_all()
        if rc != RcCode.SUCCESS:
            return
        for sock_fd in client_info_dict:
            self._server_mgmt_socket.uds_client_socket_close(client_info_dict[sock_fd]["socket_obj"])
        self._server_mgmt_socket.uds_server_socket_close()

    def _init_server(self):
        rc = self._logger_system.init_logger_system()
        if rc != RcCode.SUCCESS:
            return rc

        # Create the server management socket
        self._server_mgmt_socket = UnixDomainServerSocket(
            self._max_client, "/tmp/server_mgmt.sock", self._logger_system)
        rc = self._server_mgmt_socket.uds_server_socket_init()
        if rc != RcCode.SUCCESS:
            return rc

        # Create the port group to store the serial port config
        for group_id in range(self._max_port_group):
            rc = self._serial_port_config.add_port_group(group_id)
            if rc != RcCode.SUCCESS:
                return rc

        # Init the serial port and related server socket
        for serial_port_id in self._num_of_serial_port:
            group_id = serial_port_id % 8

            # add the new port config in the port group for thew specific port ID
            rc = self._serial_port_config.add_serial_port_config(
                serial_port_id, group_id, "COM{}".format(serial_port_id), 115200, "COM{}".format(serial_port_id))
            if rc != RcCode.SUCCESS:
                return rc

            # Create serial port object to access serial port
            serial_port_obj = ConsoleServerSerialPort(serial_port_id, self._logger_system)
            rc = serial_port_obj.create_serial_port(115200)
            if rc != RcCode.SUCCESS:
                return rc

            # Create server socket to monitor the user message
            server_socket = UnixDomainServerSocket(
                5, "/tmp/server_{}.sock".format(serial_port_id), self._logger_system)
            rc = server_socket.uds_server_socket_init()
            if rc != RcCode.SUCCESS:
                return rc

            # Bind them as an object
            self._serial_port_obj_dict[serial_port_id] = SerialPortPair(serial_port_obj, server_socket)

        time_table = {}

        # Create process and queue
        for group_id in range(self._max_port_group):
            queue = BidirectionalMessageQueue()
            handler_process = ConsoleServerHandler(tx_queue_func=queue.message_rx_queue_send,
                                                   rx_queue_func=queue.message_tx_queue_receive,
                                                   process_id=group_id)
            handler_process.start()
            self._process_handler_list.append((handler_process, queue))
            time_table[group_id] = time.time()

        count = 0
        complete_list = [False for i in range(self._max_port_group)]

        # Wait the process complete.
        while count > 5:
            for group_id in range(self._max_port_group):
                # Check if process has started
                if complete_list[group_id]:
                    continue

                queue = self._process_handler_list[group_id][0]

                # Receive the message from the process
                rc, data = queue.message_rx_queue_receive()
                if rc == RcCode.DATA_NOT_READY:
                    if (time.time() - time_table[group_id]) > 5:
                        return RcCode.FAILURE
                    elif rc == RcCode.QUEUE_CLOSED:
                        return rc
                if not isinstance(data, dict):
                    return RcCode.INVALID_TYPE
                elif "result" not in data:
                    return RcCode.INVALID_VALUE
                elif data["result"] != "OK":
                    return RcCode.ERROR
                else:
                    complete_list[group_id] = True
            count = count + 1

        # Init complete
        return RcCode.SUCCESS

    def client_msg_handle(self, request_data, client_sock):
        # Deserialize the data
        # {
        #       "request": str
        #       "serial_port_id": int
        #       "data": {
        #           ...
        #       }
        # }
        request_data = deserialize_data(request_data)

        # Process the request
        request = request_data["request"]
        match request:
            case "port_config":
                # Get prot config entry
                rc, port_group_config_dict = self._serial_port_config.get_serial_port_config_all()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg("change_baud_rate", "Failed", "Can not get the port entry")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # Merge all port group in a new dict
                port_config_dict = {}
                for group_id in port_group_config_dict:
                    port_config_dict = port_config_dict | port_config_dict | port_group_config_dict[group_id]
                self._logger.info(
                    self._logger_system.set_logger_rc_code("Data is ready. {}".format(port_config_dict)))

                # Send the port config information to client by socket
                server_reply = MessageReplyMsg("port_config", "OK", serialize_data(port_config_dict))
                rc = self._server_mgmt_socket.uds_client_socket_send(
                    client_sock, serialize_data(server_reply.get_message()))
                if rc != RcCode.SUCCESS:
                    return rc
            case "add_serial_port":
                ########################################################################################
                # Preprocess the request
                ########################################################################################

                # Check if serial port ID is in the request message
                if "serial_port_id" not in request_data:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Missing the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                serial_port_id = request_data["serial_port_id"]

                # The port name
                port_name = "COM{}".format(serial_port_id)

                # Check if baud rate is in the request message
                baud_rate = 115200 \
                    if request_data["data"] is None or "baud_rate" not in request_data else \
                        request_data["data"]["baud_rate"]

                # Check if group ID is in the request message
                group_id = (serial_port_id % 8) \
                    if request_data["data"] is None or "group_id" not in request_data else \
                        request_data["data"]["group_id"]

                # Check if alias name in the request message
                alias_name = port_name \
                    if request_data["data"] is None or "alias_name" not in request_data else \
                        request_data["data"]["alias_name"]

                ########################################################################################
                # Allocate the resource
                ########################################################################################

                # Check serial has been created or not
                if serial_port_id in self._serial_port_obj_dict:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "The serial port has been created.")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # Create serial port object to access serial port
                serial_port_obj = ConsoleServerSerialPort(serial_port_id, self._logger_system)
                rc = serial_port_obj.create_serial_port(baud_rate)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "Can not create the serial port object")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return rc

                # Create server socket to monitor the user message
                server_socket = UnixDomainServerSocket(
                    5, "/tmp/server_{}.sock".format(serial_port_id), self._logger_system)
                rc = server_socket.uds_server_socket_init()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "Can not create the server socket object")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return rc

                self._serial_port_obj_dict[serial_port_id] = SerialPortPair(serial_port_obj, server_socket)

                ########################################################################################
                # Notify the handler to process request
                ########################################################################################

                request_data = {
                    "data": {
                        "serial_pair": self._serial_port_obj_dict[serial_port_id],
                    }
                }

                # Notify the handler to process request
                rc = self._process_handler_list[group_id][0].message_tx_queue_send(
                    MessageRequestMsg("add_serial_port", serial_port_id, request_data))
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "Can not send the request to handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # Wait the handler to reply the result
                rc, reply_data = self._process_handler_list[group_id][0].message_tx_queue_receive()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "Can not add  the new port in the handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Update the port config DB
                ########################################################################################

                # add the new port in the port config
                rc = self._serial_port_config.add_serial_port_config(
                    group_id, serial_port_id, port_name, baud_rate, alias_name)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "Can not set the alias name in the port config")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the client request process completely
                ########################################################################################

                # Notify the client that server adds the new port
                server_reply = MessageReplyMsg("add_serial_port", "OK")
                rc = self._server_mgmt_socket.uds_client_socket_send(
                    client_sock, serialize_data(server_reply.get_message()))
                if rc != RcCode.SUCCESS:
                    return rc
            case "del_serial_port":
                ########################################################################################
                # Preprocess the request
                ########################################################################################

                # Check if serial port ID is in the request message
                if "serial_port_id" not in request_data:
                    server_reply = MessageReplyMsg("del_serial_port", "Failed", "Missing the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                serial_port_id = request_data["serial_port_id"]

                # Search the group ID by the serial port ID
                rc, group_id =  self._serial_port_config.search_group_id(serial_port_id)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not find the group ID by the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the handler to process request
                ########################################################################################

                # Notify the handler to process request
                rc = self._process_handler_list[group_id][0].message_tx_queue_send(
                    MessageRequestMsg("del_serial_port", serial_port_id))
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not send the request to handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # Wait the handler to reply the result
                rc, data = self._process_handler_list[group_id][0].message_tx_queue_receive()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not add  the new port in the handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Release the resource
                ########################################################################################

                if serial_port_id not in self._serial_port_obj_dict:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "The serial does not exist.")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                rc = self._serial_port_obj_dict[0].get_serial_port_obj().close_com_port()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not release the serial port")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                rc = self._serial_port_obj_dict[0].get_server_socket_obj().uds_server_socket_close()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not release the server socket")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                del self._serial_port_obj_dict[serial_port_id]

                ########################################################################################
                # Update the port config DB
                ########################################################################################

                # delete the new port in the port config
                rc = self._serial_port_config.del_serial_port_config(group_id, serial_port_id)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not set the alias name in the port config")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the client request process completely
                ########################################################################################

                # Notify the client that server adds the new port
                server_reply = MessageReplyMsg("del_serial_port", "OK")
                rc = self._server_mgmt_socket.uds_client_socket_send(
                    client_sock, serialize_data(server_reply.get_message()))
                if rc != RcCode.SUCCESS:
                    return rc
            case "change_baud_rate":
                ########################################################################################
                # Preprocess the request
                ########################################################################################

                # Check if serial port ID is in the request message
                if "serial_port_id" not in request_data:
                    server_reply = MessageReplyMsg("change_baud_rate", "Failed", "Missing the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                serial_port_id = request_data["serial_port_id"]

                # Check if baud rate is in the request message
                if request_data["data"] is None or "baud_rate" not in request_data:
                    server_reply = MessageReplyMsg("change_baud_rate", "Failed", "Missing the baud rate")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                baud_rate = request_data["data"]["baud_rate"]

                # Search the group ID by the serial port ID
                rc, group_id =  self._serial_port_config.search_group_id(serial_port_id)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Can not find the group ID by the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the handler to process request
                ########################################################################################

                # Notify the handler to process the request
                request_data = {
                    "data": {
                        "baud_rate": baud_rate,
                    }
                }
                rc = self._process_handler_list[group_id][0].message_tx_queue_send(
                    MessageRequestMsg("change_baud_rate", serial_port_id, request_data))
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Can not send the request to handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # Wait the handler to reply the result
                rc, data = self._process_handler_list[group_id][0].message_tx_queue_receive()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Can not change the baud rate in the handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Update the port config DB
                ########################################################################################

                # Update the baud rate in the port config
                rc = self._serial_port_config.modify_serial_port_config(group_id, serial_port_id, "baud_rate", baud_rate)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Can not delete the port in the port config")
                    rc = self._server_mgmt_socket.uds_client_socket_send(client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the client request process completely
                ########################################################################################

                # Notify the client that server sets the baud rate completely
                server_reply = MessageReplyMsg("change_baud_rate", "OK")
                rc = self._server_mgmt_socket.uds_client_socket_send(
                    client_sock, serialize_data(server_reply.get_message()))
                if rc != RcCode.SUCCESS:
                    return rc
            case "change_alias_name":
                ########################################################################################
                # Preprocess the request
                ########################################################################################

                # Check if serial port ID is in the request message
                if "serial_port_id" not in request_data:
                    server_reply = MessageReplyMsg("change_baud_rate", "Failed", "Missing the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                serial_port_id = request_data["serial_port_id"]

                # Check if alias name is in the request message
                if request_data["data"] is None or "alias_name" not in request_data:
                    server_reply = MessageReplyMsg("change_alias_name", "Failed", "Missing the alias name")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                alias_name = request_data["data"]["alias_name"]

                # Search the group ID by the serial port ID
                rc, group_id =  self._serial_port_config.search_group_id(serial_port_id)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Can not find the group ID by the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Update the port config DB
                ########################################################################################

                # Update the alias name in the port config
                rc = self._serial_port_config.modify_serial_port_config(group_id, serial_port_id, "alias_name", alias_name)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Can not set the alias name in the port config")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the client request process completely
                ########################################################################################

                # Notify the client that server sets the alias name completely
                server_reply = MessageReplyMsg("change_alias_name", "OK")
                rc = self._server_mgmt_socket.uds_client_socket_send(
                    client_sock, serialize_data(server_reply.get_message()))
                if rc != RcCode.SUCCESS:
                    return rc
            case "change_group":
                ########################################################################################
                # Preprocess the request
                ########################################################################################

                # Check if serial port ID is in the request message
                if "serial_port_id" not in request_data:
                    server_reply = MessageReplyMsg("change_baud_rate", "Failed", "Missing the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                serial_port_id = request_data["serial_port_id"]

                # Check if baud rate is in the request message
                if request_data["data"] is None or "group_id" not in request_data:
                    server_reply = MessageReplyMsg("change_group", "Failed", "Missing the group ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS
                new_group_id = request_data["data"]["group_id"]

                # Search the group ID by the serial port ID
                rc, old_group_id =  self._serial_port_config.search_group_id(serial_port_id)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_baud_rate", "Failed", "Can not find the group ID by the serial port ID")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the handler to process request
                ########################################################################################

                # Notify the handler to process request
                rc = self._process_handler_list[old_group_id][0].message_tx_queue_send(
                    MessageRequestMsg("del_serial_port", serial_port_id))
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not send the request to handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # Wait the handler to reply the result
                rc, data = self._process_handler_list[old_group_id][0].message_tx_queue_receive()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "del_serial_port", "Failed", "Can not add  the new port in the handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                request_data = {
                    "data": {
                        "serial_obj": self._serial_port_obj_dict[serial_port_id],
                    }
                }

                # Notify the handler to process request
                rc = self._process_handler_list[new_group_id][0].message_tx_queue_send(
                    MessageRequestMsg("add_serial_port", serial_port_id, request_data))
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "Can not send the request to handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # Wait the handler to reply the result
                rc, data = self._process_handler_list[new_group_id][0].message_tx_queue_receive()
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "add_serial_port", "Failed", "Can not add  the new port in the handler")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Update the port config DB
                ########################################################################################

                rc, port_entry = self._serial_port_config.get_serial_port_config(old_group_id, serial_port_id)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_group", "Failed", "Can not delete the port in the port config")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # delete the new port in the port config
                rc = self._serial_port_config.del_serial_port_config(old_group_id, serial_port_id)
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_group", "Failed", "Can not delete the port in the port config")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                # add the new port in the port config
                rc = self._serial_port_config.add_serial_port_config(
                    new_group_id, serial_port_id, port_entry['port_name'], port_entry['baud_rate'], port_entry['alias_name'])
                if rc != RcCode.SUCCESS:
                    server_reply = MessageReplyMsg(
                        "change_group", "Failed", "Can not set the alias name in the port config")
                    rc = self._server_mgmt_socket.uds_client_socket_send(
                        client_sock, serialize_data(server_reply.get_message()))
                    if rc != RcCode.SUCCESS:
                        return rc
                    return RcCode.SUCCESS

                ########################################################################################
                # Notify the client request process completely
                ########################################################################################

                # Notify the client that server sets the alias name completely
                server_reply = MessageReplyMsg("change_group", "OK")
                rc = self._server_mgmt_socket.uds_client_socket_send(
                    client_sock, serialize_data(server_reply.get_message()))
                if rc != RcCode.SUCCESS:
                    return rc
            case "shutdown":
                self._running = False
            case _:
                server_reply = MessageReplyMsg(request, "Failed", "Unknown request")
                rc = self._server_mgmt_socket.uds_client_socket_send(
                    client_sock, serialize_data(server_reply.get_message()))
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS

    def daemon_main(self):
        # Create the epoll to monitor the server socket
        self._server_mgmt_sock_epoll = select.epoll()
        rc, server_socket_fd = self._server_mgmt_socket.uds_server_socket_fd_get()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Can not get the server socket FD.", rc=rc))
            return rc
        self._server_mgmt_sock_epoll.register(server_socket_fd, select.EPOLLIN)

        self._running = True
        while self._running:
            events = self._server_mgmt_sock_epoll.poll(0.01)
            for socket_fd, event in events:
                if socket_fd == server_socket_fd:
                    # Connect with the new client.
                    rc, client_socket_obj = self._server_mgmt_socket.uds_server_socket_accept()
                    if rc != RcCode.SUCCESS:
                        # Ignore this event, process next event.
                        continue
                    self._logger.info(
                        self._logger_system.set_logger_rc_code(
                            "A new client arrived. {}".format(client_socket_obj[0].getpeername())))
                    client_socket_fd = client_socket_obj[0].fileno()
                    rc = self._client_info.add_client_info(client_socket_fd, client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not add client information {}".format(
                                        client_socket_obj[0].getpeername()), rc=rc))
                        return rc
                    self._server_mgmt_sock_epoll.register(client_socket_fd, select.EPOLLIN)
                elif event & select.EPOLLIN:
                    rc, client_socket_obj = self._client_info.get_client_info(socket_fd, "socket_obj")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                "Can not get client information {}".format(socket_fd), rc=rc))
                        self._server_mgmt_sock_epoll.unregister(socket_fd)
                        return rc

                    # Receive the client message
                    rc, data = self._server_mgmt_socket.uds_client_socket_recv(client_socket_obj, self._max_server_msg_size)
                    if rc != RcCode.SUCCESS or data == "":
                        # Client has closed.
                        # Close this socket and remove this socket from the socket dictionary.
                        # Remove the socket from the EPOLL list.
                        # Process the next event.
                        self._server_mgmt_socket.uds_client_socket_close(client_socket_obj)
                        rc = self._client_info.del_client_info(socket_fd)
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code(
                                    "Can not remove client {} information.".format(socket_fd), rc=rc))
                            return rc
                        self._server_mgmt_sock_epoll.unregister(socket_fd)
                        continue

                    rc = self.client_msg_handle(data, client_socket_obj)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not client {} request.".format(client_socket_obj[0].getpeername()), rc=rc))
                        rc, client_socket_obj = self._client_info.get_client_info(socket_fd, "socket_obj")
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code(
                                    "Can not get client {} information.".format(socket_fd), rc=rc))
                            return rc
                        self._server_mgmt_socket.uds_client_socket_close(client_socket_obj)
                        rc = self._client_info.del_client_info(socket_fd)
                        if rc != RcCode.SUCCESS:
                            self._logger.error(
                                self._logger_system.set_logger_rc_code(
                                    "Can not remove client {} information.".format(socket_fd), rc=rc))
                            return rc
                        self._server_mgmt_sock_epoll.unregister(socket_fd)
                elif event & select.EPOLLHUP:
                    # Client disconnects the socket.
                    # Clear the socket information for request list and epoll.
                    # Remove the socket from the EPOLL list.

                    rc, client_socket_obj = self._client_info.get_client_info(socket_fd, "socket_obj")
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not get client {} information.".format(socket_fd), rc=rc))
                        return rc
                    self._server_mgmt_socket.uds_client_socket_close(client_socket_obj)
                    rc = self._client_info.del_client_info(socket_fd)
                    if rc != RcCode.SUCCESS:
                        self._logger.error(
                            self._logger_system.set_logger_rc_code(
                                    "Can not remove client {} information.".format(socket_fd), rc=rc))
                        return rc
                    self._server_mgmt_sock_epoll.unregister(socket_fd)
        return RcCode.SUCCESS

    def run(self):
        # Initialize the console server including the serial port and server management socket.
        rc = self._init_server()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Initialize the server fail."))
            return

        # Start main flow
        rc = self.daemon_main()
        if rc != RcCode.SUCCESS:
            self._logger.error(
                self._logger_system.set_logger_rc_code("Console server management system has stopped.", rc=rc))

        self._logger.info(self._logger_system.set_logger_rc_code("Console server management system shutdown."))
