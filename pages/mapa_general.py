"""
PÁGINA DE STREAMLIT: Explorador Geográfico del Mercado (PyDeck)
================================================================
Ubicación: pages/mapa_general.py  (mismo nivel de carpetas que tus otras páginas,
           con utils/backend.py disponible para importar)

Qué muestra:
  📍 Pestaña 1 - Explorador de Propiedades
       Un punto por propiedad (~10.000).
         · Color  -> precio por m²  (o "interés": visitas por día publicada)
         · Tamaño -> superficie total / precio total / visitas
         · Hover  -> tarjeta con el detalle (dirección, precio, expensas, inmobiliaria, etc.)
  🔥 Pestaña 2 - Mapa de Calor ($/m²)
       Cuadrícula de celdas: cada celda se pinta con la mediana de USD/m² de las
       propiedades que caen adentro (o con la cantidad, para ver densidad).

Todo el tratamiento de datos se hace en un único DataFrame de pandas ("df").
"""

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="Mapa del Mercado", layout="wide")

from utils.backend import obtener_df_limpio, aplicar_filtro_global

# ==================================================
# 1. CONSTANTES (si querés cambiar algo, se toca solo acá)
# ==================================================

# Mapa base de Carto: no necesita token de Mapbox
ESTILO_MAPA = pdk.map_styles.CARTO_DARK
ZOOM_INICIAL = 11.5

# Rectángulo que rodea a La Plata. Lo que quede afuera se descarta
# (suele ser un error de geolocalización en el aviso). Ajustalo si cambiás de ciudad.
LAT_MIN, LAT_MAX = -35.3, -34.6
LON_MIN, LON_MAX = -58.4, -57.5

ESTADOS_OBRA = ("En construcción", "A estrenar")
ORDEN_ANTIGUEDAD = ["En construcción", "A estrenar", "1-5", "6-10",
                    "11-15", "16-25", "26-35", "36 o más"]

# Paletas RGB (de menor a mayor valor)
PALETA_PRECIO = [[44, 123, 182], [171, 217, 233], [255, 255, 191], [253, 174, 97], [215, 25, 28]]    # azul=barato, rojo=caro
PALETA_INTERES = [[215, 25, 28], [253, 174, 97], [255, 255, 191], [166, 217, 106], [26, 150, 65]]    # rojo=poco interés, verde=mucho
PALETA_DENSIDAD = [[255, 255, 178], [254, 204, 92], [253, 141, 60], [240, 59, 32], [189, 0, 38]]     # amarillo=pocas, rojo oscuro=muchas

# Columnas que usamos de Mongo -> nombre corto y sin tildes/ñ para el mapa
COLUMNAS = {
    "latitud": "lat",
    "longitud": "lon",
    "local_address": "direccion",
    "zona": "zona",
    "realEstateType": "tipo",
    "operationType": "operacion",
    "publisher_name": "inmobiliaria",
    "prices_amount": "precio",
    "precio_m2_tot": "precio_m2",
    "expenses": "expensas",
    "supTotal_value": "sup_total",
    "supCub_value": "sup_cubierta",
    "ambientes": "ambientes",
    "baños": "banos",
    "cochera": "cocheras",
    "antiguedad_info": "antiguedad",
    "posting_antiquity": "dias_publicada",
    "visitas": "visitas",
}
COLUMNAS_NUMERICAS = ["lat", "lon", "precio", "precio_m2", "expensas", "sup_total",
                      "sup_cubierta", "ambientes", "banos", "cocheras",
                      "dias_publicada", "visitas"]

# Tarjeta flotante. Las {llaves} son columnas del DataFrame (ya vienen formateadas como texto)
TOOLTIP_PUNTOS = {
    "html": """
    <div style="font-family: sans-serif; width: 250px;">
        <b style="font-size: 14px;">{direccion}</b><br>
        <span style="color: #aaa;">{zona} | {tipo} | {operacion}</span>
        <hr style="margin: 6px 0; border-color: #444;">
        💰 <b>{precio_txt}</b> ({precio_m2_txt}/m²)<br>
        🏢 Expensas: {expensas_txt}<br>
        📐 {sup_txt}<br>
        🛏️ {detalle_txt}<br>
        🏗️ {antiguedad_txt}<br>
        <hr style="margin: 6px 0; border-color: #444;">
        <small style="color: #bbb;">
            🏛️ {inmobiliaria}<br>
            ⏱️ {publicada_txt}
        </small>
    </div>
    """,
    "style": {"backgroundColor": "#171B26", "color": "white", "borderRadius": "8px"},
}

