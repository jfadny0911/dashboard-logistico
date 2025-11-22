# app.py - ChivoFast Dashboard (Optimized)
import os
import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MarkerCluster
from streamlit_option_menu import option_menu
import random
from io import StringIO
import re
from datetime import datetime, timedelta
import math
from typing import Optional, Tuple
from google import genai # Importación de la librería de Google GenAI

# ----------------------------
# Config / sample file paths (AJUSTADO: RUTAS DE EJEMPLO ELIMINADAS)
# ----------------------------

# Database default (SQLite for portability)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///chivofast_local.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})

# CLAVE GEMINI (INTEGRADA DIRECTAMENTE)
GEMINI_API_KEY = "AIzaSyB4Pl0C99b5zOEvplcoBgGzS4VnmLMLIi8" 

# Inicialización del Cliente Gemini
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        st.error(f"Error al inicializar el cliente Gemini. Revisa la clave API. Detalle: {e}")
        client = None

REPARTIDORES = ["Mario", "Luigi", "Princesa", "Yoshi", "Toad"]

st.set_page_config(page_title="ChivoFast — Optimized Dashboard", layout="wide")
st.title("📦 ChivoFast — Dashboard (Optimized)")

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
def read_csv_cached(uploaded_file, delimiter=','):
    """
    Try multiple encodings and return a pandas DataFrame; cached.
    Accepts a file-like object from Streamlit uploader.
    """
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    
    # Handle uploaded file object
    for enc in encodings:
        try:
            content = uploaded_file.getvalue().decode(enc)
            df = pd.read_csv(StringIO(content), sep=delimiter, engine='python')
            return df
        except Exception:
            continue
    return None

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

def clear_table(name: str):
    with engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {name}"))
        conn.commit()

def get_next_gestion_number(df: pd.DataFrame) -> int:
    if 'orden_gestion' in df.columns and not df.empty:
        try:
            max_g = pd.to_numeric(df['orden_gestion'], errors='coerce').max()
            if pd.isna(max_g):
                return 1
            return int(max_g) + 1
        except Exception:
            return len(df) + 1
    return 1

def find_col(df: pd.DataFrame, names):
    for n in names:
        if n in df.columns:
            return n
    return None

# Vectorized haversine for speed
def haversine_vectorized(lat1, lon1, lat2, lon2):
    """
    lat/lon arrays or scalars -> returns distances in km (np.array)
    """
    lat1 = np.asarray(lat1, dtype=float)
    lon1 = np.asarray(lon1, dtype=float)
    lat2 = np.asarray(lat2, dtype=float)
    lon2 = np.asarray(lon2, dtype=float)
    # handle nan
    mask = np.isnan(lat1) | np.isnan(lon1) | np.isnan(lat2) | np.isnan(lon2)
    # convert degrees to radians
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda/2.0)**2
    R = 6371.0
    res = R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    res[mask] = np.nan
    return res

# -------------------------------------------------------------------
# 🤖 LÓGICA DEL AGENTE DE ANÁLISIS IA (CON CONEXIÓN A GEMINI)
# -------------------------------------------------------------------

