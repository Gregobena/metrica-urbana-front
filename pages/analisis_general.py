import streamlit as st
import pandas as pd

st.set_page_config(page_title="Mi página base", layout="wide")
from utils.backend import obtener_df_limpio 
from utils.backend import aplicar_filtro_global 
df_limpio,tipo = aplicar_filtro_global(obtener_df_limpio())

# ==================================================
# 2. AGRUPACIÓN DE ANTIGÜEDAD
# Si necesitás cambiar los rangos, se toca solo acá
# ==================================================

# Vista general: 3 columnas (todo lo que no es estrenar/construcción es "Usados")
GRUPOS_GENERAL = {
    'En construcción': 'En construcción',
    'A estrenar': 'A estrenar',
    '1-5': 'Usados',
    '6-10': 'Usados',
    '11-15': 'Usados',
    '16-25': 'Usados',
    '26-35': 'Usados',
    '36 o más': 'Usados',
}
ORDEN_GENERAL = ['Usados', 'En construcción', 'A estrenar']

# Vista de usados en específico: 4 columnas por rango de edad
GRUPOS_USADOS = {
    '1-5': '1-10',
    '6-10': '1-10',
    '11-15': '11-25',
    '16-25': '11-25',
    '26-35': '26-35',
    '36 o más': '36 o más',
}
ORDEN_USADOS = ['1-10', '11-25', '26-35', '36 o más']

AMBIENTES = [1, 2, 3, 4, 5]

def agrupar_antiguedad(df, col_antiguedad, detallado):
    # Crea la columna "grupo_edad" según la vista elegida
    df = df.copy()
    mapa = GRUPOS_USADOS if detallado else GRUPOS_GENERAL
    df["grupo_edad"] = df[col_antiguedad].astype(str).map(mapa)
    # Los que no entran en el mapa (ej: estrenar en la vista de usados) se descartan
    return df.dropna(subset=["grupo_edad"])

def calcular_resumen(df, col_ambientes, col_precio_m2, col_precio_total):
    # Un resumen por cada combinación (grupo de edad, ambientes)
    grupos_m2 = df.groupby(["grupo_edad", col_ambientes])[col_precio_m2]
    grupos_total = df.groupby(["grupo_edad", col_ambientes])[col_precio_total]

    resumen = pd.DataFrame({
        # Para el texto: precio por m2 promedio y cantidad de unidades
        "mean_m2": grupos_m2.mean(),
        "count": grupos_m2.count(),
        # Para la barra: precio propio del inmueble
        "mediana_total": grupos_total.median(),
        "q1": grupos_total.quantile(0.20),
        "q3": grupos_total.quantile(0.80),
    }).reset_index()

    # Lo paso a diccionario para buscar fácil por (grupo, ambientes)
    return {(fila["grupo_edad"], int(fila[col_ambientes])): fila for _, fila in resumen.iterrows()}

def celda_precios(fila, unidad):
    with st.container(border=True):
        if fila is None:
            st.caption("Sin datos")
            return

        col_valor, col_unidades = st.columns([3, 2])

        # Valor medio (precio m2)
        col_valor.markdown(f"#### {unidad} {fila['mean_m2']:,.0f}")
        col_valor.caption("Valor medio")

        # Cantidad de unidades
        col_unidades.markdown(f"#### {int(fila['count'])}")
        col_unidades.caption("Unidades")

        # Dónde cae la mediana del precio del inmueble entre LI y LS
        li = fila["q1"]
        ls = fila["q3"]
        rango = ls - li
        if rango == 0:
            porcentaje = 1.0
        else:
            porcentaje = (fila["mediana_total"] - li) / rango

        # Si la mediana queda fuera de [LI, LS] la dejamos en 0 o 1
        porcentaje = min(max(porcentaje, 0.0), 1.0)

def matriz_precios(df, col_ambientes, col_antiguedad, col_precio_m2, col_precio_total, detallado=False, unidad="USD"):
    df = agrupar_antiguedad(df, col_antiguedad, detallado)
    df = df[df[col_ambientes] < 6]

    grupos = ORDEN_USADOS if detallado else ORDEN_GENERAL
    resumen = calcular_resumen(df, col_ambientes, col_precio_m2, col_precio_total)

    # Primera columna angosta para los ambientes, el resto una por grupo
    anchos = [0.6] + [3] * len(grupos)

    # Encabezados
    columnas = st.columns(anchos)
    for i, grupo in enumerate(grupos):
        if grupo in ["En construcción", "A estrenar"]:
            columnas[i + 1].subheader(f"{tipo} - {grupo}", divider="red")
        elif grupo == "Usados":
            columnas[i + 1].subheader(f"{tipo} - {grupo}", divider="blue")
        else:
            columnas[i + 1].subheader(f"{tipo} - {grupo} Años", divider="blue")

    # Una fila por cada cantidad de ambientes
    for amb in AMBIENTES:
        columnas = st.columns(anchos)
        columnas[0].markdown(f"#### {amb} amb")
        for i, grupo in enumerate(grupos):
            with columnas[i + 1]:
                celda_precios(resumen.get((grupo, amb)), unidad)

