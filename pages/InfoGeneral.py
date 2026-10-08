"""
Página de Streamlit: mapas de inmuebles y datos del censo en La Plata.

Para correrla:
    pip install streamlit streamlit-folium folium shapely branca pandas
    streamlit run pagina_mapas.py

Estructura del archivo:
    1. Configuración (lo que más vas a tocar)
    2. Carga de datos
    3. Funciones de análisis (las tuyas)
    4. Funciones de mapas
    5. La página (pestañas)
"""

import pandas as pd
import streamlit as st
import folium
import branca.colormap as cm
from streamlit_folium import st_folium
from shapely import wkt
from shapely.geometry import mapping
from shapely.ops import unary_union


# =====================================================================
# 1. CONFIGURACIÓN
# =====================================================================

RUTA_CSV = "notebooks/avisos_info_modif.csv"          # ruta al csv
CENTRO_MAPA = [-34.92, -57.95]     # centro de La Plata
ZOOM_INICIAL = 13
MIN_PROPS = 5                      # mínimo de filas por zona para tenerla en cuenta

# Variables de inmuebles que se pueden elegir (nombre que se ve : columna del csv)
VARIABLES_INMUEBLES = {
    "Precio m² total": "precio_m2_tot",
    "Precio promedio": "prices_amount",
    "A Estrenar": "cantidad_a_estrenar",
    "En construcción": "cantidad_en_construccion",
    "Visitas" : "visitas",
    "Antiguedad de Posteo" : "posting_antiquity",
    "Antigüedad (años)": "antiguedad",
    "Expensas": "expenses",
    "Cantidad de avisos": "cantidad_avisos",
    "Superficie cubierta": "supCub_value",
    "Superficie total": "supTotal_value",
}

# Variables del censo que se pueden elegir
VARIABLES_CENSO = {
    "Universitario completo (%)": "Población de 18 y más con universitario completo o más_%",
    "Secundario completo (%)": "Población de 18 y más con secundaria completa o más_%",
    "Solo salud pública (%)": "Solo salud pública_%",
    "Densidad poblacional": "densidad_pob",
    "% Personas que Reciben Jubilacion" : "Personas que reciben jubilación o pensión (65 años y más)_%",

}

# Grupos etarios para la pestaña de comparación
GRUPOS_ETARIOS = {
    "0 a 17 años (%)": "Población de 0 a 17 años_%",
    "18 a 29 años (%)": "Población de 18 a 29 años_%",
    "30 a 54 años (%)": "Población de 30 a 54 años_%",
    "55 a 69 años (%)": "Población de 55 a 69 años_%",
    "70 años y más (%)": "Población de 70 años y más_%",
}

# Colores de las escalas (de valor bajo a valor alto)
COLORES_ESCALA = ["#2c7bb6", "#ffffbf", "#d7191c"]

FONDO_MAPA = "oscuro"          # "negro" (liso, sin calles) o "oscuro" (con calles)
COLOR_SIN_DATOS = "#3a3a3a"   # radios sin avisos
COLOR_BORDE = "#888888"       # borde de los polígonos (se ve mejor sobre negro)
st.set_page_config(layout="wide")
# =====================================================================
# 2. CARGA DE DATOS
# =====================================================================

@st.cache_data
def cargar_datos(ruta):
    """
    Lee el csv, convierte la geometría WKT en polígonos y arma
    las columnas auxiliares que usan las funciones de análisis.
    Devuelve el df y un diccionario {zona: polígono de la zona}.
    """
    df = pd.read_csv(ruta)

    # Paso el texto WKT a polígonos de shapely
    df = df.dropna(subset=["Geometría en WKT"])
    df["geometria"] = df["Geometría en WKT"].apply(wkt.loads)

    # Ambientes redondeado (en el csv viene como promedio por radio)
    df["ambientes_red"] = df["ambientes"].round()

    # Antigüedad en rangos, para la tabla pivot
    df["antiguedad_info"] = pd.cut(
        df["antiguedad"],
        bins=[-1, 0.5, 5, 10, 15, 25, 35, float("inf")],
        labels=["A estrenar", "1-5", "6-10", "11-15", "16-25", "26-35", "36 o más"],
    )

    # Uno los radios de cada zona para tener un polígono por zona
    geo_zonas = {}
    for zona, grupo in df.groupby("zona"):
        geo_zonas[zona] = unary_union(list(grupo["geometria"]))

    return df, geo_zonas


# =====================================================================
# 3. FUNCIONES DE ANÁLISIS
# =====================================================================

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


