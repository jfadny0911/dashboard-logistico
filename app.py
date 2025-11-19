# app.py - ChivoFast Dashboard (versión corregida y robusta)
import os
import streamlit as st
import pandas as pd
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
import numpy as np
import math

# ----------------------------
# Rutas a archivos de ejemplo (subidos en /mnt/data)
# AÑADE AQUÍ TU ARCHIVO SUBIDO (se usa si no subes otro)
SAMPLE_CLIENTES = "/mnt/data/reporte_pedidos_entregados_colab.csv"
SAMPLE_UBIC = "/mnt/data/ubicaciones_unicas_colab (1).csv"
# ----------------------------

# ===============================
# DB: por defecto SQLite para portabilidad
# Si quieres usar Postgres, configura DATABASE_URL en env.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///chivofast_local.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})

# Lista de repartidores (simulación/por defecto)
REPARTIDORES = ["Mario", "Luigi", "Princesa", "Yoshi", "Toad"]

# Página
st.set_page_config(page_title="ChivoFast Dashboard", layout="wide")
st.title("📦 ChivoFast — Dashboard Logístico (Stable)")

# -----------------------------
# UTILIDADES
# -----------------------------
def read_uploaded_csv_with_encoding(uploaded_file, delimiter=','):
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    for enc in encodings:
        try:
            if hasattr(uploaded_file, "getvalue"):
                content = uploaded_file.getvalue().decode(enc)
                df = pd.read_csv(StringIO(content), sep=delimiter, engine='python')
            else:
                df = pd.read_csv(uploaded_file, encoding=enc)
            return df
        except Exception:
            continue
    st.error("❌ Error: No se pudo leer el archivo. Revisa la codificación y el delimitador.")
    return None

def normalize_columns(df):
    df = df.copy()
    col_map = {}
    for col in df.columns:
        c = str(col).strip().lower()
        c = c.replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n')
        c = re.sub(r'[^a-z0-9_]', '_', c)
        c = re.sub(r'_+', '_', c).strip('_')
        col_map[col] = c
    df = df.rename(columns=col_map)
    # map common names to standard
    rename_map = {
        'ubicacion': 'nombre','ubicaciones':'nombre','ubicacion_nombre':'nombre','cliente':'nombre','nombre_cliente':'nombre',
        'latitud':'lat','latitude':'lat','y':'lat',
        'longitud':'lon','longitude':'lon','lng':'lon','x':'lon','long':'lon'
    }
    for k,v in rename_map.items():
        if k in df.columns and v not in df.columns:
            df = df.rename(columns={k:v})
    return df

def haversine(lat1, lon1, lat2, lon2):
    try:
        if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
            return np.nan
        R = 6371.0
        phi1 = math.radians(float(lat1)); phi2 = math.radians(float(lat2))
        dphi = math.radians(float(lat2)-float(lat1)); dlambda = math.radians(float(lon2)-float(lon1))
        a = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2.0)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    except Exception:
        return np.nan

@st.cache_data(ttl=300)
def check_table_exists_local(name):
    try:
        with engine.connect() as conn:
            if DATABASE_URL.startswith('sqlite'):
                res = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}';"))
                return len(res.fetchall()) > 0
            else:
                res = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{name}')"))
                return res.scalar()
    except Exception:
        return False

@st.cache_data(ttl=300)
def load_table(name):
    if check_table_exists_local(name):
        try:
            with engine.connect() as conn:
                df = pd.read_sql_table(name, conn)
                df = normalize_columns(df)
                return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def clear_table(name):
    with engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {name}"))
        conn.commit()

def get_next_gestion_number(df):
    if 'orden_gestion' in df.columns and not df.empty:
        try:
            max_g = pd.to_numeric(df['orden_gestion'], errors='coerce').max()
            if pd.isna(max_g):
                return 1
            return int(max_g) + 1
        except Exception:
            return len(df) + 1
    return 1

def find_col(df, possibles):
    for p in possibles:
        if p in df.columns:
            return p
    return None

