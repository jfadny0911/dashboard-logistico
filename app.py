import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import folium
from streamlit_folium import st_folium
import random

# ===============================
# 🔗 Conexión a la base de datos
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
# 📋 Menú lateral
# ===============================
menu = st.sidebar.radio("Menú", ["Subir Excel", "Ver Datos", "KPIs", "Predicción de Rutas", "Borrar Datos"])


# 📤 Subir Excel
if menu == "Subir Excel":
    st.header("📤 Subir archivo Excel")
    uploaded_file = st.file_uploader("Selecciona un archivo Excel", type=["xlsx", "xls"])

    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            st.write("✅ Vista previa:")
            st.dataframe(df.head())

            if st.button("Guardar en BD"):
                with engine.begin() as conn:
                    df.to_sql("excel_data", conn, if_exists="append", index=False)
                st.success(f"Archivo {uploaded_file.name} cargado con {len(df)} filas.")
        except Exception as e:
            st.error(f"Error: {e}")


# 📋 Ver Datos
elif menu == "Ver Datos":
    st.header("📋 Datos almacenados")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM excel_data LIMIT 200"))
            data = [dict(row) for row in result.mappings()]

        if data:
            df = pd.DataFrame(data)
            st.dataframe(df)

            # Descargar en CSV
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Descargar datos en CSV", csv, "datos.csv", "text/csv")
        else:
            st.info("No hay datos en la tabla.")
    except Exception as e:
        st.error(f"Error: {e}")


# 📈 KPIs y Dashboard estilo BI
elif menu == "KPIs":
    st.header("📈 Indicadores Clave (KPIs)")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM excel_data"))
            data = [dict(row) for row in result.mappings()]

        if data:
            df = pd.DataFrame(data)

            total_registros = len(df)

            # Tarjetas principales
            col1, col2, col3 = st.columns(3)
            col1.metric("📊 Total registros", total_registros)
            if not df.select_dtypes(include="number").empty:
                col2.metric("🔹 Promedio global", round(df.select_dtypes(include="number").mean().mean(), 2))
                col3.metric("📈 Máximo global", round(df.select_dtypes(include="number").max().max(), 2))

            # Gráficas de columnas numéricas
            if not df.select_dtypes(include="number").empty:
                st.subheader("📊 Gráficas interactivas")
                numeric_cols = df.select_dtypes(include="number").columns

                # Gráfica de barras
                df_sum = df[numeric_cols].sum().reset_index()
                df_sum.columns = ["Columna", "Suma"]
                fig_bar = px.bar(df_sum, x="Columna", y="Suma", title="Suma por columna", color="Columna")
                st.plotly_chart(fig_bar, use_container_width=True)

                # Gráfica de líneas
                df_avg = df[numeric_cols].mean().reset_index()
                df_avg.columns = ["Columna", "Promedio"]
                fig_line = px.line(df_avg, x="Columna", y="Promedio", title="Promedio por columna", markers=True)
                st.plotly_chart(fig_line, use_container_width=True)

            # Gráfica de pastel para categóricas
            cat_cols = df.select_dtypes(include="object").columns
            if len(cat_cols) > 0:
                st.subheader("🥧 Distribución categórica")
                col_select = st.selectbox("Selecciona columna categórica", cat_cols)
                fig_pie = px.pie(df, names=col_select, title=f"Distribución de {col_select}")
                st.plotly_chart(fig_pie, use_container_width=True)

        else:
            st.info("No hay datos para calcular KPIs.")
    except Exception as e:
        st.error(f"Error: {e}")


# 🚚 Predicción de Rutas simuladas
elif menu == "Predicción de Rutas":
    st.header("🚚 Predicción de Rutas en El Salvador (Simulación)")

    # Coordenadas aproximadas de zonas principales
    zonas = {
        "San Salvador": [13.6929, -89.2182],
        "Santa Ana": [13.9942, -89.5598],
        "San Miguel": [13.4833, -88.1833],
        "La Libertad": [13.4886, -89.3222]
    }

    # Selección de origen y destino
    origen = st.selectbox("Selecciona zona de origen", list(zonas.keys()))
    destino = st.selectbox("Selecciona zona de destino", list(zonas.keys()))

    if origen != destino:
        # Crear mapa
        mapa = folium.Map(location=[13.7, -89.2], zoom_start=8)

        # Marcar puntos
        folium.Marker(zonas[origen], popup=f"Origen: {origen}", icon=folium.Icon(color="green")).add_to(mapa)
        folium.Marker(zonas[destino], popup=f"Destino: {destino}", icon=folium.Icon(color="red")).add_to(mapa)

        # Ruta simulada (con ruido aleatorio)
        lat1, lon1 = zonas[origen]
        lat2, lon2 = zonas[destino]
        puntos = [
            [lat1 + random.uniform(-0.05, 0.05), lon1 + random.uniform(-0.05, 0.05)],
            [(lat1+lat2)/2 + random.uniform(-0.05, 0.05), (lon1+lon2)/2 + random.uniform(-0.05, 0.05)],
            [lat2 + random.uniform(-0.05, 0.05), lon2 + random.uniform(-0.05, 0.05)]
        ]
        folium.PolyLine(puntos, color="blue", weight=4, opacity=0.8).add_to(mapa)

        # Mostrar mapa
        st_folium(mapa, width=700, height=500)

        # Predicción de tiempo ficticio
        tiempo_estimado = random.randint(30, 120)  # en minutos
        trafico = random.choice(["🚦 Bajo", "🚦 Medio", "🚦 Alto"])
        clima = random.choice(["☀️ Soleado", "🌧️ Lluvioso", "🌥️ Nublado"])

        st.success(f"⏱️ Tiempo estimado: {tiempo_estimado} minutos")
        st.info(f"Condiciones: {trafico} | {clima}")

    else:
        st.warning("El origen y destino no pueden ser iguales.")


# 🗑️ Borrar Datos
elif menu == "Borrar Datos":
    st.header("🗑️ Eliminar registros")
    st.warning("⚠️ Esto borrará todos los datos de la tabla `excel_data`.")

    if st.button("Borrar TODO"):
        try:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM excel_data"))
            st.success("✅ Todos los datos fueron eliminados.")
        except Exception as e:
            st.error(f"Error: {e}")
