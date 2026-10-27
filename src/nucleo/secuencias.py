#Secuencias didácticas: la planificación de una unidad de aprendizaje con el formato del MINERD.
#Acá no hay nada de Qt, solo datos y la exportación a Word. La pantalla está en src/modulos/secuencias.py.
#
#Una secuencia tiene tres partes:
#  encabezado: centro, materia, grado, sección, período y docente
#  cuerpo: eje transversal, situación de aprendizaje, competencias fundamentales y específicas,
#          contenidos (conceptos, procedimientos, actitudes y valores), indicadores de logro y
#          estrategia de enseñanza y aprendizaje
#  sesiones: van en orden y cada una tiene fecha, momento (inicio, desarrollo o cierre),
#            actividades, evidencias, instrumento de evaluación, metacognición y recursos
#
#Las competencias específicas y los indicadores de logro son los mismos registros que usa
#Calificaciones (tablas competencias_especificas e indicadores_logro), así que planificar y evaluar
#quedan conectados.
from datetime import datetime, timedelta

from src.nucleo.bd import obtener_conexion


# -----------------------------------------
# constantes
# -----------------------------------------
MOMENTOS= ["Inicio", "Desarrollo", "Cierre"]

ESTADOS_SECUENCIA= ["Borrador", "En curso", "Completada", "Archivada"]

INSTRUMENTOS_EVALUACION= [
    "Lista de cotejo", "Rúbrica", "Escala de estimación", "Guía de observación",
    "Registro anecdótico", "Prueba escrita", "Portafolio", "Diario reflexivo",
]

#Competencias fundamentales del currículo dominicano. Se repiten acá porque nucleo no puede importar
#de interfaz; tienen que coincidir con configuracion.COMPETENCIAS_FUNDAMENTALES_RD y
#tests/test_secuencias.py lo comprueba.
COMPETENCIAS_FUNDAMENTALES= [
    "Ética y Ciudadana",
    "Comunicativa",
    "Pensamiento Lógico, Creativo y Crítico",
    "Resolución de Problemas",
    "Científica y Tecnológica",
    "Ambiental y de la Salud",
    "Desarrollo Personal y Espiritual",
]

#Las competencias fundamentales elegidas se guardan en un solo texto, separadas por " | ".
SEPARADOR_COMPETENCIAS= " | "

#Los únicos campos de la tabla secuencias_didacticas que se aceptan al guardar.
CAMPOS_SECUENCIA= (
    "titulo", "materia_id", "grado_id", "seccion_id", "profesor_id", "periodo_id",
    "anio_academico", "eje_transversal", "situacion_aprendizaje",
    "competencias_fundamentales", "contenido_conceptos", "contenido_procedimientos",
    "contenido_actitudes", "estrategia", "estado", "fecha_inicio", "fecha_fin",
)


def fecha_y_hora_actual():

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def unir_competencias_fundamentales(lista):

    return SEPARADOR_COMPETENCIAS.join(nombre for nombre in lista if nombre)


def separar_competencias_fundamentales(texto):

    return [nombre.strip() for nombre in (texto or "").split("|") if nombre.strip()]


# -----------------------------------------
# guardar
# -----------------------------------------
#Valida los datos que llegan de la pantalla y se queda solo con los campos conocidos. Los campos que
#no vengan en datos no se tocan al editar una secuencia que ya existe.
def _limpiar_datos(datos):

    limpio= {campo: datos.get(campo) for campo in CAMPOS_SECUENCIA if campo in datos}

    titulo= (limpio.get("titulo") or "").strip()

    if not titulo:
        raise ValueError("La secuencia necesita un título.")

    limpio["titulo"]= titulo

    if limpio.get("estado") not in ESTADOS_SECUENCIA:
        limpio["estado"]= "Borrador"

    fecha_inicio= limpio.get("fecha_inicio")
    fecha_fin= limpio.get("fecha_fin")

    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")

    return limpio


