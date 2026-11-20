"""
PÁGINA DE STREAMLIT: Análisis por Zona
=======================================
Ubicación: pages/zona_especifica.py  (con utils/backend.py disponible para importar)

Lógica general:
  1. Se cargan DOS colecciones de Mongo: "censos" (una fila por radio censal) e
     "inmuebles" (una fila por aviso ONLINE).
  2. Todo se resume en UNA tabla por zona ("df_zonas"): una fila = una zona, con
     columnas de censo (% de jubilados, edades, etc.) y de avisos (cantidad, USD/m², etc.).
  3. El usuario elige una zona arriba de todo y cada sección analiza esa zona
     comparándola contra la tabla completa.

Filtros:
  - Barra lateral: SOLO el tipo de propiedad (Todas / Departamento / Casa / PH).
    Afecta únicamente a los datos de avisos (el censo no tiene "tipo").
  - Arriba de la página: selector grande de zona.

Cómo mover secciones: cada sección es una función "seccion_xxx()". El orden en que
aparecen en la página es la lista del final del archivo (sección 7): cortá y pegá
las líneas para reordenarlas, o borrá una para sacarla.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Análisis por Zona", layout="wide")

from utils.backend import obtener_df_limpio, obtener_df_censo

# ==================================================
# 1. CONFIGURACIÓN (lo que más probablemente quieras tocar)
# ==================================================

# Solo se consideran avisos de esta operación. Poné None para usar todos.
# (Sumar USD o calcular USD/m² mezclando alquileres con ventas no tiene sentido)
OPERACION = "venta"

# Mínimo de avisos en una zona para calcular promedios/medianas (USD/m², días, visitas promedio).
# Con menos avisos el valor no es representativo y se muestra como "sin datos".
MIN_AVISOS = 10

# Cuartiles que separan Bajo / Medio / Alto en los indicadores
CUARTIL_BAJO, CUARTIL_ALTO = 0.25, 0.75

# Colores de los gráficos
COLOR_BARRAS = "#4C78A8"      # azul: barras normales
COLOR_RESALTADO = "#F58518"   # naranja: la zona elegida

# Colores del semáforo
VERDE, AMARILLO, ROJO, GRIS = "#2E9E5B", "#D9A400", "#D64545", "#8A8F98"

# --- Columnas del censo ---
COL_POBLACION = "Población total (en hogares familiares)"   # base de todos los porcentajes
COL_HOGARES = "Total de hogares"

# Cada porcentaje se calcula así:  suma de las columnas de conteo de la zona / población de la zona * 100
# Clave = nombre de la columna resultante (se guarda como "pct_<clave>")
# Valor = columnas de CONTEO del censo que se suman
PORCENTAJES_CENSO = {
    "edad_0_17": ["Población de 0 a 17 años"],
    "edad_18_29": ["Población de 18 a 29 años"],
    "edad_30_54": ["Población de 30 a 54 años"],
    "edad_55_69": ["Población de 55 a 69 años"],
    "edad_70_mas": ["Población de 70 años y más"],
    "jubilados": ["Personas que reciben jubilación (65 años y más)"],
    "universitarios": ["Población de 18 y más con universitario completo o más"],
    "sec_incompleto": ["Población de 18 y más con primaria incompleta o menos",
                       "Población de 18 y más con primaria completa sin secundario completo"],
    "obra_social": ["Obra social o prepaga (incluye PAMI)"],
    "planes_estatales": ["Programas o planes estatales de salud"],
    "solo_publica": ["Solo salud pública"],
}

# Gráfico de edades, en el orden en que se muestra (de más joven a más grande)
GRUPOS_EDAD = [("0 a 17", "edad_0_17"), ("18 a 29", "edad_18_29"), ("30 a 54", "edad_30_54"),
               ("55 a 69", "edad_55_69"), ("70 o más", "edad_70_mas")]

# Gráficos "Top 5": (título, clave de PORCENTAJES_CENSO, descripción del eje)
TOP5_CENSO = [
    ("Jubilados", "jubilados", "% de la población que cobra jubilación (65 años y más)"),
    ("Universitarios recibidos", "universitarios", "% de la población de 18 y más con universitario completo o más"),
    ("Secundario incompleto", "sec_incompleto", "% de la población de 18 y más sin secundario completo"),
]

# Gráfico de cobertura de salud: (nombre a mostrar, clave de PORCENTAJES_CENSO)
OBRA_SOCIAL = [("Obra social o prepaga (incluye PAMI)", "obra_social"),
               ("Programas o planes estatales", "planes_estatales"),
               ("Solo salud pública", "solo_publica")]

# --- Indicadores con semáforo ---
# ascendente=True  -> VERDE cuando el valor es bajo, AMARILLO medio, ROJO alto
# ascendente=False -> ROJO cuando el valor es bajo, AMARILLO medio, VERDE alto
# etiquetas        -> texto que se muestra para (bajo, medio, alto)
# columna          -> columna de df_zonas con el valor del indicador
INDICADORES = [
    dict(titulo="Personas por hogar", columna="personas_hogar", ascendente=True,
         etiquetas=("Bajo", "Medio", "Alto"), decimales=2, usa_minimo=False),
    dict(titulo="Precio por m² (USD)", columna="precio_m2", ascendente=False,
         etiquetas=("Bajo", "Medio", "Alto"), decimales=0, usa_minimo=True),
    dict(titulo="Publicaciones cada 1.000 hab.", columna="avisos_x_mil", ascendente=True,
         etiquetas=("Bajo", "Medio", "Alto"), decimales=1, usa_minimo=False),
    dict(titulo="Días en el mercado (promedio)", columna="dias", ascendente=True,
         etiquetas=("Bajo", "Medio", "Alto"), decimales=0, usa_minimo=True),
]

# --- Comparación global (sección 7) ---
# porcentaje=True  -> se muestra qué % del total del mercado representa cada zona
# porcentaje=False -> se muestra el valor tal cual (con "unidad" al lado)
VARIABLES_GLOBALES = {
    "Plata de mercado (USD publicados)": dict(columna="usd_total", porcentaje=True),
    "Cantidad de avisos": dict(columna="n_avisos", porcentaje=True),
    "Metros cuadrados publicados": dict(columna="m2_total", porcentaje=True),
    "Precio por m² (USD)": dict(columna="precio_m2", porcentaje=False, unidad=" USD/m²", decimales=0),
    "Tiempo en el mercado (días promedio)": dict(columna="dias", porcentaje=False, unidad=" días", decimales=0),
    "Visitas promedio por aviso": dict(columna="visitas_prom", porcentaje=False, unidad=" visitas", decimales=1),
    "Visitas totales": dict(columna="visitas_total", porcentaje=False, unidad=" visitas", decimales=0),
}


# ==================================================
# 2. FUNCIONES AUXILIARES
# ==================================================

def fmt(valor, decimales=0, sufijo=""):
    """Formato argentino: 1.234,5. Si no hay dato devuelve 's/d'."""
    if pd.isna(valor):
        return "s/d"
    texto = f"{valor:,.{decimales}f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return texto + sufijo


def insignia(texto, color):
    """Etiqueta de color (HTML) para mostrar Alto / Medio / Bajo."""
    return (f'<span style="background:{color}; color:white; padding:3px 14px; '
            f'border-radius:14px; font-weight:600;">{texto}</span>')


def barras_verticales(etiquetas, valores, textos, eje_y, key):
    """Gráfico de columnas. 'etiquetas' mantiene el orden que se le pasa."""
    datos = pd.DataFrame({"categoria": etiquetas, "valor": valores, "texto": textos})
    fig = px.bar(datos, x="categoria", y="valor", text="texto",
                 category_orders={"categoria": list(etiquetas)},
                 labels={"categoria": "", "valor": eje_y})
    fig.update_traces(marker_color=COLOR_BARRAS, textposition="outside", cliponaxis=False)
    fig.update_yaxes(range=[0, max(np.nanmax(valores) * 1.2, 1)])
    fig.update_layout(height=380, bargap=0.35)
    st.plotly_chart(fig, width="stretch", key=key)


def barras_horizontales(datos, eje_x, key, colores=None, altura=320):
    """
    Gráfico de barras acostadas. El primer renglón de 'datos' queda ARRIBA.
    'datos' necesita las columnas: etiqueta, valor, texto, grupo.
    'grupo' define el color de cada barra (según el diccionario 'colores').
    """
    colores = colores or {"Zonas": COLOR_BARRAS}
    fig = px.bar(datos, x="valor", y="etiqueta", orientation="h", color="grupo", text="texto",
                 color_discrete_map=colores,
                 category_orders={"etiqueta": datos["etiqueta"].tolist()},
                 labels={"valor": eje_x, "etiqueta": ""})
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(range=[0, datos["valor"].max() * 1.25])   # espacio para el texto
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(height=altura, bargap=0.3, legend_title_text="",
                      showlegend=datos["grupo"].nunique() > 1)
    st.plotly_chart(fig, width="stretch", key=key)


def armar_top5(serie, zona, decimales=1, sufijo=" %"):
    """
    Devuelve las 5 zonas con mayor valor. Si 'zona' no está entre ellas,
    se agrega como sexta barra, con su puesto en el ranking completo.
    """
    serie = serie.dropna().sort_values(ascending=False)
    top = serie.head(5)
    if zona not in top.index and zona in serie.index:
        top = pd.concat([top, serie.loc[[zona]]])

    datos = pd.DataFrame({"zona": top.index, "valor": top.values})
    puesto = datos["zona"].map(lambda z: serie.index.get_loc(z) + 1)
    datos["etiqueta"] = puesto.astype(str) + ". " + datos["zona"]
    datos["texto"] = datos["valor"].map(lambda v: fmt(v, decimales, sufijo))
    datos["grupo"] = np.where(datos["zona"] == zona, "Zona elegida", "Top 5")
    return datos


# ==================================================
# 3. CARGA DE DATOS Y FILTRO GLOBAL (solo tipo de propiedad)
# ==================================================

df_censo_raw = obtener_df_censo()
df_inmuebles_raw = obtener_df_limpio()

# --- Inmuebles: nos quedamos con las columnas necesarias y las pasamos a número ---
COLUMNAS_INMUEBLES = ["zona", "realEstateType", "operationType", "publisher_name", "prices_amount",
                      "supTotal_value", "precio_m2_tot", "posting_antiquity", "visitas"]
df_avisos = df_inmuebles_raw.reindex(columns=COLUMNAS_INMUEBLES).dropna(subset=["zona"]).copy()
columnas_num = ["prices_amount", "supTotal_value", "precio_m2_tot", "posting_antiquity", "visitas"]
df_avisos[columnas_num] = df_avisos[columnas_num].apply(pd.to_numeric, errors="coerce")

if OPERACION:
    df_avisos = df_avisos[df_avisos["operationType"] == OPERACION]

# --- Filtro global: tipo de propiedad (misma clave que usa backend.aplicar_filtro_global) ---
st.sidebar.header("▽ Filtros Globales")
opciones_tipo = ["Todas"] + list(df_avisos["realEstateType"].dropna().unique())
tipo_sel = st.sidebar.selectbox("Tipo de Propiedad:", options=opciones_tipo, key="filtro_tipo_inmueble")

# df_avisos_todos_tipos: sin filtro de tipo (lo usa el gráfico de tipos de inmueble)
# df_avisos:             con filtro de tipo (lo usa todo lo demás)
df_avisos_todos_tipos = df_avisos
if tipo_sel != "Todas":
    df_avisos = df_avisos[df_avisos["realEstateType"] == tipo_sel]


# ==================================================
# 4. TABLA POR ZONA (una fila = una zona)
# ==================================================

def armar_tabla_censo(df_censo):
    """Suma los radios censales de cada zona y calcula los porcentajes ponderados por población."""
    columnas = {COL_POBLACION, COL_HOGARES}
    for cols in PORCENTAJES_CENSO.values():
        columnas.update(cols)
    columnas = sorted(columnas)

    base = df_censo.reindex(columns=["zona"] + columnas).dropna(subset=["zona"]).copy()
    base[columnas] = base[columnas].apply(pd.to_numeric, errors="coerce")
    por_zona = base.groupby("zona")[columnas].sum(min_count=1)

    tabla = pd.DataFrame({
        "poblacion": por_zona[COL_POBLACION],
        "hogares": por_zona[COL_HOGARES],
        "radios": base.groupby("zona").size(),
    })
    poblacion = tabla["poblacion"].replace(0, np.nan)
    for clave, cols in PORCENTAJES_CENSO.items():
        tabla[f"pct_{clave}"] = por_zona[cols].sum(axis=1, min_count=1) / poblacion * 100
    return tabla


def armar_tabla_avisos(df):
    """Resume los avisos por zona: cantidad, USD totales, m² totales, USD/m², días y visitas."""
    g = df.groupby("zona")
    tabla = pd.DataFrame({
        "n_avisos": g.size(),
        "usd_total": g["prices_amount"].sum(),
        "m2_total": g["supTotal_value"].sum(),
        "visitas_total": g["visitas"].sum(),
    })
    # Promedios y medianas: solo si la zona tiene al menos MIN_AVISOS avisos con ese dato
    tabla["precio_m2"] = g["precio_m2_tot"].median().where(g["precio_m2_tot"].count() >= MIN_AVISOS)
    tabla["dias"] = g["posting_antiquity"].mean().where(g["posting_antiquity"].count() >= MIN_AVISOS)
    tabla["visitas_prom"] = g["visitas"].mean().where(g["visitas"].count() >= MIN_AVISOS)
    return tabla


tabla_censo = armar_tabla_censo(df_censo_raw)
tabla_avisos = armar_tabla_avisos(df_avisos)

# Unimos censo + avisos por nombre de zona. "outer": no perdemos zonas que estén en una sola fuente
df_zonas = tabla_censo.join(tabla_avisos, how="outer")
for col in ["n_avisos", "usd_total", "m2_total", "visitas_total"]:
    df_zonas[col] = df_zonas[col].fillna(0)      # zona sin avisos = 0 avisos

# Indicadores que combinan censo + avisos
poblacion = df_zonas["poblacion"].replace(0, np.nan)
df_zonas["personas_hogar"] = poblacion / df_zonas["hogares"].replace(0, np.nan)
df_zonas["avisos_x_mil"] = df_zonas["n_avisos"] / poblacion * 1000    # sobreoferta: avisos cada 1.000 habitantes


# ==================================================
# 5. TÍTULO Y SELECTOR DE ZONA
# ==================================================

st.title("📍 Análisis por Zona")

if tabla_censo.empty:
    st.error("No se encontraron datos de censo para armar el análisis.")
    st.stop()

# Estilo: agranda el selector de zona (solo el que está dentro del contenedor "selector_zona")
st.markdown("""
<style>
.st-key-selector_zona div[data-baseweb="select"] > div { min-height: 3.4rem; font-size: 1.25rem; }
</style>
""", unsafe_allow_html=True)

zonas = sorted(tabla_censo.index)
with st.container(border=True, key="selector_zona"):
    st.markdown("### Elegí la zona que querés analizar")
    zona_sel = st.selectbox("Zona", zonas, key="zona_analisis", label_visibility="collapsed")

# Datos de la zona elegida
fila_zona = df_zonas.loc[zona_sel]
df_avisos_zona = df_avisos[df_avisos["zona"] == zona_sel]                           # con filtro de tipo
df_avisos_zona_todos = df_avisos_todos_tipos[df_avisos_todos_tipos["zona"] == zona_sel]   # sin filtro de tipo

st.caption(f"**{zona_sel}** | {fmt(fila_zona['poblacion'])} habitantes | {fmt(fila_zona['radios'])} radios censales | "
           f"{fmt(fila_zona['n_avisos'])} avisos ({tipo_sel.lower() if tipo_sel != 'Todas' else 'todos los tipos'})")


# ==================================================
# 6. SECCIONES
# ==================================================

def seccion_demografia():
    """Distribución de edades de la zona (% de la población), de más joven a más grande."""
    st.subheader("1. Demográficas", divider="blue")
    st.markdown("Cómo se reparten las edades en la zona (% sobre el total de habitantes).")

    valores = [fila_zona[f"pct_{clave}"] for _, clave in GRUPOS_EDAD]
    if pd.isna(valores).all():
        st.info("Esta zona no tiene datos de edades en el censo.")
        return
    barras_verticales(
        etiquetas=[nombre for nombre, _ in GRUPOS_EDAD],
        valores=valores,
        textos=[fmt(v, 1, " %") for v in valores],
        eje_y="% de la población",
        key="grafico_edades",
    )


def seccion_top5_censo():
    """Para cada variable del censo: top 5 de zonas y, si hace falta, la zona elegida como 6ª barra."""
    st.subheader("2. Cómo se ubica la zona frente al resto", divider="blue")
    st.caption("Se muestran las 5 zonas con mayor valor. Si la zona elegida no está entre ellas, "
               "aparece como sexta barra (naranja) con su puesto en el ranking.")

    for titulo, clave, descripcion in TOP5_CENSO:
        st.markdown(f"**{titulo}**")
        serie = df_zonas[f"pct_{clave}"]
        if pd.isna(serie.get(zona_sel)):
            st.caption("La zona elegida no tiene este dato en el censo; se muestra solo el top 5.")
        barras_horizontales(
            armar_top5(serie, zona_sel),
            eje_x=descripcion,
            key=f"top5_{clave}",
            colores={"Top 5": COLOR_BARRAS, "Zona elegida": COLOR_RESALTADO},
        )


def seccion_obra_social():
    """Cobertura de salud de la zona (3 columnas)."""
    st.subheader("3. Cobertura de salud", divider="blue")
    st.markdown("Qué % de la población tiene cada tipo de cobertura.")

    valores = [fila_zona[f"pct_{clave}"] for _, clave in OBRA_SOCIAL]
    if pd.isna(valores).all():
        st.info("Esta zona no tiene datos de cobertura de salud en el censo.")
        return
    barras_verticales(
        etiquetas=[nombre for nombre, _ in OBRA_SOCIAL],
        valores=valores,
        textos=[fmt(v, 1, " %") for v in valores],
        eje_y="% de la población",
        key="grafico_salud",
    )


def tarjeta_indicador(columna_st, ind):
    """Una tarjeta: valor de la zona + etiqueta de color según cuartiles de TODAS las zonas."""
    valores_zonas = df_zonas[ind["columna"]].dropna()
    valor = fila_zona[ind["columna"]]

    with columna_st, st.container(border=True):
        st.caption(ind["titulo"])

        # Sin dato (zona con pocos avisos, sin censo, etc.)
        if pd.isna(valor) or valores_zonas.empty:
            st.markdown("### s/d")
            st.markdown(insignia("Sin datos suficientes", GRIS), unsafe_allow_html=True)
            if ind["usa_minimo"]:
                st.caption(f"Se necesitan al menos {MIN_AVISOS} avisos en la zona.")
            return

        # Cuartiles calculados con todas las zonas
        q1, q3 = valores_zonas.quantile([CUARTIL_BAJO, CUARTIL_ALTO])
        if valor < q1:
            nivel = 0           # bajo
        elif valor > q3:
            nivel = 2           # alto
        else:
            nivel = 1           # medio

        # El color depende de "ascendente" (ver INDICADORES)
        colores = [VERDE, AMARILLO, ROJO] if ind["ascendente"] else [ROJO, AMARILLO, VERDE]

        d = ind["decimales"]
        st.markdown(f"### {fmt(valor, d)}")
        st.markdown(insignia(ind["etiquetas"][nivel], colores[nivel]), unsafe_allow_html=True)
        st.caption(f"Entre zonas: Q1 {fmt(q1, d)} | Q3 {fmt(q3, d)}")


def seccion_indicadores():
    """Tarjetas con semáforo: la zona comparada contra los cuartiles de todas las zonas."""
    st.subheader("4. Indicadores de la zona", divider="blue")
    st.caption("Cada valor se compara con el resto de las zonas: debajo del Q1 es bajo, entre Q1 y Q3 es medio "
               "y por encima del Q3 es alto. El color (verde / amarillo / rojo) se define en INDICADORES con "
               "la opción 'ascendente'. Los indicadores de avisos respetan el filtro de tipo.")

    columnas = st.columns(len(INDICADORES))
    for columna_st, ind in zip(columnas, INDICADORES):
        tarjeta_indicador(columna_st, ind)


def seccion_inmobiliarias():
    """Top 5 inmobiliarias con más avisos en la zona."""
    st.subheader("5. Top 5 inmobiliarias de la zona", divider="blue")

    if df_avisos_zona.empty:
        st.info("No hay avisos en esta zona con los filtros elegidos.")
        return

    conteo = df_avisos_zona["publisher_name"].fillna("Sin dato").value_counts().head(5)
    total = len(df_avisos_zona)
    datos = pd.DataFrame({"etiqueta": conteo.index, "valor": conteo.values, "grupo": "Zonas"})
    datos["texto"] = [f"{fmt(v)} ({fmt(v / total * 100, 0, ' %')})" for v in datos["valor"]]

    st.caption(f"Cantidad de avisos de cada inmobiliaria (entre paréntesis, % de los {fmt(total)} avisos de la zona).")
    barras_horizontales(datos, eje_x="Cantidad de avisos", key="top_inmobiliarias")


def seccion_tipos():
    """Cuántos departamentos / casas / PH hay publicados en la zona (ignora el filtro de tipo)."""
    st.subheader("6. Tipos de inmueble en la zona", divider="blue")
    st.caption("Este gráfico no usa el filtro de tipo de la barra lateral: muestra todos los tipos.")

    if df_avisos_zona_todos.empty:
        st.info("No hay avisos en esta zona.")
        return

    conteo = df_avisos_zona_todos["realEstateType"].fillna("Sin dato").value_counts()
    total = conteo.sum()
    barras_verticales(
        etiquetas=list(conteo.index),
        valores=list(conteo.values),
        textos=[f"{fmt(v)} ({fmt(v / total * 100, 0, ' %')})" for v in conteo.values],
        eje_y="Cantidad de avisos",
        key="grafico_tipos",
    )


def seccion_ranking_global():
    """Top 5 con más y top 5 con menos entre TODAS las zonas (no usa la zona elegida)."""
    st.subheader("7. Comparación de los top globales", divider="blue")
    st.caption("Esta sección no usa la zona elegida arriba: compara todas las zonas entre sí "
               "(respeta solo el filtro de tipo). Las zonas con valor cero no entran en el ranking.")

    nombre = st.selectbox("Variable a comparar", list(VARIABLES_GLOBALES), key="variable_global")
    cfg = VARIABLES_GLOBALES[nombre]

    serie = df_zonas[cfg["columna"]]
    if cfg["porcentaje"]:
        serie = serie / serie.sum() * 100          # qué % del total del mercado representa cada zona
        formato = lambda v: fmt(v, 2, " %")
    else:
        formato = lambda v: fmt(v, cfg["decimales"], cfg["unidad"])
    serie = serie.dropna()
    serie = serie[serie > 0]

    if serie.empty:
        st.info("No hay datos para esta variable con los filtros elegidos.")
        return

    def datos_ranking(top):
        return pd.DataFrame({"etiqueta": top.index, "valor": top.values, "grupo": "Zonas",
                             "texto": [formato(v) for v in top.values]})

    col_mas, col_menos = st.columns(2)
    with col_mas:
        st.markdown("**🔝 Top 5 con más**")
        barras_horizontales(datos_ranking(serie.nlargest(5)), eje_x=nombre, key="ranking_mas")
    with col_menos:
        st.markdown("**🔻 Top 5 con menos**")
        barras_horizontales(datos_ranking(serie.nsmallest(5)), eje_x=nombre, key="ranking_menos")


# ==================================================
# 7. ORDEN DE LA PÁGINA (cortá y pegá líneas para mover secciones)
# ==================================================

seccion_demografia()
seccion_top5_censo()
seccion_obra_social()
seccion_indicadores()
seccion_inmobiliarias()
seccion_tipos()
seccion_ranking_global()