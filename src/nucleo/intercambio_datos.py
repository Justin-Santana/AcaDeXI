"""Intercambio de datos ENTRE las 4 ediciones de AcaDeXI.

El motor de permisos (permisos.py) resuelve QUÉ puede ver/hacer cada
edición. Este módulo resuelve algo distinto: cómo un Estudiante, una
Calificación o un registro de Asistencia capturado en UNA edición puede
viajar y entenderse en OTRA, aunque su esquema interno de base de datos sea
distinto -el caso más claro es Single Teacher (bd_single_teacher.py, sin
overrides institucionales, Pieza 3(b) del prompt de arquitectura) contra
Full Institutional/Docentes (bd.py completo, con jerarquía institucional
debajo).

Casos reales que esto habilita:
  - Un Profesor en Single Teacher se incorpora formalmente a una
    institución: exporta sus Estudiantes y Calificaciones, y Dirección
    (Full Institutional) o Coordinación (Side Stepper, si el módulo
    correspondiente está otorgado) las importa a una Sección real.
  - Un Profesor en la edición Docentes exporta "sus" estudiantes (ya
    combinados con sus overrides locales, ver datos_locales_docente.py)
    para un respaldo personal o para pasárselos a otro colega.
  - Cualquier edición exporta Calificaciones de un periodo para que otra
    las revise o las combine, sin que ninguna de las dos necesite compartir
    el mismo archivo acadexi.db.

NO reemplaza a los mecanismos ya existentes (.acdx de perfil/BD Base para
aprovisionar una instalación entera, sincronizacion.py/sync_backends.py
para mantener una MISMA base de datos igual entre equipos). Este módulo es
para mover un SUBCONJUNTO de datos (una sección, un periodo) entre
instalaciones que NO comparten base de datos y que pueden incluso ser
ediciones distintas.

FORMATO DEL PAQUETE (extensión .acdxpkg; JSON plano, no cifrado -son datos
que la propia institución va a manejar entre sus miembros, igual que hoy se
pasan un Excel):
{
    "version_formato": 1,
    "tipo": "estudiantes" | "calificaciones" | "asistencia",
    "edicion_origen": "full" | "docentes" | "single_teacher" | "side_stepper",
    "generado": "2026-08-21 10:00:00",
    "registros": [ {...canónico...}, ... ]
}

REGLA DE IMPORTACIÓN (evita duplicar datos ya existentes en el destino):
el emparejamiento de un estudiante NUNCA usa el id interno de origen (cada
instalación tiene su propio autoincremental, no son comparables entre
ediciones) — se empareja por (nombre, apellidos, fecha_nacimiento). Si
coincide con un estudiante ya existente en el destino, se actualiza; si no,
se crea uno nuevo. Las calificaciones/asistencia se emparejan por el
NOMBRE de la materia y del periodo (no por su id), porque tampoco son
comparables entre instalaciones distintas.
"""
import json
from datetime import datetime

VERSION_FORMATO = 1
EXTENSION = ".acdxpkg"

CAMPOS_CANONICOS_ESTUDIANTE = ["nombre", "apellidos", "sexo", "fecha_nacimiento", "documento",
                                "direccion", "telefono", "correo", "tutor", "tutor2", "estado"]


# ============================================================
# ACCESO A DATOS SEGÚN EDICIÓN — el resto de este módulo trabaja siempre
# sobre listas de dicts "canónicos"; estas dos funciones son el único punto
# que sabe de qué esquema de base de datos concreto vienen/van esos dicts.
# ============================================================
def _conexion_para_edicion(main_window):
    """Devuelve (conexion, edicion). Para "full"/"docentes" es bd.get_connection()
    normal (Docentes ya trae aplicados sus overrides locales cuando se lee vía
    datos_locales_docente.aplicar_override; ver exportar_estudiantes). Para
    "single_teacher" es la conexión propia de bd_single_teacher.py."""
    try:
        from src.nucleo.edicion import edicion_actual
        edicion = edicion_actual()
    except Exception:
        edicion = "full"
    if edicion == "single_teacher":
        from src.nucleo import bd_single_teacher
        return bd_single_teacher.get_connection(main_window), edicion
    from src.nucleo.bd import get_connection
    return get_connection(), edicion


