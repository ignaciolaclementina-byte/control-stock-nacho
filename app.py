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
    .stock-info { 
        margin-top: 10px; padding-top: 8px; border-top: 1px solid #f0f2f6; 
        font-size: 0.8rem; color: #495057; 
    }
    .label-blue { background-color: #e7f3ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .neg-badge {
        display: inline-block; background-color: #dc3545; color: white;
        font-size: 0.65rem; padding: 1px 6px; border-radius: 8px;
        font-weight: bold; margin-left: 4px; vertical-align: middle;
    }
    .entrega-card {
        background: white; border-radius: 10px; padding: 14px 16px;
        border: 1px solid #e1e4e8; margin-bottom: 8px;
        border-left: 6px solid #6c757d;
    }
    .entrega-vigente { border-left-color: #007bff; }
    .entrega-entregado { border-left-color: #28a745; }
    .entrega-pendiente { border-left-color: #ffc107; }
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
            origen TEXT,
            FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
        )
    """)
    # Tabla entregas Monsanto/Bayer
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entregas (
            id_entrega INTEGER PRIMARY KEY AUTOINCREMENT,
            rto_monsanto TEXT,
            dia_recibido TEXT,
            cliente TEXT,
            cantidad_comprada REAL,
            producto TEXT,
            cant_entregada REAL,
            pendiente REAL,
            estado TEXT,
            vendedor TEXT,
            descontado_stock INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    migraciones = [
        "ALTER TABLE productos ADD COLUMN codigo TEXT",
        "ALTER TABLE movimientos ADD COLUMN origen TEXT",
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

def obtener_entregas():
    conn = conectar_db()
    try:
        df = pd.read_sql_query("SELECT * FROM entregas ORDER BY dia_recibido DESC", conn)
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
if 'wa_numero' not in st.session_state:
    st.session_state.wa_numero = "5493406123456"
if 'umbral_alerta' not in st.session_state:
    st.session_state.umbral_alerta = 20
if 'mov_pendiente' not in st.session_state:
    st.session_state.mov_pendiente = None

# --- 4. INTERFAZ ---
st.title("🧪 Control de Depósito Inteligente")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚡ Panel de Control",
    "📦 Entregas Monsanto/Bayer",
    "📋 Planilla Toma Stock",
    "📜 Historial",
    "📊 Análisis",
    "⚙️ Configuración"
])

# ===================== TAB 1: PANEL =====================
with tab1:
    stock_df = obtener_stock_full()
    
    if stock_df.empty:
        st.warning("⚠️ No hay datos cargados. Por favor, subí el archivo en la pestaña 'Configuración'.")
    else:
        U = st.session_state.umbral_alerta
        ultima_actualizacion = obtener_metadata("ultima_importacion")
        if ultima_actualizacion:
            st.caption(f"🕐 Última importación del Excel: **{ultima_actualizacion}**")

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
            filter_reponer = st.toggle(f"🚨 Reponer (<{U})", value=False)
            show_neg_forced = st.toggle("⚠️ Mostrar negativos siempre", value=True)

        df_f = stock_df.copy()
        if search_query:
            df_f = df_f[
                df_f["Producto"].str.contains(search_query, case=False, na=False) | 
                df_f["Código"].astype(str).str.contains(search_query, case=False, na=False)
            ]
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
                st.warning(f"""
                **¿Confirmar este movimiento?**
                - **Tipo:** {p['tipo']}  
                - **Producto:** {p['producto']}  
                - **Cantidad:** {p['cantidad']:,.2f}  
                - **Depósito:** {p['deposito']}  
                - **Lote:** {p['lote']}
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
                            st.success(f"✅ Registrado.")
                        conn.close()
                        st.session_state.mov_pendiente = None
                        st.rerun()
                with col_conf2:
                    if st.button("❌ Cancelar"):
                        st.session_state.mov_pendiente = None
                        st.rerun()

# ===================== TAB 2: ENTREGAS MONSANTO/BAYER =====================
with tab2:
    st.subheader("📦 Entregas Monsanto / Bayer — Campaña 2024/2025")

    entregas_df = obtener_entregas()

    # Sección de importación del Excel de entregas
    with st.expander("📂 Importar / Actualizar archivo de entregas", expanded=entregas_df.empty):
        st.info("Subí el archivo de entregas Monsanto/Bayer. Se reemplazará el registro anterior de entregas.")
        arch_entregas = st.file_uploader("Archivo de entregas (.xlsx)", type=["xlsx","xls"], key="uploader_entregas")

        col_op1, col_op2 = st.columns(2)
        with col_op1:
            descontar_stock = st.toggle(
                "🔄 Registrar entregas como Salidas de stock",
                value=False,
                help="Si activás esto, cada fila con CANT. ENTREGADA > 0 se registrará como un movimiento de Salida en el stock, descontando automáticamente."
            )
        with col_op2:
            deposito_entregas = st.selectbox(
                "Depósito origen de las entregas",
                options=obtener_stock_full()["Deposito"].unique().tolist() if not obtener_stock_full().empty else ["0"],
                key="dep_entregas"
            ) if descontar_stock else None

        if arch_entregas and st.button("🚀 IMPORTAR ENTREGAS", type="primary"):
            try:
                df_e = pd.read_excel(arch_entregas, header=1)
                df_e.columns = [str(c).strip() for c in df_e.columns]

                # Calcular pendiente real (unifica columna PENDIENTE y Unnamed: 7)
                col_pend2 = "Unnamed: 7" if "Unnamed: 7" in df_e.columns else None
                df_e["pendiente_real"] = df_e["PENDIENTE"].fillna(0)
                if col_pend2:
                    df_e["pendiente_real"] = df_e["pendiente_real"] + df_e[col_pend2].fillna(0)

                df_e["DIA RECIBIDO"] = pd.to_datetime(df_e["DIA RECIBIDO"], errors="coerce")

                conn = conectar_db()
                cursor = conn.cursor()
                # Limpiar entregas anteriores
                cursor.execute("DELETE FROM entregas")

                filas_ok = 0
                filas_salida = 0
                productos_no_match = []

                for _, row in df_e.iterrows():
                    prod = str(row.get("PRODUCTO","")).strip()
                    if not prod or prod.lower() == "nan":
                        continue

                    cliente = str(row.get("CLIENTE","")).strip()
                    rto = str(row.get("RTO MONSANTO","")).strip()
                    fecha = row["DIA RECIBIDO"].strftime("%d/%m/%Y") if pd.notna(row["DIA RECIBIDO"]) else ""
                    cant_comprada = float(row.get("CANTIDAD COMPRADA", 0) or 0)
                    cant_entregada = float(row.get("CANT. ENTREGADA", 0) or 0)
                    pendiente = float(row.get("pendiente_real", 0) or 0)
                    estado = str(row.get("ESTADO","")).strip()
                    vendedor = str(row.get("VENDEDOR","")).strip()

                    cursor.execute("""
                        INSERT INTO entregas 
                        (rto_monsanto, dia_recibido, cliente, cantidad_comprada, producto,
                         cant_entregada, pendiente, estado, vendedor, descontado_stock)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (rto, fecha, cliente, cant_comprada, prod,
                          cant_entregada, pendiente, estado, vendedor, 0))
                    filas_ok += 1

                    # Opción B: descontar del stock como movimiento de Salida
                    if descontar_stock and cant_entregada > 0:
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (prod,))
                        match = cursor.fetchone()
                        if match:
                            cursor.execute("""
                                INSERT INTO movimientos 
                                (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, referencia, deposito, origen)
                                VALUES (?,?,?,?,?,?,?,?)
                            """, (fecha or datetime.now().strftime("%d/%m/%Y"),
                                  "Salida", match[0], cant_entregada,
                                  "S/L", f"Entrega a {cliente}", deposito_entregas, "entrega"))
                            filas_salida += 1
                        else:
                            if prod not in productos_no_match:
                                productos_no_match.append(prod)

                conn.commit()
                conn.close()
                guardar_metadata("ultima_importacion_entregas", datetime.now().strftime("%d/%m/%Y %H:%M"))

                msg = f"✅ {filas_ok} entregas importadas."
                if descontar_stock:
                    msg += f" {filas_salida} movimientos de salida registrados en stock."
                st.success(msg)
                if productos_no_match:
                    st.warning(f"⚠️ Estos productos del archivo de entregas no coincidieron con el stock (no se descontaron): {', '.join(productos_no_match)}")
                st.rerun()

            except Exception as ex:
                st.error(f"❌ Error al importar: {ex}")

    if not entregas_df.empty:
        ultima_ent = obtener_metadata("ultima_importacion_entregas")
        if ultima_ent:
            st.caption(f"🕐 Última importación de entregas: **{ultima_ent}**")

        # KPIs de entregas
        total_comprado = entregas_df["cantidad_comprada"].sum()
        total_entregado = entregas_df["cant_entregada"].sum()
        total_pendiente = entregas_df["pendiente"].sum()
        pct_entregado = (total_entregado / total_comprado * 100) if total_comprado > 0 else 0

        ck1, ck2, ck3, ck4 = st.columns(4)
        with ck1: st.metric("Clientes únicos", entregas_df["cliente"].nunique())
        with ck2: st.metric("Total comprado", f"{total_comprado:,.0f}")
        with ck3: st.metric("Total entregado", f"{total_entregado:,.0f}", delta=f"{pct_entregado:.1f}%")
        with ck4: st.metric("Pendiente total", f"{total_pendiente:,.0f}", delta=f"-{total_pendiente:,.0f}", delta_color="inverse")

        st.markdown("---")

        # Filtros
        cf1, cf2, cf3, cf4 = st.columns(4)
        with cf1:
            f_estado = st.selectbox("Estado", ["Todos"] + sorted(entregas_df["estado"].dropna().unique().tolist()), key="f_est")
        with cf2:
            f_prod_e = st.selectbox("Producto", ["Todos"] + sorted(entregas_df["producto"].dropna().unique().tolist()), key="f_prod_e")
        with cf3:
            f_vend = st.selectbox("Vendedor", ["Todos"] + sorted(entregas_df["vendedor"].dropna().unique().tolist()), key="f_vend")
        with cf4:
            f_cliente = st.text_input("🔍 Buscar cliente", placeholder="Nombre...", key="f_cli")

        df_e_f = entregas_df.copy()
        if f_estado != "Todos": df_e_f = df_e_f[df_e_f["estado"] == f_estado]
        if f_prod_e != "Todos": df_e_f = df_e_f[df_e_f["producto"] == f_prod_e]
        if f_vend != "Todos": df_e_f = df_e_f[df_e_f["vendedor"] == f_vend]
        if f_cliente: df_e_f = df_e_f[df_e_f["cliente"].str.contains(f_cliente, case=False, na=False)]

        st.markdown(f"**{len(df_e_f)} registros** encontrados")

        # Subtotales por producto filtrado
        if not df_e_f.empty:
            sub = df_e_f.groupby("producto").agg(
                Comprado=("cantidad_comprada","sum"),
                Entregado=("cant_entregada","sum"),
                Pendiente=("pendiente","sum"),
                Clientes=("cliente","nunique")
            ).reset_index().rename(columns={"producto":"Producto"})
            sub["% Entregado"] = (sub["Entregado"] / sub["Comprado"] * 100).round(1).astype(str) + "%"
            st.dataframe(sub, use_container_width=True, hide_index=True)

            st.markdown("---")

            # Tabla detalle
            cols_mostrar = ["dia_recibido","cliente","producto","cantidad_comprada","cant_entregada","pendiente","estado","vendedor"]
            cols_mostrar = [c for c in cols_mostrar if c in df_e_f.columns]
            df_tabla = df_e_f[cols_mostrar].copy()
            df_tabla.columns = ["Fecha","Cliente","Producto","Comprado","Entregado","Pendiente","Estado","Vendedor"]
            st.dataframe(df_tabla, use_container_width=True, hide_index=True)

            # Exportar
            output_e = io.BytesIO()
            with pd.ExcelWriter(output_e, engine='openpyxl') as writer:
                df_tabla.to_excel(writer, index=False, sheet_name='Entregas')
            st.download_button("📥 Exportar vista actual", data=output_e.getvalue(), file_name="entregas_filtradas.xlsx")

            # Gráfico de pendiente por producto
            if df_e_f["pendiente"].sum() > 0:
                st.markdown("---")
                st.subheader("📊 Pendiente por producto")
                pend_chart = df_e_f[df_e_f["pendiente"] > 0].groupby("producto")["pendiente"].sum().reset_index()
                fig_pend = px.bar(pend_chart, x="producto", y="pendiente",
                                  color="pendiente", color_continuous_scale="Reds",
                                  labels={"producto":"Producto","pendiente":"Pendiente"})
                st.plotly_chart(fig_pend, use_container_width=True)
    else:
        st.info("Sin entregas cargadas. Usá el importador de arriba para cargar el archivo de Monsanto/Bayer.")

# ===================== TAB 3: PLANILLA =====================
with tab3:
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

# ===================== TAB 4: HISTORIAL =====================
with tab4:
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
            f_origen_h = st.selectbox("Origen", ["Todos", "manual", "excel", "entrega"], key="h_origen")

        df_h = hist_df.copy()
        if f_tipo_h != "Todos": df_h = df_h[df_h["Tipo"] == f_tipo_h]
        if f_prod_h != "Todos": df_h = df_h[df_h["Producto"] == f_prod_h]
        if f_dep_h != "Todos": df_h = df_h[df_h["Depósito"] == f_dep_h]
        if f_origen_h != "Todos": df_h = df_h[df_h["Origen"] == f_origen_h]

        c_hkpi1, c_hkpi2, c_hkpi3, c_hkpi4 = st.columns(4)
        with c_hkpi1: st.metric("Movimientos mostrados", len(df_h))
        with c_hkpi2: st.metric("Entradas", len(df_h[df_h["Tipo"] == "Entrada"]))
        with c_hkpi3: st.metric("Salidas", len(df_h[df_h["Tipo"] == "Salida"]))
        with c_hkpi4: st.metric("Manuales", len(df_h[df_h["Origen"] == "manual"]))

        st.dataframe(df_h.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        output_hist = io.BytesIO()
        with pd.ExcelWriter(output_hist, engine='openpyxl') as writer:
            df_h.to_excel(writer, index=False, sheet_name='Historial')
        st.download_button("📥 Exportar historial filtrado", data=output_hist.getvalue(), file_name="historial_movimientos.xlsx")
    else:
        st.info("Sin movimientos registrados.")

# ===================== TAB 5: ANÁLISIS =====================
with tab5:
    stock_df_an = obtener_stock_full()
    if not stock_df_an.empty:
        st.subheader("Top 10 productos por stock")
        df_pareto = stock_df_an.groupby("Producto")["Stock Actual"].sum().sort_values(ascending=False).head(10).reset_index()
        fig_pareto = px.bar(df_pareto, x='Stock Actual', y='Producto', orientation='h',
                            color='Stock Actual', color_continuous_scale='Greens')
        st.plotly_chart(fig_pareto, use_container_width=True)

        st.subheader("Distribución por depósito")
        df_dep = stock_df_an.groupby("Deposito")["Stock Actual"].sum().reset_index()
        fig_dep = px.pie(df_dep, names="Deposito", values="Stock Actual",
                         color_discrete_sequence=px.colors.qualitative.Set2)
        fig_dep.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_dep, use_container_width=True)

        st.subheader("Resumen por depósito")
        df_resumen = stock_df_an.groupby("Deposito").agg(
            Productos=("Producto","nunique"),
            Stock_Total=("Stock Actual","sum"),
            Stock_Promedio=("Stock Actual","mean")
        ).reset_index()
        df_resumen["Stock_Promedio"] = df_resumen["Stock_Promedio"].round(1)
        st.dataframe(df_resumen, use_container_width=True, hide_index=True)

        # Cruce entregas vs stock
        entregas_an = obtener_entregas()
        if not entregas_an.empty:
            st.markdown("---")
            st.subheader("🔗 Cruce: Stock actual vs Pendiente de entrega")
            pend_by_prod = entregas_an[entregas_an["pendiente"] > 0].groupby("producto")["pendiente"].sum().reset_index()
            pend_by_prod.columns = ["Producto", "Pendiente entregas"]
            stock_tot = stock_df_an.groupby("Producto")["Stock Actual"].sum().reset_index()
            cruce = stock_tot.merge(pend_by_prod, on="Producto", how="inner")
            cruce["Diferencia"] = cruce["Stock Actual"] - cruce["Pendiente entregas"]
            cruce["Estado"] = cruce["Diferencia"].apply(lambda x: "✅ Alcanza" if x >= 0 else "❌ Falta")
            st.dataframe(cruce, use_container_width=True, hide_index=True)
    else:
        st.info("Sin datos para analizar.")

# ===================== TAB 6: CONFIGURACIÓN =====================
with tab6:
    st.subheader("⚙️ Configuración")

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
    st.markdown("#### 📂 Importar datos de stock")
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
                st.success(f"✅ Importación exitosa. {filas_ok} registros cargados. Movimientos manuales conservados.")
                st.rerun()
            else:
                cols_enc = ', '.join(df_import.columns.tolist())
                st.error(f"❌ Columnas requeridas: ('articulo' o 'descripcion_1') y 'stock_actual'. Encontradas: {cols_enc}")
        except Exception as e: 
            st.error(f"❌ Error al procesar el archivo: {e}")

    st.markdown("---")
    st.markdown("#### 🗑️ Zona peligrosa")
    with st.expander("⚠️ Borrar todos los datos"):
        st.warning("Esta acción elimina TODOS los productos, movimientos y entregas. No se puede deshacer.")
        confirmar = st.text_input("Escribí CONFIRMAR para habilitar el botón", key="confirm_borrar")
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
                    conn.commit()
                    conn.close()
                    st.success("Entregas eliminadas.")
                    st.rerun()

st.markdown("---")
st.caption("Creado por Ignacio Diaz")
