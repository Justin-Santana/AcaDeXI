import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_ruta_wal_configurada= None

# -----------------------------------------
# sandbox del tutorial detallado (ver tutoriales.py)
# -----------------------------------------
#mientras está activo, RUTA_BD apunta temporalmente a una copia desechable del archivo
#real (para que los pasos "haz esto de verdad" del tutorial no toquen la
#base institucional). Esta bandera existe solo para que operaciones que
#el usuario podría disparar manualmente en paralelo (backup, subir/bajar
#de Sincronización) se nieguen con un aviso claro en vez de terminar
#respaldando o sincronizando por error la copia de práctica.
SANDBOX_TUTORIAL_ACTIVO= False

#En República Dominicana el MINERD no publica un criterio único de
#numeración para el "libro de clases" de cada aula -cada centro define el
#suyo internamente-, así que en vez de imponer un solo criterio fijo,
#AcaDeXI deja elegir entre las prácticas más comunes documentadas (ver
#informe adjunto): orden alfabético (por Apellidos o por Nombre, según
#convenga a la institución), orden de ingreso/matrícula, o manejo
#totalmente manual (para el centro que ya trae su propia numeración de
#otro sistema y no quiere que AcaDeXI se la reordene).
CRITERIO_APELLIDOS_NOMBRE= "Apellidos y Nombre"

CRITERIO_NOMBRE_APELLIDOS= "Nombre y Apellidos"

CRITERIO_ORDEN_MATRICULA= "Orden de Matrícula (fecha de ingreso)"

CRITERIO_MANUAL= "Manual (no reordenar automáticamente)"

CRITERIOS_NUMERO_LISTA= [
    CRITERIO_APELLIDOS_NOMBRE,
    CRITERIO_NOMBRE_APELLIDOS,
    CRITERIO_ORDEN_MATRICULA,
    CRITERIO_MANUAL,
]

DESCRIPCION_CRITERIO_NUMERO_LISTA= {
    CRITERIO_APELLIDOS_NOMBRE: "Alfabético por Primer Apellido y luego Nombre (la convención más común "
                                "en la región, la misma del Libro de Clases).",
    CRITERIO_NOMBRE_APELLIDOS: "Alfabético por Primer Nombre y luego Apellidos.",
    CRITERIO_ORDEN_MATRICULA: "Según el orden en que cada estudiante fue registrado en el sistema "
                               "(el ID interno, que solo crece), sin importar el alfabeto.",
    CRITERIO_MANUAL: "AcaDeXI no reordena nada automáticamente; el número de cada estudiante solo "
                      "cambia si tú lo editas a mano.",
}

MAX_INTENTOS_LOGIN= 5

MINUTOS_BLOQUEO_LOGIN= 15

try:

    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHash
    _ph= PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
    _ARGON2_OK= True
except Exception:
    _ARGON2_OK= False


# -----------------------------------------
# rutas de la aplicación
# -----------------------------------------
def obtener_carpeta_datos():

    if sys.platform == "win32":
        base= os.environ.get("APPDATA") or os.environ.get("USERPROFILE")
        if not base:
            try:

                base= str(Path.home())
            except Exception:
                base= None
        if not base:
            import tempfile
            base= tempfile.gettempdir()
    elif sys.platform == "darwin":
        try:

            base= str(Path.home() / "Library" / "Application Support")
        except Exception:
            import tempfile
            base= tempfile.gettempdir()
    else:
        base= os.environ.get("XDG_DATA_HOME")
        if not base:
            try:

                base= str(Path.home() / ".local" / "share")
            except Exception:
                import tempfile
                base= tempfile.gettempdir()
    ruta= os.path.join(base, "AcaDeXI")
    os.makedirs(ruta, exist_ok=True)
    os.makedirs(os.path.join(ruta, "logos"), exist_ok=True)
    os.makedirs(os.path.join(ruta, "fotos"), exist_ok=True)
    os.makedirs(os.path.join(ruta, "backups"), exist_ok=True)
    return ruta


RUTA_BD= os.path.join(obtener_carpeta_datos(), "acadexi.db")


# -----------------------------------------
# BD base institucional
# -----------------------------------------
#copia curada por el Director, SIN sus datos personales, usada como punto de partida para Docentes/Personal (se
#distribuye embebida en el perfil .acdx de cada usuario, ver perfil.py).
RUTA_BD_BASE= os.path.join(obtener_carpeta_datos(), "acadexi_base.db")


def existe_bd_base():

    return os.path.exists(RUTA_BD_BASE)


#Copia la BD actualmente en uso como 'BD Base Institucional'. El Administrador
#debe ejecutar esto SOLO después de asegurarse de que la BD no contiene datos
#personales que no quiera distribuir (o usar una BD dedicada para este fin).
def guardar_bd_base_desde_actual():

    import shutil
    shutil.copy2(RUTA_BD, RUTA_BD_BASE)
    return RUTA_BD_BASE


def eliminar_bd_base():

    if os.path.exists(RUTA_BD_BASE):
        os.remove(RUTA_BD_BASE)


def info_bd_base():

    if not existe_bd_base():
        return None
    return {
        "ruta": RUTA_BD_BASE,
        "tamano_kb": round(os.path.getsize(RUTA_BD_BASE) / 1024, 1),
        "modificado": datetime.fromtimestamp(os.path.getmtime(RUTA_BD_BASE)).strftime("%Y-%m-%d %H:%M:%S"),
    }


def obtener_conexion():

    global _ruta_wal_configurada
    conn= sqlite3.connect(RUTA_BD)
    conn.row_factory= sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = 10000")
    conn.execute("PRAGMA synchronous = NORMAL")
    #journal_mode es una propiedad persistente del archivo. Repetir la
    #negociación WAL en cada conexión fuerza E/S y puede esperar bloqueos;
    #basta una vez por cada ruta de BD usada (la ruta puede cambiar en el
    #sandbox del tutorial).
    if _ruta_wal_configurada != RUTA_BD:
        conn.execute("PRAGMA journal_mode = WAL")
        _ruta_wal_configurada= RUTA_BD
    return conn


#(nivel, ciclo) del Grado/Curso al que pertenece `seccion_id`.
def resolver_nivel_academico_de_seccion(seccion_id):

    if seccion_id is None:
        return None, None
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT grados.nivel_educativo as nivel, grados.ciclo_secundaria as ciclo
                 FROM secciones LEFT JOIN grados ON secciones.grado_id = grados.id
                 WHERE secciones.id=?""", (seccion_id,))
    fila= c.fetchone()
    conn.close()
    if not fila:
        return None, None
    return fila["nivel"], fila["ciclo"]


#(nivel, ciclo) real de un estudiante: 'Universidad' si tiene
#`carrera_id` asignada (los estudiantes universitarios se matriculan por
#Carrera, no por Sección -dato que ya existía-); si no, el nivel/ciclo de
#su Grado vía Sección; (None, None) si no tiene ninguna de las dos
#relaciones todavía (estudiante recién creado sin matricular).
def resolver_nivel_academico_estudiante(estudiante_id):

    if estudiante_id is None:
        return None, None
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT estudiantes.carrera_id as carrera_id, estudiantes.seccion_id as seccion_id,
                 grados.nivel_educativo as nivel, grados.ciclo_secundaria as ciclo
                 FROM estudiantes
                 LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                 LEFT JOIN grados ON secciones.grado_id = grados.id
                 WHERE estudiantes.id=?""", (estudiante_id,))
    fila= c.fetchone()
    conn.close()
    if not fila:
        return None, None
    if fila["carrera_id"] is not None:
        return "Universidad", None
    return fila["nivel"], fila["ciclo"]


# -----------------------------------------
# hashing de contraseñas - argon2id
# -----------------------------------------
def hash_password(password: str) -> str:

    if _ARGON2_OK:
        return _ph.hash(password)
    import hashlib
    salt= os.urandom(16).hex()
    digest= hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000).hex()
    return f"pbkdf2${salt}${digest}"


def verificar_contrasena(password: str, hashed: str) -> bool:

    if hashed.startswith("pbkdf2$"):
        import hashlib
        import hmac
        _, salt, digest= hashed.split("$")
        nuevo= hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000).hex()
        #hmac.compare_digest en vez de == : una comparación normal de strings
        #se detiene en el primer carácter distinto, así que el tiempo de
        #respuesta varía según cuántos caracteres iniciales acertó el
        #atacante (timing attack). compare_digest siempre tarda lo mismo,
        #sin importar en qué posición difieren los hashes.
        return hmac.compare_digest(nuevo, digest)
    if not _ARGON2_OK:
        return False
    try:

        return _ph.verify(hashed, password)
    except Exception:
        return False


# -----------------------------------------
# número de lista (numeración de estudiantes dentro de su sección)
# -----------------------------------------

#Lee el criterio de numeración configurado (ver CRITERIOS_NUMERO_LISTA).
#Devuelve CRITERIO_APELLIDOS_NOMBRE si la instalación aún no tiene nada
#guardado (valor por defecto de la columna) o si el valor guardado ya no
#es válido, por ejemplo tras restaurar un backup viejo.
def obtener_criterio_numero_lista():

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT criterio_numero_lista FROM configuracion WHERE id=1")
    fila= c.fetchone()
    conn.close()
    criterio= fila["criterio_numero_lista"] if fila else None
    return criterio if criterio in CRITERIOS_NUMERO_LISTA else CRITERIO_APELLIDOS_NOMBRE


#Fragmento ORDER BY (sin la palabra ORDER BY) para el criterio dado.
def _orden_sql_para_criterio(criterio):

    if criterio == CRITERIO_NOMBRE_APELLIDOS:
        return "nombre COLLATE NOCASE, apellidos COLLATE NOCASE"
    if criterio == CRITERIO_ORDEN_MATRICULA:
        return "id"
    #CRITERIO_APELLIDOS_NOMBRE es el valor por defecto y también el
    #respaldo para cualquier valor inesperado (nunca se debería llegar
    #aquí con CRITERIO_MANUAL, ese caso se filtra antes en el llamador).
    return "apellidos COLLATE NOCASE, nombre COLLATE NOCASE"


#Reasigna 1, 2, 3... a los estudiantes ACTIVOS de `seccion_id`, en el
#orden que marque `criterio` (o el configurado globalmente si no se
#especifica). Los estudiantes en estado 'Inactivo' se dejan con su
#numero_lista tal cual quedó (no se elimina su lugar de golpe: si se
#reactivan más tarde, con volver a recalcular listo), pero NO cuentan
#para asignar los números 1..n a los activos, que es lo que de verdad se
#usa a diario (pasar lista, exámenes, etc.).
#
#No hace nada si `seccion_id` es None (estudiante sin sección asignada
#todavía, p.ej. antes de matricularlo formalmente) ni si el criterio
#vigente es Manual.
def recalcular_numeros_lista(seccion_id, criterio=None):

    if not seccion_id:
        return
    criterio= criterio or obtener_criterio_numero_lista()
    if criterio == CRITERIO_MANUAL:
        return
    orden_sql= _orden_sql_para_criterio(criterio)
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute(f"""SELECT id FROM estudiantes
                  WHERE seccion_id=? AND estado='Activo'
                  ORDER BY {orden_sql}""", (seccion_id,))
    ids_en_orden= [fila["id"] for fila in c.fetchall()]
    for numero, id_est in enumerate(ids_en_orden, start=1):
        c.execute("UPDATE estudiantes SET numero_lista=? WHERE id=?", (numero, id_est))
    conn.commit()
    conn.close()


