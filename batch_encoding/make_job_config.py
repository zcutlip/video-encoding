#!/usr/bin/env python3

import glob
import json
import os
import sys
from argparse import ArgumentParser
from pathlib import Path


class NoVideosException(Exception):
    pass


class VideoEncodingConfigFile:
    DEFAULT_TEMPLATE = Path(
        os.path.dirname(os.path.realpath(__file__)), "encoding-jobs-template.json"
    )

    def __init__(
        self, video_list, config_file, outdir, decomb=False, workdir=None, template=None
    ):
        if not template:
            template = self.DEFAULT_TEMPLATE
        else:
            template = os.path.realpath(template)

        config = json.load(open(template, "r"))
        config["outdir"] = outdir
        if decomb:
            config["decomb"] = decomb
        if workdir:
            config["workdir"] = workdir
        else:
            workdir = config.get("workdir")

        videos = self._generate_video_list(video_list, workdir)
        if not videos:
            raise NoVideosException("No videos provided. Video list is empty")
        job_list = self._make_job_list(videos)

        config["jobs"] = job_list
        self.config_file = config_file
        self.config = config

    def save(self):
        json.dump(self.config, open(self.config_file, "w"), indent=2)

    def _make_job_list(self, videos):
        job_list = []
        for video in videos:
            job_dict = {}
            job_dict["input_file"] = video
            job_dict["output_title"] = ""
            job_list.append(job_dict)

        return job_list

    def _generate_video_list(self, video_list_file: str, workdir: str):
        video_list = []
        if video_list_file.endswith(".txt"):
            video_list = self._video_list_from_text_file(video_list_file, workdir)
        else:
            video_list = self._video_list_from_glob(video_list_file, workdir)

        return video_list

    def _video_list_from_glob(self, video_list_glob, workdir):
        video_list = []
        for item in glob.glob(video_list_glob):
            video_list.append(os.path.relpath(item, start=workdir))
        video_list.sort()

        return video_list

    def _video_list_from_text_file(self, video_list_file, workdir):
        video_list = []
        with open(video_list_file, "r") as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line:
                    video_file = os.path.relpath(line, start=workdir)
                    video_list.append(video_file)
        return video_list


def parse_args(args):
    parser = ArgumentParser()
    parser.add_argument(
        "video_list",
        help="Text file containing a line-by-line list of videos to encode or file glob to match a list of .mkv files",
    )
    parser.add_argument("config_file", help="Name of config file to write")
    parser.add_argument(
        "outdir", help="Output directory where encoded videos should be written"
    )
    parser.add_argument(
        "--decomb",
        help="Decomb/deinterlace all videos when encoding",
        action="store_true",
    )
    parser.add_argument(
        "--workdir", help="Working directory where video sources are found"
    )
    parser.add_argument("--template", help="Template to build job config from")

    parsed = parser.parse_args(args)
    return parsed


def main():
    argv = sys.argv[1:]
    parsed = parse_args(argv)
    kwargs = {}
    video_list = parsed.video_list
    config_file = parsed.config_file
    outdir = parsed.outdir
    if parsed.decomb:
        kwargs["decomb"] = True
    if parsed.workdir:
        kwargs["workdir"] = parsed.workdir
    if parsed.template:
        kwargs["template"] = parsed.template

    config = VideoEncodingConfigFile(video_list, config_file, outdir, *kwargs)
    config.save()


if __name__ == "__main__":
    main()
