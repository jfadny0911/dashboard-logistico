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
# Usar la variable DATABASE_URL directamente.
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
    Carga todos los datos de la tabla 'entregas' en un DataFrame, usando una consulta SQL directa para robustez.
    """
    if check_table_exists():
        with engine.connect() as conn:
            try:
                # Usar query directo para robustez contra errores de metadata
                df = pd.read_sql_query(text("SELECT * FROM entregas"), conn)
                
                # Aplicación de normalización de columnas al leer de la BD
                df.columns = [
                    re.sub(r'[^a-z0-9_]', '', col.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n').replace(' ', '_').strip())
                    for col in df.columns
                ]
                
                return df
            except Exception as e:
                # Imprimir el error detallado al log de Streamlit (ayuda a la depuración)
                print(f"ERROR: Falló la carga de datos de la tabla 'entregas'. Detalle: {e}")
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

# ====================================================================
# 🤖 LÓGICA DEL AGENTE DE ANÁLISIS IA (SIMULADA)
# ====================================================================

def run_ai_analysis(df_input, query):
    """
    Simula la respuesta de un agente IA basado en análisis de lenguaje natural sobre el DataFrame.
    """
    query_lower = query.lower()
    df = df_input.copy()

    # Intenta responder preguntas predefinidas y luego usa análisis de datos

    # 1. Preguntas sobre Repartidores
    for rep in REPARTIDORES:
        if rep.lower() in query_lower:
            df_rep = df[df['repartidor'].str.contains(rep, case=False, na=False)]
            if not df_rep.empty and 'retraso' in df_rep.columns:
                avg_delay = df_rep['retraso'].mean()
                total_deliveries = len(df_rep)
                
                if "retraso promedio" in query_lower or "demora" in query_lower:
                    return f"El repartidor **{rep}** tiene un retraso promedio de **{avg_delay:.1f} minutos** en {total_deliveries} entregas registradas."
                
                if "entregas" in query_lower or "pedidos" in query_lower:
                    return f"**{rep}** ha completado {total_deliveries} entregas. Su mejor tiempo de entrega fue de {df_rep['tiempo_entrega'].min():.0f} minutos."
    
    # 2. Preguntas sobre Condiciones
    if "clima" in query_lower and "afecta" in query_lower:
        if 'clima' in df.columns and 'tiempo_entrega' in df.columns:
            avg_by_clima = df.groupby('clima')['tiempo_entrega'].mean().sort_values(ascending=False)
            peor_clima = avg_by_clima.index[0]
            tiempo_peor = avg_by_clima.iloc[0]
            return f"Sí, el clima afecta. El promedio de entrega es más alto ({tiempo_peor:.1f} minutos) durante condiciones **{peor_clima}**, lo que sugiere la mayor dificultad."

    # 3. Preguntas sobre Ubicaciones
    if "ubicacion mas lenta" in query_lower or "peor zona" in query_lower:
        if 'ubicacion' in df.columns and 'tiempo_entrega' in df.columns:
            avg_by_ubicacion = df.groupby('ubicacion')['tiempo_entrega'].mean().sort_values(ascending=False)
            peor_ubicacion = avg_by_ubicacion.index[0]
            tiempo_peor = avg_by_ubicacion.iloc[0]
            return f"La ubicación con el tiempo de entrega promedio más alto es **{peor_ubicacion}** con **{tiempo_peor:.1f} minutos**."
    
    # Respuesta por defecto
    return "Mi análisis indica que la información solicitada no está en una métrica predefinida. Por favor, reformula tu pregunta o revisa los gráficos detallados en la sección KPI."

# ====================================================================
# 📋 Menú lateral
# ====================================================================
menu = st.sidebar.radio("Menú", ["Ver Datos", "KPIs", "Ingresar Pedido", "Predicción de Rutas", "Seguimiento de Rutas", "Agente de Análisis IA", "Borrar Datos"])

# --- 📦 Sección para agregar y ver datos ---
if menu == "Ver Datos":
    st.header("📋 Datos almacenados")
    
    # GUÍA DE COLUMNAS AÑADIDA AQUÍ
    st.subheader("💡 Guía de Estructura de Archivo CSV/Excel")
    st.markdown("""
    Para una carga correcta, tu archivo CSV debe tener los siguientes **nombres y formatos de columna** (el orden es flexible). **¡No deben estar fusionados!**
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
                # 1. Intentar leer usando coma (,) como delimitador
                df_to_load = read_uploaded_csv_with_encoding(uploaded_db_file, delimiter=',')
                if df_to_load is not None:
                    
                    # Normalizar nombres de columnas
                    df_to_load.columns = [
                        re.sub(r'[^a-z0-9_]', '', col.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n').replace(' ', '_').strip())
                        for col in df_to_load.columns
                    ]
                    
                    # Verificar la existencia de la columna departamento antes de continuar
                    if 'departamento' not in df_to_load.columns:
                        st.error("Error crítico: La columna 'departamento' no fue encontrada después de la normalización. Revisa tu archivo CSV.")
                        return

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
        if 'departamento' not in df.columns or 'municipio' not in df.columns or 'tipo_pedido' not in df.columns or 'fecha' not in df.columns:
            st.error("Error de datos: Faltan columnas clave ('departamento', 'municipio', 'tipo_pedido', 'fecha'). Por favor, asegúrate de que el CSV subido sea correcto.")
            st.stop()

        # --- AUTOMATIZACIÓN 1: Conversión y Filtrado por Tiempo ---
        
        # 1. Conversión de columna 'fecha' a datetime
        try:
            df['fecha_dt'] = pd.to_datetime(df['fecha'], format='%Y-%m-%d', errors='coerce')
            df.dropna(subset=['fecha_dt'], inplace=True)
            max_date = df['fecha_dt'].max()
        except Exception:
            st.error("Error al convertir la columna 'fecha' a formato de fecha.")
            st.stop()

        # 2. Selector de Rango de Tiempo Automático
        time_range = st.selectbox(
            'Automatización por Rango de Tiempo:',
            ['Total Histórico', 'Últimos 7 días', 'Últimos 30 días']
        )
        
        # 3. Aplicar Filtro de Tiempo
        if time_range == 'Últimos 7 días':
            start_date = max_date - timedelta(days=7)
            df_time_filtered = df[df['fecha_dt'] >= start_date]
        elif time_range == 'Últimos 30 días':
            start_date = max_date - timedelta(days=30)
            df_time_filtered = df[df['fecha_dt'] >= start_date]
        else:
            df_time_filtered = df
            
        # 4. Cálculo de KPIs y métricas usando el DataFrame filtrado por tiempo
        
        total_registros = len(df_time_filtered)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total registros", total_registros)
        
        numeric_cols = df_time_filtered.select_dtypes(include="number").columns
        if not numeric_cols.empty:
            avg_global = round(df_time_filtered[numeric_cols].mean().mean(), 2)
            max_global = round(df_time_filtered[numeric_cols].max().max(), 2)
            col2.metric("🔹 Promedio global", avg_global)
            col3.metric("📈 Máximo global", max_global)

        st.subheader("Filtros para análisis detallado")
        
        # Usamos el DataFrame completo (df) para los selectbox para asegurar que todas las opciones estén disponibles
        df_for_selectbox = df 

        # Filtro de Repartidor
        col_select_repartidor = st.selectbox(
            'Selecciona el Repartidor:',
            options=['Todos'] + (sorted(df_for_selectbox['repartidor'].unique()) if 'repartidor' in df_for_selectbox.columns else [])
        )

        col_select_departamento, col_select_municipio, col_select_tipo_pedido = st.columns(3)
        
        with col_select_departamento:
            selected_departamento = st.selectbox(
                'Selecciona el Departamento:',
                options=df_for_selectbox['departamento'].unique()
            )

        with col_select_municipio:
            municipios_disponibles = df_for_selectbox[df_for_selectbox['departamento'] == selected_departamento]['municipio'].unique()
            selected_municipio = st.selectbox(
                'Selecciona el Municipio:',
                options=municipios_disponibles
            )

        with col_select_tipo_pedido:
            tipo_pedido_disponibles = df_for_selectbox['tipo_pedido'].unique()
            selected_tipo_pedido = st.selectbox(
                'Selecciona el Tipo de Pedido:',
                options=tipo_pedido_disponibles
            )

        # Filtrado final: Aplica filtros geográficos/tipo al DataFrame ya filtrado por tiempo
        filtered_df = df_time_filtered[
            (df_time_filtered['departamento'] == selected_departamento) &
            (df_time_filtered['municipio'] == selected_municipio) &
            (df_time_filtered['tipo_pedido'] == selected_tipo_pedido)
        ]

        if 'repartidor' in df_for_selectbox.columns and col_select_repartidor != 'Todos':
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
            
        st.subheader("Datos de entrega real")
        tiempo_entrega_real = st.text_input("Tiempo de entrega real (minutos)")
        retraso_real = st.text_input("Retraso real (minutos)")

        if st.button("➕ Guardar Pedido"):
            if not orden_gestion_display or not selected_ubicacion:
                st.error("Por favor, completa los campos de Número de Gestión y Ubicación.")
            else:
                try:
                    tiempo_predicho_val = st.session_state.get('prediccion')
                    
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
                        'estado': 'Pendiente',
                        'inicio_ruta': None,
                        'destino': None,
                        'tiempo_predicho': tiempo_predicho_val, 
                        'repartidor': selected_repartidor 
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
    
    st.markdown("""
    **🚨 ¡Atención! Para que los mapas y la predicción funcionen, debes subir aquí un archivo CSV con las coordenadas de tus ubicaciones únicas.**
    Este archivo debe contener las columnas: **`Ubicación`**, **`Latitud`** y **`Longitud`**.
    """)
    uploaded_file = st.file_uploader("Sube el archivo de ubicaciones con coordenadas (CSV)", type=["csv"], key="ubicaciones_file_uploader")
    
    if uploaded_file is not None:
        try:
            # Usar coma como delimitador para archivos de coordenadas
            ubicaciones_df = read_uploaded_csv_with_encoding(uploaded_file, delimiter=',')
            st.session_state['ubicaciones_df'] = ubicaciones_df
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {e}")

    if 'ubicaciones_df' in st.session_state and st.session_state['ubicaciones_df'] is not None:
        ubicaciones_df = st.session_state['ubicaciones_df'].copy()
        
        # Normalización de nombres de columna
        ubicaciones_df.columns = [
            re.sub(r'[^a-z0-9_]', '', col.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n').replace(' ', '_').strip())
            for col in ubicaciones_df.columns
        ]
        
        col_map = {'ubicacion': 'ubicacion', 'latitud': 'latitud', 'longitud': 'longitud'}
        
        if not all(col in ubicaciones_df.columns for col in col_map.values()):
            st.error("❌ Error: El archivo debe contener las columnas 'Ubicación', 'Latitud' y 'Longitud' (o sus equivalentes).")
        else:
            # Conversión de coordenadas a numérico después de la limpieza de nombres:
            ubicaciones_df['latitud'] = pd.to_numeric(ubicaciones_df['latitud'], errors='coerce')
            ubicaciones_df['longitud'] = pd.to_numeric(ubicaciones_df['longitud'], errors='coerce')

            ubicaciones_df.dropna(subset=['latitud', 'longitud'], inplace=True)

            todas_ubicaciones = sorted(ubicaciones_df['ubicacion'].unique())
            df_entregas = load_data_from_db()

            # =======================================================
            # 🗺️ Generar Mapa de Calor (HeatMap) de Zonas de Tráfico
            # =======================================================
            st.subheader("Zonas de Alta Demanda (HeatMap)")
            
            if not df_entregas.empty:
                df_pedidos_coords = df_entregas.groupby('ubicacion').size().reset_index(name='frecuencia')
                
                heatmap_data = pd.merge(
                    df_pedidos_coords, 
                    ubicaciones_df[['ubicacion', 'latitud', 'longitud']], 
                    on='ubicacion', 
                    how='inner'
                )
                
                heatmap_list = heatmap_data[['latitud', 'longitud', 'frecuencia']].values.tolist()
            else:
                heatmap_list = [] 

            mapa_heatmap = folium.Map(location=[13.7942, -88.8965], zoom_start=8)
            
            if heatmap_list:
                HeatMap(heatmap_list, 
                        radius=15, 
                        max_val=heatmap_data['frecuencia'].max() + 1, 
                        min_opacity=0.2).add_to(mapa_heatmap)
                st.info("El mapa de calor muestra las zonas con mayor frecuencia de pedidos.")

            st_folium(mapa_heatmap, width=700, height=500)
            
            # =======================================================
            # 👇 Lógica de Predicción de Rutas Específicas
            # =======================================================
            st.markdown("---")
            st.subheader("Predicción de Rutas Específicas")

            if not df_entregas.empty:
                # Verifica que 'ubicacion' y 'departamento' estén en df_entregas
                if 'ubicacion' not in df_entregas.columns or 'departamento' not in df_entregas.columns:
                     st.warning("Advertencia: Las columnas 'ubicacion' y/o 'departamento' no están en la BD. Por favor, recarga el archivo de entregas en 'Ver Datos'.")
                     st.stop()
                     
                ordenes_pendientes = df_entregas[df_entregas['estado'] == 'Pendiente']['orden_gestion'].unique()
                selected_orden = st.selectbox("Selecciona una orden de gestión pendiente:", [''] + sorted(ordenes_pendientes))

                if selected_orden:
                    orden_data = df_entregas[df_entregas['orden_gestion'] == selected_orden].iloc[0]
                    origen_prediccion = orden_data['ubicacion']
                    
                    st.subheader(f"Ruta para la orden '{selected_orden}':")
                    st.info(f"Origen: {origen_prediccion} | Repartidor asignado: **{orden_data.get('repartidor', 'N/A')}**")
                    
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
                        
                        # Mapa de la ruta específica 
                        mapa_ruta = folium.Map(location=[(origen_coords[0] + destino_coords[0]) / 2, (origen_coords[1] + destino_coords[1]) / 2], zoom_start=10)
                        folium.Marker(origen_coords, popup=f"Origen: {origen_prediccion}", icon=folium.Icon(color="green")).add_to(mapa_ruta)
                        folium.Marker(destino_coords, popup=f"Destino: {destino_prediccion}", icon=folium.Icon(color="red")).add_to(mapa_ruta)
                        folium.PolyLine([origen_coords, destino_coords], color="blue", weight=4, opacity=0.8).add_to(mapa_ruta)
                        st_folium(mapa_ruta, width=700, height=500)
                        
                        # Cálculo de tiempo estimado (simulación)
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
                                    conn.execute(text(f"""
                                        UPDATE entregas 
                                        SET estado = 'Activa', 
                                            inicio_ruta = '{datetime.now()}', 
                                            destino = '{destino_prediccion}', 
                                            tiempo_predicho = {tiempo_estimado}
                                        WHERE orden_gestion = '{selected_orden}'
                                    """))
                                    conn.commit()
                                st.success(f"✅ Gestión '{selected_orden}' iniciada y marcada como Activa.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error al iniciar la ruta: {e}")
                    else:
                        st.warning("El origen y destino no pueden ser iguales.")
            else:
                st.info("No hay datos en la base de datos para mostrar las predicciones de ruta.")
    else:
        st.info("Por favor, sube el archivo de ubicaciones con coordenadas para ver las predicciones de ruta.")

# --- Sección para seguimiento de rutas (REDISENADA) ---
elif menu == "Seguimiento de Rutas":
    st.header("🚚 Seguimiento de Rutas Activas")
    
    df_entregas = load_data_from_db()
    ubicaciones_df = st.session_state.get('ubicaciones_df')

    if df_entregas.empty or ubicaciones_df is None or ubicaciones_df.empty:
        st.warning("⚠️ Faltan datos: Por favor, asegúrate de haber cargado la Base de Datos en 'Ver Datos' y el archivo de Ubicaciones en 'Predicción de Rutas'.")
        st.stop()
    
    # Pre-procesar coordenadas una vez
    ubicaciones_df_cleaned = ubicaciones_df.copy()
    # Las columnas ya deben tener nombres normalizados ('latitud', 'longitud') gracias a Predicción de Rutas.
    ubicaciones_df_cleaned['latitud'] = pd.to_numeric(ubicaciones_df_cleaned['latitud'], errors='coerce')
    ubicaciones_df_cleaned['longitud'] = pd.to_numeric(ubicaciones_df_cleaned['longitud'], errors='coerce')

    coordenadas = {
        loc['ubicacion']: [loc['latitud'], loc['longitud']]
        for _, loc in ubicaciones_df_cleaned.iterrows()
    }
    default_coords = [13.75, -88.9]

    ordenes_activas = df_entregas[df_entregas['estado'] == 'Activa']
    
    if 'repartidor' not in ordenes_activas.columns:
        st.error("Error: La base de datos no tiene la columna 'repartidor'. Por favor, **borra y sube tus datos nuevamente** en la sección 'Ver Datos' para actualizar la estructura.")
        st.stop()
    
    # Filtro de Repartidor
    repartidores_activos = ordenes_activas['repartidor'].unique()
    selected_repartidor_seguimiento = st.selectbox(
        "Filtrar por Repartidor:",
        options=['Todos'] + sorted(repartidores_activos)
    )
    
    if selected_repartidor_seguimiento != 'Todos':
        ordenes_activas = ordenes_activas[ordenes_activas['repartidor'] == selected_repartidor_seguimiento]

    if ordenes_activas.empty:
        st.info("No hay gestiones activas que coincidan con los filtros.")
        st.stop()

    
    st.subheader(f"Total de rutas activas: {len(ordenes_activas)}")
    st.markdown("---")


    for index, row in ordenes_activas.iterrows():
        
        # --- LÓGICA ROBUSTA DE TIEMPO Y PROGRESO ---
        try:
            # Asegurar que inicio_ruta no sea None y tenga formato de fecha
            inicio_ruta_str = str(row['inicio_ruta'])
            if inicio_ruta_str == 'None':
                st.info(f"🔴 Orden {row['orden_gestion']} no iniciada: Falta hora de inicio. Estado: Activa.")
                continue

            try:
                inicio_ruta_dt = datetime.strptime(inicio_ruta_str, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                inicio_ruta_dt = datetime.strptime(inicio_ruta_str.split('.')[0], "%Y-%m-%d %H:%M:%S")

            tiempo_predicho_min = row['tiempo_predicho']
            if tiempo_predicho_min is None or tiempo_predicho_min <= 0:
                st.error(f"❌ Orden {row['orden_gestion']}: Tiempo predicho inválido (0 o Nulo).")
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
                horas = total_segundos // 3600
                minutos = (total_segundos % 3600) // 60
                segundos = total_segundos % 60
                tiempo_restante_str = f"{minutos:02d}m {segundos:02d}s"
                estado_progreso = "En Curso"
                color_progreso = "blue"

        except Exception as e:
            st.error(f"Error interno al calcular tiempo para orden {row['orden_gestion']}.")
            continue

        
        # --- VISUALIZACIÓN MODERNA (TARJETA) ---
        col_id, col_repartidor, col_estado, col_tiempo_restante = st.columns([1, 2, 2, 1.5])
        
        col_id.metric(f"ORDEN", f"#{row['orden_gestion']}")
        col_repartidor.metric("REPARTIDOR", row['repartidor'])
        col_estado.metric("ESTADO RUTA", estado_progreso)
        col_tiempo_restante.metric("RESTANTE", tiempo_restante_str)
        
        # Mapa en miniatura
        origen_coords = coordenadas.get(row['ubicacion'], default_coords)
        destino_coords = coordenadas.get(row['destino'], default_coords)
        
        with st.expander(f"Detalles de la Ruta - {row['ubicacion']} a {row['destino']}"):
            
            col_progreso, col_mapa = st.columns([1, 1])
            
            with col_progreso:
                st.markdown(f"**Progreso ({int(progreso * 100)}% completado)**")
                st.progress(progreso)
                
                st.markdown(f"**Inicio:** {inicio_ruta_dt.strftime('%H:%M:%S')}")
                st.markdown(f"**Estimado Total:** {int(row['tiempo_predicho'])} min")
                st.markdown(f"**Condiciones:** {row['clima']} | {row['trafico']}")
                
                st.markdown("---")
                if st.button("Marcar como Entregado", key=f"entregar_{row['orden_gestion']}"):
                    with engine.connect() as conn:
                        conn.execute(text(f"UPDATE entregas SET estado = 'Entregado' WHERE orden_gestion = '{row['orden_gestion']}'"))
                        conn.commit()
                    st.success(f"✅ Gestión '{row['orden_gestion']}' marcada como Entregada.")
                    st.cache_data.clear()
                    st.rerun()

            with col_mapa:
                # Generar mapa de ruta
                mapa_ruta_min = folium.Map(location=[(origen_coords[0] + destino_coords[0]) / 2, (origen_coords[1] + destino_coords[1]) / 2], zoom_start=12)
                folium.Marker(origen_coords, popup="Origen", icon=folium.Icon(color="green", icon="play")).add_to(mapa_ruta_min)
                folium.Marker(destino_coords, popup="Destino", icon=folium.Icon(color="red", icon="flag")).add_to(mapa_ruta_min)
                folium.PolyLine([origen_coords, destino_coords], color=color_progreso, weight=5).add_to(mapa_ruta_min)
                
                st_folium(mapa_ruta_min, width=350, height=300, key=f"map_{row['orden_gestion']}")
                
                st.markdown(f"[Abrir en Google Maps](http://maps.google.com/maps?saddr={origen_coords[0]},{origen_coords[1]}&daddr={destino_coords[0]},{destino_coords[1]})")
        
        st.markdown("---")

# --- 🤖 Sección Agente de Análisis IA (NUEVA SECCIÓN) ---
elif menu == "Agente de Análisis IA":
    st.header("💬 Agente de Análisis IA")
    st.markdown("Pregunta sobre el desempeño logístico, repartidores, o zonas de entrega.")
    
    df = load_data_from_db()

    if df.empty:
        st.warning("⚠️ No hay datos en la base de datos para realizar análisis. Carga un archivo en 'Ver Datos'.")
        st.stop()

    # Área de entrada de la pregunta del usuario
    user_query = st.text_area("Escribe tu pregunta aquí (ej: '¿Cuál es el retraso promedio del repartidor Mario?')", height=100)
    
    if st.button("Obtener Respuesta IA"):
        if user_query:
            with st.spinner("Analizando datos..."):
                # Llamar a la función de análisis
                ai_response = run_ai_analysis(df, user_query)
                
                st.success("🤖 Respuesta del Agente IA:")
                st.markdown(ai_response)
        else:
            st.error("Por favor, escribe una pregunta para el análisis.")

# --- 🗑️ Sección para borrar datos ---
elif menu == "Borrar Datos":
    st.header("🗑️ Eliminar registros")
    st.warning("⚠️ Esto borrará todos los datos de la tabla `entregas` en la base de datos de Render.")
    
    if st.button("Borrar TODO", key="delete_button"):
        clear_database()