# -----------------------------
# SIDEBAR MENU
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
# VER DATOS
# -----------------------------
if selected == "Ver Datos":
    st.header("📋 Gestionar datos — Subir archivos (clientes, ubicaciones, pedidos)")
    st.markdown("Sube tus archivos CSV. El sistema normaliza encabezados automáticamente.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Clientes (CSV)")
        clientes_file = st.file_uploader("Sube archivo de CLIENTES", type=['csv'], key='upl_clientes')
        if clientes_file is None and os.path.exists(SAMPLE_CLIENTES):
            if st.button('Cargar archivo de ejemplo de clientes'):
                clientes_file = SAMPLE_CLIENTES
        if clientes_file:
            df_clientes = read_uploaded_csv_with_encoding(clientes_file)
            if df_clientes is not None:
                df_clientes = normalize_columns(df_clientes)
                if 'lat' not in df_clientes.columns or 'lon' not in df_clientes.columns or 'nombre' not in df_clientes.columns:
                    st.warning("Se han normalizado nombres de columnas. Asegúrate de que existan lat/lon/nombre. Revise la vista previa.")
                st.dataframe(df_clientes.head(200))
                if st.button('Guardar clientes en BD'):
                    with engine.connect() as conn:
                        df_clientes.to_sql('clientes', conn, if_exists='replace', index=False)
                        conn.commit()
                    st.success('Clientes guardados en la base de datos (tabla: clientes)')
                    st.cache_data.clear()
    with col2:
        st.subheader("Ubicaciones (CSV)")
        ubic_file = st.file_uploader("Sube archivo de UBICACIONES", type=['csv'], key='upl_ubic')
        if ubic_file is None and os.path.exists(SAMPLE_UBIC):
            if st.button('Cargar archivo de ejemplo de ubicaciones'):
                ubic_file = SAMPLE_UBIC
        if ubic_file:
            df_ubic = read_uploaded_csv_with_encoding(ubic_file)
            if df_ubic is not None:
                df_ubic = normalize_columns(df_ubic)
                st.dataframe(df_ubic.head(200))
                if st.button('Guardar ubicaciones en BD'):
                    with engine.connect() as conn:
                        df_ubic.to_sql('ubicaciones', conn, if_exists='replace', index=False)
                        conn.commit()
                    st.success('Ubicaciones guardadas en la base de datos (tabla: ubicaciones)')
                    st.cache_data.clear()

    st.markdown('---')
    st.subheader('Pedidos (opcional)')
    pedidos_file = st.file_uploader('Sube archivo de pedidos (CSV)', type=['csv'], key='upl_ped')
    if pedidos_file:
        df_ped = read_uploaded_csv_with_encoding(pedidos_file)
        if df_ped is not None:
            df_ped = normalize_columns(df_ped)
            st.dataframe(df_ped.head(200))
            if st.button('Guardar pedidos en entregas (append)'):
                with engine.connect() as conn:
                    df_ped.to_sql('entregas', conn, if_exists='append', index=False)
                    conn.commit()
                st.success('Pedidos añadidos a tabla entregas')
                st.cache_data.clear()

# -----------------------------
# CLIENTES
# -----------------------------
elif selected == "Clientes":
    st.header('👥 Clientes — Vista y filtros')
    df_clients = load_table('clientes')
    if df_clients.empty:
        st.info('No hay clientes cargados. Ve a "Ver Datos" para subir un CSV o carga el ejemplo.')
    else:
        dfc = df_clients.copy()
        dfc = normalize_columns(dfc)
        dfc['lat'] = pd.to_numeric(dfc.get('lat', pd.Series([])), errors='coerce')
        dfc['lon'] = pd.to_numeric(dfc.get('lon', pd.Series([])), errors='coerce')

        st.subheader('Tabla de clientes')
        st.dataframe(dfc, use_container_width=True)

        st.subheader('Filtros')
        default_cols = ['nombre','ruta','lat','lon']
        default = default_cols if set(default_cols).issubset(dfc.columns) else list(dfc.columns)[:6]
        cols = st.multiselect('Columnas a mostrar', options=list(dfc.columns), default=default)
        ruta_f = st.multiselect('Filtrar por ruta', options=sorted(dfc['ruta'].unique()) if 'ruta' in dfc.columns else [])
        estado_f = st.multiselect('Filtrar por estado', options=sorted(dfc['estado'].unique()) if 'estado' in dfc.columns else [])

        filtered = dfc.copy()
        if ruta_f: filtered = filtered[filtered['ruta'].isin(ruta_f)]
        if estado_f and 'estado' in filtered.columns: filtered = filtered[filtered['estado'].isin(estado_f)]

        st.dataframe(filtered[cols], use_container_width=True)

