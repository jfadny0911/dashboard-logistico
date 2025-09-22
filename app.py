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
from datetime import datetime, timedelta
import time

# ===============================
# 🔗 Conexión a la base de datos PostgreSQL de Render
# ===================================================
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
            conn.execute(text("SELECT 1 FROM entregas LIMIT 1"))
            return True
        except Exception:
            return False

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

def get_next_gestion_number(df):
    """Obtiene el siguiente número de gestión secuencial."""
    if 'orden_gestion' in df.columns and not df.empty:
        max_gestion = df['orden_gestion'].astype(int).max()
        return max_gestion + 1
    return 1

# ===============================
# 📋 Menú lateral
# ===============================
menu = st.sidebar.radio("Menú", ["Ver Datos", "KPIs", "Ingresar Pedido", "Predicción de Rutas", "Seguimiento de Rutas", "Borrar Datos"])

# --- 📦 Sección para agregar y ver datos ---
if menu == "Ver Datos":
    st.header("📋 Datos almacenados")
    
    uploaded_db_file = st.file_uploader("Sube tu base de datos de entregas (CSV)", type=["csv"], key="db_file_uploader")
    if uploaded_db_file is not None:
        st.warning("⚠️ Al subir un archivo, se **reemplazará** la tabla `entregas` completa en la base de datos.")
        if st.button("➕ Guardar base de datos"):
            try:
                df_to_load = read_uploaded_csv_with_encoding(uploaded_db_file, delimiter=';')
                if df_to_load is not None:
                    df_to_load.columns = [
                        re.sub(r'[^a-z0-9_]', '', col.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n').replace(' ', '_').strip())
                        for col in df_to_load.columns
                    ]
                    
                    # 🌟 Verificar y agregar columnas si no existen
                    if 'orden_gestion' not in df_to_load.columns:
                        df_to_load['orden_gestion'] = [f"{i:04d}" for i in range(1, len(df_to_load) + 1)]
                        st.info("Columna 'orden_gestion' agregada automáticamente.")
                    
                    if 'estado' not in df_to_load.columns:
                        df_to_load['estado'] = 'Pendiente'
                        st.info("Columna 'estado' agregada automáticamente.")

                    if 'inicio_ruta' not in df_to_load.columns:
                        df_to_load['inicio_ruta'] = None
                        st.info("Columna 'inicio_ruta' agregada automáticamente.")
                    
                    with engine.connect() as conn:
                        conn.execute(text("TRUNCATE TABLE entregas"))
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
            
        st.subheader("Datos de entrega real")
        tiempo_entrega_real = st.text_input("Tiempo de entrega real (minutos)")
        retraso_real = st.text_input("Retraso real (minutos)")

        if st.button("➕ Guardar Pedido"):
            if not orden_gestion_display or not selected_ubicacion:
                st.error("Por favor, completa los campos de Número de Gestión y Ubicación.")
            else:
                try:
                    nueva_fila = pd.DataFrame([{
                        'orden_gestion': orden_gestion_display,
                        'fecha': datetime.now(),
                        'zona': selected_departamento,
                        'tipo_pedido': selected_tipo_pedido,
                        'clima': selected_clima,
                        'trafico': selected_trafico,
                        'tiempo_entrega': int(tiempo_entrega_real) if tiempo_entrega_real else None,
                        'retraso': int(retraso_real) if retraso_real else None,
                        'ubicacion': selected_ubicacion,
                        'municipio': selected_municipio,
                        'departamento': selected_departamento,
                        'estado': 'Pendiente'
                    }])
                    
                    with engine.connect() as conn:
                        nueva_fila.to_sql('entregas', conn, if_exists='append', index=False)
                        conn.commit()
                    st.success("✅ Pedido guardado con éxito en la base de datos.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar el pedido: {e}")

# --- 🚚 Predicción de Rutas simuladas ---
elif menu == "Predicción de Rutas":
    st.header("🚚 Predicción de Rutas en El Salvador (Simulación)")
    
    uploaded_file = st.file_uploader("Sube el archivo de ubicaciones con coordenadas (CSV)", type=["csv"], key="ubicaciones_file_uploader")
    
    if uploaded_file is not None:
        try:
            ubicaciones_df = read_uploaded_csv_with_encoding(uploaded_file, delimiter=';')
            st.session_state['ubicaciones_df'] = ubicaciones_df
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {e}")

    if 'ubicaciones_df' in st.session_state and st.session_state['ubicaciones_df'] is not None:
        ubicaciones_df = st.session_state['ubicaciones_df']
        
        ubicaciones_df.columns = [
            re.sub(r'[^a-z0-9_]', '', col.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n'))
            for col in ubicaciones_df.columns
        ]
        
        if 'ubicacion' not in ubicaciones_df.columns or 'latitud' not in ubicaciones_df.columns or 'longitud' not in ubicaciones_df.columns:
            st.error("❌ Error: El archivo debe contener las columnas 'Ubicación', 'Latitud' y 'Longitud' (o sus equivalentes).")
        else:
            ubicaciones_df['latitud'] = ubicaciones_df['latitud'].astype(str).str.replace('° N', '').str.replace('° O', '').str.strip().astype(float)
            ubicaciones_df['longitud'] = ubicaciones_df['longitud'].astype(str).str.replace('° N', '').str.replace('° O', '').str.strip().astype(float)
            
            todas_ubicaciones = sorted(ubicaciones_df['ubicacion'].unique())
            
            df_entregas = load_data_from_db()

            if not df_entregas.empty:
                ordenes_pendientes = df_entregas[df_entregas['estado'] == 'Pendiente']['orden_gestion'].unique()
                selected_orden = st.selectbox("Selecciona una orden de gestión pendiente:", [''] + sorted(ordenes_pendientes))

                if selected_orden:
                    orden_data = df_entregas[df_entregas['orden_gestion'] == selected_orden].iloc[0]
                    origen_prediccion = orden_data['ubicacion']
                    
                    st.subheader(f"Ruta para la orden '{selected_orden}':")
                    st.info(f"Origen: {origen_prediccion}")
                    
                    todas_ubicaciones_sin_origen = [ubic for ubic in todas_ubicaciones if ubic != origen_prediccion]
                    destino_prediccion = st.selectbox("Selecciona el destino:", todas_ubicaciones_sin_origen, key="destino_prediccion")
                    
                    if origen_prediccion and destino_prediccion and origen_prediccion != destino_prediccion:
                        coordenadas = {
                            row['ubicacion']: [row['latitud'], row['longitud']]
                            for index, row in ubicaciones_df.iterrows()
                        }
                        
                        default_coords = [13.7, -89.2]
                        origen_coords = coordenadas.get(origen_prediccion, default_coords)
                        destino_coords = coordenadas.get(destino_prediccion, default_coords)
                        
                        mapa = folium.Map(location=[13.7, -89.2], zoom_start=8)
                        folium.Marker(origen_coords, popup=f"Origen: {origen_prediccion}", icon=folium.Icon(color="green")).add_to(mapa)
                        folium.Marker(destino_coords, popup=f"Destino: {destino_prediccion}", icon=folium.Icon(color="red")).add_to(mapa)
                        folium.PolyLine([origen_coords, destino_coords], color="blue", weight=4, opacity=0.8).add_to(mapa)
                        st_folium(mapa, width=700, height=500)
                        
                        base_time = 30
                        if orden_data['trafico'] == 'Medio': base_time += 15
                        elif orden_data['trafico'] == 'Alto': base_time += 30
                        if orden_data['clima'] == 'Lluvioso': base_time += 10
                        tiempo_estimado = random.randint(base_time - 5, base_time + 5)
                        
                        st.success(f"⏱️ Tiempo estimado: {tiempo_estimado} minutos")
                        st.info(f"Condiciones: Tráfico {orden_data['trafico']} | Clima {orden_data['clima']}")
                        
                        if st.button("Iniciar Ruta"):
                            try:
                                with engine.connect() as conn:
                                    conn.execute(text(f"UPDATE entregas SET estado = 'Activa', inicio_ruta = '{datetime.now()}' WHERE orden_gestion = '{selected_orden}'"))
                                    conn.commit()
                                st.success(f"✅ Gestión '{selected_orden}' iniciada y marcada como Activa.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error al iniciar la ruta: {e}")

    else:
        st.info("Por favor, sube el archivo de ubicaciones con coordenadas para ver las predicciones de ruta.")

# --- Sección para seguimiento de rutas ---
elif menu == "Seguimiento de Rutas":
    st.header("🚚 Seguimiento de Rutas")
    
    df_entregas = load_data_from_db()
    if not df_entregas.empty:
        ordenes_activas = df_entregas[df_entregas['estado'] == 'Activa']
        
        if not ordenes_activas.empty:
            for index, row in ordenes_activas.iterrows():
                tiempo_transcurrido = datetime.now() - datetime.strptime(str(row['inicio_ruta']), "%Y-%m-%d %H:%M:%S.%f")
                tiempo_restante = timedelta(minutes=row['tiempo_predicho']) - tiempo_transcurrido
                
                if tiempo_restante.total_seconds() < 0:
                    tiempo_restante_str = "00:00:00"
                    progreso = 1.0
                else:
                    total_segundos = int(tiempo_restante.total_seconds())
                    horas = total_segundos // 3600
                    minutos = (total_segundos % 3600) // 60
                    segundos = total_segundos % 60
                    tiempo_restante_str = f"{horas:02d}:{minutos:02d}:{segundos:02d}"
                    progreso = 1 - (tiempo_restante.total_seconds() / timedelta(minutes=row['tiempo_predicho']).total_seconds())
                
                ubicaciones_df = st.session_state.get('ubicaciones_df')
                if ubicaciones_df is not None and not ubicaciones_df.empty:
                    coordenadas = {
                        loc['ubicacion']: [loc['latitud'], loc['longitud']]
                        for index, loc in ubicaciones_df.iterrows()
                    }
                    origen_coords = coordenadas.get(row['ubicacion'], [13.7, -89.2])
                    destino_coords = coordenadas.get(row['destino'], [13.7, -89.2])
                    google_maps_link = f"https://www.google.com/maps/dir/?api=1&origin={origen_coords[0]},{origen_coords[1]}&destination={destino_coords[0]},{destino_coords[1]}"
                    waze_link = f"https://waze.com/ul?ll={destino_coords[0]},{destino_coords[1]}&navigate=yes"
                else:
                    google_maps_link = "#"
                    waze_link = "#"
                    origen_coords = [13.7, -89.2]
                    destino_coords = [13.7, -89.2]

                st.markdown(f"**Gestión {row['orden_gestion']} - Estado: Activa**")
                st.info(f"Ruta: **{row['ubicacion']}** -> **{row['destino']}**")
                st.markdown(f"**Tipo de Pedido:** {row['tipo_pedido']} | **Clima:** {row['clima']} | **Tráfico:** {row['trafico']}")
                
                col_progreso, col_tiempo = st.columns([3, 1])
                with col_progreso:
                    st.progress(progreso, text="Progreso de la ruta")
                with col_tiempo:
                    st.metric("Tiempo Restante", tiempo_restante_str)

                col_mapas, col_acciones = st.columns([2, 1])
                with col_mapas:
                    st.markdown(f"**Enlaces rápidos:**")
                    st.markdown(f"[Abrir en Google Maps]({google_maps_link})", unsafe_allow_html=True)
                    st.markdown(f"[Abrir en Waze]({waze_link})", unsafe_allow_html=True)
                with col_acciones:
                    if st.button("Marcar como Entregado", key=f"entregar_{row['orden_gestion']}"):
                        with engine.connect() as conn:
                            conn.execute(text(f"UPDATE entregas SET estado = 'Entregado' WHERE orden_gestion = '{row['orden_gestion']}'"))
                            conn.commit()
                        st.success(f"✅ Gestión '{row['orden_gestion']}' marcada como Entregada.")
                        st.cache_data.clear()
                        st.rerun()

                st.markdown("---")
        else:
            st.info("No hay gestiones activas en este momento.")

# --- 🗑️ Sección para borrar datos ---
elif menu == "Borrar Datos":
    st.header("🗑️ Eliminar registros")
    st.warning("⚠️ Esto borrará todos los datos de la tabla `entregas` en la base de datos de Render.")
    
    if st.button("Borrar TODO", key="delete_button"):
        clear_database()
