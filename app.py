import os
import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
# Se eliminan las importaciones de folium y plotly
# import plotly.express as px
# import folium
# from streamlit_folium import st_folium
# from folium.plugins import HeatMap, MarkerCluster
from streamlit_option_menu import option_menu
import random
from io import StringIO
import re
from datetime import datetime, timedelta
import math
from typing import Optional, Tuple
# Se comenta la importación de google genai y el cliente
# from google import genai 

# ----------------------------
# Database default (SQLite for portability)
# ----------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///chivofast_local.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})

# --- CLAVES API ---
# Se lee de forma segura desde las variables de entorno/Secrets de Streamlit
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 

# Inicialización del Cliente Gemini (comentado ya que no se usará)
# client = None
# if GEMINI_API_KEY:
#     try:
#         # Se usa la clave leída de forma segura
#         client = genai.Client(api_key=GEMINI_API_KEY)
#     except Exception as e:
#         # st.error no debe usarse en este nivel, solo una bandera
#         client = None

REPARTIDORES = ["Mario", "Luigi", "Princesa", "Yoshi", "Toad"]

st.set_page_config(page_title="ChivoFast — Panel Repartidor", layout="wide")
st.title("📦 ChivoFast — Panel de Repartidor")

# -----------------------------
# Utilities
# -----------------------------
def _normalize_name(col: str) -> str:
    c = str(col).strip().lower()
    c = c.replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n')
    c = re.sub(r'[^a-z0-9_]', '_', c)
    c = re.sub(r'_+', '_', c).strip('_')
    return c

def normalize_columns_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    # Mapa de nombres comunes para unificar columnas clave
    rename_map = {
        'ubicacion': 'nombre','ubicaciones':'nombre','ubicacion_nombre':'nombre','cliente':'nombre','nombre_cliente':'nombre',
        'latitud':'lat','latitude':'lat','y':'lat',
        'longitud':'lon','longitude':'lon','lng':'lon','x':'lon','long':'lon',
        'orden':'orden_gestion','id':'orden_gestion'
    }
    
    final_names = []
    seen_names = {}
    
    for col in df.columns:
        normalized_name = _normalize_name(col)
        
        # 1. Aplicar mapeo de nombres (ej: 'latitud' -> 'lat')
        if normalized_name in rename_map:
            normalized_name = rename_map[normalized_name]
            
        # 2. Resolución de duplicados (Añadir contador si el nombre ya existe)
        name = normalized_name
        if name in seen_names:
            seen_names[name] += 1
            name = f"{name}_{seen_names[name]}"
        else:
            seen_names[name] = 0
            
        final_names.append(name)
        
    df.columns = final_names
    return df

@st.cache_data(ttl=300)
def check_table_exists_local(name: str) -> bool:
    try:
        with engine.connect() as conn:
            if DATABASE_URL.startswith('sqlite'):
                res = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}';"))
                return len(res.fetchall()) > 0
            else:
                res = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{name}')"))
                return bool(res.scalar())
    except Exception:
        return False

@st.cache_data(ttl=300)
def load_table(name: str) -> pd.DataFrame:
    if not check_table_exists_local(name):
        return pd.DataFrame()
    try:
        with engine.connect() as conn:
            df = pd.read_sql_table(name, conn)
        df = normalize_columns_df(df)
        return df
    except Exception:
        return pd.DataFrame()

# -----------------------------
# SIMULACIÓN DE INICIO DE SESIÓN
# -----------------------------
st.sidebar.markdown("---")
# Se añade un selectbox para elegir el repartidor actual
repartidor_actual = st.sidebar.selectbox("👤 Repartidor Actual (Simulación de Sesión)", options=REPARTIDORES)

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    selected = option_menu(
        "Menú Repartidor",
        # Opciones exclusivas del repartidor
        ["Rutas Asignadas", "Bitácora"],
        icons=["list-task", "pencil-square"],
        menu_icon="truck",
        default_index=0,
    )