TOOLTIP_CELDAS = {
    "html": """
    <div style="font-family: sans-serif;">
        <b>{mediana_txt}/m²</b><br>
        <small>{cantidad} propiedades en la celda</small>
    </div>
    """,
    "style": {"backgroundColor": "#171B26", "color": "white", "borderRadius": "8px"},
}


# ==================================================
# 2. FUNCIONES AUXILIARES
# ==================================================

def miles(valor, prefijo=""):
    """Número con separador de miles argentino (1.234.567). Si no hay dato devuelve 's/d'."""
    if pd.isna(valor):
        return "s/d"
    return prefijo + f"{valor:,.0f}".replace(",", ".")


def texto_antiguedad(valor):
    """'1-5' -> '1-5 años'; 'A estrenar' queda igual."""
    if pd.isna(valor):
        return "s/d"
    return valor if valor in ESTADOS_OBRA else f"{valor} años"


def colorear(valores, vmin, vmax, paleta, alpha=200):
    """
    Convierte una Serie numérica en una lista de colores [R, G, B, A] siguiendo el degradado.
    Los valores por debajo de vmin / por encima de vmax se pintan con los colores de los extremos.
    """
    if vmax > vmin:
        t = ((valores - vmin) / (vmax - vmin)).clip(0, 1).fillna(0.5).to_numpy()
    else:
        t = np.full(len(valores), 0.5)

    posiciones = np.linspace(0, 1, len(paleta))
    canales = [np.interp(t, posiciones, [color[i] for color in paleta]) for i in range(3)]
    rgba = np.column_stack(canales + [np.full(len(t), alpha)]).astype(int)
    return rgba.tolist()


def escalar(valores, minimo, maximo):
    """Pasa una Serie a un rango [minimo, maximo] (en píxeles). Ignora el 5% más extremo de cada lado."""
    vmin, vmax = valores.quantile([0.05, 0.95])
    if pd.isna(vmin) or vmax <= vmin:
        return pd.Series((minimo + maximo) / 2, index=valores.index)
    t = ((valores - vmin) / (vmax - vmin)).clip(0, 1).fillna(0)
    return minimo + t * (maximo - minimo)


def leyenda(paleta, texto_min, texto_max):
    """Barra de degradado con el significado de los extremos."""
    colores = ", ".join(f"rgb({r},{g},{b})" for r, g, b in paleta)
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:10px; font-size:13px; margin:4px 0 8px 0;">
            <span>{texto_min}</span>
            <div style="flex:1; max-width:320px; height:10px; border-radius:5px;
                        background:linear-gradient(to right, {colores});"></div>
            <span>{texto_max}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def armar_cuadricula(df, tam_metros, min_props):
    """
    Divide el mapa en celdas cuadradas de 'tam_metros' y calcula, por celda,
    la mediana de USD/m² y la cantidad de propiedades. Devuelve un DataFrame
    con una fila por celda (lat/lon = centro de la celda).
    """
    # Grados que equivalen a 'tam_metros' (1° de latitud ≈ 111.320 m; la longitud se achica con el coseno)
    paso_lat = tam_metros / 111_320
    paso_lon = tam_metros / (111_320 * np.cos(np.radians(df["lat"].median())))

    celdas = df.assign(
        fila=np.floor(df["lat"] / paso_lat),
        col=np.floor(df["lon"] / paso_lon),
    )
    resumen = (
        celdas.groupby(["fila", "col"])
        .agg(precio_m2_mediana=("precio_m2", "median"), cantidad=("precio_m2", "size"))
        .reset_index()
    )
    resumen = resumen[resumen["cantidad"] >= min_props].copy()

    resumen["lat"] = (resumen["fila"] + 0.5) * paso_lat
    resumen["lon"] = (resumen["col"] + 0.5) * paso_lon
    resumen["mediana_txt"] = resumen["precio_m2_mediana"].map(lambda v: miles(v, "USD "))
    return resumen


# ==================================================
# 3. DATOS: carga, limpieza y filtros
# ==================================================

# Filtros globales (tipo de propiedad y zona), igual que en tus otras páginas
df_global, tipo = aplicar_filtro_global(obtener_df_limpio())

# Nos quedamos solo con las columnas necesarias (así no viajan los diccionarios
# anidados de Mongo al navegador) y les ponemos nombres cortos
df = df_global.reindex(columns=list(COLUMNAS)).rename(columns=COLUMNAS)
df[COLUMNAS_NUMERICAS] = df[COLUMNAS_NUMERICAS].apply(pd.to_numeric, errors="coerce")

