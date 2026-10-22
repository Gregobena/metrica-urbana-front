import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.backend import obtener_df_limpio, obtener_df_censo
st.set_page_config(layout="wide")


# ----------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------

# Nombre que se ve en el filtro -> columna del censo
INDICADORES_DEMO = {
    "Jubilados y pensionados (65 años y más)": "Personas que reciben jubilación o pensión (65 años y más)",
    "Población de 18 a 29 años": "Población de 18 a 29 años",
    "Población de 30 a 54 años": "Población de 30 a 54 años",
    "Universitario completo o más (18 y más)": "Población de 18 y más con universitario completo o más",
}

# Nombre que se ve en el filtro -> columna de la tabla de avisos por zona
METRICAS_AVISOS = {
    "USD totales en avisos (% del total)": "USD total (%)",
    "M² en avisos (% del total)": "M2 total (%)",
    "USD por m² (promedio)": "USD/m2 promedio",
    "Visitas (% del total)": "Visitas (%)",
    "Tiempo publicado en días (promedio)": "Días publicado",
    "Antigüedad del inmueble en años (promedio)": "Antigüedad (años)",
}

# Opciones del filtro de precio promedio: nombre -> (columna, valor)
# La comparación de tipos no distingue mayúsculas ("PH" == "Ph")
TIPOS = ["Apartamento", "PH", "Casa"]
OPCIONES_INMUEBLE = {}
for n in range(1, 6):
    nombre = f"{n} ambiente" if n == 1 else f"{n} ambientes"
    OPCIONES_INMUEBLE[nombre] = ("ambientes", n)
for tipo in TIPOS:
    OPCIONES_INMUEBLE[tipo] = ("realEstateType", tipo)

# Solo las columnas que usa esta página: cada llamada a una función
# cacheada copia el df, así que cuanto más chico, más rápido.
COLUMNAS_AVISOS = [
    "idAviso", "zona", "prices_currency", "prices_amount", "supTotal_value",
    "precio_m2_tot", "visitas", "posting_antiquity", "antiguedad",
    "ambientes", "realEstateType",
]
COLUMNAS_NUMERICAS = [
    "prices_amount", "supTotal_value", "precio_m2_tot", "visitas",
    "posting_antiquity", "antiguedad", "ambientes",
]


# ----------------------------------------------------------------------
# Datos (todo cacheado, sin pasar dataframes como argumento para que
# streamlit no tenga que hashearlos en cada interacción)
# ----------------------------------------------------------------------

@st.cache_data(ttl=7200)
def calcular_demografia_zonas():
    """
    Por zona: suma las cantidades de todos los radios censales y divide
    por la suma de la población total de la zona (así el % pesa por población).
    """
    df_censo = obtener_df_censo()

    columnas = list(INDICADORES_DEMO.values()) + ["Población total", "Total de hogares"]
    sumas = df_censo.groupby("zona")[columnas].sum()

    # Evitamos dividir por cero
    sumas = sumas[(sumas["Población total"] > 0) & (sumas["Total de hogares"] > 0)]

    demo = pd.DataFrame(index=sumas.index)
    for nombre, columna in INDICADORES_DEMO.items():
        demo[nombre] = sumas[columna] / sumas["Población total"] * 100

    demo["Personas por hogar"] = sumas["Población total"] / sumas["Total de hogares"]
    demo["Población total"] = sumas["Población total"]

    return demo.round(2).reset_index()


@st.cache_data(ttl=7200)
def preparar_avisos():
    """Avisos en USD y con zona (para no mezclar monedas), solo con las columnas necesarias."""
    df = obtener_df_limpio()
    df = df[(df["prices_currency"] == "USD") & (df["zona"].notna())]
    df = df[COLUMNAS_AVISOS].copy()

    # Aseguramos tipos numéricos y sacamos infinitos (ej: m² = 0)
    for col in COLUMNAS_NUMERICAS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["precio_m2_tot"] = df["precio_m2_tot"].replace([np.inf, -np.inf], np.nan)

    return df


