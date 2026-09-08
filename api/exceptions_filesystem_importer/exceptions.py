class IncorrectAbsolutePathException(Exception):
    def __init__(self, path):
        message = f"Path {path} was provided as an absolute path, this is not supported"
        super().__init__(message)
        self.message = message