#Crea la secuencia si secuencia_id es None, o la actualiza si ya existe. Si sesiones no es None,
#REEMPLAZA todas las sesiones que tenía. Todo ocurre en una sola transacción: o se guarda completo
#o no se guarda nada. Devuelve el id de la secuencia.
def guardar_secuencia(datos, competencias_ids=(), indicadores_ids=(), tareas_ids=(),
                      sesiones=None, secuencia_id=None):

    limpio= _limpiar_datos(datos)
    conn= obtener_conexion()

    try:

        c= conn.cursor()

        if secuencia_id is None:
            secuencia_id= insertar_secuencia(c, limpio)
        else:
            actualizar_secuencia(c, limpio, secuencia_id)

        _guardar_competencias(c, secuencia_id, competencias_ids)
        _guardar_indicadores(c, secuencia_id, indicadores_ids)
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


#insertar_secuencia, actualizar_secuencia y leer_sesiones también las usa Single Teacher: su tabla
#secuencias_didacticas tiene otras columnas, pero estas funciones solo usan las que vienen en limpio.
def insertar_secuencia(c, limpio):

    valores= dict(limpio)
    valores["creado"]= fecha_y_hora_actual()
    valores["actualizado"]= valores["creado"]

    columnas= ", ".join(valores)
    marcadores= ", ".join("?" * len(valores))
    c.execute(f"INSERT INTO secuencias_didacticas ({columnas}) VALUES ({marcadores})", list(valores.values()))

    return c.lastrowid


def actualizar_secuencia(c, limpio, secuencia_id):

    valores= dict(limpio)
    valores["actualizado"]= fecha_y_hora_actual()

    asignaciones= ", ".join(f"{columna}=?" for columna in valores)
    c.execute(f"UPDATE secuencias_didacticas SET {asignaciones} WHERE id=?", list(valores.values()) + [secuencia_id])

    if c.rowcount == 0:
        raise ValueError("La secuencia ya no existe.")


#Los tres vínculos se guardan igual: se borran los que había y se insertan los nuevos, sin repetidos
#y en el mismo orden en que llegaron.
def _guardar_competencias(c, secuencia_id, competencias_ids):

    c.execute("DELETE FROM secuencia_competencia WHERE secuencia_id=?", (secuencia_id,))

    for competencia_id in dict.fromkeys(competencias_ids or []):
        c.execute("INSERT INTO secuencia_competencia (secuencia_id, competencia_id) VALUES (?, ?)",
                  (secuencia_id, competencia_id))


def _guardar_indicadores(c, secuencia_id, indicadores_ids):

    c.execute("DELETE FROM secuencia_indicador WHERE secuencia_id=?", (secuencia_id,))

    for indicador_id in dict.fromkeys(indicadores_ids or []):
        c.execute("INSERT INTO secuencia_indicador (secuencia_id, indicador_id) VALUES (?, ?)",
                  (secuencia_id, indicador_id))


#La usan las dos ediciones (institucional y Single Teacher): la tabla secuencia_tarea es igual en ambas.
def guardar_tareas_de_secuencia(c, secuencia_id, tareas_ids):

    c.execute("DELETE FROM secuencia_tarea WHERE secuencia_id=?", (secuencia_id,))

    for tarea_id in dict.fromkeys(tareas_ids or []):
        c.execute("INSERT INTO secuencia_tarea (secuencia_id, tarea_id) VALUES (?, ?)",
                  (secuencia_id, tarea_id))


