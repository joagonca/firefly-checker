"""Load and validate configuration.

Config comes from a TOML file (default ``config.toml`` next to the project, or a path
given via ``FIREFLY_CHECKER_CONFIG``). Secrets may be supplied via the file or, preferably,
overridden by environment variables so they never have to live on disk:

    FIREFLY_PAT   overrides [firefly].pat
    HA_TOKEN      overrides [home_assistant].token
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    import tomli as tomllib  # type: ignore[no-redirect]


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


DEFAULT_STATE_PATH = "~/.local/state/firefly-checker/state.json"


@dataclass(frozen=True)
class Config:
    # Firefly
    firefly_url: str
    firefly_pat: str
    account_id: str
    # Home Assistant
    ha_url: str
    ha_token: str
    ha_notify_service: str
    # Behaviour
    target: float = 250.0
    currency: str = "EUR"
    timezone: str = "localtime"
    state_path: str = DEFAULT_STATE_PATH

    @property
    def resolved_state_path(self) -> Path:
        return Path(os.path.expanduser(self.state_path))


def _require(table: dict, section: str, key: str) -> str:
    try:
        value = table[key]
    except KeyError as exc:
        raise ConfigError(f"Missing required config: [{section}].{key}") from exc
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Config [{section}].{key} must be a non-empty string")
    return value.strip()


def _config_path() -> Path:
    env = os.environ.get("FIREFLY_CHECKER_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "config.toml"


def load(path: Path | None = None) -> Config:
    """Load configuration, applying env-var overrides for secrets."""
    cfg_path = path or _config_path()
    if not cfg_path.exists():
        raise ConfigError(
            f"Config file not found: {cfg_path}. Copy config.example.toml to config.toml "
            "and fill it in (or set FIREFLY_CHECKER_CONFIG)."
        )
    with cfg_path.open("rb") as fh:
        raw = tomllib.load(fh)

    firefly = raw.get("firefly", {})
    ha = raw.get("home_assistant", {})
    behaviour = raw.get("behaviour", {})

    pat = os.environ.get("FIREFLY_PAT") or firefly.get("pat", "")
    token = os.environ.get("HA_TOKEN") or ha.get("token", "")
    if not str(pat).strip():
        raise ConfigError("Missing Firefly PAT: set [firefly].pat or env FIREFLY_PAT")
    if not str(token).strip():
        raise ConfigError("Missing HA token: set [home_assistant].token or env HA_TOKEN")

    return Config(
        firefly_url=_require(firefly, "firefly", "url").rstrip("/"),
        firefly_pat=str(pat).strip(),
        account_id=_require(firefly, "firefly", "account_id"),
        ha_url=_require(ha, "home_assistant", "url").rstrip("/"),
        ha_token=str(token).strip(),
        ha_notify_service=_require(ha, "home_assistant", "notify_service"),
        target=float(behaviour.get("target", 250.0)),
        currency=str(behaviour.get("currency", "EUR")).strip(),
        timezone=str(behaviour.get("timezone", "localtime")).strip(),
        state_path=str(behaviour.get("state_path", DEFAULT_STATE_PATH)).strip(),
    )
