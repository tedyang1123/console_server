from enum import StrEnum


class ConsoleServerEvent(StrEnum):
    INIT_HANDLER = "init_handler"
    INIT_SERIAL_PORT = "init_serial_port"
    CONNECT_SERIAL_PORT = "connect_serial_port"
    CONFIG_BAUD_RATE = "config_baud_rate"
    CONFIG_ALIAS_NAME = "config_alias_name"
    GET_PORT_CONFIG = "get_port_config"
    CONFIG_WRITE_PERMISSION = "config_write_permisswion"