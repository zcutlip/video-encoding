import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Tuple

from selfcaffeinate import SelfCaffeinate

from .config.batch_config import ConfigFromParsedArgs
from .config.encoding_config import EncodingConfig, EncodingJobNoInputException
from .encode_report import EncodeReport
from .encoder.encoder_base import SingleEncoderBase
from .encoder.hardware import SingleEncoderHardware
from .encoder.passthrough import SingleEncoderPassthrough
from .encoder.software import SingleEncoderSoftware
from .exceptions import (
    EncodingOptionNotSupportedException,
    MalformedJobException
)


class BatchEncoderJobsException(Exception):
    def __init__(self, errors):
        super().__init__()
        self.errors = errors


class DuplicateOutputTitlesException(Exception):
    pass


class BatchEncoder(object):
    JOB_QUEUE_FILE = "jobs.json"

    def __init__(self, config: Dict, logger=None, dry_run=False, skip_encode=False, debug=False, fallback=False):
        if not logger:
            logger = logging.getLogger("batch-encoder")
            self.logger = logger
        self.debug = debug
        self.encoder_fallback = fallback
        self.dry_run = dry_run
        self.skip_encode = skip_encode
        self.workdir = config["workdir"]
        self.outdir = config["outdir"]
        self.encoders: Tuple[SingleEncoderBase, str] = []
        self._archive_queue = []
        self.malformed_jobs = []
        self.tempdir = tempfile.mkdtemp()
        self.jobfile = Path(self.workdir, self.JOB_QUEUE_FILE)
        self.jobs = config["jobs"]
        self._sanity_check_dirs()
        self._report = EncodeReport()
        self._create_job_list(self.jobs)
        self._process_jobs(config)
        if self.malformed_jobs:
            raise BatchEncoderJobsException(self.malformed_jobs)

    @property
    def report(self):
        return self._report

    def wait(self) -> int:
        self.logger.info("Running all encoders.")
        status = 0
        for encoder, input_file in self.encoders:
            encoder.run()
            # Before we block on the current encoder finishing,
            # we can do any outstanding archive tasks from previous encoders
            self._do_archive_queue()
            return_code = encoder.wait()
            if return_code:
                status += 1
            else:
                # queue up this archive task and we'll
                # do it while waiting on the next encoder to finish
                self._archive_queue.append(encoder)
                self._mark_job_complete(input_file)
            report = encoder.report
            self._report.update_report(report)

        # Do any remaining archive tasks. This should only be the last encoder
        # to have finished encoding
        self._do_archive_queue()
        self._clear_completed()
        return status

    def _sanity_check_dirs(self):
        if not self.workdir:
            raise Exception("Working directory not specified.")

        if isinstance(self.workdir, str):
            self.workdir = Path(self.workdir)

        if not self.outdir:
            raise Exception("Output directory not specified.")

        if isinstance(self.outdir, str):
            self.outdir = Path(self.outdir)

        if not os.path.isdir(self.workdir):
            raise Exception("Working directory not found: %s" % self.workdir)

        if os.path.exists(self.outdir):
            if not os.path.isdir(self.outdir):
                msg = f"Output path exists but is not a directory: {self.outdir}"
                self.logger.error(msg)
                raise Exception(msg)
        else:
            try:
                self.logger.info(f"Creating output path: {self.outdir}")
                self.outdir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.logger.error(
                    f"Unable to create output path: {self.outdir}")
                raise e

    def _noncompleted_jobs(self):
        jobs = {}
        loaded_jobs = self._read_job_list()
        for filename, job in loaded_jobs.items():
            if not job["complete"]:
                jobs[filename] = job
        return jobs

    def _process_jobs(self, config_dict: Dict):
        loaded_jobs = self._noncompleted_jobs()
        job_config_template = copy.copy(config_dict)
        job_config_template.pop("jobs")
        loaded_job: Dict

        for input_file, loaded_job in loaded_jobs.items():
            job_dict = copy.copy(job_config_template)
            job_dict["input_file"] = input_file
            job_dict["output_title"] = loaded_job["output_title"]
            # override batch parameters with job-specific parameters
            if "decomb" in loaded_job:
                job_dict["decomb"] = loaded_job["decomb"]
            if "outdir" in loaded_job:
                job_dict["outdir"] = loaded_job["outdir"]
            if "add_subtitle" in loaded_job:
                job_dict["add_subtitle"] = loaded_job["add_subtitle"]
            if "disable_auto_burn" in loaded_job:
                job_dict["disable_auto_burn"] = loaded_job["disable_auto_burn"]
            if "burn_subtitle_num" in loaded_job:
                job_dict["burn_subtitle_num"] = loaded_job["burn_subtitle_num"]
            if "crop_params" in loaded_job:
                job_dict["crop_params"] = loaded_job["crop_params"]
            if "quality" in loaded_job:
                job_dict["quality"] = loaded_job["quality"]
            if "m4v" in loaded_job:
                job_dict["m4v"] = loaded_job["m4v"]
            if "movie" in loaded_job:
                job_dict["movie"] = loaded_job["movie"]
            if "chapters" in loaded_job:
                job_dict["chapters"] = loaded_job["chapters"]
            if "no_10_bit" in loaded_job:
                job_dict["no_10_bit"] = loaded_job["no_10_bit"]
            if "resize_1080p" in loaded_job:
                job_dict["resize_1080p"] = loaded_job["resize_1080p"]
            if "additional_options" in loaded_job:
                job_dict["additional_options"] = loaded_job["additional_options"]

            # we don't need passthrough to remain in the dictionary because
            # it isn't used by the encoder constructor
            # instead, we just set the flag here so we can instantiate the proper class below
            passthrough = job_dict.pop("passthrough")
            if "passthrough" in loaded_job:
                # if this specific job should (or should NOT) be a passthrough, let's get
                # that value
                passthrough = loaded_job.pop("passthrough")

            encoder_cls: SingleEncoderBase
            class_list = [SingleEncoderHardware, SingleEncoderSoftware]
            if passthrough:
                # make the passthrough encoder first in line
                # and we can optionally fall back to the other encoders
                # if we need to and were told to
                class_list.insert(0, SingleEncoderPassthrough)
            for encoder_cls in class_list:
                self.logger.debug(
                    f"Trying encoder class {encoder_cls.__name__}")
                try:
                    encoder = encoder_cls(
                        self.tempdir,
                        job_dict,
                        logger=self.logger,
                        dry_run=self.dry_run,
                        skip_encode=self.skip_encode,
                        debug=self.debug)
                    self.encoders.append((encoder, input_file))

                except EncodingOptionNotSupportedException as e:
                    if self.encoder_fallback:
                        self.logger.error(f"{e}")
                        self.logger.error("Trying next encoder class")
                        continue
                    msg = f"Can't encode {input_file}\nException: {e}"
                    raise EncodingOptionNotSupportedException(msg)

                except MalformedJobException as e:
                    self.malformed_jobs.append(e)

                break

    def _read_job_list(self):
        try:
            jobs = json.load(open(self.jobfile, "r"))
        except FileNotFoundError:
            jobs = None

        return jobs

    def _write_job_list(self, job_dict):
        json.dump(job_dict, open(self.jobfile, "w"), indent=2)

    def _mark_job_complete(self, input_filename):
        joblist = self._read_job_list()
        job = joblist[input_filename]
        job["complete"] = True
        joblist[input_filename] = job
        self._write_job_list(joblist)

    def _create_job_list(self, jobs):
        seen_output_titles = []
        duplicate_output_titles = set()
        loaded_jobs = self._read_job_list()
        if not loaded_jobs:
            loaded_jobs = {}
        for job in jobs:
            if job["input_file"] in loaded_jobs:
                continue
            job_dict: Dict = copy.copy(job)
            input_file = job_dict.pop("input_file")
            job_dict["complete"] = False

            loaded_jobs[input_file] = job_dict
        for _, job_dict in loaded_jobs.items():
            output_title = job_dict["output_title"]
            if output_title in seen_output_titles:
                duplicate_output_titles.add(output_title)
            else:
                seen_output_titles.append(output_title)
        if duplicate_output_titles:
            dups = list(duplicate_output_titles)
            msg = f"Duplicate output titles found: {dups}"
            self.logger.fatal(msg)
            # raise the exception before we write out jobs.json
            raise DuplicateOutputTitlesException(msg)

        self._write_job_list(loaded_jobs)

    def _delete_job_list(self):
        os.unlink(self.jobfile)

    def _clear_completed(self):
        loaded_jobs = self._read_job_list()
        incomplete_jobs = 0
        for input_file, job_dict in loaded_jobs.items():
            if job_dict["complete"]:
                continue
            incomplete_jobs += 1
        if incomplete_jobs == 0:
            self._delete_job_list()

    def _do_archive_queue(self):
        self.logger.info("Checking archive queue")
        encoder: SingleEncoderBase = None
        while self._archive_queue:
            encoder = self._archive_queue.pop()
            if encoder.needs_archive():
                encoder.do_archive()


