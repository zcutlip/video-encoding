import glob
import json
import os
from typing import Dict, List, Union

from ..pkg_resources import pkgfiles
from . import data
from .base_config import make_config_parse_args
from .default import BatchEncoderDefaultConfig


class EncodingJobDuplicateInputException(Exception):
    pass


class EncodingJobNoInputException(Exception):
    pass


class EncodingJobMalformedDictException(Exception):
    pass


class DefaultEncodingJob(dict):
    JOB_TEMPLATE = "job-template.json"

    def __init__(self):
        super().__init__()
        default_job = self._load_default()
        self.update(default_job)

    def _load_default(self):
        with pkgfiles(data).joinpath(self.JOB_TEMPLATE).open("r") as _file:
            loaded = json.load(_file)
        return loaded


class EncodingJob(DefaultEncodingJob):
    ENCODING_CONFIG_KEYS = list(BatchEncoderDefaultConfig().keys())

    def __init__(self, input_file, job_dict: Dict = {}):
        super().__init__()
        self["input_file"] = input_file
        self["output_title"] = job_dict.get("output_title", "")
        for key in self.ENCODING_CONFIG_KEYS:
            if key in job_dict:
                self[key] = job_dict[key]

    @classmethod
    def from_existing_job(cls, job_dict):
        try:
            input_file = job_dict["input_file"]
        except KeyError:
            raise EncodingJobMalformedDictException(
                "No input file in existing job dict")
        return cls(input_file, job_dict=job_dict)


class EncodingConfig(dict):
    ENCODING_JOBS_TEMPLATE = "encoding-jobs-template.json"

    def __init__(self,
                 base_config: dict,
                 video_list_input: str = ""):
        super().__init__(base_config)
        # used only for sanity checking we haven't added the same file twice
        self._input_files = []

        self["jobs"] = self._make_job_list(
            video_list_input, self["workdir"], jobs=self["jobs"])

    @classmethod
    def new_config(cls):
        default = BatchEncoderDefaultConfig()
        base_config = default.encoding_config
        parsed_args = make_config_parse_args()
        base_config["outdir"] = parsed_args.outdir

        if parsed_args.workdir is not None:
            base_config["workdir"] = parsed_args.workdir
        if parsed_args.decomb is not None:
            base_config["decomb"] = parsed_args.decomb
        if parsed_args.no_sleep is not None:
            base_config["no_sleep"] = parsed_args.no_sleep
        if parsed_args.disable_auto_burn is not None:
            base_config["disable_auto_burn"] = parsed_args.disable_auto_burn
        if parsed_args.add_subtitle is not None:
            base_config["add_subtitle"] = parsed_args.add_subtitle

        job_config_file = parsed_args.config_file
        video_list = parsed_args.video_list
        encoding_config = cls(base_config, video_list_input=video_list)
        encoding_config.save(job_config_file)
        return encoding_config

    def _relpath(self, input_file, workdir):
        relpath = input_file

        # if workdir is none, and input_file is absolute
        # we should leave it alone, otherwise
        # we'll be resolving it relative to our CWD
        # If workdir is none, and input_file is relative already
        # Then there's no point because it won't change
        # so either resolve relative to workdir or leave it alone
        if workdir:
            relpath = os.path.relpath(input_file, start=workdir)
        return relpath

    def _make_job_list(self, video_list_input: str, workdir: Union[None, str], jobs=[]):
        job_list = []
        if jobs:
            for job_dict in jobs:
                job = EncodingJob.from_existing_job(job_dict)
                job_list.append(job)

        videos = self._generate_video_list(video_list_input, workdir, job_list)
        if not videos:
            raise EncodingJobNoInputException(
                f"No videos found in input specification: {video_list_input}")
        for input_file in videos:
            input_file = self._relpath(input_file, workdir)
            job = EncodingJob(input_file)
            job_list.append(job)

        return job_list

    def _resolve_abs_path(self, pathname, prefix=None):
        # we need to do expanduser (e.g., turn ~/ into /Users/zach)
        # first because none of the other operations take it into account
        pathname = os.path.expanduser(pathname)
        if prefix:
            prefix = os.path.expanduser(prefix)

        if not os.path.isabs(pathname) and prefix:
            # of pathname is already absolute, prefix should be ignored
            pathname = os.path.join(prefix, pathname)

        # we still may not have an absolute path
        # pathname could have been encoding/item.mkv
        # prefix might be ../scratch-data/tmp/, or not provided
        if not os.path.isabs:
            pathname = os.path.abspath()

        # we still might have something like
        # /Volumes/Encoding/encoding/Star Wars/../item.mkv
        pathname = os.path.normpath(pathname)
        return pathname

    def _append_input_file(self, input_file, workdir):
        input_abs_path = input_file
        if not os.path.isabs(input_file):
            input_abs_path = self._resolve_abs_path(input_file, prefix=workdir)
        if input_abs_path in self._input_files:
            raise EncodingJobDuplicateInputException(
                f"Attempted to add input file twice: {input_abs_path}")
        self._input_files.append(input_abs_path)
        self._input_files.sort()
        return list(self._input_files)

    def _generate_video_list(self, video_list_file: str, workdir: str, job_list=[]):
        video_list = self._video_list_from_job_list(job_list, workdir)

        if video_list_file.endswith(".txt"):
            video_list = self._video_list_from_text_file(
                video_list_file, workdir)
        else:
            video_list = self._video_list_from_glob(video_list_file, workdir)

        return video_list

    def _video_list_from_job_list(self, job_list: List[EncodingJob], workdir):
        video_list = []
        for job in job_list:
            job_workdir = job.get("workdir", workdir)
            video_list = self._append_input_file(
                job["input_file"], job_workdir)
        return video_list

    def _video_list_from_glob(self, video_list_glob, workdir):
        video_list = []
        if workdir:
            video_list_glob = os.path.join(workdir, video_list_glob)
        for item in glob.glob(video_list_glob):
            video_list = self._append_input_file(item, workdir)
        return video_list

    def _video_list_from_text_file(self, video_list_file, workdir):
        video_list = []
        with open(video_list_file, "r") as f:
            lines = f.readlines()
            for line in lines:
                # spaces are valid on most filesystems, so lets deal with that
                # edge case
                # Just strip newline
                line = line.rstrip("\n")

                # blank lines okay
                if line:
                    video_list = self._append_input_file(line, workdir)
        return video_list

    def save(self, config_file):
        json.dump(self, open(config_file, "w"), indent=2)
