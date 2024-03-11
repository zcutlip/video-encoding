import os
from typing import Dict

from ..command import TranscodeVideoCommand
from .encoder_base import SingleEncoderBase


class SingleEncoderSoftware(SingleEncoderBase):
    CROP_AUTO_ARG = "detect"
    ENCODER_VERBOSE_ARG = "verbose"
    # override base class's list
    # this will be checked in the superconstructor
    UNSUPPORTED_OPTIONS = ["resize_1080p", "force_software"]

    def __init__(self, tempdir, job_config: Dict, logger=None, dry_run=False, skip_encode=False, debug=False):
        super().__init__(tempdir, job_config, logger=logger,
                         dry_run=dry_run, skip_encode=skip_encode, debug=debug)

    def _build_command(self):
        crop_option = self._get_crop_option()
        subtitle_option = self._get_sub_option()
        decomb_option = self._get_decomb_option()
        command = TranscodeVideoCommand()
        debug_option = self._get_debug_option()
        if crop_option:
            for opt in crop_option:
                command.append(opt)
        if subtitle_option:
            for opt in subtitle_option:
                command.append(opt)
        if decomb_option:
            for opt in decomb_option:
                command.append(opt)
        if self.m4v:
            command.append("--m4v")
        if self.chapter_spec:
            command.extend(["--chapters", self.chapter_spec])

        if debug_option:
            command.append(debug_option)

        command.append(str(self.fq_input_file))
        command.append("--output")
        command.append(str(self.fq_temp_file))
        return command

    def _get_decomb_option(self):
        """
        Do we need to set decombing?
        """
        decomb_option = None
        if self.decomb:
            # From HandBrakeCLI --help:
            #    --comb-detect[=string]  Detect interlace artifacts in frames.
            #       If not accompanied by the decomb or deinterlace
            #       filters, this filter only logs the interlaced
            #       frame count to the activity log.
            #       If accompanied by the decomb or deinterlace
            #       filters, it causes these filters to selectively
            #       deinterlace only those frames where interlacing
            #       is detected.
            #
            # -H option to transcode-video specifies option to be passed to handbrake
            # TODO: maybe enable this combo by default?
            decomb_option = ["-H", "comb-detect", "--filter", "decomb"]
        return decomb_option

    def _get_sub_option(self):
        """
        Build option list for burning subtitles.
        Eventually this will be configurable at run-time and may return None.
        """
        if self.disable_auto_burn:
            sub_opt = ["--disable-auto-burn"]
        elif self.burn_subtitle_num:
            sub_opt = ["--burn-subtitle", str(self.burn_subtitle_num)]
        else:
            sub_opt = ["--burn-subtitle", self.SUBTITLE_AUTO_ARG]

        if self.add_subtitle:
            sub_opt.extend(["--add-subtitle", self.add_subtitle])

        input_base = os.path.splitext(self.input_file_basename)[0]

        # no matches is an empty list
        srt_files = self._find_srt_files(self.subtitles_dir, input_base)

        for srt_file in srt_files:
            lang = self._get_sub_lang(srt_file)
            sub_opt += ["--add-srt", srt_file]
            sub_opt += ["--bind-srt-language", lang]

        return sub_opt
