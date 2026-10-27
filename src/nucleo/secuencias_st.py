"""Secuencias didácticas para la edición Single Teacher.

Mismo formato MINERD que src/nucleo/secuencias.py (de donde reutiliza constantes,
validación, plantilla de sesiones, fechas, avance y la escritura del Word), pero
sobre bd_single_teacher: sin grados/profesores/catálogo de competencias. Las
competencias específicas y los indicadores de logro se escriben como texto, una
por línea."""
from datetime import datetime

from src.nucleo import bd_single_teacher as db
from src.nucleo.secuencias import (  # noqa: F401  (se re-exportan para la UI)
    MOMENTOS, ESTADOS_SECUENCIA, INSTRUMENTOS_EVALUACION, COMPETENCIAS_FUNDAMENTALES,
    sesiones_base, distribuir_fechas, progreso, validar_secuencia, escribir_docx,
    unir_competencias_fundamentales, separar_competencias_fundamentales, _guardar_sesiones)

_CAMPOS = ("titulo", "materia_id", "seccion_id", "periodo_id", "anio_academico", "eje_transversal",
           "situacion_aprendizaje", "competencias_fundamentales", "competencias_especificas",
           "indicadores_logro", "contenido_conceptos", "contenido_procedimientos",
           "contenido_actitudes", "estrategia", "estado", "fecha_inicio", "fecha_fin")


def lineas(texto):
    return [x.strip() for x in (texto or "").splitlines() if x.strip()]


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _limpiar(datos):
    limpio = {k: datos.get(k) for k in _CAMPOS if k in datos}
    titulo = (limpio.get("titulo") or "").strip()
    if not titulo:
        raise ValueError("La secuencia necesita un título.")
    limpio["titulo"] = titulo
    for campo in ("competencias_especificas", "indicadores_logro"):
        if campo in limpio:
            limpio[campo] = "\n".join(lineas(limpio[campo]))   # una por línea, sin vacías ni espacios
    if limpio.get("estado") not in ESTADOS_SECUENCIA:
        limpio["estado"] = "Borrador"
    fi, ff = limpio.get("fecha_inicio"), limpio.get("fecha_fin")
    if fi and ff and ff < fi:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")
    return limpio


def guardar_secuencia(datos, tareas_ids=(), sesiones=None, secuencia_id=None, main_window=None):
    limpio = _limpiar(datos)
    conn = db.get_connection(main_window)
    try:
        c = conn.cursor()
        if secuencia_id is None:
            limpio["creado"] = limpio["actualizado"] = _ahora()
            c.execute(f"INSERT INTO secuencias_didacticas ({', '.join(limpio)}) "
                      f"VALUES ({', '.join('?' * len(limpio))})", list(limpio.values()))
            secuencia_id = c.lastrowid
        else:
            limpio["actualizado"] = _ahora()
            c.execute(f"UPDATE secuencias_didacticas SET {', '.join(f'{k}=?' for k in limpio)} WHERE id=?",
                      list(limpio.values()) + [secuencia_id])
            if c.rowcount == 0:
                raise ValueError("La secuencia ya no existe.")
        c.execute("DELETE FROM secuencia_tarea WHERE secuencia_id=?", (secuencia_id,))
        for t in dict.fromkeys(tareas_ids or []):
            c.execute("INSERT INTO secuencia_tarea (secuencia_id, tarea_id) VALUES (?, ?)", (secuencia_id, t))
        if sesiones is not None:
            _guardar_sesiones(c, secuencia_id, sesiones)
        conn.commit()
        return secuencia_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def obtener_secuencia(secuencia_id, main_window=None):
    """Dict con la misma forma que nucleo.secuencias.obtener_secuencia (competencias e
    indicadores como listas de {"codigo": "", "descripcion": línea}) o None."""
    conn = db.get_connection(main_window)
    try:
        c = conn.cursor()
        c.execute("""SELECT s.*, m.nombre AS materia, sec.nombre AS grado, p.nombre AS periodo
                     FROM secuencias_didacticas s
                     LEFT JOIN materias m ON s.materia_id = m.id
                     LEFT JOIN secciones sec ON s.seccion_id = sec.id
                     LEFT JOIN periodos p ON s.periodo_id = p.id WHERE s.id=?""", (secuencia_id,))
        fila = c.fetchone()
        if fila is None:
            return None
        sec = dict(fila)
        sec["seccion"] = ""            # aquí "sección" ya es el curso completo (campo grado)
        f = c.execute("SELECT nombre_docente FROM configuracion WHERE id=1").fetchone()
        sec["profesor"] = (f["nombre_docente"] if f else "") or ""
        sec["competencias"] = [{"codigo": "", "descripcion": x} for x in lineas(sec["competencias_especificas"])]
        sec["indicadores"] = [{"codigo": "", "codigo_competencia": "", "descripcion": x}
                              for x in lineas(sec["indicadores_logro"])]
        c.execute("""SELECT t.id, t.titulo, 'Tarea' AS categoria, t.fecha_entrega FROM secuencia_tarea st
                     JOIN tareas t ON st.tarea_id = t.id WHERE st.secuencia_id=?
                     ORDER BY t.fecha_entrega, t.titulo""", (secuencia_id,))
        sec["tareas"] = [dict(f) for f in c.fetchall()]
        c.execute("SELECT * FROM secuencia_sesiones WHERE secuencia_id=? ORDER BY orden, id", (secuencia_id,))
        sec["sesiones"] = [dict(f) for f in c.fetchall()]
        sec["competencias_fundamentales_lista"] = separar_competencias_fundamentales(
            sec["competencias_fundamentales"])
        return sec
    finally:
        conn.close()


