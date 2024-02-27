import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Union


class VideoStreamInfoException(Exception):
    pass


class VideoStreamInfo(dict):
    HEIGHT_4k = 2160
    WIDTH_4K = 3840
    FFPROBE_COMMAND = "ffprobe"

    def __init__(self, video_path: Union[str, Path], logger=None):
        super().__init__()
        if not logger:
            logger = logging.getLogger("video-stream-info")
        self.logger = logger
        video_path = Path(video_path)
        self._video_path = video_path

        all_streams_dict = self._load_stream_info(video_path)
        super().update(all_streams_dict)

    def _locate_video_stream(self) -> Dict[str, Any]:
        streams: List[Dict[str, Any]] = self["streams"]
        stream: Dict[str, Any] = None
        for stream in streams:
            if stream["codec_type"] == "video":
                break
        if not stream:
            raise VideoStreamInfoException(
                f"Could not locate video stream for {self._video_path}")
        return stream

    def _run_ffprobe(self, video_path: Path) -> str:
        ffprobe_argv = [self.FFPROBE_COMMAND,
                        "-print_format", "json",
                        "-show_format",
                        "-v", "quiet",
                        "-show_streams", str(video_path)]
        _ran = subprocess.run(
            ffprobe_argv, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        stdout = _ran.stdout
        stderr = _ran.stderr

        try:
            _ran.check_returncode()
        except subprocess.CalledProcessError as err:
            stderr_output = stderr.decode("utf-8").rstrip()
            self.logger.error(f"ffprobe command error: {stderr_output}")
            raise err
        stdout_output = stdout.decode("utf-8").rstrip()

        return stdout_output

    def _load_stream_info(self, video_path: Path):
        ffprobe_out = self._run_ffprobe(video_path)
        all_streams = json.loads(ffprobe_out)
        return all_streams

    def screen_height(self) -> int:
        # convert the video's height to the height on a 16:9 screen
        # this accounts for videos with theatrical other ratios that may have been cropped
        width = self.video_width()
        # 16:9 is the typical screen ratio, so multiply the width by the inverse to get the height
        # e.g., to get 1920x1080, do: 1920 * (9/16)
        height = int(width * (9/16))
        return height

    def video_width(self):
        video_stream = self._locate_video_stream()
        # this should always be an int, but it doesn't hurt to convert regarless
        if not isinstance(video_stream["width"], int):
            width = int(video_stream["width"], 0)
        else:
            width = video_stream["width"]
        return width

    def video_height(self) -> int:
        video_stream = self._locate_video_stream()
        # this should always be an int, but it doesn't hurt to convert regarless
        if not isinstance(video_stream["height"], int):
            height = int(video_stream["height"], 0)
        else:
            height = video_stream["height"]
        return height

    def at_least_4k(self) -> bool:
        # this should handle the following 4K scenarios
        # - 16:9 4k: 3840x2160
        # - theatrical ratios where height cropped to less than 2160
        # - 4:3 TV ratio where height is 2160 but width is less than 3840
        four_k = False
        if self.video_height() >= self.HEIGHT_4k:
            # video height is most obvious check, but
            # could be cropped if not 16:9
            four_k = True
        elif self.video_width() >= self.WIDTH_4K:
            # if 4K cropped, width should still be 3840
            four_k = True

        return four_k