def do_encoding():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("batchencode")
    try:
        config = ConfigFromParsedArgs()
    except EncodingJobNoInputException as e:
        logger.fatal(f"{e}")
        return -1
    debug = config["debug"]
    fallback = config["fallback_okay"]
    if debug:
        # set DEBUG on the root logger so that future loggers inherit it
        logging.getLogger().setLevel(logging.DEBUG)

        # set DEBUG on our current logger
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    sc = None
    if config.encoding_config["no_sleep"]:
        sc = SelfCaffeinate()

    logger.info("Creating batch encoder.")
    skip = False
    if config["skip_encode"]:
        skip = True
    encoding_config: EncodingConfig = config.encoding_config
    if encoding_config.new_or_updated:
        logger.info("Saving updated config. Please review.")
        encoding_config.save()
    else:
        try:
            encoder = BatchEncoder(
                encoding_config, skip_encode=skip, debug=debug, fallback=fallback)
        except BatchEncoderJobsException as e:
            logger.error("Errors creating batch encoder")
            for err in e.errors:
                logger.error(f"{err}")
                sc = None
            return -1
        logger.info("Waiting for encoder to finish.")
        encoder.wait()
        logger.info("Batch encoder done.")

        report = encoder.report
        if config["report_email"]:
            report.email_report(config["report_email"])

        if config["report_path"]:
            report.write_report(config["report_path"])

    if sc:
        sc = None
    return 0


def main():
    try:
        return do_encoding()
    except KeyboardInterrupt:
        print("KeyboardInterrupt: quitting")
        return 1
    except Exception as e:
        logging.fatal(f"Terminating due to exception: {e}")
        return 1


if __name__ == "__main__":
    main()
