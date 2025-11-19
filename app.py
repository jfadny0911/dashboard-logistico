import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, AntPath
from streamlit_option_menu import option_menu
import random
from io import StringIO
import re
from datetime import datetime, timedelta
import time
import numpy as np
import math

# ===============================
# 🔗 Conexión a la base de datos PostgreSQL
# ===================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chivofast_db_user:VOVsj9KYQdoI7vBjpdIpTG1jj2Bvj0GS@dpg-d34osnbe5dus739qotu0-a.oregon-postgres.render.com/chivofast_db"
)
engine = create_engine(DATABASE_URL)

# Lista de repartidores (editable/subible)
REPARTIDORES = ["Mario", "Luigi", "Princesa", "Yoshi", "Toad"]

# Configuración de página
st.set_page_config(page_title="ChivoFast Dashboard", layout="wide")
st.title("📦 ChivoFast — Dashboard Logístico Mejorado")

# ===============================
# 📋 Funciones utilitarias
# ===================================================

def read_uploaded_csv_with_encoding(uploaded_file, delimiter=None):
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    for enc in encodings:
        try:
            file_content = uploaded_file.getvalue().decode(enc)
            df = pd.read_csv(StringIO(file_content), sep=delimiter, engine='python')
            return df
        except Exception:
            continue
    st.error("❌ Error: No se pudo leer el archivo. Revisa la codificación y el delimitador.")
    return None


def normalize_columns(df):
    df.columns = [
        re.sub(r'[^a-z0-9_]', '', col.lower()
               .replace('á','a').replace('é','e').replace('í','i')
               .replace('ó','o').replace('ú','u').replace('ñ','n')
               .replace(' ','_').strip())
        for col in df.columns
    ]
    return df


def check_table_exists(name):
    with engine.connect() as conn:
        try:
            result = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{name}')"))
            return result.scalar()
        except Exception:
            return False


@st.cache_data(ttl=600)
def load_table(name):
    if check_table_exists(name):
        with engine.connect() as conn:
            try:
                df = pd.read_sql_table(name, conn)
                df.columns = [re.sub(r'[^a-z0-9_]', '', col.lower().replace(' ','_')) for col in df.columns]
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
        max_gestion = pd.to_numeric(df['orden_gestion'], errors='coerce').max()
        if pd.isna(max_gestion):
            return 1
        return int(max_gestion) + 1
    return 1


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

# ===============================
# 📋 Menú lateral (opciones)
# ===================================================
with st.sidebar:
    selected = option_menu(
        "Menú",
        ["Ver Datos", "KPIs", "Ingresar Pedido", "Predicción de Rutas", "Seguimiento de Rutas", "Clientes", "Borrar Datos"],
        icons=["table","bar-chart","plus-square","map","geo-alt","people-fill","trash"],
        menu_icon="cast",
        default_index=0,
    )

# ===============================
# --- Ver Datos: subir y gestionar tablas ---
# ===================================================
if selected == "Ver Datos":
    st.header("📋 Gestionar datos")
    st.markdown("Sube aquí tus archivos de clientes y ubicaciones (soporta 15,000+ registros).")

    col1, col2 = st.columns(2)
    with col1:
        clientes_file = st.file_uploader("Sube archivo de CLIENTES (CSV)", type=['csv'], key='clientes_file')
        if clientes_file:
            df_clientes = read_uploaded_csv_with_encoding(clientes_file, delimiter=',')
            if df_clientes is not None:
                df_clientes = normalize_columns(df_clientes)
                # aseguramos columnas clave
                if 'lat' not in df_clientes.columns or 'lon' not in df_clientes.columns or 'nombre' not in df_clientes.columns:
                    st.error("El archivo de clientes debe incluir al menos: nombre, lat, lon. Normaliza los encabezados.")
                else:
                    st.info(f"Clientes cargados: {len(df_clientes)} filas")
                    st.session_state['df_clientes'] = df_clientes
                    if st.button("Guardar clientes en BD"):
                        with engine.connect() as conn:
                            df_clientes.to_sql('clientes', conn, if_exists='replace', index=False)
                            conn.commit()
                        st.success("Clientes guardados en la base de datos (tabla 'clientes').")
                        st.cache_data.clear()
    with col2:
        ubic_file = st.file_uploader("Sube archivo de UBICACIONES (CSV) - para mapa", type=['csv'], key='ubic_file')
        if ubic_file:
            df_ubic = read_uploaded_csv_with_encoding(ubic_file, delimiter=',')
            if df_ubic is not None:
                df_ubic = normalize_columns(df_ubic)
                if 'ubicacion' not in df_ubic.columns and 'nombre' not in df_ubic.columns:
                    st.warning("Se aconseja que la columna de ubicaciones se llame 'ubicacion' o 'nombre'.")
                if 'lat' not in df_ubic.columns or 'lon' not in df_ubic.columns:
                    st.error("El archivo de ubicaciones debe contener columnas 'lat' y 'lon'.")
                else:
                    st.info(f"Ubicaciones cargadas: {len(df_ubic)} filas")
                    st.session_state['df_ubic'] = df_ubic
                    if st.button("Guardar ubicaciones en BD"):
                        with engine.connect() as conn:
                            df_ubic.to_sql('ubicaciones', conn, if_exists='replace', index=False)
                            conn.commit()
                        st.success("Ubicaciones guardadas en la base de datos (tabla 'ubicaciones').")
                        st.cache_data.clear()

    st.markdown("---")
    st.subheader("📥 Cargar archivo de pedidos (opcional)")
    pedidos_file = st.file_uploader("Archivo de pedidos (CSV) para importar pedidos existentes", type=['csv'], key='pedidos_file')
    if pedidos_file:
        df_pedidos = read_uploaded_csv_with_encoding(pedidos_file, delimiter=',')
        if df_pedidos is not None:
            df_pedidos = normalize_columns(df_pedidos)
            st.session_state['df_pedidos'] = df_pedidos
            st.success(f"Pedidos listos: {len(df_pedidos)} filas. Pulsa Guardar para insertarlos en 'entregas'.")
            if st.button("Guardar pedidos en entregas (BD)"):
                with engine.connect() as conn:
                    df_pedidos.to_sql('entregas', conn, if_exists='append', index=False)
                    conn.commit()
                st.success("Pedidos importados a la tabla 'entregas'.")
                st.cache_data.clear()

