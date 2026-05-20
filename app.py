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

# Estilos profesionales mantenidos
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

def obtener_stock_full():
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

def descargar_planilla_inventario(df):
    output = io.BytesIO()
    df_planilla = df.copy()
    df_planilla["CONTEO FÍSICO"] = ""
    df_planilla["DIFERENCIA"] = ""
    df_planilla["OBSERVACIONES"] = ""
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_planilla.to_excel(writer, index=False, sheet_name='Toma_Stock')
    return output.getvalue()

# --- MEJORA SOLICITADA: AGRUPAR POR DEPÓSITO EN COLUMNAS ---
def descargar_excel_agrupado_depositos(df):
    output = io.BytesIO()
    
    # Creamos una tabla pivote: Filas fijas (Producto, Código, Lote) 
    # y los depósitos se convierten en columnas
    df_pivot = df.pivot_table(
        index=['Producto', 'Código', 'Unidad', 'Lote'], 
        columns='Deposito', 
        values='Stock Actual',
        aggfunc='sum'
    ).fillna(0) # Rellenar con 0 donde no hay stock en ese depósito
    
    # Agregamos una columna de Total General para facilitar el control
    df_pivot['TOTAL GENERAL'] = df_pivot.sum(axis=1)
    
    # Resetear el index para que Producto, Código, etc. vuelvan a ser columnas normales
    df_pivot = df_pivot.reset_index()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_pivot.to_excel(writer, index=False, sheet_name='Stock_Comparativo')
    return output.getvalue()

inicializar_db()

# --- 3. INTERFAZ ---
st.title("🧪 Control de Depósito Inteligente")

if 'qr_detectado' not in st.session_state:
    st.session_state.qr_detectado = "Todos"

tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚡ Panel de Control", "📋 Planilla Toma Stock", "📜 Historial", "📊 Análisis", "⚙️ Configuración"])

