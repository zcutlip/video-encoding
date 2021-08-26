import argparse
import copy
import json
from pathlib import Path
# import os
# from pathlib import Path
from pprint import pprint
from typing import Dict, List

from .. import config as config_pkg
from ..pkg_resources import pkgfiles


def base_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--workdir", help="directory containing video files to encode"
    )

    parser.add_argument(
        "--decomb",
        help="optionally have Handbrake decomb video",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "--no-sleep",
        help="prevent macOS from sleeping while encoding",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "--disable-auto-burn",
        help="don't automatically burn first forced subtitle",
        action="store_true",
        default=None
    )
    parser.add_argument(
        "--add-subtitle", help="add track selected with language code (e.g., 'eng')"
    )
    return parser


def batch_encode_parse_args():
    parser = base_parser()
    parser.add_argument("config_file", help="name of config file to load")
    parser.add_argument(
        "--report-path", help="write encoding report to the specified path"
    )
    parser.add_argument(
        "--report-email", help="email report to the specified email address"
    )
    parsed = parser.parse_args()
    return parsed


def make_config_parse_args():
    parser = base_parser()
    parser.add_argument("config_file", help="name of config file to write")
    parser.add_argument(
        "video_list",
        help="Text file containing a line-by-line list of videos to encode or file glob to match a list of .mkv files",
    )
    parser.add_argument(
        "outdir", help="Output directory where encoded videos should be written"
    )
    parsed = parser.parse_args()
    return parsed


class BatchEncoderConfig:
    DEFAULT_CONFIG_DIR = "~/.config/batchencoder"
    DEFAULT_CONFIG_FILE = "batchencoder.json"

    def __init__(self):
        self.config_dir = self.DEFAULT_CONFIG_DIR
        self.config_file = self.DEFAULT_CONFIG_FILE

        parsed_args = batch_encode_parse_args()
        config = self._load_config(parsed_args)
        self._config = config

        # Load config file from home config dir if it exists
        # using package defaults.json as source of defaults
        # config = ConfigFile(
        #     self.config_file,
        #     parent=Directory(self.config_dir),
        #     defaults=File("default.json", parent=PackageDirectory())
        # )
        # config.prepare()

        # if parsed_args.config:
        #     config_path = Path(parsed_args.config)
        #     config_path = config_path.expanduser()
        #     config_path = config_path.absolute()

        #     self.config_dir = os.path.dirname(config_path)
        #     self.config_file = os.path.basename(config_path)
        #     # if we were passed a config file, that should override any config optoins
        #     # in home config dir as well as package defaults. So load that config,
        #     # using the previous config as source of defaults
        #     provided_config = ConfigFile(
        #         self.config_file,
        #         parent=Directory(self.config_dir)
        #     )
        #     provided_config.prepare()

        #     config.update(provided_config)

        # self._dir = Directory(
        #     path=self.config_dir,
        #     # TODO: Later, turn on create=True
        #     create=False,
        #     config=config,
        # )

        # self._dir.prepare()

        # self.config = self._dir.config
        # self.config.load()
        # if parsed_args:
        #     self._update_config(vars(parsed_args))
        if self.config["pprint_config"]:
            print("Configuration dictionary:")

            pprint(self.config, width=1)

    @property
    def config(self):
        return self._config

    @property
    def encoding_config(self):
        return self.config["encoding_config"]

    def _update_config(self, orig: Dict, new: Dict, dict_keys: List[str]):
        updated_copy = copy.deepcopy(orig)
        if isinstance(orig, dict):
            for k, v in new.items():
                if k in dict_keys:
                    orig_v = orig.get(k, {})
                    v = self._update_config(orig_v, v, [])
                    updated_copy[k] = v
                elif k not in orig or orig[k] != v:
                    updated_copy[k] = v
        return updated_copy

    def _load_config(self, parsed_args):
        with pkgfiles(config_pkg).joinpath("default.json").open("r") as _file:
            config = json.load(_file)

        try:
            user_config = json.load(
                open(Path(self.DEFAULT_CONFIG_DIR, self.DEFAULT_CONFIG_FILE), "r"))
        except FileNotFoundError:
            user_config = {}

        config = self._update_config(config, user_config, ["encoding_config"])

        # turn parsed args into a dict, leaving out any None values or empty strings
        parsed_args_dict = self._prune_dict(vars(parsed_args), [None, ""])

        config_file = parsed_args_dict.pop("config_file")
        provided_config = json.load(open(config_file, "r"))
        encoding_config = self._update_config(
            config["encoding_config"], provided_config, [])
        config["encoding_config"] = encoding_config

        parsed_args_encoding_options = {
            k: v for k, v in parsed_args_dict.items() if k in config["encoding_config"]
        }
        parsed_args_options = {
            k: v for k, v in parsed_args_dict.items() if k not in config["encoding_config"]
        }
        parsed_args_options["encoding_config"] = parsed_args_encoding_options
        config = self._update_config(
            config, parsed_args_options, ["encoding_config"])
        return config

    def _prune_dict(self, old_thing, prune_vals: List):
        pruned = None
        if isinstance(old_thing, dict):
            pruned = {
                k: self._prune_dict(v, prune_vals)
                for k, v in old_thing.items()
                if v not in prune_vals
            }
        else:
            # Since we recursively call ourselves for all nested dictionaries
            # we need to handle the eventual case when we're passed in a thing
            # that isn't a dictionary
            pruned = old_thing
        return pruned

    def _update_config_old(self, args_dict):
        pruned_args = self._prune_dict(args_dict, None)
        self.config.update(pruned_args)
