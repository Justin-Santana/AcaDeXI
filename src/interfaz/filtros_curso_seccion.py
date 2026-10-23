"""Cascada Curso/Grado -> Sección, ÚNICA implementación compartida por TODOS
los módulos y pestañas de AcaDeXI que tengan este par de combos (filtros de
listado y formularios de captura por igual).

Antes, cada módulo (Asistencia, Calificaciones, Observaciones, Horario,
Estudiantes, Politécnico, Reportes, Banco de Tareas, Materias, Calendario...)
tenía su PROPIA copia de esta lógica, ligeramente distinta entre sí. Eso
provocó una serie de bugs repetidos (etiquetas "5to - A" en vez de "A" al
elegir curso, Sección quedándose en una sección vieja al volver a "Todos los
cursos", combos de Estudiante auto-seleccionando el primero de la lista sin
que el usuario lo eligiera...) que había que ir corrigiendo módulo por
módulo porque cada uno tenía su propia variante del mismo código.

Con este módulo, TODOS usan las mismas dos funciones (`poblar_combo_curso` y
`cascada_seccion_por_curso`) así que el comportamiento es idéntico en todas
partes y un arreglo aquí se aplica a todos los módulos a la vez.

REGLAS (idénticas en todos lados, en filtros y formularios de captura por igual):
  1. Con curso elegido -> Sección se muestra CORTA ("A", "B", "C"...).
     Sin curso elegido (viendo varios cursos mezclados) -> Sección se
     muestra "Curso - Sección" para no confundir secciones homónimas.
  2. Curso SIEMPRE es obligatorio primero: "Selecciona un curso/grado…"
     (data=None), sin opción "Todos los cursos" — ni siquiera en combos de
     filtro. Mientras no se elija un curso, Sección queda vacía con el
     placeholder "Selecciona primero un curso/grado…": nunca se
     auto-selecciona una sección real sin que el usuario la haya elegido,
     y nunca se ofrece un salto directo a "verlo todo" sin pasar por Curso
     primero (así se ve exactamente igual que "Asignar Clase" en Horarios
     de Materias, el patrón de referencia).
  3. La única excepción es un campo verdaderamente OPCIONAL (por ejemplo,
     la Sección de un evento del Calendario, o de una clase local del Modo
     Docente): ahí sí puede pasarse incluir_todas=True con una etiqueta
     como "— Ninguna —", porque "sin sección" es un valor de datos válido,
     no un atajo para saltarse el filtro por curso.
"""
from src.nucleo.bd import get_connection
from src.interfaz.configuracion import conectar_tooltip_seleccion


def poblar_combo_curso(combo, incluir_todos=False, seleccion_previa=None, secciones_permitidas=None):
    """Llena `combo` con todos los Grados/Cursos de la BD.

    - incluir_todos=True  -> primera opción "Todos los cursos" (data=None).
    - incluir_todos=False -> primera opción "Selecciona un curso/grado…"
      (data=None), para formularios donde el curso es obligatorio.
    - secciones_permitidas: set opcional de IDs de sección (RBAC de Profesor
      restringido). Si se pasa, solo se listan los cursos que tengan al
      menos una sección permitida.

    Conserva la selección previa si sigue existiendo en la lista nueva
    (por defecto, la que ya tuviera `combo` antes de llamar esta función;
    se puede forzar otra con `seleccion_previa`)."""
    if seleccion_previa is None and combo.count():
        seleccion_previa = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("Todos los cursos" if incluir_todos else "Selecciona un curso/grado…", None)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nombre FROM grados ORDER BY orden, nombre")
    filas_grados = c.fetchall()
    for f in filas_grados:
        if secciones_permitidas is not None:
            c.execute("SELECT id FROM secciones WHERE grado_id=?", (f["id"],))
            ids_seccion = {s["id"] for s in c.fetchall()}
            if not (ids_seccion & secciones_permitidas):
                continue
        combo.addItem(f["nombre"], f["id"])
    conn.close()
    idx = combo.findData(seleccion_previa)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)
    conectar_tooltip_seleccion(combo, "Curso/Grado")


