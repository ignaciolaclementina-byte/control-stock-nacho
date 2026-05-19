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
st.set_page_config(page_title="Control de Depósito Nacho", layout="wide", initial_sidebar_state="collapsed")

# Estilos de Interfaz de Alta Performance
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    
    /* Tarjetas de Stock Optimizadas */
    .stock-card {
        background-color: white; 
        padding: 16px; 
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); 
        margin-bottom: 15px;
        border: 1px solid #edf2f7;
        position: relative;
        transition: transform 0.2s;
    }
    .stock-card:hover { transform: translateY(-3px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    
    .card-normal { border-left: 6px solid #28a745; } 
    .card-low { border-left: 6px solid #ffc107; }      
    .card-warning { border-left: 6px solid #dc3545; } 
    
    .status-badge {
        position: absolute;
        top: 10px;
        right: 10px;
        font-size: 0.65rem;
        padding: 2px 7px;
        border-radius: 8px;
        color: white;
        font-weight: 800;
    }
    .bg-normal { background-color: #28a745; }
    .bg-low { background-color: #ffc107; color: #000; }
    .bg-warning { background-color: #dc3545; }

    .stock-title { font-size: 0.9rem; color: #1a202c; font-weight: 700; margin-bottom: 6px; line-height: 1.2; min-height: 2.4em; }
    .stock-value { font-size: 1.6rem; color: #007bff; font-weight: 800; display: block; }
    .stock-unit { font-size: 0.8rem; color: #718096; font-weight: 400; }
    
    .stock-info { 
        margin-top: 10px; 
        padding-top: 8px; 
        border-top: 1px solid #f0f4f8; 
        font-size: 0.75rem; 
        color: #4a5568; 
    }
    .label-blue { background-color: #e7f3ff; color: #007bff; padding: 1px 5px; border-radius: 4px; font-weight: bold; }
    
    /* Estilo WhatsApp */
    .ws-link {
        text-decoration: none;
        color: #25D366;
        font-weight: bold;
        font-size: 0.75rem;
        display: inline-flex;
        align-items: center;
        margin-top: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNCIONES DE BASE DE DATOS (Mantenidas íntegras) ---
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
    conn.commit(); conn.close()

def borrar_datos_totales():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM movimientos")
    cursor.execute("DELETE FROM productos")
    conn.commit(); conn.close()

def obtener_stock_full():
    conn = conectar_db()
    query = """
        SELECT p.nombre as Producto, p.codigo as Código, p.unidad as Unidad, m.lote as Lote, m.deposito as Deposito, 
               m.tipo_movimiento, m.cantidad 
        FROM movimientos m 
        JOIN productos p ON m.id_producto = p.id_producto
    """
    try: df = pd.read_sql_query(query, conn)
    except: df = pd.DataFrame()
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
            img_cv = cv2.cvtColor(np.array(img_pil.convert('RGB')), cv2.COLOR_RGB2BGR)
            valor, _, _ = cv2.QRCodeDetector().detectAndDecode(img_cv)
            return valor.strip() if valor else None
        except: return None
    return None

def descargar_excel_limpio(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Stock_Actual')
    return output.getvalue()

inicializar_db()

# --- 3. INTERFAZ ---
st.title("🧪 Depósito Inteligente")

if 'qr_detectado' not in st.session_state:
    st.session_state.qr_detectado = "Todos"

tab1, tab2, tab3, tab4 = st.tabs(["⚡ Operación", "📋 Historial", "📊 Análisis", "⚙️ Sistema"])

with tab1:
    stock_df = obtener_stock_full()
    
    if stock_df.empty:
        st.warning("⚠️ Sin datos. Cargue el archivo en 'Sistema'.")
    else:
        # Cabecera Compacta
        c_k1, c_k2, c_k3 = st.columns(3)
        with c_k1: st.metric("Productos", len(stock_df["Producto"].unique()))
        with c_k2: st.metric("Alertas", len(stock_df[stock_df["Stock Actual"] < 20]))
        with c_k3: st.metric("Depósitos", stock_df["Deposito"].nunique())

        st.markdown("---")
        
        # Operatoria de Búsqueda
        c_bus1, c_bus2 = st.columns([3, 1])
        with c_bus1:
            search_query = st.text_input("🔍 Buscar por nombre o código", placeholder="Escriba para filtrar...", key="search_main")
        with c_bus2:
            foto = st.file_uploader("📷 QR", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

        # Filtros rápidos
        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1: f_lote = st.text_input("Lote", placeholder="Filtrar lote...")
        with c_f2: f_depo = st.text_input("Depósito", placeholder="Filtrar dep...")
        with c_f3: hide_neg = st.toggle("Solo con stock", value=True)

        # Procesamiento de Filtros
        df_f = stock_df.copy()
        
        if foto:
            leido = decodificar_qr_reforzado(foto)
            if leido: 
                df_f = df_f[df_f["Código"].astype(str) == str(leido)]
                st.success(f"Código detectado: {leido}")

        if search_query:
            df_f = df_f[df_f["Producto"].str.contains(search_query, case=False) | df_f["Código"].astype(str).str.contains(search_query, case=False)]
        if f_lote: df_f = df_f[df_f["Lote"].astype(str).str.contains(f_lote, case=False)]
        if f_depo: df_f = df_f[df_f["Deposito"].astype(str) == str(f_depo)]
        if hide_neg: df_f = df_f[df_f["Stock Actual"] > 0]

        # Render de Tarjetas
        if not df_f.empty:
            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items[:40]): 
                with cols_grid[i % 4]:
                    stk = item['Stock Actual']
                    if stk <= 0: clase, txt, bg = "card-warning", "SIN STOCK", "bg-warning"
                    elif stk < 20: clase, txt, bg = "card-low", "REPONER", "bg-low"
                    else: clase, txt, bg = "card-normal", "ÓPTIMO", "bg-normal"

                    # WhatsApp Link
                    msg = urllib.parse.quote(f"Consulta Stock: {item['Producto']} - Lote: {item['Lote']} - Stock: {stk}")
                    ws_url = f"https://wa.me/5493406123456?text={msg}" # Cambiar al número deseado

                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="status-badge {bg}">{txt}</div>
                            <div class="stock-title">{item['Producto']}</div>
                            <span class="stock-value">{stk:,.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info">
                                <b>ID:</b> {item['Código']} | <b>Lote:</b> {item['Lote']}<br>
                                <b>Dep:</b> <span class="label-blue">{item['Deposito']}</span><br>
                                <a href="{ws_url}" class="ws-link">📲 Reportar por WhatsApp</a>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No hay productos que coincidan.")

with tab2:
    if not stock_df.empty:
        st.dataframe(stock_df, use_container_width=True, hide_index=True)
        excel_bin = descargar_excel_limpio(stock_df)
        st.download_button("📥 Descargar Excel Completo", data=excel_bin, file_name='stock.xlsx')

with tab3:
    if not stock_df.empty:
        st.subheader("🔝 Top 10 Productos")
        df_p = stock_df.groupby("Producto")["Stock Actual"].sum().sort_values(ascending=False).head(10).reset_index()
        fig = px.bar(df_p, x='Stock Actual', y='Producto', orientation='h', color='Stock Actual', color_continuous_scale='Greens')
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("⚙️ Importación MacroGest")
    archivo = st.file_uploader("Subir Excel/CSV", type=["xlsx", "csv"])
    if archivo and st.button("🚀 ACTUALIZAR BASE DE DATOS"):
        with st.spinner('Procesando...'):
            try:
                df_import = pd.read_csv(archivo, sep=None, engine='python', decimal=',', encoding='latin1') if archivo.name.endswith('.csv') else pd.read_excel(archivo)
                df_import.columns = [str(c).strip().lower() for c in df_import.columns]
                
                # Mapeo inteligente de columnas
                c_c = next((c for c in df_import.columns if 'cod' in c), None)
                c_p = next((c for c in df_import.columns if 'prod' in c or 'desc' in c), None)
                c_s = next((c for c in df_import.columns if 'stock' in c or 'act' in c), None)
                c_d = next((c for c in df_import.columns if 'dep' in c or 'sect' in c), None)
                c_l = next((c for c in df_import.columns if 'lote' in c), None)
                c_u = next((c for c in df_import.columns if 'unid' in c), None)

                if c_p and c_s:
                    borrar_datos_totales()
                    conn = conectar_db(); cursor = conn.cursor()
                    for _, row in df_import.iterrows():
                        nom = str(row[c_p]).strip()
                        cod = str(row[c_c]).strip() if c_c else "S/C"
                        try:
                            val = str(row[c_s]).replace('.', '').replace(',', '.')
                            stk = float(val)
                        except: stk = 0.0
                        
                        cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad, codigo) VALUES (?,?,?)", (nom, str(row[c_u]) if c_u else "LTS", cod))
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (nom,))
                        id_p = cursor.fetchone()[0]
                        cursor.execute("INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito) VALUES (?,?,?,?,?,?)",
                                       (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, stk, str(row[c_l]) if c_l else "S/L", str(row[c_d]) if c_d else "0"))
                    conn.commit(); conn.close()
                    st.success("✅ Sistema actualizado.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>Creado por Ignacio Diaz</p>", unsafe_allow_html=True)
