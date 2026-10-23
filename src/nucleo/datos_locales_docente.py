"""Almacén LOCAL del Modo Docente de AcaDeXI.

Todo lo que un Profesor guarda aquí (retoques a la ficha de "Mis Estudiantes",
fotos, y entradas de su Horario personal) vive en un archivo SQLite propio,
separado por usuario, dentro de la carpeta de datos de la aplicación. NUNCA se
escribe en la base de datos institucional (acadexi.db) que administra
Dirección/Coordinación/Administración: ese es el objetivo de este módulo.

Esto permite que un docente personalice su copia de trabajo (por ejemplo,
corregir un teléfono, añadir una foto, o anotar una clase que Dirección aún
no cargó al horario oficial) sin alterar los datos "de la fuente de verdad"
que usan los demás roles. Si Dirección reexporta el paquete de Estudiantes y
Cursos, estas personalizaciones LOCALES se conservan (se guardan por
estudiante y no se sobrescriben con la importación).
"""
import os
import sqlite3
from datetime import datetime

from src.nucleo.bd import get_app_data_dir


def _carpeta_local():
    ruta = os.path.join(get_app_data_dir(), "modo_docente_local")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def _clave_docente(main_window):
    """Identificador único y estable del docente logueado, usado para no
    mezclar los datos locales de distintos profesores que compartan equipo."""
    id_usuario = getattr(main_window, "id_usuario_actual", None)
    if id_usuario is not None:
        return f"usuario_{id_usuario}"
    usuario = getattr(main_window, "usuario_actual", None)
    return f"usuario_{usuario}" if usuario else "usuario_default"


def _ruta_bd_local(main_window):
    return os.path.join(_carpeta_local(), f"{_clave_docente(main_window)}.db")


