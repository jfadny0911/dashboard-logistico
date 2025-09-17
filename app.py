import pandas as pd
import streamlit as st
import plotly.express as px
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy import create_engine, text
import folium
from streamlit_folium import st_folium
import requests
import io

# ============================================================
# 🔗 Conexión a la base de datos (Render)
# ============================================================
DB_URL = "postgresql://chivofast_db_user:VOVsj9KYQdoI7vBjpdIpTG1jj2Bvj0GS@dpg-d34osnbe5dus739qotu0-a.oregon-postgres.render.com/chivofast_db"

db_for_sqlalchemy = DB_URL
if db_for_sqlalchemy.startswith("postgres://"):
    db_for_sqlalchemy = db_for_sqlalchemy.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_for_sqlalchemy.startswith("postgresql://"):
    db_for_sqlalchemy = db_for_sqlalchemy.replace("postgresql://", "postgresql+psycopg2://", 1)

try:
    engine = create_engine(db_for_sqlalchemy, connect_args={"sslmode": "require"})
    with engine.connect() as conn:
        test = conn.execute(text("SELECT 1")).scalar()
        st.success(f"✅ Conexión a PostgreSQL establecida (SELECT 1 = {test})")
except Exception as e:
    st.error("❌ Error al conectar a la base de datos:")
    st.text(str(e))

# ============================================================
# 📥 Cargar datos
# ============================================================
@st.cache_data
def load_data():
    df = pd.read_sql("SELECT * FROM entregas", engine)
    return df

df = load_data()

# ============================================================
# 🚀 Visualización y KPIs
# ============================================================
st.header("📦 Dashboard Predictivo de Entregas - ChivoFast")
st.markdown("Análisis y predicción de tiempos de entrega usando Inteligencia Artificial")

if not df.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("Promedio de Entrega (min)", round(df["tiempo_entrega"].mean(), 2))
    col2.metric("Retraso Promedio (min)", round(df["retraso"].mean(), 2))
    col3.metric("Total de Entregas", len(df))

    st.subheader("📍 Distribución de Entregas por Zona")
    st.plotly_chart(px.histogram(df, x="zona", color="zona", title="Número de Entregas por Zona"))

    st.subheader("🚦 Impacto del Tráfico en Tiempo de Entrega")
    st.plotly_chart(px.box(df, x="trafico", y="tiempo_entrega", color="trafico"))

    st.subheader("🌦️ Impacto del Clima en Tiempo de Entrega")
    st.plotly_chart(px.box(df, x="clima", y="tiempo_entrega", color="clima"))

    # ============================================================
    # 🤖 Predicción con RandomForest
    # ============================================================
    st.subheader("🤖 Predicción de Tiempo de Entrega")

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

    # ============================================================
    # 🔮 Estimar nuevo pedido
    # ============================================================
    st.subheader("🔮 Estimar un nuevo pedido")
    zona = st.selectbox("Zona", ["San Salvador", "San Miguel", "Santa Ana", "La Libertad"])
    tipo_pedido = st.selectbox("Tipo de pedido", df["tipo_pedido"].unique())
    clima = st.selectbox("Clima", df["clima"].unique())
    trafico = st.selectbox("Tráfico", df["trafico"].unique())
    retraso = st.slider("Retraso estimado", 0, 30, 5)

    nuevo = pd.DataFrame([[zona, tipo_pedido, clima, trafico, retraso]],
                         columns=["zona","tipo_pedido","clima","trafico","retraso"])
    nuevo_ml = pd.get_dummies(nuevo)
    nuevo_ml = nuevo_ml.reindex(columns=X.columns, fill_value=0)
    prediccion = model.predict(nuevo_ml)[0]
    st.success(f"⏱️ Tiempo estimado de entrega: {round(prediccion,2)} minutos")

    # ============================================================
    # 📥 Exportar a Excel
    # ============================================================
    def to_excel(df_export):
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine="xlsxwriter")
        df_export.to_excel(writer, index=False, sheet_name="Entregas")
        writer.close()
        processed_data = output.getvalue()
        return processed_data

    st.download_button(label="💾 Exportar datos a Excel",
                       data=to_excel(df),
                       file_name="entregas.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ============================================================
    # 🗺️ Mapa con folium + clima (OpenWeather)
    # ============================================================
    st.subheader("🗺️ Mapa de El Salvador")
    mapa = folium.Map(location=[13.7, -89.2], zoom_start=7)
    # Ejemplo: agregar marcador para cada entrega
    for _, row in df.iterrows():
        folium.Marker(
            [13.7 + (hash(row["zona"])%100)/1000, -89.2 + (hash(row["zona"])%100)/1000],
            popup=f"{row['tipo_pedido']} - Tiempo: {row['tiempo_entrega']} min"
        ).add_to(mapa)

    # Mostrar mapa
    st_data = st_folium(mapa, width=700, height=500)

else:
    st.warning("⚠️ No se pudieron cargar datos desde la base de datos PostgreSQL.")
