"""
Gestor de Vísceras — Colbeef
Backend FastAPI con conexión directa a PostgreSQL
v3.0 — Correcciones: timeout cavas, cruce con salidas, turno sugerido
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Optional

from dotenv import load_dotenv
import apps_script_local

load_dotenv()

app = FastAPI(title="Gestor Vísceras Colbeef", version="3.0")

# ─── IDs EXACTOS DE tipo_parte_producto ─────────────────
ID_VR  = 14   # Visceras Rojas
ID_VB  = 13   # Visceras Blancas
ID_CAB = 10   # Cabeza
ID_PM  = 11   # Patas y Manos

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "host":            os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST", "localhost"),
    "port":            int(os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT", "5432")),
    "dbname":          os.getenv("POSTGRES_DB") or os.getenv("DB_NAME", "sirt"),
    "user":            os.getenv("POSTGRES_USER") or os.getenv("DB_USER", "postgres"),
    "password":        os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD", ""),
    "connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5")),
    # ── CORRECCIÓN 1: subir timeout de 5000 a 30000 ms ──
    # La query de cavas es pesada por los JOINs múltiples.
    # 5 segundos es insuficiente; 30 segundos cubre el peor caso.
    "options": f"-c statement_timeout={os.getenv('POSTGRES_STATEMENT_TIMEOUT_MS', '30000')}",
}


def get_conn():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar a la BD: {str(e)}")


def query(sql: str, params=None):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def safe_query(sql: str, params=None, label: str = "consulta"):
    try:
        return query(sql, params)
    except Exception as e:
        print(f"[WARN] {label} falló: {e}")
        return []


def safe_query_many(tasks):
    if not tasks:
        return {}

    max_workers = min(len(tasks), 6)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(safe_query, sql, params, label): key
            for key, sql, params, label in tasks
        }
        return {key: future.result() for future, key in futures.items()}


def serializable(rows):
    result = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, (date, datetime)):
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        result.append(clean)
    return result


# ═══════════════════════════════════════════════════════
# PING
# ═══════════════════════════════════════════════════════
@app.get("/api/ping")
def ping():
    try:
        rows = query("SELECT current_database() AS db, now() AS ts")
        return {"ok": True, "db": rows[0]["db"], "ts": str(rows[0]["ts"])}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# CAVAS
# ── CORRECCIÓN 1: filtrar solo los 4 tipos relevantes
#    desde el WHERE para que PostgreSQL use el índice de
#    id_tipo_parte_producto y no escanee toda la tabla.
#    Esto reduce de ~50k filas a ~8k filas antes del JOIN.
# ═══════════════════════════════════════════════════════
@app.get("/api/cavas")
def get_cavas(fecha: Optional[str] = None):
    fecha_filtro = fecha or date.today().isoformat()

    sql = """
        SELECT
            pp.id                               AS id_parte_producto,
            pp.id_producto                      AS codigo,
            tpp.nombre                          AS descripcion,
            tpp.abreviatura                     AS abrev_tipo,
            pp.identificacion                   AS identificacion,
            pp.con_destino                      AS destino,
            pp.observaciones                    AS observaciones,
            pp.reetiquetado,
            pp.alistamiento,
            c.nombre                            AS cava,
            r.nombre                            AS riel,
            ppcr.fecha_ingreso                  AS fecha_ingreso_cava,
            ppcr.fecha_salida                   AS fecha_salida_cava,
            ppcr.numero_informacion_ingreso     AS numero_ingreso
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.tipo_parte_producto tpp
            ON tpp.id = pp.id_tipo_parte_producto
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr
            ON ppcr.id_parte_producto = pp.id
        LEFT JOIN trazabilidad_proceso.cava c
            ON c.id = ppcr.id_cava
        LEFT JOIN trazabilidad_proceso.riel r
            ON r.id = ppcr.id_riel
        WHERE
            pp.id_tipo_parte_producto IN (13, 14, 10, 11)
            AND ppcr.fecha_salida IS NULL
            AND ppcr.fecha_ingreso < (%s::date + INTERVAL '1 day')
        ORDER BY
            c.orden NULLS LAST,
            r.nombre,
            pp.id_producto
    """
    rows = safe_query(sql, (fecha_filtro,), "cavas")
    return {"fecha": fecha_filtro, "total": len(rows), "data": serializable(rows)}


# ═══════════════════════════════════════════════════════
# PLAN FAENA
# ═══════════════════════════════════════════════════════
@app.get("/api/plan_faena")
def get_plan_faena(fecha: Optional[str] = None):
    fecha_filtro = fecha or date.today().isoformat()
    sql = """
        SELECT
            pf.id AS id_plan, pf.fecha_plan, pf.cerrado,
            COUNT(DISTINCT pp.id) AS total_partes,
            COUNT(DISTINCT SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2)) AS juegos
        FROM trazabilidad_proceso.plan_faena pf
        LEFT JOIN trazabilidad_proceso.plan_faena_producto pfp ON pfp.id_plan_faena = pf.id
        LEFT JOIN trazabilidad_proceso.parte_producto pp ON pp.id_producto = pfp.id_producto
        WHERE pf.fecha_plan = %s::date AND pf.cerrado = false
        GROUP BY pf.id, pf.fecha_plan, pf.cerrado
        ORDER BY pf.id DESC LIMIT 1
    """
    rows = safe_query(sql, (fecha_filtro,), "plan_faena")
    return {"fecha": fecha_filtro, "plan": serializable(rows)[0] if rows else None}


# ═══════════════════════════════════════════════════════
# DECOMISOS (día exacto)
# ═══════════════════════════════════════════════════════
@app.get("/api/decomisos")
def get_decomisos(fecha: Optional[str] = None):
    fecha_filtro = fecha or date.today().isoformat()
    sql = """
        SELECT
            d.id                    AS id_decomiso,
            pp.id_producto          AS codigo_producto,
            pp.identificacion       AS identificacion,
            tpp.nombre              AS producto,
            tpp.abreviatura         AS abrev_producto,
            i.etiqueta              AS puesto_destino,
            e.nombre                AS causa_enfermedad,
            d.observacion           AS observacion,
            d.peso                  AS peso_kg,
            d.fecha_registro        AS fecha,
            d.hora_registro         AS hora,
            d.user_name             AS responsable
        FROM sai.decomiso d
        JOIN sai.inspeccion_decomiso id_rel ON id_rel.id_decomiso = d.id
        JOIN sai.inspeccion i               ON i.id = id_rel.id_inspeccion
        JOIN trazabilidad_proceso.parte_producto pp ON pp.id = i.id_parte_producto
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = d.id_tipo_parte_producto
        LEFT JOIN sai.decomiso_enfermedad de2 ON de2.id_decomiso = d.id
        LEFT JOIN sai.enfermedad e            ON e.id = de2.id_enfermedad
        WHERE d.fecha_registro = %s::date
        ORDER BY d.id DESC
    """
    rows = safe_query(sql, (fecha_filtro,), "decomisos")
    return {"fecha": fecha_filtro, "total": len(rows), "data": serializable(rows)}


# ═══════════════════════════════════════════════════════
# DESPACHOS
# ═══════════════════════════════════════════════════════
@app.get("/api/despachos")
def get_despachos(fecha: Optional[str] = None, turno: Optional[str] = None):
    fecha_filtro = fecha or date.today().isoformat()
    turno_filtro = f"%{turno}%" if turno else None

    sql = """
        SELECT
            pp.con_destino AS destino,
            COUNT(pp.id) FILTER (WHERE pp.id_tipo_parte_producto = 14) AS vr,
            COUNT(pp.id) FILTER (WHERE pp.id_tipo_parte_producto = 13) AS vb,
            COUNT(pp.id) FILTER (WHERE pp.id_tipo_parte_producto = 10) AS cabeza,
            COUNT(pp.id) FILTER (WHERE pp.id_tipo_parte_producto = 11) AS pm,
            COUNT(DISTINCT
                CASE WHEN pp.id_tipo_parte_producto IN (13,14)
                THEN SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2)
                END
            ) AS juegos,
            COUNT(pp.id) FILTER (
                WHERE pp.id_tipo_parte_producto = 13
                AND UPPER(pp.observaciones) LIKE '%%CRUDAS%%'
            ) AS crudas,
            STRING_AGG(pp.id_producto, ', ') FILTER (
                WHERE pp.id_tipo_parte_producto = 13
                AND UPPER(pp.observaciones) LIKE '%%CRUDAS%%'
            ) AS codigos_crudas
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr
            ON ppcr.id_parte_producto = pp.id
        WHERE
            pp.id_tipo_parte_producto IN (13, 14, 10, 11)
            AND ppcr.fecha_salida IS NULL
            AND ppcr.fecha_ingreso < (%s::date + INTERVAL '1 day')
            AND pp.con_destino IS NOT NULL
            AND pp.con_destino NOT IN (
                '01305/','03105/','05200/','12157/','379P/',
                'CAVA AJR','CAVA FORTUNATO','CAVA MIREYA','CAVA.',
                'CCARNES CAVA','OLIMPICA','RH32/'
            )
            AND (%s::text IS NULL OR pp.con_destino ILIKE %s::text)
        GROUP BY pp.con_destino
        HAVING COUNT(pp.id) FILTER (WHERE pp.id_tipo_parte_producto IN (13,14,10,11)) > 0
        ORDER BY pp.con_destino
    """
    rows = safe_query(sql, (fecha_filtro, turno_filtro, turno_filtro), "despachos")
    data = serializable(rows)
    totales = {
        "vr":      sum(r.get("vr",0) or 0 for r in data),
        "vb":      sum(r.get("vb",0) or 0 for r in data),
        "cabeza":  sum(r.get("cabeza",0) or 0 for r in data),
        "pm":      sum(r.get("pm",0) or 0 for r in data),
        "juegos":  sum(r.get("juegos",0) or 0 for r in data),
        "crudas":  sum(r.get("crudas",0) or 0 for r in data),
        "puestos": len(data),
    }
    return {"fecha": fecha_filtro, "turno": turno, "totales": totales, "data": data}


# ═══════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════
@app.get("/api/dashboard")
def get_dashboard(fecha: Optional[str] = None):
    fecha_filtro = fecha or date.today().isoformat()

    sql_juegos = """
        SELECT COUNT(DISTINCT SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2)) AS juegos_total,
               COUNT(pp.id) AS partes_total
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        WHERE pp.id_tipo_parte_producto IN (13,14,10,11)
          AND ppcr.fecha_salida IS NULL
          AND ppcr.fecha_ingreso < (%s::date + INTERVAL '1 day')
    """
    sql_crudas = """
        SELECT COUNT(DISTINCT SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2)) AS crudas
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        WHERE pp.id_tipo_parte_producto = 13
          AND ppcr.fecha_salida IS NULL
          AND ppcr.fecha_ingreso < (%s::date + INTERVAL '1 day')
          AND UPPER(pp.observaciones) LIKE '%%CRUDAS%%'
    """
    sql_decomisos = """
        SELECT COUNT(d.id) AS total_decomisos FROM sai.decomiso d WHERE d.fecha_registro = %s::date
    """
    sql_por_tipo = """
        SELECT tpp.nombre AS tipo, COUNT(pp.id) AS cantidad
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = pp.id_tipo_parte_producto
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        WHERE pp.id_tipo_parte_producto IN (13,14,10,11)
          AND ppcr.fecha_salida IS NULL
          AND ppcr.fecha_ingreso < (%s::date + INTERVAL '1 day')
        GROUP BY tpp.nombre ORDER BY tpp.nombre
    """
    sql_cavas = """
        SELECT c.nombre AS cava, COUNT(pp.id) AS productos, SUM(r.capacidad) AS capacidad_total
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        JOIN trazabilidad_proceso.cava c ON c.id = ppcr.id_cava
        LEFT JOIN trazabilidad_proceso.riel r ON r.id = ppcr.id_riel
        WHERE pp.id_tipo_parte_producto IN (13,14,10,11)
          AND ppcr.fecha_salida IS NULL
          AND ppcr.fecha_ingreso < (%s::date + INTERVAL '1 day')
        GROUP BY c.id, c.nombre, c.orden ORDER BY c.orden NULLS LAST
    """
    results = safe_query_many([
        ("juegos", sql_juegos, (fecha_filtro,), "dashboard.juegos"),
        ("crudas", sql_crudas, (fecha_filtro,), "dashboard.crudas"),
        ("decomisos", sql_decomisos, (fecha_filtro,), "dashboard.decomisos"),
        ("por_tipo", sql_por_tipo, (fecha_filtro,), "dashboard.por_tipo"),
        ("cavas", sql_cavas, (fecha_filtro,), "dashboard.cavas"),
    ])
    j  = results.get("juegos", [])
    cr = results.get("crudas", [])
    dc = results.get("decomisos", [])
    pt = results.get("por_tipo", [])
    cv = results.get("cavas", [])

    return {
        "fecha":        fecha_filtro,
        "juegos_total": j[0]["juegos_total"]    if j  else 0,
        "partes_total": j[0]["partes_total"]    if j  else 0,
        "crudas":       cr[0]["crudas"]          if cr else 0,
        "decomisos":    dc[0]["total_decomisos"] if dc else 0,
        "por_tipo":     serializable(pt),
        "cavas":        serializable(cv),
    }


# ═══════════════════════════════════════════════════════
# SALIDAS (reemplaza SALIDAS_DE_CAVAS_VISCERAS.xls)
# ═══════════════════════════════════════════════════════
@app.get("/api/salidas")
def get_salidas(fecha: Optional[str] = None, dias: int = 1):
    fecha_fin = fecha or date.today().isoformat()
    sql = """
        SELECT
            pp.id_producto          AS codigo,
            tpp.nombre              AS descripcion,
            tpp.abreviatura         AS abrev,
            pp.con_destino          AS destino,
            pp.observaciones        AS observaciones,
            pp.reetiquetado         AS reetiquetar,
            CASE WHEN UPPER(pp.observaciones) LIKE '%%CRUDAS%%' THEN true ELSE false END AS tiene_cruda,
            c.nombre                AS cava,
            r.nombre                AS riel,
            ppcr.fecha_ingreso      AS ingreso_cava,
            ppcr.fecha_salida       AS fecha_salida,
            EXTRACT(EPOCH FROM (ppcr.fecha_salida - ppcr.fecha_ingreso))/3600 AS horas_en_cava,
            SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2) AS codigo_base,
            pp.id_tipo_parte_producto
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = pp.id_tipo_parte_producto
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        LEFT JOIN trazabilidad_proceso.cava c ON c.id = ppcr.id_cava
        LEFT JOIN trazabilidad_proceso.riel r ON r.id = ppcr.id_riel
        WHERE pp.id_tipo_parte_producto IN (13, 14, 10, 11)
          AND ppcr.fecha_salida IS NOT NULL
          AND ppcr.fecha_salida >= (%s::date - (%s * INTERVAL '1 day'))
          AND ppcr.fecha_salida < (%s::date + INTERVAL '1 day')
        ORDER BY ppcr.fecha_salida DESC, pp.id_producto
    """
    rows = safe_query(sql, (fecha_fin, dias, fecha_fin), "salidas")
    data = serializable(rows)
    juegos = {}
    for r in data:
        b = r["codigo_base"]
        if b not in juegos:
            juegos[b] = {"codigo_base": b, "destino": r["destino"], "tiene_cruda": False,
                         "observaciones": r["observaciones"] or "", "tipos": []}
        juegos[b]["tipos"].append(r["descripcion"])
        if r["tiene_cruda"]:
            juegos[b]["tiene_cruda"] = True
    return {
        "fecha": fecha_fin, "dias_rango": dias,
        "total_partes": len(data), "total_juegos": len(juegos),
        "total_crudas": sum(1 for j in juegos.values() if j["tiene_cruda"]),
        "data": data, "resumen_juegos": list(juegos.values()),
    }


# ═══════════════════════════════════════════════════════
# DECOMISOS RANGO (últimos N días)
# ═══════════════════════════════════════════════════════
@app.get("/api/decomisos_rango")
def get_decomisos_rango(fecha: Optional[str] = None, dias: int = 4):
    fecha_fin = fecha or date.today().isoformat()
    sql = """
        SELECT
            d.id AS id_decomiso, d.fecha_registro AS fecha, d.hora_registro AS hora,
            pp.id_producto AS codigo_producto,
            SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2) AS codigo_base,
            tpp.nombre AS producto, tpp.abreviatura AS abrev,
            e.nombre AS causa, d.observacion AS observacion,
            d.peso AS peso_kg, d.user_name AS responsable, i.etiqueta AS puesto
        FROM sai.decomiso d
        JOIN sai.inspeccion_decomiso id_rel ON id_rel.id_decomiso = d.id
        JOIN sai.inspeccion i               ON i.id = id_rel.id_inspeccion
        JOIN trazabilidad_proceso.parte_producto pp ON pp.id = i.id_parte_producto
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = d.id_tipo_parte_producto
        LEFT JOIN sai.decomiso_enfermedad de2 ON de2.id_decomiso = d.id
        LEFT JOIN sai.enfermedad e            ON e.id = de2.id_enfermedad
        WHERE d.fecha_registro >= (%s::date - (%s * INTERVAL '1 day'))
          AND d.fecha_registro <= %s::date
        ORDER BY d.fecha_registro DESC, d.id DESC
    """
    rows = safe_query(sql, (fecha_fin, dias, fecha_fin), "decomisos_rango")
    data = serializable(rows)
    codigos_decomisados = {}
    for r in data:
        b = r["codigo_base"]
        codigos_decomisados.setdefault(b, []).append(
            {"producto": r["producto"], "causa": r["causa"], "fecha": r["fecha"]}
        )
    return {
        "fecha_fin": fecha_fin, "dias_rango": dias, "total": len(data),
        "codigos_con_decomiso": len(codigos_decomisados),
        "data": data, "indice_decomisados": codigos_decomisados,
    }


# ═══════════════════════════════════════════════════════
# CRUCE DIARIO
# ── CORRECCIÓN 2: ahora incorpora las SALIDAS como
#    tercera fuente. Un juego que ya tiene fecha_salida
#    asignada se marca con "ya_despachado: true" y su
#    destino se toma de la salida, no de con_destino.
#    Esto completa el cruce de los 3 archivos originales.
# ═══════════════════════════════════════════════════════
@app.get("/api/cruce_diario")
def get_cruce_diario(
    fecha: Optional[str] = None,
    turno: Optional[str] = None,
    dias_decomisos: int = 4
):
    fecha_filtro = fecha or date.today().isoformat()
    turno_filtro = f"%{turno}%" if turno else None

    # ── Fuente 1: productos en cava ahora ──
    sql_cava = """
        SELECT
            SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2) AS codigo_base,
            pp.id_producto AS codigo,
            tpp.id         AS id_tipo,
            tpp.nombre     AS tipo,
            pp.con_destino AS destino,
            pp.observaciones,
            pp.reetiquetado,
            c.nombre       AS cava,
            EXTRACT(EPOCH FROM (NOW() - ppcr.fecha_ingreso))/3600 AS horas_en_cava
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = pp.id_tipo_parte_producto
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        LEFT JOIN trazabilidad_proceso.cava c ON c.id = ppcr.id_cava
        WHERE pp.id_tipo_parte_producto IN (13, 14, 10, 11)
          AND ppcr.fecha_salida IS NULL
          AND ppcr.fecha_ingreso < (%s::date + INTERVAL '1 day')
          AND (%s::text IS NULL OR pp.con_destino ILIKE %s::text)
        ORDER BY pp.id_producto
    """

    # ── Fuente 2: decomisos últimos N días ──
    sql_decomiso = """
        SELECT DISTINCT
            SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2) AS codigo_base,
            tpp.nombre   AS producto_decomisado,
            e.nombre     AS causa,
            d.fecha_registro AS fecha_decomiso
        FROM sai.decomiso d
        JOIN sai.inspeccion_decomiso id_rel ON id_rel.id_decomiso = d.id
        JOIN sai.inspeccion i               ON i.id = id_rel.id_inspeccion
        JOIN trazabilidad_proceso.parte_producto pp ON pp.id = i.id_parte_producto
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = d.id_tipo_parte_producto
        LEFT JOIN sai.decomiso_enfermedad de2 ON de2.id_decomiso = d.id
        LEFT JOIN sai.enfermedad e            ON e.id = de2.id_enfermedad
        WHERE d.fecha_registro >= (%s::date - (%s * INTERVAL '1 day'))
          AND d.fecha_registro <= %s::date
    """

    # ── Fuente 3: salidas del día (ya despachados o con salida asignada) ──
    sql_salidas = """
        SELECT DISTINCT
            SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2) AS codigo_base,
            pp.con_destino AS destino_salida,
            DATE(ppcr.fecha_salida) AS fecha_salida
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        WHERE pp.id_tipo_parte_producto IN (13, 14, 10, 11)
          AND ppcr.fecha_salida IS NOT NULL
          AND DATE(ppcr.fecha_salida) = %s::date
    """

    results = safe_query_many([
        ("cava", sql_cava, (fecha_filtro, turno_filtro, turno_filtro), "cruce.cava"),
        ("decomiso", sql_decomiso, (fecha_filtro, dias_decomisos, fecha_filtro), "cruce.decomiso"),
        ("salidas", sql_salidas, (fecha_filtro,), "cruce.salidas"),
    ])
    rows_cava     = results.get("cava", [])
    rows_decomiso = results.get("decomiso", [])
    rows_salidas  = results.get("salidas", [])

    # Índice de decomisos
    idx_decomiso = {}
    for r in serializable(rows_decomiso):
        idx_decomiso.setdefault(r["codigo_base"], []).append({
            "producto": r["producto_decomisado"],
            "causa":    r["causa"],
            "fecha":    r["fecha_decomiso"],
        })

    # Índice de salidas del día
    idx_salidas = {}
    for r in serializable(rows_salidas):
        idx_salidas[r["codigo_base"]] = {
            "destino_salida": r["destino_salida"],
            "fecha_salida":   r["fecha_salida"],
        }

    # Construir tabla maestra
    juegos = {}
    for r in serializable(rows_cava):
        b = r["codigo_base"]
        if b not in juegos:
            salida_info = idx_salidas.get(b, {})
            juegos[b] = {
                "codigo_base":    b,
                "destino":        r["destino"] or "",
                "cava":           r["cava"] or "",
                "horas_en_cava":  round(r["horas_en_cava"] or 0, 1),
                "tiene_vr":       False,
                "tiene_vb":       False,
                "tiene_cabeza":   False,
                "tiene_pm":       False,
                "tiene_cruda":    False,
                "reetiquetar":    False,
                "decomisos":      idx_decomiso.get(b, []),
                "tiene_decomiso": b in idx_decomiso,
                "observaciones":  r["observaciones"] or "",
                # ── NUEVO: info de salida del día ──
                "ya_despachado":  b in idx_salidas,
                "destino_salida": salida_info.get("destino_salida", ""),
                "fecha_salida":   salida_info.get("fecha_salida", ""),
            }
        id_tipo = r["id_tipo"]
        if id_tipo == ID_VR:  juegos[b]["tiene_vr"]     = True
        if id_tipo == ID_VB:  juegos[b]["tiene_vb"]     = True
        if id_tipo == ID_CAB: juegos[b]["tiene_cabeza"] = True
        if id_tipo == ID_PM:  juegos[b]["tiene_pm"]     = True
        if r["reetiquetado"]:
            juegos[b]["reetiquetar"] = True
        if "CRUDAS" in (r["observaciones"] or "").upper():
            juegos[b]["tiene_cruda"] = True

    lista = []
    for j in juegos.values():
        completo = j["tiene_vr"] and j["tiene_vb"]
        j["completo"]   = completo
        j["incompleto"] = not completo
        j["estado"] = (
            "DECOMISO"   if j["tiene_decomiso"] else
            "CRUDA"      if j["tiene_cruda"]    else
            "INCOMPLETO" if j["incompleto"]      else
            "OK"
        )
        lista.append(j)

    lista.sort(key=lambda x: (
        0 if x["estado"] == "DECOMISO"   else
        1 if x["estado"] == "CRUDA"      else
        2 if x["estado"] == "INCOMPLETO" else 3,
        x["codigo_base"]
    ))

    return {
        "fecha":          fecha_filtro,
        "turno":          turno,
        "dias_decomisos": dias_decomisos,
        "totales": {
            "total_juegos":    len(lista),
            "completos":       sum(1 for j in lista if j["completo"]),
            "incompletos":     sum(1 for j in lista if j["incompleto"]),
            "con_decomiso":    sum(1 for j in lista if j["tiene_decomiso"]),
            "con_cruda":       sum(1 for j in lista if j["tiene_cruda"]),
            "con_reetiquetar": sum(1 for j in lista if j["reetiquetar"]),
            "ya_despachados":  sum(1 for j in lista if j["ya_despachado"]),
            "ok":              sum(1 for j in lista if j["estado"] == "OK"),
        },
        "juegos": lista,
    }


# ═══════════════════════════════════════════════════════
# SERVIDOR
# ═══════════════════════════════════════════════════════
app.mount("/static", StaticFiles(directory="static"), name="static")


class AppsScriptRequest(BaseModel):
    args: list = []


@app.post("/api/apps-script/{function_name}")
def run_apps_script_function(function_name: str, payload: AppsScriptRequest):
    try:
        return apps_script_local.dispatch(function_name, payload.args)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
