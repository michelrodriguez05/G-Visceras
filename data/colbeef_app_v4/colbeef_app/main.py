"""
Gestor de Vísceras — Colbeef
Backend FastAPI con conexión directa a PostgreSQL
v2.1 — IDs de tipo_parte_producto confirmados desde la BD real
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from datetime import date, datetime
from typing import Optional

app = FastAPI(title="Gestor Vísceras Colbeef", version="2.1")

# ─── IDs EXACTOS DE tipo_parte_producto ─────────────────
# Confirmados con: SELECT id, nombre FROM trazabilidad_proceso.tipo_parte_producto
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

# ─── CONFIGURACIÓN DE BD ────────────────────────────────
# Edita estos valores con los datos reales del servidor
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME",     "colbeef"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "tu_password_aqui"),
}

def get_conn():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
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

# ─── UTILIDADES ────────────────────────────────────────
def serializable(rows):
    """Convierte date/datetime a string para que JSON los acepte."""
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
# ENDPOINT: Estado de conexión
# ═══════════════════════════════════════════════════════
@app.get("/api/ping")
def ping():
    try:
        rows = query("SELECT current_database() AS db, now() AS ts")
        return {"ok": True, "db": rows[0]["db"], "ts": str(rows[0]["ts"])}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# ENDPOINT: Estado de Cavas (reemplaza el XLS 1)
# Equivale a: estado_de_productos_en_cavas_y_en_plan_de_faena_actual.xls
# ═══════════════════════════════════════════════════════
@app.get("/api/cavas")
def get_cavas(fecha: Optional[str] = None):
    """
    Retorna todos los productos actualmente en cava (sin fecha_salida),
    con su tipo, destino asignado, cava y observaciones.
    Equivale al reporte 'Estado de productos en cavas y plan de faena actual'.
    Si no se pasa fecha, usa el día de hoy.
    """
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
        LEFT JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr
            ON ppcr.id_parte_producto = pp.id
        LEFT JOIN trazabilidad_proceso.cava c
            ON c.id = ppcr.id_cava
        LEFT JOIN trazabilidad_proceso.riel r
            ON r.id = ppcr.id_riel
        WHERE
            ppcr.fecha_salida IS NULL
            AND DATE(ppcr.fecha_ingreso) <= %s::date
        ORDER BY
            c.orden NULLS LAST,
            r.nombre,
            pp.id_producto
    """
    rows = query(sql, (fecha_filtro,))
    return {"fecha": fecha_filtro, "total": len(rows), "data": serializable(rows)}


# ═══════════════════════════════════════════════════════
# ENDPOINT: Plan de Faena actual
# ═══════════════════════════════════════════════════════
@app.get("/api/plan_faena")
def get_plan_faena(fecha: Optional[str] = None):
    """Retorna el plan de faena activo (no cerrado) más reciente."""
    fecha_filtro = fecha or date.today().isoformat()

    sql = """
        SELECT
            pf.id                   AS id_plan,
            pf.fecha_plan,
            pf.cerrado,
            COUNT(DISTINCT pp.id)   AS total_partes,
            COUNT(DISTINCT SPLIT_PART(pp.id_producto, '-', 1) || '-' || SPLIT_PART(pp.id_producto, '-', 2)) AS juegos
        FROM trazabilidad_proceso.plan_faena pf
        LEFT JOIN trazabilidad_proceso.plan_faena_producto pfp
            ON pfp.id_plan_faena = pf.id
        LEFT JOIN trazabilidad_proceso.parte_producto pp
            ON pp.id_producto = pfp.id_producto
        WHERE
            pf.fecha_plan = %s::date
            AND pf.cerrado = false
        GROUP BY pf.id, pf.fecha_plan, pf.cerrado
        ORDER BY pf.id DESC
        LIMIT 1
    """
    rows = query(sql, (fecha_filtro,))
    return {"fecha": fecha_filtro, "plan": serializable(rows)[0] if rows else None}


