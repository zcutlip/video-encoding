import logging
import smtplib
from datetime import datetime, timedelta
from email import message
from pathlib import Path
from typing import List

from . import VideoEncodingAbout


class EncodedValueError(ValueError):
    pass


class Encoded:
    def __init__(self,
                 src_path: str,
                 dest_path: str,
                 success: str,
                 err_text: str = None,
                 total_seconds: int = 0,
                 encoding_seconds: int = 0,
                 archiving_seconds: int = None):
        self.src_path = src_path
        self.dest_path = dest_path
        self.success = success
        self.err_text = err_text
        self._total_elapsed = self._divmod_seconds(total_seconds)
        self._encoding_elapsed = self._divmod_seconds(encoding_seconds)
        if archiving_seconds is not None:
            self._archiving_elapsed = self._divmod_seconds(archiving_seconds)
        else:
            self._archiving_elapsed = None

    def _divmod_seconds(self, seconds):
        if seconds < 0:
            raise EncodedValueError(f"Invalid number of seconds: {seconds}")

        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return hours, minutes, seconds

    def _hr_min_sec_str(self, hours, minutes, seconds):
        _str = ""
        if hours:
            _str += f"{hours:02d}:"
        _str += f"{minutes:02d}:{seconds:02d}"
        return _str

    @property
    def total_elapsed(self) -> str:
        total_str = self._hr_min_sec_str(*self._total_elapsed)
        return total_str

    @property
    def encoding_elapsed(self):
        encoding_str = self._hr_min_sec_str(*self._encoding_elapsed)
        return encoding_str

    @property
    def archiving_elapsed(self):
        archiving_str = None
        if self._archiving_elapsed is not None:
            archiving_str = self._hr_min_sec_str(*self._archiving_elapsed)

        return archiving_str

    def add_archiving_elapsed(self, archiving_seconds):
        archving_elapsed = self._divmod_seconds(archiving_seconds)
        self._archiving_elapsed = archving_elapsed


class EncodeReport:
    EMAIL_FROM = "encoder@ascendency.org"

    def __init__(self, logger=None):
        if not logger:
            logger = logging.getLogger("encoding-report")
        self.logger = logger
        self.encoded: List[Encoded] = []
        self.encoding_failures: List[Encoded] = []
        self.date_str = None
        self._start_time = datetime.now()
        self._end_time = None

    def finish(self):
        self._end_time = datetime.now()

    def update_report(self, report):
        self.encoded.extend(report.encoded)
        self.encoding_failures.extend(report.encoding_failures)

    def add_encoded(self, encoded: Encoded):
        if encoded.success:
            self.encoded.append(encoded)
        else:
            self.encoding_failures.append(encoded)

    def report(self) -> str:
        report_lines = ["Video Encoding Report", ""]
        if self.date_str is None:
            self.date_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        date_str = self.date_str

        version_text = f"Version: {VideoEncodingAbout()}"
        report_lines.extend(self._new_header(version_text))

        date_text = f"Date: {date_str}"
        report_lines.extend(self._new_header(date_text))

        if self.encoded:
            report_lines.extend(self._new_header("Encoded files"))
            # self.encoded is a list of (src, dst) tuples

            for encoded in self.encoded:
                dst = encoded.dest_path
                encoding_time = encoded.encoding_elapsed
                line = f"{dst} [{encoding_time}]"
                report_lines.append(line)
            report_lines.append("")

        if self.encoding_failures:
            report_lines.extend(self._new_header("Encoding failures"))
            for encoded in self.encoding_failures:
                src = encoded.src_path
                err_text = encoded.err_text
                total_elapsed = encoded.total_elapsed
                report_lines.extend(self._new_header(src))
                report_lines.append(err_text)
                report_lines.append(f"Total elapsed: {total_elapsed}")
                report_lines.append("")

        report_lines.extend(self._new_header("Total time"))
        elapsed = self._elapsed_seconds()
        report_lines.append(str(elapsed))

        report_str = "\n".join(report_lines)
        return report_str

    def _elapsed_seconds(self):
        if self._end_time is None:
            self._end_time = datetime.now()
        elapsed = self._end_time - self._start_time
        elapsed = timedelta(seconds=elapsed.seconds)
        return elapsed

    def write_report(self, report_path):
        p = Path(report_path)
        p = p.expanduser()
        p = p.resolve()

        report_text = self.report()
        date_str = self.date_str
        if not p.exists():
            p.mkdir(parents=True)
        if p.is_dir():
            report_fname = f"video-batch-encoding-report ({date_str}).txt"
            full_path = Path(p, report_fname)
        else:
            full_path = p
        with open(full_path, "w") as f:
            f.write(report_text)

    def email_report(self, to_address):
        message = self._email_message(to_address)
        try:
            sender = smtplib.SMTP("localhost")
            sender.send_message(message)
        except ConnectionRefusedError as e:
            self.logger.error(f"Unable to remail report: {e}")

    def _email_message(self, to_address):
        report_text = self.report()
        m = message.EmailMessage()
        m["To"] = to_address
        m["From"] = self.EMAIL_FROM
        subject_text = "Video Encoding Report"
        m["Subject"] = subject_text
        m.set_content(report_text)
        return m

    def _new_header(self, header_text):
        lines = [header_text]
        text = "-" * len(header_text)
        lines.append(text)
        lines.append("")
        return lines
