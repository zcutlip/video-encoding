import datetime
import glob
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from ..command import TranscodeVideoCommand
from ..encode_report import Encoded, EncodeReport
from ..exceptions import (
    EncodingOptionNotSupportedException,
    MalformedJobException
)
from ..video_stream_info import VideoStreamInfo


class SingleEncoderBase:
    # Argument to '--crop' to trigger autodetection
    CROP_AUTO_ARG = None
    SUBTITLE_AUTO_ARG = "scan"
    ENCODER_VERBOSE_ARG = None
    REDIRECT_STDERR = False
    UNSUPPORTED_OPTIONS = []

    def __init__(self, tempdir, job_config: Dict, logger=None, dry_run=False, skip_encode=False, debug=False):
        if not logger:
            logger = logging.getLogger("single-encoder")
        self.logger = logger
        self.logger.debug("Debug logging enabled")
        self.debug = debug
        self.encoding_complete: bool = False
        self._total_start: datetime.datetime = None
        self._total_stop: datetime.datetime = None
        self._encoding_start: datetime.datetime = None
        self._encoding_stop: datetime.datetime = None
        self._archive_start: datetime.datetime = None
        self._archive_stop: datetime.datetime = None
        self._encoded: Encoded = None

        option: str
        bad_options = []
        for option in self.UNSUPPORTED_OPTIONS:
            if job_config[option]:
                bad_opt = option.replace("_", "-")
                bad_opt = f"--{bad_opt}"
                bad_options.append(bad_opt)

        if bad_options:
            msg = f"Unsupported options for {self.__class__.__name__}: {bad_options}"
            raise EncodingOptionNotSupportedException(msg)

        self.dry_run = dry_run
        self.skip_encode = skip_encode
        self.tempdir = tempdir
        self.job_config = job_config
        self.movie = job_config["movie"]
        self.outdir = job_config["outdir"]
        self.output_title = job_config["output_title"]
        self.input_file = job_config["input_file"]
        self.workdir = job_config["workdir"]
        self.quality = job_config["quality"]
        self.archive_root = job_config["archive_root"]
        self.media_root = job_config["media_root"]
        self.crop_params = job_config["crop_params"]
        self.decomb = job_config["decomb"]
        self.disable_auto_burn = job_config["disable_auto_burn"]
        self.burn_subtitle_num = job_config["burn_subtitle_num"]
        self.add_subtitle = job_config["add_subtitle"]
        self.m4v = job_config["m4v"]
        self.chapter_spec = job_config["chapters"]
        self.no_10_bit = job_config["no_10_bit"]
        self.resize_1080p = job_config["resize_1080p"]

        # if additional resources need to be copied to the destination,
        # populate this list with [(fq_src_1, fq_dest_1), (fq_src_2, fq_dest_2), ...]
        self.resources_to_copy: List[Tuple[str, str]] = []

        # Put movies in a title-based folder
        # to support storing mutliple versions and other assets
        # e.g.,
        # /Movies
        #     /Pulp Fiction (1994)
        #         Pulp Fiction (1994) - 1080p.mkv
        #         Pulp Fiction (1994) - SD.m4v
        # https://support.plex.tv/articles/200381043-multi-version-movies/
        if self.movie:
            self.outdir = Path(self.outdir, self.output_title)

        self.input_file_basename = os.path.basename(self.input_file)
        self.fq_input_file = Path(self.workdir, self.input_file_basename)

        self.video_stream_info = VideoStreamInfo(self.fq_input_file)

        self.subtitles_dir = Path(self.workdir, "subtitles")
        self._report = EncodeReport()
        outlog = "%s-output.log" % self.input_file_basename
        self.outlog = Path(self.workdir, outlog)

        # construct The Matrix Resurrections (2021) - 1080p.mv4
        # from "The Matrix Resurrections (2021)" and "1080p"
        outfile = self._construct_outfile_basename(
            self.output_title, self.quality, self.movie, self.m4v)
        self.job_json_name = f"{outfile}-config.json"
        fq_output_file = Path(self.outdir, outfile)
        self.fq_output_file = fq_output_file
        self.output_file_base = outfile

        encoder_log = f"{outfile}.log"
        self.encoder_log = Path(self.tempdir, encoder_log)

        temp_file = Path(self.tempdir, outfile)
        self.fq_temp_file = temp_file

        self.archive_complete = False
        self.archive_dir = None
        if self.archive_root and self.media_root:
            self.archive_dir = self._construct_archive_dst(
                self.archive_root, self.media_root, fq_output_file)
            # save job JSON to archive path
            self.job_json_name = Path(self.archive_dir, self.job_json_name)

        self._sanity_check_dirs()
        self._sanity_check_params()
        self.command: TranscodeVideoCommand = self._build_command()
        self.job_config["command"] = str(self.command)

    @property
    def report(self):
        return self._report

    def needs_archive(self):
        needs_archive = (
            self.archive_dir is not None and
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

    def needs_copy(self):
        return self.needs_encode()

    def do_archive(self):
        if self.needs_archive():
            self._archive_start = datetime.datetime.now()
            self.logger.info(
                f"Archiving {os.path.basename(self.fq_input_file)}")
            self.logger.debug(f"...to {self.archive_dir}/")
            if not self.dry_run:
                self.archive_dir.mkdir(parents=True, exist_ok=True)
                # TODO: archive crop file and subtitle file if they're available
                shutil.copy2(self.fq_input_file, self.archive_dir)
                shutil.copy2(self.encoder_log, self.archive_dir)
                for resource, _ in self.resources_to_copy:
                    shutil.copy2(resource, self.archive_dir)
                json.dump(self.job_config, open(
                    self.job_json_name, "w"), indent=2)
            self._archive_stop = datetime.datetime.now()
            self.archive_complete = True

    def copy_to_dest(self):
        tmpfile = self.fq_temp_file
        self.logger.info(
            f"Moving encoded file to {self.fq_output_file}")
        shutil.copy2(tmpfile, self.fq_output_file)
        for src, dst in self.resources_to_copy:
            self.logger.info(f"Copying resource '{src}' to '{dst}'")
            shutil.copy2(src, dst)

        tmpfile.unlink()

    def run(self):
        start = datetime.datetime.now()
        self._total_start = start
        if self.needs_encode():
            self.logger.info("Running:")
            self.logger.info(f"{self.command}")
            outlog_fh = open(self.outlog, "wb", 0)
            stderr = subprocess.PIPE
            if self.REDIRECT_STDERR:
                stderr = subprocess.STDOUT
            self._encoding_start = start
            self.process = subprocess.Popen(
                self.command, stdout=outlog_fh, stderr=stderr, bufsize=0
            )

    def wait(self):
        status = self._wait()
        if self.needs_copy():
            err_text = None
            if status == 0:
                self.copy_to_dest()
            else:
                err_text = self._err_out()

            self._total_stop = datetime.datetime.now()

            delta = self._total_stop - self._total_start
            total_sec = delta.seconds
            encoding_sec = 0
            if self.needs_encode():
                delta = self._encoding_stop - self._encoding_start
                encoding_sec = delta.seconds
            encoded = Encoded(self.input_file_basename,
                              self.fq_output_file,
                              (status == 0),
                              err_text=err_text,
                              total_seconds=total_sec,
                              encoding_seconds=encoding_sec)
            self._encoded = encoded
            self._report.add_encoded(encoded)
        else:
            self._total_stop = datetime.datetime.now()

        self.logger.info("Done.")
        if status == 0:
            self.encoding_complete = True
        return status

    def _wait(self):
        if self.needs_encode():
            self.logger.info(
                f"Waiting for '{os.path.basename(self.fq_input_file)}' to complete.")
            self.process.wait()
            self._encoding_stop = datetime.datetime.now()
            status = self.process.returncode
        else:
            status = 0
        return status

    def _err_out(self):
        _, err_out = self.process.communicate()
        # utf-8 decoding is default if not specified
        err_out = err_out.decode()
        return err_out

    def _construct_outfile_basename(self, title, quality, movie, m4v):
        outfile_base = title
        if movie and quality:
            outfile_base = f"{outfile_base} - {quality}"
        ext = "m4v" if m4v else "mkv"
        outfile_base = f"{outfile_base}.{ext}"
        return outfile_base

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

    def _get_debug_option(self):
        debug_arg = ""
        if self.debug:
            debug_arg = f"--{self.ENCODER_VERBOSE_ARG}"
        return debug_arg

    def _get_crop_option(self):
        """build option list for cropping video."""
        if self.crop_params:
            crop_opt = ["--crop", self.crop_params]
        else:
            crop_opt = ["--crop", self.CROP_AUTO_ARG]

        return crop_opt

    def _sanity_check_dirs(self):
        if not os.path.exists(self.fq_input_file):
            msg = f"Input file not found: {self.fq_input_file}"
            self.logger.error(msg)
            raise MalformedJobException(msg)

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

        if not os.path.isdir(self.tempdir):
            msg = "Temp directory not found: %s" % self.tempdir
            self.logger.error(msg)
            raise Exception(msg)

    def _sanity_check_params(self):
        if not self.output_title:
            raise MalformedJobException(
                f"No output title for {self.fq_input_file}")

    def _build_command(self):
        raise NotImplementedError(
            "_build_command() must be implemented in a subclass")

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

    def _find_srt_files(self, sub_dir: str, srt_base: str) -> List[str]:
        srt_glob = f"{sub_dir}/{srt_base}.*.srt"
        matches = glob.glob(srt_glob)
        return matches

    def _get_sub_option(self):
        """
        Build option list for burning subtitles.
        Eventually this will be configurable at run-time and may return None.
        """
        raise NotImplementedError(
            "Must override _get_sub_option() for specific transcoding engine")

    def _get_decomb_option(self):
        raise NotImplementedError(
            f"Decombing not implemented for {self.__class__.__name__}")
