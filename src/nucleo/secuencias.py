"""Secuencias didácticas (planificación de una unidad de aprendizaje, formato MINERD).

Capa de datos y exportación SIN Qt: la pantalla vive en src/modulos/secuencias.py.
Estructura (esquema de planificación por unidad de aprendizaje del MINERD):

    Encabezado ........ centro, materia, grado, sección, período, docente
    Cuerpo ............ eje transversal, situación de aprendizaje,
                        competencias fundamentales y específicas,
                        contenidos (conceptos / procedimientos / actitudes y valores),
                        indicadores de logro, estrategia de enseñanza y aprendizaje
    Secuencia ......... sesiones ordenadas: fecha, momento (inicio/desarrollo/cierre),
                        actividades de aprendizaje, evidencias, instrumentos de
                        evaluación, metacognición y recursos

Las competencias específicas y los indicadores de logro son los MISMOS registros
que usa Calificaciones (tablas competencias_especificas / indicadores_logro), así
que planificar y evaluar quedan conectados.
"""
from datetime import datetime, timedelta

from src.nucleo.bd import get_connection

MOMENTOS = ["Inicio", "Desarrollo", "Cierre"]
ESTADOS_SECUENCIA = ["Borrador", "En curso", "Completada", "Archivada"]
INSTRUMENTOS_EVALUACION = [
    "Lista de cotejo", "Rúbrica", "Escala de estimación", "Guía de observación",
    "Registro anecdótico", "Prueba escrita", "Portafolio", "Diario reflexivo",
]
# Competencias fundamentales del currículo dominicano (se re-declaran aquí porque
# nucleo no puede importar de interfaz; deben coincidir con
# configuracion.COMPETENCIAS_FUNDAMENTALES_RD, lo verifica tests/test_secuencias.py).
COMPETENCIAS_FUNDAMENTALES = [
    "Ética y Ciudadana",
    "Comunicativa",
    "Pensamiento Lógico, Creativo y Crítico",
    "Resolución de Problemas",
    "Científica y Tecnológica",
    "Ambiental y de la Salud",
    "Desarrollo Personal y Espiritual",
]
_SEP_LISTA = " | "

_CAMPOS_SECUENCIA = (
    "titulo", "materia_id", "grado_id", "seccion_id", "profesor_id", "periodo_id",
    "anio_academico", "eje_transversal", "situacion_aprendizaje",
    "competencias_fundamentales", "contenido_conceptos", "contenido_procedimientos",
    "contenido_actitudes", "estrategia", "estado", "fecha_inicio", "fecha_fin",
)
_CAMPOS_SESION = ("fecha", "momento", "actividad", "evidencia", "instrumento",
                  "metacognicion", "recursos", "duracion_min", "realizada")


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def unir_competencias_fundamentales(lista):
    return _SEP_LISTA.join(x for x in lista if x)


def separar_competencias_fundamentales(texto):
    return [x.strip() for x in (texto or "").split("|") if x.strip()]


# ------------------------------------------------------------
# CRUD de la secuencia
# ------------------------------------------------------------
def _limpiar_datos(datos):
    limpio = {k: datos.get(k) for k in _CAMPOS_SECUENCIA if k in datos}
    titulo = (limpio.get("titulo") or "").strip()
    if not titulo:
        raise ValueError("La secuencia necesita un título.")
    limpio["titulo"] = titulo
    if limpio.get("estado") not in ESTADOS_SECUENCIA:
        limpio["estado"] = "Borrador"
    fi, ff = limpio.get("fecha_inicio"), limpio.get("fecha_fin")
    if fi and ff and ff < fi:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")
    return limpio


def _reemplazar_vinculos(c, tabla, columna, secuencia_id, ids):
    c.execute(f"DELETE FROM {tabla} WHERE secuencia_id=?", (secuencia_id,))
    for i in dict.fromkeys(ids or []):  # sin duplicados, conserva orden
        c.execute(f"INSERT INTO {tabla} (secuencia_id, {columna}) VALUES (?, ?)", (secuencia_id, i))


