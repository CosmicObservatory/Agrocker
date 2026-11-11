"""Extraccion de clima historico desde WeatherAPI.

Descarga /v1/history.json por punto de muestreo y periodo (chunks de
WEATHER_CHUNK_DAYS dias), con reanudacion por punto/periodo via
weather_meta. Requiere WEATHERAPI_KEY.
"""

from __future__ import annotations

import datetime as dt
import logging
import time

import requests
from yarl import URL

from agrodb import get_conn, load_states
from pipeline.config import Config

log = logging.getLogger(__name__)

BASE_URL = URL("https://api.weatherapi.com/v1")

DAY_VARS = [
    "maxtemp_c",
    "mintemp_c",
    "avgtemp_c",
    "totalprecip_mm",
    "avghumidity",
    "uv",
]


def _ensure_points(conn, cfg: Config) -> list[dict]:
    """Registra los centroides estatales como puntos de muestreo."""
    states = load_states()
    if cfg.weather_max_points:
        states = states[: cfg.weather_max_points]
    for s in states:
        conn.execute(
            """INSERT INTO weather_points (clave_geo, estado, municipio, lat, lon)
               VALUES (?, ?, NULL, ?, ?)
               ON CONFLICT(estado, municipio) DO NOTHING""",
            (s["clave"], s["nombre"], s["lat"], s["lon"]),
        )
    conn.commit()
    rows = conn.execute(
        "SELECT id, estado, lat, lon FROM weather_points ORDER BY estado"
    ).fetchall()
    return [dict(r) for r in rows]


def _periods(cfg: Config) -> list[tuple[dt.date, dt.date]]:
    start = dt.date(cfg.weather_start_year, 1, 1)
    end = dt.date.today()
    periods = []
    cursor = start
    step = dt.timedelta(days=cfg.weather_chunk_days)
    while cursor < end:
        last = min(cursor + step, end)
        periods.append((cursor, last))
        cursor = last + dt.timedelta(days=1)
    return periods


def _already_done(conn, point_id: int, period: tuple[dt.date, dt.date]) -> bool:
    row = conn.execute(
        "SELECT 1 FROM weather_daily WHERE point_id=? AND fecha BETWEEN ? AND ? LIMIT 1",
        (point_id, period[0].isoformat(), period[1].isoformat()),
    ).fetchone()
    return row is not None


def _fetch_period(cfg: Config, lat: float, lon: float, period) -> dict | None:
    query = {
        "key": cfg.weatherapi_key,
        "q": f"{lat},{lon}",
        "dt": period[0].strftime("%Y-%m-%d"),
        "end_dt": period[1].strftime("%Y-%m-%d"),
        "solar": "yes",
        "et0": "yes",
    }
    for attempt in range(3):
        try:
            resp = requests.get(BASE_URL / "history.json", params=query, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (400, 401, 403):
                log.error("WeatherAPI error %s: %s", resp.status_code, resp.text[:200])
                return None
            log.warning("WeatherAPI %s (intento %s)", resp.status_code, attempt + 1)
        except requests.RequestException as exc:
            log.warning("WeatherAPI request fallo: %s", exc)
        time.sleep(2**attempt)
    return None


def run(cfg: Config) -> dict:
    """Punto de entrada del extractor de clima."""
    if not cfg.weatherapi_key:
        log.warning("WEATHERAPI_KEY vacia: se omite extraccion de clima")
        return {"points": 0, "rows": 0, "skipped": True}

    conn = get_conn("weather.db", cfg.db_dir)
    points = _ensure_points(conn, cfg)
    periods = _periods(cfg)
    rows_written = 0

    for point in points:
        for period in periods:
            if _already_done(conn, point["id"], period):
                continue
            payload = _fetch_period(cfg, point["lat"], point["lon"], period)
            if payload is None:
                continue
            days = payload.get("forecast", {}).get("forecastday", [])
            for day in days:
                d = day.get("day", {})
                conn.execute(
                    """INSERT OR REPLACE INTO weather_daily
                       (point_id, fecha, maxtemp_c, mintemp_c, avgtemp_c,
                        totalprecip_mm, avghumidity, uv, et0)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        point["id"],
                        day["date"],
                        d.get("maxtemp_c"),
                        d.get("mintemp_c"),
                        d.get("avgtemp_c"),
                        d.get("totalprecip_mm"),
                        d.get("avghumidity"),
                        d.get("uv"),
                        day.get("et0"),
                    ),
                )
                rows_written += 1
            conn.commit()
            time.sleep(cfg.weather_rate_limit_seconds)
        log.info("Clima completo para %s", point["estado"])

    total = conn.execute("SELECT COUNT(*) FROM weather_daily").fetchone()[0]
    conn.close()
    log.info("Clima: %s puntos, %s filas nuevas, %s totales", len(points), rows_written, total)
    return {"points": len(points), "rows": rows_written, "total": total}
