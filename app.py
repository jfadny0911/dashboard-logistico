import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
import io
import os
from sqlalchemy import create_engine, text
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# ============================================================
# 🔗 Conexión a PostgreSQL
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
        SELECT id_entrega, zona, tipo_pedido, clima, trafico, tiempo_entrega, retraso, fecha
        FROM entregas
        WHERE zona IN ('San Salvador','San Miguel','Santa Ana','La Libertad')
    """
    return pd.read_sql(query, engine)

df = load_data()

# ============================================================
# 🖥 Interfaz Streamlit
# ============================================================
st.header("📦 Dashboard Predictivo de Entregas - ChivoFast")
st.markdown("Análisis, predicción y gestión de entregas en El Salvador con datos de PostgreSQL.")

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
    # 🤖 Modelo de Predicción
    # ============================================================
    st.subheader("🤖 Predicción de Tiempo de Entrega")

    # Preparación de datos
    df_ml = pd.get_dummies(df.drop(columns=["id_entrega", "fecha"]), drop_first=True)
    X = df_ml.drop(columns=["tiempo_entrega"])
    y = df_ml["tiempo_entrega"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = mean_squared_error(y_test, y_pred, squared=False)
    r2 = r2_score(y_test, y_pred)

    st.write("📊 Resultados del Modelo:")
    st.write(f"MAE: {round(mae,2)} | RMSE: {round(rmse,2)} | R²: {round(r2,2)}")

    # Estimar un nuevo pedido
    st.subheader("🔮 Estimar un nuevo pedido")
    zona = st.selectbox("Zona", df["zona"].unique())
    tipo_pedido = st.selectbox("Tipo de pedido", df["tipo_pedido"].unique())
    clima = st.selectbox("Clima", df["clima"].unique())
    trafico = st.selectbox("Tráfico", df["trafico"].unique())
    retraso = st.slider("Retraso estimado (min)", 0, 30, 5)

    nuevo = pd.DataFrame([[zona, tipo_pedido, clima, trafico, retraso]],
                         columns=["zona", "tipo_pedido", "clima", "trafico", "retraso"])
    nuevo_ml = pd.get_dummies(nuevo)
    nuevo_ml = nuevo_ml.reindex(columns=X.columns, fill_value=0)
    prediccion = model.predict(nuevo_ml)[0]

    st.success(f"⏱️ Tiempo estimado de entrega: {round(prediccion,2)} minutos")

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
