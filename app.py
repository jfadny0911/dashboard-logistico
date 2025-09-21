import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
import random

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
# 📋 Carga y Unificación de Datos
# ===============================
def check_and_create_table():
    """
    Verifica si la tabla 'entregas' existe en la BD de Render y la crea si no es así,
    cargando los datos de los archivos CSV unificados.
    """
    try:
        with engine.connect() as conn:
            # Intenta leer una fila para verificar si la tabla existe
            conn.execute(text("SELECT 1 FROM entregas LIMIT 1"))
        return True
    except Exception:
        # Si la tabla no existe, procede a crearla
        st.info("La tabla 'entregas' no existe en la base de datos. Unificando y cargando datos...")
        try:
            # Cargar datos de los archivos CSV locales
            ubicaciones_df = pd.read_csv('ubicaciones_el_salvador.csv', sep=';')
            entregas_df = pd.read_csv('dataset_entregas (1).csv')
            
            # Unificar los DataFrames
            entregas_df.columns = [col.replace('lÃ­nea', 'linea').replace('fecha', 'hora') for col in entregas_df.columns]
            df_unificado = pd.merge(entregas_df, ubicaciones_df, on='zona')
            
            # Guardar el DataFrame unificado en la base de datos de Render
            with engine.connect() as conn:
                df_unificado.to_sql('entregas', conn, if_exists='replace', index=False)
                conn.commit()
            st.success("✅ La base de datos ha sido creada y los datos se han unificado y cargado correctamente.")
            return True
        except Exception as e:
            st.error(f"❌ Error al unificar y cargar los datos: {e}")
            return False
    return False

# Carga de datos de la base de datos en un DataFrame de Pandas
def load_data_from_db():
    """
    Carga todos los datos de la tabla 'entregas' en un DataFrame.
    """
    if check_and_create_table():
        try:
            return pd.read_sql_table('entregas', engine)
        except Exception as e:
            st.error(f"Error al leer datos de la tabla 'entregas': {e}")
            return pd.DataFrame()
    return pd.DataFrame()


# ===============================
# 📋 Menú lateral
# ===============================
menu = st.sidebar.radio("Menú", ["Ver Datos", "KPIs", "Predicción de Rutas", "Borrar Datos"])

# --- 🗑️ Sección para borrar datos ---
if menu == "Borrar Datos":
    st.header("🗑️ Eliminar registros")
    st.warning("⚠️ Esto borrará todos los datos de la tabla `entregas` en la base de datos de Render.")
    
    if st.button("Borrar TODO", key="delete_button"):
        try:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM entregas"))
                conn.commit()
            st.success("✅ Todos los datos fueron eliminados de la base de datos.")
        except Exception as e:
            st.error(f"Error: {e}")

# --- 📋 Ver Datos ---
elif menu == "Ver Datos":
    st.header("📋 Datos almacenados")
    df = load_data_from_db()
    
    if not df.empty:
        st.dataframe(df.head(200))
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Descargar datos en CSV", csv, "datos_unificados.csv", "text/csv")
    else:
        st.info("No hay datos en la tabla. Sube un archivo en la opción 'Subir Excel' si quieres cargarlos.")

