import json

from .. import data
from ..pkg_resources import pkgfiles


class BatchEncoderDefaultConfig(dict):
    DEFAULT_JSON = "default.json"

    def __init__(self):
        super().__init__()
        defaults = self._load_defaults()
        self.update(defaults)

    def _load_defaults(self):
        with pkgfiles(data).joinpath(self.DEFAULT_JSON).open("r") as _file:
            loaded = json.load(_file)
        return loaded

    @property
    def encoding_config(self):
        return self["encoding_config"]

    @encoding_config.setter
    def encoding_config(self, encoding_config):
        self["encoding_config"] = encoding_config