def _conexion_local(main_window):
    conn = sqlite3.connect(_ruta_bd_local(main_window))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS estudiantes_local (
        estudiante_id INTEGER PRIMARY KEY,
        matricula TEXT,
        nombre TEXT,
        apellidos TEXT,
        sexo TEXT,
        fecha_nacimiento TEXT,
        documento TEXT,
        direccion TEXT,
        telefono TEXT,
        correo TEXT,
        tutor TEXT,
        tutor2 TEXT,
        seccion_id INTEGER,
        estado TEXT,
        foto TEXT,
        especialidad_id INTEGER,
        carrera_id INTEGER,
        actualizado TEXT
    )""")
    # Compatibilidad con bases locales creadas antes de que estos campos existieran.
    columnas_existentes = {f["name"] for f in conn.execute("PRAGMA table_info(estudiantes_local)").fetchall()}
    for columna, tipo in (("matricula", "TEXT"), ("seccion_id", "INTEGER"), ("estado", "TEXT"),
                           ("especialidad_id", "INTEGER"), ("carrera_id", "INTEGER")):
        if columna not in columnas_existentes:
            conn.execute(f"ALTER TABLE estudiantes_local ADD COLUMN {columna} {tipo}")
    conn.execute("""CREATE TABLE IF NOT EXISTS colores_materias_local (
        clave TEXT PRIMARY KEY,
        color TEXT,
        color_hv TEXT,
        actualizado TEXT
    )""")
    # Tutorial de primer uso del Modo Docente: "visto" es una preferencia de
    # ESTE equipo para ESTE docente (igual que el resto de esta base local),
    # por eso vive aquí y no en acadexi.db -ver tutoriales.py.
    conn.execute("""CREATE TABLE IF NOT EXISTS tutorial_docente_local (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        visto INTEGER DEFAULT 0,
        actualizado TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS horario_local (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        materia_id INTEGER,
        seccion_id INTEGER,
        dia TEXT,
        hora_inicio TEXT,
        hora_fin TEXT,
        aula_texto TEXT,
        notas TEXT,
        actualizado TEXT
    )""")
    conn.commit()
    return conn


# ============================================================
# OVERRIDES DE "MIS ESTUDIANTES" (solo visibles/editables por este docente)
# ============================================================
CAMPOS_OVERRIDE_ESTUDIANTE = ["matricula", "nombre", "apellidos", "sexo", "fecha_nacimiento", "documento",
                               "direccion", "telefono", "correo", "tutor", "tutor2", "seccion_id", "estado", "foto",
                               "especialidad_id", "carrera_id"]


def obtener_override_estudiante(main_window, estudiante_id):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("SELECT * FROM estudiantes_local WHERE estudiante_id=?", (estudiante_id,))
    f = c.fetchone()
    conn.close()
    return dict(f) if f else None


def listar_overrides_estudiantes(main_window):
    """Devuelve {estudiante_id: {campo: valor, ...}} con todos los retoques locales."""
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("SELECT * FROM estudiantes_local")
    filas = c.fetchall()
    conn.close()
    return {f["estudiante_id"]: dict(f) for f in filas}


def guardar_override_estudiante(main_window, estudiante_id, campos):
    """campos: dict con cualquiera de CAMPOS_OVERRIDE_ESTUDIANTE. Los que no se
    incluyan quedan como estaban (o vacíos si es la primera vez).

    La matrícula NUNCA es editable por el docente (es un dato institucional):
    aunque llegue en `campos`, se ignora y se conserva el valor que ya hubiera
    en el override (o vacío, lo que hace que se siga mostrando la matrícula
    oficial vía aplicar_override)."""
    conn = _conexion_local(main_window)
    c = conn.cursor()
    existente = obtener_override_estudiante(main_window, estudiante_id) or {}
    valores = {campo: campos.get(campo, existente.get(campo, "")) for campo in CAMPOS_OVERRIDE_ESTUDIANTE}
    valores["matricula"] = existente.get("matricula", "")
    c.execute("""INSERT INTO estudiantes_local
                 (estudiante_id, matricula, nombre, apellidos, sexo, fecha_nacimiento, documento, direccion,
                  telefono, correo, tutor, tutor2, seccion_id, estado, foto, especialidad_id, carrera_id, actualizado)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(estudiante_id) DO UPDATE SET
                    matricula=excluded.matricula, nombre=excluded.nombre, apellidos=excluded.apellidos,
                    sexo=excluded.sexo, fecha_nacimiento=excluded.fecha_nacimiento, documento=excluded.documento,
                    direccion=excluded.direccion, telefono=excluded.telefono, correo=excluded.correo,
                    tutor=excluded.tutor, tutor2=excluded.tutor2, seccion_id=excluded.seccion_id,
                    estado=excluded.estado, foto=excluded.foto, especialidad_id=excluded.especialidad_id,
                    carrera_id=excluded.carrera_id, actualizado=excluded.actualizado""",
              (estudiante_id, valores["matricula"], valores["nombre"], valores["apellidos"], valores["sexo"],
               valores["fecha_nacimiento"], valores["documento"], valores["direccion"],
               valores["telefono"], valores["correo"], valores["tutor"], valores["tutor2"],
               valores["seccion_id"] or None, valores["estado"], valores["foto"],
               valores["especialidad_id"] or None, valores["carrera_id"] or None,
               datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


def eliminar_override_estudiante(main_window, estudiante_id):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("DELETE FROM estudiantes_local WHERE estudiante_id=?", (estudiante_id,))
    conn.commit()
    conn.close()


def aplicar_override(fila_institucional, override):
    """Combina una fila de la BD institucional (sqlite3.Row o dict) con su
    override local, si existe. El override GANA en todos los campos personalizables
    (incluidos sección y estado), EXCEPTO la matrícula, que es un dato
    institucional y siempre se muestra tal cual la tiene Dirección/Coordinación;
    lo que no se haya personalizado sigue mostrando el dato institucional tal cual."""
    combinado = dict(fila_institucional)
    if override:
        for campo in CAMPOS_OVERRIDE_ESTUDIANTE:
            valor_local = override.get(campo)
            if valor_local:
                combinado[campo] = valor_local
    return combinado


# ============================================================
# COLORES PERSONALIZADOS DE MATERIAS EN EL HORARIO (solo para este docente,
# solo en este equipo; no cambia el color que ven otros roles ni otros
# profesores). Se identifican por el mismo texto ("clave") que se usa para
# pintar los chips del calendario: el nombre de la materia (o la nota, para
# clases locales sin materia).
# ============================================================
def obtener_colores_materias_local(main_window):
    """Devuelve {clave: (color, color_hv)} con todas las personalizaciones."""
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("SELECT clave, color, color_hv FROM colores_materias_local")
    filas = c.fetchall()
    conn.close()
    return {f["clave"]: (f["color"], f["color_hv"]) for f in filas}


def guardar_color_materia_local(main_window, clave, color, color_hv):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("""INSERT INTO colores_materias_local (clave, color, color_hv, actualizado)
                 VALUES (?,?,?,?)
                 ON CONFLICT(clave) DO UPDATE SET
                    color=excluded.color, color_hv=excluded.color_hv, actualizado=excluded.actualizado""",
              (clave, color, color_hv, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


def eliminar_color_materia_local(main_window, clave):
    """Quita la personalización: la materia vuelve a su color automático."""
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("DELETE FROM colores_materias_local WHERE clave=?", (clave,))
    conn.commit()
    conn.close()


# ============================================================
# HORARIO PERSONAL DEL DOCENTE (no toca la tabla `horarios` institucional)
# ============================================================
def listar_horario_local(main_window):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("SELECT * FROM horario_local ORDER BY dia, hora_inicio")
    filas = [dict(f) for f in c.fetchall()]
    conn.close()
    return filas


def obtener_entrada_horario_local(main_window, id_local):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("SELECT * FROM horario_local WHERE id=?", (id_local,))
    f = c.fetchone()
    conn.close()
    return dict(f) if f else None


def guardar_entrada_horario_local(main_window, id_edicion, materia_id, seccion_id, dia,
                                   hora_inicio, hora_fin, aula_texto, notas):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if id_edicion is None:
        c.execute("""INSERT INTO horario_local
                     (materia_id, seccion_id, dia, hora_inicio, hora_fin, aula_texto, notas, actualizado)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (materia_id, seccion_id, dia, hora_inicio, hora_fin, aula_texto, notas, ahora))
    else:
        c.execute("""UPDATE horario_local SET materia_id=?, seccion_id=?, dia=?, hora_inicio=?,
                     hora_fin=?, aula_texto=?, notas=?, actualizado=? WHERE id=?""",
                  (materia_id, seccion_id, dia, hora_inicio, hora_fin, aula_texto, notas, ahora, id_edicion))
    conn.commit()
    conn.close()


def eliminar_entrada_horario_local(main_window, id_local):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("DELETE FROM horario_local WHERE id=?", (id_local,))
    conn.commit()
    conn.close()


# ============================================================
# TUTORIAL DE PRIMER USO — MODO DOCENTE (independiente del tutorial general;
# ver tutoriales.py). "Visto" es por equipo+docente, igual que el resto de
# esta base local.
# ============================================================
def tutorial_docente_visto(main_window):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("SELECT visto FROM tutorial_docente_local WHERE id=1")
    f = c.fetchone()
    conn.close()
    return bool(f["visto"]) if f else False


def marcar_tutorial_docente_visto(main_window, visto=True):
    conn = _conexion_local(main_window)
    c = conn.cursor()
    c.execute("""INSERT INTO tutorial_docente_local (id, visto, actualizado) VALUES (1, ?, ?)
                 ON CONFLICT(id) DO UPDATE SET visto=excluded.visto, actualizado=excluded.actualizado""",
              (1 if visto else 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
