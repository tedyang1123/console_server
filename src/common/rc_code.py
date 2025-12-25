from enum import IntEnum, auto


class RcCode(IntEnum):
    SUCCESS = 0
    FAILURE = auto()
    ERROR = auto()
    REQUEST_DENIED = auto()
    FILE_NOT_FOUND = auto()
    FILE_NOT_READ = auto()
    FILE_NOT_WRITE = auto()
    FILE_NOT_CREATE = auto()
    FILE_ACCESS_FAIL = auto()
    SIGNATURE_VERIFICATION_FAIL = auto()
    CHECKSUM_VERIFICATION_FAIL = auto()
    INVALID_VALUE = auto()
    INVALID_TYPE = auto()
    DATA_NOT_FOUND = auto()
    DATA_EXIST = auto()
    DEVICE_BUSY = auto()
    DEVICE_NOT_FOUND = auto()
    DATA_NOT_READY = auto()
    DEVICE_EXIST = auto()
    CHANGE_MENU = auto()
    EXIT_MENU = auto()
    EXIT_PROCESS = auto()
    OPEN_SERIAL_PORT = auto()
    CLOSE_SERIAL_PORT = auto()
    USER_EXIST = auto()
    USER_NOT_FOUND = auto()
    PERMISSION_DENIED = auto()
    QUEUE_CLOSED = auto()
    QUEUE_OPEN = auto()

    @classmethod
    def covert_rc_to_string(cls, rc):
        if rc == cls.SUCCESS:
            return "SUCCESS"
        elif rc == cls.FAILURE:
            return "FAILURE"
        elif rc == cls.ERROR:
            return "ERROR"
        elif rc == cls.REQUEST_DENIED:
            return "REQUEST_DENIED"
        elif rc == cls.FILE_NOT_FOUND:
            return "FILE_NOT_FOUND"
        elif rc == cls.FILE_NOT_READ:
            return "FILE_NOT_READ"
        elif rc == cls.FILE_NOT_WRITE:
            return "FILE_NOT_WRITE"
        elif rc == cls.FILE_NOT_CREATE:
            return "FILE_NOT_CREATE"
        elif rc == cls.FILE_ACCESS_FAIL:
            return "FILE_ACCESS_FAIL"
        elif rc == cls.SIGNATURE_VERIFICATION_FAIL:
            return "SIGNATURE_VERIFICATION_FAIL"
        elif rc == cls.CHECKSUM_VERIFICATION_FAIL:
            return "SIGNATURE_VERIFICATION_FAIL"
        elif rc == cls.INVALID_VALUE:
            return "INVALID_VALUE"
        elif rc == cls.INVALID_TYPE:
            return "INVALID_TYPE"
        elif rc == cls.DATA_NOT_FOUND:
            return "DATA_NOT_FOUND"
        elif rc == cls.DATA_EXIST:
            return "DATA_EXIST"
        elif rc == cls.DEVICE_BUSY:
            return "DEVICE_BUSY"
        elif rc == cls.DEVICE_NOT_FOUND:
            return "DEVICE_NOT_FOUND"
        elif rc == cls.DATA_NOT_READY:
            return "DATA_NOT_READY"
        elif rc == cls.DEVICE_EXIST:
            return "DEVICE_EXIST"
        elif rc == cls.CHANGE_MENU:
            return "CHANGE_MODE"
        elif rc == cls.EXIT_MENU:
            return "EXIT_MENU"
        elif rc == cls.EXIT_PROCESS:
            return "EXIT_PROCESS"
        elif rc == cls.OPEN_SERIAL_PORT:
            return "OPEN_SERIAL_PORT"
        elif rc == cls.CLOSE_SERIAL_PORT:
            return "CLOSE_SERIAL_PORT"
        elif rc == cls.USER_EXIST:
            return "USER_EXIST"
        elif rc == cls.USER_NOT_FOUND:
            return "USER_NOT_FOUND"
        elif rc == cls.PERMISSION_DENIED:
            return "PERMISSION_DENIED"
        elif rc == cls.QUEUE_CLOSED:
            return "QUEUE_CLOSED"
        elif rc == cls.QUEUE_OPEN:
            return "QUEUE_OPEN"
        else:
            return None


