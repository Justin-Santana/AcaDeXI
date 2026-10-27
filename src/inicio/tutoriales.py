"""Sistema de tutoriales de primer uso de AcaDeXI.

Un solo módulo (a propósito: así lo pidió el diseño) con:
  - Persistencia de "ya vio este tutorial" (ver más abajo, es por tipo).
  - Pantalla de elección (2 tarjetas: Rápido / Detallado).
  - Modo Rápido: diálogo tipo carrusel de pasos, solo lectura.
  - Modo Detallado: recorrido guiado real por la app con spotlight.
  - Orquestador `ofrecer_tutorial(main_window, tipo)`, llamado desde
    `mostrar_login()` en main.py, y reutilizable desde Configuración ▸ Mi
    Cuenta (botón "Ver tutorial de nuevo").

Hay DOS pares independientes ("general" y "docente"), cada uno con su propio
estado de "visto" — completar uno no marca el otro:

  - "general" (Admin/Director/Coordinador/Administrativo): el flag vive en
    la tabla institucional `usuarios` (columna `tutorial_general_visto`,
    migrada en bd.py) porque es una preferencia de LA CUENTA, no del equipo:
    si el mismo usuario entra desde otra PC, no debería repetírsele.

  - "docente" (rol Profesor): el flag vive en la base SQLite LOCAL por
    equipo que ya usa datos_locales_docente.py para el resto del Modo
    Docente (fotos, horario personal, overrides de Mis Estudiantes). Se
    reutiliza ese mecanismo a propósito: todo lo del Modo Docente ya sigue
    ese patrón "local a este equipo", y el tutorial encaja ahí mejor que en
    la BD institucional.

Ninguno de los dos flujos bloquea el arranque: siempre hay un botón
"Saltar tutoriales por ahora" visible desde el primer instante, y ambos
pueden relanzarse manualmente desde Configuración ▸ Mi Cuenta.
"""
import os
import json
import shutil
import time
import math
import random

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QFrame, QGraphicsOpacityEffect, QSizePolicy, QScrollArea, QTabWidget,
    QProgressBar)
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, QPropertyAnimation, QEasingCurve, QTimer, Signal, QEvent
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QPen, QShortcut, QKeySequence,
    QBitmap, QRegion)

from src.nucleo import bd
from src.nucleo.bd import obtener_conexion, get_app_data_dir
from src.nucleo.iconos import aplicar_icono_ventana, mostrar_mensaje, eventos_ui, ICONO_TUTORIAL, aplicar_icono_cabecera
from src.nucleo.permisos import modulo_visible, ROLES_GERENCIALES
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, pixmap_emoji, quitar_emojis_texto

#Ruta real de la base institucional, capturada UNA sola vez al importar este módulo (mucho antes de que exista
#ninguna sesión de tutorial). Es el valor al que siempre se restaura bd.DB_PATH al salir del sandbox -ver la
#sección SANDBOX DEL TUTORIAL DETALLADO más abajo.
_DB_PATH_REAL= bd.DB_PATH


def _motor_para_tipo(tipo):
    """Motor de base de datos según `tipo` de tutorial: "single_teacher"
    vive sobre bd_single_teacher.py (archivo aparte); todos los demás
    ("general", "docente", "side_stepper") viven sobre bd.py."""
    if tipo == "single_teacher":
        from src.nucleo import bd_single_teacher
        return bd_single_teacher
    return bd


def _db_path_real_para_tipo(tipo):
    if tipo == "single_teacher":
        return _motor_para_tipo(tipo).DB_PATH
    return _DB_PATH_REAL


#PERSISTENCIA
def tutorial_general_visto(main_window):
    id_usuario= getattr(main_window, "id_usuario_actual", None)
    if id_usuario is None:
        return True  #sin sesión identificable -> no insistir
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT tutorial_general_visto FROM usuarios WHERE id=?", (id_usuario,))
    f= c.fetchone()
    conn.close()
    return bool(f["tutorial_general_visto"]) if f else True


def marcar_tutorial_general_visto(main_window, visto=True):
    id_usuario= getattr(main_window, "id_usuario_actual", None)
    if id_usuario is None:
        return
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("UPDATE usuarios SET tutorial_general_visto=? WHERE id=?", (1 if visto else 0, id_usuario))
    conn.commit()
    conn.close()


def tutorial_docente_visto(main_window):
    from src.nucleo.datos_locales_docente import tutorial_docente_visto as _visto
    try:
        return _visto(main_window)
    except Exception:
        return True


def marcar_tutorial_docente_visto(main_window, visto=True):
    from src.nucleo.datos_locales_docente import marcar_tutorial_docente_visto as _marcar
    try:
        _marcar(main_window, visto)
    except Exception:
        pass


#PERSISTENCIA — Single Teacher y Side Stepper (Pieza 5 del prompt de arquitectura de las 4 ediciones)
def tutorial_single_teacher_visto(main_window):
    """Un solo docente, un solo archivo (bd_single_teacher.py): el flag vive
    ahí, no en `usuarios` de bd.py -que esta edición ni siquiera usa."""
    from src.nucleo import bd_single_teacher
    try:
        return bd_single_teacher.tutorial_visto(main_window)
    except Exception:
        return True


def marcar_tutorial_single_teacher_visto(main_window, visto=True):
    from src.nucleo import bd_single_teacher
    try:
        bd_single_teacher.marcar_tutorial_visto(main_window, visto)
    except Exception:
        pass


#Side Stepper reutiliza el mismo mecanismo de "general" (columna usuarios.tutorial_general_visto): comparte el
#esquema institucional de bd.py con Full Institutional, y una instalación side_stepper nunca ofrece
#tipo="general" también, así que no hay riesgo de que se pisen.
tutorial_side_stepper_visto= tutorial_general_visto
marcar_tutorial_side_stepper_visto= marcar_tutorial_general_visto


#Sandbox del tutorial detallado  El Modo Detallado pide acciones REALES ("agrega un estudiante de prueba",
#"registra una nota"...) para que el desafío sea de verdad, no una simulación. Pero eso no debe significar
#ensuciar la base de datos de la institución con estudiantes/profesores/notas falsas. La solución: mientras
#dura el tour, bd.DB_PATH apunta a una COPIA desechable del archivo real -exactamente los mismos módulos, los
#mismos widgets, el mismo flujo, pero escribiendo en un archivo aparte que se descarta al terminar. Esto es
#posible sin tocar estudiantes.py/materias.py/etc. porque obtener_conexion() en bd.py abre y cierra una conexión
#nueva en cada llamada leyendo el DB_PATH global -no hay una conexión persistente ni un singleton que hackear.
#El progreso (qué paso se alcanzó) NUNCA se guarda: si el usuario sale del Tutorial Detallado a medias, la
#próxima vez arranca desde el paso 0 -ver _leer_progreso_sandbox/_guardar_progreso_sandbox más abajo, que son
#un no-op a propósito. (La BD sandbox en sí, con el estudiante de prueba etc., sí puede seguir existiendo hasta
#completar el tour o reiniciarlo, pero eso es independiente de recordar en qué paso iba.)
def _carpeta_sandbox():
    ruta= os.path.join(get_app_data_dir(), "tutorial_sandbox")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def _clave_sandbox(main_window, tipo):
    id_usuario= getattr(main_window, "id_usuario_actual", None) or "anonimo"
    return f"{tipo}_{id_usuario}"


def _ruta_sandbox_db(main_window, tipo):
    return os.path.join(_carpeta_sandbox(), f"{_clave_sandbox(main_window, tipo)}.db")


def _ruta_sandbox_progreso(main_window, tipo):
    return os.path.join(_carpeta_sandbox(), f"{_clave_sandbox(main_window, tipo)}.json")


def _leer_progreso_sandbox(main_window, tipo):
    """El Tutorial Detallado JAMÁS retoma un progreso guardado: cada vez que
    se abre, empieza desde el paso 0. Si quedara un .json de progreso de una
    versión anterior de la app, se ignora (y se limpia) en vez de usarse."""
    ruta_progreso= _ruta_sandbox_progreso(main_window, tipo)
    if os.path.exists(ruta_progreso):
        try:
            os.remove(ruta_progreso)
        except Exception:
            pass
    return 0


def _guardar_progreso_sandbox(main_window, tipo, indice):
    """No-op a propósito: el progreso del Tutorial Detallado nunca se
    persiste. Si el usuario sale a medias, la próxima vez empieza de nuevo
    desde el paso 0 (ver _leer_progreso_sandbox)."""
    pass


def _activar_sandbox(main_window, tipo):
    """Clona la BD real en una copia de práctica (o reutiliza la que ya
    hubiera de una sesión pausada anterior) y redirige DB_PATH ahí -en el
    módulo que corresponda según `tipo` (ver _motor_para_tipo). Devuelve
    True si el sandbox quedó activo; False si algo falló y hay que seguir
    el tour sin sandbox (mejor eso que bloquear el tutorial)."""
    motor= _motor_para_tipo(tipo)
    ruta_real= _db_path_real_para_tipo(tipo)
    ruta_sandbox= _ruta_sandbox_db(main_window, tipo)
    try:
        if not os.path.exists(ruta_sandbox):
            conn= motor.obtener_conexion(main_window) if tipo == "single_teacher" else obtener_conexion()
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            conn.close()
            shutil.copy2(ruta_real, ruta_sandbox)
        motor.DB_PATH= ruta_sandbox
        motor.SANDBOX_TUTORIAL_ACTIVO= True
        return True
    except Exception as e:
        print(f"⚠ No se pudo activar el sandbox del tutorial, se continúa sobre la BD real: {e}")
        motor.DB_PATH= ruta_real
        motor.SANDBOX_TUTORIAL_ACTIVO= False
        return False


def _restaurar_bd_real(borrar_sandbox, main_window=None, tipo=None):
    """SIEMPRE debe llamarse al cerrar el asistente (completado o no):
    devuelve DB_PATH del módulo correspondiente a la base real. Si `tipo`
    es None (limpieza genérica sin tour en curso), restaura siempre bd.py
    por compatibilidad."""
    motor= _motor_para_tipo(tipo) if tipo else bd
    motor.DB_PATH= _db_path_real_para_tipo(tipo) if tipo else _DB_PATH_REAL
    motor.SANDBOX_TUTORIAL_ACTIVO= False
    if borrar_sandbox and main_window is not None and tipo is not None:
        for ruta in (_ruta_sandbox_db(main_window, tipo), _ruta_sandbox_progreso(main_window, tipo)):
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except OSError:
                pass


def _limpiar_sandboxes_huerfanos(dias=2):
    """Red de seguridad: si la app se cerró de golpe a mitad de un tour
    (o quedó un sandbox de una versión anterior), no se acumulan archivos
    temporales para siempre. Se llama una vez al ofrecer tutoriales."""
    carpeta= _carpeta_sandbox()
    limite= time.time() - dias * 86400
    try:
        for nombre in os.listdir(carpeta):
            ruta= os.path.join(carpeta, nombre)
            try:
                if os.path.getmtime(ruta) < limite:
                    os.remove(ruta)
            except OSError:
                pass
    except OSError:
        pass


#CONTENIDO — Modo Rápido (solo lectura). Cada entrada: (icono, nombre_modulo_en_self.modulos, texto_corto) 
#`nombre_modulo=None` identifica elementos de interfaz general (barra de búsqueda, perfil, tema) que existen
#para todos los roles por igual, fuera de cualquier módulo del menú -ver _CONTENIDO_INTERFAZ_GENERAL más abajo.
_CONTENIDO_INTERFAZ_GENERAL= [
    ("@buscador", None, "Buscador Global (arriba, en la barra lateral): escribe un nombre, matrícula, "
                 "materia o incluso el nombre de un módulo y presiona Enter para ir directo ahí."),
    ("@perfil", None, "Tu perfil (arriba a la izquierda): tu nombre y tu rol, con un clic en la foto "
                 "para cambiarla o volver a usar tus iniciales."),
    ("@tema", None, "Modo claro/oscuro: se cambia con un clic desde el pie del menú lateral y se "
                 "recuerda para la próxima vez que inicies sesión."),
]

CONTENIDO_GENERAL= [
    ("", "Dashboard", "Tu vistazo rápido: matrícula, asistencia del día y lo pendiente de un solo golpe."),
    *_CONTENIDO_INTERFAZ_GENERAL,
    ("", "Estudiantes", "La ficha completa de cada estudiante: datos, curso/sección, tutores y foto."),
    ("", "Profesores", "El directorio de docentes y qué materias/secciones tiene asignadas cada uno."),
    ("", "Personal", "El personal administrativo y de apoyo que no da clases."),
    ("", "Materias", "Catálogo de materias, sus créditos y quién las imparte por sección."),
    ("", "Asistencia", "Pase de lista por sección, con reportes de ausencias e inasistencias."),
    ("", "Calificaciones", "Registro de notas por periodo, con historial de cambios."),
    ("", "Politécnico", "Especialidades técnicas y sus estudiantes, si tu institución las maneja."),
    ("", "Calificaciones Técnicas", "Evaluación de competencias técnicas por Resultado de Aprendizaje."),
    ("", "Universidad", "Carreras, semestres y matrícula, si tu institución es de nivel universitario."),
    ("", "Banco de Tareas", "Tareas asignadas y sus entregas, calificables desde el mismo lugar."),
    ("", "Horario", "El horario de clases por sección, con sus bloques y aulas."),
    ("", "Calendario", "Eventos institucionales: exámenes, actividades, reuniones."),
    ("", "Observaciones", "Anotaciones de conducta o seguimiento por estudiante."),
    ("", "Materiales", "Inventario de recursos: biblioteca, laboratorio, equipos y préstamos."),
    ("", "Psicología", "Seguimiento psicológico y conductual por estudiante (edición Side Stepper)."),
    ("", "Reportes", "Boletines, constancias y reportes exportables en PDF."),
    ("", "Copias de Seguridad", "Respaldo manual de toda la base de datos institucional, cuando lo actives."),
    ("", "Sincronización", "Mantén la base de datos al día entre varios equipos."),
    ("", "Configuración", "Datos de la institución, apariencia, usuarios y seguridad."),
]

CONTENIDO_DOCENTE= [
    ("", "Mis Materias", "Las materias que impartes, con tu horario semanal a la vista."),
    *_CONTENIDO_INTERFAZ_GENERAL,
    ("", "Mis Estudiantes", "Tus estudiantes, con notas locales que solo tú ves (nunca se envían a Dirección)."),
    ("", "Asistencia", "Pase de lista de tus secciones, con reportes de ausencias e inasistencias."),
    ("", "Calificaciones", "Registro de notas por periodo, con historial de cambios."),
    ("", "Calificaciones Técnicas", "Evaluación de competencias técnicas, si activaste esta opción."),
    ("", "Banco de Tareas", "Crea tareas y califica las entregas de tus estudiantes."),
    ("", "Horario", "Agrega bloques a tu horario personal, aunque Dirección aún no los haya cargado."),
    ("", "Calendario", "Consulta eventos institucionales que te afecten."),
    ("", "Reportes", "Genera boletines y constancias de tus estudiantes."),
    ("", "Observaciones", "Registra observaciones de conducta o seguimiento."),
    ("", "Copias de Seguridad", "Respalda tu copia local y sincroniza cuando Dirección actualice datos."),
]

#El rol Estudiante es de SOLO LECTURA (ver permisos.puede_editar): su tutorial no habla de "registrar" ni
#"guardar" nada, solo de dónde encontrar su propia información.
CONTENIDO_ESTUDIANTE= [
    ("", "Dashboard", "Tu vistazo rápido al entrar: un resumen de tu situación académica."),
    *_CONTENIDO_INTERFAZ_GENERAL,
    ("", "Calificaciones", "Tus notas por periodo y tu boletín, con el historial de cambios."),
    ("", "Calificaciones Técnicas", "Tu evaluación de competencias técnicas, si tu institución las maneja."),
    ("", "Asistencia", "Tu registro de asistencia, con tus inasistencias marcadas."),
]



