import json

from ..pkg_resources import pkgfiles


class BatchEncoderDefaultConfig(dict):
    DEFAULT_JSON = "default.json"

    def __init__(self):
        super().__init__()
        defaults = self._load_defaults()
        self.update(defaults)

    def _load_defaults(self):
        with pkgfiles(__package__).joinpath(self.DEFAULT_JSON).open("r") as _file:
            loaded = json.load(_file)
        return loaded

    @property
    def encoding_config(self):
        return self["encoding_config"]
