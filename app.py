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
def create_and_load_table():
    """
    Unifica los archivos CSV y crea la tabla 'entregas' en la base de datos de Render.
    """
    st.info("Unificando y cargando datos en la base de datos...")
    try:
        # Cargar datos de los archivos CSV locales
        ubicaciones_df = pd.read_csv('ubicaciones_el_salvador.csv', sep=';')
        entregas_df = pd.read_csv('dataset_entregas (1).csv')
        
        # Unificar los DataFrames
        entregas_df.columns = [col.replace('lÃ­nea', 'linea').replace('fecha', 'hora').replace(' ', '_') for col in entregas_df.columns]
        ubicaciones_df.columns = [col.replace(' ', '_') for col in ubicaciones_df.columns]
        
        # El merge original era por 'zona', pero los nuevos datos tienen 'ubicacion' en el segundo archivo.
        # Asumiendo que 'ubicacion' del segundo archivo corresponde a 'zona' del primero.
        # Si la columna 'ubicacion' y 'zona' son equivalentes, usamos 'ubicacion' para unirlas.
        # También podemos crear una columna común. Aquí asumo que la columna 'ubicacion' es la que contiene los datos detallados
        # y 'zona' es el identificador principal. Unificaré los nombres para evitar confusiones.
        
        ubicaciones_df.rename(columns={'ubicacion': 'zona_ubicacion'}, inplace=True)
        # Crear una columna de unión si las zonas no coinciden directamente
        # En este caso, el archivo 'ubicaciones' tiene 'ubicacion' y 'municipio', que no están en 'entregas_df'.
        # El 'on=zona' del merge original no es correcto. Corregiré la lógica para usar 'departamento' y 'municipio'
        # o 'zona' si 'zona' contiene los nombres de las ubicaciones.
        # Revisando el archivo original, 'zona' en entregas_df es 'San Salvador', 'Santa Ana', 'San Miguel', 'La Libertad'.
        # Y 'ubicaciones' tiene 'departamento' con esos mismos valores. Usaré 'departamento' del archivo de ubicaciones para unificar con 'zona' del archivo de entregas.
        
        # Simplificando la lógica de unión para evitar errores:
        # Creamos una columna 'temp_zona' en `ubicaciones_df` para el merge
        ubicaciones_df['temp_zona'] = ubicaciones_df['departamento']
        entregas_df['temp_zona'] = entregas_df['zona']

        df_unificado = pd.merge(entregas_df, ubicaciones_df, on='temp_zona', how='left')
        
        # Eliminar las columnas temporales de unión y renombrar para claridad
        df_unificado.drop(columns=['temp_zona'], inplace=True)
        
        with engine.connect() as conn:
            df_unificado.to_sql('entregas', conn, if_exists='replace', index=False)
            conn.commit()
        st.success("✅ Datos unificados y cargados correctamente en la base de datos.")
    except Exception as e:
        st.error(f"❌ Error al unificar y cargar los datos: {e}")

# Carga de datos desde la base de datos en un DataFrame de Pandas
@st.cache_data(ttl=600)
def load_data_from_db():
    """
    Carga todos los datos de la tabla 'entregas' en un DataFrame.
    """
    try:
        with engine.connect() as conn:
            return pd.read_sql_table('entregas', conn)
    except ValueError:
        st.info("La tabla 'entregas' aún no se ha creado. Haz clic en 'Agregar Datos' para empezar.")
        return pd.DataFrame()

# ===============================
# 📋 Menú lateral
# ===============================
menu = st.sidebar.radio("Menú", ["Ver Datos", "KPIs", "Predicción de Rutas", "Borrar Datos"])

# --- 📤 Sección para agregar datos ---
if menu == "Ver Datos":
    st.header("📋 Datos almacenados")
    if st.button("➕ Agregar Datos"):
        create_and_load_table()
    
    df = load_data_from_db()
    
    if not df.empty:
        st.dataframe(df.head(200))
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Descargar datos en CSV", csv, "datos_unificados.csv", "text/csv")
    else:
        st.info("No hay datos en la tabla. Haz clic en 'Agregar Datos' para cargarlos por primera vez.")

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
    
    df = load_data_from_db()

    if not df.empty:
        # Obtener todas las ubicaciones únicas de los datos unificados
        todas_ubicaciones = sorted(df['ubicacion'].unique())
        
        col_origen, col_destino = st.columns(2)
        with col_origen:
            origen = st.selectbox("Selecciona zona de origen", todas_ubicaciones, key="origen_select")
        with col_destino:
            destino = st.selectbox("Selecciona zona de destino", todas_ubicaciones, key="destino_select")

        # Coordenadas aproximadas para las ubicaciones
        # Esta es una simulación. Para una aplicación real, necesitarías coordenadas geográficas reales.
        # He creado un diccionario de coordenadas aproximadas para las ubicaciones del CSV
        coordenadas = {
            "Puerto de La Libertad": [13.4886, -89.3222],
            "Playa El Tunco": [13.4886, -89.3222],
            "Carretera al Puerto de La Libertad": [13.50, -89.32],
            "Centro Comercial La Gran Vía": [13.6749, -89.2625],
            "Colonia Santa Fe": [13.49, -89.31],
            "Bulevar Monseñor Romero": [13.68, -89.26],
            "Residencial Costa del Sol": [13.2514, -88.9408],
            "Colonia Ciudad Pacífica": [13.4806, -88.1678],
            "Centro Histórico": [13.482, -88.175],
            "Metrocentro San Miguel": [13.482, -88.177],
            "Bulevar Juan Pablo II": [13.485, -88.180],
            "Colonia El Porvenir": [13.483, -88.185],
            "Colonia La Presita": [13.481, -88.170],
            "Residencial Los Olivos": [13.480, -88.165],
            "Colonia Escalón": [13.7028, -89.2275],
            "Colonia Miramonte": [13.71, -89.21],
            "Colonia San Benito": [13.68, -89.24],
            "Metrocentro San Salvador": [13.70, -89.21],
            "Bulevar de los Héroes": [13.71, -89.20],
            "Calle Arce": [13.70, -89.19],
            "Residencial Altavista": [13.70, -89.15],
            "Colonia Santa Lucía": [13.70, -89.13],
            "Colonia La Campanera": [13.69, -89.12],
            "Colonia Zacamil": [13.74, -89.20],
            "Colonia San Francisco": [13.68, -89.22],
            "Boulevard Constitución": [13.72, -89.21],
            "Colonia Médica": [13.70, -89.20],
            "Zona Rosa": [13.67, -89.23],
            "Colonia San José": [13.98, -89.55],
            "Metrocentro Santa Ana": [13.99, -89.56],
            "Bulevar Los 44": [13.99, -89.55],
            "Barrio El Calvario": [13.98, -89.54],
            "Colonia El Palmar": [13.98, -89.57],
            "Residencial Las Brisas": [13.98, -89.56]
        }
        
        if origen and destino:
            if origen != destino:
                mapa = folium.Map(location=[13.7, -89.2], zoom_start=8)
                
                origen_coords = coordenadas.get(origen, [random.uniform(13.2, 14.1), random.uniform(-89.6, -88.0)])
                destino_coords = coordenadas.get(destino, [random.uniform(13.2, 14.1), random.uniform(-89.6, -88.0)])
                
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
        st.info("La base de datos está vacía. Por favor, haz clic en 'Agregar Datos' para usar esta funcionalidad.")

# --- 🗑️ Sección para borrar datos ---
elif menu == "Borrar Datos":
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
