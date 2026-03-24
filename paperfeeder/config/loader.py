from __future__ import annotations

from .schema import Config, create_default_config


def load_config(path: str = "config.yaml") -> Config:
    return Config.from_yaml(path)


__all__ = ["Config", "create_default_config", "load_config"]

