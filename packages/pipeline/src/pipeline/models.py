"""Modelo hibrido de aptitud agricola.

1. Aptitud (0-1) por reglas agronomicas: temperatura y balance
   hidrico del ciclo productivo (PV = May-Oct, OI = Nov-Abr),
   ajustado por tipo de riego.
2. Rendimiento estimado: HistGradientBoostingRegressor entrenado con
   el historico DGSIAP por cultivo; fallback al rendimiento potencial
   del catalogo si no hay datos suficientes.
3. Produccion estimada = rendimiento x superficie mas reciente del
   estado para ese cultivo.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from agrodb import get_conn, get_ro_conn, load_states
from pipeline.config import Config

log = logging.getLogger(__name__)

CICLOS = {"PV": (5, 10), "OI": (11, 4)}  # meses inclusivos (PV: may-oct, OI: nov-abr)
MIN_TRAIN_ROWS = 30


def _cycle_months(ciclo: str) -> list[int]:
    start, end = CICLOS.get(ciclo.upper(), CICLOS["PV"])
    if start <= end:
        return list(range(start, end + 1))
    return list(range(start, 13)) + list(range(1, end + 1))


def climate_profile(weather_conn, estado: str, ciclo: str) -> dict | None:
    """Agrega el clima del estado en los meses del ciclo (promedio historico)."""
    months = _cycle_months(ciclo)
    rows = weather_conn.execute(
        """SELECT w.* FROM weather_daily w
           JOIN weather_points p ON p.id = w.point_id
           WHERE p.estado = ?""",
        (estado,),
    ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame([dict(r) for r in rows])
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["mes"] = df["fecha"].dt.month
    df = df[df["mes"].isin(months)]
    if df.empty:
        return None
    years = df["fecha"].dt.year.nunique()
    return {
        "avgtemp_c": float(df["avgtemp_c"].mean()),
        "maxtemp_c": float(df["maxtemp_c"].mean()),
        "precip_mm": float(df["totalprecip_mm"].sum() / max(years, 1)),
        "et0_mm": float(df["et0"].fillna(0).sum() / max(years, 1)),
        "humidity": float(df["avghumidity"].mean()),
        "days": len(df),
    }


def suitability(crop: dict, profile: dict | None, tipo_riego: str, ciclo: str) -> float:
    """Score de aptitud 0-1 segun parametros del cultivo y clima del ciclo."""
    if profile is None:
        return 0.5  # sin datos climaticos: neutral

    score = 1.0

    # Temperatura: penaliza fuera de la ventana optima
    t = profile["avgtemp_c"]
    t_opt_min, t_opt_max = crop["temp_opt_min"], crop["temp_opt_max"]
    if t < crop["temp_min"] or t > crop["temp_max"]:
        score *= 0.2
    elif t < t_opt_min:
        score *= 0.6 + 0.4 * (t - crop["temp_min"]) / max(t_opt_min - crop["temp_min"], 1)
    elif t > t_opt_max:
        score *= 0.6 + 0.4 * (crop["temp_max"] - t) / max(crop["temp_max"] - t_opt_max, 1)
    else:
        # Optimo pleno en el centro de la ventana
        mid = (t_opt_min + t_opt_max) / 2
        score *= 1.0 - 0.2 * abs(t - mid) / max((t_opt_max - t_opt_min) / 2, 1)

    # Balance hidrico: precipitacion del ciclo vs necesidad anual prorrateada
    needed = (crop["precip_annual_mm"] or 600) * (len(_cycle_months(ciclo)) / 12.0)
    precip = profile["precip_mm"]
    water_ratio = precip / max(needed, 1)
    if tipo_riego in ("asegurado", "ambos"):
        # Con riego asegurado el deficit se compensa casi por completo
        water_score = min(1.0, 0.55 + 0.45 * water_ratio)
    else:
        water_score = min(1.0, water_ratio)
        if water_ratio < 0.5:
            water_score *= 0.5
    score *= water_score

    # ET0 alto con poca lluvia castiga mas en temporal
    if tipo_riego == "temporal" and profile["et0_mm"] > profile["precip_mm"] * 1.5:
        score *= 0.8

    return float(np.clip(score, 0.0, 1.0))


def _production_frame(conn) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT estado, clave_cultivo, cultivo, anio, ciclo, tipo_riego,
                  superficie_ha, produccion_t, rendimiento_t_ha, precio_ton
           FROM production""",
        conn,
    )


def _norm_name(s: str) -> str:
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", str(s))
                if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def _crop_history(prod_df: pd.DataFrame, crop: dict) -> pd.DataFrame:
    """Historico DGSIAP del cultivo: match por nombre normalizado."""
    target = _norm_name(crop["nombre"])
    names = prod_df["cultivo"].map(_norm_name)
    mask = names == target
    if not mask.any():
        # fallback: coincidencia parcial (p. ej. 'chile' -> 'chile seco')
        mask = names.str.contains(target.split()[0], na=False)
    return prod_df[mask]


