from pymongo import MongoClient, GEOSPHERE
from pymongo import ReplaceOne
import certifi
import streamlit as st
import pandas as pd 

@st.cache_resource
def iniciar_conexion():
    uri = "mongodb+srv://pc_grego:8s8X2sj6cFxEXgt7@metrica.9fsxkgg.mongodb.net/metrica_urbana?retryWrites=true&w=majority"
    # Es obligatorio pasar tlsCAFile=certifi.where() para evitar el bloqueo SSL
    return MongoClient(uri, tlsCAFile=certifi.where())


# Le indicamos a pymongo dónde están los certificados

@st.cache_data(ttl=7200)
def obtener_df_limpio(COLECCION="inmuebles"):

    cliente = iniciar_conexion()

    db = cliente["metrica_urbana"]
    coleccion = db[COLECCION]

    cursor = coleccion.find({"status":"ONLINE"})
    datos = list(cursor)

    df_limpio = pd.DataFrame(datos)

    if '_id' in df_limpio.columns:
        df_limpio['_id'] = df_limpio['_id'].astype(str)
    
    return df_limpio

def aplicar_filtro_global(df_limpio):
    st.sidebar.header("▽ Filtros Globales")
    
    opciones = ["Todas"] + list(df_limpio["realEstateType"].dropna().unique())
    
    # Evitamos que "Casco Urbano" se duplique si ya viene en el DataFrame
    zonas_unicas = [z for z in df_limpio["zona"].dropna().unique() if z != "Casco Urbano"]
    zonas_casco = ["Plaza San Martin - 1, 7, 44 y 60", "Parque Alberti - 19, 31, 32 y 44","Barrio Hipodromo - 122, 1, 32 y 44","Parque Saveedra - 7, 19, 60 y 72","Plaza Moreno Sur - 13, 19, 44 y 60","Barrio Mondongo - 122, 1 60 y 72","Parque Castelli - 19, 31, 60 y 72","Plaza Belgrano - 7, 19, 32 y 44","Plaza Alsina - 1, 7, 32 y 44","Plaza Moreno Norte - 8, 13, 44 y 60","El Bosque","Parque Vucetich - 19, 31, 44 y 60","Plaza España - 1, 7, 60 y 72"]
    opciones_zonas = ["Todas", "Casco Urbano"] + zonas_unicas
    
    st.sidebar.selectbox(
        "Tipo de Propiedad:",
        options=opciones,
        key="filtro_tipo_inmueble"
    )

    st.sidebar.selectbox(
        "Zona de La Plata:",
        options=opciones_zonas,
        key="filtro_tipo_zona"
    )
    
    # Guardamos las selecciones en variables para que el código sea más legible
    tipo_sel = st.session_state["filtro_tipo_inmueble"]
    zona_sel = st.session_state["filtro_tipo_zona"]
    
    # 1. Empezamos con una copia completa
    df_filtrado = df_limpio.copy()
    
    # 2. Si eligió un tipo específico, recortamos el DataFrame
    if tipo_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado["realEstateType"] == tipo_sel]
        
    # 3. Si eligió una zona específica, volvemos a recortar sobre lo que ya quedó
    if zona_sel == "Casco Urbano":
        df_filtrado = df_filtrado[df_filtrado["zona"].isin(zonas_casco)]
    elif zona_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado["zona"] == zona_sel]
        
    # Retornamos el DataFrame resultante y las variables (puedes retornar ambas si las necesitas afuera)
    return df_filtrado, tipo_sel


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