def run_ai_analysis_gemini(df_input: pd.DataFrame, query: str):
    """
    Se conecta a Gemini para analizar el DataFrame y la consulta del usuario.
    """
    global client
    
    if not client:
        return "⚠️ Error de Conexión: El cliente Gemini no está inicializado. Verifica tu clave API."

    # 1. Preparar la consulta y limpiar los datos para el prompt
    
    # Usamos una muestra de 100 registros para no sobrecargar la API.
    df_sample = df_input.sample(min(100, len(df_input)), random_state=42) 
    
    # Seleccionar columnas clave para el análisis
    cols_to_analyze = ['repartidor', 'tiempo_entrega', 'retraso', 'clima', 'trafico', 'departamento', 'tipo_pedido']
    
    # Asegurar que las columnas existan antes de seleccionarlas
    valid_cols = [col for col in cols_to_analyze if col in df_sample.columns]
    df_sample_context = df_sample[valid_cols]
    
    # Convertir el DataFrame relevante a formato de texto para la IA
    data_context = df_sample_context.to_markdown(index=False)
    
    # 2. Construir el Prompt Estructurado
    system_instruction = (
        "Eres un Agente de Análisis Logístico experto llamado ChivoBot. Tu función es analizar el desempeño "
        "de las entregas basándote SÓLO en la tabla de datos que se te proporciona y responder directamente la pregunta del usuario. "
        "Calcula promedios, máximos o mínimos y sé conciso. Si no encuentras la respuesta en los datos de la muestra, "
        "indica que la información no es concluyente o no está disponible en la muestra actual."
    )
    
    prompt = f"""
    --- CONTEXTO DE DATOS DE ENTREGAS (Muestra Aleatoria) ---
    {data_context}
    --- FIN DE CONTEXTO ---
    
    Basado en el contexto de la tabla y tu rol como Agente Logístico:
    PREGUNTA DEL USUARIO: {query}
    """
    
    try:
        # 3. Enviar la solicitud a Gemini
        response = client.models.generate_content(
            model='gemini-2.5-flash', # Modelo rápido
            contents=prompt,
            config={"system_instruction": system_instruction}
        )
        
        return response.text
        
    except Exception as e:
        return f"❌ Error de API: No se pudo conectar o procesar la solicitud. Detalle: {e}"

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    selected = option_menu(
        "Menú",
        ["Ver Datos", "Clientes", "Mapa", "Pedidos", "Asignación", "KPIs", "Seguimiento", "Agente IA", "Borrar Datos"],
        icons=["table","people-fill","map","box-seam","truck","bar-chart","geo-alt","person-badge", "trash"],
        menu_icon="cast",
        default_index=0,
    )

# -----------------------------
# Ver Datos (upload)
# -----------------------------
if selected == "Ver Datos":
    st.header("📋 Subir/Administrar archivos")
    st.markdown("Sube tus CSV. El sistema normaliza y cachea lecturas pesadas.")

    col1, col2 = st.columns(2)
    # --- Clientes ---
    with col1:
        st.subheader("Clientes (CSV)")
        clientes_file = st.file_uploader("Sube archivo de CLIENTES", type=['csv'], key='upl_clientes')
        
        if clientes_file:
            df_clients = read_csv_cached(clientes_file)
            if df_clients is None:
                st.error("No se pudo leer el CSV de clientes.")
            else:
                df_clients = normalize_columns_df(df_clients)
                st.success("Clientes leídos (vista previa):")
                st.dataframe(df_clients.head(200))
                if st.button('Guardar clientes en BD'):
                    with engine.connect() as conn:
                        df_clients.to_sql('clientes', conn, if_exists='replace', index=False)
                    st.success("Clientes guardados en BD.")
                    st.cache_data.clear()
    # --- Ubicaciones ---
    with col2:
        st.subheader("Ubicaciones (CSV)")
        ubic_file = st.file_uploader("Sube archivo de UBICACIONES", type=['csv'], key='upl_ubic')
                
        if ubic_file:
            df_ubic = read_csv_cached(ubic_file)
            if df_ubic is None:
                st.error("No se pudo leer el CSV de ubicaciones.")
            else:
                df_ubic = normalize_columns_df(df_ubic)
                st.success("Ubicaciones leídas (vista previa):")
                st.dataframe(df_ubic.head(200))
                if st.button('Guardar ubicaciones en BD'):
                    with engine.connect() as conn:
                        df_ubic.to_sql('ubicaciones', conn, if_exists='replace', index=False)
                    st.success("Ubicaciones guardadas en BD.")
                    st.cache_data.clear()

    st.markdown('---')
    st.subheader('Pedidos (opcional)')
    pedidos_file = st.file_uploader('Sube archivo de pedidos (CSV)', type=['csv'], key='upl_ped')
    if pedidos_file:
        df_ped = read_csv_cached(pedidos_file)
        if df_ped is not None:
            df_ped = normalize_columns_df(df_ped)
            st.dataframe(df_ped.head(200))
            if st.button('Agregar pedidos a entregas'):
                with engine.connect() as conn:
                    df_ped.to_sql('entregas', conn, if_exists='append', index=False)
                st.success('Pedidos añadidos a entregas.')
                st.cache_data.clear()

