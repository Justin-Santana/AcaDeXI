"""Base de datos propia de la edición AcaDeXI Single Teacher.

Decisión aprobada (Pieza 3(b) del prompt de arquitectura de las 4
ediciones): NO reutiliza bd.py completo. bd.py trae todo el aparato
institucional (auditoría multiusuario, matrícula masiva, facultades,
Personal/Profesores plural) que un docente independiente no necesita y que
sería peso muerto a mantener sincronizado en cada fix futuro (el mismo
problema que ya pasó con la nota mínima duplicada en 6 archivos).

En su lugar, promueve el PATRÓN de datos_locales_docente.py (SQLite propio,
por usuario, en la carpeta de datos de la app) a FUENTE DE VERDAD ÚNICA:
aquí no hay overrides porque no hay nada institucional debajo que
respetar -el docente escribe directo.

Módulos con tabla propia aquí (aprobados en la propuesta):
  Estudiantes, Materias/Secciones, Calificaciones, Calificaciones Técnicas
  (categoria libre dentro de calificaciones), Asistencia, Horario, Banco de
  Tareas, Observaciones, Secuencias Didácticas.
Excluidos (no tienen sentido para un docente independiente, ver propuesta):
  Personal/Profesores múltiples, Auditoría multiusuario, matrícula masiva
  institucional, Dashboard cross-institución, Politécnico/Universidad como
  nivel institucional (facultades, pasantías).

Reutiliza el mismo fix de nota mínima por nivel educativo (Primaria/
Secundaria) que Full Institutional: la columna nivel_educativo vive en
`secciones` aquí (no en una tabla `grados` aparte, porque Single Teacher no
tiene jerarquía de grados institucional: cada "sección" ES el curso del
docente, ej. "8vo A - Matemáticas 2026").
"""
import os
import sqlite3

from src.nucleo.bd import get_app_data_dir


def _ruta_bd(main_window=None):
    """Un solo docente, un solo archivo: a diferencia de
    datos_locales_docente.py (que separa por usuario porque varios docentes
    pueden compartir un equipo institucional), Single Teacher asume que
    quien instaló esta copia es el único dueño del equipo -sigue viviendo en
    una subcarpeta propia por prolijidad y para no chocar nunca con
    acadexi.db si alguna vez conviven en el mismo %APPDATA%\\AcaDeXI en un
    equipo de pruebas."""
    carpeta = os.path.join(get_app_data_dir(), "single_teacher")
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, "acadexi_single_teacher.db")


DB_PATH = _ruta_bd()

# Bandera espejo de bd.SANDBOX_TUTORIAL_ACTIVO (ver tutoriales.py, sandbox
# del Tutorial Detallado): mientras esté en True, DB_PATH apunta a una
# copia de práctica desechable, no al archivo real del docente.
SANDBOX_TUTORIAL_ACTIVO = False


def get_connection(main_window=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _inicializar(conn)
    return conn


def _inicializar(conn):
    c = conn.cursor()
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

    # "secciones" es aquí el curso completo del docente (no hay grados
    # institucionales por encima): nombre libre, con su propio
    # nivel_educativo para que aplique el mismo fix de nota mínima por
    # nivel que ya usa Full Institutional (ver bd.resolver_nota_minima
    # equivalente, a implementar en configuracion.py cuando se conecte este
    # módulo a la UI).
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

    # Secuencias didácticas (planificación MINERD). Aquí no hay competencias
    # específicas/indicadores catalogados como en la edición institucional,
    # así que se escriben como texto (una por línea) dentro de la secuencia.
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

    conn.commit()


def wizard_completado(main_window=None):
    conn = get_connection(main_window)
    c = conn.cursor()
    c.execute("SELECT wizard_completado FROM configuracion WHERE id=1")
    f = c.fetchone()
    conn.close()
    return bool(f and f["wizard_completado"])


def marcar_wizard_completado(main_window=None, nombre_docente=""):
    conn = get_connection(main_window)
    c = conn.cursor()
    c.execute("UPDATE configuracion SET wizard_completado=1, nombre_docente=? WHERE id=1", (nombre_docente,))
    conn.commit()
    conn.close()


def tutorial_visto(main_window=None):
    """Persistencia del tutorial de primer uso de Single Teacher (ver
    tutoriales.py, tipo="single_teacher"). Vive aquí -no en la tabla
    `usuarios` de bd.py, que Single Teacher ni siquiera tiene- porque esta
    edición no tiene sesiones multiusuario: hay un solo docente, un solo
    archivo, igual que el resto de esta configuración."""
    conn = get_connection(main_window)
    c = conn.cursor()
    c.execute("SELECT tutorial_visto FROM configuracion WHERE id=1")
    f = c.fetchone()
    conn.close()
    return bool(f and f["tutorial_visto"])


def marcar_tutorial_visto(main_window=None, visto=True):
    conn = get_connection(main_window)
    c = conn.cursor()
    c.execute("UPDATE configuracion SET tutorial_visto=? WHERE id=1", (1 if visto else 0,))
    conn.commit()
    conn.close()