# ===============================
# --- KPIs (visualización avanzada) ---
# ===================================================
elif selected == "KPIs":
    st.header("📊 KPIs y análisis")
    df_ent = load_table('entregas')
    df_clients = load_table('clientes')

    if df_clients.empty and df_ent.empty:
        st.info("No hay datos en la base de datos. Sube archivos en 'Ver Datos'.")
    else:
        # preferir df_clients para ubicación de clientes
        df = df_clients if not df_clients.empty else df_ent
        df = normalize_columns(df)

        st.subheader("KPIs Generales")
        total_clientes = len(df)
        rutas = df['ruta'].nunique() if 'ruta' in df.columns else 0
        atendidos = df[df.get('estado','').str.lower() == 'entregado'].shape[0] if 'estado' in df.columns else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total clientes", total_clientes)
        col2.metric("Rutas activas", rutas)
        col3.metric("Clientes entregados", atendidos)
        col4.metric("% Entregados", f"{round((atendidos/total_clientes)*100,2) if total_clientes>0 else 0}%")

        st.markdown("---")
        if 'tiempo_entrega' in df.columns:
            st.subheader("Distribución Tiempo de Entrega")
            fig = px.histogram(df, x='tiempo_entrega', nbins=30, title='Tiempo de Entrega (min)')
            st.plotly_chart(fig, use_container_width=True)

        if 'departamento' in df.columns:
            st.subheader("Reparto por Departamento")
            dept = df.groupby('departamento').size().reset_index(name='count')
            fig2 = px.bar(dept, x='departamento', y='count')
            st.plotly_chart(fig2, use_container_width=True)

# ===============================
# --- Ingresar Pedido (nueva orden o desde cliente) ---
# ===================================================
elif selected == "Ingresar Pedido":
    st.header("📝 Ingresar / Asignar Pedido")
    df_clients = load_table('clientes')
    df_ent = load_table('entregas')

    if df_clients.empty:
        st.warning("No hay clientes en BD. Sube el archivo de clientes en 'Ver Datos' o añade manualmente.")

    with st.form("nuevo_pedido_form"):
        st.subheader("Crear nueva orden")
        if not df_clients.empty:
            cliente_sel = st.selectbox('Seleccionar cliente (opcional):', options=['Nuevo'] + df_clients['nombre'].tolist())
        else:
            cliente_sel = 'Nuevo'

        orden_gestion = st.text_input('Orden gestión (dejar vacío para autogenerar)')
        nombre_cliente = st.text_input('Nombre del cliente', value='' if cliente_sel=='Nuevo' else cliente_sel)
        departamento = st.text_input('Departamento')
        municipio = st.text_input('Municipio')
        ubicacion = st.text_input('Ubicación / Dirección')
        lat = st.text_input('Lat', value='')
        lon = st.text_input('Lon', value='')
        tipo_pedido = st.selectbox('Tipo de pedido', options=['Paquete','Documento','Comida','Otro'])
        clima = st.selectbox('Clima', options=['Normal','Lluvioso'])
        trafico = st.selectbox('Tráfico', options=['Bajo','Medio','Alto'])
        repartidor = st.selectbox('Asignar repartidor', options=REPARTIDORES)
        submit_order = st.form_submit_button('Guardar orden')

    if submit_order:
        try:
            df_ent = load_table('entregas')
            next_g = get_next_gestion_number(df_ent)
            orden = orden_gestion if orden_gestion else f"{next_g:04d}"
            nueva = pd.DataFrame([{
                'orden_gestion': orden,
                'fecha': datetime.now(),
                'zona': departamento,
                'tipo_pedido': tipo_pedido,
                'clima': clima,
                'trafico': trafico,
                'tiempo_entrega': None,
                'retraso': None,
                'ubicacion': ubicacion,
                'municipio': municipio,
                'departamento': departamento,
                'estado': 'Pendiente',
                'inicio_ruta': None,
                'destino': None,
                'tiempo_predicho': None,
                'repartidor': repartidor,
                'lat': float(lat) if lat else None,
                'lon': float(lon) if lon else None,
                'nombre': nombre_cliente
            }])
            with engine.connect() as conn:
                nueva.to_sql('entregas', conn, if_exists='append', index=False)
                conn.commit()
            st.success(f"Orden {orden} guardada en la base de datos.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Error al guardar la orden: {e}")

