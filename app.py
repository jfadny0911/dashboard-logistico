import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
import random
from io import StringIO
import re

# ===============================
# 🔗 Conexión a la base de datos PostgreSQL de Render
# ===============================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chivofast_db_user:VOVsj9KYQdoI7vBjpdIpTG1jj2Bvj0GS@dpg-d34osnbe5dus739qotu0-a.oregon-postgres.render.com/chivofast_db"
)
engine = create_engine(DATABASE_URL)

# Configuración de página
st.set_page_config(page_title="ChivoFast Dashboard", layout="wide")
st.title("📦 Dashboard Predictivo - ChivoFast")

# ===============================
# 📋 Funciones para la Base de Datos y Manejo de Archivos
# ===============================
def read_uploaded_csv_with_encoding(uploaded_file, delimiter=None):
    """
    Intenta leer un archivo CSV subido con diferentes codificaciones y detecta el delimitador.
    """
    encodings = ['latin1', 'utf-8', 'iso-8859-1', 'cp1252']
    for enc in encodings:
        try:
            file_content = uploaded_file.getvalue().decode(enc)
            df = pd.read_csv(StringIO(file_content), sep=delimiter, engine='python')
            return df
        except UnicodeDecodeError:
            continue
        except pd.errors.ParserError:
            continue
    st.error("❌ Error: No se pudo leer el archivo subido. Verifica la codificación y el delimitador.")
    return None

def check_table_exists():
    """
    Verifica si la tabla 'entregas' existe en la base de datos.
    """
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT 1 FROM entregas LIMIT 1"))
            return True
        except Exception:
            return False

def load_data_from_db():
    """
    Carga todos los datos de la tabla 'entregas' en un DataFrame.
    """
    if check_table_exists():
        with engine.connect() as conn:
            return pd.read_sql_table('entregas', conn)
    return pd.DataFrame()

def clear_database():
    """
    Borra todos los registros de la tabla 'entregas'.
    """
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM entregas"))
        conn.commit()
    st.success("🗑️ Todos los datos de la tabla `entregas` han sido eliminados.")
    st.cache_data.clear()
    st.rerun()

# ===============================
# 📋 Menú lateral
# ===============================
menu = st.sidebar.radio("Menú", ["Ver Datos", "KPIs", "Predicción de Rutas", "Borrar Datos"])

# --- 📦 Sección para agregar y ver datos ---
if menu == "Ver Datos":
    st.header("📋 Datos almacenados")
    
    uploaded_db_file = st.file_uploader("Sube tu base de datos de entregas (CSV)", type=["csv"], key="db_file_uploader")
    if uploaded_db_file is not None:
        st.warning("⚠️ Al subir un archivo, se **reemplazará** la tabla `entregas` completa en la base de datos.")
        if st.button("➕ Guardar base de datos"):
            try:
                df_to_load = read_uploaded_csv_with_encoding
