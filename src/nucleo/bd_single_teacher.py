#Base de datos de la edición Single Teacher. Un solo docente, un solo archivo SQLite.
#
#No reutiliza bd.py: ese trae todo lo institucional (auditoría de varios usuarios, matrícula masiva,
#facultades, varios profesores) que un docente independiente no necesita y que habría que mantener
#al día en cada arreglo. Acá no hay "overrides" como en datos_locales_docente.py porque no hay datos
#institucionales debajo: el docente escribe directo en su base.
#
#Lo que se guarda: estudiantes, materias y secciones, calificaciones (las técnicas son una categoría
#libre dentro de calificaciones), asistencia, horario, banco de tareas, observaciones y secuencias
#didácticas. Lo institucional (varios profesores, auditoría, dashboard, politécnico, universidad)
#no existe en esta edición.
#
#Acá "secciones" es el curso completo del docente (por ejemplo "8vo A - Matemáticas 2026"), no hay
#grados institucionales por encima. Por eso nivel_educativo vive en secciones y no en una tabla
#grados aparte: así sigue funcionando la nota mínima por nivel (Primaria o Secundaria).
import os
import sqlite3

from src.nucleo.bd import get_app_data_dir


def _ruta_bd():

    #La carpeta va aparte para no chocar con acadexi.db si las dos ediciones conviven en un equipo
    #de pruebas. No se separa por usuario: quien instaló esta copia es el único dueño del equipo.
    carpeta= os.path.join(get_app_data_dir(), "single_teacher")
    os.makedirs(carpeta, exist_ok=True)

    return os.path.join(carpeta, "acadexi_single_teacher.db")


DB_PATH= _ruta_bd()

#Igual que SANDBOX_TUTORIAL_ACTIVO de bd.py (ver tutoriales.py): mientras esté en True, DB_PATH apunta a
#una copia de práctica y no al archivo real del docente.
SANDBOX_TUTORIAL_ACTIVO= False


#main_window no se usa acá, pero se recibe porque así la llama todo el resto del código.
def obtener_conexion(main_window=None):

    conn= sqlite3.connect(DB_PATH)
    conn.row_factory= sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _inicializar(conn)

    return conn


# -----------------------------------------
# crear las tablas
# -----------------------------------------
def _inicializar(conn):

    c= conn.cursor()

    _crear_configuracion(c)
    _crear_tablas_del_curso(c)
    _crear_tablas_de_secuencias(c)

    conn.commit()


def _crear_configuracion(c):

    c.execute("""CREATE TABLE IF NOT EXISTS configuracion (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        nombre_docente TEXT,
        wizard_completado INTEGER DEFAULT 0,
        tutorial_visto INTEGER DEFAULT 0,
        nota_minima_primaria REAL,
        nota_minima_secundaria REAL,
        sistema_calificacion TEXT DEFAULT 'Numérico (Personalizado)'
    )""")

    #la configuración es una sola fila, con id 1
    c.execute("SELECT COUNT(*) as n FROM configuracion")

    if c.fetchone()["n"] == 0:
        c.execute("INSERT INTO configuracion (id) VALUES (1)")


def _crear_tablas_del_curso(c):

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


#Planificación de unidades (formato MINERD). Acá no hay catálogo de competencias ni de indicadores
#como en la edición institucional, así que se escriben como texto, una por línea, dentro de la
#propia secuencia.
def _crear_tablas_de_secuencias(c):

    c.execute("""CREATE TABLE IF NOT EXISTS secuencias_didacticas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        materia_id INTEGER,
        seccion_id INTEGER,
        periodo_id INTEGER,
        anio_academico TEXT DEFAULT '',
        eje_transversal TEXT DEFAULT '',
        situacion_aprendizaje TEXT DEFAULT '',
        competencias_fundamentales TEXT DEFAULT '',
        competencias_especificas TEXT DEFAULT '',
        indicadores_logro TEXT DEFAULT '',
        contenido_conceptos TEXT DEFAULT '',
        contenido_procedimientos TEXT DEFAULT '',
        contenido_actitudes TEXT DEFAULT '',
        estrategia TEXT DEFAULT '',
        estado TEXT DEFAULT 'Borrador',
        fecha_inicio TEXT,
        fecha_fin TEXT,
        creado TEXT,
        actualizado TEXT,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE SET NULL,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS secuencia_sesiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        secuencia_id INTEGER NOT NULL,
        orden INTEGER DEFAULT 1,
        fecha TEXT,
        momento TEXT DEFAULT 'Desarrollo',
        actividad TEXT DEFAULT '',
        evidencia TEXT DEFAULT '',
        instrumento TEXT DEFAULT '',
        metacognicion TEXT DEFAULT '',
        recursos TEXT DEFAULT '',
        duracion_min INTEGER DEFAULT 0,
        realizada INTEGER DEFAULT 0,
        FOREIGN KEY (secuencia_id) REFERENCES secuencias_didacticas(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS secuencia_tarea (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        secuencia_id INTEGER NOT NULL,
        tarea_id INTEGER NOT NULL,
        FOREIGN KEY (secuencia_id) REFERENCES secuencias_didacticas(id) ON DELETE CASCADE,
        FOREIGN KEY (tarea_id) REFERENCES tareas(id) ON DELETE CASCADE,
        UNIQUE(secuencia_id, tarea_id)
    )""")


# -----------------------------------------
# asistente de primer uso y tutorial
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


#Si el docente ya vio el tutorial de primer uso (ver tutoriales.py, tipo "single_teacher"). Se guarda
#acá y no en la tabla usuarios de bd.py porque esta edición no tiene usuarios: hay un solo docente.
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
