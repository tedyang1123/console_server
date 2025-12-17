from enum import IntEnum, auto


server_control_access_mode_menu = \
" \
===========================================================================================\r\n \
: Welcome to Consle Server\r\n \
===========================================================================================\r\n \
1. Port Accesss\r\n \
2. Port Configureation\r\n \
\r\n \
Q. Exit\r\n \
"

server_control_mgmt_mode_menu = \
" \
===========================================================================================\r\n \
: Welcome to Consle Server\r\n \
===========================================================================================\r\n \
1. Port Accesss\r\n \
2. Port Configureation\r\n \
3. User Management\r\n \
4. Network Management\r\n \
5. System Management\r\n \
\r\n \
Q. Exit\r\n \
"

server_control_port_access_menu = \
" \
===========================================================================================\r\n \
: Welcome to Consle Server\r\n \
===========================================================================================\r\n \
 1. COM1                                25. COM25\r\n \
 2. COM2                                26. COM26\r\n \
 3. COM3                                27. COM27\r\n \
 4. COM4                                28. COM28\r\n \
 5. COM5                                29. COM29\r\n \
 6. COM6                                30. COM30\r\n \
 7. COM7                                31. COM31\r\n \
 8. COM8                                32. COM32\r\n \
 9. COM9                                33. COM33\r\n \
10. COM10                               34. COM34\r\n \
11. COM11                               35. COM35\r\n \
12. COM12                               36. COM36\r\n \
13. COM13                               37. COM37\r\n \
14. COM14                               38. COM38\r\n \
15. COM15                               39. COM39\r\n \
16. COM16                               40. COM40\r\n \
17. COM17                               41. COM41\r\n \
18. COM18                               42. COM42\r\n \
19. COM19                               43. COM43\r\n \
20. COM20                               44. COM44\r\n \
21. COM21                               45. COM45\r\n \
22. COM22                               46. COM46\r\n \
23. COM23                               47. COM47\r\n \
24. COM24                               48. COM48\r\n \
\r\n \
Q. Exit\r\n \
" \

server_control_port_config_menu = \
" \
===========================================================================================\r\n \
: Welcome to Consle Server\r\n \
===========================================================================================\r\n \
1. Configure baud rate\r\n \
2. Configre Descritpion\r\n \
3. Show Port information\r\n \
\r\n \
Q. Exit\r\n \
" \

server_control_user_mgmt_menu = \
" \
===========================================================================================\r\n \
: Welcome to Consle Server\r\n \
===========================================================================================\r\n \
1. Create User Account\r\n \
2. Delete User Account\r\n \
3. COnfigure Port Access\r\n \
4. Configure RADIUS\r\n \
5. Configure TACACS+\r\n \
6. Show User Information\r\n \
\r\n \
Q. Exit\r\n \
"

server_control_network_mgnt_menu = \
" \
===========================================================================================\r\n \
: Welcome to Consle Server\r\n \
===========================================================================================\r\n \
1. Setup IP Address\r\n \
2. Setup SSH Server Port\r\n \
3. Show Network Information\r\n \
4. Direct Port Access By SSH\r\n \
5. Direct Port Access By Telnet\r\n \
6. Direct Port Access By TCP\r\n \
\r\n \
Q. Exit\r\n \
"

server_control_system_mgmt_menu = \
" \
===========================================================================================\r\n \
: Welcome to Consle Server\r\n \
===========================================================================================\r\n \
1. Setup System Log\r\n \
2. Restore Default Configuration\r\n \
3. Show System Configuration\r\n \
4. Show System Log\r\n \
4. Show System Information\r\n \
\r\n \
Q. Exit\r\n \
"


class ServerControlAccessModeMenu(IntEnum):
    SERVER_CONTROL_ACCESS_MODE_MENU = 0


SERVER_CONTROL_ACCESS_MODE_MENU_DICT = {
    ServerControlAccessModeMenu.SERVER_CONTROL_ACCESS_MODE_MENU: server_control_access_mode_menu
}


class ServerControlMgmtModeMenu(IntEnum):
    SERVER_CONTROL_MGMT_MODE_MENU = 0
    SERVER_CONTROL_PORT_ACCESS_MENU = auto()
    SERVER_CONTROL_PORT_CONFIG_MENU = auto()
    SERVER_CONTROL_USER_MGMT_MENU = auto()
    SERVER_CONTROL_NET_MGMT_MENU = auto()
    SERVER_CONTROL_SYSTEM_MGMT_MENU = auto()


SERVER_CONTROL_MGMT_MODE_MENU_DICT = {
    ServerControlMgmtModeMenu.SERVER_CONTROL_MGMT_MODE_MENU: server_control_mgmt_mode_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_PORT_ACCESS_MENU: server_control_port_access_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_PORT_CONFIG_MENU: server_control_port_config_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_USER_MGMT_MENU: server_control_user_mgmt_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_NET_MGMT_MENU: server_control_network_mgnt_menu,
    ServerControlMgmtModeMenu.SERVER_CONTROL_SYSTEM_MGMT_MENU: server_control_system_mgmt_menu,
}


SERVER_CONTROL_PROMPT = ">> "