# --- 📈 KPIs y Dashboard estilo BI ---
elif menu == "KPIs":
    st.header("📈 Indicadores Clave (KPIs)")
    df = load_data_from_db()
    
    if not df.empty:
        df_kpi = df.rename(columns={'ubicacion': 'ubicacion', 'municipio': 'municipio', 'departamento': 'departamento',
                                    'fecha': 'fecha', 'zona': 'zona', 'tipo_pedido': 'tipo_pedido', 'clima': 'clima',
                                    'trafico': 'trafico', 'tiempo_entrega': 'tiempo_entrega', 'retraso': 'retraso'})
        
        total_registros = len(df_kpi)

        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total registros", total_registros)
        
        numeric_cols = df_kpi.select_dtypes(include="number").columns
        if not numeric_cols.empty:
            avg_global = round(df_kpi[numeric_cols].mean().mean(), 2)
            max_global = round(df_kpi[numeric_cols].max().max(), 2)
            col2.metric("🔹 Promedio global", avg_global)
            col3.metric("📈 Máximo global", max_global)

        # Filtros para la visualización
        st.subheader("Filtros para análisis detallado")
        col_select_departamento, col_select_municipio, col_select_tipo_pedido = st.columns(3)
        
        with col_select_departamento:
            selected_departamento = st.selectbox(
                'Selecciona el Departamento:',
                options=df_kpi['departamento'].unique()
            )

        with col_select_municipio:
            municipios_disponibles = df_kpi[df_kpi['departamento'] == selected_departamento]['municipio'].unique()
            selected_municipio = st.selectbox(
                'Selecciona el Municipio:',
                options=municipios_disponibles
            )

        with col_select_tipo_pedido:
            tipo_pedido_disponibles = df_kpi['tipo_pedido'].unique()
            selected_tipo_pedido = st.selectbox(
                'Selecciona el Tipo de Pedido:',
                options=tipo_pedido_disponibles
            )

        filtered_df = df_kpi[
            (df_kpi['departamento'] == selected_departamento) &
            (df_kpi['municipio'] == selected_municipio) &
            (df_kpi['tipo_pedido'] == selected_tipo_pedido)
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
    
    df = load_data_from_db()

    if not df.empty:
        # Obtener todas las ubicaciones únicas de los datos unificados
        todas_ubicaciones = sorted(df['ubicacion'].unique())
        
        col_origen, col_destino = st.columns(2)
        with col_origen:
            origen = st.selectbox("Selecciona zona de origen", todas_ubicaciones, key="origen_select")
        with col_destino:
            destino = st.selectbox("Selecciona zona de destino", todas_ubicaciones, key="destino_select")
        
        if origen and destino:
            if origen != destino:
                # Cargar el archivo ubicaciones_el_salvador.csv para obtener las coordenadas
                try:
                    ubicaciones_df = pd.read_csv('ubicaciones_el_salvador.csv', sep=';')
                    coordenadas = dict(zip(ubicaciones_df['ubicacion'], ubicaciones_df[['latitud', 'longitud']].values.tolist()))
                except Exception as e:
                    st.error(f"Error al cargar el archivo de ubicaciones: {e}")
                    coordenadas = {}

                # Coordenadas por defecto si la ubicación no se encuentra
                default_coords = [13.7, -89.2]

                mapa = folium.Map(location=[13.7, -89.2], zoom_start=8)
                
                origen_coords = coordenadas.get(origen, default_coords)
                destino_coords = coordenadas.get(destino, default_coords)
                
                folium.Marker(origen_coords, popup=f"Origen: {origen}", icon=folium.Icon(color="green")).add_to(mapa)
                folium.Marker(destino_coords, popup=f"Destino: {destino}", icon=folium.Icon(color="red")).add_to(mapa)
                
                # Ruta simulada
                puntos = [
                    origen_coords,
                    [(origen_coords[0] + destino_coords[0])/2 + random.uniform(-0.05, 0.05), (origen_coords[1] + destino_coords[1])/2 + random.uniform(-0.05, 0.05)],
                    destino_coords
                ]
                folium.PolyLine(puntos, color="blue", weight=4, opacity=0.8).add_to(mapa)
                
                st_folium(mapa, width=700, height=500)
                
                tiempo_estimado = random.randint(30, 120)
                trafico = random.choice(["🚦 Bajo", "🚦 Medio", "🚦 Alto"])
                clima = random.choice(["☀️ Soleado", "🌧️ Lluvioso", "🌥️ Nublado"])
                
                st.success(f"⏱️ Tiempo estimado: {tiempo_estimado} minutos")
                st.info(f"Condiciones: {trafico} | {clima}")
            else:
                st.warning("El origen y destino no pueden ser iguales.")
    else:
        st.info("La base de datos está vacía. Por favor, carga los archivos para usar esta funcionalidad.")
