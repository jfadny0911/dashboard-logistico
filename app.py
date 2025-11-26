Skip to content
Navigation Menu
jfadny0911
dashboard-logistico

Type / to search
Code
Issues
Pull requests
Actions
Projects
Wiki
Security
5
Insights
Settings
Files
Go to file
t
.devcontainer
ARCHIVOS_PARA_LA_DEFENSA.ipynb
README.md
app.py
dataset_entregas.csv
requirements.txt
dashboard-logistico
/
app.py
in
main

Edit

Preview
Indent mode

Spaces
Indent size

4
Line wrap mode

No wrap
Editing app.py file contents
816
817
818
819
820
821
822
823
824
825
826
827
828
829
830
831
832
833
834
835
836
837
838
839
840
841
842
843
844
845
846
847
848
849
850
851
852
853
854
855
856
857
858
859
860
861
862
863
864
import os
# -----------------------------
elif selected == "Agente IA":
    st.header("💬 Agente de Análisis IA (ChivoBot)")
    st.markdown("Pregunta sobre el desempeño logístico, repartidores, o zonas de entrega. El análisis se realiza usando el modelo **Gemini 2.5 Flash** sobre una muestra de tus datos.")
    
    df_ent = load_table('entregas')

    if df_ent.empty:
        st.warning("⚠️ No hay datos de entregas cargados para realizar análisis.")
        st.stop()

    # Data preparation for AI analysis
    df = df_ent.copy()
    
    # Area de entrada de la pregunta del usuario
    user_query = st.text_area("Escribe tu pregunta aquí (ej: '¿Cuál es el retraso promedio del repartidor Mario?')", height=100)
    
    
    
    if st.button("Obtener Respuesta IA"):
        if user_query:
            with st.spinner("Conectando con Gemini y analizando datos..."):
                
                model_key = model_options[selected_model]
                
                if model_key == 'gemini':
                    ai_response = run_ai_analysis_gemini(client, df, user_query)
                
                st.success("🤖 Respuesta de ChivoBot:")
                st.markdown(ai_response)
        else:
            st.error("Por favor, escribe una pregunta para el análisis.")

# -----------------------------
# Borrar datos
# -----------------------------
elif selected == "Borrar Datos":
    st.header("🗑️ Borrar datos")
    st.warning("Esto eliminará tablas: clientes, ubicaciones, entregas")
    if st.button("Borrar TODO"):
        try:
            clear_table('clientes'); clear_table('ubicaciones'); clear_table('entregas')
            st.success("Tablas borradas.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Error: {e}")

# EOF

Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
 
