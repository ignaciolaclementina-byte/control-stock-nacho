"""
Control de DepÃ³sito Inteligente â€” La Clementina S.A.
VersiÃ³n PRO: auth, transferencias, valorizaciÃ³n, rotaciÃ³n,
             reportes, email, importaciÃ³n incremental, PDF.

Dependencias adicionales (instalar si no estÃ¡n):
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
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 1. CONFIGURACIÃ“N DE PÃGINA Y CSS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Escribir config.toml con dark mode LC si no existe o estÃ¡ desactualizado
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
    page_title="La Clementina â€” Control de DepÃ³sito",
    page_icon="ðŸŒ¿",
    layout="wide"
)

# Colores corporativos LC
_LC_YELLOW = "#F5A800"
_LC_NAVY   = "#3D4E6B"
_LC_LIGHT  = "#FFF8E7"

st.markdown(f"""
<style>
/* â”€â”€ Forzar dark mode en toda la app â”€â”€ */
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

/* MÃ©tricas */
[data-testid="metric-container"] {{
    background-color: #1C2333 !important;
    border: 1px solid #2D3748 !important;
    border-radius: 8px !important;
    padding: 12px !important;
}}

/* â”€â”€ Solo elementos HTML custom â€” */

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
.stock-card   {{
    padding:18px;border-radius:14px;margin-bottom:12px;
    border:1px solid #2D3748;position:relative;
    box-shadow:0 6px 20px rgba(0,0,0,.4);
    animation:fadeInCard .35s ease both;
    transition:transform .15s ease,box-shadow .15s ease;
}}
.stock-card:hover {{
    transform:translateY(-3px);
    box-shadow:0 10px 28px rgba(0,0,0,.5);
}}
@keyframes fadeInCard {{
    from{{opacity:0;transform:translateY(10px)}}
    to  {{opacity:1;transform:translateY(0)}}
}}
.card-normal  {{
    background:linear-gradient(145deg,#1a2a1a 0%,#1C2333 60%);
    border-left:6px solid #38a169;
}}
.card-low     {{
    background:linear-gradient(145deg,#2a2010 0%,#1C2333 60%);
    border-left:6px solid {_LC_YELLOW};
}}
.card-warning {{
    background:linear-gradient(145deg,#2a1010 0%,#1C2333 60%);
    border-left:6px solid #e53e3e;
}}
.stock-title  {{font-size:.95rem;color:#E2E8F0;font-weight:700;margin-bottom:8px;
                line-height:1.2;min-height:2.4em}}
.stock-value  {{font-size:1.75rem;color:#FAFAFA;font-weight:900;display:block;letter-spacing:-.5px}}
.stock-unit   {{font-size:.8rem;color:#A0AEC0;font-weight:400}}
.stock-info   {{margin-top:10px;padding-top:8px;border-top:1px solid #2D3748;
                font-size:.8rem;color:#A0AEC0}}
.label-blue   {{background:#1a365d;color:#90cdf4;padding:2px 6px;border-radius:4px;font-weight:bold}}
.label-orange {{background:#2d1e0a;color:{_LC_YELLOW};padding:2px 6px;border-radius:4px;font-weight:bold}}

/* Barra de progreso en cards */
.stock-progress-wrap {{
    background:#2D3748;border-radius:99px;height:7px;margin:8px 0 4px;overflow:hidden;
}}
.stock-progress-bar {{
    height:7px;border-radius:99px;transition:width .4s ease;
}}

/* Zebra en tablas nativas */
[data-testid="stDataFrame"] tr:nth-child(even) td {{
    background:rgba(255,255,255,.03) !important;
}}

/* KPI bar fija superior */
.kpi-topbar {{
    display:flex;gap:12px;padding:10px 18px;
    background:linear-gradient(90deg,{_LC_NAVY} 0%,#1a2540 100%);
    border-radius:10px;margin-bottom:14px;border:1px solid #2D3748;
    flex-wrap:wrap;align-items:center;
}}
.kpi-topbar-item {{
    display:flex;flex-direction:column;align-items:center;
    padding:0 14px;border-right:1px solid #2D3748;
}}
.kpi-topbar-item:last-child {{border-right:none}}
.kpi-topbar-val  {{font-size:1.4rem;font-weight:900;color:#FAFAFA}}
.kpi-topbar-lbl  {{font-size:.65rem;color:#A0AEC0;text-transform:uppercase;letter-spacing:.5px}}
.kpi-topbar-val.kpi-red   {{color:#fc8181}}
.kpi-topbar-val.kpi-yellow{{color:{_LC_YELLOW}}}
.kpi-topbar-val.kpi-green {{color:#68d391}}

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

/* SemÃ¡foros */
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 2. CAPA DE DATOS â€” SQLite (local/dev) o PostgreSQL/Supabase (producciÃ³n)
#    Configurar: st.secrets["DATABASE_URL"] = "postgresql://user:pass@host/db"
#    o variable de entorno DATABASE_URL en Streamlit Cloud Settings â†’ Secrets
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _get_db_url() -> str:
    try:
        return st.secrets.get("DATABASE_URL", "") or ""
    except Exception:
        return os.environ.get("DATABASE_URL", "")

_DB_URL     = _get_db_url()
IS_POSTGRES = bool(_DB_URL and "postgres" in _DB_URL.lower())

# Reglas de conflicto para INSERT OR REPLACE / INSERT OR IGNORE â†’ PostgreSQL
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
    """Traduce SQL SQLite â†’ PostgreSQL: placeholders y variantes INSERT."""
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
    """Cursor normalizado que adapta SQL segÃºn el backend."""
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
    """ConexiÃ³n unificada: sqlite3 o psycopg2 segÃºn DATABASE_URL."""

    def __init__(self):
        if IS_POSTGRES:
            import psycopg2
            url = _DB_URL.replace("postgres://", "postgresql://", 1)
            try:
                self._raw = psycopg2.connect(url, connect_timeout=8)
                self._raw.autocommit = True
                self._pg  = True
            except Exception as _pg_err:
                import streamlit as _st_warn
                if not _st_warn.session_state.get("_supabase_warn_shown"):
                    _st_warn.warning(
                        f"âš ï¸ Supabase no disponible ({_pg_err.__class__.__name__}). "
                        "Usando base de datos local (SQLite). Los datos no se sincronizarÃ¡n hasta que Supabase vuelva.",
                        icon="ðŸ—„ï¸",
                    )
                    _st_warn.session_state["_supabase_warn_shown"] = True
                self._raw = sqlite3.connect("stock_agroquimicos.db", check_same_thread=False)
                self._pg  = False
        else:
            self._raw = sqlite3.connect("stock_agroquimicos.db", check_same_thread=False)
            self._pg  = False

    def cursor(self) -> _Cur:
        return _Cur(self._raw.cursor(), self._pg)

    def execute(self, sql: str, params=()):
        cur = self.cursor()
        cur.execute(sql, params if params else None)
        return cur

    def commit(self):
        # Con autocommit=True en PostgreSQL, cada statement se commitea solo
        if not self._pg:
            self._raw.commit()
    def close(self):
        # En PostgreSQL usamos conexiÃ³n cacheada â€” no cerrar
        if not self._pg:
            self._raw.close()

    def __enter__(self): return self
    def __exit__(self, *_):
        try:    self.commit()
        except: pass
        self.close()


@st.cache_resource
def _get_cached_db() -> _DB:
    """ConexiÃ³n Ãºnica reutilizable (PostgreSQL connection pooling)."""
    return _DB()

def conectar_db() -> _DB:
    if IS_POSTGRES:
        db = _get_cached_db()
        # Reconectar si la conexiÃ³n se cerrÃ³
        try:
            db._raw.cursor().execute("SELECT 1")
        except Exception:
            _get_cached_db.clear()
            db = _get_cached_db()
        return db
    return _DB()


def _rsql(sql: str, conn, params=None) -> pd.DataFrame:
    """Ejecuta SQL y devuelve DataFrame. Usa cursor directo en PostgreSQL."""
    raw = conn._raw if isinstance(conn, _DB) else conn
    pg  = (conn._pg if isinstance(conn, _DB) else False) or IS_POSTGRES
    if pg and params:
        sql = sql.replace("?", "%s")
    try:
        if pg:
            # PostgreSQL: cursor directo (evita deprecation de pd.read_sql_query con psycopg2)
            cur = raw.cursor()
            cur.execute(sql, list(params) if params else None)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            return pd.DataFrame(rows, columns=cols)
        else:
            if params:
                return pd.read_sql_query(sql, raw, params=list(params))
            return pd.read_sql_query(sql, raw)
    except Exception:
        return pd.DataFrame()


def _changes(conn, cur) -> int:
    """Filas afectadas por Ãºltimo INSERT OR IGNORE."""
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
        f"""CREATE TABLE IF NOT EXISTS notas_cliente (
            id_nota    {_pk},
            cliente    TEXT NOT NULL,
            nota       TEXT NOT NULL,
            usuario    TEXT DEFAULT '',
            fecha      TEXT DEFAULT '',
            destacada  INTEGER DEFAULT 0
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

    # Ãndices para acelerar queries sobre tablas grandes
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 3. CRUD BÃSICO
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# NOTAS POR CLIENTE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def obtener_notas_cliente(cliente):
    try:
        conn = conectar_db()
        ph = "%s" if IS_POSTGRES else "?"
        rows = conn.execute(
            f"SELECT id_nota, nota, usuario, fecha, destacada FROM notas_cliente WHERE cliente={ph} ORDER BY destacada DESC, fecha DESC",
            (cliente,)
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []

def guardar_nota_cliente(cliente, nota, usuario, destacada=False):
    conn = conectar_db()
    ph = "%s" if IS_POSTGRES else "?"
    conn.execute(
        f"INSERT INTO notas_cliente (cliente, nota, usuario, fecha, destacada) VALUES ({ph},{ph},{ph},{ph},{ph})",
        (cliente, nota, usuario, datetime.now().strftime("%d/%m/%Y %H:%M"), 1 if destacada else 0)
    )
    conn.commit(); conn.close()

def eliminar_nota_cliente(id_nota):
    conn = conectar_db()
    ph = "%s" if IS_POSTGRES else "?"
    conn.execute(f"DELETE FROM notas_cliente WHERE id_nota={ph}", (id_nota,))
    conn.commit(); conn.close()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 4. QUERIES CON CACHÃ‰
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@st.cache_data(ttl=600, show_spinner=False)
def obtener_stock_con_lote():
    conn  = conectar_db()
    query = """
        SELECT p.nombre "Producto", p.codigo "CÃ³digo", p.unidad "Unidad",
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
    return (df.groupby(["Producto","CÃ³digo","Unidad","Lote","Deposito"])["neta"]
              .sum().reset_index().rename(columns={"neta":"Stock Actual"}))

@st.cache_data(ttl=600, show_spinner=False)
def obtener_stock_full():
    df = obtener_stock_con_lote()
    if df.empty: return df
    return df.groupby(["Producto","CÃ³digo","Unidad","Deposito"])["Stock Actual"].sum().reset_index()

@st.cache_data(ttl=600, show_spinner=False)
def obtener_historial_movimientos():
    conn  = conectar_db()
    query = """
        SELECT m.id_movimiento "ID", m.fecha_hora "Fecha", m.tipo_movimiento "Tipo",
               p.nombre "Producto", p.codigo "CÃ³digo", m.cantidad "Cantidad",
               p.unidad "Unidad", m.lote "Lote", m.deposito "DepÃ³sito",
               m.referencia "Referencia", COALESCE(m.origen,'excel') "Origen",
               COALESCE(m.anulado,0) "Anulado", COALESCE(m.usuario,'') "Usuario"
        FROM movimientos m JOIN productos p ON m.id_producto=p.id_producto
        ORDER BY m.id_movimiento DESC
        LIMIT 2000
    """
    df = _rsql(query, conn)
    conn.close()
    return df

@st.cache_data(ttl=600, show_spinner=False)
def obtener_lista_precios():
    conn = conectar_db()
    df = _rsql("SELECT * FROM lista_precios ORDER BY rubro, producto", conn)
    conn.close()
    return df

@st.cache_data(ttl=600, show_spinner=False)
def obtener_entregas(hoja=None):
    conn = conectar_db()
    if hoja and hoja != "Todas":
        df = _rsql("SELECT * FROM entregas WHERE hoja=? ORDER BY dia_recibido DESC", conn, params=(hoja,))
    else:
        df = _rsql("SELECT * FROM entregas ORDER BY hoja, dia_recibido DESC", conn)
    conn.close()
    return df

@st.cache_data(ttl=600, show_spinner=False)
def obtener_productos_completo():
    conn = conectar_db()
    df = _rsql("SELECT * FROM productos ORDER BY nombre", conn)
    conn.close()
    return df

@st.cache_data(ttl=600, show_spinner=False)
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
    df_r["DÃ­as_Cobertura"] = df_r.apply(
        lambda r: round(r["Stock Actual"] / r["Sal_Diarias"])
                  if r["Sal_Diarias"] > 0 else None, axis=1
    )
    df_r["RotaciÃ³n_Anual"] = df_r.apply(
        lambda r: round(365 / r["DÃ­as_Cobertura"], 1)
                  if r["DÃ­as_Cobertura"] and r["DÃ­as_Cobertura"] > 0 else None, axis=1
    )
    return df_r.sort_values("DÃ­as_Cobertura", na_position="last")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 5. STOCK CON COMPROMISOS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 6. AUTH
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        <h1>ðŸ§ª Control de DepÃ³sito</h1>
        <p style="color:#6c757d">La Clementina S.A.</p>
    </div>
    """, unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]
    with col:
        user = st.text_input("Usuario", key="login_user")
        pwd  = st.text_input("ContraseÃ±a", type="password", key="login_pwd")
        if st.button("Ingresar", type="primary"):
            result = verificar_usuario(user, pwd)
            if result:
                st.session_state.authenticated  = True
                st.session_state.user_rol       = result[0]
                st.session_state.user_nombre    = result[1]
                st.session_state.username       = user
                st.rerun()
            else:
                st.error("Usuario o contraseÃ±a incorrectos.")
        st.caption("Usuario inicial: **admin** / ContraseÃ±a: **admin123**")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 7. HELPERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

def _filtro_fonetico(serie, query, umbral=0.82):
    """Retorna mÃ¡scara booleana con coincidencias exactas + fonÃ©ticas."""
    q = query.lower()
    exacta = serie.fillna("").str.lower().str.contains(q, na=False)
    if len(q) < 5:
        return exacta  # bÃºsquedas cortas: solo exacta
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 8. EXPORTS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def to_excel_bytes(df, sheet_name="Hoja1"):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)
    return out.getvalue()

def hash_dataframe(df: pd.DataFrame) -> str:
    """SHA1 del contenido del DataFrame para detectar reimportaciones."""
    return hashlib.sha1(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:12]

def siguiente_numero_remito() -> str:
    """Genera el prÃ³ximo nÃºmero correlativo de remito: R-00001, R-00002..."""
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

    elems.append(Paragraph("<b>La Clementina S.A.</b> â€” Orden de Compra Sugerida", styles["Title"]))
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
        f"<font size=7 color=grey>Generado automÃ¡ticamente â€” La Clementina S.A. Â· {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()

def calcular_forecast(dias_proyeccion=30) -> pd.DataFrame:
    """Proyecta cuÃ¡nto se necesita comprar en los prÃ³ximos N dÃ­as segÃºn consumo histÃ³rico."""
    rot = calcular_rotacion_stock(90)
    stk = obtener_stock_full()
    if rot.empty or stk.empty:
        return pd.DataFrame()
    stk_sum = stk.groupby(["Producto","Unidad"])["Stock Actual"].sum().reset_index()
    rot_sum  = rot[["Producto","Sal_Diarias"]].groupby("Producto")["Sal_Diarias"].mean().reset_index()
    df_fc = stk_sum.merge(rot_sum, on="Producto", how="left").fillna(0)
    df_fc["Consumo_Proyectado"] = (df_fc["Sal_Diarias"] * dias_proyeccion).round(1)
    df_fc["Necesidad_Compra"]   = (df_fc["Consumo_Proyectado"] - df_fc["Stock Actual"]).clip(lower=0).round(1)
    df_fc["DÃ­as_Cobertura"]     = df_fc.apply(
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
        "<b>La Clementina S.A.</b> â€” Remito de Salida de DepÃ³sito",
        styles["Title"]
    ))
    elems.append(Spacer(1, .3*cm))
    elems.append(Paragraph(
        f"Nro: <b>{numero}</b> &nbsp;&nbsp; Fecha: <b>{datetime.now().strftime('%d/%m/%Y %H:%M')}</b>"
        f" &nbsp;&nbsp; Operador: <b>{usuario}</b>",
        styles["Normal"]
    ))
    elems.append(Paragraph(f"Cliente: <b>{cliente}</b> &nbsp;&nbsp; DepÃ³sito: <b>{deposito}</b>",
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
        [["EntregÃ³:", "", "RecibiÃ³:"],
         ["_________________________", "  ", "_________________________"],
         [usuario, "", cliente]],
        colWidths=[6*cm, 3*cm, 6*cm]
    )
    elems.append(_firma)
    elems.append(Spacer(1, .5*cm))
    elems.append(Paragraph(
        f"<font size=7 color=grey>Generado por Sistema de GestiÃ³n â€” La Clementina S.A. Â· {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()

def descargar_excel_agrupado(df):
    if df.empty: return b""
    pivot = df.pivot_table(
        index=["Producto","CÃ³digo","Unidad"], columns="Deposito",
        values="Stock Actual", aggfunc="sum"
    ).fillna(0)
    pivot["TOTAL GENERAL"] = pivot.sum(axis=1)
    return to_excel_bytes(pivot.reset_index(), "Comparativa_Stock")

def descargar_planilla_inventario(df):
    d = df.copy()
    d["CONTEO FÃSICO"] = ""; d["DIFERENCIA"] = ""; d["OBSERVACIONES"] = ""
    return to_excel_bytes(d, "Toma_Stock")

def generar_orden_reposicion(stock_df, umbral, consumo_df):
    """Excel con productos bajo umbral y cantidad sugerida (30 dÃ­as de cobertura)."""
    prod_df = obtener_productos_completo()
    bajo = stock_df[stock_df["Stock Actual"] < umbral].copy()
    bajo = bajo.groupby(["Producto","CÃ³digo","Unidad","Deposito"])["Stock Actual"].sum().reset_index()
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
    """Reporte mensual consolidado en mÃºltiples hojas."""
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
    """PDF mensual con reportlab. Devuelve bytes o None si no estÃ¡ disponible."""
    if not PDF_AVAILABLE: return None
    stock = obtener_stock_full()
    ent   = obtener_entregas()
    buf   = io.BytesIO()
    doc   = SimpleDocTemplate(buf, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                               topMargin=2*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    elems  = []

    # TÃ­tulo
    elems.append(Paragraph("Control de DepÃ³sito â€” La Clementina S.A.", styles["Title"]))
    elems.append(Paragraph(f"Reporte generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                            styles["Normal"]))
    elems.append(Spacer(1, 0.5*cm))

    # KPIs
    if not stock.empty:
        U = int(obtener_metadata("umbral_alerta") or 20)
        kpi_data = [
            ["Indicador", "Valor"],
            ["Total Productos",  str(stock["Producto"].nunique())],
            ["DepÃ³sitos",        str(stock["Deposito"].nunique())],
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
            rows = [["Producto","DepÃ³sito","Stock","Unidad"]]
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


@st.cache_data(ttl=600, show_spinner=False)
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
                          "<font color='#888' size=9>Insumos Agropecuarios Â· San Jorge, Santa Fe</font>",
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
            elems.append(Paragraph("La Clementina S.A. â€” Presupuesto", styles["Title"]))
    elems.append(Spacer(1, 0.3*cm))

    # Cliente y fecha
    elems.append(Paragraph(f"<b>Cliente:</b> {cliente}", styles["Normal"]))
    elems.append(Paragraph(f"<b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y')}  Â·  "
                           f"<b>Elaborado por:</b> {usuario}", styles["Normal"]))
    if obs:
        elems.append(Paragraph(f"<b>Observaciones:</b> {obs}", styles["Normal"]))
    elems.append(Spacer(1, 0.3*cm))

    # Tabla de Ã­tems
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
        "Sujeto a disponibilidad de stock. VÃ¡lido por 7 dÃ­as hÃ¡biles.</font>",
        styles["Normal"]
    ))
    elems.append(Spacer(1, 0.3*cm))
    elems.append(Paragraph(
        f"<font size=8 color='#888'>La Clementina S.A. â€” San Jorge, Santa Fe | "
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()


def generar_qr_lote(producto: str, lote: str, vencimiento: str, deposito: str) -> bytes:
    """Genera imagen PNG de QR con datos del lote. Requiere qrcode."""
    try:
        import qrcode as _qr
        _data = f"Producto: {producto}\nLote: {lote}\nVence: {vencimiento}\nDepÃ³sito: {deposito}"
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
        lambda d: "âœ… Coincide" if abs(d) < 0.01 else
                  ("ðŸ“ˆ Sobrante en sistema" if d > 0 else "ðŸ“‰ Faltante en sistema")
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
    """Excel con lotes vencidos para gestiÃ³n de baja."""
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

    # â”€â”€ Header con logo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _logo_path_ej = os.path.join(os.path.dirname(__file__), "logo.png")
    _header_data = []
    if os.path.exists(_logo_path_ej):
        try:
            from reportlab.platypus import Image as RLImage
            _img = RLImage(_logo_path_ej, width=2.5*cm, height=2.5*cm, kind="proportional")
            _header_data = [[_img,
                Paragraph("<font color='#3D4E6B' size=16><b>La Clementina S.A.</b></font><br/>"
                          "<font color='#555' size=10>Reporte Ejecutivo de DepÃ³sito</font>",
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
        elems.append(Paragraph("La Clementina S.A. â€” Reporte Ejecutivo", styles["Title"]))
        elems.append(Paragraph(datetime.now().strftime("%d/%m/%Y %H:%M"), styles["Normal"]))
    elems.append(Spacer(1, 0.4*cm))

    # â”€â”€ KPIs Stock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not stock.empty:
        elems.append(Paragraph("Stock â€” Indicadores Clave", styles["Heading2"]))
        _neg = int((stock["Stock Actual"] < 0).sum())
        _bajo = int((stock["Stock Actual"].between(0, U, inclusive="left")).sum())
        _comp = int((stock["Disponible Neto"] < 0).sum()) if "Disponible Neto" in stock.columns else 0
        _kpi = [
            ["Productos Ãºnicos", str(stock["Producto"].nunique()),
             "Volumen total", f"{stock['Stock Actual'].sum():,.0f}"],
            ["DepÃ³sitos activos", str(stock["Deposito"].nunique()),
             "Stock negativo ðŸ”´", str(_neg)],
            ["Bajo umbral ðŸŸ¡", str(_bajo),
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

        # CrÃ­ticos
        _crit = stock[stock["Stock Actual"] < U].sort_values("Stock Actual").head(12)
        if not _crit.empty:
            elems.append(Paragraph("Productos CrÃ­ticos (bajo umbral o negativos)", styles["Heading2"]))
            _rows = [["Producto", "DepÃ³sito", "Stock", "Disponible"]]
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

    # â”€â”€ Entregas pendientes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not ent.empty:
        elems.append(Paragraph("Entregas Pendientes â€” Resumen por Producto", styles["Heading2"]))
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

    # â”€â”€ Sin Entregar MG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not mg.empty:
        _mg_p = mg[mg["pendiente"] > 0]
        if not _mg_p.empty:
            elems.append(Paragraph(f"Sin Entregar MacroGest â€” {len(_mg_p)} pendientes", styles["Heading2"]))
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

    # â”€â”€ Footer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    elems.append(Spacer(1, 0.5*cm))
    elems.append(Paragraph(
        f"<font size=8 color='#888'>La Clementina S.A. â€” San Jorge, Santa Fe | "
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Confidencial</font>",
        styles["Normal"]
    ))
    doc.build(elems)
    return buf.getvalue()


@st.cache_data(ttl=600, show_spinner=False)
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
        "codigo":    next((c for c in df_raw.columns if c in ["codigo","cÃ³digo"]), None),
        "producto":  next((c for c in df_raw.columns if "descripcion" in c or "descripciÃ³n" in c or "producto" in c), None),
        "unidad":    next((c for c in df_raw.columns if "unidad" in c), None),
        "deposito":  next((c for c in df_raw.columns if "deposito" in c or "depÃ³sito" in c), None),
        "lote":      next((c for c in df_raw.columns if c == "serie" or c == "lote"), None),
        "stock":     next((c for c in df_raw.columns if c in ["antidad","cantidad","stock","stock_actual","existencia","saldo","qty"]), None),
        "venc":      next((c for c in df_raw.columns if "vencimiento" in c and "muestra" not in c), None),
        "fabric":    next((c for c in df_raw.columns if "fabricacion" in c or "fabricaciÃ³n" in c), None),
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
    """Excel en el formato de importaciÃ³n de MacroGest."""
    if stock_df.empty: return b""
    df = stock_df.copy()
    # Aseguramos stock por lote si disponible
    stk_lote = obtener_stock_con_lote()
    if not stk_lote.empty:
        out_df = stk_lote.rename(columns={
            "CÃ³digo": "codigo", "Producto": "descripcion_1",
            "Unidad": "unidad_medida", "Lote": "lote",
            "Deposito": "deposito", "Stock Actual": "stock_actual"
        })[["codigo","descripcion_1","unidad_medida","deposito","lote","stock_actual"]]
    else:
        out_df = df.rename(columns={
            "CÃ³digo": "codigo", "Producto": "descripcion_1",
            "Unidad": "unidad_medida",
            "Deposito": "deposito", "Stock Actual": "stock_actual"
        })
        out_df["lote"] = "S/L"
        out_df = out_df[["codigo","descripcion_1","unidad_medida","deposito","lote","stock_actual"]]
    return to_excel_bytes(out_df, "Exportacion_MacroGest")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 9. EMAIL
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def enviar_email_alerta(stock_bajo, pendientes_viejos):
    smtp_server = obtener_metadata("smtp_server") or ""
    smtp_port   = int(obtener_metadata("smtp_port") or 587)
    smtp_user   = obtener_metadata("smtp_user")   or ""
    smtp_pass   = obtener_metadata("smtp_pass")   or ""
    dest        = obtener_metadata("email_dest")  or ""
    if not all([smtp_server, smtp_user, smtp_pass, dest]):
        return False, "ConfiguraciÃ³n SMTP incompleta. Completar en ConfiguraciÃ³n â†’ Email."
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"âš ï¸ Alerta Stock â€” La Clementina S.A. â€” {datetime.now().strftime('%d/%m/%Y')}"
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
        <h2>âš ï¸ Reporte de Alertas â€” La Clementina S.A.</h2>
        <p>Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <h3>ðŸ“¦ Stock Bajo / Negativo</h3>
        <table border=1 cellpadding=6 cellspacing=0 style="border-collapse:collapse;width:100%">
        <tr style="background:#007bff;color:white"><th>Producto</th><th>DepÃ³sito</th><th>Stock</th></tr>
        {html_rows_stock}
        </table>
        """
        if pendientes_viejos > 0:
            html += f"<h3>â³ Entregas con +30 dÃ­as pendientes: <b style='color:red'>{pendientes_viejos}</b></h3>"
        html += "</body></html>"

        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_server, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True, f"Email enviado a {dest}"
    except Exception as e:
        return False, str(e)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 10. PARSER ENTREGAS EXCEL (igual que versiÃ³n anterior)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 10b. QUERIES PLAN COMERCIAL
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CAMPANA_ACTUAL = "2026-2027"

PRODUCTOS_FOCO_DEFAULT = [
    ("Semilla MaÃ­z (HÃ­bridos Bayer)", "Bolsas"),
    ("Semilla Soja (AutÃ³gamas)",       "Bolsas"),
    ("Round Up / Glifosato",           "Litros"),
    ("Fungicidas LÃ­nea Bayer",         "Litros"),
    ("Adengo (Herbicida MaÃ­z)",        "Litros"),
    ("Seegrown (Estimulante)",         "Litros"),
]

DISTRIBUCION_OBJETIVO = {
    "Semillas autÃ³gamas": 30,
    "AgroquÃ­micos":        30,
    "Fertilizantes":       30,
    "Otros / Servicios":   10,
}

@st.cache_data(ttl=600, show_spinner=False)
def obtener_metas_campana(campana=CAMPANA_ACTUAL):
    conn = conectar_db()
    df = _rsql("SELECT * FROM metas_campana WHERE campana=?", conn, params=(campana,))
    conn.close()
    return df

@st.cache_data(ttl=600, show_spinner=False)
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

@st.cache_data(ttl=600, show_spinner=False)
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

@st.cache_data(ttl=600, show_spinner=False)
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

@st.cache_data(ttl=600, show_spinner=False)
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
    Lee exportaciÃ³n MacroGest con columnas:
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

    # ClasificaciÃ³n automÃ¡tica Pareto 80/20
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 11. INIT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

# Cargar parÃ¡metros persistidos desde DB (solo primera vez)
if st.session_state.wa_numero is None:
    st.session_state.wa_numero = obtener_metadata("wa_numero") or "5493406123456"
if st.session_state.umbral_alerta is None:
    stored = obtener_metadata("umbral_alerta")
    st.session_state.umbral_alerta = int(stored) if stored else 20

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 12. AUTH GATE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
auth_enabled = obtener_metadata("auth_enabled") == "1"
if auth_enabled and not st.session_state.get("authenticated"):
    mostrar_login()
    st.stop()

# Header con usuario logueado + modo oscuro
# Filtro de depÃ³sito global
_deps_global_opts = ["Todos"]
try:
    _stk_deps = obtener_stock_full()
    if not _stk_deps.empty:
        _deps_global_opts += sorted(_stk_deps["Deposito"].unique().tolist())
except Exception:
    pass

_head_cols = st.columns([3, 2, 1, 1, 1])
with _head_cols[1]:
    _dep_sel = st.selectbox("ðŸ­ DepÃ³sito", _deps_global_opts, key="deposito_global",
                             label_visibility="collapsed",
                             help="Filtro global de depÃ³sito â€” afecta Panel, Stock FÃ­sico e Historial")
with _head_cols[2]:
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False
    if st.toggle("ðŸŒ™", value=st.session_state.dark_mode, key="dark_toggle", help="Modo oscuro"):
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
with _head_cols[3]:
    _auto_ref = st.selectbox("â±ï¸ Auto", ["Off", "5 min", "10 min", "30 min"],
                              key="auto_refresh_sel", label_visibility="collapsed",
                              help="Auto-actualizar datos")
    if _auto_ref != "Off":
        _ref_ms = {"5 min": 300000, "10 min": 600000, "30 min": 1800000}[_auto_ref]
        st.markdown(f"""<script>setTimeout(function(){{window.location.reload();}},{_ref_ms});</script>""",
                    unsafe_allow_html=True)
with _head_cols[2]:
    if auth_enabled and st.session_state.get("authenticated"):
        st.caption(f"ðŸ‘¤ {st.session_state.user_nombre}")
        if st.button("Salir", key="logout_btn"):
            for k in ("authenticated","user_rol","user_nombre","username"):
                st.session_state[k] = "" if k != "authenticated" else False
            st.rerun()
if auth_enabled and st.session_state.get("authenticated"):
    pass  # ya manejado arriba

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 13. TABS PRINCIPALES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    _user_info = (f'<span class="lc-badge">ðŸ‘¤ {st.session_state.user_nombre}'
                  f' &nbsp;Â·&nbsp; {st.session_state.user_rol}</span>')

st.markdown(f"""
<div class="lc-header">
    {_logo_html}
    <div style="flex:1">
        <p class="lc-header-title">Control de DepÃ³sito â€” La Clementina S.A.</p>
        <p class="lc-header-sub">Insumos Agropecuarios Â· Bayer CropScience / Monsanto-Bayer Â· San Jorge, Santa Fe</p>
    </div>
    {_user_info}
</div>
""", unsafe_allow_html=True)

# session_state para cache lazy por tab (se carga la primera vez que se abre cada tab)

tab1, tab11, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab12, tab_traz = st.tabs([
    "âš¡ Panel",
    "ðŸ”„ Sin Entregar MG",
    "ðŸ“¦ LC / LCAGRO",
    "ðŸŒ¿ Bayer DEP55",
    "ðŸšš Bayer Directa",
    "ðŸ“‹ Stock FÃ­sico",
    "ðŸ“œ Historial",
    "ðŸ’² ValorizaciÃ³n",
    "ðŸ“ˆ Reportes",
    "âš™ï¸ ConfiguraciÃ³n",
    "ðŸ“Š Plan Comercial",
    "ðŸ·ï¸ Lista de Precios",
    "ðŸ” Trazabilidad",
])

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 1 â€” PANEL DE CONTROL
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab1:
    stock_df = obtener_stock_con_compromisos()
    # Aplicar filtro global de depÃ³sito
    _dep_global = st.session_state.get("deposito_global", "Todos")
    if _dep_global != "Todos" and not stock_df.empty:
        stock_df = stock_df[stock_df["Deposito"] == _dep_global]

    if stock_df.empty:
        st.warning("âš ï¸ Sin datos. SubÃ­ el archivo en ConfiguraciÃ³n.")
        st.caption("Para empezar, andÃ¡ a âš™ï¸ ConfiguraciÃ³n â†’ Importar Stock desde MacroGest y subÃ­ el archivo de saldos.")
    else:
        U = st.session_state.umbral_alerta
        for meta, caption in [
            ("ultima_importacion",          "ðŸ• Ãšltima importaciÃ³n stock"),
            ("ultima_importacion_entregas",  "ðŸ“¦ Ãšltima importaciÃ³n entregas"),
            ("ultima_importacion_mg",        "ðŸ”„ Ãšltima importaciÃ³n MacroGest"),
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

        # â”€â”€ KPI TopBar visual prominente â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _vol_total = stock_df["Stock Actual"].sum()
        _mg_cache  = st.session_state.get("df_mg_cache")
        _pend_mg   = int(_mg_cache["pendiente"].sum()) if _mg_cache is not None and not _mg_cache.empty else 0
        st.markdown(
            f'<div class="kpi-topbar">'
            f'<div class="kpi-topbar-item"><span class="kpi-topbar-val">{stock_df["Producto"].nunique()}</span><span class="kpi-topbar-lbl">Productos</span></div>'
            f'<div class="kpi-topbar-item"><span class="kpi-topbar-val">{_vol_total:,.0f}</span><span class="kpi-topbar-lbl">Volumen Total</span></div>'
            f'<div class="kpi-topbar-item"><span class="kpi-topbar-val kpi-{"red" if neg_n > 0 else "green"}">{neg_n}</span><span class="kpi-topbar-lbl">Negativos</span></div>'
            f'<div class="kpi-topbar-item"><span class="kpi-topbar-val kpi-{"yellow" if bajo_n > 0 else "green"}">{bajo_n}</span><span class="kpi-topbar-lbl">Bajo umbral</span></div>'
            f'<div class="kpi-topbar-item"><span class="kpi-topbar-val kpi-{"red" if comp_n > 0 else "green"}">{comp_n}</span><span class="kpi-topbar-lbl">Comprometidos</span></div>'
            f'<div class="kpi-topbar-item"><span class="kpi-topbar-val kpi-{"yellow" if venc30 > 0 else "green"}">{venc30}</span><span class="kpi-topbar-lbl">Pend. +30d</span></div>'
            f'<div class="kpi-topbar-item"><span class="kpi-topbar-val kpi-{"yellow" if _pend_mg > 0 else "green"}">{_pend_mg:,}</span><span class="kpi-topbar-lbl">Sin entregar MG</span></div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # Alerta inmediata si hay stock negativo
        if neg_n > 0:
            _neg_prods = stock_df[stock_df["Stock Actual"] < 0]["Producto"].unique()
            st.error(
                f"ðŸš¨ **{neg_n} productos con stock negativo:** "
                + " Â· ".join(_neg_prods[:8])
                + (" ..." if len(_neg_prods) > 8 else ""),
                icon="ðŸš¨"
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
                st.error(f"âš—ï¸ **{len(_lv_venc)} lotes VENCIDOS con stock positivo** "
                         f"({_lv_venc['stock'].sum():,.1f} unidades) â€” ver tab Reportes â†’ Vencimientos",
                         icon="âš—ï¸")
            elif not _lv_crit.empty:
                st.warning(f"â° **{len(_lv_crit)} lotes vencen en menos de 30 dÃ­as** "
                           f"({_lv_crit['stock'].sum():,.1f} unidades) â€” ver Reportes â†’ Vencimientos")

        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        with c1: st.metric("Productos",     stock_df["Producto"].nunique(),
                            help="Total de productos distintos con movimientos registrados")
        with c2: st.metric("Volumen Total", f"{stock_df['Stock Actual'].sum():,.0f}",
                            help="Suma de stock actual de todos los productos y depÃ³sitos")
        with c3: st.metric("Stock Bajo",    bajo_n,  delta=-bajo_n,  delta_color="inverse",
                            help=f"Productos con stock entre 0 y el umbral ({U}). AtenciÃ³n pero no crÃ­tico.")
        with c4: st.metric("Negativo âš ï¸",   neg_n,   delta=-neg_n,   delta_color="inverse",
                            help="Productos con stock menor a 0. Requiere correcciÃ³n inmediata.")
        with c5: st.metric("Comprometido",  comp_n,  delta=-comp_n,  delta_color="inverse",
                            help="Productos donde el stock disponible neto es negativo (stock < compromisos pendientes)")
        with c6: st.metric("DepÃ³sitos",     stock_df["Deposito"].nunique(),
                            help="Cantidad de depÃ³sitos/ubicaciones con stock registrado")
        with c7: st.metric("Pend. +30d â³", venc30,  delta=-venc30,  delta_color="inverse",
                            help="Pedidos de entrega con mÃ¡s de 30 dÃ­as de antigÃ¼edad sin completar")

        # WhatsApp: alerta crÃ­tica + resumen KPIs del dÃ­a
        wa = st.session_state.wa_numero
        _wa_col1, _wa_col2 = st.columns(2)
        if wa:
            with _wa_col1:
                if neg_n > 0 or bajo_n > 0:
                    alertas_wa = stock_df[stock_df["Stock Actual"] < U].head(15)
                    lineas = [f"âš ï¸ *Alerta Stock* â€” {datetime.now().strftime('%d/%m/%Y')}",
                              f"La Clementina S.A."]
                    for _, r in alertas_wa.iterrows():
                        lineas.append(f"â€¢ {r['Producto']}: {r['Stock Actual']:,.1f} {r['Unidad']} ({r['Deposito']})")
                    st.link_button("ðŸ“± Enviar alerta WhatsApp",
                                   f"https://wa.me/{wa}?text={urllib.parse.quote(chr(10).join(lineas))}",
                                   use_container_width=True)
                else:
                    st.caption("âœ… Sin alertas crÃ­ticas de stock")
            with _wa_col2:
                _ent_wa = obtener_entregas()
                _pend_wa = int(_ent_wa["pendiente"].sum()) if not _ent_wa.empty else 0
                _kpi_lines = [
                    f"ðŸ“Š *Resumen LC â€” {datetime.now().strftime('%d/%m/%Y %H:%M')}*",
                    f"Productos: {stock_df['Producto'].nunique()} Â· Vol: {stock_df['Stock Actual'].sum():,.0f}",
                    f"ðŸ”´ Negativos: {neg_n} Â· ðŸŸ¡ Bajo umbral: {bajo_n}",
                    f"ðŸ“¦ Entregas pendientes: {_pend_wa:,}",
                    f"_La Clementina S.A. â€” San Jorge_",
                ]
                st.link_button("ðŸ“¤ Compartir KPIs del dÃ­a",
                               f"https://wa.me/{wa}?text={urllib.parse.quote(chr(10).join(_kpi_lines))}",
                               use_container_width=True)
        else:
            st.caption("ConfigurÃ¡ tu nÃºmero WhatsApp en âš™ï¸ ConfiguraciÃ³n para habilitar compartir.")

        st.markdown("---")

        # SemÃ¡foros por producto â€” tabla compacta y filtrable
        with st.expander("ðŸš¦ Estado de Stock por Producto", expanded=False):
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
                if row["Stock Actual"] < 0:        return "ðŸ”´ Negativo"
                elif row["Stock Actual"] < _u:     return "ðŸŸ¡ Bajo umbral"
                else:                              return "ðŸŸ¢ OK"

            _stk_sem["Estado"]  = _stk_sem.apply(_estado_sem, axis=1)
            _stk_sem["MÃ­nimo"]  = _stk_sem["stock_minimo"].apply(lambda x: int(x) if x > 0 else f"global ({U})")
            _stk_sem = _stk_sem.sort_values(
                "Estado", key=lambda s: s.map({"ðŸ”´ Negativo": 0, "ðŸŸ¡ Bajo umbral": 1, "ðŸŸ¢ OK": 2})
            )

            # Resumen por estado
            _cnt = _stk_sem["Estado"].value_counts()
            _sa, _sb, _sc = st.columns(3)
            _sa.metric("ðŸ”´ Negativos",    _cnt.get("ðŸ”´ Negativo", 0))
            _sb.metric("ðŸŸ¡ Bajo umbral",  _cnt.get("ðŸŸ¡ Bajo umbral", 0))
            _sc.metric("ðŸŸ¢ OK",           _cnt.get("ðŸŸ¢ OK", 0))

            st.markdown("---")
            # Filtro por estado
            _fil_est = st.radio("Mostrar", ["Todos", "ðŸ”´ Negativos", "ðŸŸ¡ Bajo umbral", "ðŸŸ¢ OK"],
                                horizontal=True, key="sem_filtro")
            _df_sem_show = _stk_sem.copy()
            if _fil_est == "ðŸ”´ Negativos":    _df_sem_show = _df_sem_show[_df_sem_show["Estado"] == "ðŸ”´ Negativo"]
            elif _fil_est == "ðŸŸ¡ Bajo umbral": _df_sem_show = _df_sem_show[_df_sem_show["Estado"] == "ðŸŸ¡ Bajo umbral"]
            elif _fil_est == "ðŸŸ¢ OK":          _df_sem_show = _df_sem_show[_df_sem_show["Estado"] == "ðŸŸ¢ OK"]

            st.dataframe(
                _df_sem_show[["Estado","Producto","Unidad","Stock Actual","MÃ­nimo"]]
                .rename(columns={"Stock Actual":"Stock"}),
                use_container_width=True, hide_index=True,
                column_config={
                    "Estado":  st.column_config.TextColumn("Estado", width="small"),
                    "Stock":   st.column_config.NumberColumn("Stock", format="%.1f"),
                }
            )
            if not _df_sem_show.empty:
                st.download_button("ðŸ“¥ Exportar estado de stock",
                                   data=to_excel_bytes(_df_sem_show[["Estado","Producto","Unidad","Stock Actual","MÃ­nimo"]], "Estado_Stock"),
                                   file_name=f"estado_stock_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                   key="dl_sem")

        # ProyecciÃ³n de agotamiento
        with st.expander("ðŸ“… ProyecciÃ³n de Agotamiento", expanded=False):
            st.caption("EstimaciÃ³n de dÃ­as de cobertura por producto basada en salidas de los Ãºltimos 90 dÃ­as.")
            _rot = calcular_rotacion_stock(90)
            if _rot.empty:
                st.info("Sin historial de movimientos para calcular proyecciÃ³n.")
            else:
                _rot_show = _rot[_rot["DÃ­as_Cobertura"].notna()].copy()
                _rot_show["Alerta"] = _rot_show["DÃ­as_Cobertura"].apply(
                    lambda d: "ðŸ”´ CrÃ­tico (<15d)" if d < 15 else ("ðŸŸ¡ Bajo (<45d)" if d < 45 else "ðŸŸ¢ OK")
                )
                _rp1, _rp2 = st.columns([2, 1])
                with _rp1:
                    fig_rot = px.bar(
                        _rot_show.sort_values("DÃ­as_Cobertura").head(20),
                        x="DÃ­as_Cobertura", y="Producto", orientation="h",
                        color="DÃ­as_Cobertura",
                        color_continuous_scale=["#dc3545","#ffc107","#28a745"],
                        title="DÃ­as de cobertura â€” Top 20 productos mÃ¡s crÃ­ticos",
                        labels={"DÃ­as_Cobertura": "DÃ­as"}
                    )
                    fig_rot.update_layout(height=420, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig_rot, use_container_width=True)
                with _rp2:
                    st.dataframe(
                        _rot_show[["Producto","Stock Actual","Sal_Diarias","DÃ­as_Cobertura","Alerta"]]
                        .rename(columns={"Stock Actual":"Stock","Sal_Diarias":"Sal/dÃ­a","DÃ­as_Cobertura":"DÃ­as"})
                        .round(1),
                        use_container_width=True, hide_index=True
                    )
                st.download_button("ðŸ“¥ Exportar ProyecciÃ³n (.xlsx)",
                                   data=to_excel_bytes(_rot_show, "Proyeccion"),
                                   file_name="proyeccion_agotamiento.xlsx")

        # GrÃ¡ficos
        with st.expander("ðŸ“Š GrÃ¡ficos y Comparativas", expanded=False):
            _gtabs = st.tabs(["ðŸ“¦ Por DepÃ³sito", "ðŸ† Top Productos", "âš–ï¸ Stock vs Compromisos", "ðŸ“ˆ EvoluciÃ³n", "ðŸ”¤ ClasificaciÃ³n ABC", "ðŸ—ºï¸ Treemap"])

            with _gtabs[0]:
                cg1, cg2 = st.columns(2)
                with cg1:
                    dep_g = stock_df.groupby("Deposito")["Stock Actual"].sum().reset_index()
                    fig   = px.bar(dep_g.sort_values("Stock Actual"), x="Stock Actual", y="Deposito",
                                   orientation="h", title="Stock por DepÃ³sito", color="Stock Actual",
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
                # Stock vs Compromisos por depÃ³sito
                st.caption("Compara el stock disponible contra los compromisos pendientes de entrega en cada depÃ³sito.")
                _dep_comp = stock_df.groupby("Deposito").agg(
                    Stock=("Stock Actual","sum"),
                    Comprometido=("Comprometido","sum")
                ).reset_index()
                _dep_comp["Disponible"] = (_dep_comp["Stock"] - _dep_comp["Comprometido"]).clip(lower=0)
                _dep_comp = _dep_comp.sort_values("Stock", ascending=False)
                fig_comp = px.bar(_dep_comp, x="Deposito", y=["Disponible","Comprometido"],
                                  barmode="stack", title="Stock Disponible vs Comprometido por DepÃ³sito",
                                  color_discrete_map={"Disponible":"#28a745","Comprometido":"#fd7e14"},
                                  labels={"value":"Unidades","variable":""})
                fig_comp.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_comp, use_container_width=True)
                st.dataframe(
                    _dep_comp.rename(columns={"Stock":"Stock Total","Disponible":"Disponible Neto"}),
                    use_container_width=True, hide_index=True
                )

            with _gtabs[3]:
                # EvoluciÃ³n del stock de un producto
                st.caption("SeleccionÃ¡ un producto para ver cÃ³mo evolucionÃ³ su stock en el tiempo.")
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
                                          title=f"EvoluciÃ³n de stock â€” {prod_evo}",
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
                        st.caption(f"Verde = Entrada Â· Rojo = Salida Â· {len(df_evo)} movimientos registrados")

            with _gtabs[4]:
                # ClasificaciÃ³n ABC por valor de stock
                st.caption("ABC: A = productos que concentran el 80% del stock (los mÃ¡s crÃ­ticos), B = 15%, C = el resto.")
                _abc = stock_df.groupby("Producto")["Stock Actual"].sum().reset_index()
                _abc = _abc[_abc["Stock Actual"] > 0].sort_values("Stock Actual", ascending=False)
                if _abc.empty:
                    st.info("Sin stock positivo para clasificar.")
                else:
                    _abc["Acum %"] = _abc["Stock Actual"].cumsum() / _abc["Stock Actual"].sum() * 100
                    _abc["Clase"] = _abc["Acum %"].apply(
                        lambda x: "A â€” CrÃ­tico" if x <= 80 else ("B â€” Importante" if x <= 95 else "C â€” Bajo impacto"))
                    _col_abc1, _col_abc2 = st.columns(2)
                    with _col_abc1:
                        abc_res = _abc.groupby("Clase").agg(
                            Productos=("Producto","count"),
                            Stock_Total=("Stock Actual","sum")
                        ).reset_index()
                        fig_abc = px.pie(abc_res, names="Clase", values="Productos",
                                         title="DistribuciÃ³n ABC (por cantidad de productos)",
                                         color="Clase",
                                         color_discrete_map={
                                             "A â€” CrÃ­tico":"#dc3545",
                                             "B â€” Importante":"#ffc107",
                                             "C â€” Bajo impacto":"#28a745"})
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
                    st.download_button("ðŸ“¥ Exportar clasificaciÃ³n ABC",
                                       data=to_excel_bytes(_abc, "ABC"),
                                       file_name=f"abc_{datetime.now().strftime('%Y%m%d')}.xlsx")

            with _gtabs[5]:
                # Treemap: producto Ã— depÃ³sito, tamaÃ±o = stock, color = estado
                st.caption("Cada rectÃ¡ngulo = un producto. TamaÃ±o proporcional al stock. Color por estado.")
                _tm_df = stock_df.copy()
                _tm_df = _tm_df[_tm_df["Stock Actual"] > 0]
                if _tm_df.empty:
                    st.info("Sin stock positivo para mostrar.")
                else:
                    _tm_df["Estado"] = _tm_df.apply(
                        lambda r: "ðŸ”´ Negativo" if r["Stock Actual"] < 0
                        else ("ðŸŸ¡ Bajo" if r["Stock Actual"] < U else "ðŸŸ¢ OK"), axis=1
                    )
                    _fig_tm = px.treemap(
                        _tm_df,
                        path=["Deposito", "Producto"],
                        values="Stock Actual",
                        color="Stock Actual",
                        color_continuous_scale=["#e53e3e", _LC_YELLOW, "#38a169"],
                        title="Mapa de calor â€” Stock por DepÃ³sito y Producto",
                        hover_data={"Stock Actual": ":.1f", "Unidad": True}
                    )
                    _fig_tm.update_layout(
                        height=500, margin=dict(l=10,r=10,t=40,b=10),
                        coloraxis_colorbar=dict(title="Stock")
                    )
                    _fig_tm.update_traces(
                        textinfo="label+value",
                        hovertemplate="<b>%{label}</b><br>Stock: %{value:,.1f}<extra></extra>"
                    )
                    st.plotly_chart(_fig_tm, use_container_width=True)

        st.markdown("---")

        # â”€â”€ Novedades del dÃ­a â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with st.expander("ðŸ“… Novedades del dÃ­a", expanded=False):
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
                        _hoy_df[["Fecha","Tipo","Producto","Cantidad","Unidad","Lote","DepÃ³sito","Referencia","Usuario"]]
                        .head(50),
                        use_container_width=True, hide_index=True
                    )
            else:
                st.info("Sin historial registrado.")

        # â”€â”€ Tendencias mes a mes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with st.expander("ðŸ“ˆ Tendencias Mensuales", expanded=False):
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
                            title=f"Salidas mensuales â€” {'Todos los productos' if _prod_tend=='Todos' else _prod_tend}",
                            color_discrete_sequence=["#F5A800"]
                        )
                        fig_est.update_layout(height=260, margin=dict(l=0,r=0,t=40,b=0))
                        st.plotly_chart(fig_est, use_container_width=True)

        # â”€â”€ Buscador Global mejorado â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with st.expander("ðŸ”Ž Buscador Global", expanded=False):
            st.caption("Busca simultÃ¡neamente en stock, entregas (todas las hojas) y pedidos MacroGest.")
            _bg_c1, _bg_c2 = st.columns([4, 1])
            with _bg_c1:
                q_glob = st.text_input("Buscar producto o cliente...", key="busq_global",
                                       placeholder="ej: Round Up, BELTRAMO, glifosato...")
            with _bg_c2:
                _bg_solo_pend = st.checkbox("Solo pendientes", value=True, key="bg_solo_pend")

            if q_glob and len(q_glob) >= 2:
                _bg_total = 0

                # Stock
                st.markdown("##### ðŸ“¦ Stock")
                _bg_stk = stock_df[
                    stock_df["Producto"].str.contains(q_glob, case=False, na=False) |
                    stock_df["CÃ³digo"].astype(str).str.contains(q_glob, case=False, na=False)
                ][["Producto","Deposito","Stock Actual","Comprometido","Disponible Neto"]]
                if _bg_stk.empty:
                    st.caption("Sin resultados en stock.")
                else:
                    st.dataframe(_bg_stk, use_container_width=True, hide_index=True)
                    _bg_total += len(_bg_stk)

                # Entregas todas las hojas
                st.markdown("##### ðŸ“‹ Entregas (LC/LCAGRO Â· Bayer DEP55 Â· Bayer Directa)")
                _bg_ent_all = []
                for _hk_bg in ["LA CLEMENTINA S.A", "BAYER DEP55", "BAYER DIRECTA"]:
                    _ck_bg = f"df_ent_cache_{_hk_bg}"
                    _dh_bg_cached = st.session_state.get(_ck_bg)
                    _dh_bg = _dh_bg_cached if _dh_bg_cached is not None else obtener_entregas(_hk_bg)
                    if _dh_bg is not None and not _dh_bg.empty:
                        _msk_bg = (
                            _dh_bg["producto"].str.contains(q_glob, case=False, na=False) |
                            _dh_bg["cliente"].str.contains(q_glob, case=False, na=False)
                        )
                        _hit_bg = _dh_bg[_msk_bg].copy()
                        if _bg_solo_pend:
                            _hit_bg = _hit_bg[_hit_bg["pendiente"] > 0]
                        if not _hit_bg.empty:
                            _hit_bg["Hoja"] = _hk_bg
                            _bg_ent_all.append(_hit_bg)
                if _bg_ent_all:
                    _bg_ent_df = pd.concat(_bg_ent_all, ignore_index=True)
                    _cols_bg = [c for c in ["Hoja","cliente","producto","deposito","pendiente","estado"] if c in _bg_ent_df.columns]
                    st.dataframe(_bg_ent_df[_cols_bg].head(30), use_container_width=True, hide_index=True)
                    _bg_total += len(_bg_ent_df)
                else:
                    st.caption("Sin resultados en entregas.")

                # MacroGest
                st.markdown("##### ðŸ”„ MacroGest â€” Sin Entregar")
                _bg_mg_cached = st.session_state.get("df_mg_cache")
                _bg_mg = _bg_mg_cached if (_bg_mg_cached is not None) else obtener_entregas("MACROGEST")
                if not _bg_mg.empty:
                    _bg_mg_f = _bg_mg[
                        _bg_mg["producto"].str.contains(q_glob, case=False, na=False) |
                        _bg_mg["cliente"].str.contains(q_glob, case=False, na=False)
                    ].copy()
                    if _bg_solo_pend:
                        _bg_mg_f = _bg_mg_f[_bg_mg_f["pendiente"] > 0]
                    if _bg_mg_f.empty:
                        st.caption("Sin resultados en MacroGest.")
                    else:
                        st.dataframe(_bg_mg_f[["cliente","producto","pendiente","deposito","dia_recibido"]].head(30),
                                     use_container_width=True, hide_index=True)
                        _bg_total += len(_bg_mg_f)
                else:
                    st.caption("Sin datos MacroGest.")

                st.success(f"Total de coincidencias: **{_bg_total}** registros")

        # â”€â”€ Comparativo entre CampaÃ±as â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with st.expander("ðŸ“Š Comparativo entre CampaÃ±as", expanded=False):
            st.caption("Compara volumen de ventas y pendiente entre campaÃ±as registradas en MacroGest.")
            _df_vd_comp = obtener_ventas_detalle()
            if _df_vd_comp.empty:
                st.info("Sin datos de ventas. ImportÃ¡ desde Plan Comercial â†’ Cartera de Clientes.")
            else:
                _campanas_disp = sorted(_df_vd_comp["campana"].dropna().unique().tolist(), reverse=True)
                if len(_campanas_disp) < 2:
                    st.info("Se necesitan al menos 2 campaÃ±as importadas para comparar.")
                else:
                    _cc1, _cc2 = st.columns(2)
                    with _cc1:
                        _camp_a = st.selectbox("CampaÃ±a A", _campanas_disp, index=0, key="comp_camp_a")
                    with _cc2:
                        _camp_b = st.selectbox("CampaÃ±a B", _campanas_disp, index=min(1, len(_campanas_disp)-1), key="comp_camp_b")

                    _df_a = _df_vd_comp[_df_vd_comp["campana"] == _camp_a]
                    _df_b = _df_vd_comp[_df_vd_comp["campana"] == _camp_b]

                    _ka1, _ka2, _ka3, _kb1, _kb2, _kb3 = st.columns(6)
                    _ka1.metric(f"Clientes {_camp_a}", _df_a["cliente"].nunique())
                    _ka2.metric(f"Productos {_camp_a}", _df_a["descripcion"].nunique())
                    _ka3.metric(f"Importe {_camp_a}", f"USD {_df_a['importe_total'].sum():,.0f}")
                    _kb1.metric(f"Clientes {_camp_b}", _df_b["cliente"].nunique())
                    _kb2.metric(f"Productos {_camp_b}", _df_b["descripcion"].nunique())
                    _kb3.metric(f"Importe {_camp_b}", f"USD {_df_b['importe_total'].sum():,.0f}")

                    # Comparativo por producto
                    _comp_a_prod = _df_a.groupby("descripcion")["cantidad"].sum().reset_index()
                    _comp_a_prod.columns = ["Producto", _camp_a]
                    _comp_b_prod = _df_b.groupby("descripcion")["cantidad"].sum().reset_index()
                    _comp_b_prod.columns = ["Producto", _camp_b]
                    _comp_merge = _comp_a_prod.merge(_comp_b_prod, on="Producto", how="outer").fillna(0)
                    _comp_merge["VariaciÃ³n"] = _comp_merge[_camp_a] - _comp_merge[_camp_b]
                    _comp_merge["Var %"] = (
                        (_comp_merge[_camp_a] / _comp_merge[_camp_b].replace(0, 1) - 1) * 100
                    ).round(1)
                    _comp_merge = _comp_merge.sort_values("VariaciÃ³n", ascending=False)

                    _top10_comp = _comp_merge.head(10)
                    _fig_comp = px.bar(_top10_comp, x="VariaciÃ³n", y="Producto", orientation="h",
                                       color="VariaciÃ³n",
                                       color_continuous_scale=["#dc3545", "#ffffff", "#28a745"],
                                       color_continuous_midpoint=0,
                                       title=f"Top 10 variaciones: {_camp_a} vs {_camp_b}")
                    _fig_comp.update_layout(height=350, margin=dict(l=10,r=10,t=40,b=10),
                                            coloraxis_showscale=False)
                    st.plotly_chart(_fig_comp, use_container_width=True)
                    st.dataframe(_comp_merge.round(1), use_container_width=True, hide_index=True)

        st.subheader("ðŸ” Filtros")

        search_q = st.text_input("âŒ¨ï¸ Buscar por nombre o cÃ³digo", placeholder="EscribÃ­ aquÃ­...", key="search_p1")

        with st.expander("ðŸ“· Escanear QR"):
            c_cam, c_fil = st.columns(2)
            with c_cam:
                foto_cam = st.camera_input("CÃ¡mara", key="qr_cam")
            with c_fil:
                foto_fil = st.file_uploader("O subÃ­ imagen", type=["png","jpg","jpeg"], key="qr_fil")
            foto_qr = foto_cam or foto_fil
            if foto_qr:
                res_qr = decodificar_qr_reforzado(foto_qr)
                if res_qr:
                    qr_clean = res_qr.strip().replace("\n","").replace("\r","")
                    st.success(f"âœ… QR: {qr_clean}")
                    if st.session_state.ultimo_qr_procesado != qr_clean:
                        st.session_state.ultimo_qr_procesado = qr_clean
                        m = stock_df[
                            stock_df["Producto"].str.contains(qr_clean, case=False, na=False) |
                            stock_df["CÃ³digo"].astype(str).str.contains(qr_clean, case=False, na=False)
                        ].copy()
                        if len(m) == 1:
                            st.session_state.qr_detectado = m.iloc[0]["Producto"]
                            st.rerun()
                        elif len(m) > 1:
                            opciones_qr = m["Producto"].unique().tolist()
                            st.info(f"Se encontraron {len(opciones_qr)} productos con ese cÃ³digo. SeleccionÃ¡ uno:")
                            elegido_qr = st.selectbox("Producto del QR", opciones_qr, key="qr_multi_sel")
                            if st.button("âœ… Usar este producto", key="qr_multi_btn"):
                                st.session_state.qr_detectado = elegido_qr
                                st.rerun()
                        else:
                            st.info("QR leÃ­do pero sin coincidencia en el stock actual.")
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
            lista_d = sorted(stock_df["Deposito"].dropna().unique().tolist())
            f_dep   = st.selectbox("DepÃ³sito principal", ["Todos"] + lista_d, key="dep_principal")
        with cf3:
            hide_neg       = st.toggle("Solo stock positivo",       value=True)
            filter_reponer = st.toggle(f"ðŸš¨ Reponer (<{U})",        value=False)
            show_neg_f     = st.toggle("âš ï¸ Mostrar negativos",       value=True)
            show_comp_f    = st.toggle("ðŸ”’ Solo comprometidos",      value=False)
        with cf4:
            pass

        # â”€â”€ Selector mÃºltiple de depÃ³sitos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with st.expander("ðŸ­ Filtrar por depÃ³sitos", expanded=True):
            st.caption("MarcÃ¡ los depÃ³sitos que querÃ©s ver. Si no marcÃ¡s ninguno, se muestran todos.")
            _chk_cols = st.columns(min(len(lista_d), 10)) if lista_d else []
            _deps_extra = []
            for _di, _dn in enumerate(lista_d):
                with _chk_cols[_di % len(_chk_cols)]:
                    _lbl = f"Dep. {_dn}"
                    if st.checkbox(_lbl, key=f"dep_chk_{_dn}"):
                        _deps_extra.append(_dn)
            if _deps_extra:
                st.caption(f"âœ… Mostrando: {', '.join(str(d) for d in _deps_extra)}")
            else:
                st.caption("Mostrando todos los depÃ³sitos")

        df_f = stock_df.copy()
        if search_q:
            df_f = df_f[df_f["Producto"].str.contains(search_q, case=False, na=False) |
                        df_f["CÃ³digo"].astype(str).str.contains(search_q, case=False, na=False)]
        if f_prod != "Todos" and not search_q:
            df_f = df_f[df_f["Producto"] == f_prod]
        agrupar_prod = False
        # Aplicar filtro de depÃ³sito: checkboxes tienen prioridad; si ninguno marcado, usar selector principal
        _deps_filtro = set(_deps_extra)
        if not _deps_filtro and f_dep != "Todos":
            _deps_filtro.add(f_dep)
        if _deps_filtro:
            df_f = df_f[df_f["Deposito"].isin(_deps_filtro)]
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
                        "CÃ³digo":          "first",
                        "Unidad":          "first",
                        "Stock Actual":    "sum",
                        "Comprometido":    "sum",
                        "Disponible Neto": "sum",
                        "Deposito":        lambda x: ", ".join(sorted(x.dropna().astype(str).unique())),
                    }))

        if not df_f.empty:
            excel_b = descargar_excel_agrupado(df_f)
            if excel_b:
                st.download_button("ðŸ“¥ Descargar Comparativa", data=excel_b,
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
                                    venc_info = f'<br><span style="color:{color_v};font-size:.75rem">â° Vence en {dias_v}d ({fv})</span>'
                                    b_comp += '<span class="venc-badge">VENCE</span>'

                    comp_line = (f"<br><b>ðŸ”’ Comprometido:</b> {comp:,.1f} | "
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

                    # Barra de progreso comprometido/stock
                    if stk > 0 and comp > 0:
                        _pct_comp = min(100, round(comp / stk * 100))
                        _bar_color = "#e53e3e" if _pct_comp >= 100 else (_LC_YELLOW if _pct_comp >= 60 else "#38a169")
                        _progress_html = (
                            f'<div class="stock-progress-wrap">'
                            f'<div class="stock-progress-bar" style="width:{_pct_comp}%;background:{_bar_color}"></div>'
                            f'</div>'
                            f'<div style="font-size:.68rem;color:#A0AEC0;margin-bottom:4px">'
                            f'Comprometido {_pct_comp}% del stock</div>'
                        )
                    else:
                        _progress_html = ""

                    card_html = (
                        '<div class="stock-card ' + clase + '">'
                        '<div class="stock-title">' + str(item["Producto"]) + b_neg + b_comp + '</div>'
                        '<span class="stock-value">' + f"{stk:,.1f}" + ' <small class="stock-unit">' + str(item["Unidad"]) + '</small></span>'
                        + _progress_html +
                        '<div class="stock-info">'
                        '<b>ID</b> ' + str(item["CÃ³digo"]) + '<br>'
                        '<b>Dep.</b> <span class="label-blue">' + str(item["Deposito"]) + '</span>'
                        + comp_line + venc_info + clientes_pend_line +
                        '</div>'
                        '</div>'
                    )
                    st.markdown(card_html, unsafe_allow_html=True)

        st.markdown("---")

        # Movimiento manual
        with st.expander("âž• Registrar movimiento manual"):
            st.markdown('<p class="seccion-titulo">Movimiento Manual de Stock</p>', unsafe_allow_html=True)
            cm1, cm2 = st.columns(2)
            with cm1:
                prod_m  = st.selectbox("Producto", sorted(stock_df["Producto"].unique()), key="mov_prod")
                tipo_m  = st.radio("Tipo", ["Entrada","Salida"], horizontal=True, key="mov_tipo")
            with cm2:
                cant_m  = st.number_input("Cantidad", min_value=0.01, step=0.5, key="mov_cant")
                dep_m   = st.selectbox("DepÃ³sito", sorted(stock_df["Deposito"].unique()), key="mov_dep")
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
                st.metric("Stock disponible en depÃ³sito seleccionado", f"{stk_disp:,.1f}",
                          help="Cantidad actual en el depÃ³sito antes de esta salida")
                if cant_m > stk_disp:
                    st.warning(f"âš ï¸ La cantidad ingresada ({cant_m:,.1f}) supera el stock disponible ({stk_disp:,.1f}). El stock quedarÃ¡ negativo.")
                if stk_disp <= 0:
                    st.error("ðŸš« El stock en este depÃ³sito ya es cero o negativo.")
            if st.session_state.mov_pendiente is None:
                if st.button("ðŸ“‹ Preparar movimiento"):
                    st.session_state.mov_pendiente = dict(
                        producto=prod_m, tipo=tipo_m, cantidad=cant_m,
                        deposito=dep_m, lote=lote_m, referencia=ref_m,
                        observaciones=obs_m,
                        cliente=st.session_state.get("mov_cliente","") if tipo_m=="Salida" else ""
                    )
                    st.rerun()
            else:
                p = st.session_state.mov_pendiente
                st.warning(f"**Â¿Confirmar?** {p['tipo']} | {p['producto']} | "
                           f"{p['cantidad']:,.2f} | {p['deposito']}")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("âœ… Confirmar", type="primary"):
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
                        st.success("âœ… Registrado.")
                        if _remito_bytes:
                            st.download_button("ðŸ–¨ï¸ Descargar Remito PDF",
                                               data=_remito_bytes,
                                               file_name=f"remito_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                               mime="application/pdf")
                        st.rerun()
                with cc2:
                    if st.button("âŒ Cancelar"):
                        st.session_state.mov_pendiente = None
                        st.rerun()

        # Transferencias entre depÃ³sitos
        st.markdown("---")
        with st.expander("â†”ï¸ Transferencia entre DepÃ³sitos"):
            ct1, ct2 = st.columns(2)
            with ct1:
                prod_t = st.selectbox("Producto", sorted(stock_df["Producto"].unique()), key="trans_prod")
                dep_t_options = sorted(stock_df[stock_df["Producto"]==prod_t]["Deposito"].unique().tolist())
                dep_origen = st.selectbox("DepÃ³sito Origen", dep_t_options, key="trans_origen")
                stk_orig = float(stock_df[
                    (stock_df["Producto"]==prod_t) & (stock_df["Deposito"]==dep_origen)
                ]["Stock Actual"].sum())
                st.info(f"Stock disponible en origen: **{stk_orig:,.1f}**")
            with ct2:
                todos_deps = sorted(stock_df["Deposito"].unique().tolist())
                dep_destino = st.selectbox("DepÃ³sito Destino", todos_deps, key="trans_destino")
                cant_t  = st.number_input("Cantidad", min_value=0.01,
                                          max_value=max(stk_orig, 0.01), step=0.5, key="trans_cant")
                lote_t  = st.text_input("Lote", value="S/L", key="trans_lote")
            ref_t = st.text_input("Referencia transferencia", key="trans_ref")

            if dep_origen == dep_destino:
                st.warning("Origen y destino deben ser distintos.")
            else:
                if st.session_state.trans_pendiente is None:
                    if not es_admin():
                        cod_sup_t = st.text_input("CÃ³digo de supervisor", type="password",
                                                   key="cod_sup_trans",
                                                   help="Requerido para operadores. Los admins no necesitan cÃ³digo.")
                        puede_transferir = cod_sup_t == (obtener_metadata("codigo_supervisor") or "1234")
                        if cod_sup_t and not puede_transferir:
                            st.error("âŒ CÃ³digo de supervisor incorrecto.")
                    else:
                        puede_transferir = True
                    if st.button("â†”ï¸ Preparar transferencia", disabled=not puede_transferir):
                        st.session_state.trans_pendiente = dict(
                            producto=prod_t, dep_origen=dep_origen, dep_destino=dep_destino,
                            cantidad=cant_t, lote=lote_t, referencia=ref_t
                        )
                        st.rerun()
                else:
                    tp = st.session_state.trans_pendiente
                    st.warning(
                        f"**Â¿Confirmar?** {tp['cantidad']:,.1f} Ã— {tp['producto']} | "
                        f"{tp['dep_origen']} â†’ {tp['dep_destino']}"
                    )
                    tc1, tc2 = st.columns(2)
                    with tc1:
                        if st.button("âœ… Confirmar transferencia", type="primary"):
                            conn = conectar_db()
                            id_p = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",
                                                (tp["producto"],)).fetchone()
                            if id_p:
                                ts  = datetime.now().strftime("%d/%m/%Y %H:%M")
                                ref = tp["referencia"] or f"Transferencia {tp['dep_origen']} â†’ {tp['dep_destino']}"
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
                            st.success(f"âœ… Transferencia ejecutada.")
                            st.session_state.trans_pendiente = None
                            st.rerun()
                    with tc2:
                        if st.button("âŒ Cancelar transferencia"):
                            st.session_state.trans_pendiente = None
                            st.rerun()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# FUNCIÃ“N REUTILIZABLE: ENTREGAS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@st.fragment
def mostrar_tab_entregas(hoja_nombre, titulo):
    st.subheader(titulo)
    if hoja_nombre == "LA CLEMENTINA S.A":
        with st.expander("ðŸ“‚ Importar TODAS las hojas", expanded=False):
            st.info("SubÃ­ el archivo completo de entregas Monsanto/Bayer (4 hojas).")
            arch = st.file_uploader("Archivo entregas (.xlsx)", type=["xlsx","xls"],
                                    key="uploader_entregas_global")
            co1, co2 = st.columns(2)
            with co1:
                descontar = st.toggle("ðŸ”„ Registrar como Salidas", value=False, key="tog_descontar")
            with co2:
                sf       = obtener_stock_full()
                dep_opts = sf["Deposito"].unique().tolist() if not sf.empty else ["0"]
                dep_sal  = st.selectbox("DepÃ³sito origen", dep_opts, key="dep_sal_g") if descontar else None

            if arch and st.button("ðŸš€ IMPORTAR", type="primary"):
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
                        msg = f"âœ… {ok} registros. {sal} salidas." if descontar else f"âœ… {ok} registros."
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
        if _ult_ent: st.caption(f"ðŸ• Ãšltima importaciÃ³n: **{_ult_ent}**")
    with _hdr2:
        if st.button("ðŸ”„", key=f"ent_refresh_{hoja_nombre}", help="Actualizar datos"):
            st.session_state[_ent_cache_key] = obtener_entregas(hoja_nombre)
            df_h = st.session_state[_ent_cache_key]
            st.rerun()

    if df_h is None or df_h.empty:
        st.info("Sin datos. ImportÃ¡ en 'LC / LCAGRO'.")
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
    with k6: st.metric("â³ +30d",       v30, delta=-v30, delta_color="inverse")
    with k7: st.metric("ðŸ”´ +60d",       v60, delta=-v60, delta_color="inverse")

    if v60 > 0: st.error(f"ðŸ”´ {v60} entrega(s) con mÃ¡s de 60 dÃ­as sin completar.")
    elif v30>0: st.warning(f"âš ï¸ {v30} entrega(s) con mÃ¡s de 30 dÃ­as pendiente.")

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
        f_cli = st.text_input("ðŸ” Cliente", placeholder="Buscar...", key=f"fcli_{hoja_nombre}")
    with cf5:
        f_edad = st.selectbox("AntigÃ¼edad",
                              ["Todos","Normal (â‰¤30d)","Demorado (30-60d)","CrÃ­tico (>60d)"],
                              key=f"fedad_{hoja_nombre}")

    # Pre-calcular columna lowercase para bÃºsqueda instantÃ¡nea por cliente
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
    if   f_edad == "Normal (â‰¤30d)":       df_f2 = df_f2[df_f2["dias_pend"] <= 30]
    elif f_edad == "Demorado (30-60d)":   df_f2 = df_f2[(df_f2["dias_pend"]>30) & (df_f2["dias_pend"]<=60)]
    elif f_edad == "CrÃ­tico (>60d)":      df_f2 = df_f2[df_f2["dias_pend"] > 60]

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
            "lote":"Lote","deposito":"DepÃ³sito","rto":"RTO","dias_pend":"DÃ­as"
        })
        st.dataframe(df_t, use_container_width=True, hide_index=True)
        st.download_button("ðŸ“¥ Exportar Excel", data=to_excel_bytes(df_t, "Entregas"),
                           file_name=f"entregas_{hoja_nombre.replace(' ','_')}.xlsx")


with tab2: mostrar_tab_entregas("LA CLEMENTINA S.A", "ðŸ“‹ Entregas â€” La Clementina / LCAgro")
with tab3: mostrar_tab_entregas("BAYER DEP55",       "ðŸŒ¿ Consignado Bayer â€” DepÃ³sito 55")
with tab4: mostrar_tab_entregas("BAYER DIRECTA",     "ðŸšš FacturaciÃ³n Directa Bayer 43-60")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 5 â€” STOCK FÃSICO
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab5:
    st.subheader("ðŸ“‹ Toma de Stock FÃ­sico")
    st_df = obtener_stock_full()

    _inv_tabs = st.tabs(["ðŸ“ Conteo Individual", "ðŸ“‹ Conteo Masivo", "â†©ï¸ Devoluciones", "ðŸ“Š Historial AuditorÃ­as", "ðŸ”€ Transferencia"])

    with _inv_tabs[0]:
        if not st_df.empty:
            st.download_button("ðŸ“¥ Descargar Planilla de Conteo (.xlsx)",
                               data=descargar_planilla_inventario(st_df),
                               file_name="Planilla_Toma_Stock.xlsx")
            st.markdown("---")
            st.write("### ðŸ“ Registrar Ajuste Auditado")
            ci1, ci2, ci3 = st.columns(3)
            with ci1:
                p_inv = st.selectbox("Producto", sorted(st_df["Producto"].unique()), key="inv_p")
            with ci2:
                d_inv = st.selectbox("DepÃ³sito", sorted(st_df["Deposito"].unique()), key="inv_d")
            with ci3:
                filt_s   = st_df[(st_df["Producto"]==p_inv) & (st_df["Deposito"]==d_inv)]
                val_sis  = filt_s.iloc[0]["Stock Actual"] if not filt_s.empty else 0.0
                st.metric("Stock en Sistema", f"{val_sis:,.1f}")
            ci4, ci5 = st.columns(2)
            with ci4:
                val_fis = st.number_input("Conteo FÃ­sico Real", min_value=0.0, step=1.0, value=float(val_sis))
            with ci5:
                obs_inv = st.text_input("Observaciones / Auditor")
            dif = val_fis - val_sis
            st.metric("Diferencia detectada", f"{dif:,.1f}", delta=dif)
            if dif != 0:
                if dif > 0: st.info(f"ðŸ“ˆ Sobrante de {dif:,.1f} â€” se registrarÃ¡ una Entrada de ajuste.")
                else:       st.warning(f"ðŸ“‰ Faltante de {abs(dif):,.1f} â€” se registrarÃ¡ una Salida de ajuste.")
            if st.button("ðŸ’¾ Guardar AuditorÃ­a", type="primary"):
                conn   = conectar_db()
                cod_p  = safe_str(st_df[st_df["Producto"]==p_inv].iloc[0]["CÃ³digo"]) if not st_df[st_df["Producto"]==p_inv].empty else "S/C"
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
                st.success("âœ… AuditorÃ­a guardada.")
                st.rerun()
        else:
            st.info("Sin datos de stock.")

    with _inv_tabs[1]:
        st.write("### ðŸ“‹ Conteo Masivo")
        st.caption("SubÃ­ la planilla de conteo completada para registrar todos los ajustes de una vez.")
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
                    # Buscar columnas de conteo fÃ­sico
                    _col_conteo = next((c for c in _df_conteo.columns
                                        if "conteo" in c.lower() or "fisico" in c.lower() or "fÃ­sico" in c.lower()), None)
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
                        if st.button("âœ… Importar conteo masivo", type="primary", key="btn_conteo_masivo"):
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
                                _cod = safe_str(_filt.iloc[0]["CÃ³digo"]) if not _filt.empty else "S/C"
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
                            st.success(f"âœ… {_ok_c} productos procesados.")
                            st.rerun()
                except Exception as _ex:
                    st.error(f"Error: {_ex}")

    with _inv_tabs[2]:
        st.write("### â†©ï¸ Registrar DevoluciÃ³n")
        st.caption("Registra la devoluciÃ³n de un producto por parte de un cliente. Incrementa el stock con tipo 'DevoluciÃ³n'.")
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
                _dep_dev  = st.selectbox("DepÃ³sito destino", sorted(st_df["Deposito"].unique()), key="dev_dep")
            with _dv2:
                _cli_dev  = st.text_input("Cliente que devuelve", key="dev_cli")
                _lote_dev = st.text_input("Lote", value="S/L", key="dev_lote")
                _obs_dev  = st.text_area("Motivo de devoluciÃ³n", key="dev_obs", height=80)
            _rem_dev  = st.text_input("NÂ° Remito original (opcional)", key="dev_rem")
            if st.button("ðŸ’¾ Registrar DevoluciÃ³n", type="primary", key="btn_dev"):
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
                             f"DevoluciÃ³n â€” {_cli_dev}" + (f" / Rem: {_rem_dev}" if _rem_dev else ""),
                             _dep_dev, "devolucion", usuario_actual(),
                             _obs_dev))
                        conn.commit()
                        conn.close()
                        limpiar_cache()
                        st.success(f"âœ… DevoluciÃ³n de {_cant_dev:,.1f} unidades de {_prod_dev} registrada.")
                        st.rerun()
                    else:
                        conn.close()
                        st.error("Producto no encontrado.")
                else:
                    st.warning("CompletÃ¡ el producto y la cantidad.")

    with _inv_tabs[3]:
        st.write("### ðŸ“Š Historial de AuditorÃ­as de Inventario")
        conn = conectar_db()
        df_inv_h2 = _rsql("SELECT * FROM inventario_fisico ORDER BY id_inventario DESC LIMIT 500", conn)
        conn.close()
        if df_inv_h2.empty:
            st.info("Sin auditorÃ­as registradas aÃºn.")
        else:
            _ai1, _ai2, _ai3 = st.columns(3)
            _ai1.metric("Total auditorÃ­as", len(df_inv_h2))
            _ai2.metric("Con diferencia", int((df_inv_h2["diferencia"] != 0).sum()))
            _ai3.metric("Diferencia acumulada", f"{df_inv_h2['diferencia'].sum():,.1f}")
            st.dataframe(
                df_inv_h2.rename(columns={
                    "fecha_conteo":"Fecha","codigo":"CÃ³digo","producto":"Producto",
                    "deposito":"DepÃ³sito","stock_sistema":"Sistema","conteo_fisico":"Conteo",
                    "diferencia":"Dif","observaciones":"Notas"
                }),
                use_container_width=True, hide_index=True
            )
            st.download_button("ðŸ“¥ Exportar auditorÃ­as (.xlsx)",
                               data=to_excel_bytes(df_inv_h2, "Auditorias"),
                               file_name=f"auditorias_{datetime.now().strftime('%Y%m%d')}.xlsx")

    with _inv_tabs[4]:
        st.write("### ðŸ”€ Transferencia entre DepÃ³sitos")
        st.caption("Mover stock de un depÃ³sito a otro. Genera movimiento de Salida en origen y Entrada en destino.")
        if st_df.empty:
            st.info("Sin datos de stock.")
        else:
            _deps_tr = sorted(st_df["Deposito"].unique().tolist())
            _prods_tr = sorted(st_df["Producto"].unique().tolist())
            _tr1, _tr2 = st.columns(2)
            with _tr1:
                _prod_tr = st.selectbox("Producto", _prods_tr, key="tr_prod")
                _dep_orig_tr = st.selectbox("DepÃ³sito origen", _deps_tr, key="tr_orig")
                _dep_dest_tr = st.selectbox("DepÃ³sito destino", _deps_tr, key="tr_dest")
            with _tr2:
                _filt_tr = st_df[(st_df["Producto"]==_prod_tr) & (st_df["Deposito"]==_dep_orig_tr)]
                _stk_orig_tr = float(_filt_tr["Stock Actual"].sum()) if not _filt_tr.empty else 0.0
                st.metric("Stock disponible en origen", f"{_stk_orig_tr:,.1f}")
                _cant_tr = st.number_input("Cantidad a transferir", min_value=0.01,
                                           max_value=max(_stk_orig_tr, 0.01),
                                           step=1.0, key="tr_cant")
                _motivo_tr = st.text_input("Motivo / Referencia", key="tr_motivo",
                                           placeholder="ej: ReposiciÃ³n sucursal Las Varillas")
            if _dep_orig_tr == _dep_dest_tr:
                st.warning("El depÃ³sito de origen y destino deben ser distintos.")
            elif st.button("âœ… Confirmar Transferencia", type="primary", key="btn_tr"):
                if _cant_tr > 0:
                    conn = conectar_db()
                    _id_tr = conn.execute("SELECT id_producto FROM productos WHERE nombre=?",
                                         (_prod_tr,)).fetchone()
                    if _id_tr:
                        _ts_tr = datetime.now().strftime("%d/%m/%Y %H:%M")
                        _ref_tr = f"TRANSF: {_dep_orig_tr} â†’ {_dep_dest_tr}" + (f" | {_motivo_tr}" if _motivo_tr else "")
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
                        st.success(f"âœ… Transferidos {_cant_tr:,.1f} de {_prod_tr}: {_dep_orig_tr} â†’ {_dep_dest_tr}")
                        st.rerun()
                    else:
                        conn.close()
                        st.error("Producto no encontrado.")
                else:
                    st.warning("IngresÃ¡ una cantidad mayor a cero.")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 6 â€” HISTORIAL
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab6:
    st.subheader("ðŸ“œ Historial de Movimientos")
    _ult_h = obtener_metadata("ultima_importacion")
    if _ult_h: st.caption(f"ðŸ• Ãšltima importaciÃ³n de stock: **{_ult_h}**")
    hist_df = obtener_historial_movimientos()

    if hist_df.empty:
        st.info("Sin movimientos registrados.")
    else:
        # KPIs rÃ¡pidos
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
        with ch3: f_bus_h  = st.text_input("ðŸ” Buscar producto/lote")
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
            st.markdown(f"**{_total_h} movimientos** Â· {_total_pages_h} pÃ¡ginas")
        with _ph2:
            _page_h = st.number_input("PÃ¡gina", min_value=1, max_value=_total_pages_h,
                                      value=1, step=1, key="hist_page", label_visibility="collapsed")
        with _ph3:
            st.caption(f"pÃ¡g {_page_h}/{_total_pages_h}")
        df_hf_page = df_hf.iloc[(_page_h - 1) * _PAGE_H : _page_h * _PAGE_H]
        st.dataframe(df_hf_page, use_container_width=True, hide_index=True)

        if not df_hf.empty:
            _dh1, _dh2 = st.columns(2)
            with _dh1:
                st.download_button("ðŸ“¥ Exportar historial completo (.xlsx)",
                                   data=to_excel_bytes(df_hf, "Historial"),
                                   file_name=f"historial_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                   use_container_width=True)
            with _dh2:
                # Mini grÃ¡fico de actividad por dÃ­a
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
            with st.expander("ðŸ”„ Anular Movimiento"):
                id_an = st.number_input("ID del movimiento a anular", min_value=1, step=1, key="id_anular")
                if st.button("ðŸ”„ Anular", key="btn_anular"):
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
                                 f"ANULACIÃ“N de ID {id_an}: {row_an[5]}", row_an[4], "manual",
                                 usuario_actual()))
                            conn.execute("UPDATE movimientos SET anulado=1 WHERE id_movimiento=?", (int(id_an),))
                            conn.commit()
                            limpiar_cache()
                            st.success(f"âœ… Movimiento {id_an} anulado.")
                    else:
                        st.error(f"ID {id_an} no encontrado.")
                    conn.close()
                    st.rerun()

        # Trazabilidad por lote
        st.markdown("---")
        with st.expander("ðŸ” Trazabilidad por Lote"):
            st.caption("BuscÃ¡ un nÃºmero de lote y ves todos sus movimientos: de dÃ³nde vino y a dÃ³nde fue.")
            _lote_q = st.text_input("NÃºmero de lote", key="trz_lote_input",
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
                        _df_trz[["Fecha","Tipo","Producto","Cantidad","Unidad","Lote","DepÃ³sito","Referencia","Usuario","Anulado"]],
                        use_container_width=True, hide_index=True
                    )
                    st.download_button("ðŸ“¥ Exportar trazabilidad (.xlsx)",
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
            st.subheader("â†”ï¸ Historial de Transferencias")
            st.caption(f"{len(df_tr)} transferencias registradas")
            st.dataframe(df_tr, use_container_width=True, hide_index=True)
            st.download_button("ðŸ“¥ Exportar transferencias (.xlsx)",
                               data=to_excel_bytes(df_tr, "Transferencias"),
                               file_name=f"transferencias_{datetime.now().strftime('%Y%m%d')}.xlsx")

        if not df_inv_h.empty:
            st.markdown("---")
            st.subheader("ðŸ“‹ AuditorÃ­as de Inventario")
            df_inv_show = df_inv_h.rename(columns={
                "fecha_conteo":"Fecha","codigo":"CÃ³digo","producto":"Producto","deposito":"DepÃ³sito",
                "stock_sistema":"Sistema","conteo_fisico":"Conteo","diferencia":"Dif","observaciones":"Notas"
            })
            st.dataframe(df_inv_show, use_container_width=True, hide_index=True)
            st.download_button("ðŸ“¥ Exportar auditorÃ­as (.xlsx)",
                               data=to_excel_bytes(df_inv_show, "Auditorias"),
                               file_name=f"auditorias_{datetime.now().strftime('%Y%m%d')}.xlsx")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 7 â€” VALORIZACIÃ“N Y PRECIOS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab7:
    st.subheader("ðŸ’² ValorizaciÃ³n de Inventario")
    st.caption("AquÃ­ podÃ©s asignar precios a cada producto para calcular el valor total del inventario en USD y ARS.")
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
            if st.button("ðŸ’¾ Guardar TC"):
                guardar_metadata("tipo_cambio", str(tipo_cambio))
                st.success("Tipo de cambio actualizado.")

        st.markdown("---")
        st.write("### ðŸ·ï¸ Actualizar Precios por Producto")
        st.caption("EditÃ¡ directamente la tabla. Los precios se guardan al hacer clic en Guardar.")

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
            if st.button("ðŸ’¾ Guardar Precios", type="primary"):
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
                st.success("âœ… Precios actualizados.")
                st.rerun()

        st.markdown("---")
        st.write("### ðŸ“Š Inventario Valorizado")
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
            with cv_kpi1: st.metric("ðŸ’µ Valor Total USD", f"USD {total_usd:,.2f}")
            with cv_kpi2: st.metric("ðŸ’´ Valor Total ARS", f"ARS {total_ars:,.0f}")

            df_show = (stk_val[["Producto","Unidad","Stock Actual",
                                 "precio_unitario","moneda_precio","Valor_USD","Valor_ARS"]]
                       .sort_values("Valor_USD", ascending=False)
                       .rename(columns={
                           "precio_unitario":"Precio Unit.", "moneda_precio":"Moneda",
                           "Valor_USD":"Valor USD","Valor_ARS":"Valor ARS"
                       }))
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.download_button("ðŸ“¥ Exportar ValorizaciÃ³n",
                               data=to_excel_bytes(df_show, "ValorizaciÃ³n"),
                               file_name="valorizacion_stock.xlsx")

        st.markdown("---")
        st.write("### ðŸ’¹ Margen Bruto por Producto")
        st.caption("Cruza el precio de costo (valorizaciÃ³n) con el precio de venta (lista 2026) para estimar margen bruto.")
        lp_mg = obtener_lista_precios()
        if lp_mg.empty:
            st.info("CargÃ¡ la Lista de Precios 2026 en la pestaÃ±a ðŸ·ï¸ Lista de Precios para ver el margen.")
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
                st.info("AsignÃ¡ precios de costo en 'Actualizar Precios por Producto' para ver el margen.")
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
                st.download_button("ðŸ“¥ Exportar Margen Bruto (.xlsx)",
                                   data=to_excel_bytes(_stk_mg_show, "Margen"),
                                   file_name="margen_bruto.xlsx")

        st.markdown("---")
        st.write("### ðŸ›’ Orden de ReposiciÃ³n y Forecast")
        U_rep = st.session_state.umbral_alerta
        consumo_df = calcular_rotacion_stock()
        orden_bin  = generar_orden_reposicion(stk_full, U_rep, consumo_df)
        bajo_n_rep = len(stk_full[stk_full["Stock Actual"] < U_rep])

        _fc1, _fc2, _fc3 = st.columns(3)
        with _fc1:
            dias_fc = st.selectbox("Horizonte de forecast", [15, 30, 60, 90], index=1,
                                   help="DÃ­as hacia adelante para proyectar la necesidad de compra")
        with _fc2:
            st.metric("Productos bajo umbral", bajo_n_rep,
                       help=f"Tienen menos de {U_rep} unidades en stock")
        with _fc3:
            df_fc_now = calcular_forecast(dias_fc)
            st.metric("Necesitan reposiciÃ³n", len(df_fc_now),
                       help=f"Productos que se agotarÃ­an en los prÃ³ximos {dias_fc} dÃ­as")

        if not df_fc_now.empty:
            fig_fc = px.bar(
                df_fc_now.head(20).sort_values("Necesidad_Compra", ascending=True),
                x="Necesidad_Compra", y="Producto", orientation="h",
                title=f"Necesidad de compra â€” prÃ³ximos {dias_fc} dÃ­as",
                color="Necesidad_Compra", color_continuous_scale=["#ffc107","#dc3545"],
                labels={"Necesidad_Compra":"Unidades a reponer"}
            )
            fig_fc.update_layout(height=380, showlegend=False, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_fc, use_container_width=True)
            st.dataframe(
                df_fc_now[["Producto","Unidad","Stock Actual","Consumo_Proyectado","Necesidad_Compra","DÃ­as_Cobertura"]]
                .rename(columns={"Stock Actual":"Stock","Consumo_Proyectado":f"Consumo {dias_fc}d",
                                  "Necesidad_Compra":"A Reponer","DÃ­as_Cobertura":"DÃ­as Cob."}),
                use_container_width=True, hide_index=True
            )

        _or1, _or2, _or3 = st.columns(3)
        with _or1:
            st.download_button("ðŸ“¥ Orden de ReposiciÃ³n (.xlsx)",
                               data=orden_bin, file_name="orden_reposicion.xlsx",
                               use_container_width=True)
        with _or2:
            _oc_pdf = generar_orden_compra_pdf(
                df_fc_now if not df_fc_now.empty else pd.DataFrame(),
                proveedor="Bayer CropScience / Monsanto-Bayer"
            )
            if _oc_pdf:
                st.download_button("ðŸ–¨ï¸ Orden de Compra PDF",
                                   data=_oc_pdf, file_name="orden_compra.pdf",
                                   mime="application/pdf", use_container_width=True)
        with _or3:
            st.download_button("ðŸ“¥ Forecast (.xlsx)",
                               data=to_excel_bytes(df_fc_now, "Forecast") if not df_fc_now.empty else b"",
                               file_name=f"forecast_{dias_fc}d.xlsx",
                               use_container_width=True)

        # Historial de precios
        st.markdown("---")
        st.write("### ðŸ“ˆ Historial de Precios")
        conn = conectar_db()
        df_ph = _rsql("""
                SELECT ph.fecha "Fecha", p.nombre "Producto",
                       ph.precio "Precio", ph.moneda "Moneda", ph.usuario "Usuario"
                FROM precios_historicos ph JOIN productos p ON ph.id_producto=p.id_producto
                ORDER BY ph.id_precio DESC LIMIT 200""", conn)
        conn.close()
        if not df_ph.empty:
            prod_hist = st.selectbox("Producto para ver evoluciÃ³n",
                                     ["Todos"]+sorted(df_ph["Producto"].unique().tolist()),
                                     key="prod_hist")
            df_ph_f = df_ph if prod_hist=="Todos" else df_ph[df_ph["Producto"]==prod_hist]
            st.dataframe(df_ph_f, use_container_width=True, hide_index=True)
            if prod_hist != "Todos" and len(df_ph_f) > 1:
                fig_ph = px.line(df_ph_f.sort_values("Fecha"), x="Fecha", y="Precio",
                                 title=f"EvoluciÃ³n Precio â€” {prod_hist}")
                st.plotly_chart(fig_ph, use_container_width=True)
        else:
            st.caption("Sin historial de precios todavÃ­a.")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 8 â€” REPORTES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab8:
    st.subheader("ðŸ“ˆ Reportes y AnÃ¡lisis")
    r_tab1, r_tab2, r_tab3, r_tab4, r_tab5, r_tab6, r_tab7, r_tab8, r_tab9, r_tab10, r_tab11, r_tab12, r_tab13 = st.tabs([
        "ðŸ‘¥ Dashboard Vendedores",
        "ðŸ”„ RotaciÃ³n de Stock",
        "â° Vencimientos",
        "ðŸ“„ Reporte Mensual",
        "ðŸ“Š Resumen Ejecutivo",
        "â¸ï¸ Stock Inmovilizado",
        "âš¡ Eficiencia Entregas",
        "ðŸ† Ranking Clientes",
        "ðŸ“‰ ProyecciÃ³n de Quiebre",
        "ðŸ˜´ Clientes Sin Actividad",
        "ðŸ”® PredicciÃ³n de Demanda",
        "ðŸ’° Clientes mÃ¡s Rentables",
        "ðŸ—ºï¸ Producto por Zona",
    ])

    # â”€â”€ Vendedores â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab1:
        st.write("### ðŸ‘¥ Performance por Vendedor")
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

            # Pivot producto Ã— vendedor
            st.write("#### Pendiente por Producto Ã— Vendedor")
            pv2 = df_v[df_v["pendiente"] > 0].pivot_table(
                index="producto", columns="vendedor", values="pendiente",
                aggfunc="sum", fill_value=0
            ).reset_index()
            st.dataframe(pv2, use_container_width=True, hide_index=True)

    # â”€â”€ RotaciÃ³n â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab2:
        st.write("### ðŸ”„ RotaciÃ³n de Stock")
        st.caption("DÃ­as de cobertura = Stock actual Ã· Salidas promedio diarias (90 dÃ­as).")
        dias_h = st.slider("Ventana histÃ³rica (dÃ­as)", 30, 180, 90, key="dias_rot")
        df_rot = calcular_rotacion_stock(dias_h)
        if df_rot.empty:
            st.info("Sin movimientos suficientes para calcular rotaciÃ³n.")
        else:
            cr1, cr2, cr3 = st.columns(3)
            with cr1:
                sin_mov = len(df_rot[df_rot["DÃ­as_Cobertura"].isna()])
                st.metric("Sin movimiento", sin_mov)
            with cr2:
                crit_rot = len(df_rot[df_rot["DÃ­as_Cobertura"].notna() & (df_rot["DÃ­as_Cobertura"] < 30)])
                st.metric("Cobertura < 30d ðŸš¨", crit_rot)
            with cr3:
                ok_rot = len(df_rot[df_rot["DÃ­as_Cobertura"].notna() & (df_rot["DÃ­as_Cobertura"] >= 30)])
                st.metric("Cobertura OK âœ…", ok_rot)

            st.dataframe(
                df_rot.rename(columns={
                    "Total_Salidas":"Salidas 90d","Sal_Diarias":"Sal/DÃ­a",
                    "DÃ­as_Cobertura":"DÃ­as Cobertura","RotaciÃ³n_Anual":"RotaciÃ³n Anual"
                }),
                use_container_width=True, hide_index=True
            )

            df_rot_graf = df_rot[df_rot["DÃ­as_Cobertura"].notna()].sort_values("DÃ­as_Cobertura").head(20)
            if not df_rot_graf.empty:
                fig_rot = px.bar(df_rot_graf, x="DÃ­as_Cobertura", y="Producto",
                                 orientation="h", title="DÃ­as de Cobertura (Top 20 mÃ¡s crÃ­ticos)",
                                 color="DÃ­as_Cobertura", color_continuous_scale="RdYlGn")
                fig_rot.update_layout(height=500, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_rot, use_container_width=True)

            st.download_button("ðŸ“¥ Exportar RotaciÃ³n",
                               data=to_excel_bytes(df_rot, "Rotacion"),
                               file_name="rotacion_stock.xlsx")

    # â”€â”€ Vencimientos por Lote â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab3:
        st.write("### â° Control de Vencimientos por Lote")

        df_lotes = obtener_lotes_vencimiento()

        if df_lotes.empty:
            st.info("Sin datos de lotes. ImportÃ¡ el archivo de lotes desde **âš™ï¸ ConfiguraciÃ³n â†’ ImportaciÃ³n**.")
        else:
            # Calcular dÃ­as restantes
            def _dias_v(fv):
                if not fv: return None
                try:
                    return (datetime.strptime(str(fv)[:10], "%d/%m/%Y") - datetime.now()).days
                except Exception:
                    return None

            df_lotes["dias"] = df_lotes["fecha_vencimiento"].apply(_dias_v)

            def _sem_v(d):
                if d is None:   return "âšª Sin fecha"
                if d < 0:       return "ðŸ”´ Vencido"
                if d < 30:      return "ðŸŸ  CrÃ­tico"
                if d < 90:      return "ðŸŸ¡ PrÃ³ximo"
                return "ðŸŸ¢ OK"

            df_lotes["Estado"] = df_lotes["dias"].apply(_sem_v)

            # â”€â”€ KPIs globales â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _con_fecha = df_lotes[df_lotes["dias"].notna()]
            _lv1, _lv2, _lv3, _lv4, _lv5 = st.columns(5)
            _lv1.metric("Lotes totales",      len(df_lotes))
            _lv2.metric("ðŸ”´ Vencidos",        int((_con_fecha["dias"] < 0).sum()))
            _lv3.metric("ðŸŸ  CrÃ­ticos (<30d)", int(((_con_fecha["dias"] >= 0) & (_con_fecha["dias"] < 30)).sum()))
            _lv4.metric("ðŸŸ¡ PrÃ³ximos (30-90d)",int(((_con_fecha["dias"] >= 30) & (_con_fecha["dias"] < 90)).sum()))
            _lv5.metric("ðŸŸ¢ OK",              int((_con_fecha["dias"] >= 90).sum()))

            # Alerta inmediata si hay vencidos con stock positivo
            _venc_con_stock = df_lotes[(df_lotes["dias"].notna()) &
                                       (df_lotes["dias"] < 0) &
                                       (df_lotes["stock"] > 0)]
            if not _venc_con_stock.empty:
                st.error(f"ðŸš¨ **{len(_venc_con_stock)} lotes VENCIDOS con stock positivo** â€” "
                         f"requieren revisiÃ³n urgente. Stock total involucrado: "
                         f"{_venc_con_stock['stock'].sum():,.1f}")

            st.markdown("---")

            # â”€â”€ Filtros â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _fl1, _fl2, _fl3 = st.columns([2, 2, 2])
            with _fl1:
                _est_opts = ["Todos", "ðŸ”´ Vencido", "ðŸŸ  CrÃ­tico", "ðŸŸ¡ PrÃ³ximo", "ðŸŸ¢ OK", "âšª Sin fecha"]
                _est_fil  = st.selectbox("Estado", _est_opts, key="venc_est_fil")
            with _fl2:
                _prods_v  = ["Todos"] + sorted(df_lotes["producto"].dropna().unique().tolist())
                _prod_fil = st.selectbox("Producto", _prods_v, key="venc_prod_fil")
            with _fl3:
                _dias_max = st.number_input("Mostrar vencimientos en prÃ³ximos N dÃ­as (0 = todos)",
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

            # â”€â”€ Vista agrupada por Producto â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                            "Stock_Total": "Stock Total", "Venc_Minima": "DÃ­as al prÃ³ximo venc."
                        }))

                def _sem_row(row):
                    if row["Vencido"] > 0:   return "ðŸ”´ Tiene vencidos"
                    if row["Critico"] > 0:   return "ðŸŸ  CrÃ­tico"
                    if row["Proximo"] > 0:   return "ðŸŸ¡ PrÃ³ximo"
                    return "ðŸŸ¢ OK"

                _grp["Estado General"] = _grp.apply(_sem_row, axis=1)
                _grp = _grp.sort_values("DÃ­as al prÃ³ximo venc.", na_position="last")

                st.dataframe(
                    _grp[["Producto","Unidad","Lotes","Stock Total",
                           "Vencido","Critico","Proximo","DÃ­as al prÃ³ximo venc.","Estado General"]],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Stock Total":              st.column_config.NumberColumn(format="%.1f"),
                        "DÃ­as al prÃ³ximo venc.":    st.column_config.NumberColumn(format="%d"),
                    }
                )
                st.download_button("ðŸ“¥ Exportar resumen (.xlsx)",
                                   data=to_excel_bytes(_grp, "Resumen_Vencimientos"),
                                   file_name=f"venc_resumen_{datetime.now().strftime('%Y%m%d')}.xlsx")

            else:  # Detalle por lote
                _show = df_v[["producto","unidad","deposito","lote","stock",
                               "fecha_vencimiento","fecha_fabricacion","dias","Estado"]].rename(columns={
                    "producto":"Producto","unidad":"Unidad","deposito":"DepÃ³sito",
                    "lote":"Lote","stock":"Stock","fecha_vencimiento":"Vence",
                    "fecha_fabricacion":"FabricaciÃ³n","dias":"DÃ­as restantes","Estado":"Estado"
                })
                st.dataframe(
                    _show,
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Stock":           st.column_config.NumberColumn(format="%.2f"),
                        "DÃ­as restantes":  st.column_config.NumberColumn(format="%d"),
                    }
                )
                st.download_button("ðŸ“¥ Exportar detalle (.xlsx)",
                                   data=to_excel_bytes(_show, "Detalle_Lotes"),
                                   file_name=f"venc_detalle_{datetime.now().strftime('%Y%m%d')}.xlsx")

            # â”€â”€ Exportar lotes vencidos para baja â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _lv_para_baja = df_v[df_v["Estado"] == "ðŸ”´ Vencido"].copy()
            if not _lv_para_baja.empty:
                st.markdown("---")
                st.warning(f"**{len(_lv_para_baja)} lotes vencidos** con stock total "
                           f"{_lv_para_baja['stock'].sum():,.1f} unidades.")
                st.download_button("ðŸ“‹ Exportar lotes vencidos para gestiÃ³n de baja",
                                   data=generar_venc_excel_baja(_lv_para_baja),
                                   file_name=f"lotes_vencidos_{datetime.now().strftime('%Y%m%d')}.xlsx")

            # â”€â”€ QR por lote â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            with st.expander("ðŸ·ï¸ Generar QR de lote", expanded=False):
                _qr_cols = st.columns(4)
                with _qr_cols[0]:
                    _qr_prod = st.selectbox("Producto", sorted(df_lotes["producto"].dropna().unique()),
                                            key="qr_prod")
                _lotes_del_prod = df_lotes[df_lotes["producto"] == _qr_prod]
                with _qr_cols[1]:
                    _qr_lote = st.selectbox("Lote", _lotes_del_prod["lote"].fillna("S/L").unique(),
                                            key="qr_lote")
                with _qr_cols[2]:
                    _qr_dep  = st.text_input("DepÃ³sito", key="qr_dep")
                with _qr_cols[3]:
                    _qr_row  = _lotes_del_prod[_lotes_del_prod["lote"] == _qr_lote]
                    _qr_venc = _qr_row["fecha_vencimiento"].iloc[0] if not _qr_row.empty else ""
                    st.text_input("Vencimiento", value=str(_qr_venc), disabled=True, key="qr_venc_disp")
                if st.button("ðŸ“² Generar QR", key="btn_qr_lote"):
                    _qr_bytes = generar_qr_lote(_qr_prod, _qr_lote, str(_qr_venc), _qr_dep)
                    if _qr_bytes:
                        st.image(_qr_bytes, width=200, caption=f"{_qr_prod} Â· {_qr_lote}")
                        st.download_button("â¬‡ï¸ Descargar QR (.png)", data=_qr_bytes,
                                           file_name=f"qr_{_qr_lote}.png", mime="image/png")

            # â”€â”€ Timeline de vencimientos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            st.markdown("---")
            st.write("#### ðŸ“… Timeline: Stock que vence por mes")
            _tl = generar_vencimientos_timeline()
            if not _tl.empty:
                _hoy_mes = datetime.now().strftime("%Y-%m")
                _tl_fut  = _tl[_tl["Mes"] >= _hoy_mes]
                _tl_grp  = _tl_fut.groupby("Mes")["Stock"].sum().reset_index()
                if not _tl_grp.empty:
                    _fig_tl = px.bar(_tl_grp, x="Mes", y="Stock",
                                     title="Unidades que vencen por mes (prÃ³ximos meses)",
                                     color="Stock",
                                     color_continuous_scale=["#28a745","#ffc107","#dc3545"],
                                     labels={"Stock":"Unidades","Mes":"Mes"})
                    _fig_tl.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0),
                                          showlegend=False)
                    st.plotly_chart(_fig_tl, use_container_width=True)

                    # Top productos que mÃ¡s vencen en prÃ³ximos 90d
                    _90d = datetime.now()
                    _tl_90 = _tl_fut[_tl_fut["Mes"] <= (_90d.replace(month=min(_90d.month+3,12)
                                                         ).strftime("%Y-%m"))]
                    if not _tl_90.empty:
                        _top_venc = (_tl_90.groupby("Producto")["Stock"].sum()
                                     .reset_index().sort_values("Stock", ascending=False).head(10))
                        st.caption("**Top 10 productos con mÃ¡s stock venciendo en 90 dÃ­as:**")
                        st.dataframe(_top_venc, use_container_width=True, hide_index=True)

            # â”€â”€ ConciliaciÃ³n Sistema vs Lotes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            st.markdown("---")
            with st.expander("âš–ï¸ ConciliaciÃ³n: Stock Sistema vs Lotes Importados", expanded=False):
                st.caption("Compara el stock calculado por movimientos contra la suma de lotes de MacroGest.")
                _conc = conciliar_stock_vs_lotes()
                if _conc.empty:
                    st.info("NecesitÃ¡s tener stock y lotes importados para ver la conciliaciÃ³n.")
                else:
                    _cc1, _cc2, _cc3 = st.columns(3)
                    _cc1.metric("Productos coinciden", int((_conc["Estado"] == "âœ… Coincide").sum()))
                    _cc2.metric("Sobrante en sistema", int((_conc["Estado"] == "ðŸ“ˆ Sobrante en sistema").sum()))
                    _cc3.metric("Faltante en sistema", int((_conc["Estado"] == "ðŸ“‰ Faltante en sistema").sum()))
                    _conc_fil = st.radio("Filtrar", ["Todos","Solo diferencias"],
                                         horizontal=True, key="conc_fil")
                    _df_conc_show = (_conc if _conc_fil == "Todos"
                                     else _conc[_conc["Estado"] != "âœ… Coincide"])
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
                    st.download_button("ðŸ“¥ Exportar conciliaciÃ³n (.xlsx)",
                                       data=to_excel_bytes(_conc, "Conciliacion"),
                                       file_name=f"conciliacion_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # â”€â”€ Resumen Ejecutivo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab5:
        st.write("### ðŸ“Š Resumen Ejecutivo")
        st.caption(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} Â· La Clementina S.A.")
        _re_stock = obtener_stock_con_compromisos()
        _re_ent   = obtener_entregas()
        _re_mg    = obtener_entregas("MACROGEST")
        _re_U     = st.session_state.umbral_alerta

        if not _re_stock.empty:
            # KPIs principales
            st.markdown("#### ðŸ“¦ Stock")
            _ek1,_ek2,_ek3,_ek4,_ek5,_ek6 = st.columns(6)
            with _ek1: st.metric("Productos",     _re_stock["Producto"].nunique())
            with _ek2: st.metric("DepÃ³sitos",     _re_stock["Deposito"].nunique())
            with _ek3: st.metric("Vol. Total",    f"{_re_stock['Stock Actual'].sum():,.0f}")
            with _ek4: st.metric("Bajo umbral ðŸŸ¡", int((_re_stock["Stock Actual"].between(0, _re_U, inclusive="left")).sum()))
            with _ek5: st.metric("Negativo ðŸ”´",   int((_re_stock["Stock Actual"] < 0).sum()))
            with _ek6: st.metric("Comprometido ðŸŸ ", int((_re_stock["Disponible Neto"] < 0).sum()))

            # Stock crÃ­tico
            _crit = _re_stock[_re_stock["Stock Actual"] < _re_U].sort_values("Stock Actual").head(10)
            if not _crit.empty:
                st.markdown("**ðŸš¨ Productos crÃ­ticos (bajo umbral o negativos)**")
                st.dataframe(_crit[["Producto","Deposito","Stock Actual","Comprometido","Disponible Neto"]],
                             use_container_width=True, hide_index=True)

        if not _re_ent.empty:
            st.markdown("---")
            st.markdown("#### ðŸ“‹ Entregas")
            _ee_pend = _re_ent[_re_ent["pendiente"] > 0]
            _ee_dias = (_ee_pend["dia_recibido"].apply(dias_desde)
                        if "dia_recibido" in _ee_pend.columns
                        else pd.Series(0, index=_ee_pend.index))
            _ee1,_ee2,_ee3,_ee4 = st.columns(4)
            with _ee1: st.metric("Registros pendientes", len(_ee_pend))
            with _ee2: st.metric("Clientes",             _ee_pend["cliente"].nunique())
            with _ee3: st.metric("Vol. pendiente",       f"{_ee_pend['pendiente'].sum():,.0f}")
            with _ee4: st.metric("+30 dÃ­as â³",           int((_ee_dias > 30).sum()))

        if not _re_mg.empty:
            st.markdown("---")
            st.markdown("#### ðŸ”„ Sin Entregar MacroGest")
            _em_pend = _re_mg[_re_mg["pendiente"] > 0]
            _em1,_em2,_em3 = st.columns(3)
            with _em1: st.metric("Pedidos pendientes", len(_em_pend))
            with _em2: st.metric("Clientes",           _em_pend["cliente"].nunique())
            with _em3: st.metric("Vol. pendiente",     f"{_em_pend['pendiente'].sum():,.0f}")

        # Descarga todo en un solo Excel + PDF
        st.markdown("---")
        _dej1, _dej2 = st.columns(2)
        with _dej1:
            if st.button("ðŸ“¥ Excel Ejecutivo (.xlsx)", type="primary"):
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
                        "Indicador": ["Fecha","Productos","DepÃ³sitos","Stock Negativo","Bajo Umbral",
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
                st.download_button("â¬‡ï¸ Descargar Excel",
                                   data=_out_ej.getvalue(),
                                   file_name=f"ejecutivo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with _dej2:
            if PDF_AVAILABLE:
                if st.button("ðŸ“„ PDF Ejecutivo con Logo LC"):
                    _pdf_ej = generar_ejecutivo_pdf()
                    if _pdf_ej:
                        st.download_button("â¬‡ï¸ Descargar PDF",
                                           data=_pdf_ej,
                                           file_name=f"ejecutivo_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                           mime="application/pdf")
            else:
                st.caption("PDF: `pip install reportlab`")

    # â”€â”€ Reporte Mensual â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab4:
        st.write("### ðŸ“„ Reporte Mensual Consolidado")
        rm1, rm2 = st.columns(2)
        with rm1:
            reporte_excel = generar_reporte_excel()
            st.download_button("ðŸ“¥ Descargar Reporte Excel (.xlsx)",
                               data=reporte_excel,
                               file_name=f"reporte_{datetime.now().strftime('%Y%m')}.xlsx")
        with rm2:
            if PDF_AVAILABLE:
                pdf_bytes = generar_reporte_pdf()
                if pdf_bytes:
                    st.download_button("ðŸ“¥ Descargar Reporte PDF",
                                       data=pdf_bytes,
                                       file_name=f"reporte_{datetime.now().strftime('%Y%m')}.pdf",
                                       mime="application/pdf")
            else:
                st.warning("PDF no disponible. Instalar: `pip install reportlab`")

        # Email
        st.markdown("---")
        st.write("### ðŸ“§ Enviar Alerta por Email")
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
        if st.button("ðŸ“§ Enviar Email de Alerta"):
            ok_em, msg_em = enviar_email_alerta(stk_bajo, pend_30)
            st.success(msg_em) if ok_em else st.error(msg_em)

    # â”€â”€ Stock Inmovilizado â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab6:
        st.write("### â¸ï¸ Stock Inmovilizado")
        st.caption("Productos sin ningÃºn movimiento de salida en los Ãºltimos N dÃ­as. Stock que no rota y ocupa espacio o genera costo financiero.")
        _dias_inm = st.slider("DÃ­as sin movimiento", min_value=30, max_value=365, value=90, step=15,
                               help="PerÃ­odo de anÃ¡lisis: si un producto no tuvo salidas en estos dÃ­as, se considera inmovilizado.")
        _hist_inm = obtener_historial_movimientos()
        _stk_inm  = obtener_stock_full()
        if _hist_inm.empty or _stk_inm.empty:
            st.info("Sin datos suficientes para el anÃ¡lisis.")
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

            # Ãšltima salida por producto
            _ult_sal = (
                _hist_sal.groupby("Producto")["_dt"].max().reset_index()
                .rename(columns={"_dt":"Ãšltima Salida"})
            )
            _ult_sal["Ãšltima Salida"] = _ult_sal["Ãšltima Salida"].apply(
                lambda d: d.strftime("%d/%m/%Y") if d else "Sin salidas"
            )
            _stk_inm_f = _stk_inm_f.merge(_ult_sal, on="Producto", how="left")
            _stk_inm_f["Ãšltima Salida"] = _stk_inm_f["Ãšltima Salida"].fillna("Sin salidas")

            _in1, _in2, _in3 = st.columns(3)
            _in1.metric("Productos inmovilizados", len(_stk_inm_f))
            _in2.metric("% del catÃ¡logo",
                        f"{len(_stk_inm_f)/max(1,len(_todos_prods))*100:.1f}%")
            _in3.metric("Stock total inmovilizado",
                        f"{_stk_inm_f['Stock Actual'].sum():,.0f}")

            if not _stk_inm_f.empty:
                fig_inm = px.bar(
                    _stk_inm_f.sort_values("Stock Actual", ascending=False).head(20),
                    x="Producto", y="Stock Actual",
                    title=f"Top 20 â€” Productos sin salidas en {_dias_inm} dÃ­as",
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
                st.download_button("ðŸ“¥ Exportar Inmovilizado (.xlsx)",
                                   data=to_excel_bytes(_stk_inm_f, "Inmovilizado"),
                                   file_name=f"inmovilizado_{datetime.now().strftime('%Y%m%d')}.xlsx")
            else:
                st.success(f"âœ… Todos los productos tuvieron movimientos en los Ãºltimos {_dias_inm} dÃ­as.")

    # â”€â”€ Eficiencia de Entregas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab7:
        st.write("### âš¡ Eficiencia de Entregas")
        st.caption("Tiempo promedio entre la fecha de recepciÃ³n del pedido y la confirmaciÃ³n de entrega, por vendedor y producto.")
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
            _ef3.metric("DÃ­as prom. en espera", f"{_prom_dias_g:.1f}")
            _ef4.metric("Confirmadas",
                        len(_ent_conf) if not _ent_conf.empty else "â€”")

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
                        labels={"DiasPromedio":"DÃ­as promedio","vendedor":"Vendedor"},
                        title="DÃ­as promedio en cola por vendedor"
                    )
                    fig_vend_ef.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0), showlegend=False)
                    st.plotly_chart(fig_vend_ef, use_container_width=True)
                    st.dataframe(
                        _by_vend.rename(columns={"vendedor":"Vendedor","DiasPromedio":"DÃ­as Prom."}),
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
                        _by_prod_ef.rename(columns={"producto":"Producto","DiasPromedio":"DÃ­as Prom."}),
                        use_container_width=True, hide_index=True
                    )
                    st.download_button("ðŸ“¥ Exportar eficiencia (.xlsx)",
                                       data=to_excel_bytes(_by_prod_ef, "Eficiencia"),
                                       file_name=f"eficiencia_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # â”€â”€ Ranking de Clientes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab8:
        st.write("### ðŸ† Ranking de Clientes")
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
            st.download_button("ðŸ“¥ Exportar ranking (.xlsx)",
                               data=to_excel_bytes(_rk, "Ranking_Clientes"),
                               file_name=f"ranking_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # â”€â”€ ProyecciÃ³n de Quiebre de Stock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab9:
        st.write("### ðŸ“‰ ProyecciÃ³n de Quiebre de Stock")
        st.caption("Estima cuÃ¡ntos dÃ­as quedan de stock por producto segÃºn el ritmo de salidas de los Ãºltimos 30 dÃ­as.")
        _hist_qb = obtener_historial_movimientos()
        _stk_qb  = obtener_stock_full()
        if _hist_qb.empty or _stk_qb.empty:
            st.info("Sin datos suficientes para calcular proyecciÃ³n.")
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
            _df_qb["DÃ­as_Quiebre"] = _df_qb.apply(
                lambda r: round(r["Stock Actual"] / r["Tasa_Diaria"]) if r["Tasa_Diaria"] > 0 else None, axis=1
            )

            def _sem_qb(d):
                if d is None: return "âšª Sin movimiento"
                if d < 15:    return "ðŸ”´ CrÃ­tico (<15d)"
                if d < 30:    return "ðŸŸ¡ AtenciÃ³n (15-30d)"
                return "ðŸŸ¢ OK (>30d)"

            _df_qb["Estado"] = _df_qb["DÃ­as_Quiebre"].apply(_sem_qb)
            _df_qb = _df_qb[_df_qb["Salidas_30d"] > 0].sort_values(
                "DÃ­as_Quiebre", ascending=True, na_position="last"
            )

            _qb1, _qb2, _qb3 = st.columns(3)
            _qb1.metric("ðŸ”´ CrÃ­ticos (<15d)",    int((_df_qb["Estado"]=="ðŸ”´ CrÃ­tico (<15d)").sum()))
            _qb2.metric("ðŸŸ¡ AtenciÃ³n (15-30d)",  int((_df_qb["Estado"]=="ðŸŸ¡ AtenciÃ³n (15-30d)").sum()))
            _qb3.metric("ðŸŸ¢ OK",                 int((_df_qb["Estado"]=="ðŸŸ¢ OK (>30d)").sum()))

            st.dataframe(
                _df_qb[["Estado","Producto","Unidad","Stock Actual","Tasa_Diaria","DÃ­as_Quiebre"]]
                .rename(columns={"Stock Actual":"Stock","Tasa_Diaria":"Sal/dÃ­a","DÃ­as_Quiebre":"DÃ­as al quiebre"}),
                use_container_width=True, hide_index=True
            )
            st.download_button("ðŸ“¥ Exportar proyecciÃ³n (.xlsx)",
                               data=to_excel_bytes(_df_qb, "Proyeccion_Quiebre"),
                               file_name=f"proyeccion_quiebre_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # â”€â”€ Clientes Sin Actividad â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with r_tab10:
        st.write("### ðŸ˜´ Clientes Sin Actividad")
        st.caption(
            "Clientes con historial en La Clementina (LA CLEMENTINA S.A) "
            "que NO tienen pedidos en la campaÃ±a actual (MACROGEST)."
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
                st.success("Todos los clientes histÃ³ricos tienen al menos un pedido en MacroGest.")
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
                    "Ultima_Compra":"Ãšltima Compra",
                    "Total_Comprado":"Total Comprado",
                }).sort_values("Ãšltima Compra", ascending=False)

                st.metric("Clientes sin actividad en campaÃ±a actual", len(_agg_cs))
                st.dataframe(_agg_cs, use_container_width=True, hide_index=True)
                st.download_button(
                    "ðŸ“¥ Exportar clientes sin actividad (.xlsx)",
                    data=to_excel_bytes(_agg_cs, "Clientes_Sin_Actividad"),
                    file_name=f"clientes_sin_actividad_{datetime.now().strftime('%Y%m%d')}.xlsx"
                )

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # R_TAB 11 â€” PREDICCIÃ“N DE DEMANDA
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with r_tab11:
        st.write("### ðŸ”® PredicciÃ³n de Demanda")
        st.caption("EstimaciÃ³n del volumen de ventas del prÃ³ximo mes basada en el historial de movimientos.")

        _hist_pred = obtener_historial_movimientos()
        if _hist_pred.empty:
            st.info("Sin historial de movimientos para calcular predicciones.")
        else:
            _hp = _hist_pred[_hist_pred["Anulado"] == 0].copy()
            _hp["_fecha"] = pd.to_datetime(_hp["Fecha"], dayfirst=True, errors="coerce")
            _hp["_mes"]   = _hp["_fecha"].dt.to_period("M").astype(str)
            _hp_sal = _hp[_hp["Tipo"] == "Salida"].dropna(subset=["_mes"])

            _prod_pred = st.selectbox("Producto a predecir",
                                      ["Todos"] + sorted(_hp_sal["Producto"].dropna().unique().tolist()),
                                      key="pred_prod")
            if _prod_pred != "Todos":
                _hp_sal = _hp_sal[_hp_sal["Producto"] == _prod_pred]

            _sal_mes = (_hp_sal.groupby("_mes")["Cantidad"].sum()
                        .reset_index().sort_values("_mes"))
            _sal_mes.columns = ["Mes", "Salidas"]

            if len(_sal_mes) < 2:
                st.warning("Se necesitan al menos 2 meses de historial para predecir.")
            else:
                # Promedio mÃ³vil 3 meses como predicciÃ³n simple
                _sal_mes["Promedio 3M"] = _sal_mes["Salidas"].rolling(3, min_periods=1).mean().round(0)
                _pred_val = _sal_mes["Promedio 3M"].iloc[-1]
                _prev_val = _sal_mes["Salidas"].iloc[-1]
                _var_pct  = (_pred_val - _prev_val) / _prev_val * 100 if _prev_val > 0 else 0

                _pc1, _pc2, _pc3 = st.columns(3)
                _pc1.metric("Ãšltimo mes real",    f"{_prev_val:,.0f} uds")
                _pc2.metric("PredicciÃ³n prÃ³x. mes", f"{_pred_val:,.0f} uds",
                            delta=f"{_var_pct:+.1f}%",
                            delta_color="normal")
                _pc3.metric("Promedio histÃ³rico", f"{_sal_mes['Salidas'].mean():,.0f} uds")

                # GrÃ¡fico con predicciÃ³n
                _fig_pred = go.Figure()
                _fig_pred.add_trace(go.Bar(
                    x=_sal_mes["Mes"], y=_sal_mes["Salidas"],
                    name="Salidas reales", marker_color=_LC_NAVY
                ))
                _fig_pred.add_trace(go.Scatter(
                    x=_sal_mes["Mes"], y=_sal_mes["Promedio 3M"],
                    name="Promedio mÃ³vil 3M", mode="lines+markers",
                    line=dict(color=_LC_YELLOW, width=2, dash="dash")
                ))
                # Punto de predicciÃ³n
                _mes_pred = (pd.Period(_sal_mes["Mes"].iloc[-1], "M") + 1).strftime("%Y-%m")
                _fig_pred.add_trace(go.Scatter(
                    x=[_mes_pred], y=[_pred_val],
                    name="PredicciÃ³n", mode="markers",
                    marker=dict(color="#68d391", size=14, symbol="star")
                ))
                _fig_pred.update_layout(
                    title=f"Historial + PredicciÃ³n â€” {'Todos' if _prod_pred=='Todos' else _prod_pred}",
                    height=380, margin=dict(l=10,r=10,t=40,b=10),
                    legend=dict(orientation="h", y=-0.2),
                    paper_bgcolor="rgba(0,0,0,0)", font_color="#FAFAFA",
                    plot_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(_fig_pred, use_container_width=True)

                # Tabla de predicciones para todos los productos
                st.markdown("#### ðŸ“‹ PredicciÃ³n por producto")
                _all_pred = []
                for _pp in _hp[_hp["Tipo"]=="Salida"]["Producto"].dropna().unique():
                    _pp_mes = (_hp[(_hp["Tipo"]=="Salida") & (_hp["Producto"]==_pp)]
                               .groupby("_mes")["Cantidad"].sum())
                    if len(_pp_mes) >= 2:
                        _pp_pred  = round(_pp_mes.rolling(3, min_periods=1).mean().iloc[-1], 0)
                        _pp_real  = _pp_mes.iloc[-1]
                        _pp_var   = round((_pp_pred - _pp_real) / _pp_real * 100, 1) if _pp_real > 0 else 0
                        _all_pred.append({
                            "Producto": _pp,
                            "Ãšltimo mes": int(_pp_real),
                            "PredicciÃ³n": int(_pp_pred),
                            "VariaciÃ³n %": f"{_pp_var:+.1f}%",
                            "Tendencia": "ðŸ“ˆ Sube" if _pp_var > 5 else ("ðŸ“‰ Baja" if _pp_var < -5 else "âž¡ï¸ Estable")
                        })
                if _all_pred:
                    _df_pred_tbl = pd.DataFrame(_all_pred).sort_values("PredicciÃ³n", ascending=False)
                    st.dataframe(_df_pred_tbl, use_container_width=True, hide_index=True)
                    st.download_button("ðŸ“¥ Exportar predicciones",
                                       data=to_excel_bytes(_df_pred_tbl, "Prediccion"),
                                       file_name=f"prediccion_demanda_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                       key="dl_pred")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # R_TAB 12 â€” CLIENTES MÃS RENTABLES
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with r_tab12:
        st.write("### ðŸ’° Clientes mÃ¡s Rentables")
        st.caption("Ranking de clientes por importe total comprado en la campaÃ±a actual.")

        _df_vd_rent = obtener_ventas_detalle()
        if _df_vd_rent.empty:
            st.info("Sin datos de ventas. ImportÃ¡ desde Plan Comercial â†’ Cartera de Clientes.")
        else:
            _camp_opts = sorted(_df_vd_rent["campana"].dropna().unique().tolist(), reverse=True)
            _camp_sel  = st.selectbox("CampaÃ±a", _camp_opts, key="rent_camp")
            _df_rent   = _df_vd_rent[_df_vd_rent["campana"] == _camp_sel].copy()

            _rank_rent = (_df_rent.groupby("cliente").agg(
                Importe_Total=("importe_total", "sum"),
                Cantidad_Total=("cantidad",     "sum"),
                Productos=("descripcion",       "nunique"),
                Pedidos=("numero_pedido",       "nunique"),
                Entregado=("entregada",         "sum"),
            ).reset_index()
            .rename(columns={"cliente":"Cliente"})
            .sort_values("Importe_Total", ascending=False))

            _rank_rent["% Entregado"] = (
                _rank_rent["Entregado"] / _rank_rent["Cantidad_Total"].replace(0,1) * 100
            ).round(1).astype(str) + "%"
            _rank_rent["Importe USD"] = _rank_rent["Importe_Total"].apply(lambda x: f"USD {x:,.0f}")
            _rank_rent["#"] = range(1, len(_rank_rent)+1)

            # KPIs top
            _rk1, _rk2, _rk3, _rk4 = st.columns(4)
            _rk1.metric("Total clientes",   len(_rank_rent))
            _rk2.metric("FacturaciÃ³n total", f"USD {_rank_rent['Importe_Total'].sum():,.0f}")
            _rk3.metric("Top cliente",       _rank_rent["Cliente"].iloc[0] if not _rank_rent.empty else "-")
            _rk4.metric("Ticket promedio",   f"USD {_rank_rent['Importe_Total'].mean():,.0f}")

            # GrÃ¡fico top 15
            _fig_rent = px.bar(
                _rank_rent.head(15),
                x="Importe_Total", y="Cliente", orientation="h",
                color="Importe_Total",
                color_continuous_scale=[_LC_NAVY, _LC_YELLOW],
                text="Importe USD",
                title=f"Top 15 Clientes por Importe â€” CampaÃ±a {_camp_sel}"
            )
            _fig_rent.update_traces(textposition="outside")
            _fig_rent.update_layout(
                yaxis={"categoryorder":"total ascending"},
                height=480, margin=dict(l=10,r=10,t=40,b=10),
                coloraxis_showscale=False,
                paper_bgcolor="rgba(0,0,0,0)", font_color="#FAFAFA",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(_fig_rent, use_container_width=True)

            # Pareto â€” cuÃ¡ntos clientes concentran el 80% de la facturaciÃ³n
            _rank_rent["Acum %"] = (_rank_rent["Importe_Total"].cumsum() /
                                     _rank_rent["Importe_Total"].sum() * 100).round(1)
            _pareto80 = len(_rank_rent[_rank_rent["Acum %"] <= 80])
            st.info(f"ðŸ“Š **Ley de Pareto:** {_pareto80} clientes concentran el 80% de la facturaciÃ³n ({_pareto80}/{len(_rank_rent)} = {_pareto80/len(_rank_rent)*100:.0f}% de la cartera)")

            st.dataframe(
                _rank_rent[["#","Cliente","Importe USD","Cantidad_Total","Productos","% Entregado","Acum %"]],
                use_container_width=True, hide_index=True
            )
            st.download_button("ðŸ“¥ Exportar ranking",
                               data=to_excel_bytes(_rank_rent, "Ranking_Clientes"),
                               file_name=f"ranking_clientes_{_camp_sel}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                               key="dl_rank_rent")

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # R_TAB 13 â€” PRODUCTO POR ZONA
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with r_tab13:
        st.write("### ðŸ—ºï¸ Producto mÃ¡s vendido por Zona")
        st.caption("Cruce entre localidad del cliente y productos comprados. Identifica quÃ© se vende mÃ¡s en cada zona.")

        _df_vd_zona = obtener_ventas_detalle()
        if _df_vd_zona.empty:
            st.info("Sin datos de ventas. ImportÃ¡ desde Plan Comercial â†’ Cartera de Clientes.")
        else:
            _camp_zona = st.selectbox("CampaÃ±a", sorted(_df_vd_zona["campana"].dropna().unique(), reverse=True),
                                      key="zona_camp")
            _df_zona = _df_vd_zona[(_df_vd_zona["campana"] == _camp_zona) &
                                    (_df_vd_zona["localidad"].notna()) &
                                    (_df_vd_zona["localidad"] != "")].copy()

            if _df_zona.empty:
                st.warning("Sin datos de localidad en esta campaÃ±a. VerificÃ¡ que el campo Localidad estÃ© cargado al importar.")
            else:
                _zc1, _zc2 = st.columns(2)
                with _zc1:
                    _zona_sel = st.selectbox("Filtrar por localidad",
                                             ["Todas"] + sorted(_df_zona["localidad"].unique().tolist()),
                                             key="zona_loc")
                with _zc2:
                    _top_n_zona = st.slider("Top N productos", 5, 20, 10, key="zona_topn")

                _df_zona_f = _df_zona if _zona_sel == "Todas" else _df_zona[_df_zona["localidad"] == _zona_sel]

                # Heatmap zona Ã— producto
                _pivot = (_df_zona_f.groupby(["localidad","descripcion"])["cantidad"]
                          .sum().reset_index())
                _top_prods_zona = (_pivot.groupby("descripcion")["cantidad"].sum()
                                   .nlargest(_top_n_zona).index.tolist())
                _pivot_top = _pivot[_pivot["descripcion"].isin(_top_prods_zona)]
                _heat_df   = _pivot_top.pivot_table(index="localidad", columns="descripcion",
                                                     values="cantidad", aggfunc="sum", fill_value=0)

                if not _heat_df.empty:
                    _fig_heat = px.imshow(
                        _heat_df,
                        color_continuous_scale=["#0E1117", _LC_NAVY, _LC_YELLOW],
                        title=f"Volumen por Zona Ã— Producto â€” Top {_top_n_zona}",
                        aspect="auto",
                        text_auto=".0f"
                    )
                    _fig_heat.update_layout(
                        height=max(350, len(_heat_df) * 30),
                        margin=dict(l=10,r=10,t=40,b=10),
                        paper_bgcolor="rgba(0,0,0,0)", font_color="#FAFAFA",
                        coloraxis_colorbar=dict(title="Unidades")
                    )
                    st.plotly_chart(_fig_heat, use_container_width=True)

                # Ranking por localidad
                st.markdown("#### ðŸ† Producto lÃ­der por localidad")
                _lider_zona = (_df_zona_f.groupby(["localidad","descripcion"])["cantidad"]
                               .sum().reset_index()
                               .sort_values("cantidad", ascending=False)
                               .groupby("localidad").first()
                               .reset_index()
                               .rename(columns={"descripcion":"Producto lÃ­der","cantidad":"Unidades"})
                               .sort_values("Unidades", ascending=False))
                st.dataframe(_lider_zona, use_container_width=True, hide_index=True)

                # GrÃ¡fico barras apiladas top zonas
                _top_zonas = (_df_zona_f.groupby("localidad")["cantidad"].sum()
                              .nlargest(12).index.tolist())
                _df_stack = (_df_zona_f[_df_zona_f["localidad"].isin(_top_zonas) &
                                        _df_zona_f["descripcion"].isin(_top_prods_zona)]
                             .groupby(["localidad","descripcion"])["cantidad"].sum().reset_index())
                if not _df_stack.empty:
                    _fig_stack = px.bar(
                        _df_stack, x="localidad", y="cantidad", color="descripcion",
                        title="Top 12 Zonas â€” ComposiciÃ³n por Producto",
                        labels={"cantidad":"Unidades","localidad":"Localidad","descripcion":"Producto"},
                        barmode="stack"
                    )
                    _fig_stack.update_layout(
                        height=420, margin=dict(l=10,r=10,t=40,b=10),
                        legend=dict(orientation="h", y=-0.3),
                        paper_bgcolor="rgba(0,0,0,0)", font_color="#FAFAFA",
                        plot_bgcolor="rgba(0,0,0,0)"
                    )
                    st.plotly_chart(_fig_stack, use_container_width=True)

                st.download_button("ðŸ“¥ Exportar datos por zona",
                                   data=to_excel_bytes(_pivot_top, "Producto_Zona"),
                                   file_name=f"producto_zona_{_camp_zona}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                   key="dl_zona")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 9 â€” CONFIGURACIÃ“N
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab9:
    st.subheader("âš™ï¸ ConfiguraciÃ³n")
    cfg1, cfg2, cfg3, cfg4 = st.tabs([
        "ðŸ“¥ ImportaciÃ³n / ExportaciÃ³n", "ðŸ”§ ParÃ¡metros & Sistema",
        "âš™ï¸ Config JSON", "ðŸ“‹ Changelog"
    ])

    # â”€â”€ ImportaciÃ³n / ExportaciÃ³n â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with cfg1:
        # ImportaciÃ³n completa
        with st.expander("ðŸ“¥ Importar Stock desde MacroGest (reemplaza todo)", expanded=True):
            st.info("CSV/Excel con columnas: `codigo`, `descripcion_1`, `unidad_medida`, `deposito`, `lote`, `stock_actual`")
            arch_s = st.file_uploader("Archivo de stock", type=["csv","xlsx","xls"], key="up_stock")
            if arch_s:
                # â”€â”€ Preview de columnas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                try:
                    _df_prev = pd.read_csv(arch_s) if arch_s.name.endswith(".csv") else pd.read_excel(arch_s)
                    arch_s.seek(0)
                    st.caption(f"ðŸ“‹ Columnas detectadas: `{'`, `'.join(str(c) for c in _df_prev.columns)}`  |  {len(_df_prev)} filas")
                except Exception:
                    pass
            if arch_s:
                # Verificar duplicado por hash del archivo
                _file_bytes = arch_s.read(); arch_s.seek(0)
                _file_hash  = hashlib.sha1(_file_bytes).hexdigest()[:12]
                _hash_prev  = obtener_metadata("ultimo_hash_stock")
                if _hash_prev == _file_hash:
                    st.warning(f"âš ï¸ Este archivo ya fue importado anteriormente (hash: `{_file_hash}`). "
                               "PodÃ©s igualmente importarlo de nuevo si querÃ©s actualizar.")
            if arch_s and st.button("ðŸš€ IMPORTAR STOCK COMPLETO", type="primary", key="btn_imp_stock"):
                import traceback as _tb
                _prog = st.progress(0, "Leyendo archivo...")
                try:
                    arch_s.seek(0)
                    df_s = pd.read_csv(arch_s) if arch_s.name.endswith(".csv") else pd.read_excel(arch_s)
                    _prog.progress(15, f"Archivo leÃ­do: {len(df_s)} filas")
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
                    # Filtrar filas vÃ¡lidas
                    df_s["_nom"] = df_s["descripcion_1"].apply(safe_str)
                    df_validas = df_s[df_s["_nom"] != ""].copy()
                    _prog.progress(25, f"{len(df_validas)} filas vÃ¡lidas de {len(df_s)}")
                    if df_validas.empty:
                        raise ValueError("No hay filas con producto vÃ¡lido en el archivo.")
                    _prog.progress(30, "Limpiando datos anteriores...")
                    borrar_solo_importacion()
                    conn = conectar_db()
                    _total = len(df_validas)
                    _ts = datetime.now().strftime("%d/%m/%Y %H:%M")
                    _usu = usuario_actual()

                    # â”€â”€ Paso 1: preparar filas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

                    # â”€â”€ Paso 2: insertar productos Ãºnicos en batch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                    _prog.progress(45, "Insertando productos (batch)...")
                    productos_uniq = {r["nom"]: r for r in filas_raw}
                    prod_batch = [(p["nom"], p["uni"], p["cod"]) for p in productos_uniq.values()]
                    if IS_POSTGRES:
                        from psycopg2.extras import execute_values as _ev
                        _rc = conn._raw.cursor()
                        _ev(_rc,
                            "INSERT INTO productos (nombre,unidad,codigo) VALUES %s ON CONFLICT (nombre) DO NOTHING",
                            prod_batch)
                    else:
                        conn.cursor().executemany(
                            "INSERT OR IGNORE INTO productos (nombre,unidad,codigo) VALUES (?,?,?)",
                            prod_batch
                        )
                    conn.commit()
                    pa = len(prod_batch)

                    # â”€â”€ Paso 3: cargar mapa nombre â†’ id_producto â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                    _prog.progress(60, "Mapeando IDs de productos...")
                    noms_sql = ",".join(["?" if not IS_POSTGRES else "%s"] * len(productos_uniq))
                    id_map_rows = conn.execute(
                        f"SELECT id_producto, nombre FROM productos WHERE nombre IN ({noms_sql})",
                        list(productos_uniq.keys())
                    ).fetchall()
                    id_map = {r[1]: r[0] for r in id_map_rows}

                    # â”€â”€ Paso 4: insertar movimientos en batch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                    if IS_POSTGRES:
                        from psycopg2.extras import execute_values as _ev
                        _rc2 = conn._raw.cursor()
                        _ev(_rc2,
                            """INSERT INTO movimientos
                               (fecha_hora,tipo_movimiento,id_producto,cantidad,lote,
                                referencia,deposito,origen,usuario)
                               VALUES %s""",
                            mov_batch)
                    else:
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
                    _prog.progress(100, "Â¡Listo!")
                    guardar_metadata("ultima_importacion", datetime.now().strftime("%d/%m/%Y %H:%M"))
                    guardar_metadata("ultimo_hash_stock", _file_hash)
                    registrar_importacion_log("Stock Completo", arch_s.name, mo, _file_hash)
                    limpiar_cache()
                    st.session_state["stock_imp_ok"] = (
                        f"âœ… Stock importado: {pa} productos nuevos, {mo} lÃ­neas "
                        f"(de {_total} filas vÃ¡lidas)."
                    )
                    st.rerun()
                except Exception as ex:
                    _prog.empty()
                    st.error(f"âŒ Error durante la importaciÃ³n: {ex}")
                    st.code(_tb.format_exc(), language="python")
            # Mensaje persistente post-rerun
            if st.session_state.get("stock_imp_ok"):
                st.success(st.session_state.pop("stock_imp_ok"))
            # â”€â”€ DiagnÃ³stico rÃ¡pido DB â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            with st.expander("ðŸ” DiagnÃ³stico base de datos", expanded=False):
                if st.button("ðŸ”„ Verificar estado DB", key="btn_diag"):
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

        # â”€â”€ ImportaciÃ³n Lotes + Vencimientos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with st.expander("ðŸ“¦ Importar Lotes y Vencimientos (MacroGest)", expanded=False):
            st.info(
                "SubÃ­ el archivo de MacroGest con columnas: `codigo`, `descripcion_1`, "
                "`unidad_medida`, `deposito`, `serie` (lote), `antidad` (stock), "
                "`lote_vencimiento`, `lote_fabricacion`. "
                "**Reemplaza todos los lotes activos anteriores.**"
            )
            _df_lv_prev = obtener_lotes_vencimiento()
            if not _df_lv_prev.empty:
                st.caption(f"Actualmente: {len(_df_lv_prev):,} lotes cargados Â· "
                           f"Ãºltima importaciÃ³n: {_df_lv_prev['fecha_importacion'].iloc[0] if 'fecha_importacion' in _df_lv_prev.columns else 'â€”'}")

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
                    st.caption(f"ðŸ“‹ {len(_df_lv):,} filas Â· {_df_lv['descripcion_1'].nunique() if 'descripcion_1' in _df_lv.columns else '?'} productos Â· "
                               f"{_lv_con_v:,} lotes con fecha de vencimiento")
                    if st.button("ðŸš€ IMPORTAR LOTES", type="primary", key="btn_imp_lotes"):
                        _prog_lv = st.progress(0, "Procesando...")
                        try:
                            arch_lv.seek(0)
                            _df_lv2 = (pd.read_excel(arch_lv) if not arch_lv.name.endswith(".csv")
                                       else pd.read_csv(arch_lv))
                            _prog_lv.progress(30, "Importando lotes...")
                            _tot, _cv = importar_lotes_vencimiento(_df_lv2)
                            _prog_lv.progress(100, "Â¡Listo!")
                            registrar_importacion_log("Lotes/Vencimientos", arch_lv.name, _tot)
                            limpiar_cache()
                            st.success(f"âœ… {_tot:,} lotes importados Â· {_cv:,} con fecha de vencimiento.")
                            st.rerun()
                        except Exception as _ex_lv:
                            _prog_lv.empty()
                            st.error(f"Error: {_ex_lv}")
                except Exception as _ex_prev:
                    st.error(f"No se pudo leer el archivo: {_ex_prev}")

        # ImportaciÃ³n incremental
        with st.expander("ðŸ”„ ImportaciÃ³n Incremental (solo diferencias)"):
            st.info(
                "Calcula la diferencia entre el archivo nuevo y el stock actual, "
                "e inserta **solo los ajustes**. Preserva movimientos manuales."
            )
            arch_inc = st.file_uploader("Archivo MacroGest nuevo", type=["csv","xlsx","xls"], key="up_incr")
            if arch_inc and st.button("ðŸ”„ IMPORTAR INCREMENTAL", type="primary"):
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
                    st.success(f"âœ… {ajustes} ajustes incrementales aplicados.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

        # ExportaciÃ³n MacroGest
        with st.expander("ðŸ“¤ Exportar para reimportar en MacroGest"):
            stk_exp = obtener_stock_full()
            if not stk_exp.empty:
                exp_mg = exportar_macrogest_format(stk_exp)
                st.download_button("ðŸ“¥ Exportar formato MacroGest (.xlsx)",
                                   data=exp_mg, file_name="exportacion_macrogest.xlsx")
            else:
                st.info("Sin datos de stock.")

    # â”€â”€ ParÃ¡metros & Sistema â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with cfg2:
        st.write("### ðŸš¨ ParÃ¡metros Operativos")
        new_umbral = st.number_input("Umbral de Stock Bajo (global)", min_value=1,
                                     value=int(st.session_state.umbral_alerta),
                                     help="Nivel de stock a partir del cual se dispara la alerta amarilla (global).")
        new_wa     = st.text_input("WhatsApp (5493XXXXXXXXX)", value=st.session_state.wa_numero)
        cod_sup_cfg = st.text_input("CÃ³digo de supervisor (para transferencias)",
            value=obtener_metadata("codigo_supervisor") or "1234",
            type="password", key="cod_sup_cfg",
            help="CÃ³digo que deben ingresar los operadores para autorizar transferencias entre depÃ³sitos")
        if st.button("ðŸ’¾ Guardar ParÃ¡metros"):
            st.session_state.umbral_alerta = new_umbral
            st.session_state.wa_numero     = new_wa
            guardar_metadata("umbral_alerta", str(new_umbral))
            guardar_metadata("wa_numero",     new_wa)
            guardar_metadata("codigo_supervisor", cod_sup_cfg)
            st.success("Guardado.")

        st.markdown("---")
        st.write("### ðŸ“Š Stock MÃ­nimo por Producto")
        st.caption("DefinÃ­ el stock mÃ­nimo individual de cada producto. Si es 0, se usa el umbral global.")
        _prod_cfg = obtener_productos_completo()
        if _prod_cfg.empty:
            st.info("Sin productos cargados.")
        else:
            _cols_sm = ["nombre","stock_minimo"] if "stock_minimo" in _prod_cfg.columns else ["nombre"]
            _df_sm = _prod_cfg[_cols_sm].copy().rename(columns={"nombre":"Producto","stock_minimo":"Stock MÃ­nimo"})
            if "Stock MÃ­nimo" not in _df_sm.columns:
                _df_sm["Stock MÃ­nimo"] = 0.0
            _edited_sm = st.data_editor(
                _df_sm,
                column_config={
                    "Producto":      st.column_config.TextColumn("Producto", disabled=True),
                    "Stock MÃ­nimo":  st.column_config.NumberColumn("Stock MÃ­nimo", min_value=0.0, format="%.0f",
                                     help="0 = usar umbral global"),
                },
                hide_index=True, use_container_width=True, key="editor_stock_min"
            )
            if st.button("ðŸ’¾ Guardar Stocks MÃ­nimos", type="primary", key="save_stock_min"):
                _conn_sm = conectar_db()
                for _, _r in _edited_sm.iterrows():
                    try:
                        _conn_sm.execute(
                            "UPDATE productos SET stock_minimo=? WHERE nombre=?",
                            (float(_r["Stock MÃ­nimo"]), _r["Producto"])
                        )
                    except: pass
                _conn_sm.commit(); _conn_sm.close()
                limpiar_cache()
                st.success("âœ… Stocks mÃ­nimos guardados.")
                st.rerun()

        st.markdown("---")
        st.write("### ðŸ“§ ConfiguraciÃ³n de Email")
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
                smtp_pw    = st.text_input("ContraseÃ±a SMTP", type="password", key="smtp_pw")
            if st.button("ðŸ’¾ Guardar Config Email"):
                guardar_metadata("smtp_server", smtp_s)
                guardar_metadata("smtp_port",   str(smtp_port))
                guardar_metadata("smtp_user",   smtp_u)
                guardar_metadata("email_dest",  smtp_dest)
                if smtp_pw:
                    guardar_metadata("smtp_pass", smtp_pw)
                st.success("Config email guardada.")

        st.markdown("---")
        if es_admin():
            st.write("### ðŸ‘¥ GestiÃ³n de Usuarios")
            conn = conectar_db()
            try:
                df_u = _rsql("SELECT username, nombre, rol, sede FROM usuarios", conn)
            except: df_u = pd.DataFrame()
            conn.close()
            st.dataframe(df_u, use_container_width=True, hide_index=True)

            with st.expander("âž• Agregar / Actualizar Usuario"):
                nu1, nu2 = st.columns(2)
                with nu1:
                    n_usr  = st.text_input("Username", key="n_usr")
                    n_pwd  = st.text_input("ContraseÃ±a", type="password", key="n_pwd")
                    n_nom  = st.text_input("Nombre completo", key="n_nom")
                with nu2:
                    n_rol  = st.selectbox("Rol", ["operador","supervisor","admin"], key="n_rol")
                    n_sede = st.selectbox("Sede", ["San Jorge","Las Varillas","San Francisco"], key="n_sede")
                if st.button("ðŸ’¾ Guardar Usuario", type="primary"):
                    if n_usr and n_pwd:
                        conn = conectar_db()
                        conn.execute("""INSERT OR REPLACE INTO usuarios
                            (username,password_hash,nombre,rol,sede) VALUES (?,?,?,?,?)""",
                            (n_usr, hash_pwd(n_pwd), n_nom, n_rol, n_sede))
                        conn.commit(); conn.close()
                        st.success(f"Usuario '{n_usr}' guardado.")
                        st.rerun()
                    else:
                        st.error("Username y contraseÃ±a son obligatorios.")

            auth_on = st.toggle("ðŸ” Activar autenticaciÃ³n",
                                value=(obtener_metadata("auth_enabled")=="1"),
                                key="auth_toggle")
            if st.button("ðŸ’¾ Guardar config auth"):
                guardar_metadata("auth_enabled", "1" if auth_on else "0")
                st.success("Config auth guardada. RecargÃ¡ la pÃ¡gina.")
            if auth_on:
                st.warning("âš ï¸ RecordÃ¡ cambiar la contraseÃ±a del usuario **admin** antes de activar.")

        st.markdown("---")
        st.write("### âš ï¸ Mantenimiento de Datos")
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("ðŸ—‘ï¸ Borrar solo datos importados"):
                borrar_solo_importacion()
                st.success("Datos de importaciÃ³n eliminados.")
                st.rerun()
        with col_b2:
            conf_borrado = st.text_input("EscribÃ­ **CONFIRMAR** para habilitar borrado total",
                                         placeholder="CONFIRMAR", key="conf_borrado")
            if st.button("ðŸ”¥ BORRAR BASE COMPLETA", type="primary",
                         disabled=(conf_borrado.strip() != "CONFIRMAR")):
                borrar_datos_totales()
                st.success("Base vaciada.")
                st.rerun()
        with col_b3:
            _bk = backup_db_bytes()
            if _bk:
                st.download_button("ðŸ’¾ Backup DB (.sqlite)",
                                   data=_bk,
                                   file_name=f"backup_lc_{datetime.now().strftime('%Y%m%d_%H%M')}.sqlite",
                                   help="Descarga una copia completa de la base de datos local",
                                   use_container_width=True)
            else:
                st.caption("Backup disponible solo en modo local (SQLite).")

        # â”€â”€ Historial de Importaciones â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("---")
        st.write("### ðŸ“‹ Historial de Importaciones")
        st.caption("Registro automÃ¡tico de cada importaciÃ³n realizada en la app.")
        conn_log = conectar_db()
        df_log = _rsql("""SELECT fecha_hora "Fecha", tipo "Tipo", archivo "Archivo",
                                  filas "Filas", usuario "Usuario", resultado "Resultado"
                           FROM importaciones_log ORDER BY id_log DESC LIMIT 100""", conn_log)
        conn_log.close()
        if df_log.empty:
            st.info("Sin importaciones registradas aÃºn.")
        else:
            st.dataframe(df_log, use_container_width=True, hide_index=True)
            st.download_button("ðŸ“¥ Exportar log (.xlsx)",
                               data=to_excel_bytes(df_log, "Log_Importaciones"),
                               file_name="log_importaciones.xlsx")

        # â”€â”€ Historial de Remitos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("---")
        st.write("### ðŸ–¨ï¸ Historial de Remitos")
        conn_rem = conectar_db()
        df_rem_log = _rsql("""SELECT numero "Nro", fecha_hora "Fecha", tipo "Tipo",
                                      cliente "Cliente", deposito "DepÃ³sito",
                                      usuario "Usuario", observaciones "Observaciones"
                               FROM remitos ORDER BY id_remito DESC LIMIT 200""", conn_rem)
        conn_rem.close()
        if df_rem_log.empty:
            st.info("Sin remitos emitidos aÃºn.")
        else:
            st.metric("Total remitos emitidos", len(df_rem_log))
            st.dataframe(df_rem_log, use_container_width=True, hide_index=True)
            st.download_button("ðŸ“¥ Exportar remitos (.xlsx)",
                               data=to_excel_bytes(df_rem_log, "Remitos"),
                               file_name=f"remitos_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # â”€â”€ Config JSON â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with cfg3:
        st.write("### âš™ï¸ Exportar / Importar ConfiguraciÃ³n JSON")
        st.caption("HacÃ© backup de todos los parÃ¡metros de la app en un archivo JSON. Ãštil para restaurar configuraciÃ³n en otro equipo o luego de un reset.")

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
        # TambiÃ©n metas
        _conn_cfg = conectar_db()
        _metas_cfg = _rsql("SELECT campana, vendedor, producto, meta_cantidad, meta_valor FROM metas_campana", _conn_cfg)
        _conn_cfg.close()
        if not _metas_cfg.empty:
            _cfg_exp["metas_campana"] = _metas_cfg.to_dict(orient="records")
        _json_bytes = json.dumps(_cfg_exp, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "ðŸ“¥ Exportar configuraciÃ³n (.json)",
            data=_json_bytes,
            file_name=f"config_lc_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            type="primary"
        )
        st.markdown("---")
        # Importar
        st.write("#### Importar configuraciÃ³n desde JSON")
        _arch_cfg = st.file_uploader("Archivo config (.json)", type=["json"], key="up_cfg_json")
        if _arch_cfg:
            try:
                _cfg_imp = json.loads(_arch_cfg.read().decode("utf-8"))
                st.json(_cfg_imp)
                if st.button("âœ… Aplicar configuraciÃ³n", type="primary", key="btn_apply_cfg"):
                    for _k, _v in _cfg_imp.items():
                        if _k == "metas_campana":
                            continue  # no sobrescribir metas automÃ¡ticamente
                        guardar_metadata(_k, str(_v))
                    # Refrescar session state
                    if "umbral_alerta" in _cfg_imp:
                        st.session_state.umbral_alerta = int(_cfg_imp["umbral_alerta"])
                    if "wa_numero" in _cfg_imp:
                        st.session_state.wa_numero = _cfg_imp["wa_numero"]
                    st.success("âœ… ConfiguraciÃ³n importada correctamente.")
                    st.rerun()
            except Exception as _ex:
                st.error(f"Error leyendo JSON: {_ex}")

    # â”€â”€ Changelog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with cfg4:
        st.write("### ðŸ“‹ Changelog â€” Historial de Versiones")
        st.markdown("""
| VersiÃ³n | Fecha | Cambios |
|---------|-------|---------|
| **v4.0 PRO** | Jul 2026 | Inventario fÃ­sico masivo, devoluciones, eficiencia entregas, ranking clientes, reporte ejecutivo PDF con logo, exportaciÃ³n config JSON, tabs de reportes ampliados |
| **v3.5** | Jun 2026 | Reservas de stock, filtro global de depÃ³sito, comparativa campaÃ±as, WhatsApp share, changelog, importaciÃ³n mÃºltiple |
| **v3.0 PRO** | Jun 2026 | Remitos correlativos (R-00001...), log de importaciones, backup SQLite, orden de compra PDF, forecast de demanda, novedades del dÃ­a, tendencias mensuales, tooltips KPIs, alerta stock negativo inmediata |
| **v2.5** | May 2026 | Logo LC + colores corporativos, header profesional, remitos PDF, confirmaciÃ³n entregas MG con descuento stock, observaciones en movimientos, stock inmovilizado, validaciÃ³n duplicados |
| **v2.0** | May 2026 | Ãndices DB, stock mÃ­nimo por producto, semÃ¡foros, proyecciÃ³n, trazabilidad lote, margen bruto, paginaciÃ³n historial, modo oscuro |
| **v1.5** | Abr 2026 | Lista de precios separada, cache TTL 300s, LIMIT 2000 en historial, batch imports (executemany) |
| **v1.0** | Mar 2026 | VersiÃ³n inicial: control de stock multi-depÃ³sito, importaciÃ³n MacroGest, entregas, historial, valorizaciÃ³n |
""")
        st.markdown("---")
        st.write("#### ðŸ”§ Estado del Sistema")
        _sys1, _sys2, _sys3, _sys4 = st.columns(4)
        _sys1.metric("VersiÃ³n", "v4.0 PRO")
        _sys2.metric("PDF", "âœ…" if PDF_AVAILABLE else "âŒ")
        _sys3.metric("DB", "PostgreSQL" if IS_POSTGRES else "SQLite")
        _sys4.metric("Usuario", usuario_actual())

    st.markdown("---")
    st.caption(f"La Clementina S.A. â€” v4.0 PRO â€” "
               f"{'PDF âœ…' if PDF_AVAILABLE else 'PDF âŒ (pip install reportlab)'}")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 10 â€” PLAN COMERCIAL 2026-2027
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab10:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a5276,#2e86c1);
                color:white;padding:24px 28px;border-radius:12px;margin-bottom:20px">
        <h2 style="margin:0;font-size:1.5rem">ðŸ“Š Plan Comercial â€” CampaÃ±a 2026-2027</h2>
        <p style="margin:6px 0 0;opacity:.85">La Clementina S.A. Â· DirecciÃ³n Comercial Â· San Jorge, Santa Fe</p>
    </div>
    """, unsafe_allow_html=True)

    pc1, pc2, pc3, pc4, pc5 = st.tabs([
        "ðŸ“‹ El Plan",
        "ðŸŽ¯ Metas & Productos",
        "ðŸ“ˆ KPI Dashboard",
        "ðŸ‘¥ Cartera de Clientes",
        "ðŸ“ Reportes Semanales",
    ])

    # â”€â”€ SUBTAB 1: DOCUMENTO DEL PLAN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with pc1:
        st.markdown("""
## 1. PROPÃ“SITO DEL PLAN

El presente Plan Comercial establece los lineamientos estratÃ©gicos y operativos que orientarÃ¡n la gestiÃ³n de ventas durante la **CampaÃ±a 2026-2027**. Su propÃ³sito es proveer a cada integrante del equipo comercial un marco claro de objetivos, mÃ©tricas de seguimiento y metodologÃ­a de trabajo.

Este documento es de **cumplimiento obligatorio**. Cada vendedor deberÃ¡ presentar su propio plan de acciÃ³n antes del **15 de julio de 2026**, el cual serÃ¡ evaluado semanalmente y reportado a DirecciÃ³n de forma mensual.

---

## 2. OBJETIVOS GENERALES

### 2.1 Crecimiento de FacturaciÃ³n
| Canal | Objetivo |
|---|---|
| La Clementina + Bayer | **+30 %** sobre la campaÃ±a anterior (en lÃ­nea con ajuste de precios) |
| Volumen fÃ­sico estratÃ©gico | **+20 %** en MaÃ­z, Round Up y Semillas AutÃ³gamas |

> âš ï¸ Toda desviaciÃ³n superior al **10 % negativo** sobre la meta mensual debe ser informada y fundamentada dentro de las **48 horas** al responsable comercial.

### 2.2 DistribuciÃ³n Objetivo de FacturaciÃ³n (La Clementina)
| Rubro | ParticipaciÃ³n |
|---|---|
| Semillas autÃ³gamas | **30 %** |
| AgroquÃ­micos | **30 %** |
| Fertilizantes | **30 %** |
| Otros / Servicios | **10 %** |

---

## 3. SEGMENTACIÃ“N DE CARTERA

### 3.1 Clientes Premium (Regla 80/20)
- El segmento Premium representa el **80 % de la facturaciÃ³n** en **no menos del 20 %** de los clientes activos.
- Con una cartera de 50 clientes: mÃ­nimo 10 cuentas Premium.
- Una concentraciÃ³n inferior es un **riesgo estratÃ©gico** â†’ acciÃ³n de captaciÃ³n inmediata.

### 3.2 FidelizaciÃ³n y ReactivaciÃ³n
- **Clientes activos**: seguimiento, propuestas de valor, presencia en campo.
- **Clientes inactivos**: propuesta de retorno focalizada en necesidades actuales.

Cada vendedor presenta mensualmente el **estado de su cartera** con clientes en riesgo y acciones en curso.

---

## 4. FIELD VIEW â€” CLIENTES OBJETIVOS
Cada vendedor debe:
- Identificar **mÃ­nimo 5 clientes** para seguimiento productivo vÃ­a Field View.
- Presentar el listado + cronograma antes del **31 de julio de 2026**.
- Usar los datos de la plataforma como argumento comercial en visitas.

---

## 5. KPIs Y METODOLOGÃA DE SEGUIMIENTO

| Indicador | Objetivo | Frecuencia |
|---|---|---|
| FacturaciÃ³n total (LC + Bayer) | Meta mensual / acumulado | Semanal y mensual |
| FacturaciÃ³n por rubro | Mix 30/30/30 | Mensual |
| Clientes Premium activos | â‰¥ 20 % del total | Mensual |
| Nuevos clientes | Meta por zona | Mensual |
| Volumen productos foco | Meta por producto / semestre | Mensual |
| Clientes Field View activos | **MÃ­nimo 5** por vendedor | Semestral |
| Clientes reactivados | Sobre base inactivos previos | Mensual |

### Ciclo de Reporte
- **ReuniÃ³n semanal**: avances, obstÃ¡culos y oportunidades.
- **Reporte mensual escrito** a DirecciÃ³n: KPIs, desvÃ­os y plan correctivo.
- **RevisiÃ³n semestral**: evaluaciÃ³n integral y ajuste de metas.

---

## 6. COMPROMISOS DEL EQUIPO
- âœ… Plan de acciÃ³n individual antes del **15 de julio de 2026**.
- âœ… Registro semanal en **MacroGest**: visitas, oportunidades, cartera.
- âœ… Asistencia a reuniones con informaciÃ³n actualizada.
- âœ… ComunicaciÃ³n proactiva de situaciones de riesgo.

---
> *"El Ã©xito comercial no es consecuencia del azar. Es el resultado de planificar, ejecutar y mejorar de forma consistente."*
        """)

    # â”€â”€ SUBTAB 2: METAS & PRODUCTOS FOCO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with pc2:
        st.write("### ðŸŽ¯ Productos Foco â€” Metas Generales de CampaÃ±a")

        df_pf = obtener_productos_foco()
        if not df_pf.empty:
            pf_edit = st.data_editor(
                df_pf[["producto","unidad","meta_total","prioridad"]].rename(columns={
                    "producto":"Producto","unidad":"Unidad",
                    "meta_total":"Meta Total CampaÃ±a","prioridad":"Prioridad"
                }),
                column_config={
                    "Meta Total CampaÃ±a": st.column_config.NumberColumn(min_value=0, format="%.0f"),
                    "Prioridad":          st.column_config.NumberColumn(min_value=1, max_value=10),
                },
                hide_index=True, use_container_width=True, key="edit_pf"
            )
            if st.button("ðŸ’¾ Guardar Productos Foco", key="save_pf"):
                conn = conectar_db()
                for i, r in pf_edit.iterrows():
                    conn.execute("""UPDATE productos_foco
                        SET meta_total=?, prioridad=?
                        WHERE campana=? AND producto=?""",
                        (float(r["Meta Total CampaÃ±a"]), int(r["Prioridad"]),
                         CAMPANA_ACTUAL, r["Producto"]))
                conn.commit(); conn.close()
                limpiar_cache()
                st.success("âœ… Metas actualizadas.")
                st.rerun()

        st.markdown("---")
        st.write("### ðŸ‘¤ Metas Individuales por Vendedor")

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
                                     "meta_facturacion":"Meta FacturaciÃ³n","moneda_meta":"Moneda"}),
                    on="Producto", how="left"
                )
            if "Meta Volumen" not in df_base.columns:
                df_base["Meta Volumen"]      = 0.0
            if "Meta FacturaciÃ³n" not in df_base.columns:
                df_base["Meta FacturaciÃ³n"]  = 0.0
            if "Moneda" not in df_base.columns:
                df_base["Moneda"]            = "ARS"
            df_base = df_base.fillna(0)

            edited_m = st.data_editor(
                df_base,
                column_config={
                    "Meta Volumen":      st.column_config.NumberColumn(min_value=0, format="%.1f"),
                    "Meta FacturaciÃ³n":  st.column_config.NumberColumn(min_value=0, format="%.0f"),
                    "Moneda":            st.column_config.SelectboxColumn(options=["ARS","USD"]),
                },
                hide_index=True, use_container_width=True, key="edit_metas_v"
            )
            if st.button(f"ðŸ’¾ Guardar metas de {vend_sel_m}", type="primary", key="save_metas_v"):
                conn = conectar_db()
                for _, r in edited_m.iterrows():
                    conn.execute("""INSERT OR REPLACE INTO metas_campana
                        (campana,vendedor,producto,unidad,meta_volumen,meta_facturacion,moneda_meta)
                        VALUES (?,?,?,?,?,?,?)""",
                        (CAMPANA_ACTUAL, vend_sel_m, r["Producto"], r["Unidad"],
                         float(r["Meta Volumen"]), float(r["Meta FacturaciÃ³n"]), r["Moneda"]))
                conn.commit(); conn.close()
                limpiar_cache()
                st.success(f"âœ… Metas de {vend_sel_m} guardadas.")
                st.rerun()

    # â”€â”€ SUBTAB 3: KPI DASHBOARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with pc3:
        st.write("### ðŸ“ˆ KPI Dashboard â€” CampaÃ±a 2026-2027")

        # Estado de datos disponibles
        n_ventas_est = len(obtener_ventas_detalle())
        n_mg_est = len(obtener_entregas("MACROGEST"))
        est1, est2 = st.columns(2)
        with est1:
            st.metric("ðŸ“‹ LÃ­neas de venta cargadas", n_ventas_est,
                      delta="Con datos âœ“" if n_ventas_est > 0 else "Sin datos",
                      delta_color="normal" if n_ventas_est > 0 else "inverse")
        with est2:
            st.metric("ðŸ”„ Pedidos sin entregar", n_mg_est,
                      delta="Con datos âœ“" if n_mg_est > 0 else "Sin datos",
                      delta_color="normal" if n_mg_est > 0 else "inverse")
        if n_ventas_est == 0:
            st.info("ðŸ’¡ Para ver el dashboard completo: importÃ¡ ventas desde "
                    "**Plan Comercial â†’ Cartera de Clientes â†’ Importar desde MacroGest** "
                    "y pedidos desde el tab **ðŸ”„ Sin Entregar MG**.")
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
        with kp1: st.metric("ðŸ“¦ Entregado Total",    f"{total_entregado:,.0f}")
        with kp2: st.metric("â­ Clientes Premium",   total_clientes)
        with kp3: st.metric("% Premium / Total",     f"{total_premium_pct:.1f}%",
                             delta="OK" if total_premium_pct >= 20 else "< 20% âš ï¸",
                             delta_color="normal" if total_premium_pct >= 20 else "inverse")
        with kp4: st.metric("ðŸŒ Field View activos", field_view_n,
                             delta="OK" if field_view_n >= 5 else f"< 5 objetivo",
                             delta_color="normal" if field_view_n >= 5 else "inverse")
        with kp5: st.metric("ðŸ†• Prospectos",         nuevos_n)

        st.markdown("---")

        # Gauges por vendedor (facturaciÃ³n real vs meta)
        if not ventas_r.empty and not df_metas_all.empty:
            st.write("#### FacturaciÃ³n Real vs Meta por Vendedor")
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
            st.write("#### ðŸ” AnÃ¡lisis de Ventas MacroGest")
            vend_kpi = st.selectbox("Vendedor",
                                    ["Todos"] + sorted(df_mg_all["vendedor"].unique().tolist()),
                                    key="vend_kpi_mg")
            df_mg_f = df_mg_all if vend_kpi=="Todos" else df_mg_all[df_mg_all["vendedor"]==vend_kpi]

            mk1, mk2, mk3, mk4 = st.columns(4)
            with mk1: st.metric("Importe Total",    f"${df_mg_f['importe_total'].sum():,.0f}")
            with mk2: st.metric("Clientes",          df_mg_f["cliente"].nunique())
            with mk3: st.metric("Productos",         df_mg_f["descripcion"].nunique())
            with mk4: st.metric("LÃ­neas de pedido",  len(df_mg_f))

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
            with st.expander("ðŸ“‹ Ver detalle de ventas"):
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
                st.download_button("ðŸ“¥ Exportar ventas",
                                   data=to_excel_bytes(df_det, "Ventas"),
                                   file_name=f"ventas_{vend_kpi}.xlsx")

        st.markdown("---")
        st.write("#### DistribuciÃ³n de FacturaciÃ³n por Rubro (objetivo: 30/30/30/10)")
        st.info("CargÃ¡ los montos reales por rubro para comparar contra la distribuciÃ³n objetivo.")
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

        # EvoluciÃ³n semanal de reportes
        if not df_reps.empty:
            st.markdown("---")
            st.write("#### EvoluciÃ³n de FacturaciÃ³n Semanal Reportada")
            df_evo = (df_reps.groupby("fecha_semana")["facturacion"].sum()
                      .reset_index().sort_values("fecha_semana"))
            df_evo["Acumulado"] = df_evo["facturacion"].cumsum()
            fig_evo = px.area(df_evo, x="fecha_semana", y="Acumulado",
                              title="FacturaciÃ³n Acumulada (segÃºn reportes)",
                              color_discrete_sequence=["#007bff"])
            fig_evo.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_evo, use_container_width=True)

    # â”€â”€ SUBTAB 4: CARTERA DE CLIENTES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with pc4:
        st.write("### ðŸ‘¥ GestiÃ³n de Cartera de Clientes")

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
            with kc1: st.metric("â­ Premium",     n_prem)
            with kc2: st.metric("âœ… Activos",     n_act)
            with kc3: st.metric("ðŸ˜´ Inactivos",   n_inact)
            with kc4: st.metric("ðŸ†• Prospectos",  n_prosp)
            with kc5: st.metric("ðŸŒ Field View",  n_fv)
            with kc6: st.metric("% Premium",      f"{pct_pr}%",
                                 delta="OK âœ…" if pct_pr>=20 else "< 20% âš ï¸",
                                 delta_color="normal" if pct_pr>=20 else "inverse")

            # GrÃ¡fico torta tipos
            cc1, cc2 = st.columns(2)
            with cc1:
                tipo_g = df_c.groupby("tipo").size().reset_index(name="N")
                fig_tp = px.pie(tipo_g, names="tipo", values="N",
                                title="DistribuciÃ³n por Tipo",
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
                                  "ultima_compra":"Ãšlt. Compra","observaciones":"Obs."}),
                use_container_width=True, hide_index=True
            )

        st.markdown("---")
        st.write("#### âž• Agregar / Actualizar Cliente")
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
            cli_pot  = st.number_input("Potencial facturaciÃ³n $", min_value=0.0, step=1000.0, key="nc_pot")
        with nc3:
            cli_fv   = st.toggle("Field View activo", value=False, key="nc_fv")
            cli_uc   = st.text_input("Ãšltima compra (dd/mm/aaaa)", key="nc_uc")
        cli_obs = st.text_input("Observaciones", key="nc_obs")

        if st.button("ðŸ’¾ Guardar Cliente", type="primary", key="save_nc"):
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
                st.success(f"âœ… Cliente '{cli_nom}' guardado.")
                st.rerun()
            else:
                st.error("El nombre del cliente es obligatorio.")

        # â”€â”€ Importar desde MacroGest (formato nativo) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("---")
        with st.expander("ðŸš€ Importar desde MacroGest (formato exportaciÃ³n ventas)", expanded=True):
            st.info(
                "SubÃ­ la exportaciÃ³n directa de MacroGest con columnas: "
                "`cuenta`, `deno_cuenta`, `cuit_cuenta`, `articulo`, `descripcion`, "
                "`precio`, `cantidad`, `entregada`, `fecha`, `localidad`, `observaciones_gen`, `numero`. "
                "La app clasifica automÃ¡ticamente Premium / Activo por Pareto 80/20."
            )
            img_col, frm_col = st.columns([1,2])
            with frm_col:
                vend_mg   = st.text_input("Nombre del vendedor", value="Horacio", key="mg_vend")
                reemplazar = st.toggle("Reemplazar datos previos del vendedor", value=True, key="mg_reempl")
            arch_mg = st.file_uploader("Archivo MacroGest (.xlsx/.csv)", type=["xlsx","csv","xls"], key="up_mg")

            if arch_mg:
                df_car_prev, df_ven_prev = parsear_macrogest_ventas(arch_mg, vend_mg)
                if df_car_prev.empty:
                    st.error("No se pudo leer el archivo. VerificÃ¡ que tenga las columnas correctas.")
                else:
                    # Preview
                    st.write(f"**{len(df_car_prev)} clientes detectados** â€” distribuciÃ³n Pareto automÃ¡tica:")
                    prev_cols = ["cliente","tipo","potencial_facturacion","ultima_compra","observaciones"]
                    st.dataframe(
                        df_car_prev[prev_cols].rename(columns={
                            "cliente":"Cliente","tipo":"Tipo",
                            "potencial_facturacion":"Importe Total $",
                            "ultima_compra":"Ãšlt. Compra","observaciones":"Localidad"
                        }),
                        use_container_width=True, hide_index=True
                    )
                    n_prem = (df_car_prev["tipo"]=="premium").sum()
                    n_act  = (df_car_prev["tipo"]=="activo").sum()
                    st.caption(f"â­ {n_prem} Premium  |  âœ… {n_act} Activos  |  "
                               f"ðŸ“¦ {len(df_ven_prev)} lÃ­neas de venta")

                    # Top productos por importe
                    if not df_ven_prev.empty:
                        top_prod = (df_ven_prev.groupby("descripcion")["importe_total"].sum()
                                    .reset_index().sort_values("importe_total", ascending=False).head(8))
                        fig_tp2 = px.bar(top_prod, x="importe_total", y="descripcion",
                                         orientation="h", title="Top Productos por Importe $",
                                         color_discrete_sequence=["#007bff"])
                        fig_tp2.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                        st.plotly_chart(fig_tp2, use_container_width=True)

                    if st.button(f"âœ… Confirmar importaciÃ³n de {vend_mg}", type="primary", key="confirm_mg"):
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
                        st.success(f"âœ… {len(cart_batch)} clientes y {len(ven_batch)} lÃ­neas de venta importadas para {vend_mg}.")
                        st.rerun()

        # â”€â”€ Importar cartera genÃ©rica â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("---")
        with st.expander("ðŸ“¥ Importar Cartera desde Excel (formato propio)"):
            st.caption("El archivo debe tener columnas: `vendedor`, `cliente`, `tipo`, `superficie_ha`, `potencial_facturacion`, `field_view` (0/1), `ultima_compra`, `observaciones`")
            arch_cart = st.file_uploader("Archivo cartera (.xlsx/.csv)", type=["xlsx","csv"], key="up_cart")
            if arch_cart and st.button("ðŸš€ Importar Cartera", key="imp_cart"):
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
                    st.success(f"âœ… {len(ci_batch)} clientes importados.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")

    # â”€â”€ SUBTAB 5: REPORTES SEMANALES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with pc5:
        st.write("### ðŸ“ Registro de Reportes Semanales")

        ent_v3 = obtener_entregas()
        vendedores_r = sorted(ent_v3["vendedor"].dropna().replace("","S/V").unique().tolist()) \
                       if not ent_v3.empty else ["Vendedor 1"]

        col_rp1, col_rp2 = st.columns([2,1])
        with col_rp1:
            vend_r  = st.selectbox("Vendedor", vendedores_r, key="vend_rep")
        with col_rp2:
            ver_todos = st.toggle("Ver todos los vendedores", value=False, key="rep_todos")

        # Formulario nuevo reporte
        with st.expander("âž• Cargar Reporte Semanal", expanded=True):
            rp1, rp2, rp3 = st.columns(3)
            with rp1:
                fecha_rep = st.date_input("Semana del", value=datetime.now().date(), key="rep_fecha")
                fact_rep  = st.number_input("FacturaciÃ³n de la semana $", min_value=0.0, step=1000.0, key="rep_fact")
            with rp2:
                nuev_rep   = st.number_input("Nuevos clientes", min_value=0, step=1, key="rep_nuev")
                visit_rep  = st.number_input("Visitas realizadas", min_value=0, step=1, key="rep_visit")
            with rp3:
                st.write("Campo libre")
            av_rep  = st.text_area("âœ… Avances / logros de la semana", height=80, key="rep_av")
            ob_rep  = st.text_area("âš ï¸ ObstÃ¡culos / dificultades",     height=80, key="rep_ob")
            op_rep  = st.text_area("ðŸ’¡ Oportunidades detectadas",       height=80, key="rep_op")
            pa_rep  = st.text_area("ðŸ“‹ Plan de acciÃ³n semana siguiente", height=80, key="rep_pa")

            if st.button("ðŸ’¾ Guardar Reporte", type="primary", key="save_rep"):
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
                    st.session_state["rep_ok"] = f"âœ… Reporte de {vend_r} ({fecha_rep.strftime('%d/%m/%Y')}) guardado correctamente."
                    st.rerun()
                except Exception as e:
                    st.error(f"âŒ Error al guardar: {e}")

            if st.session_state.get("rep_ok"):
                st.success(st.session_state.pop("rep_ok"))

        st.markdown("---")
        st.write("#### Historial de Reportes")
        df_rep_h = obtener_reportes(None if ver_todos else vend_r)
        if df_rep_h.empty:
            st.info("Sin reportes cargados todavÃ­a.")
        else:
            # KPIs del vendedor
            if not ver_todos:
                kr1, kr2, kr3, kr4 = st.columns(4)
                with kr1: st.metric("Reportes cargados",  len(df_rep_h))
                with kr2: st.metric("FacturaciÃ³n total",  f"${df_rep_h['facturacion'].sum():,.0f}")
                with kr3: st.metric("Nuevos clientes",    int(df_rep_h['nuevos_clientes'].sum()))
                with kr4: st.metric("Total visitas",      int(df_rep_h['visitas'].sum()))

                if len(df_rep_h) > 1:
                    df_evo_r = df_rep_h.sort_values("fecha_semana")[["fecha_semana","facturacion"]].copy()
                    df_evo_r["Acumulado"] = df_evo_r["facturacion"].cumsum()
                    fig_er = px.bar(df_evo_r, x="fecha_semana", y="facturacion",
                                    title=f"FacturaciÃ³n semanal â€” {vend_r}",
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
                    "vendedor":"Vendedor","fecha_semana":"Semana","facturacion":"FacturaciÃ³n $",
                    "nuevos_clientes":"Nuevos","visitas":"Visitas",
                    "avances":"Avances","obstaculos":"ObstÃ¡culos",
                    "oportunidades":"Oportunidades","plan_accion":"Plan PrÃ³x."
                }),
                use_container_width=True, hide_index=True
            )
            st.download_button("ðŸ“¥ Exportar Reportes",
                               data=to_excel_bytes(df_rep_h, "Reportes"),
                               file_name=f"reportes_{vend_r.replace(' ','_')}.xlsx")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 11 â€” SIN ENTREGAR MACROGEST
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@st.fragment
def _render_tab11():
    st.subheader("ðŸ”„ Pedidos Sin Entregar â€” MacroGest")
    st.caption("ImportÃ¡ el reporte de MacroGest con los pedidos pendientes de entrega. Los datos quedan guardados y se actualizan con cada importaciÃ³n.")

    with st.expander("ðŸ“‚ Importar archivo Sin Entregar", expanded=False):
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
                    f"**{len(df_prev_mg)} renglones** Â· "
                    f"{df_prev_mg['cliente'].nunique()} clientes Â· "
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
                st.caption("Preview â€” primeros 20 registros.")
                if st.button("âœ… Confirmar importaciÃ³n", type="primary", key="confirm_mg_se"):
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
                    st.success(f"âœ… {ok_mg} registros importados.")
                    st.rerun()

    st.markdown("---")
    ultima_mg = obtener_metadata("ultima_importacion_mg")
    if ultima_mg:
        st.caption(f"Ãšltima importaciÃ³n MacroGest: **{ultima_mg}**")

    # â”€â”€ Cache en session_state para velocidad mÃ¡xima de filtrado â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if "df_mg_cache" not in st.session_state or st.session_state.get("df_mg_cache") is None:
        st.session_state["df_mg_cache"] = obtener_entregas("MACROGEST")
    df_mg_stored = st.session_state["df_mg_cache"]

    _rc1, _rc2 = st.columns([8, 1])
    with _rc2:
        if st.button("ðŸ”„", key="mg_refresh", help="Actualizar datos desde la base"):
            st.session_state["df_mg_cache"] = obtener_entregas("MACROGEST")
            df_mg_stored = st.session_state["df_mg_cache"]
            st.rerun()

    if df_mg_stored is None or df_mg_stored.empty:
        st.info("Sin datos. ImportÃ¡ un archivo arriba.")
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
            f_cli_mg = st.text_input("ðŸ” Cliente", key="mg_fcli")
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
                "AntigÃ¼edad",
                ["Todos", "Reciente (â‰¤30d)", "Demorado (30-60d)", "CrÃ­tico (>60d)"],
                key="mg_fedad",
                help="DÃ­as desde la fecha de recibo del pedido"
            )

        # Filtrado ultra-rÃ¡pido: mÃ¡scara booleana sobre columna pre-lowercase
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
            if f_edad_mg == "Reciente (â‰¤30d)":      df_f_mg = df_f_mg[df_f_mg["_dias"] <= 30]
            elif f_edad_mg == "Demorado (30-60d)":  df_f_mg = df_f_mg[(df_f_mg["_dias"] > 30) & (df_f_mg["_dias"] <= 60)]
            elif f_edad_mg == "CrÃ­tico (>60d)":     df_f_mg = df_f_mg[df_f_mg["_dias"] > 60]
            df_f_mg = df_f_mg.drop(columns=["_dias"], errors="ignore")

        if not df_f_mg.empty:
            # Si hay un Ãºnico cliente filtrado â†’ vista detallada de ese cliente
            _clientes_filtrados = df_f_mg["cliente"].dropna().unique()
            _vista_cliente = len(_clientes_filtrados) == 1

            if _vista_cliente:
                _nom_cli = _clientes_filtrados[0]
                st.markdown(f"#### ðŸ‘¤ Pendientes de **{_nom_cli}**")

                # Gauge de % entregado
                _gc_tot = df_f_mg["cantidad_comprada"].sum()
                _ge_tot = df_f_mg["cant_entregada"].sum()
                _gp_tot = df_f_mg["pendiente"].sum()
                _gpct   = round(_ge_tot / _gc_tot * 100, 1) if _gc_tot > 0 else 0
                _fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=_gpct,
                    delta={"reference": 100, "suffix": "%"},
                    number={"suffix": "%", "font": {"size": 36}},
                    title={"text": "% Entregado", "font": {"size": 14}},
                    gauge={
                        "axis": {"range": [0, 100], "tickwidth": 1},
                        "bar":  {"color": "#38a169" if _gpct >= 80 else (_LC_YELLOW if _gpct >= 50 else "#e53e3e")},
                        "steps": [
                            {"range": [0,  50], "color": "#2a1010"},
                            {"range": [50, 80], "color": "#2a2010"},
                            {"range": [80,100], "color": "#1a2a1a"},
                        ],
                        "threshold": {"line": {"color": "white", "width": 3}, "thickness": .75, "value": 100}
                    }
                ))
                _fig_gauge.update_layout(
                    height=220, margin=dict(l=20,r=20,t=40,b=10),
                    paper_bgcolor="rgba(0,0,0,0)", font_color="#FAFAFA"
                )
                _gcol1, _gcol2, _gcol3, _gcol4 = st.columns([2,1,1,1])
                with _gcol1:
                    st.plotly_chart(_fig_gauge, use_container_width=True)
                with _gcol2:
                    st.metric("Comprado", f"{_gc_tot:,.0f}")
                with _gcol3:
                    st.metric("Entregado", f"{_ge_tot:,.0f}")
                with _gcol4:
                    st.metric("Pendiente", f"{_gp_tot:,.0f}", delta=f"-{_gp_tot:,.0f}" if _gp_tot > 0 else "âœ“", delta_color="inverse")
                resumen_mg = (
                    df_f_mg.groupby("producto")
                    .agg(
                        DepÃ³sitos=("deposito",        lambda x: ", ".join(sorted(x.dropna().astype(str).unique()))),
                        Comprado =("cantidad_comprada","sum"),
                        Entregado=("cant_entregada",   "sum"),
                        Pendiente=("pendiente",         "sum"),
                    )
                    .reset_index()
                    .rename(columns={"producto":"Producto"})
                    .sort_values("Pendiente", ascending=False)
                )
            else:
                resumen_mg = (
                    df_f_mg.groupby("producto")
                    .agg(
                        Clientes =("cliente",          "nunique"),
                        DepÃ³sitos=("deposito",          lambda x: ", ".join(sorted(x.dropna().astype(str).unique()))),
                        Comprado =("cantidad_comprada", "sum"),
                        Entregado=("cant_entregada",    "sum"),
                        Pendiente=("pendiente",          "sum"),
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
                st.metric("ðŸ’° Valor total pendiente de entrega (estimado)",
                          f"USD {total_imp_mg:,.0f}",
                          help="Calculado usando precio promedio de ventas MacroGest importadas")
            else:
                st.info("ðŸ’¡ Para ver el valor monetario pendiente, importÃ¡ ventas desde "
                        "**Plan Comercial â†’ Cartera de Clientes â†’ Importar desde MacroGest**.")
            # â”€â”€ SemÃ¡foro de antigÃ¼edad en el resumen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _dias_por_prod = (
                df_f_mg.groupby("producto")["dia_recibido"]
                .apply(lambda x: max(((dias_desde(v) or 0) for v in x), default=0))
                .reset_index()
            )
            _dias_por_prod.columns = ["Producto", "_dias_max"]
            resumen_mg = resumen_mg.merge(_dias_por_prod, on="Producto", how="left")
            resumen_mg["_dias_max"] = resumen_mg["_dias_max"].fillna(0).astype(int)
            resumen_mg["Estado"] = resumen_mg["_dias_max"].apply(
                lambda d: "ðŸ”´ CrÃ­tico" if d > 90 else ("ðŸŸ¡ Demorado" if d > 30 else "ðŸŸ¢ OK")
            )
            _resumen_display = resumen_mg.drop(columns=["_dias_max"], errors="ignore").reset_index(drop=True)
            # Reordenar para que Estado quede primero
            _cols_ord = ["Estado"] + [c for c in _resumen_display.columns if c != "Estado"]
            st.dataframe(_resumen_display[_cols_ord], use_container_width=True, hide_index=True)
            st.caption("ðŸ”´ CrÃ­tico >90 dÃ­as Â· ðŸŸ¡ Demorado >30 dÃ­as Â· ðŸŸ¢ OK â‰¤30 dÃ­as")

            # â”€â”€ Ranking top 10 clientes con mÃ¡s pendiente â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            with st.expander("ðŸ† Ranking â€” Clientes con mÃ¡s pendiente", expanded=False):
                _rank_df = (df_f_mg.groupby("cliente")["pendiente"].sum()
                            .reset_index().rename(columns={"cliente":"Cliente","pendiente":"Pendiente"})
                            .sort_values("Pendiente", ascending=False).head(10))
                if not _rank_df.empty:
                    _fig_rank = px.bar(_rank_df, x="Pendiente", y="Cliente", orientation="h",
                                       color="Pendiente", color_continuous_scale=["#F5A800","#3D4E6B"],
                                       title="Top 10 Clientes â€” Unidades Pendientes",
                                       text="Pendiente")
                    _fig_rank.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
                    _fig_rank.update_layout(yaxis={"categoryorder":"total ascending"},
                                            height=350, margin=dict(l=10,r=10,t=40,b=10),
                                            coloraxis_showscale=False)
                    st.plotly_chart(_fig_rank, use_container_width=True)

            # â”€â”€ GrÃ¡ficos: torta distribuciÃ³n + evoluciÃ³n mensual â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            with st.expander("ðŸ“Š GrÃ¡ficos â€” DistribuciÃ³n y evoluciÃ³n", expanded=False):
                _gc1, _gc2 = st.columns(2)
                with _gc1:
                    _dist_prod = (df_f_mg.groupby("producto")["pendiente"].sum()
                                  .reset_index().sort_values("pendiente", ascending=False).head(8))
                    if not _dist_prod.empty:
                        _fig_pie = px.pie(_dist_prod, values="pendiente", names="producto",
                                          title="Pendiente por Producto (top 8)",
                                          color_discrete_sequence=px.colors.sequential.Blues_r)
                        _fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                        _fig_pie.update_layout(height=350, showlegend=False,
                                               margin=dict(l=10,r=10,t=40,b=10))
                        st.plotly_chart(_fig_pie, use_container_width=True)
                with _gc2:
                    _evo_df = df_f_mg.copy()
                    _evo_df["_mes"] = pd.to_datetime(_evo_df["dia_recibido"], dayfirst=True, errors="coerce").dt.to_period("M").astype(str)
                    _evo_mes = (_evo_df.groupby("_mes").agg(
                        Comprado=("cantidad_comprada","sum"),
                        Entregado=("cant_entregada","sum"),
                        Pendiente=("pendiente","sum")
                    ).reset_index().rename(columns={"_mes":"Mes"}))
                    if not _evo_mes.empty and _evo_mes["Mes"].notna().any():
                        _evo_mes = _evo_mes[_evo_mes["Mes"] != "NaT"].sort_values("Mes")
                        _fig_evo = px.bar(_evo_mes, x="Mes", y=["Comprado","Entregado","Pendiente"],
                                          barmode="group", title="EvoluciÃ³n Mensual",
                                          color_discrete_map={"Comprado":"#3D4E6B","Entregado":"#2E7D32","Pendiente":"#F5A800"})
                        _fig_evo.update_layout(height=350, margin=dict(l=10,r=10,t=40,b=10),
                                               legend=dict(orientation="h", y=-0.2))
                        st.plotly_chart(_fig_evo, use_container_width=True)

            # â”€â”€ Exportar Excel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            with st.expander("ðŸ“¥ Exportar datos filtrados", expanded=False):
                _exc1, _exc2 = st.columns(2)
                with _exc1:
                    _buf_xl = io.BytesIO()
                    _df_export = df_f_mg.drop(columns=["_dias_sem"], errors="ignore").copy()
                    with pd.ExcelWriter(_buf_xl, engine="openpyxl") as _xw:
                        _df_export.to_excel(_xw, index=False, sheet_name="Sin Entregar MG")
                    st.download_button(
                        "â¬‡ï¸ Descargar Excel (.xlsx)",
                        data=_buf_xl.getvalue(),
                        file_name=f"sin_entregar_mg_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_mg_excel"
                    )
                with _exc2:
                    _csv_data = _df_export.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "â¬‡ï¸ Descargar CSV",
                        data=_csv_data,
                        file_name=f"sin_entregar_mg_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                        key="dl_mg_csv"
                    )

            # â”€â”€ Pedidos por vencer (prÃ³ximos 30 dÃ­as) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            with st.expander("â° Pedidos por vencer â€” prÃ³ximos 30 dÃ­as", expanded=False):
                _venc_df = df_f_mg.copy()
                _venc_df["_dias_ant"] = _venc_df["dia_recibido"].apply(dias_desde)
                _venc_prox = _venc_df[
                    (_venc_df["_dias_ant"] >= 25) & (_venc_df["_dias_ant"] <= 45) &
                    (_venc_df["pendiente"] > 0)
                ].copy()
                _venc_crit = _venc_df[(_venc_df["_dias_ant"] > 60) & (_venc_df["pendiente"] > 0)].copy()
                if not _venc_crit.empty:
                    st.warning(f"ðŸ”´ {len(_venc_crit)} registros con mÃ¡s de 60 dÃ­as sin entregar")
                    _cols_vc = [c for c in ["cliente","producto","deposito","pendiente","dia_recibido","_dias_ant"] if c in _venc_crit.columns]
                    st.dataframe(_venc_crit[_cols_vc].rename(columns={"_dias_ant":"DÃ­as"}).sort_values("DÃ­as", ascending=False),
                                 use_container_width=True, hide_index=True)
                if not _venc_prox.empty:
                    st.info(f"ðŸŸ¡ {len(_venc_prox)} registros con 25-45 dÃ­as de antigÃ¼edad")
                    _cols_vp = [c for c in ["cliente","producto","deposito","pendiente","dia_recibido","_dias_ant"] if c in _venc_prox.columns]
                    st.dataframe(_venc_prox[_cols_vp].rename(columns={"_dias_ant":"DÃ­as"}).sort_values("DÃ­as", ascending=False),
                                 use_container_width=True, hide_index=True)
                if _venc_crit.empty and _venc_prox.empty:
                    st.success("No hay pedidos crÃ­ticos pendientes.")

            # â”€â”€ Clientes sin actividad reciente â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            with st.expander("ðŸ˜´ Clientes sin actividad reciente (>60 dÃ­as)", expanded=False):
                _act_df = df_mg_stored.copy()
                _act_df["_dias_act"] = _act_df["dia_recibido"].apply(dias_desde)
                _ultima_act = _act_df.groupby("cliente")["_dias_act"].min().reset_index()
                _ultima_act.columns = ["Cliente", "DÃ­as desde Ãºltimo pedido"]
                _sin_act = _ultima_act[_ultima_act["DÃ­as desde Ãºltimo pedido"] > 60].sort_values("DÃ­as desde Ãºltimo pedido", ascending=False)
                if not _sin_act.empty:
                    st.dataframe(_sin_act, use_container_width=True, hide_index=True)
                    st.caption(f"Total: {len(_sin_act)} clientes sin pedidos nuevos en mÃ¡s de 60 dÃ­as.")
                else:
                    st.success("Todos los clientes tuvieron actividad en los Ãºltimos 60 dÃ­as.")

            # â”€â”€ Entregas de otras hojas para el cliente filtrado â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if _vista_cliente and f_cli_mg:
                st.markdown("---")
                st.markdown(f"#### ðŸ“‹ Entregas en otras hojas â€” **{_nom_cli}**")
                st.caption("Pedidos del mismo cliente en LC/LCAGRO, Bayer DEP55 y Bayer Directa.")

                _hojas_extra = [
                    ("LA CLEMENTINA S.A", "ðŸ“¦ LC / LCAGRO"),
                    ("BAYER DEP55",       "ðŸŒ¿ Bayer DEP55"),
                    ("BAYER DIRECTA",     "ðŸšš Bayer Directa"),
                ]
                _hay_extra = False
                for _hoja_key, _hoja_label in _hojas_extra:
                    _cache_key = f"df_ent_cache_{_hoja_key}"
                    _df_hoja = st.session_state.get(_cache_key)
                    if _df_hoja is None:
                        _df_hoja = obtener_entregas(_hoja_key)
                        st.session_state[_cache_key] = _df_hoja
                    if _df_hoja is None or _df_hoja.empty:
                        continue
                    # Filtrar por cliente (exacto + fonÃ©tico)
                    _mask_h = _filtro_fonetico(_df_hoja["cliente"], f_cli_mg)
                    _df_cli_h = _df_hoja[_mask_h].copy()
                    if _df_cli_h.empty:
                        continue
                    _hay_extra = True
                    with st.expander(f"{_hoja_label} â€” {len(_df_cli_h)} registros", expanded=True):
                        _res_h = (
                            _df_cli_h.groupby("producto")
                            .agg(
                                DepÃ³sitos=("deposito",         lambda x: ", ".join(sorted(x.dropna().astype(str).unique()))),
                                Comprado =("cantidad_comprada","sum"),
                                Entregado=("cant_entregada",   "sum"),
                                Pendiente=("pendiente",         "sum"),
                                Estado   =("estado",           lambda x: x.mode()[0] if not x.empty else ""),
                            )
                            .reset_index()
                            .rename(columns={"producto": "Producto"})
                            .sort_values("Pendiente", ascending=False)
                        )
                        _res_h["% Entregado"] = (
                            _res_h["Entregado"] / _res_h["Comprado"].replace(0, 1) * 100
                        ).round(1).astype(str) + "%"
                        st.dataframe(_res_h, use_container_width=True, hide_index=True)

                if not _hay_extra:
                    st.info("No se encontraron registros para este cliente en las otras hojas.")

            # â”€â”€ Notas por cliente â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if _vista_cliente:
                st.markdown("---")
                st.markdown(f"#### ðŸ“ Notas â€” **{_nom_cli}**")
                _notas_existentes = obtener_notas_cliente(_nom_cli)
                if _notas_existentes:
                    for _nid, _ntxt, _nusr, _nfch, _ndest in _notas_existentes:
                        _ncols = st.columns([0.05, 0.85, 0.1])
                        with _ncols[0]:
                            st.markdown("â­" if _ndest else "â€¢")
                        with _ncols[1]:
                            st.markdown(f"**{_ntxt}**" if _ndest else _ntxt)
                            st.caption(f"{_nusr} Â· {_nfch}")
                        with _ncols[2]:
                            if st.button("ðŸ—‘ï¸", key=f"del_nota_{_nid}", help="Eliminar nota"):
                                eliminar_nota_cliente(_nid)
                                st.rerun()
                else:
                    st.caption("Sin notas para este cliente.")

                with st.expander("âž• Agregar nota", expanded=False):
                    _nota_txt = st.text_area("Nota", key="nueva_nota_txt", placeholder="Acuerdo comercial, condiciÃ³n especial, contacto...")
                    _nota_dest = st.checkbox("â­ Destacada", key="nueva_nota_dest")
                    if st.button("ðŸ’¾ Guardar nota", key="btn_guardar_nota", type="primary"):
                        if _nota_txt.strip():
                            guardar_nota_cliente(_nom_cli, _nota_txt.strip(),
                                                  usuario_actual() or "Admin", _nota_dest)
                            st.success("Nota guardada.")
                            st.rerun()
                        else:
                            st.warning("EscribÃ­ algo antes de guardar.")

            # â”€â”€ Remito PDF por Cliente (completo) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            st.markdown("---")
            st.markdown("#### ðŸ“„ Resumen Completo PDF por Cliente")
            _clientes_pdf = sorted(df_f_mg["cliente"].dropna().unique().tolist()) if not df_f_mg.empty else []
            if _clientes_pdf:
                _cli_pdf = st.selectbox("Cliente para remito", _clientes_pdf, key="mg_cli_pdf")
                _generado_por = st.text_input("Generado por", value=usuario_actual() or "Ignacio", key="mg_pdf_autor")
                if st.button("ðŸ“„ Generar PDF Completo", key="mg_btn_pdf", type="primary"):
                    if not PDF_AVAILABLE:
                        st.warning("reportlab no estÃ¡ instalado. EjecutÃ¡: pip install reportlab")
                    else:
                        _buf_r = io.BytesIO()
                        _doc_r = SimpleDocTemplate(_buf_r, pagesize=landscape(A4),
                                                   rightMargin=1.2*cm, leftMargin=1.2*cm,
                                                   topMargin=1.5*cm, bottomMargin=1.5*cm)
                        _sty_r = getSampleStyleSheet()
                        _el_r  = []

                        # â”€â”€ Estilos personalizados â”€â”€
                        from reportlab.lib.styles import ParagraphStyle
                        from reportlab.lib.enums import TA_CENTER, TA_LEFT
                        _sty_titulo = ParagraphStyle("titulo_lc", parent=_sty_r["Title"],
                                                     textColor=rl_colors.HexColor("#3D4E6B"),
                                                     fontSize=16, spaceAfter=4)
                        _sty_sub    = ParagraphStyle("sub_lc", parent=_sty_r["Normal"],
                                                     textColor=rl_colors.HexColor("#3D4E6B"),
                                                     fontSize=10, spaceAfter=2)
                        _sty_sec    = ParagraphStyle("sec_lc", parent=_sty_r["Heading2"],
                                                     textColor=rl_colors.HexColor("#F5A800"),
                                                     fontSize=11, spaceBefore=12, spaceAfter=4)

                        def _sec_header(label, bg_hex, fg_hex="#FFFFFF"):
                            """Barra de secciÃ³n con color diferenciado por origen."""
                            _t = Table([[Paragraph(f"<b>{label}</b>",
                                        ParagraphStyle("sh", parent=_sty_r["Normal"],
                                                       textColor=rl_colors.HexColor(fg_hex),
                                                       fontSize=11))]],
                                       colWidths=[26.7*cm])
                            _t.setStyle(TableStyle([
                                ("BACKGROUND",    (0,0),(-1,-1), rl_colors.HexColor(bg_hex)),
                                ("TOPPADDING",    (0,0),(-1,-1), 6),
                                ("BOTTOMPADDING", (0,0),(-1,-1), 6),
                                ("LEFTPADDING",   (0,0),(-1,-1), 10),
                            ]))
                            return _t
                        _sty_small  = ParagraphStyle("small_lc", parent=_sty_r["Normal"],
                                                     fontSize=7, textColor=rl_colors.grey)

                        def _tabla(header, rows, col_widths=None):
                            _t = Table([header] + rows, repeatRows=1, colWidths=col_widths)
                            _t.setStyle(TableStyle([
                                ("BACKGROUND",    (0,0), (-1,0),  rl_colors.HexColor("#3D4E6B")),
                                ("TEXTCOLOR",     (0,0), (-1,0),  rl_colors.white),
                                ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
                                ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
                                ("FONTSIZE",      (0,0), (-1,0),  9),
                                ("FONTSIZE",      (0,1), (-1,-1), 8),
                                ("ROWBACKGROUNDS",(0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#FFF8E7")]),
                                ("GRID",          (0,0), (-1,-1), 0.4, rl_colors.HexColor("#cccccc")),
                                ("ALIGN",         (1,0), (-1,-1), "RIGHT"),
                                ("ALIGN",         (0,0), (0,-1),  "LEFT"),
                                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
                                ("TOPPADDING",    (0,0), (-1,-1), 4),
                                ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                                ("LEFTPADDING",   (0,0), (-1,-1), 4),
                                ("RIGHTPADDING",  (0,0), (-1,-1), 4),
                            ]))
                            return _t

                        # â”€â”€ Encabezado â”€â”€
                        if _logo_b64:
                            from reportlab.platypus import Image as RLImage
                            import base64
                            _logo_bytes = base64.b64decode(_logo_b64)
                            _logo_buf   = io.BytesIO(_logo_bytes)
                            _el_r.append(RLImage(_logo_buf, width=3*cm, height=1.2*cm))
                        _el_r.append(Paragraph("La Clementina S.A.", _sty_titulo))
                        _el_r.append(Paragraph("Insumos Agropecuarios Â· Bayer CropScience / Monsanto-Bayer Â· San Jorge, Santa Fe", _sty_sub))
                        _el_r.append(Spacer(1, 0.3*cm))

                        # Info cliente y fecha
                        _info_tbl = Table([[
                            Paragraph(f"<b>Cliente:</b> {_cli_pdf}", _sty_r["Normal"]),
                            Paragraph(f"<b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", _sty_r["Normal"]),
                            Paragraph(f"<b>Generado por:</b> {_generado_por}", _sty_r["Normal"]),
                        ]], colWidths=[7*cm, 5*cm, 5*cm])
                        _info_tbl.setStyle(TableStyle([
                            ("BACKGROUND", (0,0), (-1,-1), rl_colors.HexColor("#EEF2F7")),
                            ("BOX",        (0,0), (-1,-1), 0.5, rl_colors.HexColor("#3D4E6B")),
                            ("FONTSIZE",   (0,0), (-1,-1), 9),
                            ("TOPPADDING", (0,0), (-1,-1), 5),
                            ("BOTTOMPADDING",(0,0),(-1,-1),5),
                        ]))
                        _el_r.append(_info_tbl)
                        _el_r.append(Spacer(1, 0.5*cm))

                        # â”€â”€ RESUMEN EJECUTIVO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        _all_hojas_resumen = []
                        _df_mg_ej = df_mg_stored[df_mg_stored["cliente"] == _cli_pdf]
                        if not _df_mg_ej.empty:
                            _all_hojas_resumen.append(("MacroGest", _df_mg_ej))
                        for _hk_ej, _hl_ej, _ in [
                            ("LA CLEMENTINA S.A", "LC / LCAGRO", ""),
                            ("BAYER DEP55",       "Bayer DEP55", ""),
                            ("BAYER DIRECTA",     "Bayer Directa", ""),
                        ]:
                            _ck_ej = f"df_ent_cache_{_hk_ej}"
                            _dh_ej_cached = st.session_state.get(_ck_ej)
                            _dh_ej = _dh_ej_cached if _dh_ej_cached is not None else obtener_entregas(_hk_ej)
                            if _dh_ej is not None and not _dh_ej.empty:
                                _dh_ej_cli = _dh_ej[_dh_ej["cliente"] == _cli_pdf]
                                if not _dh_ej_cli.empty:
                                    _all_hojas_resumen.append((_hl_ej, _dh_ej_cli))

                        if _all_hojas_resumen:
                            _el_r.append(_sec_header("RESUMEN EJECUTIVO", "#1A1A2E"))
                            _el_r.append(Spacer(1, 0.2*cm))
                            _rej_rows = [["Origen", "Comprado", "Entregado", "Pendiente", "% Ent."]]
                            _tot_c = _tot_e = _tot_p = 0
                            for _hnm, _hdf in _all_hojas_resumen:
                                _hc = _hdf["cantidad_comprada"].sum()
                                _he = _hdf["cant_entregada"].sum()
                                _hp = _hdf["pendiente"].sum()
                                _hpct = f"{_he/_hc*100:.1f}%" if _hc > 0 else "0%"
                                _rej_rows.append([_hnm, f"{_hc:,.0f}", f"{_he:,.0f}", f"{_hp:,.0f}", _hpct])
                                _tot_c += _hc; _tot_e += _he; _tot_p += _hp
                            _rej_rows.append(["TOTAL", f"{_tot_c:,.0f}", f"{_tot_e:,.0f}", f"{_tot_p:,.0f}",
                                              f"{_tot_e/_tot_c*100:.1f}%" if _tot_c > 0 else "0%"])
                            _rej_tbl = Table(_rej_rows, colWidths=[6*cm, 3.5*cm, 3.5*cm, 3.5*cm, 3*cm])
                            _rej_tbl.setStyle(TableStyle([
                                ("BACKGROUND",    (0,0),  (-1,0),  rl_colors.HexColor("#3D4E6B")),
                                ("TEXTCOLOR",     (0,0),  (-1,0),  rl_colors.white),
                                ("BACKGROUND",    (0,-1), (-1,-1), rl_colors.HexColor("#F5A800")),
                                ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
                                ("FONTNAME",      (0,-1), (-1,-1), "Helvetica-Bold"),
                                ("FONTSIZE",      (0,0),  (-1,-1), 9),
                                ("ALIGN",         (1,0),  (-1,-1), "RIGHT"),
                                ("ROWBACKGROUNDS",(0,1),  (-1,-2), [rl_colors.white, rl_colors.HexColor("#F0F4FF")]),
                                ("GRID",          (0,0),  (-1,-1), 0.3, rl_colors.HexColor("#CCCCCC")),
                                ("TOPPADDING",    (0,0),  (-1,-1), 4),
                                ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
                            ]))
                            _el_r.append(_rej_tbl)
                            _el_r.append(Spacer(1, 0.4*cm))

                        # â”€â”€ SECCIÃ“N 1: MacroGest â”€â”€
                        _df_mg_pdf = df_mg_stored[df_mg_stored["cliente"] == _cli_pdf].copy()
                        if not _df_mg_pdf.empty:
                            _el_r.append(Spacer(1, 0.3*cm))
                            _el_r.append(_sec_header("ðŸ“‹  MacroGest â€” Pedidos Sin Entregar", "#3D4E6B"))
                            # KPIs
                            _tc_p = _df_mg_pdf["cantidad_comprada"].sum()
                            _te_p = _df_mg_pdf["cant_entregada"].sum()
                            _tp_p = _df_mg_pdf["pendiente"].sum()
                            _kpi_tbl = Table([[
                                Paragraph(f"<b>Comprado:</b> {_tc_p:,.0f}", _sty_r["Normal"]),
                                Paragraph(f"<b>Entregado:</b> {_te_p:,.0f}", _sty_r["Normal"]),
                                Paragraph(f"<b>Pendiente:</b> {_tp_p:,.0f}", _sty_r["Normal"]),
                                Paragraph(f"<b>% Entregado:</b> {(_te_p/_tc_p*100 if _tc_p>0 else 0):.1f}%", _sty_r["Normal"]),
                            ]], colWidths=[4.25*cm]*4)
                            _kpi_tbl.setStyle(TableStyle([
                                ("BACKGROUND", (0,0),(-1,-1), rl_colors.HexColor("#FFF8E7")),
                                ("FONTSIZE",   (0,0),(-1,-1), 9),
                                ("TOPPADDING", (0,0),(-1,-1), 4),
                                ("BOTTOMPADDING",(0,0),(-1,-1),4),
                                ("BOX",        (0,0),(-1,-1), 0.4, rl_colors.HexColor("#F5A800")),
                            ]))
                            _el_r.append(_kpi_tbl)
                            _el_r.append(Spacer(1, 0.2*cm))

                            # Detalle completo fila por fila con TODOS los campos
                            _hdr_mg = ["Producto", "Lote", "DepÃ³sito", "Vendedor",
                                       "Pedido", "Comprado", "Entregado", "Pendiente", "% Ent.", "Fecha Pedido"]
                            _rows_mg = []
                            for _, _rr in _df_mg_pdf.sort_values("pendiente", ascending=False).iterrows():
                                _pct = round(_rr.get("cant_entregada",0) / _rr.get("cantidad_comprada",1) * 100, 1) if _rr.get("cantidad_comprada",0) > 0 else 0
                                _rows_mg.append([
                                    Paragraph(str(_rr.get("producto","")), _sty_r["Normal"]),
                                    str(_rr.get("lote","") or "S/L"),
                                    str(_rr.get("deposito","") or ""),
                                    str(_rr.get("vendedor","") or ""),
                                    str(_rr.get("hoja","") or _rr.get("nro_pedido","") or ""),
                                    f'{_rr.get("cantidad_comprada",0):,.0f}',
                                    f'{_rr.get("cant_entregada",0):,.0f}',
                                    f'{_rr.get("pendiente",0):,.0f}',
                                    f'{_pct}%',
                                    str(_rr.get("dia_recibido","") or ""),
                                ])
                            _cw_mg = [5.5*cm, 1.8*cm, 2.5*cm, 2.5*cm, 1.8*cm, 2*cm, 2*cm, 2*cm, 1.2*cm, 2.5*cm]
                            _el_r.append(_tabla(_hdr_mg, _rows_mg, _cw_mg))

                        # â”€â”€ SECCIONES: otras hojas â”€â”€
                        _hojas_pdf = [
                            ("LA CLEMENTINA S.A", "ðŸ“¦  LC / LCAGRO â€” Entregas",       "#1A6B3C"),
                            ("BAYER DEP55",       "ðŸŒ¿  Bayer DEP55 â€” Entregas",        "#2E7D32"),
                            ("BAYER DIRECTA",     "ðŸšš  Bayer Directa â€” Entregas",      "#0277BD"),
                        ]
                        for _hk, _hl, _hcolor in _hojas_pdf:
                            _ck = f"df_ent_cache_{_hk}"
                            _dfh = st.session_state.get(_ck)
                            if _dfh is None:
                                _dfh = obtener_entregas(_hk)
                            if _dfh is None or _dfh.empty:
                                continue
                            _dfh_cli = _dfh[_dfh["cliente"] == _cli_pdf].copy()
                            if _dfh_cli.empty:
                                continue
                            _el_r.append(Spacer(1, 0.3*cm))
                            _el_r.append(_sec_header(_hl, _hcolor))
                            _hdr_h = ["Producto", "Lote", "DepÃ³sito", "Vendedor",
                                      "Estado", "Comprado", "Entregado", "Pendiente", "% Ent.", "Fecha"]
                            _rows_h = []
                            for _, _rh in _dfh_cli.sort_values("pendiente", ascending=False).iterrows():
                                _ph = round(_rh.get("cant_entregada",0) / _rh.get("cantidad_comprada",1) * 100, 1) if _rh.get("cantidad_comprada",0) > 0 else 0
                                _rows_h.append([
                                    Paragraph(str(_rh.get("producto","")), _sty_r["Normal"]),
                                    str(_rh.get("lote","") or "S/L"),
                                    str(_rh.get("deposito","") or ""),
                                    str(_rh.get("vendedor","") or ""),
                                    str(_rh.get("estado","") or ""),
                                    f'{_rh.get("cantidad_comprada",0):,.0f}',
                                    f'{_rh.get("cant_entregada",0):,.0f}',
                                    f'{_rh.get("pendiente",0):,.0f}',
                                    f'{_ph}%',
                                    str(_rh.get("dia_recibido","") or ""),
                                ])
                            _cw_h = [5.5*cm, 1.8*cm, 2.5*cm, 2.5*cm, 1.8*cm, 2*cm, 2*cm, 2*cm, 1.2*cm, 2.5*cm]
                            _el_r.append(_tabla(_hdr_h, _rows_h, _cw_h))

                        # â”€â”€ Footer â”€â”€
                        _el_r.append(Spacer(1, 0.8*cm))
                        _el_r.append(Paragraph(
                            f"La Clementina S.A. Â· San Jorge, Santa Fe Â· "
                            f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} Â· "
                            f"Sistema de Control de DepÃ³sito",
                            _sty_small
                        ))

                        _doc_r.build(_el_r)
                        st.download_button(
                            "â¬‡ï¸ Descargar PDF Completo",
                            data=_buf_r.getvalue(),
                            file_name=f"resumen_{_cli_pdf.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            key="dl_rem_cli_pdf"
                        )

            # â”€â”€ Comparativa por Vendedor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            st.markdown("---")
            st.markdown("#### ðŸ‘¤ Comparativa por Vendedor")
            st.caption("Entregado vs pendiente para cada vendedor segÃºn los filtros activos.")
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

            # â”€â”€ Tabla cruzada Cliente Ã— Producto â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            st.markdown("---")
            with st.expander("ðŸ—‚ï¸ Tabla cruzada: Cliente Ã— Producto (pendiente)", expanded=False):
                st.caption("Muestra cuÃ¡nto le falta entregar a cada cliente por producto. Ãštil para planificar despachos.")
                _cross = df_f_mg[df_f_mg["pendiente"] > 0].pivot_table(
                    index="cliente", columns="producto", values="pendiente",
                    aggfunc="sum", fill_value=0
                )
                if _cross.empty:
                    st.info("Sin pendientes con los filtros actuales.")
                else:
                    _cross["TOTAL"] = _cross.sum(axis=1)
                    _cross = _cross.sort_values("TOTAL", ascending=False)
                    # SemÃ¡foro de antigÃ¼edad por cliente
                    if "dia_recibido" in df_f_mg.columns:
                        _df_pend_sem = df_f_mg[df_f_mg["pendiente"] > 0].copy()
                        _df_pend_sem["_dias_sem"] = _df_pend_sem["dia_recibido"].apply(dias_desde)
                        _max_dias = _df_pend_sem.groupby("cliente")["_dias_sem"].max()
                        def _sem_cross(d):
                            if d > 60:  return "ðŸ”´ >60d"
                            if d > 30:  return "ðŸŸ¡ 30-60d"
                            return "ðŸŸ¢ â‰¤30d"
                        _cross["Estado"] = _cross.index.map(lambda c: _sem_cross(_max_dias.get(c, 0)))
                    st.dataframe(_cross.style.format("{:,.0f}", subset=[c for c in _cross.columns if c not in ("TOTAL","Estado")]).background_gradient(
                        cmap="Reds", subset=[c for c in _cross.columns if c not in ("TOTAL","Estado")]),
                        use_container_width=True)
                    st.download_button("ðŸ“¥ Exportar tabla cruzada",
                                       data=to_excel_bytes(_cross.reset_index(), "Cliente_x_Producto"),
                                       file_name=f"cruzada_{datetime.now().strftime('%Y%m%d')}.xlsx")

            st.markdown("---")
            cols_mg = ["dia_recibido","cliente","deposito","producto","cantidad_comprada",
                       "cant_entregada","pendiente","estado","vendedor","rto"]
            cols_mg = [c for c in cols_mg if c in df_f_mg.columns]
            df_show_mg = df_f_mg[cols_mg].rename(columns={
                "dia_recibido":"Fecha","cliente":"Cliente","deposito":"DepÃ³sito",
                "producto":"Producto",
                "cantidad_comprada":"Comprado","cant_entregada":"Entregado",
                "pendiente":"Pendiente","estado":"Estado",
                "vendedor":"Vendedor","rto":"NÂ° Pedido",
            })
            st.dataframe(df_show_mg, use_container_width=True, hide_index=True)
            out_mg = io.BytesIO()
            with pd.ExcelWriter(out_mg, engine="openpyxl") as w:
                resumen_mg.to_excel(w, index=False, sheet_name="Resumen_Producto")
                df_show_mg.to_excel(w, index=False, sheet_name="Detalle")
            st.download_button(
                "ðŸ“¥ Exportar Sin Entregar (.xlsx)",
                data=out_mg.getvalue(),
                file_name=f"sin_entregar_mg_{datetime.now().strftime('%Y%m%d')}.xlsx",
            )
            st.markdown("---")
            with st.expander("âœï¸ Registrar entrega o marcar como completado", expanded=False):
                st.caption("ActualizÃ¡ el estado de un pedido directamente desde acÃ¡.")
                if df_f_mg.empty:
                    st.info("No hay registros con los filtros actuales.")
                else:
                    pedidos_disp = df_f_mg[df_f_mg["rto"].replace("","").notna()]["rto"].unique().tolist()
                    pedidos_disp = [p for p in pedidos_disp if p and str(p).strip()]
                    if pedidos_disp:
                        rto_sel = st.selectbox("NÂ° Pedido a actualizar", pedidos_disp, key="mg_rto_sel",
                                               help="SeleccionÃ¡ el nÃºmero de pedido a modificar")
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
                                    help="IngresÃ¡ la cantidad que se acaba de entregar"
                                )
                                if st.button("ðŸ“¦ Registrar entrega parcial", key="mg_btn_parcial",
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
                                        st.toast(f"âœ… {nueva_entrega:,.1f} unidades registradas y descontadas del stock.")
                                        if _rem_mg:
                                            st.download_button("ðŸ–¨ï¸ Descargar Remito PDF",
                                                               data=_rem_mg,
                                                               file_name=f"remito_mg_{rto_sel}.pdf",
                                                               mime="application/pdf",
                                                               key="dl_rem_mg")
                                        st.rerun()
                                    else:
                                        st.warning("IngresÃ¡ una cantidad mayor a cero.")
                            with ua2:
                                st.write("")  # spacer
                                if st.button("âœ… Marcar pedido como COMPLETADO", key="mg_btn_comp",
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
                                                 f"Completar entrega â€” Cliente: {r0['cliente']}"))
                                    conn.commit(); conn.close()
                                    limpiar_cache()
                                    st.toast(f"âœ… Pedido {rto_sel} marcado como completado y stock descontado.")
                                    st.rerun()
                    else:
                        st.info("Los registros filtrados no tienen NÂ° de pedido asignado. "
                                "PodÃ©s usar 'cliente+producto' para identificarlos.")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 12 â€” LISTA DE PRECIOS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
@st.fragment
def _render_tab12():
    st.subheader("ðŸ·ï¸ Lista de Precios 2026")
    st.caption("ImportÃ¡ la lista de precios de MacroGest. Los precios quedan guardados y se pueden mapear automÃ¡ticamente al stock para valorizar el inventario.")

    # â”€â”€ Importar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with st.expander("ðŸ“‚ Importar Lista de Precios (.xlsx)", expanded=False):
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
                    "FinanciaciÃ³n":"financiacion","Financiacion":"financiacion","FINANCIACION":"financiacion",
                }
                _df_lp.rename(columns={k:v for k,v in _col_map_lp.items() if k in _df_lp.columns}, inplace=True)
                for _req in ["producto","precio_contado"]:
                    if _req not in _df_lp.columns:
                        st.error(f"Columna requerida no encontrada: `{_req}`. Columnas disponibles: {list(_df_lp.columns)}")
                        st.stop()
                _df_lp = _df_lp[_df_lp["producto"].apply(lambda x: bool(safe_str(x)))]
                _n_rub = _df_lp["rubro"].nunique() if "rubro" in _df_lp.columns else "?"
                st.markdown(f"**{len(_df_lp)} productos** Â· {_n_rub} rubros detectados")
                st.dataframe(_df_lp.head(15), use_container_width=True, hide_index=True)
                st.caption("Preview â€” primeros 15 registros")
                if st.button("âœ… Confirmar importaciÃ³n", type="primary", key="conf_lp"):
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
                    st.success(f"âœ… {len(lp_batch)} precios importados.")
                    st.rerun()
            except Exception as _ex_lp:
                st.error(f"Error: {_ex_lp}")

    # â”€â”€ Datos cargados â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    df_lp = obtener_lista_precios()

    if df_lp.empty:
        st.info("Sin datos. ImportÃ¡ un archivo arriba.")
    else:
        _lp_ult = df_lp["fecha_carga"].iloc[0] if "fecha_carga" in df_lp.columns else ""
        if _lp_ult: st.caption(f"ðŸ• Ãšltima carga: **{_lp_ult}**")

        # KPIs
        _lk1, _lk2, _lk3, _lk4 = st.columns(4)
        with _lk1: st.metric("Productos",       len(df_lp))
        with _lk2: st.metric("Rubros",          df_lp["rubro"].nunique())
        with _lk3: st.metric("Precio mÃ­n. USD", f"{df_lp['precio_contado'].min():.2f}")
        with _lk4: st.metric("Precio mÃ¡x. USD", f"{df_lp['precio_contado'].max():.2f}")

        st.markdown("---")

        # Filtros
        _lf1, _lf2, _lf3 = st.columns(3)
        with _lf1:
            rubros_lp = ["Todos"] + sorted(df_lp["rubro"].dropna().unique().tolist())
            f_rubro_lp = st.selectbox("Rubro", rubros_lp, key="f_rubro_lp")
        with _lf2:
            busq_lp = st.text_input("ðŸ” Buscar producto", key="busq_lp")
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
                "precio_contado":"Contado USD","precio_vta":"P.Vta USD","financiacion":"FinanciaciÃ³n"
            }),
            use_container_width=True, hide_index=True
        )
        st.caption(f"Mostrando {len(df_lp_f)} de {len(df_lp)} productos")

        # GrÃ¡fico por rubro
        with st.expander("ðŸ“Š GrÃ¡fico de precios por rubro", expanded=False):
            _fig_rub = px.box(
                df_lp[df_lp["precio_contado"] > 0],
                x="rubro", y="precio_contado",
                title="DistribuciÃ³n de precios por rubro (USD Contado)",
                color="rubro", labels={"precio_contado":"Precio USD","rubro":"Rubro"}
            )
            _fig_rub.update_layout(height=380, showlegend=False, margin=dict(l=0,r=0,t=40,b=80))
            _fig_rub.update_xaxes(tickangle=30)
            st.plotly_chart(_fig_rub, use_container_width=True)

        st.download_button("ðŸ“¥ Exportar lista filtrada (.xlsx)",
                           data=to_excel_bytes(
                               df_lp_f[["rubro","producto","um","precio_contado","precio_vta","financiacion"]]
                               .rename(columns={"rubro":"Rubro","producto":"Producto","um":"UM",
                                                "precio_contado":"Contado USD","precio_vta":"P.Vta USD",
                                                "financiacion":"FinanciaciÃ³n"}),
                               "Lista_Precios"),
                           file_name=f"lista_precios_{datetime.now().strftime('%Y%m%d')}.xlsx")

        # â”€â”€ Mapeo automÃ¡tico al stock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("---")
        st.write("### ðŸ”— Mapear precios al stock")
        st.caption("Cruza los nombres de la lista de precios con los productos en stock y actualiza el precio unitario en ValorizaciÃ³n.")

        _mc1, _mc2 = st.columns([2,1])
        with _mc1:
            st.info("El mapeo busca primero coincidencia **exacta** y luego **parcial** (primeros 15 caracteres). "
                    "DespuÃ©s del mapeo, los precios aparecen automÃ¡ticamente en **ðŸ’² ValorizaciÃ³n**.")
        with _mc2:
            if st.button("ðŸ”— Ejecutar mapeo automÃ¡tico", type="primary", key="btn_mapeo_lp"):
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
                    st.success(f"âœ… {mapeados} productos mapeados correctamente.")
                    if sin_match > 0:
                        st.warning(f"âš ï¸ {sin_match} productos sin coincidencia en stock.")
                        with st.expander("Ver productos sin match"):
                            st.write(no_match_list)
                    st.rerun()

        # â”€â”€ Historial de Precios â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("---")
        with st.expander("ðŸ“ˆ Historial de cambios de precio por producto", expanded=False):
            _hp_prod = st.selectbox("Producto", ["Todos"] + sorted(df_lp["producto"].dropna().unique().tolist()),
                                    key="hp_prod_sel")
            _df_hp = obtener_historial_precios(_hp_prod if _hp_prod != "Todos" else "")
            if _df_hp.empty:
                st.info("Sin historial aÃºn. Los cambios se registran cada vez que se importa una lista.")
            else:
                _fig_hp = px.line(
                    _df_hp.sort_values("fecha_hora"),
                    x="fecha_hora", y="precio",
                    color="producto" if _hp_prod == "Todos" else None,
                    markers=True, title="EvoluciÃ³n de precio",
                    labels={"precio":"Precio","fecha_hora":"Fecha"}
                )
                _fig_hp.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(_fig_hp, use_container_width=True)
                st.dataframe(_df_hp.rename(columns={
                    "fecha_hora":"Fecha","producto":"Producto",
                    "precio":"Precio","moneda":"Moneda","usuario":"Usuario"
                }), use_container_width=True, hide_index=True)

        # â”€â”€ Presupuestador â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("---")
        st.write("### ðŸ’¼ Presupuestador")
        st.caption("ArmÃ¡ un presupuesto para un cliente con productos y precios de lista. GenerÃ¡ el PDF listo para enviar.")
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
            if st.button("âž• Agregar Ã­tem", key="btn_pres_add"):
                st.session_state["pres_items"].append(
                    {"producto": _p_sel, "cantidad": _p_cant, "precio": _p_precio, "moneda": "USD"}
                )
                st.rerun()
        with _bc2:
            if st.button("ðŸ—‘ï¸ Limpiar", key="btn_pres_clear"):
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
                if st.button("ðŸ“„ Generar PDF", type="primary", key="btn_pres_pdf"):
                    _pbytes = generar_presupuesto_pdf(_pres_cliente, _items_now, usuario_actual(), _pres_obs)
                    if _pbytes:
                        st.download_button("â¬‡ï¸ Descargar Presupuesto PDF", data=_pbytes,
                                           file_name=f"presupuesto_{datetime.now().strftime('%Y%m%d')}.pdf",
                                           mime="application/pdf")
            else:
                st.caption("PDF: `pip install reportlab`")
        else:
            st.caption("AgregÃ¡ productos para armar el presupuesto.")

with tab11: _render_tab11()




with tab12: _render_tab12()

# â”€â”€ FunciÃ³n global cacheada para trazabilidad â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@st.cache_data(ttl=180, show_spinner=False)
def obtener_trazabilidad_completa():
    conn = conectar_db()
    df = _rsql("""
        SELECT m.id_movimiento, m.fecha_hora, m.tipo_movimiento,
               p.nombre producto, p.codigo, p.unidad,
               m.cantidad, m.lote, m.deposito,
               m.referencia, m.origen, m.usuario,
               COALESCE(m.anulado,0) anulado
        FROM movimientos m
        JOIN productos p ON m.id_producto = p.id_producto
        ORDER BY m.fecha_hora DESC
    """, conn)
    conn.close()
    if df.empty:
        return df
    df["lote"] = df["lote"].fillna("S/L").astype(str).str.strip()
    df["lote"] = df["lote"].replace({"": "S/L", "nan": "S/L"})
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0)
    df["neta"] = df.apply(
        lambda r: r["cantidad"] if r["tipo_movimiento"] == "Entrada" else -r["cantidad"], axis=1
    )
    return df

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB TRAZABILIDAD
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab_traz:
    st.subheader("ðŸ” Trazabilidad de Lotes y Movimientos")

    # â”€â”€ Cargar datos base (cacheado globalmente) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    df_traz = obtener_trazabilidad_completa()

    if df_traz.empty:
        st.warning("Sin datos. ImportÃ¡ el stock primero.")
        st.stop()

    df_traz["neta"] = df_traz.apply(
        lambda r: r["cantidad"] if r["tipo_movimiento"] == "Entrada" else -r["cantidad"], axis=1
    )

    # â”€â”€ Filtros de bÃºsqueda â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    st.markdown("### ðŸ”Ž Buscar")
    _tc1, _tc2, _tc3 = st.columns(3)
    with _tc1:
        _t_prod = st.selectbox("Producto", ["Todos"] + sorted(df_traz["producto"].unique().tolist()), key="traz_prod")
    with _tc2:
        _lotes_disp = sorted(df_traz["lote"].unique().tolist())
        _t_lote = st.selectbox("Lote", ["Todos"] + _lotes_disp, key="traz_lote")
    with _tc3:
        # Buscar clientes desde entregas
        try:
            _conn_e = conectar_db()
            _df_cli = _rsql("SELECT DISTINCT cliente FROM entregas WHERE cliente IS NOT NULL ORDER BY cliente", _conn_e)
            _conn_e.close()
            _clientes = sorted(_df_cli["cliente"].dropna().tolist()) if not _df_cli.empty else []
        except Exception:
            _clientes = []
        _t_cli = st.selectbox("Cliente", ["Todos"] + _clientes, key="traz_cli")

    _tc4, _tc5 = st.columns(2)
    with _tc4:
        _t_dep = st.selectbox("DepÃ³sito", ["Todos"] + sorted(df_traz["deposito"].dropna().unique().tolist()), key="traz_dep")
    with _tc5:
        _t_texto = st.text_input("Buscar texto libre (producto, lote, referencia)", key="traz_texto")

    # â”€â”€ Aplicar filtros â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    df_f = df_traz[df_traz["anulado"] == 0].copy()
    if _t_prod != "Todos":
        df_f = df_f[df_f["producto"] == _t_prod]
    if _t_lote != "Todos":
        df_f = df_f[df_f["lote"] == _t_lote]
    if _t_dep != "Todos":
        df_f = df_f[df_f["deposito"].astype(str) == str(_t_dep)]
    if _t_texto:
        _mask = (
            df_f["producto"].str.contains(_t_texto, case=False, na=False) |
            df_f["lote"].str.contains(_t_texto, case=False, na=False) |
            df_f["referencia"].astype(str).str.contains(_t_texto, case=False, na=False)
        )
        df_f = df_f[_mask]

    # Filtro por cliente: buscar entregas del cliente y filtrar por producto
    if _t_cli != "Todos":
        try:
            _conn_ec = conectar_db()
            _ph2 = "%s" if IS_POSTGRES else "?"
            _df_ec = _rsql(f"SELECT DISTINCT producto FROM entregas WHERE cliente={_ph2}", _conn_ec, params=(_t_cli,))
            _conn_ec.close()
            if not _df_ec.empty:
                _prods_cli = _df_ec["producto"].tolist()
                df_f = df_f[df_f["producto"].isin(_prods_cli)]
        except Exception:
            pass

    st.markdown(f"**{len(df_f)} movimientos encontrados**")

    # â”€â”€ Resumen por producto+lote â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    st.markdown("---")
    st.markdown("### ðŸ“¦ Stock actual por Producto / Lote / DepÃ³sito")
    if not df_f.empty:
        _resumen = (df_f.groupby(["producto", "lote", "deposito"])["neta"]
                    .sum().reset_index()
                    .rename(columns={"neta": "Stock Actual"}))
        _resumen = _resumen[_resumen["Stock Actual"] != 0].sort_values(
            ["producto", "lote", "deposito"]
        )
        if not _resumen.empty:
            st.dataframe(_resumen, use_container_width=True, hide_index=True)
        else:
            st.info("Stock neto cero para la selecciÃ³n.")

    # â”€â”€ Timeline de movimientos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    st.markdown("---")
    st.markdown("### ðŸ“‹ LÃ­nea de vida â€” Movimientos detallados")
    if not df_f.empty:
        _cols_show = ["fecha_hora", "tipo_movimiento", "producto", "lote",
                      "deposito", "cantidad", "referencia", "usuario"]
        _df_show = df_f[_cols_show].copy()
        _df_show.columns = ["Fecha", "Tipo", "Producto", "Lote",
                             "DepÃ³sito", "Cantidad", "Referencia", "Usuario"]
        _df_show = _df_show.sort_values("Fecha", ascending=False)

        # Color por tipo
        def _color_tipo(row):
            if row["Tipo"] == "Entrada":
                return ["background-color: #1a3a1a"] * len(row)
            elif row["Tipo"] == "Salida":
                return ["background-color: #3a1a1a"] * len(row)
            return [""] * len(row)

        st.dataframe(
            _df_show.style.apply(_color_tipo, axis=1),
            use_container_width=True,
            hide_index=True,
            height=400
        )

    # â”€â”€ Entregas por cliente (si hay filtro de producto o lote) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if _t_prod != "Todos" or _t_lote != "Todos":
        st.markdown("---")
        st.markdown("### ðŸšš Entregas registradas a clientes")
        try:
            _conn_ent = conectar_db()
            _ent_sql = "SELECT fecha_pedido, cliente, producto, lote, cant_entregada, deposito FROM entregas WHERE 1=1"
            _ent_params = []
            if _t_prod != "Todos":
                _ent_sql += f" AND producto = {'%s' if IS_POSTGRES else '?'}"
                _ent_params.append(_t_prod)
            if _t_lote != "Todos":
                _ent_sql += f" AND lote = {'%s' if IS_POSTGRES else '?'}"
                _ent_params.append(_t_lote)
            _ent_sql += " ORDER BY fecha_pedido DESC"
            _df_ent = _rsql(_ent_sql, _conn_ent, params=_ent_params if _ent_params else None)
            _conn_ent.close()
            if not _df_ent.empty:
                st.dataframe(_df_ent, use_container_width=True, hide_index=True)
            else:
                st.info("Sin entregas registradas para este filtro.")
        except Exception as _e:
            st.info(f"No se pudieron cargar entregas: {_e}")

    # â”€â”€ Exportar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    st.markdown("---")
    st.markdown("### ðŸ“¥ Exportar trazabilidad")
    _ec1, _ec2 = st.columns(2)
    with _ec1:
        if not df_f.empty:
            _xlsx_traz = to_excel_bytes(df_f[[
                "fecha_hora","tipo_movimiento","producto","codigo","lote",
                "deposito","cantidad","referencia","usuario"
            ]].rename(columns={
                "fecha_hora":"Fecha","tipo_movimiento":"Tipo","producto":"Producto",
                "codigo":"CÃ³digo","lote":"Lote","deposito":"DepÃ³sito",
                "cantidad":"Cantidad","referencia":"Referencia","usuario":"Usuario"
            }), "Trazabilidad")
            st.download_button(
                "ðŸ“Š Descargar Excel",
                data=_xlsx_traz,
                file_name=f"trazabilidad_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_traz_xlsx"
            )
    with _ec2:
        if PDF_AVAILABLE and not df_f.empty:
            try:
                _buf_pdf = io.BytesIO()
                _doc = SimpleDocTemplate(_buf_pdf, pagesize=landscape(A4),
                                         leftMargin=1*cm, rightMargin=1*cm,
                                         topMargin=1.5*cm, bottomMargin=1*cm)
                _styles = getSampleStyleSheet()
                _elems = []
                _elems.append(Paragraph(
                    f"Trazabilidad â€” La Clementina S.A. â€” {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                    _styles["Heading2"]
                ))
                _elems.append(Spacer(1, 0.3*cm))
                _pdf_df = df_f[["fecha_hora","tipo_movimiento","producto","lote",
                                 "deposito","cantidad","referencia"]].head(500)
                _pdf_df.columns = ["Fecha","Tipo","Producto","Lote","DepÃ³sito","Cantidad","Referencia"]
                _data_pdf = [list(_pdf_df.columns)] + _pdf_df.values.tolist()
                _tbl = Table(_data_pdf, repeatRows=1)
                _tbl.setStyle(TableStyle([
                    ("BACKGROUND",  (0,0), (-1,0),  rl_colors.HexColor("#1B5E20")),
                    ("TEXTCOLOR",   (0,0), (-1,0),  rl_colors.white),
                    ("FONTSIZE",    (0,0), (-1,-1), 7),
                    ("GRID",        (0,0), (-1,-1), 0.3, rl_colors.grey),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [rl_colors.white, rl_colors.HexColor("#F1F8E9")]),
                ]))
                _elems.append(_tbl)
                _doc.build(_elems)
                _buf_pdf.seek(0)
                st.download_button(
                    "ðŸ“„ Descargar PDF",
                    data=_buf_pdf,
                    file_name=f"trazabilidad_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    key="dl_traz_pdf"
                )
            except Exception as _ep:
                st.caption(f"PDF no disponible: {_ep}")
        elif not PDF_AVAILABLE:
            st.caption("PDF no disponible (reportlab no instalado)")
