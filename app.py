import streamlit as st

# 1. Definir tus páginas usando st.Page (asegurate de tener los archivos creados)
# Podés asignarles un título visible (tu "H2") y un emoji/ícono
analisis_general= st.Page("pages/analisis_general.py", title="Analisis Interno", icon="📊")
competencia = st.Page("pages/competencia.py", title="Competencia", icon="🎯")
mapa_general = st.Page("pages/mapa_general.py", title="Mapa del Mercado", icon="🗺️")

zona_especifica = st.Page("pages/zona_especifica.py", title="Analisis por Zona", icon="📍")
mapa_buscador = st.Page("pages/mapa_buscador.py", title="Mapa Buscador", icon="🔍")

analisis_interno = st.Page("pages/analisis_interno.py", title="Analisis Interno", icon="🏢")
mapa_propio = st.Page("pages/mapa_propio.py", title="Mapa Propio", icon="📌")

evolucion = st.Page("pages/evolucion.py", title="Evolucion del Mercado", icon="📈")

app_pag = st.Page("app.py", title="App Principal", icon="🏠")

# 2. Agrupar las páginas en un diccionario. 
# Los nombres de las claves ("Marketing", "Métrica Urbana") serán tus títulos "H1" en la barra lateral.
paginas = {
    "MERCADO": [analisis_general, competencia, mapa_general],
    "ZONAS": [zona_especifica, mapa_buscador],
    "INTERNO": [analisis_interno, mapa_propio],
    "EVOLUCIÓN": [evolucion]
}

# 3. Inicializar y correr la navegación
pg = st.navigation(paginas)
pg.run()