def cascada_seccion_por_curso(combo_curso, combo_seccion, incluir_todas=False, secciones_permitidas=None,
                               etiqueta_todas="Todas las secciones", etiquetas_cortas_sin_curso=False):
    """Repuebla `combo_seccion` según el curso elegido en `combo_curso`.
    Ver las reglas 1-3 en el docstring del módulo. `secciones_permitidas`
    es un set opcional de IDs de sección (RBAC de Profesor restringido);
    None = sin restricción. `etiqueta_todas` permite personalizar el texto
    del ítem "sin sección concreta" cuando incluir_todas=True (por ejemplo,
    "— Ninguna —" en vez de "Todas las secciones" para un campo opcional).

    `etiquetas_cortas_sin_curso`: por defecto (False) sigue la Regla 1 de
    siempre -"Curso - Sección" cuando se ven varios cursos mezclados, para
    no confundir secciones homónimas de distintos grados (ej. "5to - A" y
    "3ro - A")-. Ponlo en True SOLO si el propio caso de uso ya deja claro
    a qué curso pertenece cada sección por otro medio (por ejemplo, un
    "Alcance" opcional donde igual se elige el Curso en un combo aparte de
    al lado) y se prefiere el texto corto ("A") incluso sin curso
    seleccionado. Con secciones homónimas entre grados, esto puede volver
    ambiguo cuál es cuál -por eso no es el comportamiento por defecto-."""
    curso_id = combo_curso.currentData()
    seleccion_previa = combo_seccion.currentData()
    combo_seccion.blockSignals(True)
    combo_seccion.clear()

    if incluir_todas:
        combo_seccion.addItem(etiqueta_todas, None)
    elif curso_id is None:
        combo_seccion.addItem("Selecciona primero un curso/grado…", None)
    else:
        combo_seccion.addItem("Selecciona una sección…", None)

    if curso_id is not None or incluir_todas:
        conn = get_connection()
        c = conn.cursor()
        if curso_id is not None:
            c.execute("SELECT id, nombre FROM secciones WHERE grado_id=? ORDER BY nombre", (curso_id,))
            for f in c.fetchall():
                if secciones_permitidas is not None and f["id"] not in secciones_permitidas:
                    continue
                combo_seccion.addItem(f["nombre"], f["id"])  # etiqueta corta: ya sabemos el curso
        elif etiquetas_cortas_sin_curso:
            c.execute("""SELECT secciones.id, secciones.nombre FROM secciones
                         LEFT JOIN grados ON secciones.grado_id = grados.id
                         ORDER BY grados.orden, secciones.nombre""")
            for f in c.fetchall():
                if secciones_permitidas is not None and f["id"] not in secciones_permitidas:
                    continue
                combo_seccion.addItem(f["nombre"], f["id"])
        else:
            c.execute("""SELECT secciones.id, secciones.nombre,
                         (grados.nombre || ' - ' || secciones.nombre) as etiqueta
                         FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id
                         ORDER BY grados.orden, secciones.nombre""")
            for f in c.fetchall():
                if secciones_permitidas is not None and f["id"] not in secciones_permitidas:
                    continue
                combo_seccion.addItem(f["etiqueta"], f["id"])
        conn.close()

    if curso_id is None:
        # Sin curso concreto: si el combo es un filtro, se resetea a "Todas las
        # secciones" (índice 0) en vez de conservar una selección específica de
        # un curso que ya no se está viendo. Si es obligatorio, no hay nada que
        # seleccionar todavía (solo está el placeholder, índice 0).
        combo_seccion.setCurrentIndex(0)
    else:
        idx = combo_seccion.findData(seleccion_previa)
        combo_seccion.setCurrentIndex(idx if idx >= 0 else 0)
    combo_seccion.blockSignals(False)
    conectar_tooltip_seleccion(combo_seccion, "Sección")


