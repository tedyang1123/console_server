class SerialPortPair:
    def __init__(self, serial_port_obj, server_socket_obj):
        self._serial_port_obj = serial_port_obj
        self._server_socket_obj = server_socket_obj
        self._client_socket_dict = {}

    def get_serial_port_obj(self):
        return self._serial_port_obj

    def get_server_socket_obj(self):
        return self._server_socket_obj

    def get_client_socket_dict(self):
        return self._client_socket_dict