#CONTENIDO — Modo Detallado (interactivo). Cada paso: (icono, nombre_modulo, titulo, texto,
#texto_boton_objetivo, pestaña_o_None, objetivo_fijo_o_None)  `texto_boton_objetivo` es un fragmento del texto
#visible del botón real de "guardar/agregar/registrar" de ese paso (no el objectName: varios botones del
#proyecto no tienen objectName asignado, así que buscar por texto visible es más confiable — ver
#_buscar_boton_por_texto). None = paso informativo (sin acción detectable, p. ej. reportes exportables o el
#doble clic en una celda del horario).  `pestaña` es un fragmento del texto visible de la pestaña (QTabWidget)
#que hay que abrir primero dentro del módulo, o None si el módulo no tiene pestañas o ya se trata de la
#primera/única. CADA pestaña de CADA módulo con pestañas tiene su propio paso — no se salta ninguna.
#`objetivo_fijo` (7º campo, OPCIONAL -se puede omitir y la tupla se queda en 6) es el nombre de un atributo de
#`main_window` que señalar cuando el elemento vive FIJO en la barra lateral -no dentro de ningún módulo del
#menú- como el buscador global, la tarjeta de perfil o el interruptor de tema. En estos pasos `nombre_modulo`
#va en None (no se navega a ningún módulo: se señala el elemento tal cual esté la pantalla en ese momento).
def _pasos_interfaz_general():
    """Pasos compartidos por TODOS los roles -se insertan tal cual, justo
    después de la introducción, en cada PASOS_* que los necesite (ver más
    abajo). Viven en una función y no en una constante para que cada rol
    reciba su propia lista de tuplas (los pasos se mutan indirectamente al
    recorrer el tour -guardar progreso, etc.- así que compartir la MISMA
    lista de Python entre PASOS_GENERAL/PASOS_DOCENTE/PASOS_ESTUDIANTE sería
    frágil; una tupla nueva por cada llamada es más seguro y no cuesta nada)."""
    return [
        ("", None, "Busca cualquier cosa desde aquí",
         "Escribe un nombre, matrícula, materia, evento o incluso el nombre de un módulo "
         "(\"calificaciones\", \"horario\"...) y presiona Enter: te lleva directo al resultado, sin "
         "tener que navegar módulo por módulo. Respeta lo que puedes ver: por ejemplo, un Profesor "
         "solo encuentra resultados de sus propias secciones.", None, None, "pildora_busqueda"),
        ("", None, "Tu perfil, siempre a mano",
         "Aquí ves tu nombre y tu rol. Toca tu foto para cambiarla o volver a usar tus iniciales -se "
         "guarda solo para tu cuenta.", None, None, "tarjeta_perfil"),
        ("", None, "Modo claro / oscuro",
         "Cambia la apariencia de toda la aplicación con un clic; se recuerda para la próxima vez "
         "que inicies sesión en este equipo.", None, None, "btn_tema"),
    ]



PASOS_GENERAL= [
    ("", "Dashboard", "Tu punto de partida",
     "Aquí aterrizas después de iniciar sesión: matrícula total, asistencia del día y accesos "
     "rápidos a lo que sueles revisar primero.", None, None),

    *_pasos_interfaz_general(),

    ("", "Estudiantes", "Agrega un estudiante de prueba",
     "Completa el formulario con datos de prueba (nombre, curso/sección) y presiona Guardar. "
     "Así se da de alta cualquier estudiante nuevo, con matrícula generada automáticamente.",
     "Guardar", None),

    ("", "Profesores", "Registra un profesor de prueba",
     "Llena el formulario y guarda: así se da de alta un docente y, más adelante, se le asignan "
     "materias y secciones desde Materias.", "Guardar", None),

    ("", "Personal", "Registra personal administrativo",
     "Completa el formulario y guarda para dar de alta a alguien del personal de apoyo (no da "
     "clases).", "Guardar", None),

    #---- Materias: 5 pestañas ----
    ("", "Materias", "Crea una materia de prueba",
     "Da de alta una materia con su nombre y créditos.", "Guardar Materia", "Materias"),
    ("", "Materias", "Crea un curso/sección de prueba",
     "Aquí defines los cursos/grados y sus secciones (ej. \"5to - A\").", "Guardar Sección",
     "Cursos y Secciones"),
    ("", "Materias", "Registra un aula de prueba",
     "Da de alta un aula o laboratorio: luego se asigna a un bloque de horario.", "Guardar Aula",
     "Aulas y Laboratorios"),
    ("", "Materias", "Asigna una clase al horario",
     "Esta es la forma real de asignar clases al horario institucional (lo que luego ven todos "
     "en el módulo Horario): elige materia, sección, día y hora, y guarda.", "Guardar Horario",
     "Horarios"),
    ("", "Materias", "Asigna un co-docente",
     "Asigna a un segundo profesor (auxiliar/suplente) a una materia ya existente.",
     "Asignar Co-Docente", "Co-Docentes"),

    #---- Asistencia: 2 pestañas ----
    ("", "Asistencia", "Registra la asistencia de una sección",
     "Elige un curso/sección y marca presente/ausente a un par de estudiantes de prueba, luego "
     "guarda. Este es el pase de lista diario.", "Guardar", "Registro Diario"),
    ("", "Asistencia", "Genera un informe de inasistencias",
     "Aquí AcaDeXI te alerta de estudiantes con inasistencias reiteradas; genera el informe "
     "automático para verlo.", "Generar Informe Automático", "Alertas de Inasistencia"),

    #---- Calificaciones: 9 pestañas ----
    ("", "Calificaciones", "Registra una calificación",
     "Elige un curso, materia y estudiante, anota una nota de prueba y guarda.",
     "Registrar Calificación", "Registrar Calificación"),
    ("", "Calificaciones", "Explora el Boletín / Promedios",
     "Aquí se calcula el promedio y se genera el boletín de un estudiante por periodo.", None,
     "Boletín / Promedios"),
    ("", "Calificaciones", "Explora el Historial Académico",
     "El histórico completo de calificaciones de un estudiante a través de los periodos.", None,
     "Historial Académico"),
    ("", "Calificaciones", "Explora el Desempeño Individual",
     "Una vista más detallada del desempeño de un solo estudiante a lo largo del periodo.", None,
     "Desempeño Individual"),
    ("", "Calificaciones", "Explora Seguimiento (RP / Incompletos)",
     "Da seguimiento a estudiantes con Recuperación Pendiente o notas incompletas.", None,
     "Seguimiento"),
    ("", "Calificaciones", "Explora Evaluaciones Finales",
     "El cierre de periodo: notas finales y decisiones de promoción por estudiante.", None,
     "Evaluaciones Finales"),
    ("", "Calificaciones", "Explora el Currículo (CE)",
     "Vincula competencias específicas (CE) del currículo a cada materia.", None, "Currículo"),
    ("", "Calificaciones", "Explora Notas por Competencia",
     "Registra calificaciones desglosadas por competencia específica, no solo una nota global.",
     None, "Notas por Competencia"),
    ("", "Calificaciones", "Explora Compartir Calificaciones",
     "Exporta e importa paquetes de calificaciones entre equipos o instituciones.", None,
     "Compartir Calificaciones"),

    #---- Politécnico: 6 pestañas ----
    ("", "Politécnico", "Crea un Área Técnica de prueba",
     "Si tu institución maneja especialidades técnicas, aquí las das de alta.",
     "Guardar Área Técnica", "Áreas Técnicas"),
    ("", "Politécnico", "Crea un Módulo Técnico de prueba",
     "Cada Área Técnica se subdivide en módulos técnicos evaluables.", "Guardar Módulo Técnico",
     "Módulos Técnicos"),
    ("", "Politécnico", "Asigna un profesor a un módulo",
     "Vincula a un docente con un módulo técnico específico.", "Asignar Profesor",
     "Profesores por Módulo"),
    ("", "Politécnico", "Explora Talleres y Laboratorios",
     "Vincula un aula/taller a un módulo técnico según el equipo que requiera.", None,
     "Talleres y Laboratorios"),
    ("", "Politécnico", "Registra una Empresa de Pasantía",
     "Da de alta una empresa donde los estudiantes puedan hacer pasantías.", "Guardar Empresa",
     "Empresas de Pasantía"),
    ("", "Politécnico", "Registra una Pasantía de prueba",
     "Vincula a un estudiante con una empresa de pasantía.", "Registrar Pasantía",
     "Control de Pasantías"),

    #---- Calificaciones Técnicas: 3 pestañas ----
    ("", "Calificaciones Técnicas", "Explora Módulos y RA",
     "Aquí se definen los Resultados de Aprendizaje (RA) que se evalúan por módulo técnico.",
     None, "Módulos y RA"),
    ("", "Calificaciones Técnicas", "Registra notas por competencia",
     "Anota notas de prueba por Resultado de Aprendizaje y guarda todos los cambios.",
     "Guardar Todos los Cambios", "Registro de Notas"),
    ("", "Calificaciones Técnicas", "Genera un Boletín Técnico",
     "La tabla de abajo ya trae preseleccionado un estudiante (fila resaltada); solo presiona "
     "el botón para generar su boletín técnico con las competencias evaluadas.",
     "Generar Boletín del Seleccionado", "Boletín Técnico"),

    #---- Universidad: 3 pestañas ----
    ("", "Universidad", "Crea una Facultad de prueba",
     "Si tu institución es universitaria, aquí organizas facultades, carreras y su pensum.",
     "Agregar Facultad", "Facultades"),
    ("", "Universidad", "Crea una Carrera de prueba",
     "Cada carrera pertenece a una facultad ya creada.", "Agregar Carrera", "Carreras"),
    ("", "Universidad", "Agrega una materia al Pensum",
     "Arma la malla curricular de una carrera, semestre por semestre.", "Agregar al Pensum",
     "Malla Curricular"),

    #---- Banco de Tareas: 2 pestañas ----
    ("", "Banco de Tareas", "Crea una tarea de prueba",
     "Da de alta una tarea corta con fecha de entrega.", "Guardar Tarea", "Catálogo de Tareas"),
    ("", "Banco de Tareas", "Genera y califica una entrega",
     "Genera/actualiza la lista de entregas de la tarea y califica una de prueba.",
     "Calificar Entrega Seleccionada", "Entregas"),

    ("", "Horario", "Así se ve el horario ya armado",
     "Esta es la vista de solo lectura del horario semanal por sección (para asignar clases "
     "nuevas, usa Materias ▸ Horarios, que ya viste).", None, None),

    ("", "Calendario", "Agrega un evento de prueba",
     "Da de alta un evento (examen, actividad, reunión) con su fecha.", "Guardar Evento", None),

    ("", "Observaciones", "Registra una observación de prueba",
     "Elige un estudiante y anota una observación de conducta o seguimiento de prueba.",
     "Guardar Observación", None),

    ("", "Materiales", "Registra un material de prueba",
     "El inventario de recursos (biblioteca, laboratorio, equipos): da de alta un material con "
     "su cantidad y ubicación, y guarda.",
     "Guardar material", None),

    ("", "Psicología", "Registra un seguimiento de prueba",
     "Elige un estudiante y anota un registro de seguimiento psicológico/conductual de prueba. "
     "Este módulo solo existe en la edición Side Stepper.",
     "Guardar registro", None),

    ("", "Reportes", "Genera un reporte",
     "Elige cualquier reporte (boletín, constancia, listado) y expórtalo para ver el resultado "
     "en PDF. Las pestañas cambian según el tipo de institución configurado.", None, None),

    ("", "Sincronización", "Cómo se mantienen al día varios equipos",
     "Aquí conectas un método (carpeta compartida, Google Drive, servidor propio) para que "
     "varios equipos compartan la misma base de datos.", None, None),

    ("", "Copias de Seguridad", "Crea un respaldo manual",
     "Además de los respaldos automáticos, guarda una copia de seguridad de toda la base de "
     "datos institucional en el momento que quieras.", "Crear Backup Ahora", None),

    ("", "Configuración", "Tu cuenta y la institución",
     "Aquí cambias tu contraseña y el tema visual (pestaña Mi Cuenta) y, según tu rol, los "
     "datos de la Institución, el plan Académico, Usuarios y Roles, Seguridad y Backups, y el "
     "registro de Auditoría. Desde Mi Cuenta también puedes exportar tu Perfil Institucional "
     "Portátil (.acdx) para llevar tu cuenta a otro equipo, y repetir este tutorial cuando "
     "quieras.", None, None),

    ("", None, "¡Listo! Ya conoces AcaDeXI",
     "Esto fue solo un repaso guiado -explora con confianza, todo lo que hiciste aquí fue sobre "
     "una copia de práctica y tus datos reales están intactos. Puedes repetir este tutorial "
     "cuando quieras desde Configuración ▸ Mi Cuenta.", None, None),
]

PASOS_DOCENTE= [
    ("", "Mis Materias", "Tu punto de partida",
     "Tus materias y tu horario semanal, todo en una sola pantalla. Este módulo es solo de "
     "consulta: no se edita aquí.", None, None),

    *_pasos_interfaz_general(),

    ("", "Mis Estudiantes", "Ajusta un dato local",
     "Prueba a corregir un teléfono o agregar una foto a un estudiante: se guarda solo en este "
     "equipo, nunca se envía a Dirección ni se pierde si reimportan datos.", "Guardar", None),

    ("", "Asistencia", "Registra la asistencia de tu sección",
     "Marca presente/ausente a un par de estudiantes de prueba y guarda.", "Guardar",
     "Registro Diario"),
    ("", "Asistencia", "Genera un informe de inasistencias",
     "Genera el informe automático de estudiantes con inasistencias reiteradas.",
     "Generar Informe Automático", "Alertas de Inasistencia"),

    ("", "Calificaciones", "Registra una calificación",
     "Elige un estudiante tuyo, anota una nota de prueba y guarda.", "Registrar Calificación",
     "Registrar Calificación"),
    ("", "Calificaciones", "Explora el Boletín / Promedios",
     "Aquí se calcula el promedio y se genera el boletín de un estudiante por periodo.", None,
     "Boletín / Promedios"),
    ("", "Calificaciones", "Explora el Historial Académico",
     "El histórico completo de calificaciones de un estudiante a través de los periodos.", None,
     "Historial Académico"),

    ("", "Calificaciones Técnicas", "Explora Módulos y RA",
     "Si impartes una materia técnica, aquí se definen los Resultados de Aprendizaje evaluables.",
     None, "Módulos y RA"),
    ("", "Calificaciones Técnicas", "Registra notas por competencia",
     "Anota notas de prueba por Resultado de Aprendizaje y guarda todos los cambios.",
     "Guardar Todos los Cambios", "Registro de Notas"),

    ("", "Banco de Tareas", "Crea una tarea de prueba",
     "Da de alta una tarea corta para ver cómo luego se califican las entregas.",
     "Guardar Tarea", "Catálogo de Tareas"),
    ("", "Banco de Tareas", "Genera y califica una entrega",
     "Genera/actualiza la lista de entregas y califica una de prueba.",
     "Calificar Entrega Seleccionada", "Entregas"),

    ("", "Horario", "Agrega un bloque a tu horario",
     "Anota una clase que Dirección todavía no haya cargado al horario oficial: vive solo en "
     "este equipo y no se pierde si Dirección actualiza el horario institucional.",
     "Guardar Clase Local", None),

    ("", "Calendario", "Consulta eventos institucionales",
     "Revisa exámenes, actividades y reuniones que te afecten.", None, None),

    ("", "Reportes", "Genera un reporte",
     "Genera un boletín o constancia de uno de tus estudiantes y expórtalo en PDF.", None, None),

    ("", "Observaciones", "Registra una observación de prueba",
     "Elige un estudiante tuyo y anota una observación de conducta o seguimiento de prueba.",
     "Guardar Observación", None),

    ("", "Copias de Seguridad", "Crea un respaldo de prueba",
     "Respalda tu copia local. También desde aquí importas el paquete de Estudiantes y Cursos "
     "cuando Dirección lo reexporte.", "Crear Backup Ahora", None),

    ("", "Sincronización", "Cómo se mantiene al día tu copia local",
     "Conecta un método para mantener sincronizada tu copia con la de Dirección.", None, None),

    ("", "Configuración", "Tu cuenta",
     "Cambia tu contraseña, el tema visual y tus preferencias personales -incluida si quieres "
     "ver el módulo de Calificaciones Técnicas en tu menú. También puedes repetir este tutorial "
     "desde Mi Cuenta.", None, None),

    ("", None, "¡Listo! Ya conoces tu Modo Docente",
     "Esto fue solo un repaso guiado -explora con confianza, todo lo que hiciste aquí fue sobre "
     "una copia de práctica y tus datos reales están intactos. Puedes repetir este tutorial "
     "cuando quieras desde Configuración ▸ Mi Cuenta.", None, None),
]