# -----------------------------
# Clientes view
# -----------------------------
elif selected == "Clientes":
    st.header("👥 Clientes")
    df_clients = load_table('clientes')
    if df_clients.empty:
        st.info("No hay clientes cargados.")
    else:
        dfc = df_clients.copy()
        dfc['lat'] = pd.to_numeric(dfc.get('lat'), errors='coerce')
        dfc['lon'] = pd.to_numeric(dfc.get('lon'), errors='coerce')
        st.dataframe(dfc, use_container_width=True)
        # quick filters cached
        cols = list(dfc.columns)
        default_cols = ['nombre','lat','lon']
        default = [c for c in default_cols if c in cols] + cols[:3]
        sel_cols = st.multiselect("Columnas a mostrar", options=cols, default=default[:6])
        st.dataframe(dfc[sel_cols], use_container_width=True)

# -----------------------------
# Mapa (Híbrido optimizado)
# -----------------------------
elif selected == "Mapa":
    st.header("🗺️ Mapa Híbrido (optimizado)")
    df_clients = load_table('clientes')
    df_ubic = load_table('ubicaciones')
    df_ent = load_table('entregas')

    # choose coordinates source
    base = df_clients if not df_clients.empty else df_ubic
    if base.empty:
        st.info("No hay datos de coordenadas.")
    else:
        base = base.copy()
        base['lat'] = pd.to_numeric(base.get('lat'), errors='coerce')
        base['lon'] = pd.to_numeric(base.get('lon'), errors='coerce')
        base.dropna(subset=['lat','lon'], inplace=True)
        if base.empty:
            st.warning("No hay coordenadas válidas.")
        else:
            # compute frequencies from entregas if possible
            merged = pd.DataFrame()
            if not df_ent.empty:
                df_ent_n = df_ent.copy()
                # try to detect join key
                join_key = find_col(df_ent_n, ['ubicacion','nombre','cliente','nombre_cliente','direccion'])
                if join_key and 'nombre' in base.columns:
                    counts = df_ent_n.groupby(join_key).size().reset_index(name='freq')
                    merged = pd.merge(counts, base, left_on=join_key, right_on='nombre', how='inner')
                else:
                    # fallback: group by rounded lat/lon if entregas have coords
                    if 'lat' in df_ent_n.columns and 'lon' in df_ent_n.columns:
                        tmp = df_ent_n.copy()
                        tmp['lat_r'] = pd.to_numeric(tmp.get('lat')).round(4); tmp['lon_r'] = pd.to_numeric(tmp.get('lon')).round(4)
                        coords_counts = tmp.groupby(['lat_r','lon_r']).size().reset_index(name='freq')
                        base['lat_r'] = base['lat'].round(4); base['lon_r'] = base['lon'].round(4)
                        merged = pd.merge(coords_counts, base, left_on=['lat_r','lon_r'], right_on=['lat_r','lon_r'], how='inner')
            # if merged is empty, show only base markers
            if merged.empty:
                st.info("No hay datos de entregas unidos; mostrando puntos base.")
                m = folium.Map(location=[base['lat'].mean(), base['lon'].mean()], zoom_start=11, tiles="CartoDB Positron")
                # limit markers rendered for performance (sampling)
                n_points = len(base)
                max_render = st.sidebar.slider("Max markers to render (for speed)", min_value=500, max_value=5000, value=2000, step=500)
                sample_df = base if n_points <= max_render else base.sample(max_render, random_state=1)
                cluster = MarkerCluster().add_to(m)
                for _, r in sample_df.iterrows():
                    folium.CircleMarker(location=[r['lat'], r['lon']], radius=3, tooltip=str(r.get('nombre','')), color="blue", fill=True).add_to(cluster)
                st_folium(m, width=1000, height=650)
            else:
                # ensure numeric
                merged['lat'] = pd.to_numeric(merged['lat'], errors='coerce')
                merged['lon'] = pd.to_numeric(merged['lon'], errors='coerce')
                merged = merged.dropna(subset=['lat','lon'])
                if merged.empty:
                    st.warning("Después de limpiar coordenadas la unión quedó vacía.")
                else:
                    # If large dataset, downsample for marker rendering while keeping heatmap full data
                    total_points = len(merged)
                    heat_data = merged[['lat','lon','freq']].values.tolist()
                    max_markers = st.sidebar.slider("Max markers for detailed markers", min_value=500, max_value=5000, value=1500, step=500)
                    if total_points > max_markers:
                        # show full heatmap but sample markers
                        markers_df = merged.sample(max_markers, random_state=42)
                    else:
                        markers_df = merged

                    # build map
                    m = folium.Map(location=[merged['lat'].mean(), merged['lon'].mean()], zoom_start=11, tiles="CartoDB Positron")

                    # 1) Heatmap (multicolor)
                    HeatMap(heat_data, radius=18, blur=20, min_opacity=0.2,
                            gradient={0.1:'purple',0.3:'blue',0.5:'cyan',0.7:'lime',0.9:'yellow',1.0:'red'}).add_to(m)

                    # 2) proportional circles (on sampled markers_df)
                    for _, row in markers_df.iterrows():
                        folium.Circle(
                            location=[row['lat'], row['lon']],
                            radius=max(6, int(row['freq']) * 8),
                            color="blue",
                            fill=True,
                            fill_opacity=0.25,
                            popup=f"{row.get('nombre', '')}: {int(row['freq'])} entregas"
                        ).add_to(m)

                    # 3) cluster for detail (sampled)
                    cluster = MarkerCluster().add_to(m)
                    for _, row in markers_df.iterrows():
                        folium.Marker(
                            location=[row['lat'], row['lon']],
                            popup=f"<b>{row.get('nombre','')}</b><br>Entregas: {int(row['freq'])}",
                            icon=folium.Icon(color="blue", icon="info-sign")
                        ).add_to(cluster)

                    st_folium(m, width=1000, height=650)

