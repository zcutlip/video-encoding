class MalformedJobException(Exception):
    pass


class EncodingOptionNotSupportedException(Exception):
    pass


class IncompatibleInputException(Exception):
    """
    Input video file not compatible with a provided option
    """
    pass