# ═══════════════════════════════════════════════════════
# ENDPOINT: Decomisos (reemplaza el XLS 2)
# Equivale a: reporte_de_decomisos_de_subproductos.xls
# ═══════════════════════════════════════════════════════
@app.get("/api/decomisos")
def get_decomisos(fecha: Optional[str] = None):
    """
    Retorna decomisos del día con producto, causa (enfermedad) y puesto.
    Equivale al reporte 'Reporte de decomisos de subproductos'.
    """
    fecha_filtro = fecha or date.today().isoformat()

    sql = """
        SELECT
            d.id                            AS id_decomiso,
            pp.id_producto                  AS codigo_producto,
            pp.identificacion               AS identificacion,
            tpp.nombre                      AS producto,
            tpp.abreviatura                 AS abrev_producto,
            i.etiqueta                      AS puesto_destino,
            e.nombre                        AS causa_enfermedad,
            d.observacion                   AS observacion,
            d.peso                          AS peso_kg,
            d.fecha_registro                AS fecha,
            d.hora_registro                 AS hora,
            d.user_name                     AS responsable,
            s.nombre                        AS sucursal
        FROM sai.decomiso d
        JOIN sai.inspeccion_decomiso id_rel
            ON id_rel.id_decomiso = d.id
        JOIN sai.inspeccion i
            ON i.id = id_rel.id_inspeccion
        JOIN trazabilidad_proceso.parte_producto pp
            ON pp.id = i.id_parte_producto
        JOIN trazabilidad_proceso.tipo_parte_producto tpp
            ON tpp.id = d.id_tipo_parte_producto
        LEFT JOIN sai.decomiso_enfermedad de2
            ON de2.id_decomiso = d.id
        LEFT JOIN sai.enfermedad e
            ON e.id = de2.id_enfermedad
        LEFT JOIN organizaciones.sucursal s
            ON s.id = (
                SELECT va.id_sucursal
                FROM trazabilidad_proceso.vehiculo_asignado_sucursal vas
                JOIN trazabilidad_proceso.vehiculo_asignado va ON va.id = vas.id_vehiculo_asignado
                LIMIT 1
            )
        WHERE d.fecha_registro = %s::date
        ORDER BY d.id DESC
    """
    rows = query(sql, (fecha_filtro,))
    return {"fecha": fecha_filtro, "total": len(rows), "data": serializable(rows)}


# ═══════════════════════════════════════════════════════
# ENDPOINT: Despachos por destino — tabla pivot
# Columnas: Puesto | VR | VB | Cabeza | PM | Juegos | Turno | Crudas
# Reproduce exactamente la lógica del App Script original
# ═══════════════════════════════════════════════════════
@app.get("/api/despachos")
def get_despachos(fecha: Optional[str] = None, turno: Optional[str] = None):
    """
    Tabla pivot por puesto de destino:
      - VR  = id_tipo_parte_producto = 14 (Visceras Rojas)
      - VB  = id_tipo_parte_producto = 13 (Visceras Blancas)
      - CAB = id_tipo_parte_producto = 10 (Cabeza)
      - PM  = id_tipo_parte_producto = 11 (Patas y Manos)
      - Juegos = códigos base únicos (XXXX-XXXXX) con VR + VB
      - Crudas = VB con observaciones LIKE 'CRUDAS'
    Solo incluye destinos activos (excluye cavas propias y puestos internos).
    """
    fecha_filtro = fecha or date.today().isoformat()

    # El turno en los destinos viene como sufijo: "NOMBRE CLIENTE / DxL"
    turno_filtro = f"%{turno}%" if turno else None

    sql = """
        SELECT
            pp.con_destino                              AS destino,

            -- Conteos por tipo usando IDs exactos de la BD
            COUNT(pp.id) FILTER (
                WHERE pp.id_tipo_parte_producto = 14)   AS vr,
            COUNT(pp.id) FILTER (
                WHERE pp.id_tipo_parte_producto = 13)   AS vb,
            COUNT(pp.id) FILTER (
                WHERE pp.id_tipo_parte_producto = 10)   AS cabeza,
            COUNT(pp.id) FILTER (
                WHERE pp.id_tipo_parte_producto = 11)   AS pm,

            -- Juegos = códigos base únicos que tienen TANTO VR como VB en este destino
            COUNT(DISTINCT
                CASE WHEN pp.id_tipo_parte_producto IN (13, 14)
                THEN SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2)
                END
            )                                           AS juegos,

            -- Crudas = VB con observación CRUDAS
            COUNT(pp.id) FILTER (
                WHERE pp.id_tipo_parte_producto = 13
                AND UPPER(pp.observaciones) LIKE '%CRUDAS%'
            )                                           AS crudas,

            -- Listado de códigos con cruda para el detalle
            STRING_AGG(pp.id_producto, ', ') FILTER (
                WHERE pp.id_tipo_parte_producto = 13
                AND UPPER(pp.observaciones) LIKE '%CRUDAS%'
            )                                           AS codigos_crudas

        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr
            ON ppcr.id_parte_producto = pp.id
        WHERE
            ppcr.fecha_salida IS NULL
            AND DATE(ppcr.fecha_ingreso) <= %s::date
            AND pp.con_destino IS NOT NULL
            AND pp.con_destino NOT IN (
                '01305/','03105/','05200/','12157/','379P/',
                'CAVA AJR','CAVA FORTUNATO','CAVA MIREYA','CAVA.',
                'CCARNES CAVA','OLIMPICA','RH32/'
            )
            AND pp.id_tipo_parte_producto IN (13, 14, 10, 11)
            AND (%s::text IS NULL OR pp.con_destino ILIKE %s::text)
        GROUP BY pp.con_destino
        HAVING
            COUNT(pp.id) FILTER (WHERE pp.id_tipo_parte_producto IN (13,14,10,11)) > 0
        ORDER BY pp.con_destino
    """
    rows = query(sql, (fecha_filtro, turno_filtro, turno_filtro))
    data = serializable(rows)

    # Totales para el resumen del frontend
    totales = {
        "vr":     sum(r.get("vr",0) or 0     for r in data),
        "vb":     sum(r.get("vb",0) or 0     for r in data),
        "cabeza": sum(r.get("cabeza",0) or 0 for r in data),
        "pm":     sum(r.get("pm",0) or 0     for r in data),
        "juegos": sum(r.get("juegos",0) or 0 for r in data),
        "crudas": sum(r.get("crudas",0) or 0 for r in data),
        "puestos": len(data),
    }

    return {
        "fecha":    fecha_filtro,
        "turno":    turno,
        "totales":  totales,
        "data":     data,
    }


