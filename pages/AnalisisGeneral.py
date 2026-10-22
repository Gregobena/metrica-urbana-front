import streamlit as st
import pandas as pd
import plotly.express as px
from utils.backend import obtener_df_limpio
from utils.backend import aplicar_filtro_global 
df_limpio,tipo = aplicar_filtro_global(obtener_df_limpio())
df_limpio.loc[df_limpio["baños"] == 0, "baños"] = 1

st.title("¿ Como se encuentra el mercado inmobiliario Platense ?")
st.set_page_config(layout="wide")

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
