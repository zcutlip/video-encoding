#!/usr/bin/env python3

# import argparse
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Tuple

from selfcaffeinate import SelfCaffeinate

from .config.config import BatchEncoderConfig


class BatchEncoder(object):
    QUEUE_FILE = "queue.txt"
    JOB_QUEUE_FILE = "jobs.json"

    def __init__(self, config: Dict, logger=None):
        if not logger:
            logger = logging.getLogger("batch-encoder")
            self.logger = logger
        self.decomb = config.decomb
        self.workdir = config.workdir
        self.outdir = config.outdir
        self.encoders: Tuple[SingleEncoder, str] = []
        self.tempdir = tempfile.mkdtemp()
        self.jobfile = Path(self.workdir, self.JOB_QUEUE_FILE)
        self.jobs = config.jobs
        self._sanity_check_dirs()
        self._create_job_list(self.jobs)
        self._process_jobs()

    def wait(self):
        print("Running all encoders.")
        for encoder, input_file in self.encoders:
            encoder.run()
            encoder.wait()
            self._mark_job_complete(input_file)
        self._clear_completed()

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
            if "decomb" in job_dict:
                decomb = job_dict["decomb"]
            if "outdir" in job_dict:
                outdir = job_dict["outdir"]
            output_title = job_dict["output_title"]

            encoder = SingleEncoder(
                self.workdir,
                self.tempdir,
                outdir,
                input_file,
                output_title,
                decomb=decomb,
            )
            self.encoders.append((encoder, input_file))

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
            job_dict = {"complete": False}
            for k, v in job.items():
                if k != "input_file":
                    job_dict[k] = v
            loaded_jobs[job["input_file"]] = job_dict
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


class SingleEncoder(object):
    TRANSCODE = "transcode-video"

    def __init__(
        self,
        workdir,
        tempdir,
        outdir,
        input_file,
        output_title,
        decomb=False,
        logger=None,
    ):
        if not logger:
            logger = logging.getLogger("single-encoder")
        self.logger = logger
        self.decomb = decomb
        self.tempdir = tempdir
        self.outdir = outdir
        self.input_file_basename = os.path.basename(input_file)
        self.input_file = Path(workdir, self.input_file_basename)
        # self.fq_input_file="%s/%s" % (workdir,input_file)
        self.crops_dir = Path(workdir, "Crops")
        self.subtitles_dir = Path(workdir, "subtitles")
        self.output_title = output_title
        outlog = "%s.log" % self.input_file_basename
        self.outlog = Path(workdir, outlog)
        outfile = "%s.m4v" % output_title
        self.fq_temp_file = Path(self.tempdir, outfile)
        self.fq_output_file = Path(self.outdir, outfile)
        self._sanity_check_dirs()
        self.command = self._build_command()

    def run(self):
        self.logger.info("Running:")
        self.logger.info(self.command)
        self.outlog_file = open(self.outlog, "wb", 0)
        self.process = subprocess.Popen(
            self.command, stdout=self.outlog_file, stderr=self.outlog_file, bufsize=0
        )

    def _wait(self):
        self.logger.info("Waiting for encode job of %s to complete." % self.input_file)
        self.process.wait()

    def wait(self):
        self._wait()
        print("Moving encoded file to %s" % self.fq_output_file)
        shutil.move(self.fq_temp_file, self.fq_output_file)
        print("Done.")

    def _sanity_check_dirs(self):
        if not os.path.exists(self.input_file):
            raise Exception("Input file not found: %s" % self.input_file)

        if not os.path.isdir(self.outdir):
            raise Exception("Output directory not found: %s" % self.outdir)

        if not os.path.isdir(self.tempdir):
            raise Exception("Temp directory not found: %s" % self.tempdir)

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
        sub_opt = ["--burn-subtitle", "scan"]

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
        crop_file = "%s/%s_crop.txt" % (self.crops_dir, self.input_file_basename)

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


def main():
    logger = logging.getLogger()
    config = BatchEncoderConfig(sys.argv[1:])

    if config.no_sleep:
        sc = SelfCaffeinate()
    else:
        sc = None

    logger.info("Creating batch encoder.")
    encoder = BatchEncoder(config)
    logger.info("Waiting for encoder to finish.")
    encoder.wait()
    logger.info("Batch encoder done.")
    if sc:
        sc = None


if __name__ == "__main__":
    main()