# -----------------------------
# Pedidos (create + list)
# -----------------------------
elif selected == "Pedidos":
    st.header("📦 Pedidos")
    df_ent = load_table('entregas')
    st.subheader("Pedidos existentes")
    if df_ent.empty:
        st.info("No hay pedidos.")
    else:
        st.dataframe(df_ent, use_container_width=True)

    st.markdown("---")
    st.subheader("Crear pedido")
    with st.form("form_new"):
        nombre = st.text_input("Nombre cliente")
        orden = st.text_input("Orden (opcional)")
        lat = st.text_input("Lat (opcional)")
        lon = st.text_input("Lon (opcional)")
        tipo = st.selectbox("Tipo", ["Paquete","Comida","Documento","Otro"])
        prioridad = st.selectbox("Prioridad", ["Normal","Alta","Baja"])
        repartidor = st.selectbox("Repartidor", options=REPARTIDORES)
        submit = st.form_submit_button("Crear")
    if submit:
        try:
            df_ent = load_table('entregas')
            next_num = get_next_gestion_number(df_ent)
            orden_final = orden if orden else f"{next_num:04d}"
            nueva = pd.DataFrame([{
                "orden_gestion": orden_final,
                "fecha": datetime.now(),
                "nombre": nombre,
                "lat": float(lat) if lat else None,
                "lon": float(lon) if lon else None,
                "tipo_pedido": tipo,
                "prioridad": prioridad,
                "estado": "Pendiente",
                "repartidor": repartidor
            }])
            with engine.connect() as conn:
                nueva.to_sql('entregas', conn, if_exists='append', index=False)
                conn.commit()
            st.success(f"Pedido {orden_final} creado.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Error creando pedido: {e}")

# -----------------------------
# Asignación
# -----------------------------
elif selected == "Asignación":
    st.header("🚚 Asignación")
    df_ent = load_table('entregas')
    if df_ent.empty:
        st.info("No hay entregas.")
    else:
        pendientes = df_ent[df_ent.get('estado','').astype(str).str.lower().str.contains('pendiente')]
        st.subheader("Pendientes")
        cols_show = [c for c in ['orden_gestion','nombre','municipio','departamento'] if c in pendientes.columns]
        st.dataframe(pendientes[cols_show].head(200))
        sel_ord = st.selectbox("Orden", options=pendientes['orden_gestion'].tolist() if not pendientes.empty else [])
        sel_rep = st.selectbox("Repartidor", options=REPARTIDORES)
        if st.button("Asignar") and sel_ord:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"UPDATE entregas SET repartidor='{sel_rep}', estado='Asignado' WHERE orden_gestion='{sel_ord}'")) # Update status to 'Asignado'
                    conn.commit()
                st.success("Asignado.")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Error asignando: {e}")

