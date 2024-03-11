import shlex
from typing import List


class BaseCommand(List[str]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self) -> str:
        command_str = shlex.join(self)
        return command_str


class FFProbeCommand(BaseCommand):
    COMMAND = "ffprobe"

    def __init__(self):
        super().__init__([self.COMMAND])


class TranscodeVideoCommand(BaseCommand):
    # Don Melton's Video Transcoding project
    # https://github.com/donmelton/video_transcoding
    TRANSCODE = "transcode-video"

    def __init__(self):
        super().__init__([self.TRANSCODE])


class OtherTranscodeCommand(TranscodeVideoCommand):
    # Don Melton's Other Video Transcoding project
    # https://github.com/donmelton/other_video_transcoding
    TRANSCODE = "other-transcode"