def guardar_secuencia(datos, competencias_ids=(), indicadores_ids=(), tareas_ids=(),
                      sesiones=None, secuencia_id=None):
    """Crea (secuencia_id=None) o actualiza una secuencia con sus vínculos y,
    si `sesiones` no es None, REEMPLAZA su lista de sesiones. Todo en una sola
    transacción. Devuelve el id."""
    limpio = _limpiar_datos(datos)
    conn = get_connection()
    try:
        c = conn.cursor()
        if secuencia_id is None:
            limpio["creado"] = limpio["actualizado"] = _ahora()
            cols = ", ".join(limpio)
            c.execute(f"INSERT INTO secuencias_didacticas ({cols}) VALUES ({', '.join('?' * len(limpio))})",
                      list(limpio.values()))
            secuencia_id = c.lastrowid
        else:
            limpio["actualizado"] = _ahora()
            sets = ", ".join(f"{k}=?" for k in limpio)
            c.execute(f"UPDATE secuencias_didacticas SET {sets} WHERE id=?",
                      list(limpio.values()) + [secuencia_id])
            if c.rowcount == 0:
                raise ValueError("La secuencia ya no existe.")
        _reemplazar_vinculos(c, "secuencia_competencia", "competencia_id", secuencia_id, competencias_ids)
        _reemplazar_vinculos(c, "secuencia_indicador", "indicador_id", secuencia_id, indicadores_ids)
        _reemplazar_vinculos(c, "secuencia_tarea", "tarea_id", secuencia_id, tareas_ids)
        if sesiones is not None:
            _guardar_sesiones(c, secuencia_id, sesiones)
        conn.commit()
        return secuencia_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _guardar_sesiones(c, secuencia_id, sesiones):
    c.execute("DELETE FROM secuencia_sesiones WHERE secuencia_id=?", (secuencia_id,))
    for orden, s in enumerate(sesiones, start=1):
        momento = s.get("momento") if s.get("momento") in MOMENTOS else "Desarrollo"
        valores = {k: s.get(k) for k in _CAMPOS_SESION}
        valores["momento"] = momento
        valores["duracion_min"] = int(valores.get("duracion_min") or 0)
        valores["realizada"] = 1 if valores.get("realizada") else 0
        c.execute(
            "INSERT INTO secuencia_sesiones (secuencia_id, orden, " + ", ".join(_CAMPOS_SESION) +
            ") VALUES (?, ?, " + ", ".join("?" * len(_CAMPOS_SESION)) + ")",
            [secuencia_id, orden] + [valores[k] for k in _CAMPOS_SESION])


def obtener_secuencia(secuencia_id):
    """Secuencia completa como dict (con nombres legibles, vínculos y sesiones) o None."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT s.*, m.nombre AS materia, g.nombre AS grado, sec.nombre AS seccion,
                            p.nombre AS periodo,
                            TRIM(COALESCE(pr.nombre,'') || ' ' || COALESCE(pr.apellidos,'')) AS profesor
                     FROM secuencias_didacticas s
                     LEFT JOIN materias m ON s.materia_id = m.id
                     LEFT JOIN grados g ON s.grado_id = g.id
                     LEFT JOIN secciones sec ON s.seccion_id = sec.id
                     LEFT JOIN periodos p ON s.periodo_id = p.id
                     LEFT JOIN profesores pr ON s.profesor_id = pr.id
                     WHERE s.id=?""", (secuencia_id,))
        fila = c.fetchone()
        if fila is None:
            return None
        sec = dict(fila)
        c.execute("""SELECT ce.* FROM secuencia_competencia sc
                     JOIN competencias_especificas ce ON sc.competencia_id = ce.id
                     WHERE sc.secuencia_id=? ORDER BY ce.orden, ce.codigo""", (secuencia_id,))
        sec["competencias"] = [dict(f) for f in c.fetchall()]
        c.execute("""SELECT il.*, ce.codigo AS codigo_competencia FROM secuencia_indicador si
                     JOIN indicadores_logro il ON si.indicador_id = il.id
                     JOIN competencias_especificas ce ON il.competencia_id = ce.id
                     WHERE si.secuencia_id=? ORDER BY ce.orden, ce.codigo, il.orden, il.codigo""",
                  (secuencia_id,))
        sec["indicadores"] = [dict(f) for f in c.fetchall()]
        c.execute("""SELECT t.id, t.titulo, t.categoria, t.fecha_entrega FROM secuencia_tarea st
                     JOIN tareas t ON st.tarea_id = t.id WHERE st.secuencia_id=?
                     ORDER BY t.fecha_entrega, t.titulo""", (secuencia_id,))
        sec["tareas"] = [dict(f) for f in c.fetchall()]
        c.execute("SELECT * FROM secuencia_sesiones WHERE secuencia_id=? ORDER BY orden, id", (secuencia_id,))
        sec["sesiones"] = [dict(f) for f in c.fetchall()]
        sec["competencias_fundamentales_lista"] = separar_competencias_fundamentales(
            sec.get("competencias_fundamentales"))
        return sec
    finally:
        conn.close()


