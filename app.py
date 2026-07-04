"""
Control de Depósito Inteligente — La Clementina S.A.
Versión PRO: auth, transferencias, valorización, rotación,
             reportes, email, importación incremental, PDF.

Dependencias adicionales (instalar si no están):
    pip install streamlit pandas plotly numpy opencv-python pillow openpyxl
    pip install reportlab          # PDF reports (opcional)
    # Para PostgreSQL (opcional):
    # pip install psycopg2-binary
    # Setear variable de entorno DATABASE_URL=postgresql://...
"""

import streamlit as st
import pandas as pd
import sqlite3
import os
import re as _re
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import cv2
import io
from PIL import Image
import urllib.parse
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURACIÓN DE PÁGINA Y CSS
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gestión de Agroquímicos — LC", layout="wide")
st.markdown("""
<style>
.main{background-color:#f4f7f6}
.stButton>button{width:100%;border-radius:8px;font-weight:bold;height:3em}
.stock-card{background:white;padding:18px;border-radius:12px;
    box-shadow:0 4px 15px rgba(0,0,0,.05);margin-bottom:12px;
    border:1px solid #e1e4e8;position:relative}
.card-normal {border-left:8px solid #28a745}
.card-low    {border-left:8px solid #ffc107}
.card-warning{border-left:8px solid #dc3545}
.stock-title {font-size:.95rem;color:#1a1c21;font-weight:700;margin-bottom:8px;
    line-height:1.2;min-height:2.4em}
.stock-value {font-size:1.5rem;color:#007bff;font-weight:800;display:block}
.stock-unit  {font-size:.8rem;color:#6c757d;font-weight:400}
.stock-info  {margin-top:10px;padding-top:8px;border-top:1px solid #f0f2f6;
    font-size:.8rem;color:#495057}
.label-blue  {background:#e7f3ff;color:#007bff;padding:2px 6px;border-radius:4px;font-weight:bold}
.label-orange{background:#fff3cd;color:#856404;padding:2px 6px;border-radius:4px;font-weight:bold}
.neg-badge   {display:inline-block;background:#dc3545;color:white;font-size:.65rem;
    padding:1px 6px;border-radius:8px;font-weight:bold;margin-left:4px;vertical-align:middle}
.comp-badge  {display:inline-block;background:#fd7e14;color:white;font-size:.65rem;
    padding:1px 6px;border-radius:8px;font-weight:bold;margin-left:4px;vertical-align:middle}
.venc-badge  {display:inline-block;background:#6f42c1;color:white;font-size:.65rem;
    padding:1px 6px;border-radius:8px;font-weight:bold;margin-left:4px;vertical-align:middle}
.login-box   {max-width:400px;margin:80px auto;padding:30px;background:white;
    border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.1)}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2. CAPA DE DATOS — SQLite (local/dev) o PostgreSQL/Supabase (producción)
#    Configurar: st.secrets["DATABASE_URL"] = "postgresql://user:pass@host/db"
#    o variable de entorno DATABASE_URL en Streamlit Cloud Settings → Secrets
# ─────────────────────────────────────────────────────────────────────────────

def _get_db_url() -> str:
    try:
        return st.secrets.get("DATABASE_URL", "") or ""
    except Exception:
        return os.environ.get("DATABASE_URL", "")

_DB_URL     = _get_db_url()
IS_POSTGRES = bool(_DB_URL and "postgres" in _DB_URL.lower())

# Reglas de conflicto para INSERT OR REPLACE / INSERT OR IGNORE → PostgreSQL
_UPSERT_CONF = {
    "metadata":         ["clave"],
    "usuarios":         ["username"],
    "metas_campana":    ["campana", "vendedor", "producto"],
    "cartera_clientes": ["vendedor", "cliente", "campana"],
    "productos_foco":   ["campana", "producto"],
}
_IGNORE_CONF = {
    "productos":      ["nombre"],
    "productos_foco": ["campana", "producto"],
}
_OR_REPLACE_RE = _re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
    _re.IGNORECASE | _re.DOTALL,
)
_OR_IGNORE_RE = _re.compile(
    r"INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
    _re.IGNORECASE | _re.DOTALL,
)

def _adapt_pg(sql: str) -> str:
    """Traduce SQL SQLite → PostgreSQL: placeholders y variantes INSERT."""
    sql = sql.replace("?", "%s")
    m = _OR_REPLACE_RE.match(sql.strip())
    if m:
        table = m.group(1).strip()
        cols  = [c.strip() for c in m.group(2).split(",")]
        ph    = m.group(3).strip()
        conf  = _UPSERT_CONF.get(table)
        if conf:
            sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in conf)
            sql  = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) "
                    f"ON CONFLICT ({', '.join(conf)}) DO UPDATE SET {sets}")
    m2 = _OR_IGNORE_RE.match(sql.strip())
    if m2:
        table = m2.group(1).strip()
        cols  = [c.strip() for c in m2.group(2).split(",")]
        ph    = m2.group(3).strip()
        conf  = _IGNORE_CONF.get(table, [])
        ct    = f"ON CONFLICT ({', '.join(conf)}) DO NOTHING" if conf else "ON CONFLICT DO NOTHING"
        sql   = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) {ct}"
    return sql


class _Cur:
    """Cursor normalizado que adapta SQL según el backend."""
    __slots__ = ("_c", "_pg")

    def __init__(self, raw_cursor, pg: bool):
        self._c  = raw_cursor
        self._pg = pg

    def execute(self, sql: str, params=None):
        sql = _adapt_pg(sql) if self._pg else sql
        if params is not None:
            self._c.execute(sql, list(params) if isinstance(params, tuple) else params)
        else:
            self._c.execute(sql)
        return self

    def executemany(self, sql: str, seq):
        sql = _adapt_pg(sql) if self._pg else sql
        self._c.executemany(sql, seq)

    def fetchone(self):  return self._c.fetchone()
    def fetchall(self):  return self._c.fetchall()
    def __iter__(self):  return iter(self._c)

    @property
    def description(self): return self._c.description
    @property
    def rowcount(self):    return self._c.rowcount


class _DB:
    """Conexión unificada: sqlite3 o psycopg2 según DATABASE_URL."""

    def __init__(self):
        if IS_POSTGRES:
            import psycopg2
            url = _DB_URL.replace("postgres://", "postgresql://", 1)
            self._raw = psycopg2.connect(url)
            self._pg  = True
        else:
            self._raw = sqlite3.connect("stock_agroquimicos.db", check_same_thread=False)
            self._pg  = False

    def cursor(self) -> _Cur:
        return _Cur(self._raw.cursor(), self._pg)

    def execute(self, sql: str, params=()):
        cur = self.cursor()
        cur.execute(sql, params if params else None)
        return cur

    def commit(self): self._raw.commit()
    def close(self):  self._raw.close()

    def __enter__(self): return self
    def __exit__(self, *_):
        try:    self.commit()
        except: pass
        self.close()


def conectar_db() -> _DB:
    return _DB()


def _rsql(sql: str, conn, params=None) -> pd.DataFrame:
    """pd.read_sql_query con adaptación automática de placeholders."""
    raw = conn._raw if isinstance(conn, _DB) else conn
    if IS_POSTGRES and params:
        sql = sql.replace("?", "%s")
    try:
        if params:
            return pd.read_sql_query(sql, raw, params=list(params))
        return pd.read_sql_query(sql, raw)
    except Exception:
        return pd.DataFrame()


def _changes(conn, cur) -> int:
    """Filas afectadas por último INSERT OR IGNORE."""
    if IS_POSTGRES:
        return cur.rowcount if cur else 0
    row = conn._raw.execute("SELECT changes()").fetchone()
    return row[0] if row else 0


def inicializar_db():
    conn = conectar_db()
    c    = conn.cursor()
    _pk  = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    for ddl in [
        f"""CREATE TABLE IF NOT EXISTS productos (
            id_producto       {_pk},
            nombre            TEXT NOT NULL UNIQUE,
            unidad            TEXT NOT NULL,
            codigo            TEXT,
            fecha_vencimiento TEXT,
            precio_unitario   REAL DEFAULT 0,
            moneda_precio     TEXT DEFAULT 'USD',
            proveedor         TEXT DEFAULT 'Bayer/Monsanto'
        )""",
        f"""CREATE TABLE IF NOT EXISTS movimientos (
            id_movimiento   {_pk},
            fecha_hora      TEXT NOT NULL,
            tipo_movimiento TEXT NOT NULL,
            id_producto     INTEGER NOT NULL,
            cantidad        REAL NOT NULL,
            lote            TEXT,
            referencia      TEXT,
            deposito        TEXT,
            origen          TEXT,
            anulado         INTEGER DEFAULT 0,
            usuario         TEXT DEFAULT ''
        )""",
        f"""CREATE TABLE IF NOT EXISTS entregas (
            id_entrega        {_pk},
            hoja              TEXT,
            rto               TEXT,
            dia_recibido      TEXT,
            cliente           TEXT,
            deposito          TEXT,
            cantidad_comprada REAL,
            producto          TEXT,
            lote              TEXT,
            cant_entregada    REAL,
            pendiente         REAL,
            estado            TEXT,
            vendedor          TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS metadata (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS inventario_fisico (
            id_inventario  {_pk},
            fecha_conteo   TEXT NOT NULL,
            codigo         TEXT NOT NULL,
            producto       TEXT NOT NULL,
            deposito       TEXT NOT NULL,
            stock_sistema  REAL NOT NULL,
            conteo_fisico  REAL NOT NULL,
            diferencia     REAL NOT NULL,
            observaciones  TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS transferencias (
            id_transferencia  {_pk},
            fecha_hora        TEXT NOT NULL,
            id_producto       INTEGER NOT NULL,
            cantidad          REAL NOT NULL,
            lote              TEXT,
            deposito_origen   TEXT NOT NULL,
            deposito_destino  TEXT NOT NULL,
            referencia        TEXT,
            usuario           TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS usuarios (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            nombre        TEXT,
            rol           TEXT DEFAULT 'operador',
            sede          TEXT DEFAULT 'San Jorge'
        )""",
        f"""CREATE TABLE IF NOT EXISTS precios_historicos (
            id_precio   {_pk},
            id_producto INTEGER NOT NULL,
            fecha       TEXT NOT NULL,
            precio      REAL NOT NULL,
            moneda      TEXT DEFAULT 'USD',
            usuario     TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS metas_campana (
            id_meta          {_pk},
            campana          TEXT NOT NULL DEFAULT '2026-2027',
            vendedor         TEXT NOT NULL,
            producto         TEXT NOT NULL,
            unidad           TEXT DEFAULT 'Tn',
            meta_volumen     REAL DEFAULT 0,
            meta_facturacion REAL DEFAULT 0,
            moneda_meta      TEXT DEFAULT 'ARS',
            UNIQUE(campana, vendedor, producto)
        )""",
        f"""CREATE TABLE IF NOT EXISTS cartera_clientes (
            id_cliente            {_pk},
            vendedor              TEXT NOT NULL,
            cliente               TEXT NOT NULL,
            tipo                  TEXT DEFAULT 'activo',
            superficie_ha         REAL DEFAULT 0,
            potencial_facturacion REAL DEFAULT 0,
            field_view            INTEGER DEFAULT 0,
            ultima_compra         TEXT,
            estado                TEXT DEFAULT 'activo',
            observaciones         TEXT,
            campana               TEXT DEFAULT '2026-2027',
            UNIQUE(vendedor, cliente, campana)
        )""",
        f"""CREATE TABLE IF NOT EXISTS reportes_semanales (
            id_reporte      {_pk},
            vendedor        TEXT NOT NULL,
            fecha_semana    TEXT NOT NULL,
            facturacion     REAL DEFAULT 0,
            nuevos_clientes INTEGER DEFAULT 0,
            visitas         INTEGER DEFAULT 0,
            avances         TEXT,
            obstaculos      TEXT,
            oportunidades   TEXT,
            plan_accion     TEXT,
            campana         TEXT DEFAULT '2026-2027'
        )""",
        f"""CREATE TABLE IF NOT EXISTS productos_foco (
            id_foco    {_pk},
            campana    TEXT NOT NULL DEFAULT '2026-2027',
            producto   TEXT NOT NULL,
            unidad     TEXT DEFAULT 'Tn',
            meta_total REAL DEFAULT 0,
            prioridad  INTEGER DEFAULT 1,
            UNIQUE(campana, producto)
        )""",
        f"""CREATE TABLE IF NOT EXISTS ventas_detalle (
            id_venta      {_pk},
            campana       TEXT DEFAULT '2026-2027',
            vendedor      TEXT NOT NULL,
            cuenta        TEXT,
            cliente       TEXT NOT NULL,
            cuit          TEXT,
            articulo      TEXT,
            descripcion   TEXT,
            precio        REAL DEFAULT 0,
            cantidad      REAL DEFAULT 0,
            entregada     REAL DEFAULT 0,
            importe_total REAL DEFAULT 0,
            fecha         TEXT,
            fecha_entrega TEXT,
            localidad     TEXT,
            observaciones TEXT,
            numero_pedido TEXT
        )""",
    ]:
        try:
            c.execute(ddl)
        except Exception:
            pass

    # Migraciones para instalaciones SQLite previas (se ignoran en Supabase)
    if not IS_POSTGRES:
        for m in [
            "ALTER TABLE productos ADD COLUMN codigo TEXT",
            "ALTER TABLE productos ADD COLUMN fecha_vencimiento TEXT",
            "ALTER TABLE productos ADD COLUMN precio_unitario REAL DEFAULT 0",
            "ALTER TABLE productos ADD COLUMN moneda_precio TEXT DEFAULT 'USD'",
            "ALTER TABLE productos ADD COLUMN proveedor TEXT DEFAULT 'Bayer/Monsanto'",
            "ALTER TABLE movimientos ADD COLUMN origen TEXT",
            "ALTER TABLE movimientos ADD COLUMN anulado INTEGER DEFAULT 0",
            "ALTER TABLE movimientos ADD COLUMN usuario TEXT DEFAULT ''",
            "ALTER TABLE entregas ADD COLUMN hoja TEXT",
            "ALTER TABLE entregas ADD COLUMN lote TEXT",
            "ALTER TABLE entregas ADD COLUMN deposito TEXT",
        ]:
            try:  c.execute(m)
            except: pass

    # Usuario admin por defecto
    row = c.execute("SELECT COUNT(*) FROM usuarios").fetchone()
    if row[0] == 0:
        c.execute(
            "INSERT INTO usuarios (username,password_hash,nombre,rol) VALUES (?,?,?,?)",
            ("admin", hashlib.sha256("admin123".encode()).hexdigest(), "Administrador", "admin")
        )

    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# 3. CRUD BÁSICO
# ─────────────────────────────────────────────────────────────────────────────
def guardar_metadata(clave, valor):
    conn = conectar_db()
    conn.execute("INSERT OR REPLACE INTO metadata (clave,valor) VALUES (?,?)", (clave, valor))
    conn.commit(); conn.close()

def obtener_metadata(clave):
    conn = conectar_db()
    row  = conn.execute("SELECT valor FROM metadata WHERE clave=?", (clave,)).fetchone()
    conn.close()
    return row[0] if row else None

def borrar_datos_totales():
    conn = conectar_db()
    for t in ("movimientos","productos","metadata","inventario_fisico","transferencias","precios_historicos"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit(); conn.close()
    limpiar_cache()

def borrar_solo_importacion():
    conn = conectar_db()
    conn.execute("DELETE FROM movimientos WHERE origen = 'excel'")
    conn.execute("DELETE FROM productos WHERE id_producto NOT IN (SELECT DISTINCT id_producto FROM movimientos)")
    conn.commit(); conn.close()
    limpiar_cache()

# ─────────────────────────────────────────────────────────────────────────────
# 4. QUERIES CON CACHÉ
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def obtener_stock_con_lote():
    conn  = conectar_db()
    query = """
        SELECT p.nombre "Producto", p.codigo "Código", p.unidad "Unidad",
               m.lote "Lote", m.deposito "Deposito",
               m.tipo_movimiento, m.cantidad
        FROM movimientos m JOIN productos p ON m.id_producto=p.id_producto
        WHERE COALESCE(m.anulado,0)=0
    """
    df = _rsql(query, conn)
    conn.close()
    if df.empty: return pd.DataFrame()
    df["neta"] = df.apply(
        lambda r: r["cantidad"] if r["tipo_movimiento"]=="Entrada" else -r["cantidad"], axis=1
    )
    return (df.groupby(["Producto","Código","Unidad","Lote","Deposito"])["neta"]
              .sum().reset_index().rename(columns={"neta":"Stock Actual"}))

@st.cache_data(ttl=30)
def obtener_stock_full():
    df = obtener_stock_con_lote()
    if df.empty: return df
    return df.groupby(["Producto","Código","Unidad","Deposito"])["Stock Actual"].sum().reset_index()

@st.cache_data(ttl=30)
def obtener_historial_movimientos():
    conn  = conectar_db()
    query = """
        SELECT m.id_movimiento "ID", m.fecha_hora "Fecha", m.tipo_movimiento "Tipo",
               p.nombre "Producto", p.codigo "Código", m.cantidad "Cantidad",
               p.unidad "Unidad", m.lote "Lote", m.deposito "Depósito",
               m.referencia "Referencia", COALESCE(m.origen,'excel') "Origen",
               COALESCE(m.anulado,0) "Anulado", COALESCE(m.usuario,'') "Usuario"
        FROM movimientos m JOIN productos p ON m.id_producto=p.id_producto
        ORDER BY m.id_movimiento DESC
    """
    df = _rsql(query, conn)
    conn.close()
    return df

@st.cache_data(ttl=30)
def obtener_entregas(hoja=None):
    conn = conectar_db()
    if hoja and hoja != "Todas":
        df = _rsql("SELECT * FROM entregas WHERE hoja=? ORDER BY dia_recibido DESC", conn, params=(hoja,))
    else:
        df = _rsql("SELECT * FROM entregas ORDER BY hoja, dia_recibido DESC", conn)
    conn.close()
    return df

@st.cache_data(ttl=30)
def obtener_productos_completo():
    conn = conectar_db()
    df = _rsql("SELECT * FROM productos ORDER BY nombre", conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def calcular_rotacion_stock(dias=90):
    conn           = conectar_db()
    fecha_corte_dt = datetime.now() - timedelta(days=dias)
    query = """
        SELECT p.nombre "Producto", m.fecha_hora "FechaHora", m.cantidad "Cantidad"
        FROM movimientos m JOIN productos p ON m.id_producto=p.id_producto
        WHERE m.tipo_movimiento='Salida' AND COALESCE(m.anulado,0)=0
    """
    df_raw = _rsql(query, conn)
    conn.close()
    if not df_raw.empty:
        df_raw["_dt"] = pd.to_datetime(df_raw["FechaHora"], format="%d/%m/%Y %H:%M", errors="coerce")
        df_raw = df_raw[df_raw["_dt"] >= fecha_corte_dt]
        df_s = df_raw.groupby("Producto")["Cantidad"].sum().reset_index().rename(columns={"Cantidad":"Total_Salidas"})
    else:
        df_s = pd.DataFrame()

    stock = obtener_stock_full()
    if stock.empty: return pd.DataFrame()
    df_r = stock.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()
    if not df_s.empty:
        df_r = df_r.merge(df_s, on="Producto", how="left")
        df_r["Total_Salidas"] = df_r["Total_Salidas"].fillna(0)
    else:
        df_r["Total_Salidas"] = 0
    df_r["Sal_Diarias"]  = df_r["Total_Salidas"] / dias
    df_r["Días_Cobertura"] = df_r.apply(
        lambda r: round(r["Stock Actual"] / r["Sal_Diarias"])
                  if r["Sal_Diarias"] > 0 else None, axis=1
    )
    df_r["Rotación_Anual"] = df_r.apply(
        lambda r: round(365 / r["Días_Cobertura"], 1)
                  if r["Días_Cobertura"] and r["Días_Cobertura"] > 0 else None, axis=1
    )
    return df_r.sort_values("Días_Cobertura", na_position="last")

# ─────────────────────────────────────────────────────────────────────────────
# 5. STOCK CON COMPROMISOS
# ─────────────────────────────────────────────────────────────────────────────
def obtener_stock_con_compromisos():
    stock = obtener_stock_full()
    if stock.empty: return stock
    ent = obtener_entregas()
    if not ent.empty:
        pend = (ent[ent["pendiente"] > 0]
                .groupby("producto")["pendiente"].sum()
                .reset_index()
                .rename(columns={"producto":"Producto","pendiente":"Comprometido"}))
        stock = stock.merge(pend, on="Producto", how="left")
        stock["Comprometido"] = stock["Comprometido"].fillna(0)
    else:
        stock["Comprometido"] = 0.0
    stock["Disponible Neto"] = stock["Stock Actual"] - stock["Comprometido"]
    return stock

# ─────────────────────────────────────────────────────────────────────────────
# 6. AUTH
# ─────────────────────────────────────────────────────────────────────────────
def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def verificar_usuario(username, password):
    conn = conectar_db()
    row  = conn.execute(
        "SELECT rol, nombre FROM usuarios WHERE username=? AND password_hash=?",
        (username, hash_pwd(password))
    ).fetchone()
    conn.close()
    return row  # (rol, nombre) or None

def mostrar_login():
    st.markdown("""
    <div style="max-width:400px;margin:60px auto;text-align:center">
        <h1>🧪 Control de Depósito</h1>
        <p style="color:#6c757d">La Clementina S.A.</p>
    </div>
    """, unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]
    with col:
        user = st.text_input("Usuario", key="login_user")
        pwd  = st.text_input("Contraseña", type="password", key="login_pwd")
        if st.button("Ingresar", type="primary"):
            result = verificar_usuario(user, pwd)
            if result:
                st.session_state.authenticated  = True
                st.session_state.user_rol       = result[0]
                st.session_state.user_nombre    = result[1]
                st.session_state.username       = user
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
        st.caption("Usuario inicial: **admin** / Contraseña: **admin123**")

# ─────────────────────────────────────────────────────────────────────────────
# 7. HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def limpiar_cache():
    """Invalida todas las caches de datos. Llamar tras cualquier escritura en DB."""
    st.cache_data.clear()

def safe_float(val, default=0.0):
    try:
        if val is None: return default
        f = float(val)
        return f if f == f else default  # NaN check
    except: return default

def safe_str(val, default=""):
    try:
        if val is None: return default
        s = str(val).strip()
        return "" if s.lower() in ("nan","nat","none","") else s
    except: return default

def safe_fecha(val):
    try:
        return "" if pd.isna(val) else pd.Timestamp(val).strftime("%d/%m/%Y")
    except: return ""

def dias_desde(fecha_str):
    try:
        return (datetime.now() - datetime.strptime(str(fecha_str).strip(), "%d/%m/%Y")).days
    except: return 0

def dias_hasta(fecha_str):
    try:
        return (datetime.strptime(str(fecha_str).strip(), "%d/%m/%Y") - datetime.now()).days
    except: return 9999

def usuario_actual():
    return st.session_state.get("username", "sistema")

def es_admin():
    return st.session_state.get("user_rol","operador") in ("admin","supervisor")

def decodificar_qr_reforzado(foto_input):
    if foto_input is None: return None
    try:
        foto_input.seek(0)
        img = np.array(Image.open(foto_input).convert('RGB'))
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        img = cv2.copyMakeBorder(img, 20,20,20,20, cv2.BORDER_CONSTANT, value=[255,255,255])
        det = cv2.QRCodeDetector()
        val, _, _ = det.detectAndDecode(img)
        if val: return val.strip()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        val, _, _ = det.detectAndDecode(gray)
        return val.strip() if val else None
    except: return None

# ─────────────────────────────────────────────────────────────────────────────
# 8. EXPORTS
# ─────────────────────────────────────────────────────────────────────────────
def to_excel_bytes(df, sheet_name="Hoja1"):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)
    return out.getvalue()

def descargar_excel_agrupado(df):
    if df.empty: return b""
    pivot = df.pivot_table(
        index=["Producto","Código","Unidad"], columns="Deposito",
        values="Stock Actual", aggfunc="sum"
    ).fillna(0)
    pivot["TOTAL GENERAL"] = pivot.sum(axis=1)
    return to_excel_bytes(pivot.reset_index(), "Comparativa_Stock")

def descargar_planilla_inventario(df):
    d = df.copy()
    d["CONTEO FÍSICO"] = ""; d["DIFERENCIA"] = ""; d["OBSERVACIONES"] = ""
    return to_excel_bytes(d, "Toma_Stock")

def generar_orden_reposicion(stock_df, umbral, consumo_df):
    """Excel con productos bajo umbral y cantidad sugerida (30 días de cobertura)."""
    prod_df = obtener_productos_completo()
    bajo = stock_df[stock_df["Stock Actual"] < umbral].copy()
    bajo = bajo.groupby(["Producto","Código","Unidad","Deposito"])["Stock Actual"].sum().reset_index()
    if not consumo_df.empty:
        bajo = bajo.merge(
            consumo_df[["Producto","Sal_Diarias"]].groupby("Producto")["Sal_Diarias"].mean().reset_index(),
            on="Producto", how="left"
        )
        bajo["Sal_Diarias"] = bajo["Sal_Diarias"].fillna(0)
        bajo["Sugerido_30d"] = (bajo["Sal_Diarias"] * 30 - bajo["Stock Actual"]).clip(lower=0).round(1)
    else:
        bajo["Sugerido_30d"] = (umbral * 2 - bajo["Stock Actual"]).clip(lower=0)

    if "proveedor" in prod_df.columns:
        bajo = bajo.merge(prod_df[["nombre","proveedor"]].rename(columns={"nombre":"Producto"}),
                          on="Producto", how="left")
    bajo["Fecha_Orden"] = datetime.now().strftime("%d/%m/%Y")
    return to_excel_bytes(bajo, "Orden_Reposicion")

def generar_reporte_excel():
    """Reporte mensual consolidado en múltiples hojas."""
    stock = obtener_stock_full()
    hist  = obtener_historial_movimientos()
    ent   = obtener_entregas()
    out   = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        if not stock.empty:
            stock.to_excel(w, index=False, sheet_name="Stock_Actual")
        if not hist.empty:
            hist.head(500).to_excel(w, index=False, sheet_name="Movimientos")
        if not ent.empty:
            ent.to_excel(w, index=False, sheet_name="Entregas")
        # KPI summary
        kpi = pd.DataFrame({
            "Indicador": ["Total Productos","Volumen Total","Stock Negativo","Fecha Reporte"],
            "Valor": [
                len(stock["Producto"].unique()) if not stock.empty else 0,
                stock["Stock Actual"].sum() if not stock.empty else 0,
                len(stock[stock["Stock Actual"] < 0]) if not stock.empty else 0,
                datetime.now().strftime("%d/%m/%Y %H:%M")
            ]
        })
        kpi.to_excel(w, index=False, sheet_name="Resumen")
    return out.getvalue()

def generar_reporte_pdf():
    """PDF mensual con reportlab. Devuelve bytes o None si no está disponible."""
    if not PDF_AVAILABLE: return None
    stock = obtener_stock_full()
    ent   = obtener_entregas()
    buf   = io.BytesIO()
    doc   = SimpleDocTemplate(buf, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                               topMargin=2*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    elems  = []

    # Título
    elems.append(Paragraph("Control de Depósito — La Clementina S.A.", styles["Title"]))
    elems.append(Paragraph(f"Reporte generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                            styles["Normal"]))
    elems.append(Spacer(1, 0.5*cm))

    # KPIs
    if not stock.empty:
        U = int(obtener_metadata("umbral_alerta") or 20)
        kpi_data = [
            ["Indicador", "Valor"],
            ["Total Productos",  str(stock["Producto"].nunique())],
            ["Depósitos",        str(stock["Deposito"].nunique())],
            ["Volumen Total",    f"{stock['Stock Actual'].sum():,.0f}"],
            ["Stock Bajo",       str(len(stock[(stock["Stock Actual"] >= 0) & (stock["Stock Actual"] < U)]))],
            ["Stock Negativo",   str(len(stock[stock["Stock Actual"] < 0]))],
        ]
        t = Table(kpi_data, colWidths=[8*cm, 8*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), rl_colors.HexColor("#007bff")),
            ("TEXTCOLOR",  (0,0), (-1,0), rl_colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#f0f8ff")]),
            ("GRID",       (0,0), (-1,-1), 0.5, rl_colors.HexColor("#dee2e6")),
            ("FONTSIZE",   (0,0), (-1,-1), 10),
            ("TOPPADDING", (0,0), (-1,-1), 6),
        ]))
        elems.append(t); elems.append(Spacer(1, 0.5*cm))

    # Top 20 stock bajo
    if not stock.empty:
        elems.append(Paragraph("Stock Bajo Umbral", styles["Heading2"]))
        bajo = stock[stock["Stock Actual"] < int(obtener_metadata("umbral_alerta") or 20)]
        if not bajo.empty:
            rows = [["Producto","Depósito","Stock","Unidad"]]
            for _, r in bajo.head(20).iterrows():
                rows.append([r["Producto"][:35], r["Deposito"], f"{r['Stock Actual']:,.1f}", r["Unidad"]])
            t2 = Table(rows, colWidths=[9*cm, 3.5*cm, 2.5*cm, 2.5*cm])
            t2.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), rl_colors.HexColor("#ffc107")),
                ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0), (-1,-1), 9),
                ("GRID",          (0,0), (-1,-1), 0.4, rl_colors.grey),
                ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#fffbf0")]),
            ]))
            elems.append(t2)
        else:
            elems.append(Paragraph("Sin productos bajo umbral.", styles["Normal"]))
        elems.append(Spacer(1, 0.5*cm))

    # Entregas pendientes
    if not ent.empty:
        elems.append(Paragraph("Entregas Pendientes por Producto", styles["Heading2"]))
        pend = (ent[ent["pendiente"] > 0]
                .groupby("producto")
                .agg(Clientes=("cliente","nunique"), Pendiente=("pendiente","sum"))
                .reset_index().sort_values("Pendiente", ascending=False).head(15))
        if not pend.empty:
            rows = [["Producto","Clientes","Pendiente"]]
            for _, r in pend.iterrows():
                rows.append([r["producto"][:40], str(r["Clientes"]), f"{r['Pendiente']:,.0f}"])
            t3 = Table(rows, colWidths=[10*cm, 3*cm, 4*cm])
            t3.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), rl_colors.HexColor("#28a745")),
                ("TEXTCOLOR",     (0,0), (-1,0), rl_colors.white),
                ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0), (-1,-1), 9),
                ("GRID",          (0,0), (-1,-1), 0.4, rl_colors.grey),
                ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#f0fff4")]),
            ]))
            elems.append(t3)

    doc.build(elems)
    return buf.getvalue()

def exportar_macrogest_format(stock_df):
    """Excel en el formato de importación de MacroGest."""
    if stock_df.empty: return b""
    df = stock_df.copy()
    # Aseguramos stock por lote si disponible
    stk_lote = obtener_stock_con_lote()
    if not stk_lote.empty:
        out_df = stk_lote.rename(columns={
            "Código": "codigo", "Producto": "descripcion_1",
            "Unidad": "unidad_medida", "Lote": "lote",
            "Deposito": "deposito", "Stock Actual": "stock_actual"
        })[["codigo","descripcion_1","unidad_medida","deposito","lote","stock_actual"]]
    else:
        out_df = df.rename(columns={
            "Código": "codigo", "Producto": "descripcion_1",
            "Unidad": "unidad_medida",
            "Deposito": "deposito", "Stock Actual": "stock_actual"
        })
        out_df["lote"] = "S/L"
        out_df = out_df[["codigo","descripcion_1","unidad_medida","deposito","lote","stock_actual"]]
    return to_excel_bytes(out_df, "Exportacion_MacroGest")

# ─────────────────────────────────────────────────────────────────────────────
# 9. EMAIL
# ─────────────────────────────────────────────────────────────────────────────
def enviar_email_alerta(stock_bajo, pendientes_viejos):
    smtp_server = obtener_metadata("smtp_server") or ""
    smtp_port   = int(obtener_metadata("smtp_port") or 587)
    smtp_user   = obtener_metadata("smtp_user")   or ""
    smtp_pass   = obtener_metadata("smtp_pass")   or ""
    dest        = obtener_metadata("email_dest")  or ""
    if not all([smtp_server, smtp_user, smtp_pass, dest]):
        return False, "Configuración SMTP incompleta. Completar en Configuración → Email."
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⚠️ Alerta Stock — La Clementina S.A. — {datetime.now().strftime('%d/%m/%Y')}"
        msg["From"]    = smtp_user
        msg["To"]      = dest

        html_rows_stock = "".join(
            f"<tr><td>{r['Producto']}</td><td>{r['Deposito']}</td>"
            f"<td style='color:{'red' if r['Stock Actual']<0 else 'orange'};font-weight:bold'>"
            f"{r['Stock Actual']:,.1f} {r['Unidad']}</td></tr>"
            for _, r in stock_bajo.head(20).iterrows()
        ) if not stock_bajo.empty else "<tr><td colspan=3>Sin alertas</td></tr>"

        html = f"""
        <html><body style="font-family:Arial,sans-serif;color:#333">
        <h2>⚠️ Reporte de Alertas — La Clementina S.A.</h2>
        <p>Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <h3>📦 Stock Bajo / Negativo</h3>
        <table border=1 cellpadding=6 cellspacing=0 style="border-collapse:collapse;width:100%">
        <tr style="background:#007bff;color:white"><th>Producto</th><th>Depósito</th><th>Stock</th></tr>
        {html_rows_stock}
        </table>
        """
        if pendientes_viejos > 0:
            html += f"<h3>⏳ Entregas con +30 días pendientes: <b style='color:red'>{pendientes_viejos}</b></h3>"
        html += "</body></html>"

        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_server, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True, f"Email enviado a {dest}"
    except Exception as e:
        return False, str(e)

# ─────────────────────────────────────────────────────────────────────────────
# 10. PARSER ENTREGAS EXCEL (igual que versión anterior)
# ─────────────────────────────────────────────────────────────────────────────
def parsear_entregas_excel(archivo):
    registros = []

    def _parse_hoja(sheet, header_row, col_map, hoja_tag, deposito_default):
        try:
            df = pd.read_excel(archivo, sheet_name=sheet, header=header_row)
            df.columns = [str(c).strip() for c in df.columns]
            fecha_col = col_map.get("fecha")
            if fecha_col and fecha_col in df.columns:
                df[fecha_col] = pd.to_datetime(df[fecha_col], errors="coerce")
            for _, r in df.iterrows():
                prod = safe_str(r.get(col_map.get("producto","PRODUCTO"),""))
                if not prod: continue
                dep = safe_str(r.get("DEPOSITO","")) if "DEPOSITO" in df.columns else ""
                registros.append({
                    "hoja":              hoja_tag,
                    "rto":               safe_str(r.get(col_map.get("rto",""),"")) if col_map.get("rto") else "",
                    "dia_recibido":      safe_fecha(r[fecha_col]) if fecha_col else "",
                    "cliente":           safe_str(r.get(col_map.get("cliente","CLIENTE"),"")) ,
                    "deposito":          (f"BAYER DEP {dep}" if dep else deposito_default) if hoja_tag=="BAYER DIRECTA" else deposito_default,
                    "cantidad_comprada": safe_float(r.get(col_map.get("comprado","CANTIDAD COMPRADA"),0)),
                    "producto":          prod,
                    "lote":              safe_str(r.get(col_map.get("lote",""),"")) if col_map.get("lote") else "",
                    "cant_entregada":    safe_float(r.get(col_map.get("entregado","CANT. ENTREGADA"),0)),
                    "pendiente":         safe_float(r.get(col_map.get("pendiente","PENDIENTE"),0)),
                    "estado":            safe_str(r.get(col_map.get("estado","ESTADO"),"")) ,
                    "vendedor":          safe_str(r.get(col_map.get("vendedor","VENDEDOR"),"")) ,
                })
        except Exception as e:
            st.warning(f"Hoja '{sheet}': {e}")

    _parse_hoja("LA CLEMENTINA S.A", 1,
                {"fecha":"DIA RECIBIDO","rto":"RTO MONSANTO","cliente":"CLIENTE",
                 "producto":"PRODUCTO","comprado":"CANTIDAD COMPRADA",
                 "entregado":"CANT. ENTREGADA","pendiente":"PENDIENTE",
                 "estado":"ESTADO","vendedor":"VENDEDOR"},
                "LA CLEMENTINA S.A", "LA CLEMENTINA")

    _parse_hoja("LCAGRO S.A", 1,
                {"fecha":"DIA RECIBIDO","rto":"RTO MONSANTO","cliente":"CLIENTE",
                 "producto":"PRODUCTO","comprado":"CANTIDAD COMPRADA",
                 "entregado":"CANT. ENTREGADA","pendiente":"PENDIENTE",
                 "estado":"ESTADO","vendedor":"VENDEDOR"},
                "LCAGRO S.A", "LCAGRO")

    _parse_hoja("MERC CONSIGNADO BAYER DEP55", 2,
                {"fecha":"DIA","cliente":"PRODUCTOR","producto":"PRODUCTO",
                 "lote":"LOTE","comprado":"CANTIDAD","entregado":"CANTIDAD ENT",
                 "pendiente":"CANTIDAD PEND","estado":"ESTADO","vendedor":"VENDEDOR"},
                "BAYER DEP55", "DEP 55")

    _parse_hoja("MERC. FACT DIRECTA BAYER 43-60", 1,
                {"fecha":"DIA RECIBIDO","rto":"RTO BAYER","cliente":"CLIENTE",
                 "producto":"PRODUCTO","lote":"NRO LOTE","comprado":"CANTIDAD COMPRADA",
                 "entregado":"CANT. ENTREGADA","pendiente":"PENDIENTE",
                 "estado":"ESTADO","vendedor":"VENDEDOR"},
                "BAYER DIRECTA", "BAYER DIRECTO")

    return pd.DataFrame(registros) if registros else pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
# 10b. QUERIES PLAN COMERCIAL
# ─────────────────────────────────────────────────────────────────────────────
CAMPANA_ACTUAL = "2026-2027"

PRODUCTOS_FOCO_DEFAULT = [
    ("Semilla Maíz (Híbridos Bayer)", "Bolsas"),
    ("Semilla Soja (Autógamas)",       "Bolsas"),
    ("Round Up / Glifosato",           "Litros"),
    ("Fungicidas Línea Bayer",         "Litros"),
    ("Adengo (Herbicida Maíz)",        "Litros"),
    ("Seegrown (Estimulante)",         "Litros"),
]

DISTRIBUCION_OBJETIVO = {
    "Semillas autógamas": 30,
    "Agroquímicos":        30,
    "Fertilizantes":       30,
    "Otros / Servicios":   10,
}

@st.cache_data(ttl=30)
def obtener_metas_campana(campana=CAMPANA_ACTUAL):
    conn = conectar_db()
    df = _rsql("SELECT * FROM metas_campana WHERE campana=?", conn, params=(campana,))
    conn.close()
    return df

@st.cache_data(ttl=30)
def obtener_cartera(vendedor=None, campana=CAMPANA_ACTUAL):
    conn = conectar_db()
    if vendedor:
        df = _rsql("SELECT * FROM cartera_clientes WHERE vendedor=? AND campana=? ORDER BY tipo, cliente",
                   conn, params=(vendedor, campana))
    else:
        df = _rsql("SELECT * FROM cartera_clientes WHERE campana=? ORDER BY vendedor, tipo, cliente",
                   conn, params=(campana,))
    conn.close()
    return df

@st.cache_data(ttl=30)
def obtener_reportes(vendedor=None, campana=CAMPANA_ACTUAL):
    conn = conectar_db()
    if vendedor:
        df = _rsql("SELECT * FROM reportes_semanales WHERE vendedor=? AND campana=? ORDER BY fecha_semana DESC",
                   conn, params=(vendedor, campana))
    else:
        df = _rsql("SELECT * FROM reportes_semanales WHERE campana=? ORDER BY fecha_semana DESC",
                   conn, params=(campana,))
    conn.close()
    return df

@st.cache_data(ttl=30)
def obtener_productos_foco(campana=CAMPANA_ACTUAL):
    conn = conectar_db()
    df = _rsql("SELECT * FROM productos_foco WHERE campana=? ORDER BY prioridad", conn, params=(campana,))
    conn.close()
    if df.empty:
        conn2 = conectar_db()
        for i, (prod, uni) in enumerate(PRODUCTOS_FOCO_DEFAULT, 1):
            try:
                conn2.execute("INSERT OR IGNORE INTO productos_foco (campana,producto,unidad,meta_total,prioridad) VALUES (?,?,?,?,?)",
                              (campana, prod, uni, 0, i))
            except: pass
        conn2.commit(); conn2.close()
        conn3 = conectar_db()
        df = _rsql("SELECT * FROM productos_foco WHERE campana=? ORDER BY prioridad", conn3, params=(campana,))
        conn3.close()
    return df

@st.cache_data(ttl=30)
def obtener_ventas_detalle(vendedor=None, campana=CAMPANA_ACTUAL):
    conn = conectar_db()
    if vendedor:
        df = _rsql("SELECT * FROM ventas_detalle WHERE vendedor=? AND campana=? ORDER BY fecha DESC",
                   conn, params=(vendedor, campana))
    else:
        df = _rsql("SELECT * FROM ventas_detalle WHERE campana=? ORDER BY vendedor, fecha DESC",
                   conn, params=(campana,))
    conn.close()
    return df

def parsear_macrogest_ventas(archivo, vendedor, campana=CAMPANA_ACTUAL):
    """
    Lee exportación MacroGest con columnas:
    cuenta, deno_cuenta, cuit_cuenta, articulo, descripcion,
    precio, cantidad, entregada, fecha, localidad, observaciones_gen, numero
    Devuelve (df_cartera, df_ventas) listos para insertar.
    """
    try:
        df = pd.read_excel(archivo)
    except:
        try:
            df = pd.read_csv(archivo)
        except:
            return pd.DataFrame(), pd.DataFrame()

    df.columns = [str(c).strip().lower().replace(" ","_") for c in df.columns]

    def _f(col, default=""):
        return safe_str(col) if col in df.columns else default

    # Normalizar precio/cantidad (pueden venir con coma decimal)
    def parse_num(v):
        try:
            return float(str(v).replace(",",".").replace(" ",""))
        except: return 0.0

    filas_ventas = []
    for _, r in df.iterrows():
        cliente = safe_str(r.get("deno_cuenta",""))
        if not cliente: continue
        precio   = parse_num(r.get("precio",  0))
        cantidad = parse_num(r.get("cantidad", 0))
        entregada= parse_num(r.get("entregada",0))
        filas_ventas.append({
            "campana":       campana,
            "vendedor":      vendedor,
            "cuenta":        safe_str(r.get("cuenta","")),
            "cliente":       cliente,
            "cuit":          safe_str(r.get("cuit_cuenta","")),
            "articulo":      safe_str(r.get("articulo","")),
            "descripcion":   safe_str(r.get("descripcion","")),
            "precio":        precio,
            "cantidad":      cantidad,
            "entregada":     entregada,
            "importe_total": precio * cantidad,
            "fecha":         safe_str(r.get("fecha","")),
            "fecha_entrega": safe_str(r.get("fecha_entrega","")),
            "localidad":     safe_str(r.get("localidad","")),
            "observaciones": safe_str(r.get("observaciones_gen","")),
            "numero_pedido": safe_str(r.get("numero",""))
        })

    df_v = pd.DataFrame(filas_ventas)
    if df_v.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Construir cartera: un registro por cliente con totales
    cart = (df_v.groupby(["cuenta","cliente","cuit"])
            .agg(
                importe_total=("importe_total","sum"),
                localidad=("localidad","first"),
                fecha=("fecha","max"),
            ).reset_index())

    # Clasificación automática Pareto 80/20
    cart = cart.sort_values("importe_total", ascending=False).reset_index(drop=True)
    total_imp = cart["importe_total"].sum()
    cart["acum"] = cart["importe_total"].cumsum()
    cart["pct_acum"] = cart["acum"] / total_imp if total_imp > 0 else 0
    # Los que acumulan hasta el 80% = premium
    umbral_idx = (cart["pct_acum"] <= 0.80).sum()
    cart["tipo"] = "activo"
    cart.loc[:umbral_idx, "tipo"] = "premium"

    df_cartera = pd.DataFrame({
        "vendedor":              vendedor,
        "cliente":               cart["cliente"],
        "tipo":                  cart["tipo"],
        "superficie_ha":         0.0,
        "potencial_facturacion": cart["importe_total"].round(2),
        "field_view":            0,
        "ultima_compra":         cart["fecha"].apply(lambda x: x[:10] if len(str(x))>=10 else ""),
        "estado":                "activo",
        "observaciones":         cart["localidad"],
        "campana":               campana,
    })
    return df_cartera, df_v

def parsear_sin_entregar_macrogest(archivo, vendedor=""):
    """
    Lee exportacion MacroGest de pedidos sin entregar.
    Columnas: cuenta, deno_cuenta, articulo, descripcion,
    precio, cantidad, entregada, fecha, localidad, estado, numero.
    Mapea a tabla entregas con hoja='MACROGEST'.
    Calcula pendiente = cantidad - entregada.
    """
    try:
        df = pd.read_excel(archivo)
    except Exception:
        try:
            df = pd.read_csv(archivo)
        except Exception:
            return pd.DataFrame()
    df.columns = [str(c).strip().lower().replace(" ","_") for c in df.columns]
    def _n(v):
        try:    return float(str(v).replace(",",".").replace(" ",""))
        except: return 0.0
    registros = []
    for _, r in df.iterrows():
        cliente = safe_str(r.get("deno_cuenta",""))
        if not cliente: continue
        cantidad  = _n(r.get("cantidad",  0))
        entregada = _n(r.get("entregada", 0))
        pendiente = max(round(cantidad - entregada, 4), 0)
        fecha = ""
        try:    fecha = pd.Timestamp(r["fecha"]).strftime("%d/%m/%Y")
        except: pass
        registros.append({
            "hoja":              "MACROGEST",
            "rto":               safe_str(r.get("numero","")),
            "dia_recibido":      fecha,
            "cliente":           cliente,
            "deposito":          safe_str(r.get("deposito","")) or "MacroGest",
            "cantidad_comprada": cantidad,
            "producto":          safe_str(r.get("descripcion","")),
            "lote":              safe_str(r.get("codigo_sinonimo","")) or "S/L",
            "cant_entregada":    entregada,
            "pendiente":         pendiente,
            "estado":            safe_str(r.get("estado","")),
            "vendedor":          vendedor,
        })
    return pd.DataFrame(registros) if registros else pd.DataFrame()

def ventas_reales_por_vendedor(campana=CAMPANA_ACTUAL):
    """
    Combina ventas_detalle (MacroGest) + entregas para medir performance real.
    ventas_detalle tiene precedencia; entregas se usa como fallback.
    """
    df_mg = obtener_ventas_detalle(campana=campana)
    if not df_mg.empty:
        r = (df_mg.groupby("vendedor")
             .agg(
                 Importe_Total=("importe_total","sum"),
                 Entregado_Total=("entregada","sum"),
                 Cant_Total=("cantidad","sum"),
                 Clientes_Activos=("cliente","nunique"),
                 Productos_Distintos=("descripcion","nunique"),
             ).reset_index())
        r["% Entregado"] = (r["Entregado_Total"] / r["Cant_Total"].replace(0,1) * 100).round(1)
        return r

    # Fallback: datos de entregas
    ent = obtener_entregas()
    if ent.empty: return pd.DataFrame()
    r = (ent.groupby("vendedor")
         .agg(Importe_Total=("cantidad_comprada","sum"),
              Entregado_Total=("cant_entregada","sum"),
              Cant_Total=("cantidad_comprada","sum"),
              Clientes_Activos=("cliente","nunique"),
              Productos_Distintos=("producto","nunique"))
         .reset_index())
    r["% Entregado"] = (r["Entregado_Total"] / r["Importe_Total"].replace(0,1) * 100).round(1)
    return r

def gauge_kpi(valor, meta, titulo, unidad=""):
    """Plotly gauge chart para un KPI individual."""
    pct = min((valor / meta * 100) if meta > 0 else 0, 150)
    color = "#28a745" if pct >= 90 else ("#ffc107" if pct >= 60 else "#dc3545")
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=valor,
        delta={"reference": meta, "valueformat": ",.0f"},
        title={"text": titulo, "font": {"size": 13}},
        number={"suffix": f" {unidad}", "valueformat": ",.1f"},
        gauge={
            "axis": {"range": [0, max(meta * 1.3, valor * 1.1, 1)]},
            "bar":  {"color": color},
            "steps": [
                {"range": [0, meta * 0.6],  "color": "#fff0f0"},
                {"range": [meta * 0.6, meta * 0.9],  "color": "#fffbf0"},
                {"range": [meta * 0.9, meta * 1.3],  "color": "#f0fff4"},
            ],
            "threshold": {"line": {"color": "black", "width": 3}, "value": meta},
        }
    ))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=40, b=10))
    return fig

# ─────────────────────────────────────────────────────────────────────────────
# 11. INIT
# ─────────────────────────────────────────────────────────────────────────────
inicializar_db()

# Session state
_defaults = {
    "qr_detectado":        "Todos",
    "wa_numero":           None,
    "umbral_alerta":       None,
    "mov_pendiente":       None,
    "ultimo_qr_procesado": None,
    "authenticated":       False,
    "user_rol":            "operador",
    "user_nombre":         "",
    "username":            "",
    "trans_pendiente":     None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Cargar parámetros persistidos desde DB (solo primera vez)
if st.session_state.wa_numero is None:
    st.session_state.wa_numero = obtener_metadata("wa_numero") or "5493406123456"
if st.session_state.umbral_alerta is None:
    stored = obtener_metadata("umbral_alerta")
    st.session_state.umbral_alerta = int(stored) if stored else 20

# ─────────────────────────────────────────────────────────────────────────────
# 12. AUTH GATE
# ─────────────────────────────────────────────────────────────────────────────
auth_enabled = obtener_metadata("auth_enabled") == "1"
if auth_enabled and not st.session_state.get("authenticated"):
    mostrar_login()
    st.stop()

# Header con usuario logueado
if auth_enabled and st.session_state.get("authenticated"):
    c_head1, c_head2 = st.columns([6, 1])
    with c_head2:
        st.caption(f"👤 {st.session_state.user_nombre} ({st.session_state.user_rol})")
        if st.button("Salir", key="logout_btn"):
            for k in ("authenticated","user_rol","user_nombre","username"):
                st.session_state[k] = "" if k != "authenticated" else False
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 13. TABS PRINCIPALES
# ─────────────────────────────────────────────────────────────────────────────
st.title("🧪 Control de Depósito Inteligente")

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
    "⚡ Panel",
    "📦 LC / LCAGRO",
    "🌿 Bayer DEP55",
    "🚚 Bayer Directa",
    "📋 Stock Físico",
    "📜 Historial",
    "💲 Valorización",
    "📈 Reportes",
    "⚙️ Configuración",
    "📊 Plan Comercial",
    "🔄 Sin Entregar MG",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PANEL DE CONTROL
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    stock_df = obtener_stock_con_compromisos()

    if stock_df.empty:
        st.warning("⚠️ Sin datos. Subí el archivo en Configuración.")
        st.caption("Para empezar, andá a ⚙️ Configuración → Importar Stock desde MacroGest y subí el archivo de saldos.")
    else:
        U = st.session_state.umbral_alerta
        for meta, caption in [
            ("ultima_importacion",          "🕐 Última importación stock"),
            ("ultima_importacion_entregas",  "📦 Última importación entregas"),
        ]:
            val = obtener_metadata(meta)
            if val: st.caption(f"{caption}: **{val}**")

        # KPIs
        neg_n  = len(stock_df[stock_df["Stock Actual"] < 0])
        bajo_n = len(stock_df[(stock_df["Stock Actual"] >= 0) & (stock_df["Stock Actual"] < U)])
        comp_n = len(stock_df[stock_df["Disponible Neto"] < 0])

        ent_panel = obtener_entregas()
        venc30 = 0
        if not ent_panel.empty:
            ent_panel["dias_p"] = ent_panel["dia_recibido"].apply(dias_desde)
            venc30 = len(ent_panel[(ent_panel["pendiente"] > 0) & (ent_panel["dias_p"] > 30)])

        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        with c1: st.metric("Productos",      stock_df["Producto"].nunique())
        with c2: st.metric("Volumen Total",  f"{stock_df['Stock Actual'].sum():,.0f}")
        with c3: st.metric("Stock Bajo",     bajo_n,  delta=-bajo_n,  delta_color="inverse")
        with c4: st.metric("Negativo ⚠️",    neg_n,   delta=-neg_n,   delta_color="inverse")
        with c5: st.metric("Comprometido",   comp_n,  delta=-comp_n,  delta_color="inverse")
        with c6: st.metric("Depósitos",      stock_df["Deposito"].nunique())
        with c7: st.metric("Pend. +30d ⏳",  venc30,  delta=-venc30,  delta_color="inverse")

        # Alerta WhatsApp
        wa = st.session_state.wa_numero
        if (neg_n > 0 or bajo_n > 0) and wa:
            alertas_wa = stock_df[stock_df["Stock Actual"] < U].head(15)
            lineas = [f"⚠️ Alerta Stock {datetime.now().strftime('%d/%m/%Y')}"]
            for _, r in alertas_wa.iterrows():
                lineas.append(f"• {r['Producto']}: {r['Stock Actual']:,.1f} {r['Unidad']} ({r['Deposito']})")
            st.link_button("📱 Enviar alerta WhatsApp",
                           f"https://wa.me/{wa}?text={urllib.parse.quote(chr(10).join(lineas))}")

        st.markdown("---")

        # Gráficos
        with st.expander("📊 Gráficos", expanded=False):
            cg1, cg2 = st.columns(2)
            with cg1:
                dep_g = stock_df.groupby("Deposito")["Stock Actual"].sum().reset_index()
                fig   = px.bar(dep_g.sort_values("Stock Actual"), x="Stock Actual", y="Deposito",
                               orientation="h", title="Stock por Depósito", color="Stock Actual",
                               color_continuous_scale="Blues")
                fig.update_layout(height=300, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig, use_container_width=True)
            with cg2:
                top = (stock_df.groupby("Producto")["Stock Actual"].sum()
                       .reset_index().sort_values("Stock Actual", ascending=False).head(15))
                fig2 = px.bar(top.sort_values("Stock Actual"), x="Stock Actual", y="Producto",
                              orientation="h", title="Top 15 Productos", color="Stock Actual",
                              color_continuous_scale="Greens")
                fig2.update_layout(height=400, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig2, use_container_width=True)

            if not ent_panel.empty:
                est_g = ent_panel.groupby("estado").size().reset_index(name="N")
                est_g = est_g[est_g["estado"].str.strip() != ""]
                if not est_g.empty:
                    fig3 = px.pie(est_g, names="estado", values="N",
                                  title="Estado Entregas", hole=0.4)
                    fig3.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig3, use_container_width=True)

        st.markdown("---")
        st.subheader("🔍 Filtros")

        search_q = st.text_input("⌨️ Buscar por nombre o código", placeholder="Escribí aquí...", key="search_p1")

        with st.expander("📷 Escanear QR"):
            c_cam, c_fil = st.columns(2)
            with c_cam:
                foto_cam = st.camera_input("Cámara", key="qr_cam")
            with c_fil:
                foto_fil = st.file_uploader("O subí imagen", type=["png","jpg","jpeg"], key="qr_fil")
            foto_qr = foto_cam or foto_fil
            if foto_qr:
                res_qr = decodificar_qr_reforzado(foto_qr)
                if res_qr:
                    qr_clean = res_qr.strip().replace("\n","").replace("\r","")
                    st.success(f"✅ QR: {qr_clean}")
                    if st.session_state.ultimo_qr_procesado != qr_clean:
                        st.session_state.ultimo_qr_procesado = qr_clean
                        m = stock_df[
                            stock_df["Producto"].str.contains(qr_clean, case=False, na=False) |
                            stock_df["Código"].astype(str).str.contains(qr_clean, case=False, na=False)
                        ].copy()
                        if len(m) == 1:
                            st.session_state.qr_detectado = m.iloc[0]["Producto"]
                            st.rerun()
                        elif len(m) > 1:
                            opciones_qr = m["Producto"].unique().tolist()
                            st.info(f"Se encontraron {len(opciones_qr)} productos con ese código. Seleccioná uno:")
                            elegido_qr = st.selectbox("Producto del QR", opciones_qr, key="qr_multi_sel")
                            if st.button("✅ Usar este producto", key="qr_multi_btn"):
                                st.session_state.qr_detectado = elegido_qr
                                st.rerun()
                        else:
                            st.info("QR leído pero sin coincidencia en el stock actual.")
                else:
                    st.warning("QR no detectado.")

        cf1, cf2, cf3 = st.columns(3)
        with cf1:
            lista_p = ["Todos"] + sorted(stock_df["Producto"].unique().tolist())
            idx_p   = lista_p.index(st.session_state.qr_detectado) \
                      if st.session_state.qr_detectado in lista_p else 0
            f_prod = st.selectbox("Producto", lista_p, index=idx_p)
            st.session_state.qr_detectado = f_prod
        with cf2:
            lista_d = ["Todos"] + sorted(stock_df["Deposito"].unique().tolist())
            f_dep   = st.selectbox("Depósito", lista_d)
        with cf3:
            hide_neg       = st.toggle("Solo stock positivo",       value=True)
            filter_reponer = st.toggle(f"🚨 Reponer (<{U})",        value=False)
            show_neg_f     = st.toggle("⚠️ Mostrar negativos",       value=True)
            show_comp_f    = st.toggle("🔒 Solo comprometidos",      value=False)

        df_f = stock_df.copy()
        if search_q:
            df_f = df_f[df_f["Producto"].str.contains(search_q, case=False, na=False) |
                        df_f["Código"].astype(str).str.contains(search_q, case=False, na=False)]
        if f_prod != "Todos" and not search_q:
            df_f = df_f[df_f["Producto"] == f_prod]
        if f_dep != "Todos":
            df_f = df_f[df_f["Deposito"] == f_dep]
        if hide_neg:
            mask = df_f["Stock Actual"] > 0
            if show_neg_f: mask = mask | (df_f["Stock Actual"] < 0)
            df_f = df_f[mask]
        if filter_reponer:
            df_f = df_f[df_f["Stock Actual"] < U]
        if show_comp_f:
            df_f = df_f[df_f["Disponible Neto"] < 0]

        if not df_f.empty:
            excel_b = descargar_excel_agrupado(df_f)
            if excel_b:
                st.download_button("📥 Descargar Comparativa", data=excel_b,
                                   file_name="stock_agrupado.xlsx")

            # Vencimientos en cards
            prod_df_venc = obtener_productos_completo()

            items = df_f.to_dict("records")
            cols_g = st.columns(4)
            for i, item in enumerate(items):
                with cols_g[i % 4]:
                    stk   = item["Stock Actual"]
                    comp  = item.get("Comprometido", 0)
                    disp  = item.get("Disponible Neto", stk)
                    clase = "card-warning" if stk <= 0 else ("card-low" if stk < U else "card-normal")
                    b_neg  = '<span class="neg-badge">NEGATIVO</span>'     if stk  < 0    else ""
                    b_comp = '<span class="comp-badge">COMPROMETIDO</span>'if comp > 0    else ""

                    # Vencimiento
                    venc_info = ""
                    if not prod_df_venc.empty:
                        row_v = prod_df_venc[prod_df_venc["nombre"] == item["Producto"]]
                        if not row_v.empty:
                            fv = safe_str(row_v.iloc[0].get("fecha_vencimiento",""))
                            if fv:
                                dias_v = dias_hasta(fv)
                                if dias_v <= 90:
                                    color_v = "red" if dias_v <= 30 else "orange"
                                    venc_info = f'<br><span style="color:{color_v};font-size:.75rem">⏰ Vence en {dias_v}d ({fv})</span>'
                                    b_comp += '<span class="venc-badge">VENCE</span>'

                    comp_line = (f"<br><b>🔒 Comprometido:</b> {comp:,.1f} | "
                                 f"<b>Disp.Neto:</b> {disp:,.1f}") if comp > 0 else ""

                    # Clientes con entrega pendiente para este producto
                    clientes_pend_line = ""
                    if not ent_panel.empty and comp > 0:
                        cli_pend = (ent_panel[
                            (ent_panel["producto"].str.lower() == item["Producto"].lower()) &
                            (ent_panel["pendiente"] > 0)
                        ][["cliente","pendiente","deposito"]]
                        .sort_values("pendiente", ascending=False)
                        .head(5))
                        if not cli_pend.empty:
                            filas = "".join(
                                f"<tr><td style='padding:1px 6px'>{r['cliente']}</td>"
                                f"<td style='padding:1px 6px;text-align:right'><b>{r['pendiente']:,.0f}</b></td>"
                                f"<td style='padding:1px 6px;color:#6c757d'>{r['deposito'] or '-'}</td></tr>"
                                for _, r in cli_pend.iterrows()
                            )
                            clientes_pend_line = (
                                f"<br><b>👥 Clientes con pendiente:</b>"
                                f"<table style='width:100%;font-size:.75rem;margin-top:4px'>"
                                f"<tr style='color:#6c757d'><td>Cliente</td><td>Pend.</td><td>Depósito</td></tr>"
                                f"{filas}</table>"
                            )

                    st.markdown(f"""
                        <div class="stock-card {clase}">
                            <div class="stock-title">{item['Producto']}{b_neg}{b_comp}</div>
                            <span class="stock-value">{stk:,.1f}
                                <small class="stock-unit">{item['Unidad']}</small></span>
                            <div class="stock-info">
                                <b>🆔</b> {item['Código']}<br>
                                <b>📍</b> <span class="label-blue">{item['Deposito']}</span>
                                {comp_line}{venc_info}{clientes_pend_line}
                            </div>
                        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # Movimiento manual
        with st.expander("➕ Registrar movimiento manual"):
            cm1, cm2 = st.columns(2)
            with cm1:
                prod_m  = st.selectbox("Producto", sorted(stock_df["Producto"].unique()), key="mov_prod")
                tipo_m  = st.radio("Tipo", ["Entrada","Salida"], horizontal=True, key="mov_tipo")
            with cm2:
                cant_m  = st.number_input("Cantidad", min_value=0.01, step=0.5, key="mov_cant")
                dep_m   = st.selectbox("Depósito", sorted(stock_df["Deposito"].unique()), key="mov_dep")
            lote_m = st.text_input("Lote", value="S/L", key="mov_lote")
            ref_m  = st.text_input("Referencia", value="", key="mov_ref")
            # Advertencia de stock disponible en tiempo real
            if tipo_m == "Salida":
                stk_disp = float(stock_df[
                    (stock_df["Producto"] == prod_m) & (stock_df["Deposito"] == dep_m)
                ]["Stock Actual"].sum()) if not stock_df.empty else 0.0
                st.metric("Stock disponible en depósito seleccionado", f"{stk_disp:,.1f}",
                          help="Cantidad actual en el depósito antes de esta salida")
                if cant_m > stk_disp:
                    st.warning(f"⚠️ La cantidad ingresada ({cant_m:,.1f}) supera el stock disponible ({stk_disp:,.1f}). El stock quedará negativo.")
                if stk_disp <= 0:
                    st.error("🚫 El stock en este depósito ya es cero o negativo.")
            if st.session_state.mov_pendiente is None:
                if st.button("📋 Preparar movimiento"):
                    st.session_state.mov_pendiente = dict(
                        producto=prod_m, tipo=tipo_m, cantidad=cant_m,
                        deposito=dep_m, lote=lote_m, referencia=ref_m
                    )
                    st.rerun()
            else:
                p = st.session_state.mov_pendiente
                st.warning(f"**¿Confirmar?** {p['tipo']} | {p['producto']} | "
                           f"{p['cantidad']:,.2f} | {p['deposito']}")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Confirmar", type="primary"):
                        conn = conectar_db()
                        id_p = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",
                                            (p["producto"],)).fetchone()
                        if id_p:
                            conn.execute("""INSERT INTO movimientos
                                (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen,usuario)
                                VALUES (?,?,?,?,?,?,?,?,?)""",
                                (datetime.now().strftime("%d/%m/%Y %H:%M"), p["tipo"],
                                 id_p[0], p["cantidad"], p["lote"], p["referencia"],
                                 p["deposito"], "manual", usuario_actual()))
                            conn.commit()
                        conn.close()
                        limpiar_cache()
                        st.session_state.mov_pendiente = None
                        st.success("✅ Registrado.")
                        st.rerun()
                with cc2:
                    if st.button("❌ Cancelar"):
                        st.session_state.mov_pendiente = None
                        st.rerun()

        # Transferencias entre depósitos
        st.markdown("---")
        with st.expander("↔️ Transferencia entre Depósitos"):
            ct1, ct2 = st.columns(2)
            with ct1:
                prod_t = st.selectbox("Producto", sorted(stock_df["Producto"].unique()), key="trans_prod")
                dep_t_options = sorted(stock_df[stock_df["Producto"]==prod_t]["Deposito"].unique().tolist())
                dep_origen = st.selectbox("Depósito Origen", dep_t_options, key="trans_origen")
                stk_orig = float(stock_df[
                    (stock_df["Producto"]==prod_t) & (stock_df["Deposito"]==dep_origen)
                ]["Stock Actual"].sum())
                st.info(f"Stock disponible en origen: **{stk_orig:,.1f}**")
            with ct2:
                todos_deps = sorted(stock_df["Deposito"].unique().tolist())
                dep_destino = st.selectbox("Depósito Destino", todos_deps, key="trans_destino")
                cant_t  = st.number_input("Cantidad", min_value=0.01,
                                          max_value=max(stk_orig, 0.01), step=0.5, key="trans_cant")
                lote_t  = st.text_input("Lote", value="S/L", key="trans_lote")
            ref_t = st.text_input("Referencia transferencia", key="trans_ref")

            if dep_origen == dep_destino:
                st.warning("Origen y destino deben ser distintos.")
            else:
                if st.session_state.trans_pendiente is None:
                    if not es_admin():
                        cod_sup_t = st.text_input("Código de supervisor", type="password",
                                                   key="cod_sup_trans",
                                                   help="Requerido para operadores. Los admins no necesitan código.")
                        puede_transferir = cod_sup_t == (obtener_metadata("codigo_supervisor") or "1234")
                        if cod_sup_t and not puede_transferir:
                            st.error("❌ Código de supervisor incorrecto.")
                    else:
                        puede_transferir = True
                    if st.button("↔️ Preparar transferencia", disabled=not puede_transferir):
                        st.session_state.trans_pendiente = dict(
                            producto=prod_t, dep_origen=dep_origen, dep_destino=dep_destino,
                            cantidad=cant_t, lote=lote_t, referencia=ref_t
                        )
                        st.rerun()
                else:
                    tp = st.session_state.trans_pendiente
                    st.warning(
                        f"**¿Confirmar?** {tp['cantidad']:,.1f} × {tp['producto']} | "
                        f"{tp['dep_origen']} → {tp['dep_destino']}"
                    )
                    tc1, tc2 = st.columns(2)
                    with tc1:
                        if st.button("✅ Confirmar transferencia", type="primary"):
                            conn = conectar_db()
                            id_p = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",
                                                (tp["producto"],)).fetchone()
                            if id_p:
                                ts  = datetime.now().strftime("%d/%m/%Y %H:%M")
                                ref = tp["referencia"] or f"Transferencia {tp['dep_origen']} → {tp['dep_destino']}"
                                usu = usuario_actual()
                                for tipo, dep in [("Salida", tp["dep_origen"]), ("Entrada", tp["dep_destino"])]:
                                    conn.execute("""INSERT INTO movimientos
                                        (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen,usuario)
                                        VALUES (?,?,?,?,?,?,?,?,?)""",
                                        (ts, tipo, id_p[0], tp["cantidad"], tp["lote"], ref, dep, "manual", usu))
                                conn.execute("""INSERT INTO transferencias
                                    (fecha_hora,id_producto,cantidad,lote,deposito_origen,deposito_destino,referencia,usuario)
                                    VALUES (?,?,?,?,?,?,?,?)""",
                                    (ts, id_p[0], tp["cantidad"], tp["lote"],
                                     tp["dep_origen"], tp["dep_destino"], ref, usu))
                                conn.commit()
                            conn.close()
                            limpiar_cache()
                            st.success(f"✅ Transferencia ejecutada.")
                            st.session_state.trans_pendiente = None
                            st.rerun()
                    with tc2:
                        if st.button("❌ Cancelar transferencia"):
                            st.session_state.trans_pendiente = None
                            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN REUTILIZABLE: ENTREGAS
# ═══════════════════════════════════════════════════════════════════════════════
def mostrar_tab_entregas(hoja_nombre, titulo):
    st.subheader(titulo)
    if hoja_nombre == "LA CLEMENTINA S.A":
        with st.expander("📂 Importar TODAS las hojas", expanded=obtener_entregas().empty):
            st.info("Subí el archivo completo de entregas Monsanto/Bayer (4 hojas).")
            arch = st.file_uploader("Archivo entregas (.xlsx)", type=["xlsx","xls"],
                                    key="uploader_entregas_global")
            co1, co2 = st.columns(2)
            with co1:
                descontar = st.toggle("🔄 Registrar como Salidas", value=False, key="tog_descontar")
            with co2:
                sf       = obtener_stock_full()
                dep_opts = sf["Deposito"].unique().tolist() if not sf.empty else ["0"]
                dep_sal  = st.selectbox("Depósito origen", dep_opts, key="dep_sal_g") if descontar else None

            if arch and st.button("🚀 IMPORTAR", type="primary"):
                try:
                    df_u = parsear_entregas_excel(arch)
                    if df_u.empty:
                        st.error("No se pudieron leer las hojas.")
                    else:
                        conn = conectar_db()
                        conn.execute("DELETE FROM entregas")
                        # Batch insert entregas
                        ent_batch = [
                            (r["hoja"], r["rto"], r["dia_recibido"], r["cliente"],
                             r["deposito"], r["cantidad_comprada"], r["producto"], r["lote"],
                             r["cant_entregada"], r["pendiente"], r["estado"], r["vendedor"])
                            for _, r in df_u.iterrows()
                        ]
                        conn.cursor().executemany("""INSERT INTO entregas
                            (hoja,rto,dia_recibido,cliente,deposito,cantidad_comprada,
                            producto,lote,cant_entregada,pendiente,estado,vendedor)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", ent_batch)
                        ok = len(ent_batch)
                        sal = 0; no_match = []
                        if descontar:
                            # Obtener IDs de productos de una sola vez
                            prod_names = df_u[df_u["cant_entregada"] > 0]["producto"].unique().tolist()
                            if prod_names:
                                ph = ",".join(["?"] * len(prod_names))
                                id_rows = conn.execute(
                                    f"SELECT id_producto, nombre FROM productos WHERE nombre IN ({ph})",
                                    prod_names).fetchall()
                                id_map_e = {row[1]: row[0] for row in id_rows}
                                _ts_e = datetime.now().strftime("%d/%m/%Y %H:%M")
                                _usu_e = usuario_actual()
                                sal_batch = []
                                for _, r in df_u[df_u["cant_entregada"] > 0].iterrows():
                                    pid = id_map_e.get(r["producto"])
                                    if pid:
                                        sal_batch.append((
                                            r["dia_recibido"] or _ts_e, "Salida", pid,
                                            r["cant_entregada"], r["lote"] or "S/L",
                                            f"Entrega {r['cliente']}", dep_sal, "entrega", _usu_e))
                                        sal += 1
                                    elif r["producto"] not in no_match:
                                        no_match.append(r["producto"])
                                if sal_batch:
                                    conn.cursor().executemany("""INSERT INTO movimientos
                                        (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,
                                         referencia,deposito,origen,usuario)
                                        VALUES (?,?,?,?,?,?,?,?,?)""", sal_batch)
                        conn.commit(); conn.close()
                        guardar_metadata("ultima_importacion_entregas",
                                         datetime.now().strftime("%d/%m/%Y %H:%M"))
                        limpiar_cache()
                        msg = f"✅ {ok} registros. {sal} salidas." if descontar else f"✅ {ok} registros."
                        st.success(msg)
                        if no_match: st.warning(f"Sin coincidencia: {', '.join(no_match)}")
                        st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

    df_h = obtener_entregas(hoja_nombre)
    if df_h.empty:
        st.info("Sin datos. Importá en 'LC / LCAGRO'.")
        return

    df_h["dias_pend"] = df_h["dia_recibido"].apply(dias_desde)
    tc = df_h["cantidad_comprada"].sum()
    te = df_h["cant_entregada"].sum()
    tp = df_h["pendiente"].sum()
    pct = (te/tc*100) if tc > 0 else 0
    v30 = len(df_h[(df_h["pendiente"] > 0) & (df_h["dias_pend"] > 30)])
    v60 = len(df_h[(df_h["pendiente"] > 0) & (df_h["dias_pend"] > 60)])

    k1,k2,k3,k4,k5,k6,k7 = st.columns(7)
    with k1: st.metric("Registros",     len(df_h))
    with k2: st.metric("Clientes",      df_h["cliente"].nunique())
    with k3: st.metric("Comprado",      f"{tc:,.0f}")
    with k4: st.metric("Entregado",     f"{te:,.0f}", delta=f"{pct:.1f}%")
    with k5: st.metric("Pendiente",     f"{tp:,.0f}", delta=f"-{tp:,.0f}" if tp>0 else "0", delta_color="inverse")
    with k6: st.metric("⏳ +30d",       v30, delta=-v30, delta_color="inverse")
    with k7: st.metric("🔴 +60d",       v60, delta=-v60, delta_color="inverse")

    if v60 > 0: st.error(f"🔴 {v60} entrega(s) con más de 60 días sin completar.")
    elif v30>0: st.warning(f"⚠️ {v30} entrega(s) con más de 30 días pendiente.")

    st.markdown("---")
    cf1,cf2,cf3,cf4,cf5 = st.columns(5)
    with cf1:
        f_est = st.selectbox("Estado", ["Todos"]+sorted(df_h["estado"].dropna().unique().tolist()),
                             key=f"fest_{hoja_nombre}")
    with cf2:
        f_pr = st.selectbox("Producto", ["Todos"]+sorted(df_h["producto"].dropna().unique().tolist()),
                            key=f"fprod_{hoja_nombre}")
    with cf3:
        f_vd = st.selectbox("Vendedor",
                            ["Todos"]+sorted(df_h["vendedor"].dropna().replace("","S/V").unique().tolist()),
                            key=f"fvend_{hoja_nombre}")
    with cf4:
        f_cli = st.text_input("🔍 Cliente", placeholder="Buscar...", key=f"fcli_{hoja_nombre}")
    with cf5:
        f_edad = st.selectbox("Antigüedad",
                              ["Todos","Normal (≤30d)","Demorado (30-60d)","Crítico (>60d)"],
                              key=f"fedad_{hoja_nombre}")

    df_f2 = df_h.copy()
    if f_est  != "Todos": df_f2 = df_f2[df_f2["estado"] == f_est]
    if f_pr   != "Todos": df_f2 = df_f2[df_f2["producto"] == f_pr]
    if f_vd   != "Todos": df_f2 = df_f2[df_f2["vendedor"].replace("","S/V") == f_vd]
    if f_cli:             df_f2 = df_f2[df_f2["cliente"].str.contains(f_cli, case=False, na=False)]
    if   f_edad == "Normal (≤30d)":       df_f2 = df_f2[df_f2["dias_pend"] <= 30]
    elif f_edad == "Demorado (30-60d)":   df_f2 = df_f2[(df_f2["dias_pend"]>30) & (df_f2["dias_pend"]<=60)]
    elif f_edad == "Crítico (>60d)":      df_f2 = df_f2[df_f2["dias_pend"] > 60]

    st.markdown(f"**{len(df_f2)} registros**")
    if not df_f2.empty:
        sub = (df_f2.groupby("producto")
               .agg(Comprado=("cantidad_comprada","sum"), Entregado=("cant_entregada","sum"),
                    Pendiente=("pendiente","sum"), Clientes=("cliente","nunique"))
               .reset_index().rename(columns={"producto":"Producto"}))
        sub["% Entregado"] = (sub["Entregado"]/sub["Comprado"].replace(0,1)*100).round(1).astype(str)+"%"
        st.dataframe(sub, use_container_width=True, hide_index=True)
        st.markdown("---")

        cols_b = ["dia_recibido","cliente","producto","cantidad_comprada",
                  "cant_entregada","pendiente","estado","vendedor","dias_pend"]
        tiene_lote = (df_f2["lote"].replace("","").notna()) & (df_f2["lote"].replace("","") != "")
        if tiene_lote.any(): cols_b.insert(3,"lote")
        if "deposito" in df_f2.columns and df_f2["deposito"].nunique()>1: cols_b.insert(1,"deposito")
        if "rto" in df_f2.columns: cols_b.insert(0,"rto")
        cols_b = [c for c in cols_b if c in df_f2.columns]
        df_t = df_f2[cols_b].rename(columns={
            "dia_recibido":"Fecha","cliente":"Cliente","producto":"Producto",
            "cantidad_comprada":"Comprado","cant_entregada":"Entregado",
            "pendiente":"Pendiente","estado":"Estado","vendedor":"Vendedor",
            "lote":"Lote","deposito":"Depósito","rto":"RTO","dias_pend":"Días"
        })
        st.dataframe(df_t, use_container_width=True, hide_index=True)
        st.download_button("📥 Exportar Excel", data=to_excel_bytes(df_t, "Entregas"),
                           file_name=f"entregas_{hoja_nombre.replace(' ','_')}.xlsx")


with tab2: mostrar_tab_entregas("LA CLEMENTINA S.A", "📋 Entregas — La Clementina / LCAgro")
with tab3: mostrar_tab_entregas("BAYER DEP55",       "🌿 Consignado Bayer — Depósito 55")
with tab4: mostrar_tab_entregas("BAYER DIRECTA",     "🚚 Facturación Directa Bayer 43-60")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — STOCK FÍSICO
# ═══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("📋 Toma de Stock Físico")
    st_df = obtener_stock_full()
    if not st_df.empty:
        st.download_button("📥 Descargar Planilla de Conteo (.xlsx)",
                           data=descargar_planilla_inventario(st_df),
                           file_name="Planilla_Toma_Stock.xlsx")
        st.markdown("---")
        st.write("### 📝 Registrar Ajuste Auditado")
        ci1, ci2, ci3 = st.columns(3)
        with ci1:
            p_inv = st.selectbox("Producto", sorted(st_df["Producto"].unique()), key="inv_p")
        with ci2:
            d_inv = st.selectbox("Depósito", sorted(st_df["Deposito"].unique()), key="inv_d")
        with ci3:
            filt_s   = st_df[(st_df["Producto"]==p_inv) & (st_df["Deposito"]==d_inv)]
            val_sis  = filt_s.iloc[0]["Stock Actual"] if not filt_s.empty else 0.0
            st.metric("Stock en Sistema", f"{val_sis:,.1f}")
        ci4, ci5 = st.columns(2)
        with ci4:
            val_fis = st.number_input("Conteo Físico Real", min_value=0.0, step=1.0, value=float(val_sis))
        with ci5:
            obs_inv = st.text_input("Observaciones / Auditor")
        dif = val_fis - val_sis
        st.metric("Diferencia detectada", f"{dif:,.1f}", delta=dif)
        if st.button("💾 Guardar Auditoría"):
            conn   = conectar_db()
            cod_p  = safe_str(st_df[st_df["Producto"]==p_inv].iloc[0]["Código"]) if not st_df[st_df["Producto"]==p_inv].empty else "S/C"
            conn.execute("""INSERT INTO inventario_fisico
                (fecha_conteo,codigo,producto,deposito,stock_sistema,conteo_fisico,diferencia,observaciones)
                VALUES (?,?,?,?,?,?,?,?)""",
                (datetime.now().strftime("%d/%m/%Y %H:%M"), cod_p, p_inv, d_inv, val_sis, val_fis, dif, obs_inv))
            if dif != 0:
                id_p = conn.execute("SELECT id_producto FROM productos WHERE nombre=?", (p_inv,)).fetchone()
                if id_p:
                    conn.execute("""INSERT INTO movimientos
                        (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen,usuario)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (datetime.now().strftime("%d/%m/%Y %H:%M"),
                         "Entrada" if dif>0 else "Salida", id_p[0], abs(dif),
                         "S/L", f"Ajuste Inventario. {obs_inv}", d_inv, "manual", usuario_actual()))
            conn.commit(); conn.close()
            limpiar_cache()
            st.success("✅ Auditoría guardada.")
            st.rerun()
    else:
        st.info("Sin datos de stock.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — HISTORIAL
# ═══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("📜 Historial de Movimientos")
    hist_df = obtener_historial_movimientos()

    if hist_df.empty:
        st.info("Sin movimientos registrados.")
    else:
        ch1, ch2, ch3 = st.columns(3)
        with ch1: f_tipo_h = st.selectbox("Tipo", ["Todos","Entrada","Salida"])
        with ch2: f_orig_h = st.selectbox("Origen", ["Todos","excel","manual","entrega"])
        with ch3: f_bus_h  = st.text_input("🔍 Buscar")
        cd1, cd2, cd3 = st.columns(3)
        with cd1:
            f_desde = st.date_input("Desde", value=datetime.now().date()-timedelta(days=30))
        with cd2:
            f_hasta = st.date_input("Hasta", value=datetime.now().date())
        with cd3:
            f_anulados = st.toggle("Mostrar anulados", value=False)

        df_hf = hist_df.copy()
        if f_tipo_h != "Todos": df_hf = df_hf[df_hf["Tipo"] == f_tipo_h]
        if f_orig_h != "Todos": df_hf = df_hf[df_hf["Origen"] == f_orig_h]
        if f_bus_h:
            df_hf = df_hf[
                df_hf["Producto"].str.contains(f_bus_h, case=False, na=False) |
                df_hf["Lote"].astype(str).str.contains(f_bus_h, case=False, na=False) |
                df_hf["Referencia"].astype(str).str.contains(f_bus_h, case=False, na=False)
            ]
        if not f_anulados:
            df_hf = df_hf[df_hf["Anulado"] == 0]

        def parse_fh(s):
            try: return datetime.strptime(str(s)[:10], "%d/%m/%Y").date()
            except: return None
        df_hf["_fdt"] = df_hf["Fecha"].apply(parse_fh)
        df_hf = df_hf[(df_hf["_fdt"] >= f_desde) & (df_hf["_fdt"] <= f_hasta)].drop(columns=["_fdt"])

        st.markdown(f"**{len(df_hf)} filas**")
        st.dataframe(df_hf, use_container_width=True, hide_index=True)

        if not df_hf.empty:
            st.download_button("📥 Exportar historial", data=to_excel_bytes(df_hf, "Historial"),
                               file_name="historial.xlsx")

        # Anular movimiento
        if es_admin():
            st.markdown("---")
            with st.expander("🔄 Anular Movimiento"):
                id_an = st.number_input("ID del movimiento a anular", min_value=1, step=1, key="id_anular")
                if st.button("🔄 Anular", key="btn_anular"):
                    conn = conectar_db()
                    row_an = conn.execute(
                        "SELECT tipo_movimiento,id_producto,cantidad,lote,deposito,referencia,anulado "
                        "FROM movimientos WHERE id_movimiento=?", (int(id_an),)
                    ).fetchone()
                    if row_an:
                        if row_an[6]:
                            st.error("Este movimiento ya fue anulado.")
                        else:
                            tipo_rev = "Salida" if row_an[0]=="Entrada" else "Entrada"
                            conn.execute("""INSERT INTO movimientos
                                (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen,usuario)
                                VALUES (?,?,?,?,?,?,?,?,?)""",
                                (datetime.now().strftime("%d/%m/%Y %H:%M"), tipo_rev,
                                 row_an[1], row_an[2], row_an[3],
                                 f"ANULACIÓN de ID {id_an}: {row_an[5]}", row_an[4], "manual",
                                 usuario_actual()))
                            conn.execute("UPDATE movimientos SET anulado=1 WHERE id_movimiento=?", (int(id_an),))
                            conn.commit()
                            limpiar_cache()
                            st.success(f"✅ Movimiento {id_an} anulado.")
                    else:
                        st.error(f"ID {id_an} no encontrado.")
                    conn.close()
                    st.rerun()

        # Historial de transferencias
        conn = conectar_db()
        df_tr = _rsql("""
                SELECT t.id_transferencia "ID", t.fecha_hora "Fecha", p.nombre "Producto",
                       t.cantidad "Cantidad", t.lote "Lote",
                       t.deposito_origen "Origen", t.deposito_destino "Destino",
                       t.referencia "Referencia", t.usuario "Usuario"
                FROM transferencias t JOIN productos p ON t.id_producto=p.id_producto
                ORDER BY t.id_transferencia DESC""", conn)
        df_inv_h = _rsql("SELECT * FROM inventario_fisico ORDER BY id_inventario DESC", conn)
        conn.close()

        if not df_tr.empty:
            st.markdown("---")
            st.subheader("↔️ Historial de Transferencias")
            st.dataframe(df_tr, use_container_width=True, hide_index=True)

        if not df_inv_h.empty:
            st.markdown("---")
            st.subheader("📋 Auditorías de Inventario")
            st.dataframe(df_inv_h.rename(columns={
                "fecha_conteo":"Fecha","codigo":"Código","producto":"Producto","deposito":"Depósito",
                "stock_sistema":"Sistema","conteo_fisico":"Conteo","diferencia":"Dif","observaciones":"Notas"
            }), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7 — VALORIZACIÓN Y PRECIOS
# ═══════════════════════════════════════════════════════════════════════════════
with tab7:
    st.subheader("💲 Valorización de Inventario")
    st.caption("Aquí podés asignar precios a cada producto para calcular el valor total del inventario en USD y ARS.")
    stk_full = obtener_stock_full()
    prod_full = obtener_productos_completo()

    if stk_full.empty:
        st.info("Sin datos de stock para valorizar.")
    else:
        # Tipo de cambio
        cv1, cv2, cv3 = st.columns(3)
        with cv1:
            tc_stored = float(obtener_metadata("tipo_cambio") or 1000)
            tipo_cambio = st.number_input("Tipo de cambio ARS/USD",
                                          min_value=1.0, value=tc_stored, step=10.0, key="tc_val")
            if st.button("💾 Guardar TC"):
                guardar_metadata("tipo_cambio", str(tipo_cambio))
                st.success("Tipo de cambio actualizado.")

        st.markdown("---")
        st.write("### 🏷️ Actualizar Precios por Producto")
        st.caption("Editá directamente la tabla. Los precios se guardan al hacer clic en Guardar.")

        if not prod_full.empty:
            cols_precio = ["nombre","precio_unitario","moneda_precio","proveedor","fecha_vencimiento"]
            cols_precio = [c for c in cols_precio if c in prod_full.columns]
            df_edit = prod_full[cols_precio].copy().rename(columns={
                "nombre":"Producto","precio_unitario":"Precio","moneda_precio":"Moneda",
                "proveedor":"Proveedor","fecha_vencimiento":"Vencimiento"
            })
            edited = st.data_editor(
                df_edit,
                column_config={
                    "Precio":      st.column_config.NumberColumn("Precio", min_value=0.0, format="%.2f"),
                    "Moneda":      st.column_config.SelectboxColumn("Moneda", options=["USD","ARS"]),
                    "Proveedor":   st.column_config.TextColumn("Proveedor"),
                    "Vencimiento": st.column_config.TextColumn("Vencimiento (dd/mm/aaaa)"),
                },
                hide_index=True,
                use_container_width=True,
                key="editor_precios"
            )
            if st.button("💾 Guardar Precios", type="primary"):
                conn = conectar_db()
                for _, r in edited.iterrows():
                    precio = float(r["Precio"]) if r["Precio"] else 0.0
                    moneda = r.get("Moneda","USD") or "USD"
                    prov   = r.get("Proveedor","") or ""
                    venc   = r.get("Vencimiento","") or ""
                    conn.execute("""UPDATE productos
                        SET precio_unitario=?, moneda_precio=?, proveedor=?, fecha_vencimiento=?
                        WHERE nombre=?""",
                        (precio, moneda, prov, venc, r["Producto"]))
                    if precio > 0:
                        id_p = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",
                                            (r["Producto"],)).fetchone()
                        if id_p:
                            conn.execute("""INSERT INTO precios_historicos
                                (id_producto,fecha,precio,moneda,usuario) VALUES (?,?,?,?,?)""",
                                (id_p[0], datetime.now().strftime("%d/%m/%Y"), precio, moneda,
                                 usuario_actual()))
                conn.commit(); conn.close()
                limpiar_cache()
                st.success("✅ Precios actualizados.")
                st.rerun()

        st.markdown("---")
        st.write("### 📊 Inventario Valorizado")
        prod_refr = obtener_productos_completo()
        if not prod_refr.empty:
            stk_val = stk_full.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()
            stk_val = stk_val.merge(
                prod_refr[["nombre","precio_unitario","moneda_precio"]].rename(columns={"nombre":"Producto"}),
                on="Producto", how="left"
            )
            stk_val["precio_unitario"] = stk_val["precio_unitario"].fillna(0)
            stk_val["moneda_precio"]   = stk_val["moneda_precio"].fillna("USD")
            stk_val["Valor_USD"] = stk_val.apply(
                lambda r: r["Stock Actual"] * r["precio_unitario"]
                          if r["moneda_precio"]=="USD"
                          else r["Stock Actual"] * r["precio_unitario"] / tipo_cambio, axis=1
            )
            stk_val["Valor_ARS"] = stk_val["Valor_USD"] * tipo_cambio
            total_usd = stk_val["Valor_USD"].sum()
            total_ars = stk_val["Valor_ARS"].sum()

            cv_kpi1, cv_kpi2 = st.columns(2)
            with cv_kpi1: st.metric("💵 Valor Total USD", f"USD {total_usd:,.2f}")
            with cv_kpi2: st.metric("💴 Valor Total ARS", f"ARS {total_ars:,.0f}")

            df_show = (stk_val[["Producto","Unidad","Stock Actual",
                                 "precio_unitario","moneda_precio","Valor_USD","Valor_ARS"]]
                       .sort_values("Valor_USD", ascending=False)
                       .rename(columns={
                           "precio_unitario":"Precio Unit.", "moneda_precio":"Moneda",
                           "Valor_USD":"Valor USD","Valor_ARS":"Valor ARS"
                       }))
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.download_button("📥 Exportar Valorización",
                               data=to_excel_bytes(df_show, "Valorización"),
                               file_name="valorizacion_stock.xlsx")

        st.markdown("---")
        st.write("### 🛒 Orden de Reposición Sugerida")
        U_rep = st.session_state.umbral_alerta
        consumo_df = calcular_rotacion_stock()
        orden_bin  = generar_orden_reposicion(stk_full, U_rep, consumo_df)
        bajo_n_rep = len(stk_full[stk_full["Stock Actual"] < U_rep])
        st.info(f"{bajo_n_rep} productos con stock bajo umbral ({U_rep}). "
                "El Excel incluye la cantidad sugerida basada en consumo de los últimos 90 días.")
        st.download_button("📥 Descargar Orden de Reposición (.xlsx)",
                           data=orden_bin, file_name="orden_reposicion.xlsx")

        # Historial de precios
        st.markdown("---")
        st.write("### 📈 Historial de Precios")
        conn = conectar_db()
        df_ph = _rsql("""
                SELECT ph.fecha "Fecha", p.nombre "Producto",
                       ph.precio "Precio", ph.moneda "Moneda", ph.usuario "Usuario"
                FROM precios_historicos ph JOIN productos p ON ph.id_producto=p.id_producto
                ORDER BY ph.id_precio DESC LIMIT 200""", conn)
        conn.close()
        if not df_ph.empty:
            prod_hist = st.selectbox("Producto para ver evolución",
                                     ["Todos"]+sorted(df_ph["Producto"].unique().tolist()),
                                     key="prod_hist")
            df_ph_f = df_ph if prod_hist=="Todos" else df_ph[df_ph["Producto"]==prod_hist]
            st.dataframe(df_ph_f, use_container_width=True, hide_index=True)
            if prod_hist != "Todos" and len(df_ph_f) > 1:
                fig_ph = px.line(df_ph_f.sort_values("Fecha"), x="Fecha", y="Precio",
                                 title=f"Evolución Precio — {prod_hist}")
                st.plotly_chart(fig_ph, use_container_width=True)
        else:
            st.caption("Sin historial de precios todavía.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 8 — REPORTES
# ═══════════════════════════════════════════════════════════════════════════════
with tab8:
    st.subheader("📈 Reportes y Análisis")
    r_tab1, r_tab2, r_tab3, r_tab4 = st.tabs([
        "👥 Dashboard Vendedores",
        "🔄 Rotación de Stock",
        "⏰ Vencimientos",
        "📄 Reporte Mensual"
    ])

    # ── Vendedores ────────────────────────────────────────────────────────────
    with r_tab1:
        st.write("### 👥 Performance por Vendedor")
        ent_all = obtener_entregas()
        if ent_all.empty:
            st.info("Sin datos de entregas.")
        else:
            ent_all["vendedor"] = ent_all["vendedor"].replace("","S/V")
            rv1, rv2 = st.columns(2)
            with rv1:
                f_hoja_v = st.selectbox("Hoja",
                    ["Todas","LA CLEMENTINA S.A","LCAGRO S.A","BAYER DEP55","BAYER DIRECTA"],
                    key="f_hoja_vend")
            with rv2:
                f_est_v = st.selectbox("Estado",
                    ["Todos"]+sorted(ent_all["estado"].dropna().unique().tolist()),
                    key="f_est_vend")
            df_v = ent_all.copy()
            if f_hoja_v != "Todas": df_v = df_v[df_v["hoja"]==f_hoja_v]
            if f_est_v  != "Todos": df_v = df_v[df_v["estado"]==f_est_v]

            pivot_v = df_v.groupby("vendedor").agg(
                Clientes=("cliente","nunique"),
                Registros=("id_entrega","count"),
                Comprado=("cantidad_comprada","sum"),
                Entregado=("cant_entregada","sum"),
                Pendiente=("pendiente","sum"),
            ).reset_index()
            pivot_v["% Entregado"] = (pivot_v["Entregado"]/pivot_v["Comprado"].replace(0,1)*100).round(1)
            pivot_v = pivot_v.sort_values("Pendiente", ascending=False)
            st.dataframe(pivot_v, use_container_width=True, hide_index=True)

            fig_vend = px.bar(pivot_v, x="vendedor", y=["Entregado","Pendiente"],
                              barmode="stack", title="Entregado vs Pendiente por Vendedor",
                              color_discrete_sequence=["#28a745","#dc3545"])
            fig_vend.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_vend, use_container_width=True)

            # Pivot producto × vendedor
            st.write("#### Pendiente por Producto × Vendedor")
            pv2 = df_v[df_v["pendiente"] > 0].pivot_table(
                index="producto", columns="vendedor", values="pendiente",
                aggfunc="sum", fill_value=0
            ).reset_index()
            st.dataframe(pv2, use_container_width=True, hide_index=True)

    # ── Rotación ─────────────────────────────────────────────────────────────
    with r_tab2:
        st.write("### 🔄 Rotación de Stock")
        st.caption("Días de cobertura = Stock actual ÷ Salidas promedio diarias (90 días).")
        dias_h = st.slider("Ventana histórica (días)", 30, 180, 90, key="dias_rot")
        df_rot = calcular_rotacion_stock(dias_h)
        if df_rot.empty:
            st.info("Sin movimientos suficientes para calcular rotación.")
        else:
            cr1, cr2, cr3 = st.columns(3)
            with cr1:
                sin_mov = len(df_rot[df_rot["Días_Cobertura"].isna()])
                st.metric("Sin movimiento", sin_mov)
            with cr2:
                crit_rot = len(df_rot[df_rot["Días_Cobertura"].notna() & (df_rot["Días_Cobertura"] < 30)])
                st.metric("Cobertura < 30d 🚨", crit_rot)
            with cr3:
                ok_rot = len(df_rot[df_rot["Días_Cobertura"].notna() & (df_rot["Días_Cobertura"] >= 30)])
                st.metric("Cobertura OK ✅", ok_rot)

            st.dataframe(
                df_rot.rename(columns={
                    "Total_Salidas":"Salidas 90d","Sal_Diarias":"Sal/Día",
                    "Días_Cobertura":"Días Cobertura","Rotación_Anual":"Rotación Anual"
                }),
                use_container_width=True, hide_index=True
            )

            df_rot_graf = df_rot[df_rot["Días_Cobertura"].notna()].sort_values("Días_Cobertura").head(20)
            if not df_rot_graf.empty:
                fig_rot = px.bar(df_rot_graf, x="Días_Cobertura", y="Producto",
                                 orientation="h", title="Días de Cobertura (Top 20 más críticos)",
                                 color="Días_Cobertura", color_continuous_scale="RdYlGn")
                fig_rot.update_layout(height=500, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_rot, use_container_width=True)

            st.download_button("📥 Exportar Rotación",
                               data=to_excel_bytes(df_rot, "Rotacion"),
                               file_name="rotacion_stock.xlsx")

    # ── Vencimientos ─────────────────────────────────────────────────────────
    with r_tab3:
        st.write("### ⏰ Control de Vencimientos")
        prod_venc = obtener_productos_completo()
        if prod_venc.empty or "fecha_vencimiento" not in prod_venc.columns:
            st.info("Sin fechas de vencimiento cargadas. Actualizalas en Valorización → Precios.")
        else:
            prod_venc = prod_venc[prod_venc["fecha_vencimiento"].notna() &
                                   (prod_venc["fecha_vencimiento"] != "")]
            if prod_venc.empty:
                st.info("Sin fechas de vencimiento cargadas.")
            else:
                prod_venc["dias_hasta_venc"] = prod_venc["fecha_vencimiento"].apply(dias_hasta)
                prod_venc["Estado_Venc"] = prod_venc["dias_hasta_venc"].apply(
                    lambda d: "🔴 Vencido" if d < 0 else
                              ("🟠 Crítico (<30d)" if d < 30 else
                               ("🟡 Alerta (30-90d)" if d < 90 else "🟢 OK"))
                )
                dias_fil = st.slider("Mostrar vencimientos en próximos N días", 0, 365, 90, key="dias_venc")
                df_v_fil = prod_venc[prod_venc["dias_hasta_venc"] <= dias_fil].sort_values("dias_hasta_venc")

                v1, v2, v3, v4 = st.columns(4)
                with v1: st.metric("🔴 Vencidos",     len(df_v_fil[df_v_fil["dias_hasta_venc"] < 0]))
                with v2: st.metric("🟠 Crítico <30d", len(df_v_fil[(df_v_fil["dias_hasta_venc"]>=0)  & (df_v_fil["dias_hasta_venc"]<30)]))
                with v3: st.metric("🟡 30-90d",       len(df_v_fil[(df_v_fil["dias_hasta_venc"]>=30) & (df_v_fil["dias_hasta_venc"]<90)]))
                with v4: st.metric("Total en ventana", len(df_v_fil))

                st.dataframe(
                    df_v_fil[["nombre","fecha_vencimiento","dias_hasta_venc","Estado_Venc","proveedor"]].rename(columns={
                        "nombre":"Producto","fecha_vencimiento":"Vence","dias_hasta_venc":"Días",
                        "Estado_Venc":"Estado","proveedor":"Proveedor"
                    }),
                    use_container_width=True, hide_index=True
                )

    # ── Reporte Mensual ───────────────────────────────────────────────────────
    with r_tab4:
        st.write("### 📄 Reporte Mensual Consolidado")
        rm1, rm2 = st.columns(2)
        with rm1:
            reporte_excel = generar_reporte_excel()
            st.download_button("📥 Descargar Reporte Excel (.xlsx)",
                               data=reporte_excel,
                               file_name=f"reporte_{datetime.now().strftime('%Y%m')}.xlsx")
        with rm2:
            if PDF_AVAILABLE:
                pdf_bytes = generar_reporte_pdf()
                if pdf_bytes:
                    st.download_button("📥 Descargar Reporte PDF",
                                       data=pdf_bytes,
                                       file_name=f"reporte_{datetime.now().strftime('%Y%m')}.pdf",
                                       mime="application/pdf")
            else:
                st.warning("PDF no disponible. Instalar: `pip install reportlab`")

        # Email
        st.markdown("---")
        st.write("### 📧 Enviar Alerta por Email")
        email_dest_show = obtener_metadata("email_dest") or "(no configurado)"
        st.caption(f"Destinatario configurado: **{email_dest_show}**")
        stk_bajo = obtener_stock_full()
        pend_30  = 0
        if not stk_bajo.empty:
            U_em  = st.session_state.umbral_alerta
            stk_bajo = stk_bajo[stk_bajo["Stock Actual"] < U_em]
            ent_em = obtener_entregas()
            if not ent_em.empty:
                ent_em["dp"] = ent_em["dia_recibido"].apply(dias_desde)
                pend_30 = len(ent_em[(ent_em["pendiente"] > 0) & (ent_em["dp"] > 30)])
        if st.button("📧 Enviar Email de Alerta"):
            ok_em, msg_em = enviar_email_alerta(stk_bajo, pend_30)
            st.success(msg_em) if ok_em else st.error(msg_em)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 9 — CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════
with tab9:
    st.subheader("⚙️ Configuración")
    cfg1, cfg2 = st.tabs(["📥 Importación / Exportación", "🔧 Parámetros & Sistema"])

    # ── Importación / Exportación ─────────────────────────────────────────────
    with cfg1:
        # Importación completa
        with st.expander("📥 Importar Stock desde MacroGest (reemplaza todo)", expanded=True):
            st.info("CSV/Excel con columnas: `codigo`, `descripcion_1`, `unidad_medida`, `deposito`, `lote`, `stock_actual`")
            arch_s = st.file_uploader("Archivo de stock", type=["csv","xlsx","xls"], key="up_stock")
            if arch_s:
                # ── Preview de columnas ───────────────────────────────────────
                try:
                    _df_prev = pd.read_csv(arch_s) if arch_s.name.endswith(".csv") else pd.read_excel(arch_s)
                    arch_s.seek(0)
                    st.caption(f"📋 Columnas detectadas: `{'`, `'.join(str(c) for c in _df_prev.columns)}`  |  {len(_df_prev)} filas")
                except Exception:
                    pass
            if arch_s and st.button("🚀 IMPORTAR STOCK COMPLETO", type="primary", key="btn_imp_stock"):
                import traceback as _tb
                _prog = st.progress(0, "Leyendo archivo...")
                try:
                    arch_s.seek(0)
                    df_s = pd.read_csv(arch_s) if arch_s.name.endswith(".csv") else pd.read_excel(arch_s)
                    _prog.progress(15, f"Archivo leído: {len(df_s)} filas")
                    # Normalizar columnas
                    df_s.columns = [str(c).strip().lower().replace(" ","_").replace(".","") for c in df_s.columns]
                    _COL_MAP = {
                        "descripcion":      "descripcion_1",
                        "descripcion1":     "descripcion_1",
                        "desc":             "descripcion_1",
                        "nombre":           "descripcion_1",
                        "articulo":         "descripcion_1",
                        "unidad":           "unidad_medida",
                        "um":               "unidad_medida",
                        "u_medida":         "unidad_medida",
                        "stock":            "stock_actual",
                        "saldo":            "stock_actual",
                        "existencia":       "stock_actual",
                        "deposito_nombre":  "deposito",
                        "dep":              "deposito",
                        "almacen":          "deposito",
                    }
                    df_s.rename(columns={k: v for k, v in _COL_MAP.items() if k in df_s.columns}, inplace=True)
                    if "descripcion_1" not in df_s.columns:
                        raise ValueError(f"Columna de producto no encontrada. Disponibles: {list(df_s.columns)}")
                    # Filtrar filas válidas
                    df_s["_nom"] = df_s["descripcion_1"].apply(safe_str)
                    df_validas = df_s[df_s["_nom"] != ""].copy()
                    _prog.progress(25, f"{len(df_validas)} filas válidas de {len(df_s)}")
                    if df_validas.empty:
                        raise ValueError("No hay filas con producto válido en el archivo.")
                    _prog.progress(30, "Limpiando datos anteriores...")
                    borrar_solo_importacion()
                    conn = conectar_db()
                    _total = len(df_validas)
                    _ts = datetime.now().strftime("%d/%m/%Y %H:%M")
                    _usu = usuario_actual()

                    # ── Paso 1: preparar filas ─────────────────────────────────
                    _prog.progress(35, f"Preparando {_total} filas...")
                    filas_raw = []
                    for _, row in df_validas.iterrows():
                        filas_raw.append({
                            "nom": row["_nom"],
                            "cod": safe_str(row.get("codigo","")),
                            "uni": safe_str(row.get("unidad_medida","U")) or "U",
                            "dep": safe_str(row.get("deposito","0")) or "0",
                            "lot": safe_str(row.get("lote","S/L")) or "S/L",
                            "stk": safe_float(row.get("stock_actual", 0.0)),
                        })

                    # ── Paso 2: insertar productos únicos en batch ─────────────
                    _prog.progress(45, "Insertando productos (batch)...")
                    productos_uniq = {r["nom"]: r for r in filas_raw}
                    prod_batch = [(p["nom"], p["uni"], p["cod"]) for p in productos_uniq.values()]
                    conn.cursor().executemany(
                        "INSERT OR IGNORE INTO productos (nombre,unidad,codigo) VALUES (?,?,?)",
                        prod_batch
                    )
                    conn.commit()
                    pa = len(prod_batch)

                    # ── Paso 3: cargar mapa nombre → id_producto ───────────────
                    _prog.progress(60, "Mapeando IDs de productos...")
                    noms_sql = ",".join(["?"] * len(productos_uniq))
                    id_map_rows = conn.execute(
                        f"SELECT id_producto, nombre FROM productos WHERE nombre IN ({noms_sql})",
                        list(productos_uniq.keys())
                    ).fetchall()
                    id_map = {r[1]: r[0] for r in id_map_rows}

                    # ── Paso 4: insertar movimientos en batch ──────────────────
                    _prog.progress(70, "Insertando movimientos (batch)...")
                    mov_batch = []
                    for r in filas_raw:
                        pid = id_map.get(r["nom"])
                        if pid is None:
                            continue
                        mov_batch.append((
                            _ts, "Entrada", pid,
                            r["stk"], r["lot"], "Saldo Inicial",
                            r["dep"], "excel", _usu
                        ))
                    conn.cursor().executemany(
                        """INSERT INTO movimientos
                           (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,
                            referencia,deposito,origen,usuario)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        mov_batch
                    )
                    conn.commit()
                    mo = len(mov_batch)
                    conn.close()
                    _prog.progress(100, "¡Listo!")
                    guardar_metadata("ultima_importacion", datetime.now().strftime("%d/%m/%Y %H:%M"))
                    limpiar_cache()
                    st.session_state["stock_imp_ok"] = (
                        f"✅ Stock importado: {pa} productos nuevos, {mo} líneas "
                        f"(de {_total} filas válidas)."
                    )
                    st.rerun()
                except Exception as ex:
                    _prog.empty()
                    st.error(f"❌ Error durante la importación: {ex}")
                    st.code(_tb.format_exc(), language="python")
            # Mensaje persistente post-rerun
            if st.session_state.get("stock_imp_ok"):
                st.success(st.session_state.pop("stock_imp_ok"))
            # ── Diagnóstico rápido DB ──────────────────────────────────────────
            with st.expander("🔍 Diagnóstico base de datos", expanded=False):
                if st.button("🔄 Verificar estado DB", key="btn_diag"):
                    try:
                        conn_d = conectar_db()
                        n_prod = conn_d.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
                        n_mov  = conn_d.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0]
                        n_exc  = conn_d.execute("SELECT COUNT(*) FROM movimientos WHERE origen='excel'").fetchone()[0]
                        n_ent  = conn_d.execute("SELECT COUNT(*) FROM entregas").fetchone()[0]
                        conn_d.close()
                        st.info(
                            f"**Productos:** {n_prod}  |  "
                            f"**Movimientos totales:** {n_mov}  |  "
                            f"**Movimientos excel:** {n_exc}  |  "
                            f"**Entregas:** {n_ent}"
                        )
                    except Exception as ex:
                        st.error(f"Error al consultar DB: {ex}")

        # Importación incremental
        with st.expander("🔄 Importación Incremental (solo diferencias)"):
            st.info(
                "Calcula la diferencia entre el archivo nuevo y el stock actual, "
                "e inserta **solo los ajustes**. Preserva movimientos manuales."
            )
            arch_inc = st.file_uploader("Archivo MacroGest nuevo", type=["csv","xlsx","xls"], key="up_incr")
            if arch_inc and st.button("🔄 IMPORTAR INCREMENTAL", type="primary"):
                try:
                    df_inc = pd.read_csv(arch_inc) if arch_inc.name.endswith(".csv") else pd.read_excel(arch_inc)
                    df_inc.columns = [str(c).strip().lower().replace(" ","_").replace(".","") for c in df_inc.columns]
                    _COL_MAP_INC = {
                        "descripcion":"descripcion_1","descripcion1":"descripcion_1",
                        "desc":"descripcion_1","nombre":"descripcion_1","articulo":"descripcion_1",
                        "unidad":"unidad_medida","um":"unidad_medida",
                        "stock":"stock_actual","saldo":"stock_actual","existencia":"stock_actual","cantidad":"stock_actual",
                        "dep":"deposito","almacen":"deposito",
                    }
                    df_inc.rename(columns={k: v for k, v in _COL_MAP_INC.items() if k in df_inc.columns}, inplace=True)
                    stk_actual = obtener_stock_full()
                    stk_actual_dict = {} if stk_actual.empty else {
                        (r["Producto"],r["Deposito"]): r["Stock Actual"]
                        for _, r in stk_actual.iterrows()
                    }
                    conn = conectar_db()
                    # Calcular ajustes necesarios
                    ajustes_raw = []
                    for _, row in df_inc.iterrows():
                        nom = safe_str(row.get("descripcion_1",""))
                        if not nom: continue
                        dep = safe_str(row.get("deposito","0"))
                        stk_nuevo = safe_float(row.get("stock_actual",0.0))
                        stk_prev  = stk_actual_dict.get((nom, dep), 0.0)
                        dif_inc   = stk_nuevo - stk_prev
                        if abs(dif_inc) < 0.001: continue
                        ajustes_raw.append({
                            "nom": nom, "dep": dep,
                            "cod": safe_str(row.get("codigo","")),
                            "uni": safe_str(row.get("unidad_medida","U")) or "U",
                            "lot": safe_str(row.get("lote","S/L")) or "S/L",
                            "dif": dif_inc,
                        })
                    # Batch insert productos nuevos
                    if ajustes_raw:
                        prod_inc = list({r["nom"]: (r["nom"],r["uni"],r["cod"]) for r in ajustes_raw}.values())
                        conn.cursor().executemany(
                            "INSERT OR IGNORE INTO productos (nombre,unidad,codigo) VALUES (?,?,?)",
                            prod_inc)
                        conn.commit()
                        # Obtener IDs de una vez
                        noms_inc = [r["nom"] for r in ajustes_raw]
                        ph_inc = ",".join(["?"] * len(set(noms_inc)))
                        id_rows_inc = conn.execute(
                            f"SELECT id_producto,nombre FROM productos WHERE nombre IN ({ph_inc})",
                            list(set(noms_inc))).fetchall()
                        id_map_inc = {r[1]: r[0] for r in id_rows_inc}
                        _ts_inc = datetime.now().strftime("%d/%m/%Y %H:%M")
                        _usu_inc = usuario_actual()
                        mov_inc_batch = [
                            (_ts_inc, "Entrada" if r["dif"] > 0 else "Salida",
                             id_map_inc[r["nom"]], abs(r["dif"]),
                             r["lot"], "Ajuste Incremental MacroGest",
                             r["dep"], "excel", _usu_inc)
                            for r in ajustes_raw if r["nom"] in id_map_inc
                        ]
                        conn.cursor().executemany("""INSERT INTO movimientos
                            (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,
                             referencia,deposito,origen,usuario)
                            VALUES (?,?,?,?,?,?,?,?,?)""", mov_inc_batch)
                    ajustes = len(ajustes_raw)
                    conn.commit(); conn.close()
                    guardar_metadata("ultima_importacion", datetime.now().strftime("%d/%m/%Y %H:%M"))
                    limpiar_cache()
                    st.success(f"✅ {ajustes} ajustes incrementales aplicados.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

        # Exportación MacroGest
        with st.expander("📤 Exportar para reimportar en MacroGest"):
            stk_exp = obtener_stock_full()
            if not stk_exp.empty:
                exp_mg = exportar_macrogest_format(stk_exp)
                st.download_button("📥 Exportar formato MacroGest (.xlsx)",
                                   data=exp_mg, file_name="exportacion_macrogest.xlsx")
            else:
                st.info("Sin datos de stock.")

    # ── Parámetros & Sistema ──────────────────────────────────────────────────
    with cfg2:
        st.write("### 🚨 Parámetros Operativos")
        new_umbral = st.number_input("Umbral de Stock Bajo", min_value=1,
                                     value=int(st.session_state.umbral_alerta))
        new_wa     = st.text_input("WhatsApp (5493XXXXXXXXX)", value=st.session_state.wa_numero)
        cod_sup_cfg = st.text_input("Código de supervisor (para transferencias)",
            value=obtener_metadata("codigo_supervisor") or "1234",
            type="password", key="cod_sup_cfg",
            help="Código que deben ingresar los operadores para autorizar transferencias entre depósitos")
        if st.button("💾 Guardar Parámetros"):
            st.session_state.umbral_alerta = new_umbral
            st.session_state.wa_numero     = new_wa
            guardar_metadata("umbral_alerta", str(new_umbral))
            guardar_metadata("wa_numero",     new_wa)
            guardar_metadata("codigo_supervisor", cod_sup_cfg)
            st.success("Guardado.")

        st.markdown("---")
        st.write("### 📧 Configuración de Email")
        with st.expander("Configurar SMTP"):
            ep1, ep2 = st.columns(2)
            with ep1:
                smtp_s = st.text_input("SMTP Server",
                    value=obtener_metadata("smtp_server") or "smtp.gmail.com", key="smtp_s")
                smtp_u = st.text_input("Usuario SMTP",
                    value=obtener_metadata("smtp_user") or "", key="smtp_u")
                smtp_dest = st.text_input("Email destinatario",
                    value=obtener_metadata("email_dest") or "", key="smtp_dest")
            with ep2:
                smtp_p_val = int(obtener_metadata("smtp_port") or 587)
                smtp_port  = st.number_input("Puerto", min_value=1, value=smtp_p_val, key="smtp_port")
                smtp_pw    = st.text_input("Contraseña SMTP", type="password", key="smtp_pw")
            if st.button("💾 Guardar Config Email"):
                guardar_metadata("smtp_server", smtp_s)
                guardar_metadata("smtp_port",   str(smtp_port))
                guardar_metadata("smtp_user",   smtp_u)
                guardar_metadata("email_dest",  smtp_dest)
                if smtp_pw:
                    guardar_metadata("smtp_pass", smtp_pw)
                st.success("Config email guardada.")

        st.markdown("---")
        if es_admin():
            st.write("### 👥 Gestión de Usuarios")
            conn = conectar_db()
            try:
                df_u = _rsql("SELECT username, nombre, rol, sede FROM usuarios", conn)
            except: df_u = pd.DataFrame()
            conn.close()
            st.dataframe(df_u, use_container_width=True, hide_index=True)

            with st.expander("➕ Agregar / Actualizar Usuario"):
                nu1, nu2 = st.columns(2)
                with nu1:
                    n_usr  = st.text_input("Username", key="n_usr")
                    n_pwd  = st.text_input("Contraseña", type="password", key="n_pwd")
                    n_nom  = st.text_input("Nombre completo", key="n_nom")
                with nu2:
                    n_rol  = st.selectbox("Rol", ["operador","supervisor","admin"], key="n_rol")
                    n_sede = st.selectbox("Sede", ["San Jorge","Las Varillas","San Francisco"], key="n_sede")
                if st.button("💾 Guardar Usuario", type="primary"):
                    if n_usr and n_pwd:
                        conn = conectar_db()
                        conn.execute("""INSERT OR REPLACE INTO usuarios
                            (username,password_hash,nombre,rol,sede) VALUES (?,?,?,?,?)""",
                            (n_usr, hash_pwd(n_pwd), n_nom, n_rol, n_sede))
                        conn.commit(); conn.close()
                        st.success(f"Usuario '{n_usr}' guardado.")
                        st.rerun()
                    else:
                        st.error("Username y contraseña son obligatorios.")

            auth_on = st.toggle("🔐 Activar autenticación",
                                value=(obtener_metadata("auth_enabled")=="1"),
                                key="auth_toggle")
            if st.button("💾 Guardar config auth"):
                guardar_metadata("auth_enabled", "1" if auth_on else "0")
                st.success("Config auth guardada. Recargá la página.")
            if auth_on:
                st.warning("⚠️ Recordá cambiar la contraseña del usuario **admin** antes de activar.")

        st.markdown("---")
        st.write("### ⚠️ Mantenimiento de Datos")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("🗑️ Borrar solo datos importados"):
                borrar_solo_importacion()
                st.success("Datos de importación eliminados.")
                st.rerun()
        with col_b2:
            conf_borrado = st.text_input("Escribí **CONFIRMAR** para habilitar borrado total",
                                         placeholder="CONFIRMAR", key="conf_borrado")
            if st.button("🔥 BORRAR BASE COMPLETA", type="primary",
                         disabled=(conf_borrado.strip() != "CONFIRMAR")):
                borrar_datos_totales()
                st.success("Base vaciada.")
                st.rerun()

    st.markdown("---")
    st.caption(f"La Clementina S.A. — v2.0 PRO — "
               f"{'PDF ✅' if PDF_AVAILABLE else 'PDF ❌ (pip install reportlab)'}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 10 — PLAN COMERCIAL 2026-2027
# ═══════════════════════════════════════════════════════════════════════════════
with tab10:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a5276,#2e86c1);
                color:white;padding:24px 28px;border-radius:12px;margin-bottom:20px">
        <h2 style="margin:0;font-size:1.5rem">📊 Plan Comercial — Campaña 2026-2027</h2>
        <p style="margin:6px 0 0;opacity:.85">La Clementina S.A. · Dirección Comercial · San Jorge, Santa Fe</p>
    </div>
    """, unsafe_allow_html=True)

    pc1, pc2, pc3, pc4, pc5 = st.tabs([
        "📋 El Plan",
        "🎯 Metas & Productos",
        "📈 KPI Dashboard",
        "👥 Cartera de Clientes",
        "📝 Reportes Semanales",
    ])

    # ── SUBTAB 1: DOCUMENTO DEL PLAN ─────────────────────────────────────────
    with pc1:
        st.markdown("""
## 1. PROPÓSITO DEL PLAN

El presente Plan Comercial establece los lineamientos estratégicos y operativos que orientarán la gestión de ventas durante la **Campaña 2026-2027**. Su propósito es proveer a cada integrante del equipo comercial un marco claro de objetivos, métricas de seguimiento y metodología de trabajo.

Este documento es de **cumplimiento obligatorio**. Cada vendedor deberá presentar su propio plan de acción antes del **15 de julio de 2026**, el cual será evaluado semanalmente y reportado a Dirección de forma mensual.

---

## 2. OBJETIVOS GENERALES

### 2.1 Crecimiento de Facturación
| Canal | Objetivo |
|---|---|
| La Clementina + Bayer | **+30 %** sobre la campaña anterior (en línea con ajuste de precios) |
| Volumen físico estratégico | **+20 %** en Maíz, Round Up y Semillas Autógamas |

> ⚠️ Toda desviación superior al **10 % negativo** sobre la meta mensual debe ser informada y fundamentada dentro de las **48 horas** al responsable comercial.

### 2.2 Distribución Objetivo de Facturación (La Clementina)
| Rubro | Participación |
|---|---|
| Semillas autógamas | **30 %** |
| Agroquímicos | **30 %** |
| Fertilizantes | **30 %** |
| Otros / Servicios | **10 %** |

---

## 3. SEGMENTACIÓN DE CARTERA

### 3.1 Clientes Premium (Regla 80/20)
- El segmento Premium representa el **80 % de la facturación** en **no menos del 20 %** de los clientes activos.
- Con una cartera de 50 clientes: mínimo 10 cuentas Premium.
- Una concentración inferior es un **riesgo estratégico** → acción de captación inmediata.

### 3.2 Fidelización y Reactivación
- **Clientes activos**: seguimiento, propuestas de valor, presencia en campo.
- **Clientes inactivos**: propuesta de retorno focalizada en necesidades actuales.

Cada vendedor presenta mensualmente el **estado de su cartera** con clientes en riesgo y acciones en curso.

---

## 4. FIELD VIEW — CLIENTES OBJETIVOS
Cada vendedor debe:
- Identificar **mínimo 5 clientes** para seguimiento productivo vía Field View.
- Presentar el listado + cronograma antes del **31 de julio de 2026**.
- Usar los datos de la plataforma como argumento comercial en visitas.

---

## 5. KPIs Y METODOLOGÍA DE SEGUIMIENTO

| Indicador | Objetivo | Frecuencia |
|---|---|---|
| Facturación total (LC + Bayer) | Meta mensual / acumulado | Semanal y mensual |
| Facturación por rubro | Mix 30/30/30 | Mensual |
| Clientes Premium activos | ≥ 20 % del total | Mensual |
| Nuevos clientes | Meta por zona | Mensual |
| Volumen productos foco | Meta por producto / semestre | Mensual |
| Clientes Field View activos | **Mínimo 5** por vendedor | Semestral |
| Clientes reactivados | Sobre base inactivos previos | Mensual |

### Ciclo de Reporte
- **Reunión semanal**: avances, obstáculos y oportunidades.
- **Reporte mensual escrito** a Dirección: KPIs, desvíos y plan correctivo.
- **Revisión semestral**: evaluación integral y ajuste de metas.

---

## 6. COMPROMISOS DEL EQUIPO
- ✅ Plan de acción individual antes del **15 de julio de 2026**.
- ✅ Registro semanal en **MacroGest**: visitas, oportunidades, cartera.
- ✅ Asistencia a reuniones con información actualizada.
- ✅ Comunicación proactiva de situaciones de riesgo.

---
> *"El éxito comercial no es consecuencia del azar. Es el resultado de planificar, ejecutar y mejorar de forma consistente."*
        """)

    # ── SUBTAB 2: METAS & PRODUCTOS FOCO ─────────────────────────────────────
    with pc2:
        st.write("### 🎯 Productos Foco — Metas Generales de Campaña")

        df_pf = obtener_productos_foco()
        if not df_pf.empty:
            pf_edit = st.data_editor(
                df_pf[["producto","unidad","meta_total","prioridad"]].rename(columns={
                    "producto":"Producto","unidad":"Unidad",
                    "meta_total":"Meta Total Campaña","prioridad":"Prioridad"
                }),
                column_config={
                    "Meta Total Campaña": st.column_config.NumberColumn(min_value=0, format="%.0f"),
                    "Prioridad":          st.column_config.NumberColumn(min_value=1, max_value=10),
                },
                hide_index=True, use_container_width=True, key="edit_pf"
            )
            if st.button("💾 Guardar Productos Foco", key="save_pf"):
                conn = conectar_db()
                for i, r in pf_edit.iterrows():
                    conn.execute("""UPDATE productos_foco
                        SET meta_total=?, prioridad=?
                        WHERE campana=? AND producto=?""",
                        (float(r["Meta Total Campaña"]), int(r["Prioridad"]),
                         CAMPANA_ACTUAL, r["Producto"]))
                conn.commit(); conn.close()
                limpiar_cache()
                st.success("✅ Metas actualizadas.")
                st.rerun()

        st.markdown("---")
        st.write("### 👤 Metas Individuales por Vendedor")

        ent_vend = obtener_entregas()
        vendedores_lista = sorted(ent_vend["vendedor"].dropna().replace("","S/V").unique().tolist()) \
                           if not ent_vend.empty else []
        if not vendedores_lista:
            vendedores_lista = ["Vendedor 1","Vendedor 2","Vendedor 3"]

        vend_sel_m = st.selectbox("Vendedor", vendedores_lista, key="vend_sel_metas")
        df_metas   = obtener_metas_campana()
        df_metas_v = df_metas[df_metas["vendedor"]==vend_sel_m] if not df_metas.empty else pd.DataFrame()

        # Armar tabla editable combinando productos_foco con metas existentes
        df_pf2 = obtener_productos_foco()
        if not df_pf2.empty:
            df_base = df_pf2[["producto","unidad"]].copy()
            df_base.columns = ["Producto","Unidad"]
            if not df_metas_v.empty:
                df_base = df_base.merge(
                    df_metas_v[["producto","meta_volumen","meta_facturacion","moneda_meta"]]
                    .rename(columns={"producto":"Producto","meta_volumen":"Meta Volumen",
                                     "meta_facturacion":"Meta Facturación","moneda_meta":"Moneda"}),
                    on="Producto", how="left"
                )
            if "Meta Volumen" not in df_base.columns:
                df_base["Meta Volumen"]      = 0.0
            if "Meta Facturación" not in df_base.columns:
                df_base["Meta Facturación"]  = 0.0
            if "Moneda" not in df_base.columns:
                df_base["Moneda"]            = "ARS"
            df_base = df_base.fillna(0)

            edited_m = st.data_editor(
                df_base,
                column_config={
                    "Meta Volumen":      st.column_config.NumberColumn(min_value=0, format="%.1f"),
                    "Meta Facturación":  st.column_config.NumberColumn(min_value=0, format="%.0f"),
                    "Moneda":            st.column_config.SelectboxColumn(options=["ARS","USD"]),
                },
                hide_index=True, use_container_width=True, key="edit_metas_v"
            )
            if st.button(f"💾 Guardar metas de {vend_sel_m}", type="primary", key="save_metas_v"):
                conn = conectar_db()
                for _, r in edited_m.iterrows():
                    conn.execute("""INSERT OR REPLACE INTO metas_campana
                        (campana,vendedor,producto,unidad,meta_volumen,meta_facturacion,moneda_meta)
                        VALUES (?,?,?,?,?,?,?)""",
                        (CAMPANA_ACTUAL, vend_sel_m, r["Producto"], r["Unidad"],
                         float(r["Meta Volumen"]), float(r["Meta Facturación"]), r["Moneda"]))
                conn.commit(); conn.close()
                limpiar_cache()
                st.success(f"✅ Metas de {vend_sel_m} guardadas.")
                st.rerun()

    # ── SUBTAB 3: KPI DASHBOARD ───────────────────────────────────────────────
    with pc3:
        st.write("### 📈 KPI Dashboard — Campaña 2026-2027")

        # Estado de datos disponibles
        n_ventas_est = len(obtener_ventas_detalle())
        n_mg_est = len(obtener_entregas("MACROGEST"))
        est1, est2 = st.columns(2)
        with est1:
            st.metric("📋 Líneas de venta cargadas", n_ventas_est,
                      delta="Con datos ✓" if n_ventas_est > 0 else "Sin datos",
                      delta_color="normal" if n_ventas_est > 0 else "inverse")
        with est2:
            st.metric("🔄 Pedidos sin entregar", n_mg_est,
                      delta="Con datos ✓" if n_mg_est > 0 else "Sin datos",
                      delta_color="normal" if n_mg_est > 0 else "inverse")
        if n_ventas_est == 0:
            st.info("💡 Para ver el dashboard completo: importá ventas desde "
                    "**Plan Comercial → Cartera de Clientes → Importar desde MacroGest** "
                    "y pedidos desde el tab **🔄 Sin Entregar MG**.")
        st.markdown("---")
        ventas_r = ventas_reales_por_vendedor()
        df_metas_all = obtener_metas_campana()
        df_cart  = obtener_cartera()
        df_reps  = obtener_reportes()

        # KPIs globales
        total_entregado = ventas_r["Entregado_Total"].sum() if not ventas_r.empty else 0
        total_clientes  = df_cart[df_cart["tipo"]=="premium"]["cliente"].nunique() if not df_cart.empty else 0
        total_premium_pct = 0
        total_activos   = df_cart["cliente"].nunique() if not df_cart.empty else 0
        if total_activos > 0:
            total_premium_pct = round(df_cart[df_cart["tipo"]=="premium"]["cliente"].nunique() / total_activos * 100, 1)
        field_view_n  = int(df_cart["field_view"].sum()) if not df_cart.empty else 0
        nuevos_n      = int(df_cart[df_cart["tipo"]=="prospecto"]["cliente"].nunique()) if not df_cart.empty else 0

        kp1, kp2, kp3, kp4, kp5 = st.columns(5)
        with kp1: st.metric("📦 Entregado Total",    f"{total_entregado:,.0f}")
        with kp2: st.metric("⭐ Clientes Premium",   total_clientes)
        with kp3: st.metric("% Premium / Total",     f"{total_premium_pct:.1f}%",
                             delta="OK" if total_premium_pct >= 20 else "< 20% ⚠️",
                             delta_color="normal" if total_premium_pct >= 20 else "inverse")
        with kp4: st.metric("🌐 Field View activos", field_view_n,
                             delta="OK" if field_view_n >= 5 else f"< 5 objetivo",
                             delta_color="normal" if field_view_n >= 5 else "inverse")
        with kp5: st.metric("🆕 Prospectos",         nuevos_n)

        st.markdown("---")

        # Gauges por vendedor (facturación real vs meta)
        if not ventas_r.empty and not df_metas_all.empty:
            st.write("#### Facturación Real vs Meta por Vendedor")
            metas_vend = (df_metas_all.groupby("vendedor")["meta_facturacion"].sum().reset_index()
                          .rename(columns={"meta_facturacion":"Meta"}))
            merged_g = ventas_r.merge(metas_vend, left_on="vendedor", right_on="vendedor", how="outer").fillna(0)
            cols_g = st.columns(min(len(merged_g), 4))
            for i, (_, r) in enumerate(merged_g.iterrows()):
                if i >= 4: break
                with cols_g[i % 4]:
                    fig_g = gauge_kpi(r["Entregado_Total"], r["Meta"],
                                      r["vendedor"][:20], "u.")
                    st.plotly_chart(fig_g, use_container_width=True)

        st.markdown("---")
        st.write("#### Performance por Vendedor")
        if not ventas_r.empty:
            st.dataframe(ventas_r.rename(columns={
                "vendedor":"Vendedor",
                "Importe_Total":"Importe Total $",
                "Entregado_Total":"Cant. Entregada",
                "Cant_Total":"Cant. Total",
                "Clientes_Activos":"Clientes",
                "Productos_Distintos":"Productos",
                "% Entregado":"% Entregado"
            }), use_container_width=True, hide_index=True)

            fig_bar = px.bar(
                ventas_r.sort_values("Importe_Total", ascending=False),
                x="vendedor", y="Importe_Total",
                title="Importe Total por Vendedor",
                color_discrete_sequence=["#007bff"],
                labels={"vendedor":"Vendedor","Importe_Total":"Importe $"}
            )
            fig_bar.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_bar, use_container_width=True)

        # Detalle ventas MacroGest por vendedor
        df_mg_all = obtener_ventas_detalle()
        if not df_mg_all.empty:
            st.markdown("---")
            st.write("#### 🔍 Análisis de Ventas MacroGest")
            vend_kpi = st.selectbox("Vendedor",
                                    ["Todos"] + sorted(df_mg_all["vendedor"].unique().tolist()),
                                    key="vend_kpi_mg")
            df_mg_f = df_mg_all if vend_kpi=="Todos" else df_mg_all[df_mg_all["vendedor"]==vend_kpi]

            mk1, mk2, mk3, mk4 = st.columns(4)
            with mk1: st.metric("Importe Total",    f"${df_mg_f['importe_total'].sum():,.0f}")
            with mk2: st.metric("Clientes",          df_mg_f["cliente"].nunique())
            with mk3: st.metric("Productos",         df_mg_f["descripcion"].nunique())
            with mk4: st.metric("Líneas de pedido",  len(df_mg_f))

            # Top clientes
            mc1, mc2 = st.columns(2)
            with mc1:
                top_cli = (df_mg_f.groupby("cliente")["importe_total"].sum()
                           .reset_index().sort_values("importe_total", ascending=False).head(10))
                fig_cli = px.bar(top_cli.sort_values("importe_total"), x="importe_total", y="cliente",
                                 orientation="h", title="Top 10 Clientes por Importe",
                                 color_discrete_sequence=["#ffd700"])
                fig_cli.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_cli, use_container_width=True)
            with mc2:
                top_prod2 = (df_mg_f.groupby("descripcion")["importe_total"].sum()
                             .reset_index().sort_values("importe_total", ascending=False).head(10))
                fig_pr2 = px.bar(top_prod2.sort_values("importe_total"), x="importe_total", y="descripcion",
                                 orientation="h", title="Top 10 Productos por Importe",
                                 color_discrete_sequence=["#28a745"])
                fig_pr2.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_pr2, use_container_width=True)

            # Tabla detalle filtrable
            with st.expander("📋 Ver detalle de ventas"):
                f_cli_k = st.text_input("Buscar cliente", key="bus_cli_k")
                f_prod_k = st.text_input("Buscar producto", key="bus_prod_k")
                df_det = df_mg_f.copy()
                if f_cli_k:
                    df_det = df_det[df_det["cliente"].str.contains(f_cli_k, case=False, na=False)]
                if f_prod_k:
                    df_det = df_det[df_det["descripcion"].str.contains(f_prod_k, case=False, na=False)]
                st.dataframe(
                    df_det[["vendedor","cliente","descripcion","cantidad","precio","importe_total",
                             "entregada","fecha","localidad","observaciones"]].rename(columns={
                        "vendedor":"Vendedor","cliente":"Cliente","descripcion":"Producto",
                        "cantidad":"Cant.","precio":"Precio","importe_total":"Importe $",
                        "entregada":"Entregado","fecha":"Fecha","localidad":"Localidad",
                        "observaciones":"Obs."
                    }),
                    use_container_width=True, hide_index=True
                )
                st.download_button("📥 Exportar ventas",
                                   data=to_excel_bytes(df_det, "Ventas"),
                                   file_name=f"ventas_{vend_kpi}.xlsx")

        st.markdown("---")
        st.write("#### Distribución de Facturación por Rubro (objetivo: 30/30/30/10)")
        st.info("Cargá los montos reales por rubro para comparar contra la distribución objetivo.")
        rubros = list(DISTRIBUCION_OBJETIVO.keys())
        vals_reales = []
        col_r = st.columns(4)
        for i, rubro in enumerate(rubros):
            with col_r[i]:
                v = st.number_input(rubro, min_value=0.0, step=1000.0, key=f"rubro_{i}")
                vals_reales.append(v)
        total_rubros = sum(vals_reales)
        if total_rubros > 0:
            pcts_reales = [v/total_rubros*100 for v in vals_reales]
            df_dist = pd.DataFrame({
                "Rubro": rubros,
                "% Real": [round(p,1) for p in pcts_reales],
                "% Objetivo": list(DISTRIBUCION_OBJETIVO.values())
            })
            fig_dist = px.bar(df_dist, x="Rubro", y=["% Real","% Objetivo"],
                              barmode="group", title="Mix Real vs Objetivo",
                              color_discrete_sequence=["#007bff","#dee2e6"])
            fig_dist.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_dist, use_container_width=True)

        # Evolución semanal de reportes
        if not df_reps.empty:
            st.markdown("---")
            st.write("#### Evolución de Facturación Semanal Reportada")
            df_evo = (df_reps.groupby("fecha_semana")["facturacion"].sum()
                      .reset_index().sort_values("fecha_semana"))
            df_evo["Acumulado"] = df_evo["facturacion"].cumsum()
            fig_evo = px.area(df_evo, x="fecha_semana", y="Acumulado",
                              title="Facturación Acumulada (según reportes)",
                              color_discrete_sequence=["#007bff"])
            fig_evo.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_evo, use_container_width=True)

    # ── SUBTAB 4: CARTERA DE CLIENTES ─────────────────────────────────────────
    with pc4:
        st.write("### 👥 Gestión de Cartera de Clientes")

        ent_v2 = obtener_entregas()
        vendedores_c = sorted(ent_v2["vendedor"].dropna().replace("","S/V").unique().tolist()) \
                       if not ent_v2.empty else ["Vendedor 1"]
        vend_c = st.selectbox("Vendedor", ["Todos"] + vendedores_c, key="vend_cart")

        df_c = obtener_cartera(None if vend_c=="Todos" else vend_c)

        # KPIs cartera
        if not df_c.empty:
            n_prem  = len(df_c[df_c["tipo"]=="premium"])
            n_act   = len(df_c[df_c["tipo"]=="activo"])
            n_inact = len(df_c[df_c["tipo"]=="inactivo"])
            n_prosp = len(df_c[df_c["tipo"]=="prospecto"])
            n_fv    = int(df_c["field_view"].sum())
            n_tot   = len(df_c)
            pct_pr  = round(n_prem/n_tot*100,1) if n_tot>0 else 0

            kc1,kc2,kc3,kc4,kc5,kc6 = st.columns(6)
            with kc1: st.metric("⭐ Premium",     n_prem)
            with kc2: st.metric("✅ Activos",     n_act)
            with kc3: st.metric("😴 Inactivos",   n_inact)
            with kc4: st.metric("🆕 Prospectos",  n_prosp)
            with kc5: st.metric("🌐 Field View",  n_fv)
            with kc6: st.metric("% Premium",      f"{pct_pr}%",
                                 delta="OK ✅" if pct_pr>=20 else "< 20% ⚠️",
                                 delta_color="normal" if pct_pr>=20 else "inverse")

            # Gráfico torta tipos
            cc1, cc2 = st.columns(2)
            with cc1:
                tipo_g = df_c.groupby("tipo").size().reset_index(name="N")
                fig_tp = px.pie(tipo_g, names="tipo", values="N",
                                title="Distribución por Tipo",
                                color="tipo",
                                color_discrete_map={"premium":"#ffd700","activo":"#28a745",
                                                    "inactivo":"#6c757d","prospecto":"#007bff"},
                                hole=0.4)
                fig_tp.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_tp, use_container_width=True)
            with cc2:
                if not df_c[df_c["tipo"]=="premium"].empty:
                    df_prem_g = df_c[df_c["tipo"]=="premium"].sort_values("potencial_facturacion",ascending=False).head(10)
                    fig_pr = px.bar(df_prem_g, x="potencial_facturacion", y="cliente",
                                    orientation="h", title="Top Premium por Potencial",
                                    color_discrete_sequence=["#ffd700"])
                    fig_pr.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig_pr, use_container_width=True)

            st.markdown("---")
            st.dataframe(
                df_c[["vendedor","cliente","tipo","superficie_ha","potencial_facturacion","field_view","estado","ultima_compra","observaciones"]]
                .rename(columns={"vendedor":"Vendedor","cliente":"Cliente","tipo":"Tipo",
                                  "superficie_ha":"Ha","potencial_facturacion":"Potencial $",
                                  "field_view":"FV","estado":"Estado",
                                  "ultima_compra":"Últ. Compra","observaciones":"Obs."}),
                use_container_width=True, hide_index=True
            )

        st.markdown("---")
        st.write("#### ➕ Agregar / Actualizar Cliente")
        if vend_c == "Todos":
            vend_nuevo = st.selectbox("Vendedor", vendedores_c, key="vend_nc")
        else:
            vend_nuevo = vend_c

        nc1, nc2, nc3 = st.columns(3)
        with nc1:
            cli_nom  = st.text_input("Nombre del cliente", key="nc_nom")
            cli_tipo = st.selectbox("Tipo", ["activo","premium","inactivo","prospecto"], key="nc_tipo")
        with nc2:
            cli_ha   = st.number_input("Superficie (ha)", min_value=0.0, step=10.0, key="nc_ha")
            cli_pot  = st.number_input("Potencial facturación $", min_value=0.0, step=1000.0, key="nc_pot")
        with nc3:
            cli_fv   = st.toggle("Field View activo", value=False, key="nc_fv")
            cli_uc   = st.text_input("Última compra (dd/mm/aaaa)", key="nc_uc")
        cli_obs = st.text_input("Observaciones", key="nc_obs")

        if st.button("💾 Guardar Cliente", type="primary", key="save_nc"):
            if cli_nom:
                conn = conectar_db()
                conn.execute("""INSERT OR REPLACE INTO cartera_clientes
                    (vendedor,cliente,tipo,superficie_ha,potencial_facturacion,
                     field_view,ultima_compra,estado,observaciones,campana)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (vend_nuevo, cli_nom, cli_tipo, cli_ha, cli_pot,
                     1 if cli_fv else 0, cli_uc, "activo", cli_obs, CAMPANA_ACTUAL))
                conn.commit(); conn.close()
                limpiar_cache()
                st.success(f"✅ Cliente '{cli_nom}' guardado.")
                st.rerun()
            else:
                st.error("El nombre del cliente es obligatorio.")

        # ── Importar desde MacroGest (formato nativo) ──────────────────────
        st.markdown("---")
        with st.expander("🚀 Importar desde MacroGest (formato exportación ventas)", expanded=True):
            st.info(
                "Subí la exportación directa de MacroGest con columnas: "
                "`cuenta`, `deno_cuenta`, `cuit_cuenta`, `articulo`, `descripcion`, "
                "`precio`, `cantidad`, `entregada`, `fecha`, `localidad`, `observaciones_gen`, `numero`. "
                "La app clasifica automáticamente Premium / Activo por Pareto 80/20."
            )
            img_col, frm_col = st.columns([1,2])
            with frm_col:
                vend_mg   = st.text_input("Nombre del vendedor", value="Horacio", key="mg_vend")
                reemplazar = st.toggle("Reemplazar datos previos del vendedor", value=True, key="mg_reempl")
            arch_mg = st.file_uploader("Archivo MacroGest (.xlsx/.csv)", type=["xlsx","csv","xls"], key="up_mg")

            if arch_mg:
                df_car_prev, df_ven_prev = parsear_macrogest_ventas(arch_mg, vend_mg)
                if df_car_prev.empty:
                    st.error("No se pudo leer el archivo. Verificá que tenga las columnas correctas.")
                else:
                    # Preview
                    st.write(f"**{len(df_car_prev)} clientes detectados** — distribución Pareto automática:")
                    prev_cols = ["cliente","tipo","potencial_facturacion","ultima_compra","observaciones"]
                    st.dataframe(
                        df_car_prev[prev_cols].rename(columns={
                            "cliente":"Cliente","tipo":"Tipo",
                            "potencial_facturacion":"Importe Total $",
                            "ultima_compra":"Últ. Compra","observaciones":"Localidad"
                        }),
                        use_container_width=True, hide_index=True
                    )
                    n_prem = (df_car_prev["tipo"]=="premium").sum()
                    n_act  = (df_car_prev["tipo"]=="activo").sum()
                    st.caption(f"⭐ {n_prem} Premium  |  ✅ {n_act} Activos  |  "
                               f"📦 {len(df_ven_prev)} líneas de venta")

                    # Top productos por importe
                    if not df_ven_prev.empty:
                        top_prod = (df_ven_prev.groupby("descripcion")["importe_total"].sum()
                                    .reset_index().sort_values("importe_total", ascending=False).head(8))
                        fig_tp2 = px.bar(top_prod, x="importe_total", y="descripcion",
                                         orientation="h", title="Top Productos por Importe $",
                                         color_discrete_sequence=["#007bff"])
                        fig_tp2.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                        st.plotly_chart(fig_tp2, use_container_width=True)

                    if st.button(f"✅ Confirmar importación de {vend_mg}", type="primary", key="confirm_mg"):
                        conn = conectar_db()
                        if reemplazar:
                            conn.execute("DELETE FROM cartera_clientes WHERE vendedor=? AND campana=?",
                                         (vend_mg, CAMPANA_ACTUAL))
                            conn.execute("DELETE FROM ventas_detalle WHERE vendedor=? AND campana=?",
                                         (vend_mg, CAMPANA_ACTUAL))
                        # Batch insert cartera
                        cart_batch = [
                            (r["vendedor"],r["cliente"],r["tipo"],0,
                             r["potencial_facturacion"],0,r["ultima_compra"],
                             "activo",r["observaciones"],r["campana"])
                            for _, r in df_car_prev.iterrows()
                        ]
                        conn.cursor().executemany("""INSERT OR REPLACE INTO cartera_clientes
                            (vendedor,cliente,tipo,superficie_ha,potencial_facturacion,
                             field_view,ultima_compra,estado,observaciones,campana)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""", cart_batch)
                        # Batch insert ventas detalle
                        ven_batch = [
                            (r["campana"],r["vendedor"],r["cuenta"],r["cliente"],r["cuit"],
                             r["articulo"],r["descripcion"],r["precio"],r["cantidad"],
                             r["entregada"],r["importe_total"],r["fecha"],r["fecha_entrega"],
                             r["localidad"],r["observaciones"],r["numero_pedido"])
                            for _, r in df_ven_prev.iterrows()
                        ]
                        conn.cursor().executemany("""INSERT INTO ventas_detalle
                            (campana,vendedor,cuenta,cliente,cuit,articulo,descripcion,
                             precio,cantidad,entregada,importe_total,fecha,fecha_entrega,
                             localidad,observaciones,numero_pedido)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", ven_batch)
                        conn.commit(); conn.close()
                        limpiar_cache()
                        st.success(f"✅ {len(cart_batch)} clientes y {len(ven_batch)} líneas de venta importadas para {vend_mg}.")
                        st.rerun()

        # ── Importar cartera genérica ───────────────────────────────────────
        st.markdown("---")
        with st.expander("📥 Importar Cartera desde Excel (formato propio)"):
            st.caption("El archivo debe tener columnas: `vendedor`, `cliente`, `tipo`, `superficie_ha`, `potencial_facturacion`, `field_view` (0/1), `ultima_compra`, `observaciones`")
            arch_cart = st.file_uploader("Archivo cartera (.xlsx/.csv)", type=["xlsx","csv"], key="up_cart")
            if arch_cart and st.button("🚀 Importar Cartera", key="imp_cart"):
                try:
                    df_ci = pd.read_csv(arch_cart) if arch_cart.name.endswith(".csv") else pd.read_excel(arch_cart)
                    df_ci.columns = [c.strip().lower() for c in df_ci.columns]
                    ci_batch = [
                        (safe_str(r.get("vendedor","")), safe_str(r.get("cliente","")),
                         safe_str(r.get("tipo","activo")),
                         safe_float(r.get("superficie_ha",0)),
                         safe_float(r.get("potencial_facturacion",0)),
                         int(safe_float(r.get("field_view",0))),
                         safe_str(r.get("ultima_compra","")),
                         "activo", safe_str(r.get("observaciones","")), CAMPANA_ACTUAL)
                        for _, r in df_ci.iterrows() if safe_str(r.get("cliente",""))
                    ]
                    conn = conectar_db()
                    conn.cursor().executemany("""INSERT OR REPLACE INTO cartera_clientes
                        (vendedor,cliente,tipo,superficie_ha,potencial_facturacion,
                         field_view,ultima_compra,estado,observaciones,campana)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""", ci_batch)
                    conn.commit(); conn.close()
                    limpiar_cache()
                    st.success(f"✅ {len(ci_batch)} clientes importados.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

    # ── SUBTAB 5: REPORTES SEMANALES ──────────────────────────────────────────
    with pc5:
        st.write("### 📝 Registro de Reportes Semanales")

        ent_v3 = obtener_entregas()
        vendedores_r = sorted(ent_v3["vendedor"].dropna().replace("","S/V").unique().tolist()) \
                       if not ent_v3.empty else ["Vendedor 1"]

        col_rp1, col_rp2 = st.columns([2,1])
        with col_rp1:
            vend_r  = st.selectbox("Vendedor", vendedores_r, key="vend_rep")
        with col_rp2:
            ver_todos = st.toggle("Ver todos los vendedores", value=False, key="rep_todos")

        # Formulario nuevo reporte
        with st.expander("➕ Cargar Reporte Semanal", expanded=True):
            rp1, rp2, rp3 = st.columns(3)
            with rp1:
                fecha_rep = st.date_input("Semana del", value=datetime.now().date(), key="rep_fecha")
                fact_rep  = st.number_input("Facturación de la semana $", min_value=0.0, step=1000.0, key="rep_fact")
            with rp2:
                nuev_rep   = st.number_input("Nuevos clientes", min_value=0, step=1, key="rep_nuev")
                visit_rep  = st.number_input("Visitas realizadas", min_value=0, step=1, key="rep_visit")
            with rp3:
                st.write("Campo libre")
            av_rep  = st.text_area("✅ Avances / logros de la semana", height=80, key="rep_av")
            ob_rep  = st.text_area("⚠️ Obstáculos / dificultades",     height=80, key="rep_ob")
            op_rep  = st.text_area("💡 Oportunidades detectadas",       height=80, key="rep_op")
            pa_rep  = st.text_area("📋 Plan de acción semana siguiente", height=80, key="rep_pa")

            if st.button("💾 Guardar Reporte", type="primary", key="save_rep"):
                try:
                    conn = conectar_db()
                    conn.execute("""INSERT INTO reportes_semanales
                        (vendedor,fecha_semana,facturacion,nuevos_clientes,visitas,
                         avances,obstaculos,oportunidades,plan_accion,campana)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (vend_r, fecha_rep.strftime("%d/%m/%Y"),
                         fact_rep, nuev_rep, visit_rep,
                         av_rep, ob_rep, op_rep, pa_rep, CAMPANA_ACTUAL))
                    conn.commit(); conn.close()
                    limpiar_cache()
                    st.session_state["rep_ok"] = f"✅ Reporte de {vend_r} ({fecha_rep.strftime('%d/%m/%Y')}) guardado correctamente."
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")

            if st.session_state.get("rep_ok"):
                st.success(st.session_state.pop("rep_ok"))

        st.markdown("---")
        st.write("#### Historial de Reportes")
        df_rep_h = obtener_reportes(None if ver_todos else vend_r)
        if df_rep_h.empty:
            st.info("Sin reportes cargados todavía.")
        else:
            # KPIs del vendedor
            if not ver_todos:
                kr1, kr2, kr3, kr4 = st.columns(4)
                with kr1: st.metric("Reportes cargados",  len(df_rep_h))
                with kr2: st.metric("Facturación total",  f"${df_rep_h['facturacion'].sum():,.0f}")
                with kr3: st.metric("Nuevos clientes",    int(df_rep_h['nuevos_clientes'].sum()))
                with kr4: st.metric("Total visitas",      int(df_rep_h['visitas'].sum()))

                if len(df_rep_h) > 1:
                    df_evo_r = df_rep_h.sort_values("fecha_semana")[["fecha_semana","facturacion"]].copy()
                    df_evo_r["Acumulado"] = df_evo_r["facturacion"].cumsum()
                    fig_er = px.bar(df_evo_r, x="fecha_semana", y="facturacion",
                                    title=f"Facturación semanal — {vend_r}",
                                    color_discrete_sequence=["#007bff"])
                    fig_er.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig_er, use_container_width=True)

            cols_rep = ["vendedor","fecha_semana","facturacion","nuevos_clientes","visitas",
                        "avances","obstaculos","oportunidades","plan_accion"] \
                        if ver_todos else \
                       ["fecha_semana","facturacion","nuevos_clientes","visitas",
                        "avances","obstaculos","oportunidades","plan_accion"]
            cols_rep = [c for c in cols_rep if c in df_rep_h.columns]
            st.dataframe(
                df_rep_h[cols_rep].rename(columns={
                    "vendedor":"Vendedor","fecha_semana":"Semana","facturacion":"Facturación $",
                    "nuevos_clientes":"Nuevos","visitas":"Visitas",
                    "avances":"Avances","obstaculos":"Obstáculos",
                    "oportunidades":"Oportunidades","plan_accion":"Plan Próx."
                }),
                use_container_width=True, hide_index=True
            )
            st.download_button("📥 Exportar Reportes",
                               data=to_excel_bytes(df_rep_h, "Reportes"),
                               file_name=f"reportes_{vend_r.replace(' ','_')}.xlsx")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 11 — SIN ENTREGAR MACROGEST
# ═══════════════════════════════════════════════════════════════════════════════
with tab11:
    st.subheader("🔄 Pedidos Sin Entregar — MacroGest")
    st.caption("Importá el reporte de MacroGest con los pedidos pendientes de entrega. Los datos quedan guardados y se actualizan con cada importación.")

    with st.expander("📂 Importar archivo Sin Entregar", expanded=obtener_entregas("MACROGEST").empty):
        mg_col1, mg_col2 = st.columns(2)
        with mg_col1:
            mg_vendedor = st.text_input(
                "Vendedor (opcional)",
                value="",
                key="mg_vend_se",
                placeholder="ej: Juan Perez",
            )
        with mg_col2:
            mg_reemplazar = st.toggle(
                "Reemplazar datos MacroGest previos",
                value=True,
                key="mg_reempl_se",
            )
        arch_mg_se = st.file_uploader(
            "Archivo MacroGest (.xlsx / .csv)",
            type=["xlsx", "xls", "csv"],
            key="up_mg_se",
        )
        if arch_mg_se:
            try:
                arch_mg_se.seek(0)
                df_prev_mg = parsear_sin_entregar_macrogest(arch_mg_se, mg_vendedor)
            except Exception as ex:
                df_prev_mg = pd.DataFrame()
                st.error(f"Error leyendo archivo: {ex}")

            if not df_prev_mg.empty:
                tc_mg = df_prev_mg["cantidad_comprada"].sum()
                te_mg = df_prev_mg["cant_entregada"].sum()
                tp_mg = df_prev_mg["pendiente"].sum()
                st.markdown(
                    f"**{len(df_prev_mg)} renglones** · "
                    f"{df_prev_mg['cliente'].nunique()} clientes · "
                    f"{df_prev_mg['producto'].nunique()} productos"
                )
                km1, km2, km3 = st.columns(3)
                with km1: st.metric("Comprado total",  f"{tc_mg:,.0f}")
                with km2: st.metric("Entregado total", f"{te_mg:,.0f}")
                with km3: st.metric("Pendiente total", f"{tp_mg:,.0f}")
                st.dataframe(
                    df_prev_mg[["cliente","producto","cantidad_comprada",
                                "cant_entregada","pendiente","estado",
                                "dia_recibido","vendedor"]].head(20),
                    use_container_width=True, hide_index=True,
                )
                st.caption("Preview — primeros 20 registros.")
                if st.button("✅ Confirmar importación", type="primary", key="confirm_mg_se"):
                    conn = conectar_db()
                    if mg_reemplazar:
                        conn.execute("DELETE FROM entregas WHERE hoja='MACROGEST'")
                    mg_batch = [
                        ("MACROGEST", r["rto"], r["dia_recibido"],
                         r["cliente"], r["deposito"], r["cantidad_comprada"],
                         r["producto"], r["lote"], r["cant_entregada"],
                         r["pendiente"], r["estado"], r["vendedor"])
                        for _, r in df_prev_mg.iterrows()
                    ]
                    conn.cursor().executemany("""INSERT INTO entregas
                        (hoja,rto,dia_recibido,cliente,deposito,cantidad_comprada,
                         producto,lote,cant_entregada,pendiente,estado,vendedor)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", mg_batch)
                    ok_mg = len(mg_batch)
                    conn.commit(); conn.close()
                    guardar_metadata("ultima_importacion_mg",
                                     datetime.now().strftime("%d/%m/%Y %H:%M"))
                    limpiar_cache()
                    st.success(f"✅ {ok_mg} registros importados.")
                    st.rerun()

    st.markdown("---")
    ultima_mg = obtener_metadata("ultima_importacion_mg")
    if ultima_mg:
        st.caption(f"Última importación MacroGest: **{ultima_mg}**")

    df_mg_stored = obtener_entregas("MACROGEST")

    if df_mg_stored.empty:
        st.info("Sin datos. Importá un archivo arriba.")
    else:
        tc2 = df_mg_stored["cantidad_comprada"].sum()
        te2 = df_mg_stored["cant_entregada"].sum()
        tp2 = df_mg_stored["pendiente"].sum()
        pct2 = te2 / tc2 * 100 if tc2 > 0 else 0
        k1,k2,k3,k4,k5 = st.columns(5)
        with k1: st.metric("Registros",  len(df_mg_stored))
        with k2: st.metric("Clientes",   df_mg_stored["cliente"].nunique())
        with k3: st.metric("Comprado",   f"{tc2:,.0f}")
        with k4: st.metric("Entregado",  f"{te2:,.0f}", delta=f"{pct2:.1f}%")
        with k5: st.metric("Pendiente",  f"{tp2:,.0f}",
                            delta=f"-{tp2:,.0f}" if tp2>0 else "0",
                            delta_color="inverse")
        st.markdown("---")
        mf1, mf2, mf3, mf4, mf5 = st.columns(5)
        with mf1:
            f_cli_mg = st.text_input("🔍 Cliente", key="mg_fcli")
        with mf2:
            prods_mg = ["Todos"] + sorted(df_mg_stored["producto"].dropna().unique().tolist())
            f_prod_mg = st.selectbox("Producto", prods_mg, key="mg_fprod")
        with mf3:
            vends_mg = ["Todos"] + sorted(df_mg_stored["vendedor"].replace("","S/V").dropna().unique().tolist())
            f_vend_mg = st.selectbox("Vendedor", vends_mg, key="mg_fvend")
        with mf4:
            solo_pend_mg = st.toggle("Solo pendientes > 0", value=True, key="mg_fpend")
        with mf5:
            f_edad_mg = st.selectbox(
                "Antigüedad",
                ["Todos", "Reciente (≤30d)", "Demorado (30-60d)", "Crítico (>60d)"],
                key="mg_fedad",
                help="Días desde la fecha de recibo del pedido"
            )

        df_f_mg = df_mg_stored.copy()
        if f_cli_mg:  df_f_mg = df_f_mg[df_f_mg["cliente"].str.contains(f_cli_mg, case=False, na=False)]
        if f_prod_mg != "Todos": df_f_mg = df_f_mg[df_f_mg["producto"] == f_prod_mg]
        if f_vend_mg != "Todos": df_f_mg = df_f_mg[df_f_mg["vendedor"].replace("","S/V") == f_vend_mg]
        if solo_pend_mg: df_f_mg = df_f_mg[df_f_mg["pendiente"] > 0]
        if f_edad_mg != "Todos":
            df_f_mg["_dias"] = df_f_mg["dia_recibido"].apply(dias_desde)
            if f_edad_mg == "Reciente (≤30d)":      df_f_mg = df_f_mg[df_f_mg["_dias"] <= 30]
            elif f_edad_mg == "Demorado (30-60d)":  df_f_mg = df_f_mg[(df_f_mg["_dias"] > 30) & (df_f_mg["_dias"] <= 60)]
            elif f_edad_mg == "Crítico (>60d)":     df_f_mg = df_f_mg[df_f_mg["_dias"] > 60]
            df_f_mg = df_f_mg.drop(columns=["_dias"], errors="ignore")

        if not df_f_mg.empty:
            resumen_mg = (
                df_f_mg.groupby("producto")
                .agg(
                    Clientes =("cliente",   "nunique"),
                    Depósitos=("deposito",  lambda x: ", ".join(sorted(x.dropna().astype(str).unique()))),
                    Comprado =("cantidad_comprada","sum"),
                    Entregado=("cant_entregada",   "sum"),
                    Pendiente=("pendiente",         "sum"),
                )
                .reset_index()
                .rename(columns={"producto":"Producto"})
                .sort_values("Pendiente", ascending=False)
            )
            resumen_mg["% Entregado"] = (
                resumen_mg["Entregado"] / resumen_mg["Comprado"].replace(0,1) * 100
            ).round(1).astype(str) + "%"
            # Cruzar con ventas_detalle para calcular valor $ pendiente
            df_vd_mg = obtener_ventas_detalle()
            if not df_vd_mg.empty:
                precio_prom = (df_vd_mg.groupby("descripcion")["precio"]
                               .mean().reset_index()
                               .rename(columns={"descripcion":"Producto","precio":"Precio Prom"}))
                resumen_mg = resumen_mg.merge(precio_prom, on="Producto", how="left")
                resumen_mg["Precio Prom"] = resumen_mg["Precio Prom"].fillna(0)
                resumen_mg["Importe Pend. $"] = (resumen_mg["Pendiente"] * resumen_mg["Precio Prom"]).round(0)
                total_imp_mg = resumen_mg["Importe Pend. $"].sum()
                st.metric("💰 Valor total pendiente de entrega (estimado)",
                          f"USD {total_imp_mg:,.0f}",
                          help="Calculado usando precio promedio de ventas MacroGest importadas")
            else:
                st.info("💡 Para ver el valor monetario pendiente, importá ventas desde "
                        "**Plan Comercial → Cartera de Clientes → Importar desde MacroGest**.")
            st.dataframe(resumen_mg, use_container_width=True, hide_index=True)
            st.markdown("---")
            cols_mg = ["dia_recibido","cliente","deposito","producto","cantidad_comprada",
                       "cant_entregada","pendiente","estado","vendedor","rto"]
            cols_mg = [c for c in cols_mg if c in df_f_mg.columns]
            df_show_mg = df_f_mg[cols_mg].rename(columns={
                "dia_recibido":"Fecha","cliente":"Cliente","deposito":"Depósito",
                "producto":"Producto",
                "cantidad_comprada":"Comprado","cant_entregada":"Entregado",
                "pendiente":"Pendiente","estado":"Estado",
                "vendedor":"Vendedor","rto":"N° Pedido",
            })
            st.dataframe(df_show_mg, use_container_width=True, hide_index=True)
            out_mg = io.BytesIO()
            with pd.ExcelWriter(out_mg, engine="openpyxl") as w:
                resumen_mg.to_excel(w, index=False, sheet_name="Resumen_Producto")
                df_show_mg.to_excel(w, index=False, sheet_name="Detalle")
            st.download_button(
                "📥 Exportar Sin Entregar (.xlsx)",
                data=out_mg.getvalue(),
                file_name=f"sin_entregar_mg_{datetime.now().strftime('%Y%m%d')}.xlsx",
            )
            st.markdown("---")
            with st.expander("✏️ Registrar entrega o marcar como completado", expanded=False):
                st.caption("Actualizá el estado de un pedido directamente desde acá.")
                if df_f_mg.empty:
                    st.info("No hay registros con los filtros actuales.")
                else:
                    pedidos_disp = df_f_mg[df_f_mg["rto"].replace("","").notna()]["rto"].unique().tolist()
                    pedidos_disp = [p for p in pedidos_disp if p and str(p).strip()]
                    if pedidos_disp:
                        rto_sel = st.selectbox("N° Pedido a actualizar", pedidos_disp, key="mg_rto_sel",
                                               help="Seleccioná el número de pedido a modificar")
                        row_sel = df_f_mg[df_f_mg["rto"] == rto_sel]
                        if not row_sel.empty:
                            r0 = row_sel.iloc[0]
                            st.write(f"**Cliente:** {r0['cliente']} | **Producto:** {r0['producto']} | "
                                     f"**Pendiente actual:** {r0['pendiente']:,.1f}")
                            ua1, ua2 = st.columns(2)
                            with ua1:
                                nueva_entrega = st.number_input(
                                    "Cantidad entregada ahora", min_value=0.0,
                                    max_value=float(r0["pendiente"]) if r0["pendiente"] > 0 else 9999.0,
                                    step=1.0, key="mg_nueva_ent",
                                    help="Ingresá la cantidad que se acaba de entregar"
                                )
                                if st.button("📦 Registrar entrega parcial", key="mg_btn_parcial",
                                             help="Descuenta la cantidad del pendiente"):
                                    if nueva_entrega > 0:
                                        conn = conectar_db()
                                        conn.execute("""
                                            UPDATE entregas SET
                                                cant_entregada = cant_entregada + ?,
                                                pendiente = MAX(0, pendiente - ?)
                                            WHERE hoja='MACROGEST' AND rto=?
                                        """, (nueva_entrega, nueva_entrega, rto_sel))
                                        conn.commit(); conn.close()
                                        limpiar_cache()
                                        st.toast(f"✅ {nueva_entrega:,.1f} unidades registradas como entregadas.")
                                        st.rerun()
                                    else:
                                        st.warning("Ingresá una cantidad mayor a cero.")
                            with ua2:
                                st.write("")  # spacer
                                if st.button("✅ Marcar pedido como COMPLETADO", key="mg_btn_comp",
                                             type="primary",
                                             help="Cierra el pedido poniendo pendiente=0 y estado=ENTREGADO"):
                                    conn = conectar_db()
                                    conn.execute("""
                                        UPDATE entregas SET pendiente=0, estado='ENTREGADO',
                                            cant_entregada=cantidad_comprada
                                        WHERE hoja='MACROGEST' AND rto=?
                                    """, (rto_sel,))
                                    conn.commit(); conn.close()
                                    limpiar_cache()
                                    st.toast(f"✅ Pedido {rto_sel} marcado como completado.")
                                    st.rerun()
                    else:
                        st.info("Los registros filtrados no tienen N° de pedido asignado. "
                                "Podés usar 'cliente+producto' para identificarlos.")
