import logging

from src.common.rc_code import RcCode


class LoggerSystem:
    def __init__(self, loger_name):
        self._file_handler = None
        self._screen_handler = None
        self._formatter = None
        self._logger_name = loger_name
        self._logger = logging.getLogger(self._logger_name)
    
    def init_logger_system(self):
        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._screen_handler = logging.StreamHandler()
        self._screen_handler.setLevel(logging.DEBUG)
        self._screen_handler.setFormatter(self._formatter)

        self._file_handler = logging.FileHandler('/var/log/{}.log'.format(self._logger_name))
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(self._formatter)

        self._logger.setLevel(logging.DEBUG)

        self._logger.addHandler(self._screen_handler)
        self._logger.addHandler(self._file_handler)
        self._logger.propagate = False

        return RcCode.SUCCESS
