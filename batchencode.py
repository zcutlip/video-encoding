#!/usr/bin/env python

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from shutil import copyfile
from selfcaffeinate import SelfCaffeinate


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workdir", help="Directory containing video files to encode.")
    parser.add_argument(
        "--outdir", help="Directory to write encoded files to.")
    parser.add_argument(
        "--decomb", help="Optionally have Handbrake decomb video.", action="store_true")
    parser.add_argument(
        "--no-sleep", help="Prevent macOS from sleeping while encoding.", action="store_true")
    args = parser.parse_args(argv)
    return args


class BatchEncoder(object):
    QUEUE_FILE = "queue.txt"

    def __init__(self, workdir, outdir, decomb=False):
        self.decomb = decomb
        self.workdir = workdir
        self.queue_file = "%s/%s" % (self.workdir, self.QUEUE_FILE)
        self.outdir = outdir
        self.tempdir = tempfile.mkdtemp()
        self._sanity_check_dirs()
        self._backup_queue_file()
        self._process_queue_file()

    def wait(self):
        print("Running all encoders.")
        for encoder, line in self.encoders:
            encoder.run()
            encoder.wait()
            self._delete_line_from_queue(line)

    def _sanity_check_dirs(self):
        if not os.path.isdir(self.workdir):
            raise Exception("Working directory not found: %s" % self.workdir)

        if not os.path.isdir(self.outdir):
            raise Exception("Output directory not found: %s" % self.outdir)

        if not os.path.exists("%s" % self.queue_file):
            raise Exception("Can't find queue file: %s" % self.queue_file)

    def _process_queue_file(self):
        self.encoders = []
        linecount = 0
        for line in open(self.queue_file).readlines():
            linecount += 1
            line = line.rstrip()
            parts = line.split(',', 1)
            # handle empty or malformed line
            if not len(parts) == 2:
                print("Skipping line %d: %s" % (linecount, line))
                continue
            (input_file, output_title) = parts
            encoder = SingleEncoder(
                self.workdir, self.tempdir, self.outdir, input_file, output_title, decomb=self.decomb)
            self.encoders.append((encoder, line))

    def _backup_queue_file(self):
        queue_file_backup = "%s.orig" % self.queue_file
        copyfile(self.queue_file, queue_file_backup)

    def _delete_line_from_queue(self, line):
        output = []
        for queue_line in open(self.queue_file, "rb"):
            if line != queue_line.rstrip():
                output.append(queue_line)

        queue_out = open(self.queue_file, "wb")
        for outline in output:
            queue_out.write(outline)
        queue_out.close()


class SingleEncoder(object):
    TRANSCODE = "transcode-video"

    def __init__(self, workdir, tempdir, outdir, input_file, output_title, decomb=False):
        self.decomb = decomb
        self.tempdir = tempdir
        self.outdir = outdir
        self.input_file = input_file
        self.input_file_basename = os.path.basename(self.input_file)
        # self.fq_input_file="%s/%s" % (workdir,input_file)
        self.crops_dir = "%s/%s" % (workdir, "Crops")
        self.subtitles_dir = "%s/%s" % (workdir, "subtitles")
        self.output_title = output_title
        self.outlog = "%s.log" % self.input_file
        self.fq_temp_file = "%s/%s.m4v" % (self.tempdir, self.output_title)
        self.fq_output_file = "%s/%s.m4v" % (self.outdir, self.output_title)
        self._sanity_check_dirs()
        self.command = self._build_command()

    def run(self):
        print("Running:")
        print(self.command)
        self.outlog_file = open(self.outlog, "wb", 0)
        self.process = subprocess.Popen(
            self.command, stdout=self.outlog_file, stderr=self.outlog_file, bufsize=0)

    def _wait(self):
        print("Waiting for encode job of %s to complete." % self.input_file)
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

        subtitle_glob = "%s/%s.*.srt" % (self.subtitles_dir,
                                         os.path.splitext(self.input_file_basename)[0])

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
            print(e)
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
    args = parse_args(sys.argv[1:])

    decomb = args.decomb
    workdir = args.workdir
    outdir = args.outdir
    if args.no_sleep:
        sc = SelfCaffeinate()
    else:
        sc = None

    print("Creating batch encoder.")
    encoder = BatchEncoder(workdir, outdir, decomb=decomb)
    print("Waiting for encoder to finish.")
    encoder.wait()
    print("Batch encoder done.")
    if sc:
        sc = None


if __name__ == '__main__':
    main()