# ===============================
# --- Predicción de Rutas (mapas / heatmap / seleccionar origen) ---
# ===================================================
elif selected == "Predicción de Rutas":
    st.header("🚚 Predicción y Mapa de Rutas")

    ubicaciones = load_table('ubicaciones')
    df_ent = load_table('entregas')

    if ubicaciones.empty:
        st.info("Sube el archivo de ubicaciones en 'Ver Datos' para ver mapas y predicciones.")
    else:
        ubic = normalize_columns(ubicaciones.copy())
        ubic['lat'] = pd.to_numeric(ubic['lat'], errors='coerce')
        ubic['lon'] = pd.to_numeric(ubic['lon'], errors='coerce')
        ubic.dropna(subset=['lat','lon'], inplace=True)

        st.subheader('Zonas de Alta Demanda (HeatMap)')
        if not df_ent.empty:
            df_count = df_ent.groupby('ubicacion').size().reset_index(name='freq')
            heat = pd.merge(df_count, ubic[['ubicacion','lat','lon']], on='ubicacion', how='inner')
            heat_list = heat[['lat','lon','freq']].values.tolist()
        else:
            heat_list = []

        m = folium.Map(location=[ubic['lat'].mean(), ubic['lon'].mean()], zoom_start=9)
        if heat_list:
            HeatMap(heat_list, radius=12, min_opacity=0.3).add_to(m)
        st_folium(m, width=900, height=500)

        st.markdown('---')
        st.subheader('Predicción simple entre origen y destino (simulada)')
        todas = sorted(ubic['ubicacion'].unique()) if 'ubicacion' in ubic.columns else []
        origen = st.selectbox('Origen', options=[''] + todas)
        destino = st.selectbox('Destino', options=[''] + todas)

        if origen and destino and origen!=destino:
            coords = {row['ubicacion']:[row['lat'], row['lon']] for _,row in ubic.iterrows()}
            o = coords.get(origen)
            d = coords.get(destino)
            mapa = folium.Map(location=[(o[0]+d[0])/2,(o[1]+d[1])/2], zoom_start=12)
            folium.Marker(o, popup='Origen').add_to(mapa)
            folium.Marker(d, popup='Destino').add_to(mapa)
            folium.PolyLine([o,d], color='blue', weight=4).add_to(mapa)
            st_folium(mapa, width=900, height=500)

            # simulación de tiempo
            base = 20 + haversine(o[0],o[1],d[0],d[1])
            est = int(base + random.randint(-5,10))
            st.success(f"Tiempo estimado (simulado): {est} minutos")

