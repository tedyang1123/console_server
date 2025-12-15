import threading


class SshServer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def __init_server(self):
        # Create SSH server subsystem which verifies the user.

        # Create SSH server subsystem which does not verify the user.
        pass

    def run(self):
        pass