#Borra las sesiones de la secuencia y guarda las nuevas numerándolas desde 1. También la usa Single Teacher.
def guardar_sesiones(c, secuencia_id, sesiones):

    c.execute("DELETE FROM secuencia_sesiones WHERE secuencia_id=?", (secuencia_id,))

    for orden, sesion in enumerate(sesiones, start=1):

        momento= sesion.get("momento")

        if momento not in MOMENTOS:
            momento= "Desarrollo"

        c.execute("""INSERT INTO secuencia_sesiones
                     (secuencia_id, orden, fecha, momento, actividad, evidencia, instrumento,
                      metacognicion, recursos, duracion_min, realizada)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (secuencia_id, orden, sesion.get("fecha"), momento, sesion.get("actividad"),
                   sesion.get("evidencia"), sesion.get("instrumento"), sesion.get("metacognicion"),
                   sesion.get("recursos"), int(sesion.get("duracion_min") or 0),
                   1 if sesion.get("realizada") else 0))


# -----------------------------------------
# leer
# -----------------------------------------
#La secuencia completa como diccionario (con los nombres de materia, grado, etc., los vínculos y las
#sesiones), o None si no existe.
def obtener_secuencia(secuencia_id):

    conn= obtener_conexion()

    try:

        c= conn.cursor()
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
        fila= c.fetchone()

        if fila is None:
            return None

        secuencia= dict(fila)
        secuencia["competencias"]= _leer_competencias(c, secuencia_id)
        secuencia["indicadores"]= _leer_indicadores(c, secuencia_id)
        secuencia["tareas"]= _leer_tareas(c, secuencia_id)
        secuencia["sesiones"]= leer_sesiones(c, secuencia_id)
        secuencia["competencias_fundamentales_lista"]= separar_competencias_fundamentales(
            secuencia.get("competencias_fundamentales"))

        return secuencia

    finally:
        conn.close()


def _leer_competencias(c, secuencia_id):

    c.execute("""SELECT ce.* FROM secuencia_competencia sc
                 JOIN competencias_especificas ce ON sc.competencia_id = ce.id
                 WHERE sc.secuencia_id=? ORDER BY ce.orden, ce.codigo""", (secuencia_id,))

    return [dict(fila) for fila in c.fetchall()]


def _leer_indicadores(c, secuencia_id):

    c.execute("""SELECT il.*, ce.codigo AS codigo_competencia FROM secuencia_indicador si
                 JOIN indicadores_logro il ON si.indicador_id = il.id
                 JOIN competencias_especificas ce ON il.competencia_id = ce.id
                 WHERE si.secuencia_id=? ORDER BY ce.orden, ce.codigo, il.orden, il.codigo""",
              (secuencia_id,))

    return [dict(fila) for fila in c.fetchall()]


def _leer_tareas(c, secuencia_id):

    c.execute("""SELECT t.id, t.titulo, t.categoria, t.fecha_entrega FROM secuencia_tarea st
                 JOIN tareas t ON st.tarea_id = t.id WHERE st.secuencia_id=?
                 ORDER BY t.fecha_entrega, t.titulo""", (secuencia_id,))

    return [dict(fila) for fila in c.fetchall()]


def leer_sesiones(c, secuencia_id):

    c.execute("SELECT * FROM secuencia_sesiones WHERE secuencia_id=? ORDER BY orden, id", (secuencia_id,))

    return [dict(fila) for fila in c.fetchall()]


#Resumen para la tabla principal. materias_permitidas (un set de ids) limita a un Profesor a sus
#materias, igual que el resto de módulos; None significa sin restricción. Un Profesor también ve las
#secuencias que él mismo creó (profesor_id), aunque la materia no sea suya.
def listar_secuencias(profesor_id=None, materias_permitidas=None, materia_id=None,
                      grado_id=None, estado=None, texto=""):

    condiciones= []
    valores= []

    if materias_permitidas is not None:

        marcadores= ", ".join("?" * len(materias_permitidas)) or "NULL"
        condicion= f"s.materia_id IN ({marcadores})"
        valores.extend(sorted(materias_permitidas))

        if profesor_id is not None:
            condicion= f"({condicion} OR s.profesor_id = ?)"
            valores.append(profesor_id)

        condiciones.append(condicion)

    if materia_id:
        condiciones.append("s.materia_id = ?")
        valores.append(materia_id)

    if grado_id:
        condiciones.append("s.grado_id = ?")
        valores.append(grado_id)

    if estado:
        condiciones.append("s.estado = ?")
        valores.append(estado)

    if texto and texto.strip():
        condiciones.append("(s.titulo LIKE ? OR s.situacion_aprendizaje LIKE ?)")
        valores.extend([f"%{texto.strip()}%"] * 2)

    donde= ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    conn= obtener_conexion()

    try:

        c= conn.cursor()
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
                      {donde}
                      ORDER BY COALESCE(s.fecha_inicio, s.creado) DESC, s.id DESC""", valores)

        return [dict(fila) for fila in c.fetchall()]

    finally:
        conn.close()


# -----------------------------------------
# eliminar, duplicar y marcar avance
# -----------------------------------------
def eliminar_secuencia(secuencia_id):

    conn= obtener_conexion()

    try:
        conn.execute("DELETE FROM secuencias_didacticas WHERE id=?", (secuencia_id,))
        conn.commit()

    finally:
        conn.close()