def poblar_combo_nivel_educativo(combo, incluir_todos=True, seleccion_previa=None):
    """Llena `combo` con los niveles educativos (`grados.nivel_educativo`)
    que realmente existen entre los Cursos/Grados dados de alta -no con la
    lista completa de NIVELES_ACADEMICOS de configuracion.py-, para no
    ofrecer un filtro por un nivel que la institución no tiene ningún grado
    creado todavía. Se listan en el mismo orden fijo de siempre
    (Primaria, Secundaria, Preparatoria, Universidad); cualquier grado con
    `nivel_educativo` NULL ("sin clasificar") se ignora aquí, igual que en
    el resto de la app.

    - incluir_todos=True  -> primera opción "Todos los niveles" (data=None),
      es el caso normal para un combo de FILTRO (Asistencia, Reportes...).
    - incluir_todos=False -> primera opción "Selecciona un nivel…"
      (data=None), para el caso -poco común- de que el nivel sea un dato
      obligatorio en vez de un filtro.

    Conserva la selección previa si sigue existiendo en la lista nueva,
    igual que `poblar_combo_curso`."""
    ORDEN_NIVELES = ["Primaria", "Secundaria", "Preparatoria", "Universidad"]
    if seleccion_previa is None and combo.count():
        seleccion_previa = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("Todos los niveles" if incluir_todos else "Selecciona un nivel…", None)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT nivel_educativo FROM grados WHERE nivel_educativo IS NOT NULL")
    presentes = {f["nivel_educativo"] for f in c.fetchall()}
    conn.close()
    for nivel in ORDEN_NIVELES:
        if nivel in presentes:
            combo.addItem(nivel, nivel)
    idx = combo.findData(seleccion_previa)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


