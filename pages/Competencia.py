"""
Competencia.py

Página de Streamlit con el análisis de la competencia (inmobiliarias)
del mercado inmobiliario de La Plata.

Secciones:
    1) Mercado Completo
        - Filtro "Inmobiliarias sin contar"
        - Gráfico Principal con Totales
        - Gráfico Principal con Promedios
        - Gráfico Comparativo (Top 5 / Bottom 5)
        - Gráfico de dispersión (precio vs M2 / antigüedad)
    2) Análisis Específico
        - Buscador de inmobiliaria + resumen
        - Gráficos de la inmobiliaria (barras o torta)
        - Tabla comparada contra el promedio

Para sacar una sección: ir al final del archivo (ARMADO DE LA PÁGINA)
y comentar con # la línea correspondiente.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from notebooks.procesamiento import df_limpio
st.set_page_config(layout="wide")


# =====================================================================
# CONFIGURACIÓN GENERAL (se puede tocar libremente)
# =====================================================================

# True  -> torta a la izquierda y barras a la derecha
# False -> torta arriba y barras abajo
GRAFICOS_EN_PARALELO = False

# Cantidad de inmobiliarias que aparecen en el filtro "Inmobiliarias sin contar"
CANT_FILTRO_EXCLUIR = 25

# Cantidad de inmobiliarias que se muestran con nombre en tortas y barras
CANT_EN_GRAFICOS = 10

# Cantidad de inmobiliarias en cada tabla del Gráfico Comparativo
CANT_EN_TABLAS = 5

# Mínimo de avisos que necesita una inmobiliaria para entrar en los promedios
# (1 = entran todas las que tengan al menos un aviso)
MIN_AVISOS_PROMEDIO = 5

# Columna que identifica a cada inmobiliaria
COL_INMO = "publisher_name"

# Colores
COLOR_BARRAS = "#4C78A8"
COLOR_RESALTADO = "#F58518"
VERDE_CLARO = "#C8E6C9"
ROJO_CLARO = "#FFCDD2"


# =====================================================================
# OPCIONES DE LOS FILTROS
# =====================================================================

OPCIONES_TOTALES = [
    "Visitas (total)",
    "Market Share en Avisos",
    "M2 Publicados",
    "Cantidad a Estrenar",
    "Cantidad en Construcción",
    "Market Share en USD",
]

# nombre que se ve en pantalla -> (columna del df, cantidad de ambientes o None)
OPCIONES_PROMEDIOS = {
    "Visitas (promedio)": ("visitas", None),
    "M2 (promedio)": ("supTotal_value", None),
    "M2/USD (promedio)": ("precio_m2_tot", None),
    "Precio para 1 ambiente (promedio)": ("prices_amount", 1),
    "Precio para 2 ambientes (promedio)": ("prices_amount", 2),
    "Precio para 3 ambientes (promedio)": ("prices_amount", 3),
    "Precio para 4 ambientes (promedio)": ("prices_amount", 4),
    "Precio para 5 ambientes (promedio)": ("prices_amount", 5),
    "Antigüedad (promedio)": ("antiguedad", None),
}

# Variables extra de "Análisis Específico" (son totales).
# Se traducen a la opción equivalente de OPCIONES_TOTALES.
TOTALES_ESPECIFICO = {
    "Cantidad Avisos": "Market Share en Avisos",
    "Visitas totales": "Visitas (total)",
    "Valor Total": "Market Share en USD",
}

VARIABLES_ESPECIFICO = list(OPCIONES_PROMEDIOS.keys()) + list(TOTALES_ESPECIFICO.keys())


# =====================================================================
# FUNCIONES DE FORMATO
# =====================================================================

def formato_numero(valor, con_signo=False):
    """Formatea un número al estilo argentino (1.234.567,8).
    Si el número es chico (< 100) muestra 1 decimal, si no, ninguno."""
    if pd.isna(valor):
        return "Sin datos"
    decimales = 1 if abs(valor) < 100 else 0
    signo = "+" if con_signo else ""
    texto = f"{valor:{signo},.{decimales}f}"
    # intercambio los separadores: "," -> "." y "." -> ","
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def formato_diferencia(valor):
    """Igual que formato_numero pero siempre con signo (+ / -)."""
    return formato_numero(valor, con_signo=True)


def formato_porcentaje(valor):
    """Muestra un porcentaje con signo, ej: +12,5 %"""
    if pd.isna(valor):
        return "Sin datos"
    return f"{valor:+.1f} %".replace(".", ",")


# =====================================================================
# FUNCIONES DE CÁLCULO
# =====================================================================

def filtrar_estrenar(df):
    """Avisos marcados como 'a estrenar' en antiguedad_info."""
    return df[df["antiguedad_info"].str.contains("estrenar", case=False, na=False)]


def filtrar_construccion(df):
    """Avisos marcados como 'en construcción' en antiguedad_info."""
    return df[df["antiguedad_info"].str.contains("construc", case=False, na=False)]


def calcular_totales(df, tipo):
    """Devuelve una Serie (índice = inmobiliaria) con el TOTAL de la variable
    elegida, ordenada de mayor a menor. Las inmobiliarias con 0 se descartan."""
    if tipo == "Visitas (total)":
        serie = df.groupby(COL_INMO)["visitas"].sum()
    elif tipo == "Market Share en Avisos":
        serie = df.groupby(COL_INMO).size()
    elif tipo == "M2 Publicados":
        serie = df.groupby(COL_INMO)["supTotal_value"].sum()
    elif tipo == "Cantidad a Estrenar":
        # solo se cuentan los avisos a estrenar -> el % es sobre ese grupo
        serie = filtrar_estrenar(df).groupby(COL_INMO).size()
    elif tipo == "Cantidad en Construcción":
        # solo se cuentan los avisos en construcción -> el % es sobre ese grupo
        serie = filtrar_construccion(df).groupby(COL_INMO).size()
    else:  # "Market Share en USD"
        serie = df.groupby(COL_INMO)["prices_amount"].sum()

    serie = serie[serie > 0]
    return serie.sort_values(ascending=False)


def calcular_promedios(df, tipo, min_avisos=MIN_AVISOS_PROMEDIO):    
    """Devuelve una Serie (índice = inmobiliaria) con el PROMEDIO de la variable
    elegida: suma del valor / cantidad de avisos de esa inmobiliaria.
    Las inmobiliarias sin avisos para esa variable se descartan."""
    columna, ambientes = OPCIONES_PROMEDIOS[tipo]

    datos = df
    if ambientes is not None:
        # solo los avisos con esa cantidad de ambientes
        datos = df[df["ambientes"] == ambientes]

    agrupado = datos.groupby(COL_INMO)[columna]
    serie = agrupado.mean()
    cantidad_avisos = agrupado.count()

    serie = serie[cantidad_avisos >= min_avisos]
    return serie.dropna().sort_values(ascending=False)


def calcular_variable(df, variable):
    """Calcula cualquier variable de la sección Análisis Específico."""
    if variable in OPCIONES_PROMEDIOS:
        return calcular_promedios(df, variable)
    return calcular_totales(df, TOTALES_ESPECIFICO[variable])


# =====================================================================
# FUNCIONES DE GRÁFICOS
# =====================================================================

def armar_datos_grafico(serie, cantidad, resaltar=None):
    """Se queda con las primeras `cantidad` inmobiliarias.
    Si hay una para resaltar y quedó afuera del top, la agrega al final."""
    top = serie.head(cantidad)
    if resaltar is not None and resaltar in serie.index and resaltar not in top.index:
        top = pd.concat([top, serie[[resaltar]]])
    return top


def grafico_torta(serie, titulo, resaltar=None, agrupar_resto=True):
    """Gráfico de torta (solo %).
    agrupar_resto=True junta a las que no entran en el top en una porción 'Otras'."""
    datos = armar_datos_grafico(serie, CANT_EN_GRAFICOS, resaltar)

    if agrupar_resto:
        resto = serie.drop(datos.index).sum()
        if resto > 0:
            datos = pd.concat([datos, pd.Series({"Otras": resto})])

    tabla = datos.reset_index()
    tabla.columns = ["Inmobiliaria", "Valor"]

    fig = px.pie(tabla, names="Inmobiliaria", values="Valor", title=titulo)

    # la inmobiliaria resaltada se separa un poco del resto
    separacion = [0.12 if nombre == resaltar else 0 for nombre in tabla["Inmobiliaria"]]
    fig.update_traces(
        sort=False,
        pull=separacion,
        textinfo="percent",
        hovertemplate="%{label}: %{percent}<extra></extra>",
    )
    fig.update_layout(separators=",.", legend_title_text="Inmobiliaria")
    return fig


def grafico_barras(serie, titulo, nombre_valor, resaltar=None):
    """Gráfico de barras horizontales (valores numéricos, no %).
    La inmobiliaria resaltada aparece en otro color."""
    datos = armar_datos_grafico(serie, CANT_EN_GRAFICOS, resaltar)

    tabla = datos.reset_index()
    tabla.columns = ["Inmobiliaria", nombre_valor]

    colores = [COLOR_RESALTADO if nombre == resaltar else COLOR_BARRAS
               for nombre in tabla["Inmobiliaria"]]

    # si los valores son chicos (ej: antigüedad) muestro 1 decimal
    formato = ",.1f" if datos.max() < 100 else ",.0f"

    fig = px.bar(tabla, x=nombre_valor, y="Inmobiliaria", orientation="h", title=titulo)
    fig.update_traces(
        marker_color=colores,
        texttemplate="%{x:" + formato + "}",
        textposition="outside",
        cliponaxis=False,
    )
    fig.update_layout(
        separators=",.",
        height=120 + 35 * len(tabla),
        yaxis_title=None,
        # el más grande arriba
        yaxis={"categoryorder": "array", "categoryarray": list(tabla["Inmobiliaria"])[::-1]},
    )
    return fig


def mostrar_torta_y_barras(fig_torta, fig_barras, en_paralelo=GRAFICOS_EN_PARALELO):
    """Muestra los dos gráficos.
    en_paralelo=True  -> torta a la izquierda, barras a la derecha
    en_paralelo=False -> torta arriba, barras abajo"""
    if en_paralelo:
        col_izq, col_der = st.columns(2)
        col_izq.plotly_chart(fig_torta, width="stretch")
        col_der.plotly_chart(fig_barras, width="stretch")
    else:
        st.plotly_chart(fig_torta, width="stretch")
        st.plotly_chart(fig_barras, width="stretch")


def mostrar_tabla_ranking(serie, promedio, color):
    """Tabla del Gráfico Comparativo, pintada del color indicado."""
    tabla = pd.DataFrame({
        "Inmobiliaria": serie.index,
        "Valor": serie.values,
        "Comparación con el Promedio": serie.values - promedio,
        "Comparación en % con el Promedio": (serie.values - promedio) / promedio * 100,
    })

    estilo = (
        tabla.style
        .format({
            "Valor": formato_numero,
            "Comparación con el Promedio": formato_diferencia,
            "Comparación en % con el Promedio": formato_porcentaje,
        })
        .set_properties(**{"background-color": color, "color": "black"})
    )
    st.dataframe(estilo, hide_index=True, width="stretch")


# =====================================================================
# SECCIÓN 1: MERCADO COMPLETO
# =====================================================================

def filtro_inmobiliarias_excluidas(df):
    """Checklist con las inmobiliarias con más avisos.
    Las tildadas se sacan del análisis de Mercado Completo (no se borran del df)."""
    top = df[COL_INMO].value_counts().head(CANT_FILTRO_EXCLUIR)
    excluidas = []

    with st.expander("Inmobiliarias sin contar:"):
        st.caption("Tildá las inmobiliarias que quieras sacar de esta sección.")
        columnas = st.columns(3)
        for posicion, (nombre, cantidad) in enumerate(top.items()):
            columna = columnas[posicion % 3]
            if columna.checkbox(f"{nombre} ({cantidad} avisos)", key=f"excluir_{nombre}"):
                excluidas.append(nombre)

    if excluidas:
        st.caption("Sin contar: " + ", ".join(excluidas))

    return df[~df[COL_INMO].isin(excluidas)]


def seccion_totales(df):
    st.subheader("Gráfico Principal con Totales")
    tipo = st.selectbox("Tipo de Información", OPCIONES_TOTALES, key="tipo_totales")

    serie = calcular_totales(df, tipo)
    if serie.empty:
        st.warning("No hay datos para esta opción.")
        return

    if tipo in ["Cantidad a Estrenar", "Cantidad en Construcción"]:
        st.caption("Los porcentajes se calculan solo sobre los avisos de este tipo, "
                   "no sobre todas las publicaciones.")

    fig_torta = grafico_torta(serie, f"{tipo}: participación de cada inmobiliaria")
    st.caption("Clickea en sus nombres a la derecha para quitarlas del Grafico")
    fig_barras = grafico_barras(serie, f"{tipo}: top {CANT_EN_GRAFICOS} inmobiliarias", tipo)
    mostrar_torta_y_barras(fig_torta, fig_barras)


def seccion_promedios(df):
    st.subheader("Gráfico Principal con Promedios")
    col_tipo, col_minimo = st.columns([3, 1])
    tipo = col_tipo.selectbox("Tipo de Información", list(OPCIONES_PROMEDIOS), key="tipo_promedios")
    # mínimo de avisos que tiene que tener una inmobiliaria para entrar en el gráfico
    min_avisos = col_minimo.number_input("Mínimo de avisos", min_value=1,
                                         value=MIN_AVISOS_PROMEDIO, step=1,
                                         key="min_avisos_promedios")

    serie = calcular_promedios(df, tipo, min_avisos)
    if serie.empty:
        st.warning(f"Ninguna inmobiliaria tiene {min_avisos} avisos o más para esta opción.")
        return

    st.caption("Promedio = suma del valor / cantidad de avisos de cada inmobiliaria. "
               f"Solo aparecen las que tienen al menos {min_avisos} avisos para esta variable.")

    # en promedios no se agrupa el resto en 'Otras' (sumar promedios no tiene sentido)
    fig_torta = grafico_torta(serie, f"{tipo}: top {CANT_EN_GRAFICOS} en %", agrupar_resto=False)
    fig_barras = grafico_barras(serie, f"{tipo}: top {CANT_EN_GRAFICOS} inmobiliarias", tipo)
    mostrar_torta_y_barras(fig_torta, fig_barras)


def seccion_comparativa(df):
    st.subheader("Gráfico Comparativo")
    variable = st.selectbox("Variable a Comparar", list(OPCIONES_PROMEDIOS), key="variable_comparar")

    serie = calcular_promedios(df, variable)
    if serie.empty:
        st.warning("No hay datos para esta opción.")
        return

    promedio = serie.mean()
    st.caption(f"Promedio entre inmobiliarias: {formato_numero(promedio)}")

    col_izq, col_der = st.columns(2)
    with col_izq:
        st.markdown(f"**Top {CANT_EN_TABLAS}: valores más altos**")
        mostrar_tabla_ranking(serie.head(CANT_EN_TABLAS), promedio, VERDE_CLARO)
    with col_der:
        st.markdown(f"**Top {CANT_EN_TABLAS}: valores más bajos**")
        mostrar_tabla_ranking(serie.tail(CANT_EN_TABLAS).sort_values(), promedio, ROJO_CLARO)


def seccion_dispersion(df):
    st.subheader("Evolución del precio")
    eje = st.radio("Ver el precio según", ["M2 totales", "Antigüedad"],
                   horizontal=True, key="eje_dispersion")
    ocultar_extremos = st.checkbox("Ocultar valores extremos (1% más alto)",
                                   value=True, key="ocultar_extremos")

    columna_x = "supCub_value" if eje == "M2 totales" else "antiguedad"
    datos = df

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
    st.plotly_chart(fig, width="stretch")

    if pendiente is not None:
        unidad = "m2" if eje == "M2 totales" else "año de antigüedad"
        st.caption(f"Según la tendencia, por cada {unidad} más el precio cambia en promedio "
                   f"USD {formato_diferencia(pendiente)}.")


# =====================================================================
# SECCIÓN 2: ANÁLISIS ESPECÍFICO
# =====================================================================

def selector_inmobiliaria(df):
    """Buscador: se escribe el nombre y se elige de la lista."""
    inmobiliarias = sorted(df[COL_INMO].unique())
    return st.selectbox(
        "Inmobiliaria:", inmobiliarias, index=None,
        placeholder="Escribí el nombre de la inmobiliaria...", key="inmo_elegida",
    )


def resumen_inmobiliaria(df, elegida):
    """Números principales de la inmobiliaria elegida."""
    avisos = calcular_totales(df, "Market Share en Avisos")
    visitas = calcular_totales(df, "Visitas (total)")
    valor = calcular_totales(df, "Market Share en USD")
    posicion = list(avisos.index).index(elegida) + 1

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cantidad de avisos", formato_numero(avisos.get(elegida, 0)))
    col2.metric("Visitas totales", formato_numero(visitas.get(elegida, 0)))
    col3.metric("Valor total (USD)", formato_numero(valor.get(elegida, 0)))
    col4.metric("Puesto por cantidad de avisos", f"{posicion} de {len(avisos)}")


def grafico_inmobiliaria(df, elegida):
    """Barras o torta de una variable, con la inmobiliaria elegida resaltada."""
    st.subheader("Gráficos de la inmobiliaria")
    col1, col2 = st.columns([2, 1])
    variable = col1.selectbox("Variable", VARIABLES_ESPECIFICO, key="variable_especifico")
    tipo_grafico = col2.radio("Tipo de gráfico", ["Barras", "Torta"],
                              horizontal=True, key="tipo_grafico_especifico")

    serie = calcular_variable(df, variable)
    if elegida not in serie.index:
        st.warning(f"{elegida} no tiene avisos para «{variable}».")
        return

    if tipo_grafico == "Barras":
        fig = grafico_barras(serie, f"{variable}: {elegida} frente al top {CANT_EN_GRAFICOS}",
                             variable, resaltar=elegida)
        st.caption("La inmobiliaria elegida aparece en naranja.")
    else:
        # 'Otras' solo tiene sentido en las variables de totales
        es_total = variable in TOTALES_ESPECIFICO
        fig = grafico_torta(serie, f"{variable}: {elegida} frente al top {CANT_EN_GRAFICOS}",
                            resaltar=elegida, agrupar_resto=es_total)
        st.caption("La porción de la inmobiliaria elegida aparece separada.")

    st.plotly_chart(fig, width="stretch")


def tabla_inmobiliaria_vs_promedio(df, elegida):
    """Tabla con todas las variables: verde si está por encima del promedio,
    rojo si está por debajo."""
    st.subheader("Comparación con el promedio del mercado")

    filas = []
    for variable in VARIABLES_ESPECIFICO:
        serie = calcular_variable(df, variable)
        valor = serie.get(elegida, np.nan)
        promedio = serie.mean()
        filas.append({
            "Variable": variable,
            elegida: valor,
            "Promedio del mercado": promedio,
            "Diferencia": valor - promedio,
            "Diferencia %": (valor - promedio) / promedio * 100,
        })
    tabla = pd.DataFrame(filas)

    def pintar_fila(fila):
        """Pinta solo la celda del valor de la inmobiliaria."""
        color = ""
        if pd.notna(fila[elegida]):
            if fila[elegida] > fila["Promedio del mercado"]:
                color = f"background-color: {VERDE_CLARO}; color: black"
            elif fila[elegida] < fila["Promedio del mercado"]:
                color = f"background-color: {ROJO_CLARO}; color: black"
        return [color if columna == elegida else "" for columna in fila.index]

    estilo = (
        tabla.style
        .apply(pintar_fila, axis=1)
        .format({
            elegida: formato_numero,
            "Promedio del mercado": formato_numero,
            "Diferencia": formato_diferencia,
            "Diferencia %": formato_porcentaje,
        })
    )
    st.dataframe(estilo, hide_index=True, width="stretch", height=35 * (len(tabla) + 1) + 3)
    st.caption("Verde: por encima del promedio. Rojo: por debajo. "
               "El promedio es entre inmobiliarias que tienen datos en esa variable.")


# =====================================================================
# ARMADO DE LA PÁGINA
# Para sacar una sección, comentá (con #) su línea.
# =====================================================================

st.title("Competencia")
st.caption("Cómo se reparte el mercado entre las inmobiliarias de La Plata.")

# ---------------- 1) MERCADO COMPLETO ----------------
st.header("Mercado Completo")
df_mercado = filtro_inmobiliarias_excluidas(df_limpio)   # <- filtro "Inmobiliarias sin contar"
                                                         #    (si lo sacás, usá: df_mercado = df_limpio)
seccion_totales(df_mercado)        # <- Gráfico Principal con Totales
st.divider()
seccion_promedios(df_mercado)      # <- Gráfico Principal con Promedios
st.divider()
seccion_comparativa(df_mercado)    # <- Gráfico Comparativo (tablas verde / roja)
st.divider()
seccion_dispersion(df_mercado)     # <- Dispersión precio vs M2 / antigüedad

# ---------------- 2) ANÁLISIS ESPECÍFICO ----------------
st.header("Análisis Específico")
inmo_elegida = selector_inmobiliaria(df_limpio)          # <- buscador (no lo saques: lo usan las 3 de abajo)

if inmo_elegida is None:
    st.info("Elegí una inmobiliaria para ver su análisis.")
else:
    resumen_inmobiliaria(df_limpio, inmo_elegida)            # <- números principales
    grafico_inmobiliaria(df_limpio, inmo_elegida)            # <- gráfico de barras / torta
    tabla_inmobiliaria_vs_promedio(df_limpio, inmo_elegida)  # <- tabla verde / roja vs promedio