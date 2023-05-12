import os
import sys
from pathlib import Path
from typing import Dict

from ..command import OtherTranscodeCommand
from ..exceptions import EncodingOptionNotSupportedException
from .encoder_base import SingleEncoderBase


class OperatingSystemNotSupported(Exception):
    pass


class SingleEncoderHardware(SingleEncoderBase):
    SUPPORTED_PLATFORMS = ["darwin"]
    CROP_AUTO_ARG = "auto"
    SUBTITLE_AUTO_ARG = "auto"
    ENCODER_VERBOSE_ARG = "debug"
    REDIRECT_STDERR = True
    UNSUPPORTED_OPTIONS = ["decomb", "m4v", "chapters"]

    def __init__(self, tempdir, job_config: Dict, logger=None, dry_run=False, skip_encode=False, debug=False):
        if sys.platform not in self.SUPPORTED_PLATFORMS:
            raise OperatingSystemNotSupported(
                f"OS/platform not supported {sys.platform}")
        bad_options = []
        for option in self.UNSUPPORTED_OPTIONS:
            if job_config[option]:
                bad_opt = f"--{option}"
                bad_options.append(bad_opt)

        if bad_options:
            msg = f"Unsupported options for {self.__class__.__name__}: {bad_options}"
            raise EncodingOptionNotSupportedException(msg)

        super().__init__(tempdir, job_config, logger, dry_run, skip_encode, debug=debug)

    def _make_input_symlink(self):
        input_path = Path(self.tempdir, "input")
        input_path.mkdir(exist_ok=True)
        fq_linkname = Path(input_path, self.output_file_base)
        self.logger.debug(
            f"Making symlink from {self.fq_input_file} to {fq_linkname}")
        try:
            os.symlink(self.fq_input_file, fq_linkname)
        except FileExistsError:
            pass
        return fq_linkname

    def _build_command(self):
        crop_option = self._get_crop_option()
        subtitle_option = self._get_sub_option()
        debug_option = self._get_debug_option()

        command = OtherTranscodeCommand()
        if crop_option:
            for opt in crop_option:
                command.append(opt)
        if subtitle_option:
            for opt in subtitle_option:
                command.append(opt)
        if debug_option:
            command.append(debug_option)
        command.extend(["--hevc", "--vt", "--10-bit"])
        self.input_file_symlink = self._make_input_symlink()
        command.append(str(self.input_file_symlink))
        return command

    def _get_sub_option(self):
        """
        Build option list for burning subtitles.
        Eventually this will be configurable at run-time and may return None.
        """

        # --burn-subtitle TRACK|auto
        if self.disable_auto_burn:
            # there is no disable-subtitle-burn for other-transcode
            # I believe you just don't populate the "--burn-subtitle" option
            sub_opt = []
        elif self.burn_subtitle_num:
            sub_opt = ["--burn-subtitle", str(self.burn_subtitle_num)]
        else:
            sub_opt = ["--burn-subtitle", self.SUBTITLE_AUTO_ARG]

        if self.add_subtitle:
            # --add-subtitle TRACK[=forced]|auto|all|LANGUAGE|STRING
            sub_opt.extend(["--add-subtitle", self.add_subtitle])

        # Check for external subtitle files that need to be copied
        # other-transcode doesn't support encoding these into the resulting file
        # so we need to copy them into place if they exist
        self._populate_external_sub_resources()

    def run(self):
        os.chdir(self.tempdir)
        return super().run()
