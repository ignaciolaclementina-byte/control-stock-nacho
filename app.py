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
from difflib import SequenceMatcher

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
        position: absolute; top: 10px; right: 10px;
        font-size: 0.7rem; padding: 2px 8px;
        border-radius: 10px; color: white; font-weight: bold;
    }
    .bg-normal { background-color: #28a745; }
    .bg-low { background-color: #ffc107; color: #000; }
    .bg-warning { background-color: #dc3545; }

    .stock-info { 
        margin-top: 10px; padding-top: 8px; 
        border-top: 1px solid #f0f2f6; 
        font-size: 0.8rem; color: #495057; 
    }
    .label-blue { background-color: #e7f3ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .label-prov { background-color: #f0fff4; color: #28a745; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    
    .wa-btn {
        display: inline-flex; align-items: center;
        background-color: #25D366; color: white !important;
        padding: 5px 10px; border-radius: 6px;
        text-decoration: none; font-size: 0.75rem; font-weight: bold; margin-top: 10px;
    }
    .neg-badge {
        display: inline-block; background-color: #dc3545; color: white;
        font-size: 0.65rem; padding: 1px 6px; border-radius: 8px;
        font-weight: bold; margin-left: 4px; vertical-align: middle;
    }
    .min-badge {
        display: inline-block; background-color: #6f42c1; color: white;
        font-size: 0.65rem; padding: 1px 6px; border-radius: 8px;
        font-weight: bold; margin-left: 4px; vertical-align: middle;
    }
    .fuzzy-hint {
        background: #fff3cd; border: 1px solid #ffc107;
        border-radius: 8px; padding: 8px 12px;
        font-size: 0.85rem; margin-bottom: 8px;
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
            codigo TEXT,
            stock_minimo REAL DEFAULT 0,
            proveedor TEXT DEFAULT '',
            wa_proveedor TEXT DEFAULT ''
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
        CREATE TABLE IF NOT EXISTS metadata (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    # Migraciones seguras — nunca rompen una DB existente
    migraciones = [
        "ALTER TABLE productos ADD COLUMN codigo TEXT",
        "ALTER TABLE movimientos ADD COLUMN origen TEXT",
        "ALTER TABLE productos ADD COLUMN stock_minimo REAL DEFAULT 0",
        "ALTER TABLE productos ADD COLUMN proveedor TEXT DEFAULT ''",
        "ALTER TABLE productos ADD COLUMN wa_proveedor TEXT DEFAULT ''",
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
    cursor.execute("""
        DELETE FROM productos 
        WHERE id_producto NOT IN (SELECT DISTINCT id_producto FROM movimientos)
    """)
    conn.commit()
    conn.close()

def guardar_metadata(clave, valor):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO metadata (clave, valor) VALUES (?, ?)", (clave, valor))
    conn.commit()
    conn.close()

def obtener_metadata(clave):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM metadata WHERE clave = ?", (clave,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def obtener_stock_con_lote():
    conn = conectar_db()
    query = """
        SELECT p.nombre as Producto, p.codigo as Código, p.unidad as Unidad, 
               m.lote as Lote, m.deposito as Deposito, 
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

def obtener_stock_full_con_proveedor():
    """Stock full enriquecido con datos de proveedor y stock_minimo de la tabla productos."""
    df = obtener_stock_full()
    if df.empty: return df
    conn = conectar_db()
    try:
        prov_df = pd.read_sql_query(
            "SELECT nombre, COALESCE(stock_minimo,0) as stock_minimo, COALESCE(proveedor,'') as proveedor, COALESCE(wa_proveedor,'') as wa_proveedor FROM productos",
            conn
        )
    except:
        prov_df = pd.DataFrame(columns=["nombre","stock_minimo","proveedor","wa_proveedor"])
    conn.close()
    df = df.merge(prov_df, left_on="Producto", right_on="nombre", how="left")
    df["stock_minimo"] = df["stock_minimo"].fillna(0)
    df["proveedor"] = df["proveedor"].fillna("")
    df["wa_proveedor"] = df["wa_proveedor"].fillna("")
    df = df.drop(columns=["nombre"], errors="ignore")
    return df

def obtener_historial_movimientos():
    conn = conectar_db()
    query = """
        SELECT m.id_movimiento as ID, m.fecha_hora as Fecha, m.tipo_movimiento as Tipo,
               p.nombre as Producto, p.codigo as Código,
               m.cantidad as Cantidad, p.unidad as Unidad,
               m.lote as Lote, m.deposito as Depósito,
               m.referencia as Referencia,
               COALESCE(m.origen, 'excel') as Origen
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

def guardar_proveedor_producto(nombre_producto, stock_minimo, proveedor, wa_proveedor):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE productos 
        SET stock_minimo = ?, proveedor = ?, wa_proveedor = ?
        WHERE nombre = ?
    """, (stock_minimo, proveedor, wa_proveedor, nombre_producto))
    conn.commit()
    conn.close()

def obtener_todos_productos():
    conn = conectar_db()
    try:
        df = pd.read_sql_query(
            "SELECT nombre, COALESCE(stock_minimo,0) as stock_minimo, COALESCE(proveedor,'') as proveedor, COALESCE(wa_proveedor,'') as wa_proveedor FROM productos ORDER BY nombre",
            conn
        )
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

# PRO BÚSQUEDA FUZZY: tolerante a errores tipográficos
def busqueda_fuzzy(query, lista_nombres, umbral=0.55):
    """Devuelve nombres que coincidan aproximadamente con el query."""
    query = query.lower().strip()
    resultados = []
    for nombre in lista_nombres:
        ratio = SequenceMatcher(None, query, nombre.lower()).ratio()
        # También buscar si alguna palabra del nombre contiene el query
        palabras_match = any(query in palabra.lower() for palabra in nombre.split())
        if ratio >= umbral or palabras_match:
            resultados.append((nombre, ratio))
    resultados.sort(key=lambda x: x[1], reverse=True)
    return [r[0] for r in resultados]

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
if 'wa_numero' not in st.session_state:
    st.session_state.wa_numero = "5493406123456"
if 'umbral_alerta' not in st.session_state:
    st.session_state.umbral_alerta = 20
# PRO confirmación de movimiento
if 'mov_pendiente' not in st.session_state:
    st.session_state.mov_pendiente = None

# --- 4. INTERFAZ ---
st.title("🧪 Control de Depósito Inteligente")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚡ Panel de Control", 
    "📋 Planilla Toma Stock", 
    "📜 Historial", 
    "📊 Análisis", 
    "🏷️ Productos",
    "⚙️ Configuración"
])

# ===================== TAB 1: PANEL =====================
with tab1:
    stock_df = obtener_stock_full_con_proveedor()
    
    if stock_df.empty:
        st.warning("⚠️ No hay datos cargados. Por favor, subí el archivo en la pestaña 'Configuración'.")
    else:
        U = st.session_state.umbral_alerta

        ultima_actualizacion = obtener_metadata("ultima_importacion")
        if ultima_actualizacion:
            st.caption(f"🕐 Última importación del Excel: **{ultima_actualizacion}**")

        df_kpi = stock_df.copy()
        negativos_n = len(df_kpi[df_kpi["Stock Actual"] < 0])

        # PRO stock_minimo por producto: crítico es el que está bajo SU propio mínimo o bajo el global
        def es_critico(row, U_global):
            minimo = row["stock_minimo"] if row["stock_minimo"] > 0 else U_global
            return 0 <= row["Stock Actual"] < minimo

        criticos_n = len(df_kpi[df_kpi.apply(lambda r: es_critico(r, U), axis=1)])

        c_kpi1, c_kpi2, c_kpi3, c_kpi4, c_kpi5 = st.columns(5)
        with c_kpi1: st.metric("Total Productos", len(df_kpi["Producto"].unique()))
        with c_kpi2: st.metric("Volumen Total", f"{df_kpi['Stock Actual'].sum():,.0f}")
        with c_kpi3: st.metric("Stock Bajo", criticos_n, delta=-criticos_n, delta_color="inverse")
        with c_kpi4: st.metric("Stock Negativo ⚠️", negativos_n, delta=-negativos_n, delta_color="inverse")
        with c_kpi5: st.metric("Depósitos", df_kpi["Deposito"].nunique())

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
            hide_neg = st.toggle("Solo con stock positivo", value=True)
            filter_reponer = st.toggle(f"🚨 Reponer (bajo mínimo)", value=False)
            show_neg_forced = st.toggle("⚠️ Mostrar negativos siempre", value=True)

        df_f = stock_df.copy()

        # PRO FUZZY: si la búsqueda no da resultados exactos, buscar fonéticamente
        fuzzy_usado = False
        if search_query:
            df_exacto = df_f[
                df_f["Producto"].str.contains(search_query, case=False, na=False) | 
                df_f["Código"].astype(str).str.contains(search_query, case=False, na=False)
            ]
            if df_exacto.empty:
                # Intentar búsqueda fuzzy
                todos_nombres = stock_df["Producto"].unique().tolist()
                nombres_fuzzy = busqueda_fuzzy(search_query, todos_nombres)
                if nombres_fuzzy:
                    df_f = df_f[df_f["Producto"].isin(nombres_fuzzy)]
                    fuzzy_usado = True
                else:
                    df_f = df_exacto
            else:
                df_f = df_exacto

        if st.session_state.qr_detectado != "Todos" and not search_query:
            df_f = df_f[df_f["Producto"] == st.session_state.qr_detectado]
        if f_depo != "Todos":
            df_f = df_f[df_f["Deposito"] == f_depo]
        if hide_neg:
            if show_neg_forced:
                df_f = df_f[(df_f["Stock Actual"] > 0) | (df_f["Stock Actual"] < 0)]
            else:
                df_f = df_f[df_f["Stock Actual"] > 0]
        # PRO stock_minimo: filtro "Reponer" usa mínimo por producto
        if filter_reponer:
            def bajo_minimo(row):
                minimo = row["stock_minimo"] if row["stock_minimo"] > 0 else U
                return row["Stock Actual"] < minimo
            df_f = df_f[df_f.apply(bajo_minimo, axis=1)]

        # Aviso de búsqueda fuzzy
        if fuzzy_usado:
            st.markdown(f'<div class="fuzzy-hint">🔍 No se encontraron resultados exactos para "<b>{search_query}</b>". Mostrando resultados similares.</div>', unsafe_allow_html=True)

        if not df_f.empty:
            # Reporte masivo WhatsApp — usa número de proveedor si está disponible, sino el global
            criticos_wa = df_f[df_f.apply(lambda r: es_critico(r, U), axis=1)]
            if not criticos_wa.empty:
                lineas = [f"🚨 REPORTE STOCK CRÍTICO - {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
                lineas.append(f"Umbral global: {U} unidades\n")
                for _, r in criticos_wa.iterrows():
                    emoji = "❌" if r["Stock Actual"] <= 0 else "⚠️"
                    minimo_prod = r["stock_minimo"] if r["stock_minimo"] > 0 else U
                    lineas.append(f"{emoji} {r['Producto']} | Dep: {r['Deposito']} | Stock: {r['Stock Actual']:,.1f} {r['Unidad']} | Mín: {minimo_prod:,.0f}")
                msg_masivo = urllib.parse.quote("\n".join(lineas))
                link_masivo = f"https://wa.me/{st.session_state.wa_numero}?text={msg_masivo}"
                st.markdown(
                    f'<a href="{link_masivo}" target="_blank" style="display:inline-flex;align-items:center;background:#25D366;color:white;padding:8px 16px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:0.85rem;margin-bottom:12px;">💬 Reportar {len(criticos_wa)} productos críticos por WhatsApp</a>',
                    unsafe_allow_html=True
                )

            excel_bin = descargar_excel_agrupado_sin_lote(df_f[["Producto","Código","Unidad","Deposito","Stock Actual"]])
            st.download_button(label="📥 Descargar Comparativa Total", data=excel_bin, file_name='stock_agrupado.xlsx')

            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items): 
                with cols_grid[i % 4]:
                    stk_val = item['Stock Actual']
                    minimo_prod = item["stock_minimo"] if item["stock_minimo"] > 0 else U
                    clase = "card-warning" if stk_val <= 0 else ("card-low" if stk_val < minimo_prod else "card-normal")
                    badge_neg = '<span class="neg-badge">NEGATIVO</span>' if stk_val < 0 else ""
                    # PRO: badge de stock mínimo personalizado
                    badge_min = f'<span class="min-badge">MÍN: {minimo_prod:,.0f}</span>' if item["stock_minimo"] > 0 else ""
                    
                    # PRO PROVEEDOR: usar número del proveedor si existe, sino el global
                    wa_dest = item["wa_proveedor"] if item.get("wa_proveedor","").strip() else st.session_state.wa_numero
                    prov_texto = item.get("proveedor","").strip()
                    prov_html = f'<br><b>🏭 Prov:</b> <span class="label-prov">{prov_texto}</span>' if prov_texto else ""

                    msg_wa = urllib.parse.quote(f"Reporte: {item['Producto']}. Dep: {item['Deposito']}. Stock: {stk_val}")
                    link_wa = f"https://wa.me/{wa_dest}?text={msg_wa}"
                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{item['Producto']}{badge_neg}{badge_min}</div>
                            <span class="stock-value">{stk_val:,.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info">
                                <b>🆔 Cód:</b> {item['Código']}<br>
                                <b>📍 Dep:</b> <span class="label-blue">{item['Deposito']}</span>
                                {prov_html}
                            </div>
                            <a href="{link_wa}" target="_blank" class="wa-btn">💬 Reportar</a>
                        </div>
                    """, unsafe_allow_html=True)

        st.markdown("---")
        # PRO CONFIRMACIÓN: movimiento manual con paso de confirmación
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

            # PRO CONFIRMACIÓN: primero "preparar", luego confirmar
            if st.session_state.mov_pendiente is None:
                if st.button("📋 Preparar movimiento"):
                    st.session_state.mov_pendiente = {
                        "producto": prod_sel,
                        "tipo": tipo_mov,
                        "cantidad": cantidad_mov,
                        "deposito": deposito_mov,
                        "lote": lote_mov,
                        "referencia": ref_mov
                    }
                    st.rerun()
            else:
                p = st.session_state.mov_pendiente
                st.warning(f"""
                **¿Confirmar este movimiento?**
                - **Tipo:** {p['tipo']}
                - **Producto:** {p['producto']}
                - **Cantidad:** {p['cantidad']:,.2f}
                - **Depósito:** {p['deposito']}
                - **Lote:** {p['lote']}
                - **Referencia:** {p['referencia'] or '—'}
                """)
                col_conf1, col_conf2 = st.columns(2)
                with col_conf1:
                    if st.button("✅ Confirmar y registrar", type="primary"):
                        conn = conectar_db()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (p["producto"],))
                        id_p = cursor.fetchone()
                        if id_p:
                            cursor.execute("""
                                INSERT INTO movimientos 
                                (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, referencia, deposito, origen)
                                VALUES (?,?,?,?,?,?,?,?)
                            """, (datetime.now().strftime("%d/%m/%Y %H:%M"), p["tipo"],
                                  id_p[0], p["cantidad"], p["lote"], p["referencia"], p["deposito"], "manual"))
                            conn.commit()
                            st.success(f"✅ {p['tipo']} de {p['cantidad']:.2f} registrada para **{p['producto']}**.")
                        else:
                            st.error("No se encontró el producto.")
                        conn.close()
                        st.session_state.mov_pendiente = None
                        st.rerun()
                with col_conf2:
                    if st.button("❌ Cancelar"):
                        st.session_state.mov_pendiente = None
                        st.rerun()

# ===================== TAB 2: PLANILLA =====================
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

# ===================== TAB 3: HISTORIAL =====================
with tab3:
    st.subheader("📜 Historial de Movimientos")
    hist_df = obtener_historial_movimientos()
    if not hist_df.empty:
        c_hf1, c_hf2, c_hf3, c_hf4 = st.columns(4)
        with c_hf1:
            f_tipo_h = st.selectbox("Tipo", ["Todos", "Entrada", "Salida"], key="h_tipo")
        with c_hf2:
            f_prod_h = st.selectbox("Producto", ["Todos"] + sorted(hist_df["Producto"].unique().tolist()), key="h_prod")
        with c_hf3:
            f_dep_h = st.selectbox("Depósito", ["Todos"] + sorted(hist_df["Depósito"].unique().tolist()), key="h_dep")
        with c_hf4:
            f_origen_h = st.selectbox("Origen", ["Todos", "manual", "excel"], key="h_origen")

        df_h = hist_df.copy()
        if f_tipo_h != "Todos": df_h = df_h[df_h["Tipo"] == f_tipo_h]
        if f_prod_h != "Todos": df_h = df_h[df_h["Producto"] == f_prod_h]
        if f_dep_h != "Todos": df_h = df_h[df_h["Depósito"] == f_dep_h]
        if f_origen_h != "Todos": df_h = df_h[df_h["Origen"] == f_origen_h]

        c_hkpi1, c_hkpi2, c_hkpi3, c_hkpi4 = st.columns(4)
        with c_hkpi1: st.metric("Movimientos mostrados", len(df_h))
        with c_hkpi2: st.metric("Total entradas", len(df_h[df_h["Tipo"] == "Entrada"]))
        with c_hkpi3: st.metric("Total salidas", len(df_h[df_h["Tipo"] == "Salida"]))
        with c_hkpi4: st.metric("Manuales", len(df_h[df_h["Origen"] == "manual"]))

        st.dataframe(df_h.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        output_hist = io.BytesIO()
        with pd.ExcelWriter(output_hist, engine='openpyxl') as writer:
            df_h.to_excel(writer, index=False, sheet_name='Historial')
        st.download_button("📥 Exportar historial filtrado", data=output_hist.getvalue(), file_name="historial_movimientos.xlsx")
    else:
        st.info("Sin movimientos registrados.")

# ===================== TAB 4: ANÁLISIS =====================
with tab4:
    stock_df_an = obtener_stock_full()
    if not stock_df_an.empty:
        st.subheader("Top 10 productos por stock")
        df_pareto = stock_df_an.groupby("Producto")["Stock Actual"].sum().sort_values(ascending=False).head(10).reset_index()
        fig_pareto = px.bar(df_pareto, x='Stock Actual', y='Producto', orientation='h', color='Stock Actual', color_continuous_scale='Greens')
        st.plotly_chart(fig_pareto, use_container_width=True)

        st.subheader("Distribución por depósito")
        df_dep = stock_df_an.groupby("Deposito")["Stock Actual"].sum().reset_index()
        fig_dep = px.pie(df_dep, names="Deposito", values="Stock Actual", color_discrete_sequence=px.colors.qualitative.Set2)
        fig_dep.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_dep, use_container_width=True)

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

# ===================== TAB 5: PRODUCTOS (NUEVO) =====================
with tab5:
    st.subheader("🏷️ Gestión de Productos")
    st.caption("Configurá el stock mínimo y el proveedor de cada producto. El botón de WhatsApp en el panel irá directo al proveedor asignado.")

    todos_prod = obtener_todos_productos()
    if todos_prod.empty:
        st.info("Sin productos cargados.")
    else:
        # Buscador dentro de la pestaña
        busq_prod = st.text_input("🔍 Buscar producto", placeholder="Escriba para filtrar...", key="busq_tab5")
        if busq_prod:
            todos_prod = todos_prod[todos_prod["nombre"].str.contains(busq_prod, case=False, na=False)]

        st.markdown(f"**{len(todos_prod)} productos** | Editá el stock mínimo y proveedor:")

        # Editar en bloque con st.data_editor
        todos_prod_edit = todos_prod.copy()
        todos_prod_edit.columns = ["Producto", "Stock Mínimo", "Proveedor", "WA Proveedor"]

        df_editado = st.data_editor(
            todos_prod_edit,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Producto": st.column_config.TextColumn("Producto", disabled=True),
                "Stock Mínimo": st.column_config.NumberColumn("Stock Mínimo", min_value=0, step=1, help="0 = usar el umbral global"),
                "Proveedor": st.column_config.TextColumn("Proveedor", help="Nombre del proveedor"),
                "WA Proveedor": st.column_config.TextColumn("WA Proveedor", help="Número WhatsApp del proveedor (con código de país, sin +). Ej: 5493406999888"),
            },
            key="editor_productos"
        )

        if st.button("💾 Guardar cambios de productos", type="primary"):
            conn = conectar_db()
            cursor = conn.cursor()
            for _, row in df_editado.iterrows():
                cursor.execute("""
                    UPDATE productos 
                    SET stock_minimo = ?, proveedor = ?, wa_proveedor = ?
                    WHERE nombre = ?
                """, (
                    float(row["Stock Mínimo"]) if row["Stock Mínimo"] else 0,
                    str(row["Proveedor"]).strip() if row["Proveedor"] else "",
                    str(row["WA Proveedor"]).strip() if row["WA Proveedor"] else "",
                    row["Producto"]
                ))
            conn.commit()
            conn.close()
            st.success(f"✅ {len(df_editado)} productos actualizados.")
            st.rerun()

        # Exportar tabla de productos a Excel
        output_prod = io.BytesIO()
        with pd.ExcelWriter(output_prod, engine='openpyxl') as writer:
            df_editado.to_excel(writer, index=False, sheet_name='Productos')
        st.download_button("📥 Exportar tabla de productos", data=output_prod.getvalue(), file_name="productos_config.xlsx")

# ===================== TAB 6: CONFIGURACIÓN =====================
with tab6:
    st.subheader("⚙️ Configuración")

    st.markdown("#### 📱 WhatsApp para alertas (número global)")
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

    st.markdown("#### 🚨 Umbral de stock crítico global")
    st.caption("Se aplica a los productos que no tienen stock mínimo propio configurado en la pestaña Productos.")
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

    st.markdown("#### 📂 Importar datos")
    st.info("💡 La importación **conserva tus movimientos manuales**. Solo reemplaza los datos del Excel anterior.")

    archivo = st.file_uploader("Subí el archivo 'export 3.xlsx' o 'export 3.csv'", type=["xlsx", "csv", "xls"])
    
    if archivo and st.button("🚀 PROCESAR E IMPORTAR"):
        try:
            if archivo.name.endswith('.csv'):
                df_import = pd.read_csv(archivo, encoding='latin1')
            else:
                df_import = pd.read_excel(archivo)
                
            df_import.columns = [str(c).strip().lower() for c in df_import.columns]
            
            col_nombre = None
            if 'articulo' in df_import.columns:
                col_nombre = 'articulo'
            elif 'descripcion_1' in df_import.columns:
                col_nombre = 'descripcion_1'

            if col_nombre and 'stock_actual' in df_import.columns:
                borrar_solo_importacion()
                conn = conectar_db()
                cursor = conn.cursor()
                filas_ok = 0
                
                for _, row in df_import.iterrows():
                    nom = str(row[col_nombre]).strip()
                    if pd.isna(row[col_nombre]) or nom == "" or nom.lower() == "nan": 
                        continue
                    cod = str(row['codigo']).strip() if 'codigo' in df_import.columns else "S/C"
                    uni = str(row['unidad_medida']).strip() if 'unidad_medida' in df_import.columns else "UNID"
                    dep = str(row['deposito']).strip() if 'deposito' in df_import.columns else "0"
                    lot = str(row['lote']).strip() if 'lote' in df_import.columns and not pd.isna(row['lote']) and str(row['lote']).strip() != "" else "S/L"
                    
                    # INSERT OR IGNORE preserva stock_minimo/proveedor/wa_proveedor si el producto ya existía
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
                            INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito, origen) 
                            VALUES (?,?,?,?,?,?,?)
                        """, (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, v, lot, dep, "excel"))
                        filas_ok += 1
                    except:
                        continue
                        
                conn.commit()
                conn.close()
                guardar_metadata("ultima_importacion", datetime.now().strftime("%d/%m/%Y %H:%M"))
                st.success(f"✅ Importación exitosa. {filas_ok} registros cargados. Movimientos manuales y configuración de productos conservados.")
                st.rerun()
            else:
                cols_enc = ', '.join(df_import.columns.tolist())
                st.error(f"❌ Columnas requeridas: ('articulo' o 'descripcion_1') y 'stock_actual'. Encontradas: {cols_enc}")
        except Exception as e: 
            st.error(f"❌ Error al procesar el archivo: {e}")

    st.markdown("---")
    st.markdown("#### 🗑️ Zona peligrosa")
    with st.expander("⚠️ Borrar todos los datos"):
        st.warning("Esta acción elimina TODOS los productos y movimientos (incluidos manuales). No se puede deshacer.")
        confirmar = st.text_input("Escribí CONFIRMAR para habilitar el botón", key="confirm_borrar")
        if confirmar == "CONFIRMAR":
            if st.button("🗑️ Borrar todo", type="primary"):
                borrar_datos_totales()
                st.success("Base de datos limpiada.")
                st.rerun()

st.markdown("---")
st.caption("Creado por Ignacio Diaz")