# Sin coordenadas o sin precio por m² no se puede dibujar. También descartamos coordenadas fuera de La Plata
df = df.dropna(subset=["lat", "lon", "precio_m2"])
df = df[
    (df["precio_m2"] > 0)
    & df["lat"].between(LAT_MIN, LAT_MAX)
    & df["lon"].between(LON_MIN, LON_MAX)
]

# --- Filtros propios del mapa (barra lateral) ---
st.sidebar.header("Filtros del mapa")

operaciones = sorted(df["operacion"].dropna().unique())
if operaciones:
    opciones_op = ["Todas"] + operaciones
    por_defecto = opciones_op.index("venta") if "venta" in opciones_op else 0
    op_sel = st.sidebar.selectbox("Operación", opciones_op, index=por_defecto)
    if op_sel != "Todas":
        df = df[df["operacion"] == op_sel]

antiguedades = [a for a in ORDEN_ANTIGUEDAD if a in df["antiguedad"].unique()]
ant_sel = st.sidebar.multiselect("Antigüedad", antiguedades, placeholder="Todas")
if ant_sel:
    df = df[df["antiguedad"].isin(ant_sel)]

inmos = sorted(df["inmobiliaria"].dropna().unique())
inmo_sel = st.sidebar.multiselect("Inmobiliaria", inmos, placeholder="Todas")
if inmo_sel:
    df = df[df["inmobiliaria"].isin(inmo_sel)]

if df.empty:
    st.title("🗺️ Explorador Geográfico del Mercado")
    st.warning("No hay propiedades con coordenadas para los filtros elegidos.")
    st.stop()

df = df.copy()

# ==================================================
# 4. COLUMNAS CALCULADAS
# ==================================================

# Interés = visitas por día publicada (alto = se mueve rápido; bajo = posible sobrevaluada)
df["dias_publicada"] = df["dias_publicada"].fillna(1).clip(lower=1)
df["visitas"] = df["visitas"].fillna(0)
df["visitas_dia"] = df["visitas"] / df["dias_publicada"]

# Los avisos sin expensas suelen venir en 0: los tratamos como "sin dato"
df["expensas"] = df["expensas"].replace(0, np.nan)

# Textos listos para la tarjeta (el tooltip de PyDeck no sabe dar formato a números)
for col in ["direccion", "zona", "tipo", "operacion", "inmobiliaria"]:
    df[col] = df[col].fillna("s/d")
df["operacion"] = df["operacion"].str.capitalize()

df["precio_txt"] = df["precio"].map(lambda v: miles(v, "USD "))
df["precio_m2_txt"] = df["precio_m2"].map(lambda v: miles(v, "USD "))
df["expensas_txt"] = df["expensas"].map(lambda v: miles(v, "$ "))
df["sup_txt"] = df["sup_cubierta"].map(miles) + " m² cub. / " + df["sup_total"].map(miles) + " m² tot."
df["detalle_txt"] = (df["ambientes"].map(miles) + " amb | " + df["banos"].map(miles) + " baños | "
                     + df["cocheras"].map(miles) + " coch.")
df["antiguedad_txt"] = df["antiguedad"].map(texto_antiguedad)
df["publicada_txt"] = (
    "Publicada hace " + df["dias_publicada"].astype(int).astype(str) + " días | "
    + df["visitas"].astype(int).astype(str) + " visitas ("
    + df["visitas_dia"].round(1).astype(str).str.replace(".", ",", regex=False) + "/día)"
)

# ==================================================
# 5. PÁGINA
# ==================================================

st.title("🗺️ Explorador Geográfico del Mercado")
st.caption(f"Tipo de propiedad: **{tipo}** | Mostrando **{miles(len(df))}** propiedades con ubicación.")

m1, m2, m3 = st.columns(3)
m1.metric("Mediana USD/m²", miles(df["precio_m2"].median()))
m2.metric("Mediana de precio", miles(df["precio"].median(), "USD "))
m3.metric("Interés mediano (visitas/día)", f"{df['visitas_dia'].median():.1f}".replace(".", ","))

# El mapa arranca centrado en donde están las propiedades
vista = pdk.ViewState(latitude=df["lat"].median(), longitude=df["lon"].median(),
                      zoom=ZOOM_INICIAL, pitch=0)

tab_puntos, tab_calor = st.tabs(["📍 Explorador de Propiedades", "🔥 Mapa de Calor ($/m²)"])

