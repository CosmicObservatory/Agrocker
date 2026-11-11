"""Extraccion de precios de mercado.

Fuentes, en orden de preferencia:
1. API de queprecio.info (requiere QUEPRECIO_TOKEN).
2. Scraping ASPX del SNIIM (economia-sniim.gob.mx) — fragil, best-effort.
3. Fixtures deterministicos para que el sistema sea funcional sin red.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import random

import pandas as pd
import requests

from agrodb import get_conn
from pipeline.config import Config

log = logging.getLogger(__name__)

SNIIM_URL = "http://www.economia-sniim.gob.mx/nuevo/Consultas/MercadosNacionales/PreciosDeMercado/Agricolas/ConsultaAndenSubasta.aspx"
QUEPRECIO_URL = "https://queprecio.info/api/v1/precios"

# Productos representativos para fixtures (nombre SNIIM simplificado)
_FIXTURE_PRODUCTS = [
    ("Maiz", "Blanco"), ("Frijol", "Negro"), ("Trigo", "Cristario"),
    ("Sorgo", "Blanco"), ("Cebada", "Forrajero"), ("Avena", "Blanca"),
    ("Soya", "Amarilla"), ("Algodon", "Blanco"), ("Canola", "0"),
    ("Fresa", "0"), ("Tomate", "Saladette"), ("Cebolla", "Blanca"),
    ("Ajo", "0"), ("Chile", "Guajillo"), ("Papa", "0"),
]
_FIXTURE_STATES = ["Jalisco", "Sinaloa", "Michoacán de Ocampo", "Guanajuato",
                   "Chihuahua", "Sonora", "México", "Puebla", "Veracruz de Ignacio de la Llave"]
_BASE_PRICES = {
    "Maiz": 5200, "Frijol": 18000, "Trigo": 6200, "Sorgo": 4800,
    "Cebada": 5600, "Avena": 7000, "Soya": 9800, "Algodon": 15000,
    "Canola": 11000, "Fresa": 25000, "Tomate": 14000, "Cebolla": 12000,
    "Ajo": 35000, "Chile": 22000, "Papa": 9000,
}


def _insert(conn, df: pd.DataFrame, fuente: str) -> int:
    for col in ("variedad", "estado", "central", "precio_min",
                "precio_max", "precio_frec", "unidad"):
        if col not in df.columns:
            df[col] = None
    rows = [
        (
            r.fecha, r.producto, getattr(r, "variedad", None),
            getattr(r, "estado", None), getattr(r, "central", None),
            _num(getattr(r, "precio_min", None)),
            _num(getattr(r, "precio_max", None)),
            _num(getattr(r, "precio_frec", None)),
            getattr(r, "unidad", None) or "kg", fuente,
        )
        for r in df.itertuples(index=False)
    if getattr(r, "fecha", None) is not None
    and getattr(r, "producto", None) is not None
    ]
    if not rows:
        return 0
    conn.executemany(
        """INSERT OR REPLACE INTO market_prices
           (fecha, producto, variedad, estado, central,
            precio_min, precio_max, precio_frec, unidad, fuente)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    return len(rows)


def _num(v) -> float | None:
    try:
        if pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_queprecio(cfg: Config) -> pd.DataFrame | None:
    if not cfg.queprecio_token:
        return None
    try:
        resp = requests.get(
            QUEPRECIO_URL,
            headers={"Authorization": f"Bearer {cfg.queprecio_token}"},
            params={"formato": "json"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("queprecio.info fallo: %s", exc)
        return None
    # Normalizacion best-effort del formato de la API
    rows = []
    for item in data if isinstance(data, list) else data.get("data", []):
        rows.append(
            {
                "fecha": item.get("fecha") or item.get("date"),
                "producto": item.get("producto") or item.get("product"),
                "variedad": item.get("variedad"),
                "estado": item.get("estado"),
                "central": item.get("central") or item.get("mercado"),
                "precio_min": item.get("precio_min"),
                "precio_max": item.get("precio_max"),
                "precio_frec": item.get("precio_frec") or item.get("precio"),
                "unidad": item.get("unidad", "kg"),
            }
        )
    return pd.DataFrame(rows) if rows else None


def _fetch_sniim() -> pd.DataFrame | None:
    """Intento best-effort de scraping del SNIIM; devuelve None si falla."""
    try:
        resp = requests.get(SNIIM_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("SNIIM no disponible: %s", exc)
        return None
    # El SNIIM sirve tablas ASP.NET; parseo minimo con pandas
    try:
        import io
        tables = pd.read_html(io.StringIO(resp.text))
    except (ValueError, ImportError):
        return None
    if not tables:
        return None
    df = tables[0]
    log.info("SNIIM: %s filas scrapeadas", len(df))
    # Renombrado generico; el formato exacto varia por seccion
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.head(5000)


def _fixture_prices(days: int = 365) -> pd.DataFrame:
    """Serie sintetica determinista (mismo seed => mismos datos)."""
    rng = random.Random(42)
    rows = []
    today = dt.date.today()
    for i in range(days):
        fecha = (today - dt.timedelta(days=i)).isoformat()
        for product, variety in _FIXTURE_PRODUCTS:
            base = _BASE_PRICES[product]
            seasonal = 1 + 0.15 * ((i % 365) / 365.0 - 0.5)
            noise = rng.uniform(0.9, 1.1)
            precio = round(base * seasonal * noise / 100) * 100
            state = _FIXTURE_STATES[rng.randrange(len(_FIXTURE_STATES))]
            rows.append(
                {
                    "fecha": fecha,
                    "producto": product,
                    "variedad": variety,
                    "estado": state,
                    "central": f"Central {state}",
                    "precio_min": precio * 0.95,
                    "precio_max": precio * 1.05,
                    "precio_frec": precio,
                    "unidad": "kg",
                }
            )
    return pd.DataFrame(rows)


def _has_data(conn) -> bool:
    return conn.execute("SELECT COUNT(*) FROM market_prices").fetchone()[0] > 0


def run(cfg: Config) -> dict:
    """Punto de entrada del extractor de precios."""
    conn = get_conn("prices.db", cfg.db_dir)
    total = 0

    df = _fetch_queprecio(cfg)
    if df is not None and not df.empty:
        total += _insert(conn, df, "queprecio.info")
        log.info("Precios queprecio.info: %s filas insertadas", total)
    else:
        df = _fetch_sniim()
        if df is not None and not df.empty:
            for col in ("variedad", "estado", "central", "precio_min",
                        "precio_max", "precio_frec", "unidad"):
                if col not in df.columns:
                    df[col] = None
            total += _insert(conn, df, "sniim")
            log.info("Precios SNIIM: %s filas insertadas", total)

    if total == 0 and not _has_data(conn):
        df = _fixture_prices()
        total += _insert(conn, df, "fixture")
        log.warning("Sin fuente de precios disponible: %s fixtures", len(df))
    elif total == 0:
        log.info("prices.db ya tiene datos; fixtures omitidos")

    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM market_prices").fetchone()[0]
    conn.close()
    log.info("Precios: %s filas nuevas, %s totales", total, n)
    return {"rows_new": total, "total": n}
