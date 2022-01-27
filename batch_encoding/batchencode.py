import copy
import glob
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Tuple

from selfcaffeinate import SelfCaffeinate

from .config.batch_config import ConfigFromParsedArgs
from .config.encoding_config import EncodingConfig
from .encode_report import EncodeReport


class MalformedJobException(Exception):
    pass


class BatchEncoderJobsException(Exception):
    def __init__(self, errors):
        super().__init__()
        self.errors = errors


class BatchEncoder(object):
    JOB_QUEUE_FILE = "jobs.json"

    def __init__(self, config: Dict, logger=None, dry_run=False, skip_encode=False):
        if not logger:
            logger = logging.getLogger("batch-encoder")
            self.logger = logger
        self.dry_run = dry_run
        self.skip_encode = skip_encode
        self.decomb = config["decomb"]
        self.workdir = config["workdir"]
        self.outdir = config["outdir"]
        self.encoders: Tuple[SingleEncoder, str] = []
        self._archive_queue = []
        self.malformed_jobs = []
        self.tempdir = tempfile.mkdtemp()
        self.jobfile = Path(self.workdir, self.JOB_QUEUE_FILE)
        self.jobs = config["jobs"]
        self.disable_auto_burn = config["disable_auto_burn"]
        self.add_subtitle = config["add_subtitle"]
        self.archive_root = config["archive_root"]
        self.media_root = config["media_root"]
        self._sanity_check_dirs()
        self._report = EncodeReport()
        self._create_job_list(self.jobs)
        self._process_jobs()
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

        if not self.outdir:
            raise Exception("Output directory not specified.")

        if not os.path.isdir(self.workdir):
            raise Exception("Working directory not found: %s" % self.workdir)

        if not os.path.isdir(self.outdir):
            raise Exception("Output directory not found: %s" % self.outdir)

    def _noncompleted_jobs(self):
        jobs = {}
        loaded_jobs = self._read_job_list()
        for filename, job in loaded_jobs.items():
            if not job["complete"]:
                jobs[filename] = job
        return jobs

    def _process_jobs(self):
        loaded_jobs = self._noncompleted_jobs()

        for input_file, job_dict in loaded_jobs.items():
            decomb = self.decomb
            outdir = self.outdir
            add_subtitle = self.add_subtitle
            disable_auto_burn = self.disable_auto_burn
            crop_params = self.crop_params

            if "decomb" in job_dict:
                decomb = job_dict["decomb"]
            if "outdir" in job_dict:
                outdir = job_dict["outdir"]
            if "add_subtitle" in job_dict:
                add_subtitle = job_dict["add_subtitle"]
            if "disable_auto_burn" in job_dict:
                disable_auto_burn = job_dict["disable_auto_burn"]
            if "crop_params" in job_dict:
                crop_params = job_dict["crop_params"]

            output_title = job_dict["output_title"]
            try:
                encoder = SingleEncoder(
                    self.workdir,
                    self.tempdir,
                    outdir,
                    input_file,
                    output_title,
                    self.archive_root,
                    self.media_root,
                    crop_params,
                    disable_auto_burn=disable_auto_burn,
                    add_subtitle=add_subtitle,
                    decomb=decomb,
                    dry_run=self.dry_run,
                    skip_encode=self.skip_encode
                )
                self.encoders.append((encoder, input_file))
            except MalformedJobException as e:
                self.malformed_jobs.append(e)

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
        encoder: SingleEncoder = None
        while self._archive_queue:
            encoder = self._archive_queue.pop()
            if encoder.needs_archive():
                encoder.do_archive()