# ===============================
# --- Seguimiento de Rutas (activa) ---
# ===================================================
elif selected == "Seguimiento de Rutas":
    st.header("🚚 Seguimiento de Rutas Activas")
    df_ent = load_table('entregas')
    ubic = load_table('ubicaciones')

    if df_ent.empty:
        st.info("No hay entregas registradas. Carga datos en 'Ver Datos' o crea pedidos en 'Ingresar Pedido'.")
    else:
        ordenes_activas = df_ent[df_ent['estado'].isin(['Activa','En Curso','activa','en curso'])]
        if ordenes_activas.empty:
            st.info('No hay rutas activas en este momento.')
        else:
            repartidores = ordenes_activas['repartidor'].dropna().unique().tolist()
            sel_rep = st.selectbox('Filtrar por repartidor', options=['Todos']+list(repartidores))
            if sel_rep!='Todos':
                ordenes_activas = ordenes_activas[ordenes_activas['repartidor']==sel_rep]

            st.subheader(f'Total rutas activas: {len(ordenes_activas)}')

            # Preprocesar ubicaciones
            ubic_map = {}
            if not ubic.empty:
                ubic = normalize_columns(ubic)
                ubic['lat'] = pd.to_numeric(ubic['lat'], errors='coerce')
                ubic['lon'] = pd.to_numeric(ubic['lon'], errors='coerce')
                for _,r in ubic.iterrows():
                    key = r.get('ubicacion') or r.get('nombre')
                    if key:
                        ubic_map[key]=[r['lat'],r['lon']]

            default = [13.7,-89.2]

            for _,row in ordenes_activas.iterrows():
                with st.expander(f"Orden {row.get('orden_gestion','-')} — {row.get('nombre',row.get('ubicacion',''))}"):
                    col1,col2 = st.columns([1,2])
                    with col1:
                        st.markdown(f"**Repartidor:** {row.get('repartidor','N/A')}")
                        st.markdown(f"**Estado:** {row.get('estado')}")
                        st.markdown(f"**Inicio:** {row.get('inicio_ruta')}")
                        # progreso básico
                        tp = row.get('tiempo_predicho') or 0
                        st.progress(0 if not tp else min(1, 0.5))
                        if st.button('Marcar como Entregado', key=f'ent_{row.get("orden_gestion")}'):
                            with engine.connect() as conn:
                                conn.execute(text(f"UPDATE entregas SET estado='Entregado' WHERE orden_gestion='{row.get('orden_gestion')}'"))
                                conn.commit()
                            st.success('Marcada como Entregada')
                            st.cache_data.clear()
                    with col2:
                        origin = ubic_map.get(row.get('ubicacion'), default)
                        dest = ubic_map.get(row.get('destino'), default)
                        mapa_min = folium.Map(location=[(origin[0]+dest[0])/2,(origin[1]+dest[1])/2], zoom_start=12)
                        folium.Marker(origin, popup='Origen').add_to(mapa_min)
                        folium.Marker(dest, popup='Destino').add_to(mapa_min)
                        folium.PolyLine([origin,dest], color='blue', weight=4).add_to(mapa_min)
                        st_folium(mapa_min, width=600, height=300)

# ===============================
# --- Sección Clientes (visualizar y filtrar) ---
# ===================================================
elif selected == "Clientes":
    st.header('👥 Clientes — Visualización y Gestión')
    df_clients = load_table('clientes')

    if df_clients.empty:
        st.info('No hay clientes en la base de datos. Suba el archivo en "Ver Datos".')
    else:
        dfc = normalize_columns(df_clients.copy())
        dfc['lat'] = pd.to_numeric(dfc['lat'], errors='coerce')
        dfc['lon'] = pd.to_numeric(dfc['lon'], errors='coerce')

        st.subheader('📋 Tabla de Clientes (soporta grandes volúmenes)')
        st.dataframe(dfc, use_container_width=True)

        st.subheader('🔎 Filtros')
        cols = st.multiselect('Mostrar columnas', options=list(dfc.columns), default=['nombre','ruta','lat','lon','municipio'])
        filtros = st.columns(3)
        ruta_f = filtros[0].multiselect('Ruta', options=dfc['ruta'].unique())
        depto_f = filtros[1].multiselect('Departamento', options=dfc['departamento'].unique() if 'departamento' in dfc.columns else [])
        estado_f = filtros[2].multiselect('Estado', options=dfc['estado'].unique() if 'estado' in dfc.columns else [])

        dfc_filtered = dfc.copy()
        if ruta_f: dfc_filtered = dfc_filtered[dfc_filtered['ruta'].isin(ruta_f)]
        if depto_f and 'departamento' in dfc_filtered.columns: dfc_filtered = dfc_filtered[dfc_filtered['departamento'].isin(depto_f)]
        if estado_f and 'estado' in dfc_filtered.columns: dfc_filtered = dfc_filtered[dfc_filtered['estado'].isin(estado_f)]

        st.dataframe(dfc_filtered[cols], use_container_width=True)

# ===============================
# --- Borrar Datos (peligroso) ---
# ===================================================
elif selected == "Borrar Datos":
    st.header('🗑️ Borrar datos (Peligroso)')
    st.warning('Esto eliminará todas las tablas gestionadas: clientes, ubicaciones, entregas')
    if st.button('Borrar TODO'):
        try:
            clear_table('clientes')
            clear_table('ubicaciones')
            clear_table('entregas')
            st.success('Tablas borradas correctamente.')
            st.cache_data.clear()
        except Exception as e:
            st.error(f'Error al borrar tablas: {e}')