#(es_politecnico, es_universidad, ambos_a_la_vez) para `main_window`,
#con el mismo criterio usado en todo el resto de la app (ver
#estudiantes.py, banco_tareas.py, etc.): "Personalizado" puede tener
#Politécnico y Universidad activos a la vez, en cuyo caso ninguno de los
#dos es "obligatorio" por sí solo -es el único caso en que ambos flags
#salen True.
def _flags_tipo_institucion(main_window):

    try:

        tipo, personalizados= main_window._tipo_institucion()
    except Exception:
        return False, False, False
    es_poli= tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)
    es_uni= tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)
    ambos= tipo == "Personalizado" and "Politécnico" in personalizados and "Universidad" in personalizados
    return es_poli, es_uni, ambos


#True si corresponde MOSTRAR la columna "No." (Número de Lista) con
#los filtros actualmente elegidos, en cualquier pantalla que liste
#estudiantes de una sección (Asistencia, Banco de Tareas, Observaciones,
#Politécnico...).
#
#El número de lista es "1..n DENTRO de una sección" -mezclar
#estudiantes de varias secciones (o de varias áreas técnicas/carreras
#dentro de la misma sección, en un Politécnico/Universidad) volvería la
#columna confusa, no un verdadero orden. Por eso, antes de mostrarla, se
#exige haber filtrado hasta el nivel más específico que aplique:
#- Sección concreta SIEMPRE (`seccion_id` no puede ser None/"Todas").
#- Área Técnica concreta, SI la institución es Politécnico (o
#Personalizado con Politécnico activo) -salvo que también tenga
#Universidad activa a la vez, caso en que no se exige ninguna de las
#dos (mismo criterio que el resto de la app, ver _flags_tipo_institucion).
#- Carrera concreta, SI la institución es Universidad, con la misma
#excepción de arriba.
def mostrar_columna_numero_lista(main_window, seccion_id, especialidad_id=None, carrera_id=None):

    if seccion_id is None:
        return False
    es_poli, es_uni, ambos= _flags_tipo_institucion(main_window)
    if ambos:
        return True
    if es_poli and especialidad_id is None:
        return False
    if es_uni and carrera_id is None:
        return False
    return True


#Aplica recalcular_numeros_lista() a cada sección que tenga al menos
#un estudiante. Se usa al cambiar el criterio global desde Configuración,
#o desde el botón "Recalcular Números de Lista" del módulo Estudiantes
#cuando se quiere refrescar todo de una vez (por ejemplo, tras importar
#varios estudiantes nuevos).
def recalcular_numeros_lista_todas_secciones(criterio=None):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT DISTINCT seccion_id FROM estudiantes WHERE seccion_id IS NOT NULL")
    secciones= [fila["seccion_id"] for fila in c.fetchall()]
    conn.close()
    for seccion_id in secciones:
        recalcular_numeros_lista(seccion_id, criterio=criterio)


# -----------------------------------------
# protección contra fuerza bruta en el login
# -----------------------------------------


