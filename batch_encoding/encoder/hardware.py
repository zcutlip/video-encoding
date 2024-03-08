import os
import sys
from pathlib import Path
from typing import Dict

from ..command import OtherTranscodeCommand
from ..exceptions import IncompatibleInputException
from .encoder_base import SingleEncoderBase


class OperatingSystemNotSupported(Exception):
    pass


class SingleEncoderHardware(SingleEncoderBase):
    SUPPORTED_PLATFORMS = ["darwin"]
    CROP_AUTO_ARG = "auto"
    SUBTITLE_AUTO_ARG = "auto"
    ENCODER_VERBOSE_ARG = "debug"
    REDIRECT_STDERR = True
    # override base class's list
    # this will be checked in the superconstructor
    UNSUPPORTED_OPTIONS = ["decomb", "m4v", "chapters",]

    def __init__(self, tempdir, job_config: Dict, logger=None, dry_run=False, skip_encode=False, debug=False):
        if sys.platform not in self.SUPPORTED_PLATFORMS:
            raise OperatingSystemNotSupported(
                f"OS/platform not supported {sys.platform}")
        self._hevc = False
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

        # only use hevc/h.265 for 4K, else use h.264, which is default
        if self.video_stream_info.at_least_4k():
            self._hevc = True
            command.extend(["--hevc"])
        command.extend(["--vt"])
        # only enable 10-bit if we're using hevc/h.265 (and we weren't told to disable it)
        if self._hevc and not self.no_10_bit:
            command.append("--10-bit")
        else:
            command.append("--no-10-bit")

        if self.resize_1080p:
            if self.video_stream_info.at_least_4k():
                command.append("--1080p")
            else:
                msg = f"Input file [{self.input_file_basename}] must be 4k or better to resize to 1080p"
                raise IncompatibleInputException(msg)

        if self.additional_options:
            for option in self.additional_options:
                command.append(option)
        self.input_file_symlink = self._make_input_symlink()
        command.append(str(self.input_file_symlink))
        return command

    def _populate_external_sub_resources(self):
        # locate any matching external srt files that need to be copied into place
        # The way this works is:
        # locate all:
        # {workdir}/subtitles/The_Matrix_title_00.*.srt
        # compute destination:
        # {outdir}/The Matrix (1999) - 1080p.eng.srt
        # then add the (fq_src, fq_dest) pair to self.sources_to_copy

        input_base = os.path.splitext(self.input_file_basename)[0]
        output_base = os.path.splitext(self.output_file_base)[0]
        # no matches is an empty list
        srt_files = self._find_srt_files(self.subtitles_dir, input_base)
        for srt_infile in srt_files:
            lang = self._get_sub_lang(srt_infile)
            srt_dest_base = f"{output_base}.{lang}.srt"
            fq_dest = Path(self.outdir, srt_dest_base)
            srt_dest = str(fq_dest)
            src_dest_pair = (srt_infile, srt_dest)
            self.resources_to_copy.append(src_dest_pair)

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

        return sub_opt

    def run(self):
        os.chdir(self.tempdir)
        return super().run()