class SingleEncoder(object):
    TRANSCODE = "transcode-video"

    def __init__(
        self,
        workdir,
        tempdir,
        outdir,
        input_file,
        output_title,
        archive_root,
        media_root,
        crop_params,
        decomb=False,
        disable_auto_burn=False,
        add_subtitle=None,
        logger=None,
        dry_run=False,
        skip_encode=False
    ):
        if not logger:
            logger = logging.getLogger("single-encoder")
        self.logger = logger
        self.dry_run = dry_run
        self.skip_encode = skip_encode
        self.tempdir = tempdir
        self.outdir = outdir
        self.input_file_basename = os.path.basename(input_file)
        self.output_title = output_title
        self.crop_params = crop_params
        self.decomb = decomb
        self.disable_auto_burn = disable_auto_burn
        self.add_subtitle = add_subtitle
        input_file = Path(workdir, self.input_file_basename)
        self.input_file = str(input_file)

        self.crops_dir = Path(workdir, "Crops")
        self.subtitles_dir = Path(workdir, "subtitles")
        self._report = EncodeReport()
        outlog = "%s.log" % self.input_file_basename
        self.outlog = Path(workdir, outlog)
        outfile = "%s.m4v" % output_title

        temp_file = Path(self.tempdir, outfile)
        self.fq_temp_file = str(temp_file)

        output_file = Path(self.outdir, outfile)
        self.fq_output_file = str(output_file)

        self.archive_complete = False
        self.archive_dst = None
        if archive_root and media_root:
            self.archive_dst = self._construct_archive_dst(
                archive_root, media_root, output_file)

        self._sanity_check_dirs()
        self._sanity_check_params()
        self.command = self._build_command()
        self.encoding_complete = False

    @property
    def report(self):
        return self._report

    def needs_archive(self):
        needs_archive = (
            self.archive_dst is not None and
            self.encoding_complete and
            not self.archive_complete
        )
        return needs_archive

    def needs_encode(self):
        needs_encode = (
            not self.encoding_complete and
            not self.dry_run and
            not self.skip_encode
        )
        return needs_encode

    def do_archive(self):
        if self.needs_archive():
            self.logger.info(
                f"Archiving {self.input_file} to {self.archive_dst}/")
            if not self.dry_run:
                self.archive_dst.mkdir(parents=True, exist_ok=True)
                # TODO: archive crop file and subtitle file if they're available
                shutil.copy2(self.input_file, self.archive_dst)
            self.archive_complete = True

    def run(self):
        self.logger.info("Running:")
        self.logger.info(self.command)
        if self.needs_encode():
            self.outlog_file = open(self.outlog, "wb", 0)
            self.process = subprocess.Popen(
                self.command, stdout=self.outlog_file, stderr=subprocess.PIPE, bufsize=0
            )

    def wait(self):
        status = self._wait()
        if self.needs_encode():
            if status == 0:
                self.logger.info("Moving encoded file to %s" %
                                 self.fq_output_file)
                shutil.move(self.fq_temp_file, self.fq_output_file)
                self._report.add_encoded(
                    self.input_file_basename, str(self.fq_output_file))
            else:
                err_out = self._err_out()
                self._report.add_encoding_failure(
                    self.input_file_basename, err_out)
        self.logger.info("Done.")
        if status == 0:
            self.encoding_complete = True
        return status

    def _wait(self):
        if self.needs_encode():
            self.logger.info(
                "Waiting for encode job of %s to complete." % self.input_file)
            self.process.wait()
            status = self.process.returncode
        else:
            status = 0
        return status

    def _err_out(self):
        _, err_out = self.process.communicate()
        # utf-8 decoding is default if not specified
        err_out = err_out.decode()
        return err_out

    def _sanity_check_dirs(self):
        if not os.path.exists(self.input_file):
            raise MalformedJobException(
                "Input file not found: %s" % self.input_file)

        if not os.path.isdir(self.outdir):
            raise Exception("Output directory not found: %s" % self.outdir)

        if not os.path.isdir(self.tempdir):
            raise Exception("Temp directory not found: %s" % self.tempdir)

    def _sanity_check_params(self):
        if not self.output_title:
            raise MalformedJobException(
                f"No output title for {self.input_file}")

    def _build_command(self):
        crop_option = self._get_crop_option()
        subtitle_option = self._get_sub_option()
        decomb_option = self._get_decomb_option()
        command = [self.TRANSCODE]
        if crop_option:
            for opt in crop_option:
                command.append(opt)
        if subtitle_option:
            for opt in subtitle_option:
                command.append(opt)
        if decomb_option:
            for opt in decomb_option:
                command.append(opt)
        command.append("--m4v")
        command.append(self.input_file)
        command.append("--output")
        command.append(self.fq_temp_file)
        return command

    def _get_sub_lang(self, srt_file_name):
        lang = ""
        if not srt_file_name.endswith(".srt"):
            return lang
        # "subs/mymovie.eng.srt"
        srt_basename = os.path.basename(srt_file_name)
        # "mymovie.eng.srt"
        srt_basename = os.path.splitext(srt_basename)[0]
        # "mymovie.eng"
        lang = os.path.splitext(srt_basename)[1]
        # ".eng"
        lang = lang.lstrip(".")
        # "eng"
        return lang

    def _get_sub_option(self):
        """
        Build option list for burning subtitles.
        Eventually this will be configurable at run-time and may return None.
        """
        if self.disable_auto_burn:
            sub_opt = ["--disable-auto-burn"]
        else:
            sub_opt = ["--burn-subtitle", "scan"]

        if self.add_subtitle:
            sub_opt.extend(["--add-subtitle", self.add_subtitle])

        subtitle_glob = "%s/%s.*.srt" % (
            self.subtitles_dir,
            os.path.splitext(self.input_file_basename)[0],
        )

        matching_srt_files = glob.glob(subtitle_glob)
        for srt_file in matching_srt_files:
            lang = self._get_sub_lang(srt_file)
            sub_opt += ["--add-srt", srt_file]
            sub_opt += ["--bind-srt-language", lang]

        return sub_opt

    def _get_crop_option(self):
        """build option list for cropping video."""
        crop_file = "%s/%s_crop.txt" % (self.crops_dir,
                                        self.input_file_basename)

        try:
            crop_val = open(crop_file, "rb").readline().strip()
            crop_opt = ["--crop", crop_val]
        except Exception as e:
            self.logger.error(e)
            crop_opt = ["--crop", "detect"]

        return crop_opt

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

    def _construct_archive_dst(self, archive_root, media_root, output_file):
        # convert everything to a Path object in case they aren't already
        archive_root = Path(archive_root)
        media_root = Path(media_root)
        output_file = Path(output_file)

        # Find the subpath of the media root there the encoded file will be written
        # E.g., /Volumes/media/videos/Movies/Star Wars (1977).m4v -> Movies/Star Wars (1977).m4v
        relative_output = output_file.relative_to(media_root)

        # Get the stem, e.g., Movies/Star Wars (1977)
        relative_output = relative_output.with_suffix('')

        # Mirror this path in the archive root
        # E.g., /Volumes/Media Archive/videos/Movies/Star Wars (1977)
        archive_path = Path(archive_root, relative_output)

        return archive_path


def main():
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger()
    config = ConfigFromParsedArgs()
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
            encoder = BatchEncoder(encoding_config, skip_encode=skip)
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


if __name__ == "__main__":
    main()
