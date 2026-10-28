#Secuencias didácticas de la edición Single Teacher.
#
#Mismo formato MINERD que src/nucleo/secuencias.py, de donde salen las constantes, la validación, la
#plantilla de sesiones, las fechas, el avance y la escritura del Word. La diferencia es que esto
#trabaja sobre bd_single_teacher: no hay grados, ni profesores, ni catálogo de competencias. Las
#competencias específicas y los indicadores de logro se escriben como texto, una por línea.
from src.nucleo import bd_single_teacher
from src.nucleo.secuencias import (ESTADOS_SECUENCIA, escribir_docx, fecha_y_hora_actual,
                                   guardar_sesiones, guardar_tareas_de_secuencia, insertar_secuencia,
                                   actualizar_secuencia, leer_sesiones,
                                   separar_competencias_fundamentales)

#Los únicos campos de la tabla secuencias_didacticas de Single Teacher que se aceptan al guardar.
CAMPOS_SECUENCIA= (
    "titulo", "materia_id", "seccion_id", "periodo_id", "anio_academico", "eje_transversal",
    "situacion_aprendizaje", "competencias_fundamentales", "competencias_especificas",
    "indicadores_logro", "contenido_conceptos", "contenido_procedimientos",
    "contenido_actitudes", "estrategia", "estado", "fecha_inicio", "fecha_fin",
)


#Parte un texto en líneas, sin espacios sobrantes y sin líneas vacías.
def lineas(texto):

    return [linea.strip() for linea in (texto or "").splitlines() if linea.strip()]


# -----------------------------------------
# guardar
# -----------------------------------------
def _limpiar_datos(datos):

    limpio= {campo: datos.get(campo) for campo in CAMPOS_SECUENCIA if campo in datos}

    titulo= (limpio.get("titulo") or "").strip()

    if not titulo:
        raise ValueError("La secuencia necesita un título.")

    limpio["titulo"]= titulo

    #las competencias y los indicadores se guardan una por línea, sin vacías ni espacios de más
    for campo in ("competencias_especificas", "indicadores_logro"):
        if campo in limpio:
            limpio[campo]= "\n".join(lineas(limpio[campo]))

    if limpio.get("estado") not in ESTADOS_SECUENCIA:
        limpio["estado"]= "Borrador"

    fecha_inicio= limpio.get("fecha_inicio")
    fecha_fin= limpio.get("fecha_fin")

    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")

    return limpio


#Crea la secuencia si secuencia_id es None, o la actualiza si ya existe. Si sesiones no es None,
#REEMPLAZA todas las que tenía. Todo en una sola transacción. Devuelve el id.
def guardar_secuencia(datos, tareas_ids=(), sesiones=None, secuencia_id=None, main_window=None):

    limpio= _limpiar_datos(datos)
    conn= bd_single_teacher.obtener_conexion(main_window)

    try:

        c= conn.cursor()

        if secuencia_id is None:
            secuencia_id= insertar_secuencia(c, limpio)
        else:
            actualizar_secuencia(c, limpio, secuencia_id)

        guardar_tareas_de_secuencia(c, secuencia_id, tareas_ids)

        if sesiones is not None:
            guardar_sesiones(c, secuencia_id, sesiones)

        conn.commit()

        return secuencia_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# -----------------------------------------
# leer
# -----------------------------------------
#Devuelve el mismo diccionario que nucleo.secuencias.obtener_secuencia, para que el Word y la
#validación sirvan para las dos ediciones. Las competencias y los indicadores salen como listas de
#{"codigo": "", "descripcion": una línea}. Devuelve None si la secuencia no existe.
def obtener_secuencia(secuencia_id, main_window=None):

    conn= bd_single_teacher.obtener_conexion(main_window)

    try:

        c= conn.cursor()
        c.execute("""SELECT s.*, m.nombre AS materia, sec.nombre AS grado, p.nombre AS periodo
                     FROM secuencias_didacticas s
                     LEFT JOIN materias m ON s.materia_id = m.id
                     LEFT JOIN secciones sec ON s.seccion_id = sec.id
                     LEFT JOIN periodos p ON s.periodo_id = p.id WHERE s.id=?""", (secuencia_id,))
        fila= c.fetchone()

        if fila is None:
            return None

        secuencia= dict(fila)

        #acá la "sección" ya es el curso completo, que va en el campo grado
        secuencia["seccion"]= ""

        fila_docente= c.execute("SELECT nombre_docente FROM configuracion WHERE id=1").fetchone()
        secuencia["profesor"]= (fila_docente["nombre_docente"] if fila_docente else "") or ""

        secuencia["competencias"]= [{"codigo": "", "descripcion": linea}
                                    for linea in lineas(secuencia["competencias_especificas"])]
        secuencia["indicadores"]= [{"codigo": "", "codigo_competencia": "", "descripcion": linea}
                                   for linea in lineas(secuencia["indicadores_logro"])]

        c.execute("""SELECT t.id, t.titulo, 'Tarea' AS categoria, t.fecha_entrega FROM secuencia_tarea st
                     JOIN tareas t ON st.tarea_id = t.id WHERE st.secuencia_id=?
                     ORDER BY t.fecha_entrega, t.titulo""", (secuencia_id,))
        secuencia["tareas"]= [dict(fila_tarea) for fila_tarea in c.fetchall()]

        secuencia["sesiones"]= leer_sesiones(c, secuencia_id)
        secuencia["competencias_fundamentales_lista"]= separar_competencias_fundamentales(
            secuencia["competencias_fundamentales"])

        return secuencia

    finally:
        conn.close()