# -----------------------------
# MAPA (reemplazado por mapa híbrido)
# -----------------------------
elif selected == "Mapa":
    st.header('🗺️ Mapa Híbrido — Heatmap + Burbujas + Marcadores + Cluster')
    df_ubic = load_table('ubicaciones')
    df_clients = load_table('clientes')

    # elegir el dataset base para coordenadas
    if df_clients.empty and df_ubic.empty:
        st.info('No hay datos de ubicaciones o clientes. Sube archivos en "Ver Datos".')
    else:
        if not df_clients.empty:
            dfc = normalize_columns(df_clients.copy())
        else:
            dfc = normalize_columns(df_ubic.copy())

        dfc['lat'] = pd.to_numeric(dfc.get('lat'), errors='coerce')
        dfc['lon'] = pd.to_numeric(dfc.get('lon'), errors='coerce')
        dfc = dfc.dropna(subset=['lat','lon']).reset_index(drop=True)
        if dfc.empty:
            st.warning("No hay coordenadas válidas en clientes/ubicaciones.")
        else:
            # Cargar entregas para contar frecuencias por ubicación
            df_ent = load_table('entregas')
            if df_ent.empty:
                st.info('No hay entregas registradas (tabla entregas vacía).')
                # mostrar solo marcadores desde dfc
                m = folium.Map(location=[dfc['lat'].mean(), dfc['lon'].mean()], zoom_start=10, tiles="CartoDB Positron")
                for _, r in dfc.iterrows():
                    folium.CircleMarker(location=[r['lat'], r['lon']], radius=3, tooltip=str(r.get('nombre','')), color="blue", fill=True).add_to(m)
                st_folium(m, width=1000, height=600)
            else:
                # Normalizar entregas
                df_ent = normalize_columns(df_ent.copy())

                # detectar columna que identifica ubicación en entregas
                possible_cols = ['ubicacion','nombre','cliente','nombre_cliente','direccion']
                col_ubic = next((c for c in possible_cols if c in df_ent.columns), None)

                if col_ubic is None:
                    st.warning("No se encontró una columna clara de ubicación en la tabla 'entregas'. Mostraré marcadores base.")
                    m = folium.Map(location=[dfc['lat'].mean(), dfc['lon'].mean()], zoom_start=10, tiles="CartoDB Positron")
                    for _, r in dfc.iterrows():
                        folium.CircleMarker(location=[r['lat'], r['lon']], radius=3, tooltip=str(r.get('nombre','')), color="blue", fill=True).add_to(m)
                    st_folium(m, width=1000, height=600)
                else:
                    counts = df_ent.groupby(col_ubic).size().reset_index(name='freq')

                    # unir counts con dfc (join left_on=col_ubic, right_on='nombre')
                    if 'nombre' in dfc.columns:
                        merged = pd.merge(counts, dfc, left_on=col_ubic, right_on='nombre', how='inner')
                    else:
                        # si no hay 'nombre' en dfc, intentar unir por lat/lon si entregas tienen lat/lon
                        merged = pd.DataFrame()
                        if 'lat' in df_ent.columns and 'lon' in df_ent.columns:
                            # agregar frecuencias por coordenadas aproximadas (agrupando por rounded coords)
                            tmp = df_ent.copy()
                            tmp['lat_r'] = tmp['lat'].round(4)
                            tmp['lon_r'] = tmp['lon'].round(4)
                            coords_counts = tmp.groupby(['lat_r','lon_r']).size().reset_index(name='freq')
                            # merge with dfc rounded coords
                            dfc['lat_r'] = dfc['lat'].round(4); dfc['lon_r'] = dfc['lon'].round(4)
                            merged = pd.merge(coords_counts, dfc, left_on=['lat_r','lon_r'], right_on=['lat_r','lon_r'], how='inner')

                    # verificar columnas necesarias
                    if not merged.empty and {'lat','lon','freq'}.issubset(merged.columns):
                        # crear mapa híbrido
                        m = folium.Map(location=[merged['lat'].mean(), merged['lon'].mean()], zoom_start=11, tiles="CartoDB Positron")

                        # 1) HeatMap multicolor
                        HeatMap(
                            merged[['lat','lon','freq']].values.tolist(),
                            radius=22,
                            blur=30,
                            min_opacity=0.20,
                            gradient={0.1:'purple',0.3:'blue',0.5:'cyan',0.7:'lime',0.9:'yellow',1.0:'red'}
                        ).add_to(m)

                        # 2) Circulos proporcionales
                        for _, row in merged.iterrows():
                            folium.Circle(
                                location=[row['lat'], row['lon']],
                                radius=max(8, row['freq'] * 10),
                                color="blue",
                                fill=True,
                                fill_color="blue",
                                fill_opacity=0.25,
                                popup=f"{row.get(col_ubic, row.get('nombre',''))}: {int(row['freq'])} entregas"
                            ).add_to(m)

                        # 3) MarkerCluster + marcadores detallados
                        cluster = MarkerCluster().add_to(m)
                        for _, row in merged.iterrows():
                            folium.Marker(
                                location=[row['lat'], row['lon']],
                                popup=f"<b>{row.get(col_ubic, row.get('nombre',''))}</b><br>Entregas: {int(row['freq'])}",
                                icon=folium.Icon(color="blue", icon="info-sign")
                            ).add_to(cluster)

                        st_folium(m, width=1000, height=650)
                    else:
                        st.warning("No se pudieron generar capas avanzadas porque la unión de entregas y ubicaciones no produjo lat/lon/freq.")
                        # fallback: mostrar marcadores desde dfc
                        m = folium.Map(location=[dfc['lat'].mean(), dfc['lon'].mean()], zoom_start=10, tiles="CartoDB Positron")
                        for _, r in dfc.iterrows():
                            folium.CircleMarker(location=[r['lat'], r['lon']], radius=3, tooltip=str(r.get('nombre','')), color="blue", fill=True).add_to(m)
                        st_folium(m, width=1000, height=600)