def listar_secuencias(profesor_id=None, materias_permitidas=None, materia_id=None,
                      grado_id=None, estado=None, texto=""):
    """Resumen para la tabla. `materias_permitidas` (set de ids) restringe a un
    Profesor a sus materias, igual que el resto de módulos; None = sin restricción.
    Un Profesor también ve las secuencias que él mismo creó (profesor_id)."""
    condiciones, params = [], []
    if materias_permitidas is not None:
        marcas = ", ".join("?" * len(materias_permitidas)) or "NULL"
        cond = f"s.materia_id IN ({marcas})"
        params.extend(sorted(materias_permitidas))
        if profesor_id is not None:
            cond = f"({cond} OR s.profesor_id = ?)"
            params.append(profesor_id)
        condiciones.append(cond)
    if materia_id:
        condiciones.append("s.materia_id = ?"); params.append(materia_id)
    if grado_id:
        condiciones.append("s.grado_id = ?"); params.append(grado_id)
    if estado:
        condiciones.append("s.estado = ?"); params.append(estado)
    if texto and texto.strip():
        condiciones.append("(s.titulo LIKE ? OR s.situacion_aprendizaje LIKE ?)")
        params.extend([f"%{texto.strip()}%"] * 2)
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(f"""SELECT s.id, s.titulo, s.estado, s.fecha_inicio, s.fecha_fin,
                             m.nombre AS materia, g.nombre AS grado, sec.nombre AS seccion,
                             p.nombre AS periodo,
                             (SELECT COUNT(*) FROM secuencia_sesiones x WHERE x.secuencia_id = s.id) AS total_sesiones,
                             (SELECT COUNT(*) FROM secuencia_sesiones x
                                WHERE x.secuencia_id = s.id AND x.realizada = 1) AS sesiones_realizadas
                      FROM secuencias_didacticas s
                      LEFT JOIN materias m ON s.materia_id = m.id
                      LEFT JOIN grados g ON s.grado_id = g.id
                      LEFT JOIN secciones sec ON s.seccion_id = sec.id
                      LEFT JOIN periodos p ON s.periodo_id = p.id
                      {where}
                      ORDER BY COALESCE(s.fecha_inicio, s.creado) DESC, s.id DESC""", params)
        return [dict(f) for f in c.fetchall()]
    finally:
        conn.close()