# ============================================================
# ESTUDIANTES
# ============================================================
def exportar_estudiantes(main_window, ruta_archivo, seccion_id=None):
    """Exporta estudiantes (de una sección concreta, o todos si
    seccion_id=None) al formato canónico. En "docentes", si el estudiante
    tiene un override local (datos_locales_docente), se exporta la versión
    YA COMBINADA (aplicar_override) -es lo que el propio docente ve y
    considera correcto, no el dato institucional crudo."""
    conn, edicion = _conexion_para_edicion(main_window)
    c = conn.cursor()
    if seccion_id is not None:
        c.execute("SELECT * FROM estudiantes WHERE seccion_id=?", (seccion_id,))
    else:
        c.execute("SELECT * FROM estudiantes")
    filas = [dict(f) for f in c.fetchall()]
    conn.close()

    if edicion == "docentes":
        from src.nucleo.datos_locales_docente import listar_overrides_estudiantes, aplicar_override
        overrides = listar_overrides_estudiantes(main_window)
        filas = [aplicar_override(f, overrides.get(f["id"])) for f in filas]

    registros = [{campo: f.get(campo, "") for campo in CAMPOS_CANONICOS_ESTUDIANTE} for f in filas]
    _escribir_paquete(ruta_archivo, "estudiantes", edicion, registros)
    return len(registros)


def importar_estudiantes(main_window, ruta_archivo, seccion_id_destino=None):
    """Importa un paquete de estudiantes al destino. Empareja por (nombre,
    apellidos, fecha_nacimiento): si ya existe, ACTUALIZA sus campos
    canónicos; si no, lo CREA (y lo asigna a `seccion_id_destino` si se
    indicó -en Full Institutional/Docentes eso es obligatorio para que el
    estudiante aparezca en algún listado; en Single Teacher puede ser una
    "sección"/curso propio del docente).

    Devuelve {"creados": n, "actualizados": n}."""
    datos = _leer_paquete(ruta_archivo, tipo_esperado="estudiantes")
    conn, edicion = _conexion_para_edicion(main_window)
    c = conn.cursor()
    creados = actualizados = 0
    for reg in datos["registros"]:
        c.execute("""SELECT id FROM estudiantes WHERE nombre=? AND apellidos=? AND
                     IFNULL(fecha_nacimiento,'')=IFNULL(?,'')""",
                  (reg.get("nombre", ""), reg.get("apellidos", ""), reg.get("fecha_nacimiento", "")))
        existente = c.fetchone()
        if existente:
            sets = ", ".join(f"{campo}=?" for campo in CAMPOS_CANONICOS_ESTUDIANTE)
            valores = [reg.get(campo, "") for campo in CAMPOS_CANONICOS_ESTUDIANTE]
            c.execute(f"UPDATE estudiantes SET {sets} WHERE id=?", (*valores, existente["id"]))
            actualizados += 1
        else:
            columnas = list(CAMPOS_CANONICOS_ESTUDIANTE)
            valores = [reg.get(campo, "") for campo in columnas]
            if seccion_id_destino is not None:
                columnas.append("seccion_id")
                valores.append(seccion_id_destino)
            marcadores = ", ".join("?" for _ in columnas)
            c.execute(f"INSERT INTO estudiantes ({', '.join(columnas)}) VALUES ({marcadores})", valores)
            creados += 1
    conn.commit()
    conn.close()
    return {"creados": creados, "actualizados": actualizados}


