import multiprocessing
from queue import Queue, ShutDown, Empty

from src.common.rc_code import RcCode


class UniDirectionalMessageQueue:
    def __init__(self, support_multiple_processing=False, max_item=0,
                 send_blocking=False, send_timeout=False, receive_blocking=False, receive_timeout=False):
        self._support_multiple_processing = support_multiple_processing
        self._max_item = max_item
        self._send_blocking = send_blocking
        self._send_timeout = send_timeout
        self._receive_blocking = receive_blocking
        self._receive_timeout = receive_timeout

        if self._support_multiple_processing:
            self._queue = multiprocessing.Queue(self._max_item)
        else:
            self._queue = Queue(self._max_item)

    def message_queue_send(self, data):
        try:
            self._queue.put(data, block=self._send_blocking, timeout=self._send_timeout)
        except ShutDown:
            return RcCode.QUEUE_CLOSED
        return RcCode.SUCCESS

    def message_queue_receive(self):
        try:
            item = self._queue.get(block=self._receive_blocking, timeout=self._receive_timeout)
        except ShutDown:
            return RcCode.QUEUE_CLOSED, None
        except Empty:
            return RcCode.DATA_NOT_READY, None
        return RcCode.SUCCESS, item


class BidirectionalMessageQueue:
    def __init__(self, support_multiple_processing=False, max_item=0,
                 send_blocking=False, send_timeout=False, receive_blocking=False, receive_timeout=False):
        self._support_multiple_processing = support_multiple_processing
        self._max_item = max_item
        self._send_blocking = send_blocking
        self._send_timeout = send_timeout
        self._receive_blocking = receive_blocking
        self._receive_timeout = receive_timeout

        if self._support_multiple_processing:
            self.tx_queue = multiprocessing.Queue(self._max_item)
            self.rx_queue = multiprocessing.Queue(self._max_item)
        else:
            self.tx_queue = Queue(self._max_item)
            self.rx_queue = Queue(self._max_item)

    def message_tx_queue_send(self, data):
        try:
            self.tx_queue.put(data, block=self._send_blocking, timeout=self._send_timeout)
        except ShutDown:
            return RcCode.QUEUE_CLOSED
        return RcCode.SUCCESS

    def message_tx_queue_receive(self):
        try:
            item = self.tx_queue.get(block=self._receive_blocking, timeout=self._receive_timeout)
        except ShutDown:
            return RcCode.QUEUE_CLOSED, None
        except Empty:
            return RcCode.DATA_NOT_READY, None
        return RcCode.SUCCESS, item

    def message_rx_queue_send(self, data):
        try:
            self.rx_queue.put(data, block=self._send_blocking, timeout=self._send_timeout)
        except ShutDown:
            return RcCode.QUEUE_CLOSED
        return RcCode.SUCCESS

    def message_rx_queue_receive(self):
        try:
            item = self.rx_queue.get(block=self._receive_blocking, timeout=self._receive_timeout)
        except ShutDown:
            return RcCode.QUEUE_CLOSED, None
        except Empty:
            return RcCode.DATA_NOT_READY, None
        return RcCode.SUCCESS, item