@st.cache_data(ttl=7200)
def calcular_tabla_avisos():
    """Una fila por zona con los totales y promedios de sus avisos."""
    df = preparar_avisos()

    tabla = df.groupby("zona").agg(**{
        "USD total": ("prices_amount", "sum"),
        "M2 total": ("supTotal_value", "sum"),
        "USD/m2 promedio": ("precio_m2_tot", "mean"),
        "Visitas": ("visitas", "sum"),
        "Días publicado": ("posting_antiquity", "mean"),
        "Antigüedad (años)": ("antiguedad", "mean"),
        "Avisos": ("idAviso", "count"),
    }).reset_index()

    # Market share: qué % del total representa cada zona
    for columna in ["USD total", "M2 total", "Visitas"]:
        tabla[columna + " (%)"] = tabla[columna] / tabla[columna].sum() * 100

    return tabla.round(2)


# ----------------------------------------------------------------------
# Gráficos
# ----------------------------------------------------------------------

def formato_etiqueta(columna):
    """Devuelve (sufijo, decimales) para las etiquetas de las barras."""
    if columna.endswith("(%)"):
        return " %", 2
    if columna in ("promedio", "USD/m2 promedio"):
        return "", 0
    return "", 2


def grafico_barras(df, columna, titulo, color="#1f77b4", sufijo=None, decimales=None):
    """Barras horizontales, el valor más alto queda arriba."""
    suf_auto, dec_auto = formato_etiqueta(columna)
    sufijo = suf_auto if sufijo is None else sufijo
    decimales = dec_auto if decimales is None else decimales

    df = df.sort_values(columna, ascending=True)

    fig = px.bar(df, x=columna, y="zona", orientation="h", title=titulo)
    fig.update_traces(
        marker_color=color,
        texttemplate=f"%{{x:,.{decimales}f}}{sufijo}",
        textposition="outside",
        cliponaxis=False,
    )
    fig.update_layout(
        xaxis_title=None,
        yaxis_title=None,
        height=40 * len(df) + 120,
        margin=dict(l=10, r=60),
    )
    return fig


def grafico_dispersion(df, x, y):
    """Dispersión por zona con recta de tendencia. Devuelve (figura, correlación)."""
    fig = px.scatter(df, x=x, y=y, size="Avisos", hover_name="zona")

    datos = df[[x, y]].dropna()
    correlacion = None

    # La correlación y la recta necesitan variación en ambos ejes
    if len(datos) >= 3 and datos[x].nunique() > 1 and datos[y].nunique() > 1:
        pendiente, ordenada = np.polyfit(datos[x], datos[y], 1)
        xs = np.array([datos[x].min(), datos[x].max()])
        fig.add_trace(go.Scatter(
            x=xs,
            y=pendiente * xs + ordenada,
            mode="lines",
            name="Tendencia",
        ))
        correlacion = datos[x].corr(datos[y])

    return fig, correlacion