# -----------------------------
# KPIs (optimized)
# -----------------------------
elif selected == "KPIs":
    st.header("📊 KPIs (Optimized)")
    df_ent = load_table('entregas')
    
    # 1. Base de datos para KPIs: Entregas
    df = df_ent.copy()
    
    if df.empty:
        st.info("No hay datos de entregas cargados.")
        st.stop()

    # Data cleaning and preparation for KPIs
    df['fecha'] = pd.to_datetime(df.get('fecha', pd.NaT), errors='coerce')
    df['tiempo_entrega'] = pd.to_numeric(df.get('tiempo_entrega'), errors='coerce')
    df['retraso'] = pd.to_numeric(df.get('retraso'), errors='coerce')
    df = df.dropna(subset=['fecha'])
    
    if df.empty:
         st.warning("Los datos de entrega no contienen fechas válidas.")
         st.stop()

    max_date = df['fecha'].max()
    
    # --- Automatización 1: Selector de Rango de Tiempo ---
    time_range = st.selectbox(
        'Automatización por Rango de Tiempo:',
        ['Total Histórico', 'Últimos 7 días', 'Últimos 30 días']
    )

    if time_range == 'Últimos 7 días':
        start_date = max_date - timedelta(days=7)
        df_filtered = df[df['fecha'] >= start_date]
    elif time_range == 'Últimos 30 días':
        start_date = max_date - timedelta(days=30)
        df_filtered = df[df['fecha'] >= start_date]
    else:
        df_filtered = df
        
    if df_filtered.empty:
         st.info("No hay datos en el rango de tiempo seleccionado.")
         st.stop()
         
    # --- Cálculo de Métricas ---
    col_estado = find_col(df_filtered, ['estado','status'])
    total_entregas = len(df_filtered)
    atendidos = int(df_filtered[df_filtered.get(col_estado,'').astype(str).str.lower().isin(['entregado','atendido'])].shape[0])
    avg_delivery_time = round(df_filtered['tiempo_entrega'].mean(), 1)
    avg_delay = round(df_filtered['retraso'].mean(), 1)
    
    # Show KPIs
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Entregas", total_entregas)
    c2.metric("Entregados / Atendidos", atendidos)
    c3.metric("Tiempo Promedio (min)", avg_delivery_time)
    c4.metric("Retraso Promedio (min)", avg_delay)
    
    st.markdown("---")
    st.subheader("Análisis de Rendimiento")

    # Filtros manuales (aplicados al df ya filtrado por tiempo)
    col_dep, col_mun, col_tipo = st.columns(3)
    
    with col_dep:
        selected_departamento = st.selectbox('Departamento', options=['Todos'] + sorted(df_filtered.get('departamento', pd.Series()).dropna().unique().tolist()))
    with col_mun:
        mun_options = df_filtered[df_filtered['departamento']==selected_departamento].get('municipio', pd.Series()).dropna().unique().tolist() if selected_departamento != 'Todos' else df_filtered.get('municipio', pd.Series()).dropna().unique().tolist()
        selected_municipio = st.selectbox('Municipio', options=['Todos'] + sorted(mun_options))
    with col_tipo:
        selected_tipo_pedido = st.selectbox('Tipo de Pedido', options=['Todos'] + sorted(df_filtered.get('tipo_pedido', pd.Series()).dropna().unique().tolist()))

    # Aplicar filtros
    final_df = df_filtered.copy()
    if selected_departamento != 'Todos':
        final_df = final_df[final_df['departamento'] == selected_departamento]
    if selected_municipio != 'Todos':
        final_df = final_df[final_df['municipio'] == selected_municipio]
    if selected_tipo_pedido != 'Todos':
        final_df = final_df[final_df['tipo_pedido'] == selected_tipo_pedido]

    if final_df.empty:
        st.info("No hay datos que coincidan con los filtros geográficos/de pedido.")
    else:
        # Gráficos Dinámicos
        
        # 1. Retraso vs Tráfico
        df_trafico = final_df.groupby('trafico')['retraso'].mean().reset_index()
        fig_trafico = px.bar(df_trafico, x='trafico', y='retraso', 
                             title='Retraso Promedio por Nivel de Tráfico', color='trafico')
        st.plotly_chart(fig_trafico, use_container_width=True)

        # 2. Distribución de Tiempos
        fig_distribucion = px.histogram(final_df, x='tiempo_entrega', color='repartidor', 
                                         title='Distribución de Tiempos de Entrega', nbins=30)
        st.plotly_chart(fig_distribucion, use_container_width=True)


