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
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import difflib

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

# Escribir config.toml con dark mode LC si no existe o está desactualizado
_cfg_dir  = os.path.join(os.path.dirname(__file__), ".streamlit")
_cfg_file = os.path.join(_cfg_dir, "config.toml")
_cfg_content = """[theme]
base = "dark"
primaryColor = "#F5A800"
backgroundColor = "#0E1117"
secondaryBackgroundColor = "#1C2333"
textColor = "#FAFAFA"
font = "sans serif"
"""
try:
    os.makedirs(_cfg_dir, exist_ok=True)
    _write_cfg = True
    if os.path.exists(_cfg_file):
        with open(_cfg_file, "r", encoding="utf-8") as _f:
            _write_cfg = _f.read().strip() != _cfg_content.strip()
    if _write_cfg:
        with open(_cfg_file, "w", encoding="utf-8") as _f:
            _f.write(_cfg_content)
except Exception:
    pass

st.set_page_config(
    page_title="La Clementina — Control de Depósito",
    page_icon="🌿",
    layout="wide"
)

# Colores corporativos LC
_LC_YELLOW = "#F5A800"
_LC_NAVY   = "#3D4E6B"
_LC_LIGHT  = "#FFF8E7"

st.markdown(f"""
<style>
/* ── Forzar dark mode en toda la app ── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stHeader"], .main, .block-container {{
    background-color: #0E1117 !important;
    color: #FAFAFA !important;
}}
[data-testid="stToolbar"]  {{ background-color: #0E1117 !important; }}
[data-testid="stDecoration"] {{ display: none; }}
section[data-testid="stSidebar"] {{ background-color: #1C2333 !important; }}

/* Expanders */
details, [data-testid="stExpander"] > div:first-child {{
    background-color: #1C2333 !important;
    border: 1px solid #2D3748 !important;
    border-radius: 8px !important;
}}

/* Métricas */
[data-testid="metric-container"] {{
    background-color: #1C2333 !important;
    border: 1px solid #2D3748 !important;
    border-radius: 8px !important;
    padding: 12px !important;
}}

/* ── Solo elementos HTML custom — */

/* Botones LC */
.stButton>button{{
    width:100%;border-radius:8px;font-weight:bold;height:3em;
    background:{_LC_NAVY};color:white;border:none;
}}
.stButton>button:hover{{background:{_LC_YELLOW};color:{_LC_NAVY}}}

/* Tabs acento LC */
.stTabs [data-baseweb="tab-list"] {{border-bottom:3px solid {_LC_YELLOW}!important}}
.stTabs [aria-selected="true"]    {{color:{_LC_YELLOW}!important;font-weight:700!important}}

/* Header LC */
.lc-header {{
    background:linear-gradient(135deg,{_LC_NAVY} 0%,#1a2540 100%);
    padding:14px 24px;border-radius:12px;margin-bottom:16px;
    display:flex;align-items:center;gap:18px;
    box-shadow:0 4px 20px rgba(0,0,0,.4);border:1px solid #2D3748;
}}
.lc-header-title {{color:white;font-size:1.35rem;font-weight:800;margin:0}}
.lc-header-sub   {{color:{_LC_YELLOW};font-size:.82rem;font-weight:600;margin:2px 0 0}}
.lc-badge        {{background:{_LC_YELLOW};color:{_LC_NAVY};font-weight:800;
                   padding:4px 10px;border-radius:6px;font-size:.75rem}}

/* Cards de stock */
.stock-card   {{background:#1C2333;padding:18px;border-radius:12px;
                box-shadow:0 4px 15px rgba(0,0,0,.3);margin-bottom:12px;
                border:1px solid #2D3748;position:relative}}
.card-normal  {{border-left:8px solid #38a169}}
.card-low     {{border-left:8px solid {_LC_YELLOW}}}
.card-warning {{border-left:8px solid #e53e3e}}
.stock-title  {{font-size:.95rem;color:#E2E8F0;font-weight:700;margin-bottom:8px;
                line-height:1.2;min-height:2.4em}}
.stock-value  {{font-size:1.5rem;color:#FAFAFA;font-weight:800;display:block}}
.stock-unit   {{font-size:.8rem;color:#A0AEC0}}
.stock-info   {{margin-top:10px;padding-top:8px;border-top:1px solid #2D3748;
                font-size:.8rem;color:#A0AEC0}}
.label-blue   {{background:#1a365d;color:#90cdf4;padding:2px 6px;border-radius:4px;font-weight:bold}}
.label-orange {{background:#2d1e0a;color:{_LC_YELLOW};padding:2px 6px;border-radius:4px;font-weight:bold}}

/* Badges */
.neg-badge  {{display:inline-block;background:#e53e3e;color:white;font-size:.65rem;
              padding:1px 6px;border-radius:8px;font-weight:bold;margin-left:4px;vertical-align:middle}}
.comp-badge {{display:inline-block;background:{_LC_YELLOW};color:{_LC_NAVY};font-size:.65rem;
              padding:1px 6px;border-radius:8px;font-weight:bold;margin-left:4px;vertical-align:middle}}
.venc-badge {{display:inline-block;background:#6b46c1;color:white;font-size:.65rem;
              padding:1px 6px;border-radius:8px;font-weight:bold;margin-left:4px;vertical-align:middle}}

/* Login */
.login-box {{max-width:400px;margin:80px auto;padding:30px;background:#1C2333;
             border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.4);border:1px solid #2D3748}}

/* Semáforos */
.semaforo-verde    {{background:#1a2e1a;border-left:6px solid #38a169;padding:8px 14px;border-radius:6px;margin:3px 0}}
.semaforo-amarillo {{background:#2d2010;border-left:6px solid {_LC_YELLOW};padding:8px 14px;border-radius:6px;margin:3px 0}}
.semaforo-rojo     {{background:#2d1212;border-left:6px solid #e53e3e;padding:8px 14px;border-radius:6px;margin:3px 0}}
.semaforo-label    {{font-weight:700;font-size:.85rem;color:#FAFAFA}}

/* Otros */
.projeccion-card {{background:#1C2333;border:1px solid #2D3748;border-radius:8px;padding:12px;margin:4px 0}}
.remito-box      {{background:#1C2333;border:2px solid {_LC_NAVY};border-radius:10px;padding:20px}}
.seccion-titulo  {{color:{_LC_YELLOW};font-weight:800;border-bottom:3px solid {_LC_YELLOW};
                   padding-bottom:4px;margin-bottom:12px}}
.presupuesto-item {{background:#1C2333;border-left:4px solid {_LC_YELLOW};
                    padding:8px 12px;margin:4px 0;border-radius:4px;font-size:.9rem;color:#FAFAFA}}

/* Mobile */
@media (max-width:768px) {{
    .stock-card {{padding:12px;margin-bottom:8px}}
    .stock-title {{font-size:.85rem;min-height:auto}}
    .stock-value {{font-size:1.3rem}}
    .lc-header   {{padding:10px 14px}}
    .lc-header-title {{font-size:1.1rem}}
    .stTabs [data-baseweb="tab-list"] {{flex-wrap:wrap}}
}}
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
        f"""CREATE TABLE IF NOT EXISTS lista_precios (
            id_precio_lista {_pk},
            rubro           TEXT,
            producto        TEXT NOT NULL,
            um              TEXT,
            precio_contado  REAL DEFAULT 0,
            precio_vta      REAL DEFAULT 0,
            financiacion    TEXT,
            fecha_carga     TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS remitos (
            id_remito    {_pk},
            numero       TEXT NOT NULL,
            fecha_hora   TEXT NOT NULL,
            cliente      TEXT,
            deposito     TEXT,
            usuario      TEXT,
            observaciones TEXT,
            items_json   TEXT,
            tipo         TEXT DEFAULT 'manual'
        )""",
        f"""CREATE TABLE IF NOT EXISTS lotes_vencimiento (
            id_lote         {_pk},
            codigo          TEXT,
            producto        TEXT NOT NULL,
            unidad          TEXT,
            deposito        TEXT,
            lote            TEXT,
            stock           REAL DEFAULT 0,
            fecha_vencimiento TEXT,
            fecha_fabricacion TEXT,
            estado          TEXT DEFAULT 'activa',
            fecha_importacion TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS reservas_stock (
            id_reserva   {_pk},
            fecha_hora   TEXT NOT NULL,
            id_producto  INTEGER NOT NULL,
            cantidad     REAL NOT NULL,
            cliente      TEXT NOT NULL,
            deposito     TEXT,
            lote         TEXT,
            referencia   TEXT,
            estado       TEXT DEFAULT 'activa',
            fecha_vencimiento_reserva TEXT,
            usuario      TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS importaciones_log (
            id_log      {_pk},
            fecha_hora  TEXT NOT NULL,
            tipo        TEXT NOT NULL,
            archivo     TEXT,
            filas       INTEGER DEFAULT 0,
            usuario     TEXT,
            hash        TEXT,
            resultado   TEXT
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
            "ALTER TABLE productos ADD COLUMN stock_minimo REAL DEFAULT 0",
            "ALTER TABLE movimientos ADD COLUMN origen TEXT",
            "ALTER TABLE movimientos ADD COLUMN anulado INTEGER DEFAULT 0",
            "ALTER TABLE movimientos ADD COLUMN usuario TEXT DEFAULT ''",
            "ALTER TABLE entregas ADD COLUMN hoja TEXT",
            "ALTER TABLE entregas ADD COLUMN lote TEXT",
            "ALTER TABLE entregas ADD COLUMN deposito TEXT",
            "ALTER TABLE movimientos ADD COLUMN observaciones TEXT DEFAULT ''",
            "ALTER TABLE entregas ADD COLUMN confirmada INTEGER DEFAULT 0",
            "ALTER TABLE entregas ADD COLUMN fecha_confirmacion TEXT",
            "ALTER TABLE entregas ADD COLUMN usuario_confirmacion TEXT",
        ]:
            try:  c.execute(m)
            except: pass

    # Índices para acelerar queries sobre tablas grandes
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_mov_producto ON movimientos(id_producto)",
        "CREATE INDEX IF NOT EXISTS idx_mov_origen   ON movimientos(origen)",
        "CREATE INDEX IF NOT EXISTS idx_mov_anulado  ON movimientos(anulado)",
        "CREATE INDEX IF NOT EXISTS idx_mov_fecha    ON movimientos(fecha_hora)",
        "CREATE INDEX IF NOT EXISTS idx_ent_hoja     ON entregas(hoja)",
        "CREATE INDEX IF NOT EXISTS idx_ent_pend     ON entregas(pendiente)",
        "CREATE INDEX IF NOT EXISTS idx_ent_cliente  ON entregas(cliente)",
        "CREATE INDEX IF NOT EXISTS idx_ent_origen   ON entregas(origen)",
        "CREATE INDEX IF NOT EXISTS idx_lp_producto  ON lista_precios(producto)",
    ]:
        try:
            if IS_POSTGRES: c.execute("SAVEPOINT idx_save")
            c.execute(idx_sql)
            if IS_POSTGRES: c.execute("RELEASE SAVEPOINT idx_save")
        except Exception:
            if IS_POSTGRES:
                try: c.execute("ROLLBACK TO SAVEPOINT idx_save")
                except Exception: pass

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
@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
def obtener_stock_full():
    df = obtener_stock_con_lote()
    if df.empty: return df
    return df.groupby(["Producto","Código","Unidad","Deposito"])["Stock Actual"].sum().reset_index()

@st.cache_data(ttl=300, show_spinner=False)
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
        LIMIT 2000
    """
    df = _rsql(query, conn)
    conn.close()
    return df

@st.cache_data(ttl=300, show_spinner=False)
def obtener_lista_precios():
    conn = conectar_db()
    df = _rsql("SELECT * FROM lista_precios ORDER BY rubro, producto", conn)
    conn.close()
    return df

@st.cache_data(ttl=300, show_spinner=False)
def obtener_entregas(hoja=None):
    conn = conectar_db()
    if hoja and hoja != "Todas":
        df = _rsql("SELECT * FROM entregas WHERE hoja=? ORDER BY dia_recibido DESC", conn, params=(hoja,))
    else:
        df = _rsql("SELECT * FROM entregas ORDER BY hoja, dia_recibido DESC", conn)
    conn.close()
    return df

@st.cache_data(ttl=300, show_spinner=False)
def obtener_productos_completo():
    conn = conectar_db()
    df = _rsql("SELECT * FROM productos ORDER BY nombre", conn)
    conn.close()
    return df

@st.cache_data(ttl=300, show_spinner=False)
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
    # Resetear preload y caches de session_state
    for _k in list(st.session_state.keys()):
        if _k.startswith("df_ent_cache_") or _k == "df_mg_cache":
            st.session_state[_k] = None

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

def _similitud(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

def _filtro_fonetico(serie, query, umbral=0.6):
    """Retorna máscara booleana con coincidencias exactas + fonéticas."""
    q = query.lower()
    exacta = serie.fillna("").str.lower().str.contains(q, na=False)
    if len(q) < 4:
        return exacta
    fonetica = serie.fillna("").apply(
        lambda x: any(_similitud(q, word) >= umbral for word in x.lower().split())
    )
    return exacta | fonetica

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

def hash_dataframe(df: pd.DataFrame) -> str:
    """SHA1 del contenido del DataFrame para detectar reimportaciones."""
    return hashlib.sha1(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:12]

def siguiente_numero_remito() -> str:
    """Genera el próximo número correlativo de remito: R-00001, R-00002..."""
    conn = conectar_db()
    try:
        row = conn.execute("SELECT COUNT(*) FROM remitos").fetchone()
        n   = (row[0] if row else 0) + 1
    except Exception:
        n = 1
    conn.close()
    return f"R-{n:05d}"

def registrar_remito(numero, cliente, deposito, items, usuario, observaciones="", tipo="manual"):
    import json as _json
    conn = conectar_db()
    conn.execute("""INSERT INTO remitos (numero,fecha_hora,cliente,deposito,usuario,observaciones,items_json,tipo)
                    VALUES (?,?,?,?,?,?,?,?)""",
                 (numero, datetime.now().strftime("%d/%m/%Y %H:%M"),
                  cliente, deposito, usuario, observaciones,
                  _json.dumps(items, ensure_ascii=False), tipo))
    conn.commit(); conn.close()

def registrar_importacion_log(tipo, archivo, filas, hash_val="", resultado="ok"):
    conn = conectar_db()
    try:
        conn.execute("""INSERT INTO importaciones_log (fecha_hora,tipo,archivo,filas,usuario,hash,resultado)
                        VALUES (?,?,?,?,?,?,?)""",
                     (datetime.now().strftime("%d/%m/%Y %H:%M"), tipo, archivo,
                      filas, usuario_actual(), hash_val, resultado))
        conn.commit()
    except Exception:
        pass
    conn.close()

def backup_db_bytes() -> bytes:
    """Exporta la DB SQLite completa como bytes para descarga (solo SQLite local)."""
    if IS_POSTGRES:
        return b""
    db_path = os.path.join(os.path.dirname(__file__), "stock.db")
    if not os.path.exists(db_path):
        return b""
    with open(db_path, "rb") as f:
        return f.read()

def generar_orden_compra_pdf(productos_bajo: pd.DataFrame, proveedor="Bayer CropScience / Monsanto-Bayer") -> bytes:
    """PDF de orden de compra sugerida para productos bajo umbral."""
    if not PDF_AVAILABLE or productos_bajo.empty:
        return b""
    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               rightMargin=1.5*cm, leftMargin=1.5*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elems  = []

    elems.append(Paragraph("<b>La Clementina S.A.</b> — Orden de Compra Sugerida", styles["Title"]))
    elems.append(Paragraph(
        f"Fecha: <b>{datetime.now().strftime('%d/%m/%Y')}</b> &nbsp;&nbsp; "
        f"Proveedor: <b>{proveedor}</b> &nbsp;&nbsp; "
        f"Operador: <b>{usuario_actual()}</b>",
        styles["Normal"]
    ))
    elems.append(Spacer(1, .5*cm))

    cols = [c for c in ["Producto","Unidad","Stock Actual","Sugerido_30d","proveedor"] if c in productos_bajo.columns]
    _hdr = [["#"] + [c.replace("_"," ").replace("Sugerido 30d","Cant. Sugerida") for c in cols]]
    _rows = [[str(i+1)] + [str(round(productos_bajo.iloc[i][c],1)) if isinstance(productos_bajo.iloc[i][c], float)
                            else str(productos_bajo.iloc[i][c]) for c in cols]
             for i in range(len(productos_bajo))]
    _tbl = Table(_hdr + _rows, repeatRows=1)
    _tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  rl_colors.HexColor("#3D4E6B")),
        ("TEXTCOLOR",     (0,0), (-1,0),  rl_colors.white),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#FFF8E7")]),
        ("GRID",          (0,0), (-1,-1), .4, rl_colors.grey),
    ]))
    elems.append(_tbl)
    elems.append(Spacer(1, 1*cm))
    elems.append(Paragraph(
        f"<font size=7 color=grey>Generado automáticamente — La Clementina S.A. · {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()

def calcular_forecast(dias_proyeccion=30) -> pd.DataFrame:
    """Proyecta cuánto se necesita comprar en los próximos N días según consumo histórico."""
    rot = calcular_rotacion_stock(90)
    stk = obtener_stock_full()
    if rot.empty or stk.empty:
        return pd.DataFrame()
    stk_sum = stk.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()
    rot_sum  = rot[["Producto","Sal_Diarias"]].groupby("Producto")["Sal_Diarias"].mean().reset_index()
    df_fc = stk_sum.merge(rot_sum, on="Producto", how="left").fillna(0)
    df_fc["Consumo_Proyectado"] = (df_fc["Sal_Diarias"] * dias_proyeccion).round(1)
    df_fc["Necesidad_Compra"]   = (df_fc["Consumo_Proyectado"] - df_fc["Stock Actual"]).clip(lower=0).round(1)
    df_fc["Días_Cobertura"]     = df_fc.apply(
        lambda r: round(r["Stock Actual"] / r["Sal_Diarias"]) if r["Sal_Diarias"] > 0 else None, axis=1
    )
    return df_fc[df_fc["Necesidad_Compra"] > 0].sort_values("Necesidad_Compra", ascending=False)

def generar_remito_pdf(numero: str, cliente: str, deposito: str,
                       items: list, usuario: str, observaciones: str = "") -> bytes:
    """
    Genera un remito de salida en PDF.
    items: lista de dicts con keys producto, unidad, lote, cantidad.
    """
    if not PDF_AVAILABLE:
        return b""
    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               rightMargin=1.5*cm, leftMargin=1.5*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elems  = []

    # Encabezado
    elems.append(Paragraph(
        "<b>La Clementina S.A.</b> — Remito de Salida de Depósito",
        styles["Title"]
    ))
    elems.append(Spacer(1, .3*cm))
    elems.append(Paragraph(
        f"Nro: <b>{numero}</b> &nbsp;&nbsp; Fecha: <b>{datetime.now().strftime('%d/%m/%Y %H:%M')}</b>"
        f" &nbsp;&nbsp; Operador: <b>{usuario}</b>",
        styles["Normal"]
    ))
    elems.append(Paragraph(f"Cliente: <b>{cliente}</b> &nbsp;&nbsp; Depósito: <b>{deposito}</b>",
                            styles["Normal"]))
    if observaciones:
        elems.append(Paragraph(f"Observaciones: {observaciones}", styles["Normal"]))
    elems.append(Spacer(1, .5*cm))

    # Tabla de items
    _header = [["#", "Producto", "Lote", "Cantidad", "Unidad"]]
    _rows   = [[str(i+1), it["producto"], it.get("lote",""), f'{it["cantidad"]:,.2f}', it.get("unidad","")]
               for i, it in enumerate(items)]
    _tbl = Table(_header + _rows, colWidths=[1*cm, 8*cm, 3*cm, 2.5*cm, 2*cm])
    _tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  rl_colors.HexColor("#3D4E6B")),
        ("TEXTCOLOR",     (0,0), (-1,0),  rl_colors.white),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#FFF8E7")]),
        ("GRID",          (0,0), (-1,-1), .5, rl_colors.grey),
        ("ALIGN",         (3,0), (3,-1),  "RIGHT"),
    ]))
    elems.append(_tbl)
    elems.append(Spacer(1, 1.5*cm))

    # Firmas
    _firma = Table(
        [["Entregó:", "", "Recibió:"],
         ["_________________________", "  ", "_________________________"],
         [usuario, "", cliente]],
        colWidths=[6*cm, 3*cm, 6*cm]
    )
    elems.append(_firma)
    elems.append(Spacer(1, .5*cm))
    elems.append(Paragraph(
        f"<font size=7 color=grey>Generado por Sistema de Gestión — La Clementina S.A. · {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()

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

def registrar_cambio_precio(producto: str, precio_nuevo: float, moneda: str, usuario: str):
    """Guarda un registro en historial_precios cada vez que cambia el precio de un producto."""
    conn = conectar_db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS historial_precios (
            id_precio   INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora  TEXT NOT NULL,
            producto    TEXT NOT NULL,
            precio      REAL NOT NULL,
            moneda      TEXT DEFAULT 'USD',
            usuario     TEXT
        )""")
        conn.execute(
            "INSERT INTO historial_precios (fecha_hora,producto,precio,moneda,usuario) VALUES (?,?,?,?,?)",
            (datetime.now().strftime("%d/%m/%Y %H:%M"), producto, precio_nuevo, moneda, usuario)
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


@st.cache_data(ttl=300, show_spinner=False)
def obtener_historial_precios(producto: str = "") -> pd.DataFrame:
    conn = conectar_db()
    try:
        if producto:
            df = _rsql("SELECT * FROM historial_precios WHERE producto=? ORDER BY id_precio DESC LIMIT 200",
                       conn, params=(producto,))
        else:
            df = _rsql("SELECT * FROM historial_precios ORDER BY id_precio DESC LIMIT 500", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def generar_presupuesto_pdf(cliente: str, items: list, usuario: str, obs: str = "") -> bytes:
    """
    PDF de presupuesto con branding LC.
    items = [{"producto": str, "cantidad": float, "precio": float, "moneda": str}, ...]
    """
    if not PDF_AVAILABLE: return b""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             rightMargin=1.5*cm, leftMargin=1.5*cm,
                             topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    elems  = []

    # Header
    _logo_path_p = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(_logo_path_p):
        try:
            from reportlab.platypus import Image as RLImage
            _img_p = RLImage(_logo_path_p, width=2*cm, height=2*cm, kind="proportional")
            _ht = Table([[_img_p,
                Paragraph("<font color='#3D4E6B' size=15><b>La Clementina S.A.</b></font><br/>"
                          "<font color='#888' size=9>Insumos Agropecuarios · San Jorge, Santa Fe</font>",
                          styles["Normal"]),
                Paragraph(f"<font color='#888' size=9>PRESUPUESTO<br/>"
                          f"{datetime.now().strftime('%d/%m/%Y')}</font>", styles["Normal"])
            ]], colWidths=[2.5*cm, 11*cm, 4*cm])
            _ht.setStyle(TableStyle([
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("BACKGROUND", (0,0), (-1,-1), rl_colors.HexColor("#FFF8E7")),
                ("LINEBELOW", (0,0), (-1,-1), 2, rl_colors.HexColor("#F5A800")),
                ("TOPPADDING", (0,0), (-1,-1), 6),
                ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ]))
            elems.append(_ht)
        except Exception:
            elems.append(Paragraph("La Clementina S.A. — Presupuesto", styles["Title"]))
    elems.append(Spacer(1, 0.3*cm))

    # Cliente y fecha
    elems.append(Paragraph(f"<b>Cliente:</b> {cliente}", styles["Normal"]))
    elems.append(Paragraph(f"<b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y')}  ·  "
                           f"<b>Elaborado por:</b> {usuario}", styles["Normal"]))
    if obs:
        elems.append(Paragraph(f"<b>Observaciones:</b> {obs}", styles["Normal"]))
    elems.append(Spacer(1, 0.3*cm))

    # Tabla de ítems
    _rows = [["#", "Producto", "Cantidad", "Precio Unit.", "Moneda", "Total"]]
    _total_usd = 0.0
    _total_ars = 0.0
    for i, it in enumerate(items, 1):
        _subtotal = it["cantidad"] * it["precio"]
        if it["moneda"] == "USD": _total_usd += _subtotal
        else:                     _total_ars += _subtotal
        _rows.append([
            str(i),
            it["producto"][:45],
            f"{it['cantidad']:,.2f}",
            f"{it['precio']:,.2f}",
            it["moneda"],
            f"{_subtotal:,.2f}",
        ])
    if _total_usd > 0:
        _rows.append(["", "", "", "", "TOTAL USD", f"{_total_usd:,.2f}"])
    if _total_ars > 0:
        _rows.append(["", "", "", "", "TOTAL ARS", f"{_total_ars:,.2f}"])

    _t = Table(_rows, colWidths=[0.8*cm, 8.5*cm, 2.2*cm, 2.5*cm, 1.8*cm, 2.2*cm])
    _t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), rl_colors.HexColor("#3D4E6B")),
        ("TEXTCOLOR",     (0,0), (-1,0), rl_colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("GRID",          (0,0), (-1,-3), 0.4, rl_colors.grey),
        ("ROWBACKGROUNDS",(0,1), (-1,-3), [rl_colors.white, rl_colors.HexColor("#FFF8E7")]),
        ("BACKGROUND",    (0,-2), (-1,-1), rl_colors.HexColor("#F5A800")),
        ("FONTNAME",      (0,-2), (-1,-1), "Helvetica-Bold"),
        ("ALIGN",         (2,0), (-1,-1), "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    elems.append(_t)
    elems.append(Spacer(1, 0.5*cm))
    elems.append(Paragraph(
        "<font size=8 color='#888'>Precios expresados en la moneda indicada. "
        "Sujeto a disponibilidad de stock. Válido por 7 días hábiles.</font>",
        styles["Normal"]
    ))
    elems.append(Spacer(1, 0.3*cm))
    elems.append(Paragraph(
        f"<font size=8 color='#888'>La Clementina S.A. — San Jorge, Santa Fe | "
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()


def generar_qr_lote(producto: str, lote: str, vencimiento: str, deposito: str) -> bytes:
    """Genera imagen PNG de QR con datos del lote. Requiere qrcode."""
    try:
        import qrcode as _qr
        _data = f"Producto: {producto}\nLote: {lote}\nVence: {vencimiento}\nDepósito: {deposito}"
        _img  = _qr.make(_data)
        _buf  = io.BytesIO()
        _img.save(_buf, format="PNG")
        return _buf.getvalue()
    except ImportError:
        return b""


def conciliar_stock_vs_lotes() -> pd.DataFrame:
    """
    Compara stock del sistema (movimientos) con suma de lotes importados.
    Retorna DataFrame con diferencias por producto.
    """
    stock_sys = obtener_stock_full()
    lotes     = obtener_lotes_vencimiento()
    if stock_sys.empty or lotes.empty:
        return pd.DataFrame()

    _sys = (stock_sys.groupby("Producto")["Stock Actual"]
            .sum().reset_index().rename(columns={"Stock Actual": "Stock Sistema"}))
    _lot = (lotes.groupby("producto")["stock"]
            .sum().reset_index()
            .rename(columns={"producto": "Producto", "stock": "Stock Lotes"}))

    _merge = _sys.merge(_lot, on="Producto", how="outer").fillna(0)
    _merge["Diferencia"] = _merge["Stock Sistema"] - _merge["Stock Lotes"]
    _merge["Estado"] = _merge["Diferencia"].apply(
        lambda d: "✅ Coincide" if abs(d) < 0.01 else
                  ("📈 Sobrante en sistema" if d > 0 else "📉 Faltante en sistema")
    )
    return _merge.sort_values("Diferencia", key=abs, ascending=False)


def generar_vencimientos_timeline() -> pd.DataFrame:
    """Agrupa stock de lotes por mes de vencimiento para timeline."""
    lotes = obtener_lotes_vencimiento()
    if lotes.empty: return pd.DataFrame()
    _df = lotes[lotes["fecha_vencimiento"].notna() & (lotes["stock"] > 0)].copy()
    def _mes(fv):
        try: return datetime.strptime(str(fv)[:10], "%d/%m/%Y").strftime("%Y-%m")
        except: return None
    _df["mes"] = _df["fecha_vencimiento"].apply(_mes)
    _df = _df[_df["mes"].notna()]
    return (_df.groupby(["mes","producto"])["stock"]
            .sum().reset_index()
            .rename(columns={"mes":"Mes","producto":"Producto","stock":"Stock"})
            .sort_values("Mes"))


def generar_venc_excel_baja(lotes_venc: pd.DataFrame) -> bytes:
    """Excel con lotes vencidos para gestión de baja."""
    _out = io.BytesIO()
    with pd.ExcelWriter(_out, engine="openpyxl") as _w:
        lotes_venc.to_excel(_w, index=False, sheet_name="Lotes_Para_Baja")
    return _out.getvalue()


def generar_ejecutivo_pdf() -> bytes:
    """Reporte ejecutivo PDF con branding LC. Retorna bytes."""
    if not PDF_AVAILABLE: return b""
    stock = obtener_stock_con_compromisos()
    ent   = obtener_entregas()
    mg    = obtener_entregas("MACROGEST")
    U     = int(obtener_metadata("umbral_alerta") or 20)
    buf   = io.BytesIO()
    doc   = SimpleDocTemplate(buf, pagesize=A4,
                               rightMargin=1.5*cm, leftMargin=1.5*cm,
                               topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    elems  = []

    # ── Header con logo ──────────────────────────────────────────────────────
    _logo_path_ej = os.path.join(os.path.dirname(__file__), "logo.png")
    _header_data = []
    if os.path.exists(_logo_path_ej):
        try:
            from reportlab.platypus import Image as RLImage
            _img = RLImage(_logo_path_ej, width=2.5*cm, height=2.5*cm, kind="proportional")
            _header_data = [[_img,
                Paragraph("<font color='#3D4E6B' size=16><b>La Clementina S.A.</b></font><br/>"
                          "<font color='#555' size=10>Reporte Ejecutivo de Depósito</font>",
                          styles["Normal"]),
                Paragraph(f"<font color='#888' size=9>{datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
                          styles["Normal"])]]
        except Exception:
            _header_data = None
    if _header_data:
        _ht = Table(_header_data, colWidths=[3*cm, 11*cm, 4*cm])
        _ht.setStyle(TableStyle([
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("BACKGROUND", (0,0), (-1,-1), rl_colors.HexColor("#FFF8E7")),
            ("LINEBELOW",  (0,0), (-1,-1), 2, rl_colors.HexColor("#F5A800")),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ]))
        elems.append(_ht)
    else:
        elems.append(Paragraph("La Clementina S.A. — Reporte Ejecutivo", styles["Title"]))
        elems.append(Paragraph(datetime.now().strftime("%d/%m/%Y %H:%M"), styles["Normal"]))
    elems.append(Spacer(1, 0.4*cm))

    # ── KPIs Stock ───────────────────────────────────────────────────────────
    if not stock.empty:
        elems.append(Paragraph("Stock — Indicadores Clave", styles["Heading2"]))
        _neg = int((stock["Stock Actual"] < 0).sum())
        _bajo = int((stock["Stock Actual"].between(0, U, inclusive="left")).sum())
        _comp = int((stock["Disponible Neto"] < 0).sum()) if "Disponible Neto" in stock.columns else 0
        _kpi = [
            ["Productos únicos", str(stock["Producto"].nunique()),
             "Volumen total", f"{stock['Stock Actual'].sum():,.0f}"],
            ["Depósitos activos", str(stock["Deposito"].nunique()),
             "Stock negativo 🔴", str(_neg)],
            ["Bajo umbral 🟡", str(_bajo),
             "Comprometido sin stock", str(_comp)],
        ]
        _t = Table(_kpi, colWidths=[5*cm, 3*cm, 5*cm, 4*cm])
        _t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), rl_colors.HexColor("#FFF8E7")),
            ("BACKGROUND",    (0,0), (0,-1), rl_colors.HexColor("#3D4E6B")),
            ("TEXTCOLOR",     (0,0), (0,-1), rl_colors.white),
            ("BACKGROUND",    (2,0), (2,-1), rl_colors.HexColor("#3D4E6B")),
            ("TEXTCOLOR",     (2,0), (2,-1), rl_colors.white),
            ("FONTNAME",      (0,0), (-1,-1), "Helvetica"),
            ("FONTSIZE",      (0,0), (-1,-1), 10),
            ("GRID",          (0,0), (-1,-1), 0.5, rl_colors.HexColor("#ccc")),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        elems.append(_t); elems.append(Spacer(1, 0.3*cm))

        # Críticos
        _crit = stock[stock["Stock Actual"] < U].sort_values("Stock Actual").head(12)
        if not _crit.empty:
            elems.append(Paragraph("Productos Críticos (bajo umbral o negativos)", styles["Heading2"]))
            _rows = [["Producto", "Depósito", "Stock", "Disponible"]]
            for _, r in _crit.iterrows():
                _dn = r.get("Disponible Neto", r["Stock Actual"])
                _rows.append([r["Producto"][:40], r["Deposito"],
                               f"{r['Stock Actual']:,.1f}", f"{_dn:,.1f}"])
            _tc = Table(_rows, colWidths=[9*cm, 3.5*cm, 2.5*cm, 2.5*cm])
            _tc.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), rl_colors.HexColor("#F5A800")),
                ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0), (-1,-1), 9),
                ("GRID",          (0,0), (-1,-1), 0.4, rl_colors.grey),
                ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#fffbf0")]),
            ]))
            elems.append(_tc); elems.append(Spacer(1, 0.3*cm))

    # ── Entregas pendientes ──────────────────────────────────────────────────
    if not ent.empty:
        elems.append(Paragraph("Entregas Pendientes — Resumen por Producto", styles["Heading2"]))
        _pend_g = (ent[ent["pendiente"] > 0]
                   .groupby("producto")
                   .agg(Clientes=("cliente","nunique"), Pendiente=("pendiente","sum"))
                   .reset_index().sort_values("Pendiente", ascending=False).head(12))
        if not _pend_g.empty:
            _re = [["Producto","Clientes","Vol. Pendiente"]]
            for _, r in _pend_g.iterrows():
                _re.append([r["producto"][:45], str(r["Clientes"]), f"{r['Pendiente']:,.0f}"])
            _te = Table(_re, colWidths=[10*cm, 3*cm, 4*cm])
            _te.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), rl_colors.HexColor("#3D4E6B")),
                ("TEXTCOLOR",     (0,0), (-1,0), rl_colors.white),
                ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0), (-1,-1), 9),
                ("GRID",          (0,0), (-1,-1), 0.4, rl_colors.grey),
                ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#f0f4f8")]),
            ]))
            elems.append(_te); elems.append(Spacer(1, 0.3*cm))

    # ── Sin Entregar MG ──────────────────────────────────────────────────────
    if not mg.empty:
        _mg_p = mg[mg["pendiente"] > 0]
        if not _mg_p.empty:
            elems.append(Paragraph(f"Sin Entregar MacroGest — {len(_mg_p)} pendientes", styles["Heading2"]))
            _id_col_mg = "rto" if "rto" in _mg_p.columns else (_mg_p.columns[0] if len(_mg_p.columns) else "pendiente")
            _mg_top = (_mg_p.groupby("cliente")
                       .agg(Items=(_id_col_mg,"nunique"), Pendiente=("pendiente","sum"))
                       .reset_index().sort_values("Pendiente", ascending=False).head(10))
            _rm = [["Cliente","Remitos","Pendiente"]]
            for _, r in _mg_top.iterrows():
                _rm.append([r["cliente"][:40], str(r["Items"]), f"{r['Pendiente']:,.0f}"])
            _tmg = Table(_rm, colWidths=[10*cm, 3*cm, 4*cm])
            _tmg.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), rl_colors.HexColor("#3D4E6B")),
                ("TEXTCOLOR",     (0,0), (-1,0), rl_colors.white),
                ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0), (-1,-1), 9),
                ("GRID",          (0,0), (-1,-1), 0.4, rl_colors.grey),
                ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#f0f4f8")]),
            ]))
            elems.append(_tmg); elems.append(Spacer(1, 0.3*cm))

    # ── Footer ───────────────────────────────────────────────────────────────
    elems.append(Spacer(1, 0.5*cm))
    elems.append(Paragraph(
        f"<font size=8 color='#888'>La Clementina S.A. — San Jorge, Santa Fe | "
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Confidencial</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()


@st.cache_data(ttl=300, show_spinner=False)
def obtener_lotes_vencimiento() -> pd.DataFrame:
    conn = conectar_db()
    df = _rsql("""SELECT codigo, producto, unidad, deposito, lote,
                         stock, fecha_vencimiento, fecha_fabricacion, estado, fecha_importacion
                  FROM lotes_vencimiento
                  WHERE estado = 'activa'
                  ORDER BY fecha_vencimiento ASC""", conn)
    conn.close()
    return df


def importar_lotes_vencimiento(df_raw: pd.DataFrame) -> tuple[int, int]:
    """
    Importa lotes desde el Excel de MacroGest (lote_vencimiento.xlsx).
    Retorna (filas_importadas, filas_con_vencimiento).
    Reemplaza todos los lotes activos previos.
    """
    from datetime import datetime as _dt
    _ahora = _dt.now().strftime("%d/%m/%Y %H:%M")

    # Normalizar columnas
    df_raw.columns = [str(c).strip().lower() for c in df_raw.columns]

    # Mapeo flexible de columnas
    _col_map = {
        "codigo":    next((c for c in df_raw.columns if c in ["codigo","código"]), None),
        "producto":  next((c for c in df_raw.columns if "descripcion" in c or "descripción" in c or "producto" in c), None),
        "unidad":    next((c for c in df_raw.columns if "unidad" in c), None),
        "deposito":  next((c for c in df_raw.columns if "deposito" in c or "depósito" in c), None),
        "lote":      next((c for c in df_raw.columns if c == "serie" or c == "lote"), None),
        "stock":     next((c for c in df_raw.columns if c in ["antidad","cantidad","stock","stock_actual","existencia","saldo","qty"]), None),
        "venc":      next((c for c in df_raw.columns if "vencimiento" in c and "muestra" not in c), None),
        "fabric":    next((c for c in df_raw.columns if "fabricacion" in c or "fabricación" in c), None),
    }

    if not _col_map["producto"]:
        raise ValueError(f"Columna de producto no encontrada. Disponibles: {list(df_raw.columns)}")

    conn = conectar_db()
    # Marcar todos los anteriores como inactivos (reemplazo completo)
    conn.execute("UPDATE lotes_vencimiento SET estado='inactiva' WHERE estado='activa'")

    filas = 0
    con_venc = 0
    rows_to_insert = []
    for _, r in df_raw.iterrows():
        _prod = safe_str(r.get(_col_map["producto"], "")).strip()
        if not _prod:
            continue
        _cod   = safe_str(r.get(_col_map["codigo"], "")) if _col_map["codigo"] else ""
        _uni   = safe_str(r.get(_col_map["unidad"], "")) if _col_map["unidad"] else ""
        _dep   = safe_str(r.get(_col_map["deposito"], "")) if _col_map["deposito"] else ""
        _lote  = safe_str(r.get(_col_map["lote"], "")) if _col_map["lote"] else ""
        _stk   = safe_float(r.get(_col_map["stock"], 0)) if _col_map["stock"] else 0.0
        _venc  = None
        _fab   = None
        if _col_map["venc"]:
            _v = r.get(_col_map["venc"])
            if pd.notna(_v):
                try:
                    _venc = pd.Timestamp(_v).strftime("%d/%m/%Y")
                    con_venc += 1
                except Exception:
                    pass
        if _col_map["fabric"]:
            _f = r.get(_col_map["fabric"])
            if pd.notna(_f):
                try:
                    _fab = pd.Timestamp(_f).strftime("%d/%m/%Y")
                except Exception:
                    pass
        rows_to_insert.append((_cod, _prod, _uni, _dep, _lote, _stk, _venc, _fab, "activa", _ahora))
        filas += 1

    _ph = "%s" if IS_POSTGRES else "?"
    _sql_lv = (
        f"INSERT INTO lotes_vencimiento "
        f"(codigo,producto,unidad,deposito,lote,stock,fecha_vencimiento,fecha_fabricacion,estado,fecha_importacion) "
        f"VALUES ({','.join([_ph]*10)})"
    )
    conn.cursor().executemany(_sql_lv, rows_to_insert)
    conn.commit()
    conn.close()
    return filas, con_venc


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

@st.cache_data(ttl=300, show_spinner=False)
def obtener_metas_campana(campana=CAMPANA_ACTUAL):
    conn = conectar_db()
    df = _rsql("SELECT * FROM metas_campana WHERE campana=?", conn, params=(campana,))
    conn.close()
    return df

@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
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
    "deposito_global":     "Todos",
    "dark_mode":           False,
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

# Header con usuario logueado + modo oscuro
# Filtro de depósito global
_deps_global_opts = ["Todos"]
try:
    _stk_deps = obtener_stock_full()
    if not _stk_deps.empty:
        _deps_global_opts += sorted(_stk_deps["Deposito"].unique().tolist())
except Exception:
    pass

_head_cols = st.columns([3, 2, 1, 1])
with _head_cols[1]:
    _dep_sel = st.selectbox("🏭 Depósito", _deps_global_opts, key="deposito_global",
                             label_visibility="collapsed",
                             help="Filtro global de depósito — afecta Panel, Stock Físico e Historial")
with _head_cols[2]:
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    if st.toggle("🌙", value=st.session_state.dark_mode, key="dark_toggle", help="Modo oscuro"):
        st.session_state.dark_mode = True
        st.markdown("""<style>
        .main{background:#1a1c21!important;color:#e0e0e0!important}
        .stApp{background:#1a1c21!important}
        .stock-card{background:#2d2f36!important;border-color:#444!important;color:#e0e0e0!important}
        .stock-title{color:#e0e0e0!important}
        .stock-info{color:#aaa!important}
        section[data-testid="stSidebar"]{background:#111!important}
        </style>""", unsafe_allow_html=True)
    else:
        st.session_state.dark_mode = False
with _head_cols[2]:
    if auth_enabled and st.session_state.get("authenticated"):
        st.caption(f"👤 {st.session_state.user_nombre}")
        if st.button("Salir", key="logout_btn"):
            for k in ("authenticated","user_rol","user_nombre","username"):
                st.session_state[k] = "" if k != "authenticated" else False
            st.rerun()
if auth_enabled and st.session_state.get("authenticated"):
    pass  # ya manejado arriba

# ─────────────────────────────────────────────────────────────────────────────
# 13. TABS PRINCIPALES
# ─────────────────────────────────────────────────────────────────────────────

# Header corporativo con logo
_logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
_logo_b64  = ""
if os.path.exists(_logo_path):
    with open(_logo_path, "rb") as _lf:
        import base64 as _b64
        _logo_b64 = _b64.b64encode(_lf.read()).decode()

_logo_html = (
    f'<img src="data:image/png;base64,{_logo_b64}" style="height:54px;border-radius:4px">'
    if _logo_b64 else
    f'<div style="background:{_LC_YELLOW};color:{_LC_NAVY};font-weight:900;font-size:1.4rem;'
    f'padding:8px 14px;border-radius:6px;letter-spacing:1px">LC</div>'
)

_user_info = ""
if st.session_state.get("authenticated"):
    _user_info = (f'<span class="lc-badge">👤 {st.session_state.user_nombre}'
                  f' &nbsp;·&nbsp; {st.session_state.user_rol}</span>')

st.markdown(f"""
<div class="lc-header">
    {_logo_html}
    <div style="flex:1">
        <p class="lc-header-title">Control de Depósito — La Clementina S.A.</p>
        <p class="lc-header-sub">Insumos Agropecuarios · Bayer CropScience / Monsanto-Bayer · San Jorge, Santa Fe</p>
    </div>
    {_user_info}
</div>
""", unsafe_allow_html=True)

# session_state para cache lazy por tab (se carga la primera vez que se abre cada tab)

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs([
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
    "🏷️ Lista de Precios",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PANEL DE CONTROL
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    stock_df = obtener_stock_con_compromisos()
    # Aplicar filtro global de depósito
    _dep_global = st.session_state.get("deposito_global", "Todos")
    if _dep_global != "Todos" and not stock_df.empty:
        stock_df = stock_df[stock_df["Deposito"] == _dep_global]

    if stock_df.empty:
        st.warning("⚠️ Sin datos. Subí el archivo en Configuración.")
        st.caption("Para empezar, andá a ⚙️ Configuración → Importar Stock desde MacroGest y subí el archivo de saldos.")
    else:
        U = st.session_state.umbral_alerta
        for meta, caption in [
            ("ultima_importacion",          "🕐 Última importación stock"),
            ("ultima_importacion_entregas",  "📦 Última importación entregas"),
            ("ultima_importacion_mg",        "🔄 Última importación MacroGest"),
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

        # Alerta inmediata si hay stock negativo
        if neg_n > 0:
            _neg_prods = stock_df[stock_df["Stock Actual"] < 0]["Producto"].unique()
            st.error(
                f"🚨 **{neg_n} productos con stock negativo:** "
                + " · ".join(_neg_prods[:8])
                + (" ..." if len(_neg_prods) > 8 else ""),
                icon="🚨"
            )

        # Alerta lotes vencidos con stock positivo
        _lotes_panel = obtener_lotes_vencimiento()
        if not _lotes_panel.empty:
            def _dias_lote(fv):
                try: return (datetime.strptime(str(fv)[:10], "%d/%m/%Y") - datetime.now()).days
                except: return None
            _lotes_panel["_dias"] = _lotes_panel["fecha_vencimiento"].apply(_dias_lote)
            _lv_venc = _lotes_panel[(_lotes_panel["_dias"].notna()) &
                                    (_lotes_panel["_dias"] < 0) &
                                    (_lotes_panel["stock"] > 0)]
            _lv_crit = _lotes_panel[(_lotes_panel["_dias"].notna()) &
                                    (_lotes_panel["_dias"] >= 0) &
                                    (_lotes_panel["_dias"] < 30) &
                                    (_lotes_panel["stock"] > 0)]
            if not _lv_venc.empty:
                st.error(f"⚗️ **{len(_lv_venc)} lotes VENCIDOS con stock positivo** "
                         f"({_lv_venc['stock'].sum():,.1f} unidades) — ver tab Reportes → Vencimientos",
                         icon="⚗️")
            elif not _lv_crit.empty:
                st.warning(f"⏰ **{len(_lv_crit)} lotes vencen en menos de 30 días** "
                           f"({_lv_crit['stock'].sum():,.1f} unidades) — ver Reportes → Vencimientos")

        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        with c1: st.metric("Productos",     stock_df["Producto"].nunique(),
                            help="Total de productos distintos con movimientos registrados")
        with c2: st.metric("Volumen Total", f"{stock_df['Stock Actual'].sum():,.0f}",
                            help="Suma de stock actual de todos los productos y depósitos")
        with c3: st.metric("Stock Bajo",    bajo_n,  delta=-bajo_n,  delta_color="inverse",
                            help=f"Productos con stock entre 0 y el umbral ({U}). Atención pero no crítico.")
        with c4: st.metric("Negativo ⚠️",   neg_n,   delta=-neg_n,   delta_color="inverse",
                            help="Productos con stock menor a 0. Requiere corrección inmediata.")
        with c5: st.metric("Comprometido",  comp_n,  delta=-comp_n,  delta_color="inverse",
                            help="Productos donde el stock disponible neto es negativo (stock < compromisos pendientes)")
        with c6: st.metric("Depósitos",     stock_df["Deposito"].nunique(),
                            help="Cantidad de depósitos/ubicaciones con stock registrado")
        with c7: st.metric("Pend. +30d ⏳", venc30,  delta=-venc30,  delta_color="inverse",
                            help="Pedidos de entrega con más de 30 días de antigüedad sin completar")

        # WhatsApp: alerta crítica + resumen KPIs del día
        wa = st.session_state.wa_numero
        _wa_col1, _wa_col2 = st.columns(2)
        if wa:
            with _wa_col1:
                if neg_n > 0 or bajo_n > 0:
                    alertas_wa = stock_df[stock_df["Stock Actual"] < U].head(15)
                    lineas = [f"⚠️ *Alerta Stock* — {datetime.now().strftime('%d/%m/%Y')}",
                              f"La Clementina S.A."]
                    for _, r in alertas_wa.iterrows():
                        lineas.append(f"• {r['Producto']}: {r['Stock Actual']:,.1f} {r['Unidad']} ({r['Deposito']})")
                    st.link_button("📱 Enviar alerta WhatsApp",
                                   f"https://wa.me/{wa}?text={urllib.parse.quote(chr(10).join(lineas))}",
                                   use_container_width=True)
                else:
                    st.caption("✅ Sin alertas críticas de stock")
            with _wa_col2:
                _ent_wa = obtener_entregas()
                _pend_wa = int(_ent_wa["pendiente"].sum()) if not _ent_wa.empty else 0
                _kpi_lines = [
                    f"📊 *Resumen LC — {datetime.now().strftime('%d/%m/%Y %H:%M')}*",
                    f"Productos: {stock_df['Producto'].nunique()} · Vol: {stock_df['Stock Actual'].sum():,.0f}",
                    f"🔴 Negativos: {neg_n} · 🟡 Bajo umbral: {bajo_n}",
                    f"📦 Entregas pendientes: {_pend_wa:,}",
                    f"_La Clementina S.A. — San Jorge_",
                ]
                st.link_button("📤 Compartir KPIs del día",
                               f"https://wa.me/{wa}?text={urllib.parse.quote(chr(10).join(_kpi_lines))}",
                               use_container_width=True)
        else:
            st.caption("Configurá tu número WhatsApp en ⚙️ Configuración para habilitar compartir.")

        st.markdown("---")

        # Semáforos por producto — tabla compacta y filtrable
        with st.expander("🚦 Estado de Stock por Producto", expanded=False):
            _prod_comp = obtener_productos_completo()
            _stk_sem = stock_df.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()
            if not _prod_comp.empty and "stock_minimo" in _prod_comp.columns:
                _stk_sem = _stk_sem.merge(
                    _prod_comp[["nombre","stock_minimo"]].rename(columns={"nombre":"Producto"}),
                    on="Producto", how="left"
                )
                _stk_sem["stock_minimo"] = _stk_sem["stock_minimo"].fillna(0)
            else:
                _stk_sem["stock_minimo"] = 0

            def _estado_sem(row):
                _u = row["stock_minimo"] if row["stock_minimo"] > 0 else U
                if row["Stock Actual"] < 0:        return "🔴 Negativo"
                elif row["Stock Actual"] < _u:     return "🟡 Bajo umbral"
                else:                              return "🟢 OK"

            _stk_sem["Estado"]  = _stk_sem.apply(_estado_sem, axis=1)
            _stk_sem["Mínimo"]  = _stk_sem["stock_minimo"].apply(lambda x: int(x) if x > 0 else f"global ({U})")
            _stk_sem = _stk_sem.sort_values(
                "Estado", key=lambda s: s.map({"🔴 Negativo": 0, "🟡 Bajo umbral": 1, "🟢 OK": 2})
            )

            # Resumen por estado
            _cnt = _stk_sem["Estado"].value_counts()
            _sa, _sb, _sc = st.columns(3)
            _sa.metric("🔴 Negativos",    _cnt.get("🔴 Negativo", 0))
            _sb.metric("🟡 Bajo umbral",  _cnt.get("🟡 Bajo umbral", 0))
            _sc.metric("🟢 OK",           _cnt.get("🟢 OK", 0))

            st.markdown("---")
            # Filtro por estado
            _fil_est = st.radio("Mostrar", ["Todos", "🔴 Negativos", "🟡 Bajo umbral", "🟢 OK"],
                                horizontal=True, key="sem_filtro")
            _df_sem_show = _stk_sem.copy()
            if _fil_est == "🔴 Negativos":    _df_sem_show = _df_sem_show[_df_sem_show["Estado"] == "🔴 Negativo"]
            elif _fil_est == "🟡 Bajo umbral": _df_sem_show = _df_sem_show[_df_sem_show["Estado"] == "🟡 Bajo umbral"]
            elif _fil_est == "🟢 OK":          _df_sem_show = _df_sem_show[_df_sem_show["Estado"] == "🟢 OK"]

            st.dataframe(
                _df_sem_show[["Estado","Producto","Unidad","Stock Actual","Mínimo"]]
                .rename(columns={"Stock Actual":"Stock"}),
                use_container_width=True, hide_index=True,
                column_config={
                    "Estado":  st.column_config.TextColumn("Estado", width="small"),
                    "Stock":   st.column_config.NumberColumn("Stock", format="%.1f"),
                }
            )
            if not _df_sem_show.empty:
                st.download_button("📥 Exportar estado de stock",
                                   data=to_excel_bytes(_df_sem_show[["Estado","Producto","Unidad","Stock Actual","Mínimo"]], "Estado_Stock"),
                                   file_name=f"estado_stock_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                   key="dl_sem")

        # Proyección de agotamiento
        with st.expander("📅 Proyección de Agotamiento", expanded=False):
            st.caption("Estimación de días de cobertura por producto basada en salidas de los últimos 90 días.")
            _rot = calcular_rotacion_stock(90)
            if _rot.empty:
                st.info("Sin historial de movimientos para calcular proyección.")
            else:
                _rot_show = _rot[_rot["Días_Cobertura"].notna()].copy()
                _rot_show["Alerta"] = _rot_show["Días_Cobertura"].apply(
                    lambda d: "🔴 Crítico (<15d)" if d < 15 else ("🟡 Bajo (<45d)" if d < 45 else "🟢 OK")
                )
                _rp1, _rp2 = st.columns([2, 1])
                with _rp1:
                    fig_rot = px.bar(
                        _rot_show.sort_values("Días_Cobertura").head(20),
                        x="Días_Cobertura", y="Producto", orientation="h",
                        color="Días_Cobertura",
                        color_continuous_scale=["#dc3545","#ffc107","#28a745"],
                        title="Días de cobertura — Top 20 productos más críticos",
                        labels={"Días_Cobertura": "Días"}
                    )
                    fig_rot.update_layout(height=420, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig_rot, use_container_width=True)
                with _rp2:
                    st.dataframe(
                        _rot_show[["Producto","Stock Actual","Sal_Diarias","Días_Cobertura","Alerta"]]
                        .rename(columns={"Stock Actual":"Stock","Sal_Diarias":"Sal/día","Días_Cobertura":"Días"})
                        .round(1),
                        use_container_width=True, hide_index=True
                    )
                st.download_button("📥 Exportar Proyección (.xlsx)",
                                   data=to_excel_bytes(_rot_show, "Proyeccion"),
                                   file_name="proyeccion_agotamiento.xlsx")

        # Gráficos
        with st.expander("📊 Gráficos y Comparativas", expanded=False):
            _gtabs = st.tabs(["📦 Por Depósito", "🏆 Top Productos", "⚖️ Stock vs Compromisos", "📈 Evolución", "🔤 Clasificación ABC"])

            with _gtabs[0]:
                cg1, cg2 = st.columns(2)
                with cg1:
                    dep_g = stock_df.groupby("Deposito")["Stock Actual"].sum().reset_index()
                    fig   = px.bar(dep_g.sort_values("Stock Actual"), x="Stock Actual", y="Deposito",
                                   orientation="h", title="Stock por Depósito", color="Stock Actual",
                                   color_continuous_scale="Blues")
                    fig.update_layout(height=300, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig, use_container_width=True)
                with cg2:
                    if not ent_panel.empty:
                        est_g = ent_panel.groupby("estado").size().reset_index(name="N")
                        est_g = est_g[est_g["estado"].str.strip() != ""]
                        if not est_g.empty:
                            fig3 = px.pie(est_g, names="estado", values="N",
                                          title="Estado de Entregas", hole=0.4)
                            fig3.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                            st.plotly_chart(fig3, use_container_width=True)

            with _gtabs[1]:
                top = (stock_df.groupby("Producto")["Stock Actual"].sum()
                       .reset_index().sort_values("Stock Actual", ascending=False).head(15))
                fig2 = px.bar(top.sort_values("Stock Actual"), x="Stock Actual", y="Producto",
                              orientation="h", title="Top 15 Productos por Stock",
                              color="Stock Actual", color_continuous_scale="Greens")
                fig2.update_layout(height=420, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig2, use_container_width=True)

            with _gtabs[2]:
                # Stock vs Compromisos por depósito
                st.caption("Compara el stock disponible contra los compromisos pendientes de entrega en cada depósito.")
                _dep_comp = stock_df.groupby("Deposito").agg(
                    Stock=("Stock Actual","sum"),
                    Comprometido=("Comprometido","sum")
                ).reset_index()
                _dep_comp["Disponible"] = (_dep_comp["Stock"] - _dep_comp["Comprometido"]).clip(lower=0)
                _dep_comp = _dep_comp.sort_values("Stock", ascending=False)
                fig_comp = px.bar(_dep_comp, x="Deposito", y=["Disponible","Comprometido"],
                                  barmode="stack", title="Stock Disponible vs Comprometido por Depósito",
                                  color_discrete_map={"Disponible":"#28a745","Comprometido":"#fd7e14"},
                                  labels={"value":"Unidades","variable":""})
                fig_comp.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_comp, use_container_width=True)
                st.dataframe(
                    _dep_comp.rename(columns={"Stock":"Stock Total","Disponible":"Disponible Neto"}),
                    use_container_width=True, hide_index=True
                )

            with _gtabs[3]:
                # Evolución del stock de un producto
                st.caption("Seleccioná un producto para ver cómo evolucionó su stock en el tiempo.")
                hist_evo = obtener_historial_movimientos()
                if hist_evo.empty:
                    st.info("Sin historial de movimientos.")
                else:
                    prod_evo = st.selectbox("Producto", sorted(stock_df["Producto"].unique()), key="evo_prod")
                    df_evo = hist_evo[hist_evo["Producto"] == prod_evo].copy()
                    if df_evo.empty:
                        st.info("Sin movimientos para este producto.")
                    else:
                        df_evo = df_evo[df_evo["Anulado"] == 0].copy()
                        def _parse_dt(s):
                            try: return datetime.strptime(str(s)[:16], "%d/%m/%Y %H:%M")
                            except: return None
                        df_evo["_dt"] = df_evo["Fecha"].apply(_parse_dt)
                        df_evo = df_evo.dropna(subset=["_dt"]).sort_values("_dt")
                        df_evo["Delta"] = df_evo.apply(
                            lambda r: r["Cantidad"] if r["Tipo"]=="Entrada" else -r["Cantidad"], axis=1)
                        df_evo["Stock Acumulado"] = df_evo["Delta"].cumsum()
                        df_evo["Fecha Mov"] = df_evo["_dt"].dt.strftime("%d/%m/%Y")
                        fig_evo = px.area(df_evo, x="_dt", y="Stock Acumulado",
                                          title=f"Evolución de stock — {prod_evo}",
                                          color_discrete_sequence=["#007bff"],
                                          labels={"_dt":"Fecha","Stock Acumulado":"Unidades"})
                        fig_evo.add_scatter(x=df_evo["_dt"], y=df_evo["Stock Acumulado"],
                                            mode="markers",
                                            marker=dict(color=df_evo["Tipo"].map(
                                                {"Entrada":"#28a745","Salida":"#dc3545"})),
                                            name="Movimientos",
                                            hovertemplate="%{customdata}<br>Stock: %{y:,.1f}<extra></extra>",
                                            customdata=df_evo["Tipo"] + " " + df_evo["Cantidad"].astype(str))
                        fig_evo.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0))
                        st.plotly_chart(fig_evo, use_container_width=True)
                        st.caption(f"Verde = Entrada · Rojo = Salida · {len(df_evo)} movimientos registrados")

            with _gtabs[4]:
                # Clasificación ABC por valor de stock
                st.caption("ABC: A = productos que concentran el 80% del stock (los más críticos), B = 15%, C = el resto.")
                _abc = stock_df.groupby("Producto")["Stock Actual"].sum().reset_index()
                _abc = _abc[_abc["Stock Actual"] > 0].sort_values("Stock Actual", ascending=False)
                if _abc.empty:
                    st.info("Sin stock positivo para clasificar.")
                else:
                    _abc["Acum %"] = _abc["Stock Actual"].cumsum() / _abc["Stock Actual"].sum() * 100
                    _abc["Clase"] = _abc["Acum %"].apply(
                        lambda x: "A — Crítico" if x <= 80 else ("B — Importante" if x <= 95 else "C — Bajo impacto"))
                    _col_abc1, _col_abc2 = st.columns(2)
                    with _col_abc1:
                        abc_res = _abc.groupby("Clase").agg(
                            Productos=("Producto","count"),
                            Stock_Total=("Stock Actual","sum")
                        ).reset_index()
                        fig_abc = px.pie(abc_res, names="Clase", values="Productos",
                                         title="Distribución ABC (por cantidad de productos)",
                                         color="Clase",
                                         color_discrete_map={
                                             "A — Crítico":"#dc3545",
                                             "B — Importante":"#ffc107",
                                             "C — Bajo impacto":"#28a745"})
                        fig_abc.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0))
                        st.plotly_chart(fig_abc, use_container_width=True)
                    with _col_abc2:
                        st.dataframe(abc_res.rename(columns={"Stock_Total":"Stock Total"}),
                                     use_container_width=True, hide_index=True)
                    st.dataframe(
                        _abc[["Producto","Stock Actual","Acum %","Clase"]].rename(
                            columns={"Stock Actual":"Stock","Acum %":"% Acumulado"}
                        ).round(1),
                        use_container_width=True, hide_index=True
                    )
                    st.download_button("📥 Exportar clasificación ABC",
                                       data=to_excel_bytes(_abc, "ABC"),
                                       file_name=f"abc_{datetime.now().strftime('%Y%m%d')}.xlsx")

        st.markdown("---")

        # ── Novedades del día ─────────────────────────────────────────────────
        with st.expander("📅 Novedades del día", expanded=False):
            _hoy_str = datetime.now().strftime("%d/%m/%Y")
            _hist_hoy = obtener_historial_movimientos()
            if not _hist_hoy.empty:
                _hoy_df = _hist_hoy[
                    _hist_hoy["Fecha"].astype(str).str.startswith(_hoy_str) &
                    (_hist_hoy["Anulado"] == 0)
                ]
                if _hoy_df.empty:
                    st.info(f"Sin movimientos registrados hoy ({_hoy_str}).")
                else:
                    _nd1, _nd2, _nd3 = st.columns(3)
                    _nd1.metric("Movimientos hoy",  len(_hoy_df))
                    _nd2.metric("Entradas",  int((_hoy_df["Tipo"]=="Entrada").sum()))
                    _nd3.metric("Salidas",   int((_hoy_df["Tipo"]=="Salida").sum()))
                    st.dataframe(
                        _hoy_df[["Fecha","Tipo","Producto","Cantidad","Unidad","Lote","Depósito","Referencia","Usuario"]]
                        .head(50),
                        use_container_width=True, hide_index=True
                    )
            else:
                st.info("Sin historial registrado.")

        # ── Tendencias mes a mes ──────────────────────────────────────────────
        with st.expander("📈 Tendencias Mensuales", expanded=False):
            st.caption("Compara el volumen de movimientos mes a mes para detectar tendencias de consumo.")
            _hist_tend = obtener_historial_movimientos()
            if _hist_tend.empty:
                st.info("Sin historial para mostrar tendencias.")
            else:
                def _mes_tend(s):
                    try: return datetime.strptime(str(s)[:10], "%d/%m/%Y").strftime("%Y-%m")
                    except: return None
                _hist_tend["Mes"] = _hist_tend["Fecha"].apply(_mes_tend)
                _tend_df = (
                    _hist_tend[_hist_tend["Anulado"] == 0]
                    .dropna(subset=["Mes"])
                    .groupby(["Mes","Tipo"])["Cantidad"].sum()
                    .reset_index()
                    .sort_values("Mes")
                )
                if not _tend_df.empty:
                    fig_tend = px.bar(
                        _tend_df, x="Mes", y="Cantidad", color="Tipo",
                        barmode="group",
                        color_discrete_map={"Entrada":"#3D4E6B","Salida":"#F5A800"},
                        title="Volumen de Entradas y Salidas por Mes",
                        labels={"Cantidad":"Unidades","Mes":"Mes"}
                    )
                    fig_tend.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig_tend, use_container_width=True)

                    # Estacionalidad: top productos por mes
                    st.markdown("**Estacionalidad por Producto**")
                    _prod_tend = st.selectbox("Producto", ["Todos"] + sorted(stock_df["Producto"].unique().tolist()),
                                              key="tend_prod")
                    _hist_t2 = _hist_tend[_hist_tend["Anulado"] == 0].copy()
                    if _prod_tend != "Todos":
                        _hist_t2 = _hist_t2[_hist_t2["Producto"] == _prod_tend]
                    _sal_mes = (
                        _hist_t2[_hist_t2["Tipo"]=="Salida"]
                        .dropna(subset=["Mes"])
                        .groupby("Mes")["Cantidad"].sum()
                        .reset_index().sort_values("Mes")
                    )
                    if not _sal_mes.empty:
                        fig_est = px.area(
                            _sal_mes, x="Mes", y="Cantidad",
                            title=f"Salidas mensuales — {'Todos los productos' if _prod_tend=='Todos' else _prod_tend}",
                            color_discrete_sequence=["#F5A800"]
                        )
                        fig_est.update_layout(height=260, margin=dict(l=0,r=0,t=40,b=0))
                        st.plotly_chart(fig_est, use_container_width=True)

        # ── Buscador Global ───────────────────────────────────────────────────
        with st.expander("🔎 Buscador Global", expanded=False):
            st.caption("Busca simultáneamente en stock, entregas y pedidos Sin Entregar MacroGest.")
            q_glob = st.text_input("Buscar producto o cliente...", key="busq_global",
                                   placeholder="ej: Round Up, BELTRAMO, glifosato...")
            if q_glob and len(q_glob) >= 2:
                _bg_cols = st.columns(3)
                with _bg_cols[0]:
                    st.markdown("**📦 En Stock**")
                    _bg_stk = stock_df[
                        stock_df["Producto"].str.contains(q_glob, case=False, na=False) |
                        stock_df["Código"].astype(str).str.contains(q_glob, case=False, na=False)
                    ][["Producto","Deposito","Stock Actual","Comprometido","Disponible Neto"]]
                    if _bg_stk.empty: st.info("Sin resultados.")
                    else: st.dataframe(_bg_stk, use_container_width=True, hide_index=True)

                with _bg_cols[1]:
                    st.markdown("**📋 En Entregas**")
                    if not ent_panel.empty:
                        _bg_ent = ent_panel[
                            ent_panel["producto"].str.contains(q_glob, case=False, na=False) |
                            ent_panel["cliente"].str.contains(q_glob, case=False, na=False)
                        ][["hoja","cliente","producto","pendiente","estado"]].head(20)
                        if _bg_ent.empty: st.info("Sin resultados.")
                        else: st.dataframe(_bg_ent, use_container_width=True, hide_index=True)
                    else:
                        st.info("Sin datos de entregas.")

                with _bg_cols[2]:
                    st.markdown("**🔄 En Sin Entregar MG**")
                    _bg_mg_cached = st.session_state.get("df_mg_cache")
                    _bg_mg = _bg_mg_cached if (_bg_mg_cached is not None) else obtener_entregas("MACROGEST")
                    if not _bg_mg.empty:
                        _bg_mg_f = _bg_mg[
                            _bg_mg["producto"].str.contains(q_glob, case=False, na=False) |
                            _bg_mg["cliente"].str.contains(q_glob, case=False, na=False)
                        ][["cliente","producto","pendiente","deposito","dia_recibido"]].head(20)
                        if _bg_mg_f.empty: st.info("Sin resultados.")
                        else: st.dataframe(_bg_mg_f, use_container_width=True, hide_index=True)
                    else:
                        st.info("Sin datos MacroGest.")

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

        cf1, cf2, cf3, cf4 = st.columns(4)
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
        with cf4:
            agrupar_prod   = st.toggle("🗂️ Agrupar por producto",    value=True,
                                       help="Suma todos los depósitos y muestra una card por producto")

        df_f = stock_df.copy()
        if search_q:
            df_f = df_f[df_f["Producto"].str.contains(search_q, case=False, na=False) |
                        df_f["Código"].astype(str).str.contains(search_q, case=False, na=False)]
        if f_prod != "Todos" and not search_q:
            df_f = df_f[df_f["Producto"] == f_prod]
        if f_dep != "Todos":
            df_f = df_f[df_f["Deposito"] == f_dep]
            agrupar_prod = False
        if hide_neg:
            mask = df_f["Stock Actual"] > 0
            if show_neg_f: mask = mask | (df_f["Stock Actual"] < 0)
            df_f = df_f[mask]
        if filter_reponer:
            df_f = df_f[df_f["Stock Actual"] < U]
        if show_comp_f:
            df_f = df_f[df_f["Disponible Neto"] < 0]

        if agrupar_prod and not df_f.empty:
            df_f = (df_f.groupby("Producto", as_index=False)
                    .agg({
                        "Código":          "first",
                        "Unidad":          "first",
                        "Stock Actual":    "sum",
                        "Comprometido":    "sum",
                        "Disponible Neto": "sum",
                        "Deposito":        lambda x: ", ".join(sorted(x.dropna().astype(str).unique())),
                    }))

        if not df_f.empty:
            excel_b = descargar_excel_agrupado(df_f)
            if excel_b:
                st.download_button("📥 Descargar Comparativa", data=excel_b,
                                   file_name="stock_agrupado.xlsx")

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
                                "<tr>"
                                "<td style='padding:1px 6px'>" + str(r["cliente"]) + "</td>"
                                "<td style='padding:1px 6px;text-align:right'><b>" + f"{r['pendiente']:,.0f}" + "</b></td>"
                                "<td style='padding:1px 6px;color:#aaa'>" + str(r["deposito"] or "-") + "</td>"
                                "</tr>"
                                for _, r in cli_pend.iterrows()
                            )
                            clientes_pend_line = (
                                "<br><b>Clientes pendiente:</b>"
                                "<table style='width:100%;font-size:.75rem;margin-top:4px'>"
                                "<tr style='color:#aaa'><td>Cliente</td><td>Pend.</td><td>Dep.</td></tr>"
                                + filas +
                                "</table>"
                            )

                    card_html = (
                        '<div class="stock-card ' + clase + '">'
                        '<div class="stock-title">' + str(item["Producto"]) + b_neg + b_comp + '</div>'
                        '<span class="stock-value">' + f"{stk:,.1f}" + ' <small class="stock-unit">' + str(item["Unidad"]) + '</small></span>'
                        '<div class="stock-info">'
                        '<b>ID</b> ' + str(item["Código"]) + '<br>'
                        '<b>Dep.</b> <span class="label-blue">' + str(item["Deposito"]) + '</span>'
                        + comp_line + venc_info + clientes_pend_line +
                        '</div>'
                        '</div>'
                    )
                    st.markdown(card_html, unsafe_allow_html=True)

        st.markdown("---")

        # Movimiento manual
        with st.expander("➕ Registrar movimiento manual"):
            st.markdown('<p class="seccion-titulo">Movimiento Manual de Stock</p>', unsafe_allow_html=True)
            cm1, cm2 = st.columns(2)
            with cm1:
                prod_m  = st.selectbox("Producto", sorted(stock_df["Producto"].unique()), key="mov_prod")
                tipo_m  = st.radio("Tipo", ["Entrada","Salida"], horizontal=True, key="mov_tipo")
            with cm2:
                cant_m  = st.number_input("Cantidad", min_value=0.01, step=0.5, key="mov_cant")
                dep_m   = st.selectbox("Depósito", sorted(stock_df["Deposito"].unique()), key="mov_dep")
            cm3, cm4 = st.columns(2)
            with cm3:
                lote_m = st.text_input("Lote", value="S/L", key="mov_lote")
                ref_m  = st.text_input("Referencia / Remito", value="", key="mov_ref")
            with cm4:
                obs_m  = st.text_area("Observaciones", value="", key="mov_obs", height=90,
                                      placeholder="Motivo, cliente destino, etc.")
                if tipo_m == "Salida":
                    cliente_remito = st.text_input("Cliente (para remito)", value="", key="mov_cliente")
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
                        deposito=dep_m, lote=lote_m, referencia=ref_m,
                        observaciones=obs_m,
                        cliente=st.session_state.get("mov_cliente","") if tipo_m=="Salida" else ""
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
                        _remito_bytes = b""
                        if id_p:
                            conn.execute("""INSERT INTO movimientos
                                (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,
                                 deposito,origen,usuario,observaciones)
                                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                (datetime.now().strftime("%d/%m/%Y %H:%M"), p["tipo"],
                                 id_p[0], p["cantidad"], p["lote"], p["referencia"],
                                 p["deposito"], "manual", usuario_actual(), p.get("observaciones","")))
                            conn.commit()
                            # Generar remito PDF si es salida
                            if p["tipo"] == "Salida":
                                _nro_remito = siguiente_numero_remito()
                                _prod_rem   = obtener_productos_completo()
                                _uni_rem    = ""
                                if not _prod_rem.empty:
                                    _row_uni = _prod_rem[_prod_rem["nombre"]==p["producto"]]
                                    _uni_rem = _row_uni.iloc[0]["unidad"] if not _row_uni.empty else ""
                                _items_rem = [{"producto":p["producto"],"lote":p["lote"],
                                               "cantidad":p["cantidad"],"unidad":_uni_rem}]
                                registrar_remito(_nro_remito, p.get("cliente","---"),
                                                 p["deposito"], _items_rem,
                                                 usuario_actual(), p.get("observaciones",""))
                                if PDF_AVAILABLE:
                                    _remito_bytes = generar_remito_pdf(
                                        numero=_nro_remito,
                                        cliente=p.get("cliente","---"),
                                        deposito=p["deposito"],
                                        items=_items_rem,
                                        usuario=usuario_actual(),
                                        observaciones=p.get("observaciones","")
                                    )
                        conn.close()
                        limpiar_cache()
                        st.session_state.mov_pendiente = None
                        st.success("✅ Registrado.")
                        if _remito_bytes:
                            st.download_button("🖨️ Descargar Remito PDF",
                                               data=_remito_bytes,
                                               file_name=f"remito_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                               mime="application/pdf")
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
@st.fragment
def mostrar_tab_entregas(hoja_nombre, titulo):
    st.subheader(titulo)
    if hoja_nombre == "LA CLEMENTINA S.A":
        with st.expander("📂 Importar TODAS las hojas", expanded=False):
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

    _ent_cache_key = f"df_ent_cache_{hoja_nombre}"
    if _ent_cache_key not in st.session_state or st.session_state[_ent_cache_key] is None:
        st.session_state[_ent_cache_key] = obtener_entregas(hoja_nombre)
    df_h = st.session_state[_ent_cache_key]

    _ult_ent = obtener_metadata("ultima_importacion_entregas")
    _hdr1, _hdr2 = st.columns([9, 1])
    with _hdr1:
        if _ult_ent: st.caption(f"🕐 Última importación: **{_ult_ent}**")
    with _hdr2:
        if st.button("🔄", key=f"ent_refresh_{hoja_nombre}", help="Actualizar datos"):
            st.session_state[_ent_cache_key] = obtener_entregas(hoja_nombre)
            df_h = st.session_state[_ent_cache_key]
            st.rerun()

    if df_h is None or df_h.empty:
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

    # Pre-calcular columna lowercase para búsqueda instantánea por cliente
    _ent_cli_key = f"ent_cli_lower_{hoja_nombre}"
    _ent_id_key  = f"ent_cache_id_{hoja_nombre}"
    if _ent_cli_key not in st.session_state or st.session_state.get(_ent_id_key) != id(df_h):
        st.session_state[_ent_cli_key] = df_h["cliente"].fillna("").str.lower()
        st.session_state[_ent_id_key]  = id(df_h)

    _mask2 = pd.Series([True] * len(df_h), index=df_h.index)
    if f_est != "Todos": _mask2 &= df_h["estado"] == f_est
    if f_pr  != "Todos": _mask2 &= df_h["producto"] == f_pr
    if f_vd  != "Todos": _mask2 &= df_h["vendedor"].replace("","S/V") == f_vd
    if f_cli:            _mask2 &= st.session_state[_ent_cli_key].str.contains(f_cli.lower(), na=False)

    df_f2 = df_h[_mask2].copy()
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

    _inv_tabs = st.tabs(["📝 Conteo Individual", "📋 Conteo Masivo", "↩️ Devoluciones", "📊 Historial Auditorías", "🔀 Transferencia"])

    with _inv_tabs[0]:
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
            if dif != 0:
                if dif > 0: st.info(f"📈 Sobrante de {dif:,.1f} — se registrará una Entrada de ajuste.")
                else:       st.warning(f"📉 Faltante de {abs(dif):,.1f} — se registrará una Salida de ajuste.")
            if st.button("💾 Guardar Auditoría", type="primary"):
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
                            (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen,usuario,observaciones)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (datetime.now().strftime("%d/%m/%Y %H:%M"),
                             "Entrada" if dif>0 else "Salida", id_p[0], abs(dif),
                             "S/L", f"Ajuste Inventario", d_inv, "manual", usuario_actual(), obs_inv))
                conn.commit(); conn.close()
                registrar_importacion_log("Ajuste Inventario", f"{p_inv}/{d_inv}", 1)
                limpiar_cache()
                st.success("✅ Auditoría guardada.")
                st.rerun()
        else:
            st.info("Sin datos de stock.")

    with _inv_tabs[1]:
        st.write("### 📋 Conteo Masivo")
        st.caption("Subí la planilla de conteo completada para registrar todos los ajustes de una vez.")
        if st_df.empty:
            st.info("Sin datos de stock.")
        else:
            arch_conteo = st.file_uploader("Planilla de conteo (.xlsx)",
                                           type=["xlsx","xls","csv"], key="up_conteo_masivo")
            if arch_conteo:
                try:
                    _df_conteo = (pd.read_excel(arch_conteo) if not arch_conteo.name.endswith(".csv")
                                  else pd.read_csv(arch_conteo))
                    _df_conteo.columns = [str(c).strip() for c in _df_conteo.columns]
                    # Buscar columnas de conteo físico
                    _col_conteo = next((c for c in _df_conteo.columns
                                        if "conteo" in c.lower() or "fisico" in c.lower() or "físico" in c.lower()), None)
                    _col_prod   = next((c for c in _df_conteo.columns
                                        if "producto" in c.lower() or "nombre" in c.lower()), None)
                    _col_dep    = next((c for c in _df_conteo.columns
                                        if "deposit" in c.lower() or "dep" in c.lower()), None)
                    if not _col_conteo or not _col_prod:
                        st.error(f"Columnas no detectadas. Disponibles: {list(_df_conteo.columns)}")
                    else:
                        _df_conteo = _df_conteo[_df_conteo[_col_prod].notna()].copy()
                        st.caption(f"{len(_df_conteo)} productos en la planilla")
                        st.dataframe(_df_conteo.head(10), use_container_width=True, hide_index=True)
                        if st.button("✅ Importar conteo masivo", type="primary", key="btn_conteo_masivo"):
                            conn = conectar_db()
                            _ok_c = 0
                            for _, _rc in _df_conteo.iterrows():
                                _pn = safe_str(_rc.get(_col_prod,""))
                                _dp = safe_str(_rc.get(_col_dep,"")) if _col_dep else ""
                                _cf = safe_float(_rc.get(_col_conteo, 0))
                                if not _pn: continue
                                _filt = st_df[st_df["Producto"]==_pn]
                                if _dp: _filt = _filt[_filt["Deposito"]==_dp]
                                _vs = float(_filt["Stock Actual"].sum()) if not _filt.empty else 0.0
                                _dif = _cf - _vs
                                _cod = safe_str(_filt.iloc[0]["Código"]) if not _filt.empty else "S/C"
                                conn.execute("""INSERT INTO inventario_fisico
                                    (fecha_conteo,codigo,producto,deposito,stock_sistema,conteo_fisico,diferencia,observaciones)
                                    VALUES (?,?,?,?,?,?,?,?)""",
                                    (datetime.now().strftime("%d/%m/%Y %H:%M"), _cod, _pn,
                                     _dp or "General", _vs, _cf, _dif, "Conteo masivo"))
                                if abs(_dif) > 0.001:
                                    _id_p = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",(_pn,)).fetchone()
                                    if _id_p:
                                        conn.execute("""INSERT INTO movimientos
                                            (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,deposito,origen,usuario)
                                            VALUES (?,?,?,?,?,?,?,?,?)""",
                                            (datetime.now().strftime("%d/%m/%Y %H:%M"),
                                             "Entrada" if _dif>0 else "Salida", _id_p[0], abs(_dif),
                                             "S/L", "Ajuste conteo masivo", _dp or "General",
                                             "manual", usuario_actual()))
                                _ok_c += 1
                            conn.commit(); conn.close()
                            registrar_importacion_log("Conteo Masivo", arch_conteo.name, _ok_c)
                            limpiar_cache()
                            st.success(f"✅ {_ok_c} productos procesados.")
                            st.rerun()
                except Exception as _ex:
                    st.error(f"Error: {_ex}")

    with _inv_tabs[2]:
        st.write("### ↩️ Registrar Devolución")
        st.caption("Registra la devolución de un producto por parte de un cliente. Incrementa el stock con tipo 'Devolución'.")
        if st_df.empty:
            st.info("Sin datos de stock.")
        else:
            _dv1, _dv2 = st.columns(2)
            with _dv1:
                _prod_dev = st.selectbox("Producto devuelto",
                                         sorted(obtener_productos_completo()["nombre"].tolist()
                                                if not obtener_productos_completo().empty else []),
                                         key="dev_prod")
                _cant_dev = st.number_input("Cantidad devuelta", min_value=0.01, step=1.0, key="dev_cant")
                _dep_dev  = st.selectbox("Depósito destino", sorted(st_df["Deposito"].unique()), key="dev_dep")
            with _dv2:
                _cli_dev  = st.text_input("Cliente que devuelve", key="dev_cli")
                _lote_dev = st.text_input("Lote", value="S/L", key="dev_lote")
                _obs_dev  = st.text_area("Motivo de devolución", key="dev_obs", height=80)
            _rem_dev  = st.text_input("N° Remito original (opcional)", key="dev_rem")
            if st.button("💾 Registrar Devolución", type="primary", key="btn_dev"):
                if _prod_dev and _cant_dev > 0:
                    conn = conectar_db()
                    _id_dev = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",
                                           (_prod_dev,)).fetchone()
                    if _id_dev:
                        conn.execute("""INSERT INTO movimientos
                            (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,referencia,
                             deposito,origen,usuario,observaciones)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (datetime.now().strftime("%d/%m/%Y %H:%M"), "Entrada",
                             _id_dev[0], _cant_dev, _lote_dev,
                             f"Devolución — {_cli_dev}" + (f" / Rem: {_rem_dev}" if _rem_dev else ""),
                             _dep_dev, "devolucion", usuario_actual(),
                             _obs_dev))
                        conn.commit()
                        conn.close()
                        limpiar_cache()
                        st.success(f"✅ Devolución de {_cant_dev:,.1f} unidades de {_prod_dev} registrada.")
                        st.rerun()
                    else:
                        conn.close()
                        st.error("Producto no encontrado.")
                else:
                    st.warning("Completá el producto y la cantidad.")

    with _inv_tabs[3]:
        st.write("### 📊 Historial de Auditorías de Inventario")
        conn = conectar_db()
        df_inv_h2 = _rsql("SELECT * FROM inventario_fisico ORDER BY id_inventario DESC LIMIT 500", conn)
        conn.close()
        if df_inv_h2.empty:
            st.info("Sin auditorías registradas aún.")
        else:
            _ai1, _ai2, _ai3 = st.columns(3)
            _ai1.metric("Total auditorías", len(df_inv_h2))
            _ai2.metric("Con diferencia", int((df_inv_h2["diferencia"] != 0).sum()))
            _ai3.metric("Diferencia acumulada", f"{df_inv_h2['diferencia'].sum():,.1f}")
            st.dataframe(
                df_inv_h2.rename(columns={
                    "fecha_conteo":"Fecha","codigo":"Código","producto":"Producto",
                    "deposito":"Depósito","stock_sistema":"Sistema","conteo_fisico":"Conteo",
                    "diferencia":"Dif","observaciones":"Notas"
                }),
                use_container_width=True, hide_index=True
            )
            st.download_button("📥 Exportar auditorías (.xlsx)",
                               data=to_excel_bytes(df_inv_h2, "Auditorias"),
                               file_name=f"auditorias_{datetime.now().strftime('%Y%m%d')}.xlsx")

    with _inv_tabs[4]:
        st.write("### 🔀 Transferencia entre Depósitos")
        st.caption("Mover stock de un depósito a otro. Genera movimiento de Salida en origen y Entrada en destino.")
        if st_df.empty:
            st.info("Sin datos de stock.")
        else:
            _deps_tr = sorted(st_df["Deposito"].unique().tolist())
            _prods_tr = sorted(st_df["Producto"].unique().tolist())
            _tr1, _tr2 = st.columns(2)
            with _tr1:
                _prod_tr = st.selectbox("Producto", _prods_tr, key="tr_prod")
                _dep_orig_tr = st.selectbox("Depósito origen", _deps_tr, key="tr_orig")
                _dep_dest_tr = st.selectbox("Depósito destino", _deps_tr, key="tr_dest")
            with _tr2:
                _filt_tr = st_df[(st_df["Producto"]==_prod_tr) & (st_df["Deposito"]==_dep_orig_tr)]
                _stk_orig_tr = float(_filt_tr["Stock Actual"].sum()) if not _filt_tr.empty else 0.0
                st.metric("Stock disponible en origen", f"{_stk_orig_tr:,.1f}")
                _cant_tr = st.number_input("Cantidad a transferir", min_value=0.01,
                                           max_value=max(_stk_orig_tr, 0.01),
                                           step=1.0, key="tr_cant")
                _motivo_tr = st.text_input("Motivo / Referencia", key="tr_motivo",
                                           placeholder="ej: Reposición sucursal Las Varillas")
            if _dep_orig_tr == _dep_dest_tr:
                st.warning("El depósito de origen y destino deben ser distintos.")
            elif st.button("✅ Confirmar Transferencia", type="primary", key="btn_tr"):
                if _cant_tr > 0:
                    conn = conectar_db()
                    _id_tr = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",
                                         (_prod_tr,)).fetchone()
                    if _id_tr:
                        _ts_tr = datetime.now().strftime("%d/%m/%Y %H:%M")
                        _ref_tr = f"TRANSF: {_dep_orig_tr} → {_dep_dest_tr}" + (f" | {_motivo_tr}" if _motivo_tr else "")
                        conn.cursor().executemany(
                            """INSERT INTO movimientos
                               (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,
                                referencia,deposito,origen,usuario)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            [
                                (_ts_tr, "Salida",  _id_tr[0], _cant_tr, "S/L", _ref_tr, _dep_orig_tr, "transferencia", usuario_actual()),
                                (_ts_tr, "Entrada", _id_tr[0], _cant_tr, "S/L", _ref_tr, _dep_dest_tr, "transferencia", usuario_actual()),
                            ]
                        )
                        conn.commit(); conn.close()
                        limpiar_cache()
                        st.success(f"✅ Transferidos {_cant_tr:,.1f} de {_prod_tr}: {_dep_orig_tr} → {_dep_dest_tr}")
                        st.rerun()
                    else:
                        conn.close()
                        st.error("Producto no encontrado.")
                else:
                    st.warning("Ingresá una cantidad mayor a cero.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — HISTORIAL
# ═══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("📜 Historial de Movimientos")
    _ult_h = obtener_metadata("ultima_importacion")
    if _ult_h: st.caption(f"🕐 Última importación de stock: **{_ult_h}**")
    hist_df = obtener_historial_movimientos()

    if hist_df.empty:
        st.info("Sin movimientos registrados.")
    else:
        # KPIs rápidos
        _hk1, _hk2, _hk3, _hk4 = st.columns(4)
        with _hk1: st.metric("Total movimientos", len(hist_df))
        with _hk2: st.metric("Entradas", int((hist_df["Tipo"]=="Entrada").sum()))
        with _hk3: st.metric("Salidas",  int((hist_df["Tipo"]=="Salida").sum()))
        with _hk4:
            _usu_list = hist_df["Usuario"].replace("","sistema").unique()
            st.metric("Operadores", len(_usu_list))
        st.markdown("---")

        ch1, ch2, ch3, ch4 = st.columns(4)
        with ch1: f_tipo_h = st.selectbox("Tipo", ["Todos","Entrada","Salida"])
        with ch2: f_orig_h = st.selectbox("Origen", ["Todos","excel","manual","entrega"])
        with ch3: f_bus_h  = st.text_input("🔍 Buscar producto/lote")
        with ch4:
            usu_opts = ["Todos"] + sorted(hist_df["Usuario"].replace("","sistema").unique().tolist())
            f_usu_h  = st.selectbox("Operador", usu_opts)
        cd1, cd2, cd3 = st.columns(3)
        with cd1:
            f_desde = st.date_input("Desde", value=datetime.now().date()-timedelta(days=30))
        with cd2:
            f_hasta = st.date_input("Hasta", value=datetime.now().date())
        with cd3:
            f_anulados = st.toggle("Mostrar anulados", value=False)

        _hmask = pd.Series([True] * len(hist_df), index=hist_df.index)
        if f_tipo_h != "Todos": _hmask &= hist_df["Tipo"] == f_tipo_h
        if f_orig_h != "Todos": _hmask &= hist_df["Origen"] == f_orig_h
        if f_usu_h  != "Todos": _hmask &= hist_df["Usuario"].replace("","sistema") == f_usu_h
        if f_bus_h:
            _q = f_bus_h.lower()
            _hmask &= (
                hist_df["Producto"].fillna("").str.lower().str.contains(_q, na=False) |
                hist_df["Lote"].astype(str).str.lower().str.contains(_q, na=False) |
                hist_df["Referencia"].astype(str).str.lower().str.contains(_q, na=False)
            )
        if not f_anulados:
            _hmask &= hist_df["Anulado"] == 0

        df_hf = hist_df[_hmask].copy()

        def parse_fh(s):
            try: return datetime.strptime(str(s)[:10], "%d/%m/%Y").date()
            except: return None
        df_hf["_fdt"] = df_hf["Fecha"].apply(parse_fh)
        df_hf = df_hf[(df_hf["_fdt"] >= f_desde) & (df_hf["_fdt"] <= f_hasta)].drop(columns=["_fdt"])

        _PAGE_H = 150
        _total_h = len(df_hf)
        _total_pages_h = max(1, (_total_h + _PAGE_H - 1) // _PAGE_H)
        _ph1, _ph2, _ph3 = st.columns([1, 2, 1])
        with _ph1:
            st.markdown(f"**{_total_h} movimientos** · {_total_pages_h} páginas")
        with _ph2:
            _page_h = st.number_input("Página", min_value=1, max_value=_total_pages_h,
                                      value=1, step=1, key="hist_page", label_visibility="collapsed")
        with _ph3:
            st.caption(f"pág {_page_h}/{_total_pages_h}")
        df_hf_page = df_hf.iloc[(_page_h - 1) * _PAGE_H : _page_h * _PAGE_H]
        st.dataframe(df_hf_page, use_container_width=True, hide_index=True)

        if not df_hf.empty:
            _dh1, _dh2 = st.columns(2)
            with _dh1:
                st.download_button("📥 Exportar historial completo (.xlsx)",
                                   data=to_excel_bytes(df_hf, "Historial"),
                                   file_name=f"historial_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                   use_container_width=True)
            with _dh2:
                # Mini gráfico de actividad por día
                if len(df_hf) > 1:
                    df_hf["_fdt2"] = df_hf["Fecha"].apply(parse_fh)
                    act_g = df_hf.groupby(["_fdt2","Tipo"]).size().reset_index(name="N")
                    act_g["_fdt2"] = act_g["_fdt2"].astype(str)
                    fig_act = px.bar(act_g, x="_fdt2", y="N", color="Tipo",
                                     color_discrete_map={"Entrada":"#28a745","Salida":"#dc3545"},
                                     title="Actividad diaria", barmode="group")
                    fig_act.update_layout(height=220, margin=dict(l=0,r=0,t=30,b=0),
                                          xaxis_title="", yaxis_title="Movimientos")
                    st.plotly_chart(fig_act, use_container_width=True)

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

        # Trazabilidad por lote
        st.markdown("---")
        with st.expander("🔍 Trazabilidad por Lote"):
            st.caption("Buscá un número de lote y ves todos sus movimientos: de dónde vino y a dónde fue.")
            _lote_q = st.text_input("Número de lote", key="trz_lote_input",
                                    placeholder="ej: L2024-001, LOTE3...")
            if _lote_q and len(_lote_q) >= 2:
                _df_trz = hist_df[
                    hist_df["Lote"].astype(str).str.contains(_lote_q, case=False, na=False)
                ].copy()
                if _df_trz.empty:
                    st.info(f"Sin movimientos para el lote '{_lote_q}'.")
                else:
                    _trz_ent = _df_trz[_df_trz["Tipo"] == "Entrada"]["Cantidad"].sum()
                    _trz_sal = _df_trz[_df_trz["Tipo"] == "Salida"]["Cantidad"].sum()
                    _tc1, _tc2, _tc3, _tc4 = st.columns(4)
                    _tc1.metric("Movimientos",      len(_df_trz))
                    _tc2.metric("Entradas totales", f"{_trz_ent:,.1f}")
                    _tc3.metric("Salidas totales",  f"{_trz_sal:,.1f}")
                    _tc4.metric("Stock neto",       f"{_trz_ent - _trz_sal:,.1f}")
                    st.dataframe(
                        _df_trz[["Fecha","Tipo","Producto","Cantidad","Unidad","Lote","Depósito","Referencia","Usuario","Anulado"]],
                        use_container_width=True, hide_index=True
                    )
                    st.download_button("📥 Exportar trazabilidad (.xlsx)",
                                       data=to_excel_bytes(_df_trz, "Trazabilidad"),
                                       file_name=f"trz_lote_{_lote_q}.xlsx")

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
            st.caption(f"{len(df_tr)} transferencias registradas")
            st.dataframe(df_tr, use_container_width=True, hide_index=True)
            st.download_button("📥 Exportar transferencias (.xlsx)",
                               data=to_excel_bytes(df_tr, "Transferencias"),
                               file_name=f"transferencias_{datetime.now().strftime('%Y%m%d')}.xlsx")

        if not df_inv_h.empty:
            st.markdown("---")
            st.subheader("📋 Auditorías de Inventario")
            df_inv_show = df_inv_h.rename(columns={
                "fecha_conteo":"Fecha","codigo":"Código","producto":"Producto","deposito":"Depósito",
                "stock_sistema":"Sistema","conteo_fisico":"Conteo","diferencia":"Dif","observaciones":"Notas"
            })
            st.dataframe(df_inv_show, use_container_width=True, hide_index=True)
            st.download_button("📥 Exportar auditorías (.xlsx)",
                               data=to_excel_bytes(df_inv_show, "Auditorias"),
                               file_name=f"auditorias_{datetime.now().strftime('%Y%m%d')}.xlsx")


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
        st.write("### 💹 Margen Bruto por Producto")
        st.caption("Cruza el precio de costo (valorización) con el precio de venta (lista 2026) para estimar margen bruto.")
        lp_mg = obtener_lista_precios()
        if lp_mg.empty:
            st.info("Cargá la Lista de Precios 2026 en la pestaña 🏷️ Lista de Precios para ver el margen.")
        elif not prod_refr.empty:
            _stk_mg = stk_full.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()
            _stk_mg = _stk_mg.merge(
                prod_refr[["nombre","precio_unitario","moneda_precio"]].rename(columns={"nombre":"Producto"}),
                on="Producto", how="left"
            )
            _lp_map = lp_mg.groupby("producto")["precio_vta"].mean().reset_index()
            _lp_map.columns = ["Producto", "precio_vta"]
            _stk_mg = _stk_mg.merge(_lp_map, on="Producto", how="left")
            _tc_mg = float(obtener_metadata("tipo_cambio") or 1000)
            _stk_mg["Costo_USD"] = _stk_mg.apply(
                lambda r: r["precio_unitario"] if r.get("moneda_precio","USD")=="USD"
                          else (r["precio_unitario"] / _tc_mg), axis=1
            ).fillna(0)
            _stk_mg["Venta_ARS"]  = _stk_mg["precio_vta"].fillna(0)
            _stk_mg["Venta_USD"]  = _stk_mg["Venta_ARS"] / _tc_mg
            _stk_mg["Margen_USD"] = (_stk_mg["Venta_USD"] - _stk_mg["Costo_USD"]).round(2)
            _stk_mg["Margen_%"]   = _stk_mg.apply(
                lambda r: round((r["Margen_USD"] / r["Costo_USD"]) * 100, 1) if r["Costo_USD"] > 0 else None, axis=1
            )
            _stk_mg["Stock_Valor_USD"] = _stk_mg["Stock Actual"] * _stk_mg["Costo_USD"]
            _stk_mg_show = _stk_mg[_stk_mg["Costo_USD"] > 0].sort_values("Margen_%", ascending=False)
            if _stk_mg_show.empty:
                st.info("Asigná precios de costo en 'Actualizar Precios por Producto' para ver el margen.")
            else:
                _mg1, _mg2 = st.columns(2)
                with _mg1:
                    _avg_margin = _stk_mg_show["Margen_%"].mean()
                    st.metric("Margen promedio", f"{_avg_margin:.1f}%")
                with _mg2:
                    _productos_sin_vta = len(_stk_mg[_stk_mg["precio_vta"].isna() | (_stk_mg["precio_vta"] == 0)])
                    st.metric("Sin precio de venta", _productos_sin_vta)
                fig_mg = px.bar(
                    _stk_mg_show.head(20).sort_values("Margen_%"),
                    x="Margen_%", y="Producto", orientation="h",
                    color="Margen_%", color_continuous_scale=["#dc3545","#ffc107","#28a745"],
                    title="Margen Bruto % por Producto",
                    labels={"Margen_%":"Margen %"}
                )
                fig_mg.update_layout(height=400, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_mg, use_container_width=True)
                st.dataframe(
                    _stk_mg_show[["Producto","Stock Actual","Costo_USD","Venta_USD","Margen_USD","Margen_%"]]
                    .rename(columns={"Stock Actual":"Stock","Costo_USD":"Costo USD",
                                     "Venta_USD":"PVta USD","Margen_USD":"Margen USD","Margen_%":"Margen %"})
                    .round(2),
                    use_container_width=True, hide_index=True
                )
                st.download_button("📥 Exportar Margen Bruto (.xlsx)",
                                   data=to_excel_bytes(_stk_mg_show, "Margen"),
                                   file_name="margen_bruto.xlsx")

        st.markdown("---")
        st.write("### 🛒 Orden de Reposición y Forecast")
        U_rep = st.session_state.umbral_alerta
        consumo_df = calcular_rotacion_stock()
        orden_bin  = generar_orden_reposicion(stk_full, U_rep, consumo_df)
        bajo_n_rep = len(stk_full[stk_full["Stock Actual"] < U_rep])

        _fc1, _fc2, _fc3 = st.columns(3)
        with _fc1:
            dias_fc = st.selectbox("Horizonte de forecast", [15, 30, 60, 90], index=1,
                                   help="Días hacia adelante para proyectar la necesidad de compra")
        with _fc2:
            st.metric("Productos bajo umbral", bajo_n_rep,
                       help=f"Tienen menos de {U_rep} unidades en stock")
        with _fc3:
            df_fc_now = calcular_forecast(dias_fc)
            st.metric("Necesitan reposición", len(df_fc_now),
                       help=f"Productos que se agotarían en los próximos {dias_fc} días")

        if not df_fc_now.empty:
            fig_fc = px.bar(
                df_fc_now.head(20).sort_values("Necesidad_Compra", ascending=True),
                x="Necesidad_Compra", y="Producto", orientation="h",
                title=f"Necesidad de compra — próximos {dias_fc} días",
                color="Necesidad_Compra", color_continuous_scale=["#ffc107","#dc3545"],
                labels={"Necesidad_Compra":"Unidades a reponer"}
            )
            fig_fc.update_layout(height=380, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_fc, use_container_width=True)
            st.dataframe(
                df_fc_now[["Producto","Unidad","Stock Actual","Consumo_Proyectado","Necesidad_Compra","Días_Cobertura"]]
                .rename(columns={"Stock Actual":"Stock","Consumo_Proyectado":f"Consumo {dias_fc}d",
                                  "Necesidad_Compra":"A Reponer","Días_Cobertura":"Días Cob."}),
                use_container_width=True, hide_index=True
            )

        _or1, _or2, _or3 = st.columns(3)
        with _or1:
            st.download_button("📥 Orden de Reposición (.xlsx)",
                               data=orden_bin, file_name="orden_reposicion.xlsx",
                               use_container_width=True)
        with _or2:
            _oc_pdf = generar_orden_compra_pdf(
                df_fc_now if not df_fc_now.empty else pd.DataFrame(),
                proveedor="Bayer CropScience / Monsanto-Bayer"
            )
            if _oc_pdf:
                st.download_button("🖨️ Orden de Compra PDF",
                                   data=_oc_pdf, file_name="orden_compra.pdf",
                                   mime="application/pdf", use_container_width=True)
        with _or3:
            st.download_button("📥 Forecast (.xlsx)",
                               data=to_excel_bytes(df_fc_now, "Forecast") if not df_fc_now.empty else b"",
                               file_name=f"forecast_{dias_fc}d.xlsx",
                               use_container_width=True)

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
    r_tab1, r_tab2, r_tab3, r_tab4, r_tab5, r_tab6, r_tab7, r_tab8, r_tab9, r_tab10 = st.tabs([
        "👥 Dashboard Vendedores",
        "🔄 Rotación de Stock",
        "⏰ Vencimientos",
        "📄 Reporte Mensual",
        "📊 Resumen Ejecutivo",
        "⏸️ Stock Inmovilizado",
        "⚡ Eficiencia Entregas",
        "🏆 Ranking Clientes",
        "📉 Proyección de Quiebre",
        "😴 Clientes Sin Actividad",
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

    # ── Vencimientos por Lote ─────────────────────────────────────────────────
    with r_tab3:
        st.write("### ⏰ Control de Vencimientos por Lote")

        df_lotes = obtener_lotes_vencimiento()

        if df_lotes.empty:
            st.info("Sin datos de lotes. Importá el archivo de lotes desde **⚙️ Configuración → Importación**.")
        else:
            # Calcular días restantes
            def _dias_v(fv):
                if not fv: return None
                try:
                    return (datetime.strptime(str(fv)[:10], "%d/%m/%Y") - datetime.now()).days
                except Exception:
                    return None

            df_lotes["dias"] = df_lotes["fecha_vencimiento"].apply(_dias_v)

            def _sem_v(d):
                if d is None:   return "⚪ Sin fecha"
                if d < 0:       return "🔴 Vencido"
                if d < 30:      return "🟠 Crítico"
                if d < 90:      return "🟡 Próximo"
                return "🟢 OK"

            df_lotes["Estado"] = df_lotes["dias"].apply(_sem_v)

            # ── KPIs globales ─────────────────────────────────────────────────
            _con_fecha = df_lotes[df_lotes["dias"].notna()]
            _lv1, _lv2, _lv3, _lv4, _lv5 = st.columns(5)
            _lv1.metric("Lotes totales",      len(df_lotes))
            _lv2.metric("🔴 Vencidos",        int((_con_fecha["dias"] < 0).sum()))
            _lv3.metric("🟠 Críticos (<30d)", int(((_con_fecha["dias"] >= 0) & (_con_fecha["dias"] < 30)).sum()))
            _lv4.metric("🟡 Próximos (30-90d)",int(((_con_fecha["dias"] >= 30) & (_con_fecha["dias"] < 90)).sum()))
            _lv5.metric("🟢 OK",              int((_con_fecha["dias"] >= 90).sum()))

            # Alerta inmediata si hay vencidos con stock positivo
            _venc_con_stock = df_lotes[(df_lotes["dias"].notna()) &
                                       (df_lotes["dias"] < 0) &
                                       (df_lotes["stock"] > 0)]
            if not _venc_con_stock.empty:
                st.error(f"🚨 **{len(_venc_con_stock)} lotes VENCIDOS con stock positivo** — "
                         f"requieren revisión urgente. Stock total involucrado: "
                         f"{_venc_con_stock['stock'].sum():,.1f}")

            st.markdown("---")

            # ── Filtros ───────────────────────────────────────────────────────
            _fl1, _fl2, _fl3 = st.columns([2, 2, 2])
            with _fl1:
                _est_opts = ["Todos", "🔴 Vencido", "🟠 Crítico", "🟡 Próximo", "🟢 OK", "⚪ Sin fecha"]
                _est_fil  = st.selectbox("Estado", _est_opts, key="venc_est_fil")
            with _fl2:
                _prods_v  = ["Todos"] + sorted(df_lotes["producto"].dropna().unique().tolist())
                _prod_fil = st.selectbox("Producto", _prods_v, key="venc_prod_fil")
            with _fl3:
                _dias_max = st.number_input("Mostrar vencimientos en próximos N días (0 = todos)",
                                            min_value=0, value=365, step=30, key="venc_dias_max")

            df_v = df_lotes.copy()
            if _est_fil != "Todos":
                df_v = df_v[df_v["Estado"] == _est_fil]
            if _prod_fil != "Todos":
                df_v = df_v[df_v["producto"] == _prod_fil]
            if _dias_max > 0:
                df_v = df_v[(df_v["dias"].isna()) | (df_v["dias"] <= _dias_max)]

            df_v = df_v.sort_values("dias", na_position="last")

            st.caption(f"Mostrando {len(df_v):,} lotes")

            # ── Vista agrupada por Producto ───────────────────────────────────
            _vista = st.radio("Vista", ["Por Lote (detalle)", "Por Producto (resumen)"],
                              horizontal=True, key="venc_vista")

            if _vista == "Por Producto (resumen)":
                _grp = (df_v.groupby(["producto", "unidad"])
                        .agg(
                            Lotes=("lote", "count"),
                            Stock_Total=("stock", "sum"),
                            Vencido=("dias", lambda x: int((x < 0).sum())),
                            Critico=("dias", lambda x: int(((x >= 0) & (x < 30)).sum())),
                            Proximo=("dias", lambda x: int(((x >= 30) & (x < 90)).sum())),
                            Venc_Minima=("dias", "min"),
                        )
                        .reset_index()
                        .rename(columns={
                            "producto": "Producto", "unidad": "Unidad",
                            "Stock_Total": "Stock Total", "Venc_Minima": "Días al próximo venc."
                        }))

                def _sem_row(row):
                    if row["Vencido"] > 0:   return "🔴 Tiene vencidos"
                    if row["Critico"] > 0:   return "🟠 Crítico"
                    if row["Proximo"] > 0:   return "🟡 Próximo"
                    return "🟢 OK"

                _grp["Estado General"] = _grp.apply(_sem_row, axis=1)
                _grp = _grp.sort_values("Días al próximo venc.", na_position="last")

                st.dataframe(
                    _grp[["Producto","Unidad","Lotes","Stock Total",
                           "Vencido","Critico","Proximo","Días al próximo venc.","Estado General"]],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Stock Total":              st.column_config.NumberColumn(format="%.1f"),
                        "Días al próximo venc.":    st.column_config.NumberColumn(format="%d"),
                    }
                )
                st.download_button("📥 Exportar resumen (.xlsx)",
                                   data=to_excel_bytes(_grp, "Resumen_Vencimientos"),
                                   file_name=f"venc_resumen_{datetime.now().strftime('%Y%m%d')}.xlsx")

            else:  # Detalle por lote
                _show = df_v[["producto","unidad","deposito","lote","stock",
                               "fecha_vencimiento","fecha_fabricacion","dias","Estado"]].rename(columns={
                    "producto":"Producto","unidad":"Unidad","deposito":"Depósito",
                    "lote":"Lote","stock":"Stock","fecha_vencimiento":"Vence",
                    "fecha_fabricacion":"Fabricación","dias":"Días restantes","Estado":"Estado"
                })
                st.dataframe(
                    _show,
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Stock":           st.column_config.NumberColumn(format="%.2f"),
                        "Días restantes":  st.column_config.NumberColumn(format="%d"),
                    }
                )
                st.download_button("📥 Exportar detalle (.xlsx)",
                                   data=to_excel_bytes(_show, "Detalle_Lotes"),
                                   file_name=f"venc_detalle_{datetime.now().strftime('%Y%m%d')}.xlsx")

            # ── Exportar lotes vencidos para baja ────────────────────────────
            _lv_para_baja = df_v[df_v["Estado"] == "🔴 Vencido"].copy()
            if not _lv_para_baja.empty:
                st.markdown("---")
                st.warning(f"**{len(_lv_para_baja)} lotes vencidos** con stock total "
                           f"{_lv_para_baja['stock'].sum():,.1f} unidades.")
                st.download_button("📋 Exportar lotes vencidos para gestión de baja",
                                   data=generar_venc_excel_baja(_lv_para_baja),
                                   file_name=f"lotes_vencidos_{datetime.now().strftime('%Y%m%d')}.xlsx")

            # ── QR por lote ───────────────────────────────────────────────────
            st.markdown("---")
            with st.expander("🏷️ Generar QR de lote", expanded=False):
                _qr_cols = st.columns(4)
                with _qr_cols[0]:
                    _qr_prod = st.selectbox("Producto", sorted(df_lotes["producto"].dropna().unique()),
                                            key="qr_prod")
                _lotes_del_prod = df_lotes[df_lotes["producto"] == _qr_prod]
                with _qr_cols[1]:
                    _qr_lote = st.selectbox("Lote", _lotes_del_prod["lote"].fillna("S/L").unique(),
                                            key="qr_lote")
                with _qr_cols[2]:
                    _qr_dep  = st.text_input("Depósito", key="qr_dep")
                with _qr_cols[3]:
                    _qr_row  = _lotes_del_prod[_lotes_del_prod["lote"] == _qr_lote]
                    _qr_venc = _qr_row["fecha_vencimiento"].iloc[0] if not _qr_row.empty else ""
                    st.text_input("Vencimiento", value=str(_qr_venc), disabled=True, key="qr_venc_disp")
                if st.button("📲 Generar QR", key="btn_qr_lote"):
                    _qr_bytes = generar_qr_lote(_qr_prod, _qr_lote, str(_qr_venc), _qr_dep)
                    if _qr_bytes:
                        st.image(_qr_bytes, width=200, caption=f"{_qr_prod} · {_qr_lote}")
                        st.download_button("⬇️ Descargar QR (.png)", data=_qr_bytes,
                                           file_name=f"qr_{_qr_lote}.png", mime="image/png")
                    else:
                        st.info("Instalá `qrcode` para usar esta función: `pip install qrcode[pil]`")

            # ── Timeline de vencimientos ──────────────────────────────────────
            st.markdown("---")
            st.write("#### 📅 Timeline: Stock que vence por mes")
            _tl = generar_vencimientos_timeline()
            if not _tl.empty:
                _hoy_mes = datetime.now().strftime("%Y-%m")
                _tl_fut  = _tl[_tl["Mes"] >= _hoy_mes]
                _tl_grp  = _tl_fut.groupby("Mes")["Stock"].sum().reset_index()
                if not _tl_grp.empty:
                    _fig_tl = px.bar(_tl_grp, x="Mes", y="Stock",
                                     title="Unidades que vencen por mes (próximos meses)",
                                     color="Stock",
                                     color_continuous_scale=["#28a745","#ffc107","#dc3545"],
                                     labels={"Stock":"Unidades","Mes":"Mes"})
                    _fig_tl.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0),
                                          showlegend=False)
                    st.plotly_chart(_fig_tl, use_container_width=True)

                    # Top productos que más vencen en próximos 90d
                    _90d = datetime.now()
                    _tl_90 = _tl_fut[_tl_fut["Mes"] <= (_90d.replace(month=min(_90d.month+3,12)
                                                         ).strftime("%Y-%m"))]
                    if not _tl_90.empty:
                        _top_venc = (_tl_90.groupby("Producto")["Stock"].sum()
                                     .reset_index().sort_values("Stock", ascending=False).head(10))
                        st.caption("**Top 10 productos con más stock venciendo en 90 días:**")
                        st.dataframe(_top_venc, use_container_width=True, hide_index=True)

            # ── Conciliación Sistema vs Lotes ─────────────────────────────────
            st.markdown("---")
            with st.expander("⚖️ Conciliación: Stock Sistema vs Lotes Importados", expanded=False):
                st.caption("Compara el stock calculado por movimientos contra la suma de lotes de MacroGest.")
                _conc = conciliar_stock_vs_lotes()
                if _conc.empty:
                    st.info("Necesitás tener stock y lotes importados para ver la conciliación.")
                else:
                    _cc1, _cc2, _cc3 = st.columns(3)
                    _cc1.metric("Productos coinciden", int((_conc["Estado"] == "✅ Coincide").sum()))
                    _cc2.metric("Sobrante en sistema", int((_conc["Estado"] == "📈 Sobrante en sistema").sum()))
                    _cc3.metric("Faltante en sistema", int((_conc["Estado"] == "📉 Faltante en sistema").sum()))
                    _conc_fil = st.radio("Filtrar", ["Todos","Solo diferencias"],
                                         horizontal=True, key="conc_fil")
                    _df_conc_show = (_conc if _conc_fil == "Todos"
                                     else _conc[_conc["Estado"] != "✅ Coincide"])
                    st.dataframe(
                        _df_conc_show.rename(columns={
                            "Stock Sistema":"Sistema","Stock Lotes":"Lotes"
                        }),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Sistema":    st.column_config.NumberColumn(format="%.2f"),
                            "Lotes":      st.column_config.NumberColumn(format="%.2f"),
                            "Diferencia": st.column_config.NumberColumn(format="%.2f"),
                        }
                    )
                    st.download_button("📥 Exportar conciliación (.xlsx)",
                                       data=to_excel_bytes(_conc, "Conciliacion"),
                                       file_name=f"conciliacion_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # ── Resumen Ejecutivo ─────────────────────────────────────────────────────
    with r_tab5:
        st.write("### 📊 Resumen Ejecutivo")
        st.caption(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · La Clementina S.A.")
        _re_stock = obtener_stock_con_compromisos()
        _re_ent   = obtener_entregas()
        _re_mg    = obtener_entregas("MACROGEST")
        _re_U     = st.session_state.umbral_alerta

        if not _re_stock.empty:
            # KPIs principales
            st.markdown("#### 📦 Stock")
            _ek1,_ek2,_ek3,_ek4,_ek5,_ek6 = st.columns(6)
            with _ek1: st.metric("Productos",     _re_stock["Producto"].nunique())
            with _ek2: st.metric("Depósitos",     _re_stock["Deposito"].nunique())
            with _ek3: st.metric("Vol. Total",    f"{_re_stock['Stock Actual'].sum():,.0f}")
            with _ek4: st.metric("Bajo umbral 🟡", int((_re_stock["Stock Actual"].between(0, _re_U, inclusive="left")).sum()))
            with _ek5: st.metric("Negativo 🔴",   int((_re_stock["Stock Actual"] < 0).sum()))
            with _ek6: st.metric("Comprometido 🟠", int((_re_stock["Disponible Neto"] < 0).sum()))

            # Stock crítico
            _crit = _re_stock[_re_stock["Stock Actual"] < _re_U].sort_values("Stock Actual").head(10)
            if not _crit.empty:
                st.markdown("**🚨 Productos críticos (bajo umbral o negativos)**")
                st.dataframe(_crit[["Producto","Deposito","Stock Actual","Comprometido","Disponible Neto"]],
                             use_container_width=True, hide_index=True)

        if not _re_ent.empty:
            st.markdown("---")
            st.markdown("#### 📋 Entregas")
            _ee_pend = _re_ent[_re_ent["pendiente"] > 0]
            _ee_dias = (_ee_pend["dia_recibido"].apply(dias_desde)
                        if "dia_recibido" in _ee_pend.columns
                        else pd.Series(0, index=_ee_pend.index))
            _ee1,_ee2,_ee3,_ee4 = st.columns(4)
            with _ee1: st.metric("Registros pendientes", len(_ee_pend))
            with _ee2: st.metric("Clientes",             _ee_pend["cliente"].nunique())
            with _ee3: st.metric("Vol. pendiente",       f"{_ee_pend['pendiente'].sum():,.0f}")
            with _ee4: st.metric("+30 días ⏳",           int((_ee_dias > 30).sum()))

        if not _re_mg.empty:
            st.markdown("---")
            st.markdown("#### 🔄 Sin Entregar MacroGest")
            _em_pend = _re_mg[_re_mg["pendiente"] > 0]
            _em1,_em2,_em3 = st.columns(3)
            with _em1: st.metric("Pedidos pendientes", len(_em_pend))
            with _em2: st.metric("Clientes",           _em_pend["cliente"].nunique())
            with _em3: st.metric("Vol. pendiente",     f"{_em_pend['pendiente'].sum():,.0f}")

        # Descarga todo en un solo Excel + PDF
        st.markdown("---")
        _dej1, _dej2 = st.columns(2)
        with _dej1:
            if st.button("📥 Excel Ejecutivo (.xlsx)", type="primary"):
                _out_ej = io.BytesIO()
                with pd.ExcelWriter(_out_ej, engine="openpyxl") as _w:
                    if not _re_stock.empty:
                        _re_stock.to_excel(_w, index=False, sheet_name="Stock_Actual")
                        _crit_all = _re_stock[_re_stock["Stock Actual"] < _re_U]
                        if not _crit_all.empty:
                            _crit_all.to_excel(_w, index=False, sheet_name="Stock_Critico")
                    if not _re_ent.empty:
                        _re_ent[_re_ent["pendiente"] > 0].to_excel(_w, index=False, sheet_name="Entregas_Pendientes")
                    if not _re_mg.empty:
                        _re_mg[_re_mg["pendiente"] > 0].to_excel(_w, index=False, sheet_name="SinEntregar_MG")
                    _kpi_ej = pd.DataFrame({
                        "Indicador": ["Fecha","Productos","Depósitos","Stock Negativo","Bajo Umbral",
                                      "Pendientes Entregas","Pendientes MG"],
                        "Valor": [
                            datetime.now().strftime("%d/%m/%Y %H:%M"),
                            _re_stock["Producto"].nunique() if not _re_stock.empty else 0,
                            _re_stock["Deposito"].nunique() if not _re_stock.empty else 0,
                            int((_re_stock["Stock Actual"] < 0).sum()) if not _re_stock.empty else 0,
                            int((_re_stock["Stock Actual"].between(0,_re_U,inclusive="left")).sum()) if not _re_stock.empty else 0,
                            len(_re_ent[_re_ent["pendiente"]>0]) if not _re_ent.empty else 0,
                            len(_re_mg[_re_mg["pendiente"]>0])  if not _re_mg.empty  else 0,
                        ]
                    })
                    _kpi_ej.to_excel(_w, index=False, sheet_name="KPIs")
                st.download_button("⬇️ Descargar Excel",
                                   data=_out_ej.getvalue(),
                                   file_name=f"ejecutivo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with _dej2:
            if PDF_AVAILABLE:
                if st.button("📄 PDF Ejecutivo con Logo LC"):
                    _pdf_ej = generar_ejecutivo_pdf()
                    if _pdf_ej:
                        st.download_button("⬇️ Descargar PDF",
                                           data=_pdf_ej,
                                           file_name=f"ejecutivo_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                           mime="application/pdf")
            else:
                st.caption("PDF: `pip install reportlab`")

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

    # ── Stock Inmovilizado ────────────────────────────────────────────────────
    with r_tab6:
        st.write("### ⏸️ Stock Inmovilizado")
        st.caption("Productos sin ningún movimiento de salida en los últimos N días. Stock que no rota y ocupa espacio o genera costo financiero.")
        _dias_inm = st.slider("Días sin movimiento", min_value=30, max_value=365, value=90, step=15,
                               help="Período de análisis: si un producto no tuvo salidas en estos días, se considera inmovilizado.")
        _hist_inm = obtener_historial_movimientos()
        _stk_inm  = obtener_stock_full()
        if _hist_inm.empty or _stk_inm.empty:
            st.info("Sin datos suficientes para el análisis.")
        else:
            def _parse_dt_inm(s):
                try: return datetime.strptime(str(s)[:10], "%d/%m/%Y")
                except: return None
            _hist_sal = _hist_inm[(_hist_inm["Tipo"] == "Salida") & (_hist_inm["Anulado"] == 0)].copy()
            _hist_sal["_dt"] = _hist_sal["Fecha"].apply(_parse_dt_inm)
            _corte = datetime.now() - timedelta(days=_dias_inm)
            _recientes = set(
                _hist_sal[_hist_sal["_dt"] >= _corte]["Producto"].unique()
            )
            _todos_prods = set(_stk_inm["Producto"].unique())
            _inmovilizados = _todos_prods - _recientes
            _stk_inm_f = _stk_inm[_stk_inm["Producto"].isin(_inmovilizados)].copy()
            _stk_inm_f = _stk_inm_f.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()

            # Última salida por producto
            _ult_sal = (
                _hist_sal.groupby("Producto")["_dt"].max().reset_index()
                .rename(columns={"_dt":"Última Salida"})
            )
            _ult_sal["Última Salida"] = _ult_sal["Última Salida"].apply(
                lambda d: d.strftime("%d/%m/%Y") if d else "Sin salidas"
            )
            _stk_inm_f = _stk_inm_f.merge(_ult_sal, on="Producto", how="left")
            _stk_inm_f["Última Salida"] = _stk_inm_f["Última Salida"].fillna("Sin salidas")

            _in1, _in2, _in3 = st.columns(3)
            _in1.metric("Productos inmovilizados", len(_stk_inm_f))
            _in2.metric("% del catálogo",
                        f"{len(_stk_inm_f)/max(1,len(_todos_prods))*100:.1f}%")
            _in3.metric("Stock total inmovilizado",
                        f"{_stk_inm_f['Stock Actual'].sum():,.0f}")

            if not _stk_inm_f.empty:
                fig_inm = px.bar(
                    _stk_inm_f.sort_values("Stock Actual", ascending=False).head(20),
                    x="Producto", y="Stock Actual",
                    title=f"Top 20 — Productos sin salidas en {_dias_inm} días",
                    color="Stock Actual",
                    color_continuous_scale=["#28a745","#ffc107","#dc3545"],
                    labels={"Stock Actual":"Stock"}
                )
                fig_inm.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0),
                                       xaxis_tickangle=-40, showlegend=False)
                st.plotly_chart(fig_inm, use_container_width=True)
                st.dataframe(
                    _stk_inm_f.sort_values("Stock Actual", ascending=False)
                    .rename(columns={"Stock Actual":"Stock"}),
                    use_container_width=True, hide_index=True
                )
                st.download_button("📥 Exportar Inmovilizado (.xlsx)",
                                   data=to_excel_bytes(_stk_inm_f, "Inmovilizado"),
                                   file_name=f"inmovilizado_{datetime.now().strftime('%Y%m%d')}.xlsx")
            else:
                st.success(f"✅ Todos los productos tuvieron movimientos en los últimos {_dias_inm} días.")

    # ── Eficiencia de Entregas ────────────────────────────────────────────────
    with r_tab7:
        st.write("### ⚡ Eficiencia de Entregas")
        st.caption("Tiempo promedio entre la fecha de recepción del pedido y la confirmación de entrega, por vendedor y producto.")
        _ent_ef = obtener_entregas()
        if _ent_ef.empty:
            st.info("Sin datos de entregas.")
        else:
            _ent_conf = _ent_ef[_ent_ef.get("confirmada", pd.Series(0, index=_ent_ef.index)).fillna(0) == 1].copy() \
                        if "confirmada" in _ent_ef.columns else pd.DataFrame()

            # Global metrics
            _ef1, _ef2, _ef3, _ef4 = st.columns(4)
            _total_pend  = len(_ent_ef[_ent_ef["pendiente"] > 0])
            _prom_dias_g = _ent_ef["dia_recibido"].apply(dias_desde).mean() if "dia_recibido" in _ent_ef.columns else 0
            _ef1.metric("Registros activos", len(_ent_ef))
            _ef2.metric("Pendientes de entrega", _total_pend)
            _ef3.metric("Días prom. en espera", f"{_prom_dias_g:.1f}")
            _ef4.metric("Confirmadas",
                        len(_ent_conf) if not _ent_conf.empty else "—")

            st.markdown("---")
            # Tiempo en cola por vendedor
            if "vendedor" in _ent_ef.columns and "dia_recibido" in _ent_ef.columns:
                _ent_ef["dias_espera"] = _ent_ef["dia_recibido"].apply(dias_desde)
                _id_col_ef = "rto" if "rto" in _ent_ef.columns else "pendiente"
                _by_vend = (_ent_ef[_ent_ef["pendiente"] > 0]
                            .groupby("vendedor")
                            .agg(Pedidos=(_id_col_ef,"nunique"),
                                 Volumen=("pendiente","sum"),
                                 DiasPromedio=("dias_espera","mean"))
                            .reset_index().sort_values("DiasPromedio", ascending=False))
                if not _by_vend.empty:
                    st.write("#### Por Vendedor")
                    fig_vend_ef = px.bar(
                        _by_vend, x="vendedor", y="DiasPromedio",
                        color="DiasPromedio",
                        color_continuous_scale=["#28a745","#ffc107","#dc3545"],
                        labels={"DiasPromedio":"Días promedio","vendedor":"Vendedor"},
                        title="Días promedio en cola por vendedor"
                    )
                    fig_vend_ef.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0), showlegend=False)
                    st.plotly_chart(fig_vend_ef, use_container_width=True)
                    st.dataframe(
                        _by_vend.rename(columns={"vendedor":"Vendedor","DiasPromedio":"Días Prom."}),
                        use_container_width=True, hide_index=True
                    )

            # Por producto
            if "producto" in _ent_ef.columns and "dia_recibido" in _ent_ef.columns:
                _by_prod_ef = (_ent_ef[_ent_ef["pendiente"] > 0]
                               .groupby("producto")
                               .agg(Pedidos=(_id_col_ef,"nunique"),
                                    Volumen=("pendiente","sum"),
                                    DiasPromedio=("dias_espera","mean"))
                               .reset_index().sort_values("Volumen", ascending=False).head(15))
                if not _by_prod_ef.empty:
                    st.write("#### Por Producto (top 15 por volumen pendiente)")
                    st.dataframe(
                        _by_prod_ef.rename(columns={"producto":"Producto","DiasPromedio":"Días Prom."}),
                        use_container_width=True, hide_index=True
                    )
                    st.download_button("📥 Exportar eficiencia (.xlsx)",
                                       data=to_excel_bytes(_by_prod_ef, "Eficiencia"),
                                       file_name=f"eficiencia_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # ── Ranking de Clientes ───────────────────────────────────────────────────
    with r_tab8:
        st.write("### 🏆 Ranking de Clientes")
        st.caption("Clientes ordenados por volumen total pedido, cantidad de remitos y balance pendiente.")
        _ent_rk = obtener_entregas()
        if _ent_rk.empty:
            st.info("Sin datos de entregas.")
        else:
            # Columnas presentes en el DataFrame
            _agg_rk = {"Pendiente": ("pendiente", "sum")}
            if "rto"      in _ent_rk.columns: _agg_rk["Remitos"]  = ("rto",      "nunique")
            if "cantidad" in _ent_rk.columns: _agg_rk["Vol. Total"] = ("cantidad", "sum")
            if "producto" in _ent_rk.columns: _agg_rk["Productos"] = ("producto", "nunique")
            _rk = (_ent_rk.groupby("cliente")
                   .agg(**_agg_rk)
                   .reset_index()
                   .rename(columns={"cliente": "Cliente"})
                   .sort_values("Pendiente", ascending=False)
                   .reset_index(drop=True))
            _rk.index = _rk.index + 1  # ranking 1-based

            _rk_top = _rk.head(5)
            st.markdown("**Top 5 clientes por pendiente**")
            _rc = st.columns(min(5, len(_rk_top)))
            for _ci, _row in enumerate(_rk_top.itertuples()):
                _val_lbl = f"{_row.Pendiente:,.0f}"
                _sub_lbl = f"{_row.Remitos} remitos" if hasattr(_row, "Remitos") else ""
                _rc[_ci].metric(f"#{_ci+1} {str(_row.Cliente)[:15]}", _val_lbl, _sub_lbl)

            st.markdown("---")
            _n_rk   = st.slider("Mostrar top N clientes", 10, 100, 25, key="rk_n")
            _y_col  = "Vol. Total" if "Vol. Total" in _rk.columns else "Pendiente"
            fig_rk  = px.bar(
                _rk.head(_n_rk),
                x="Cliente", y=_y_col,
                color="Pendiente",
                color_continuous_scale=["#3D4E6B","#F5A800","#dc3545"],
                title=f"Top {_n_rk} clientes"
            )
            fig_rk.update_layout(height=380, margin=dict(l=0,r=0,t=40,b=0), xaxis_tickangle=-40)
            st.plotly_chart(fig_rk, use_container_width=True)
            st.dataframe(_rk.head(_n_rk), use_container_width=True)
            st.download_button("📥 Exportar ranking (.xlsx)",
                               data=to_excel_bytes(_rk, "Ranking_Clientes"),
                               file_name=f"ranking_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # ── Proyección de Quiebre de Stock ────────────────────────────────────────
    with r_tab9:
        st.write("### 📉 Proyección de Quiebre de Stock")
        st.caption("Estima cuántos días quedan de stock por producto según el ritmo de salidas de los últimos 30 días.")
        _hist_qb = obtener_historial_movimientos()
        _stk_qb  = obtener_stock_full()
        if _hist_qb.empty or _stk_qb.empty:
            st.info("Sin datos suficientes para calcular proyección.")
        else:
            _hoy_qb = datetime.now()
            def _parse_fecha_qb(s):
                try:
                    return datetime.strptime(str(s).strip()[:16], "%d/%m/%Y %H:%M")
                except Exception:
                    try: return datetime.strptime(str(s).strip()[:10], "%d/%m/%Y")
                    except: return None

            _hist_qb["_dt"] = _hist_qb["Fecha"].apply(_parse_fecha_qb)
            _desde30 = _hoy_qb - timedelta(days=30)
            _sal30 = _hist_qb[
                (_hist_qb["Tipo"] == "Salida") &
                (_hist_qb["Anulado"] == 0) &
                (_hist_qb["_dt"].notna()) &
                (_hist_qb["_dt"] >= _desde30)
            ].groupby("Producto")["Cantidad"].sum().reset_index()
            _sal30.columns = ["Producto", "Salidas_30d"]
            _sal30["Tasa_Diaria"] = (_sal30["Salidas_30d"] / 30).round(3)

            _stk_tot = _stk_qb.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()
            _df_qb = _stk_tot.merge(_sal30, on="Producto", how="left").fillna(0)
            _df_qb["Días_Quiebre"] = _df_qb.apply(
                lambda r: round(r["Stock Actual"] / r["Tasa_Diaria"]) if r["Tasa_Diaria"] > 0 else None, axis=1
            )

            def _sem_qb(d):
                if d is None: return "⚪ Sin movimiento"
                if d < 15:    return "🔴 Crítico (<15d)"
                if d < 30:    return "🟡 Atención (15-30d)"
                return "🟢 OK (>30d)"

            _df_qb["Estado"] = _df_qb["Días_Quiebre"].apply(_sem_qb)
            _df_qb = _df_qb[_df_qb["Salidas_30d"] > 0].sort_values(
                "Días_Quiebre", ascending=True, na_position="last"
            )

            _qb1, _qb2, _qb3 = st.columns(3)
            _qb1.metric("🔴 Críticos (<15d)",    int((_df_qb["Estado"]=="🔴 Crítico (<15d)").sum()))
            _qb2.metric("🟡 Atención (15-30d)",  int((_df_qb["Estado"]=="🟡 Atención (15-30d)").sum()))
            _qb3.metric("🟢 OK",                 int((_df_qb["Estado"]=="🟢 OK (>30d)").sum()))

            st.dataframe(
                _df_qb[["Estado","Producto","Unidad","Stock Actual","Tasa_Diaria","Días_Quiebre"]]
                .rename(columns={"Stock Actual":"Stock","Tasa_Diaria":"Sal/día","Días_Quiebre":"Días al quiebre"}),
                use_container_width=True, hide_index=True
            )
            st.download_button("📥 Exportar proyección (.xlsx)",
                               data=to_excel_bytes(_df_qb, "Proyeccion_Quiebre"),
                               file_name=f"proyeccion_quiebre_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # ── Clientes Sin Actividad ────────────────────────────────────────────────
    with r_tab10:
        st.write("### 😴 Clientes Sin Actividad")
        st.caption(
            "Clientes con historial en La Clementina (LA CLEMENTINA S.A) "
            "que NO tienen pedidos en la campaña actual (MACROGEST)."
        )
        _ent_all_cs = obtener_entregas()
        if _ent_all_cs.empty:
            st.info("Sin datos de entregas.")
        else:
            _cli_hist = set(
                _ent_all_cs[_ent_all_cs["hoja"]=="LA CLEMENTINA S.A"]["cliente"].dropna().unique()
            )
            _cli_mg   = set(
                _ent_all_cs[_ent_all_cs["hoja"]=="MACROGEST"]["cliente"].dropna().unique()
            )
            _cli_sin  = _cli_hist - _cli_mg

            if not _cli_sin:
                st.success("Todos los clientes históricos tienen al menos un pedido en MacroGest.")
            else:
                _df_hist_lc = _ent_all_cs[
                    (_ent_all_cs["hoja"]=="LA CLEMENTINA S.A") &
                    (_ent_all_cs["cliente"].isin(_cli_sin))
                ]
                _agg_cs = _df_hist_lc.groupby("cliente").agg(
                    Ultima_Compra=("dia_recibido", "max"),
                    Total_Comprado=("cantidad_comprada", "sum"),
                    Registros=("id_entrega", "count"),
                ).reset_index().rename(columns={
                    "cliente":"Cliente",
                    "Ultima_Compra":"Última Compra",
                    "Total_Comprado":"Total Comprado",
                }).sort_values("Última Compra", ascending=False)

                st.metric("Clientes sin actividad en campaña actual", len(_agg_cs))
                st.dataframe(_agg_cs, use_container_width=True, hide_index=True)
                st.download_button(
                    "📥 Exportar clientes sin actividad (.xlsx)",
                    data=to_excel_bytes(_agg_cs, "Clientes_Sin_Actividad"),
                    file_name=f"clientes_sin_actividad_{datetime.now().strftime('%Y%m%d')}.xlsx"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 9 — CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════
with tab9:
    st.subheader("⚙️ Configuración")
    cfg1, cfg2, cfg3, cfg4 = st.tabs([
        "📥 Importación / Exportación", "🔧 Parámetros & Sistema",
        "⚙️ Config JSON", "📋 Changelog"
    ])

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
            if arch_s:
                # Verificar duplicado por hash del archivo
                _file_bytes = arch_s.read(); arch_s.seek(0)
                _file_hash  = hashlib.sha1(_file_bytes).hexdigest()[:12]
                _hash_prev  = obtener_metadata("ultimo_hash_stock")
                if _hash_prev == _file_hash:
                    st.warning(f"⚠️ Este archivo ya fue importado anteriormente (hash: `{_file_hash}`). "
                               "Podés igualmente importarlo de nuevo si querés actualizar.")
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
                    guardar_metadata("ultimo_hash_stock", _file_hash)
                    registrar_importacion_log("Stock Completo", arch_s.name, mo, _file_hash)
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

        # ── Importación Lotes + Vencimientos ──────────────────────────────────
        with st.expander("📦 Importar Lotes y Vencimientos (MacroGest)", expanded=False):
            st.info(
                "Subí el archivo de MacroGest con columnas: `codigo`, `descripcion_1`, "
                "`unidad_medida`, `deposito`, `serie` (lote), `antidad` (stock), "
                "`lote_vencimiento`, `lote_fabricacion`. "
                "**Reemplaza todos los lotes activos anteriores.**"
            )
            _df_lv_prev = obtener_lotes_vencimiento()
            if not _df_lv_prev.empty:
                st.caption(f"Actualmente: {len(_df_lv_prev):,} lotes cargados · "
                           f"última importación: {_df_lv_prev['fecha_importacion'].iloc[0] if 'fecha_importacion' in _df_lv_prev.columns else '—'}")

            arch_lv = st.file_uploader("Archivo de lotes (.xlsx / .xls / .csv)",
                                       type=["xlsx","xls","csv"], key="up_lotes_venc")
            if arch_lv:
                try:
                    _df_lv = (pd.read_excel(arch_lv) if not arch_lv.name.endswith(".csv")
                              else pd.read_csv(arch_lv))
                    arch_lv.seek(0)
                    _lv_col_venc = next((c for c in _df_lv.columns
                                        if "vencimiento" in str(c).lower() and "muestra" not in str(c).lower()), None)
                    _lv_con_v = int(_df_lv[_lv_col_venc].notna().sum()) if _lv_col_venc else 0
                    st.caption(f"📋 {len(_df_lv):,} filas · {_df_lv['descripcion_1'].nunique() if 'descripcion_1' in _df_lv.columns else '?'} productos · "
                               f"{_lv_con_v:,} lotes con fecha de vencimiento")
                    if st.button("🚀 IMPORTAR LOTES", type="primary", key="btn_imp_lotes"):
                        _prog_lv = st.progress(0, "Procesando...")
                        try:
                            arch_lv.seek(0)
                            _df_lv2 = (pd.read_excel(arch_lv) if not arch_lv.name.endswith(".csv")
                                       else pd.read_csv(arch_lv))
                            _prog_lv.progress(30, "Importando lotes...")
                            _tot, _cv = importar_lotes_vencimiento(_df_lv2)
                            _prog_lv.progress(100, "¡Listo!")
                            registrar_importacion_log("Lotes/Vencimientos", arch_lv.name, _tot)
                            limpiar_cache()
                            st.success(f"✅ {_tot:,} lotes importados · {_cv:,} con fecha de vencimiento.")
                            st.rerun()
                        except Exception as _ex_lv:
                            _prog_lv.empty()
                            st.error(f"Error: {_ex_lv}")
                except Exception as _ex_prev:
                    st.error(f"No se pudo leer el archivo: {_ex_prev}")

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
        new_umbral = st.number_input("Umbral de Stock Bajo (global)", min_value=1,
                                     value=int(st.session_state.umbral_alerta),
                                     help="Nivel de stock a partir del cual se dispara la alerta amarilla (global).")
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
        st.write("### 📊 Stock Mínimo por Producto")
        st.caption("Definí el stock mínimo individual de cada producto. Si es 0, se usa el umbral global.")
        _prod_cfg = obtener_productos_completo()
        if _prod_cfg.empty:
            st.info("Sin productos cargados.")
        else:
            _cols_sm = ["nombre","stock_minimo"] if "stock_minimo" in _prod_cfg.columns else ["nombre"]
            _df_sm = _prod_cfg[_cols_sm].copy().rename(columns={"nombre":"Producto","stock_minimo":"Stock Mínimo"})
            if "Stock Mínimo" not in _df_sm.columns:
                _df_sm["Stock Mínimo"] = 0.0
            _edited_sm = st.data_editor(
                _df_sm,
                column_config={
                    "Producto":      st.column_config.TextColumn("Producto", disabled=True),
                    "Stock Mínimo":  st.column_config.NumberColumn("Stock Mínimo", min_value=0.0, format="%.0f",
                                     help="0 = usar umbral global"),
                },
                hide_index=True, use_container_width=True, key="editor_stock_min"
            )
            if st.button("💾 Guardar Stocks Mínimos", type="primary", key="save_stock_min"):
                _conn_sm = conectar_db()
                for _, _r in _edited_sm.iterrows():
                    try:
                        _conn_sm.execute(
                            "UPDATE productos SET stock_minimo=? WHERE nombre=?",
                            (float(_r["Stock Mínimo"]), _r["Producto"])
                        )
                    except: pass
                _conn_sm.commit(); _conn_sm.close()
                limpiar_cache()
                st.success("✅ Stocks mínimos guardados.")
                st.rerun()

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
        col_b1, col_b2, col_b3 = st.columns(3)
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
        with col_b3:
            _bk = backup_db_bytes()
            if _bk:
                st.download_button("💾 Backup DB (.sqlite)",
                                   data=_bk,
                                   file_name=f"backup_lc_{datetime.now().strftime('%Y%m%d_%H%M')}.sqlite",
                                   help="Descarga una copia completa de la base de datos local",
                                   use_container_width=True)
            else:
                st.caption("Backup disponible solo en modo local (SQLite).")

        # ── Historial de Importaciones ────────────────────────────────────────
        st.markdown("---")
        st.write("### 📋 Historial de Importaciones")
        st.caption("Registro automático de cada importación realizada en la app.")
        conn_log = conectar_db()
        df_log = _rsql("""SELECT fecha_hora "Fecha", tipo "Tipo", archivo "Archivo",
                                  filas "Filas", usuario "Usuario", resultado "Resultado"
                           FROM importaciones_log ORDER BY id_log DESC LIMIT 100""", conn_log)
        conn_log.close()
        if df_log.empty:
            st.info("Sin importaciones registradas aún.")
        else:
            st.dataframe(df_log, use_container_width=True, hide_index=True)
            st.download_button("📥 Exportar log (.xlsx)",
                               data=to_excel_bytes(df_log, "Log_Importaciones"),
                               file_name="log_importaciones.xlsx")

        # ── Historial de Remitos ───────────────────────────────────────────────
        st.markdown("---")
        st.write("### 🖨️ Historial de Remitos")
        conn_rem = conectar_db()
        df_rem_log = _rsql("""SELECT numero "Nro", fecha_hora "Fecha", tipo "Tipo",
                                      cliente "Cliente", deposito "Depósito",
                                      usuario "Usuario", observaciones "Observaciones"
                               FROM remitos ORDER BY id_remito DESC LIMIT 200""", conn_rem)
        conn_rem.close()
        if df_rem_log.empty:
            st.info("Sin remitos emitidos aún.")
        else:
            st.metric("Total remitos emitidos", len(df_rem_log))
            st.dataframe(df_rem_log, use_container_width=True, hide_index=True)
            st.download_button("📥 Exportar remitos (.xlsx)",
                               data=to_excel_bytes(df_rem_log, "Remitos"),
                               file_name=f"remitos_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # ── Config JSON ───────────────────────────────────────────────────────────
    with cfg3:
        st.write("### ⚙️ Exportar / Importar Configuración JSON")
        st.caption("Hacé backup de todos los parámetros de la app en un archivo JSON. Útil para restaurar configuración en otro equipo o luego de un reset.")

        # Exportar
        _cfg_keys = [
            "umbral_alerta","wa_numero","smtp_server","smtp_port","smtp_user",
            "email_dest","codigo_supervisor","auth_enabled",
            "ultimo_hash_stock","ultimo_hash_entregas","ultimo_hash_mg",
        ]
        _cfg_exp = {}
        for _k in _cfg_keys:
            _v = obtener_metadata(_k)
            if _v: _cfg_exp[_k] = _v
        # También metas
        _conn_cfg = conectar_db()
        _metas_cfg = _rsql("SELECT campana, vendedor, producto, meta_cantidad, meta_valor FROM metas_campana", _conn_cfg)
        _conn_cfg.close()
        if not _metas_cfg.empty:
            _cfg_exp["metas_campana"] = _metas_cfg.to_dict(orient="records")
        _json_bytes = json.dumps(_cfg_exp, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "📥 Exportar configuración (.json)",
            data=_json_bytes,
            file_name=f"config_lc_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            type="primary"
        )
        st.markdown("---")
        # Importar
        st.write("#### Importar configuración desde JSON")
        _arch_cfg = st.file_uploader("Archivo config (.json)", type=["json"], key="up_cfg_json")
        if _arch_cfg:
            try:
                _cfg_imp = json.loads(_arch_cfg.read().decode("utf-8"))
                st.json(_cfg_imp)
                if st.button("✅ Aplicar configuración", type="primary", key="btn_apply_cfg"):
                    for _k, _v in _cfg_imp.items():
                        if _k == "metas_campana":
                            continue  # no sobrescribir metas automáticamente
                        guardar_metadata(_k, str(_v))
                    # Refrescar session state
                    if "umbral_alerta" in _cfg_imp:
                        st.session_state.umbral_alerta = int(_cfg_imp["umbral_alerta"])
                    if "wa_numero" in _cfg_imp:
                        st.session_state.wa_numero = _cfg_imp["wa_numero"]
                    st.success("✅ Configuración importada correctamente.")
                    st.rerun()
            except Exception as _ex:
                st.error(f"Error leyendo JSON: {_ex}")

    # ── Changelog ─────────────────────────────────────────────────────────────
    with cfg4:
        st.write("### 📋 Changelog — Historial de Versiones")
        st.markdown("""
| Versión | Fecha | Cambios |
|---------|-------|---------|
| **v4.0 PRO** | Jul 2026 | Inventario físico masivo, devoluciones, eficiencia entregas, ranking clientes, reporte ejecutivo PDF con logo, exportación config JSON, tabs de reportes ampliados |
| **v3.5** | Jun 2026 | Reservas de stock, filtro global de depósito, comparativa campañas, WhatsApp share, changelog, importación múltiple |
| **v3.0 PRO** | Jun 2026 | Remitos correlativos (R-00001...), log de importaciones, backup SQLite, orden de compra PDF, forecast de demanda, novedades del día, tendencias mensuales, tooltips KPIs, alerta stock negativo inmediata |
| **v2.5** | May 2026 | Logo LC + colores corporativos, header profesional, remitos PDF, confirmación entregas MG con descuento stock, observaciones en movimientos, stock inmovilizado, validación duplicados |
| **v2.0** | May 2026 | Índices DB, stock mínimo por producto, semáforos, proyección, trazabilidad lote, margen bruto, paginación historial, modo oscuro |
| **v1.5** | Abr 2026 | Lista de precios separada, cache TTL 300s, LIMIT 2000 en historial, batch imports (executemany) |
| **v1.0** | Mar 2026 | Versión inicial: control de stock multi-depósito, importación MacroGest, entregas, historial, valorización |
""")
        st.markdown("---")
        st.write("#### 🔧 Estado del Sistema")
        _sys1, _sys2, _sys3, _sys4 = st.columns(4)
        _sys1.metric("Versión", "v4.0 PRO")
        _sys2.metric("PDF", "✅" if PDF_AVAILABLE else "❌")
        _sys3.metric("DB", "PostgreSQL" if IS_POSTGRES else "SQLite")
        _sys4.metric("Usuario", usuario_actual())

    st.markdown("---")
    st.caption(f"La Clementina S.A. — v4.0 PRO — "
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
@st.fragment
def _render_tab11():
    st.subheader("🔄 Pedidos Sin Entregar — MacroGest")
    st.caption("Importá el reporte de MacroGest con los pedidos pendientes de entrega. Los datos quedan guardados y se actualizan con cada importación.")

    with st.expander("📂 Importar archivo Sin Entregar", expanded=False):
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
                    registrar_importacion_log("Sin Entregar MG", arch_mg_se.name, ok_mg)
                    limpiar_cache()
                    st.success(f"✅ {ok_mg} registros importados.")
                    st.rerun()

    st.markdown("---")
    ultima_mg = obtener_metadata("ultima_importacion_mg")
    if ultima_mg:
        st.caption(f"Última importación MacroGest: **{ultima_mg}**")

    # ── Cache en session_state para velocidad máxima de filtrado ─────────────
    if "df_mg_cache" not in st.session_state or st.session_state.get("df_mg_cache") is None:
        st.session_state["df_mg_cache"] = obtener_entregas("MACROGEST")
    df_mg_stored = st.session_state["df_mg_cache"]

    _rc1, _rc2 = st.columns([8, 1])
    with _rc2:
        if st.button("🔄", key="mg_refresh", help="Actualizar datos desde la base"):
            st.session_state["df_mg_cache"] = obtener_entregas("MACROGEST")
            df_mg_stored = st.session_state["df_mg_cache"]
            st.rerun()

    if df_mg_stored is None or df_mg_stored.empty:
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

        # Filtrado ultra-rápido: máscara booleana sobre columna pre-lowercase
        if "df_mg_cli_lower" not in st.session_state or st.session_state.get("df_mg_cache_id") != id(df_mg_stored):
            st.session_state["df_mg_cli_lower"] = df_mg_stored["cliente"].fillna("").str.lower()
            st.session_state["df_mg_cache_id"]  = id(df_mg_stored)
        _cli_lower = st.session_state["df_mg_cli_lower"]

        _mask = pd.Series([True] * len(df_mg_stored), index=df_mg_stored.index)
        if f_cli_mg:
            _mask &= _filtro_fonetico(df_mg_stored["cliente"], f_cli_mg)
        if f_prod_mg != "Todos":
            _mask &= df_mg_stored["producto"] == f_prod_mg
        if f_vend_mg != "Todos":
            _mask &= df_mg_stored["vendedor"].replace("","S/V") == f_vend_mg
        if solo_pend_mg:
            _mask &= df_mg_stored["pendiente"] > 0

        df_f_mg = df_mg_stored[_mask].copy()

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

            # ── Remito PDF por Cliente ────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 📄 Remito PDF por Cliente")
            _clientes_pdf = sorted(df_f_mg["cliente"].dropna().unique().tolist()) if not df_f_mg.empty else []
            if _clientes_pdf:
                _cli_pdf = st.selectbox("Cliente para remito", _clientes_pdf, key="mg_cli_pdf")
                if st.button("📄 Generar Remito PDF", key="mg_btn_pdf"):
                    if not PDF_AVAILABLE:
                        st.warning("reportlab no está instalado. Ejecutá: pip install reportlab")
                    else:
                        _df_cli_pdf = df_f_mg[(df_f_mg["cliente"] == _cli_pdf) & (df_f_mg["pendiente"] > 0)]
                        if _df_cli_pdf.empty:
                            st.info(f"{_cli_pdf} no tiene pendientes.")
                        else:
                            _buf_r = io.BytesIO()
                            _doc_r = SimpleDocTemplate(_buf_r, pagesize=A4,
                                                       rightMargin=1.5*cm, leftMargin=1.5*cm,
                                                       topMargin=2*cm, bottomMargin=2*cm)
                            _sty_r = getSampleStyleSheet()
                            _el_r  = []
                            # Header
                            _el_r.append(Paragraph(
                                "<b>La Clementina S.A.</b> — Remito de Pendientes",
                                _sty_r["Title"]
                            ))
                            _el_r.append(Paragraph(
                                f"Cliente: <b>{_cli_pdf}</b> &nbsp;&nbsp; "
                                f"Fecha: <b>{datetime.now().strftime('%d/%m/%Y')}</b>",
                                _sty_r["Normal"]
                            ))
                            _el_r.append(Spacer(1, 0.5*cm))
                            # Tabla
                            _hdr_r = [["Producto", "Comprado", "Entregado", "Pendiente", "% Entregado"]]
                            _rows_r = []
                            for _, _rr in _df_cli_pdf.iterrows():
                                _pct_r = round(_rr["cant_entregada"] / _rr["cantidad_comprada"] * 100, 1) if _rr.get("cantidad_comprada", 0) > 0 else 0
                                _rows_r.append([
                                    str(_rr.get("producto","")),
                                    f'{_rr.get("cantidad_comprada",0):,.0f}',
                                    f'{_rr.get("cant_entregada",0):,.0f}',
                                    f'{_rr.get("pendiente",0):,.0f}',
                                    f'{_pct_r}%',
                                ])
                            _tbl_r = Table(_hdr_r + _rows_r, repeatRows=1)
                            _tbl_r.setStyle(TableStyle([
                                ("BACKGROUND",    (0,0), (-1,0),  rl_colors.HexColor("#3D4E6B")),
                                ("TEXTCOLOR",     (0,0), (-1,0),  rl_colors.white),
                                ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
                                ("FONTSIZE",      (0,0), (-1,-1), 9),
                                ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#FFF8E7")]),
                                ("GRID",          (0,0), (-1,-1), 0.5, rl_colors.grey),
                            ]))
                            _el_r.append(_tbl_r)
                            _el_r.append(Spacer(1, 1*cm))
                            _el_r.append(Paragraph(
                                "<font size=8 color=grey>La Clementina S.A. · San Jorge, Santa Fe</font>",
                                _sty_r["Normal"]
                            ))
                            _doc_r.build(_el_r)
                            st.download_button(
                                "⬇️ Descargar Remito PDF",
                                data=_buf_r.getvalue(),
                                file_name=f"remito_pendientes_{_cli_pdf.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                key="dl_rem_cli_pdf"
                            )

            # ── Comparativa por Vendedor ──────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 👤 Comparativa por Vendedor")
            st.caption("Entregado vs pendiente para cada vendedor según los filtros activos.")
            _vend_mg = df_f_mg.groupby("vendedor").agg(
                Clientes=("cliente","nunique"),
                Comprado=("cantidad_comprada","sum"),
                Entregado=("cant_entregada","sum"),
                Pendiente=("pendiente","sum"),
            ).reset_index().rename(columns={"vendedor":"Vendedor"})
            _vend_mg["% Entregado"] = (_vend_mg["Entregado"] / _vend_mg["Comprado"].replace(0,1) * 100).round(1)
            _vend_mg = _vend_mg.sort_values("Pendiente", ascending=False)
            _vg1, _vg2 = st.columns(2)
            with _vg1:
                st.dataframe(_vend_mg, use_container_width=True, hide_index=True)
            with _vg2:
                if len(_vend_mg) > 0:
                    fig_vm = px.bar(_vend_mg, x="Vendedor", y=["Entregado","Pendiente"],
                                    barmode="stack", title="Entregado vs Pendiente",
                                    color_discrete_map={"Entregado":"#28a745","Pendiente":"#dc3545"},
                                    labels={"value":"Unidades","variable":""})
                    fig_vm.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig_vm, use_container_width=True)

            # ── Tabla cruzada Cliente × Producto ─────────────────────────────
            st.markdown("---")
            with st.expander("🗂️ Tabla cruzada: Cliente × Producto (pendiente)", expanded=False):
                st.caption("Muestra cuánto le falta entregar a cada cliente por producto. Útil para planificar despachos.")
                _cross = df_f_mg[df_f_mg["pendiente"] > 0].pivot_table(
                    index="cliente", columns="producto", values="pendiente",
                    aggfunc="sum", fill_value=0
                )
                if _cross.empty:
                    st.info("Sin pendientes con los filtros actuales.")
                else:
                    _cross["TOTAL"] = _cross.sum(axis=1)
                    _cross = _cross.sort_values("TOTAL", ascending=False)
                    # Semáforo de antigüedad por cliente
                    if "dia_recibido" in df_f_mg.columns:
                        _df_pend_sem = df_f_mg[df_f_mg["pendiente"] > 0].copy()
                        _df_pend_sem["_dias_sem"] = _df_pend_sem["dia_recibido"].apply(dias_desde)
                        _max_dias = _df_pend_sem.groupby("cliente")["_dias_sem"].max()
                        def _sem_cross(d):
                            if d > 60:  return "🔴 >60d"
                            if d > 30:  return "🟡 30-60d"
                            return "🟢 ≤30d"
                        _cross["Estado"] = _cross.index.map(lambda c: _sem_cross(_max_dias.get(c, 0)))
                    st.dataframe(_cross.style.format("{:,.0f}", subset=[c for c in _cross.columns if c not in ("TOTAL","Estado")]).background_gradient(
                        cmap="Reds", subset=[c for c in _cross.columns if c not in ("TOTAL","Estado")]),
                        use_container_width=True)
                    st.download_button("📥 Exportar tabla cruzada",
                                       data=to_excel_bytes(_cross.reset_index(), "Cliente_x_Producto"),
                                       file_name=f"cruzada_{datetime.now().strftime('%Y%m%d')}.xlsx")

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
                                             help="Descuenta la cantidad del pendiente y genera movimiento en stock"):
                                    if nueva_entrega > 0:
                                        conn = conectar_db()
                                        conn.execute("""
                                            UPDATE entregas SET
                                                cant_entregada = cant_entregada + ?,
                                                pendiente = MAX(0, pendiente - ?),
                                                confirmada = 1,
                                                fecha_confirmacion = ?,
                                                usuario_confirmacion = ?
                                            WHERE hoja='MACROGEST' AND rto=?
                                        """, (nueva_entrega, nueva_entrega,
                                              datetime.now().strftime("%d/%m/%Y %H:%M"),
                                              usuario_actual(), rto_sel))
                                        # Descontar del stock
                                        _id_prod_mg = conn.execute(
                                            "SELECT id_producto FROM productos WHERE nombre=?",
                                            (r0["producto"],)
                                        ).fetchone()
                                        if _id_prod_mg:
                                            conn.execute("""INSERT INTO movimientos
                                                (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,
                                                 referencia,deposito,origen,usuario,observaciones)
                                                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                                (datetime.now().strftime("%d/%m/%Y %H:%M"), "Salida",
                                                 _id_prod_mg[0], nueva_entrega,
                                                 safe_str(r0.get("lote","S/L")) or "S/L",
                                                 f"Entrega MG pedido {rto_sel}",
                                                 safe_str(r0.get("deposito","")) or "",
                                                 "entrega_mg", usuario_actual(),
                                                 f"Cliente: {r0['cliente']}"))
                                        conn.commit()
                                        # Remito PDF
                                        _rem_mg = b""
                                        if PDF_AVAILABLE:
                                            _prod_mg_list = obtener_productos_completo()
                                            _uni_mg = ""
                                            if not _prod_mg_list.empty:
                                                _row_mg = _prod_mg_list[_prod_mg_list["nombre"]==r0["producto"]]
                                                _uni_mg = _row_mg.iloc[0]["unidad"] if not _row_mg.empty else ""
                                            _rem_mg = generar_remito_pdf(
                                                numero=f"MG-{rto_sel}",
                                                cliente=r0["cliente"],
                                                deposito=safe_str(r0.get("deposito","")),
                                                items=[{"producto":r0["producto"],"lote":safe_str(r0.get("lote","S/L")),
                                                        "cantidad":nueva_entrega,"unidad":_uni_mg}],
                                                usuario=usuario_actual(),
                                                observaciones=f"Pedido MacroGest {rto_sel}"
                                            )
                                        conn.close()
                                        limpiar_cache()
                                        st.toast(f"✅ {nueva_entrega:,.1f} unidades registradas y descontadas del stock.")
                                        if _rem_mg:
                                            st.download_button("🖨️ Descargar Remito PDF",
                                                               data=_rem_mg,
                                                               file_name=f"remito_mg_{rto_sel}.pdf",
                                                               mime="application/pdf",
                                                               key="dl_rem_mg")
                                        st.rerun()
                                    else:
                                        st.warning("Ingresá una cantidad mayor a cero.")
                            with ua2:
                                st.write("")  # spacer
                                if st.button("✅ Marcar pedido como COMPLETADO", key="mg_btn_comp",
                                             type="primary",
                                             help="Cierra el pedido poniendo pendiente=0 y estado=ENTREGADO"):
                                    conn = conectar_db()
                                    _pend_comp = float(r0.get("pendiente", 0))
                                    conn.execute("""
                                        UPDATE entregas SET pendiente=0, estado='ENTREGADO',
                                            cant_entregada=cantidad_comprada,
                                            confirmada=1, fecha_confirmacion=?, usuario_confirmacion=?
                                        WHERE hoja='MACROGEST' AND rto=?
                                    """, (datetime.now().strftime("%d/%m/%Y %H:%M"), usuario_actual(), rto_sel))
                                    # Descontar pendiente restante del stock
                                    if _pend_comp > 0:
                                        _id_pc = conn.execute(
                                            "SELECT id_producto FROM productos WHERE nombre=?",
                                            (r0["producto"],)
                                        ).fetchone()
                                        if _id_pc:
                                            conn.execute("""INSERT INTO movimientos
                                                (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,
                                                 referencia,deposito,origen,usuario,observaciones)
                                                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                                (datetime.now().strftime("%d/%m/%Y %H:%M"), "Salida",
                                                 _id_pc[0], _pend_comp,
                                                 safe_str(r0.get("lote","S/L")) or "S/L",
                                                 f"Completar MG pedido {rto_sel}",
                                                 safe_str(r0.get("deposito","")) or "",
                                                 "entrega_mg", usuario_actual(),
                                                 f"Completar entrega — Cliente: {r0['cliente']}"))
                                    conn.commit(); conn.close()
                                    limpiar_cache()
                                    st.toast(f"✅ Pedido {rto_sel} marcado como completado y stock descontado.")
                                    st.rerun()
                    else:
                        st.info("Los registros filtrados no tienen N° de pedido asignado. "
                                "Podés usar 'cliente+producto' para identificarlos.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 12 — LISTA DE PRECIOS
# ═══════════════════════════════════════════════════════════════════════════════
@st.fragment
def _render_tab12():
    st.subheader("🏷️ Lista de Precios 2026")
    st.caption("Importá la lista de precios de MacroGest. Los precios quedan guardados y se pueden mapear automáticamente al stock para valorizar el inventario.")

    # ── Importar ──────────────────────────────────────────────────────────────
    with st.expander("📂 Importar Lista de Precios (.xlsx)", expanded=False):
        arch_lp = st.file_uploader("Archivo lista de precios", type=["xlsx","xls","csv"], key="up_lista_precios")
        if arch_lp:
            try:
                _df_lp = pd.read_excel(arch_lp) if not arch_lp.name.endswith(".csv") else pd.read_csv(arch_lp)
                _df_lp.columns = [str(c).strip() for c in _df_lp.columns]
                _col_map_lp = {
                    "Rubro":"rubro","RUBRO":"rubro",
                    "Producto":"producto","PRODUCTO":"producto","Descripcion":"producto",
                    "UM":"um","Unidad":"um","U.M.":"um",
                    "Contado":"precio_contado","CONTADO":"precio_contado","Precio Contado":"precio_contado",
                    "P Vta":"precio_vta","Precio Vta":"precio_vta","P. VTA":"precio_vta","PVta":"precio_vta",
                    "Financiación":"financiacion","Financiacion":"financiacion","FINANCIACION":"financiacion",
                }
                _df_lp.rename(columns={k:v for k,v in _col_map_lp.items() if k in _df_lp.columns}, inplace=True)
                for _req in ["producto","precio_contado"]:
                    if _req not in _df_lp.columns:
                        st.error(f"Columna requerida no encontrada: `{_req}`. Columnas disponibles: {list(_df_lp.columns)}")
                        st.stop()
                _df_lp = _df_lp[_df_lp["producto"].apply(lambda x: bool(safe_str(x)))]
                _n_rub = _df_lp["rubro"].nunique() if "rubro" in _df_lp.columns else "?"
                st.markdown(f"**{len(_df_lp)} productos** · {_n_rub} rubros detectados")
                st.dataframe(_df_lp.head(15), use_container_width=True, hide_index=True)
                st.caption("Preview — primeros 15 registros")
                if st.button("✅ Confirmar importación", type="primary", key="conf_lp"):
                    _ts_lp = datetime.now().strftime("%d/%m/%Y %H:%M")
                    lp_batch = [
                        (safe_str(r.get("rubro","")), safe_str(r.get("producto","")),
                         safe_str(r.get("um","")), safe_float(r.get("precio_contado",0)),
                         safe_float(r.get("precio_vta",0)), safe_str(r.get("financiacion","")), _ts_lp)
                        for _, r in _df_lp.iterrows() if safe_str(r.get("producto",""))
                    ]
                    conn = conectar_db()
                    conn.execute("DELETE FROM lista_precios")
                    conn.cursor().executemany("""INSERT INTO lista_precios
                        (rubro,producto,um,precio_contado,precio_vta,financiacion,fecha_carga)
                        VALUES (?,?,?,?,?,?,?)""", lp_batch)
                    conn.commit(); conn.close()
                    # Registrar historial de precios
                    for _item_lp in lp_batch:
                        if _item_lp[3] > 0:  # precio_contado
                            registrar_cambio_precio(_item_lp[1], _item_lp[3], "USD", usuario_actual())
                    limpiar_cache()
                    st.success(f"✅ {len(lp_batch)} precios importados.")
                    st.rerun()
            except Exception as _ex_lp:
                st.error(f"Error: {_ex_lp}")

    # ── Datos cargados ────────────────────────────────────────────────────────
    df_lp = obtener_lista_precios()

    if df_lp.empty:
        st.info("Sin datos. Importá un archivo arriba.")
    else:
        _lp_ult = df_lp["fecha_carga"].iloc[0] if "fecha_carga" in df_lp.columns else ""
        if _lp_ult: st.caption(f"🕐 Última carga: **{_lp_ult}**")

        # KPIs
        _lk1, _lk2, _lk3, _lk4 = st.columns(4)
        with _lk1: st.metric("Productos",       len(df_lp))
        with _lk2: st.metric("Rubros",          df_lp["rubro"].nunique())
        with _lk3: st.metric("Precio mín. USD", f"{df_lp['precio_contado'].min():.2f}")
        with _lk4: st.metric("Precio máx. USD", f"{df_lp['precio_contado'].max():.2f}")

        st.markdown("---")

        # Filtros
        _lf1, _lf2, _lf3 = st.columns(3)
        with _lf1:
            rubros_lp = ["Todos"] + sorted(df_lp["rubro"].dropna().unique().tolist())
            f_rubro_lp = st.selectbox("Rubro", rubros_lp, key="f_rubro_lp")
        with _lf2:
            busq_lp = st.text_input("🔍 Buscar producto", key="busq_lp")
        with _lf3:
            orden_lp = st.selectbox("Ordenar por", ["Rubro / Producto","Mayor precio","Menor precio"], key="ord_lp")

        _lp_mask = pd.Series([True] * len(df_lp), index=df_lp.index)
        if f_rubro_lp != "Todos": _lp_mask &= df_lp["rubro"] == f_rubro_lp
        if busq_lp: _lp_mask &= df_lp["producto"].fillna("").str.lower().str.contains(busq_lp.lower(), na=False)
        df_lp_f = df_lp[_lp_mask].copy()
        if orden_lp == "Mayor precio":   df_lp_f = df_lp_f.sort_values("precio_contado", ascending=False)
        elif orden_lp == "Menor precio": df_lp_f = df_lp_f.sort_values("precio_contado", ascending=True)

        st.dataframe(
            df_lp_f[["rubro","producto","um","precio_contado","precio_vta","financiacion"]]
            .rename(columns={
                "rubro":"Rubro","producto":"Producto","um":"UM",
                "precio_contado":"Contado USD","precio_vta":"P.Vta USD","financiacion":"Financiación"
            }),
            use_container_width=True, hide_index=True
        )
        st.caption(f"Mostrando {len(df_lp_f)} de {len(df_lp)} productos")

        # Gráfico por rubro
        with st.expander("📊 Gráfico de precios por rubro", expanded=False):
            _fig_rub = px.box(
                df_lp[df_lp["precio_contado"] > 0],
                x="rubro", y="precio_contado",
                title="Distribución de precios por rubro (USD Contado)",
                color="rubro", labels={"precio_contado":"Precio USD","rubro":"Rubro"}
            )
            _fig_rub.update_layout(height=380, showlegend=False, margin=dict(l=0,r=0,t=40,b=80))
            _fig_rub.update_xaxes(tickangle=30)
            st.plotly_chart(_fig_rub, use_container_width=True)

        st.download_button("📥 Exportar lista filtrada (.xlsx)",
                           data=to_excel_bytes(
                               df_lp_f[["rubro","producto","um","precio_contado","precio_vta","financiacion"]]
                               .rename(columns={"rubro":"Rubro","producto":"Producto","um":"UM",
                                                "precio_contado":"Contado USD","precio_vta":"P.Vta USD",
                                                "financiacion":"Financiación"}),
                               "Lista_Precios"),
                           file_name=f"lista_precios_{datetime.now().strftime('%Y%m%d')}.xlsx")

        # ── Mapeo automático al stock ─────────────────────────────────────────
        st.markdown("---")
        st.write("### 🔗 Mapear precios al stock")
        st.caption("Cruza los nombres de la lista de precios con los productos en stock y actualiza el precio unitario en Valorización.")

        _mc1, _mc2 = st.columns([2,1])
        with _mc1:
            st.info("El mapeo busca primero coincidencia **exacta** y luego **parcial** (primeros 15 caracteres). "
                    "Después del mapeo, los precios aparecen automáticamente en **💲 Valorización**.")
        with _mc2:
            if st.button("🔗 Ejecutar mapeo automático", type="primary", key="btn_mapeo_lp"):
                prod_db = obtener_productos_completo()
                if prod_db.empty:
                    st.warning("Sin productos en stock para mapear.")
                else:
                    conn = conectar_db()
                    mapeados = sin_match = 0
                    no_match_list = []
                    for _, lp_row in df_lp.iterrows():
                        nom_lp = safe_str(lp_row["producto"]).upper().strip()
                        match = prod_db[prod_db["nombre"].str.upper().str.strip() == nom_lp]
                        if match.empty and len(nom_lp) >= 5:
                            match = prod_db[prod_db["nombre"].str.upper().str.contains(nom_lp[:15], na=False)]
                        if not match.empty:
                            conn.execute("UPDATE productos SET precio_unitario=?, moneda_precio='USD' WHERE nombre=?",
                                         (float(lp_row["precio_contado"]), match.iloc[0]["nombre"]))
                            mapeados += 1
                        else:
                            sin_match += 1
                            no_match_list.append(safe_str(lp_row["producto"]))
                    conn.commit(); conn.close()
                    limpiar_cache()
                    st.success(f"✅ {mapeados} productos mapeados correctamente.")
                    if sin_match > 0:
                        st.warning(f"⚠️ {sin_match} productos sin coincidencia en stock.")
                        with st.expander("Ver productos sin match"):
                            st.write(no_match_list)
                    st.rerun()

        # ── Historial de Precios ──────────────────────────────────────────────
        st.markdown("---")
        with st.expander("📈 Historial de cambios de precio por producto", expanded=False):
            _hp_prod = st.selectbox("Producto", ["Todos"] + sorted(df_lp["producto"].dropna().unique().tolist()),
                                    key="hp_prod_sel")
            _df_hp = obtener_historial_precios(_hp_prod if _hp_prod != "Todos" else "")
            if _df_hp.empty:
                st.info("Sin historial aún. Los cambios se registran cada vez que se importa una lista.")
            else:
                _fig_hp = px.line(
                    _df_hp.sort_values("fecha_hora"),
                    x="fecha_hora", y="precio",
                    color="producto" if _hp_prod == "Todos" else None,
                    markers=True, title="Evolución de precio",
                    labels={"precio":"Precio","fecha_hora":"Fecha"}
                )
                _fig_hp.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(_fig_hp, use_container_width=True)
                st.dataframe(_df_hp.rename(columns={
                    "fecha_hora":"Fecha","producto":"Producto",
                    "precio":"Precio","moneda":"Moneda","usuario":"Usuario"
                }), use_container_width=True, hide_index=True)

        # ── Presupuestador ────────────────────────────────────────────────────
        st.markdown("---")
        st.write("### 💼 Presupuestador")
        st.caption("Armá un presupuesto para un cliente con productos y precios de lista. Generá el PDF listo para enviar.")
        _pres_lp = obtener_lista_precios()
        _pres_pf = obtener_productos_completo()
        _src_prods_p = sorted(_pres_lp["producto"].dropna().unique().tolist() if not _pres_lp.empty
                              else _pres_pf["nombre"].dropna().unique().tolist())

        _pp1, _pp2 = st.columns(2)
        with _pp1: _pres_cliente = st.text_input("Cliente", key="pres_cliente")
        with _pp2: _pres_obs     = st.text_input("Observaciones (opcional)", key="pres_obs")

        _pit1, _pit2, _pit3 = st.columns([3, 1, 1])
        with _pit1:
            _p_sel = st.selectbox("Producto", _src_prods_p, key="pres_item_prod")
        with _pit2:
            _p_cant = st.number_input("Cantidad", min_value=0.01, value=1.0, step=1.0, key="pres_item_cant")
        with _pit3:
            _p_sug = 0.0
            if not _pres_lp.empty:
                _lpm = _pres_lp[_pres_lp["producto"] == _p_sel]
                if not _lpm.empty: _p_sug = float(_lpm.iloc[0].get("precio_contado", 0))
            _p_precio = st.number_input("Precio USD", min_value=0.0, value=_p_sug, step=0.01, key="pres_item_precio")

        if "pres_items" not in st.session_state:
            st.session_state["pres_items"] = []

        _bc1, _bc2 = st.columns(2)
        with _bc1:
            if st.button("➕ Agregar ítem", key="btn_pres_add"):
                st.session_state["pres_items"].append(
                    {"producto": _p_sel, "cantidad": _p_cant, "precio": _p_precio, "moneda": "USD"}
                )
                st.rerun()
        with _bc2:
            if st.button("🗑️ Limpiar", key="btn_pres_clear"):
                st.session_state["pres_items"] = []
                st.rerun()

        _items_now = st.session_state.get("pres_items", [])
        if _items_now:
            _df_it = pd.DataFrame(_items_now)
            _df_it["Subtotal"] = _df_it["cantidad"] * _df_it["precio"]
            st.dataframe(_df_it.rename(columns={"producto":"Producto","cantidad":"Cantidad",
                                                 "precio":"Precio","moneda":"Moneda","Subtotal":"Subtotal USD"}),
                         use_container_width=True, hide_index=True)
            st.metric("Total presupuesto (USD)", f"${_df_it['Subtotal'].sum():,.2f}")
            if PDF_AVAILABLE:
                if st.button("📄 Generar PDF", type="primary", key="btn_pres_pdf"):
                    _pbytes = generar_presupuesto_pdf(_pres_cliente, _items_now, usuario_actual(), _pres_obs)
                    if _pbytes:
                        st.download_button("⬇️ Descargar Presupuesto PDF", data=_pbytes,
                                           file_name=f"presupuesto_{datetime.now().strftime('%Y%m%d')}.pdf",
                                           mime="application/pdf")
            else:
                st.caption("PDF: `pip install reportlab`")
        else:
            st.caption("Agregá productos para armar el presupuesto.")

with tab11: _render_tab11()




with tab12: _render_tab12()
