import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import numpy as np
import cv2
import io
from PIL import Image
import urllib.parse

# --- 1. CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Gestión de Agroquímicos", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; height: 3em; }
    
    .stock-card {
        background-color: white; 
        padding: 18px; 
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); 
        margin-bottom: 12px;
        border: 1px solid #e1e4e8;
        position: relative;
    }
    .card-normal { border-left: 8px solid #28a745; } 
    .card-low { border-left: 8px solid #ffc107; }      
    .card-warning { border-left: 8px solid #dc3545; } 
    
    .stock-title { font-size: 0.95rem; color: #1a1c21; font-weight: 700; margin-bottom: 8px; line-height: 1.2; min-height: 2.4em; }
    .stock-value { font-size: 1.5rem; color: #007bff; font-weight: 800; display: block; }
    .stock-unit { font-size: 0.8rem; color: #6c757d; font-weight: 400; }
    
    .status-badge {
        position: absolute;
        top: 10px;
        right: 10px;
        font-size: 0.7rem;
        padding: 2px 8px;
        border-radius: 10px;
        color: white;
        font-weight: bold;
    }
    .bg-normal { background-color: #28a745; }
    .bg-low { background-color: #ffc107; color: #000; }
    .bg-warning { background-color: #dc3545; }

    .stock-info { 
        margin-top: 10px; 
        padding-top: 8px; 
        border-top: 1px solid #f0f2f6; 
        font-size: 0.8rem; 
        color: #495057; 
    }
    .label-blue { background-color: #e7f3ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    
    .wa-btn {
        display: inline-flex;
        align-items: center;
        background-color: #25D366;
        color: white !important;
        padding: 5px 10px;
        border-radius: 6px;
        text-decoration: none;
        font-size: 0.75rem;
        font-weight: bold;
        margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNCIONES DE BASE DE DATOS ---
def conectar_db():
    return sqlite3.connect("stock_agroquimicos.db")

def inicializar_db():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id_producto INTEGER PRIMARY KEY AUTOINCREMENT, 
            nombre TEXT NOT NULL UNIQUE, 
            unidad TEXT NOT NULL,
            codigo TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT, 
            fecha_hora TEXT NOT NULL, 
            tipo_movimiento TEXT NOT NULL, 
            id_producto INTEGER NOT NULL, 
            cantidad REAL NOT NULL, 
            lote TEXT, 
            referencia TEXT, 
            deposito TEXT,
            FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
        )
    """)
    try: cursor.execute("ALTER TABLE productos ADD COLUMN codigo TEXT")
    except: pass
    conn.commit()
    conn.close()

def borrar_datos_totales():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM movimientos")
    cursor.execute("DELETE FROM productos")
    conn.commit()
    conn.close()

def obtener_stock_con_lote():
    conn = conectar_db()
    query = """
        SELECT p.nombre as Producto, p.codigo as Código, p.unidad as Unidad, m.lote as Lote, m.deposito as Deposito, 
               m.tipo_movimiento, m.cantidad 
        FROM movimientos m 
        JOIN productos p ON m.id_producto = p.id_producto
    """
    try:
        df = pd.read_sql_query(query, conn)
    except:
        df = pd.DataFrame()
    conn.close()
    
    if df.empty: return pd.DataFrame()
    
    df["neta"] = df.apply(lambda r: r["cantidad"] if r["tipo_movimiento"] == "Entrada" else -r["cantidad"], axis=1)
    res = df.groupby(["Producto", "Código", "Unidad", "Lote", "Deposito"])["neta"].sum().reset_index()
    return res.rename(columns={"neta": "Stock Actual"})

def obtener_stock_full():
    df = obtener_stock_con_lote()
    if df.empty: return df
    res = df.groupby(["Producto", "Código", "Unidad", "Deposito"])["Stock Actual"].sum().reset_index()
    return res

# MEJORA 4: Historial real de movimientos individuales
def obtener_historial_movimientos():
    conn = conectar_db()
    query = """
        SELECT m.id_movimiento as ID, m.fecha_hora as Fecha, m.tipo_movimiento as Tipo,
               p.nombre as Producto, p.codigo as Código,
               m.cantidad as Cantidad, p.unidad as Unidad,
               m.lote as Lote, m.deposito as Depósito,
               m.referencia as Referencia
        FROM movimientos m
        JOIN productos p ON m.id_producto = p.id_producto
        ORDER BY m.id_movimiento DESC
    """
    try:
        df = pd.read_sql_query(query, conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

def decodificar_qr_reforzado(foto_input):
    if foto_input is not None:
        try:
            foto_input.seek(0)
            img_pil = Image.open(foto_input)
            img_np = np.array(img_pil.convert('RGB'))
            img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            detector = cv2.QRCodeDetector()
            valor, _, _ = detector.detectAndDecode(img_cv)
            if valor: return valor.strip()
            return None
        except: return None
    return None

def descargar_excel_agrupado_sin_lote(df):
    output = io.BytesIO()
    df_pivot = df.pivot_table(
        index=['Producto', 'Código', 'Unidad'], 
        columns='Deposito', 
        values='Stock Actual',
        aggfunc='sum'
    ).fillna(0)
    df_pivot['TOTAL GENERAL'] = df_pivot.sum(axis=1)
    df_pivot = df_pivot.reset_index()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_pivot.to_excel(writer, index=False, sheet_name='Comparativa_Stock_Total')
    return output.getvalue()

def descargar_planilla_inventario(df):
    output = io.BytesIO()
    df_planilla = df.copy()
    df_planilla["CONTEO FÍSICO"] = ""
    df_planilla["DIFERENCIA"] = ""
    df_planilla["OBSERVACIONES"] = ""
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_planilla.to_excel(writer, index=False, sheet_name='Toma_Stock')
    return output.getvalue()

inicializar_db()

# --- 3. SESSION STATE ---
if 'qr_detectado' not in st.session_state:
    st.session_state.qr_detectado = "Todos"

# MEJORA 1: Número WhatsApp configurable
if 'wa_numero' not in st.session_state:
    st.session_state.wa_numero = "5493406123456"

# MEJORA 2: Umbral de alerta configurable
if 'umbral_alerta' not in st.session_state:
    st.session_state.umbral_alerta = 20

# --- 4. INTERFAZ ---
st.title("🧪 Control de Depósito Inteligente")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚡ Panel de Control", "📋 Planilla Toma Stock", "📜 Historial", "📊 Análisis", "⚙️ Configuración"])

with tab1:
    stock_df = obtener_stock_full()
    
    if stock_df.empty:
        st.warning("⚠️ No hay datos cargados. Por favor, subí el archivo en la pestaña 'Configuración'.")
    else:
        U = st.session_state.umbral_alerta

        df_kpi = stock_df.copy()
        c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
        with c_kpi1: st.metric("Total Productos", len(df_kpi["Producto"].unique()))
        with c_kpi2: st.metric("Volumen Total", f"{df_kpi['Stock Actual'].sum():,.0f}")
        with c_kpi3:
            # MEJORA 2: umbral variable
            criticos_n = len(df_kpi[df_kpi["Stock Actual"] < U])
            st.metric("Alertas Críticas", criticos_n, delta=-criticos_n, delta_color="inverse")
        with c_kpi4: st.metric("Depósitos", df_kpi["Deposito"].nunique())

        st.markdown("---")
        st.subheader("🔍 Filtros Dinámicos")
        search_query = st.text_input("⌨️ Buscar por nombre o código", placeholder="Escriba aquí...", key="search_input")

        # MEJORA 3: Escaneo QR conectado a la UI
        with st.expander("📷 Escanear código QR"):
            col_cam, col_file = st.columns(2)
            with col_cam:
                foto_camara = st.camera_input("Cámara", key="qr_camara")
            with col_file:
                foto_archivo = st.file_uploader("O subí imagen", type=["png","jpg","jpeg"], key="qr_file")
            
            foto_qr = foto_camara or foto_archivo
            if foto_qr:
                resultado_qr = decodificar_qr_reforzado(foto_qr)
                if resultado_qr:
                    st.success(f"✅ QR detectado: **{resultado_qr}**")
                    match_qr = stock_df[
                        stock_df["Producto"].str.contains(resultado_qr, case=False, na=False) |
                        stock_df["Código"].astype(str).str.contains(resultado_qr, case=False, na=False)
                    ]
                    if not match_qr.empty:
                        st.session_state.qr_detectado = match_qr.iloc[0]["Producto"]
                        st.rerun()
                    else:
                        st.info(f"QR leído ({resultado_qr}) pero no coincide con ningún producto.")
                else:
                    st.warning("No se detectó ningún QR. Intentá con mejor iluminación o acercate más.")

        c1, c2, c3 = st.columns(3)
        with c1:
            lista_productos = ["Todos"] + sorted(stock_df["Producto"].unique().tolist())
            idx_inicio = lista_productos.index(st.session_state.qr_detectado) if st.session_state.qr_detectado in lista_productos else 0
            f_prod = st.selectbox("Producto", lista_productos, index=idx_inicio)
            st.session_state.qr_detectado = f_prod
        with c2: 
            lista_depos = ["Todos"] + sorted(stock_df["Deposito"].unique().tolist())
            f_depo = st.selectbox("Filtrar por Depósito", lista_depos)
        with c3: 
            st.write("Ver:")
            hide_neg = st.toggle("Solo con stock", value=True)
            # MEJORA 2: umbral en el label
            filter_reponer = st.toggle(f"🚨 Reponer (<{U})", value=False)

        df_f = stock_df.copy()
        if search_query:
            df_f = df_f[df_f["Producto"].str.contains(search_query, case=False, na=False) | df_f["Código"].astype(str).str.contains(search_query, case=False, na=False)]
        if st.session_state.qr_detectado != "Todos" and not search_query:
            df_f = df_f[df_f["Producto"] == st.session_state.qr_detectado]
        if f_depo != "Todos": df_f = df_f[df_f["Deposito"] == f_depo]
        if hide_neg: df_f = df_f[df_f["Stock Actual"] > 0]
        if filter_reponer: df_f = df_f[df_f["Stock Actual"] < U]

        if not df_f.empty:
            excel_bin = descargar_excel_agrupado_sin_lote(df_f)
            st.download_button(label="📥 Descargar Comparativa Total", data=excel_bin, file_name='stock_agrupado.xlsx')

            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items): 
                with cols_grid[i % 4]:
                    stk_val = item['Stock Actual']
                    # MEJORA 2: umbral variable en color de card
                    clase = "card-warning" if stk_val <= 0 else ("card-low" if stk_val < U else "card-normal")
                    msg_wa = urllib.parse.quote(f"Reporte: {item['Producto']}. Dep: {item['Deposito']}. Stock: {stk_val}")
                    # MEJORA 1: número dinámico
                    link_wa = f"https://wa.me/{st.session_state.wa_numero}?text={msg_wa}"
                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{item['Producto']}</div>
                            <span class="stock-value">{stk_val:,.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info"><b>🆔 Cód:</b> {item['Código']}<br><b>📍 Dep:</b> <span class="label-blue">{item['Deposito']}</span></div>
                            <a href="{link_wa}" target="_blank" class="wa-btn">💬 Reportar</a>
                        </div>
                    """, unsafe_allow_html=True)

        # MEJORA 5: Registro manual de movimientos
        st.markdown("---")
        with st.expander("➕ Registrar movimiento manual"):
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                prod_sel = st.selectbox("Producto", sorted(stock_df["Producto"].unique()), key="mov_prod")
                tipo_mov = st.radio("Tipo", ["Entrada", "Salida"], horizontal=True, key="mov_tipo")
            with c_m2:
                cantidad_mov = st.number_input("Cantidad", min_value=0.01, step=0.5, key="mov_cant")
                deposito_mov = st.selectbox("Depósito", sorted(stock_df["Deposito"].unique()), key="mov_dep")
            lote_mov = st.text_input("Lote (opcional)", value="S/L", key="mov_lote")
            ref_mov = st.text_input("Referencia (opcional)", value="", key="mov_ref")

            if st.button("✅ Registrar movimiento"):
                conn = conectar_db()
                cursor = conn.cursor()
                cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (prod_sel,))
                id_p = cursor.fetchone()
                if id_p:
                    cursor.execute("""
                        INSERT INTO movimientos 
                        (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, referencia, deposito)
                        VALUES (?,?,?,?,?,?,?)
                    """, (datetime.now().strftime("%d/%m/%Y %H:%M"), tipo_mov,
                          id_p[0], cantidad_mov, lote_mov, ref_mov, deposito_mov))
                    conn.commit()
                    st.success(f"✅ {tipo_mov} de {cantidad_mov:.2f} registrada para **{prod_sel}** en depósito **{deposito_mov}**.")
                    st.rerun()
                else:
                    st.error("No se encontró el producto en la base de datos.")
                conn.close()

with tab2:
    st.subheader("📋 Planilla para Inventario Físico (CON LOTES)")
    stock_lotes = obtener_stock_con_lote()
    if not stock_lotes.empty:
        depo_audit = st.selectbox("Depósito a Auditar", ["Todos"] + sorted(stock_lotes["Deposito"].unique().tolist()), key="audit_depo")
        df_audit = stock_lotes.copy()
        if depo_audit != "Todos": df_audit = df_audit[df_audit["Deposito"] == depo_audit]
        st.dataframe(df_audit, use_container_width=True, hide_index=True)
        st.download_button(label="📥 Descargar Planilla", data=descargar_planilla_inventario(df_audit), file_name='toma_stock_lotes.xlsx')
    else:
        st.info("Sin datos cargados.")

# MEJORA 4: Historial real de movimientos
with tab3:
    st.subheader("📜 Historial de Movimientos")
    hist_df = obtener_historial_movimientos()
    if not hist_df.empty:
        c_hf1, c_hf2, c_hf3 = st.columns(3)
        with c_hf1:
            f_tipo_h = st.selectbox("Tipo", ["Todos", "Entrada", "Salida"], key="h_tipo")
        with c_hf2:
            f_prod_h = st.selectbox("Producto", ["Todos"] + sorted(hist_df["Producto"].unique().tolist()), key="h_prod")
        with c_hf3:
            f_dep_h = st.selectbox("Depósito", ["Todos"] + sorted(hist_df["Depósito"].unique().tolist()), key="h_dep")

        df_h = hist_df.copy()
        if f_tipo_h != "Todos": df_h = df_h[df_h["Tipo"] == f_tipo_h]
        if f_prod_h != "Todos": df_h = df_h[df_h["Producto"] == f_prod_h]
        if f_dep_h != "Todos": df_h = df_h[df_h["Depósito"] == f_dep_h]

        c_hkpi1, c_hkpi2, c_hkpi3 = st.columns(3)
        with c_hkpi1: st.metric("Movimientos mostrados", len(df_h))
        with c_hkpi2: st.metric("Total entradas", len(df_h[df_h["Tipo"] == "Entrada"]))
        with c_hkpi3: st.metric("Total salidas", len(df_h[df_h["Tipo"] == "Salida"]))

        st.dataframe(df_h.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        output_hist = io.BytesIO()
        with pd.ExcelWriter(output_hist, engine='openpyxl') as writer:
            df_h.to_excel(writer, index=False, sheet_name='Historial')
        st.download_button("📥 Exportar historial filtrado", data=output_hist.getvalue(), file_name="historial_movimientos.xlsx")
    else:
        st.info("Sin movimientos registrados.")

with tab4:
    stock_df_an = obtener_stock_full()
    if not stock_df_an.empty:
        st.subheader("Top 10 productos por stock")
        df_pareto = stock_df_an.groupby("Producto")["Stock Actual"].sum().sort_values(ascending=False).head(10).reset_index()
        fig_pareto = px.bar(df_pareto, x='Stock Actual', y='Producto', orientation='h', color='Stock Actual', color_continuous_scale='Greens')
        st.plotly_chart(fig_pareto, use_container_width=True)

        # MEJORA 6: gráfico de distribución por depósito
        st.subheader("Distribución por depósito")
        df_dep = stock_df_an.groupby("Deposito")["Stock Actual"].sum().reset_index()
        fig_dep = px.pie(
            df_dep, names="Deposito", values="Stock Actual",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig_dep.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_dep, use_container_width=True)

        # Tabla resumen por depósito
        st.subheader("Resumen por depósito")
        df_resumen = stock_df_an.groupby("Deposito").agg(
            Productos=("Producto", "nunique"),
            Stock_Total=("Stock Actual", "sum"),
            Stock_Promedio=("Stock Actual", "mean")
        ).reset_index()
        df_resumen["Stock_Promedio"] = df_resumen["Stock_Promedio"].round(1)
        st.dataframe(df_resumen, use_container_width=True, hide_index=True)
    else:
        st.info("Sin datos para analizar.")

with tab5:
    st.subheader("⚙️ Configuración")

    # MEJORA 1: WhatsApp configurable
    st.markdown("#### 📱 WhatsApp para alertas")
    col_wa1, col_wa2 = st.columns([3,1])
    with col_wa1:
        nuevo_num = st.text_input(
            "Número WhatsApp (con código de país, sin +)",
            value=st.session_state.wa_numero,
            placeholder="Ej: 5493406123456"
        )
    with col_wa2:
        st.write("")
        st.write("")
        if st.button("💾 Guardar"):
            st.session_state.wa_numero = nuevo_num.strip()
            st.success("✅ Número guardado.")

    st.markdown("---")

    # MEJORA 2: Umbral de alerta configurable
    st.markdown("#### 🚨 Umbral de stock crítico")
    nuevo_umbral = st.slider(
        "Stock mínimo antes de alertar (unidades)",
        min_value=1, max_value=500,
        value=st.session_state.umbral_alerta,
        help="Los productos con stock menor a este valor aparecerán en amarillo o rojo."
    )
    if nuevo_umbral != st.session_state.umbral_alerta:
        st.session_state.umbral_alerta = nuevo_umbral
        st.rerun()

    st.markdown("---")

    # Importación original intacta
    st.markdown("#### 📂 Importar datos")
    archivo = st.file_uploader("Subí el archivo 'export 3.xlsx' o 'export 3.csv'", type=["xlsx", "csv", "xls"])
    
    if archivo and st.button("🚀 PROCESAR E IMPORTAR"):
        try:
            if archivo.name.endswith('.csv'):
                df_import = pd.read_csv(archivo, encoding='latin1')
            else:
                df_import = pd.read_excel(archivo)
                
            df_import.columns = [str(c).strip().lower() for c in df_import.columns]
            
            # Soporte para columna 'articulo' o 'descripcion_1'
            col_nombre = None
            if 'articulo' in df_import.columns:
                col_nombre = 'articulo'
            elif 'descripcion_1' in df_import.columns:
                col_nombre = 'descripcion_1'

            if col_nombre and 'stock_actual' in df_import.columns:
                borrar_datos_totales()
                conn = conectar_db()
                cursor = conn.cursor()
                
                for _, row in df_import.iterrows():
                    nom = str(row[col_nombre]).strip()
                    if pd.isna(row[col_nombre]) or nom == "" or nom.lower() == "nan": 
                        continue
                        
                    cod = str(row['codigo']).strip() if 'codigo' in df_import.columns else "S/C"
                    uni = str(row['unidad_medida']).strip() if 'unidad_medida' in df_import.columns else "UNID"
                    dep = str(row['deposito']).strip() if 'deposito' in df_import.columns else "0"
                    lot = str(row['lote']).strip() if 'lote' in df_import.columns and not pd.isna(row['lote']) and str(row['lote']).strip() != "" else "S/L"
                    
                    cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad, codigo) VALUES (?,?,?)", (nom, uni, cod))
                    cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (nom,))
                    id_p = cursor.fetchone()[0]
                    
                    val_raw = str(row['stock_actual']).strip()
                    if pd.isna(row['stock_actual']) or val_raw == "" or val_raw.lower() == "nan":
                        continue
                        
                    if '.' in val_raw and ',' in val_raw:
                        val_raw = val_raw.replace('.', '')
                    val_raw = val_raw.replace(',', '.')
                    
                    try:
                        v = float(val_raw)
                        cursor.execute("""
                            INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito) 
                            VALUES (?,?,?,?,?,?)
                        """, (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, v, lot, dep))
                    except:
                        continue
                        
                conn.commit()
                conn.close()
                st.success("✅ Importación por Lotes exitosa.")
                st.rerun()
            else:
                cols_enc = ', '.join(df_import.columns.tolist())
                st.error(f"❌ Columnas requeridas: ('articulo' o 'descripcion_1') y 'stock_actual'. Encontradas: {cols_enc}")
        except Exception as e: 
            st.error(f"❌ Error al procesar el archivo: {e}")

    st.markdown("---")
    st.markdown("#### 🗑️ Zona peligrosa")
    with st.expander("⚠️ Borrar todos los datos"):
        st.warning("Esta acción elimina todos los productos y movimientos de la base de datos. No se puede deshacer.")
        confirmar = st.text_input("Escribí CONFIRMAR para habilitar el botón", key="confirm_borrar")
        if confirmar == "CONFIRMAR":
            if st.button("🗑️ Borrar todo", type="primary"):
                borrar_datos_totales()
                st.success("Base de datos limpiada.")
                st.rerun()

st.markdown("---")
st.caption("Creado por Ignacio Diaz")
