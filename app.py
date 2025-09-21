import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
import random
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
    encodings = ['latin1', 'utf-8', 'iso-8859-1', 'cp1252']
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
    encodings = ['latin1', 'utf-8', 'iso-8859-1', 'cp1252']
    for enc in encodings:
        try:
            file_content = uploaded_file.getvalue().decode(enc)
            # Intenta detectar el delimitador automáticamente
            try:
                df = pd.read_csv(StringIO(file_content))
                return df
            except pd.errors.ParserError:
                try:
                    df = pd.read_csv(StringIO(file_content), sep=';')
                    return df
                except pd.errors.ParserError:
                    continue
        except UnicodeDecodeError:
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

        entregas_df.columns = [col.replace('lÃnea', 'linea').replace('fecha', 'hora').replace(' ', '_') for col in entregas_df.columns]
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
            avg_global = round(df[numeric_cols].mean().mean(), 2)
            max_global = round(df[numeric_cols].max().max(), 2)
            col2.metric("🔹 Promedio global", avg_global)
            col3.metric("📈 Máximo global", max_global)

        # Filtros para la visualización
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

# --- 🚚 Predicción de Rutas simuladas ---
elif menu == "Predicción de Rutas":
    st.header("🚚 Predicción de Rutas en El Salvador (Simulación)")
    
    uploaded_file = st.file_uploader("Sube el archivo de ubicaciones con coordenadas (CSV)", type=["csv"], key="ubicaciones_file_uploader")
    
    if uploaded_file is not None:
        try:
            # Se usa una función más robusta para leer el archivo subido
            ubicaciones_df = read_uploaded_csv_with_encoding(uploaded_file)
            
            if ubicaciones_df is None:
                st.warning("El archivo subido no pudo ser procesado. Asegúrate de que es un CSV válido.")
            # 🌟 Se modifican los nombres de las columnas para que coincidan con tu archivo
            elif 'Ubicación' not in ubicaciones_df.columns or 'Latitud' not in ubicaciones_df.columns or 'Longitud' not in ubicaciones_df.columns:
                st.error("❌ Error: El archivo debe contener las columnas 'Ubicación', 'Latitud' y 'Longitud'.")
            else:
                # Renombrar las columnas del archivo subido para que el resto del código funcione
                ubicaciones_df = ubicaciones_df.rename(columns={
                    'Ubicación': 'ubicacion',
                    'Latitud': 'latitud',
                    'Longitud': 'longitud'
                })

                todas_ubicaciones = sorted(ubicaciones_df['ubicacion'].unique())
                
                st.success("✅ Archivo de ubicaciones cargado con éxito. Ahora puedes seleccionar los puntos de la ruta.")
                
                col_origen, col_destino = st.columns(2)
                with col_origen:
                    origen = st.selectbox("Selecciona zona de origen", todas_ubicaciones, key="origen_select")
                with col_destino:
                    destino = st.selectbox("Selecciona zona de destino", todas_ubicaciones, key="destino_select")

                col_clima, col_trafico = st.columns(2)
                with col_clima:
                    clima_options = ['Soleado', 'Lluvioso', 'Nublado']
                    selected_clima = st.selectbox("Selecciona el clima:", options=clima_options)
                with col_trafico:
                    trafico_options = ['Bajo', 'Medio', 'Alto']
                    selected_trafico = st.selectbox("Selecciona el tráfico:", options=trafico_options)

                if origen and destino:
                    if origen != destino:
                        coordenadas = {
                            row['ubicacion']: [row['latitud'], row['longitud']]
                            for index, row in ubicaciones_df.iterrows()
                        }
                        
                        default_coords = [13.7, -89.2]

                        mapa = folium.Map(location=[13.7, -89.2], zoom_start=8)
                        
                        origen_coords = coordenadas.get(origen, default_coords)
                        destino_coords = coordenadas.get(destino, default_coords)
                        
                        folium.Marker(origen_coords, popup=f"Origen: {origen}", icon=folium.Icon(color="green")).add_to(mapa)
                        folium.Marker(destino_coords, popup=f"Destino: {destino}", icon=folium.Icon(color="red")).add_to(mapa)
                        
                        puntos = [
                            origen_coords,
                            [(origen_coords[0] + destino_coords[0])/2 + random.uniform(-0.05, 0.05), (origen_coords[1] + destino_coords[1])/2 + random.uniform(-0.05, 0.05)],
                            destino_coords
                        ]
                        folium.PolyLine(puntos, color="blue", weight=4, opacity=0.8).add_to(mapa)
                        
                        st_folium(mapa, width=700, height=500)
                        
                        base_time = 30
                        if selected_trafico == 'Medio':
                            base_time += 15
                        elif selected_trafico == 'Alto':
                            base_time += 30
                        
                        if selected_clima == 'Lluvioso':
                            base_time += 10
                        
                        tiempo_estimado = random.randint(base_time - 5, base_time + 5)
                        
                        st.success(f"⏱️ Tiempo estimado: {tiempo_estimado} minutos")
                        st.info(f"Condiciones: Tráfico {selected_trafico} | Clima {selected_clima}")
                    else:
                        st.warning("El origen y destino no pueden ser iguales.")
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {e}")
    else:
        st.info("Por favor, sube el archivo de ubicaciones con coordenadas para ver las predicciones de ruta.")

# --- 🗑️ Sección para borrar datos ---
elif menu == "Borrar Datos":
    st.header("🗑️ Eliminar registros")
    st.warning("⚠️ Esto borrará todos los datos de la tabla `entregas` en la base de datos de Render.")
    
    if st.button("Borrar TODO", key="delete_button"):
        clear_database()
