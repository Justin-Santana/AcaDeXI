# -----------------------------------------
# base de datos de la edición Single Teacher
# No reutiliza bd.py completo: bd.py trae todo el aparato institucional (auditoría multiusuario,
# matrícula masiva, facultades, Personal y Profesores en plural) que un docente independiente no
# necesita, y mantenerlo sincronizado en cada arreglo es peso muerto.
# Acá el docente escribe directo: no hay nada institucional debajo que respetar, así que no hay
# overrides como en datos_locales_docente.py. Tablas propias: estudiantes, materias, secciones,
# calificaciones, asistencia, horario, tareas y observaciones.
# -----------------------------------------
import os
import sqlite3

from src.nucleo.bd import get_app_data_dir


# un solo docente, un solo archivo. Vive en su propia subcarpeta para no chocar nunca con
# acadexi.db si las dos ediciones conviven en el mismo %APPDATA%\AcaDeXI.
def _ruta_bd(main_window=None):

    carpeta= os.path.join(get_app_data_dir(), "single_teacher")
    os.makedirs(carpeta, exist_ok=True)

    return os.path.join(carpeta, "acadexi_single_teacher.db")


DB_PATH= _ruta_bd()

#bandera espejo de bd.SANDBOX_TUTORIAL_ACTIVO: mientras esté en True, DB_PATH apunta a una copia de
#práctica del tutorial y no al archivo real del docente.
SANDBOX_TUTORIAL_ACTIVO= False


# -----------------------------------------
# conexión y creación de las tablas
# -----------------------------------------
def obtener_conexion(main_window=None):

    conn= sqlite3.connect(DB_PATH)
    conn.row_factory= sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _inicializar(conn)

    return conn


def _inicializar(conn):

    c= conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS configuracion (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        nombre_docente TEXT,
        wizard_completado INTEGER DEFAULT 0,
        tutorial_visto INTEGER DEFAULT 0,
        nota_minima_primaria REAL,
        nota_minima_secundaria REAL,
        sistema_calificacion TEXT DEFAULT 'Numérico (Personalizado)'
    )""")
    c.execute("SELECT COUNT(*) as n FROM configuracion")
    if c.fetchone()["n"] == 0:
        c.execute("INSERT INTO configuracion (id) VALUES (1)")

    #"secciones" acá es el curso completo del docente, con su nivel_educativo para que aplique el
    #mismo arreglo de nota mínima por nivel que la edición completa (no hay grados por encima).
    c.execute("""CREATE TABLE IF NOT EXISTS secciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        nivel_educativo TEXT,
        anio_academico TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS materias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        es_tecnica INTEGER DEFAULT 0,
        estado TEXT DEFAULT 'Activa'
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS estudiantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        apellidos TEXT,
        sexo TEXT,
        fecha_nacimiento TEXT,
        documento TEXT,
        direccion TEXT,
        telefono TEXT,
        correo TEXT,
        tutor TEXT,
        tutor2 TEXT,
        foto TEXT,
        seccion_id INTEGER,
        estado TEXT DEFAULT 'Activo',
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS periodos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        anio_academico TEXT,
        orden INTEGER DEFAULT 1
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS calificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        materia_id INTEGER,
        periodo_id INTEGER,
        categoria TEXT,
        descripcion TEXT,
        valor REAL,
        peso REAL DEFAULT 0,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS asistencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        seccion_id INTEGER,
        materia_id INTEGER,
        fecha TEXT,
        estado TEXT DEFAULT 'Presente',
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS horario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        materia_id INTEGER,
        seccion_id INTEGER,
        dia TEXT,
        hora_inicio TEXT,
        hora_fin TEXT,
        aula_texto TEXT,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE SET NULL,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS tareas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        materia_id INTEGER,
        seccion_id INTEGER,
        periodo_id INTEGER,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        fecha_entrega TEXT,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE CASCADE,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS observaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        fecha TEXT,
        tipo TEXT,
        descripcion TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE
    )""")

    conn.commit()


# -----------------------------------------
# wizard y tutorial de primer uso
# esta edición no tiene usuarios ni sesiones: un solo docente, un solo archivo, así que estas dos
# banderas viven en la tabla configuracion y no en la tabla usuarios de bd.py.
# -----------------------------------------
def wizard_completado(main_window=None):

    conn= obtener_conexion(main_window)
    c= conn.cursor()
    c.execute("SELECT wizard_completado FROM configuracion WHERE id=1")
    fila= c.fetchone()
    conn.close()

    return bool(fila and fila["wizard_completado"])


def marcar_wizard_completado(main_window=None, nombre_docente=""):

    conn= obtener_conexion(main_window)
    c= conn.cursor()
    c.execute("UPDATE configuracion SET wizard_completado=1, nombre_docente=? WHERE id=1", (nombre_docente,))
    conn.commit()
    conn.close()


def tutorial_visto(main_window=None):

    conn= obtener_conexion(main_window)
    c= conn.cursor()
    c.execute("SELECT tutorial_visto FROM configuracion WHERE id=1")
    fila= c.fetchone()
    conn.close()

    return bool(fila and fila["tutorial_visto"])


def marcar_tutorial_visto(main_window=None, visto=True):

    conn= obtener_conexion(main_window)
    c= conn.cursor()
    c.execute("UPDATE configuracion SET tutorial_visto=? WHERE id=1", (1 if visto else 0,))
    conn.commit()
    conn.close()
