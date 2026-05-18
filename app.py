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
        box-shadow: 0 4px 6px rgba(0,0,0,0.07); 
        margin-bottom: 12px;
        border: 1px solid #e1e4e8;
    }
    .card-normal { border-left: 6px solid #28a745; } 
    .card-warning { border-left: 6px solid #dc3545; } 
    
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
    .label-blue { color: #007bff; font-weight: bold; }
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
            unidad TEXT NOT NULL
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
    try:
        cursor.execute("ALTER TABLE movimientos ADD COLUMN deposito TEXT DEFAULT '0'")
    except:
        pass
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
        SELECT p.nombre as Producto, p.unidad as Unidad, m.lote as Lote, m.deposito as Deposito, 
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
    res = df.groupby(["Producto", "Unidad", "Lote", "Deposito"])["neta"].sum().reset_index()
    return res.rename(columns={"neta": "Stock Actual"})

def decodificar_qr_reforzado(foto_input):
    if foto_input is not None:
        try:
            # RESETEO DE PUNTERO
            foto_input.seek(0)
            
            # Conversión de imagen
            img_pil = Image.open(foto_input)
            img_np = np.array(img_pil.convert('RGB'))
            img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            
            detector = cv2.QRCodeDetector()
            
            # INTENTO 1: Imagen Original
            valor, _, _ = detector.detectAndDecode(img_cv)
            if valor: return valor.strip()
            
            # INTENTO 2: Escala de Grises + Contraste (CLAHE)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            res_gray = clahe.apply(gray)
            valor, _, _ = detector.detectAndDecode(res_gray)
            if valor: return valor.strip()
            
            # INTENTO 3: Binarización (Blanco y Negro puro)
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            valor, _, _ = detector.detectAndDecode(thresh)
            if valor: return valor.strip()
            
            return None
        except Exception as e:
            st.error(f"Error técnico: {e}")
            return None
    return None

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
            # Procesamos automáticamente al subir o al apretar el botón
            with st.spinner("Procesando imagen..."):
                codigo = decodificar_qr_reforzado(foto)
                if codigo:
                    matches = [p for p in stock_df["Producto"].unique() if codigo.lower() in p.lower()]
                    if matches:
                        if st.session_state.qr_detectado != matches[0]:
                            st.session_state.qr_detectado = matches[0]
                            st.success(f"✅ Producto: {matches[0]}")
                            st.rerun()
                    else:
                        st.error(f"❌ El código '{codigo}' no figura en el stock.")
                elif btn_procesar:
                    st.warning("⚠️ No se encontró QR. Intentá con más luz o centrando el código.")

        st.markdown("---")
        st.subheader("🔍 Filtros y Resultados")
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            lista_productos = ["Todos"] + sorted(stock_df["Producto"].unique().tolist())
            idx_inicio = lista_productos.index(st.session_state.qr_detectado) if st.session_state.qr_detectado in lista_productos else 0
            f_prod = st.selectbox("Producto Seleccionado", lista_productos, index=idx_inicio, key="prod_select")
            st.session_state.qr_detectado = f_prod
        
        with c2: f_lote = st.text_input("Filtrar Lote", placeholder="Ej: AF05...")
        with c3: f_depo = st.text_input("Depósito Exacto", placeholder="Ej: 0")
        with c4: hide_neg = st.toggle("Solo disponible", value=True)

        df_f = stock_df.copy()
        if st.session_state.qr_detectado != "Todos":
            df_f = df_f[df_f["Producto"] == st.session_state.qr_detectado]
        if f_lote: 
            df_f = df_f[df_f["Lote"].astype(str).str.contains(f_lote, case=False)]
        if f_depo: 
            df_f = df_f[df_f["Deposito"].astype(str) == str(f_depo)]
        if hide_neg: 
            df_f = df_f[df_f["Stock Actual"] > 0]

        if not df_f.empty:
            # Opción de descarga
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_f.to_excel(writer, index=False, sheet_name='Stock')
            st.download_button(label="📥 Descargar Excel Filtrado", data=output.getvalue(), file_name='stock_filtrado.xlsx')

            # Render de tarjetas
            items = df_f.to_dict('records')
            cols_grid = st.columns(4)
            for i, item in enumerate(items[:40]): 
                with cols_grid[i % 4]:
                    clase = "card-normal" if item['Stock Actual'] > 0 else "card-warning"
                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{item['Producto']}</div>
                            <span class="stock-value">{item['Stock Actual']:.1f} <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info">
                                <b>📍 Dep:</b> <span class="label-blue">{item['Deposito']}</span> | 
                                <b>🏷️ Lote:</b> {item['Lote']}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No hay resultados para los filtros seleccionados.")

with tab2:
    if not stock_df.empty:
        st.dataframe(stock_df, use_container_width=True, hide_index=True)

with tab3:
    if not stock_df.empty:
        fig = px.bar(stock_df[stock_df["Stock Actual"] > 0].groupby("Deposito")["Stock Actual"].sum().reset_index(), 
                     x='Deposito', y='Stock Actual', color='Deposito', text_auto='.2s')
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("⚙️ Importación de Datos")
    archivo = st.file_uploader("Subí el Export de MacroGest (Excel o CSV)", type=["xlsx", "csv"])
    if archivo and st.button("🚀 ACTUALIZAR SISTEMA"):
        with st.spinner('Sincronizando base de datos...'):
            borrar_datos_totales()
            conn = conectar_db(); cursor = conn.cursor()
            df_import = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
            df_import.columns = df_import.columns.str.strip().str.lower()
            
            for _, row in df_import.iterrows():
                nom = str(row.get('descripcion_1', row.iloc[:,1])).strip()
                stk = float(row.get('stock_actual', 0))
                cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad) VALUES (?,?)", (nom, str(row.get('unidad_medida', 'UN'))))
                cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (nom,))
                id_p = cursor.fetchone()[0]
                cursor.execute("INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito) VALUES (?,?,?,?,?,?)",
                               (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, stk, str(row.get('lote', 'S/L')), str(row.get('deposito', '0'))))
            conn.commit(); conn.close()
            st.success("✅ Base de datos actualizada con éxito.")
            st.rerun()

st.markdown("---")
st.caption("Desarrollado por Ignacio Diaz")