# ============================================================
# CALIFICACIONES (emparejadas por NOMBRE de materia y de periodo, no por id)
# ============================================================
def exportar_calificaciones(main_window, ruta_archivo, materia_id, periodo_id=None):
    conn, edicion = _conexion_para_edicion(main_window)
    c = conn.cursor()
    c.execute("SELECT nombre FROM materias WHERE id=?", (materia_id,))
    fila_materia = c.fetchone()
    nombre_materia = fila_materia["nombre"] if fila_materia else ""

    parametros = [materia_id]
    filtro_periodo = ""
    nombre_periodo = ""
    if periodo_id is not None:
        c.execute("SELECT nombre FROM periodos WHERE id=?", (periodo_id,))
        fila_periodo = c.fetchone()
        nombre_periodo = fila_periodo["nombre"] if fila_periodo else ""
        filtro_periodo = " AND calificaciones.periodo_id=?"
        parametros.append(periodo_id)

    c.execute(f"""SELECT estudiantes.nombre as est_nombre, estudiantes.apellidos as est_apellidos,
                  estudiantes.fecha_nacimiento as est_fecha_nacimiento,
                  calificaciones.categoria, calificaciones.descripcion,
                  calificaciones.valor, calificaciones.peso
                  FROM calificaciones
                  JOIN estudiantes ON calificaciones.estudiante_id = estudiantes.id
                  WHERE calificaciones.materia_id=?{filtro_periodo}""", parametros)
    filas = c.fetchall()
    conn.close()

    registros = [{
        "estudiante_nombre": f["est_nombre"], "estudiante_apellidos": f["est_apellidos"],
        "estudiante_fecha_nacimiento": f["est_fecha_nacimiento"],
        "materia_nombre": nombre_materia, "periodo_nombre": nombre_periodo,
        "categoria": f["categoria"], "descripcion": f["descripcion"],
        "valor": f["valor"], "peso": f["peso"],
    } for f in filas]
    _escribir_paquete(ruta_archivo, "calificaciones", edicion, registros)
    return len(registros)


def importar_calificaciones(main_window, ruta_archivo, materia_id_destino, periodo_id_destino):
    """Importa calificaciones hacia `materia_id_destino`/`periodo_id_destino`
    ya elegidos por quien importa (a diferencia de estudiantes, aquí SIEMPRE
    se pide el destino explícito: mezclar calificaciones de una materia con
    otra por nombre sería demasiado arriesgado de automatizar). Solo importa
    la calificación de un estudiante si ese estudiante YA EXISTE en el
    destino (emparejado igual que en importar_estudiantes); los que no
    existan se reportan para que el usuario los importe primero con
    importar_estudiantes. Devuelve {"importadas": n, "estudiantes_faltantes": [...]}."""
    datos = _leer_paquete(ruta_archivo, tipo_esperado="calificaciones")
    conn, edicion = _conexion_para_edicion(main_window)
    c = conn.cursor()
    importadas = 0
    faltantes = []
    for reg in datos["registros"]:
        c.execute("""SELECT id FROM estudiantes WHERE nombre=? AND apellidos=? AND
                     IFNULL(fecha_nacimiento,'')=IFNULL(?,'')""",
                  (reg.get("estudiante_nombre", ""), reg.get("estudiante_apellidos", ""),
                   reg.get("estudiante_fecha_nacimiento", "")))
        fila_est = c.fetchone()
        if not fila_est:
            faltantes.append(f"{reg.get('estudiante_nombre', '')} {reg.get('estudiante_apellidos', '')}".strip())
            continue
        c.execute("""INSERT INTO calificaciones
                     (estudiante_id, materia_id, periodo_id, categoria, descripcion, valor, peso)
                     VALUES (?,?,?,?,?,?,?)""",
                  (fila_est["id"], materia_id_destino, periodo_id_destino,
                   reg.get("categoria", ""), reg.get("descripcion", ""),
                   reg.get("valor"), reg.get("peso", 0)))
        importadas += 1
    conn.commit()
    conn.close()
    return {"importadas": importadas, "estudiantes_faltantes": faltantes}


# ============================================================
# LECTURA/ESCRITURA DEL PAQUETE
# ============================================================
def _escribir_paquete(ruta_archivo, tipo, edicion, registros):
    paquete = {
        "version_formato": VERSION_FORMATO,
        "tipo": tipo,
        "edicion_origen": edicion,
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "registros": registros,
    }
    with open(ruta_archivo, "w", encoding="utf-8") as f:
        json.dump(paquete, f, ensure_ascii=False, indent=2)


def _leer_paquete(ruta_archivo, tipo_esperado):
    with open(ruta_archivo, "r", encoding="utf-8") as f:
        datos = json.load(f)
    if datos.get("tipo") != tipo_esperado:
        raise ValueError(
            f"Este archivo es un paquete de '{datos.get('tipo', 'desconocido')}', "
            f"no de '{tipo_esperado}'. Elige el archivo correcto.")
    if datos.get("version_formato", 0) > VERSION_FORMATO:
        raise ValueError(
            "Este paquete se generó con una versión más nueva de AcaDeXI que no "
            "reconoce este campo de intercambio. Actualiza la app antes de importarlo.")
    return datos