# ═══════════════════════════════════════════════════════
# ENDPOINT: Dashboard — métricas resumen
# ═══════════════════════════════════════════════════════
@app.get("/api/dashboard")
def get_dashboard(fecha: Optional[str] = None):
    """Métricas agregadas para el panel principal."""
    fecha_filtro = fecha or date.today().isoformat()

    # Juegos totales en cava
    sql_juegos = """
        SELECT COUNT(DISTINCT
            SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2)
        ) AS juegos_total,
        COUNT(pp.id) AS partes_total
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr
            ON ppcr.id_parte_producto = pp.id
        WHERE ppcr.fecha_salida IS NULL
          AND DATE(ppcr.fecha_ingreso) <= %s::date
    """

    # Crudas (Visceras Blancas id=13 con observación CRUDAS)
    sql_crudas = """
        SELECT COUNT(DISTINCT
            SPLIT_PART(pp.id_producto,'-',1)||'-'||SPLIT_PART(pp.id_producto,'-',2)
        ) AS crudas
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        WHERE ppcr.fecha_salida IS NULL
          AND DATE(ppcr.fecha_ingreso) <= %s::date
          AND pp.id_tipo_parte_producto = 13
          AND UPPER(pp.observaciones) LIKE '%CRUDAS%'
    """

    # Decomisos del día
    sql_decomisos = """
        SELECT COUNT(d.id) AS total_decomisos
        FROM sai.decomiso d
        WHERE d.fecha_registro = %s::date
    """

    # Totales por tipo de producto en cava
    sql_por_tipo = """
        SELECT tpp.nombre AS tipo, COUNT(pp.id) AS cantidad
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = pp.id_tipo_parte_producto
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        WHERE ppcr.fecha_salida IS NULL
          AND DATE(ppcr.fecha_ingreso) <= %s::date
        GROUP BY tpp.nombre
        ORDER BY tpp.nombre
    """

    # Ocupación por cava
    sql_cavas = """
        SELECT c.nombre AS cava, COUNT(pp.id) AS productos,
               SUM(r.capacidad) AS capacidad_total
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        JOIN trazabilidad_proceso.cava c ON c.id = ppcr.id_cava
        LEFT JOIN trazabilidad_proceso.riel r ON r.id = ppcr.id_riel
        WHERE ppcr.fecha_salida IS NULL
          AND DATE(ppcr.fecha_ingreso) <= %s::date
        GROUP BY c.id, c.nombre, c.orden
        ORDER BY c.orden NULLS LAST
    """

    j  = query(sql_juegos,   (fecha_filtro,))
    cr = query(sql_crudas,   (fecha_filtro,))
    dc = query(sql_decomisos,(fecha_filtro,))
    pt = query(sql_por_tipo, (fecha_filtro,))
    cv = query(sql_cavas,    (fecha_filtro,))

    return {
        "fecha":          fecha_filtro,
        "juegos_total":   j[0]["juegos_total"]   if j  else 0,
        "partes_total":   j[0]["partes_total"]   if j  else 0,
        "crudas":         cr[0]["crudas"]         if cr else 0,
        "decomisos":      dc[0]["total_decomisos"] if dc else 0,
        "por_tipo":       serializable(pt),
        "cavas":          serializable(cv),
    }


