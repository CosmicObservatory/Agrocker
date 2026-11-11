"""Tests del modelo hibrido y helpers."""

import pandas as pd
import pytest

from agrodb import canonical_state, get_conn, init_dbs, load_states
from pipeline.models import _cycle_months, suitability


def test_load_states_32():
    states = load_states()
    assert len(states) == 32
    assert all("nombre" in s and "lat" in s for s in states)


def test_canonical_state_aliases():
    assert canonical_state("MICHOACAN") == "Michoacán de Ocampo"
    assert canonical_state("Veracruz") == "Veracruz de Ignacio de la Llave"
    assert canonical_state("Jalisco") == "Jalisco"
    assert canonical_state("Narnia") is None


def test_cycle_months():
    assert _cycle_months("PV") == [5, 6, 7, 8, 9, 10]
    assert sorted(_cycle_months("OI")) == [1, 2, 3, 4, 11, 12]


def _crop(**kw):
    base = dict(
        clave="maiz", nombre="Maiz", ciclo_productivo_meses=6,
        temp_min=10, temp_opt_min=18, temp_opt_max=34, temp_max=40,
        precip_annual_mm=700, riego_recomendado="ambos",
        rendimiento_potencial_t_ha=4.5, precio_ref_ton=5200,
    )
    base.update(kw)
    return base


def test_suitability_optimal():
    crop = _crop()
    profile = {"avgtemp_c": 26, "maxtemp_c": 32, "precip_mm": 400,
               "et0_mm": 500, "humidity": 60}
    score = suitability(crop, profile, "asegurado", "PV")
    assert 0.5 < score <= 1.0


def test_suitability_too_hot():
    crop = _crop()
    profile = {"avgtemp_c": 42, "maxtemp_c": 45, "precip_mm": 100,
               "et0_mm": 900, "humidity": 30}
    score = suitability(crop, profile, "temporal", "PV")
    assert score < 0.4


def test_suitability_no_profile_neutral():
    assert suitability(_crop(), None, "temporal", "PV") == 0.5


def test_dbs_created(tmp_path):
    paths = init_dbs(tmp_path)
    assert set(paths) == {"weather.db", "production.db", "prices.db"}
    conn = get_conn("production.db", tmp_path)
    conn.execute(
        "INSERT INTO crops (clave, nombre) VALUES ('x', 'X')"
    )
    assert conn.execute("SELECT COUNT(*) FROM crops").fetchone()[0] == 1
    conn.close()


def test_crop_history_matching():
    from pipeline.models import _crop_history
    df = pd.DataFrame({
        "cultivo": ["MAIZ", "Frijol", "Maiz Azul"],
        "rendimiento_t_ha": [4.0, 1.5, 3.5],
    })
    crop = _crop()
    hist = _crop_history(df, crop)
    assert set(hist["cultivo"]) == {"MAIZ"}
