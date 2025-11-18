import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap 
import random
from io import StringIO
import re
from datetime import datetime, timedelta
import time
import numpy as np 

# ===============================
# 🔗 Conexión a la base de datos PostgreSQL de Render
# ===================================================
# Asegúrate de configurar esta variable de entorno en tu entorno de despliegue
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chivofast_db_user:VOVsj9KYQdoI7vBjpdIpTG1jj2Bvj0GS@dpg-d34osnbe5dus739qotu0-a.oregon-postgres.render.com/chivofast_db"
)
engine = create_engine(DATABASE_URL)

# Lista de repartidores disponibles (para simulación)
REPARTIDORES = ["Mario", "Luigi", "Princesa", "Yoshi", "Toad"]

# Configuración de página
st.set_page_config(page_title="ChivoFast Dashboard", layout="wide")
st.title("📦 Dashboard Predictivo - ChivoFast")

# ===============================
# 📋 Funciones para la Base de Datos y Manejo de Archivos
# ===================================================
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
            result = conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'entregas')"))
            return result.scalar()
        except Exception:
            return False

@st.cache_data(ttl=600)
def load_data_from_db():
    """
    Carga todos los datos de la tabla 'entregas' en un DataFrame y normaliza los nombres de columna.
    """
    if check_table_exists():
        with engine.connect() as conn:
            try:
                df = pd.read_sql_table('entregas', conn)
                
                # Aplicación de normalización de columnas al leer de la BD
                df.columns = [
                    re.sub(r'[^a-z0-9_]', '', col.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n').replace(' ', '_').strip())
                    for col in df.columns
                ]
                
                return df
            except Exception:
                return pd.DataFrame()
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

def get_next_gestion_number(df):
    """Obtiene el siguiente número de gestión secuencial."""
    if 'orden_gestion' in df.columns and not df.empty:
        max_gestion = pd.to_numeric(df['orden_gestion'], errors='coerce').max()
        if pd.isna(max_gestion):
            return 1
        return int(max_gestion) + 1
    return 1

def clean_coord(coord):
    """Limpia y normaliza cadenas de coordenadas."""
    if pd.isna(coord) or not str(coord).strip():
        return None 
    return str(coord).replace('° N', '').replace('° O', '').strip()

# ===============================
# 📋 Menú lateral
# ===============================
menu = st.sidebar.radio("Menú", ["Ver Datos", "KPIs", "Ingresar Pedido", "Predicción de Rutas", "Seguimiento de Rutas", "Borrar Datos"])

# --- 📦 Sección para agregar y ver datos ---
if menu == "Ver Datos":
    st.header("📋 Datos almacenados")
    
    # GUÍA DE COLUMNAS AÑADIDA AQUÍ
    st.subheader("💡 Guía de Estructura de Archivo CSV/Excel")
    st.markdown("""
    Para una carga correcta, tu archivo CSV debe tener los siguientes **nombres y formatos de columna** (el orden es flexible). El sistema asume que el delimitador es la **coma (,)**.
    """)
    
    # Tabla con la guía de formato
    guide_data = {
        "Columna Clave": ["Ubicación", "Municipio", "Departamento", "Latitud", "Longitud", "Tipo de Pedido", "Clima", "Tráfico", "Tiempo de Entrega", "Retraso"],
        "Nombre del Sistema": ["ubicacion", "municipio", "departamento", "latitud", "longitud", "tipo_pedido", "clima", "trafico", "tiempo_entrega", "retraso"],
        "Formato Requerido": ["Texto", "Texto", "Texto (ej: San Salvador)", "Número Decimal (ej: 13.70)", "Número Decimal (ej: -89.23)", "Texto", "Texto", "Texto (Bajo, Medio, Alto)", "Número (minutos)", "Número (minutos)"],
    }
    guide_df = pd.DataFrame(guide_data)
    st.dataframe(guide_df, hide_index=True)

    st.markdown("---")
    
    # Lógica de carga de archivo
    uploaded_db_file = st.file_uploader("Sube tu base de datos de entregas (CSV)", type=["csv"], key="db_file_uploader")
    if uploaded_db_file is not None:
        st.warning("⚠️ Al subir un archivo, se **reemplazará** la tabla `entregas` completa en la base de datos.")
        if st.button("➕ Guardar base de datos"):
            try:
                # Intentar leer usando coma (,) como delimitador
                df_to_load = read_uploaded_csv_with_encoding(uploaded_db_file, delimiter=',')
                if df_to_load is not None:
                    
                    # Normalizar nombres de columnas
                    df_to_load.columns = [
                        re.sub(r'[^a-z0-9_]', '', col.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n').replace(' ', '_').strip())
                        for col in df_to_load.columns
                    ]
                    
                    # Lógica estándar de verificación de columnas
                    if 'orden_gestion' not in df_to_load.columns:
                        df_to_load['orden_gestion'] = [f"{i:04d}" for i in range(1, len(df_to_load) + 1)]
                        st.info("Columna 'orden_gestion' agregada automáticamente.")
                        
                    if 'estado' not in df_to_load.columns:
                        df_to_load['estado'] = 'Pendiente'
                        st.info("Columna 'estado' agregada automáticamente.")
                        
                    if 'repartidor' not in df_to_load.columns:
                        df_to_load['repartidor'] = [random.choice(REPARTIDORES) for _ in range(len(df_to_load))]
                        st.info("Columna 'repartidor' agregada automáticamente (simulada).")
                        
                    if 'inicio_ruta' not in df_to_load.columns:
                        df_to_load['inicio_ruta'] = None
                    df_to_load['inicio_ruta'] = df_to_load['inicio_ruta'].astype(str)
                    
                    if 'destino' not in df_to_load.columns:
                        df_to_load['destino'] = None
                    df_to_load['destino'] = df_to_load['destino'].astype(str)
                    
                    if 'tiempo_predicho' not in df_to_load.columns:
                        df_to_load['tiempo_predicho'] = None
                    
                    with engine.connect() as conn:
                        df_to_load.to_sql('entregas', conn, if_exists='replace', index=False) 
                        conn.commit()
                    st.success("✅ Base de datos cargada con éxito. Por favor, reinicia la aplicación para ver los datos.")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error al procesar el archivo: {e}")

    df = load_data_from_db()

    if not df.empty:
        st.dataframe(df.head(200))
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Descargar datos en CSV", csv, "datos_unificados.csv", "text/csv")
    else:
        st.info("No hay datos en la tabla. Sube un archivo en la sección de arriba para empezar.")

# --- 📈 KPIs y Dashboard estilo BI ---
elif menu == "KPIs":
    st.header("📈 Indicadores Clave (KPIs)")
    df = load_data_from_db()
    
    if not df.empty:
        # Verifica la existencia de columnas clave para evitar errores
        if 'departamento' not in df.columns or 'municipio' not in df.columns or 'tipo_pedido' not in df.columns:
            st.error("Error de datos: Faltan columnas clave ('departamento', 'municipio', 'tipo_pedido'). Por favor, asegúrate de que el CSV subido sea correcto y que el proceso de carga se haya completado sin errores.")
            st.stop()

        total_registros = len(df)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total registros", total_registros)
        
        numeric_cols = df.select_dtypes(include="number").columns
        if not numeric_cols.empty:
            avg_global = round(df[numeric_cols].mean().mean(), 2)
            max_global = round(df[numeric_cols].max().max(), 2)
            col2.metric("🔹 Promedio global", avg_global)
            col3.metric("📈 Máximo global", max_global)

        st.subheader("Filtros para análisis detallado")
        
        # Filtro de Repartidor
        col_select_repartidor = st.selectbox(
            'Selecciona el Repartidor:',
            options=['Todos'] + (sorted(df['repartidor'].unique()) if 'repartidor' in df.columns else [])
        )

        col_select_departamento, col_select_municipio, col_select_tipo_pedido = st.columns(3)
        
        with col_select_departamento:
            selected_departamento = st.selectbox(
                'Selecciona el Departamento:',
                options=df['departamento'].unique()
            )

        with col_select_municipio:
            municipios_disponibles = df[df['departamento'] == selected_departamento]['municipio'].unique()
            selected_municipio = st.selectbox(
                'Selecciona el Municipio:',
                options=municipios_disponibles
            )

        with col_select_tipo_pedido:
            tipo_pedido_disponibles = df['tipo_pedido'].unique()
            selected_tipo_pedido = st.selectbox(
                'Selecciona el Tipo de Pedido:',
                options=tipo_pedido_disponibles
            )

        filtered_df = df[
            (df['departamento'] == selected_departamento) &
            (df['municipio'] == selected_municipio) &
            (df['tipo_pedido'] == selected_tipo_pedido)
        ]

        if 'repartidor' in df.columns and col_select_repartidor != 'Todos':
            filtered_df = filtered_df[filtered_df['repartidor'] == col_select_repartidor]

        if not filtered_df.empty:
            st.markdown("---")
            st.subheader(f"Análisis para {selected_tipo_pedido} en {selected_municipio}, {selected_departamento}")
            
            fig_clima = px.box(filtered_df, x='clima', y='tiempo_entrega',
                                 title='Tiempo de Entrega por Clima',
                                 labels={'clima': 'Clima', 'tiempo_entrega': 'Tiempo de Entrega (min)'},
                                 color='clima')
            st.plotly_chart(fig_clima, use_container_width=True)

            df_retraso_trafico = filtered_df.groupby('trafico')['retraso'].mean().reset_index()
            fig_trafico = px.bar(df_retraso_trafico, x='trafico', y='retraso',
                                 title='Retraso Promedio por Tráfico',
                                 labels={'trafico': 'Nivel de Tráfico', 'retraso': 'Retraso Promedio (min)'},
                                 color='trafico')
            st.plotly_chart(fig_trafico, use_container_width=True)
            
            fig_distribucion = px.histogram(filtered_df, x='tiempo_entrega', nbins=20,
                                             title='Distribución del Tiempo de Entrega',
                                             labels={'tiempo_entrega': 'Tiempo de Entrega (min)'},
                                             color='tipo_pedido')
            st.plotly_chart(fig_distribucion, use_container_width=True)

            if 'repartidor' in filtered_df.columns and len(filtered_df['repartidor'].unique()) > 1:
                 df_repartidor = filtered_df.groupby('repartidor')['tiempo_entrega'].mean().reset_index()
                 fig_repartidor = px.bar(df_repartidor, x='repartidor', y='tiempo_entrega',
                                     title='Promedio de Tiempo de Entrega por Repartidor',
                                     labels={'repartidor': 'Repartidor', 'tiempo_entrega': 'Tiempo Promedio (min)'},
                                     color='repartidor')
                 st.plotly_chart(fig_repartidor, use_container_width=True)


        else:
            st.warning("No hay datos para la combinación de filtros seleccionada.")
    else:
        st.info("No hay datos en la base de datos para mostrar los KPIs.")

# --- 🆕 Sección para ingresar un nuevo pedido ---
elif menu == "Ingresar Pedido":
    st.header("📝 Ingresar una Nueva Orden de Visita")
    
    df = load_data_from_db()
    if df.empty:
        st.warning("No hay datos en la base de datos para generar predicciones. Por favor, carga un archivo en la sección 'Ver Datos'.")
    else:
        if 'orden_gestion' not in df.columns:
             st.error("Error: La columna 'orden_gestion' no está en los datos cargados. Por favor, asegúrate de subir un archivo correcto en 'Ver Datos'.")
             st.stop()
             
        if 'orden_gestion_nueva' not in st.session_state:
            st.session_state['orden_gestion_nueva'] = ""

        if st.button("Generar Gestión"):
            nueva_gestion = get_next_gestion_number(df)
            st.session_state['orden_gestion_nueva'] = f"{nueva_gestion:04d}"
        
        orden_gestion_display = st.text_input("Número de Gestión", value=st.session_state.get('orden_gestion_nueva', ''), disabled=True)

        col1, col2 = st.columns(2)
        with col1:
            departamentos = sorted(df['departamento'].unique())
            selected_departamento = st.selectbox("Departamento", departamentos)
            municipios = sorted(df[df['departamento'] == selected_departamento]['municipio'].unique())
            selected_municipio = st.selectbox("Municipio", municipios)
            tipos_pedido = sorted(df['tipo_pedido'].unique())
            selected_tipo_pedido = st.selectbox("Tipo de Pedido", tipos_pedido)
            selected_repartidor = st.selectbox("Repartidor Asignado", REPARTIDORES) 
        
        with col2:
            ubicaciones_en_municipio = sorted(df[(df['departamento'] == selected_departamento) & (df['municipio'] == selected_municipio)]['ubicacion'].unique())
            selected_ubicacion = st.selectbox("Ubicación", ubicaciones_en_municipio)
            climas = sorted(df['clima'].unique())
            selected_clima = st.selectbox("Clima", climas)
            traficos = sorted(df['trafico'].unique())
            selected_trafico = st.selectbox("Tráfico", traficos)

        st.subheader("Predicción de la nueva orden")
        
        if st.button("Calcular Predicción"):
            base_time = 30
            if selected_trafico == 'Medio': base_time += 15
            elif selected_trafico == 'Alto': base_time += 30
            if selected_clima == 'Lluvioso': base_time += 10
            tiempo_estimado = random.randint(base_time - 5, base_time + 5)
            st.session_state['prediccion'] = tiempo_estimado
            st.success(f"⏱️ Tiempo estimado de entrega: {tiempo_estimado} minutos")
            
        st.subheader
