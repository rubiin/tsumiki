from fabric.utils import get_relative_path, logger, os

from utils.singleton import SingletonMixin
from utils.validation import (
    validate_config_enums,
    validate_widgets,
)

from .constants import APPLICATION_NAME, DEFAULT_CONFIG
from .functions import (
    deep_merge,
    read_toml_file,
)
from .widget_settings import BarConfig

# Pre-computed excluded keys for config merging
_EXCLUDED_SCHEMA_KEYS = frozenset(["$schema"])
_LIST_CONFIG_KEYS = frozenset(["widget_groups", "collapsible_groups"])


class TsumikiConfig(SingletonMixin):
    "A class to read the configuration file and return the default configuration"

    __slots__ = (
        "config",
        "root_dir",
        "toml_config_file",
    )


    def __init__(self):
        if not self._init_once():
            return
        self.root_dir = get_relative_path("..")

        self.toml_config_file = f"{self.root_dir}/config.toml"
        self.config = self._load_config()

        self._initialized = True

    def _load_config(self) -> BarConfig:
        """Load and merge configuration from JSON or TOML file."""
        check_toml = os.path.exists(self.toml_config_file)

        if not check_toml:
            raise FileNotFoundError("Please provide toml config.")

        parsed_data = read_toml_file(file_path=self.toml_config_file)
        if parsed_data is None:
            logger.warning("[CONFIG] Failed to parse config.toml, using defaults")
            parsed_data = {}

        try:
            validate_config_enums(
                parsed_data, f"{self.root_dir}/{APPLICATION_NAME}.schema.json"
            )
            validate_widgets(parsed_data, DEFAULT_CONFIG)
        except (ValueError, FileNotFoundError) as exc:
            raise SystemExit(f"[CONFIG] {exc}") from None

        # Merge configuration with defaults
        for key, default_value in DEFAULT_CONFIG.items():
            if key in _EXCLUDED_SCHEMA_KEYS:
                continue

            if key in _LIST_CONFIG_KEYS:
                # For lists, use the user's value or default if not present
                parsed_data[key] = parsed_data.get(key, default_value)
            else:
                # For dictionaries, merge with defaults
                parsed_data[key] = deep_merge(parsed_data.get(key, {}), default_value)

        return parsed_data


configuration = TsumikiConfig()
tsumiki_config = configuration.config
