import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import numpy as np
import cv2
import io

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

def decodificar_qr(foto_input):
    if foto_input is not None:
        try:
            file_bytes = np.asarray(bytearray(foto_input.read()), dtype=np.uint8)
            opencv_image = cv2.imdecode(file_bytes, 1)
            detector = cv2.QRCodeDetector()
            valor, pts, qr_rect = detector.detectAndDecode(opencv_image)
            return valor if valor else None
        except:
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
        # MEJORA: Cambio de camera_input por file_uploader para mayor compatibilidad con botones OK/Aceptar
        with st.expander("📷 Escanear QR (Cámara o Galería)"):
            foto = st.file_uploader("Subí una foto del QR para filtrar", type=["jpg", "png", "jpeg"])
            if foto:
                codigo = decodificar_qr(foto)
                if codigo:
                    matches = [p for p in stock_df["Producto"].unique() if codigo.lower() in p.lower()]
                    if matches:
                        st.session_state.qr_detectado = matches[0]
                        st.success(f"✅ Producto identificado: {matches[0]}")
                    else:
                        st.error(f"❌ Código detectado: '{codigo}'. No coincide con ningún producto.")
                else:
                    st.warning("⚠️ No se detectó un código QR nítido en la imagen.")

        st.subheader("🔍 Filtros de Búsqueda")
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            lista_productos = ["Todos"] + sorted(stock_df["Producto"].unique().tolist())
            idx_inicio = lista_productos.index(st.session_state.qr_detectado) if st.session_state.qr_detectado in lista_productos else 0
            f_prod = st.selectbox("Seleccionar Producto", lista_productos, index=idx_inicio)
        
        with c2: 
            f_lote = st.text_input("Filtrar Lote", placeholder="Ej: AF05...")
        
        with c3: 
            f_depo = st.text_input("Depósito Exacto", placeholder="Ej: 0")
        
        with c4: 
            hide_neg = st.toggle("Solo disponible", value=True)

        df_f = stock_df.copy()
        if f_prod != "Todos":
            df_f = df_f[df_f["Producto"] == f_prod]
        if f_lote: 
            df_f = df_f[df_f["Lote"].str.contains(f_lote, case=False)]
        if f_depo: 
            df_f = df_f[df_f["Deposito"].astype(str) == str(f_depo)]
        if hide_neg: 
            df_f = df_f[df_f["Stock Actual"] > 0]

        # --- MEJORA: DESCARGA PROFESIONAL EN EXCEL ---
        if not df_f.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_f.to_excel(writer, index=False, sheet_name='Stock')
                workbook  = writer.book
                worksheet = writer.sheets['Stock']
                
                # Formato: Encabezado verde claro con bordes
                header_format = workbook.add_format({
                    'bold': True, 
                    'fg_color': '#D7E4BC', 
                    'border': 1,
                    'align': 'center'
                })
                
                for col_num, value in enumerate(df_f.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    worksheet.set_column(col_num, col_num, 20)
                
                worksheet.autofilter(0, 0, len(df_f), len(df_f.columns) - 1)
            
            st.download_button(
                label="📥 Descargar Stock en Excel (.xlsx)",
                data=output.getvalue(),
                file_name=f'stock_agro_{datetime.now().strftime("%d%m%Y")}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )

        st.markdown("---")
        
        if not df_f.empty:
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
            st.info("No se encontraron resultados con los filtros aplicados.")

with tab2:
    if not stock_df.empty:
        st.subheader("📋 Listado Consolidado")
        st.dataframe(stock_df, use_container_width=True, hide_index=True)

with tab3:
    if not stock_df.empty:
        st.subheader("📊 Análisis de Stock Real")
        df_grafico = stock_df[stock_df["Stock Actual"] > 0]
        if not df_grafico.empty:
            depo_stats = df_grafico.groupby("Deposito")["Stock Actual"].sum().reset_index()
            fig = px.bar(depo_stats, x='Deposito', y='Stock Actual', 
                         title="Existencias Totales por Depósito",
                         labels={'Stock Actual': 'Cantidad', 'Deposito': 'N° Depósito'},
                         color='Deposito', text_auto='.2s')
            fig.update_layout(xaxis_type='category')
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        st.subheader("📋 Resumen por Unidad y Depósito")
        tabla_resumen = stock_df.pivot_table(index="Deposito", columns="Unidad", values="Stock Actual", aggfunc="sum", fill_value=0)
        st.dataframe(tabla_resumen.style.format("{:.2f}"), use_container_width=True)

with tab4:
    st.subheader("⚙️ Importar desde MacroGest")
    archivo = st.file_uploader("Subí el archivo Export (Excel o CSV)", type=["xlsx", "csv"])
    
    if archivo:
        try:
            df_import = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
            df_import.columns = df_import.columns.str.strip().str.lower()
            
            st.write("Vista previa:")
            st.dataframe(df_import.head(3), use_container_width=True)
            
            if st.button("🚀 INICIAR PROCESAMIENTO"):
                with st.spinner('Sincronizando...'):
                    borrar_datos_totales()
                    conn = conectar_db()
                    cursor = conn.cursor()
                    
                    # Columnas dinámicas
                    col_nom = 'descripcion_1' if 'descripcion_1' in df_import.columns else df_import.columns[1]
                    col_stk = 'stock_actual' if 'stock_actual' in df_import.columns else 'stock actual'
                    col_uni = 'unidad_medida' if 'unidad_medida' in df_import.columns else 'unidad'
                    col_lot = 'lote' if 'lote' in df_import.columns else 'lotes'
                    col_dep = 'deposito' if 'deposito' in df_import.columns else 'dep'
                    
                    for _, row in df_import.iterrows():
                        nom = str(row[col_nom]).strip()
                        stk = float(row[col_stk])
                        uni = str(row[col_uni]).strip() if col_uni in df_import.columns and pd.notna(row[col_uni]) else "UN"
                        lot = str(row[col_lot]).strip() if col_lot in df_import.columns and pd.notna(row[col_lot]) else "S/L"
                        dep = str(row[col_dep]).strip() if col_dep in df_import.columns and pd.notna(row[col_dep]) else "0"
                        
                        cursor.execute("INSERT OR IGNORE INTO productos (nombre, unidad) VALUES (?,?)", (nom, uni))
                        cursor.execute("SELECT id_producto FROM productos WHERE nombre = ?", (nom,))
                        id_p = cursor.fetchone()[0]
                        cursor.execute("""
                            INSERT INTO movimientos (fecha_hora, tipo_movimiento, id_producto, cantidad, lote, deposito, referencia) 
                            VALUES (?,?,?,?,?,?,?)
                        """, (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada", id_p, stk, lot, dep, "CARGA_MACRO"))
                    
                    conn.commit()
                    conn.close()
                    st.success("✅ Datos importados correctamente.")
                    st.rerun()
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")

st.markdown("---")
st.caption("Desarrollado por Ignacio Diaz")
