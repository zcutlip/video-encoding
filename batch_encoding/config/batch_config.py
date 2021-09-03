import json
from pathlib import Path

from .base_config import ConfigFromParsedArgs, base_parser


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


class BatchEncoderConfig(ConfigFromParsedArgs):
    ARG_PARSE_FN = batch_encode_parse_args
    DEFAULT_CONFIG_PATH = Path("~/.config/batchencoder/batchencoder.json")
    SUB_DICT_KEYS = ["encoding_config"]

    def update_from_parsed_args(self, config, parsed_args_dict, sub_dict_keys):
        config_file = parsed_args_dict.pop("config_file")
        provided_config = json.load(open(config_file, "r"))
        encoding_config = self._update_config(
            config["encoding_config"], provided_config, [])
        config["encoding_config"] = encoding_config

        super().update_from_parsed_args(config, parsed_args_dict, sub_dict_keys)