# =====================================================================
# 4. FUNCIONES DE MAPAS
# =====================================================================

def mapa_base():
    """Mapa vacío centrado en La Plata, con fondo negro u oscuro según la configuración."""
    m = folium.Map(location=CENTRO_MAPA, zoom_start=ZOOM_INICIAL, tiles=None)

    if FONDO_MAPA == "oscuro":
        # Fondo gris oscuro de Esri, con calles
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Fondo oscuro",
        ).add_to(m)
    else:
        # Sin tiles: solo pinto el fondo de negro
        m.get_root().header.add_child(
            folium.Element("<style>.leaflet-container {background: #000000;}</style>")
        )

    return m

def mapa_poligonos(df_geo, columna_valor, columna_nombre):
    """
    Pinta polígonos según una columna.
    Los que no tienen dato se dibujan igual, en gris, para que no queden huecos.
    """
    m = mapa_base()

    # La escala se arma solo con los que tienen dato
    datos = df_geo.dropna(subset=[columna_valor])
    escala = None
    if not datos.empty:
        minimo = datos[columna_valor].min()
        maximo = datos[columna_valor].max()
        if minimo == maximo:
            maximo = minimo + 1
        escala = cm.LinearColormap(COLORES_ESCALA, vmin=minimo, vmax=maximo, caption=columna_valor)

    # Recorro TODOS los polígonos, tengan dato o no
    for _, fila in df_geo.iterrows():
        valor = fila[columna_valor]

        if pd.isna(valor) or escala is None:
            color = COLOR_SIN_DATOS
            texto = f"{fila[columna_nombre]}: sin datos"
        else:
            color = escala(valor)
            texto = f"{fila[columna_nombre]}: {valor:,.2f}"

        folium.GeoJson(
            mapping(fila["geometria"]),
            style_function=lambda x, color=color: {
                "fillColor": color,
                "color": COLOR_BORDE,
                "weight": 0.5,
                "fillOpacity": 0.7,
            },
            tooltip=texto,
        ).add_to(m)

    if escala is not None:
        escala.add_to(m)
    return m

def mapa_puntos(df, columna_valor):
    """
    Un círculo por radio con avisos, ubicado en la lat/long promedio de los inmuebles.
    El color depende de la columna elegida.
    El tamaño depende de la cantidad de avisos, salvo en "a estrenar" y "en construcción":
    ahí depende solo de los avisos que cumplen esa condición.
    """
    m = mapa_base()
    datos = df.dropna(subset=["latitud", "longitud", columna_valor])
    if datos.empty:
        return m

    # Columna que define el tamaño del círculo
    if columna_valor in ["cantidad_a_estrenar", "cantidad_en_construccion"]:
        columna_tamaño = columna_valor
    else:
        columna_tamaño = "cantidad_avisos"

    if columna_tamaño != "cantidad_avisos":
        datos = datos[datos[columna_tamaño] > 0]

    minimo = datos[columna_valor].min()
    maximo = datos[columna_valor].max()
    if minimo == maximo:
        maximo = minimo + 1
    escala = cm.LinearColormap(COLORES_ESCALA, vmin=minimo, vmax=maximo, caption=columna_valor)

    for _, fila in datos.iterrows():
        radio = min(3 + fila[columna_tamaño], 15)   # tope para que no queden gigantes
        folium.CircleMarker(
            location=[fila["latitud"], fila["longitud"]],
            radius=radio,
            color=escala(fila[columna_valor]),
            fill=True,
            fill_opacity=0.8,
            tooltip=(
                f"{fila['zona']}<br>"
                f"{columna_valor}: {fila[columna_valor]:,.2f}<br>"
                f"Avisos: {int(fila['cantidad_avisos'])}"
            ),
        ).add_to(m)

    escala.add_to(m)
    return m


def agregar_geometria_zonas(df_comparativo, geo_zonas):
    """Le pega a la tabla por zona el polígono de cada zona."""
    df = df_comparativo.copy()
    df["geometria"] = df["zona"].map(geo_zonas)
    return df.dropna(subset=["geometria"])


def mostrar_mapa(m, clave):
    """Muestra un mapa folium en streamlit. La clave tiene que ser distinta para cada mapa."""
    st_folium(m, height=500, use_container_width=True, returned_objects=[], key=clave)


# =====================================================================
# 5. LA PÁGINA
# =====================================================================

