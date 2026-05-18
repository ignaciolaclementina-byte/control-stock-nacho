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

# Estilos profesionales mantenidos
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
    # Agregamos la columna 'codigo' a la tabla de productos
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
    # Asegurar que las columnas existan si la DB ya estaba creada
    try: cursor.execute("ALTER TABLE productos ADD COLUMN codigo TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE movimientos ADD COLUMN deposito TEXT DEFAULT '0'")
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
    # Agrupamos incluyendo el Código
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

def descargar_excel_limpio(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Stock_Actual')
    return output.getvalue()

inicializar_db()

# --- 3. INTERFAZ ---
st.title("🧪 Control de Depósito Inteligente")

# Estado para el buscador (permite que el QR llene el campo de búsqueda)
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

tab1, tab2, tab3, tab4 = st.tabs(["⚡ Panel de Control", "📋 Historial Completo", "📊 Análisis", "⚙️ Configuración"])

with tab1:
    stock_df = obtener_stock_full()
    
    if stock_df.empty:
        st.warning("⚠️ No hay datos cargados. Por favor, subí el archivo en la pestaña 'Configuración'.")
    else:
        st.markdown("### 🔍 Identificación de Producto")
        c_cam1, c_cam2 = st.columns([3, 1])
        
        with c_cam1:
            # Buscador por nombre o por código
            f_search = st.text_input("Buscar por Nombre o Código de Producto", 
                                     value=st.session_state.search_query,
                                     placeholder="Ej: Dicamba o 10007...")
            st.session_state.search_query = f_search

        with c_cam2:
            foto = st.file_uploader("📷 Escanear QR", type=["jpg", "png", "jpeg"])
            if foto:
                codigo_qr = decodificar_qr_reforzado(foto)
                if codigo_qr:
                    st.session_state.search_query = codigo_qr
                    st.success(f"Detectado: {codigo_qr}")
                    st.rerun()

        st.markdown("---")
        
        # Filtros secundarios
        c1, c2, c3 = st.columns(3)
        with c1: f_lote = st.text_input("Filtrar por Lote", placeholder="Todos")
        with c2: f_depo = st.text_input("Filtrar por Depósito", placeholder="Ej: 55")
        with c3: hide_neg = st.toggle("Solo con stock", value=True)

        # Lógica de filtrado
        df_f = stock_df.copy()
        if st.session_state.search_query:
            # Filtra si el texto está en el nombre O en el código
            df_f = df_f[
                (df_f["Producto"].str.contains(st.session_state.search_query, case=False)) | 
                (df_f["Código"].astype(str).str.contains(st.session_state.search_query, case=False))
            ]
        if f_lote: 
            df_f = df_f[df_f["Lote"].astype(str).str.contains(f_lote, case=False)]
        if f_depo: 
            df_f = df_f[df_f["Deposito"].astype(str) == str(f_depo)]
        if hide_neg: 
            df_f = df_f[df_f["Stock Actual"] > 0]

        if not df_f.empty:
            excel_bin = descargar_excel_limpio(df_f)
            st.download_button(label="📥 Descargar Resultado Excel", data=excel_bin, file_name='stock_busqueda.xlsx')

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
        else:
            st.info("No se encontraron resultados para la búsqueda.")

with tab2:
    if not stock_df.empty:
        st.dataframe(stock_df, use_container_width=True, hide_index=True)

with tab3:
    if not stock_df.empty:
        st.subheader("📊 Análisis Consolidado (Suma por Código)")
        # Consolidamos ignorando lotes para ver el total del producto en el depósito
        df_consolidado = stock_df.groupby(["Producto", "Código", "Deposito", "Unidad"])["Stock Actual"].sum().reset_index()
        df_consolidado = df_consolidado[df_consolidado["Stock Actual"] > 0]
        
        st.dataframe(df_consolidado.sort_values(by="Stock Actual", ascending=False), use_container_width=True, hide_index=True)

with tab4:
    st.subheader("⚙️ Sincronización con MacroGest")
    archivo = st.file_uploader("Subí el archivo Export (Excel/CSV)", type=["xlsx", "csv"])
    if archivo and st.button("🚀 ACTUALIZAR TODO"):
        with st.spinner('Procesando...'):
            try:
                if archivo.name.endswith('.csv'):
                    df_import = pd.read_csv(archivo, sep=None, engine='python', decimal=',', encoding='latin1')
                else:
                    df_import = pd.read_excel(archivo)
                
                df_import.columns = [str(c).strip().lower() for c in df_import.columns]
                
                # Buscamos columnas clave incluyendo 'codigo'
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
                        cod_val = str(row[col_cod]).strip() if col_cod else "S/C"
                        
                        try:
                            val_raw = str(row[col_stock])
                            if "," in val_raw and "." in val_raw: val_raw = val_raw.replace('.', '').replace(',', '.')
                            elif "," in val_raw: val_raw = val_raw.replace(',', '.')
                            stk = float(val_raw)
                        except: stk = 0.0
                        
                        un = str(row[col_un]) if col_un else "LTS"
                        lt = str(row[col_lote]) if col_lote else "S/L"
                        dp = str(row[col_depo]) if col_depo else "0"

                        # Guardamos nombre y código
                        cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad, codigo) VALUES (?,?,?)", (nom, un, cod_val))
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (nom,))
                        id_p = cursor.fetchone()[0]
                        cursor.execute("""
                            INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito) 
                            VALUES (?,?,?,?,?,?)
                        """, (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, stk, lt, dp))
                    
                    conn.commit(); conn.close()
                    st.success("✅ Sistema actualizado con códigos de producto.")
                    st.rerun()
                else:
                    st.error("No se encontraron las columnas necesarias en el archivo.")
            except Exception as e:
                st.error(f"Error al procesar: {e}")

st.markdown("---")
st.caption("Desarrollado por Ignacio Diaz")
