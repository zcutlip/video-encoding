#!/usr/bin/env python3
from argparse import ArgumentParser

from .job_config import EncodingConfig


def parse_args():
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

    parsed = parser.parse_args()
    return parsed


def main():
    parsed = parse_args()
    kwargs = {}
    video_list = parsed.video_list
    config_file = parsed.config_file
    outdir = parsed.outdir

    if parsed.workdir:
        kwargs["workdir"] = parsed.workdir

    if parsed.decomb:
        kwargs["decomb"] = True

    config = EncodingConfig(video_list, outdir, **kwargs)
    config.save(config_file)


if __name__ == "__main__":
    main()
