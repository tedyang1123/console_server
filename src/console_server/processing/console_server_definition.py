from enum import StrEnum


VALID_BAUD_RATE = [50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800, 9600, 19200, 38400, 57600, 115200,
                   230400, 460800, 500000, 576000, 921600, 1000000, 1152000, 1500000, 2000000, 2500000, 3000000, 3500000, 4000000]


class ConsoleServerEvent(StrEnum):
    INIT_HANDLER = "init_handler"
    INIT_SERIAL_PORT = "init_serial_port"
    INIT_DEFAULT_ACCOUNT = "init_default_account"

    CONNECT_SERIAL_PORT = "connect_serial_port"
    SET_BAUD_RATE = "set_baud_rate"
    SET_ALIAS_NAME = "set_alias_name"
    GET_PORT_CONFIG = "get_port_config"
    GET_PORT_STATUS = "get_port_status"

    CREATE_GROUP = "create_group"
    DESTROY_GROUP = "destroy_group"
    MODIFY_GROUP = "modify_group"
    GET_GROUP_CONFIG = "get_group_config"
    GET_GROUP_STATUS = "get_group_status"

    ADD_USER_ACCOUNT = "add_user_account"
    DEL_USER_ACCOUNT = "del_user_account"
    MODIFY_USER_ROLE = "modify_user_role"
    USER_JOIN_GROUP = "user_join_group"
    USER_LEAVE_GROUP = "user_leave_group"
    PORT_JOIN_GROUP = "port_join_group"
    PORT_LEAVE_GROUP = "port_leave_group"
    GET_USER_CONFIG = "get_user_config"
    GET_USER_STATUS = "get_user_status"


class UserRole(StrEnum):
    ROLE_ADMIN = "admin"
    ROLE_OPERATOR = "operator"
    ROLE_CONSOLE_USER = "console_user"
    ROLE_INVALID = "invalid_role"

    @classmethod
    def is_valid(cls, role):
        match role:
            case cls.ROLE_ADMIN | cls.ROLE_CONSOLE_USER | cls.ROLE_OPERATOR:
                return True
        return False

    @classmethod
    def get_list(cls):
        return [cls.ROLE_ADMIN, cls.ROLE_OPERATOR, cls.ROLE_CONSOLE_USER]


UserRolePriorityDict = {
    UserRole.ROLE_ADMIN: 0,
    UserRole.ROLE_OPERATOR: 1,
    UserRole.ROLE_CONSOLE_USER: 2,
    UserRole.ROLE_INVALID: 3
}

PriorityUserRole_dict = {
    0: UserRole.ROLE_ADMIN,
    1: UserRole.ROLE_OPERATOR,
    2: UserRole.ROLE_CONSOLE_USER,
    3: UserRole.ROLE_INVALID
}