def listar_secuencias(materia_id=None, seccion_id=None, estado=None, texto="", main_window=None):

    condiciones= []
    valores= []

    if materia_id:
        condiciones.append("s.materia_id = ?")
        valores.append(materia_id)

    if seccion_id:
        condiciones.append("s.seccion_id = ?")
        valores.append(seccion_id)

    if estado:
        condiciones.append("s.estado = ?")
        valores.append(estado)

    if texto and texto.strip():
        condiciones.append("(s.titulo LIKE ? OR s.situacion_aprendizaje LIKE ?)")
        valores.extend([f"%{texto.strip()}%"] * 2)

    donde= ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    conn= bd_single_teacher.obtener_conexion(main_window)

    try:

        c= conn.cursor()
        c.execute(f"""SELECT s.id, s.titulo, s.estado, s.fecha_inicio, s.fecha_fin,
                             m.nombre AS materia, sec.nombre AS curso, p.nombre AS periodo,
                             (SELECT COUNT(*) FROM secuencia_sesiones x WHERE x.secuencia_id = s.id) AS total_sesiones,
                             (SELECT COUNT(*) FROM secuencia_sesiones x
                                WHERE x.secuencia_id = s.id AND x.realizada = 1) AS sesiones_realizadas
                      FROM secuencias_didacticas s
                      LEFT JOIN materias m ON s.materia_id = m.id
                      LEFT JOIN secciones sec ON s.seccion_id = sec.id
                      LEFT JOIN periodos p ON s.periodo_id = p.id
                      {donde}
                      ORDER BY COALESCE(s.fecha_inicio, s.creado) DESC, s.id DESC""", valores)

        return [dict(fila) for fila in c.fetchall()]

    finally:
        conn.close()


#Las tareas del banco, filtradas por materia y por curso si se indican. Las que no tienen curso
#sirven para cualquiera.
def tareas_de_materia(materia_id=None, seccion_id=None, main_window=None):

    consulta= "SELECT id, titulo, 'Tarea' AS categoria, fecha_entrega FROM tareas WHERE 1=1"
    valores= []

    if materia_id:
        consulta += " AND materia_id=?"
        valores.append(materia_id)

    if seccion_id:
        consulta += " AND (seccion_id IS NULL OR seccion_id=?)"
        valores.append(seccion_id)

    conn= bd_single_teacher.obtener_conexion(main_window)

    try:

        return [dict(fila) for fila in conn.execute(consulta + " ORDER BY fecha_entrega, titulo", valores)]

    finally:
        conn.close()


# -----------------------------------------
# eliminar, duplicar y exportar
# -----------------------------------------
def eliminar_secuencia(secuencia_id, main_window=None):

    conn= bd_single_teacher.obtener_conexion(main_window)

    try:

        conn.execute("DELETE FROM secuencias_didacticas WHERE id=?", (secuencia_id,))
        conn.commit()

    finally:
        conn.close()


#Copia una secuencia en Borrador, sin fechas y con ninguna sesión realizada. No copia las tareas.
def duplicar_secuencia(secuencia_id, nuevo_titulo=None, main_window=None):

    secuencia= obtener_secuencia(secuencia_id, main_window)

    if secuencia is None:
        raise ValueError("La secuencia ya no existe.")

    datos= {campo: secuencia.get(campo) for campo in CAMPOS_SECUENCIA}
    datos["titulo"]= nuevo_titulo or f"{secuencia['titulo']} (copia)"
    datos["estado"]= "Borrador"
    datos["fecha_inicio"]= None
    datos["fecha_fin"]= None

    sesiones= [dict(sesion, fecha=None, realizada=0) for sesion in secuencia["sesiones"]]

    return guardar_secuencia(datos, tareas_ids=[], sesiones=sesiones, main_window=main_window)


def exportar_docx(secuencia_id, ruta_salida, main_window=None):

    secuencia= obtener_secuencia(secuencia_id, main_window)

    if secuencia is None:
        raise ValueError("La secuencia ya no existe.")

    return escribir_docx(secuencia, ruta_salida)
