"""Consultas de solo lectura sobre las 3 bases SQLite."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from agrodb import get_ro_conn, load_states

DB_DIR = Path(os.environ.get("DB_DIR", "data"))


def _ro(name: str):
    path = DB_DIR / name
    if not path.exists():
        return None
    return get_ro_conn(name, DB_DIR)


def list_crops() -> pd.DataFrame:
    conn = _ro("production.db")
    if conn is None:
        return pd.DataFrame()
    try:
        return pd.read_sql_query("SELECT * FROM crops ORDER BY nombre", conn)
    finally:
        conn.close()


def predictions(cultivo: str, ciclo: str, tipo_riego: str) -> pd.DataFrame:
    """Ranking estatal para un cultivo/ciclo/riego."""
    conn = _ro("production.db")
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(
            """SELECT p.*, c.nombre AS cultivo_nombre
               FROM state_crop_predictions p
               JOIN crops c ON c.clave = p.clave_cultivo
               WHERE p.clave_cultivo = ? AND p.ciclo = ? AND p.tipo_riego = ?
               ORDER BY p.score_final DESC""",
            conn, params=(cultivo, ciclo, tipo_riego),
        )
        return df
    finally:
        conn.close()


def production_history(cultivo_nombre: str) -> pd.DataFrame:
    """Agregado nacional anual del cultivo (produccion, superficie, rendimiento)."""
    conn = _ro("production.db")
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(
            """SELECT anio, SUM(superficie_ha) AS superficie_ha,
                      SUM(produccion_t) AS produccion_t,
                      SUM(produccion_t)/NULLIF(SUM(superficie_ha),0) AS rendimiento_t_ha
               FROM production
               WHERE lower(cultivo) LIKE ?
               GROUP BY anio ORDER BY anio""",
            conn, params=(f"%{cultivo_nombre.lower()}%",),
        )
        return df
    finally:
        conn.close()


def price_history(producto: str) -> pd.DataFrame:
    conn = _ro("prices.db")
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(
            """SELECT fecha, AVG(precio_frec) AS precio_prom,
                      MIN(precio_min) AS precio_min, MAX(precio_max) AS precio_max
               FROM market_prices
               WHERE lower(producto) LIKE ? AND precio_frec IS NOT NULL
               GROUP BY fecha ORDER BY fecha""",
            conn, params=(f"%{producto.lower()}%",),
        )
        if not df.empty:
            df["fecha"] = pd.to_datetime(df["fecha"])
        return df
    finally:
        conn.close()


def state_climate_profile(estado: str, ciclo: str) -> dict | None:
    conn = _ro("weather.db")
    if conn is None:
        return None
    try:
        months = {"PV": list(range(5, 11)), "OI": list(range(11, 13)) + list(range(1, 5))}
        rows = conn.execute(
            """SELECT w.* FROM weather_daily w
               JOIN weather_points p ON p.id = w.point_id
               WHERE p.estado = ?""",
            (estado,),
        ).fetchall()
        if not rows:
            return None
        df = pd.DataFrame([dict(r) for r in rows])
        df["fecha"] = pd.to_datetime(df["fecha"])
        df = df[df["fecha"].dt.month.isin(months.get(ciclo, months["PV"]))]
        if df.empty:
            return None
        years = df["fecha"].dt.year.nunique()
        return {
            "temp_prom_c": round(float(df["avgtemp_c"].mean()), 1),
            "precip_prom_mm": round(float(df["totalprecip_mm"].sum()) / max(years, 1), 0),
            "et0_mm": round(float(df["et0"].fillna(0).sum()) / max(years, 1), 0),
            "dias": len(df),
        }
    finally:
        conn.close()


def geo_states() -> pd.DataFrame:
    return pd.DataFrame(load_states())
