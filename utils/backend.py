from pymongo import MongoClient, GEOSPHERE
from pymongo import ReplaceOne
import certifi
import streamlit as st
import pandas as pd 
@st.cache_resource
def iniciar_conexion():
    uri = st.secrets["mongo"]["uri"]
    # Es obligatorio pasar tlsCAFile=certifi.where() para evitar el bloqueo SSL
    return MongoClient(uri, tlsCAFile=certifi.where())


# Le indicamos a pymongo dónde están los certificados

@st.cache_data(ttl=7200)
def obtener_df_limpio():

    cliente = iniciar_conexion()

    db = cliente["metrica_urbana"]
    coleccion = db["inmuebles"]

    cursor = coleccion.find({"status":"ONLINE"})
    datos = list(cursor)

    df_limpio = pd.DataFrame(datos)

    if '_id' in df_limpio.columns:
        df_limpio['_id'] = df_limpio['_id'].astype(str)
    
    return df_limpio

def aplicar_filtro_global(df_limpio):
    st.sidebar.header("Filtros Globales")
    
    opciones = ["Todas"] + list(df_limpio["realEstateType"].dropna().unique())
    
    st.sidebar.selectbox(
        "Tipo de Propiedad:",
        options=opciones,
        key="filtro_tipo_inmueble"
    )
    
    if st.session_state["filtro_tipo_inmueble"] == "Todas":
        return df_limpio.copy(), st.session_state["filtro_tipo_inmueble"]
    else:
        return df_limpio[df_limpio["realEstateType"] == st.session_state["filtro_tipo_inmueble"]].copy(), st.session_state["filtro_tipo_inmueble"]

@st.cache_data(ttl=7200)
def obtener_df_censo():

    cliente = iniciar_conexion()

    db = cliente["metrica_urbana"]
    coleccion = db["censos"]

    cursor = coleccion.find()
    datos = list(cursor)

    df_limpio = pd.DataFrame(datos)

    if '_id' in df_limpio.columns:
        df_limpio['_id'] = df_limpio['_id'].astype(str)
    return df_limpio





def tabla_pivot(df, index, columns, values, aggfunc="mean", min_props=1, max_index=None):
    """
    Pivotea el df y devuelve, por ej:
    Indice=Ambientes
    Columnas=Antiguedad_info
    Valores= PrecioM2 / M2 / Expensas
    aggfunc= count/mean
    min_props=3 ( minimo de props por renglon para tomar en cuenta)
    max_index= ( para ambientes, maximo x ambientes se toman en cuenta)
    """
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
    df = df.copy()
    df["antiguedad_info"] = pd.Categorical(
        df["antiguedad_info"],
        categories=orden_antiguedad,
        ordered=True
    )

    # Si me pasan un máximo, descarto los index que lo superan (ej: ambientes > 6)
    if max_index is not None:
        df = df[df[index] <= max_index]
    cantidad = df.groupby(index)[values].count()

    # Me quedo solo con los index que llegan al mínimo
    index_validos = cantidad[cantidad >= min_props].index
    df_filtrado = df[df[index].isin(index_validos)]

    # Armo la pivot con los datos filtrados
    tabla = df_filtrado.pivot_table(
        index=index,
        columns=columns,
        values=values,
        aggfunc=aggfunc,
        fill_value=0,
        observed=False
    ).round(1)

    return tabla


def comparacion_con_valor_normal(df, valor="Población de 18 y más con universitario completo o más_%", min_props=3):
    """
    Arma un df separado por zonas comparando los valores:
    Valor / Cantidad de Props / Diferencia (Puntos) del prom / Variación vs Normal (%) del prom
    """
    # 1. Agrupamos calculando el promedio del valor y contando la cantidad de inmuebles reales
    df_edades = df.groupby("zona").agg({
        valor: "mean",
        "id_radio_censal": "count"
    }).reset_index()

    df_edades = df_edades.rename(columns={"id_radio_censal": "Cantidad Props"})
    df_edades[valor] = df_edades[valor].round(2)

    # Filtramos las zonas que no alcanzan el mínimo de propiedades
    df_edades = df_edades[df_edades["Cantidad Props"] >= min_props].copy()

    # 2. Calculamos el "valor normal" usando solo las zonas válidas
    promedio_general = df_edades[valor].mean()

    # 3. Diferencia absoluta en puntos
    df_edades["Diferencia (Puntos)"] = (df_edades[valor] - promedio_general).round(2)

    # 4. Variación porcentual relativa respecto al promedio
    df_edades["Variación vs Normal (%)"] = ((df_edades[valor] / promedio_general - 1) * 100).round(2)

    # 5. Ordenamos la tabla
    df_comparativo = df_edades.sort_values(by="Diferencia (Puntos)", ascending=False)

    return promedio_general, df_comparativo


def comparacion_por_grupo_etario(df, grupo_etario, valor, min_props=5):
    """
    grupo_etario: columna de % del csv, ej. "Población de 18 a 29 años_%"
    valor: columna a comparar dentro de esas zonas, ej. "precio_m2_tot"
    """
    # 1. Zonas por arriba del promedio en ese grupo etario
    prom_etario, df_etario = comparacion_con_valor_normal(df, grupo_etario, min_props)
    zonas_por_encima = df_etario[df_etario["Diferencia (Puntos)"] > 0]["zona"]

    # 2. Filtramos el df a solo esas zonas
    df_filtrado = df[df["zona"].isin(zonas_por_encima)]

    # 3. Sobre ese subconjunto, comparamos el valor pedido zona por zona
    prom_valor, df_valor = comparacion_con_valor_normal(df_filtrado, valor, min_props)

    return prom_etario, df_etario, prom_valor, df_valor

