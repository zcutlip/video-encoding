import argparse
import os
from pathlib import Path
from pprint import pprint

from scruffy.config import ConfigFile, ConfigNode
from scruffy.file import Directory, File, PackageDirectory


class BatchEncoderParsedArgs(argparse.ArgumentParser):
    def __init__(self, exit_on_error=True, **kwargs):
        super(BatchEncoderParsedArgs, self).__init__(**kwargs)
        self.exit_on_error = exit_on_error
        self.add_argument("--config", help="Path to config file.")
        self.add_argument(
            "--workdir", help="Directory containing video files to encode."
        )
        self.add_argument("--outdir", help="Directory to write encoded files to.")
        self.add_argument(
            "--decomb",
            help="Optionally have Handbrake decomb video.",
            action="store_true",
            default=None,
        )
        self.add_argument(
            "--no-sleep",
            help="Prevent macOS from sleeping while encoding.",
            action="store_true",
            default=None,
        )

    def parse_args(self, args=None):
        parsed_args = None
        try:
            parsed_args = super(BatchEncoderParsedArgs, self).parse_args(args)
            # TODO: later if we need two discrete argument dictionaries,
            # look at grumpy _regsiter_parsed_args()
        except SystemExit as se:
            if self.exit_on_error:
                raise se
            else:
                pass

        return parsed_args


class BatchEncoderConfig:
    DEFAULT_CONFIG_DIR = "~/.config/batchencoder"
    DEFAULT_CONFIG_FILE = "batchencoder.yaml"

    def __init__(
        self, args, exit_on_error=True, parsed_args_cls=BatchEncoderParsedArgs
    ):
        self.config_dir = self.DEFAULT_CONFIG_DIR
        self.config_file = self.DEFAULT_CONFIG_FILE

        argparser = parsed_args_cls(exit_on_error=exit_on_error)
        parsed_args = argparser.parse_args(args)
        if parsed_args.config:
            config_path = Path(parsed_args.config)
            config_path = config_path.expanduser()
            config_path = config_path.absolute()

            self.config_dir = os.path.dirname(config_path)
            self.config_file = os.path.basename(config_path)

        self._dir = Directory(
            path=self.config_dir,
            # TODO: Later, turn on create=True
            create=False,
            config=ConfigFile(
                self.config_file,
                defaults=File("./default.json", parent=PackageDirectory()),
            ),
        )
        self._dir.prepare()

        self.config = self._dir.config
        self.config.load()
        if parsed_args:
            self._update_config(vars(parsed_args))
        if self.config.pprint_config:
            print("Configuration dictionary:")

            pprint(self.config.to_dict(), width=1)

    def __getattr__(self, attr):
        _value = None
        if hasattr(self.config, attr):
            _value = getattr(self.config, attr)
        else:
            raise AttributeError(
                "%r has no attribute %r" % (self.__class__.__name__, attr)
            )
        if isinstance(_value, ConfigNode):
            _value = _value._get_value()
        return _value

    def _prune_dict(self, old_thing, prune_val):
        pruned = None
        if isinstance(old_thing, dict):
            pruned = {
                k: self._prune_dict(v, prune_val)
                for k, v in old_thing.items()
                if v != prune_val
            }
        else:
            # Since we recursively call ourselves for all nested dictionaries
            # we need to handle the eventual case when we're passed in a thing
            # that isn't a dictionary
            pruned = old_thing
        return pruned

    def _update_config(self, args_dict):
        pruned_args = self._prune_dict(args_dict, None)
        self.config.update(pruned_args)
