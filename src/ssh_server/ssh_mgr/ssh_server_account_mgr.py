import copy
import logging
import subprocess
import pwd

from src.common.rc_code import RcCode


ADMIN_ACCOUNT_NAME = "tedyang"
ADMIN_ACCOUNT_PASSWORD = "tedyang"


class SshServerAccountMgr:
    def __init__(self):
        self._account_dict = {}
        self._logger = logging.getLogger(__name__)

    def _create_account_entry(self, username, is_admin=False, deletable=True, activate=False):
        self._account_dict[username] = {
            "is_admin": is_admin,
            "deletable": deletable,
            "activate": activate
        }
        return RcCode.SUCCESS

    def _init_logger_system(self):
        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)-5s][%(levelname)-5s] %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._screen_handler = logging.StreamHandler()
        self._screen_handler.setLevel(logging.WARNING)
        self._screen_handler.setFormatter(self._formatter)

        host, port = self._client_sock.getpeername()
        self._file_handler = logging.FileHandler('/var/log/ssh-server-{}:{}.log'.format(host, port))
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(self._formatter)

        self._logger.setLevel(logging.DEBUG)

        self._logger.addHandler(self._screen_handler)
        self._logger.addHandler(self._file_handler)
        self._logger.propagate = False

    def _create_default_account(self):
        self._account_dict[ADMIN_ACCOUNT_NAME] = {
            "is_admin": True,
            "deletable": False,
            "activate": True
        }
        rc = self._create_account_entry(ADMIN_ACCOUNT_NAME, is_admin=True, deletable=False, activate=True)
        if rc != RcCode.SUCCESS:
            return rc
        if not self._checkk_linux_user_exist(ADMIN_ACCOUNT_NAME):
            rc = self.create_account(ADMIN_ACCOUNT_NAME, ADMIN_ACCOUNT_NAME)
            if rc != RcCode.SUCCESS:
                del self._account_dict[ADMIN_ACCOUNT_NAME]
        else:
            rc = RcCode.SUCCESS
        return rc

    def _checkk_linux_user_exist(self, username):
        try:
            pwd.getpwnam(username)
        except KeyError:
            return False
        return True
    
    def init_account_system(self):
        rc = self._create_default_account()
        if rc != RcCode.SUCCESS:
            return rc
        return RcCode.SUCCESS

    def create_account(self, username, password, is_admin=False):
        if self._checkk_linux_user_exist(username):
            return RcCode.USER_EXIST
        self._account_dict[username] = {
            "is_admin": is_admin,
            "deletable": False,
            "activate": True
        }
        try:
            subprocess.run(['useradd', '-m', '-p', password, username])
        except subprocess.CalledProcessError:
            del self._account_dict[username]
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def delete_account(self, username):
        if not self._checkk_linux_user_exist(username):
            return RcCode.USER_NOT_FOUND
        if not self._account_dict[username]["deletable"]:
            return RcCode.PERMISSION_DENIED
        try:
            subprocess.call(["userdel", "-r", username])
            del self._account_dict[username]
        except subprocess.CalledProcessError:
            return RcCode.FAILURE
        return RcCode.SUCCESS

    def activate_account(self, username):
        if not self._checkk_linux_user_exist(username):
            return RcCode.USER_NOT_FOUND
        if self._account_dict[username]["activate"]:
            return RcCode.SUCCESS
        self._account_dict[username]["activate"] = True
        return RcCode.SUCCESS

    def deactivate_account(self, username):
        if not self._checkk_linux_user_exist(username):
            return RcCode.USER_NOT_FOUND
        if not self._account_dict[username]["activate"]:
            return RcCode.SUCCESS
        self._account_dict[username]["activate"] = False
        return RcCode.SUCCESS
    
    def get_account_info(self, usename):
        if usename not in self._account_dict:
            self._logger.warning("usename {}".format(usename))
            self._logger.warning("db {}".format(self._account_dict))
            return RcCode.DATA_NOT_FOUND, None
        user_info_dict = copy.deepcopy(self._account_dict[usename])
        return RcCode.SUCCESS, user_info_dict
