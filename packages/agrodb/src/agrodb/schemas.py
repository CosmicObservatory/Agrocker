"""Schemas SQLite del proyecto Agrocker.

Tres bases de datos, una por fuente de datos:
- weather.db     : clima historico (WeatherAPI)
- production.db  : produccion agricola (DGSIAP) + catalogo de cultivos + predicciones
- prices.db      : precios de mercado (SNIIM / queprecio.info)
"""

WEATHER_SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_points (
    id INTEGER PRIMARY KEY,
    clave_geo TEXT NOT NULL,
    estado TEXT NOT NULL,
    municipio TEXT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    UNIQUE(estado, municipio)
);

CREATE TABLE IF NOT EXISTS weather_daily (
    point_id INTEGER NOT NULL REFERENCES weather_points(id),
    fecha TEXT NOT NULL,
    maxtemp_c REAL,
    mintemp_c REAL,
    avgtemp_c REAL,
    totalprecip_mm REAL,
    avghumidity REAL,
    uv REAL,
    et0 REAL,
    PRIMARY KEY (point_id, fecha)
);

CREATE TABLE IF NOT EXISTS weather_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_weather_daily_fecha ON weather_daily(fecha);
"""

PRODUCTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS geo_states (
    clave TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    lat REAL,
    lon REAL
);

CREATE TABLE IF NOT EXISTS production (
    estado TEXT NOT NULL,
    municipio TEXT NOT NULL,
    clave_cultivo TEXT NOT NULL,
    cultivo TEXT,
    anio INTEGER NOT NULL,
    ciclo TEXT,
    tipo_riego TEXT,
    superficie_ha REAL,
    produccion_t REAL,
    rendimiento_t_ha REAL,
    precio_ton REAL,
    PRIMARY KEY (estado, municipio, clave_cultivo, anio, ciclo, tipo_riego)
);

CREATE INDEX IF NOT EXISTS idx_production_estado_cultivo
    ON production(estado, clave_cultivo, anio);

CREATE TABLE IF NOT EXISTS crops (
    clave TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    ciclo_productivo_meses INTEGER,
    temp_min REAL,
    temp_opt_min REAL,
    temp_opt_max REAL,
    temp_max REAL,
    precip_annual_mm REAL,
    riego_recomendado TEXT,
    rendimiento_potencial_t_ha REAL,
    precio_ref_ton REAL
);

CREATE TABLE IF NOT EXISTS state_crop_predictions (
    estado TEXT NOT NULL,
    clave_cultivo TEXT NOT NULL,
    ciclo TEXT NOT NULL,
    tipo_riego TEXT NOT NULL,
    aptitud REAL,
    rendimiento_est_t_ha REAL,
    produccion_est_t REAL,
    score_final REAL,
    computed_at TEXT,
    PRIMARY KEY (estado, clave_cultivo, ciclo, tipo_riego)
);
"""

PRICES_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_prices (
    fecha TEXT NOT NULL,
    producto TEXT NOT NULL,
    variedad TEXT,
    estado TEXT,
    central TEXT,
    precio_min REAL,
    precio_max REAL,
    precio_frec REAL,
    unidad TEXT,
    fuente TEXT,
    PRIMARY KEY (fecha, producto, variedad, estado, central, fuente)
);

CREATE INDEX IF NOT EXISTS idx_prices_producto_fecha
    ON market_prices(producto, fecha);
"""

SCHEMAS = {
    "weather.db": WEATHER_SCHEMA,
    "production.db": PRODUCTION_SCHEMA,
    "prices.db": PRICES_SCHEMA,
}
