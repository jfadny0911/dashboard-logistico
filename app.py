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
from datetime import datetime
import math
from typing import Optional, Tuple

# ----------------------------
# Config / sample file paths (adjust if needed)
SAMPLE_CLIENTES = "/mnt/data/reporte_pedidos_entregados_colab.csv"
SAMPLE_UBIC = "/mnt/data/ubicaciones_unicas_colab (1).csv"
# ----------------------------

# Database default (SQLite for portability)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///chivofast_local.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})

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
    df.columns = [_normalize_name(c) for c in df.columns]
    # map common names
    rename_map = {
        'ubicacion': 'nombre','ubicaciones':'nombre','ubicacion_nombre':'nombre','cliente':'nombre','nombre_cliente':'nombre',
        'latitud':'lat','latitude':'lat','y':'lat',
        'longitud':'lon','longitude':'lon','lng':'lon','x':'lon','long':'lon'
    }
    for k, v in rename_map.items():
        if k in df.columns and v not in df.columns:
            df.rename(columns={k:v}, inplace=True)
    return df

@st.cache_data(ttl=300)
def read_csv_cached(uploaded_file, delimiter=','):
    """
    Try multiple encodings and return a pandas DataFrame; cached.
    Accepts either a path (str) or a file-like object from Streamlit uploader.
    """
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    # if string path, read directly
    if isinstance(uploaded_file, str):
        for enc in encodings:
            try:
                df = pd.read_csv(uploaded_file, encoding=enc)
                return df
            except Exception:
                continue
        return None

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

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    selected = option_menu(
        "Menú",
        ["Ver Datos", "Clientes", "Mapa", "Pedidos", "Asignación", "KPIs", "Seguimiento", "Borrar Datos"],
        icons=["table","people-fill","map","box-seam","truck","bar-chart","geo-alt","trash"],
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
    with col1:
        st.subheader("Clientes (CSV)")
        clientes_file = st.file_uploader("Sube archivo de CLIENTES", type=['csv'], key='upl_clientes')
        if clientes_file is None and os.path.exists(SAMPLE_CLIENTES):
            if st.button('Cargar ejemplo de clientes'):
                clientes_file = SAMPLE_CLIENTES
        if clientes_file:
            df_clientes = read_csv_cached(clientes_file)
            if df_clientes is None:
                st.error("No se pudo leer el CSV de clientes.")
            else:
                df_clientes = normalize_columns_df(df_clientes)
                st.success("Clientes leídos (vista previa):")
                st.dataframe(df_clientes.head(200))
                if st.button('Guardar clientes en BD'):
                    with engine.connect() as conn:
                        df_clientes.to_sql('clientes', conn, if_exists='replace', index=False)
                        conn.commit()
                    st.success("Clientes guardados en BD.")
                    st.cache_data.clear()
    with col2:
        st.subheader("Ubicaciones (CSV)")
        ubic_file = st.file_uploader("Sube archivo de UBICACIONES", type=['csv'], key='upl_ubic')
        if ubic_file is None and os.path.exists(SAMPLE_UBIC):
            if st.button('Cargar ejemplo de ubicaciones'):
                ubic_file = SAMPLE_UBIC
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
                        conn.commit()
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
                    conn.commit()
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
                        tmp['lat_r'] = tmp['lat'].round(4); tmp['lon_r'] = tmp['lon'].round(4)
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
                    conn.execute(text(f"UPDATE entregas SET repartidor='{sel_rep}' WHERE orden_gestion='{sel_ord}'"))
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
    df_clients = load_table('clientes')
    df = df_clients if not df_clients.empty else df_ent
    if df.empty:
        st.info("No hay datos.")
    else:
        df = normalize_columns_df(df.copy())
        col_nombre = find_col(df, ['nombre','ubicacion','cliente','direccion'])
        col_lat = find_col(df, ['lat','latitud','latitude'])
        col_lon = find_col(df, ['lon','longitud','longitude','lng'])
        col_ruta = find_col(df, ['ruta','route','ruta_asignada'])
        col_estado = find_col(df, ['estado','status'])
        total_clientes = len(df)
        total_rutas = int(df[col_ruta].nunique()) if col_ruta and col_ruta in df.columns else 0
        atendidos = int(df[df.get(col_estado,'').astype(str).str.lower().isin(['entregado','atendido'])].shape[0]) if col_estado else 0

        # Distancias vectorizadas (cache key by basic stats)
        distancia_total = distancia_prom = cliente_mas_lejano = cliente_mas_cercano = 'No disponible'
        if col_lat and col_lon and col_lat in df.columns and col_lon in df.columns:
            df[col_lat] = pd.to_numeric(df[col_lat], errors='coerce')
            df[col_lon] = pd.to_numeric(df[col_lon], errors='coerce')
            df = df.dropna(subset=[col_lat, col_lon]).reset_index(drop=True)
            if not df.empty:
                base_lat = df[col_lat].mean(); base_lon = df[col_lon].mean()
                # vectorized calc
                df['dist_km'] = haversine_vectorized(base_lat, base_lon, df[col_lat].values, df[col_lon].values)
                distancia_total = round(float(df['dist_km'].sum()),2)
                distancia_prom = round(float(df['dist_km'].mean()),2)
                if col_nombre:
                    cliente_mas_lejano = df.sort_values('dist_km', ascending=False).iloc[0][[col_nombre,'dist_km']].to_dict()
                    cliente_mas_cercano = df.sort_values('dist_km', ascending=True).iloc[0][[col_nombre,'dist_km']].to_dict()

        # show KPIs
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total clientes", total_clientes)
        c2.metric("Total rutas", total_rutas)
        c3.metric("Atendidos", atendidos)
        c4.metric("% Entregados", f"{round((atendidos/total_clientes)*100,2) if total_clientes>0 else 0}%")
        c5,c6,c7 = st.columns(3)
        c5.metric("Tiempo promedio (min)", "No disponible")
        c6.metric("Distancia total (km)", distancia_total)
        c7.metric("Dist prom por cliente (km)", distancia_prom)

        st.markdown("---")
        st.subheader("Clientes por ruta")
        if col_ruta and col_ruta in df.columns:
            ruta_counts = df[col_ruta].value_counts().reset_index()
            ruta_counts.columns = ['ruta','clientes']
            fig = px.bar(ruta_counts, x='ruta', y='clientes')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay columna 'ruta'.")

        st.subheader("Ranking por distancia")
        if 'dist_km' in df.columns:
            cols_to_show = [c for c in [col_nombre, 'dist_km', col_ruta] if c and c in df.columns]
            if cols_to_show:
                st.dataframe(df[cols_to_show].sort_values(by='dist_km', ascending=False).head(50))
            else:
                st.warning("No hay columnas para mostrar ranking.")
        else:
            st.info("No se calculó distancias (faltan lat/lon).")

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
        if activos.empty:
            st.info("No hay rutas activas.")
        else:
            for _, row in activos.iterrows():
                with st.expander(f"Orden {row.get('orden_gestion','-')} — {row.get('nombre','')}"):
                    c1,c2 = st.columns([1,2])
                    with c1:
                        st.markdown(f"**Repartidor:** {row.get('repartidor','N/A')}")
                        st.markdown(f"**Estado:** {row.get('estado')}")
                        st.markdown(f"**Inicio:** {row.get('inicio_ruta')}")
                        if st.button(f"Marcar Entregado {row.get('orden_gestion')}", key=f"ent_{row.get('orden_gestion')}"):
                            with engine.connect() as conn:
                                conn.execute(text(f"UPDATE entregas SET estado='Entregado' WHERE orden_gestion='{row.get('orden_gestion')}'"))
                                conn.commit()
                            st.success("Marcada como entregada.")
                            st.cache_data.clear()
                    with c2:
                        # attempt to get origin from ubicaciones else use row coords
                        origin = None
                        if not df_ubic.empty:
                            du = normalize_columns_df(df_ubic.copy())
                            du['lat'] = pd.to_numeric(du.get('lat'), errors='coerce'); du['lon'] = pd.to_numeric(du.get('lon'), errors='coerce')
                            origin = du[du.get('nombre')==row.get('ubicacion')] if 'nombre' in du.columns else None
                        if origin is not None and not origin.empty:
                            o = [origin.iloc[0]['lat'], origin.iloc[0]['lon']]
                        else:
                            o = [row.get('lat') or 13.7, row.get('lon') or -89.2]
                        d = [row.get('lat'), row.get('lon')]
                        try:
                            m = folium.Map(location=[(o[0]+(d[0] or o[0]))/2, (o[1]+(d[1] or o[1]))/2], zoom_start=12, tiles="CartoDB Positron")
                            folium.Marker(o, popup="Origen").add_to(m)
                            folium.Marker(d, popup="Destino").add_to(m)
                            folium.PolyLine([o,d], color="blue", weight=4).add_to(m)
                            st_folium(m, width=600, height=300)
                        except Exception:
                            st.info("No hay coordenadas válidas para mini-mapa.")

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
