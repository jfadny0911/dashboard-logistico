import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import random
import os
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import io
import plotly.express as px

st.set_page_config(page_title="Dashboard Logístico - ChivoFast", layout="wide")

# ===============================
# Carpetas
# ===============================
UPLOAD_DIR = "uploaded_files"
HISTORICO_DIR = "historico"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(HISTORICO_DIR, exist_ok=True)

HIST_ENTREGAS = os.path.join(HISTORICO_DIR, "historico_entregas.xlsx")
HIST_PREDICCIONES = os.path.join(HISTORICO_DIR, "historico_predicciones.xlsx")

# ===============================
# Inicializar df
# ===============================
df = pd.DataFrame()
if os.path.exists(HIST_ENTREGAS):
    df = pd.read_excel(HIST_ENTREGAS)

# ===============================
# Sidebar: subir / borrar Excel
# ===============================
st.sidebar.header("📥 Subir / Eliminar archivos")
uploaded_file = st.sidebar.file_uploader("Sube un archivo Excel", type=["xlsx"])
if uploaded_file:
    df_nuevo = pd.read_excel(uploaded_file)
    # Guardar archivo original
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"✅ Archivo guardado: {uploaded_file.name}")

    # Concatenar al histórico
    df = pd.concat([df, df_nuevo], ignore_index=True)
    df.to_excel(HIST_ENTREGAS, index=False)
    st.sidebar.info(f"Histórico actualizado: {len(df)} filas")

# Listar archivos guardados
st.sidebar.subheader("Archivos subidos")
files_list = os.listdir(UPLOAD_DIR)
for f in files_list:
    st.sidebar.write(f)
    if st.sidebar.button(f"🗑 Borrar {f}"):
        os.remove(os.path.join(UPLOAD_DIR, f))
        st.sidebar.warning(f"⚠️ Archivo {f} borrado")

# ===============================
# Dashboard principal
# ===============================
st.title("📦 Dashboard Logístico - ChivoFast")
st.markdown("Análisis, predicción de tiempos de entrega y registro histórico")

if not df.empty:
    # ===============================
    # KPIs
    # ===============================
    st.subheader("📌 KPIs")

    trafico_factor = {"🚦 Bajo": 1.0, "🚦 Medio": 1.15, "🚦 Alto": 1.3}
    clima_factor = {"☀️ Soleado": 1.0, "🌥️ Nublado": 1.1, "🌧️ Lluvioso": 1.25}

    df["tiempo_ajustado"] = df["tiempo_entrega"] * df["trafico"].map(trafico_factor) * df["clima"].map(clima_factor)

    promedio = df["tiempo_entrega"].mean()
    promedio_aj = df["tiempo_ajustado"].mean()
    retraso_prom = df["retraso"].mean()
    total_entregas = len(df)
    min_aj = df["tiempo_ajustado"].min()
    max_aj = df["tiempo_ajustado"].max()

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Promedio", round(promedio,2))
    col2.metric("Promedio Ajustado", round(promedio_aj,2))
    col3.metric("Retraso Promedio", round(retraso_prom,2))
    col4.metric("Total Entregas", total_entregas)
    col5.metric("Entrega más rápida", round(min_aj,2))
    col6.metric("Entrega más larga", round(max_aj,2))

    # ===============================
    # Gráficos de distribución
    # ===============================
    st.subheader("📊 Distribución de Entregas")
    fig1 = px.histogram(df, x="zona", color="tipo_pedido", title="Número de entregas por zona y tipo de pedido")
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = px.box(df, x="trafico", y="tiempo_entrega", color="clima", title="Impacto de tráfico y clima en tiempo de entrega")
    st.plotly_chart(fig2, use_container_width=True)

    # ===============================
    # Predicción de rutas ML
    # ===============================
    st.subheader("🚚 Predicción de Rutas")

    required_cols = ["zona","tipo_pedido","clima","trafico","tiempo_entrega"]
    if all(col in df.columns for col in required_cols):
        df_ml = pd.get_dummies(df[required_cols].dropna(), drop_first=True)
        X = df_ml.drop(columns=["tiempo_entrega"])
        y = df_ml["tiempo_entrega"]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        st.info(f"MAE del modelo: {round(mae,2)} min")

        zonas = df["zona"].unique()
        origen = st.selectbox("Origen", zonas)
        destino = st.selectbox("Destino", zonas)
        if origen != destino:
            tipo_pedido = st.selectbox("Tipo de pedido", df["tipo_pedido"].unique())
            clima_sel = st.selectbox("Clima", df["clima"].unique())
            trafico_sel = st.selectbox("Tráfico", df["trafico"].unique())

            nuevo = pd.DataFrame([[origen,tipo_pedido,clima_sel,trafico_sel]],
                                 columns=["zona","tipo_pedido","clima","trafico"])
            nuevo_ml = pd.get_dummies(nuevo)
            nuevo_ml = nuevo_ml.reindex(columns=X.columns, fill_value=0)
            pred_base = model.predict(nuevo_ml)[0]
            pred_ajustada = pred_base * trafico_factor[trafico_sel] * clima_factor[clima_sel]
            st.success(f"⏱️ Tiempo estimado: {round(pred_ajustada,2)} min")
            st.info(f"Condiciones: {trafico_sel} | {clima_sel}")

            # ===============================
            # Guardar predicción histórica
            # ===============================
            df_pred = pd.DataFrame({
                "Origen":[origen],
                "Destino":[destino],
                "Tipo Pedido":[tipo_pedido],
                "Clima":[clima_sel],
                "Tráfico":[trafico_sel],
                "Tiempo Estimado":[round(pred_ajustada,2)]
            })

            if os.path.exists(HIST_PREDICCIONES):
                df_hist_pred = pd.read_excel(HIST_PREDICCIONES)
                df_pred = pd.concat([df_hist_pred, df_pred], ignore_index=True)
            df_pred.to_excel(HIST_PREDICCIONES, index=False)

            st.download_button("⬇️ Descargar predicción en Excel", data=df_pred.to_excel(index=False),
                               file_name="historico_predicciones.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        else:
            st.warning("Origen y destino no pueden ser iguales.")
    else:
        st.warning(f"El dataset debe contener: {required_cols}")

    # ===============================
    # Descargar histórico completo de entregas
    # ===============================
    with open(HIST_ENTREGAS, "rb") as f:
        st.download_button("⬇️ Descargar histórico de entregas", data=f,
                           file_name="historico_entregas.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Descargar histórico completo de predicciones
    if os.path.exists(HIST_PREDICCIONES):
        with open(HIST_PREDICCIONES, "rb") as f:
            st.download_button("⬇️ Descargar histórico de predicciones", data=f,
                               file_name="historico_predicciones.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.warning("⚠️ No hay datos cargados. Sube un Excel para comenzar.")