#Revisa si la cuenta `username` está bloqueada por demasiados intentos
#fallidos. Devuelve (bloqueado: bool, minutos_restantes: int).
#Si el bloqueo ya venció, lo limpia (junto con el contador) para que la
#cuenta quede libre de nuevo sin que el usuario tenga que esperar a un
#login exitoso.
def verificar_bloqueo_login(username):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT bloqueado_hasta FROM usuarios WHERE username=?", (username,))
    fila= c.fetchone()
    if not fila or not fila["bloqueado_hasta"]:
        conn.close()
        return False, 0
    try:

        hasta= datetime.strptime(fila["bloqueado_hasta"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        conn.close()
        return False, 0
    ahora= datetime.now()
    if ahora >= hasta:
        c.execute("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return False, 0
    minutos_restantes= max(1, int((hasta - ahora).total_seconds() // 60) + 1)
    conn.close()
    return True, minutos_restantes


#Suma 1 al contador de intentos fallidos de `username`. Si llega a
#MAX_INTENTOS_LOGIN, bloquea la cuenta por MINUTOS_BLOQUEO_LOGIN minutos y
#reinicia el contador (para que, al desbloquearse, empiece de cero en vez
#de quedar ya cerca del límite). Devuelve (bloqueada_ahora: bool,
#intentos_restantes: int) para que login.py pueda avisar cuántos intentos
#le quedan antes de bloquearse.
def registrar_intento_fallido_login(username):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT intentos_fallidos FROM usuarios WHERE username=?", (username,))
    fila= c.fetchone()
    if not fila:
        conn.close()
        return False, MAX_INTENTOS_LOGIN
    nuevos_intentos= (fila["intentos_fallidos"] or 0) + 1
    if nuevos_intentos >= MAX_INTENTOS_LOGIN:
        bloqueado_hasta= (datetime.now() + timedelta(minutes=MINUTOS_BLOQUEO_LOGIN)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=? WHERE username=?",
                  (bloqueado_hasta, username))
        conn.commit()
        conn.close()
        return True, 0
    c.execute("UPDATE usuarios SET intentos_fallidos=? WHERE username=?", (nuevos_intentos, username))
    conn.commit()
    conn.close()
    return False, MAX_INTENTOS_LOGIN - nuevos_intentos


#Limpia el contador de intentos fallidos y cualquier bloqueo vigente de
#`username`. Se llama tras un login exitoso.
def resetear_intentos_login(username):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE username=?", (username,))
    conn.commit()
    conn.close()


# -----------------------------------------
# esquema de base de datos
# -----------------------------------------
#Verifica si una columna existe en una tabla.
def _columna_existe(conn, tabla, columna):

    c= conn.cursor()
    c.execute(f"PRAGMA table_info({tabla})")
    columnas= [fila["name"] for fila in c.fetchall()]
    return columna in columnas


#Agrega una columna a una tabla solo si no existe, e imprime en consola
#qué migración se aplicó (para que quede claro en el log de arranque).
def _agregar_columna_si_falta(conn, tabla, columna, definicion):

    if not _columna_existe(conn, tabla, columna):
        c= conn.cursor()
        c.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        print(f"✅ Migración: columna '{columna}' agregada a tabla '{tabla}'")


def inicializar_bd():

    conn= obtener_conexion()
    c= conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS configuracion (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        nombre_institucion TEXT,
        direccion TEXT,
        telefono TEXT,
        correo TEXT,
        sitio_web TEXT,
        logo_path TEXT,
        tipo_institucion TEXT DEFAULT 'Escuela',
        modulos_personalizados TEXT DEFAULT '',
        escala_maxima REAL DEFAULT 100,
        nota_minima REAL DEFAULT 70,
        nota_minima_primaria REAL,
        nota_minima_secundaria REAL,
        metodo_calculo TEXT DEFAULT 'Promedio Ponderado',
        sistema_calificacion TEXT DEFAULT 'Numérico (Personalizado)',
        anio_academico TEXT DEFAULT '2026-2027',
        division_periodo TEXT DEFAULT 'Trimestres',
        cantidad_periodos INTEGER DEFAULT 3,
        idioma TEXT DEFAULT 'Español',
        tema TEXT DEFAULT 'Colorful (Multicolor)',
        modo_oscuro INTEGER DEFAULT 1,
        requerir_login INTEGER DEFAULT 1,
        recordar_usuario INTEGER DEFAULT 0,
        ultimo_usuario TEXT DEFAULT '',
        login_translucido INTEGER DEFAULT 1,
        wizard_completado INTEGER DEFAULT 0,
        smtp_host TEXT DEFAULT '',
        smtp_puerto INTEGER DEFAULT 587,
        smtp_usuario TEXT DEFAULT '',
        smtp_password TEXT DEFAULT '',
        smtp_remitente TEXT DEFAULT '',
        smtp_seguridad TEXT DEFAULT 'TLS',
        firma_path TEXT DEFAULT '',
        pie_pagina TEXT DEFAULT '',
        auditoria_activa INTEGER DEFAULT 1,
        backup_modo TEXT DEFAULT 'Manual',
        backup_carpeta TEXT DEFAULT '',
        backup_ultima_fecha TEXT DEFAULT '',
        mostrar_backups_gerenciales INTEGER DEFAULT 0,
        valores_estados_asistencia TEXT DEFAULT ''
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        nombre_completo TEXT,
        rol TEXT NOT NULL,
        correo TEXT,
        telefono TEXT,
        foto TEXT,
        activo INTEGER DEFAULT 1,
        fecha_creacion TEXT
    )""")

    #Compatibilidad: AcaDeXI es un sistema exclusivo para PERSONAL de la
    #institución (Administrador/Director/Coordinador/Profesor/Administrativo);
    #el rol "Estudiante" ya no existe (ver permisos.py). Si alguna
    #instalación previa llegó a crear cuentas con ese rol, se reasignan aquí
    #a "Administrativo" (el rol de menor privilegio actual) en vez de dejar
    #cuentas huérfanas con un rol que el sistema ya no reconoce.
    c.execute("UPDATE usuarios SET rol='Administrativo' WHERE rol='Estudiante'")

    c.execute("""CREATE TABLE IF NOT EXISTS periodos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        anio_academico TEXT,
        orden INTEGER DEFAULT 1
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS especialidades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        codigo TEXT,
        color TEXT DEFAULT '#6366F1'
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS aulas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        tipo TEXT DEFAULT 'Aula',
        capacidad INTEGER DEFAULT 30,
        especialidad_id INTEGER,
        FOREIGN KEY (especialidad_id) REFERENCES especialidades(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS grados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        tipo TEXT DEFAULT 'Grado',
        facultad_id INTEGER,
        orden INTEGER DEFAULT 1,
        especialidad_id INTEGER,
        carrera_id INTEGER,
        FOREIGN KEY (especialidad_id) REFERENCES especialidades(id) ON DELETE SET NULL,
        FOREIGN KEY (carrera_id) REFERENCES carreras(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS profesores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        apellidos TEXT,
        especialidad TEXT,
        correo TEXT,
        telefono TEXT,
        horario_laboral TEXT,
        estado TEXT DEFAULT 'Activo',
        foto TEXT,
        usuario_id INTEGER,
        imparte_tecnico INTEGER DEFAULT 0,
        especialidad_tecnica_id INTEGER,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
        FOREIGN KEY (especialidad_tecnica_id) REFERENCES especialidades(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS secciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grado_id INTEGER,
        nombre TEXT NOT NULL,
        turno TEXT DEFAULT 'Mañana',
        aula_id INTEGER,
        especialidad_id INTEGER,
        carrera_id INTEGER,
        profesor_guia_id INTEGER,
        anio_academico TEXT,
        FOREIGN KEY (grado_id) REFERENCES grados(id) ON DELETE CASCADE,
        FOREIGN KEY (aula_id) REFERENCES aulas(id) ON DELETE SET NULL,
        FOREIGN KEY (especialidad_id) REFERENCES especialidades(id) ON DELETE SET NULL,
        FOREIGN KEY (carrera_id) REFERENCES carreras(id) ON DELETE SET NULL,
        FOREIGN KEY (profesor_guia_id) REFERENCES profesores(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS materias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT,
        nombre TEXT NOT NULL,
        creditos INTEGER DEFAULT 0,
        especialidad_id INTEGER,
        profesor_id INTEGER,
        estado TEXT DEFAULT 'Activa',
        FOREIGN KEY (especialidad_id) REFERENCES especialidades(id) ON DELETE SET NULL,
        FOREIGN KEY (profesor_id) REFERENCES profesores(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS horarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seccion_id INTEGER,
        materia_id INTEGER,
        dia TEXT,
        hora_inicio TEXT,
        hora_fin TEXT,
        aula_id INTEGER,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        FOREIGN KEY (aula_id) REFERENCES aulas(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS estudiantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matricula TEXT UNIQUE,
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
        especialidad_id INTEGER,
        carrera_id INTEGER,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL,
        FOREIGN KEY (especialidad_id) REFERENCES especialidades(id) ON DELETE SET NULL,
        FOREIGN KEY (carrera_id) REFERENCES carreras(id) ON DELETE SET NULL
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

    c.execute("""CREATE TABLE IF NOT EXISTS desempeno_individual (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        periodo_id INTEGER,
        competencia TEXT,
        nivel TEXT,
        observacion TEXT,
        actualizado TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, periodo_id, competencia)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS recuperacion_pedagogica (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        materia_id INTEGER,
        periodo_id INTEGER,
        nota_rp REAL,
        fecha TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, materia_id, periodo_id)
    )""")

    # -----------------------------------------
    # cascada de evaluaciones finales (Ordenanza 04-2023, MINERD)
    # -----------------------------------------
    #RP (recuperacion_pedagogica, arriba) ya existía. Estas tres tablas cubren las
    #etapas siguientes: Completiva (50% año + 50% examen), Extraordinaria (30% año +
    #70% examen) y Especial (última oportunidad). AcaDeXI NO decide automáticamente
    #cuándo una materia "cae" en la siguiente etapa: cada nota se registra solo cuando
    #el docente/Coordinación decide evaluar ahí. Igual, si la nota registrada en una
    #etapa vuelve a quedar por debajo del mínimo, el sistema no promueve por sí solo
    #el paso a la siguiente etapa: eso lo decide quien evalúa.
    c.execute("""CREATE TABLE IF NOT EXISTS evaluacion_completiva (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        materia_id INTEGER,
        anio_academico TEXT,
        nota_completiva REAL,
        fecha TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, materia_id, anio_academico)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS evaluacion_extraordinaria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        materia_id INTEGER,
        anio_academico TEXT,
        nota_extraordinaria REAL,
        fecha TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, materia_id, anio_academico)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS evaluacion_especial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        materia_id INTEGER,
        anio_academico TEXT,
        nota_especial REAL,
        fecha TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, materia_id, anio_academico)
    )""")

    #Decisión final del año académico (promoción/repitencia). Se guarda tal cual la
    #registre el docente/Coordinación; AcaDeXI solo la almacena y la muestra, nunca
    #la calcula ni la impone.
    c.execute("""CREATE TABLE IF NOT EXISTS decision_promocion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        anio_academico TEXT,
        decision TEXT DEFAULT 'Pendiente',
        observacion TEXT,
        usuario TEXT,
        fecha TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, anio_academico)
    )""")

    # -----------------------------------------
    # currículo por competencias específicas (Motor Dinámico, MINERD)
    # -----------------------------------------
    #No se crean columnas fijas (CE1, CE2, CE3...) porque la cantidad de
    #Competencias Específicas varía por materia y por grado (primaria puede
    #tener 3, secundaria 5 o más). La interfaz itera sobre las filas de
    #`competencias_especificas` que correspondan a la materia+grado
    #seleccionados y dibuja las columnas dinámicamente.
    #
    #El flujo real de evaluación queda modelado así:
    #Materia -> Competencias (CE) -> Indicadores (IL) -> Evidencias
    #-> Nota de Competencia por Período -> Nota de Período -> Boletín
    #
    #Una "evidencia" sigue siendo una fila de `calificaciones` (examen,
    #proyecto, práctica...), la tabla que ya existía. Lo nuevo es que ahora
    #una evidencia puede vincularse a UNA o VARIAS Competencias Específicas
    #(calificacion_competencia) y, opcionalmente, a los Indicadores de Logro
    #concretos que validó (calificacion_indicador). Con eso el sistema puede
    #calcular solo la nota de cada competencia por período, sin que el
    #docente tenga que promediar nada a mano.
    c.execute("""CREATE TABLE IF NOT EXISTS competencias_especificas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        materia_id INTEGER NOT NULL,
        grado_id INTEGER NOT NULL,
        codigo TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        competencia_fundamental TEXT DEFAULT '',
        orden INTEGER DEFAULT 1,
        estado TEXT DEFAULT 'Activa',
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        FOREIGN KEY (grado_id) REFERENCES grados(id) ON DELETE CASCADE,
        UNIQUE(materia_id, grado_id, codigo)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS indicadores_logro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        competencia_id INTEGER NOT NULL,
        codigo TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        orden INTEGER DEFAULT 1,
        FOREIGN KEY (competencia_id) REFERENCES competencias_especificas(id) ON DELETE CASCADE,
        UNIQUE(competencia_id, codigo)
    )""")

    #Vínculo evidencia <-> competencia específica (muchos a muchos: una
    #evidencia, ej. un Proyecto Final, puede calificar varias CE a la vez).
    c.execute("""CREATE TABLE IF NOT EXISTS calificacion_competencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calificacion_id INTEGER NOT NULL,
        competencia_id INTEGER NOT NULL,
        FOREIGN KEY (calificacion_id) REFERENCES calificaciones(id) ON DELETE CASCADE,
        FOREIGN KEY (competencia_id) REFERENCES competencias_especificas(id) ON DELETE CASCADE,
        UNIQUE(calificacion_id, competencia_id)
    )""")

    #Vínculo evidencia <-> indicador de logro concreto (opcional, granularidad fina).
    c.execute("""CREATE TABLE IF NOT EXISTS calificacion_indicador (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calificacion_id INTEGER NOT NULL,
        indicador_id INTEGER NOT NULL,
        evidenciado INTEGER DEFAULT 1,
        FOREIGN KEY (calificacion_id) REFERENCES calificaciones(id) ON DELETE CASCADE,
        FOREIGN KEY (indicador_id) REFERENCES indicadores_logro(id) ON DELETE CASCADE,
        UNIQUE(calificacion_id, indicador_id)
    )""")

    #Nota consolidada de una Competencia Específica para un estudiante en un
    #período. Se recalcula automáticamente a partir de las evidencias
    #vinculadas (ver calcular_nota_final), pero admite modo manual si el
    #docente necesita corregirla a mano. Guarda también la observación
    #docente de esa competencia (punto pedido: "Observación por competencia").
    c.execute("""CREATE TABLE IF NOT EXISTS competencia_periodo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER NOT NULL,
        competencia_id INTEGER NOT NULL,
        periodo_id INTEGER NOT NULL,
        nota REAL,
        modo_nota TEXT DEFAULT 'Automática',
        observacion TEXT DEFAULT '',
        fecha_evaluacion TEXT,
        actualizado TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (competencia_id) REFERENCES competencias_especificas(id) ON DELETE CASCADE,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, competencia_id, periodo_id)
    )""")

    #Cierre/bloqueo de período: cuando Dirección/Coordinación cierra un
    #período, el registro de notas de ese período deja de aceptar cambios
    #para roles no gerenciales (ver permisos.ROLES_GERENCIALES).
    c.execute("""CREATE TABLE IF NOT EXISTS periodo_bloqueo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        periodo_id INTEGER NOT NULL,
        anio_academico TEXT NOT NULL,
        bloqueado INTEGER DEFAULT 0,
        bloqueado_por TEXT,
        fecha_bloqueo TEXT,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE CASCADE,
        UNIQUE(periodo_id, anio_academico)
    )""")

    #Historial de cambios de calificaciones: quién cambió qué, de qué valor
    #a qué valor, cuándo y por qué. Independiente de `auditoria` (que solo
    #registra la acción general) porque aquí se necesita el valor anterior
    #y el nuevo campo por campo, para poder mostrar un historial legible.
    c.execute("""CREATE TABLE IF NOT EXISTS historial_cambios_calificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tabla_origen TEXT NOT NULL,
        registro_id INTEGER,
        estudiante_id INTEGER,
        campo TEXT,
        valor_anterior TEXT,
        valor_nuevo TEXT,
        usuario TEXT,
        motivo TEXT DEFAULT '',
        fecha TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS tareas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        materia_id INTEGER,
        periodo_id INTEGER,
        profesor_id INTEGER,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        categoria TEXT DEFAULT 'Tarea',
        fecha_asignacion TEXT,
        fecha_entrega TEXT,
        peso REAL DEFAULT 0,
        valor_maximo REAL DEFAULT 100,
        estado TEXT DEFAULT 'Activa',
        competencias TEXT DEFAULT '',
        curso_id INTEGER,
        seccion_id INTEGER,
        especialidad_id INTEGER,
        carrera_id INTEGER,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE SET NULL,
        FOREIGN KEY (profesor_id) REFERENCES profesores(id) ON DELETE SET NULL,
        FOREIGN KEY (curso_id) REFERENCES grados(id) ON DELETE SET NULL,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL,
        FOREIGN KEY (especialidad_id) REFERENCES especialidades(id) ON DELETE SET NULL,
        FOREIGN KEY (carrera_id) REFERENCES carreras(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS tarea_entregas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarea_id INTEGER NOT NULL,
        estudiante_id INTEGER NOT NULL,
        estado_entrega TEXT DEFAULT 'Pendiente',
        fecha_entrega_real TEXT,
        observacion TEXT,
        calificacion_id INTEGER,
        FOREIGN KEY (tarea_id) REFERENCES tareas(id) ON DELETE CASCADE,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (calificacion_id) REFERENCES calificaciones(id) ON DELETE SET NULL,
        UNIQUE (tarea_id, estudiante_id)
    )""")

    #Plantilla de Competencias Específicas que evalúa una tarea del Banco de
    #Tareas. Al calificar una entrega (banco_tareas._calificar_entrega crea o
    #actualiza una fila en `calificaciones`), esta plantilla se copia hacia
    #`calificacion_competencia` para que la evidencia quede vinculada a las
    #mismas CE que la tarea, sin que el docente tenga que repetir el trabajo.
    c.execute("""CREATE TABLE IF NOT EXISTS tarea_competencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarea_id INTEGER NOT NULL,
        competencia_id INTEGER NOT NULL,
        FOREIGN KEY (tarea_id) REFERENCES tareas(id) ON DELETE CASCADE,
        FOREIGN KEY (competencia_id) REFERENCES competencias_especificas(id) ON DELETE CASCADE,
        UNIQUE(tarea_id, competencia_id)
    )""")

    #Equivalente de `tarea_competencia` para materias con modelo_evaluacion =
    #'Técnica (RA)' (Politécnico). Vincula una tarea del Banco de Tareas con
    #uno o varios Resultados de Aprendizaje de su materia. Al calificar una
    #entrega (banco_tareas._calificar_entrega), la nota se copia hacia
    #`calificacion_ra` para cada RA vinculado, para que Calificaciones
    #Técnicas quede sincronizado sin trabajo extra del docente.
    c.execute("""CREATE TABLE IF NOT EXISTS tarea_ra (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarea_id INTEGER NOT NULL,
        resultado_aprendizaje_id INTEGER NOT NULL,
        FOREIGN KEY (tarea_id) REFERENCES tareas(id) ON DELETE CASCADE,
        FOREIGN KEY (resultado_aprendizaje_id) REFERENCES resultados_aprendizaje(id) ON DELETE CASCADE,
        UNIQUE(tarea_id, resultado_aprendizaje_id)
    )""")

    # -----------------------------------------
    # secuencias didácticas (formato de planificación MINERD)
    # -----------------------------------------
    #Una secuencia es la planificación de una unidad de aprendizaje de UNA
    #materia en UN grado: situación de aprendizaje, competencias
    #fundamentales y específicas, contenidos (conceptos / procedimientos /
    #actitudes y valores), indicadores de logro, estrategia, y una lista
    #ordenada de sesiones (fecha, momento Inicio/Desarrollo/Cierre,
    #actividad, evidencia, instrumento, metacognición, recursos).
    #Reutiliza competencias_especificas / indicadores_logro (los mismos que
    #ya usa Calificaciones) y se puede vincular a tareas del Banco de Tareas.
    #============================================================
    c.execute("""CREATE TABLE IF NOT EXISTS secuencias_didacticas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        materia_id INTEGER,
        grado_id INTEGER,
        seccion_id INTEGER,
        profesor_id INTEGER,
        periodo_id INTEGER,
        anio_academico TEXT DEFAULT '',
        eje_transversal TEXT DEFAULT '',
        situacion_aprendizaje TEXT DEFAULT '',
        competencias_fundamentales TEXT DEFAULT '',
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
        FOREIGN KEY (grado_id) REFERENCES grados(id) ON DELETE SET NULL,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL,
        FOREIGN KEY (profesor_id) REFERENCES profesores(id) ON DELETE SET NULL,
        FOREIGN KEY (periodo_id) REFERENCES periodos(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS secuencia_competencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        secuencia_id INTEGER NOT NULL,
        competencia_id INTEGER NOT NULL,
        FOREIGN KEY (secuencia_id) REFERENCES secuencias_didacticas(id) ON DELETE CASCADE,
        FOREIGN KEY (competencia_id) REFERENCES competencias_especificas(id) ON DELETE CASCADE,
        UNIQUE(secuencia_id, competencia_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS secuencia_indicador (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        secuencia_id INTEGER NOT NULL,
        indicador_id INTEGER NOT NULL,
        FOREIGN KEY (secuencia_id) REFERENCES secuencias_didacticas(id) ON DELETE CASCADE,
        FOREIGN KEY (indicador_id) REFERENCES indicadores_logro(id) ON DELETE CASCADE,
        UNIQUE(secuencia_id, indicador_id)
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

    #Paquetes de calificaciones compartidos entre docentes: cada vez que alguien
    #IMPORTA un archivo exportado por otro docente, se guarda una fila aquí con
    #el resumen del paquete. Sirve para (a) mostrar de dónde salió cada nota
    #importada y (b) poder deshacer una importación completa de una sola vez,
    #sin tener que buscar fila por fila.
    c.execute("""CREATE TABLE IF NOT EXISTS paquetes_calificaciones (
        id TEXT PRIMARY KEY,
        materia_id INTEGER,
        seccion_id INTEGER,
        periodo_id INTEGER,
        exportado_por TEXT,
        fecha_exportacion TEXT,
        importado_por TEXT,
        fecha_importacion TEXT,
        cantidad_filas INTEGER DEFAULT 0,
        nombre_archivo TEXT
    )""")

    # -----------------------------------------
    # calificaciones técnicas (Politécnico)
    # -----------------------------------------
    #Resultados de Aprendizaje (RA) Modelo de Educación Técnico Profesional (ETP) del MINERD, República
    #Dominicana, y un modelo simplificado equivalente para politécnicos de
    #otros países. Solo aplica a materias con materias.modelo_evaluacion =
    #'Técnica (RA)' (ver migración más abajo); las materias académicas
    #normales siguen usando el motor de Competencias Específicas ya existente.
    #
    #Cada módulo/materia técnica se descompone en Resultados de Aprendizaje
    #(RA1, RA2...), cada uno con un peso porcentual dentro del módulo (la
    #suma de los pesos de un mismo módulo debería totalizar 100%, aunque
    #AcaDeXI no lo fuerza a nivel de BD para no bloquear guardados
    #intermedios mientras el docente arma el módulo — la interfaz sí avisa
    #visualmente si la suma no cierra en 100%).
    c.execute("""CREATE TABLE IF NOT EXISTS resultados_aprendizaje (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        materia_id INTEGER NOT NULL,
        codigo TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        peso REAL NOT NULL DEFAULT 0,
        orden INTEGER DEFAULT 1,
        estado TEXT DEFAULT 'Activo',
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        UNIQUE(materia_id, codigo)
    )""")

    #Nota de un estudiante en un RA concreto, para un año académico. La
    #Calificación Final (C.F.) del módulo se calcula siempre en caliente
    #(nota * peso, sumado) a partir de estas filas — nunca se guarda un
    #C.F. "congelado" que pueda desincronizarse si luego se corrige un RA.
    c.execute("""CREATE TABLE IF NOT EXISTS calificacion_ra (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER NOT NULL,
        resultado_aprendizaje_id INTEGER NOT NULL,
        anio_academico TEXT NOT NULL,
        nota REAL,
        domina TEXT DEFAULT '',
        observacion TEXT DEFAULT '',
        usuario TEXT DEFAULT '',
        actualizado TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (resultado_aprendizaje_id) REFERENCES resultados_aprendizaje(id) ON DELETE CASCADE,
        UNIQUE(estudiante_id, resultado_aprendizaje_id, anio_academico)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        tipo TEXT DEFAULT 'Institucional',
        fecha TEXT NOT NULL,
        hora TEXT,
        seccion_id INTEGER,
        materia_id INTEGER,
        usuario_id INTEGER,
        visibilidad TEXT DEFAULT 'Institucional',
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE SET NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS observaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER NOT NULL,
        profesor_id INTEGER,
        usuario_id INTEGER,
        fecha TEXT,
        tipo TEXT DEFAULT 'Neutra',
        texto TEXT NOT NULL,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (profesor_id) REFERENCES profesores(id) ON DELETE SET NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS empresas_pasantia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        rubro TEXT,
        ubicacion TEXT,
        contacto TEXT,
        telefono TEXT,
        cupos INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS pasantias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER,
        empresa_id INTEGER,
        horas_acumuladas REAL DEFAULT 0,
        estado TEXT DEFAULT 'En curso',
        desempeno TEXT,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (empresa_id) REFERENCES empresas_pasantia(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS facultades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS carreras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        facultad_id INTEGER,
        FOREIGN KEY (facultad_id) REFERENCES facultades(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS pensum (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        carrera_id INTEGER,
        materia_id INTEGER,
        semestre INTEGER DEFAULT 1,
        prerrequisito_id INTEGER,
        electiva INTEGER DEFAULT 0,
        FOREIGN KEY (carrera_id) REFERENCES carreras(id) ON DELETE CASCADE,
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS personal_administrativo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        apellidos TEXT,
        cargo TEXT,
        departamento TEXT,
        correo TEXT,
        telefono TEXT,
        direccion TEXT,
        fecha_ingreso TEXT,
        estado TEXT DEFAULT 'Activo',
        usuario_id INTEGER,
        foto TEXT,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS materia_profesores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        materia_id INTEGER,
        profesor_id INTEGER,
        seccion_id INTEGER,
        tipo_asignacion TEXT DEFAULT 'Titular',
        FOREIGN KEY (materia_id) REFERENCES materias(id) ON DELETE CASCADE,
        FOREIGN KEY (profesor_id) REFERENCES profesores(id) ON DELETE CASCADE,
        FOREIGN KEY (seccion_id) REFERENCES secciones(id) ON DELETE SET NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS tokens_recuperacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        token TEXT NOT NULL,
        creado TEXT,
        expira TEXT,
        usado INTEGER DEFAULT 0,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS auditoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        modulo TEXT,
        accion TEXT,
        usuario TEXT,
        detalle TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        tipo TEXT,
        destino TEXT,
        tamano_kb REAL,
        usuario TEXT,
        exitoso INTEGER DEFAULT 1
    )""")

    #============================================================
    #PSICOLOGÍA — módulo exclusivo del rol Side Stepper "Psicólogo/a"
    #(ver permisos.py: MODULOS_EXTRA_SIDE_STEPPER, es_psicologo). Es
    #DELIBERADAMENTE una tabla propia y no una reutilización de
    #`observaciones`: aunque el patrón de UI se copia de Observaciones
    #(naturaleza + categorías + destacada + texto libre), el contenido de
    #un registro de Psicología es información sensible/confidencial que
    #NUNCA debe mezclarse con la bandeja de Observaciones que ve un
    #Profesor o Coordinador -tener tablas separadas es lo que permite que
    #el RBAC de acceso (solo Psicólogo/a + roles gerenciales, ver
    #permisos.puede_ver_psicologia) sea una simple condición de
    #visibilidad de MÓDULO, sin tener que filtrar fila por fila dentro de
    #`observaciones` para ocultar las sensibles de quien no debe verlas.
    c.execute("""CREATE TABLE IF NOT EXISTS psicologia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estudiante_id INTEGER NOT NULL,
        psicologo_usuario_id INTEGER,
        fecha TEXT,
        naturaleza TEXT DEFAULT 'Informativa',
        categorias TEXT DEFAULT '',
        texto TEXT NOT NULL,
        destacada INTEGER DEFAULT 0,
        confidencial INTEGER DEFAULT 1,
        proxima_cita TEXT,
        estado_caso TEXT DEFAULT 'Abierto',
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
        FOREIGN KEY (psicologo_usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""")

    #============================================================
    #MATERIALES — inventario configurable de recursos de la institución
    #(libros, equipos de laboratorio, instrumentos, uniformes deportivos,
    #herramientas de talleres técnicos...). El catálogo de categorías es
    #abierto (lo define cada institución, ver categorias_material) y el
    #acceso a cada categoría se otorga POR USUARIO, no por rol fijo: así
    #un Bibliotecario y un Encargado de Laboratorio pueden compartir el
    #mismo rol de "Administrativo" y aun así cada uno solo interactúe con
    #su propia categoría (ver permisos_materiales_usuario y
    #permisos.categorias_material_permitidas). Los roles gerenciales
    #(Administrador/Director/Coordinador) siempre ven y gestionan TODAS
    #las categorías, sin necesidad de una fila aquí.
    c.execute("""CREATE TABLE IF NOT EXISTS categorias_material (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        icono TEXT DEFAULT '📦',
        descripcion TEXT DEFAULT ''
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS materiales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        categoria_id INTEGER NOT NULL,
        codigo TEXT,
        nombre TEXT NOT NULL,
        descripcion TEXT DEFAULT '',
        cantidad_total INTEGER DEFAULT 1,
        cantidad_disponible INTEGER DEFAULT 1,
        ubicacion TEXT DEFAULT '',
        estado TEXT DEFAULT 'Disponible',
        adquirido TEXT,
        actualizado TEXT,
        FOREIGN KEY (categoria_id) REFERENCES categorias_material(id) ON DELETE CASCADE
    )""")

    #Préstamos/salidas del material (opcional por categoría: un libro se
    #presta a un estudiante/profesor; un equipo de laboratorio también).
    #No es obligatorio usarlo -un material puede gestionarse solo por
    #cantidad_disponible- pero da trazabilidad de quién tiene qué.
    c.execute("""CREATE TABLE IF NOT EXISTS material_movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        material_id INTEGER NOT NULL,
        tipo TEXT DEFAULT 'Préstamo',
        cantidad INTEGER DEFAULT 1,
        estudiante_id INTEGER,
        responsable TEXT,
        fecha TEXT,
        fecha_devolucion_esperada TEXT,
        fecha_devuelto TEXT,
        observacion TEXT DEFAULT '',
        usuario_id INTEGER,
        FOREIGN KEY (material_id) REFERENCES materiales(id) ON DELETE CASCADE,
        FOREIGN KEY (estudiante_id) REFERENCES estudiantes(id) ON DELETE SET NULL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
    )""")

    #Permiso de acceso por usuario+categoría (ver permisos.py). Que un
    #usuario NO tenga ninguna fila aquí significa "sin acceso a ninguna
    #categoría" -salvo que sea un rol gerencial, que siempre ve todo sin
    #pasar por esta tabla-.
    c.execute("""CREATE TABLE IF NOT EXISTS permisos_materiales_usuario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        categoria_id INTEGER NOT NULL,
        puede_editar INTEGER DEFAULT 1,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
        FOREIGN KEY (categoria_id) REFERENCES categorias_material(id) ON DELETE CASCADE,
        UNIQUE(usuario_id, categoria_id)
    )""")

    c.execute("SELECT COUNT(*) as n FROM configuracion")
    if c.fetchone()["n"] == 0:
        c.execute("INSERT INTO configuracion (id) VALUES (1)")

    #Migraciones suaves...
    _agregar_columna_si_falta(conn, "profesores", "usuario_id", "INTEGER REFERENCES usuarios(id) ON DELETE SET NULL")
    _agregar_columna_si_falta(conn, "profesores", "foto", "TEXT")

    #Preferencia PERSONAL del propio usuario (se configura en Configuración ▸ Mi
    #Cuenta): si un Profesor quiere ver "Calificaciones Técnicas" en su menú.
    #Es una decisión manual del docente, no depende de qué materias tenga
    #asignadas -por eso vive en `usuarios`, no se calcula de `materias`/
    #`materia_profesores`. Los roles gerenciales ignoran esta columna: para
    #ellos el módulo sigue apareciendo siempre que la institución sea
    #Politécnico (ver _aplicar_permisos_por_rol en main.py).
    _agregar_columna_si_falta(conn, "usuarios", "mostrar_calif_tecnicas", "INTEGER DEFAULT 0")

    #Tutorial general de primer uso (Admin/Director/Coordinación/Personal): se
    #ofrece una sola vez por USUARIO institucional (no por equipo), así que
    #vive aquí junto a `usuarios` — igual que `mostrar_calif_tecnicas` arriba.
    #El tutorial del Modo Docente es independiente y NO usa esta columna: vive
    #en la base local por equipo (ver datos_locales_docente.py), porque todo
    #lo del Modo Docente ya sigue ese patrón local.
    _agregar_columna_si_falta(conn, "usuarios", "tutorial_general_visto", "INTEGER DEFAULT 0")

    #Protección contra fuerza bruta en el login: cuenta de intentos fallidos
    #consecutivos y, si llega al máximo (ver MAX_INTENTOS_LOGIN en login.py),
    #una marca de tiempo hasta la cual la cuenta queda bloqueada. Ambas se
    #reinician a 0/NULL en cuanto el usuario entra correctamente (ver
    #resetear_intentos_login más abajo).
    _agregar_columna_si_falta(conn, "usuarios", "intentos_fallidos", "INTEGER DEFAULT 0")
    _agregar_columna_si_falta(conn, "usuarios", "bloqueado_hasta", "TEXT")

    #Intentos de adivinar un código de recuperación por correo: cada token
    #de 6 dígitos tiene 1,000,000 de combinaciones posibles, pero sin un
    #límite de intentos alguien con acceso a la app podría probarlos todos
    #dentro de la ventana de 15 minutos que dura vigente. Se corta a los 5
    #intentos fallidos por token (ver _restablecer_por_correo en login.py).
    _agregar_columna_si_falta(conn, "tokens_recuperacion", "intentos", "INTEGER DEFAULT 0")

    #Nivel educativo del Grado/Curso: 'Primaria' o 'Secundaria'. Se usa para
    #resolver la nota mínima aprobatoria por nivel en el Sistema Dominicano
    #(Ordenanza 04-2023, MINERD) — ver nota_minima_primaria/nota_minima_secundaria
    #más abajo y resolver_nota_minima() en configuracion.py. Queda NULL
    #("sin clasificar") para instalaciones existentes y para instituciones que
    #no sean de tipo Escuela con Sistema Dominicano (Politécnico, Universidad,
    #Personalizado, u otros sistemas de calificación): esos casos siguen
    #funcionando exactamente igual que antes, usando el fallback `nota_minima`
    #general. Nivel Inicial/Preescolar queda deliberadamente fuera de alcance:
    #no es uno de los dos valores válidos y no tiene lógica propia en la app.
    _agregar_columna_si_falta(conn, "grados", "nivel_educativo", "TEXT")

    # -----------------------------------------
    # nivel académico transversal (Primaria/Secundaria/Preparatoria/Universidad)
    # -----------------------------------------
    #Extiende lo anterior: `grados.nivel_educativo` ahora puede tomar
    #cualquiera de los 4 niveles académicos (ver NIVELES_ACADEMICOS en
    #configuracion.py), no solo Primaria/Secundaria. Es la MISMA columna que
    #ya usaba nota_minima -reutilizada, no duplicada- porque un Curso/Grado
    #solo puede pertenecer a un nivel a la vez y esa ya era su fuente de
    #verdad. Un estudiante NO tiene su propio campo "nivel": se deriva de su
    #Sección -> Grado (K-12) o de su Carrera (Universidad, ver
    #estudiantes.carrera_id, que ya existía). Ver
    #resolver_nivel_academico_estudiante() más abajo, el único punto por el
    #que cualquier módulo debe preguntar el nivel de un estudiante.
    #
    #Dentro de Secundaria, República Dominicana distingue Primer Ciclo
    #(sin módulos técnicos) de Segundo Ciclo (donde sí puede haber
    #modalidad técnico-profesional). Es información del Grado, igual que
    #nivel_educativo, así que vive en la misma tabla. Queda NULL cuando
    #nivel_educativo no es 'Secundaria', o para instalaciones existentes
    #que aún no han clasificado sus grados de secundaria por ciclo -en ese
    #caso, y solo para no bloquear a nadie de forma retroactiva, un grado
    #de Secundaria sin ciclo asignado se trata como Segundo Ciclo al
    #validar módulos técnicos (ver puede_tener_componente_tecnico() en
    #configuracion.py): es la institución quien debe clasificar sus grados
    #para que la restricción de Primer Ciclo aplique.
    _agregar_columna_si_falta(conn, "grados", "ciclo_secundaria", "TEXT")

    #Niveles académicos que la institución realmente ofrece (lista separada
    #por comas, MISMO patrón que `modulos_personalizados`). Solo tiene
    #sentido -y solo se deja editar en la UI- para tipo_institucion
    #'Escuela' y 'Personalizado': para 'Politécnico' y 'Universidad' el
    #nivel se deduce automáticamente del tipo (ver
    #niveles_academicos_habilitados() en configuracion.py), como ya hacía
    #el proyecto con `modulos_personalizados` para Politécnico/Universidad
    #dentro de Personalizado.
    _agregar_columna_si_falta(conn, "configuracion", "niveles_educativos_habilitados", "TEXT")

    #Nota mínima aprobatoria por nivel educativo (Sistema Dominicano). Se eligió
    #agregar dos columnas nuevas en `configuracion` (en vez de una tabla aparte)
    #porque `nota_minima` ya vivía ahí como un único valor por institución y
    #estas son, conceptualmente, la misma configuración desdoblada en dos —
    #consistente con cómo esta tabla ya guarda otros pares de valores afines
    #(p. ej. smtp_*, backup_*, mostrar_calif_tecnicas, tutorial_general_visto
    #arriba) como columnas en vez de tablas satélite. `nota_minima` (el campo
    #viejo) se conserva intacto y sigue siendo el valor usado para cualquier
    #sistema de calificación que NO sea el dominicano (Numérico Personalizado,
    #Estados Unidos), y también el fallback para un grado sin `nivel_educativo`
    #clasificado.
    #
    #Piso normativo confirmado: Primaria 65 (Ordenanza 04-2023, MINERD).
    #Secundaria 70. Ver NOTA_MIN_PRIMARIA_PISO/TECHO y
    #NOTA_MIN_SECUNDARIA_PISO/TECHO en configuracion.py, que son los límites
    #que la UI (wizard y Configuración > Calificaciones) hace cumplir.
    requiere_backfill_nota_minima_nivel= not _columna_existe(conn, "configuracion", "nota_minima_primaria")
    _agregar_columna_si_falta(conn, "configuracion", "nota_minima_primaria", "REAL")
    _agregar_columna_si_falta(conn, "configuracion", "nota_minima_secundaria", "REAL")
    if requiere_backfill_nota_minima_nivel:
        #Migración de instalaciones existentes: se copia el valor global que
        #ya tenían a AMBOS niveles, para que el comportamiento no cambie ni
        #un punto el día que se actualiza la app. La institución puede luego
        #ajustar Primaria y Secundaria por separado desde Configuración >
        #Calificaciones si sabe que difieren.
        c.execute("SELECT nota_minima FROM configuracion WHERE id=1")
        fila_cfg= c.fetchone()
        if fila_cfg is not None:
            valor_actual= fila_cfg["nota_minima"] if fila_cfg["nota_minima"] is not None else 70
            c.execute("UPDATE configuracion SET nota_minima_primaria=?, nota_minima_secundaria=? WHERE id=1",
                      (valor_actual, valor_actual))
            print(f"✅ Migración: nota_minima_primaria/nota_minima_secundaria inicializadas en {valor_actual} "
                  f"(copiadas de nota_minima; ajústalas por separado en Configuración > Calificaciones si difieren)")

    _agregar_columna_si_falta(conn, "personal_administrativo", "foto", "TEXT")

    columnas_smtp= {
        "smtp_host": "TEXT DEFAULT ''",
        "smtp_puerto": "INTEGER DEFAULT 587",
        "smtp_usuario": "TEXT DEFAULT ''",
        "smtp_password": "TEXT DEFAULT ''",
        "smtp_remitente": "TEXT DEFAULT ''",
        "smtp_seguridad": "TEXT DEFAULT 'TLS'",
    }
    for columna, definicion in columnas_smtp.items():
        _agregar_columna_si_falta(conn, "configuracion", columna, definicion)

    columnas_branding= {
        "firma_path": "TEXT DEFAULT ''",
        "pie_pagina": "TEXT DEFAULT ''",
    }
    for columna, definicion in columnas_branding.items():
        _agregar_columna_si_falta(conn, "configuracion", columna, definicion)

    _agregar_columna_si_falta(conn, "configuracion", "auditoria_activa", "INTEGER DEFAULT 1")

    columnas_backup= {
        "backup_modo": "TEXT DEFAULT 'Manual'",
        "backup_carpeta": "TEXT DEFAULT ''",
        "backup_ultima_fecha": "TEXT DEFAULT ''",
    }
    for columna, definicion in columnas_backup.items():
        _agregar_columna_si_falta(conn, "configuracion", columna, definicion)

    _agregar_columna_si_falta(conn, "configuracion", "mostrar_backups_gerenciales", "INTEGER DEFAULT 0")
    _agregar_columna_si_falta(conn, "configuracion", "sistema_calificacion", "TEXT DEFAULT 'Numérico (Personalizado)'")
    _agregar_columna_si_falta(conn, "configuracion", "valores_estados_asistencia", "TEXT DEFAULT ''")

    _agregar_columna_si_falta(conn, "aulas", "especialidad_id", "INTEGER REFERENCES especialidades(id) ON DELETE SET NULL")
    _agregar_columna_si_falta(conn, "grados", "especialidad_id", "INTEGER REFERENCES especialidades(id) ON DELETE SET NULL")
    _agregar_columna_si_falta(conn, "estudiantes", "especialidad_id", "INTEGER REFERENCES especialidades(id) ON DELETE SET NULL")
    #Carrera del estudiante — análogo a especialidad_id, pero para instituciones de
    #tipo Universidad (o Personalizado con el módulo Universidad activo).
    _agregar_columna_si_falta(conn, "estudiantes", "carrera_id", "INTEGER REFERENCES carreras(id) ON DELETE SET NULL")
    #Carrera del Curso/Sección — mismo concepto que especialidad_id para Politécnico,
    #pero para instituciones de tipo Universidad: permite (opcionalmente) clasificar
    #un Curso/Sección universitario por Carrera, igual que un Curso/Sección de
    #Politécnico se clasifica por Área Técnica. No es obligatorio ni de uso frecuente
    #-la mayoría de universidades matriculan solo por estudiante.carrera_id- pero
    #cuando sí se usa, alimenta el mismo filtro de Carrera ya implementado en los
    #demás módulos (Estudiantes, Asistencia, Calificaciones, Reportes, etc.).
    _agregar_columna_si_falta(conn, "grados", "carrera_id", "INTEGER REFERENCES carreras(id) ON DELETE SET NULL")
    _agregar_columna_si_falta(conn, "secciones", "carrera_id", "INTEGER REFERENCES carreras(id) ON DELETE SET NULL")

    #Un profesor puede impartir módulos técnicos además de (o en vez de) materias
    #académicas normales — solo relevante en instituciones con módulo Politécnico
    #activo. `imparte_tecnico` es el interruptor; `especialidad_tecnica_id` es el
    #área técnica principal que domina (independiente del texto libre en
    #`especialidad`, que es su especialidad académica, ej. "Matemáticas").
    _agregar_columna_si_falta(conn, "profesores", "imparte_tecnico", "INTEGER DEFAULT 0")
    _agregar_columna_si_falta(conn, "profesores", "especialidad_tecnica_id",
                               "INTEGER REFERENCES especialidades(id) ON DELETE SET NULL")

    for columna in ("rubro", "ubicacion"):
        _agregar_columna_si_falta(conn, "empresas_pasantia", columna, "TEXT")

    _agregar_columna_si_falta(conn, "estudiantes", "tutor2", "TEXT")

    #------------------------------------------------------------------
    #Número de Lista (ver informe adjunto sobre el sistema dominicano):
    #en RD no hay un criterio único normado por el MINERD para numerar a
    #los alumnos dentro del "libro de clases" de cada aula/sección -es una
    #práctica de cada centro-, pero la convención más extendida (y la que
    #ya usan referentes regionales como el Libro de Clases chileno) es
    #numerar en ORDEN ALFABÉTICO dentro de cada sección, de forma fija
    #durante todo el año. `numero_lista` es ese número (1, 2, 3... por
    #sección, no global) y `criterio_numero_lista` (en `configuracion`)
    #es CÓMO se calcula, para que cada institución lo pueda ajustar en vez
    #de imponer un único criterio -ver CRITERIOS_NUMERO_LISTA más abajo.
    _agregar_columna_si_falta(conn, "estudiantes", "numero_lista", "INTEGER")
    _agregar_columna_si_falta(conn, "configuracion", "criterio_numero_lista",
                               "TEXT DEFAULT 'Apellidos y Nombre'")


    _agregar_columna_si_falta(conn, "tareas", "competencias", "TEXT DEFAULT ''")

    #------------------------------------------------------------------
    #Habilitar Psicología para Administradores (ver configuracion.py ▸
    #pestaña "Usuarios y Roles", solo visible para el rol Administrador
    #-no Director/Coordinador-, y permisos.puede_ver_psicologia). Por
    #defecto en 0: el módulo de Psicología sigue siendo, como siempre,
    #exclusivo del cargo de Side Stepper al que se le otorgue -esto es
    #solo un interruptor adicional para que un Administrador que también
    #ejerce de psicólogo/a de la institución pueda activárselo a sí
    #mismo sin tener que crear un cargo personalizado en Side Stepper.
    _agregar_columna_si_falta(conn, "configuracion", "psicologia_habilitada_admin", "INTEGER DEFAULT 0")

    #Alcance opcional de la tarea (Banco de Tareas): si el docente deja estos
    #campos vacíos, la tarea sigue aplicando a TODAS las secciones que cursan
    #la materia (comportamiento de siempre). Si los llena, la tarea (con su
    #propia fecha de entrega) queda restringida a ese curso/sección/área
    #técnica/carrera — así una misma materia impartida en varios cursos
    #puede tener fechas de entrega distintas por grupo, creando una tarea
    #por grupo en vez de una sola fecha global para todos.
    _agregar_columna_si_falta(conn, "tareas", "curso_id", "INTEGER REFERENCES grados(id) ON DELETE SET NULL")
    _agregar_columna_si_falta(conn, "tareas", "seccion_id", "INTEGER REFERENCES secciones(id) ON DELETE SET NULL")
    _agregar_columna_si_falta(conn, "tareas", "especialidad_id",
                               "INTEGER REFERENCES especialidades(id) ON DELETE SET NULL")
    _agregar_columna_si_falta(conn, "tareas", "carrera_id", "INTEGER REFERENCES carreras(id) ON DELETE SET NULL")

    #Modelo de evaluación de la materia: 'Competencias' (currículo académico
    #por Competencias Específicas/Indicadores de Logro, el de siempre) o
    #'Técnica (RA)' (Resultados de Aprendizaje, para módulos técnicos de un
    #Politécnico — ver calificaciones_tecnicas.py). Por defecto 'Competencias'
    #para no alterar el comportamiento de ninguna materia ya existente.
    _agregar_columna_si_falta(conn, "materias", "modelo_evaluacion", "TEXT DEFAULT 'Competencias'")
    #Curso/grado al que se vincula una materia o módulo técnico. OPCIONAL: NULL = no vinculada a un
    #curso específico (disponible para cualquier curso que tenga su área/tipo).
    _agregar_columna_si_falta(conn, "materias", "grado_id", "INTEGER REFERENCES grados(id) ON DELETE SET NULL")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materias_grado ON materias(grado_id)")

    #Estado de publicación de una evidencia/calificación: una nota puede
    #guardarse como Borrador (solo la ve quien la escribió) o Pendiente
    #(falta revisión) antes de Publicarse (visible en boletín y para el
    #estudiante/tutor). Por defecto "Publicada" para no romper el
    #comportamiento de calificaciones ya existentes.
    _agregar_columna_si_falta(conn, "calificaciones", "estado_publicacion", "TEXT DEFAULT 'Publicada'")
    #Trazabilidad: si esta "evidencia" en realidad nació de un ajuste rápido hecho
    #desde una Observación (ver observaciones.py), se guarda aquí el id de esa
    #observación, para poder mostrar "esta nota viene de tal observación" en el
    #historial y evitar que parezca una evidencia académica huérfana.
    _agregar_columna_si_falta(conn, "calificaciones", "origen_observacion_id", "INTEGER")

    #Compartir calificaciones entre docentes: un profesor que imparte una materia
    #puede EXPORTAR sus notas (por sección+periodo) a un archivo, y el profesor
    #titular de esa sección (que no necesariamente imparte esa materia) las
    #IMPORTA para poder generar el boletín completo. Una fila importada queda
    #marcada de solo lectura: nadie la edita a mano, porque el "registro físico"
    #de quien la generó ya certifica el dato (evita que el boletín impreso no
    #coincida con lo que el docente original entregó).
    for columna, definicion in (
        ("solo_lectura", "INTEGER DEFAULT 0"),
        ("importado_de", "TEXT"),
        ("importado_en", "TEXT"),
        ("origen_exportacion_id", "TEXT"),
    ):
        _agregar_columna_si_falta(conn, "calificaciones", columna, definicion)

    #Recuperación Pedagógica: deja de ser un campo de nota suelto y pasa a
    #ser un submódulo con fecha, observaciones, actividades realizadas y
    #el docente responsable, tal como lo exige el flujo de RP real.
    for columna, definicion in (
        ("observacion", "TEXT DEFAULT ''"),
        ("actividades_realizadas", "TEXT DEFAULT ''"),
        ("docente_responsable", "TEXT DEFAULT ''"),
    ):
        _agregar_columna_si_falta(conn, "recuperacion_pedagogica", columna, definicion)

    #Misma idea para el resto de la cascada (Completiva, Extraordinaria,
    #Especial): observación del proceso y responsable de la evaluación.
    for tabla_cascada in ("evaluacion_completiva", "evaluacion_extraordinaria", "evaluacion_especial"):
        for columna, definicion in (("observacion", "TEXT DEFAULT ''"), ("responsable", "TEXT DEFAULT ''")):
            _agregar_columna_si_falta(conn, tabla_cascada, columna, definicion)

    #Cierre de año: además de la decisión (Promovido/Repitente/Pendiente),
    #se guarda la lista de materias que quedaron pendientes al momento del
    #cierre, para que el boletín/reporte de cierre no tenga que recalcularla.
    _agregar_columna_si_falta(conn, "decision_promocion", "materias_pendientes", "TEXT DEFAULT ''")

    #Politécnico (RD): cuando la decisión final es "Repite el Grado" en un
    #estudiante con módulos técnicos, el centro puede optar por trasladarlo
    #a un liceo regular (sin oferta técnica) o, según su conducta durante el
    #año, autorizarle repetir el año dentro del mismo politécnico. AcaDeXI
    #solo guarda y muestra esta decisión — nunca la calcula ni la impone.
    #Ver calificaciones_tecnicas.py y el aviso de fuente que acompaña esta
    #sección en pantalla (información indicada por el centro, no una
    #normativa oficial verificada del MINERD).
    _agregar_columna_si_falta(conn, "decision_promocion", "accion_no_promocion", "TEXT DEFAULT ''")
    _agregar_columna_si_falta(conn, "decision_promocion", "motivo_conducta", "TEXT DEFAULT ''")

    #Observaciones: se reemplaza el antiguo campo único "tipo" (Positiva/Negativa/
    #Neutra/Académica/Conductual, este último par ambiguo) por dos dimensiones
    #independientes: "naturaleza" (Positiva/Informativa/Negativa, cómo fue) y
    #"categorias" (etiquetas de tema separadas por coma, de qué trata). "tipo" se
    #conserva en la tabla para no romper datos existentes, pero el módulo ya no lo
    #usa. "destacada" marca observaciones que requieren atención (seguimiento,
    #comunicación con padres, problema disciplinario) para el banner de la interfaz.
    requiere_migracion_naturaleza= not _columna_existe(conn, "observaciones", "naturaleza")
    _agregar_columna_si_falta(conn, "observaciones", "naturaleza", "TEXT DEFAULT 'Informativa'")
    _agregar_columna_si_falta(conn, "observaciones", "categorias", "TEXT DEFAULT ''")
    _agregar_columna_si_falta(conn, "observaciones", "destacada", "INTEGER DEFAULT 0")
    #Materia/Módulo donde se registró la observación (opcional — una
    #observación general de conducta puede no estar ligada a ninguna). Sirve
    #para que, al sugerir un ajuste (ver observaciones.py), el sistema sepa
    #si redirigir a "Ajustar Competencia" (materias con Competencias
    #Específicas) o a Calificaciones Técnicas (materias Modelo RA).
    _agregar_columna_si_falta(conn, "observaciones", "materia_id", "INTEGER REFERENCES materias(id) ON DELETE SET NULL")
    if requiere_migracion_naturaleza:
        mapa_tipo_legado= {
            "Positiva": ("Positiva", ""),
            "Negativa": ("Negativa", ""),
            "Neutra": ("Informativa", ""),
            "Académica": ("Informativa", "rendimiento"),
            "Conductual": ("Informativa", "conducta"),
        }
        c.execute("SELECT id, tipo FROM observaciones")
        filas_obs= c.fetchall()
        for fila_obs in filas_obs:
            naturaleza_migrada, categoria_migrada= mapa_tipo_legado.get(fila_obs["tipo"], ("Informativa", ""))
            c.execute("UPDATE observaciones SET naturaleza=?, categorias=? WHERE id=?",
                      (naturaleza_migrada, categoria_migrada, fila_obs["id"]))
        if filas_obs:
            print(f"✅ Migración: {len(filas_obs)} observación(es) migrada(s) a naturaleza/categorías")

    # -----------------------------------------
    # índices para optimización de rendimiento
    # -----------------------------------------
    #Estudiantes
    c.execute("CREATE INDEX IF NOT EXISTS idx_estudiantes_nombre ON estudiantes(nombre, apellidos)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_estudiantes_seccion ON estudiantes(seccion_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_estudiantes_estado ON estudiantes(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_estudiantes_seccion_estado_nombre ON estudiantes(seccion_id, estado, apellidos, nombre)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_estudiantes_carrera_estado_seccion ON estudiantes(carrera_id, estado, seccion_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_estudiantes_matricula ON estudiantes(matricula) WHERE matricula IS NOT NULL AND matricula != ''")

    #Profesores
    c.execute("CREATE INDEX IF NOT EXISTS idx_profesores_nombre ON profesores(nombre, apellidos)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_profesores_estado ON profesores(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_profesores_usuario ON profesores(usuario_id)")

    #Materias
    c.execute("CREATE INDEX IF NOT EXISTS idx_materias_nombre ON materias(nombre)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materias_estado ON materias(estado)")

    #Asistencia
    c.execute("CREATE INDEX IF NOT EXISTS idx_asistencia_estudiante ON asistencia(estudiante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_asistencia_fecha ON asistencia(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_asistencia_seccion ON asistencia(seccion_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_asistencia_materia ON asistencia(materia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_asistencia_seccion_fecha_materia ON asistencia(seccion_id, fecha, materia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_asistencia_estudiante_seccion_fecha_materia ON asistencia(estudiante_id, seccion_id, fecha, materia_id)")

    #Calificaciones
    c.execute("CREATE INDEX IF NOT EXISTS idx_calificaciones_estudiante ON calificaciones(estudiante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calificaciones_materia ON calificaciones(materia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calificaciones_periodo ON calificaciones(periodo_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calificaciones_est_materia_periodo ON calificaciones(estudiante_id, materia_id, periodo_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calificaciones_periodo_estudiante ON calificaciones(periodo_id, estudiante_id)")

    #Evaluaciones finales (Completiva / Extraordinaria / Especial / Decisión de promoción)
    c.execute("CREATE INDEX IF NOT EXISTS idx_completiva_est ON evaluacion_completiva(estudiante_id, materia_id, anio_academico)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_extraordinaria_est ON evaluacion_extraordinaria(estudiante_id, materia_id, anio_academico)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_especial_est ON evaluacion_especial(estudiante_id, materia_id, anio_academico)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_decision_promocion_est ON decision_promocion(estudiante_id, anio_academico)")

    #Currículo por competencias específicas (motor dinámico RD)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ce_materia_grado ON competencias_especificas(materia_id, grado_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_indicadores_competencia ON indicadores_logro(competencia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calif_comp_calificacion ON calificacion_competencia(calificacion_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calif_comp_competencia ON calificacion_competencia(competencia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calif_ind_calificacion ON calificacion_indicador(calificacion_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_competencia_periodo_est ON competencia_periodo(estudiante_id, periodo_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_competencia_periodo_comp ON competencia_periodo(competencia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_periodo_bloqueo ON periodo_bloqueo(periodo_id, anio_academico)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_historial_calif_registro ON historial_cambios_calificaciones(tabla_origen, registro_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_historial_calif_estudiante ON historial_cambios_calificaciones(estudiante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tarea_competencia_tarea ON tarea_competencia(tarea_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tarea_ra_tarea ON tarea_ra(tarea_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_paquetes_calif_seccion ON paquetes_calificaciones(seccion_id, materia_id)")

    #Secuencias didácticas
    c.execute("CREATE INDEX IF NOT EXISTS idx_secuencias_materia ON secuencias_didacticas(materia_id, grado_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_secuencias_profesor ON secuencias_didacticas(profesor_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_secuencia_sesiones_sec ON secuencia_sesiones(secuencia_id, orden)")

    #Calificaciones Técnicas (Resultados de Aprendizaje - RA, Politécnico)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ra_materia ON resultados_aprendizaje(materia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ra_estado ON resultados_aprendizaje(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calif_ra_estudiante ON calificacion_ra(estudiante_id, anio_academico)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_calif_ra_ra ON calificacion_ra(resultado_aprendizaje_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materias_modelo_evaluacion ON materias(modelo_evaluacion)")

    #Horarios
    c.execute("CREATE INDEX IF NOT EXISTS idx_horarios_seccion ON horarios(seccion_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_horarios_materia ON horarios(materia_id)")

    #Tareas
    c.execute("CREATE INDEX IF NOT EXISTS idx_tareas_materia ON tareas(materia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tareas_estado ON tareas(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tareas_materia_estado_entrega ON tareas(materia_id, estado, fecha_entrega)")

    #Tarea entregas
    c.execute("CREATE INDEX IF NOT EXISTS idx_tarea_entregas_tarea ON tarea_entregas(tarea_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tarea_entregas_estudiante ON tarea_entregas(estudiante_id)")

    #Observaciones
    c.execute("CREATE INDEX IF NOT EXISTS idx_observaciones_estudiante ON observaciones(estudiante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_observaciones_fecha ON observaciones(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_observaciones_naturaleza ON observaciones(naturaleza)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_observaciones_destacada ON observaciones(destacada)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_observaciones_materia ON observaciones(materia_id)")

    #Eventos
    c.execute("CREATE INDEX IF NOT EXISTS idx_eventos_fecha ON eventos(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eventos_tipo ON eventos(tipo)")

    #Auditoria
    c.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_usuario ON auditoria(usuario)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_modulo ON auditoria(modulo)")

    #Usuarios
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON usuarios(rol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_activo ON usuarios(activo)")

    #Personal administrativo
    c.execute("CREATE INDEX IF NOT EXISTS idx_personal_usuario ON personal_administrativo(usuario_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_personal_nombre ON personal_administrativo(apellidos, nombre)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_personal_estado ON personal_administrativo(estado)")

    #Materia profesores
    c.execute("CREATE INDEX IF NOT EXISTS idx_materia_profesores_materia ON materia_profesores(materia_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materia_profesores_profesor ON materia_profesores(profesor_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materia_profesores_seccion ON materia_profesores(seccion_id)")

    #Politécnico (pasantías / empresas)
    c.execute("CREATE INDEX IF NOT EXISTS idx_pasantias_estudiante ON pasantias(estudiante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pasantias_empresa ON pasantias(empresa_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pasantias_estado ON pasantias(estado)")

    #Universidad (facultades / carreras / pensum)
    c.execute("CREATE INDEX IF NOT EXISTS idx_carreras_facultad ON carreras(facultad_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pensum_carrera ON pensum(carrera_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pensum_materia ON pensum(materia_id)")

    #Índices ÚNICOS: red de seguridad a nivel de BD contra duplicados (además de
    #la validación que hace universidad.py antes de guardar). Van en try/except
    #porque una base ya existente podría tener duplicados de antes de esta
    #validación; en ese caso se omite el índice y queda solo la validación de
    #la aplicación, en vez de romper el arranque de bases ya instaladas.
    for _stmt_unico in (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_facultades_nombre_unico ON facultades(nombre)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_carreras_nombre_facultad_unico ON carreras(nombre, facultad_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pensum_carrera_materia_unico ON pensum(carrera_id, materia_id)",
        #Áreas técnicas: nombre único en todo el sistema.
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_especialidades_nombre_unico ON especialidades(nombre)",
        #Materias/módulos técnicos comparten la misma tabla `materias`, pero se
        #tratan como dos catálogos distintos de cara al usuario (ver
        #materias.py y politecnico.py), así que la unicidad de nombre se
        #valida POR SEPARADO en cada subconjunto con índices parciales:
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_materias_nombre_tecnica_unico ON materias(nombre) "
        "WHERE modelo_evaluacion = 'Técnica (RA)'",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_materias_nombre_academica_unico ON materias(nombre) "
        "WHERE especialidad_id IS NULL AND (modelo_evaluacion IS NULL OR modelo_evaluacion != 'Técnica (RA)')",
    ):
        try:

            c.execute(_stmt_unico)
        except sqlite3.IntegrityError:
            pass

    #Secciones (usadas en JOIN desde estudiantes/horarios/asistencia)
    c.execute("CREATE INDEX IF NOT EXISTS idx_secciones_grado ON secciones(grado_id)")

    #Backups
    c.execute("CREATE INDEX IF NOT EXISTS idx_backups_fecha ON backups(id)")

    #Psicología
    c.execute("CREATE INDEX IF NOT EXISTS idx_psicologia_estudiante ON psicologia(estudiante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_psicologia_fecha ON psicologia(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_psicologia_psicologo ON psicologia(psicologo_usuario_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_psicologia_estado_caso ON psicologia(estado_caso)")

    #Materiales
    c.execute("CREATE INDEX IF NOT EXISTS idx_materiales_categoria ON materiales(categoria_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materiales_estado ON materiales(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materiales_nombre ON materiales(nombre)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_material_mov_material ON material_movimientos(material_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_material_mov_estudiante ON material_movimientos(estudiante_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_permisos_mat_usuario ON permisos_materiales_usuario(usuario_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_permisos_mat_categoria ON permisos_materiales_usuario(categoria_id)")

    #Boletín Oficial RD (Fase 1-3, ver boletin_minerd.py): formato del
    #boletín, colores por nivel (Primaria/Secundaria son documentos
    #distintos en la plantilla real) y rango de fechas por período (para
    #poder repartir asistencia/observaciones por período en el boletín;
    #opcional, sin esto esas cajas quedan en blanco).
    try:

        from src.boletines.boletin_minerd import migrar_configuracion_boletin
        migrar_configuracion_boletin(conn)
    except ImportError:
        pass  #Módulo del Boletín Oficial RD no instalado en esta copia todavía.

    conn.commit()
    conn.close()
    print("Base de datos inicializada correctamente")


def obtener_config_smtp():

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT smtp_host, smtp_puerto, smtp_usuario, smtp_password, smtp_remitente,
                 smtp_seguridad, nombre_institucion FROM configuracion WHERE id=1""")
    fila= c.fetchone()
    conn.close()
    if not fila:
        return None
    return {
        "host": fila["smtp_host"] or "",
        "puerto": fila["smtp_puerto"] or 587,
        "usuario": fila["smtp_usuario"] or "",
        "password": fila["smtp_password"] or "",
        "remitente": fila["smtp_remitente"] or fila["smtp_usuario"] or "",
        "seguridad": fila["smtp_seguridad"] or "TLS",
        "institucion": fila["nombre_institucion"] or "AcaDeXI",
    }


def enviar_correo(destinatario, asunto, cuerpo):

    cfg= obtener_config_smtp()
    if not cfg or not cfg["host"] or not cfg["usuario"]:
        raise RuntimeError(
            "El servidor de correo (SMTP) no está configurado. Ve a Configuración "
            "Seguridad y Backups Correo (SMTP) para configurarlo, o usa la recuperación "
            "por autorización de Administrador.")

    import smtplib
    from email.mime.text import MIMEText

    mensaje= MIMEText(cuerpo, "plain", "utf-8")
    mensaje["Subject"]= asunto
    mensaje["From"]= cfg["remitente"] or cfg["usuario"]
    mensaje["To"]= destinatario

    #sendmail() no lanza excepción si el servidor ACEPTÓ el mensaje pero
    #rechazó a este destinatario en particular (buzón inexistente, dominio
    #inválido, etc.): devuelve un dict {destinatario: (código, motivo)} con
    #los rechazados. Si no se revisa, el código de recuperación por correo
    #queda dado por "enviado" aunque nunca haya llegado a nadie.
    if cfg["seguridad"] == "SSL":
        with smtplib.SMTP_SSL(cfg["host"], int(cfg["puerto"]), timeout=15) as server:
            server.login(cfg["usuario"], cfg["password"])
            rechazados= server.sendmail(mensaje["From"], [destinatario], mensaje.as_string())
    else:
        with smtplib.SMTP(cfg["host"], int(cfg["puerto"]), timeout=15) as server:
            if cfg["seguridad"] == "TLS":
                server.starttls()
            server.login(cfg["usuario"], cfg["password"])
            rechazados= server.sendmail(mensaje["From"], [destinatario], mensaje.as_string())

    if destinatario in rechazados:
        codigo, motivo= rechazados[destinatario]
        raise RuntimeError(f"El servidor de correo rechazó al destinatario {destinatario} "
                            f"({codigo}: {motivo}).")


def auditoria_esta_activa():

    try:

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT auditoria_activa FROM configuracion WHERE id=1")
        fila= c.fetchone()
        conn.close()
        if fila is None or fila["auditoria_activa"] is None:
            return True
        return bool(fila["auditoria_activa"])
    except Exception:
        return True


def registrar_auditoria(modulo, accion, usuario, detalle=""):

    es_cambio_del_interruptor= (modulo == "Configuración" and "auditoría" in accion.lower())
    if not es_cambio_del_interruptor and not auditoria_esta_activa():
        return
    try:

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute(
            "INSERT INTO auditoria (fecha, modulo, accion, usuario, detalle) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), modulo, accion, usuario or "Sistema", detalle)
        )
        conn.commit()
        conn.close()
    except Exception as error:
        print(f"Error registrando auditoría: {error}")


def obtener_config_backup():

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT backup_modo, backup_carpeta, backup_ultima_fecha FROM configuracion WHERE id=1")
    fila= c.fetchone()
    conn.close()
    if not fila:
        return {"modo": "Manual", "carpeta": "", "ultima_fecha": ""}
    return {
        "modo": fila["backup_modo"] or "Manual",
        "carpeta": fila["backup_carpeta"] or "",
        "ultima_fecha": fila["backup_ultima_fecha"] or "",
    }


def guardar_config_backup(modo, carpeta):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("UPDATE configuracion SET backup_modo=?, backup_carpeta=? WHERE id=1", (modo, carpeta or ""))
    conn.commit()
    conn.close()


def mostrar_backups_gerenciales():

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT mostrar_backups_gerenciales FROM configuracion WHERE id=1")
    fila= c.fetchone()
    conn.close()
    return bool(fila["mostrar_backups_gerenciales"]) if fila else False


def guardar_mostrar_backups_gerenciales(valor):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("UPDATE configuracion SET mostrar_backups_gerenciales=? WHERE id=1", (1 if valor else 0,))
    conn.commit()
    conn.close()


def _registrar_historial_backup(tipo, destino, usuario="Sistema", exitoso=True):

    try:

        conn= obtener_conexion()
        c= conn.cursor()
        tamano_kb= os.path.getsize(destino) / 1024 if os.path.exists(destino) else 0
        c.execute("""INSERT INTO backups (fecha, tipo, destino, tamano_kb, usuario, exitoso)
                     VALUES (?,?,?,?,?,?)""",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tipo, destino, tamano_kb,
                   usuario or "Sistema", int(exitoso)))
        conn.commit()
        conn.close()
    except Exception as error:
        print(f"Error registrando historial de backup: {error}")


def obtener_historial_backups(limite=100):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT * FROM backups ORDER BY id DESC LIMIT ?", (limite,))
    filas= c.fetchall()
    conn.close()
    return filas


def crear_backup(carpeta_extra=None, tipo="Manual", usuario="Sistema"):

    if SANDBOX_TUTORIAL_ACTIVO:
        #El propio Tutorial Detallado pide crear un backup de prueba como
        #paso guiado -bloquearlo por completo rompería ese paso. En vez de
        #eso: se etiqueta sin ambigüedad como práctica (para que nunca se
        #confunda con un respaldo real en el historial) y NUNCA se copia a
        #la carpeta externa configurada por la institución (Google Drive,
        #servidor propio, etc.) -eso sí sería grave, ya que saldría del
        #control de AcaDeXI. RUTA_BD ya apunta al archivo sandbox, así que
        #lo único que se respalda es la copia de práctica, no datos reales.
        tipo= f"🧪 Práctica (Tutorial) - {tipo}"
        carpeta_extra= None
    import shutil
    prefijo_archivo= "PRACTICA_TUTORIAL_" if SANDBOX_TUTORIAL_ACTIVO else ""
    nombre= f"{prefijo_archivo}acadexi_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    destino= os.path.join(obtener_carpeta_datos(), "backups", nombre)
    shutil.copy2(RUTA_BD, destino)
    _registrar_historial_backup(tipo, destino, usuario)

    if carpeta_extra:
        try:

            os.makedirs(carpeta_extra, exist_ok=True)
            destino_extra= os.path.join(carpeta_extra, nombre)
            shutil.copy2(RUTA_BD, destino_extra)
            _registrar_historial_backup(f"{tipo} (Carpeta Personalizada)", destino_extra, usuario)
        except Exception as error:
            print(f"No se pudo copiar el backup a la carpeta configurada: {error}")
            _registrar_historial_backup(f"{tipo} (Carpeta Personalizada)", carpeta_extra, usuario, exitoso=False)

    try:

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("UPDATE configuracion SET backup_ultima_fecha=? WHERE id=1",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return destino


def ejecutar_backup_automatico_al_iniciar():

    cfg= obtener_config_backup()
    modo= cfg["modo"]
    dias_por_modo= {"Diario": 1, "Semanal": 7, "Mensual": 30}
    if modo not in dias_por_modo:
        return
    if cfg["ultima_fecha"]:
        try:

            transcurridos= (datetime.now() - datetime.strptime(cfg["ultima_fecha"], "%Y-%m-%d %H:%M:%S")).days
            if transcurridos < dias_por_modo[modo]:
                return
        except ValueError:
            pass
    ruta= crear_backup(cfg["carpeta"] or None, tipo=f"Automático ({modo})")
    registrar_auditoria("Seguridad", f"Backup automático ({modo.lower()})", "Sistema", ruta)


def ejecutar_backup_al_cerrar():

    cfg= obtener_config_backup()
    if cfg["modo"] != "Al cerrar":
        return
    ruta= crear_backup(cfg["carpeta"] or None, tipo="Automático (Al cerrar)")
    registrar_auditoria("Seguridad", "Backup automático (al cerrar)", "Sistema", ruta)


def restaurar_backup(ruta_backup):

    import shutil
    shutil.copy2(ruta_backup, RUTA_BD)
