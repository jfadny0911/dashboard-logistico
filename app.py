import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
import io
import os
from sqlalchemy import create_engine, text

# ============================================================
# 🔗 Configuración de conexión a PostgreSQL
# ============================================================
DATABASE_URL = "postgresql+psycopg2://chivofast_db_user:VOVsj9KYQdoI7vBjpdIpTG1jj2Bvj0GS@dpg-d34osnbe5dus739qotu0-a.oregon-postgres.render.com/chivofast_db"

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        test = conn.execute(text("SELECT 1")).scalar()
        st.success(f"✅ Conexión a PostgreSQL establecida (SELECT 1 = {test})")
except Exception as e:
    st.error("❌ Error al conectar a la base de datos:")
    st.text(str(e))
    st.stop()

# ============================================================
# 📥 Cargar datos desde la BD
# ============================================================
@st.cache_data
def load_data():
    query = """
        SELECT zona, tipo_pedido, clima, trafico, tiempo_entrega, retraso, fecha
        FROM entregas
        WHERE zona IN ('San Salvador','San Miguel','Santa Ana','La Libertad')
    """
    return pd.read_sql(query, engine)

df = load_data()

# ============================================================
# 🖥 Interfaz Streamlit
# ============================================================
st.header("📦 Dashboard Predictivo de Entregas - ChivoFast")
st.markdown("Análisis y predicción de tiempos de entrega en El Salvador con datos de la base de datos PostgreSQL.")

if not df.empty:
    # ============================================================
    # 📌 KPIs
    # ============================================================
    st.subheader("📌 Indicadores Clave (KPIs)")
    col1, col2, col3 = st.columns(3)
    col1.metric("Promedio de Entrega (min)", round(df["tiempo_entrega"].mean(), 2))
    col2.metric("Retraso Promedio (min)", round(df["retraso"].mean(), 2))
    col3.metric("Total de Entregas", len(df))

    # ============================================================
    # 📊 Diagramas
    # ============================================================
    st.subheader("📍 Distribución de Entregas por Zona")
    st.plotly_chart(px.histogram(df, x="zona", color="zona", title="Número de Entregas por Zona"))

    st.subheader("🚦 Impacto del Tráfico en Tiempo de Entrega")
    st.plotly_chart(px.box(df, x="trafico", y="tiempo_entrega", color="trafico"))

    st.subheader("🌦️ Impacto del Clima en Tiempo de Entrega")
    st.plotly_chart(px.box(df, x="clima", y="tiempo_entrega", color="clima"))

    # ============================================================
    # 🗺 Mapa de El Salvador (simulado)
    # ============================================================
    st.subheader("🗺 Mapa de El Salvador con Zonas de Entregas")
    mapa = folium.Map(location=[13.7, -89.2], zoom_start=7)

    zonas_coords = {
        "San Salvador": [13.6929, -89.2182],
        "San Miguel": [13.4833, -88.1833],
        "Santa Ana": [13.9942, -89.5597],
        "La Libertad": [13.4883, -89.3222]
    }

    for _, row in df.iterrows():
        coords = zonas_coords.get(row["zona"], [13.7, -89.2])
        popup = f"📍 {row['zona']}<br>🚚 Pedido: {row['tipo_pedido']}<br>🌦 Clima: {row['clima']}<br>🚦 Tráfico: {row['trafico']}<br>⏱ Tiempo: {row['tiempo_entrega']} min"
        folium.Marker(location=coords, popup=popup, icon=folium.Icon(color="blue")).add_to(mapa)

    st_folium(mapa, width=700)

    # ============================================================
    # 📂 Archivos (Subir y Borrar)
    # ============================================================
    st.subheader("📂 Archivos")
    UPLOAD_DIR = "archivos_subidos"
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Subir archivos
    uploaded_files = st.file_uploader("Subir archivos", accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            with open(os.path.join(UPLOAD_DIR, file.name), "wb") as f:
                f.write(file.getbuffer())
        st.success("✅ Archivos subidos correctamente.")

    # Listar archivos existentes
    archivos = os.listdir(UPLOAD_DIR)
    if archivos:
        st.write("📑 Archivos disponibles:")
        for archivo in archivos:
            st.write(f"- {archivo}")

        # Opción de borrar
        archivo_borrar = st.selectbox("Seleccionar archivo a borrar", archivos)
        if st.button("🗑 Borrar archivo"):
            os.remove(os.path.join(UPLOAD_DIR, archivo_borrar))
            st.success(f"✅ Archivo '{archivo_borrar}' borrado con éxito.")
    else:
        st.info("No hay archivos disponibles.")

    # ============================================================
    # ⬇️ Exportar datos en Excel
    # ============================================================
    def to_excel(df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Entregas")
        return output.getvalue()

    st.download_button(
        label="⬇️ Descargar datos en Excel",
        data=to_excel(df),
        file_name="entregas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.warning("⚠️ No se encontraron datos en la base de datos.")