# -----------------------------
# Rutas Asignadas (Visualización)
# -----------------------------
if selected == "Rutas Asignadas":
    st.header(f"🚛 Rutas Asignadas para **{repartidor_actual}**")
    st.markdown("Esta es tu lista de tareas diarias, establecidas por gerencia.")
    
    df_ent = load_table('entregas')
    
    if df_ent.empty:
        st.info("No hay entregas cargadas en el sistema.")
        st.stop()
        
    # Filtrar por el repartidor actual y estados de ruta (Activa, Pendiente/Asignado)
    df_ent = df_ent.copy()
    col_rep = 'repartidor'
    col_estado = 'estado'
    
    # Asegurarse de que las columnas críticas existan
    if col_rep not in df_ent.columns or col_estado not in df_ent.columns:
         st.error("Error: Las columnas 'repartidor' o 'estado' no se encontraron en la tabla de entregas.")
         st.stop()
        
    # Filtrar solo las entregas para el repartidor actual y que no hayan sido finalizadas
    entregas_rep = df_ent[
        (df_ent[col_rep].astype(str) == repartidor_actual) &
        (df_ent[col_estado].astype(str).str.lower().isin(['activa', 'asignado', 'pendiente', 'en curso', 'enprogreso']))
    ]

    if entregas_rep.empty:
        st.info(f"🎉 No tienes rutas activas o pendientes asignadas para hoy, {repartidor_actual}.")
    else:
        st.success(f"Tienes **{len(entregas_rep)}** entregas pendientes/activas.")
        
        # Columnas clave para mostrar (solo visual)
        cols_show = [
            'orden_gestion', 
            'nombre', 
            'tipo_pedido', 
            'prioridad', 
            'estado'
        ]
        
        # Filtramos las columnas que realmente existen
        final_cols = [c for c in cols_show if c in entregas_rep.columns] + [c for c in entregas_rep.columns if c not in cols_show]
        
        # Mostrar las rutas asignadas (las "rutas establecidas por gerencia")
        st.dataframe(
            entregas_rep[final_cols].sort_values(by=['prioridad', 'orden_gestion'], ascending=[False, True]), 
            use_container_width=True,
            hide_index=True
        )

# -----------------------------
# Bitácora del Repartidor (Acción)
# -----------------------------
elif selected == "Bitácora":
    st.header(f"📝 Bitácora de Entrega para **{repartidor_actual}**")
    st.markdown("Registra el resultado de la entrega y añade tus comentarios.")
    
    df_ent = load_table('entregas')
    
    if df_ent.empty:
        st.warning("No hay datos de entregas cargados.")
        st.stop()
        
    # Mostrar solo órdenes activas/pendientes del repartidor
    entregas_rep = df_ent[
        (df_ent['repartidor'].astype(str) == repartidor_actual) &
        (df_ent['estado'].astype(str).str.lower().isin(['activa', 'asignado', 'pendiente', 'en curso', 'enprogreso']))
    ]
    
    if entregas_rep.empty:
        st.info("No tienes entregas activas para registrar en la bitácora.")
        st.stop()
        
    order_options = [''] + entregas_rep['orden_gestion'].astype(str).tolist()
    
    with st.form("form_bitacora"):
        
        # Selectbox para la orden a reportar
        sel_ord_input = st.selectbox(
            "Selecciona la Orden a Reportar", 
            options=order_options, 
            index=0
        )
        
        # Selección de estado
        estado_final = st.selectbox(
            "Resultado de la Entrega", 
            options=['', 'Entregado', 'Cancelado', 'Anulado'],
            index=0
        )
        
        # Campo de comentario
        comentario = st.text_area("Comentario (Razón de Cancelación/Anulación, detalles de Entrega)", height=100)
        
        submit_bitacora = st.form_submit_button("Guardar Registro de Bitácora")
        
    if submit_bitacora:
        if not sel_ord_input or not estado_final:
            st.error("⚠️ Debes seleccionar una Orden y un Resultado de Entrega.")
        else:
            try:
                # 1. Validación (Doble Check)
                if sel_ord_input not in entregas_rep['orden_gestion'].astype(str).values:
                    st.error(f"❌ La orden **{sel_ord_input}** no está activa o no está asignada a ti.")
                    st.stop()
                    
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 2. Actualización de la BD
                with engine.connect() as conn:
                    # Actualizar estado, tiempo_entrega (asumiendo que es el tiempo total o finalización), comentario
                    conn.execute(
                        text("""
                             UPDATE entregas 
                             SET estado=:estado, 
                                 tiempo_entrega=:time, 
                                 comentario_bitacora=:comment,
                                 fecha_finalizacion=:time
                             WHERE orden_gestion=:ord
                             """),
                        {
                            "estado": estado_final, 
                            "time": current_time, 
                            "comment": comentario, 
                            "ord": sel_ord_input
                        }
                    )
                    conn.commit()
                    
                st.success(f"✅ Bitácora para orden **{sel_ord_input}** guardada como **{estado_final}**.")
                st.cache_data.clear()
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al guardar la bitácora: {e}")

# Las demás secciones administrativas del código anterior han sido eliminadas o comentadas.

# EOF