# -----------------------------
# Seguimiento (mini-mapas)
# -----------------------------
elif selected == "Seguimiento":
    st.header("🚨 Seguimiento por ruta (Activas)")
    df_ent = load_table('entregas')
    df_ubic = load_table('ubicaciones')
    if df_ent.empty:
        st.info("No hay entregas.")
    else:
        df_ent = normalize_columns_df(df_ent.copy())
        activos = df_ent[df_ent.get('estado','').astype(str).str.lower().str.contains('activa|en curso|enprogreso', na=False)]
        
        # Merge coordinates from ubicaciones table
        df_merged = pd.DataFrame()
        if not df_ubic.empty:
             df_ubic = df_ubic.copy()
             # Ensure lat/lon columns are correctly named and numeric
             df_ubic['lat'] = pd.to_numeric(df_ubic.get('lat'), errors='coerce')
             df_ubic['lon'] = pd.to_numeric(df_ubic.get('lon'), errors='coerce')
             
             # Attempt merge on common name columns ('nombre' in ubicaciones and 'nombre' or similar in entregas)
             join_key = find_col(activos, ['nombre','ubicacion'])
             if join_key and 'nombre' in df_ubic.columns:
                 df_merged = pd.merge(activos, df_ubic[['nombre','lat','lon']], left_on=join_key, right_on='nombre', how='left', suffixes=('_ent','_ubic'))
             else:
                 df_merged = activos
        else:
            df_merged = activos

        if df_merged.empty:
            st.info("No hay rutas activas.")
        else:
            # Filter by repartidor
            rep_opts = ['Todos'] + sorted(df_merged.get('repartidor', pd.Series()).dropna().unique().tolist())
            sel_rep = st.selectbox("Filtrar por repartidor", options=rep_opts)
            if sel_rep != 'Todos':
                df_merged = df_merged[df_merged['repartidor'] == sel_rep]
                
            if df_merged.empty:
                 st.info(f"No hay rutas activas para {sel_rep}.")
                 st.stop()
                 
            # --- Rendering Active Routes ---
            for _, row in df_merged.iterrows():
                
                # --- TIME/PROGRESS CALCULATION ---
                try:
                    inicio_ruta_str = str(row.get('inicio_ruta'))
                    if inicio_ruta_str == 'None' or inicio_ruta_str == 'nan':
                        st.info(f"🔴 Orden {row.get('orden_gestion')} no iniciada: Falta hora de inicio.")
                        continue

                    inicio_ruta_dt = pd.to_datetime(inicio_ruta_str, errors='coerce')
                    if pd.isna(inicio_ruta_dt):
                         st.info(f"🔴 Orden {row.get('orden_gestion')}: Formato de fecha de inicio inválido.")
                         continue
                         
                    tiempo_predicho_min = pd.to_numeric(row.get('tiempo_predicho'), errors='coerce')
                    if pd.isna(tiempo_predicho_min) or tiempo_predicho_min <= 0:
                        st.error(f"❌ Orden {row.get('orden_gestion')}: Tiempo predicho inválido (0 o Nulo).")
                        continue

                    tiempo_transcurrido = datetime.now() - inicio_ruta_dt
                    tiempo_restante_segundos = tiempo_predicho_min * 60 - tiempo_transcurrido.total_seconds()

                    if tiempo_restante_segundos < 0:
                        progreso = 1.0
                        tiempo_restante_str = "¡Retraso!"
                        estado_progreso = "🔴 En Retraso"
                        color_progreso = "red"
                    else:
                        progreso = 1 - (tiempo_restante_segundos / (tiempo_predicho_min * 60))
                        total_segundos = int(tiempo_restante_segundos)
                        minutos = (total_segundos % 3600) // 60
                        segundos = total_segundos % 60
                        tiempo_restante_str = f"{minutos:02d}m {segundos:02d}s"
                        estado_progreso = "En Curso"
                        color_progreso = "blue"

                except Exception as e:
                     st.error(f"Error interno al calcular tiempo para orden {row.get('orden_gestion')}: {e}")
                     continue

                # --- COORDINATE LOGIC ---
                # Get the destination coordinates, prioritizing the merged column
                lat_dest = row.get('lat_ubic') if 'lat_ubic' in row and not pd.isna(row.get('lat_ubic')) else row.get('lat')
                lon_dest = row.get('lon_ubic') if 'lon_ubic' in row and not pd.isna(row.get('lon_ubic')) else row.get('lon')

                # Using San Salvador (approximate center) as default fallback for origin
                origin_coords = [13.70, -89.20] 
                dest_coords = [lat_dest, lon_dest]
                
                if pd.isna(lat_dest) or pd.isna(lon_dest):
                    dest_coords = None # Mark as unusable
                
                # --- Rendering ---
                st.markdown(f"### Orden #{row.get('orden_gestion')} ({row.get('repartidor')})")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("ESTADO RUTA", estado_progreso)
                c2.metric("DESTINO", row.get('nombre', 'N/A'))
                c3.metric("TIEMPO RESTANTE", tiempo_restante_str)
                c4.metric("INICIO", pd.to_datetime(row.get('inicio_ruta')).strftime('%H:%M:%S') if row.get('inicio_ruta') else 'N/A')

                
                with st.expander(f"Detalles de la Ruta {row.get('orden_gestion')}"):
                    
                    col_progreso, col_mapa = st.columns([1, 1])
                    
                    with col_progreso:
                        st.markdown(f"**Progreso ({int(progreso * 100)}% completado)**")
                        st.progress(progreso)
                        
                        st.markdown(f"**Estimado Total:** {int(tiempo_predicho_min)} min")
                        st.markdown(f"**Condiciones:** {row.get('clima','N/A')} | {row.get('trafico','N/A')}")
                        st.markdown(f"**Cliente:** {row.get('nombre','N/A')}")
                        
                        st.markdown("---")
                        if st.button(f"Marcar Entregado #{row.get('orden_gestion')}", key=f"ent_{row.get('orden_gestion')}"):
                            with engine.connect() as conn:
                                conn.execute(text(f"UPDATE entregas SET estado='Entregado' WHERE orden_gestion='{row.get('orden_gestion')}'"))
                            st.success("Marcada como entregada.")
                            st.cache_data.clear()
                            st.rerun()

                    with col_mapa:
                        if dest_coords:
                            m = folium.Map(location=[(origin_coords[0] + dest_coords[0])/2, (origin_coords[1] + dest_coords[1])/2], zoom_start=12, tiles="CartoDB Positron")
                            folium.Marker(origin_coords, popup="Origen", icon=folium.Icon(color="green", icon="play")).add_to(m)
                            folium.Marker(dest_coords, popup=f"Destino: {row.get('nombre','N/A')}", icon=folium.Icon(color="red", icon="flag")).add_to(m)
                            folium.PolyLine([origin_coords, dest_coords], color=color_progreso, weight=5).add_to(m)
                            st_folium(m, width=350, height=300, key=f"map_{row.get('orden_gestion')}")
                            st.markdown(f"[Abrir en Google Maps](http://maps.google.com/maps?saddr={origin_coords[0]},{origin_coords[1]}&daddr={dest_coords[0]},{dest_coords[1]})")
                        else:
                            st.info("Coordenadas de destino no disponibles.")
                        
                st.markdown("---")

