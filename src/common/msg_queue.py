from multiprocessing import Queue

from src.common.logger_system import LoggerSystem
from src.common.rc_code import RcCode


class BiMsgQueue:
    def __init__(self, logger_system=None):
        self._logger_system = logger_system
        if self._logger_system is not None:
            self._logger = self._logger_system.get_logger()
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

        return rc

    def local_peer_send_msg(self, msg):
        try:
            self._tx_queue.put(msg)
        except Queue.Full:
            self._logger.error("The message queue is full.")
            return RcCode.QUEUE_FULL
        return RcCode.SUCCESS
    
    def local_peer_receive_msg(self):
        try:
            msg = self._rx_queue.get()
        except Queue.Full:
            self._logger.error("The message queue is empty.")
            return RcCode.QUEUE_ENPTY, None
        return RcCode.SUCCESS, msg

    def remote_peer_send_msg(self, msg):
        try:
            self._rx_queue.put(msg)
        except Queue.Full:
            self._logger.error("The message queue is full.")
            return RcCode.QUEUE_FULL
        return RcCode.SUCCESS
    
    def remote_peer_receive_msg(self):
        try:
            msg = self._tx_queue.get()
        except Queue.Full:
            self._logger.error("The message queue is empty.")
            return RcCode.QUEUE_ENPTY, None
        return RcCode.SUCCESS, msg