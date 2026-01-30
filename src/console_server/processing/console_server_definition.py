from enum import StrEnum


class ConsoleServerEvent(StrEnum):
    INIT_HANDLER = "init_handler"
    INIT_SERIAL_PORT = "init_serial_port"
    CONNECT_SERIAL_PORT = "connect_serial_port"
    CONFIG_BAUD_RATE = "config_baud_rate"
    CONFIG_ALIAS_NAME = "config_alias_name"
    GET_PORT_CONFIG = "get_port_config"
    ADD_USER_ACCOUNT = "add_user_account"
    DEL_USER_ACCOUNT = "del_user_account"
    GET_USER_ACCOUT = "get_user_account"
    MODIFY_USER_ROLE = "modify_user_role"
    CREATE_GROUP = "create_group"
    DESTROY_GROUP = "destroy_group"
    GET_GROUP = "get_group"
    USER_JOIN_GROUP = "user_join_group"
    USER_LEAVE_GROUP = "user_leave_group"
    PORT_JOIN_GROUP = "port_join_group"
    PORT_LEAVE_GROUP = "port_leave_group"


class UserRole(StrEnum):
    ROLE_ADMIN = "admin"
    ROLE_CONSOLE_USER = "console_user"
    ROLE_OPERATOR = "operator"

    @classmethod
    def is_valid(cls, role):
        match role:
            case cls.ROLE_ADMIN | cls.ROLE_CONSOLE_USER | cls.ROLE_OPERATOR:
                return True
        return False