# ─── Servir el frontend ────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# ═══════════════════════════════════════════════════════
# ENDPOINT: Salidas de Cava (reemplaza SALIDAS_DE_CAVAS_VISCERAS.xls)
# Este archivo llegaba por correo — ahora se consulta directo a la BD
# Son los productos que YA SALIERON de cava (fecha_salida IS NOT NULL)
# con su destino, observaciones y si tienen crudas
# ═══════════════════════════════════════════════════════
@app.get("/api/salidas")
def get_salidas(fecha: Optional[str] = None, dias: int = 1):
    """
    Retorna productos que salieron de cava en los últimos N días.
    Equivale al archivo SALIDAS_DE_CAVAS_VISCERAS_XX-XX-XX.xls.
    Columnas: Ingreso a Cava | Código | Descripción | Peso en Pie |
              Cliente | Sexo | Especie | Destino | Cava | Riel |
              Re-etiquetar | Devolución | Observaciones | Horas en Cava
    """
    fecha_fin   = fecha or date.today().isoformat()

    sql = """
        SELECT
            pp.id_producto                                          AS codigo,
            tpp.nombre                                              AS descripcion,
            tpp.abreviatura                                         AS abrev,
            pp.con_destino                                          AS destino,
            pp.observaciones                                        AS observaciones,
            pp.reetiquetado                                         AS reetiquetar,
            CASE WHEN UPPER(pp.observaciones) LIKE '%CRUDAS%'
                 THEN true ELSE false END                           AS tiene_cruda,
            c.nombre                                                AS cava,
            r.nombre                                                AS riel,
            ppcr.fecha_ingreso                                      AS ingreso_cava,
            ppcr.fecha_salida                                       AS fecha_salida,
            EXTRACT(EPOCH FROM (ppcr.fecha_salida - ppcr.fecha_ingreso))/3600
                                                                    AS horas_en_cava,
            -- Código base para cruzar con decomisos
            SPLIT_PART(pp.id_producto,'-',1)||'-'||
            SPLIT_PART(pp.id_producto,'-',2)                        AS codigo_base,
            id_tipo_parte_producto
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
            ppcr.fecha_salida IS NOT NULL
            AND DATE(ppcr.fecha_salida) >= (%s::date - INTERVAL '%s days')
            AND DATE(ppcr.fecha_salida) <= %s::date
            AND pp.id_tipo_parte_producto IN (13, 14, 10, 11)
        ORDER BY ppcr.fecha_salida DESC, pp.id_producto
    """
    rows = query(sql, (fecha_fin, dias, fecha_fin))
    data = serializable(rows)

    # Agrupar por juego (código base) para el resumen
    juegos = {}
    for r in data:
        b = r["codigo_base"]
        if b not in juegos:
            juegos[b] = {
                "codigo_base": b,
                "destino":     r["destino"],
                "tiene_cruda": False,
                "observaciones": r["observaciones"] or "",
                "tipos": []
            }
        juegos[b]["tipos"].append(r["descripcion"])
        if r["tiene_cruda"]:
            juegos[b]["tiene_cruda"] = True

    total_crudas = sum(1 for j in juegos.values() if j["tiene_cruda"])

    return {
        "fecha":         fecha_fin,
        "dias_rango":    dias,
        "total_partes":  len(data),
        "total_juegos":  len(juegos),
        "total_crudas":  total_crudas,
        "data":          data,
        "resumen_juegos": list(juegos.values())
    }


