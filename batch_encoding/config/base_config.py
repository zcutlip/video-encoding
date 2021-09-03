
import argparse
import copy
import json
from pathlib import Path
from pprint import pprint
from typing import Dict, List

from .default import BatchEncoderDefaultConfig


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


class ConfigFromParsedArgs(dict):
    DEFAULT_CONFIG_PATH = None
    ARG_PARSE_FN = None
    SUB_DICT_KEYS = []

    def __init__(self):
        super().__init__()

        if not self.ARG_PARSE_FN:
            raise NotImplementedError("Must override ARG_PARSE_FN")
        if not self.DEFAULT_CONFIG_PATH:
            raise NotImplementedError("Must override DEFAULT_CONFIG_PATH")

        parsed_args = self.ARG_PARSE_FN()
        config = self.load_config(parsed_args, self.SUB_DICT_KEYS)
        self.update(config)

        if self["pprint_config"]:
            print("Configuration dictionary:")
            pprint(self, width=1)

    def _update_config(self, orig: Dict, new: Dict, sub_dict_keys: List[str]):
        updated_copy = copy.deepcopy(orig)
        if isinstance(orig, dict):
            for k, v in new.items():
                if k in sub_dict_keys:
                    orig_v = orig.get(k, {})
                    v = self._update_config(orig_v, v, [])
                    updated_copy[k] = v
                elif k not in orig or orig[k] != v:
                    updated_copy[k] = v
        return updated_copy

    def load_config(self, parsed_args, sub_dict_keys):
        config = BatchEncoderDefaultConfig()

        try:
            user_config = json.load(
                open(Path(self.DEFAULT_CONFIG_PATH), "r"))
        except FileNotFoundError:
            user_config = {}

        config = self._update_config(config, user_config, sub_dict_keys)

        # turn parsed args into a dict, leaving out any None values or empty strings
        parsed_args_dict = self._prune_dict(vars(parsed_args), [None, ""])

        config = self.update_from_parsed_args(
            config, parsed_args_dict, sub_dict_keys)
        return config

    def update_from_parsed_args(self, config, parsed_args_dict, sub_dict_keys):
        config_file = parsed_args_dict.pop("config_file")
        provided_config = json.load(open(config_file, "r"))
        encoding_config = self._update_config(
            config["encoding_config"], provided_config, [])
        config["encoding_config"] = encoding_config

        for subkey in sub_dict_keys:
            # argparse gives you a flat namespace, so we need to
            # idenitfy those args which are part of a subdict, and pull them
            # from the namespace and add them to their own dictionary
            # before updating the config
            parsed_args_subkey_options = {
                k: v for k, v in parsed_args_dict.items() if k in config[subkey]
            }
            parsed_args_options = {
                k: v for k, v in parsed_args_dict.items() if k not in config[subkey]
            }
            parsed_args_options[subkey] = parsed_args_subkey_options
            config = self._update_config(
                config, parsed_args_options, [parsed_args_subkey_options])
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
