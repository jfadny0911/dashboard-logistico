# -----------------------------
# Asignación
# -----------------------------
elif selected == "Asignación":
    st.header("🚚 Asignación")
    df_ent = load_table('entregas')
    if df_ent.empty:
        st.info("No hay entregas.")
    else:
        # Filtramos pedidos PENDIENTES o ASIGNADOS (para reasignar)
        pendientes = df_ent[df_ent.get('estado','').astype(str).str.lower().isin(['pendiente', 'asignado', 'pendiente_asignado'])]
        st.subheader("Pedidos Pendientes de Asignar/Iniciar")
        
        cols_show = [c for c in ['orden_gestion','nombre','municipio','departamento', 'prioridad', 'repartidor', 'estado'] if c in pendientes.columns]
        st.dataframe(pendientes[cols_show].head(200))
        
        # CAMBIO SOLICITADO: Digitar el ID de la orden
        default_orders = pendientes['orden_gestion'].tolist() if not pendientes.empty else []
        
        # Usamos un text_input para digitar el ID
        sel_ord_input = st.text_input("Digita el ID de la Orden a Asignar", value=default_orders[0] if default_orders else "")
        sel_rep = st.selectbox("Repartidor", options=REPARTIDORES)
        
        # Botón Asignar (Activa la ruta)
        if st.button("Asignar e Iniciar Ruta"):
            # 1. Validación de existencia y estado
            if not sel_ord_input:
                st.error("Por favor, digita un ID de orden válido.")
                st.stop()
                
            orden_existe = sel_ord_input in pendientes['orden_gestion'].values
            
            if not orden_existe:
                st.error(f"❌ La orden {sel_ord_input} no existe o no está en estado Pendiente/Asignado.")
                st.stop()

            try:
                # 2. Asignar repartidor, cambiar estado a 'Activa' y poner hora de inicio (datetime.now())
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                with engine.connect() as conn:
                    # Usamos parameterized query para evitar SQL injection y errores de tipo
                    conn.execute(
                        text("UPDATE entregas SET repartidor=:rep, estado='Activa', inicio_ruta=:time WHERE orden_gestion=:ord"),
                        {"rep": sel_rep, "time": current_time, "ord": sel_ord_input}
                    )
                    conn.commit()
                st.success(f"Ruta para orden {sel_ord_input} asignada a {sel_rep} e INICIADA.")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Error asignando e iniciando ruta: {e}")
