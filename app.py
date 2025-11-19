import streamlit as st
import pandas as pd
import io
import re
from streamlit_option_menu import option_menu
import folium
from streamlit_folium import st_folium
from folium.plugins import AntPath

# ==============================================================
# 🔧 UTILIDADES
# ==============================================================

def read_uploaded_csv_with_encoding(uploaded_file, delimiter=','):
    try:
        data = uploaded_file.read()
        decoded_data = data.decode('utf-8')
        df = pd.read_csv(io.StringIO(decoded_data), delimiter=delimiter)
        return df
    except UnicodeDecodeError:
        try:
            decoded_data = data.decode('latin-1')
            df = pd.read_csv(io.StringIO(decoded_data), delimiter=delimiter)
            return df
        except Exception:
            st.error("❌ Error al leer el archivo CSV.")
            return None


def normalize_cols(df):
    df.columns = [
        re.sub(r'[^a-z0-9_]', '', col.lower().replace('á','a')
        .replace('é','e').replace('í','i').replace('ó','o')
        .replace('ú','u').replace('ñ','n')).strip()
        for col in df.columns
    ]
    return df


def apply_column_map(df):
    rename_map = {
        'latitude': 'latitud',
        'lat': 'latitud',
        'latitud_': 'latitud',
        'lng': 'longitud',
        'lon': 'longitud',
        'long': 'longitud',
        'longitud_': 'longitud',
        'location': 'ubicacion',
        'direccion': 'ubicacion',
        'sucursal': 'ubicacion'
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df


def validate_location_columns(df):
    required = ['ubicacion', 'latitud', 'longitud']
    missing = [c for c in required if c not in df.columns]

    if missing:
        st.error(f"❌ El archivo NO contiene las columnas requeridas: {missing}")
        st.stop()


# ==============================================================
# 🌐 CONFIG DE PÁGINA
# ==============================================================

st.set_page_config(page_title="Seguimiento de Rutas", layout="wide")
st.title("🚚 Sistema Optimizado de Predicción y Seguimiento de Rutas")

# ==============================================================
# 📌 MENÚ LATERAL MODERNO
# ==============================================================

with st.sidebar:
    selected = option_menu(
        "Menú Principal",
        ["Carga de Ubicaciones", "Mapa General", "Seguimiento por Ruta"],
        icons=["upload", "map", "geo-alt"],
        menu_icon="cast",
        default_index=0
    )

# ==============================================================
# 🟦 1. CARGA DE UBICACIONES
# ==============================================================

if selected == "Carga de Ubicaciones":
    st.header("📂 Subir Archivo de Ubicaciones")
    uploaded_file = st.file_uploader("Sube un archivo CSV con ubicaciones:", type="csv")

    if uploaded_file:
        df = read_uploaded_csv_with_encoding(uploaded_file)

        if df is not None:
            df = normalize_cols(df)
            df = apply_column_map(df)
            validate_location_columns(df)

            df['latitud'] = pd.to_numeric(df['latitud'], errors='coerce')
            df['longitud'] = pd.to_numeric(df['longitud'], errors='coerce')

            df.dropna(subset=['latitud', 'longitud'], inplace=True)

            st.session_state['ubicaciones'] = df

            st.success("✅ Archivo cargado y validado correctamente.")
            st.dataframe(df, use_container_width=True)

# ==============================================================
# 🟩 2. MAPA GENERAL
# ==============================================================

if selected == "Mapa General":
    st.header("🌍 Mapa General de Ubicaciones")

    if 'ubicaciones' not in st.session_state:
        st.warning("⚠ Primero debes cargar un archivo CSV en la sección 'Carga de Ubicaciones'")
        st.stop()

    df = st.session_state['ubicaciones']

    # Crear mapa centrado
    m = folium.Map(location=[df['latitud'].mean(), df['longitud'].mean()], zoom_start=12)

    for _, row in df.iterrows():
        folium.Marker(
            location=[row['latitud'], row['longitud']],
            popup=row['ubicacion'],
            tooltip=row['ubicacion']
        ).add_to(m)

    st_folium(m, width=900, height=500)

# ==============================================================
# 🟥 3. SEGUIMIENTO POR RUTA
# ==============================================================

if selected == "Seguimiento por Ruta":
    st.header("📍 Seguimiento Detallado por Ruta")

    if 'ubicaciones' not in st.session_state:
        st.warning("⚠ Primero debes cargar un archivo CSV.")
        st.stop()

    df = st.session_state['ubicaciones']

    # Selección de ruta
    ruta = st.selectbox("Selecciona una ruta/ubicación a seguir:", df['ubicacion'].unique())

    df_ruta = df[df['ubicacion'] == ruta]

    # Crear mapa con AntPath (línea animada)
    m = folium.Map(location=[df_ruta['latitud'].mean(), df_ruta['longitud'].mean()], zoom_start=14)

    coords = df_ruta[['latitud', 'longitud']].values.tolist()

    AntPath(
        coords,
        color="blue",
        weight=5,
        delay=700
    ).add_to(m)

    for _, row in df_ruta.iterrows():
        folium.Marker(
            location=[row['latitud'], row['longitud']],
            popup=row['ubicacion'],
            tooltip=row['ubicacion']
        ).add_to(m)

    st_folium(m, width=900, height=500)

    st.subheader("📄 Datos de esta ruta")
    st.dataframe(df_ruta, use_container_width=True)
