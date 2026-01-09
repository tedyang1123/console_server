from enum import StrEnum
import multiprocessing
from src.common.msg_queue import BiMsgQueue
from src.common.rc_code import RcCode


class DbEnum(StrEnum):
    CONFIG_ACCOUNT_DB = "config_account_db"
    CONFIG_SERIAL_PORT_DB = "config_serial_port_db"


class DbCallbackEventEnum(StrEnum):
    DB_CALLBACK_ADD_EVENT = "db_add_entry",
    DB_CALLBACK_DELETE_EVENT = "db_event_entry"
    DB_CALLBACK_MODIFY_EVENT = "db_motify_entry"


class DbOperationEnum(StrEnum):
    DB_OPERATION_ADD = "add"
    DB_OPERATION_DELETE = "delete"
    DB_OPERATION_MODIFY = "modify"
    DB_OPERATION_REGISTER = "register"
    DB_OPERATION_UNREGISTER = "unregister"


class DbTable:
    def __init__(self):
        self. _notify_dict = {
            "db_add": {},
            "db_delete": {},
            "db_modify": {}
        }

    def do_notify(self, event):
        notify_dict = self. _notify_dict[event]
        for notifier in notify_dict:
            rc = notify_dict[notifier]["callback"](event)
            if rc != RcCode.SUCCESS:
                print("Notify {} the event {} fail".format(notifier, event))
        return RcCode.SUCCESS
    
    def register_event(self, handler_name, event, handler_callback):
        match event:
            case DbCallbackEventEnum.DB_CALLBACK_ADD_EVENT | DbCallbackEventEnum.DB_CALLBACK_DELETE_EVENT | DbCallbackEventEnum.DB_CALLBACK_MODIFY_EVENT:
                if handler_name in self._notify_dict[event]:
                    return RcCode.DATA_EXIST
                self._notify_dict[event][handler_name] = handler_callback
            case _:
                return RcCode.INVALID_TYPE
        return RcCode.SUCCESS
    
    def unregister_event(self, handler_name, event):
        match event:
            case DbCallbackEventEnum.DB_CALLBACK_ADD_EVENT | DbCallbackEventEnum.DB_CALLBACK_DELETE_EVENT | DbCallbackEventEnum.DB_CALLBACK_MODIFY_EVENT:
                if handler_name not in self._notify_dict[event]:
                    return RcCode.DATA_NOT_FOUND
                del self._notify_dict[event][handler_name]
            case _:
                return RcCode.INVALID_TYPE
        return RcCode.SUCCESS


class ConfigAccoutTable(DbTable):
    def __init__(self):
        super().__init__()
        self._account_dict = {}

    def add_entry(self, account_name, is_admin, deletable, activate):
        if account_name in self._account_dict:
            return RcCode.DATA_EXIST
        self._account_dict[account_name] = {
            "is_admin": is_admin,
            "deletable": deletable,
            "activate": activate
        }
        rc = self.do_notify("db_add")
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def delete_entry(self, account_name):
        if account_name not in self._account_dict:
            return RcCode.DATA_NOT_FOUND
        if not self._account_dict[account_name]["deletable"]:
            return RcCode.PERMISSION_DENIED
        del self._account_dict[account_name]
        rc = self.do_notify("db_delete")
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def modify_entry(self, account_name, field, data):
        if account_name not in self._account_dict:
            return RcCode.DATA_NOT_FOUND
        match field:
            case "is_admin" | "activate" | "deletable":
                if field == "deletable":
                    count = 0
                    for username in self._account_dict:
                        if username == account_name:
                            continue
                        if self._account_dict[username]["deletable"]:
                            count = count + 1
                    if count == 0:
                        return RcCode.PERMISSION_DENIED
            case _:
                return RcCode.INVALID_TYPE
        self._account_dict[field] = data
        rc = self.do_notify("db_modify")
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS


class ConfigSerialPortTable(DbTable):
    def __init__(self):
        super().__init__()
        self._serial_port_dict = {}

    def add_entry(self, serial_port_id, ssh_port_id):
        if serial_port_id in self._serial_port_dict:
            return RcCode.DATA_EXIST
        for serial_port_id in self._serial_port_dict:
            if self._serial_port_dict[serial_port_id]["ssh_port_id"] == ssh_port_id:
                return RcCode.DATA_EXIST
        self._serial_port_dict[serial_port_id] = {"ssh_port_id": ssh_port_id}
        rc = self.do_notify("db_add")
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def delete_entry(self, serial_port_id):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        del self._serial_port_dict[serial_port_id]
        rc = self.do_notify("db_delete")
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def modify_entry(self, serial_port_id, field, data):
        if serial_port_id not in self._serial_port_dict:
            return RcCode.DATA_NOT_FOUND
        if self._serial_port_dict[serial_port_id][field] == data:
            return RcCode.SUCCESS
        match field:
            case "ssh_port_id":
                for port_id in self._serial_port_dict:
                    if port_id != serial_port_id and self._serial_port_dict[port_id]["ssh_port_id"] == data:
                        return RcCode.DATA_EXIST
                self._serial_port_dict[serial_port_id]["ssh_port_id"] = data
            case _:
                return RcCode.INVALID_TYPE
        rc = self.do_notify("db_modify")
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS


class DbServer(multiprocessing.Process):
    def __init__(self):
        multiprocessing.Process.__init__(self)
        self._config_serial_port_table = ConfigSerialPortTable()
        self._confing_account_table = ConfigAccoutTable()
        self._msg_queue = BiMsgQueue()

    def _search_db(self, db_type):
        match db_type:
            case DbEnum.CONFIG_ACCOUNT_DB:
                return RcCode.SUCCESS, self._confing_account_table
            case DbEnum.CONFIG_SERIAL_PORT_DB:
                return RcCode.SUCCESS, self._config_serial_port_table
        return RcCode.INVALID_TYPE, None
    
    def _check_callback_event(self, callback_event):
        match callback_event:
            case DbCallbackEventEnum.DB_CALLBACK_ADD_EVENT | DbCallbackEventEnum.DB_CALLBACK_DELETE_EVENT | \
                DbCallbackEventEnum.DB_CALLBACK_MODIFY_EVENT:
                return RcCode.SUCCESS
        return RcCode.INVALID_VALUE

    def _register_callback(self, db_type, parameter):
        handler_name = parameter["handler_name"]
        callback_event = parameter["callback_event"]
        callback = parameter["callback"]
        rc, db_obj = self._search_db(db_type)
        if rc != RcCode.SUCCESS:
            return RcCode.INVALID_TYPE
        
        rc = self._check_callback_event(handler_name, callback_event, callback)
        if rc != RcCode.SUCCESS:
            return rc
        
        rc = db_obj.register_event(handler_name, callback_event, callback)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def _unregister_callback(self, db_type, parameter):
        handler_name = parameter["handler_name"]
        callback_event = parameter["callback_event"]
        rc, db_obj = self._search_db(db_type)
        if rc != RcCode.SUCCESS:
            return RcCode.INVALID_TYPE
        
        rc = self._check_callback_event(db_obj, callback_event)
        if rc != RcCode.SUCCESS:
            return RcCode.INVALID_TYPE
        
        rc = db_obj.unregister_event(handler_name, callback_event)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def _add_entry(self, db_type, parameter):
        rc, db_obj = self._search_db(db_type)
        if rc != RcCode.SUCCESS:
            return RcCode.INVALID_TYPE
        
        match parameter.db:
            case "config_account_db":
                account_name = parameter["account_name"]
                is_admin = parameter["is_admin"]
                deletable = parameter["deletable"]
                activate = parameter["activate"]
                rc = db_obj.add_entry(account_name, is_admin, deletable, activate)
                if rc != RcCode.SUCCESS:
                    return rc
            case "config_serial_port_db":
                serial_port_id = parameter["serial_port_id"]
                ssh_port_id = parameter["ssh_port_id"]
                rc = db_obj.add_entry(serial_port_id, ssh_port_id)
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS

    def _delete_entry(self, db_type, parameter):
        rc, db_obj = self._search_db(db_type)
        if rc != RcCode.SUCCESS:
            return RcCode.INVALID_TYPE
        
        match parameter.db:
            case "config_account_db":
                account_name = parameter["account_name"]
                rc = db_obj.delete_entry(account_name)
                if rc != RcCode.SUCCESS:
                    return rc
            case "config_serial_port_db":
                serial_port_id = parameter["serial_port_id"]
                rc = db_obj.delete_entry(serial_port_id)
                if rc != RcCode.SUCCESS:
                    return rc
        return RcCode.SUCCESS
                

    def _modify_entry(self, db_type, parameter):
        rc, db_obj = self._search_db(db_type)
        if rc != RcCode.SUCCESS:
            return RcCode.INVALID_TYPE
        account_name = parameter["account_name"]
        field = parameter["field"]
        data = parameter
        rc = db_obj.modify_entry(account_name, field, data)
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS
    
    def _process_request(self, msg):
        match msg.operation:
            case DbOperationEnum.DB_OPERATION_ADD:
                rc = self._add_entry(msg.db, msg.paramter)
            case DbOperationEnum.DB_OPERATION_DELETE:
                rc = self._delete_entry(msg.db, msg.paramter)
            case DbOperationEnum.DB_OPERATION_MODIFY:
                rc = self._modify_entry(msg.db, msg.paramter)
            case DbOperationEnum.DB_OPERATION_REGISTER:
                rc = self._register_callback(msg.db, msg.paramter)
            case DbOperationEnum.DB_OPERATION_UNREGISTER:
                rc = self._unregister_callback(msg.db, msg.paramter)
        return rc