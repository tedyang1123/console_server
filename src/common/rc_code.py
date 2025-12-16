from enum import IntEnum, auto


class RcCode(IntEnum):
    SUCCESS = 0
    FAILURE = auto()
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
    DEVICE_BUSY = auto()
    DEVICE_NOT_FOUND = auto()
    DATA_NOT_READY = auto()
    DEVICE_EXIST = auto()
    EXIT_PROCESS = auto()
    OPEN_SERIAL = auto()
    OPEN_TERMINAL = auto()
    USER_EXIST = auto()
    USER_NOT_FOUND = auto()
    PERMISSION_DENIED = auto()

    @classmethod
    def covert_rc_to_string(cls, rc):
        if rc == cls.SUCCESS:
            return "SUCCESS"
        elif rc == cls.FAILURE:
            return "FAILURE"
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
        elif rc == cls.DEVICE_BUSY:
            return "DEVICE_BUSY"
        elif rc == cls.DEVICE_NOT_FOUND:
            return "DEVICE_NOT_FOUND"
        elif rc == cls.DATA_NOT_READY:
            return "DATA_NOT_READY"
        elif rc == cls.DEVICE_EXIST:
            return "DEVICE_EXIST"
        elif rc == cls.EXIT_PROCESS:
            return "EXIT_PROCESS"
        elif rc == cls.OPEN_SERIAL:
            return "OPEN_SERIAL"
        elif rc == cls.OPEN_TERMINAL:
            return "OPEN_TERMINAL"
        elif rc == cls.USER_EXIST:
            return "USER_EXIST"
        elif rc == cls.USER_NOT_FOUND:
            return "USER_NOT_FOUND"
        elif rc == cls.PERMISSION_DENIED:
            return "PERMISSION_DENIED"
        else:
            return None


