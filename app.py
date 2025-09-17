import streamlit as st
import pandas as pd
import plotly.express as px
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy import create_engine, text
import os
import requests
import folium
from streamlit_folium import st_folium
import io
import smtplib
from email.message import EmailMessage

# ============================================================
# 🔗 Configuración de conexión y APIs
# ============================================================
DATABASE_URL = os.getenv("DATABASE_URL")
OPENWEATHER_API_KEY = "157cfb5a57724258093e18ea5efda645"
OPENROUTESERVICE_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjgzYzM4NmEzMjkzNzRkMjQ4NWQ3YmJlIiwiaCI6Im11cm11cjY0In0="

if not DATABASE_URL:
    st.error("❌ No se encontró DATABASE_URL en los Secrets de Streamlit")
else:
    db_for_sqlalchemy = DATABASE_URL
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
# 📥 Cargar datos desde PostgreSQL
# ============================================================
@st.cache_data
def load_data():
    if not DATABASE_URL:
        return pd.DataFrame()
    engine_local = create_engine(db_for_sqlalchemy, connect_args={"sslmode": "require"})
    df = pd.read_sql("SELECT * FROM entregas WHERE zona IN ('San Salvador','San Miguel','Santa Ana','La Libertad')", engine_local)
    return df

df = load_data()

# ============================================================
# 🖥 Interfaz Streamlit
# ============================================================
st.header("📦 Dashboard Predictivo de Entregas - ChivoFast")
st.markdown("Análisis y predicción de tiempos de entrega usando Inteligencia Artificial")

if not df.empty:
    # KPIs
    st.subheader("📌 Indicadores Clave (KPIs)")
    col1, col2, col3 = st.columns(3)
    col1.metric("Promedio de Entrega (min)", round(df["tiempo_entrega"].mean(), 2))
    col2.metric("Retraso Promedio (min)", round(df["retraso"].mean(), 2))
    col3.metric("Total de Entregas", len(df))

    # Diagramas
    st.subheader("📍 Distribución de Entregas por Zona")
    st.plotly_chart(px.histogram(df, x="zona", color="zona", title="Número de Entregas por Zona"))

    st.subheader("🚦 Impacto del Tráfico en Tiempo de Entrega")
    st.plotly_chart(px.box(df, x="trafico", y="tiempo_entrega", color="trafico"))

    st.subheader("🌦️ Impacto del Clima en Tiempo de Entrega")
    st.plotly_chart(px.box(df, x="clima", y="tiempo_entrega", color="clima"))

    # Predicción
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

    # Estimar nuevo pedido
    st.subheader("🔮 Estimar un nuevo pedido")
    zona = st.selectbox("Zona", df["zona"].unique())
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

    # Exportar Excel
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

    # Mapa de El Salvador
    st.subheader("🗺 Mapa de El Salvador")
    mapa = folium.Map(location=[13.7, -89.2], zoom_start=7)
    for _, row in df.iterrows():
        folium.Marker(
            location=[13.7 + (hash(row["zona"])%5)*0.01, -89.2 + (hash(row["zona"])%5)*0.01],
            popup=f"Zona: {row['zona']} | Pedido: {row['tipo_pedido']} | Tiempo: {row['tiempo_entrega']} min"
        ).add_to(mapa)
    st_folium(mapa, width=700)

    # ============================================================
    # 🌡 Clima en tiempo real
    # ============================================================
    st.subheader("🌦️ Clima en tiempo real por zona")
    for zona_name, coords in {
        "San Salvador": [13.7, -89.2],
        "San Miguel": [13.48, -88.18],
        "Santa Ana": [13.98, -89.57],
        "La Libertad": [13.49, -89.32]
    }.items():
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={coords[0]}&lon={coords[1]}&appid={OPENWEATHER_API_KEY}&units=metric"
        try:
            res = requests.get(url).json()
            st.write(f"{zona_name}: {res['weather'][0]['description']}, Temp: {res['main']['temp']}°C")
        except:
            st.write(f"{zona_name}: ❌ No se pudo obtener el clima")

    # ============================================================
    # 🚚 Rutas optimizadas (OpenRouteService)
    # ============================================================
    st.subheader("🚚 Predicción de la mejor ruta por proveedor")
    proveedores = df["tipo_pedido"].unique()
    for prov in proveedores:
        st.write(f"Proveedor: {prov}")
        prov_df = df[df["tipo_pedido"]==prov]
        # Generar ruta simple por lat/lon ficticio (para demo)
        coords = [[13.7, -89.2]] + [[13.7 + i*0.01, -89.2 + i*0.01] for i in range(len(prov_df))]
        m = folium.Map(location=[13.7, -89.2], zoom_start=7)
        folium.PolyLine(locations=coords, color="blue", weight=5).add_to(m)
        st_folium(m, width=700)

    # ============================================================
    # 📧 Enviar rutas por correo
    # ============================================================
    st.subheader("📧 Enviar rutas por correo")
    email = st.text_input("Correo del proveedor")
    if st.button("Enviar rutas"):
        try:
            msg = EmailMessage()
            msg["Subject"] = "Rutas de Entrega - ChivoFast"
            msg["From"] = "tucorreo@example.com"
            msg["To"] = email
            msg.set_content("Adjuntamos las rutas de entrega para su proveedor.")
            msg.add_attachment(to_excel(df), maintype="application", subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="entregas.xlsx")
            with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
                smtp.starttls()
                smtp.login("tucorreo@example.com", "TU_CONTRASEÑA")  # Cambiar a tu cuenta
                smtp.send_message(msg)
            st.success("✅ Rutas enviadas correctamente")
        except Exception as e:
            st.error(f"❌ Error al enviar correo: {e}")

else:
    st.warning("⚠️ No se pudieron cargar datos desde la base de datos PostgreSQL.")