# -----------------------------
# PEDIDOS
# -----------------------------
elif selected == "Pedidos":
    st.header('📦 Pedidos — Crear y administrar')
    df_ent = load_table('entregas')
    st.subheader('📄 Pedidos existentes')
    if df_ent.empty:
        st.info('No hay pedidos en la tabla entregas. Puedes cargarlos en "Ver Datos" o crear nuevos aquí.')
    else:
        st.dataframe(df_ent, use_container_width=True)

    st.markdown('---')
    st.subheader('➕ Crear nuevo pedido')
    with st.form('form_new_order'):
        nombre = st.text_input('Nombre cliente')
        orden = st.text_input('Orden gestión (opcional)')
        lat = st.text_input('Lat (opcional)')
        lon = st.text_input('Lon (opcional)')
        tipo = st.selectbox('Tipo de pedido', ['Paquete','Comida','Documento','Otro'])
        prioridad = st.selectbox('Prioridad', ['Normal','Alta','Baja'])
        repartidor = st.selectbox('Asignar repartidor (opcional)', options=REPARTIDORES)
        submit = st.form_submit_button('Crear pedido')
    if submit:
        try:
            df_ent = load_table('entregas')
            next_num = get_next_gestion_number(df_ent)
            orden_final = orden if orden else f"{next_num:04d}"
            nueva = pd.DataFrame([{
                'orden_gestion': orden_final,
                'fecha': datetime.now(),
                'nombre': nombre,
                'lat': float(lat) if lat else None,
                'lon': float(lon) if lon else None,
                'tipo_pedido': tipo,
                'prioridad': prioridad,
                'estado': 'Pendiente',
                'repartidor': repartidor
            }])
            with engine.connect() as conn:
                nueva.to_sql('entregas', conn, if_exists='append', index=False)
                conn.commit()
            st.success(f'Pedido {orden_final} creado y guardado en entregas')
            st.cache_data.clear()
        except Exception as e:
            st.error(f'Error al crear pedido: {e}')

