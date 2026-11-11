# Agrocker

Plataforma de **aptitud agricola por estado** para Mexico. Cruza tres
fuentes de datos y predice los mejores estados para sembrar un cultivo
dado, estimando produccion segun los parametros propios del cultivo
(ciclo productivo y tipo de riego).

## Arquitectura

Monorepo **uv workspace** con 2 contenedores Docker y 3 bases SQLite
(archivos en el volumen `data/`, sin contenedor propio):

| Servicio | Imagen | Funcion |
|---|---|---|
| `pipeline` | `packages/pipeline` | Descarga clima (WeatherAPI), produccion (DGSIAP CSVs), precios (SNIIM/queprecio.info) y materializa predicciones con modelo hibrido reglas + sklearn. |
| `dashboard` | `packages/dashboard` | App Dash + Plotly en `:8050`: ranking de estados, mapa coropletico, historicos de produccion y precios. |

Bases SQLite:

- `data/weather.db` — clima diario por punto de muestreo estatal.
- `data/production.db` — produccion DGSIAP, catalogo de cultivos, geoestados, `state_crop_predictions`.
- `data/prices.db` — precios de mercado.

Paquete compartido `packages/agrodb`: esquemas, helpers de conexion
(escritura / solo-lectura) y catalogo canonico de estados.

## Inicio rapido

```bash
cp .env.example .env   # agrega WEATHERAPI_KEY
uv sync                # desarrollo local (opcional)

docker compose build
docker compose run --rm pipeline          # one-shot: ingesta + modelo
docker compose up -d dashboard            # http://localhost:8050
```

Modo programado (actualiza datos cada N horas):

```bash
docker compose run --rm -e PIPELINE_INTERVAL_HOURS=24 pipeline agro-pipeline all --loop
```

O por tarea: `agro-pipeline siap|prices|weather|model|reference`.

## Modelo hibrido

1. **Aptitud (reglas agronomicas)**: temperatura media del ciclo
   (PV = may-oct, OI = nov-abr) vs ventana optima del cultivo;
   balance precipitación/ET0 ajustado por tipo de riego.
2. **Rendimiento (ML)**: `HistGradientBoostingRegressor` por cultivo
   sobre el historico DGSIAP; fallback a rendimiento potencial del
   catalogo × aptitud si hay pocos datos.
3. **Produccion estimada** = rendimiento × superficie mas reciente
   del estado.

El catalogo de cultivos (`crops`) es editable directamente en
`production.db` (ciclo en meses, temperaturas optima/min/max,
precipitacion anual requerida, riego recomendado, rendimiento
potencial, precio referencia).

## Estructura

```
packages/
  agrodb/       esquemas SQLite + estados canonicos (geojson INEGI)
  pipeline/     extractores + modelo + CLI (agro-pipeline)
  dashboard/    app Dash (agro-dashboard) + geojson para el mapa
base-code/      codigo y notebooks previos (referencia)
data/           bases SQLite (gitignored, persistente via volumen)
```

## Notas

- **Clima**: WeatherAPI `/v1/history.json` en chunks de 18 dias, con
  reanudacion automatica; requiere `WEATHERAPI_KEY`.
- **DGSIAP**: CSVs de datos abiertos descubiertos desde
  `nube.agricultura.gob.mx`; alternativa: `SIAP_LOCAL_DIR` con CSVs
  propios o `SIAP_BASE_URL`.
- **Precios**: SNIIM (scraping ASPX best-effort), API queprecio.info
  (`QUEPRECIO_TOKEN`) o fixtures deterministicos si no hay fuente.
- Solo el pipeline escribe en las SQLite; el dashboard las abre en
  modo `mode=ro`.
