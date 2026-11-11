"""Configuracion del pipeline desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("DB_DIR", "data"))
    )
    weatherapi_key: str = field(
        default_factory=lambda: os.environ.get("WEATHERAPI_KEY", "")
    )
    weather_start_year: int = field(
        default_factory=lambda: int(os.environ.get("WEATHER_START_YEAR", "2010"))
    )
    weather_chunk_days: int = field(
        default_factory=lambda: int(os.environ.get("WEATHER_CHUNK_DAYS", "18"))
    )
    weather_max_points: int = field(
        default_factory=lambda: int(os.environ.get("WEATHER_MAX_POINTS", "0"))
    )
    weather_rate_limit_seconds: float = field(
        default_factory=lambda: float(os.environ.get("WEATHER_RATE_LIMIT_SECONDS", "0.5"))
    )
    siap_base_url: str = field(
        default_factory=lambda: os.environ.get("SIAP_BASE_URL", "")
    )
    siap_local_dir: str = field(
        default_factory=lambda: os.environ.get("SIAP_LOCAL_DIR", "")
    )
    queprecio_token: str = field(
        default_factory=lambda: os.environ.get("QUEPRECIO_TOKEN", "")
    )
    pipeline_interval_hours: float = field(
        default_factory=lambda: float(os.environ.get("PIPELINE_INTERVAL_HOURS", "0"))
    )


def load_config() -> Config:
    return Config()