def _latest_surface(conn, estado: str, crop: dict) -> float | None:
    target = _norm_name(crop["nombre"])
    rows = conn.execute(
        """SELECT cultivo, superficie_ha, anio FROM production
           WHERE estado = ? AND superficie_ha > 0
           ORDER BY anio DESC""",
        (estado,),
    ).fetchall()
    for r in rows:
        if _norm_name(r["cultivo"]) == target or target.split()[0] in _norm_name(r["cultivo"]):
            return r["superficie_ha"]
    return None


def _train_crop_model(df: pd.DataFrame) -> HistGradientBoostingRegressor | None:
    """Entrena un modelo de rendimiento por cultivo con su historico."""
    d = df.dropna(subset=["rendimiento_t_ha", "anio"]).copy()
    if len(d) < MIN_TRAIN_ROWS or d["rendimiento_t_ha"].nunique() < 2:
        return None
    d["anio_c"] = d["anio"] - d["anio"].mean()
    X = d[["anio_c"]]
    y = d["rendimiento_t_ha"].clip(lower=0)
    model = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.08,
                                        max_depth=4, random_state=42)
    model.fit(X, y)
    return model


def predict_all(cfg: Config) -> dict:
    """Re-calcula y materializa state_crop_predictions para todos los cultivos."""
    prod_conn = get_conn("production.db", cfg.db_dir)
    weather_conn = get_ro_conn("weather.db", cfg.db_dir) \
        if (cfg.db_dir / "weather.db").exists() else None

    crops = [dict(r) for r in prod_conn.execute("SELECT * FROM crops").fetchall()]
    prod_df = _production_frame(prod_conn)

    # Modelos por cultivo (match por nombre, no por clave DGSIAP)
    models = {}
    histories = {}
    for crop in crops:
        hist = _crop_history(prod_df, crop)
        histories[crop["clave"]] = hist
        models[crop["clave"]] = _train_crop_model(hist)

    states = [s["nombre"] for s in load_states()]
    written = 0
    now = date.today().isoformat()

    for crop in crops:
        clave = crop["clave"]
        hist = histories[clave]
        model = models.get(clave)
        for estado in states:
            for ciclo in CICLOS:
                for tipo_riego in ("temporal", "asegurado"):
                    apt = suitability(crop, _safe_profile(weather_conn, estado, ciclo), tipo_riego, ciclo)
                    rend = _estimate_yield(model, hist, estado, crop, tipo_riego, apt)
                    superficie = _latest_surface(prod_conn, estado, crop)
                    produccion = rend * superficie if superficie else None
                    score = apt * (0.5 + 0.5 * min(rend / max(crop["rendimiento_potencial_t_ha"] or 1, 1), 1.0))
                    prod_conn.execute(
                        """INSERT OR REPLACE INTO state_crop_predictions
                           (estado, clave_cultivo, ciclo, tipo_riego, aptitud,
                            rendimiento_est_t_ha, produccion_est_t, score_final, computed_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (estado, clave, ciclo, tipo_riego, apt, rend,
                         produccion, score, now),
                    )
                    written += 1

    prod_conn.commit()
    prod_conn.close()
    if weather_conn:
        weather_conn.close()
    log.info("Predicciones materializadas: %s filas", written)
    return {"predictions": written}


def _safe_profile(weather_conn, estado: str, ciclo: str) -> dict | None:
    if weather_conn is None:
        return None
    return climate_profile(weather_conn, estado, ciclo)


def _estimate_yield(model, hist, estado, crop, tipo_riego, apt) -> float:
    """Rendimiento estimado: modelo ML si existe; si no, catalogo x aptitud."""
    base = crop["rendimiento_potencial_t_ha"] or 2.0
    if model is None:
        return float(base * (0.5 + 0.5 * apt))

    # Feature simple: ano centrado no aplica a futuro; usamos media historica
    # del estado-cultivo si existe, combinada con la tendencia del modelo.
    estado_hist = hist[hist["estado"] == estado]
    if estado_hist.empty:
        pred = float(np.mean(model.predict(pd.DataFrame({"anio_c": [0.0]}))))
    else:
        last_anio = estado_hist["anio"].max()
        pred = float(model.predict(
            pd.DataFrame({"anio_c": [last_anio - estado_hist["anio"].mean()]})
        )[0])
    pred = float(np.clip(pred, 0, base * 1.5))
    # Ajuste por aptitud climatica del ciclo actual
    return float(pred * (0.6 + 0.4 * apt))
