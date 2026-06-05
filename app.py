import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import cv2
import io
import os
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
    .vence-badge { display: inline-block; background-color: #fd7e14; color: white; font-size: 0.65rem; padding: 1px 6px; border-radius: 8px; font-weight: bold; margin-left: 4px; vertical-align: middle; }
    .alerta-banner { background: #fff3cd; border: 1px solid #ffc107; border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
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
            fecha_vencimiento TEXT,
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS depositos_nombres (
            codigo TEXT PRIMARY KEY,
            nombre_legible TEXT NOT NULL
        )
    """)
    migraciones = [
        "ALTER TABLE productos ADD COLUMN codigo TEXT",
        "ALTER TABLE movimientos ADD COLUMN origen TEXT",
        "ALTER TABLE movimientos ADD COLUMN fecha_vencimiento TEXT",
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

def obtener_nombres_depositos():
    conn = conectar_db()
    try:
        df = pd.read_sql_query("SELECT codigo, nombre_legible FROM depositos_nombres", conn)
        return dict(zip(df["codigo"], df["nombre_legible"]))
    except:
        return {}
    finally:
        conn.close()

def nombre_deposito(codigo, mapa):
    return mapa.get(str(codigo), str(codigo))

def obtener_stock_con_lote():
    conn = conectar_db()
    query = """
        SELECT p.nombre as Producto, p.codigo as Código, p.unidad as Unidad,
               m.lote as Lote, m.deposito as Deposito,
               m.tipo_movimiento, m.cantidad,
               m.fecha_vencimiento as FechaVencimiento
        FROM movimientos m JOIN productos p ON m.id_producto = p.id_producto
    """
    try: df = pd.read_sql_query(query, conn)
    except: df = pd.DataFrame()
    conn.close()
    if df.empty: return pd.DataFrame()
    df["neta"] = df.apply(lambda r: r["cantidad"] if r["tipo_movimiento"] == "Entrada" else -r["cantidad"], axis=1)
    res = df.groupby(["Producto","Código","Unidad","Lote","Deposito","FechaVencimiento"])["neta"].sum().reset_index()
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
               p.unidad as Unidad, m.lote as Lote, m.deposito as Depósito,
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

def obtener_lotes_por_vencer(dias=60):
    conn = conectar_db()
    query = """
        SELECT p.nombre as Producto, m.lote as Lote, m.deposito as Deposito,
               m.fecha_vencimiento as Vencimiento, m.tipo_movimiento, m.cantidad
        FROM movimientos m JOIN productos p ON m.id_producto = p.id_producto
        WHERE m.fecha_vencimiento IS NOT NULL AND m.fecha_vencimiento != ''
    """
    try: df = pd.read_sql_query(query, conn)
    except: df = pd.DataFrame()
    conn.close()
    if df.empty: return pd.DataFrame()
    df["neta"] = df.apply(lambda r: r["cantidad"] if r["tipo_movimiento"]=="Entrada" else -r["cantidad"], axis=1)
    df = df.groupby(["Producto","Lote","Deposito","Vencimiento"])["neta"].sum().reset_index()
    df = df[df["neta"] > 0]
    hoy = date.today()
    resultado = []
    for _, r in df.iterrows():
        try:
            fv = datetime.strptime(r["Vencimiento"], "%Y-%m-%d").date()
            dias_restantes = (fv - hoy).days
            if dias_restantes <= dias:
                resultado.append({**r.to_dict(), "Dias Restantes": dias_restantes, "Vence": fv.strftime("%d/%m/%Y")})
        except:
            pass
    return pd.DataFrame(resultado) if resultado else pd.DataFrame()

def parsear_entregas_excel(archivo):
    registros = []
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
            registros.append({"hoja": "LA CLEMENTINA S.A","rto": safe_str(r.get("RTO MONSANTO","")),"dia_recibido": safe_fecha(r["DIA RECIBIDO"]),"cliente": safe_str(r.get("CLIENTE","")),"deposito": "LA CLEMENTINA","cantidad_comprada": safe_float(r.get("CANTIDAD COMPRADA", 0)),"producto": prod,"lote": "","cant_entregada": safe_float(r.get("CANT. ENTREGADA", 0)),"pendiente": pend,"estado": safe_str(r.get("ESTADO","")),"vendedor": safe_str(r.get("VENDEDOR","")),})
    except: pass
    try:
        df = pd.read_excel(archivo, sheet_name='LCAGRO S.A', header=1)
        df.columns = [str(c).strip() for c in df.columns]
        df["DIA RECIBIDO"] = pd.to_datetime(df["DIA RECIBIDO"], errors="coerce")
        for _, r in df.iterrows():
            prod = safe_str(r.get("PRODUCTO",""))
            if not prod: continue
            registros.append({"hoja": "LCAGRO S.A","rto": safe_str(r.get("RTO MONSANTO","")),"dia_recibido": safe_fecha(r["DIA RECIBIDO"]),"cliente": safe_str(r.get("CLIENTE","")),"deposito": "LCAGRO","cantidad_comprada": safe_float(r.get("CANTIDAD COMPRADA", 0)),"producto": prod,"lote": "","cant_entregada": safe_float(r.get("CANT. ENTREGADA", 0)),"pendiente": safe_float(r.get("PENDIENTE", 0)),"estado": safe_str(r.get("ESTADO","")),"vendedor": safe_str(r.get("VENDEDOR","")),})
    except: pass
    try:
        df = pd.read_excel(archivo, sheet_name='MERC CONSIGNADO BAYER DEP55', header=2)
        df.columns = [str(c).strip() for c in df.columns]
        df["DIA"] = pd.to_datetime(df["DIA"], errors="coerce")
        for _, r in df.iterrows():
            prod = safe_str(r.get("PRODUCTO",""))
            if not prod: continue
            registros.append({"hoja": "BAYER DEP55","rto": "","dia_recibido": safe_fecha(r["DIA"]),"cliente": safe_str(r.get("PRODUCTOR","")),"deposito": "DEP 55","cantidad_comprada": safe_float(r.get("CANTIDAD", 0)),"producto": prod,"lote": safe_str(r.get("LOTE","")),"cant_entregada": safe_float(r.get("CANTIDAD ENT", 0)),"pendiente": safe_float(r.get("CANTIDAD PEND", 0)),"estado": safe_str(r.get("ESTADO","")),"vendedor": safe_str(r.get("VENDEDOR","")),})
    except: pass
    try:
        df = pd.read_excel(archivo, sheet_name='MERC. FACT DIRECTA BAYER 43-60', header=1)
        df.columns = [str(c).strip() for c in df.columns]
        df["DIA RECIBIDO"] = pd.to_datetime(df["DIA RECIBIDO"], errors="coerce")
        for _, r in df.iterrows():
            prod = safe_str(r.get("PRODUCTO",""))
            if not prod: continue
            dep_raw = safe_str(r.get("DEPOSITO",""))
            deposito = f"BAYER DEP {dep_raw}" if dep_raw else "BAYER DIRECTO"
            registros.append({"hoja": "BAYER DIRECTA","rto": safe_str(r.get("RTO BAYER","")),"dia_recibido": safe_fecha(r["DIA RECIBIDO"]),"cliente": safe_str(r.get("CLIENTE","")),"deposito": deposito,"cantidad_comprada": safe_float(r.get("CANTIDAD COMPRADA", 0)),"producto": prod,"lote": safe_str(r.get("NRO LOTE","")),"cant_entregada": safe_float(r.get("CANT. ENTREGADA", 0)),"pendiente": safe_float(r.get("PENDIENTE", 0)),"estado": safe_str(r.get("ESTADO","")),"vendedor": safe_str(r.get("VENDEDOR","")),})
    except: pass
    return pd.DataFrame(registros) if registros else pd.DataFrame()

inicializar_db()

if 'qr_detectado' not in st.session_state:
    st.session_state.qr_detectado = "Todos"
if 'wa_numero' not in st.session_state:
    st.session_state.wa_numero = "5493406123456"
if 'umbral_alerta' not in st.session_state:
    st.session_state.umbral_alerta = 20
if 'mov_pendiente' not in st.session_state:
    st.session_state.mov_pendiente = None

st.title("🧪 Control de Depósito Inteligente")

def mostrar_banner_alertas():
    stock_df_b = obtener_stock_full()
    alertas = []
    if not stock_df_b.empty:
        U = st.session_state.umbral_alerta
        bajos = stock_df_b[stock_df_b["Stock Actual"] < U]
        if not bajos.empty:
            alertas.append(f"⚠️ **{len(bajos)} productos** con stock bajo")
        negativos = stock_df_b[stock_df_b["Stock Actual"] < 0]
        if not negativos.empty:
            alertas.append(f"❌ **{len(negativos)} productos** negativos")
    lotes_venc = obtener_lotes_por_vencer(60)
    if not lotes_venc.empty:
        criticos = lotes_venc[lotes_venc["Dias Restantes"] <= 30]
        if not criticos.empty:
            alertas.append(f"🔴 **{len(criticos)} lotes** vencen <30d")
    entregas_b = obtener_entregas()
    if not entregas_b.empty:
        pend = entregas_b[entregas_b["pendiente"] > 0]
        if not pend.empty:
            alertas.append(f"📦 **{pend['pendiente'].sum():,.0f}** pendiente")
    if alertas:
        html = "<div class='alerta-banner'><b>🔔 Alertas</b><br>" + " | ".join(alertas) + "</div>"
        st.markdown(html, unsafe_allow_html=True)

mostrar_banner_alertas()

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⚡ Panel de Control", "📦 LC / LCAGRO", "🌿 Bayer DEP55", "🚚 Bayer Directa",
    "📋 Planilla Stock", "📜 Historial", "⚙️ Configuración"
])

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
        lotes_venc_kpi = obtener_lotes_por_vencer(30)

        c_kpi1, c_kpi2, c_kpi3, c_kpi4, c_kpi5, c_kpi6 = st.columns(6)
        with c_kpi1: st.metric("Total Productos", len(df_kpi["Producto"].unique()))
        with c_kpi2: st.metric("Volumen Total", f"{df_kpi['Stock Actual'].sum():,.0f}")
        with c_kpi3:
            criticos_n = len(df_kpi[(df_kpi["Stock Actual"] >= 0) & (df_kpi["Stock Actual"] < U)])
            st.metric("Stock Bajo", criticos_n, delta=-criticos_n, delta_color="inverse")
        with c_kpi4:
            st.metric("Stock Negativo ⚠️", negativos_n, delta=-negativos_n, delta_color="inverse")
        with c_kpi5: st.metric("Depósitos", df_kpi["Deposito"].nunique())
        with c_kpi6:
            st.metric("Lotes vencen <30d", len(lotes_venc_kpi), delta=-len(lotes_venc_kpi) if len(lotes_venc_kpi) > 0 else 0, delta_color="inverse")

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

            lotes_venc_set = set()
            lv_df = obtener_lotes_por_vencer(60)
            if not lv_df.empty:
                for _, lv in lv_df.iterrows():
                    lotes_venc_set.add(lv["Producto"])

            dep_mapa = obtener_nombres_depositos()

            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items):
                with cols_grid[i % 4]:
                    stk_val = item['Stock Actual']
                    clase = "card-warning" if stk_val <= 0 else ("card-low" if stk_val < U else "card-normal")
                    badge_neg = '<span class="neg-badge">NEGATIVO</span>' if stk_val < 0 else ""
                    badge_venc = '<span class="vence-badge">VENCE PRONTO</span>' if item["Producto"] in lotes_venc_set else ""
                    dep_display = nombre_deposito(item['Deposito'], dep_mapa)
                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{item['Producto']}{badge_neg}{badge_venc}</div>
                            <span class="stock-value">{stk_val:,.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info"><b>🆔 Cód:</b> {item['Código']}<br><b>📍 Dep:</b> <span class="label-blue">{dep_display}</span></div>
                        </div>
                    """, unsafe_allow_html=True)

        if not lotes_venc_kpi.empty:
            st.markdown("---")
            st.subheader("🔴 Lotes que vencen en menos de 30 días")
            st.dataframe(lotes_venc_kpi[["Producto","Lote","Deposito","Vence","Dias Restantes","neta"]].rename(columns={"neta":"Stock"}), use_container_width=True, hide_index=True)

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
            fecha_venc_mov = st.date_input("Fecha de vencimiento (opcional)", value=None, key="mov_venc")

            if st.session_state.mov_pendiente is None:
                if st.button("📋 Preparar movimiento"):
                    st.session_state.mov_pendiente = {
                        "producto": prod_sel, "tipo": tipo_mov,
                        "cantidad": cantidad_mov, "deposito": deposito_mov,
                        "lote": lote_mov, "referencia": ref_mov,
                        "vencimiento": str(fecha_venc_mov) if fecha_venc_mov else ""
                    }
                    st.rerun()
            else:
                p = st.session_state.mov_pendiente
                venc_txt = f" | Vence: {p.get('vencimiento','')}" if p.get('vencimiento') else ""
                st.warning(f"""**¿Confirmar movimiento?**
- **{p['tipo']}** | **{p['producto']}** | {p['cantidad']:,.2f} | Dep: {p['deposito']}{venc_txt}""")
                col_conf1, col_conf2 = st.columns(2)
                with col_conf1:
                    if st.button("✅ Confirmar y registrar", type="primary"):
                        conn = conectar_db()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre=?", (p["producto"],))
                        id_p = cursor.fetchone()
                        if id_p:
                            cursor.execute("""
                                INSERT INTO movimientos (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen,fecha_vencimiento)
                                VALUES (?,?,?,?,?,?,?,?,?)
                            """, (datetime.now().strftime("%d/%m/%Y %H:%M"), p["tipo"],
                                  id_p[0], p["cantidad"], p["lote"], p["referencia"],
                                  p["deposito"], "manual", p.get("vencimiento","")))
                            conn.commit()
                            st.success("✅ Registrado.")
                        conn.close()
                        st.session_state.mov_pendiente = None
                        st.rerun()
                with col_conf2:
                    if st.button("❌ Cancelar"):
                        st.session_state.mov_pendiente = None
                        st.rerun()

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

        if df_f2["pendiente"].sum() > 0:
            st.markdown("---")
            st.subheader("📊 Pendiente por producto")
            pend_chart = df_f2[df_f2["pendiente"] > 0].groupby("producto")["pendiente"].sum().reset_index()
            fig_p = px.bar(pend_chart, x="producto", y="pendiente",
                           color="pendiente", color_continuous_scale="Reds",
                           labels={"producto":"Producto","pendiente":"Pendiente"})
            st.plotly_chart(fig_p, use_container_width=True)

        st.subheader("📊 Entregado vs Comprado")
        cmp_chart = df_f2.groupby("producto").agg(
            Comprado=("cantidad_comprada","sum"),
            Entregado=("cant_entregada","sum")
        ).reset_index().melt(id_vars="producto", var_name="Tipo", value_name="Cantidad")
        fig_cmp = px.bar(cmp_chart, x="producto", y="Cantidad", color="Tipo", barmode="group",
                         color_discrete_map={"Comprado":"#6c757d","Entregado":"#28a745"},
                         labels={"producto":"Producto"})
        st.plotly_chart(fig_cmp, use_container_width=True)

with tab2:
    subtab_lc, subtab_lcagro = st.tabs(["🏢 LA CLEMENTINA S.A", "🏢 LCAGRO S.A"])
    with subtab_lc:
        mostrar_tab_entregas("LA CLEMENTINA S.A", "#007bff", "📦 Entregas Monsanto — LA CLEMENTINA S.A")
    with subtab_lcagro:
        mostrar_tab_entregas("LCAGRO S.A", "#6f42c1", "📦 Entregas Monsanto — LCAGRO S.A")

with tab3:
    mostrar_tab_entregas("BAYER DEP55", "#fd7e14", "🌿 Mercadería Consignada Bayer — DEP 55")

with tab4:
    mostrar_tab_entregas("BAYER DIRECTA", "#20c997", "🚚 Mercadería Factura Directa Bayer — DEP 43/60")

with tab5:
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

with tab6:
    st.subheader("📜 Historial de Movimientos")
    hist_df = obtener_historial_movimientos()
    if not hist_df.empty:
        c_hf1, c_hf2, c_hf3, c_hf4 = st.columns(4)
        with c_hf1: f_tipo_h = st.selectbox("Tipo", ["Todos","Entrada","Salida"], key="h_tipo")
        with c_hf2: f_prod_h = st.selectbox("Producto", ["Todos"] + sorted(hist_df["Producto"].unique().tolist()), key="h_prod")
        with c_hf3: f_dep_h = st.selectbox("Depósito", ["Todos"] + sorted(hist_df["Depósito"].unique().tolist()), key="h_dep")
        with c_hf4: f_origen_h = st.selectbox("Origen", ["Todos","manual","excel","entrega"], key="h_origen")

        df_h = hist_df.copy()
        if f_tipo_h != "Todos": df_h = df_h[df_h["Tipo"] == f_tipo_h]
        if f_prod_h != "Todos": df_h = df_h[df_h["Producto"] == f_prod_h]
        if f_dep_h != "Todos": df_h = df_h[df_h["Depósito"] == f_dep_h]
        if f_origen_h != "Todos": df_h = df_h[df_h["Origen"] == f_origen_h]

        c_hkpi1, c_hkpi2, c_hkpi3, c_hkpi4 = st.columns(4)
        with c_hkpi1: st.metric("Movimientos", len(df_h))
        with c_hkpi2: st.metric("Entradas", len(df_h[df_h["Tipo"] == "Entrada"]))
        with c_hkpi3: st.metric("Salidas", len(df_h[df_h["Tipo"] == "Salida"]))
        with c_hkpi4: st.metric("Manuales", len(df_h[df_h["Origen"] == "manual"]))

        st.dataframe(df_h.drop(columns=["ID"]), use_container_width=True, hide_index=True)
        output_hist = io.BytesIO()
        with pd.ExcelWriter(output_hist, engine='openpyxl') as writer:
            df_h.to_excel(writer, index=False, sheet_name='Historial')
        st.download_button("📥 Exportar historial", data=output_hist.getvalue(), file_name="historial_movimientos.xlsx")
    else:
        st.info("Sin movimientos registrados.")

with tab7:
    st.subheader("⚙️ Configuración")

    st.markdown("#### 💾 Backup de base de datos")
    st.info("Descargá una copia de seguridad completa. Guardala en un lugar seguro.")
    col_bk1, col_bk2 = st.columns(2)
    with col_bk1:
        if st.button("📥 Descargar backup completo"):
            try:
                db_path = "stock_agroquimicos.db"
                if os.path.exists(db_path):
                    with open(db_path, "rb") as f:
                        db_bytes = f.read()
                    fecha_bk = datetime.now().strftime("%Y%m%d_%H%M")
                    st.download_button(
                        label="⬇️ Guardar archivo .db",
                        data=db_bytes,
                        file_name=f"backup_stock_{fecha_bk}.db",
                        mime="application/octet-stream",
                        key="dl_backup"
                    )
            except Exception as e:
                st.error(f"Error: {e}")
    with col_bk2:
        st.markdown("**Restaurar desde backup:**")
        backup_file = st.file_uploader("Subí un .db de backup", type=["db"], key="restore_db")
        if backup_file and st.button("🔄 Restaurar backup", type="primary"):
            confirmar_restore = st.checkbox("Confirmo reemplazar la BD actual")
            if confirmar_restore:
                try:
                    with open("stock_agroquimicos.db", "wb") as f:
                        f.write(backup_file.read())
                    st.success("✅ BD restaurada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.markdown("---")
    st.markdown("#### 🏭 Nombres de Depósitos")
    st.caption("Asigná nombres legibles a códigos de depósito.")
    stock_dep_config = obtener_stock_full()
    if not stock_dep_config.empty:
        dep_codigos = sorted(stock_dep_config["Deposito"].unique().tolist())
        dep_nombres_actuales = obtener_nombres_depositos()
        dep_data = pd.DataFrame({
            "Código": dep_codigos,
            "Nombre Legible": [dep_nombres_actuales.get(str(d), str(d)) for d in dep_codigos]
        })
        dep_editado = st.data_editor(dep_data, use_container_width=True, hide_index=True,
                                      column_config={"Código": st.column_config.TextColumn(disabled=True),
                                                     "Nombre Legible": st.column_config.TextColumn()},
                                      key="editor_depositos")
        if st.button("💾 Guardar nombres de depósitos"):
            conn = conectar_db()
            cursor = conn.cursor()
            for _, row in dep_editado.iterrows():
                cursor.execute("INSERT OR REPLACE INTO depositos_nombres (codigo, nombre_legible) VALUES (?,?)",
                               (str(row["Código"]), str(row["Nombre Legible"]).strip()))
            conn.commit(); conn.close()
            st.success("✅ Nombres actualizados.")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 🚨 Umbral de stock crítico")
    nuevo_umbral = st.slider("Stock mínimo antes de alertar", min_value=1, max_value=500, value=st.session_state.umbral_alerta)
    if nuevo_umbral != st.session_state.umbral_alerta:
        st.session_state.umbral_alerta = nuevo_umbral
        st.rerun()

    st.markdown("---")
    st.markdown("#### 📂 Importar datos de stock")
    st.info("💡 La importación **conserva tus movimientos manuales**. Solo reemplaza los datos del Excel anterior.")
    archivo = st.file_uploader("Subí el archivo 'export 3.xlsx' o 'export 3.csv'", type=["xlsx","csv","xls"])

    if archivo and st.button("🚀 PROCESAR E IMPORTAR"):
        try:
            if archivo.name.endswith('.csv'):
                df_import = pd.read_csv(archivo, encoding='latin1')
            else:
                df_import = pd.read_excel(archivo)
            df_import.columns = [str(c).strip().lower() for c in df_import.columns]
            col_nombre = None
            if 'articulo' in df_import.columns: col_nombre = 'articulo'
            elif 'descripcion_1' in df_import.columns: col_nombre = 'descripcion_1'
            if col_nombre and 'stock_actual' in df_import.columns:
                borrar_solo_importacion()
                conn = conectar_db(); cursor = conn.cursor(); filas_ok = 0
                for _, row in df_import.iterrows():
                    nom = str(row[col_nombre]).strip()
                    if pd.isna(row[col_nombre]) or nom == "" or nom.lower() == "nan": continue
                    cod = str(row['codigo']).strip() if 'codigo' in df_import.columns else "S/C"
                    uni = str(row['unidad_medida']).strip() if 'unidad_medida' in df_import.columns else "UNID"
                    dep = str(row['deposito']).strip() if 'deposito' in df_import.columns else "0"
                    lot = str(row['lote']).strip() if 'lote' in df_import.columns and not pd.isna(row['lote']) and str(row['lote']).strip() != "" else "S/L"
                    cursor.execute("INSERT OR IGNORE INTO productos (nombre,unidad,codigo) VALUES (?,?,?)", (nom,uni,cod))
                    cursor.execute("SELECT id_producto FROM productos WHERE nombre=?", (nom,))
                    id_p = cursor.fetchone()[0]
                    val_raw = str(row['stock_actual']).strip()
                    if pd.isna(row['stock_actual']) or val_raw == "" or val_raw.lower() == "nan": continue
                    if '.' in val_raw and ',' in val_raw: val_raw = val_raw.replace('.','')
                    val_raw = val_raw.replace(',','.')
                    try:
                        v = float(val_raw)
                        cursor.execute("INSERT INTO movimientos (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,deposito,origen) VALUES (?,?,?,?,?,?,?)",
                                       (datetime.now().strftime("%d/%m/%Y %H:%M"),"Entrada",id_p,v,lot,dep,"excel"))
                        filas_ok += 1
                    except: continue
                conn.commit(); conn.close()
                guardar_metadata("ultima_importacion", datetime.now().strftime("%d/%m/%Y %H:%M"))
                st.success(f"✅ {filas_ok} registros importados.")
                st.rerun()
            else:
                cols_enc = ', '.join(df_import.columns.tolist())
                st.error(f"❌ Columnas requeridas: ('articulo' o 'descripcion_1') y 'stock_actual'. Encontradas: {cols_enc}")
        except Exception as e:
            st.error(f"❌ Error: {e}")

    st.markdown("---")
    st.markdown("#### 🗑️ Zona peligrosa")
    with st.expander("⚠️ Borrar datos"):
        st.warning("No se puede deshacer.")
        confirmar = st.text_input("Escribí CONFIRMAR", key="confirm_borrar")
        if confirmar == "CONFIRMAR":
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("🗑️ Borrar stock y movimientos", type="primary"):
                    borrar_datos_totales()
                    st.success("Stock limpiado.")
                    st.rerun()
            with col_b2:
                if st.button("🗑️ Borrar solo entregas"):
                    conn = conectar_db()
                    conn.execute("DELETE FROM entregas")
                    conn.commit(); conn.close()
                    st.success("Entregas eliminadas.")
                    st.rerun()

st.markdown("---")
st.caption("Creado por Ignacio Diaz")
