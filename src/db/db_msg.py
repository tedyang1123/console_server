class DbQueueMsg:
    def __init__(self, db, operation, **kwargs):
        self.db = db
        self.operation = operation
        self.parameter = kwargs
