"""App Dash de Agrocker: aptitud agricola por estado."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, State, callback, dcc, html

from dashboard import queries

ASSETS = Path(__file__).parent / "assets"
GEOJSON = json.loads((ASSETS / "mexico_states.geojson").read_text(encoding="utf-8"))

COLORSCALE = "YlGn"

app = Dash(__name__, title="Agrocker — Aptitud agricola")
server = app.server


def _layout() -> html.Div:
    crops = queries.list_crops()
    crop_options = [
        {"label": r.nombre, "value": r.clave}
        for r in crops.itertuples(index=False)
    ] if not crops.empty else []

    return html.Div(
        style={"backgroundColor": "#0f1419", "color": "#e6e6e6",
               "fontFamily": "system-ui, sans-serif", "padding": "24px"},
        children=[
            html.H1("Agrocker", style={"marginBottom": "4px"}),
            html.P(
                "Mejores estados de Mexico para sembrar un cultivo, "
                "segun clima (WeatherAPI), produccion historica (DGSIAP) "
                "y precios de mercado (SNIIM).",
                style={"color": "#9aa4b2", "marginTop": 0},
            ),
            html.Div(
                style={"display": "flex", "gap": "16px", "flexWrap": "wrap",
                       "marginBottom": "20px"},
                children=[
                    html.Div([
                        html.Label("Cultivo", style={"display": "block"}),
                        dcc.Dropdown(
                            id="cultivo", options=crop_options,
                            value=crop_options[0]["value"] if crop_options else None,
                            clearable=False, style={"width": "220px"},
                        ),
                    ]),
                    html.Div([
                        html.Label("Ciclo productivo", style={"display": "block"}),
                        dcc.RadioItems(
                            id="ciclo",
                            options=[{"label": "Primavera-Verano", "value": "PV"},
                                     {"label": "Otono-Invierno", "value": "OI"}],
                            value="PV", inline=True,
                        ),
                    ]),
                    html.Div([
                        html.Label("Tipo de riego", style={"display": "block"}),
                        dcc.RadioItems(
                            id="riego",
                            options=[{"label": "Temporal", "value": "temporal"},
                                     {"label": "Asegurado", "value": "asegurado"}],
                            value="temporal", inline=True,
                        ),
                    ]),
                ],
            ),
            html.Div(id="kpis", style={"display": "flex", "gap": "16px",
                                       "marginBottom": "20px"}),
            dcc.Graph(id="mapa", style={"height": "520px"}),
            html.Div(
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                       "gap": "16px", "marginTop": "16px"},
                children=[
                    dcc.Graph(id="ranking"),
                    html.Div(id="detalle_estado",
                             style={"backgroundColor": "#171c24",
                                    "borderRadius": "8px", "padding": "16px"}),
                ],
            ),
            html.Div(
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                       "gap": "16px", "marginTop": "16px"},
                children=[
                    dcc.Graph(id="hist_produccion"),
                    dcc.Graph(id="hist_precios"),
                ],
            ),
        ],
    )


app.layout = _layout()


def _kpi_card(title: str, value: str, sub: str = "") -> html.Div:
    return html.Div(
        style={"backgroundColor": "#171c24", "borderRadius": "8px",
               "padding": "14px 18px", "minWidth": "180px", "flex": "1"},
        children=[
            html.Div(title, style={"color": "#9aa4b2", "fontSize": "13px"}),
            html.Div(value, style={"fontSize": "26px", "fontWeight": 600}),
            html.Div(sub, style={"color": "#9aa4b2", "fontSize": "12px"}),
        ],
    )


@callback(
    Output("mapa", "figure"),
    Output("ranking", "figure"),
    Output("kpis", "children"),
    Output("hist_produccion", "figure"),
    Output("hist_precios", "figure"),
    Output("detalle_estado", "children"),
    Input("cultivo", "value"),
    Input("ciclo", "value"),
    Input("riego", "value"),
    State("mapa", "clickData"),
)
def update_dashboard(cultivo, ciclo, riego, click_data):
    df = queries.predictions(cultivo, ciclo, riego) if cultivo else pd.DataFrame()

    if df.empty:
        empty = {"data": [], "layout": {"paper_bgcolor": "#0f1419",
                                        "plot_bgcolor": "#0f1419",
                                        "font": {"color": "#e6e6e6"},
                                        "title": {"text": "Sin predicciones. "
                                                          "Ejecuta el pipeline."}}}
        return (empty, empty, [_kpi_card("Estado", "—")],
                empty, empty, html.P("Sin datos de prediccion."))

    # Mapa coropletico
    fig_map = px.choropleth(
        df, geojson=GEOJSON, locations="estado",
        featureidkey="properties.name", color="score_final",
        color_continuous_scale=COLORSCALE, range_color=[0, df["score_final"].max()],
        labels={"score_final": "Score", "estado": "Estado"},
        title=f"Mejores estados — score de aptitud",
    )
    fig_map.update_geos(fitbounds="locations", visible=False)
    fig_map.update_layout(
        paper_bgcolor="#0f1419", plot_bgcolor="#0f1419",
        font={"color": "#e6e6e6"}, geo_bgcolor="#0f1419",
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
    )

    # Ranking de barras
    top = df.head(10).iloc[::-1]
    fig_rank = px.bar(
        top, x="score_final", y="estado", orientation="h",
        color="score_final", color_continuous_scale=COLORSCALE,
        labels={"score_final": "Score", "estado": ""},
        title="Top 10 estados",
    )
    fig_rank.update_layout(
        paper_bgcolor="#0f1419", plot_bgcolor="#0f1419",
        font={"color": "#e6e6e6"}, showlegend=False,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        yaxis={"categoryorder": "array", "categoryarray": top["estado"].tolist()},
    )

    # KPIs
    best = df.iloc[0]
    total_prod = df["produccion_est_t"].sum()
    rend_prom = df["rendimiento_est_t_ha"].mean()
    kpis = [
        _kpi_card("Mejor estado", best["estado"],
                  f"score {best['score_final']:.2f}"),
        _kpi_card("Produccion estimada", f"{total_prod:,.0f} t"
                  if pd.notna(total_prod) else "—",
                  "suma de estados con superficie"),
        _kpi_card("Rendimiento prom.", f"{rend_prom:.2f} t/ha",
                  f"aptitud prom. {df['aptitud'].mean():.2f}"),
    ]

    # Detalle del estado (clic en mapa o primer estado)
    estado_sel = None
    if click_data and click_data.get("points"):
        estado_sel = click_data["points"][0].get("location")
    if estado_sel not in set(df["estado"]):
        estado_sel = best["estado"]
    row = df[df["estado"] == estado_sel].iloc[0]
    clima = queries.state_climate_profile(estado_sel, ciclo)
    detalle = html.Div(children=[
        html.H3(estado_sel, style={"marginTop": 0}),
        html.P(f"Cultivo: {row['cultivo_nombre']} | Ciclo: {ciclo} | "
               f"Riego: {riego}", style={"color": "#9aa4b2"}),
        html.Ul([
            html.Li(f"Aptitud climatica: {row['aptitud']:.2f}"),
            html.Li(f"Rendimiento estimado: {row['rendimiento_est_t_ha']:.2f} t/ha"),
            html.Li(f"Produccion estimada: "
                    f"{row['produccion_est_t']:,.0f} t"
                    if pd.notna(row["produccion_est_t"]) else "—"),
            html.Li(f"Score final: {row['score_final']:.2f}"),
        ]),
        html.H4("Clima del ciclo", style={"color": "#9aa4b2"}),
        html.Ul([
            html.Li(f"Temp. prom.: {clima['temp_prom_c']} °C") if clima else html.Li("Sin datos climaticos"),
            html.Li(f"Precipitacion: {clima['precip_prom_mm']} mm") if clima else None,
            html.Li(f"ET0: {clima['et0_mm']} mm") if clima else None,
        ]),
    ])

    # Historia de produccion
    crops = queries.list_crops()
    crop_row = crops[crops["clave"] == cultivo]
    hist_prod = pd.DataFrame()
    hist_prec = pd.DataFrame()
    if not crop_row.empty:
        nombre = crop_row.iloc[0]["nombre"]
        hist_prod = queries.production_history(nombre)
        hist_prec = queries.price_history(nombre)

    if not hist_prod.empty:
        fig_hp = px.line(hist_prod, x="anio", y="produccion_t",
                         markers=True, title="Produccion historica (t)")
        fig_hp.add_scatter(x=hist_prod["anio"],
                           y=hist_prod["superficie_ha"],
                           name="Superficie (ha)", yaxis="y2")
        fig_hp.update_layout(
            paper_bgcolor="#0f1419", plot_bgcolor="#0f1419",
            font={"color": "#e6e6e6"},
            yaxis2={"overlaying": "y", "side": "right", "title": "ha"},
            margin={"l": 0, "r": 0, "t": 40, "b": 0},
            legend={"orientation": "h"},
        )
    else:
        fig_hp = {"data": [], "layout": {"paper_bgcolor": "#0f1419",
                "plot_bgcolor": "#0f1419", "font": {"color": "#e6e6e6"},
                "title": {"text": "Sin historial de produccion"}}}

    if not hist_prec.empty:
        fig_hpr = px.line(hist_prec, x="fecha", y="precio_prom",
                          title="Precio de mercado ($/kg)")
        fig_hpr.update_layout(
            paper_bgcolor="#0f1419", plot_bgcolor="#0f1419",
            font={"color": "#e6e6e6"},
            margin={"l": 0, "r": 0, "t": 40, "b": 0},
        )
    else:
        fig_hpr = {"data": [], "layout": {"paper_bgcolor": "#0f1419",
                "plot_bgcolor": "#0f1419", "font": {"color": "#e6e6e6"},
                "title": {"text": "Sin historial de precios"}}}

    return fig_map, fig_rank, kpis, fig_hp, fig_hpr, detalle


def main() -> None:
    app.run(host="0.0.0.0", port=8050, debug=False)


if __name__ == "__main__":
    main()