with tab1:
    stock_df = obtener_stock_full()
    
    if stock_df.empty:
        st.warning("⚠️ No hay datos cargados. Por favor, subí el archivo en la pestaña 'Configuración'.")
    else:
        # KPIs
        df_kpi = stock_df.copy()
        c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
        with c_kpi1: st.metric("Total Productos", len(df_kpi["Producto"].unique()))
        with c_kpi2: st.metric("Volumen Total", f"{df_kpi['Stock Actual'].sum():,.0f}")
        with c_kpi3:
            criticos_n = len(df_kpi[df_kpi["Stock Actual"] < 20])
            st.metric("Alertas Críticas", criticos_n, delta=-criticos_n, delta_color="inverse")
        with c_kpi4: st.metric("Depósitos", df_kpi["Deposito"].nunique())

        st.markdown("### 📷 Identificar Producto")
        c_cam1, c_cam2 = st.columns([3, 1])
        with c_cam1:
            foto = st.file_uploader("Sacá foto al QR", type=["jpg", "png", "jpeg"], key="uploader_qr")
        with c_cam2:
            st.write("") 
            btn_procesar = st.button("🔍 ESCANEAR QR")
            if st.button("🔄 Limpiar Búsqueda"):
                st.session_state.qr_detectado = "Todos"
                st.rerun()

        if foto:
            with st.spinner("Procesando imagen..."):
                codigo_leido = decodificar_qr_reforzado(foto)
                if codigo_leido:
                    match = stock_df[(stock_df["Código"].astype(str) == str(codigo_leido)) | (stock_df["Producto"].str.contains(codigo_leido, case=False))]
                    if not match.empty:
                        res_prod = match["Producto"].iloc[0]
                        if st.session_state.qr_detectado != res_prod:
                            st.session_state.qr_detectado = res_prod
                            st.rerun()

        st.markdown("---")
        st.subheader("🔍 Filtros Dinámicos")
        
        search_query = st.text_input("⌨️ Buscar por nombre o código", placeholder="Empiece a escribir para filtrar...", key="search_input")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            lista_productos = ["Todos"] + sorted(stock_df["Producto"].unique().tolist())
            idx_inicio = lista_productos.index(st.session_state.qr_detectado) if st.session_state.qr_detectado in lista_productos else 0
            f_prod = st.selectbox("Producto", lista_productos, index=idx_inicio, key="prod_select")
            st.session_state.qr_detectado = f_prod
        
        with c2: 
            lista_lotes = ["Todos"] + sorted(stock_df["Lote"].unique().tolist())
            f_lote = st.selectbox("Filtrar por Lote", lista_lotes)
            
        with c3: 
            lista_depos = ["Todos"] + sorted(stock_df["Deposito"].unique().tolist())
            f_depo = st.selectbox("Filtrar por Depósito", lista_depos)
            
        with c4: 
            st.write("Ver:")
            hide_neg = st.toggle("Solo con stock", value=True)
            filter_reponer = st.toggle("🚨 Reponer (<20)", value=False)

        # Aplicación de filtros
        df_f = stock_df.copy()
        
        if search_query:
            df_f = df_f[df_f["Producto"].str.contains(search_query, case=False) | df_f["Código"].astype(str).str.contains(search_query, case=False)]
        if st.session_state.qr_detectado != "Todos" and not search_query:
            df_f = df_f[df_f["Producto"] == st.session_state.qr_detectado]
        if f_lote != "Todos": 
            df_f = df_f[df_f["Lote"] == f_lote]
        if f_depo != "Todos": 
            df_f = df_f[df_f["Deposito"] == f_depo]
        if hide_neg: 
            df_f = df_f[df_f["Stock Actual"] > 0]
        if filter_reponer:
            df_f = df_f[df_f["Stock Actual"] < 20]

        if not df_f.empty:
            st.write(f"Mostrando **{len(df_f)}** registros encontrados.")
            
            # BOTÓN DE EXCEL CON LA MEJORA DE AGRUPACIÓN POR DEPÓSITO
            excel_bin = descargar_excel_agrupado_depositos(df_f)
            st.download_button(
                label="📥 Descargar Excel Comparativo (Depósitos en columnas)", 
                data=excel_bin, 
                file_name=f'stock_comparativo_{datetime.now().strftime("%d_%m")}.xlsx', 
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items): 
                with cols_grid[i % 4]:
                    stk_val = item['Stock Actual']
                    if stk_val <= 0:
                        clase, txt_status, bg_status = "card-warning", "SIN STOCK", "bg-warning"
                    elif stk_val < 20:
                        clase, txt_status, bg_status = "card-low", "REPONER", "bg-low"
                    else:
                        clase, txt_status, bg_status = "card-normal", "ÓPTIMO", "bg-normal"

                    msg_wa = urllib.parse.quote(f"Hola! Reporto stock de {item['Producto']}. Depósito: {item['Deposito']}. Lote: {item['Lote']}. Cantidad: {stk_val} {item['Unidad']}.")
                    link_wa = f"https://wa.me/5493406123456?text={msg_wa}"

                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="status-badge {bg_status}">{txt_status}</div>
                            <div class="stock-title">{item['Producto']}</div>
                            <span class="stock-value">{stk_val:,.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info">
                                <b>🆔 Cód:</b> {item['Código']}<br>
                                <b>📍 Dep:</b> <span class="label-blue">{item['Deposito']}</span><br>
                                <b>🏷️ Lote:</b> {item['Lote']}
                            </div>
                            <a href="{link_wa}" target="_blank" class="wa-btn">💬 Reportar Stock</a>
                        </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No se encontraron productos con los filtros seleccionados.")

with tab2:
    st.subheader("📋 Planilla para Inventario Físico")
    if not stock_df.empty:
        depo_list = sorted(stock_df["Deposito"].unique().tolist())
        sel_depo = st.selectbox("Seleccionar Depósito para Auditar", ["Todos"] + depo_list)
        df_audit = stock_df.copy()
        if sel_depo != "Todos":
            df_audit = df_audit[df_audit["Deposito"] == sel_depo]
        st.dataframe(df_audit, use_container_width=True, hide_index=True)
        excel_audit = descargar_planilla_inventario(df_audit)
        st.download_button(label=f"📥 Descargar Planilla de Conteo", data=excel_audit, file_name=f'planilla_conteo_{datetime.now().strftime("%d_%m")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

with tab3:
    if not stock_df.empty:
        st.dataframe(stock_df, use_container_width=True, hide_index=True)

with tab4:
    if not stock_df.empty:
        df_pareto = stock_df.groupby("Producto")["Stock Actual"].sum().sort_values(ascending=False).head(10).reset_index()
        fig_pareto = px.bar(df_pareto, x='Stock Actual', y='Producto', orientation='h', color='Stock Actual', color_continuous_scale='Greens')
        st.plotly_chart(fig_pareto, use_container_width=True)

with tab5:
    st.subheader("⚙️ Importación MacroGest")
    archivo = st.file_uploader("Subí el archivo 'export 3.xls'", type=["xlsx", "csv"])
    if archivo and st.button("🚀 PROCESAR E IMPORTAR"):
        with st.spinner('Sincronizando...'):
            try:
                df_import = pd.read_excel(archivo) if archivo.name.endswith('.xlsx') else pd.read_csv(archivo, encoding='latin1')
                df_import.columns = [str(c).strip() for c in df_import.columns]
                if 'Artículo' in df_import.columns and 'Descripción' in df_import.columns:
                    borrar_datos_totales()
                    conn = conectar_db(); cursor = conn.cursor()
                    cols_depositos = [c for c in df_import.columns if c not in ['Artículo', 'Descripción'] and "Unnamed" not in c]
                    for _, row in df_import.iterrows():
                        nom = str(row['Descripción']).strip()
                        if pd.isna(nom) or nom == "" or nom == "nan": continue
                        cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad, codigo) VALUES (?,?,?)", (nom, "UNID", str(row['Artículo'])))
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (nom,))
                        id_p = cursor.fetchone()[0]
                        for depo in cols_depositos:
                            try:
                                val = float(str(row[depo]).replace('.', '').replace(',', '.'))
                                if val != 0:
                                    cursor.execute("INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito) VALUES (?,?,?,?,?,?)",
                                                   (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, val, "S/L", depo))
                            except: continue
                    conn.commit(); conn.close()
                    st.success("✅ Importación exitosa.")
                    st.rerun()
            except Exception as e: st.error(f"❌ Error: {e}")

st.markdown("---")
st.caption("Creado por Ignacio Diaz")
