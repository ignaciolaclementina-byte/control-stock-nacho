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
        background-color: white; padding: 18px; border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 12px;
        border: 1px solid #e1e4e8; position: relative;
    }
    .card-normal { border-left: 8px solid #28a745; }
    .card-low { border-left: 8px solid #ffc107; }
    .card-warning { border-left: 8px solid #dc3545; }
    .stock-title { font-size: 0.95rem; color: #1a1c21; font-weight: 700; margin-bottom: 8px; line-height: 1.2; min-height: 2.4em; }
    .stock-value { font-size: 1.5rem; color: #007bff; font-weight: 800; display: block; }
    .stock-unit { font-size: 0.8rem; color: #6c757d; font-weight: 400; }
    .stock-info { margin-top: 10px; padding-top: 8px; border-top: 1px solid #f0f2f6; font-size: 0.8rem; color: #495057; }
    .label-blue { background-color: #e7f3ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .neg-badge { display: inline-block; background-color: #dc3545; color: white; font-size: 0.65rem; padding: 1px 6px; border-radius: 8px; font-weight: bold; margin-left: 4px; vertical-align: middle; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. BASE DE DATOS ---
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
            origen TEXT,
            FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entregas (
            id_entrega INTEGER PRIMARY KEY AUTOINCREMENT,
            hoja TEXT,
            rto TEXT,
            dia_recibido TEXT,
            cliente TEXT,
            deposito TEXT,
            cantidad_comprada REAL,
            producto TEXT,
            lote TEXT,
            cant_entregada REAL,
            pendiente REAL,
            estado TEXT,
            vendedor TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    # NUEVA TABLA: Historial de Conteo Físico por QR
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario_fisico (
            id_inventario INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_conteo TEXT NOT NULL,
            codigo TEXT NOT NULL,
            producto TEXT NOT NULL,
            deposito TEXT NOT NULL,
            stock_sistema REAL NOT NULL,
            conteo_fisico REAL NOT NULL,
            diferencia REAL NOT NULL,
            observaciones TEXT
        )
    """)
    
    migraciones = [
        "ALTER TABLE productos ADD COLUMN codigo TEXT",
        "ALTER TABLE movimientos ADD COLUMN origen TEXT",
        "ALTER TABLE entregas ADD COLUMN hoja TEXT",
        "ALTER TABLE entregas ADD COLUMN lote TEXT",
        "ALTER TABLE entregas ADD COLUMN deposito TEXT",
    ]
    for m in migraciones:
        try: cursor.execute(m)
        except: pass
    conn.commit()
    conn.close()

def borrar_datos_totales():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM movimientos")
    cursor.execute("DELETE FROM productos")
    cursor.execute("DELETE FROM metadata")
    cursor.execute("DELETE FROM inventario_fisico")
    conn.commit()
    conn.close()

def borrar_solo_importacion():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM movimientos WHERE origen = 'excel' OR origen IS NULL")
    cursor.execute("DELETE FROM productos WHERE id_producto NOT IN (SELECT DISTINCT id_producto FROM movimientos)")
    conn.commit()
    conn.close()

def guardar_metadata(clave, valor):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO metadata (clave, valor) VALUES (?,?)", (clave, valor))
    conn.commit()
    conn.close()

def obtener_metadata(clave):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM metadata WHERE clave=?", (clave,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def obtener_stock_con_lote():
    conn = conectar_db()
    query = """
        SELECT p.nombre as Producto, p.codigo as Código, p.unidad as Unidad,
               m.lote as Lote, m.deposito as Deposito,
               m.tipo_movimiento, m.cantidad
        FROM movimientos m JOIN productos p ON m.id_producto = p.id_producto
    """
    try: df = pd.read_sql_query(query, conn)
    except: df = pd.DataFrame()
    conn.close()
    if df.empty: return pd.DataFrame()
    df["neta"] = df.apply(lambda r: r["cantidad"] if r["tipo_movimiento"] == "Entrada" else -r["cantidad"], axis=1)
    res = df.groupby(["Producto","Código","Unidad","Lote","Deposito"])["neta"].sum().reset_index()
    return res.rename(columns={"neta": "Stock Actual"})

def obtener_stock_full():
    df = obtener_stock_con_lote()
    if df.empty: return df
    return df.groupby(["Producto","Código","Unidad","Deposito"])["Stock Actual"].sum().reset_index()

def obtener_historial_movimientos():
    conn = conectar_db()
    query = """
        SELECT m.id_movimiento as ID, m.fecha_hora as Fecha, m.tipo_movimiento as Tipo,
               p.nombre as Producto, p.codigo as Código, m.cantidad as Cantidad,
               p.unidad as Unidad, m.lote as Lote, m.depósito as Depósito,
               m.referencia as Referencia, COALESCE(m.origen,'excel') as Origen
        FROM movimientos m JOIN productos p ON m.id_producto = p.id_producto
        ORDER BY m.id_movimiento DESC
    """
    try: df = pd.read_sql_query(query, conn)
    except: df = pd.DataFrame()
    conn.close()
    return df

def obtener_entregas(hoja=None):
    conn = conectar_db()
    try:
        if hoja and hoja != "Todas":
            df = pd.read_sql_query("SELECT * FROM entregas WHERE hoja=? ORDER BY dia_recibido DESC", conn, params=(hoja,))
        else:
            df = pd.read_sql_query("SELECT * FROM entregas ORDER BY hoja, dia_recibido DESC", conn)
    except: df = pd.DataFrame()
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
    df_pivot = df.pivot_table(index=['Producto','Código','Unidad'], columns='Deposito',
                               values='Stock Actual', aggfunc='sum').fillna(0)
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

def safe_float(val, default=0.0):
    try:
        if val is None or (hasattr(val, '__class__') and val.__class__.__name__ == 'NaTType'):
            return default
        f = float(val)
        return f if not (f != f) else default
    except:
        return default

def safe_str(val, default=""):
    try:
        if val is None or (hasattr(val, '__class__') and val.__class__.__name__ == 'NaTType'):
            return default
        s = str(val).strip()
        return "" if s.lower() in ("nan","nat","none","") else s
    except:
        return default

def safe_fecha(val):
    try:
        if pd.isna(val):
            return ""
        return pd.Timestamp(val).strftime("%d/%m/%Y")
    except:
        return ""

def parsear_entregas_excel(archivo):
    registros = []
    # --- Hoja 1: LA CLEMENTINA S.A ---
    try:
        df = pd.read_excel(archivo, sheet_name='LA CLEMENTINA S.A', header=1)
        df.columns = [str(c).strip() for c in df.columns]
        df["DIA RECIBIDO"] = pd.to_datetime(df["DIA RECIBIDO"], errors="coerce")
        for _, r in df.iterrows():
            prod = safe_str(r.get("PRODUCTO",""))
            if not prod: continue
            pend = safe_float(r.get("PENDIENTE", 0))
            if "Unnamed: 7" in df.columns:
                pend += safe_float(r.get("Unnamed: 7", 0))
            registros.append({
                "hoja": "LA CLEMENTINA S.A",
                "rto": safe_str(r.get("RTO MONSANTO","")),
                "dia_recibido": safe_fecha(r["DIA RECIBIDO"]),
                "cliente": safe_str(r.get("CLIENTE","")),
                "deposito": "LA CLEMENTINA",
                "cantidad_comprada": safe_float(r.get("CANTIDAD COMPRADA", 0)),
                "producto": prod,
                "lote": "",
                "cant_entregada": safe_float(r.get("CANT. ENTREGADA", 0)),
                "pendiente": pend,
                "estado": safe_str(r.get("ESTADO","")),
                "vendedor": safe_str(r.get("VENDEDOR","")),
            })
    except Exception as e:
        st.warning(f"Hoja 'LA CLEMENTINA S.A': {e}")

    # --- Hoja 2: LCAGRO S.A ---
    try:
        df = pd.read_excel(archivo, sheet_name='LCAGRO S.A', header=1)
        df.columns = [str(c).strip() for c in df.columns]
        df["DIA RECIBIDO"] = pd.to_datetime(df["DIA RECIBIDO"], errors="coerce")
        for _, r in df.iterrows():
            prod = safe_str(r.get("PRODUCTO",""))
            if not prod: continue
            registros.append({
                "hoja": "LCAGRO S.A",
                "rto": safe_str(r.get("RTO MONSANTO","")),
                "dia_recibido": safe_fecha(r["DIA RECIBIDO"]),
                "cliente": safe_str(r.get("CLIENTE","")),
                "deposito": "LCAGRO",
                "cantidad_comprada": safe_float(r.get("CANTIDAD COMPRADA", 0)),
                "producto": prod,
                "lote": "",
                "cant_entregada": safe_float(r.get("CANT. ENTREGADA", 0)),
                "pendiente": safe_float(r.get("PENDIENTE", 0)),
                "estado": safe_str(r.get("ESTADO","")),
                "vendedor": safe_str(r.get("VENDEDOR","")),
            })
    except Exception as e:
        st.warning(f"Hoja 'LCAGRO S.A': {e}")

    # --- Hoja 3: MERC CONSIGNADO BAYER DEP55 ---
    try:
        df = pd.read_excel(archivo, sheet_name='MERC CONSIGNADO BAYER DEP55', header=2)
        df.columns = [str(c).strip() for c in df.columns]
        df["DIA"] = pd.to_datetime(df["DIA"], errors="coerce")
        for _, r in df.iterrows():
            prod = safe_str(r.get("PRODUCTO",""))
            if not prod: continue
            registros.append({
                "hoja": "BAYER DEP55",
                "rto": "",
                "dia_recibido": safe_fecha(r["DIA"]),
                "cliente": safe_str(r.get("PRODUCTOR","")),
                "deposito": "DEP 55",
                "cantidad_comprada": safe_float(r.get("CANTIDAD", 0)),
                "producto": prod,
                "lote": safe_str(r.get("LOTE","")),
                "cant_entregada": safe_float(r.get("CANTIDAD ENT", 0)),
                "pendiente": safe_float(r.get("CANTIDAD PEND", 0)),
                "estado": safe_str(r.get("ESTADO","")),
                "vendedor": safe_str(r.get("VENDEDOR","")),
            })
    except Exception as e:
        st.warning(f"Hoja 'MERC CONSIGNADO BAYER DEP55': {e}")

    # --- Hoja 4: MERC. FACT DIRECTA BAYER 43-60 ---
    try:
        df = pd.read_excel(archivo, sheet_name='MERC. FACT DIRECTA BAYER 43-60', header=1)
        df.columns = [str(c).strip() for c in df.columns]
        df["DIA RECIBIDO"] = pd.to_datetime(df["DIA RECIBIDO"], errors="coerce")
        for _, r in df.iterrows():
            prod = safe_str(r.get("PRODUCTO",""))
            if not prod: continue
            dep_raw = safe_str(r.get("DEPOSITO",""))
            deposito = f"BAYER DEP {dep_raw}" if dep_raw else "BAYER DIRECTO"
            registros.append({
                "hoja": "BAYER DIRECTA",
                "rto": safe_str(r.get("RTO BAYER","")),
                "dia_recibido": safe_fecha(r["DIA RECIBIDO"]),
                "cliente": safe_str(r.get("CLIENTE","")),
                "deposito": deposito,
                "cantidad_comprada": safe_float(r.get("CANTIDAD COMPRADA", 0)),
                "producto": prod,
                "lote": safe_str(r.get("NRO LOTE","")),
                "cant_entregada": safe_float(r.get("CANT. ENTREGADA", 0)),
                "pendiente": safe_float(r.get("PENDIENTE", 0)),
                "estado": safe_str(r.get("ESTADO","")),
                "vendedor": safe_str(r.get("VENDEDOR","")),
            })
    except Exception as e:
        st.warning(f"Hoja 'MERC. FACT DIRECTA BAYER 43-60': {e}")

    return pd.DataFrame(registros) if registros else pd.DataFrame()

inicializar_db()

# --- 3. SESSION STATE ---
if 'qr_detectado' not in st.session_state:
    st.session_state.qr_detectado = "Todos"
if 'wa_numero' not in st.session_state:
    st.session_state.wa_numero = "5493406123456"
if 'umbral_alerta' not in st.session_state:
    st.session_state.umbral_alerta = 20
if 'mov_pendiente' not in st.session_state:
    st.session_state.mov_pendiente = None

# --- 4. INTERFAZ ---
st.title("🧪 Control de Depósito Inteligente")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⚡ Panel de Control",
    "📦 LC / LCAGRO",
    "🌿 Bayer DEP55",
    "🚚 Bayer Directa",
    "📋 Planilla Stock",
    "📜 Historial",
    "⚙️ Configuración"
])

# ===================== TAB 1: PANEL =====================
with tab1:
    stock_df = obtener_stock_full()
    if stock_df.empty:
        st.warning("⚠️ No hay datos cargados. Por favor, subí el archivo en la pestaña 'Configuración'.")
    else:
        U = st.session_state.umbral_alerta
        ultima_act = obtener_metadata("ultima_importacion")
        if ultima_act:
            st.caption(f"🕐 Última importación stock: **{ultima_act}**")
        ultima_ent = obtener_metadata("ultima_importacion_entregas")
        if ultima_ent:
            st.caption(f"📦 Última importación entregas: **{ultima_ent}**")

        df_kpi = stock_df.copy()
        negativos_n = len(df_kpi[df_kpi["Stock Actual"] < 0])
        c_kpi1, c_kpi2, c_kpi3, c_kpi4, c_kpi5 = st.columns(5)
        with c_kpi1: st.metric("Total Productos", len(df_kpi["Producto"].unique()))
        with c_kpi2: st.metric("Volumen Total", f"{df_kpi['Stock Actual'].sum():,.0f}")
        with c_kpi3:
            criticos_n = len(df_kpi[(df_kpi["Stock Actual"] >= 0) & (df_kpi["Stock Actual"] < U)])
            st.metric("Stock Bajo", criticos_n, delta=-criticos_n, delta_color="inverse")
        with c_kpi4:
            st.metric("Stock Negativo ⚠️", negativos_n, delta=-negativos_n, delta_color="inverse")
        with c_kpi5: st.metric("Depósitos", df_kpi["Deposito"].nunique())

        entregas_panel = obtener_entregas()
        if not entregas_panel.empty:
            pend_tot = entregas_panel[entregas_panel["pendiente"] > 0]["pendiente"].sum()
            if pend_tot > 0:
                st.info(f"📋 Pendiente total de entregas: **{pend_tot:,.0f}** unidades")

        st.markdown("---")
        st.subheader("🔍 Filtros Dinámicos")
        search_query = st.text_input("⌨️ Buscar por nombre o código", placeholder="Escriba aquí...", key="search_input")

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
                    st.warning("No se detectó ningún QR.")

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
            hide_neg = st.toggle("Solo con stock positivo", value=True)
            filter_reponer = st.toggle(f"🚨 Reponer (<{U})", value=False)
            show_neg_forced = st.toggle("⚠️ Mostrar negativos siempre", value=True)

        df_f = stock_df.copy()
        if search_query:
            df_f = df_f[df_f["Producto"].str.contains(search_query, case=False, na=False) |
                        df_f["Código"].astype(str).str.contains(search_query, case=False, na=False)]
        if st.session_state.qr_detectado != "Todos" and not search_query:
            df_f = df_f[df_f["Producto"] == st.session_state.qr_detectado]
        if f_depo != "Todos":
            df_f = df_f[df_f["Deposito"] == f_depo]
        if hide_neg:
            if show_neg_forced:
                df_f = df_f[(df_f["Stock Actual"] > 0) | (df_f["Stock Actual"] < 0)]
            else:
                df_f = df_f[df_f["Stock Actual"] > 0]
        if filter_reponer:
            df_f = df_f[df_f["Stock Actual"] < U]

        if not df_f.empty:
            excel_bin = descargar_excel_agrupado_sin_lote(df_f)
            st.download_button(label="📥 Descargar Comparativa Total", data=excel_bin, file_name='stock_agrupado.xlsx')
            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items):
                with cols_grid[i % 4]:
                    stk_val = item['Stock Actual']
                    clase = "card-warning" if stk_val <= 0 else ("card-low" if stk_val < U else "card-normal")
                    badge_neg = '<span class="neg-badge">NEGATIVO</span>' if stk_val < 0 else ""
                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{item['Producto']}{badge_neg}</div>
                            <span class="stock-value">{stk_val:,.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info"><b>🆔 Cód:</b> {item['Código']}<br><b>📍 Dep:</b> <span class="label-blue">{item['Deposito']}</span></div>
                        </div>
                    """, unsafe_allow_html=True)

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

            if st.session_state.mov_pendiente is None:
                if st.button("📋 Preparar movimiento"):
                    st.session_state.mov_pendiente = {
                        "producto": prod_sel, "tipo": tipo_mov,
                        "cantidad": cantidad_mov, "deposito": deposito_mov,
                        "lote": lote_mov, "referencia": ref_mov
                    }
                    st.rerun()
            else:
                p = st.session_state.mov_pendiente
                st.warning(f"""**¿Confirmar movimiento?**
- **{p['tipo']}** | **{p['producto']}** | {p['cantidad']:,.2f} | Dep: {p['deposito']}""")
                col_conf1, col_conf2 = st.columns(2)
                with col_conf1:
                    if st.button("✅ Confirmar y registrar", type="primary"):
                        conn = conectar_db()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre=?", (p["producto"],))
                        id_p = cursor.fetchone()
                        if id_p:
                            cursor.execute("""
                                INSERT INTO movimientos (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen)
                                VALUES (?,?,?,?,?,?,?,?)
                            """, (datetime.now().strftime("%d/%m/%Y %H:%M"), p["tipo"],
                                  id_p[0], p["cantidad"], p["lote"], p["referencia"], p["deposito"], "manual"))
                            conn.commit()
                            st.success("✅ Registrado.")
                        conn.close()
                        st.session_state.mov_pendiente = None
                        st.rerun()
                with col_conf2:
                    if st.button("❌ Cancelar"):
                        st.session_state.mov_pendiente = None
                        st.rerun()

# ===================== FUNCIÓN REUTILIZABLE PARA MOSTRAR ENTREGAS =====================
def mostrar_tab_entregas(hoja_nombre, color_estado, titulo):
    st.subheader(titulo)
    if hoja_nombre == "LA CLEMENTINA S.A":
        with st.expander("📂 Importar / Actualizar TODAS las hojas de entregas", expanded=obtener_entregas().empty):
            st.info("Subí el archivo completo de entregas Monsanto/Bayer. Se importan las 4 hojas automáticamente.")
            arch = st.file_uploader("Archivo de entregas (.xlsx)", type=["xlsx","xls"], key="uploader_entregas_global")

            col_op1, col_op2 = st.columns(2)
            with col_op1:
                descontar = st.toggle("🔄 Registrar como Salidas de stock", value=False, key="toggle_descontar")
            with col_op2:
                sf = obtener_stock_full()
                dep_opts = sf["Deposito"].unique().tolist() if not sf.empty else ["0"]
                dep_sal = st.selectbox("Depósito origen", dep_opts, key="dep_sal_global") if descontar else None

            if arch and st.button("🚀 IMPORTAR TODAS LAS HOJAS", type="primary"):
                try:
                    df_unif = parsear_entregas_excel(arch)
                    if df_unif.empty:
                        st.error("No se pudieron leer las hojas del archivo.")
                    else:
                        conn = conectar_db()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM entregas")
                        filas_ok = 0
                        filas_salida = 0
                        no_match = []

                        for _, r in df_unif.iterrows():
                            cursor.execute("""
                                INSERT INTO entregas (hoja,rto,dia_recibido,cliente,deposito,
                                cantidad_comprada,producto,lote,cant_entregada,pendiente,estado,vendedor)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (r["hoja"], r["rto"], r["dia_recibido"], r["cliente"], r["deposito"],
                                  r["cantidad_comprada"], r["producto"], r["lote"],
                                  r["cant_entregada"], r["pendiente"], r["estado"], r["vendedor"]))
                            filas_ok += 1

                            if descontar and r["cant_entregada"] > 0:
                                cursor.execute("SELECT id_producto FROM productos WHERE nombre=?", (r["producto"],))
                                match = cursor.fetchone()
                                if match:
                                    cursor.execute("""
                                        INSERT INTO movimientos (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen)
                                        VALUES (?,?,?,?,?,?,?,?)
                                    """, (r["dia_recibido"] or datetime.now().strftime("%d/%m/%Y"),
                                          "Salida", match[0], r["cant_entregada"],
                                          r["lote"] or "S/L", f"Entrega a {r['cliente']}", dep_sal, "entrega"))
                                    filas_salida += 1
                                else:
                                    if r["producto"] not in no_match:
                                        no_match.append(r["producto"])

                        conn.commit()
                        conn.close()
                        guardar_metadata("ultima_importacion_entregas", datetime.now().strftime("%d/%m/%Y %H:%M"))
                        msg = f"✅ {filas_ok} registros importados de las 4 hojas."
                        if descontar: msg += f" {filas_salida} salidas registradas."
                        st.success(msg)
                        if no_match:
                            st.warning(f"⚠️ Sin coincidencia en stock: {', '.join(no_match)}")
                        st.rerun()
                except Exception as ex:
                    st.error(f"❌ Error: {ex}")

    df_h = obtener_entregas(hoja_nombre)
    if df_h.empty:
        st.info("Sin datos. Importá el archivo de entregas en la pestaña 'LC / LCAGRO'.")
        return

    tc = df_h["cantidad_comprada"].sum()
    te = df_h["cant_entregada"].sum()
    tp = df_h["pendiente"].sum()
    pct = (te / tc * 100) if tc > 0 else 0
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: st.metric("Registros", len(df_h))
    with k2: st.metric("Clientes", df_h["cliente"].nunique())
    with k3: st.metric("Total comprado", f"{tc:,.0f}")
    with k4: st.metric("Entregado", f"{te:,.0f}", delta=f"{pct:.1f}%")
    with k5: st.metric("Pendiente", f"{tp:,.0f}", delta=f"-{tp:,.0f}" if tp > 0 else "0", delta_color="inverse")

    st.markdown("---")
    cf1, cf2, cf3, cf4 = st.columns(4)
    with cf1:
        estados_disp = ["Todos"] + sorted(df_h["estado"].dropna().unique().tolist())
        f_est = st.selectbox("Estado", estados_disp, key=f"fest_{hoja_nombre}")
    with cf2:
        prods_disp = ["Todos"] + sorted(df_h["producto"].dropna().unique().tolist())
        f_pr = st.selectbox("Producto", prods_disp, key=f"fprod_{hoja_nombre}")
    with cf3:
        vend_disp = ["Todos"] + sorted(df_h["vendedor"].dropna().replace("","S/V").unique().tolist())
        f_vd = st.selectbox("Vendedor", vend_disp, key=f"fvend_{hoja_nombre}")
    with cf4:
        f_cli = st.text_input("🔍 Cliente", placeholder="Buscar...", key=f"fcli_{hoja_nombre}")

    df_f2 = df_h.copy()
    if f_est != "Todos": df_f2 = df_f2[df_f2["estado"] == f_est]
    if f_pr != "Todos": df_f2 = df_f2[df_f2["producto"] == f_pr]
    if f_vd != "Todos": df_f2 = df_f2[df_f2["vendedor"].replace("","S/V") == f_vd]
    if f_cli: df_f2 = df_f2[df_f2["cliente"].str.contains(f_cli, case=False, na=False)]

    tiene_lote = df_f2["lote"].replace("","").notna() & (df_f2["lote"].replace("","") != "")
    mostrar_lote = tiene_lote.any()

    st.markdown(f"**{len(df_f2)} registros encontrados**")

    if not df_f2.empty:
        sub = df_f2.groupby("producto").agg(
            Comprado=("cantidad_comprada","sum"),
            Entregado=("cant_entregada","sum"),
            Pendiente=("pendiente","sum"),
            Clientes=("cliente","nunique")
        ).reset_index().rename(columns={"producto":"Producto"})
        sub["% Entregado"] = (sub["Entregado"] / sub["Comprado"].replace(0,1) * 100).round(1).astype(str) + "%"
        st.dataframe(sub, use_container_width=True, hide_index=True)
        st.markdown("---")

        cols_base = ["dia_recibido","cliente","producto","cantidad_comprada","cant_entregada","pendiente","estado","vendedor"]
        if mostrar_lote: cols_base.insert(3, "lote")
        if "deposito" in df_f2.columns and df_f2["deposito"].nunique() > 1:
            cols_base.insert(1, "deposito")
        if "rto" in df_f2.columns:
            cols_base.insert(0, "rto")
        cols_base = [c for c in cols_base if c in df_f2.columns]
        df_tabla = df_f2[cols_base].copy()
        nombres = {"dia_recibido":"Fecha","cliente":"Cliente","producto":"Producto",
                   "cantidad_comprada":"Comprado","cant_entregada":"Entregado",
                   "pendiente":"Pendiente","estado":"Estado","vendedor":"Vendedor",
                   "lote":"Lote","deposito":"Depósito","rto":"RTO"}
        df_tabla.rename(columns=nombres, inplace=True)
        st.dataframe(df_tabla, use_container_width=True, hide_index=True)

        output_e = io.BytesIO()
        with pd.ExcelWriter(output_e, engine='openpyxl') as writer:
            df_tabla.to_excel(writer, index=False, sheet_name='Entregas')
        st.download_button(f"📥 Exportar vista", data=output_e.getvalue(),
                           file_name=f"entregas_{hoja_nombre.replace(' ','_')}.xlsx",
                           key=f"dl_{hoja_nombre}")

with tab2: mostrar_tab_entregas("LA CLEMENTINA S.A", "#28a745", "📦 Entregas - La Clementina")
with tab3: mostrar_tab_entregas("BAYER DEP55", "#007bff", "🌿 Mercadería Consignada Bayer DEP 55")
with tab4: mostrar_tab_entregas("BAYER DIRECTA", "#fd7e14", "🚚 Facturación Directa Bayer 43-60")

# ===================== TAB 5: PLANILLA STOCK (CONTEO FÍSICO INTEGRADO) =====================
with tab5:
    st.subheader("📋 Toma de Inventario Físico y Auditoría")
    df_planilla_raw = obtener_stock_con_lote()
    
    if df_planilla_raw.empty:
        st.info("No hay stock disponible para auditar.")
    else:
        # --- NUEVA SECCIÓN: CONTEO FÍSICO POR QR ---
        st.markdown("### 📷 Captura Rápida de Stock (Escanear Código QR)")
        col_inv_cam, col_inv_manual = st.columns([1, 1])
        
        producto_encontrado = None
        codigo_encontrado = None
        deposito_encontrado = None
        stock_sistema_encontrado = 0.0
        
        with col_inv_cam:
            foto_inv = st.camera_input("Enfocá el QR del Producto en el Galpón", key="inv_camara_qr")
            if foto_inv:
                qr_leido = decodificar_qr_reforzado(foto_inv)
                if qr_leido:
                    # Buscamos en el DataFrame de stock si coincide con el código numérico o parte del nombre
                    match_inv = df_planilla_raw[
                        (df_planilla_raw["Código"].astype(str) == str(qr_leido)) | 
                        (df_planilla_raw["Producto"].str.contains(str(qr_leido), case=False, na=False))
                    ]
                    if not match_inv.empty:
                        producto_encontrado = match_inv.iloc[0]["Producto"]
                        codigo_encontrado = match_inv.iloc[0]["Código"]
                        deposito_encontrado = match_inv.iloc[0]["Deposito"]
                        stock_sistema_encontrado = match_inv.iloc[0]["Stock Actual"]
                        st.success(f"🎯 Producto Identificado: **{producto_encontrado}** (Cód: {codigo_encontrado})")
                    else:
                        st.error(f"❌ El QR ({qr_leido}) no coincide con ningún producto importado en la base de datos.")
                else:
                    st.warning("⚠️ No se pudo leer bien el QR. Intentá centrarlo mejor o con más luz.")
                    
        with col_inv_manual:
            if producto_encontrado:
                st.markdown(f"**📍 Depósito:** {deposito_encontrado}")
                st.markdown(f"**💻 Stock Teórico en Sistema:** `{stock_sistema_encontrado:,.2f}`")
                
                conteo_input = st.number_input("📥 Cantidad Física Real Encontrada", min_value=0.0, step=1.0, value=float(stock_sistema_encontrado), key="cant_fisica_qr")
                obs_input = st.text_input("📝 Notas / Observaciones", placeholder="Ej: Faltan 2 bidones rotos...", key="obs_fisica_qr")
                
                dif_calculada = conteo_input - stock_sistema_encontrado
                if dif_calculada == 0:
                    st.caption("✅ El conteo coincide perfectamente con el sistema.")
                elif dif_calculada > 0:
                    st.caption(f"🟢 Sobran `+{dif_calculada:,.2f}` unidades.")
                else:
                    st.caption(f"🔴 Faltan `{dif_calculada:,.2f}` unidades.")
                    
                if st.button("💾 Guardar Conteo en Auditoría", type="primary"):
                    conn = conectar_db()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO inventario_fisico (fecha_conteo, codigo, producto, deposito, stock_sistema, conteo_fisico, diferencia, observaciones)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (datetime.now().strftime("%d/%m/%Y %H:%M"), str(codigo_encontrado), producto_encontrado, deposito_encontrado, stock_sistema_encontrado, conteo_input, dif_calculada, obs_input))
                    conn.commit()
                    conn.close()
                    st.success("✅ Conteo guardado con éxito en el registro histórico.")
                    st.rerun()
            else:
                st.info("💡 Escaneá un código QR con la cámara de tu celular o computadora para cargar su stock físico al instante.")

        st.markdown("---")
        st.markdown("### 📋 Planilla General para Inventario en Papel / Excel")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            f_dep_p = st.selectbox("Filtrar Depósito para la planilla", ["Todos"] + sorted(df_planilla_raw["Deposito"].unique().tolist()), key="f_dep_planilla")
        with col_p2:
            st.write("")
            st.write("")
            df_descarga = df_planilla_raw.copy()
            if f_dep_p != "Todos":
                df_descarga = df_descarga[df_descarga["Deposito"] == f_dep_p]
            bin_planilla = descargar_planilla_inventario(df_descarga)
            st.download_button("📥 Descargar Planilla de Toma de Stock (.xlsx)", data=bin_planilla, file_name=f"Planilla_Toma_Stock_{f_dep_p}.xlsx")
            
        df_mostrar_p = df_planilla_raw.copy()
        if f_dep_p != "Todos":
            df_mostrar_p = df_mostrar_p[df_mostrar_p["Deposito"] == f_dep_p]
            
        st.dataframe(df_mostrar_p, use_container_width=True, hide_index=True)
        
        # --- NUEVA SECCIÓN: HISTÓRICO DE AUDITORÍAS REALIZADAS ---
        with st.expander("📊 Ver Historial de Conteos Físicos Guardados", expanded=False):
            conn = conectar_db()
            try:
                df_auditorias = pd.read_sql_query("SELECT fecha_conteo as [Fecha/Hora], codigo as [Cód], producto as [Producto], deposito as [Depósito], stock_sistema as [Stock Sistema], conteo_fisico as [Conteo Físico], diferencia as [Diferencia], observaciones as [Observaciones] FROM inventario_fisico ORDER BY id_inventario DESC", conn)
            except:
                df_auditorias = pd.DataFrame()
            conn.close()
            
            if not df_auditorias.empty:
                st.dataframe(df_auditorias, use_container_width=True, hide_index=True)
                
                output_auditoria = io.BytesIO()
                with pd.ExcelWriter(output_auditoria, engine='openpyxl') as writer:
                    df_auditorias.to_excel(writer, index=False, sheet_name='Conteos_Fisicos')
                st.download_button("📥 Exportar Historial de Diferencias (.xlsx)", data=output_auditoria.getvalue(), file_name="Historial_Ajustes_Inventario.xlsx")
            else:
                st.caption("Todavía no se registraron conteos físicos mediante código QR.")

# ===================== TAB 6: HISTORIAL =====================
with tab6:
    st.subheader("📜 Historial General de Movimientos")
    df_m = obtener_historial_movimientos()
    if df_m.empty:
        st.info("No hay movimientos registrados en el sistema.")
    else:
        ch1, ch2, ch3 = st.columns(3)
        with ch1:
            f_tm = st.selectbox("Tipo Movimiento", ["Todos", "Entrada", "Salida"])
        with ch2:
            f_or = st.selectbox("Origen", ["Todos", "excel", "manual", "entrega"])
        with ch3:
            f_txt = st.text_input("🔍 Buscar en Historial (Filtro rápido)", placeholder="Palabra clave...")

        df_mf = df_m.copy()
        if f_tm != "Todos": df_mf = df_mf[df_mf["Tipo"] == f_tm]
        if f_or != "Todos": df_mf = df_mf[df_mf["Origen"] == f_or]
        if f_txt:
            df_mf = df_mf[df_mf["Producto"].str.contains(f_txt, case=False, na=False) |
                          df_mf["Código"].astype(str).str.contains(f_txt, case=False, na=False) |
                          df_mf["Referencia"].str.contains(f_txt, case=False, na=False)]

        st.markdown(f"**{len(df_mf)} filas encontradas**")
        st.dataframe(df_mf, use_container_width=True, hide_index=True)

        if st.button("🗑️ Eliminar fila seleccionada"):
            st.info("Para eliminar un movimiento manual erróneo, por favor contactar al administrador del sistema con el ID del registro.")

# ===================== TAB 7: CONFIGURACIÓN =====================
with tab7:
    st.subheader("⚙️ Parámetros globales y carga de datos macro")
    
    with st.expander("📊 Umbral de Alertas y Enlaces"):
        st.session_state.umbral_alerta = st.number_input("Mínimo crítico para alerta de Stock Bajo:", min_value=1, value=st.session_state.umbral_alerta)
        st.session_state.wa_numero = st.text_input("Número de WhatsApp de destino:", value=st.session_state.wa_numero)

    with st.expander("📂 Importar Stock Base desde MacroGest / Excel", expanded=obtener_stock_full().empty):
        st.info("Cargá la planilla base de stock exportada de MacroGest para actualizar la lista base de productos.")
        archivo_stock = st.file_uploader("Planilla de Stock (.xlsx)", type=["xlsx","xls"], key="uploader_stock_base")
        
        if archivo_stock and st.button("🚀 PROCESAR E IMPORTAR STOCK BASE"):
            try:
                df_excel = pd.read_excel(archivo_stock)
                df_excel.columns = [str(c).strip() for c in df_excel.columns]
                
                col_prod = next((c for c in df_excel.columns if 'producto' in c.lower() or 'articulo' in c.lower() or 'nombre' in c.lower()), None)
                col_cod = next((c for c in df_excel.columns if 'cod' in c.lower() or 'id' in c.lower() or 'clv' in c.lower() or 'código' in c.lower()), None)
                col_cant = next((c for c in df_excel.columns if 'cant' in c.lower() or 'stock' in c.lower() or 'actual' in c.lower() or 'físico' in c.lower()), None)
                col_uni = next((c for c in df_excel.columns if 'uni' in c.lower() or 'medida' in c.lower()), None)
                col_dep = next((c for c in df_excel.columns if 'dep' in c.lower() or 'suc' in c.lower() or 'ubica' in c.lower()), None)
                col_lot = next((c for c in df_excel.columns if 'lote' in c.lower() or 'partida' in c.lower()), None)

                if not col_prod or not col_cant:
                    st.error(f"No se encontraron las columnas requeridas en el Excel. Detectadas: {list(df_excel.columns)}")
                else:
                    borrar_solo_importacion()
                    conn = conectar_db()
                    cursor = conn.cursor()
                    
                    p_cargados = 0
                    m_cargados = 0
                    
                    for _, fila in df_excel.iterrows():
                        nom = safe_str(fila[col_prod])
                        if not nom: continue
                        
                        cod = safe_str(fila[col_cod]) if col_cod else "S/C"
                        uni = safe_str(fila[col_uni]) if col_uni else "U"
                        cant = safe_float(fila[col_cant])
                        dep = safe_str(fila[col_dep]) if col_dep else "CENTRAL"
                        lot = safe_str(fila[col_lot]) if col_lot else "S/L"
                        
                        cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad, codigo) VALUES (?,?,?)", (nom, uni, cod))
                        cursor.execute("UPDATE productos SET codigo=?, unidad=? WHERE nombre=?", (cod, uni, nom))
                        
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre=?", (nom,))
                        id_p = cursor.fetchone()[0]
                        
                        cursor.execute("""
                            INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, referencia, deposito, origen)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, cant, lot, "Importación Inicial Excel", dep, "excel"))
                        
                        m_cargados += 1
                        
                    conn.commit()
                    conn.close()
                    guardar_metadata("ultima_importacion", datetime.now().strftime("%d/%m/%Y %H:%M"))
                    st.success(f"✨ ¡Importación Exitosa! Se procesaron {m_cargados} líneas de stock base de MacroGest.")
                    st.rerun()
            except Exception as ex:
                st.error(f"Ocurrió un error en la lectura del archivo: {ex}")

    with st.expander("🚨 Zona de peligro / Reseteo de Base de Datos"):
        st.warning("Estas acciones borrarán de forma irreversible los datos del almacenamiento interno de la app.")
        if st.button("🗑️ Borrar base de datos completa (Productos y Movimientos)"):
            borrar_datos_totales()
            st.success("Base de datos completamente vaciada.")
            st.rerun()