def main():
    st.title("Mapas de inmuebles y censo - La Plata")

    df, geo_zonas = cargar_datos(RUTA_CSV)
    todas_las_variables = {**VARIABLES_INMUEBLES, **VARIABLES_CENSO}

    tab_radios, tab_zonas, tab_etario, tab_puntos, tab_pivot = st.tabs([
        "Por radio censal",
        "Ranking por zona",
        "Grupo etario",
        "Avisos",
        "Tabla pivot",
    ])

    # ----- Pestaña 1: cada radio censal pintado por una variable -----
    with tab_radios:
        nombre = st.selectbox("Variable", list(todas_las_variables.keys()), key="var_radios")
        columna = todas_las_variables[nombre]

        col1, col2, col3 = st.columns(3)
        col1.metric("Promedio", f"{df[columna].mean():,.2f}")
        col2.metric("Mínimo", f"{df[columna].min():,.2f}")
        col3.metric("Máximo", f"{df[columna].max():,.2f}")

        mostrar_mapa(mapa_poligonos(df, columna, "Código de radio."), "mapa_radios")

    # ----- Pestaña 2: ranking de zonas contra el promedio -----
    with tab_zonas:
        nombre = st.selectbox("Variable", list(todas_las_variables.keys()), key="var_zonas")
        columna = todas_las_variables[nombre]

        promedio, df_comp = comparacion_con_valor_normal(df, columna, min_props=MIN_PROPS)
        st.metric("Promedio de las zonas", f"{promedio:,.2f}")

        # Mapa: cada zona pintada según cuánto se aleja del promedio
        df_geo = agregar_geometria_zonas(df_comp, geo_zonas)
        mostrar_mapa(mapa_poligonos(df_geo, columna, "zona"), "mapa_zonas")

        st.subheader("Diferencia contra el promedio")
        st.bar_chart(df_comp.set_index("zona")["Diferencia (Puntos)"])
        st.dataframe(df_comp, hide_index=True)

    # ----- Pestaña 3: zonas con más de un grupo etario y su valor -----
    with tab_etario:
        col1, col2 = st.columns(2)
        nombre_grupo = col1.selectbox("Grupo etario", list(GRUPOS_ETARIOS.keys()))
        nombre_valor = col2.selectbox("Valor a comparar", list(VARIABLES_INMUEBLES.keys()), key="var_etario")

        prom_etario, df_etario, prom_valor, df_valor = comparacion_por_grupo_etario(
            df, GRUPOS_ETARIOS[nombre_grupo], VARIABLES_INMUEBLES[nombre_valor], min_props=MIN_PROPS
        )

        col1, col2, col3 = st.columns(3)
        col1.metric(f"Promedio {nombre_grupo}", f"{prom_etario:,.2f}")
        col2.metric("Zonas por encima", len(df_valor))
        col3.metric(f"Promedio {nombre_valor} en esas zonas", f"{prom_valor:,.2f}")

        if df_valor.empty:
            st.info("No hay zonas que cumplan el mínimo de propiedades.")
        else:
            df_geo = agregar_geometria_zonas(df_valor, geo_zonas)
            mostrar_mapa(mapa_poligonos(df_geo, VARIABLES_INMUEBLES[nombre_valor], "zona"), "mapa_etario")

            st.bar_chart(df_valor.set_index("zona")["Diferencia (Puntos)"])
            st.dataframe(df_valor, hide_index=True)

    # ----- Pestaña 4: puntos con los avisos -----
    with tab_puntos:
        nombre = st.selectbox("Color según", list(VARIABLES_INMUEBLES.keys()), key="var_puntos")
        st.caption(
            "El tamaño del círculo depende de la cantidad de avisos "
            "(en 'A estrenar' y 'En construcción', solo de los avisos que cumplen esa condición)."
        )
        mostrar_mapa(mapa_puntos(df, VARIABLES_INMUEBLES[nombre]), "mapa_puntos")

    # ----- Pestaña 5: tabla pivot ambientes x antigüedad -----
    with tab_pivot:
        col1, col2 = st.columns(2)
        nombre = col1.selectbox("Valor", list(VARIABLES_INMUEBLES.keys()), key="var_pivot")
        funcion = col2.radio("Cálculo", ["mean", "count"], horizontal=True)

        tabla = tabla_pivot(
            df,
            index="ambientes_red",
            columns="antiguedad_info",
            values=VARIABLES_INMUEBLES[nombre],
            aggfunc=funcion,
            min_props=3,
            max_index=6,
        )
        tabla.columns = tabla.columns.astype(str)   # streamlit necesita nombres de texto

        st.dataframe(tabla)
        st.bar_chart(tabla)


main()