def eliminar_secuencia(secuencia_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM secuencias_didacticas WHERE id=?", (secuencia_id,))
        conn.commit()
    finally:
        conn.close()


def duplicar_secuencia(secuencia_id, nuevo_titulo=None):
    """Copia una secuencia (sin fechas, sin marcar sesiones como realizadas, en
    Borrador) para reutilizarla en otro grupo o período. Devuelve el id nuevo."""
    sec = obtener_secuencia(secuencia_id)
    if sec is None:
        raise ValueError("La secuencia ya no existe.")
    datos = {k: sec.get(k) for k in _CAMPOS_SECUENCIA}
    datos["titulo"] = nuevo_titulo or f"{sec['titulo']} (copia)"
    datos["estado"] = "Borrador"
    datos["fecha_inicio"] = datos["fecha_fin"] = None
    sesiones = [dict(s, fecha=None, realizada=0) for s in sec["sesiones"]]
    return guardar_secuencia(
        datos, [x["id"] for x in sec["competencias"]], [x["id"] for x in sec["indicadores"]],
        [], sesiones)


def marcar_sesion_realizada(sesion_id, realizada=True):
    conn = get_connection()
    try:
        conn.execute("UPDATE secuencia_sesiones SET realizada=? WHERE id=?", (1 if realizada else 0, sesion_id))
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------
# Sesiones: plantilla, fechas y avance
# ------------------------------------------------------------
def sesiones_base(cantidad=3):
    """Plantilla inicial: la primera sesión es de Inicio, la última de Cierre y
    el resto de Desarrollo. Con 1 sola sesión se usa Desarrollo."""
    cantidad = max(1, int(cantidad))
    sesiones = []
    for i in range(cantidad):
        if cantidad == 1:
            momento = "Desarrollo"
        elif i == 0:
            momento = "Inicio"
        elif i == cantidad - 1:
            momento = "Cierre"
        else:
            momento = "Desarrollo"
        sesiones.append({"fecha": None, "momento": momento, "actividad": "", "evidencia": "",
                         "instrumento": "", "metacognicion": "", "recursos": "",
                         "duracion_min": 0, "realizada": 0})
    return sesiones


def distribuir_fechas(fecha_inicio, cantidad, dias_semana=(0, 1, 2, 3, 4), feriados=()):
    """Fechas ISO (YYYY-MM-DD) de `cantidad` sesiones desde `fecha_inicio`,
    usando solo los días de la semana indicados (0=lunes) y saltando feriados."""
    if cantidad <= 0:
        return []
    dias = set(dias_semana)
    if not dias:
        raise ValueError("Indica al menos un día de clase.")
    saltar = {str(f)[:10] for f in feriados}
    dia = datetime.strptime(str(fecha_inicio)[:10], "%Y-%m-%d")
    fechas = []
    while len(fechas) < cantidad:
        iso = dia.strftime("%Y-%m-%d")
        if dia.weekday() in dias and iso not in saltar:
            fechas.append(iso)
        dia += timedelta(days=1)
    return fechas


def progreso(sesiones):
    """(realizadas, total, porcentaje entero) a partir de la lista de sesiones."""
    total = len(sesiones)
    hechas = sum(1 for s in sesiones if s.get("realizada"))
    return hechas, total, (round(100 * hechas / total) if total else 0)


def validar_secuencia(sec):
    """Lista de advertencias (no bloquean el guardado) para ayudar al docente a
    completar lo que el formato del MINERD espera de una secuencia."""
    avisos = []
    if not (sec.get("situacion_aprendizaje") or "").strip():
        avisos.append("Falta la situación de aprendizaje.")
    if not sec.get("competencias") and not sec.get("competencias_fundamentales_lista"):
        avisos.append("No se ha seleccionado ninguna competencia.")
    if sec.get("competencias") and not sec.get("indicadores"):
        avisos.append("Hay competencias específicas pero ningún indicador de logro.")
    if not any((sec.get(k) or "").strip() for k in
               ("contenido_conceptos", "contenido_procedimientos", "contenido_actitudes")):
        avisos.append("No se han descrito contenidos (conceptos, procedimientos o actitudes y valores).")
    sesiones = sec.get("sesiones") or []
    if not sesiones:
        avisos.append("La secuencia no tiene sesiones.")
    else:
        if not any(s.get("momento") == "Inicio" for s in sesiones):
            avisos.append("Ninguna sesión es de Inicio (recuperación de saberes previos).")
        if not any(s.get("momento") == "Cierre" for s in sesiones):
            avisos.append("Ninguna sesión es de Cierre.")
        sin_actividad = [i for i, s in enumerate(sesiones, 1) if not (s.get("actividad") or "").strip()]
        if sin_actividad:
            avisos.append("Sesiones sin actividad descrita: " + ", ".join(map(str, sin_actividad)) + ".")
        sin_evaluar = [i for i, s in enumerate(sesiones, 1)
                       if (s.get("evidencia") or "").strip() and not (s.get("instrumento") or "").strip()]
        if sin_evaluar:
            avisos.append("Sesiones con evidencia pero sin instrumento de evaluación: "
                          + ", ".join(map(str, sin_evaluar)) + ".")
    return avisos


# ------------------------------------------------------------
# Catálogos para los selectores de la pantalla
# ------------------------------------------------------------
def indicadores_de_competencias(competencias_ids):
    """Indicadores de logro de las competencias dadas (para el selector)."""
    ids = list(competencias_ids or [])
    if not ids:
        return []
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(f"""SELECT il.*, ce.codigo AS codigo_competencia FROM indicadores_logro il
                      JOIN competencias_especificas ce ON il.competencia_id = ce.id
                      WHERE il.competencia_id IN ({', '.join('?' * len(ids))})
                      ORDER BY ce.orden, ce.codigo, il.orden, il.codigo""", ids)
        return [dict(f) for f in c.fetchall()]
    finally:
        conn.close()


def tareas_de_materia(materia_id, grado_id=None):
    """Tareas del Banco de Tareas de una materia (opcionalmente de un grado) para vincular."""
    if not materia_id:
        return []
    conn = get_connection()
    try:
        c = conn.cursor()
        sql = "SELECT id, titulo, categoria, fecha_entrega FROM tareas WHERE materia_id=?"
        params = [materia_id]
        if grado_id:
            sql += " AND (curso_id IS NULL OR curso_id=?)"
            params.append(grado_id)
        c.execute(sql + " ORDER BY fecha_entrega, titulo", params)
        return [dict(f) for f in c.fetchall()]
    finally:
        conn.close()


# ------------------------------------------------------------
# Exportación a Word (.docx) con el esquema del MINERD
# ------------------------------------------------------------
def _fmt_fecha(iso):
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""


def _nombre_centro():
    try:
        conn = get_connection()
        try:
            f = conn.execute("SELECT nombre_institucion FROM configuracion WHERE id=1").fetchone()
        finally:
            conn.close()
        return (f["nombre_institucion"] if f else "") or ""
    except Exception:
        return ""


def exportar_docx(secuencia_id, ruta_salida):
    """Genera el documento Word de la secuencia (horizontal, editable por el
    docente). Devuelve `ruta_salida`. Lanza ValueError si la secuencia no existe."""
    sec = obtener_secuencia(secuencia_id)
    if sec is None:
        raise ValueError("La secuencia ya no existe.")
    return escribir_docx(sec, ruta_salida, _nombre_centro())


def _codigo_y_texto(codigo, descripcion, separador=". "):
    return f"{codigo}{separador}{descripcion}" if codigo else descripcion


def escribir_docx(sec, ruta_salida, centro=""):
    """Escribe el Word a partir de un dict de secuencia (el de obtener_secuencia
    o el equivalente de Single Teacher, cuyas competencias/indicadores pueden
    venir sin código). Compartido por ambas ediciones."""
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document()
    seccion = doc.sections[0]
    seccion.orientation = WD_ORIENT.LANDSCAPE
    seccion.page_width, seccion.page_height = seccion.page_height, seccion.page_width
    for lado in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(seccion, lado, Cm(1.8))
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)

    def sombrear(celda, color="D9E2F3"):
        tc_pr = celda._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), color)
        tc_pr.append(shd)

    def texto_celda(celda, texto, negrita=False):
        celda.text = ""
        p = celda.paragraphs[0]
        r = p.add_run(texto or "")
        r.bold = negrita
        return p

    def titulo(texto):
        p = doc.add_paragraph()
        r = p.add_run(texto)
        r.bold = True
        r.font.size = Pt(11)
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)

    cabecera = doc.add_paragraph()
    cabecera.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if centro:
        r = cabecera.add_run(centro + "\n"); r.bold = True; r.font.size = Pt(13)
    r = cabecera.add_run("Planificación de Unidad de Aprendizaje — Secuencia Didáctica")
    r.bold = True; r.font.size = Pt(12)

    t = doc.add_table(rows=3, cols=4)
    t.style = "Table Grid"
    pares = [
        ("Título de la unidad", sec["titulo"], "Asignatura", sec.get("materia") or ""),
        ("Grado / Sección", " ".join(x for x in (sec.get("grado"), sec.get("seccion")) if x),
         "Período / Año escolar", " · ".join(x for x in (sec.get("periodo"), sec.get("anio_academico")) if x)),
        ("Docente", sec.get("profesor") or "",
         "Fechas", " – ".join(x for x in (_fmt_fecha(sec.get("fecha_inicio")), _fmt_fecha(sec.get("fecha_fin"))) if x)),
    ]
    for fila, (e1, v1, e2, v2) in zip(t.rows, pares):
        for idx, (txt, neg) in enumerate(((e1, True), (v1, False), (e2, True), (v2, False))):
            texto_celda(fila.cells[idx], txt, neg)
            if neg:
                sombrear(fila.cells[idx])

    def bloque(rotulo, valor):
        if (valor or "").strip():
            titulo(rotulo)
            doc.add_paragraph(valor.strip())

    bloque("Eje transversal / Descriptores", sec.get("eje_transversal"))
    bloque("Situación de aprendizaje", sec.get("situacion_aprendizaje"))
    if sec.get("competencias_fundamentales_lista"):
        titulo("Competencias fundamentales")
        for x in sec["competencias_fundamentales_lista"]:
            doc.add_paragraph(x, style="List Bullet")
    if sec.get("competencias"):
        titulo("Competencias específicas")
        for ce in sec["competencias"]:
            doc.add_paragraph(_codigo_y_texto(ce.get("codigo"), ce["descripcion"]), style="List Bullet")

    contenidos = [("Conceptos", sec.get("contenido_conceptos")),
                  ("Procedimientos", sec.get("contenido_procedimientos")),
                  ("Actitudes y valores", sec.get("contenido_actitudes"))]
    if any((v or "").strip() for _, v in contenidos):
        titulo("Contenidos")
        tc = doc.add_table(rows=2, cols=3)
        tc.style = "Table Grid"
        for i, (rot, val) in enumerate(contenidos):
            texto_celda(tc.rows[0].cells[i], rot, True); sombrear(tc.rows[0].cells[i])
            texto_celda(tc.rows[1].cells[i], val)

    if sec.get("indicadores"):
        titulo("Indicadores de logro")
        for il in sec["indicadores"]:
            prefijo = " · ".join(x for x in (il.get("codigo_competencia"), il.get("codigo")) if x)
            doc.add_paragraph(_codigo_y_texto(prefijo, il["descripcion"], ": "), style="List Bullet")
    bloque("Estrategia de enseñanza y de aprendizaje", sec.get("estrategia"))

    titulo("Secuencia didáctica")
    columnas = ["Fecha", "Momento", "Actividades de aprendizaje", "Evidencias de aprendizaje",
                "Instrumentos de evaluación", "Metacognición", "Recursos"]
    ts = doc.add_table(rows=1, cols=len(columnas))
    ts.style = "Table Grid"
    for i, nombre in enumerate(columnas):
        texto_celda(ts.rows[0].cells[i], nombre, True); sombrear(ts.rows[0].cells[i])
    for s in sec["sesiones"]:
        fila = ts.add_row().cells
        valores = [_fmt_fecha(s.get("fecha")), s.get("momento") or "", s.get("actividad") or "",
                   s.get("evidencia") or "", s.get("instrumento") or "",
                   s.get("metacognicion") or "", s.get("recursos") or ""]
        for celda, v in zip(fila, valores):
            texto_celda(celda, v)
    if sec.get("tareas"):
        titulo("Tareas vinculadas del Banco de Tareas")
        for tarea in sec["tareas"]:
            extra = f" (entrega {_fmt_fecha(tarea['fecha_entrega'])})" if tarea.get("fecha_entrega") else ""
            doc.add_paragraph(f"{tarea['titulo']} — {tarea.get('categoria') or 'Tarea'}{extra}",
                              style="List Bullet")
    doc.save(ruta_salida)
    return ruta_salida