#El rol Estudiante no puede editar nada (ver permisos.puede_editar), así que este recorrido es puramente
#informativo: cada paso solo señala dónde está su información, sin ningún texto_boton_objetivo que verificar
#-por eso el Tutorial Detallado, para este rol, tampoco necesita el sandbox de práctica en ningún sentido "de
#riesgo" (no hay nada que se pueda romper), aunque igualmente se activa por uniformidad con el resto de roles.
PASOS_ESTUDIANTE= [
    ("", "Dashboard", "Tu punto de partida",
     "Aquí aterrizas después de iniciar sesión: un resumen rápido de tu situación académica.",
     None, None),

    *_pasos_interfaz_general(),

    ("", "Calificaciones", "Tus notas y tu boletín",
     "Consulta tus calificaciones por periodo y materia. Si tu institución lo permite, también "
     "verás aquí tu boletín y el historial de cambios de tus notas.", None, None),

    ("", "Calificaciones Técnicas", "Tu evaluación por competencias",
     "Si tu institución maneja evaluación técnica, aquí ves tu avance por Resultado de "
     "Aprendizaje en las materias técnicas que cursas.", None, None),

    ("", "Asistencia", "Tu registro de asistencia",
     "Revisa tus inasistencias y llegadas tarde registradas por tus profesores, sección por "
     "sección.", None, None),

    (None, None, "¡Listo! Ya conoces AcaDeXI",
     "Esto fue solo un repaso guiado por lo que puedes consultar. Puedes repetirlo cuando "
     "quieras la próxima vez que inicies sesión si aún no lo has visto.", None, None),
]


#Contenido y pasos — Single Teacher (Pieza 5 del prompt de arquitectura de las 4 ediciones). no pasan por
#_filtrar_contenido/_filtrar_pasos: esas dos funciones consultan main_window.nav_list/modulos institucionales
#-Single Teacher tiene su propio menú fijo (single_teacher_ui.py, Pieza 3), sin RBAC ni variación posible entre
#instalaciones, así que se muestra tal cual. Los textos de botón deben calzar EXACTAMENTE con los de
#single_teacher_ui.py -si cambias uno allá, actualiza aquí también.
CONTENIDO_SINGLE_TEACHER= [
    ("", None, "Eres dueño directo de tus datos: no hay ninguna Dirección/Coordinación por encima. "
               "Tú creas tus propios cursos, estudiantes y materias desde cero."),
    *_CONTENIDO_INTERFAZ_GENERAL,
    ("", None, "Estudiantes: la ficha de cada uno de tus estudiantes, con curso y datos de contacto."),
    ("", None, "Materias: las materias que tú mismo defines, sin depender de que nadie más las cree."),
    ("", None, "Asistencia: pase de lista de tus cursos, con reportes de ausencias."),
    ("", None, "Calificaciones: registro de notas por periodo, con tu propio sistema de evaluación."),
    ("", None, "Banco de Tareas: crea tareas y califica las entregas."),
    ("", None, "Secuencias Didácticas: planifica tus unidades con el esquema del MINERD y expórtalas a Word."),
    ("", None, "Horario: tu horario de clases, con sus bloques y aulas."),
    ("", None, "Observaciones: anotaciones de conducta o seguimiento por estudiante."),
    ("", None, "Reportes: exporta a Excel o intercambia datos con otra instalación de AcaDeXI -por "
               "ejemplo, si te incorporas formalmente a una institución más adelante."),
]

PASOS_SINGLE_TEACHER= [
    ("", "Dashboard", "Tu punto de partida",
     "Cuántos estudiantes, cursos y materias tienes, y cuántos registraste presentes hoy.",
     None, None),

    *_pasos_interfaz_general(),

    ("", "Estudiantes", "Agrega un estudiante de prueba",
     "Primero toca \"Gestionar mis cursos\" y crea un curso de prueba si todavía no tienes "
     "ninguno; luego completa el formulario (nombre, curso) y presiona Guardar.",
     "Guardar", None),

    ("", "Materias", "Crea una materia de prueba",
     "Escribe el nombre de una materia y presiona Guardar Materia. Aquí no depende de ninguna "
     "Coordinación: tú decides qué materias existen.", "Guardar Materia", None),

    ("", "Asistencia", "Registra la asistencia de un curso",
     "Elige el curso y la fecha, marca el estado de cada estudiante y presiona Guardar.",
     "Guardar", None),

    ("", "Calificaciones", "Registra una calificación",
     "Elige curso, estudiante, materia y periodo, anota una nota de prueba y presiona Registrar "
     "Calificación.", "Registrar Calificación", None),

    ("", "Banco de Tareas", "Crea una tarea de prueba",
     "Elige curso y materia, escribe un título y presiona Guardar Tarea.", "Guardar Tarea", None),

    ("", "Secuencias Didácticas", "Crea una secuencia de prueba",
     "Presiona Nueva secuencia, escribe un título y presiona Guardar. Después, con Editar, "
     "completa la situación de aprendizaje, las competencias y las sesiones (inicio, desarrollo "
     "y cierre); con Exportar a Word la llevas al formato del MINERD.", "Nueva secuencia", None),

    ("", "Horario", "Agrega un bloque a tu horario",
     "Elige curso, materia, día y horas (formato HH:MM) y presiona Guardar Horario.",
     "Guardar Horario", None),

    ("", "Observaciones", "Registra una observación",
     "Elige curso y estudiante, escribe una nota y presiona Guardar Observación.",
     "Guardar Observación", None),

    ("", "Reportes", "Explora Reportes",
     "Desde aquí exportas tus Estudiantes o Calificaciones a Excel, o intercambias datos con "
     "otra instalación de AcaDeXI.", None, None),

    ("", "Configuración", "Tu nombre y tus notas mínimas",
     "Aquí ajustas tu nombre, la nota mínima aprobatoria por nivel educativo, y puedes repetir "
     "este tutorial cuando quieras.", None, None),

    (None, None, "¡Listo! Ya conoces AcaDeXI Single Teacher",
     "Puedes repetir este tutorial cuando quieras desde Configuración.", None, None),
]


#Tarjeta de elección (Rápido / Detallado)
class _TarjetaModo(QFrame):
    elegida= Signal()

    def __init__(self, icono, titulo, descripcion, parent=None):
        super().__init__(parent)
        self.setObjectName("TarjetaModoTutorial")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(240)
        lay= QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 22)
        lay.setSpacing(10)

        lbl_icono= QLabel(icono)
        lbl_icono.setStyleSheet("font-size: 34px; background: transparent;")
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_icono)

        lbl_titulo= QLabel(titulo)
        lbl_titulo.setObjectName("TituloTarjetaModoTutorial")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setWordWrap(True)
        lay.addWidget(lbl_titulo)

        lbl_desc= QLabel(descripcion)
        lbl_desc.setObjectName("DescModulo")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        lay.addWidget(lbl_desc)
        lay.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.elegida.emit()
        super().mousePressEvent(event)


def _colores_tema(main_window):
    """Extrae (bg, texto, accent, accent_hv) de la paleta activa, con
    respaldo fijo si `main_window` no trae theme_palettes (p. ej. en tests)."""
    try:
        paleta= main_window.theme_palettes.get(main_window.tema_actual, {})
        idx= 1 if getattr(main_window, "modo_oscuro", True) else 0
        bg= paleta.get("display_bg", ("#FFFFFF", "#1E293B"))[idx]
        txt= paleta.get("text_primary", ("#0F172A", "#F8FAFC"))[idx]
        accent= paleta.get("btn_op_bg", ("#6366F1", "#4F46E5"))[idx]
        accent_hv= paleta.get("btn_op_hover", ("#4F46E5", "#4338CA"))[idx]
        return bg, txt, accent, accent_hv
    except Exception:
        return "#FFFFFF", "#0F172A", "#6366F1", "#4F46E5"


class PantallaEleccionTutorial(QDialog):
    """2 tarjetas: Modo Rápido / Modo Detallado, + "Saltar por ahora"."""

    RAPIDO= "rapido"
    DETALLADO= "detallado"
    SALTAR= None

    def __init__(self, main_window, titulo, subtitulo, parent=None, mostrar_detallado=True):
        super().__init__(parent or main_window)
        self.main_window= main_window
        self.resultado= self.SALTAR
        self.setWindowTitle(titulo)
        aplicar_icono_ventana(self, ICONO_TUTORIAL)
        self.setMinimumWidth(560)

        lay= QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 22)
        lay.setSpacing(18)

        lbl_titulo= QLabel(titulo)
        lbl_titulo.setStyleSheet("font-size: 19px; font-weight: bold; background: transparent;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_titulo)

        lbl_sub= QLabel(subtitulo)
        lbl_sub.setObjectName("DescModulo")
        lbl_sub.setWordWrap(True)
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_sub)

        fila= QHBoxLayout()
        fila.setSpacing(16)
        t_rapido= _TarjetaModo("⚡", "Modo Rápido", "Un recorrido corto de lectura: qué es cada sección, sin tener "
                                                      "que hacer clic en nada del programa real.")
        t_rapido.elegida.connect(lambda: self._elegir(self.RAPIDO))
        fila.addWidget(t_rapido)
        #mostrar_detallado=False: para ediciones/tipos sin pasos
        #interactivos todavía (ver PASOS_SINGLE_TEACHER cuando aplique) se oculta la tarjeta por completo en vez de
        #ofrecer una opción que no se puede completar.
        if mostrar_detallado:
            t_detallado= _TarjetaModo("📖", "Modo Detallado", "Un recorrido guiado paso a paso, con acciones "
                                                                "reales en cada módulo (podrás saltar cualquier paso).")
            t_detallado.elegida.connect(lambda: self._elegir(self.DETALLADO))
            fila.addWidget(t_detallado)
        lay.addLayout(fila)

        btn_saltar= QPushButton("Saltar tutoriales por ahora")
        btn_saltar.setObjectName("BtnAccionNeutro")
        btn_saltar.clicked.connect(lambda: self._elegir(self.SALTAR))
        lay.addWidget(btn_saltar, alignment=Qt.AlignmentFlag.AlignCenter)

        bg, txt, accent, accent_hv = _colores_tema(main_window)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; }}
            QLabel {{ color: {txt}; background: transparent; }}
            QFrame#TarjetaModoTutorial {{
                background-color: rgba(127,127,127,0.08); border: 1px solid rgba(127,127,127,0.25);
                border-radius: 12px;
            }}
            QFrame#TarjetaModoTutorial:hover {{ border: 1px solid {accent}; }}
            QLabel#TituloTarjetaModoTutorial {{ font-size: 15px; font-weight: bold; }}
            QPushButton#BtnAccionNeutro {{
                background-color: transparent; color: {txt}; border: 1px solid rgba(127,127,127,0.35);
                border-radius: 6px; padding: 8px 18px;
            }}
            QPushButton#BtnAccionNeutro:hover {{ background-color: rgba(127,127,127,0.12); }}
        """)

    def _elegir(self, resultado):
        self.resultado= resultado
        self.accept()


#Iconos de interfaz general (dibujados con QPainter)  Los pasos "de interfaz general" (buscador, perfil, tema
#-ver _CONTENIDO_INTERFAZ_GENERAL) no pertenecen a ningún módulo del menú, así que `aplicar_icono_cabecera` no
#tiene un icono de módulo que mostrarles y el paso se queda sin ningún indicador visual. En vez de recurrir a
#un emoji (que además renderiza distinto según el sistema operativo/fuente instalada), se dibuja un icono
#vectorial simple con QPainter para cada uno de los tres casos, reconocidos por el marcador "@nombre" en el
#campo `icono` de la tupla de contenido.
ICONOS_INTERFAZ_GENERAL= ("@buscador", "@perfil", "@tema")


class _IconoInterfazGeneral(QWidget):
    """Icono vectorial de 72x72 dibujado a mano con QPainter, para los
    pasos de interfaz general del carrusel de Modo Rápido (ver
    ICONOS_INTERFAZ_GENERAL). Sustituye al emoji: se ve igual en cualquier
    sistema operativo y sigue una misma línea visual -un "badge" circular
    de fondo, un aro sutil de borde y el glifo centrado- para que los tres
    iconos (buscador, perfil, tema) luzcan como un mismo set y no como
    dibujos sueltos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tipo= None
        self.color= QColor("#4a90d9")
        self.setFixedSize(72, 72)

    def establecer(self, tipo, color_hex):
        #tipo llega con el "@" incluido (p. ej. "@buscador"); se quita aquí para quedarnos solo con la clave
        #("buscador").
        self.tipo= tipo.lstrip("@") if tipo else None
        self.color= QColor(color_hex)
        self.update()

    def paintEvent(self, event):
        if not self.tipo:
            return
        p= QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        #"Badge" circular de fondo, compartido por los tres iconos, para que se sientan como un mismo set (como los
        #íconos redondos de apps móviles) y no como dibujos sueltos flotando en el aire.
        diam= min(w, h) * 0.86
        rect_fondo= QRectF(cx - diam / 2, cy - diam / 2, diam, diam)

        if self.tipo in ("buscador", "perfil"):
            fondo= QColor(self.color)
            fondo.setAlpha(34)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fondo)
            p.drawEllipse(rect_fondo)

        if self.tipo == "buscador":
            #Lupa: aro grueso de puntas redondeadas + mango corto en diagonal, ligeramente desplazada del centro para
            #dejarle sitio al mango dentro del badge.
            pen= QPen(self.color)
            pen.setWidthF(diam * 0.075)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)

            radio_lente= diam * 0.235
            centro_lente= QPointF(cx - diam * 0.075, cy - diam * 0.075)
            p.drawEllipse(centro_lente, radio_lente, radio_lente)

            ang= math.radians(45)
            desde= QPointF(centro_lente.x() + math.cos(ang) * radio_lente,
                             centro_lente.y() + math.sin(ang) * radio_lente)
            hasta= QPointF(cx + diam * 0.30, cy + diam * 0.30)
            p.drawLine(desde, hasta)

        elif self.tipo == "perfil":
            #Avatar minimalista: cabeza + hombros como dos círculos solapados, recortados por el propio badge para que el
            #"cuerpo" se sugiera sin necesitar una curva Bézier.
            p.setClipPath(self._circulo(rect_fondo))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.color)

            radio_cuerpo= diam * 0.40
            centro_cuerpo= QPointF(cx, cy + diam * 0.40)
            p.drawEllipse(centro_cuerpo, radio_cuerpo, radio_cuerpo)

            radio_cabeza= diam * 0.185
            centro_cabeza= QPointF(cx, cy - diam * 0.155)
            p.drawEllipse(centro_cabeza, radio_cabeza, radio_cabeza)
            p.setClipping(False)

        elif self.tipo == "tema":
            #Sol a la izquierda / luna a la derecha, en dos mitades de color reales (no solo un aro con rayos): comunica
            #"claro/ oscuro" de un vistazo, con colores fijos que representan el concepto en sí (día/noche) y no dependen
            #del tema activo.
            circulo= self._circulo(rect_fondo)
            mitad_izq_rect= QPainterPath()
            mitad_izq_rect.addRect(QRectF(rect_fondo.left(), rect_fondo.top(),
                                           rect_fondo.width() / 2, rect_fondo.height()))
            mitad_clara= circulo.intersected(mitad_izq_rect)
            mitad_oscura= circulo.subtracted(mitad_clara)

            color_claro= QColor("#F1F5F9")
            color_oscuro= QColor("#1E293B")
            color_sol= QColor("#F59E0B")
            color_luna= QColor("#F1F5F9")

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color_claro)
            p.drawPath(mitad_clara)
            p.setBrush(color_oscuro)
            p.drawPath(mitad_oscura)

            #Sol: núcleo + 6 rayos cortos, todo dentro de la mitad clara.
            radio_sol= diam * 0.125
            centro_sol= QPointF(cx - diam * 0.22, cy)
            p.setBrush(color_sol)
            p.drawEllipse(centro_sol, radio_sol, radio_sol)

            pen_rayo= QPen(color_sol)
            pen_rayo.setWidthF(diam * 0.028)
            pen_rayo.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen_rayo)
            for i in range(6):
                ang= math.radians(60 * i)
                x1= centro_sol.x() + math.cos(ang) * radio_sol * 1.55
                y1= centro_sol.y() + math.sin(ang) * radio_sol * 1.55
                x2= centro_sol.x() + math.cos(ang) * radio_sol * 2.05
                y2= centro_sol.y() + math.sin(ang) * radio_sol * 2.05
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            #Luna: media luna (círculo menos un recorte desplazado), dentro de la mitad oscura.
            centro_luna= QPointF(cx + diam * 0.22, cy)
            radio_luna= diam * 0.145
            luna= QPainterPath()
            luna.addEllipse(centro_luna, radio_luna, radio_luna)
            recorte= QPainterPath()
            recorte.addEllipse(QPointF(centro_luna.x() + radio_luna * 0.55,
                                        centro_luna.y() - radio_luna * 0.35),
                                radio_luna * 0.85, radio_luna * 0.85)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color_luna)
            p.drawPath(luna.subtracted(recorte))

            #Línea divisoria sutil entre las dos mitades.
            pen_div= QPen(QColor(127, 127, 127, 90))
            pen_div.setWidthF(1.0)
            p.setPen(pen_div)
            p.drawLine(QPointF(cx, rect_fondo.top() + 1), QPointF(cx, rect_fondo.bottom() - 1))

        #Aro fino compartido por los tres, para que el badge se lea como un elemento acabado (como un marco de avatar)
        #y no como una mancha de color sin borde.
        pen_borde= QPen(QColor(127, 127, 127, 80))
        pen_borde.setWidthF(1.0)
        p.setPen(pen_borde)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect_fondo)

        p.end()

    @staticmethod
    def _circulo(rect):
        path= QPainterPath()
        path.addEllipse(rect)
        return path


