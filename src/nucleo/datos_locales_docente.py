#Datos LOCALES del Modo Docente. Todo lo que un Profesor retoca (la ficha de "Mis Estudiantes", las
#fotos, los colores de sus materias y su horario personal) se guarda en un SQLite propio, uno por
#usuario, dentro de la carpeta de datos de la app. NUNCA se escribe en acadexi.db, que es la base
#institucional que administran Dirección, Coordinación y Administración.
#
#Así un docente puede corregir un teléfono, poner una foto o anotar una clase que Dirección todavía
#no cargó en el horario oficial, sin cambiar los datos que usan los demás roles. Si Dirección vuelve
#a exportar el paquete de Estudiantes y Cursos, estos retoques se conservan: se guardan por
#estudiante y la importación no los pisa.
import os
import sqlite3
from datetime import datetime

from src.nucleo.bd import get_app_data_dir

#Campos de la ficha del estudiante que el docente puede retocar.
CAMPOS_OVERRIDE_ESTUDIANTE= ["matricula", "nombre", "apellidos", "sexo", "fecha_nacimiento", "documento",
                             "direccion", "telefono", "correo", "tutor", "tutor2", "seccion_id", "estado",
                             "foto", "especialidad_id", "carrera_id"]


def _ahora():

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -----------------------------------------
# la base local
# -----------------------------------------
def _carpeta_local():

    ruta= os.path.join(get_app_data_dir(), "modo_docente_local")
    os.makedirs(ruta, exist_ok=True)

    return ruta


#Identifica al docente que entró, para que dos profesores que comparten un equipo no mezclen sus datos.
def _clave_docente(main_window):

    id_usuario= getattr(main_window, "id_usuario_actual", None)

    if id_usuario is not None:
        return f"usuario_{id_usuario}"

    usuario= getattr(main_window, "usuario_actual", None)

    return f"usuario_{usuario}" if usuario else "usuario_default"


def _ruta_bd_local(main_window):

    return os.path.join(_carpeta_local(), f"{_clave_docente(main_window)}.db")


def _conexion_local(main_window):

    conn= sqlite3.connect(_ruta_bd_local(main_window))
    conn.row_factory= sqlite3.Row

    _crear_tablas_locales(conn)
    _agregar_columnas_faltantes(conn)

    conn.commit()

    return conn


def _crear_tablas_locales(conn):

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

    conn.execute("""CREATE TABLE IF NOT EXISTS colores_materias_local (
        clave TEXT PRIMARY KEY,
        color TEXT,
        color_hv TEXT,
        actualizado TEXT
    )""")

    #si ya vio el tutorial de primer uso: es una preferencia de ESTE equipo y de ESTE docente, igual que
    #el resto de esta base, por eso vive acá y no en acadexi.db (ver tutoriales.py)
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


#Las bases locales creadas antes de que existieran estas columnas no las tienen: se les agregan.
def _agregar_columnas_faltantes(conn):

    filas= conn.execute("PRAGMA table_info(estudiantes_local)").fetchall()
    columnas_existentes= {fila["name"] for fila in filas}

    for columna, tipo in (("matricula", "TEXT"), ("seccion_id", "INTEGER"), ("estado", "TEXT"),
                          ("especialidad_id", "INTEGER"), ("carrera_id", "INTEGER")):

        if columna not in columnas_existentes:
            conn.execute(f"ALTER TABLE estudiantes_local ADD COLUMN {columna} {tipo}")


# -----------------------------------------
# estudiantes: retoques del docente
# -----------------------------------------
def obtener_override_estudiante(main_window, estudiante_id):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("SELECT * FROM estudiantes_local WHERE estudiante_id=?", (estudiante_id,))
    fila= c.fetchone()
    conn.close()

    return dict(fila) if fila else None


#Devuelve {estudiante_id: {campo: valor, ...}} con todos los retoques del docente.
def listar_overrides_estudiantes(main_window):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("SELECT * FROM estudiantes_local")
    filas= c.fetchall()
    conn.close()

    return {fila["estudiante_id"]: dict(fila) for fila in filas}


#campos es un diccionario con cualquiera de CAMPOS_OVERRIDE_ESTUDIANTE. Los que no vengan quedan como
#estaban, o vacíos si es la primera vez. La matrícula NUNCA la cambia el docente (es un dato
#institucional): aunque llegue en campos, se ignora y se conserva la que ya hubiera, y si no había
#ninguna queda vacía, así que se sigue mostrando la oficial (ver aplicar_override).
def guardar_override_estudiante(main_window, estudiante_id, campos):

    conn= _conexion_local(main_window)
    c= conn.cursor()

    c.execute("SELECT * FROM estudiantes_local WHERE estudiante_id=?", (estudiante_id,))
    fila= c.fetchone()
    existente= dict(fila) if fila else {}

    valores= {campo: campos.get(campo, existente.get(campo, "")) for campo in CAMPOS_OVERRIDE_ESTUDIANTE}
    valores["matricula"]= existente.get("matricula", "")
    valores["seccion_id"]= valores["seccion_id"] or None
    valores["especialidad_id"]= valores["especialidad_id"] or None
    valores["carrera_id"]= valores["carrera_id"] or None
    valores["estudiante_id"]= estudiante_id
    valores["actualizado"]= _ahora()

    #se reemplaza la fila completa: arriba ya se armaron todas las columnas
    c.execute("""INSERT OR REPLACE INTO estudiantes_local
                 (estudiante_id, matricula, nombre, apellidos, sexo, fecha_nacimiento, documento, direccion,
                  telefono, correo, tutor, tutor2, seccion_id, estado, foto, especialidad_id, carrera_id,
                  actualizado)
                 VALUES (:estudiante_id, :matricula, :nombre, :apellidos, :sexo, :fecha_nacimiento,
                         :documento, :direccion, :telefono, :correo, :tutor, :tutor2, :seccion_id,
                         :estado, :foto, :especialidad_id, :carrera_id, :actualizado)""", valores)

    conn.commit()
    conn.close()


