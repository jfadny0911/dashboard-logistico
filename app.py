import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
import random
import time
from io import StringIO

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
def read_csv_with_encoding_and_delimiter(file_path, delimiter=','):
    """Intenta leer un archivo CSV con diferentes codificaciones."""
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    for enc in encodings:
        try:
            return pd.read_csv(file_path, sep=delimiter, encoding=enc)
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            st.error(f"❌ Error: Archivo no encontrado en la ruta: {file_path}")
            return None
    st.error("❌ Error de codificación: No se pudo leer el archivo con las codificaciones probadas.")
    return None

def read_uploaded_csv_with_encoding(uploaded_file):
    """Intenta leer un archivo CSV subido con diferentes codificaciones y detecta el delimitador."""
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    for enc in encodings:
        try:
            # Primero, leer con el delimitador predeterminado de pandas (,)
            file_content = uploaded_file.getvalue().decode(enc)
            df = pd.read_csv(StringIO(file_content))
            return df
        except UnicodeDecodeError:
            continue
        except pd.errors.ParserError:
            # Si falla, intenta con otros delimitadores comunes
            try:
                df = pd.read_csv(StringIO(file_content), sep=';')
                return df
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

def create_and_load_table():
    """
    Unifica los archivos CSV y crea la tabla 'entregas' en la base de datos.
    """
    st.info("Unificando y cargando datos en la base de datos...")
    try:
        ubicaciones_df = read_csv_with_encoding_and_delimiter('ubicaciones_el_salvador.csv', delimiter=';')
        entregas_df = read_csv_with_encoding_and_delimiter('dataset_entregas (1).csv')
        
        if ubicaciones_df is None or entregas_df is None:
            st.warning("No se pudo cargar uno o ambos archivos locales. Abortando la carga de datos.")
            return

        entregas_df.columns = [col.replace('lÃ­nea', 'linea').replace('fecha', 'hora').replace(' ', '_') for col in entregas_df.columns]
        ubicaciones_df.columns = [col.replace(' ', '_') for col in ubicaciones_df.columns]
        
        df_unificado = pd.merge(entregas_df, ubicaciones_df, left_on='zona', right_on='departamento', how='left')
        
        with engine.connect() as conn:
            df_unificado.to_sql('entregas', conn, if_exists='replace', index=False)
            conn.commit()
        st.success("✅ Datos unificados y cargados correctamente en la base de datos.")
    except Exception as e:
        st.error(f"❌ Error al unificar y cargar los datos: {e}")

@st.cache_data(ttl=600)
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
    if not check_table_exists():
        st.warning("La tabla 'entregas' no existe en la base de datos. Haz clic en el botón para cargar los datos.")
        if st.button("➕ Agregar datos"):
            create_and_load_table()
    
    df = load_data_from_db()

    if not df.empty:
        st.dataframe(df.head(200))
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Descargar datos en CSV", csv, "datos_unificados.csv", "text/csv")
    else:
        st.info("No hay datos en la tabla. Haz clic en 'Agregar datos' para cargarlos por primera vez.")

# --- 📈 KPIs y Dashboard estilo BI ---
elif menu == "KPIs":
    st.header("📈 Indicadores Clave (KPIs)")
    df = load_data_from_db()
    
    if not df.empty:
        total_registros = len(df)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total registros", total_registros)
        
        numeric_cols = df.select_dtypes(include="number").columns
        if not numeric_cols.empty:
            avg_global = round(df[numeric_cols].mean().
