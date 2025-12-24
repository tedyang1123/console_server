from enum import IntEnum, auto


server_control_access_mode_menu =\
"\
====================================================================================\r\n\
: Welcome to Console Server                                                         \r\n\
====================================================================================\r\n\
1. Port Accesses\r\n\
2. Port Configuration\r\n\
\r\n\
Q. Exit\r\n\
"

server_control_mgmt_mode_menu =\
"\
====================================================================================\r\n\
: Welcome to Console Server                                                         \r\n\
====================================================================================\r\n\
1. Port Accesses\r\n\
2. Port Configuration\r\n\
3. User Management\r\n\
4. Network Management\r\n\
5. System Management\r\n\
\r\n\
Q. Exit\r\n\
"

server_control_port_access_menu: str =\
"\
====================================================================================\r\n\
: Welcome to Console Server                                                         \r\n\
====================================================================================\r\n\
{}\r\n\
\r\n\
Q. Exit\r\n\
"

SERVER_CONTROL_ITEM_SELECT_PROMPT = "Enter Action ID or Q/q> "
SERVER_CONTROL_PORT_CONFIG_PROMPT = "Enter Port ID or Q/q> "
SERVER_CONTROL_USER_CONFIG_PROMPT = "Enter baud rate or Q/q> "
SERVER_CONTROL_ALIAS_NAME_PROMPT = "Enter alias name or Q/q> "

server_control_port_config_menu =\
"\
====================================================================================\r\n\
: Welcome to Console Server                                                         \r\n\
====================================================================================\r\n\
{}\r\n\
\r\n\
A/a. Change the alisa name for the port.\r\n\
B/b. Change the baud rate for the port.\r\n\
Q. Exit\r\n\
"\

server_control_user_mgmt_menu =\
"\
====================================================================================\r\n\
: Welcome to Console Server                                                         \r\n\
====================================================================================\r\n\
1. Create User Account\r\n\
2. Delete User Account\r\n\
3. Configure Port Access\r\n\
4. Configure RADIUS\r\n\
5. Configure TACACS+\r\n\
6. Show User Information\r\n\
\r\n\
Q. Exit\r\n\
"

server_control_network_mgnt_menu =\
"\
====================================================================================\r\n\
: Welcome to Console Server                                                         \r\n\
====================================================================================\r\n\
1. Setup Network Configuration\r\n\
2. Setup Server Management Port\r\n\
3. Show Network Information\r\n\
4. Direct Port Access By SSH\r\n\
5. Direct Port Access By Telnet\r\n\
6. Direct Port Access By TCP\r\n\
\r\n\
Q. Exit\r\n\
"

server_control_system_mgmt_menu =\
"\
====================================================================================\r\n\
: Welcome to Console Server                                                         \r\n\
====================================================================================\r\n\
1. Setup System Log\r\n\
2. Restore Default Configuration\r\n\
3. Show System Configuration\r\n\
4. Show System Log\r\n\
4. Show System Information\r\n\
\r\n\
Q. Exit\r\n\
"


class ServerControlAccessModeMenu(IntEnum):
    SERVER_CONTROL_PORT_ACCESS_MENU = 1
    SERVER_CONTROL_PORT_CONFIG_MENU = auto()


SERVER_CONTROL_ACCESS_MODE_MENU_DICT = {
    ServerControlAccessModeMenu.SERVER_CONTROL_PORT_ACCESS_MENU: server_control_port_access_menu
}


class ServerControlMgmtModeMenu(IntEnum):
    SERVER_CONTROL_PORT_ACCESS_MENU = 1
    SERVER_CONTROL_PORT_CONFIG_MENU = auto()
    SERVER_CONTROL_USER_MGMT_MENU = auto()
    SERVER_CONTROL_NET_MGMT_MENU = auto()
    SERVER_CONTROL_SYSTEM_MGMT_MENU = auto()


SERVER_CONTROL_MGMT_MODE_MENU_DICT = {
    ServerControlMgmtModeMenu.SERVER_CONTROL_PORT_ACCESS_MENU: server_control_port_access_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_PORT_CONFIG_MENU: server_control_port_config_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_USER_MGMT_MENU: server_control_user_mgmt_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_NET_MGMT_MENU: server_control_network_mgnt_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_SYSTEM_MGMT_MENU: server_control_system_mgmt_menu,
}

class ServerControlMenu(IntEnum):
    SERVER_CONTROL_ACCESS_MODE_MENU = 0
    SERVER_CONTROL_MGMT_MODE_MENU = auto()
    SERVER_CONTROL_PORT_ACCESS_MENU = auto()
    SERVER_CONTROL_PORT_CONFIG_MENU = auto()
    SERVER_CONTROL_USER_MGMT_MENU = auto()
    SERVER_CONTROL_NET_MGMT_MENU = auto()
    SERVER_CONTROL_SYSTEM_MGMT_MENU = auto()

    # Enter the SERVER_CONTROL_PORT_ACCESS_MENU
    SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU = auto()

SERVER_CONTROL_MENU_DICT = {
    ServerControlMenu.SERVER_CONTROL_ACCESS_MODE_MENU: server_control_port_access_menu,
    ServerControlMenu.SERVER_CONTROL_MGMT_MODE_MENU: server_control_mgmt_mode_menu,
    ServerControlMenu.SERVER_CONTROL_PORT_ACCESS_MENU: server_control_port_access_menu,
    ServerControlMenu.SERVER_CONTROL_PORT_CONFIG_MENU: server_control_port_config_menu,
    ServerControlMenu.SERVER_CONTROL_USER_MGMT_MENU: server_control_user_mgmt_menu,
    ServerControlMenu.SERVER_CONTROL_NET_MGMT_MENU: server_control_network_mgnt_menu,
    ServerControlMenu.SERVER_CONTROL_SYSTEM_MGMT_MENU: server_control_system_mgmt_menu,
    ServerControlMenu.SERVER_CONTROL_SERIAL_PORT_ACCESS_MENU: "",
}


SERVER_CONTROL_GENERAL_PROMPT = ">> "