# --------------------------------------------------
# Pestaña 1: un punto por propiedad
# --------------------------------------------------
with tab_puntos:
    col_color, col_tamano = st.columns(2)
    color_por = col_color.radio("Color del punto", ["Precio por m²", "Interés (visitas por día)"],
                                horizontal=True)
    tamano_por = col_tamano.radio("Tamaño del punto", ["Superficie total", "Precio total", "Visitas", "Fijo"],
                                  horizontal=True)

    # Color: degradado entre el percentil 5 y el 95 para que los extremos no "aplasten" la escala
    if color_por == "Precio por m²":
        valor_color, paleta = df["precio_m2"], PALETA_PRECIO
        texto_min, texto_max = "Más barato", "Más caro"
    else:
        valor_color, paleta = df["visitas_dia"], PALETA_INTERES
        texto_min, texto_max = "Poco interés (posible sobrevaluada)", "Mucho interés (se mueve rápido)"
    vmin, vmax = valor_color.quantile([0.05, 0.95])
    df["color"] = colorear(valor_color, vmin, vmax, paleta)

    # Tamaño: radio en píxeles entre 4 y 16 (no cambia al hacer zoom)
    columna_tamano = {"Superficie total": "sup_total", "Precio total": "precio", "Visitas": "visitas"}
    if tamano_por == "Fijo":
        df["radio"] = 7
    else:
        serie = df[columna_tamano[tamano_por]]
        df["radio"] = escalar(serie.fillna(serie.median()), 4, 16)

    leyenda(paleta, texto_min, texto_max)

    # Solo viajan al navegador las columnas que usa el mapa y la tarjeta
    columnas_capa = ["lon", "lat", "color", "radio", "direccion", "zona", "tipo", "operacion",
                     "precio_txt", "precio_m2_txt", "expensas_txt", "sup_txt", "detalle_txt",
                     "antiguedad_txt", "inmobiliaria", "publicada_txt"]

    capa_puntos = pdk.Layer(
        "ScatterplotLayer",
        data=df[columnas_capa],
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius="radio",
        radius_units="pixels",
        stroked=True,
        get_line_color=[255, 255, 255, 90],
        line_width_min_pixels=1,
        pickable=True,          # necesario para que aparezca la tarjeta al pasar el mouse
        auto_highlight=True,
    )

    st.pydeck_chart(
        pdk.Deck(layers=[capa_puntos], initial_view_state=vista, map_provider="carto",
                 map_style=ESTILO_MAPA, tooltip=TOOLTIP_PUNTOS),
        height=650,
    )
    st.caption("Pasá el mouse sobre un punto para ver la ficha de la propiedad.")

# --------------------------------------------------
# Pestaña 2: mapa de calor por cuadrícula
# --------------------------------------------------
with tab_calor:
    c1, c2, c3 = st.columns(3)
    modo = c1.radio("Pintar celdas según", ["Precio por m² (mediana)", "Cantidad de propiedades"],
                    horizontal=True)
    tam_celda = c2.slider("Tamaño de la celda (metros)", 100, 600, 250, step=50)
    min_props = c3.slider("Mínimo de propiedades por celda", 1, 10, 3)

    celdas = armar_cuadricula(df, tam_celda, min_props)

    if celdas.empty:
        st.info("Ninguna celda llega al mínimo de propiedades. Probá con celdas más grandes o un mínimo menor.")
    else:
        if modo.startswith("Precio"):
            valor_celda, paleta = celdas["precio_m2_mediana"], PALETA_PRECIO
            texto_min, texto_max = "Más barato", "Más caro"
        else:
            valor_celda, paleta = celdas["cantidad"], PALETA_DENSIDAD
            texto_min, texto_max = "Pocas propiedades", "Muchas propiedades"
        vmin, vmax = valor_celda.quantile([0.05, 0.95])
        celdas["color"] = colorear(valor_celda, vmin, vmax, paleta, alpha=170)

        leyenda(paleta, texto_min, texto_max)

        capa_celdas = pdk.Layer(
            "GridCellLayer",
            data=celdas[["lon", "lat", "color", "mediana_txt", "cantidad"]],
            get_position=["lon", "lat"],
            cell_size=tam_celda,    # lado de la celda en metros
            coverage=0.95,          # deja un borde finito entre celdas
            get_fill_color="color",
            extruded=False,         # plano, sin altura
            pickable=True,
            auto_highlight=True,
        )

        st.pydeck_chart(
            pdk.Deck(layers=[capa_celdas], initial_view_state=vista, map_provider="carto",
                     map_style=ESTILO_MAPA, tooltip=TOOLTIP_CELDAS),
            height=650,
        )
        st.caption(f"{miles(len(celdas))} celdas con al menos {min_props} propiedades. "
                   "Las celdas con menos quedan sin pintar para no mostrar valores poco representativos.")