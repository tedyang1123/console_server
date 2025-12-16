import base64
import os
import threading
import pam
import paramiko


class SshKeyHandler:
    def __init__(self, server_pri_key_file, auth_host_pub_key_file=None):
        self._auth_host_pub_key_file = auth_host_pub_key_file
        self._server_pri_key_file = os.path.expanduser(server_pri_key_file)
        self._server_private_key = None
        self._host_pub_keys = {}

        self._init_server_pri_key()
        self._init_host_pub_key()

    def _init_host_pub_key(self):
        if self._auth_host_pub_key_file:
            try:
                with open(self._auth_host_pub_key_file, 'r') as fd:
                    host_keys = fd.readlines()
                for key in host_keys:
                    entries = key.split(' ')
                    if len(entries) != 3:
                        continue
                    if entries[0] != 'ssh-rsa':
                        continue

                    user = entries[2].split('@')
                    self.add_host_public_key(entries[1], user[0])
            except OSError:
                print("Can not access file to get the host public keys.")
                return

    def _init_server_pri_key(self):
        self._server_private_key = paramiko.RSAKey(filename=self._server_pri_key_file)

    def add_host_public_key(self, user, key_data):
        key = paramiko.RSAKey(data=base64.decodestring(key_data))
        if user not in self._host_pub_keys:
            self._host_pub_keys[user] = []
        self._host_pub_keys[user].append(key)

    def get_host_public_key(self, user):
        if user not in self._host_pub_keys:
            return None
        return self._host_pub_keys[user]

    def get_server_private_key(self):
        return self._server_private_key


class SshServerPassWdAuthenticator(paramiko.ServerInterface):
    def __init__(self, ssh_key_handler):
        self.thread_event = threading.Event()
        self._ssh_key_handler = ssh_key_handler
        self.username = ''
        self.key = ''

    def check_channel_request(self, kind, chanid):
        """ Check if channel request is ok.
        For now support only session.
        """
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def auth_fail(self):
        """ Failed authentication
        """
        return paramiko.AUTH_FAILED

    def auth_success(self):
        """ Successful authentication
        """
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_password(self, username, password):
        """ Check for user password. Disabled by default.

        @param username Username to check
        @param password Password to check
        @return paramiko.AUTH_FAILED
        """
        p = pam.pam()
        if not p.authenticate(username, password):
            return paramiko.AUTH_FAILED
        self.username = username
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username, key):
        """ Check for public key authentication.
        Utilizes SSHKeyHandler for managing keys.

        @param username Username to check
        @param key User provided public key
        @return paramiko.AUTH_SUCCESSFUL if key found for user, paramiko.AUTH_FAILED otherwise
        """
        keys = self._ssh_key_handler.get_host_public_key(username)
        if not keys:
            return paramiko.AUTH_FAILED
        if key in keys:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def enable_auth_gssapi(self):
        """ GSSAPI disabled by default
        """
        return False

    def get_allowed_auths(self, username):
        """ Get allowed authentication methods.
        By default supports only publickey.
        Methods are comma separated list.

        Possible values: gssapi-keyex,gssapi-with-mic,password,publickey

        @returns String containing authentication methods
        """
        return 'password,publickey'

    def check_channel_shell_request(self, channel):
        """ Check if we provide shell

        @returns True if shell is provided, False otherwise
        """
        self.thread_event.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        """ Check if we provide pseudo-terminal on given dimensions

        @returns True if pty is provided, False otherwise
        """
        return True


class SshServerNoneAuthenticator(paramiko.ServerInterface):
    def __init__(self, ssh_key_handler):
        self.thread_event = threading.Event()
        self._ssh_key_handler = ssh_key_handler
        self.username = ''
        self.key = ''

    def check_channel_request(self, kind, chanid):
        """ Check if channel request is ok.
        For now support only session.
        """
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def auth_fail(self):
        """ Failed authentication
        """
        return paramiko.AUTH_FAILED

    def auth_success(self):
        """ Successful authentication
        """
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_none(self, username):
        """ CDetermine if a client may open channels with no (further) authentication.

        @param username Username to check
        @return paramiko.AUTH_FAILED
        """
        # TBD: implement the user authorized
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_password(self, username, password):
        """ Check for user password. Disabled by default.

        @param username Username to check
        @param password Password to check
        @return paramiko.AUTH_FAILED
        """
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        """ Check for public key authentication.
        Utilizes SSHKeyHandler for managing keys.

        @param username Username to check
        @param key User provided public key
        @return paramiko.AUTH_SUCCESSFUL if key found for user, paramiko.AUTH_FAILED otherwise
        """
        keys = self._ssh_key_handler.get_host_public_key(username)
        if not keys:
            return paramiko.AUTH_FAILED
        if key in keys:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def enable_auth_gssapi(self):
        """ GSSAPI disabled by default
        """
        return False

    def get_allowed_auths(self, username):
        """ Get allowed authentication methods.
        By default supports only publickey.
        Methods are comma separated list.

        Possible values: gssapi-keyex,gssapi-with-mic,password,publickey

        @returns String containing authentication methods
        """
        return 'password,publickey'

    def check_channel_shell_request(self, channel):
        """ Check if we provide shell

        @returns True if shell is provided, False otherwise
        """
        self.thread_event.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        """ Check if we provide pseudo-terminal on given dimensions

        @returns True if pty is provided, False otherwise
        """
        return True