# -----------------------------
# Agente IA (new section)
# -----------------------------
elif selected == "Agente IA":
    st.header("💬 Agente de Análisis IA (ChivoBot - Conectado a Gemini)")
    st.markdown("Pregunta sobre el desempeño logístico, repartidores, o zonas de entrega. El análisis se realiza usando el modelo **Gemini 2.5 Flash** sobre una muestra de tus datos.")
    
    df_ent = load_table('entregas')

    if df_ent.empty:
        st.warning("⚠️ No hay datos de entregas cargados para realizar análisis.")
        st.stop()

    # Data preparation for AI analysis
    df = df_ent.copy()
    
    # Area de entrada de la pregunta del usuario
    user_query = st.text_area("Escribe tu pregunta aquí (ej: '¿Cuál es el retraso promedio del repartidor Mario?')", height=100)
    
    if st.button("Obtener Respuesta IA"):
        if user_query:
            with st.spinner("Conectando con Gemini y analizando datos..."):
                # Llamar a la función de análisis de Gemini
                ai_response = run_ai_analysis_gemini(df, user_query)
                
                st.success("🤖 Respuesta de ChivoBot:")
                st.markdown(ai_response)
        else:
            st.error("Por favor, escribe una pregunta para el análisis.")

# -----------------------------
# Borrar datos
# -----------------------------
elif selected == "Borrar Datos":
    st.header("🗑️ Borrar datos")
    st.warning("Esto eliminará tablas: clientes, ubicaciones, entregas")
    if st.button("Borrar TODO"):
        try:
            clear_table('clientes'); clear_table('ubicaciones'); clear_table('entregas')
            st.success("Tablas borradas.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Error: {e}")

# EOF
