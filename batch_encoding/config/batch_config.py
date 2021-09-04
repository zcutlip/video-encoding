import argparse
import copy
import json
from pathlib import Path
from pprint import pprint
from typing import Dict, List

from .default import BatchEncoderDefaultConfig
from .encoding_config import EncodingConfig


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config_file", help="name of encoding config file to load or create")
    parser.add_argument(
        "--video-list",
        help="Text file containing a line-by-line list or file glob to match a list of input files",
    )
    parser.add_argument(
        "--outdir", help="Output directory where encoded videos should be written"
    )

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
    parser.add_argument(
        "--report-path", help="write encoding report to the specified path"
    )
    parser.add_argument(
        "--report-email", help="email report to the specified email address"
    )
    parsed = parser.parse_args()
    return parsed


class ConfigFromParsedArgs(BatchEncoderDefaultConfig):
    DEFAULT_CONFIG_PATH = Path("~/.config/batchencoder/batchencoder.json")
    ENCODING_CONFIG_KEY = "encoding_config"

    def __init__(self):
        super().__init__()

        parsed_args = parse_args()
        config = self.load_config(parsed_args)
        self.update(config)

        if self["pprint_config"]:
            print("Configuration dictionary:")
            pprint(self, width=1)

    def load_config(self, parsed_args):
        # No need to load default config because it's our base class. we already loaded it
        # config = BatchEncoderDefaultConfig()
        # Load a user config if exists, else emtpy dict
        try:
            user_config = json.load(
                open(Path(self.DEFAULT_CONFIG_PATH), "r"))
        except FileNotFoundError:
            user_config = {}

        # update config with user-overrides
        config = self._update_config(
            self, user_config, self.ENCODING_CONFIG_KEY)

        # turn parsed args into a dict, leaving out any None values or empty strings
        parsed_args_dict = self._prune_dict(vars(parsed_args), [None, ""])

        # update override user config & defaults with command-line args
        config = self.update_from_parsed_args(config, parsed_args_dict)

        return config

    def update_from_parsed_args(self, config, parsed_args_dict):
        encoding_conf_k = self.ENCODING_CONFIG_KEY

        # Get the filename of the provided encoding config file
        # remove "config_file" from args, because we don't actually set
        # it as a key in the overall config dict
        encoding_config_file = parsed_args_dict.pop("config_file")

        base_encoding_config = config.encoding_config
        if not base_encoding_config["workdir"]:
            base_encoding_config["workdir"] = parsed_args_dict.get("workdir")

        try:
            video_input_str = parsed_args_dict.pop("video_list")
        except KeyError:
            video_input_str = ""

        # load an encoding config, or create one if it doesn't exist
        provided_encoding_config = EncodingConfig(
            base_encoding_config, encoding_config_file, video_input_str=video_input_str)

        # Replace the skeleton encoding config from the main config
        # with the provided encoding config
        config.encoding_config = provided_encoding_config

        # Get set of keys in encoding config for use when unflatting parsed aregs
        config_sub_keys = config.encoding_config.keys()

        # unflatten parsed args into a dictionary with same structure
        # as our overall config, including encoding_config subdict
        parsed_args_options = self._unflatten_parsed_args_dict(
            parsed_args_dict, encoding_conf_k, config_sub_keys)

        # update our overall config with overrides from command line options
        config = self._update_config(
            config, parsed_args_options, subkey=encoding_conf_k)

        return config

    def _update_config(self, orig: Dict, new: Dict, subkey=None):
        updated_copy = copy.deepcopy(orig)
        if isinstance(orig, dict):
            for k, v in new.items():
                if k == subkey:
                    orig_v = orig.get(k, {})
                    v = self._update_config(orig_v, v)
                    updated_copy[k] = v
                elif k not in orig or orig[k] != v:
                    updated_copy[k] = v
        return updated_copy

    def _generate_new_encoding_config(self, config_file):
        pass

    def _unflatten_parsed_args_dict(self, parsed_args_dict, encoding_conf_k, config_sub_keys):
        # argparse gives you a flat namespace, so we need to
        # idenitfy those args which are part of a subdict, and pull them
        # from the namespace and add them to their own dictionary
        # before updating the config
        parsed_args_subkey_options = {
            k: v for k, v in parsed_args_dict.items() if k in config_sub_keys
        }
        parsed_args_options = {
            k: v for k, v in parsed_args_dict.items() if k not in config_sub_keys
        }
        parsed_args_options[encoding_conf_k] = parsed_args_subkey_options
        return parsed_args_options

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