#Modo rápido — carrusel de solo lectura (patrón "step_card")
class TutorialRapidoDialog(QDialog):
    def __init__(self, main_window, pasos, titulo, parent=None):
        super().__init__(parent or main_window)
        self.main_window= main_window
        self.pasos= pasos
        self.indice= 0
        self.setWindowTitle(titulo)
        aplicar_icono_ventana(self, ICONO_TUTORIAL)
        self.setMinimumSize(480, 320)

        lay= QVBoxLayout(self)
        lay.setContentsMargins(26, 26, 26, 20)
        lay.setSpacing(14)

        self.lbl_progreso= QLabel()
        self.lbl_progreso.setObjectName("DescModulo")
        self.lbl_progreso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_progreso)

        self.barra_progreso= QProgressBar()
        self.barra_progreso.setTextVisible(False)
        self.barra_progreso.setFixedHeight(6)
        self.barra_progreso.setMaximum(len(pasos))
        lay.addWidget(self.barra_progreso)

        #Fila de icono: el QLabel de emoji/icono de módulo y el icono vectorial QPainter (ver _IconoInterfazGeneral)
        #ocupan el MISMO lugar -solo uno de los dos está visible a la vez, según el paso (_mostrar_paso decide cuál,
        #mirando si `icono` es uno de los marcadores "@..." de ICONOS_INTERFAZ_GENERAL).
        fila_icono= QHBoxLayout()
        fila_icono.addStretch()
        self.lbl_icono= QLabel()
        self.lbl_icono.setStyleSheet("font-size: 46px; background: transparent;")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fila_icono.addWidget(self.lbl_icono)
        _, _, self._accent_tutorial, _ = _colores_tema(main_window)
        self.icono_vectorial= _IconoInterfazGeneral()
        fila_icono.addWidget(self.icono_vectorial)
        fila_icono.addStretch()
        lay.addLayout(fila_icono)

        self.lbl_nombre= QLabel()
        self.lbl_nombre.setStyleSheet("font-size: 17px; font-weight: bold; background: transparent;")
        self.lbl_nombre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_nombre)

        self.lbl_texto= QLabel()
        self.lbl_texto.setObjectName("DescModulo")
        self.lbl_texto.setWordWrap(True)
        self.lbl_texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_texto, 1)

        fila_botones= QHBoxLayout()
        self.btn_atras= QPushButton("Atrás")
        self.btn_atras.setIcon(icono_emoji("⬅"))
        self.btn_atras.setIconSize(_QSize_emoji(16, 16))
        self.btn_atras.setObjectName("BtnAccionNeutro")
        self.btn_atras.clicked.connect(self._atras)
        fila_botones.addWidget(self.btn_atras)
        fila_botones.addStretch()
        btn_saltar= QPushButton("Saltar")
        btn_saltar.setObjectName("BtnAccionNeutro")
        btn_saltar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_saltar)
        self.btn_siguiente= QPushButton("Siguiente ")
        self.btn_siguiente.setObjectName("BtnAccionAgregar")
        self.btn_siguiente.clicked.connect(self._siguiente)
        fila_botones.addWidget(self.btn_siguiente)
        lay.addLayout(fila_botones)

        bg, txt, accent, accent_hv = _colores_tema(main_window)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; }}
            QLabel {{ color: {txt}; background: transparent; }}
            QPushButton#BtnAccionAgregar {{
                background-color: {accent}; color: white; border: none; border-radius: 6px;
                padding: 8px 20px; font-weight: bold;
            }}
            QPushButton#BtnAccionAgregar:hover {{ background-color: {accent_hv}; }}
            QPushButton#BtnAccionNeutro {{
                background-color: transparent; color: {txt}; border: 1px solid rgba(127,127,127,0.35);
                border-radius: 6px; padding: 8px 16px;
            }}
            QPushButton#BtnAccionNeutro:hover {{ background-color: rgba(127,127,127,0.12); }}
        """)

        self._mostrar_paso()

    def _mostrar_paso(self):
        icono, nombre, texto = self.pasos[self.indice]
        self.lbl_progreso.setText(f"{self.indice + 1} de {len(self.pasos)}")
        self.barra_progreso.setValue(self.indice + 1)

        if icono in ICONOS_INTERFAZ_GENERAL:
            #Paso "de interfaz general" (buscador/perfil/tema): no hay módulo del que sacar un icono real, así que se
            #dibuja el icono vectorial en su lugar y se oculta el QLabel de emoji.
            self.lbl_icono.hide()
            self.lbl_icono.setText("")
            self.icono_vectorial.establecer(icono, self._accent_tutorial)
            self.icono_vectorial.show()
        else:
            self.icono_vectorial.hide()
            self.lbl_icono.show()
            self.lbl_icono.setText(icono)
            aplicar_icono_cabecera(self.lbl_icono, nombre, tamano=40)

        self.lbl_nombre.setText(nombre if nombre else "")
        self.lbl_texto.setText(texto)
        self.btn_atras.setEnabled(self.indice > 0)
        self.btn_siguiente.setText("Terminar " if self.indice == len(self.pasos) - 1 else "Siguiente ")

    def _siguiente(self):
        if self.indice == len(self.pasos) - 1:
            self.accept()
            return
        self.indice += 1
        self._mostrar_paso()

    def _atras(self):
        if self.indice > 0:
            self.indice -= 1
            self._mostrar_paso()

    def keyPressEvent(self, event):
        #Navegación cómoda sin soltar el teclado: flechas para moverse, Enter/Espacio para avanzar (o terminar en el
        #último paso). Escape ya cierra el diálogo por comportamiento estándar de QDialog.
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._siguiente()
        elif event.key() == Qt.Key.Key_Left:
            self._atras()
        else:
            super().keyPressEvent(event)


#Modo detallado — recorrido guiado real con spotlight
class _OverlaySpotlight(QWidget):
    """Capa semitransparente sobre TODA la ventana principal, con un
    recorte iluminado alrededor de `rect_agujero` (coordenadas locales de
    este overlay). Si `rect_agujero` es None, no recorta nada (paso
    informativo, solo se atenúa el fondo).

    IMPORTANTE: el agujero interactivo (`rect_agujero`, lo que de verdad se
    puede tocar) y el marco de resaltado visual (`rect_resaltado`, el borde
    que señala "toca aquí") son DOS rects distintos a propósito. Al
    principio eran el mismo -el rect exacto del botón "Guardar", por
    ejemplo- y eso rompía cualquier paso que pidiera "llena el formulario y
    presiona Guardar": el agujero solo dejaba tocar el botón, así que el
    usuario podía pulsar Guardar pero NUNCA escribir en los campos del
    formulario que se suponía debía llenar antes -el propio Guardar
    entonces solo devolvía errores de validación, sin ninguna forma de
    corregirlos. Ahora `rect_agujero` puede ser mucho más grande (p. ej.
    toda la tarjeta/página del formulario -ver AsistenteSpotlight.
    _colocar_spotlight), mientras que `rect_resaltado` sigue siendo el
    marco pequeño y pulsante alrededor del botón, solo para guiar la
    vista hacia la acción final.

    El recorte NO es solo visual: también se aplica como `setMask()` -una
    máscara real de forma/clic construida con un QBitmap- para que el
    agujero sea de verdad interactivo. Antes esto se intentaba solo
    ignorando el clic en `mousePressEvent` cuando caía dentro del área
    iluminada, con la idea de "dejarlo pasar" al botón real de abajo, pero
    eso NO funciona en Qt para widgets superpuestos dentro de la misma
    ventana: ignorar un evento de mouse lo propaga hacia el widget PADRE
    (este mismo overlay, dentro de AsistenteSpotlight), nunca hacia otro
    widget que esté simplemente dibujado más abajo en el z-order. El
    resultado era que el overlay se quedaba con el clic y el botón
    resaltado (p. ej. "Guardar") nunca llegaba a recibirlo -de ahí que el
    Tutorial Detallado no dejara interactuar con los botones.
    `setMask()` sí resuelve esto de raíz: en la zona enmascarada como
    "agujero", Qt directamente considera que este overlay no existe ahí, y
    entrega el clic al widget real que hay debajo.

    `mascara_actualizada` avisa a quien envuelve este overlay (ver
    AsistenteSpotlight._actualizar_mascara_propia) cada vez que la
    máscara cambia, porque ESTE overlay no es el único widget superpuesto:
    también lo envuelve AsistenteSpotlight, y ese contenedor necesita
    quedar en sintonía -si no, el clic se topa con él antes de llegar
    siquiera al overlay."""

    mascara_actualizada= Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.rect_agujero= None
        self.rect_resaltado= None
        #bloqueante=True: pasos con acción real -oscurece y captura el
        #resto de la ventana, solo se puede tocar lo resaltado (el
        #"desafío" tiene que sentirse real). bloqueante=False: pasos
        #puramente informativos -no hay nada que verificar, así que no tiene sentido quitarle el control de la ventana
        #al usuario; deja pasar todos los clics y no oscurece el fondo.
        self.bloqueante= True
        #Distingue "sin máscara" (clearMask(), visible en todas partes) de "máscara con un agujero real" -ver el
        #comentario largo en AsistenteSpotlight._actualizar_mascara_propia sobre por qué esta distinción es
        #imprescindible y no se puede inferir de mask() sola.
        self.tiene_agujero_real= False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def establecer_objetivo(self, rect_agujero, rect_resaltado=None):
        """`rect_agujero`: lo que queda realmente clicable/editable (puede
        ser grande, p. ej. todo el formulario). `rect_resaltado`: el marco
        visual que señala la acción final (p. ej. el botón "Guardar"); si
        se omite, se usa el mismo `rect_agujero` (caso simple, un solo
        botón, sin formulario que llenar)."""
        self.rect_agujero= rect_agujero
        self.rect_resaltado= rect_resaltado if rect_resaltado is not None else rect_agujero
        self._actualizar_mascara()
        self.update()

    def establecer_bloqueante(self, bloqueante):
        self.bloqueante= bloqueante
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not bloqueante)
        self._actualizar_mascara()
        self.update()

    def resizeEvent(self, event):
        #El bitmap de la máscara se construye del tamaño actual del overlay:
        #si la ventana cambia de tamaño, hay que reconstruirlo con el nuevo.
        self._actualizar_mascara()
        super().resizeEvent(event)

    def _actualizar_mascara(self):
        """Reconstruye la máscara de forma/clic del overlay a partir de
        `rect_agujero`. Sin agujero real que abrir (no bloqueante, o
        bloqueante pero todavía sin objetivo localizado) se usa el widget
        completo tal cual, sin máscara."""
        if not self.bloqueante or self.rect_agujero is None or self.rect_agujero.isEmpty()\
                or self.size().isEmpty():
            self.clearMask()
            self.tiene_agujero_real= False
            self.mascara_actualizada.emit()
            return
        bitmap= QBitmap(self.size())
        bitmap.fill(Qt.GlobalColor.color1)  #color1 = zona "sólida": el overlay bloquea aquí
        pintor= QPainter(bitmap)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setBrush(Qt.GlobalColor.color0)  #color0 = el agujero: los clics pasan al widget real
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.drawRoundedRect(QRectF(self.rect_agujero.adjusted(-6, -6, 6, 6)), 10, 10)
        pintor.end()
        self.setMask(QRegion(bitmap))
        self.tiene_agujero_real= True
        self.mascara_actualizada.emit()

    def paintEvent(self, event):
        if not self.bloqueante:
            return  #sin oscurecer: el usuario ve la app normal, con el panel flotando encima
        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path= QPainterPath()
        path.addRect(QRectF(self.rect()))
        if self.rect_agujero is not None and not self.rect_agujero.isEmpty():
            recorte= QPainterPath()
            recorte.addRoundedRect(QRectF(self.rect_agujero.adjusted(-6, -6, 6, 6)), 10, 10)
            path= path.subtracted(recorte)
        painter.fillPath(path, QColor(0, 0, 0, 140))
        #El marco de resaltado se dibuja SIEMPRE alrededor de
        #rect_resaltado (el botón), esté o no dentro del área oscurecida
        #-si el agujero es grande (todo el formulario), el marco queda sencillamente dibujado sobre fondo ya visible,
        #señalando la acción final dentro de la zona ya interactiva.
        if self.rect_resaltado is not None and not self.rect_resaltado.isEmpty():
            pen= QPen(QColor(99, 102, 241), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect_resaltado.adjusted(-6, -6, 6, 6)), 10, 10)

    def mousePressEvent(self, event):
        #Con la máscara activa, este método solo llega a dispararse para clics en la zona oscurecida (bloqueante): al
        #agujero, Qt ya lo entrega directamente al widget real de abajo, sin pasar por aquí. Basta con aceptar el
        #evento para que no se propague más allá.
        event.accept()


class _BannerSandbox(QFrame):
    """Franja fija en la parte superior de la ventana, visible durante TODO
    el Tutorial Detallado, recordando que nada de lo que se guarde aquí
    toca la base de datos real -el mismo principio que el borde de color
    de un entorno aislado: tiene que ser imposible no verlo, para que
    nadie confunda al "estudiante de prueba" con uno real."""

    ALTURA= 34

    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.setFixedHeight(self.ALTURA)
        lay= QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lbl= QLabel("Estás practicando — nada de lo que hagas aquí se guarda en la base de datos real.")
        lbl.setStyleSheet("color: white; font-weight: bold; background: transparent;")
        lay.addWidget(lbl)
        lay.addStretch()
        self.setStyleSheet("background-color: #D97706; border: none;")  #ámbar: ni error ni éxito, "atención"

    def acomodar(self, ancho):
        self.setGeometry(0, 0, ancho, self.height())


class _PanelInstruccion(QFrame):
    """Tarjeta flotante con el texto del paso y los botones de control,
    hija del overlay (para quedar siempre por encima). Se puede arrastrar
    libremente agarrando la manija superior (ver _manija/eventFilter):
    quien la mueve deja de estar a merced del posicionamiento automático
    -ver AsistenteSpotlight._posicionar_panel-, que respeta esa posición
    manual mientras dure el paso actual."""
    siguiente= Signal()
    saltar_paso= Signal()
    salir= Signal()
    tamano_cambiado= Signal()  #el texto de ayuda (u otro contenido) cambió de alto
    arrastrado= Signal()  #el usuario está moviendo el panel a mano

    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window= main_window
        self.setObjectName("PanelInstruccionTutorial")
        self.setFixedWidth(400)
        lay= QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 16)
        lay.setSpacing(8)

        #--- Manija para arrastrar el panel --- Deliberadamente una fila propia, separada del texto: así el usuario
        #siempre sabe dónde "agarrar" sin arriesgarse a mover el panel sin querer al intentar leer o hacer clic en otra
        #parte.
        self._manija= QLabel("⠿⠿⠿  Arrastra para mover · Ctrl+H oculta/muestra")
        self._manija.setObjectName("ManijaPanelTutorial")
        self._manija.setCursor(Qt.CursorShape.SizeAllCursor)
        self._manija.setStyleSheet("font-size: 10px; letter-spacing: 1px; background: transparent;")
        self._manija.installEventFilter(self)
        lay.addWidget(self._manija)
        self._offset_arrastre= None

        self.lbl_progreso= QLabel()
        self.lbl_progreso.setObjectName("DescModulo")
        lay.addWidget(self.lbl_progreso)

        self.barra_progreso= QProgressBar()
        self.barra_progreso.setTextVisible(False)
        self.barra_progreso.setFixedHeight(6)
        lay.addWidget(self.barra_progreso)

        self.lbl_titulo= QLabel()
        self.lbl_titulo.setStyleSheet("font-size: 15px; font-weight: bold; background: transparent;")
        self.lbl_titulo.setWordWrap(True)
        fila_titulo= QHBoxLayout()
        fila_titulo.setContentsMargins(0, 0, 0, 0)
        fila_titulo.setSpacing(8)
        self.lbl_icono_titulo= QLabel()
        self.lbl_icono_titulo.setStyleSheet("font-size: 17px; background: transparent;")
        self.lbl_icono_titulo.setFixedSize(22, 22)
        self.lbl_icono_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fila_titulo.addWidget(self.lbl_icono_titulo, 0, Qt.AlignmentFlag.AlignTop)
        fila_titulo.addWidget(self.lbl_titulo, 1)
        lay.addLayout(fila_titulo)

        self.lbl_texto= QLabel()
        self.lbl_texto.setObjectName("DescModulo")
        self.lbl_texto.setWordWrap(True)
        lay.addWidget(self.lbl_texto)

        self.lbl_completado= QLabel("¡Bien hecho!")
        self.lbl_completado.setStyleSheet("color: #22C55E; font-weight: bold; background: transparent;")
        self.lbl_completado.setVisible(False)
        lay.addWidget(self.lbl_completado)

        self.lbl_ayuda= QLabel()
        self.lbl_ayuda.setWordWrap(True)
        self.lbl_ayuda.setStyleSheet("color: #F59E0B; font-size: 11px; background: transparent;")
        self.lbl_ayuda.setVisible(False)
        lay.addWidget(self.lbl_ayuda)

        fila_salir= QHBoxLayout()
        btn_salir= QPushButton("Salir")
        btn_salir.setIcon(icono_emoji("✖"))
        btn_salir.setIconSize(_QSize_emoji(16, 16))
        btn_salir.setObjectName("BtnAccionNeutro")
        btn_salir.setMinimumHeight(32)
        btn_salir.clicked.connect(self.salir.emit)
        fila_salir.addWidget(btn_salir)
        fila_salir.addStretch()
        lay.addLayout(fila_salir)

        fila_accion= QHBoxLayout()
        fila_accion.setSpacing(8)
        self.btn_saltar_paso= QPushButton("Saltar este paso")
        self.btn_saltar_paso.setObjectName("BtnAccionNeutro")
        self.btn_saltar_paso.setMinimumHeight(32)
        self.btn_saltar_paso.clicked.connect(self.saltar_paso.emit)
        fila_accion.addWidget(self.btn_saltar_paso)
        #Este botón SOLO existe para pasos informativos (sin acción real que verificar). En pasos con acción real
        #permanece oculto: el único camino hacia adelante es completar la acción de verdad -o "Saltar este paso", que
        #es una decisión explícita y distinta, nunca el mismo botón disfrazado de "ya lo hice".
        self.btn_siguiente= QPushButton("Continuar ")
        self.btn_siguiente.setObjectName("BtnAccionAgregar")
        self.btn_siguiente.setMinimumHeight(32)
        self.btn_siguiente.clicked.connect(self.siguiente.emit)
        fila_accion.addWidget(self.btn_siguiente)
        lay.addLayout(fila_accion)

    def eventFilter(self, obj, event):
        #Arrastre manual: solo desde la manija (ver __init__), nunca desde el resto del panel -así un clic sobre el
        #texto o cerca de un botón nunca se confunde con "empezar a arrastrar".
        if obj is self._manija:
            tipo= event.type()
            if tipo == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._offset_arrastre= event.globalPosition().toPoint() - self.pos()
                return True
            if tipo == QEvent.Type.MouseMove and self._offset_arrastre is not None:
                self.move(event.globalPosition().toPoint() - self._offset_arrastre)
                self.arrastrado.emit()
                return True
            if tipo == QEvent.Type.MouseButtonRelease and self._offset_arrastre is not None:
                self._offset_arrastre= None
                return True
        return super().eventFilter(obj, event)

    def mostrar_ayuda(self, texto):
        self.lbl_ayuda.setText(texto)
        self.lbl_ayuda.setVisible(bool(texto))

        bg, txt, accent, accent_hv = _colores_tema(self.main_window)
        self.setStyleSheet(f"""
            QFrame#PanelInstruccionTutorial {{
                background-color: {bg}; border-radius: 12px; border: 1px solid {accent};
            }}
            QLabel {{ color: {txt}; }}
            QLabel#ManijaPanelTutorial {{ color: {accent}; }}
            QPushButton#BtnAccionAgregar {{
                background-color: {accent}; color: white; border: none; border-radius: 6px;
                padding: 7px 16px; font-weight: bold;
            }}
            QPushButton#BtnAccionAgregar:hover {{ background-color: {accent_hv}; }}
            QPushButton#BtnAccionNeutro {{
                background-color: transparent; color: {txt}; border: 1px solid rgba(127,127,127,0.35);
                border-radius: 6px; padding: 7px 12px;
            }}
            QPushButton#BtnAccionNeutro:hover {{ background-color: rgba(127,127,127,0.12); }}
        """)
        #BUG CORREGIDO: mostrar/ocultar el texto de ayuda cambia cuántas líneas ocupa el panel (aparece DESPUÉS del
        #primer adjustSize() del paso, cuando el botón objetivo tarda en encontrarse -ver
        #AsistenteSpotlight._enganchar_boton). Como el panel se posiciona con move() y no vive dentro del layout de un
        #padre, Qt NO lo redimensiona solo cuando su contenido interno crece: había que pedírselo explícitamente, o el
        #texto nuevo (o el texto de la descripción, empujado hacia abajo) quedaba recortado/superpuesto con lo de más
        #abajo -exactamente el texto cortado reportado.
        self.adjustSize()
        self.tamano_cambiado.emit()


class _ConfettiOverlay(QWidget):
    """Lluvia de confeti breve para celebrar que se completó CORRECTAMENTE
    una parte del Tutorial Detallado (acción real validada, o paso
    informativo leído hasta el final con "Continuar") -nunca al "Saltar
    este paso", que es justo lo contrario de "terminarla bien".

    Puramente decorativo y efímero: vive encima de todo (hijo de
    AsistenteSpotlight, `raise_()` al crearse) pero es transparente a los
    clics -WA_TransparentForMouseEvents- para no robarle ni un solo
    milisegundo de interacción al usuario ni interferir con la máscara de
    agujero del paso (ver AsistenteSpotlight._actualizar_mascara_propia).
    Se autodestruye sola (`deleteLater`) al terminar su propia animación,
    así que quien la lanza no tiene que acordarse de limpiarla."""
    _COLORES= ("#22C55E", "#F59E0B", "#3B82F6", "#EF4444", "#A855F7", "#EC4899", "#14B8A6")
    _DURACION_MS= 1400
    _INTERVALO_MS= 16
    _N_PARTICULAS= 90

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(parent.rect())
        ancho= max(parent.width(), 1)
        colores= [QColor(c) for c in self._COLORES]
        self._particulas= []
        for _ in range(self._N_PARTICULAS):
            self._particulas.append({
                #Arrancan por encima del borde superior, escalonadas en el
                #tiempo (y_inicial negativa variable), para que no caigan
                #todas "en bloque" sino en una lluvia continua.
                "x": random.uniform(0, ancho),
                "y": random.uniform(-parent.height() * 0.6 - 40, -10),
                "vx": random.uniform(-40, 40) / 1000.0,   #px/ms
                "vy": random.uniform(180, 340) / 1000.0,  #px/ms
                "rot": random.uniform(0, 360),
                "vrot": random.uniform(-260, 260) / 1000.0,  #grados/ms
                "color": random.choice(colores),
                "ancho": random.uniform(5, 9),
                "alto": random.uniform(8, 14),
                "fase": random.uniform(0, 2 * math.pi),
            })
        self._transcurrido_ms= 0
        self._timer= QTimer(self)
        self._timer.timeout.connect(self._avanzar)
        self.show()
        self.raise_()
        self._timer.start(self._INTERVALO_MS)

    def _avanzar(self):
        self._transcurrido_ms += self._INTERVALO_MS
        for p in self._particulas:
            p["y"] += p["vy"] * self._INTERVALO_MS
            #Un vaivén lateral en seno (además de la deriva `vx` lineal) es lo que hace que el confeti "revolotee" al caer
            #en vez de descender en línea recta -mucho más creíble visualmente.
            p["x"] += p["vx"] * self._INTERVALO_MS + math.sin(p["y"] / 28.0 + p["fase"]) * 0.6
            p["rot"] += p["vrot"] * self._INTERVALO_MS
        self.update()
        if self._transcurrido_ms >= self._DURACION_MS:
            self._timer.stop()
            self.hide()
            self.deleteLater()

    def paintEvent(self, event):
        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        #Se apaga (fade out) en el último tercio de la animación, en vez de desaparecer de golpe cuando el timer
        #termina.
        restante= max(0.0, 1.0 - (self._transcurrido_ms / self._DURACION_MS))
        opacidad= min(1.0, restante * 1.6)
        for p in self._particulas:
            pintor.save()
            pintor.translate(p["x"], p["y"])
            pintor.rotate(p["rot"])
            color= QColor(p["color"])
            color.setAlphaF(max(0.0, opacidad))
            pintor.setBrush(color)
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.drawRect(QRectF(-p["ancho"] / 2, -p["alto"] / 2, p["ancho"], p["alto"]))
            pintor.restore()
        pintor.end()


class AsistenteSpotlight(QWidget):
    """Recorrido interactivo real: navega el `nav_list`/`stacked_widget` de
    `main_window` módulo por módulo y espera una acción concreta (clic en
    el botón de guardar/agregar de esa pantalla) o el salto manual del
    paso. No usa una ventana ni proceso aparte: es un overlay hijo directo
    de la ventana principal, así que respeta la instancia única y el
    ciclo de vida normal de `MainWindow`."""

    finalizado= Signal()

    #Cuántas veces (cada 1s) se reintenta encontrar el botón objetivo antes de mostrar la ayuda de "¿no lo
    #encuentras?" -no como error, solo como apoyo si el módulo tardó en construir sus combos/pestañas.
    _INTENTOS_ANTES_DE_AYUDAR= 5

    def __init__(self, main_window, pasos, tipo):
        super().__init__(main_window)
        self.main_window= main_window
        self.pasos= pasos
        self.tipo= tipo  #"general" o "docente", solo para marcar el flag correcto al terminar
        self._objetivo_fijo_actual= None

        #BUG CORREGIDO: antes, la primera línea de este constructor era `self.setGeometry(main_window.rect())`, ANTES
        #de crear self.overlay/self.banner/self.panel. Cambiar el tamaño de un QWidget dispara un resizeEvent de
        #inmediato (aunque el widget todavía no se haya mostrado), y este widget sobrescribe resizeEvent para llamar a
        #_reposicionar() -que a su vez usa self.overlay/self.banner/self.panel. Ese primer resizeEvent llegaba entonces
        #con esos atributos todavía sin existir, lanzaba un AttributeError dentro del propio manejador de eventos de Qt
        #(que PySide se traga: imprime el traceback y sigue, sin propagarlo), y como resultado _reposicionar() -el
        #ÚNICO lugar donde se llama a banner.acomodar() para darle el ancho completo de la ventana- jamás llegaba a
        #completarse. Si después la ventana principal no volvía a moverse/redimensionarse durante el tour (lo normal),
        #el banner se quedaba para siempre con el tamaño por defecto de un QWidget recién creado (~100x30 px), angosto
        #y solapado con el logo de la barra lateral -exactamente el bug de la franja naranja cortada reportado.
        #
        #La solución: no tocar la geometría de nada hasta que TODOS los widgets hijos ya existan, y al final del
        #constructor, llamar a
        #_reposicionar() explícitamente UNA vez -ya no dependemos de que
        #algún resizeEvent "de suerte" nos coloque todo correctamente. `_listo` además blinda eventFilter/resizeEvent
        #por si Qt disparara algún evento de verdad durante esta construcción.
        self._listo= False

        #El sandbox ya se activó en _lanzar() antes de construir este
        #asistente (si hubiera fallado, no se habría llegado hasta aquí).
        self.indice= min(_leer_progreso_sandbox(main_window, tipo), max(0, len(pasos) - 1))

        self.overlay= _OverlaySpotlight(self)        #Este widget (AsistenteSpotlight) es EN SÍ MISMO otra capa opaca
        #superpuesta sobre main_window (es el widget que envuelve al overlay, y es sibling directo de
        #main_window.stacked_widget). Si solo el overlay tuviera el agujero clicable, el clic se seguiría topando con
        #este contenedor antes de llegar siquiera al overlay -así que se mantiene en sintonía con la máscara del
        #overlay (ver _actualizar_mascara_propia, que además protege siempre a panel y banner) cada vez que esta
        #cambia.
        self.overlay.mascara_actualizada.connect(self._actualizar_mascara_propia)
        #IMPORTANTE: banner y panel son hijos de ESTE widget (self), NO de self.overlay -a propósito. En los pasos
        #informativos, el overlay
        #se vuelve WA_TransparentForMouseEvents=True para dejar pasar los
        #clics hacia la app real de abajo (nada que verificar, el usuario debe poder seguir usando la app con
        #libertad); pero en Qt, ese atributo en un widget hace que se ignore TODO su subárbol al decidir quién recibe
        #un clic -incluidos sus propios hijos. Si panel/banner fueran hijos del overlay, el botón "Continuar" del panel
        #dejaría de ser clicable justo en esos pasos (bug ya presente en el original, confirmado también ahí). Al
        #colgarlos de aquí, quedan totalmente al margen de esa transparencia y siguen recibiendo sus propios clics sin
        #importar el estado del overlay.
        self.banner= _BannerSandbox(self, main_window)
        self.panel= _PanelInstruccion(self, main_window)
        #"Continuar" (solo disponible en pasos informativos, sin acción real que verificar) SÍ cuenta como "terminar
        #esa parte correctamente" -el usuario llegó al final del paso y decidió avanzar-, así que celebra igual que un
        #paso con acción real
        #validada (ver _celebrar_paso_completado / _on_exito_reportado).
        #"Saltar este paso" es justo lo contrario -una renuncia explícita a completarlo- y por eso NO celebra ni fuerza
        #mostrar el panel.
        self.panel.siguiente.connect(self._avanzar_por_paso_completado)
        self.panel.saltar_paso.connect(self._avanzar_manual)
        self.panel.salir.connect(self._salir)
        self.panel.tamano_cambiado.connect(self._actualizar_mascara_propia)
        self.panel.arrastrado.connect(self._on_panel_arrastrado)
        #True en cuanto el usuario arrastra el panel a mano DURANTE el paso actual: mientras dure, _posicionar_panel
        #deja de recolocarlo
        #automáticamente (si no, cada reintento de _enganchar_boton -uno
        #por segundo mientras no aparece el botón- lo hubiera arrancado de donde el usuario lo puso). Se reinicia a
        #False en cada paso nuevo -ver _mostrar_paso_actual- para que el próximo paso vuelva a empezar con una posición
        #sensata por defecto.
        self._panel_movido_manualmente= False

        #--- Animación de entrada (solo la primera vez que se coloca el panel en su posición real, al arrancar el tour
        #-ver _posicionar_panel/_reproducir_animacion_entrada) --- Banner y panel SÍ se desplazan (deslizamiento suave)
        #además de tener fundido de opacidad -a diferencia de cualquier otro reposicionamiento posterior, que siempre
        #mueve panel/banner de golpe. Por eso _reproducir_animacion_entrada recalcula la máscara de este contenedor en
        #CADA cuadro (conectada a `valueChanged` de la animación de posición), no solo al final: la máscara depende del
        #`geometry()` real de panel y banner (ver _actualizar_mascara_propia), y si no se refrescara a cada paso
        #intermedio, se verían recortados visualmente a mitad del desplazamiento.
        self._animacion_entrada_pendiente= True
        self._efecto_overlay= QGraphicsOpacityEffect(self.overlay)
        self.overlay.setGraphicsEffect(self._efecto_overlay)
        self._efecto_banner= QGraphicsOpacityEffect(self.banner)
        self.banner.setGraphicsEffect(self._efecto_banner)
        self._efecto_panel= QGraphicsOpacityEffect(self.panel)
        self.panel.setGraphicsEffect(self._efecto_panel)

        self._boton_objetivo_actual= None
        self._intentos_boton= 0

        self._atajo_salir= QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._atajo_salir.activated.connect(self._salir)

        #Ctrl+H: oculta la ventanita de instrucciones para que no tape lo que el usuario tiene que tocar/llenar (sobre
        #todo en pasos con acción pendiente, donde la página queda agujereada y a veces el panel flota encima de un
        #campo del formulario). La misma tecla la vuelve a mostrar. Se usa una COMBINACIÓN (no una tecla suelta) a
        #propósito: en los pasos de formulario el usuario está escribiendo en campos de texto y una tecla simple como
        #"H" se la comería el atajo en vez de escribirse. Ctrl+H no está asignado a ningún atajo de ningún módulo (ver
        #atajos.py y los registrar_atajo del proyecto).
        self._panel_oculto= False
        self._atajo_panel= QShortcut(QKeySequence("Ctrl+H"), self)
        self._atajo_panel.activated.connect(self._alternar_panel)

        #El Buscador Global (Ctrl+F) abre un diálogo flotante que saca al usuario de la pantalla resaltada -si se
        #abriera a mitad de un paso con acción pendiente, el botón que el tutorial busca deja de estar visible y el
        #asistente se queda reintentando sin nunca encontrarlo. Se desactiva el QShortcut real (no basta con que el
        #tutorial "ignore" el evento: si no se desactiva, Ctrl+F igual abre el diálogo por su cuenta) mientras dure el
        #tour, y se restaura siempre al cerrar (ver _cerrar), se haya completado o no.
        self._atajo_buscador_global= getattr(main_window, "_atajo_buscador_global", None)
        if self._atajo_buscador_global is not None:
            self._atajo_buscador_global.setEnabled(False)

        #BUG: la franja naranja se dibujaba SOBRE el contenido real de la
        #app (encabezado del módulo, "Buenas noches", el logo de la barra
        #lateral...) en vez de empujarlo hacia abajo -este widget es un overlay flotante encima de main_window, no algo
        #que main_window sepa que debe "hacerle espacio". Se soluciona reduciendo, durante todo el tour, el layout del
        #contenedor central en la altura del banner -así el contenido real se recorre hacia abajo y nada queda tapado-
        #y restaurando el margen original al cerrar (ver _cerrar), sin asumir que ese margen siempre fue (0,0,0,0).
        self._layout_central= main_window.centralWidget().layout() if main_window.centralWidget() else None
        self._margenes_originales= self._layout_central.contentsMargins() if self._layout_central else None
        if self._layout_central is not None:
            m= self._margenes_originales
            self._layout_central.setContentsMargins(m.left(), m.top() + _BannerSandbox.ALTURA, m.right(), m.bottom())

        eventos_ui.exito_reportado.connect(self._on_exito_reportado)

        main_window.installEventFilter(self)
        self._listo= True
        self.show()
        self.raise_()
        #Coloca overlay/banner/panel con las medidas reales de la ventana AHORA que los tres ya existen -ver el
        #comentario largo arriba de este constructor sobre por qué ya no basta con confiar en que algún resizeEvent lo
        #haga por su cuenta.
        self._reposicionar()
        QTimer.singleShot(0, self._mostrar_paso_actual)

    #-------- ciclo de vida / reposicionamiento --------
    def _actualizar_mascara_propia(self):
        """Máscara de ESTE contenedor (AsistenteSpotlight) -independiente
        de la del overlay, aunque coherente con ella. Un hijo colocado
        dentro de una zona "agujero" de la máscara de su padre TAMPOCO
        recibe clics NI SE PINTA (se comprobó: el enmascarado excluye a
        todo el subárbol ahí, igual que WA_TransparentForMouseEvents) -por
        eso no basta con copiar la máscara del overlay tal cual: hay que
        garantizar que panel y banner, hijos de este widget, queden SIEMPRE
        dentro de la parte "sólida" (visible/clicable) de esta máscara, sin
        importar el estado bloqueante ni si su posición actual cae dentro
        del agujero de la página (pasos de formulario -ver más abajo)."""
        if self.size().isEmpty():
            return
        if self.overlay.bloqueante:
            #Sólido en todas partes salvo el agujero de acción real (si ya se localizó) -reforzando panel y banner como
            #sólidos siempre (ver el bloque de abajo): NO se puede asumir que caen fuera del agujero, porque en los pasos
            #de formulario el agujero es la página entera.
            #
            #BUG CORREGIDO: QWidget.mask() devuelve una QRegion VACÍA tanto si el overlay no tiene ninguna máscara puesta
            #(clearMask(), "visible en todas partes") como si se le puso explícitamente una máscara sin área ("visible en
            #NINGUNA parte") -mask() por sí sola no permite distinguir ambos casos. El código anterior copiaba
            #self.overlay.mask() tal cual sobre `self` sin importar cuál de los dos casos era; mientras el asistente
            #todavía no localiza la página/botón del paso (rect_agujero es None -algo que pasa en CADA cambio de paso, y
            #puede durar varios segundos si el módulo tarda en construirse), el overlay usa clearMask() con la intención de
            #"sin agujero, pero visible" -y ese
            #clearMask() se traducía, al copiarlo, en una máscara VACÍA
            #sobre este contenedor: como banner y panel son hijos de este
            #widget (no del overlay), quedaban con CERO área visible/
            #clicable -de ahí que "la ventanita de progreso" (y la franja naranja) simplemente no aparecieran durante ese
            #lapso. Ahora se usa el flag `tiene_agujero_real`, que sí distingue los dos casos, y se refleja la MISMA
            #distinción aquí: sin agujero real
            #todavía -> este contenedor tampoco debe llevar máscara.
            if self.overlay.tiene_agujero_real:
                #BUG: el comentario de arriba asume que el panel "siempre queda lejos del agujero", pero eso deja de ser cierto
                #en los pasos que piden llenar un formulario: ahí `rect_agujero` es la página ENTERA (ver _colocar_spotlight
                #-TODA la tarjeta del módulo, no solo el botón), así que el panel casi siempre termina posicionado ADENTRO de
                #esa zona "agujero" al calcularse en _posicionar_panel. Copiar la máscara del overlay tal cual entonces también
                #agujereaba a este contenedor exactamente ahí -y `setMask()` no solo bloquea clics, TAMBIÉN recorta el pintado:
                #el panel (y a veces el banner) simplemente dejaban de dibujarse, sin ningún error ni traceback. De ahí la
                #ventanita de instrucciones que "ni siquiera aparece" en varios pasos del Tutorial Detallado. La solución:
                #igual que en la rama no bloqueante de más abajo, se refuerza explícitamente el área de panel y banner como
                #"sólida" (uniéndola a la máscara del overlay) en vez de asumir que ya caen fuera.
                mascara= QRegion(self.overlay.mask())
                if self.panel.isVisible():
                    mascara= mascara.united(QRegion(self.panel.geometry()))
                if self.banner.isVisible():
                    mascara= mascara.united(QRegion(self.banner.geometry()))
                self.setMask(mascara)
            else:
                self.clearMask()
            return
        #No bloqueante: se deja pasar TODO clic hacia la app real de
        #abajo (nada que verificar en este paso), EXCEPTO sobre panel y
        #banner, que deben seguir siendo interactivos.
        bitmap= QBitmap(self.size())
        bitmap.fill(Qt.GlobalColor.color0)  #agujero por defecto: clics pasan a la app real
        pintor= QPainter(bitmap)
        pintor.setBrush(Qt.GlobalColor.color1)  #sólido = este widget conserva el clic aquí
        pintor.setPen(Qt.PenStyle.NoPen)
        if self.panel.isVisible():
            pintor.drawRect(self.panel.geometry())
        if self.banner.isVisible():
            pintor.drawRect(self.banner.geometry())
        pintor.end()
        self.setMask(QRegion(bitmap))

    def eventFilter(self, obj, event):
        if self._listo and event.type() in (event.Type.Resize, event.Type.Move):
            self._reposicionar()
        return False

    def resizeEvent(self, event):
        if self._listo:
            self._reposicionar()
        super().resizeEvent(event)

    def _reposicionar(self):
        self.setGeometry(self.main_window.rect())
        self.overlay.setGeometry(self.rect())
        self.banner.acomodar(self.width())
        self.banner.raise_()
        self._colocar_spotlight()

    #-------- navegación real por los módulos --------
    def _mostrar_paso_actual(self):
        self._boton_objetivo_actual= None
        #Deja cada pantalla EXACTAMENTE como estaba: si el paso anterior abrió a la fuerza un formulario colapsado para
        #encontrar su botón, se vuelve a cerrar antes de pasar al siguiente paso.
        self._restaurar_paneles_desplegables(getattr(self, "_paneles_expandidos_tutorial", None))
        self._paneles_expandidos_tutorial= None
        self._intentos_boton= 0
        self._panel_movido_manualmente= False  #cada paso arranca con posición automática
        self.overlay.establecer_objetivo(None)  #evita arrastrar el agujero del paso anterior
        if self.indice >= len(self.pasos):
            self._terminar()
            return
        #Las tuplas de 6 campos (todo lo escrito antes de esta mejora) siguen funcionando igual; el 7º campo
        #(`objetivo_fijo`) es opcional y solo lo usan los pasos nuevos que señalan un elemento FIJO de la barra lateral
        #(buscador, perfil, tema...) en vez de un botón dentro de un módulo -ver _rect_objetivo_fijo.
        paso= self.pasos[self.indice]
        icono, nombre_modulo, titulo, texto, texto_boton_objetivo, pestaña = paso[:6]
        objetivo_fijo= paso[6] if len(paso) > 6 else None
        self._objetivo_fijo_actual= objetivo_fijo
        self._accion_real_pendiente= texto_boton_objetivo is not None

        if nombre_modulo and nombre_modulo in self.main_window.modulos:
            fila= self.main_window.modulos.index(nombre_modulo)
            self.main_window.nav_list.setCurrentRow(fila)  #dispara cambiar_vista() -> carga el módulo real

        #BUG CORREGIDO: con nombre_modulo=None (pasos "de interfaz general",
        #sin módulo propio, o el paso de cierre) esto imprimía literalmente "Paso N de M · None" en el panel.
        if pestaña:
            etiqueta_paso= f"{nombre_modulo} · {pestaña}"
        elif nombre_modulo:
            etiqueta_paso= nombre_modulo
        else:
            etiqueta_paso= "AcaDeXI"
        self.panel.lbl_progreso.setText(f"Paso {self.indice + 1} de {len(self.pasos)} · {etiqueta_paso}")
        self.panel.barra_progreso.setMaximum(len(self.pasos))
        self.panel.barra_progreso.setValue(self.indice)
        self.panel.lbl_titulo.setText(titulo)
        self.panel.lbl_icono_titulo.setText(icono)
        aplicar_icono_cabecera(self.panel.lbl_icono_titulo, nombre_modulo, tamano=20)
        self.panel.lbl_texto.setText(texto)
        self.panel.lbl_completado.setVisible(False)
        self.panel.mostrar_ayuda("")

        #La regla de oro: "Continuar" SOLO existe cuando no hay nada que verificar. Si el paso pide una acción real, el
        #único botón visible además de "Salir" es "Saltar este paso" -avanzar de verdad requiere completar la acción de
        #verdad (ver _on_exito_reportado).
        self.panel.btn_siguiente.setVisible(not self._accion_real_pendiente)
        es_ultimo_paso= self.indice == len(self.pasos) - 1
        self.panel.btn_siguiente.setText("Finalizar " if es_ultimo_paso else "Continuar ")
        self.panel.btn_saltar_paso.setVisible(self._accion_real_pendiente)
        #Los pasos que señalan un elemento fijo (objetivo_fijo) también necesitan el overlay "bloqueante" -aunque no
        #esperen ninguna acción real- porque solo en ese modo se dibuja el recorte iluminado; si no, el usuario vería
        #el panel flotando sin ninguna pista de a qué se refiere (ver _OverlaySpotlight.paintEvent).
        self.overlay.establecer_bloqueante(self._accion_real_pendiente or bool(objetivo_fijo))
        self.panel.adjustSize()

        _guardar_progreso_sandbox(self.main_window, self.tipo, self.indice)

        #Da tiempo a que el módulo (si estaba en placeholder) termine de cargarse de verdad antes de tocar sus pestañas
        #o buscar el botón.
        QTimer.singleShot(150, lambda: self._preparar_pestana_y_boton(pestaña, texto_boton_objetivo))

    def _preparar_pestana_y_boton(self, pestaña, texto_boton_objetivo):
        pagina= self.main_window.stacked_widget.currentWidget()
        if pagina is None:
            return
        self._pagina_actual= pagina
        if pestaña:
            tabs= pagina.findChild(QTabWidget)
            if tabs is not None:
                objetivo_norm= pestaña.strip().lower()
                for i in range(tabs.count()):
                    if objetivo_norm in tabs.tabText(i).strip().lower():
                        tabs.setCurrentIndex(i)
                        break
            #Varios módulos construyen el contenido de la pestaña (o recargan sus combos) recién al seleccionarla -se le da
            #un respiro extra antes de buscar el botón dentro de ella.
            QTimer.singleShot(220, lambda: self._enganchar_boton(texto_boton_objetivo))
        else:
            self._enganchar_boton(texto_boton_objetivo)

    @staticmethod
    def _expandir_paneles_desplegables(pagina):
        """Si el botón objetivo de este paso vive dentro de un formulario
        colapsable (PanelDesplegable de calendario.py/horario.py -"Nueva
        tarea" de Banco de Tareas, "Agregar una clase local"
        de Horario, "Nuevo Módulo Técnico" de Politécnico, etc.-), hay que
        desplegarlo ANTES de buscar el botón: un panel colapsado oculta de
        verdad su contenido (ver PanelDesplegable.expandir), así que sin
        este paso el botón nunca aparecería visible y el tutorial se
        quedaría atascado ofreciendo "Saltar este paso" sin necesidad.

        Se detecta por duck-typing (tener a la vez `expandir` y
        `cuerpo_layout`) en vez de importar la clase concreta, porque hay
        más de una implementación de PanelDesplegable en el proyecto -misma
        interfaz, sin relación de herencia entre ellas- y así este motor de
        tutoriales no necesita conocerlas todas por nombre.

        Devuelve la lista de paneles que estaban CERRADOS y este método
        abrió, para que el asistente pueda devolverlos a su estado original
        al cambiar de paso (ver _restaurar_paneles_desplegables): el tour
        no debe dejar ninguna pantalla con proporciones distintas a las
        originales."""
        abiertos_por_el_tutorial= []
        for panel in pagina.findChildren(QWidget):
            if hasattr(panel, "expandir") and hasattr(panel, "cuerpo_layout"):
                try:
                    if getattr(panel, "_expandido", True) is False:
                        abiertos_por_el_tutorial.append(panel)
                    panel.expandir(True, animar=False)
                except Exception:
                    pass
        return abiertos_por_el_tutorial

    @staticmethod
    def _restaurar_paneles_desplegables(paneles):
        """Vuelve a CERRAR los paneles que el tutorial abrió a la fuerza:
        cada pestaña de cada módulo debe quedar exactamente igual a como
        estaba antes de que el recorrido pasara por ella."""
        for panel in paneles or []:
            try:
                panel.expandir(False, animar=False)
            except Exception:
                pass

    @staticmethod
    def _buscar_boton_por_texto(pagina, fragmento):
        """Busca, entre todos los QPushButton descendientes de `pagina` que
        estén VISIBLES ahora mismo, el primero cuyo texto contenga
        `fragmento` (sin distinguir mayúsculas). Se busca por texto y no por
        objectName porque varios botones "Guardar" del proyecto no tienen
        objectName asignado -el texto visible es lo único confiable en
        todos los módulos por igual. Al estar filtrando por isVisible(), en
        un QTabWidget esto automáticamente descarta los botones de
        pestañas que no son la actual (Qt las oculta)."""
        fragmento_norm= fragmento.strip().lower()
        for boton in pagina.findChildren(QPushButton):
            if not boton.isVisible():
                continue
            if fragmento_norm in boton.text().strip().lower():
                return boton
        return None

    def _enganchar_boton(self, texto_boton_objetivo):
        """Solo ubica y resalta el botón -ya NO se conecta a su `clicked`.
        `clicked` dispara aunque el módulo rechace el formulario (campos
        vacíos, matrícula duplicada...); la única confirmación válida de
        que la acción se completó de verdad es el aviso de éxito real que
        el propio módulo ya muestra tras guardar en la base de datos (ver
        _on_exito_reportado / iconos.eventos_ui)."""
        if not texto_boton_objetivo:
            self._colocar_spotlight()
            return
        pagina= self.main_window.stacked_widget.currentWidget()
        if pagina is None:
            return
        #Acumulamos en vez de reemplazar: este método se reintenta mientras el botón no aparece, y si el primer intento
        #ya abrió paneles que estaban cerrados, los siguientes intentos no deben perderlos de
        #vista (si no, quedarían expandidos para siempre tras el paso).
        nuevos= self._expandir_paneles_desplegables(pagina)
        previos= getattr(self, "_paneles_expandidos_tutorial", None) or []
        self._paneles_expandidos_tutorial= previos + [
            p for p in nuevos if not any(p is q for q in previos)]
        boton= self._buscar_boton_por_texto(pagina, texto_boton_objetivo)
        self._boton_objetivo_actual= boton
        self._colocar_spotlight()
        if boton is not None:
            return
        #No se encontró todavía (p. ej. falta elegir un combo primero, o el módulo sigue construyendo su contenido). Se
        #reintenta un par de veces con calma antes de ofrecer ayuda -nunca se deja al usuario atrapado sin ninguna
        #salida: "Saltar este paso" sigue disponible en todo momento.
        self._intentos_boton += 1
        if self._intentos_boton < self._INTENTOS_ANTES_DE_AYUDAR:
            QTimer.singleShot(1000, lambda: self._enganchar_boton(texto_boton_objetivo))
        else:
            self.panel.mostrar_ayuda(
                "¿No encuentras el botón? Puede que primero debas completar otro campo de esta "
                "pantalla, o usa 'Saltar este paso'.")

    @staticmethod
    def _es_descendiente(widget, ancestro):
        actual= widget
        vistos= 0
        while actual is not None and vistos < 50:
            if actual is ancestro:
                return True
            actual= actual.parentWidget() if hasattr(actual, "parentWidget") else None
            vistos += 1
        return False

    def _on_exito_reportado(self, parent, titulo, texto):
        """Único disparador real de avance en un paso con acción pendiente:
        un aviso de ÉXITO que el propio módulo mostró, y que ocurrió DENTRO
        de la página que el tutorial tiene resaltada ahora mismo (así un
        guardado exitoso en otra pantalla, si el usuario se saliera del
        recorrido, no hace avanzar un paso que no tiene nada que ver)."""
        if not getattr(self, "_accion_real_pendiente", False):
            return
        pagina= getattr(self, "_pagina_actual", None)
        if pagina is None or not self._es_descendiente(parent, pagina):
            return
        self._accion_real_pendiente= False  #evita doble avance si llegan dos avisos seguidos
        self.panel.lbl_completado.setVisible(True)
        self.panel.mostrar_ayuda("")
        self._celebrar_paso_completado()
        QTimer.singleShot(650, self._avanzar_manual)

    def _rect_objetivo_fijo(self):
        """Para pasos con `objetivo_fijo` (nombre de un atributo de
        main_window): localiza ese widget FIJO de la barra lateral -el
        buscador global, la tarjeta de perfil, el interruptor de tema...-
        que no vive dentro de ninguna página del stacked_widget, así que no
        tiene sentido buscarlo por texto de botón ni recortar "la página
        actual" para él. Devuelve None si el paso actual no usa este modo,
        o si el widget no existe/no está visible ahora mismo (p. ej. antes
        de iniciar sesión)."""
        nombre= self._objetivo_fijo_actual
        if not nombre:
            return None
        widget= getattr(self.main_window, nombre, None)
        if widget is None or not widget.isVisible():
            return None
        try:
            punto= widget.mapTo(self.main_window, widget.rect().topLeft())
            return QRect(punto, widget.size())
        except RuntimeError:
            return None

    def _colocar_spotlight(self):
        rect_fijo= self._rect_objetivo_fijo()
        if rect_fijo is not None:
            #Aquí el agujero y el marco de resaltado son el MISMO rect: no hay ningún formulario que llenar alrededor, solo
            #un elemento puntual de la barra lateral que se señala (y que de paso sigue siendo clicable/editable si el
            #usuario quiere probarlo).
            self.overlay.establecer_objetivo(rect_fijo)
            self._posicionar_panel(rect_fijo)
            return

        objetivo= self._boton_objetivo_actual
        rect_boton= None
        if objetivo is not None and objetivo.isVisible():
            try:
                punto= objetivo.mapTo(self.main_window, objetivo.rect().topLeft())
                rect_boton= QRect(punto, objetivo.size())
            except RuntimeError:
                rect_boton= None

        #El agujero interactivo real NO se limita al botón: si solo se abriera un hueco del tamaño de "Guardar", el
        #usuario podría tocar ese botón pero jamás escribir en los campos del formulario que se supone debía llenar
        #antes -Guardar entonces solo devuelve errores de validación, sin ninguna forma de corregirlos (bug reportado
        #en el Tutorial Detallado). Por eso el agujero cubre TODA la página del módulo actual
        #(main_window.stacked_widget.
        #currentWidget()) -el usuario puede tocar y escribir en cualquier
        #campo de esa pantalla-, mientras que el marco visual de resaltado se mantiene pequeño, alrededor del botón,
        #para seguir señalando cuál es la acción final. El resto de la ventana (menú lateral, cambiar de módulo, etc.)
        #sigue bloqueado, para que el usuario no se salga del recorrido.
        rect_agujero= rect_boton
        pagina_actual= self.main_window.stacked_widget.currentWidget()
        if pagina_actual is not None:
            try:
                punto_pagina= pagina_actual.mapTo(self.main_window, pagina_actual.rect().topLeft())
                rect_agujero= QRect(punto_pagina, pagina_actual.size())
            except RuntimeError:
                pass

        self.overlay.establecer_objetivo(rect_agujero, rect_boton)
        self._posicionar_panel(rect_boton)

    def _posicionar_panel(self, rect_referencia):
        """Coloca el panel de instrucción evitando taparse con el spotlight:
        a la derecha del objetivo si hay espacio, si no a la izquierda, y
        si tampoco cabe ahí (o no hay ningún objetivo que señalar, p. ej.
        mientras se busca el botón), en la esquina inferior derecha -NUNCA
        centrado sobre el contenido: un paso con acción pendiente suele
        agujerear la página ENTERA (ver _colocar_spotlight), así que
        "centrado abajo" terminaba tapando justo la tabla/lista que el
        usuario necesita ver para completar la acción (bug reportado).

        `rect_referencia` puede ser el botón resaltado, el widget fijo
        resaltado, o None (paso informativo, o acción cuyo botón aún no se
        localiza). Si el usuario ya arrastró el panel a mano en este mismo
        paso, se respeta esa posición -solo se recorta para que no quede
        fuera de la ventana si esta cambió de tamaño mientras tanto."""
        ancho_ventana= self.main_window.width()
        alto_ventana= self.main_window.height()
        ancho_panel= self.panel.width()
        alto_panel= self.panel.sizeHint().height()
        y_min= self.banner.height() + 12

        if self._panel_movido_manualmente:
            x= max(24, min(self.panel.x(), ancho_ventana - ancho_panel - 24))
            y= max(y_min, min(self.panel.y(), alto_ventana - alto_panel - 24))
        elif rect_referencia is not None and rect_referencia.right() + 24 + ancho_panel < ancho_ventana:
            x= rect_referencia.right() + 24
            y= max(y_min, min(rect_referencia.top(), alto_ventana - alto_panel - 24))
        elif rect_referencia is not None and rect_referencia.left() - 24 - ancho_panel > 0:
            x= rect_referencia.left() - 24 - ancho_panel
            y= max(y_min, min(rect_referencia.top(), alto_ventana - alto_panel - 24))
        else:
            #Sin objetivo localizado (o sin espacio a los lados): esquina inferior derecha, lejos del centro, para no
            #interrumpir la visibilidad de lo que el usuario tiene que hacer.
            x= ancho_ventana - ancho_panel - 24
            y= alto_ventana - alto_panel - 24
        y= max(y, y_min)
        if self._animacion_entrada_pendiente:
            self._animacion_entrada_pendiente= False
            self.panel.raise_()
            self.banner.raise_()
            self._reproducir_animacion_entrada(x, y)
        else:
            self.panel.move(x, y)
            self.panel.raise_()
            self.banner.raise_()
            self._actualizar_mascara_propia()  #el panel ya está en su posición final

    def _reproducir_animacion_entrada(self, x_panel, y_panel):
        """Entrada en cascada al arrancar el Tutorial Detallado: primero se
        oscurece el overlay, después la franja naranja se desliza desde
        arriba, y por último el panel de instrucciones se desliza desde un
        poco más abajo -cada pieza con su propio fundido de opacidad al
        mismo tiempo. Solo ocurre una vez por tour (ver el flag en
        __init__), nunca al cambiar de paso.

        Se usa QEasingCurve.OutQuint (desaceleración larga y pareja, sin
        ningún rebote/overshoot) para que se sienta suave y elegante, no
        "juguetón" -a diferencia de un OutBack, que llegaría a pasarse del
        destino antes de asentarse.

        Importante: como panel y banner SÍ cambian de posición durante
        este efecto (a diferencia del resto de la app, donde su geometría
        es fija entre reposicionamientos), la máscara de este contenedor
        -que depende de su `geometry()` real, ver _actualizar_mascara_propia-
        se recalcula en CADA cuadro de la animación (conectado a
        `valueChanged`), no solo al final; si no, se verían recortados
        visualmente a mitad de camino."""
        duracion_overlay= 380
        duracion_pieza= 460
        curva_fundido= QEasingCurve.Type.OutCubic
        curva_deslizamiento= QEasingCurve.Type.OutQuint

        #--- Overlay: solo un fundido (el fondo oscurecido no se desplaza) ---
        self._efecto_overlay.setOpacity(0.0)
        self._anim_entrada_overlay= QPropertyAnimation(self._efecto_overlay, b"opacity", self)
        self._anim_entrada_overlay.setDuration(duracion_overlay)
        self._anim_entrada_overlay.setStartValue(0.0)
        self._anim_entrada_overlay.setEndValue(1.0)
        self._anim_entrada_overlay.setEasingCurve(curva_fundido)

        #--- Banner: se desliza desde arriba de la ventana + fundido ---
        punto_inicio_banner= QPoint(0, -self.banner.height())
        self.banner.move(punto_inicio_banner)
        self._efecto_banner.setOpacity(0.0)
        self._anim_entrada_banner_pos= QPropertyAnimation(self.banner, b"pos", self)
        self._anim_entrada_banner_pos.setDuration(duracion_pieza)
        self._anim_entrada_banner_pos.setStartValue(punto_inicio_banner)
        self._anim_entrada_banner_pos.setEndValue(QPoint(0, 0))
        self._anim_entrada_banner_pos.setEasingCurve(curva_deslizamiento)
        self._anim_entrada_banner_pos.valueChanged.connect(self._actualizar_mascara_propia)
        self._anim_entrada_banner_fade= QPropertyAnimation(self._efecto_banner, b"opacity", self)
        self._anim_entrada_banner_fade.setDuration(duracion_pieza)
        self._anim_entrada_banner_fade.setStartValue(0.0)
        self._anim_entrada_banner_fade.setEndValue(1.0)
        self._anim_entrada_banner_fade.setEasingCurve(curva_fundido)

        #--- Panel: se desliza desde un poco más abajo de su posición final + fundido -el más notorio de los tres, así
        #que es el último en llegar, para que la mirada lo siga con naturalidad ---
        punto_inicio_panel= QPoint(x_panel, y_panel + 32)
        self.panel.move(punto_inicio_panel)
        self._efecto_panel.setOpacity(0.0)
        self._anim_entrada_panel_pos= QPropertyAnimation(self.panel, b"pos", self)
        self._anim_entrada_panel_pos.setDuration(duracion_pieza)
        self._anim_entrada_panel_pos.setStartValue(punto_inicio_panel)
        self._anim_entrada_panel_pos.setEndValue(QPoint(x_panel, y_panel))
        self._anim_entrada_panel_pos.setEasingCurve(curva_deslizamiento)
        self._anim_entrada_panel_pos.valueChanged.connect(self._actualizar_mascara_propia)
        self._anim_entrada_panel_pos.finished.connect(self._actualizar_mascara_propia)
        self._anim_entrada_panel_fade= QPropertyAnimation(self._efecto_panel, b"opacity", self)
        self._anim_entrada_panel_fade.setDuration(duracion_pieza)
        self._anim_entrada_panel_fade.setStartValue(0.0)
        self._anim_entrada_panel_fade.setEndValue(1.0)
        self._anim_entrada_panel_fade.setEasingCurve(curva_fundido)

        self._anim_entrada_overlay.start()
        QTimer.singleShot(110, self._anim_entrada_banner_pos.start)
        QTimer.singleShot(110, self._anim_entrada_banner_fade.start)
        QTimer.singleShot(200, self._anim_entrada_panel_pos.start)
        QTimer.singleShot(200, self._anim_entrada_panel_fade.start)

    def _alternar_panel(self):
        """Ctrl+H: oculta la ventanita de instrucciones (y la trae de vuelta
        con la misma tecla). El estado se mantiene entre pasos del tour: si
        el usuario la ocultó, sigue oculta hasta que él mismo la vuelva a
        mostrar — así puede completar tranquilo una acción de varios campos
        sin que el panel reaparezca a mitad de camino. Nada más depende de
        la visibilidad del panel: el overlay, el banner y el progreso del
        paso siguen funcionando igual (ver _actualizar_mascara_propia, que
        ya trata al panel invisible como "sin área sólida extra")."""
        self._panel_oculto= not self._panel_oculto
        if self._panel_oculto:
            self.panel.hide()
        else:
            self.panel.show()
            #Reposiciona/valida que quede dentro de la ventana (por si esta cambió de tamaño mientras estuvo oculta) y por
            #encima de todo.
            self._colocar_spotlight()
        self._actualizar_mascara_propia()

    def _celebrar_paso_completado(self):
        """Se dispara cada vez que una parte del Tutorial Detallado se
        completa CORRECTAMENTE -acción real validada por
        `_on_exito_reportado`, o paso informativo confirmado con
        "Continuar" (ver _avanzar_por_paso_completado)-, nunca al usar
        "Saltar este paso". Dos cosas:

        1) Si el usuario había ocultado la ventanita de instrucciones con
           Ctrl+H (ver _alternar_panel), se vuelve a mostrar sin esperar a
           que él mismo la reactive: ya se acabó el motivo por el que la
           ocultó (tapar un campo mientras llenaba el formulario de ESTE
           paso), y así no se pierde el "¡Bien hecho!" ni el progreso
           actualizado, y el próximo paso arranca con la ventanita visible
           en vez de dejarla oculta "para siempre" por inercia.
        2) Lanza una animación breve de confeti (ver _ConfettiOverlay) a
           modo de celebración visual.
        """
        if self._panel_oculto:
            self._panel_oculto= False
            self.panel.show()
            #Igual que en _alternar_panel: reposiciona/valida que quede dentro de la ventana y refresca la máscara, por si
            #el tamaño de la ventana cambió mientras el panel estuvo oculto.
            self._colocar_spotlight()
            self._actualizar_mascara_propia()
        _ConfettiOverlay(self)

    def _avanzar_por_paso_completado(self):
        """Puente para la señal `siguiente` del panel (botón "Continuar",
        solo en pasos informativos): a diferencia de "Saltar este paso",
        SÍ cuenta como terminar la parte correctamente."""
        self._celebrar_paso_completado()
        self._avanzar_manual()

    def _on_panel_arrastrado(self):
        """El usuario está moviendo el panel a mano: deja de recolocarse
        solo (ver _posicionar_panel) y su nueva posición debe seguir
        siendo visible/clicable de inmediato -por eso se refresca la
        máscara en cada tick del arrastre, no solo al soltar."""
        self._panel_movido_manualmente= True
        self.panel.raise_()
        self._actualizar_mascara_propia()

    #-------- avance / salida --------
    def _avanzar_manual(self):
        self.indice += 1
        self._mostrar_paso_actual()

    def _salir(self):
        #Salir a medias no rompe nada ni pierde datos ya guardados por el usuario en los pasos reales que sí completó:
        #el sandbox (con ese trabajo ya hecho) y el paso alcanzado se conservan en disco, para retomar justo ahí la
        #próxima vez -no se marca el tutorial como "visto", así que se le seguirá ofreciendo.
        self._cerrar(borrar_sandbox=False)

    def _terminar(self):
        if self.tipo == "general":
            marcar_tutorial_general_visto(self.main_window, True)
        else:
            marcar_tutorial_docente_visto(self.main_window, True)
        self._cerrar(borrar_sandbox=True, volver_a_dashboard=True)

    def _cerrar(self, borrar_sandbox, volver_a_dashboard=False):
        #Al salir del tour (completo o a medias), ninguna pantalla debe quedar con proporciones distintas a las
        #originales: se cierran los paneles que el tutorial abrió a la fuerza en el paso actual.
        self._restaurar_paneles_desplegables(getattr(self, "_paneles_expandidos_tutorial", None))
        self._paneles_expandidos_tutorial= None
        try:
            eventos_ui.exito_reportado.disconnect(self._on_exito_reportado)
        except (TypeError, RuntimeError):
            pass
        try:
            self.main_window.removeEventFilter(self)
        except Exception:
            pass
        if self._layout_central is not None:
            m= self._margenes_originales
            self._layout_central.setContentsMargins(m.left(), m.top(), m.right(), m.bottom())
        if self._atajo_buscador_global is not None:
            self._atajo_buscador_global.setEnabled(True)
        #SIEMPRE se restaura, se haya completado o no: en el instante en que esta ventana de tutorial se cierra, el
        #resto de la app (y todo lo que el usuario guarde después) tiene que volver a escribir en la base de datos
        #real, nunca seguir apuntando a la copia de práctica.
        _restaurar_bd_real(borrar_sandbox, self.main_window, self.tipo)
        #Al completar el tour (nunca al salir a medias, ver _salir) se devuelve al usuario al Dashboard: después de 44
        #pasos saltando de módulo en módulo, es fácil terminar en cualquier pantalla -mejor un punto de partida
        #conocido y neutral que dejarlo donde sea que haya quedado el último paso. Se hace DESPUÉS de restaurar la BD
        #real (arriba), no antes: si el Dashboard se recargara todavía
        #apuntando al sandbox, mostraría los números de práctica en vez de los reales. Y se fuerza `cambiar_vista`
        #explícitamente además de `setCurrentRow`, porque si el Dashboard YA era el módulo visible antes de terminar el
        #tour, cambiar la fila seleccionada a la misma que ya estaba no dispara `currentRowChanged` -y sin eso,
        #`pagina.refrescar()` nunca se llama y se seguirían viendo los datos de práctica aunque la BD ya esté
        #restaurada.
        if volver_a_dashboard and "Dashboard" in self.main_window.modulos:
            fila_dashboard= self.main_window.modulos.index("Dashboard")
            self.main_window.nav_list.setCurrentRow(fila_dashboard)
            self.main_window.cambiar_vista(fila_dashboard)
        self.finalizado.emit()
        self.deleteLater()


#ORQUESTADOR — llamado desde main.py (mostrar_login) y desde Configuración ▸ Mi Cuenta ("Ver tutorial de
#nuevo")
def _modulo_visible_ahora(main_window, nombre):
    """Fuente de verdad REAL de qué módulos ve este usuario ahora mismo.

    Antes se repetía aquí la regla de permisos.modulo_visible(rol, nombre),
    que solo mira la tabla ACCESO_MODULOS por rol -y por eso se quedaba
    corta en varios casos reales: no sabe si "Politécnico"/"Universidad"
    existen para el tipo de institución configurado (main_window solo
    agrega esos módulos a self.modulos si corresponde -ver
    main._construir_modulos_info), no sabe si un Profesor activó su
    preferencia personal de "Calificaciones Técnicas", y no sabe si
    "Copias de Seguridad" está encendido para roles gerenciales (un
    interruptor aparte, ver mostrar_backups_gerenciales()). Como resultado,
    el tour podía anunciar un paso de "Politécnico" en una institución que
    ni siquiera tiene ese módulo -y quedarse sin poder navegar a ningún
    lado, muy confuso.

    Preguntarle directamente al menú lateral YA CONSTRUIDO (main_window.
    nav_list, ya actualizado por _aplicar_permisos_por_rol() antes de
    ofrecer cualquier tutorial -ver mostrar_login() en main.py) es la única
    forma de que el tutorial nunca se desincronice de esas reglas, estén
    donde estén definidas: si el usuario no lo ve en el menú, el tutorial
    tampoco se lo ofrece; si lo ve, se lo ofrece.

    `nombre=None` identifica los pasos "de interfaz general" (buscador,
    perfil, tema...) y el paso de cierre: no pertenecen a ningún módulo
    del menú, así que son visibles para todos siempre."""
    if nombre is None:
        return True
    modulos= getattr(main_window, "modulos", None)
    nav_list= getattr(main_window, "nav_list", None)
    if not modulos or nav_list is None:
        #Sin ventana real construida todavía (p. ej. algún test unitario que arma un main_window mínimo): no se
        #descarta nada por defecto.
        return modulo_visible(getattr(main_window, "rol_actual", None), nombre)
    if nombre not in modulos:
        return False
    item= nav_list.item(modulos.index(nombre))
    return item is not None and not item.isHidden()


def _filtrar_contenido(main_window, lista):
    return [t for t in lista if _modulo_visible_ahora(main_window, t[1])]


def _filtrar_pasos(main_window, lista):
    return [p for p in lista if _modulo_visible_ahora(main_window, p[1])]


def _lanzar(main_window, tipo, titulo_carrusel, contenido_rapido, pasos_detallado, marcar_visto):
    #El rol Estudiante no tiene el módulo "Configuración" en su menú (ver permisos.ACCESO_MODULOS), así que no
    #puede relanzarlo manualmente; por eso el texto de la pantalla de elección varía según el rol. En cualquier
    #caso, la oferta SOLO se hace una vez por usuario: el flag se marca al completar, al saltar o incluso al salir
    #a medias del
    #detallado (ver más abajo).
    puede_repetir_manualmente= _modulo_visible_ahora(main_window, "Configuración")
    texto_repetir= (
        "Puedes verlo ahora en el modo que prefieras, o saltarlo — siempre podrás repetirlo desde "
        "Configuración ▸ Mi Cuenta." if puede_repetir_manualmente else
        "Puedes verlo ahora en el modo que prefieras, o saltarlo por esta vez."
    )
    dialogo_eleccion= PantallaEleccionTutorial(
        main_window, "¿Quieres un recorrido por AcaDeXI?", texto_repetir,
        mostrar_detallado=bool(pasos_detallado))
    dialogo_eleccion.exec()
    eleccion= dialogo_eleccion.resultado

    if eleccion == PantallaEleccionTutorial.RAPIDO:
        TutorialRapidoDialog(main_window, contenido_rapido, titulo_carrusel).exec()
        marcar_visto(main_window, True)
    elif eleccion == PantallaEleccionTutorial.DETALLADO:
        if not _activar_sandbox(main_window, tipo):
            mostrar_mensaje(
                "advertencia", "No se pudo preparar el modo práctica",
                "El Tutorial Detallado necesita crear una copia temporal de la base de datos para "
                "practicar sin afectar tus datos reales, y no se pudo crear ahora mismo (revisa el "
                "espacio en disco o los permisos de la carpeta de datos de AcaDeXI). Puedes intentarlo "
                "de nuevo más tarde desde Configuración ▸ Mi Cuenta, o usar el Modo Rápido mientras tanto.",
                main_window)
            return
        #A partir de aquí bd.DB_PATH ya apunta al sandbox: el asistente solo tiene que navegar y validar, no le
        #concierne dónde escribe
        #obtener_conexion().
        asistente= AsistenteSpotlight(main_window, pasos_detallado, tipo)
        #El tutorial solo se RECOMIENDA una vez por usuario: aunque se salga del recorrido a medias, al cerrarse el
        #asistente (finalizado se emite tanto al completar como al salir) se marca como "visto". La señal llega DESPUÉS
        #de que _cerrar restauró la BD real, así que el flag se escribe en la base de verdad y no en la copia de
        #práctica. Sigue pudiendo repetirse manualmente desde Configuración ▸ Mi Cuenta.
        asistente.finalizado.connect(lambda: marcar_visto(main_window, True))
        #Completarlo lo marca igualmente (ver _terminar); ya sea completado o abandonado, el resultado es el mismo: se
        #ofreció una sola vez.
    elif eleccion == PantallaEleccionTutorial.SALTAR:
        #"Saltar por ahora": se marca como visto SIEMPRE (también para el rol Estudiante, que no puede repetirlo
        #manualmente desde Configuración): el tutorial se RECOMIENDA una sola vez por usuario. Si el rol puede
        #repetirlo manualmente, queda accesible en Configuración ▸ Mi Cuenta.
        marcar_visto(main_window, True)


def ofrecer_tutorial(main_window, tipo, forzar=False):
    """tipo: "general", "docente", "single_teacher" o "side_stepper". Si
    `forzar=True` (botón "Ver tutorial de nuevo" en Configuración), se
    muestra sin importar el flag de "visto".

    El rol Estudiante usa tipo="general" también (mismo flag de "visto" por
    cuenta, mismo mecanismo de sandbox/elección) pero con SU PROPIO
    contenido -CONTENIDO_ESTUDIANTE/PASOS_ESTUDIANTE-, ya que es de solo
    lectura: no tendría sentido pedirle "agrega un estudiante de prueba" a
    quien no puede escribir nada en el sistema (ver permisos.puede_editar)."""
    if tipo == "general":
        if not forzar and tutorial_general_visto(main_window):
            return
        rol= getattr(main_window, "rol_actual", None)
        if rol == "Estudiante":
            contenido_base, pasos_base = CONTENIDO_ESTUDIANTE, PASOS_ESTUDIANTE
        else:
            contenido_base, pasos_base = CONTENIDO_GENERAL, PASOS_GENERAL
        contenido= _filtrar_contenido(main_window, contenido_base)
        pasos= _filtrar_pasos(main_window, pasos_base)
        _lanzar(main_window, "general", "Tutorial General de AcaDeXI", contenido, pasos,
                marcar_tutorial_general_visto)
    elif tipo == "docente":
        if not forzar and tutorial_docente_visto(main_window):
            return
        contenido= _filtrar_contenido(main_window, CONTENIDO_DOCENTE)
        pasos= _filtrar_pasos(main_window, PASOS_DOCENTE)
        _lanzar(main_window, "docente", "Tutorial del Sistema", contenido, pasos,
                marcar_tutorial_docente_visto)
    elif tipo == "single_teacher":
        if not forzar and tutorial_single_teacher_visto(main_window):
            return
        #Sin _filtrar_contenido/_filtrar_pasos a propósito: ver el docstring de CONTENIDO_SINGLE_TEACHER más arriba.
        _lanzar(main_window, "single_teacher", "Bienvenido a AcaDeXI Single Teacher",
                CONTENIDO_SINGLE_TEACHER, PASOS_SINGLE_TEACHER, marcar_tutorial_single_teacher_visto)
    elif tipo == "side_stepper":
        if not forzar and tutorial_side_stepper_visto(main_window):
            return
        #Side Stepper SÍ reutiliza el filtrado dinámico normal: comparte el esquema/UI de bd.py con Full Institutional,
        #así que el menú ya refleja exactamente los módulos que permisos.
        #obtener_permisos_side_stepper() le otorgó a este rol (ver
        #permisos.modulo_visible). Reutilizar CONTENIDO_GENERAL/ PASOS_GENERAL como base, filtrados, da automáticamente
        #"el contenido correcto para lo que esta persona puede ver".
        contenido= _filtrar_contenido(main_window, CONTENIDO_GENERAL)
        pasos= _filtrar_pasos(main_window, PASOS_GENERAL)
        _lanzar(main_window, "side_stepper", "Bienvenido a AcaDeXI Side Stepper", contenido, pasos,
                marcar_tutorial_side_stepper_visto)


def ofrecer_tutoriales_tras_login(main_window):
    """Punto de enganche único desde mostrar_login(): decide cuál(es) par(es)
    ofrecer según el rol Y la edición, respetando que son independientes
    entre sí. Single Teacher y Side Stepper se resuelven por EDICIÓN, antes
    que por rol: un Side Stepper con un rol personalizado (ver permisos.py)
    no necesariamente coincide con ROLES_GERENCIALES/"Administrativo", así
    que decidir por edición primero es lo único que no se queda corto con
    un rol nuevo que la app no anticipó."""
    _limpiar_sandboxes_huerfanos()
    try:
        from src.nucleo.edicion import edicion_actual
        edicion= edicion_actual()
    except Exception:
        edicion= "full"

    if edicion == "single_teacher":
        ofrecer_tutorial(main_window, "single_teacher")
        return
    if edicion == "side_stepper":
        ofrecer_tutorial(main_window, "side_stepper")
        return

    rol= getattr(main_window, "rol_actual", None)
    if rol == "Profesor":
        ofrecer_tutorial(main_window, "docente")
    if rol in ROLES_GERENCIALES or rol in ("Administrativo", "Estudiante"):
        ofrecer_tutorial(main_window, "general")
