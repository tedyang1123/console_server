import queue
from multiprocessing import Queue

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode


class BiMsgQueue:
    def __init__(self, logger_system=None, tx_blocking=True, tx_timeout=None, rx_blocking=True, rx_timeout=None):
        self._tx_blocking = tx_blocking
        self._rx_blocking = rx_blocking
        self._tx_timeout = tx_timeout
        self._rx_timeout = rx_timeout
        self._logger_system = logger_system
        self._logger = None
        self._tx_queue = Queue()
        self._rx_queue = Queue()
    
    def init_queue(self):
        # Init log system
        if self._logger_system is None:
            self._logger_system = LoggerSystem("BiMsgQueue")
            rc = self._logger_system.init_logger_system()
            if rc != RcCode.SUCCESS:
                return rc

        # Init queue
        self._logger = self._logger_system.get_logger()
        self._tx_queue = Queue()
        self._rx_queue = Queue()

        return RcCode.SUCCESS

    def local_peer_send_msg(self, msg):
        try:
            self._tx_queue.put(msg, self._tx_blocking, self._tx_timeout)
        except queue.Full:
            return RcCode.QUEUE_FULL
        return RcCode.SUCCESS
    
    def local_peer_receive_msg(self):
        try:
            msg = self._rx_queue.get(self._rx_blocking, self._rx_timeout)
        except queue.Empty:
            return RcCode.QUEUE_ENPTY, None
        return RcCode.SUCCESS, msg

    def remote_peer_send_msg(self, msg):
        try:
            self._rx_queue.put(msg, self._tx_blocking, self._tx_timeout)
        except queue.Full:
            return RcCode.QUEUE_FULL
        return RcCode.SUCCESS
    
    def remote_peer_receive_msg(self):
        try:
            msg = self._tx_queue.get(self._rx_blocking, self._rx_timeout)
        except queue.Empty:
            return RcCode.QUEUE_ENPTY, None
        return RcCode.SUCCESS, msg