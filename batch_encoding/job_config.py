import glob
import json
import os
from typing import List, Union

from . import data
from .pkg_resources import pkgfiles


class EncodingJobDuplicateInputException(Exception):
    pass


class EncodingJobNoInputException(Exception):
    pass


class EncodingJob(dict):
    JOB_TEMPLATE = "job-template.json"

    def __init__(self,
                 input_file: str,
                 output_title: str = "",
                 workdir: str = None,
                 outdir: str = None,
                 disble_auto_burn: bool = False,
                 add_subtitle: str = None,
                 decomb: bool = False):
        template_dict = self._load_template()
        super().__init__(template_dict)
        self["input_file"] = input_file
        self["output_title"] = output_title
        if workdir:
            self["workdir"] = workdir
        if outdir:
            self["outdir"] = outdir
        if disble_auto_burn:
            self["no_auto_burn"] = disble_auto_burn
        if add_subtitle:
            self["add_subtitle"] = add_subtitle
        if decomb:
            self["decomb"] = decomb

    def _load_template(self):
        loaded = None
        with pkgfiles(data).joinpath(self.JOB_TEMPLATE).open("r") as _file:
            loaded = json.load(_file)
        return loaded


class EncodingConfig(dict):
    ENCODING_JOBS_TEMPLATE = "encoding-jobs-template.json"

    def __init__(self,
                 video_list_input: str,
                 outdir: str,
                 workdir: str = None,
                 disble_auto_burn: bool = False,
                 add_subtitle: str = None,
                 decomb: bool = False,
                 jobs: List[EncodingJob] = None):
        template_dict = self._load_template()
        super().__init__(template_dict)
        # used only for sanity checking we haven't added the same file twice
        self._input_files = []
        self["outdir"] = outdir
        if workdir:
            self["workdir"] = workdir
        self["no_auto_burn"] = disble_auto_burn
        if add_subtitle:
            self["add_subtitle"] = add_subtitle
        self["decomb"] = decomb
        self["jobs"] = self._make_job_list(
            video_list_input, self["workdir"], jobs=jobs)

    def _load_template(self):
        loaded = None
        with pkgfiles(data).joinpath(self.ENCODING_JOBS_TEMPLATE).open("r") as _file:
            loaded = json.load(_file)
        return loaded

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
        # TODO: handle a list of pre-exisitng job objects
        videos = self._generate_video_list(video_list_input, workdir)
        if not videos:
            raise EncodingJobNoInputException(
                f"No videos found in input specification: {video_list_input}")
        job_list = []
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

    def _generate_video_list(self, video_list_file: str, workdir: str):
        video_list = []
        if video_list_file.endswith(".txt"):
            video_list = self._video_list_from_text_file(
                video_list_file, workdir)
        else:
            video_list = self._video_list_from_glob(video_list_file, workdir)

        return video_list

    def _video_list_from_glob(self, video_list_glob, workdir):
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
        json.dump(self.config, open(config_file, "w"), indent=2)