#Copia una secuencia para reutilizarla en otro grupo o período: queda en Borrador, sin fechas y con
#ninguna sesión realizada. No copia las tareas vinculadas. Devuelve el id de la copia.
def duplicar_secuencia(secuencia_id, nuevo_titulo=None):

    secuencia= obtener_secuencia(secuencia_id)

    if secuencia is None:
        raise ValueError("La secuencia ya no existe.")

    datos= {campo: secuencia.get(campo) for campo in CAMPOS_SECUENCIA}
    datos["titulo"]= nuevo_titulo or f"{secuencia['titulo']} (copia)"
    datos["estado"]= "Borrador"
    datos["fecha_inicio"]= None
    datos["fecha_fin"]= None

    sesiones= [dict(sesion, fecha=None, realizada=0) for sesion in secuencia["sesiones"]]

    return guardar_secuencia(
        datos,
        competencias_ids=[competencia["id"] for competencia in secuencia["competencias"]],
        indicadores_ids=[indicador["id"] for indicador in secuencia["indicadores"]],
        tareas_ids=[],
        sesiones=sesiones)


def marcar_sesion_realizada(sesion_id, realizada=True):

    conn= obtener_conexion()

    try:
        conn.execute("UPDATE secuencia_sesiones SET realizada=? WHERE id=?", (1 if realizada else 0, sesion_id))
        conn.commit()

    finally:
        conn.close()


# -----------------------------------------
# sesiones: plantilla, fechas y avance
# -----------------------------------------
#Plantilla inicial: la primera sesión es de Inicio, la última de Cierre y las del medio de Desarrollo.
#Si es una sola sesión, es de Desarrollo.
def sesiones_base(cantidad=3):

    cantidad= max(1, int(cantidad))
    sesiones= []

    for posicion in range(cantidad):
        sesiones.append({"fecha": None, "momento": _momento_de_sesion(posicion, cantidad),
                         "actividad": "", "evidencia": "", "instrumento": "", "metacognicion": "",
                         "recursos": "", "duracion_min": 0, "realizada": 0})

    return sesiones


def _momento_de_sesion(posicion, cantidad):

    if cantidad == 1:
        return "Desarrollo"

    if posicion == 0:
        return "Inicio"

    if posicion == cantidad - 1:
        return "Cierre"

    return "Desarrollo"


#Las fechas (YYYY-MM-DD) de las sesiones a partir de fecha_inicio, usando solo los días de la semana
#indicados (0 es lunes) y saltando los feriados.
def distribuir_fechas(fecha_inicio, cantidad, dias_semana=(0, 1, 2, 3, 4), feriados=()):

    if cantidad <= 0:
        return []

    dias= set(dias_semana)

    if not dias:
        raise ValueError("Indica al menos un día de clase.")

    feriados_saltados= {str(feriado)[:10] for feriado in feriados}
    dia= datetime.strptime(str(fecha_inicio)[:10], "%Y-%m-%d")
    fechas= []

    while len(fechas) < cantidad:

        fecha_iso= dia.strftime("%Y-%m-%d")

        if dia.weekday() in dias and fecha_iso not in feriados_saltados:
            fechas.append(fecha_iso)

        dia += timedelta(days=1)

    return fechas


#Devuelve (sesiones realizadas, total de sesiones, porcentaje entero).
def progreso(sesiones):

    total= len(sesiones)
    realizadas= sum(1 for sesion in sesiones if sesion.get("realizada"))
    porcentaje= round(100 * realizadas / total) if total else 0

    return realizadas, total, porcentaje


# -----------------------------------------
# validación pedagógica
# -----------------------------------------
#Lista de avisos para ayudar al docente a completar lo que el formato del MINERD espera. No impiden
#guardar la secuencia.
def validar_secuencia(secuencia):

    avisos= []

    if not (secuencia.get("situacion_aprendizaje") or "").strip():
        avisos.append("Falta la situación de aprendizaje.")

    if not secuencia.get("competencias") and not secuencia.get("competencias_fundamentales_lista"):
        avisos.append("No se ha seleccionado ninguna competencia.")

    if secuencia.get("competencias") and not secuencia.get("indicadores"):
        avisos.append("Hay competencias específicas pero ningún indicador de logro.")

    campos_de_contenido= ("contenido_conceptos", "contenido_procedimientos", "contenido_actitudes")

    if not any((secuencia.get(campo) or "").strip() for campo in campos_de_contenido):
        avisos.append("No se han descrito contenidos (conceptos, procedimientos o actitudes y valores).")

    avisos.extend(_avisos_de_sesiones(secuencia.get("sesiones") or []))

    return avisos


