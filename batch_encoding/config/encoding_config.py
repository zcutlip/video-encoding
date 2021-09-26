import glob
import json
import os
from pathlib import Path
from typing import Dict, List, Union

from .. import data
from ..pkg_resources import pkgfiles
from .default import BatchEncoderDefaultConfig


class EncodingJobDuplicateInputException(Exception):
    pass


class EncodingJobNoInputException(Exception):
    pass


class EncodingJobMalformedDictException(Exception):
    pass


class EncodingConfigArchivePathException(Exception):
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
    ENCODING_CONFIG_KEYS = list(
        BatchEncoderDefaultConfig().encoding_config_keys)

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

    def __init__(self,
                 base_config: dict,
                 config_file: str,
                 video_input_str: str = ""):
        super().__init__(base_config)
        # used only for sanity checking we haven't added the same file twice
        self._input_files = {}

        # Did we create a new config/update an existing one?
        self._new_or_updated = False
        # save this so we can write it to disk later if it is new or updated
        self._config_file = config_file
        self._update_from_config_file(config_file)

        self["jobs"] = self._make_job_list(
            video_input_str, self["workdir"], jobs=self["jobs"])
        # might not be fully configured yet, so don't sanity check paths
        # self.sanity_check_archive_paths()

    @property
    def new_or_updated(self):
        return self._new_or_updated

    def save(self):
        json.dump(self, open(self._config_file, "w"), indent=2)

    def sanity_check(self):
        self.sanity_check_archive_paths()

    def sanity_check_archive_paths(self):
        if self["archive_root"]:
            if not self["media_root"]:
                raise EncodingConfigArchivePathException(
                    "Archive root path provided without media root path")
            media_root = Path(self["media_root"])
            outdir = Path(self["outdir"])
            if media_root not in outdir.parents:
                raise EncodingConfigArchivePathException(
                    f"Output directory {outdir} not a subdirectory of media root {media_root}")

    def _update_from_config_file(self, config_file):
        try:
            loaded = json.load(open(config_file, "r"))
            self.update(loaded)
        except FileNotFoundError:
            self._new_or_updated = True

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

        videos_dict = self._generate_video_list(
            video_list_input, workdir, job_list)
        new_videos = [k for k, v in videos_dict.items() if v["new"] is True]
        new_videos.sort()
        if new_videos:
            self._new_or_updated = True
        for input_file in new_videos:
            input_file = self._relpath(input_file, workdir)
            job = EncodingJob(input_file)
            job_list.append(job)

        if not job_list:
            raise EncodingJobNoInputException(
                f"No videos found in input specification: {video_list_input}")
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

    def _append_input_file(self, input_file, workdir, new=True):
        input_abs_path = input_file
        if not os.path.isabs(input_file):
            input_abs_path = self._resolve_abs_path(input_file, prefix=workdir)
        if input_abs_path in self._input_files:
            raise EncodingJobDuplicateInputException(
                f"Attempted to add input file twice: {input_abs_path}")
        self._input_files[input_abs_path] = {"new": new}

        return dict(self._input_files)

    def _generate_video_list(self, video_list_file: str, workdir: str, job_list=[]):
        self._video_list_from_job_list(job_list, workdir)

        if video_list_file:
            if video_list_file.endswith(".txt"):
                self._video_list_from_text_file(video_list_file, workdir)
            else:
                self._video_list_from_glob(video_list_file, workdir)
        return self._input_files

    def _video_list_from_job_list(self, job_list: List[EncodingJob], workdir):
        video_list = {}
        for job in job_list:
            job_workdir = job.get("workdir", workdir)
            video_list = self._append_input_file(
                job["input_file"], job_workdir, new=False)
        return video_list

    def _video_list_from_glob(self, video_list_glob, workdir):
        video_list = {}
        if workdir:
            video_list_glob = os.path.join(workdir, video_list_glob)
        for item in glob.glob(video_list_glob):
            video_list = self._append_input_file(item, workdir)
        return video_list

    def _video_list_from_text_file(self, video_list_file, workdir):
        video_list = {}
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
