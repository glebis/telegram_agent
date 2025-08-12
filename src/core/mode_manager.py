import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class ModeManager:
    """Manages bot modes and presets from YAML configuration"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            # Default to config/modes.yaml relative to project root
            config_path = Path(__file__).parent.parent.parent / "config" / "modes.yaml"

        self.config_path = Path(config_path)
        self._config = None
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
            logger.info(f"Loaded mode configuration from {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading mode configuration: {e}")
            # Fallback to basic configuration
            self._config = {
                "modes": {
                    "default": {
                        "name": "Default",
                        "prompt": "Describe the image in ≤40 words.",
                        "embed": False,
                    }
                },
                "aliases": {},
            }

    def get_available_modes(self) -> List[str]:
        """Get list of available mode names"""
        return list(self._config.get("modes", {}).keys())

    def get_mode_info(self, mode_name: str) -> Optional[Dict]:
        """Get information about a specific mode"""
        return self._config.get("modes", {}).get(mode_name)

    def get_mode_presets(self, mode_name: str) -> List[str]:
        """Get available presets for a mode"""
        mode_info = self.get_mode_info(mode_name)
        if not mode_info:
            return []

        presets = mode_info.get("presets", [])
        return [preset["name"] for preset in presets]

    def get_preset_info(self, mode_name: str, preset_name: str) -> Optional[Dict]:
        """Get information about a specific preset"""
        mode_info = self.get_mode_info(mode_name)
        if not mode_info:
            return None

        presets = mode_info.get("presets", [])
        for preset in presets:
            if preset.get("name") == preset_name:
                return preset

        return None

    def is_valid_mode(self, mode_name: str) -> bool:
        """Check if mode name is valid"""
        return mode_name in self.get_available_modes()

    def is_valid_preset(self, mode_name: str, preset_name: str) -> bool:
        """Check if preset is valid for the given mode"""
        presets = self.get_mode_presets(mode_name)
        return preset_name in presets

    def get_mode_prompt(self, mode_name: str, preset_name: Optional[str] = None) -> str:
        """Get the prompt for a mode/preset combination"""
        mode_info = self.get_mode_info(mode_name)
        if not mode_info:
            return "Describe this image."

        # If no preset specified, return mode's default prompt
        if not preset_name:
            return mode_info.get("prompt", "Describe this image.")

        # Get preset-specific prompt
        preset_info = self.get_preset_info(mode_name, preset_name)
        if preset_info:
            return preset_info.get(
                "prompt", mode_info.get("prompt", "Describe this image.")
            )

        return mode_info.get("prompt", "Describe this image.")

    def should_embed(self, mode_name: str) -> bool:
        """Check if mode should generate embeddings"""
        mode_info = self.get_mode_info(mode_name)
        return mode_info.get("embed", False) if mode_info else False

    def get_mode_settings(self) -> Dict:
        """Get global mode settings"""
        return self._config.get("settings", {})

    def get_command_aliases(self) -> Dict[str, str]:
        """Get command aliases mapping"""
        return self._config.get("aliases", {})

    def resolve_alias(self, command: str) -> Optional[str]:
        """Resolve a command alias to mode.preset format"""
        aliases = self.get_command_aliases()
        return aliases.get(command)

    def get_similarity_threshold(self) -> float:
        """Get similarity threshold for image matching"""
        settings = self.get_mode_settings()
        return settings.get("similarity_threshold", 0.7)

    def get_max_similar_images(self) -> int:
        """Get maximum number of similar images to return"""
        settings = self.get_mode_settings()
        return settings.get("max_similar_images", 5)

    def get_image_max_size(self) -> int:
        """Get maximum image size for processing"""
        settings = self.get_mode_settings()
        return settings.get("image_max_size", 1024)

    def get_supported_formats(self) -> List[str]:
        """Get list of supported image formats"""
        settings = self.get_mode_settings()
        return settings.get("supported_formats", ["jpg", "jpeg", "png", "webp"])

    def reload_config(self) -> bool:
        """Reload configuration from file"""
        try:
            self._load_config()
            return True
        except Exception as e:
            logger.error(f"Error reloading configuration: {e}")
            return False

    def validate_config(self) -> List[str]:
        """Validate configuration and return any errors"""
        errors = []

        if not self._config:
            errors.append("Configuration is empty or invalid")
            return errors

        # Check modes section
        modes = self._config.get("modes", {})
        if not modes:
            errors.append("No modes defined in configuration")

        # Validate each mode
        for mode_name, mode_info in modes.items():
            if not isinstance(mode_info, dict):
                errors.append(f"Mode '{mode_name}' is not a dictionary")
                continue

            # Check required fields
            if "prompt" not in mode_info:
                errors.append(f"Mode '{mode_name}' missing 'prompt' field")

            # Validate presets if they exist
            presets = mode_info.get("presets", [])
            if presets and not isinstance(presets, list):
                errors.append(f"Mode '{mode_name}' presets must be a list")
            else:
                for i, preset in enumerate(presets):
                    if not isinstance(preset, dict):
                        errors.append(
                            f"Mode '{mode_name}' preset {i} is not a dictionary"
                        )
                        continue

                    if "name" not in preset:
                        errors.append(
                            f"Mode '{mode_name}' preset {i} missing 'name' field"
                        )

                    if "prompt" not in preset:
                        errors.append(
                            f"Mode '{mode_name}' preset {i} missing 'prompt' field"
                        )

        # Validate aliases
        aliases = self._config.get("aliases", {})
        for alias, target in aliases.items():
            if "." not in target:
                errors.append(
                    f"Alias '{alias}' target '{target}' should be in 'mode.preset' format"
                )
            else:
                mode_name, preset_name = target.split(".", 1)
                if not self.is_valid_mode(mode_name):
                    errors.append(
                        f"Alias '{alias}' references invalid mode '{mode_name}'"
                    )
                elif preset_name and not self.is_valid_preset(mode_name, preset_name):
                    errors.append(
                        f"Alias '{alias}' references invalid preset '{preset_name}' for mode '{mode_name}'"
                    )

        return errors