def eliminar_override_estudiante(main_window, estudiante_id):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("DELETE FROM estudiantes_local WHERE estudiante_id=?", (estudiante_id,))
    conn.commit()
    conn.close()


#Combina una fila de la base institucional (sqlite3.Row o dict) con el retoque del docente, si hay.
#El retoque gana en todos los campos (incluidos sección y estado) MENOS la matrícula, que siempre se
#muestra como la tiene Dirección. Lo que el docente no retocó sigue mostrando el dato institucional.
def aplicar_override(fila_institucional, override):

    combinado= dict(fila_institucional)

    if not override:
        return combinado

    for campo in CAMPOS_OVERRIDE_ESTUDIANTE:

        valor_local= override.get(campo)

        if valor_local:
            combinado[campo]= valor_local

    return combinado


# -----------------------------------------
# colores de las materias en el horario
# -----------------------------------------
#Solo para este docente y en este equipo: no cambia el color que ven los otros roles ni otros
#profesores. La clave es el mismo texto que se usa para pintar los chips del calendario: el nombre
#de la materia, o la nota en las clases locales que no tienen materia.
#Devuelve {clave: (color, color_hv)}.
def obtener_colores_materias_local(main_window):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("SELECT clave, color, color_hv FROM colores_materias_local")
    filas= c.fetchall()
    conn.close()

    return {fila["clave"]: (fila["color"], fila["color_hv"]) for fila in filas}


def guardar_color_materia_local(main_window, clave, color, color_hv):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("""INSERT INTO colores_materias_local (clave, color, color_hv, actualizado)
                 VALUES (?,?,?,?)
                 ON CONFLICT(clave) DO UPDATE SET
                    color=excluded.color, color_hv=excluded.color_hv, actualizado=excluded.actualizado""",
              (clave, color, color_hv, _ahora()))
    conn.commit()
    conn.close()


#Quita el color personalizado: la materia vuelve a su color automático.
def eliminar_color_materia_local(main_window, clave):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("DELETE FROM colores_materias_local WHERE clave=?", (clave,))
    conn.commit()
    conn.close()


# -----------------------------------------
# horario personal del docente
# -----------------------------------------
#No toca la tabla horarios de la base institucional.
def listar_horario_local(main_window):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("SELECT * FROM horario_local ORDER BY dia, hora_inicio")
    filas= [dict(fila) for fila in c.fetchall()]
    conn.close()

    return filas


def obtener_entrada_horario_local(main_window, id_local):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("SELECT * FROM horario_local WHERE id=?", (id_local,))
    fila= c.fetchone()
    conn.close()

    return dict(fila) if fila else None


#Si id_edicion es None se crea una entrada nueva; si trae un id, se actualiza esa.
def guardar_entrada_horario_local(main_window, id_edicion, materia_id, seccion_id, dia,
                                  hora_inicio, hora_fin, aula_texto, notas):

    conn= _conexion_local(main_window)
    c= conn.cursor()

    if id_edicion is None:
        c.execute("""INSERT INTO horario_local
                     (materia_id, seccion_id, dia, hora_inicio, hora_fin, aula_texto, notas, actualizado)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (materia_id, seccion_id, dia, hora_inicio, hora_fin, aula_texto, notas, _ahora()))
    else:
        c.execute("""UPDATE horario_local SET materia_id=?, seccion_id=?, dia=?, hora_inicio=?,
                     hora_fin=?, aula_texto=?, notas=?, actualizado=? WHERE id=?""",
                  (materia_id, seccion_id, dia, hora_inicio, hora_fin, aula_texto, notas, _ahora(), id_edicion))

    conn.commit()
    conn.close()


def eliminar_entrada_horario_local(main_window, id_local):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("DELETE FROM horario_local WHERE id=?", (id_local,))
    conn.commit()
    conn.close()


# -----------------------------------------
# tutorial de primer uso del Modo Docente
# -----------------------------------------
#Es independiente del tutorial general (ver tutoriales.py). "Visto" es por equipo y por docente,
#igual que el resto de esta base local.
def tutorial_docente_visto(main_window):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("SELECT visto FROM tutorial_docente_local WHERE id=1")
    fila= c.fetchone()
    conn.close()

    return bool(fila["visto"]) if fila else False


def marcar_tutorial_docente_visto(main_window, visto=True):

    conn= _conexion_local(main_window)
    c= conn.cursor()
    c.execute("""INSERT INTO tutorial_docente_local (id, visto, actualizado) VALUES (1, ?, ?)
                 ON CONFLICT(id) DO UPDATE SET visto=excluded.visto, actualizado=excluded.actualizado""",
              (1 if visto else 0, _ahora()))
    conn.commit()
    conn.close()
