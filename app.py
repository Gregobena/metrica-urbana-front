import streamlit as st
import pandas as pd
import plotly.express as px
import re 

from utils.backend import tabla_pivot

st.set_page_config(page_title="Mi página base", layout="wide")
from utils.backend import obtener_df_limpio 
from utils.backend import aplicar_filtro_global 
df_limpio,tipo = aplicar_filtro_global(obtener_df_limpio())

# ==================================================
# 2. GRÁFICOS
# Cada gráfico es una función aparte, así agregás otro fácil
# ==================================================
def grafico_torta(df, col_categoria, col_valor):
    return px.pie(df, names=col_categoria, values=col_valor)

def grafico_barras(df, col_categoria, col_valor):
    return px.bar(df, x=col_categoria, y=col_valor)

def armar_grafico(df, grafico, col_categoria=None, col_valor=None, es_pivot=False, col_pivot=None):
    # --- Caso 1: viene de tabla_pivot (index = categorías, una columna por cada grupo) ---
    if es_pivot:
        nombre_index = df.index.name  # ej: "ambientes"

        if grafico == "torta":
            # Sin col_pivot sumo todas las columnas; con col_pivot uso solo esa
            if col_pivot is None:
                serie = df.sum(axis=1)
            else:
                serie = df[col_pivot]
            df_torta = serie.reset_index()
            df_torta.columns = [nombre_index, "valor"]
            return grafico_torta(df_torta, nombre_index, "valor")

        elif grafico == "barras":
            # Paso a formato largo: una fila por cada combinación index + columna
            df_largo = df.reset_index().melt(
                id_vars=nombre_index,
                var_name=df.columns.name,  # ej: "antiguedad_info"
                value_name="valor"
            )
            # Como texto para que cada cantidad de ambientes sea una barra separada
            df_largo[nombre_index] = df_largo[nombre_index].astype(str)
            return px.bar(df_largo, x=nombre_index, y="valor", color=df.columns.name, barmode="group")

    # --- Caso 2: df común (como estaba antes) ---
    # Agrupamos por si la categoría se repite en varias filas
    df_agrupado = df.groupby(col_categoria)[col_valor].sum().reset_index()

    if grafico == "torta":
        return grafico_torta(df_agrupado, col_categoria, col_valor)
    elif grafico == "barras":
        return grafico_barras(df_agrupado, col_categoria, col_valor)

# Auxiliares para tarjeta_precios
def ordenar_antiguedad(df):
    orden_antiguedad = [
        'En construcción',
        'A estrenar',
        '1-5',
        '6-10',
        '11-15',
        '16-25',
        '26-35',
        '36 o más'
    ]
    df["antiguedad_info"] = pd.Categorical(
        df["antiguedad_info"], 
        categories=orden_antiguedad, 
        ordered=True
    )
    return df

def clave_orden(texto):
    # Define el orden de los bloques: primero A estrenar, después En construcción,
    # y después los rangos de años ordenados por su primer número (1-5, 6-10, ..., +36)
    texto = str(texto)
    if texto == "A estrenar":
        return (0, 0)
    if texto == "En construcción":
        return (1, 0)
    numeros = re.findall(r"\d+", texto)
    primero = int(numeros[0]) if numeros else 999
    return (2, primero)

