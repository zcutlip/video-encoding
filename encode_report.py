import logging
import smtplib
from datetime import datetime
from email import message
from pathlib import Path


class EncodeReport:
    EMAIL_FROM = "encoder@ascendency.org"

    def __init__(self, logger=None):
        if not logger:
            logger = logging.getLogger("encoding-report")
        self.encoded = []
        self.encoding_failures = []
        self.date_str = None

    def update_report(self, report):
        self.encoded.extend(report.encoded)
        self.encoding_failures.extend(report.encoding_failures)

    def add_encoded(self, src_path, dest_path):
        self.encoded.append((src_path, dest_path))

    def add_encoding_failure(self, src_path, err_text):
        self.encoding_failures.append((src_path, err_text))

    def report(self) -> str:
        report_lines = ["Video Encoding Report", ""]
        if self.date_str is None:
            self.date_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        date_str = self.date_str

        date_text = f"Date: {date_str}"
        report_lines.extend(self._new_header(date_text))

        if self.encoded:
            report_lines.extend(self._new_header("Encoded files"))
            # self.encoded is a list of (src, dst) tuples
            for _, dst in self.encoded:
                report_lines.append(dst)
            report_lines.append("")

        if self.encoding_failures:
            report_lines.extend(self._new_header("Encoding failures"))
            for src, err_text in self.encoding_failures:
                report_lines.extend(self._new_header(src))
                report_lines.append(err_text)
                report_lines.append("")

        report_str = "\n".join(report_lines)
        return report_str

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