def secciones_del_nivel_educativo(nivel):
    """Devuelve el set de IDs de sección cuyo Curso/Grado pertenece a
    `nivel` ("Primaria", "Secundaria", "Preparatoria", "Universidad").

    `nivel=None` significa "sin filtro de nivel" (por ejemplo, la opción
    "Todos los niveles" de `poblar_combo_nivel_educativo`) y por eso
    devuelve None -no un set vacío- para que `interseccion_opcional` lo
    trate como "no restringe nada", igual que `secciones_permitidas=None`
    ya significa "sin restricción" en `poblar_combo_curso` /
    `cascada_seccion_por_curso`."""
    if nivel is None:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT secciones.id FROM secciones
                 JOIN grados ON secciones.grado_id = grados.id
                 WHERE grados.nivel_educativo=?""", (nivel,))
    ids = {f["id"] for f in c.fetchall()}
    conn.close()
    return ids


def interseccion_opcional(*sets_opcionales):
    """Combina varios sets de IDs de sección que puedan venir o no de una
    restricción activa, donde None siempre significa "sin restricción"
    (ver `secciones_permitidas` en `poblar_combo_curso`/
    `cascada_seccion_por_curso` y el `nivel=None` de
    `secciones_del_nivel_educativo`). Así los llamadores pueden combinar,
    por ejemplo, el RBAC de un Profesor con el filtro de nivel educativo de
    una pantalla sin tener que estar comprobando manualmente cuál de los
    dos es None antes de intersectar.

    - Si TODOS los argumentos son None -> devuelve None (sigue sin haber
      ninguna restricción real).
    - Si solo algunos son sets -> devuelve la intersección de esos (los
      None se ignoran, ya que "sin restricción" no reduce el resultado).
    - Si la intersección resultante es vacía, se devuelve el set vacío tal
      cual (a diferencia de None, un set vacío SÍ es una restricción real:
      significa "ninguna sección cumple las condiciones combinadas")."""
    activos = [s for s in sets_opcionales if s is not None]
    if not activos:
        return None
    resultado = activos[0]
    for s in activos[1:]:
        resultado = resultado & s
    return resultado


def preseleccionar_curso_y_seccion(combo_curso, combo_seccion, seccion_id, incluir_todas=False,
                                    etiqueta_todas="Todas las secciones", etiquetas_cortas_sin_curso=False):
    """Para pantallas de edición: dado el `seccion_id` ya guardado de un
    registro, busca su curso, lo selecciona primero en `combo_curso`, y
    luego llama a la cascada para preseleccionar `seccion_id` en
    `combo_seccion` — igual que al editar un Horario o un Estudiante."""
    grado_id = None
    if seccion_id:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT grado_id FROM secciones WHERE id=?", (seccion_id,))
        fila = c.fetchone()
        conn.close()
        grado_id = fila["grado_id"] if fila else None
    combo_curso.blockSignals(True)
    idx_curso = combo_curso.findData(grado_id)
    combo_curso.setCurrentIndex(idx_curso if idx_curso >= 0 else 0)
    combo_curso.blockSignals(False)
    cascada_seccion_por_curso(combo_curso, combo_seccion, incluir_todas=incluir_todas, etiqueta_todas=etiqueta_todas,
                               etiquetas_cortas_sin_curso=etiquetas_cortas_sin_curso)
    if seccion_id is not None:
        combo_seccion.blockSignals(True)
        idx_seccion = combo_seccion.findData(seccion_id)
        combo_seccion.setCurrentIndex(idx_seccion if idx_seccion >= 0 else 0)
        combo_seccion.blockSignals(False)


# ============================================================
# MÓDULOS TÉCNICOS / MATERIAS VINCULADAS A UN CURSO (opcional)
# ============================================================
# Una materia o módulo técnico puede quedar vinculado a un curso/grado
# (materias.grado_id). Es OPCIONAL: NULL = no vinculado, y entonces aparece
# para cualquier curso del área que lo use. Las áreas técnicas solo existen
# en Secundaria - Segundo Ciclo (ver puede_tener_componente_tecnico), así
# que un módulo técnico solo puede vincularse a esos cursos.

def curso_admite_componente_tecnico(grado_id):
    """True si el curso/grado puede tener módulos técnicos (Secundaria - Segundo Ciclo)."""
    from src.interfaz.configuracion import puede_tener_componente_tecnico
    if grado_id is None:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT nivel_educativo, ciclo_secundaria FROM grados WHERE id=?", (grado_id,))
    f = c.fetchone()
    conn.close()
    return bool(f) and puede_tener_componente_tecnico(f["nivel_educativo"], f["ciclo_secundaria"], None)


def poblar_combo_curso_opcional(combo, solo_con_componente_tecnico=False, seleccion_previa=None):
    """Combo de Curso/Grado OPCIONAL: primera opción \"— Sin curso específico —\" (data=None),
    que deja la materia/módulo disponible para cualquier curso. Con
    solo_con_componente_tecnico=True solo se listan los cursos que admiten
    módulos técnicos (Secundaria - Segundo Ciclo)."""
    from src.interfaz.configuracion import puede_tener_componente_tecnico
    if seleccion_previa is None and combo.count():
        seleccion_previa = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("— Sin curso específico —", None)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, nombre, nivel_educativo, ciclo_secundaria FROM grados ORDER BY orden, nombre")
    for f in c.fetchall():
        if solo_con_componente_tecnico and not puede_tener_componente_tecnico(
                f["nivel_educativo"], f["ciclo_secundaria"], None):
            continue
        combo.addItem(f["nombre"], f["id"])
    conn.close()
    idx = combo.findData(seleccion_previa)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


def modulos_tecnicos_por_area_y_curso(especialidad_id=None, grado_id=None):
    """Lista [(id, nombre)] de módulos técnicos (modelo 'Técnica (RA)').
    - especialidad_id: si se indica, solo los de esa área técnica.
    - grado_id: si se indica, solo los vinculados a ESE curso o sin curso
      específico (grado_id NULL). Sin grado_id: todos los del área."""
    sql = ("SELECT id, nombre FROM materias WHERE modelo_evaluacion = 'Técnica (RA)'")
    params = []
    if especialidad_id is not None:
        sql += " AND especialidad_id = ?"
        params.append(especialidad_id)
    if grado_id is not None:
        sql += " AND (grado_id = ? OR grado_id IS NULL)"
        params.append(grado_id)
    sql += " ORDER BY nombre"
    conn = get_connection()
    c = conn.cursor()
    c.execute(sql, params)
    filas = [(f["id"], f["nombre"]) for f in c.fetchall()]
    conn.close()
    return filas