def listar_secuencias(materia_id=None, seccion_id=None, estado=None, texto="", main_window=None):
    condiciones, params = [], []
    for col, val in (("s.materia_id", materia_id), ("s.seccion_id", seccion_id), ("s.estado", estado)):
        if val:
            condiciones.append(f"{col} = ?"); params.append(val)
    if texto and texto.strip():
        condiciones.append("(s.titulo LIKE ? OR s.situacion_aprendizaje LIKE ?)")
        params.extend([f"%{texto.strip()}%"] * 2)
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    conn = db.get_connection(main_window)
    try:
        c = conn.cursor()
        c.execute(f"""SELECT s.id, s.titulo, s.estado, s.fecha_inicio, s.fecha_fin,
                             m.nombre AS materia, sec.nombre AS curso, p.nombre AS periodo,
                             (SELECT COUNT(*) FROM secuencia_sesiones x WHERE x.secuencia_id = s.id) AS total_sesiones,
                             (SELECT COUNT(*) FROM secuencia_sesiones x
                                WHERE x.secuencia_id = s.id AND x.realizada = 1) AS sesiones_realizadas
                      FROM secuencias_didacticas s
                      LEFT JOIN materias m ON s.materia_id = m.id
                      LEFT JOIN secciones sec ON s.seccion_id = sec.id
                      LEFT JOIN periodos p ON s.periodo_id = p.id
                      {where}
                      ORDER BY COALESCE(s.fecha_inicio, s.creado) DESC, s.id DESC""", params)
        return [dict(f) for f in c.fetchall()]
    finally:
        conn.close()


def eliminar_secuencia(secuencia_id, main_window=None):
    conn = db.get_connection(main_window)
    try:
        conn.execute("DELETE FROM secuencias_didacticas WHERE id=?", (secuencia_id,))
        conn.commit()
    finally:
        conn.close()


def duplicar_secuencia(secuencia_id, nuevo_titulo=None, main_window=None):
    sec = obtener_secuencia(secuencia_id, main_window)
    if sec is None:
        raise ValueError("La secuencia ya no existe.")
    datos = {k: sec.get(k) for k in _CAMPOS}
    datos.update(titulo=nuevo_titulo or f"{sec['titulo']} (copia)", estado="Borrador",
                 fecha_inicio=None, fecha_fin=None)
    return guardar_secuencia(datos, [], [dict(s, fecha=None, realizada=0) for s in sec["sesiones"]],
                             main_window=main_window)


def tareas_de_materia(materia_id=None, seccion_id=None, main_window=None):
    conn = db.get_connection(main_window)
    try:
        sql, params = "SELECT id, titulo, 'Tarea' AS categoria, fecha_entrega FROM tareas WHERE 1=1", []
        if materia_id:
            sql += " AND materia_id=?"; params.append(materia_id)
        if seccion_id:
            sql += " AND (seccion_id IS NULL OR seccion_id=?)"; params.append(seccion_id)
        return [dict(f) for f in conn.execute(sql + " ORDER BY fecha_entrega, titulo", params)]
    finally:
        conn.close()


def exportar_docx(secuencia_id, ruta_salida, main_window=None):
    sec = obtener_secuencia(secuencia_id, main_window)
    if sec is None:
        raise ValueError("La secuencia ya no existe.")
    return escribir_docx(sec, ruta_salida)
