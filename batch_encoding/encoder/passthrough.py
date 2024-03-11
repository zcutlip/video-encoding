import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict

from .encoder_base import SingleEncoderBase


class SingleEncoderPassthrough(SingleEncoderBase):
    CROP_AUTO_ARG = "auto"
    SUBTITLE_AUTO_ARG = "auto"
    ENCODER_VERBOSE_ARG = "debug"
    REDIRECT_STDERR = True
    # override base class's list
    # this will be checked in the superconstructor
    UNSUPPORTED_OPTIONS = ["decomb",
                           "m4v",
                           "chapters",
                           "disable_auto_burn",
                           "add_subtitle",
                           "crop_params",
                           "chapters",
                           "resize_1080p",
                           "force_software"]

    def __init__(self, tempdir, job_config: Dict, logger=None, dry_run=False, skip_encode=False, debug=False):
        super().__init__(tempdir, job_config, logger, dry_run, skip_encode, debug=debug)
        self.encoding_complete = True

    def _build_command(self):
        return []

    def run(self):
        # get a path to the logfile we're going to write
        # in the same directory next to the input file
        input_log_base = f"{self.input_file_basename}.log"
        fq_input_log_file = Path(self.workdir, input_log_base)

        date_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

        log_lines = ["** Passthrough Encoder **",
                     f"Date: {date_str}",
                     f"Source: {self.fq_input_file}",
                     f"Destination: {self.fq_output_file}",
                     ""]

        with open(self.encoder_log, "w") as logfile:
            logfile.write("\n".join(log_lines))

        # this is mostly to make it easy to see on the filesystem
        # which input files have been encoded, but it's also occasionally
        # convenient to have the work log right there
        with open(fq_input_log_file, "w") as logfile:
            logfile.write("\n".join(log_lines))

        super().run()

    def needs_copy(self):
        return True

    def copy_to_dest(self):

        self.logger.info(
            f"Copying input file to {self.fq_output_file}")
        shutil.copy2(self.fq_input_file, self.fq_output_file)