def tarjeta_precios(df, col_ambientes, col_antiguedad, col_precio_m2, col_precio_total, unidad="USD"):
    # Un bloque por cada tipo de antigüedad (ej: Usado, A estrenar)
    df = ordenar_antiguedad(df)

    antiguedades = sorted(df[col_antiguedad].dropna().unique(), key=clave_orden)
    for antiguedad in antiguedades:

        if antiguedad not in ["En construcción","A estrenar"]:
            st.subheader(f"{tipo} - {antiguedad} Años", divider="blue")
        else:
            st.subheader(f"{tipo} - {antiguedad} ", divider="red")

        # Filtramos y agrupamos por cantidad de ambientes
        df_ant = df[(df[col_antiguedad] == antiguedad) & (df["ambientes"] < 6)]
        grupos_m2 = df_ant.groupby(col_ambientes)[col_precio_m2]
        grupos_total = df_ant.groupby(col_ambientes)[col_precio_total]

        resumen = pd.DataFrame({
            # Para el texto: precio por m2 promedio y cantidad de unidades
            "mean_m2": grupos_m2.mean(),
            "count": grupos_m2.count(),
            # Para la barra: precio propio del inmueble
            "mean_total": grupos_total.mean(),
            "q1": grupos_total.quantile(0.125),
            "q3": grupos_total.quantile(0.875),
        }).reset_index()

        # Fórmula de los bigotes del box-plot (sobre prices_amount)
        resumen["ric"] = resumen["q3"] - resumen["q1"]
        resumen["li"] = resumen["q1"] 
        resumen["ls"] = resumen["q3"] 

        # Una fila por cada cantidad de ambientes
        for _, fila in resumen.iterrows():
            with st.container(border=True):
                col_valor, col_unidades, col_barra = st.columns([1, 1, 3])

                # Columna 1: ambientes y valor medio (precio m2)
                col_valor.caption(f"{int(fila[col_ambientes])} amb")
                col_valor.markdown(f"### {unidad} {fila['mean_m2']:,.0f}")
                col_valor.caption("Valor medio")

                # Columna 2: cantidad de unidades
                col_unidades.markdown(f"### {int(fila['count'])}")
                col_unidades.caption("Unidades")

                # Columna 3: dónde cae el precio promedio del inmueble entre LI y LS
                rango = fila["ls"] - fila["li"]
                if rango == 0:
                    porcentaje = 1.0
                else:
                    porcentaje = (fila["mean_total"] - fila["li"]) / rango

                # Si el promedio queda fuera de [LI, LS] lo dejamos en 0 o 1
                porcentaje = min(max(porcentaje, 0.0), 1.0)
                col_barra.progress(float(porcentaje))
                col_barra.markdown(f"Rango de Precios de Lista: USD {fila['li']:,.0f}  — USD {fila['ls']:,.0f} | Promedio: USD {fila["mean_total"]:,.0f}")

# ==================================================
# 3. PÁGINA
# ==================================================

st.title("Metricas Generales")
st.header("Departamentos")

# --- Controles en la barra lateral ---
st.sidebar.header("Opciones")

# --- Contenido principal ---

# Valores en Tarjeta

tarjeta_precios(df_limpio, "ambientes", "antiguedad_info", "precio_m2_tot","prices_amount", "USD/m²")

# Valores En Grafico
st.subheader("Graficos" , divider="blue")
grafico = st.radio("Tipo de gráfico", ["barras", "torta"])

amb_antig_precio_m2_mean = tabla_pivot(df_limpio,"ambientes","antiguedad_info","precio_m2_tot","mean",5,5)
fig = armar_grafico(amb_antig_precio_m2_mean, grafico, es_pivot=True)

st.plotly_chart(fig, width="stretch",key="amb_antig_precio_m2_mean")

amb_antig_precio_m2_count = tabla_pivot(df_limpio,"ambientes","antiguedad_info","precio_m2_tot","count",5,5)
fig = armar_grafico(amb_antig_precio_m2_count, grafico, es_pivot=True)
st.plotly_chart(fig, width="stretch")

# Valores en Tabla
st.subheader("Datos", divider="blue")

import numpy as np

# Reemplazamos los 0 por NaN para que el cálculo del color los ignore
df_mean_procesado = amb_antig_precio_m2_mean.replace(0, np.nan)
df_count_procesado = amb_antig_precio_m2_count.replace(0, np.nan)

st.markdown("Tabla de Datos sobre promedio de USD/m2")
with st.expander("Ver datos"):
    st.dataframe(
        df_mean_procesado.style
        .background_gradient(cmap='Greens', axis=None)
        .format(na_rep='0') # Vuelve a imprimir "0" donde hay un NaN
    )

st.markdown("Tabla de Datos sobre cantidad de inmuebles registrados")
with st.expander("Ver datos"):
    st.dataframe(
        df_count_procesado.style
        .background_gradient(cmap='Greens', axis=None)
        .format(na_rep='0') # Vuelve a imprimir "0" donde hay un NaN
    )