# ═══════════════════════════════════════════════════════
# ENDPOINT: DECOMISOS con rango de fechas (3-4 días atrás)
# El proceso diario requiere ver decomisos de días anteriores
# para cruzarlos con los productos que están en cava hoy
# ═══════════════════════════════════════════════════════
@app.get("/api/decomisos_rango")
def get_decomisos_rango(fecha: Optional[str] = None, dias: int = 4):
    """
    Decomisos de los últimos N días (por defecto 4).
    Usado para cruzar con el estado actual de cavas:
    si un producto en cava tiene decomiso reciente → marcarlo.
    """
    fecha_fin   = fecha or date.today().isoformat()

    sql = """
        SELECT
            d.id                                                    AS id_decomiso,
            d.fecha_registro                                        AS fecha,
            d.hora_registro                                         AS hora,
            pp.id_producto                                          AS codigo_producto,
            SPLIT_PART(pp.id_producto,'-',1)||'-'||
            SPLIT_PART(pp.id_producto,'-',2)                        AS codigo_base,
            tpp.nombre                                              AS producto,
            tpp.abreviatura                                         AS abrev,
            e.nombre                                                AS causa,
            d.observacion                                           AS observacion,
            d.peso                                                  AS peso_kg,
            d.user_name                                             AS responsable,
            i.etiqueta                                              AS puesto
        FROM sai.decomiso d
        JOIN sai.inspeccion_decomiso id_rel ON id_rel.id_decomiso = d.id
        JOIN sai.inspeccion i               ON i.id = id_rel.id_inspeccion
        JOIN trazabilidad_proceso.parte_producto pp ON pp.id = i.id_parte_producto
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = d.id_tipo_parte_producto
        LEFT JOIN sai.decomiso_enfermedad de2 ON de2.id_decomiso = d.id
        LEFT JOIN sai.enfermedad e            ON e.id = de2.id_enfermedad
        WHERE
            d.fecha_registro >= (%s::date - INTERVAL '%s days')
            AND d.fecha_registro <= %s::date
        ORDER BY d.fecha_registro DESC, d.id DESC
    """
    rows = query(sql, (fecha_fin, dias, fecha_fin))
    data = serializable(rows)

    # Índice de códigos base con decomiso para el cruce
    codigos_decomisados = {}
    for r in data:
        b = r["codigo_base"]
        if b not in codigos_decomisados:
            codigos_decomisados[b] = []
        codigos_decomisados[b].append({
            "producto": r["producto"],
            "causa":    r["causa"],
            "fecha":    r["fecha"]
        })

    return {
        "fecha_fin":            fecha_fin,
        "dias_rango":           dias,
        "total":                len(data),
        "codigos_con_decomiso": len(codigos_decomisados),
        "data":                 data,
        "indice_decomisados":   codigos_decomisados
    }


