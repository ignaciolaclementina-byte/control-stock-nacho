import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import numpy as np
import cv2
import io
from PIL import Image

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
        box-shadow: 0 4px 66px rgba(0,0,0,0.07); 
        margin-bottom: 12px;
        border: 1px solid #e1e4e8;
    }
    .card-normal { border-left: 8px solid #28a745; } 
    .card-low { border-left: 8px solid #ffc107; }      
    .card-warning { border-left: 8px solid #dc3545; } 
    .stock-title { font-size: 0.95rem; color: #1a1c21; font-weight: 700; margin-bottom: 8px; line-height: 1.2; min-height: 2.4em; }
    .stock-value { font-size: 1.5rem; color: #007bff; font-weight: 800; display: block; }
    .stock-unit { font-size: 0.8rem; color: #6c757d; font-weight: 400; }
    .stock-info { 
        margin-top: 10px; 
        padding-top: 8px; 
        border-top: 1px solid #f0f2f6; 
        font-size: 0.8rem; 
        color: #495057; 
    }
    .label-blue { background-color: #e7f3ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
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
            img_np = np.array(img_pil.convert('RGB'))
            img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            detector = cv2.QRCodeDetector()
            valor, _, _ = detector.detectAndDecode(img_cv)
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
st.title("🧪 Control de Depósito Inteligente")

if 'qr_detectado' not in st.session_state:
    st.session_state.qr_detectado = "Todos"

tab1, tab2, tab3, tab4 = st.tabs(["⚡ Panel de Control", "📋 Historial Completo", "📊 Análisis", "⚙️ Configuración"])

with tab1:
    stock_df = obtener_stock_full()
    
    if stock_df.empty:
        st.warning("⚠️ No hay datos cargados. Por favor, subí el archivo en la pestaña 'Configuración'.")
    else:
        st.markdown("### 📷 Identificar Producto")
        c_cam1, c_cam2 = st.columns([3, 1])
        
        with c_cam1:
            foto = st.file_uploader("Sacá foto al QR", type=["jpg", "png", "jpeg"], key="uploader_qr")
        
        with c_cam2:
            st.write("") 
            btn_procesar = st.button("🔍 ESCANEAR QR")
            if st.button("🔄 Limpiar"):
                st.session_state.qr_detectado = "Todos"
                st.rerun()

        if foto:
            with st.spinner("Procesando imagen..."):
                codigo_leido = decodificar_qr_reforzado(foto)
                if codigo_leido:
                    # Búsqueda por código o nombre
                    match = stock_df[(stock_df["Código"].astype(str) == str(codigo_leido)) | (stock_df["Producto"].str.contains(codigo_leido, case=False))]
                    if not match.empty:
                        res_prod = match["Producto"].iloc[0]
                        st.session_state.qr_detectado = res_prod
                        st.success(f"✅ Identificado: {res_prod}")
                        st.rerun()
                elif btn_procesar:
                    st.warning("⚠️ No se pudo leer el QR.")

        st.markdown("---")
        st.subheader("🔍 Filtros y Resultados")
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            # Lista que incluye Nombre y Código para facilitar la búsqueda visual
            opciones_busqueda = ["Todos"] + sorted(stock_df["Producto"].unique().tolist())
            idx_inicio = opciones_busqueda.index(st.session_state.qr_detectado) if st.session_state.qr_detectado in opciones_busqueda else 0
            f_prod = st.selectbox("Buscar por Nombre o Código", opciones_busqueda, index=idx_inicio)
            st.session_state.qr_detectado = f_prod
            
        with c2: f_lote = st.text_input("Lote", placeholder="Ej: AF05...")
        with c3: f_depo = st.text_input("Depósito", placeholder="Ej: 0")
        with c4: hide_neg = st.toggle("Solo con stock", value=True)

        df_f = stock_df.copy()
        
        # --- LÓGICA DE FILTRADO MEJORADA (PRODUCTO Y CÓDIGO) ---
        if st.session_state.qr_detectado != "Todos":
            df_f = df_f[df_f["Producto"] == st.session_state.qr_detectado]
            
        if f_lote: 
            df_f = df_f[df_f["Lote"].astype(str).str.contains(f_lote, case=False)]
        if f_depo: 
            df_f = df_f[df_f["Deposito"].astype(str) == str(f_depo)]
        if hide_neg: 
            df_f = df_f[df_f["Stock Actual"] > 0]

        if not df_f.empty:
            excel_bin = descargar_excel_limpio(df_f)
            st.download_button(label="📥 Descargar Excel", data=excel_bin, file_name='stock_actual.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items[:40]): 
                with cols_grid[i % 4]:
                    stk_val = item['Stock Actual']
                    clase = "card-warning" if stk_val <= 0 else "card-low" if stk_val < 20 else "card-normal"

                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{item['Producto']}</div>
                            <span class="stock-value">{stk_val:,.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info">
                                <b>🆔 Cód:</b> {item['Código']}<br>
                                <b>📍 Dep:</b> <span class="label-blue">{item['Deposito']}</span><br>
                                <b>🏷️ Lote:</b> {item['Lote']}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

with tab2:
    if not stock_df.empty:
        st.dataframe(stock_df, use_container_width=True, hide_index=True)

with tab3:
    if not stock_df.empty:
        st.subheader("📊 Análisis Consolidado")
        df_consolidado = stock_df.groupby(["Producto", "Deposito", "Unidad"])["Stock Actual"].sum().reset_index()
        df_consolidado = df_consolidado[df_consolidado["Stock Actual"] > 0] 
        
        c_filtro1, c_filtro2 = st.columns(2)
        with c_filtro1:
            sel_p = st.selectbox("Suma total de:", sorted(df_consolidado["Producto"].unique()))
        with c_filtro2:
            sel_d = st.selectbox("En depósito:", ["Todos"] + sorted(df_consolidado["Deposito"].unique().tolist()))
        
        df_target = df_consolidado[df_consolidado["Producto"] == sel_p]
        if sel_d != "Todos":
            df_target = df_target[df_target["Deposito"] == sel_d]
        
        suma_final = df_target["Stock Actual"].sum()
        st.metric(f"Total {sel_p}", f"{suma_final:,.1f} {df_target['Unidad'].iloc[0] if not df_target.empty else ''}")

        fig_vol = px.bar(df_consolidado.groupby("Deposito")["Stock Actual"].sum().reset_index(), 
                         x='Deposito', y='Stock Actual', color='Stock Actual', text_auto='.2s',
                         title="Stock total por sector")
        st.plotly_chart(fig_vol, use_container_width=True)

with tab4:
    st.subheader("⚙️ Importación MacroGest")
    archivo = st.file_uploader("Subí Excel o CSV", type=["xlsx", "csv"])
    if archivo and st.button("🚀 ACTUALIZAR TODO"):
        with st.spinner('Sincronizando...'):
            try:
                df_import = pd.read_csv(archivo, sep=None, engine='python', decimal=',', encoding='latin1') if archivo.name.endswith('.csv') else pd.read_excel(archivo)
                df_import.columns = [str(c).strip().lower() for c in df_import.columns]
                
                col_cod = next((c for c in df_import.columns if 'codigo' in c or 'código' in c), None)
                col_prod = next((c for c in df_import.columns if 'producto' in c or 'descripcion' in c), None)
                col_stock = next((c for c in df_import.columns if 'stock' in c or 'actual' in c), None)
                col_depo = next((c for c in df_import.columns if 'deposito' in c or 'sector' in c), None)
                col_lote = next((c for c in df_import.columns if 'lote' in c), None)
                col_un = next((c for c in df_import.columns if 'unidad' in c), None)

                if col_prod and col_stock:
                    borrar_datos_totales()
                    conn = conectar_db(); cursor = conn.cursor()
                    for _, row in df_import.iterrows():
                        nom = str(row[col_prod]).strip()
                        cod = str(row[col_cod]).strip() if col_cod else "S/C"
                        val_raw = str(row[col_stock]).strip()
                        stk_val = val_raw.replace('.', '').replace(',', '.') if "," in val_raw else val_raw
                        
                        try: stk = float(stk_val)
                        except: stk = 0.0
                        
                        cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad, codigo) VALUES (?,?,?)", (nom, str(row[col_un]) if col_un else "LTS", cod))
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (nom,))
                        id_p = cursor.fetchone()[0]
                        cursor.execute("INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito) VALUES (?,?,?,?,?,?)",
                                       (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, stk, str(row[col_lote]) if col_lote else "S/L", str(row[col_depo]) if col_depo else "0"))
                    conn.commit(); conn.close()
                    st.success("✅ Sistema actualizado correctamente.")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")

st.markdown("---")
st.caption("Desarrollado por Ignacio Diaz")