# ==================================================
# 3. PÁGINA
# ==================================================

st.title("Metricas Generales")
st.header("Departamentos")

# --- Controles en la barra lateral ---
st.sidebar.header("Opciones")

# --- Filtro ---
detallado = st.checkbox("Mostrar usados en específico (por rango de edad)")

# --- Contenido principal ---
matriz_precios(df_limpio, "ambientes", "antiguedad_info", "precio_m2_tot", "prices_amount", detallado, "USD/m²")
# ==================================================
# 4. GRÁFICO DE RANGOS (dot plot con barras de error horizontales)
# ==================================================
import plotly.express as px

st.subheader("Comparación de rangos de precios", divider="blue")
st.markdown("Aclaracion: Se descartaron propiedades con valores extremos (muy bajo o muy alto precio) para evitar distorsiones y mostrar informacion mas real")

def grafico_rangos(df, col_ambientes, col_antiguedad, col_precio_m2, col_precio_total, detallado=False):
    df = agrupar_antiguedad(df, col_antiguedad, detallado)
    df = df[df[col_ambientes] < 6]

    grupos = ORDEN_USADOS if detallado else ORDEN_GENERAL
    resumen = calcular_resumen(df, col_ambientes, col_precio_m2, col_precio_total)

    # Separación vertical entre los puntos de un mismo ambiente
    paso = 0.2
    filas = []
    for amb in AMBIENTES:
        for i, grupo in enumerate(grupos):
            fila = resumen.get((grupo, amb))
            if fila is None:
                continue
            filas.append({
                "ambientes": amb,
                "grupo_edad": grupo,
                # Posición en Y: el ambiente más un pequeño desvío según el grupo
                "y": amb + (i - (len(grupos) - 1) / 2) * paso,
                # El punto es la mediana, las barras van de LI a LS
                "mediana": fila["mediana_total"],
                "err_mas": max(fila["q3"] - fila["mediana_total"], 0),
                "err_menos": max(fila["mediana_total"] - fila["q1"], 0),
                "Precio Minimo": fila["q1"],
                "Precio Maximo": fila["q3"],
                "unidades": int(fila["count"]),
            })

    df_rangos = pd.DataFrame(filas)
    if df_rangos.empty:
        return None

    fig = px.scatter(
        df_rangos,
        x="mediana",
        y="y",
        color="grupo_edad",
        error_x="err_mas",
        error_x_minus="err_menos",
        category_orders={"grupo_edad": grupos},
        hover_data={"y": False, "ambientes": True, "Precio Minimo": ":,.0f", "Precio Maximo": ":,.0f", "mediana": ":,.0f", "unidades": True},
        labels={"mediana": "Precio Medio", "grupo_edad": "Antigüedad"},
    )

    # Eje Y con los ambientes (1 amb arriba)
    fig.update_yaxes(
        tickvals=AMBIENTES,
        ticktext=[f"{a} amb" for a in AMBIENTES],
        autorange="reversed",
        title=None,
    )
    fig.update_traces(marker=dict(size=10))
    fig.update_layout(height=650)
    return fig

fig_rangos = grafico_rangos(df_limpio, "ambientes", "antiguedad_info", "precio_m2_tot", "prices_amount", detallado)

if fig_rangos is None:
    st.info("No hay datos para mostrar.")
else:
    st.plotly_chart(fig_rangos, width="stretch", key="rangos_precios")

# ==================================================
# 5. EVOLUCIÓN DEL PRECIO (dispersión + línea de tendencia)
# ==================================================
import numpy as np
import plotly.express as px

# Columna que identifica a cada inmobiliaria
COL_INMO = "publisher_name"

# Colores
COLOR_BARRAS = "#4C78A8"
COLOR_RESALTADO = "#F58518"

# Auxiliares de formato (estilo argentino: 1.234.567,8)
def formato_numero(valor, con_signo=False):
    # Si el número es chico (< 100) muestra 1 decimal, si no, ninguno
    if pd.isna(valor):
        return "Sin datos"
    decimales = 1 if abs(valor) < 100 else 0
    signo = "+" if con_signo else ""
    texto = f"{valor:{signo},.{decimales}f}"
    # intercambio los separadores: "," -> "." y "." -> ","
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")

def formato_diferencia(valor):
    # Igual que formato_numero pero siempre con signo (+ / -)
    return formato_numero(valor, con_signo=True)

