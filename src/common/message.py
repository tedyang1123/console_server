
class MessageRequestMsg:
    def __init__(self, request: str="", serial_port_id:int =-1, data=None):
        self.request = request
        self.serial_port_id = serial_port_id
        self.data = data

    def get_message(self):
        return {"request": self.request, "serial_port_id": self.serial_port_id, "data": self.data}

    def set_message(self, msg_dict):
        self.request = msg_dict["request"]
        self.serial_port_id = msg_dict["serial_port_id"]
        self.data = msg_dict["data"]


class MessageReplyMsg:
    def __init__(self, request: str="", result="", msg="", serial_port_id:int =-1, data=None):
        self.request = request
        self.result = result
        self.msg = msg
        self.serial_port_id = serial_port_id
        self.data = data

    def get_message(self):
        return {"request": self.request, "result": self.result, "serial_port_id": self.serial_port_id, "data": self.data}

    def set_message(self, msg_dict):
        self.request = msg_dict["request"]
        self.result = msg_dict["result"]
        self.msg = msg_dict["msg"]
        self.serial_port_id = msg_dict["serial_port_id"]
        self.data = msg_dict["data"]