def grafico_por_grupos(df, x, y):
    """
    Divide las zonas en 4 grupos según la variable x (de menor a mayor) y
    muestra el valor promedio de y en cada grupo. Sirve para ver el "progreso".
    Devuelve None si hay pocas zonas.
    """
    datos = df[[x, y]].dropna().copy()
    if len(datos) < 8:
        return None

    # rank(method="first") evita errores por valores repetidos
    etiquetas = ["Grupo 1 (valor más bajo)", "Grupo 2", "Grupo 3", "Grupo 4 (valor más alto)"]
    datos["grupo"] = pd.qcut(datos[x].rank(method="first"), 4, labels=etiquetas)

    resumen = datos.groupby("grupo", observed=True).agg(
        precio=(y, "mean"),
        zonas=(y, "count"),
    ).reset_index()

    fig = px.bar(
        resumen, x="grupo", y="precio", text="precio", hover_data=["zonas"],
        title=f"{y} según el grupo de zonas por '{x}'",
    )
    fig.update_traces(marker_color="#ff7f0e", texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(xaxis_title=None, yaxis_title=y)
    return fig


def precio_promedio_por_zona(df, opcion, metrica, min_avisos):
    """Precio promedio por zona para un tipo de inmueble o cantidad de ambientes."""
    columna, valor = OPCIONES_INMUEBLE[opcion]

    if columna == "realEstateType":
        df = df[df[columna].astype(str).str.lower() == valor.lower()]
    else:
        df = df[df[columna] == valor]

    tabla = df.groupby("zona").agg(
        promedio=(metrica, "mean"),
        cantidad=("idAviso", "count"),
    ).reset_index()

    tabla = tabla[(tabla["cantidad"] >= min_avisos) & tabla["promedio"].notna()].copy()
    tabla["promedio"] = tabla["promedio"].round(0)
    return tabla


# ----------------------------------------------------------------------
# Página
# ----------------------------------------------------------------------

st.title("Comparación de las zonas en La Plata")
st.caption(
    "Esta página compara todas las zonas de la ciudad en dos aspectos: "
    "quiénes viven en ellas (datos del censo) y cómo se comporta el mercado "
    "de avisos inmobiliarios online."
)

demo = calcular_demografia_zonas()
tabla_avisos = calcular_tabla_avisos()
df_avisos = preparar_avisos()


# ---------------------------- Demografía ----------------------------

st.header("Demografía")
st.caption(
    "Los porcentajes se calculan por zona completa: se suman las personas de todos "
    "los radios censales de la zona y se divide por la población total de esa zona. "
    "Así una zona con muchos radios no pesa igual que una con pocos."
)

st.subheader("Zonas con mayor porcentaje de población según indicador")
st.caption("Top 10 de zonas. El valor es el % sobre la población total de la zona.")

indicador = st.selectbox(
    "Indicador:",
    options=list(INDICADORES_DEMO.keys()),
    key="zg_indicador_demo",
)
top10 = demo.nlargest(10, indicador)
st.plotly_chart(
    grafico_barras(top10, indicador, indicador + " (% de la población)", sufijo=" %", decimales=2),
    key="zg_chart_demo",
)

st.subheader("Personas por hogar")
st.caption(
    "Población total dividida por la cantidad de hogares de la zona. "
    "Un número alto suele indicar familias más grandes; uno bajo, más gente viviendo sola o en pareja."
)
st.plotly_chart(
    grafico_barras(demo, "Personas por hogar", "Personas por hogar en cada zona", color="#2ca02c"),
    key="zg_chart_hogar",
)


# ------------------------ Avisos inmobiliarios ------------------------

st.header("Avisos inmobiliarios")
st.caption(
    "Solo se tienen en cuenta los avisos activos publicados en USD. "
    "Para que una zona con muy pocos avisos no distorsione las comparaciones, "
    "podés fijar un mínimo de avisos por zona."
)

min_avisos = st.number_input(
    "Mínimo de avisos por zona:",
    min_value=1,
    value=3,
    step=1,
    key="zg_min_avisos",
)
tabla_filtrada = tabla_avisos[tabla_avisos["Avisos"] >= min_avisos]

if tabla_filtrada.empty:
    st.warning("Ninguna zona llega a ese mínimo de avisos. Probá con un número más bajo.")
    st.stop()

# --- Market share: top 5 más y top 5 menos ---
st.subheader("Market share de las zonas: las 5 que más y las 5 que menos")
st.caption(
    "Las métricas en % muestran cuánto representa cada zona del total de la ciudad. "
    "En las de promedio, mayor número de días publicado significa que los avisos tardan más en venderse."
)

metrica_label = st.selectbox(
    "Métrica:",
    options=list(METRICAS_AVISOS.keys()),
    key="zg_metrica_avisos",
)
metrica = METRICAS_AVISOS[metrica_label]

col_mas, col_menos = st.columns(2)
with col_mas:
    st.plotly_chart(
        grafico_barras(tabla_filtrada.nlargest(5, metrica), metrica, "Top 5 con más", color="#1f77b4"),
        key="zg_chart_mas",
    )
with col_menos:
    st.plotly_chart(
        grafico_barras(tabla_filtrada.nsmallest(5, metrica), metrica, "Top 5 con menos", color="#d62728"),
        key="zg_chart_menos",
    )

# --- Precio promedio por ambientes o tipo ---
st.subheader("Precio promedio por zona según tipo de inmueble")
st.caption(
    "Elegí una cantidad de ambientes o un tipo de propiedad y mirá cuánto cuesta en promedio en cada zona. "
    "Solo aparecen las zonas que tienen al menos el mínimo de avisos de ese tipo."
)

col_filtro, col_unidad = st.columns(2)
with col_filtro:
    opcion = st.selectbox(
        "Inmueble:",
        options=list(OPCIONES_INMUEBLE.keys()),
        key="zg_opcion_inmueble",
    )
with col_unidad:
    unidad = st.radio(
        "Mostrar:",
        options=["Precio (USD)", "USD por m²"],
        horizontal=True,
        key="zg_unidad_precio",
    )

columna_precio = "prices_amount" if unidad == "Precio (USD)" else "precio_m2_tot"
tabla_precios = precio_promedio_por_zona(df_avisos, opcion, columna_precio, min_avisos)

if tabla_precios.empty:
    st.info("No hay zonas con suficientes avisos para esta selección.")
else:
    st.plotly_chart(
        grafico_barras(tabla_precios, "promedio", f"{unidad} promedio - {opcion}", color="#9467bd"),
        key="zg_chart_precio",
    )

# --- Precio vs demografía ---
st.subheader("¿Cómo cambia el precio según las características de la zona?")
st.caption(
    "Cada burbuja es una zona (el tamaño depende de la cantidad de avisos). "
    "La línea muestra la tendencia: si sube, el precio por m² crece cuando aumenta esa variable demográfica."
)

variable_demo = st.selectbox(
    "Variable demográfica:",
    options=["Personas por hogar"] + list(INDICADORES_DEMO.keys()),
    key="zg_variable_demo",
)

df_scatter = demo.merge(tabla_filtrada, on="zona", how="inner")

if len(df_scatter) < 3:
    st.info("No hay suficientes zonas con datos de censo y avisos para armar este gráfico.")
else:
    fig, correlacion = grafico_dispersion(df_scatter, variable_demo, "USD/m2 promedio")
    st.plotly_chart(fig, key="zg_chart_scatter")

    if correlacion is not None:
        st.caption(
            f"Correlación entre '{variable_demo}' y el precio por m²: {correlacion:.2f} "
            "(cerca de 1 = suben juntas, cerca de -1 = una sube y la otra baja, cerca de 0 = no hay relación clara). "
            "Ojo: una correlación no prueba que una variable cause a la otra."
        )

    # Vista alternativa: se ve más claro el "progreso" del precio
    st.markdown("**Vista por grupos**")
    st.caption(
        "Las zonas se ordenan según la variable elegida y se dividen en 4 grupos del mismo tamaño. "
        "Cada barra es el USD/m² promedio de las zonas del grupo: si las barras suben de izquierda a "
        "derecha, el precio crece junto con la variable."
    )
    fig_grupos = grafico_por_grupos(df_scatter, variable_demo, "USD/m2 promedio")
    if fig_grupos is None:
        st.info("Hacen falta al menos 8 zonas para armar los grupos. Probá bajando el mínimo de avisos.")
    else:
        st.plotly_chart(fig_grupos, key="zg_chart_grupos")

    with st.expander("Ver tabla de datos usada en estos gráficos"):
        columnas_tabla = ["zona", variable_demo, "USD/m2 promedio", "Avisos"]
        st.dataframe(
            df_scatter[columnas_tabla].sort_values("USD/m2 promedio", ascending=False),
            hide_index=True,
        )