def seccion_dispersion(df):
    st.subheader("Evolución del precio", divider="blue")
    eje = st.radio("Ver el precio según", ["M2 totales", "Antigüedad", "Ambientes", "Baños"],
                   horizontal=True, key="eje_dispersion")
    ocultar_extremos = st.checkbox("Ocultar valores extremos (1% más alto)",
                                   value=True, key="ocultar_extremos")
    if eje == "M2 totales":
        columna_x = "supCub_value" 
    elif eje == "Ambientes":
        columna_x = "ambientes"
    elif eje == "Baños":
        columna_x = "baños"
    elif eje == "Antigüedad":
        columna_x = "antiguedad"

    # Copia para no modificar el df original (los baños en 0 se cuentan como 1)
    datos = df.copy()
    datos.loc[datos["baños"] == 0, "baños"] = 1

    if ocultar_extremos:
        limite_x = datos[columna_x].quantile(0.99)
        limite_y = datos["prices_amount"].quantile(0.99)
        datos = datos[(datos[columna_x] <= limite_x) & (datos["prices_amount"] <= limite_y)]

    fig = px.scatter(
        datos, x=columna_x, y="prices_amount", opacity=0.5,
        hover_name=COL_INMO,
        hover_data={"local_address": True},
        labels={columna_x: eje, "prices_amount": "Precio (USD)", "local_address": "Dirección"},
    )
    fig.update_traces(marker_color=COLOR_BARRAS)

    # línea de tendencia (recta que mejor se ajusta a los puntos)
    pendiente = None
    if datos[columna_x].nunique() > 1:
        pendiente, ordenada = np.polyfit(datos[columna_x], datos["prices_amount"], 1)
        xs = np.linspace(datos[columna_x].min(), datos[columna_x].max(), 50)
        fig.add_scatter(x=xs, y=pendiente * xs + ordenada, mode="lines", name="Tendencia",
                        line={"color": COLOR_RESALTADO, "width": 3})

    fig.update_layout(separators=",.")
    st.plotly_chart(fig, width="stretch", key="dispersion_precio")

    if pendiente is not None:
        if eje == "M2 totales":
            unidad = "M2" 
        elif eje == "Ambientes":
            unidad = "ambiente"
        elif eje == "Baños":
            unidad = "baño"
        elif eje == "Antigüedad":
            unidad = "año"
        st.caption(f"Según la tendencia, por cada {unidad} más el precio cambia en promedio "
                   f"USD {formato_diferencia(pendiente)}.")

seccion_dispersion(df_limpio)

st.title("¿ Como se encuentra el mercado inmobiliario Platense ?")

# Asumiendo que tu DataFrame se llama 'df' y tiene las columnas 'precio' y 'cocheras'

st.subheader("Impacto de las cocheras en el precio , Comparativa Con y Sin Cochera")

df_limpio = df_limpio[df_limpio["ambientes"].isin([1,2,3,4,5])].copy()
df_limpio["Estado Cochera"] = df_limpio["cochera"].apply(lambda x: "Con Cochera" if x > 0 else "Sin Cochera")
# 1. Agrupar los datos calculando la mediana del precio por cantidad de cocheras
df_agrupado = df_limpio[df_limpio["realEstateType"] == tipo ].groupby(["ambientes",'Estado Cochera'])['prices_amount'].median().reset_index()

# 2. Asegurar que 'cocheras' se trate como texto o categoría para que el eje X sea discreto (0, 1, 2, 3)
df_agrupado['ambientes'] = df_agrupado["ambientes"].astype(str) + "Amb"

# 3. Crear el gráfico con Plotly
fig_bar = px.bar(
    df_agrupado, 
    x='ambientes', 
    y='prices_amount',
    color='Estado Cochera',
    barmode="group",
    title="Precio Mediano según Ambientes y si cuenta con cochera",
    labels={'ambientes': 'Cantidad de Ambientes', 'prices_amount': 'Precio Mediano (USD)', "Estado Cochera":"Cochera"},
    text_auto='.2s',# Muestra el valor sobre la barra formateado
    color_discrete_map={
        'Con Cochera': '#1f77b4', # Azul
        'Sin Cochera': '#ff7f0e'  # Naranja
    }   
)

# 4. Mostrar en Streamlit
st.plotly_chart(fig_bar, use_container_width=True)

precio_m2_sin = df_limpio[df_limpio["cochera"] == 0]["precio_m2_tot"].mean()
precio_m2_con = df_limpio[df_limpio["cochera"] > 0]["precio_m2_tot"].mean()

diferencia = precio_m2_con - precio_m2_sin

col1, col2 = st.columns(2)

with col1: 
    st.metric(
        label="Valor USD/m2 con cochera",
        value=f"${precio_m2_con:,.0f}"
    )
with col2: 
    st.metric(
        label="Valor USD/m2 sin cochera",
        value=f"${precio_m2_sin:,.0f}", 
        delta=f"+${diferencia:,.0f} extra"
    )
