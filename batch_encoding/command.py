import shlex
from typing import List


class EncodeCommand(List[str]):
    TRANSCODE = "transcode-video"

    def __init__(self):
        super().__init__([self.TRANSCODE])

    def __str__(self) -> str:
        command_str = shlex.join(self)
        return command_str