def _avisos_de_sesiones(sesiones):

    if not sesiones:
        return ["La secuencia no tiene sesiones."]

    avisos= []

    if not any(sesion.get("momento") == "Inicio" for sesion in sesiones):
        avisos.append("Ninguna sesión es de Inicio (recuperación de saberes previos).")

    if not any(sesion.get("momento") == "Cierre" for sesion in sesiones):
        avisos.append("Ninguna sesión es de Cierre.")

    #los números de sesión empiezan en 1, como los ve el docente en la tabla
    sin_actividad= [numero for numero, sesion in enumerate(sesiones, 1)
                    if not (sesion.get("actividad") or "").strip()]

    if sin_actividad:
        avisos.append("Sesiones sin actividad descrita: " + ", ".join(map(str, sin_actividad)) + ".")

    sin_instrumento= [numero for numero, sesion in enumerate(sesiones, 1)
                      if (sesion.get("evidencia") or "").strip() and not (sesion.get("instrumento") or "").strip()]

    if sin_instrumento:
        avisos.append("Sesiones con evidencia pero sin instrumento de evaluación: "
                      + ", ".join(map(str, sin_instrumento)) + ".")

    return avisos


# -----------------------------------------
# listas para los selectores de la pantalla
# -----------------------------------------
#Los indicadores de logro de las competencias elegidas.
def indicadores_de_competencias(competencias_ids):

    ids= list(competencias_ids or [])

    if not ids:
        return []

    conn= obtener_conexion()

    try:

        c= conn.cursor()
        c.execute(f"""SELECT il.*, ce.codigo AS codigo_competencia FROM indicadores_logro il
                      JOIN competencias_especificas ce ON il.competencia_id = ce.id
                      WHERE il.competencia_id IN ({', '.join('?' * len(ids))})
                      ORDER BY ce.orden, ce.codigo, il.orden, il.codigo""", ids)

        return [dict(fila) for fila in c.fetchall()]

    finally:
        conn.close()


#Las tareas del Banco de Tareas de una materia (y de un grado, si se indica) para poder vincularlas.
def tareas_de_materia(materia_id, grado_id=None):

    if not materia_id:
        return []

    conn= obtener_conexion()

    try:

        c= conn.cursor()

        if grado_id:
            c.execute("""SELECT id, titulo, categoria, fecha_entrega FROM tareas
                         WHERE materia_id=? AND (curso_id IS NULL OR curso_id=?)
                         ORDER BY fecha_entrega, titulo""", (materia_id, grado_id))
        else:
            c.execute("""SELECT id, titulo, categoria, fecha_entrega FROM tareas
                         WHERE materia_id=? ORDER BY fecha_entrega, titulo""", (materia_id,))

        return [dict(fila) for fila in c.fetchall()]

    finally:
        conn.close()


# -----------------------------------------
# exportar a Word (.docx) con el esquema del MINERD
# -----------------------------------------
#Genera el Word de la secuencia y devuelve la ruta. Lanza ValueError si la secuencia no existe.
def exportar_docx(secuencia_id, ruta_salida):

    secuencia= obtener_secuencia(secuencia_id)

    if secuencia is None:
        raise ValueError("La secuencia ya no existe.")

    return escribir_docx(secuencia, ruta_salida, _nombre_centro())


def _nombre_centro():

    try:

        conn= obtener_conexion()
        fila= conn.execute("SELECT nombre_institucion FROM configuracion WHERE id=1").fetchone()
        conn.close()

        return (fila["nombre_institucion"] if fila else "") or ""

    except Exception:
        return ""


#Escribe el Word a partir del diccionario de una secuencia. Lo usan las dos ediciones: en Single
#Teacher las competencias y los indicadores vienen sin código. python-docx se importa acá adentro,
#y no arriba, para que la app arranque aunque la librería no esté instalada.
def escribir_docx(secuencia, ruta_salida, centro=""):

    from docx import Document

    documento= Document()

    _preparar_pagina(documento)
    _escribir_encabezado(documento, centro)
    _escribir_tabla_de_datos(documento, secuencia)
    _escribir_cuerpo(documento, secuencia)
    _escribir_tabla_de_sesiones(documento, secuencia)
    _escribir_tareas(documento, secuencia)

    documento.save(ruta_salida)

    return ruta_salida


