import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import random
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sqlalchemy import create_engine, text
import os

st.set_page_config(page_title="Dashboard Logístico - ChivoFast", layout="wide")

# ===============================
# Inicializar df vacío
# ===============================
df = pd.DataFrame()

# ===============================
# Sidebar: subir/borrar archivo Excel
# ===============================
st.sidebar.header("📥 Cargar/Eliminar Datos")
uploaded_file = st.sidebar.file_uploader("Sube un archivo Excel", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.sidebar.success(f"✅ Archivo cargado: {len(df)} filas")

if st.sidebar.button("🗑 Borrar datos cargados"):
    df = pd.DataFrame()
    st.sidebar.warning("⚠️ Datos borrados")

# ===============================
# Conexión opcional a PostgreSQL
# ===============================
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL)
        st.sidebar.success("✅ Conectado a PostgreSQL")
        try:
            df_db = pd.read_sql("SELECT * FROM excel_data", engine)
            if not df_db.empty:
                df = df_db
                st.sidebar.info(f"Datos cargados desde DB: {len(df)} filas")
        except:
            st.sidebar.warning("⚠️ No se pudo cargar datos de DB")
    except Exception as e:
        st.sidebar.error(f"❌ Error al conectar DB: {e}")

# ===============================
# Dashboard Principal
# ===============================
st.title("📦 Dashboard Logístico - ChivoFast")
st.markdown("Análisis y predicción de tiempos de entrega usando Inteligencia Artificial")

# ===============================
# KPIs
# ===============================
if not df.empty:
    st.subheader("📌 Indicadores Clave (KPIs)")

    # Factores de ajuste
    trafico_factor = {"🚦 Bajo": 1.0, "🚦 Medio": 1.15, "🚦 Alto": 1.3}
    clima_factor = {"☀️ Soleado": 1.0, "🌥️ Nublado": 1.1, "🌧️ Lluvioso": 1.25}

    # Ajuste de tiempo
    df["tiempo_ajustado"] = df["tiempo_entrega"] * df["trafico"].map(trafico_factor) * df["clima"].map(clima_factor)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Promedio de Entrega (min)", round(df["tiempo_entrega"].mean(), 2))
    col2.metric("Promedio Ajustado (min)", round(df["tiempo_ajustado"].mean(), 2))
    col3.metric("Retraso Promedio (min)", round(df["retraso"].mean(), 2))
    col4.metric("Total de Entregas", len(df))

    col5, col6 = st.columns(2)
    col5.metric("Entrega más rápida (ajustada)", round(df["tiempo_ajustado"].min(), 2))
    col6.metric("Entrega más larga (ajustada)", round(df["tiempo_ajustado"].max(), 2))

    # ===============================
    # Predicción de Rutas ML + Ajustes
    # ===============================
    st.subheader("🚚 Predicción de Rutas (ML + Clima/Tráfico)")

    try:
        required_cols = ["zona", "tipo_pedido", "clima", "trafico", "tiempo_entrega"]
        if all(col in df.columns for col in required_cols):
            df_ml = pd.get_dummies(df[required_cols].dropna(), drop_first=True)
            X = df_ml.drop(columns=["tiempo_entrega"])
            y = df_ml["tiempo_entrega"]

            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            mae = mean_absolute_error(y_test, y_pred)
            st.info(f"MAE del modelo: {round(mae,2)} min (error promedio en test)")

            # Selección de ruta
            zonas = df["zona"].unique()
            origen = st.selectbox("Selecciona zona de origen", zonas)
            destino = st.selectbox("Selecciona zona de destino", zonas)

            if origen != destino:
                tipo_pedido = st.selectbox("Selecciona tipo de pedido", df["tipo_pedido"].unique())
                clima_sel = st.selectbox("Selecciona clima", df["clima"].unique())
                trafico_sel = st.selectbox("Selecciona tráfico", df["trafico"].unique())

                nuevo = pd.DataFrame([[origen, tipo_pedido, clima_sel, trafico_sel]],
                                     columns=["zona", "tipo_pedido", "clima", "trafico"])
                nuevo_ml = pd.get_dummies(nuevo)
                nuevo_ml = nuevo_ml.reindex(columns=X.columns, fill_value=0)
                pred_base = model.predict(nuevo_ml)[0]

                # Ajuste
                pred_ajustada = pred_base * trafico_factor[trafico_sel] * clima_factor[clima_sel]
                st.success(f"⏱️ Tiempo estimado de entrega: {round(pred_ajustada,2)} minutos")
                st.info(f"Condiciones seleccionadas: {trafico_sel} | {clima_sel}")

                # Mapa de ruta simulada
                coords = {
                    "San Salvador": [13.6929, -89.2182],
                    "Santa Ana": [13.9942, -89.5598],
                    "San Miguel": [13.4833, -88.1833],
                    "La Libertad": [13.4886, -89.3222]
                }
                mapa = folium.Map(location=[13.7, -89.2], zoom_start=8)
                folium.Marker(coords[origen], popup=f"Origen: {origen}", icon=folium.Icon(color="green")).add_to(mapa)
                folium.Marker(coords[destino], popup=f"Destino: {destino}", icon=folium.Icon(color="red")).add_to(mapa)

                lat1, lon1 = coords[origen]
                lat2, lon2 = coords[destino]
                puntos = [
                    [lat1 + random.uniform(-0.03, 0.03), lon1 + random.uniform(-0.03, 0.03)],
                    [(lat1+lat2)/2 + random.uniform(-0.03, 0.03), (lon1+lon2)/2 + random.uniform(-0.03, 0.03)],
                    [lat2 + random.uniform(-0.03, 0.03), lon2 + random.uniform(-0.03, 0.03)]
                ]
                folium.PolyLine(puntos, color="blue", weight=4, opacity=0.8).add_to(mapa)
                st_folium(mapa, width=700, height=500)

            else:
                st.warning("El origen y destino no pueden ser iguales.")

        else:
            st.warning(f"El dataset debe contener las columnas: {required_cols}")

    except Exception as e:
        st.error(f"Error al entrenar modelo o predecir rutas: {e}")

else:
    st.warning("⚠️ No hay datos cargados. Sube un Excel o conecta la base de datos.")
