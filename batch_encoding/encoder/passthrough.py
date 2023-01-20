import shutil
from datetime import datetime
from typing import Dict

from ..exceptions import EncodingOptionNotSupportedException
from .encoder_base import SingleEncoderBase


class SingleEncoderPassthrough(SingleEncoderBase):
    CROP_AUTO_ARG = "auto"
    SUBTITLE_AUTO_ARG = "auto"
    ENCODER_VERBOSE_ARG = "debug"
    REDIRECT_STDERR = True
    UNSUPPORTED_OPTIONS = ["decomb", "m4v", "chapters",
                           "disable_auto_burn", "add_subtitle", "crop_params", "chapters"]

    def __init__(self, tempdir, job_config: Dict, logger=None, dry_run=False, skip_encode=False, debug=False):

        bad_options = []
        for option in self.UNSUPPORTED_OPTIONS:
            if job_config[option]:
                bad_opt = f"--{option}"
                bad_options.append(bad_opt)

        if bad_options:
            msg = f"Unsupported options for {self.__class__.__name__}: {bad_options}"
            raise EncodingOptionNotSupportedException(msg)

        super().__init__(tempdir, job_config, logger, dry_run, skip_encode, debug=debug)
        self.encoding_complete = True

    def _build_command(self):
        return []

    def run(self):
        date_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        with open(self.encoder_log, "w") as logfile:
            print("** Passthrough Encoder **", file=logfile)
            print(f"Date: {date_str}", file=logfile)
            print(f"Source: {self.fq_input_file}", file=logfile)
            print(f"Destination: {self.fq_output_file}", file=logfile)
        super().run()

    def needs_copy(self):
        return True

    def copy_to_dest(self):

        self.logger.info(
            f"Copying input file to {self.fq_output_file}")
        shutil.copy2(self.fq_input_file, self.fq_output_file)
