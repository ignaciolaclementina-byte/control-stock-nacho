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

# Estilos profesionales con semáforo de alertas y diseño optimizado
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
        transition: transform 0.2s;
    }
    .stock-card:hover { transform: translateY(-5px); }

    /* SEMÁFORO DE ALERTAS DINÁMICO */
    .card-normal { border-left: 8px solid #28a745; }  /* Verde: OK */
    .card-low { border-left: 8px solid #ffc107; }     /* Amarillo: Bajo */
    .card-warning { border-left: 8px solid #dc3545; }  /* Rojo: Crítico */
    
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
        SELECT p.nombre as Producto, p.unidad as Unidad, m.lote as Lote, m.deposito as Deposito, 
               m.tipo_movimiento, m.cantidad 
        FROM movimientos m 
        JOIN productos p ON m.id_producto = p.id_producto
    """
    try: df = pd.read_sql_query(query, conn)
    except: df = pd.DataFrame()
    conn.close()
    if df.empty: return pd.DataFrame()
    df["neta"] = df.apply(lambda r: r["cantidad"] if r["tipo_movimiento"] == "Entrada" else -r["cantidad"], axis=1)
    res = df.groupby(["Producto", "Unidad", "Lote", "Deposito"])["neta"].sum().reset_index()
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
            
            # Intento con escala de grises para baja luz
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            valor, _, _ = detector.detectAndDecode(gray)
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

tab1, tab2, tab3, tab4 = st.tabs(["⚡ Panel de Control", "📋 Historial", "📊 Análisis Pro", "⚙️ Configuración"])

with tab1:
    stock_df = obtener_stock_full()
    if stock_df.empty:
        st.warning("⚠️ Sin datos. Cargá el Excel en la pestaña Configuración.")
    else:
        # Buscador y Escáner en la parte superior
        col_search, col_qr = st.columns([3, 1])
        with col_search:
            search_query = st.text_input("🔍 Buscar por Producto o Lote...", "").lower()
        with col_qr:
            foto = st.file_uploader("Escanear QR", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

        if foto:
            codigo = decodificar_qr_reforzado(foto)
            if codigo:
                matches = [p for p in stock_df["Producto"].unique() if codigo.lower() in p.lower()]
                if matches:
                    st.session_state.qr_detectado = matches[0]
                    st.success(f"✅ Detectado: {matches[0]}")
            else:
                st.error("No se pudo leer el QR.")

        # Filtros Rápidos
        c1, c2, c3 = st.columns(3)
        with c1:
            lista_p = ["Todos"] + sorted(stock_df["Producto"].unique().tolist())
            idx = lista_p.index(st.session_state.qr_detectado) if st.session_state.qr_detectado in lista_p else 0
            f_prod = st.selectbox("Filtrar Producto", lista_p, index=idx)
        with c2:
            f_depo = st.multiselect("Filtrar Depósitos", sorted(stock_df["Deposito"].unique()))
        with c3:
            ver_alertas = st.toggle("Ver solo Alertas ⚠️", value=False)

        # Aplicar Lógica de Filtros
        df_f = stock_df.copy()
        if search_query:
            df_f = df_f[df_f["Producto"].str.lower().str.contains(search_query) | df_f["Lote"].str.lower().str.contains(search_query)]
        if f_prod != "Todos":
            df_f = df_f[df_f["Producto"] == f_prod]
        if f_depo:
            df_f = df_f[df_f["Deposito"].isin(f_depo)]
        if ver_alertas:
            df_f = df_f[df_f["Stock Actual"] < 50] # Umbral de alerta

        # Botón de Descarga
        if not df_f.empty:
            excel_bin = descargar_excel_limpio(df_f)
            st.download_button("📥 Exportar Resultados", data=excel_bin, file_name='stock_filtrado.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            # Render de Tarjetas con Semáforo
            st.write("")
            cols_grid = st.columns(4)
            for i, row in enumerate(df_f.to_dict('records')[:40]):
                with cols_grid[i % 4]:
                    val = row['Stock Actual']
                    # Definición de color del semáforo
                    if val <= 0: clase = "card-warning"
                    elif val < 50: clase = "card-low"
                    else: clase = "card-normal"

                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{row['Producto']}</div>
                            <span class="stock-value">{val:,.1f} <small class="stock-unit">{row['Unidad']}</small></span>
                            <div class="stock-info">
                                <b>Dep:</b> <span class="label-blue">{row['Deposito']}</span> | <b>Lote:</b> {row['Lote']}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

with tab2:
    if not stock_df.empty:
        st.dataframe(stock_df, use_container_width=True, hide_index=True)

with tab3:
    if not stock_df.empty:
        st.subheader("📊 Dashboard de Control")
        df_ana = stock_df[stock_df["Stock Actual"] > 0].copy()
        
        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Unidades Totales", f"{df_ana['Stock Actual'].sum():,.0f}")
        k2.metric("Variedad de Lotes", len(df_ana))
        k3.metric("Lotes en Alerta", len(df_ana[df_ana['Stock Actual'] < 50]))

        st.markdown("---")
        c_pie, c_bar = st.columns(2)
        with c_pie:
            fig_p = px.pie(df_ana.groupby("Deposito")["Stock Actual"].sum().reset_index(), 
                         values='Stock Actual', names='Deposito', hole=0.4, title="Stock por Depósito",
                         color_discrete_sequence=px.colors.qualitative.Safe)
            st.plotly_chart(fig_p, use_container_width=True)
        with c_bar:
            df_top = df_ana.groupby("Producto")["Stock Actual"].sum().sort_values(ascending=False).head(10).reset_index()
            fig_b = px.bar(df_top, x='Stock Actual', y='Producto', orientation='h', title="Top 10 Productos",
                         color='Stock Actual', color_continuous_scale='Blues')
            st.plotly_chart(fig_b, use_container_width=True)

with tab4:
    st.subheader("⚙️ Sincronización con MacroGest")
    archivo = st.file_uploader("Subí el reporte (Excel o CSV)", type=["xlsx", "csv"])
    if archivo and st.button("🚀 ACTUALIZAR SISTEMA"):
        with st.spinner('Procesando...'):
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
            st.success("✅ Base de datos actualizada."); st.rerun()

st.markdown("---")
st.caption("Desarrollado por Ignacio Diaz")