def _preparar_pagina(documento):

    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm, Pt

    pagina= documento.sections[0]
    pagina.orientation= WD_ORIENT.LANDSCAPE
    pagina.page_width, pagina.page_height= pagina.page_height, pagina.page_width

    for margen in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(pagina, margen, Cm(1.8))

    documento.styles["Normal"].font.name= "Calibri"
    documento.styles["Normal"].font.size= Pt(10)


def _escribir_encabezado(documento, centro):

    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    parrafo= documento.add_paragraph()
    parrafo.alignment= WD_ALIGN_PARAGRAPH.CENTER

    if centro:
        texto_centro= parrafo.add_run(centro + "\n")
        texto_centro.bold= True
        texto_centro.font.size= Pt(13)

    titulo= parrafo.add_run("Planificación de Unidad de Aprendizaje — Secuencia Didáctica")
    titulo.bold= True
    titulo.font.size= Pt(12)


#Cuadro de arriba: tres filas con dos pares "rótulo y valor" cada una.
def _escribir_tabla_de_datos(documento, secuencia):

    fechas= _unir(" – ", _fecha_para_word(secuencia.get("fecha_inicio")), _fecha_para_word(secuencia.get("fecha_fin")))

    filas= [
        ("Título de la unidad", secuencia["titulo"], "Asignatura", secuencia.get("materia") or ""),
        ("Grado / Sección", _unir(" ", secuencia.get("grado"), secuencia.get("seccion")),
         "Período / Año escolar", _unir(" · ", secuencia.get("periodo"), secuencia.get("anio_academico"))),
        ("Docente", secuencia.get("profesor") or "", "Fechas", fechas),
    ]

    tabla= documento.add_table(rows=3, cols=4)
    tabla.style= "Table Grid"

    for fila_tabla, (rotulo1, valor1, rotulo2, valor2) in zip(tabla.rows, filas):

        _poner_texto_celda(fila_tabla.cells[0], rotulo1, negrita=True)
        _sombrear_celda(fila_tabla.cells[0])
        _poner_texto_celda(fila_tabla.cells[1], valor1)
        _poner_texto_celda(fila_tabla.cells[2], rotulo2, negrita=True)
        _sombrear_celda(fila_tabla.cells[2])
        _poner_texto_celda(fila_tabla.cells[3], valor2)


#Todo lo que va entre el cuadro de datos y la tabla de sesiones. Cada bloque solo sale si tiene algo escrito.
def _escribir_cuerpo(documento, secuencia):

    _escribir_bloque(documento, "Eje transversal / Descriptores", secuencia.get("eje_transversal"))
    _escribir_bloque(documento, "Situación de aprendizaje", secuencia.get("situacion_aprendizaje"))

    if secuencia.get("competencias_fundamentales_lista"):

        _escribir_titulo(documento, "Competencias fundamentales")

        for nombre in secuencia["competencias_fundamentales_lista"]:
            documento.add_paragraph(nombre, style="List Bullet")

    if secuencia.get("competencias"):

        _escribir_titulo(documento, "Competencias específicas")

        for competencia in secuencia["competencias"]:
            documento.add_paragraph(_codigo_y_texto(competencia.get("codigo"), competencia["descripcion"]),
                                    style="List Bullet")

    _escribir_contenidos(documento, secuencia)

    if secuencia.get("indicadores"):

        _escribir_titulo(documento, "Indicadores de logro")

        for indicador in secuencia["indicadores"]:
            prefijo= _unir(" · ", indicador.get("codigo_competencia"), indicador.get("codigo"))
            documento.add_paragraph(_codigo_y_texto(prefijo, indicador["descripcion"], ": "), style="List Bullet")

    _escribir_bloque(documento, "Estrategia de enseñanza y de aprendizaje", secuencia.get("estrategia"))