# ═══════════════════════════════════════════════════════
# ENDPOINT: CRUCE DIARIO — el proceso completo
# Combina los 3 archivos originales en una sola consulta:
#   1. Estado de Cavas (productos en cava hoy)
#   2. Decomisos (últimos 4 días)
#   3. Salidas de Cava (productos que ya salieron)
# Resultado: tabla maestra con estado de cada juego
# ═══════════════════════════════════════════════════════
@app.get("/api/cruce_diario")
def get_cruce_diario(fecha: Optional[str] = None, turno: Optional[str] = None, dias_decomisos: int = 4):
    """
    Proceso principal diario. Reemplaza el cruce manual de los 3 archivos XLS.
    Para cada juego (código base) informa:
      - Si está en cava hoy
      - Si tiene decomiso en los últimos N días
      - Si ya tiene destino asignado (salida)
      - Si tiene crudas
      - Qué subproductos se van a despachar y a qué puesto
    """
    fecha_filtro = fecha or date.today().isoformat()
    turno_filtro = f"%{turno}%" if turno else None

    # ── 1. Productos en cava hoy ──
    sql_cava = """
        SELECT
            SPLIT_PART(pp.id_producto,'-',1)||'-'||
            SPLIT_PART(pp.id_producto,'-',2)                    AS codigo_base,
            pp.id_producto                                       AS codigo,
            tpp.nombre                                           AS tipo,
            tpp.id                                               AS id_tipo,
            pp.con_destino                                       AS destino,
            pp.observaciones                                     AS observaciones,
            pp.reetiquetado,
            c.nombre                                             AS cava,
            EXTRACT(EPOCH FROM (NOW() - ppcr.fecha_ingreso))/3600 AS horas_en_cava
        FROM trazabilidad_proceso.parte_producto pp
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = pp.id_tipo_parte_producto
        JOIN trazabilidad_proceso.parte_producto_cava_riel ppcr ON ppcr.id_parte_producto = pp.id
        LEFT JOIN trazabilidad_proceso.cava c ON c.id = ppcr.id_cava
        WHERE
            ppcr.fecha_salida IS NULL
            AND DATE(ppcr.fecha_ingreso) <= %s::date
            AND pp.id_tipo_parte_producto IN (13, 14, 10, 11)
            AND (%s::text IS NULL OR pp.con_destino ILIKE %s::text)
        ORDER BY pp.id_producto
    """

    # ── 2. Códigos base con decomiso en los últimos N días ──
    sql_decomiso = """
        SELECT DISTINCT
            SPLIT_PART(pp.id_producto,'-',1)||'-'||
            SPLIT_PART(pp.id_producto,'-',2)                    AS codigo_base,
            tpp.nombre                                           AS producto_decomisado,
            e.nombre                                             AS causa,
            d.fecha_registro                                     AS fecha_decomiso
        FROM sai.decomiso d
        JOIN sai.inspeccion_decomiso id_rel ON id_rel.id_decomiso = d.id
        JOIN sai.inspeccion i               ON i.id = id_rel.id_inspeccion
        JOIN trazabilidad_proceso.parte_producto pp ON pp.id = i.id_parte_producto
        JOIN trazabilidad_proceso.tipo_parte_producto tpp ON tpp.id = d.id_tipo_parte_producto
        LEFT JOIN sai.decomiso_enfermedad de2 ON de2.id_decomiso = d.id
        LEFT JOIN sai.enfermedad e            ON e.id = de2.id_enfermedad
        WHERE d.fecha_registro >= (%s::date - INTERVAL '%s days')
          AND d.fecha_registro <= %s::date
    """

    rows_cava    = query(sql_cava, (fecha_filtro, turno_filtro, turno_filtro))
    rows_decomiso= query(sql_decomiso, (fecha_filtro, dias_decomisos, fecha_filtro))

    # Índice de decomisos por código base
    idx_decomiso = {}
    for r in serializable(rows_decomiso):
        b = r["codigo_base"]
        if b not in idx_decomiso:
            idx_decomiso[b] = []
        idx_decomiso[b].append({"producto": r["producto_decomisado"], "causa": r["causa"], "fecha": r["fecha_decomiso"]})

    # Construir tabla maestra por juego
    juegos = {}
    for r in serializable(rows_cava):
        b = r["codigo_base"]
        if b not in juegos:
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
            }
        id_tipo = r["id_tipo"]
        if id_tipo == 14: juegos[b]["tiene_vr"]     = True
        if id_tipo == 13: juegos[b]["tiene_vb"]     = True
        if id_tipo == 10: juegos[b]["tiene_cabeza"] = True
        if id_tipo == 11: juegos[b]["tiene_pm"]     = True
        if r["reetiquetado"]:          juegos[b]["reetiquetar"] = True
        if "CRUDAS" in (r["observaciones"] or "").upper():
            juegos[b]["tiene_cruda"] = True

    # Clasificar cada juego
    lista = []
    for b, j in juegos.items():
        completo = j["tiene_vr"] and j["tiene_vb"]
        j["completo"]    = completo
        j["incompleto"]  = not completo
        j["estado"] = (
            "DECOMISO"   if j["tiene_decomiso"] else
            "CRUDA"      if j["tiene_cruda"]    else
            "INCOMPLETO" if j["incompleto"]     else
            "OK"
        )
        lista.append(j)

    lista.sort(key=lambda x: (0 if x["estado"]=="DECOMISO" else 1 if x["estado"]=="CRUDA" else 2, x["codigo_base"]))

    totales = {
        "total_juegos":      len(lista),
        "completos":         sum(1 for j in lista if j["completo"]),
        "incompletos":       sum(1 for j in lista if j["incompleto"]),
        "con_decomiso":      sum(1 for j in lista if j["tiene_decomiso"]),
        "con_cruda":         sum(1 for j in lista if j["tiene_cruda"]),
        "con_reetiquetar":   sum(1 for j in lista if j["reetiquetar"]),
        "ok":                sum(1 for j in lista if j["estado"]=="OK"),
    }

    return {
        "fecha":            fecha_filtro,
        "turno":            turno,
        "dias_decomisos":   dias_decomisos,
        "totales":          totales,
        "juegos":           lista,
    }

