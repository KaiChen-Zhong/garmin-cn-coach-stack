"""
Project configuration helpers.

Keeps Garmin auth settings in one place so CLI, scheduler, API server,
exporter, and importer do not silently use different accounts or regions.
"""

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - requirements include pyyaml
    yaml = None

PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else CONFIG_PATH
    if not config_path.exists() or yaml is None:
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return _expand_env(data)


def _env_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_garmin_config() -> dict:
    cfg = load_config().get("garmin", {})

    is_cn = _env_bool("GARMIN_IS_CN")
    if is_cn is not None:
        cfg["is_cn"] = is_cn

    if os.getenv("GARMIN_EMAIL"):
        cfg["email"] = os.getenv("GARMIN_EMAIL")
    if os.getenv("GARMIN_PASSWORD"):
        cfg["password"] = os.getenv("GARMIN_PASSWORD")
    if os.getenv("GARMIN_TOKEN_DIR"):
        cfg["token_dir"] = os.getenv("GARMIN_TOKEN_DIR")
    if os.getenv("GARMIN_MFA_MODE"):
        cfg["mfa_mode"] = os.getenv("GARMIN_MFA_MODE")

    cfg.setdefault("is_cn", False)
    cfg.setdefault("mfa_mode", "prompt")
    cfg.setdefault("token_dir", "~/.garminconnect-cn" if cfg.get("is_cn") else "~/.garminconnect")

    if cfg.get("token_dir"):
        cfg["token_dir"] = str(Path(cfg["token_dir"]).expanduser())

    return cfg
