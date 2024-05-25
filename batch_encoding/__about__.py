__title__ = "Batch Video Encoding"
__version__ = "1.5.1"
__summary__ = "A harness for betch-encoding DVD & Blu-Ray rips"


class VideoEncodingAbout:
    def __init__(self) -> None:
        self.version = __version__
        self.summary = __summary__
        self.title = __title__

    def __str__(self):
        return f"{self.title.upper()}: {self.summary}. Version {self.version}"


"""
See PEP 440 for version scheme
https://www.python.org/dev/peps/pep-0440/#examples-of-compliant-version-schemes
Examples:

FINAL
0.9
0.9.1
0.9.2
...
0.9.10
0.9.11
1.0
1.0.1
1.1
2.0
2.0.1
...

PRE_RELEASES

X.YaN   # Alpha release
X.YbN   # Beta release
X.YrcN  # Release Candidate
X.Y     # Final release
"""