#Tabla de tres columnas: conceptos, procedimientos y actitudes y valores.
def _escribir_contenidos(documento, secuencia):

    contenidos= [("Conceptos", secuencia.get("contenido_conceptos")),
                 ("Procedimientos", secuencia.get("contenido_procedimientos")),
                 ("Actitudes y valores", secuencia.get("contenido_actitudes"))]

    if not any((texto or "").strip() for _, texto in contenidos):
        return

    _escribir_titulo(documento, "Contenidos")

    tabla= documento.add_table(rows=2, cols=3)
    tabla.style= "Table Grid"

    for columna, (rotulo, texto) in enumerate(contenidos):
        _poner_texto_celda(tabla.rows[0].cells[columna], rotulo, negrita=True)
        _sombrear_celda(tabla.rows[0].cells[columna])
        _poner_texto_celda(tabla.rows[1].cells[columna], texto)


def _escribir_tabla_de_sesiones(documento, secuencia):

    _escribir_titulo(documento, "Secuencia didáctica")

    columnas= ["Fecha", "Momento", "Actividades de aprendizaje", "Evidencias de aprendizaje",
               "Instrumentos de evaluación", "Metacognición", "Recursos"]

    tabla= documento.add_table(rows=1, cols=len(columnas))
    tabla.style= "Table Grid"

    for columna, nombre in enumerate(columnas):
        _poner_texto_celda(tabla.rows[0].cells[columna], nombre, negrita=True)
        _sombrear_celda(tabla.rows[0].cells[columna])

    for sesion in secuencia["sesiones"]:

        celdas= tabla.add_row().cells
        valores= [_fecha_para_word(sesion.get("fecha")), sesion.get("momento") or "",
                  sesion.get("actividad") or "", sesion.get("evidencia") or "",
                  sesion.get("instrumento") or "", sesion.get("metacognicion") or "",
                  sesion.get("recursos") or ""]

        for celda, valor in zip(celdas, valores):
            _poner_texto_celda(celda, valor)


def _escribir_tareas(documento, secuencia):

    if not secuencia.get("tareas"):
        return

    _escribir_titulo(documento, "Tareas vinculadas del Banco de Tareas")

    for tarea in secuencia["tareas"]:

        entrega= ""

        if tarea.get("fecha_entrega"):
            entrega= f" (entrega {_fecha_para_word(tarea['fecha_entrega'])})"

        documento.add_paragraph(f"{tarea['titulo']} — {tarea.get('categoria') or 'Tarea'}{entrega}",
                                style="List Bullet")


# -----------------------------------------
# piezas chicas del Word
# -----------------------------------------
def _escribir_titulo(documento, texto):

    from docx.shared import Pt

    parrafo= documento.add_paragraph()
    letras= parrafo.add_run(texto)
    letras.bold= True
    letras.font.size= Pt(11)
    parrafo.paragraph_format.space_before= Pt(8)
    parrafo.paragraph_format.space_after= Pt(2)


#Un título con su párrafo debajo, solo si el valor tiene algo escrito.
def _escribir_bloque(documento, rotulo, valor):

    if not (valor or "").strip():
        return

    _escribir_titulo(documento, rotulo)
    documento.add_paragraph(valor.strip())


def _poner_texto_celda(celda, texto, negrita=False):

    celda.text= ""
    letras= celda.paragraphs[0].add_run(texto or "")
    letras.bold= negrita


#Pinta el fondo de la celda. python-docx no trae una función para esto, hay que escribir el XML.
def _sombrear_celda(celda, color="D9E2F3"):

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    propiedades= celda._tc.get_or_add_tcPr()
    sombra= OxmlElement("w:shd")
    sombra.set(qn("w:val"), "clear")
    sombra.set(qn("w:color"), "auto")
    sombra.set(qn("w:fill"), color)
    propiedades.append(sombra)


#La fecha guardada es YYYY-MM-DD y en el Word va como DD/MM/YYYY. Si no hay fecha, queda vacío.
def _fecha_para_word(fecha_iso):

    try:
        return datetime.strptime(str(fecha_iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")

    except (ValueError, TypeError):
        return ""


#Une los textos que no estén vacíos con el separador. Sirve para "grado sección", "período · año", etc.
def _unir(separador, *textos):

    return separador.join(texto for texto in textos if texto)


def _codigo_y_texto(codigo, descripcion, separador=". "):

    return f"{codigo}{separador}{descripcion}" if codigo else descripcion