# -----------------------------
# ASIGNACIÓN
# -----------------------------
elif selected == "Asignación":
    st.header('🚚 Asignación de repartidores')
    df_ent = load_table('entregas')
    if df_ent.empty:
        st.info('No hay pedidos para asignar. Crea pedidos en la pestaña "Pedidos" o importa en "Ver Datos"')
    else:
        pendientes = df_ent[df_ent.get('estado','').str.lower().isin(['pendiente','pendiente ' , 'pendiente'])]
        st.subheader('Pedidos pendientes')
        cols_show = [c for c in ['orden_gestion','nombre','municipio','departamento'] if c in pendientes.columns]
        st.dataframe(pendientes[cols_show].head(200), use_container_width=True)

        sel_ord = st.selectbox('Seleccionar orden', options=pendientes['orden_gestion'].tolist() if not pendientes.empty else [])
        sel_rep = st.selectbox('Seleccionar repartidor', options=REPARTIDORES)
        if st.button('Asignar repartidor') and sel_ord:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"UPDATE entregas SET repartidor = '{sel_rep}' WHERE orden_gestion = '{sel_ord}'"))
                    conn.commit()
                st.success(f'Orden {sel_ord} asignada a {sel_rep}')
                st.cache_data.clear()
            except Exception as e:
                st.error(f'Error asignando repartidor: {e}')

# -----------------------------
# KPIs (REESCRITOS ROBUSTOS)
# -----------------------------
# --- 📈 KPIs y Dashboard estilo BI ---
elif selected == "KPIs":
    st.header("📈 Indicadores Clave (KPIs)")
    
    
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

# -----------------------------
# SEGUIMIENTO
# -----------------------------
elif selected == "Seguimiento":
    st.header('🚨 Seguimiento por ruta (Activas)')
    df_ent = load_table('entregas')
    df_ubic = load_table('ubicaciones')
    if df_ent.empty:
        st.info('No hay entregas registradas')
    else:
        df_ent = normalize_columns(df_ent.copy())
        activos = df_ent[df_ent.get('estado','').astype(str).str.lower().isin(['activa','en curso','enprogreso','en curso'])]
        if activos.empty:
            st.info('No hay rutas activas')
        else:
            for _, row in activos.iterrows():
                with st.expander(f"Orden {row.get('orden_gestion','-')} — {row.get('nombre','')}"):
                    col1, col2 = st.columns([1,2])
                    with col1:
                        st.markdown(f"**Repartidor:** {row.get('repartidor','N/A')}")
                        st.markdown(f"**Estado:** {row.get('estado')}")
                        st.markdown(f"**Inicio:** {row.get('inicio_ruta')}")
                        if st.button(f"Marcar Entregado {row.get('orden_gestion')}", key=f"ent_{row.get('orden_gestion')}"):
                            with engine.connect() as conn:
                                conn.execute(text(f"UPDATE entregas SET estado='Entregado' WHERE orden_gestion='{row.get('orden_gestion')}'"))
                                conn.commit()
                            st.success('Marcada como Entregado')
                            st.cache_data.clear()
                    with col2:
                        origin = None
                        dest = None
                        if df_ubic is not None and not df_ubic.empty:
                            du = normalize_columns(df_ubic.copy())
                            du['lat'] = pd.to_numeric(du.get('lat'), errors='coerce')
                            du['lon'] = pd.to_numeric(du.get('lon'), errors='coerce')
                            origin = du[du.get('nombre')==row.get('ubicacion')] if 'nombre' in du.columns else None
                        if origin is not None and not origin.empty:
                            o = [origin.iloc[0]['lat'], origin.iloc[0]['lon']]
                        else:
                            o = [row.get('lat') or 13.7, row.get('lon') or -89.2]
                        d = [row.get('lat'), row.get('lon')]
                        # mapa mini
                        try:
                            m = folium.Map(location=[(o[0]+(d[0] or o[0]))/2,(o[1]+(d[1] or o[1]))/2], zoom_start=12)
                            folium.Marker(o, popup='Origen').add_to(m)
                            folium.Marker(d, popup='Destino').add_to(m)
                            folium.PolyLine([o,d], color='blue', weight=4).add_to(m)
                            st_folium(m, width=600, height=300)
                        except Exception:
                            st.info("No hay coordenadas válidas para mostrar mini-mapa.")

# -----------------------------
# BORRAR DATOS
# -----------------------------
elif selected == "Borrar Datos":
    st.header('🗑️ Borrar datos (Peligroso)')
    st.warning('Esto eliminará las tablas: clientes, ubicaciones, entregas')
    if st.button('Borrar TODO'):
        try:
            clear_table('clientes'); clear_table('ubicaciones'); clear_table('entregas')
            st.success('Tablas borradas')
            st.cache_data.clear()
        except Exception as e:
            st.error(f'Error: {e}')

# FIN
