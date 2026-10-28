#iconos_auto.py — Iconización AUTOMÁTICA y coherente de toda la app.
#
#Problema que resuelve
# -----------------------------------------
# los iconos vectoriales de `iconos_emoji.py` se asignan a mano, llamada por
# -----------------------------------------
#llamada. Eso inevitablemente deja huecos: botones creados dinámicamente,
#diálogos sin icono de ventana, pestañas sin icono, módulos nuevos que se
#olvidan de llamar a `icono_emoji`... y mapas de palabras duplicados por
#archivo que derivan en iconos INCOHERENTES entre módulos (el mismo botón
#"Exportar" con dibujos distintos según la ventana).
#
#Solución
#Un único filtro de eventos instalado sobre la QApplication. Cada vez que un
#widget se pule (evento Polish/Show) o cambia su texto, se le asigna el icono
#que corresponde según SU TEXTO, usando UN SOLO mapa semántico compartido por
#toda la app. Así:
#
#- No existe botón, pestaña o diálogo sin icono (cobertura total).
#- "Guardar" se ve IGUAL en todos los módulos (coherencia total).
#- Los módulos nuevos quedan iconizados sin escribir ni una línea.
#
#Uso (desde main.py, una sola vez):
#from iconos_auto import instalar_iconos_automaticos
#instalar_iconos_automaticos(app)
#
#Las llamadas explícitas a `icono_emoji(...)` de los módulos siguen teniendo
#prioridad visual: el filtro NUNCA sobreescribe un icono ya asignado (solo
#rellena los que están vacíos).
import re
import unicodedata

from PySide6.QtCore import QObject, QEvent, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QPushButton, QToolButton, QDialog, QMessageBox,
                               QMainWindow, QTabWidget)
from src.nucleo.iconos_emoji import EMOJI_IMPORTAR, EMOJI_EXPORTAR

TAM_ICONO= QSize(18, 18)

#Mapa semántico único (normalizado: minúsculas, sin tildes). Orden = prioridad: primero las acciones concretas,
#después los sustantivos. Todo apunta a dibujos existentes en iconos_emoji.
_MAPA= [
    ('guardar', '💾'), ('eliminar', '🗑'), ('borrar', '🗑'),
    ('quitar', '🗑'), ('suprimir', '🗑'),
    ('limpiar', '🧹'), ('vaciar', '🧹'), ('despejar', '🧹'),
    ('duplicar', '📋'), ('copiar', '📋'), ('pegar', '📋'),
    ('editar', '✏'), ('modificar', '✏'),
    ('crear', '➕'), ('agregar', '➕'), ('anadir', '➕'), ('nuevo', '➕'),
    ('restaurar', '♻'), ('restablecer', '♻'), ('recuperar', '♻'),
    ('actualizar', '🔄'), ('recargar', '🔄'), ('refrescar', '🔄'),
    ('verificar', '🔄'), ('comprobar', '🔄'), ('sincronizar', '🔄'),
    #'importar'/'exportar' (y sinónimos) usan el icono dedicado de bandeja con flecha
    #(EMOJI_IMPORTAR/EMOJI_EXPORTAR, ver iconos_emoji.py), NO el sobre de correo (📥/📤): ese sobre es el mismo
    #dibujo que usa el icono real de "correo/email" más abajo, y mezclaba "traer/enviar datos" con "enviar un
    #correo" en cualquier botón que no trajera su propio icono.
    ('importar', EMOJI_IMPORTAR), ('descargar', EMOJI_IMPORTAR),
    ('exportar', EMOJI_EXPORTAR), ('subir', EMOJI_EXPORTAR),
    ('cargar', '📂'), ('examinar', '📁'), ('carpeta', '📁'), ('abrir', '📂'),
    ('filtr', '\uE000'), ('buscar', '🔍'), ('busqueda', '🔍'), ('lupa', '🔍'),
    ('imprimir', '🖨'), ('pdf', '📄'), ('csv', '📊'), ('excel', '📊'),
    ('respaldo', '🛡'), ('backup', '🛡'), ('copia de seguridad', '🛡'),
    ('reparar', '🛠'), ('diagnostico', '🧪'), ('probar', '⚡'),
    ('comprimir', '📦'), ('paquete', '📦'),
    ('cancelar', '✖'), ('descartar', '✖'),
    ('salir', '✖'), ('cerrar sesion', '🚪'),
    ('iniciar sesion', '🔑'), ('acceder', '🔑'), ('login', '🔑'), ('entrar', '🔑'),
    ('aplicar', '✅'), ('confirmar', '✔'), ('aceptar', '✔'),
    ('atras', '⬅'), ('anterior', '⬅'), ('siguiente', '➡'), ('avanzar', '➡'),
    ('volver', '↩'), ('finalizar', '🏁'), ('terminar', '🏁'),
    ('empezar', '🚀'), ('comenzar', '🚀'), ('iniciar', '🚀'),
    ('paso', '🧭'), ('wizard', '🧭'), ('asistente', '🧭'),
    ('expandir', '🔽'), ('colapsar', '🔽'),
    ('contrasena', '🔒'), ('pass', '🔑'), ('clave', '🔑'), ('candado', '🔒'),
    ('bloquear', '🔒'), ('desbloquear', '🔓'), ('permiso', '🔑'),
    ('seguridad', '🛡'), ('privacidad', '🛡'), ('auditor', '🛡'),
    #---- personas ----
    ('usuario', '👤'), ('perfil', '👤'), ('cuenta', '👤'), ('rol', '👤'),
    ('docente', '🧑'), ('profesor', '👥'), ('personal', '👥'),
    ('estudiante', '🎓'), ('alumno', '🎓'), ('matricula', '🎓'),
    ('inscribir', '🎓'), ('inscripcion', '🎓'),
    ('familia', '🏠'), ('acudiente', '🏠'), ('representante', '🏠'),
    #---- académico ----
    ('materia', '📘'), ('asignatura', '📘'), ('area', '📘'),
    ('curso', '📚'), ('grado', '📚'), ('nivel', '📚'),
    ('seccion', '🏫'), ('aula', '🏫'), ('sala', '🏫'),
    ('universidad', '🏛'), ('institucion', '🏛'), ('colegio', '🏛'),
    ('escuela', '🏫'), ('politecnico', '🏫'),
    ('horario', '📅'), ('calendario', '📅'), ('agenda', '📅'), ('fecha', '📅'),
    ('anio escolar', '📆'), ('anio', '📆'),
    ('periodo', '🗓'), ('lapso', '🗓'), ('trimestre', '🗓'),
    ('nota', '📈'), ('calificacion', '📊'), ('evaluacion', '📊'),
    ('promedio', '📈'), ('boletin', '📄'), ('libreta', '📄'),
    ('competencia', '🎯'), ('objetivo', '🎯'), ('meta', '🎯'),
    ('desempeno', '📈'), ('logro', '🏆'), ('exito', '🏆'), ('premio', '🏆'),
    ('felicitar', '🎉'), ('felicitacion', '🎉'), ('celebrar', '🎉'),
    ('asistencia', '✅'), ('inasistencia', '❌'), ('ausencia', '❌'),
    ('tardanza', '🕐'), ('retraso', '🕐'),
    ('recordatorio', '🔔'), ('alarma', '🔔'), ('campana', '🔔'),
    ('alerta', '🚨'), ('aviso', '🔔'), ('notificacion', '🔔'),
    ('observacion', '🗒'), ('anotacion', '📝'), ('comentario', '📝'),
    ('tarea', '📋'), ('actividad', '📋'), ('plan', '📋'),
    ('examen', '📝'), ('quiz', '📝'),
    ('reporte', '📊'), ('informe', '📊'), ('estadistic', '📊'),
    ('grafic', '📊'), ('resumen', '📊'), ('indicador', '📊'),
    ('historial', '🕒'), ('registro', '📇'), ('bitacora', '📇'),
    ('constancia', '📜'), ('certificado', '📜'), ('diploma', '📜'),
    ('acta', '📜'), ('documento', '📄'), ('archivo', '📁'),
    ('plantilla', '📄'), ('formato', '📄'), ('firma', '✍'),
    #---- configuración / sistema / varios ----
    ('configuracion', '⚙'), ('ajustes', '⚙'), ('preferencia', '⚙'),
    ('opciones', '⚙'), ('herramienta', '🧰'),
    ('idioma', '🔤'), ('fuente', '🔤'), ('texto', '🔤'),
    ('tema', '🎨'), ('apariencia', '🎨'), ('color', '🎨'), ('estilo', '🎨'),
    ('accesibilidad', '👁'), ('vista previa', '👁'), ('previsualizar', '👁'),
    ('detalle', '👁'), ('ver ', '👁'), ('mostrar', '👁'), ('ocultar', '🙈'),
    ('nube', '☁'), ('drive', '☁'), ('onedrive', '☁'), ('dropbox', '☁'),
    ('conectar', '🔌'), ('desconectar', '🔌'), ('conexion', '🔌'), ('red', '🔌'),
    ('servidor', '🖥'), ('equipo', '🖥'), ('sistema', '🖥'),
    ('base de datos', '🗄'),
    ('correo', '✉'), ('email', '✉'), ('mensaje', '✉'), ('sms', '✉'),
    ('telefono', '📞'), ('llamada', '📞'), ('contacto', '📇'),
    ('foto', '🖼'), ('imagen', '🖼'), ('logo', '🖼'), ('camara', '📷'),
    ('ayuda', '💡'), ('tutorial', '💡'), ('guia', '💡'), ('sugerencia', '💡'),
    ('idea', '💡'), ('consejo', '💡'),
    ('ubicacion', '📍'), ('direccion', '📍'), ('mapa', '🗺'),
    ('enlace', '🔗'), ('link', '🔗'), ('web', '🔗'),
    ('velocidad', '⚡'), ('rendimiento', '⚡'), ('energia', '⚡'),
    ('advertencia', '⚠'), ('peligro', '⚠'), ('precaucion', '⚠'),
    ('error', '🚨'), ('emergencia', '🚨'), ('critico', '🚨'),
    ('prohibido', '⛔'), ('bloqueado', '⛔'),
    ('peso', '⚖'), ('equivalencia', '⚖'),
    ('dinero', '💼'), ('pago', '💼'), ('factura', '💼'), ('presupuesto', '💼'),
    ('agua', '💧'), ('clima', '🌤'), ('salir', '✖'), ('cerrar', '✖'),

    #---- ampliaciones (huecos detectados: módulos/botones sin ningún keyword que los cubriera) — se agregan AL
    #FINAL para no adelantarse en prioridad a ningún grupo ya existente arriba ----
    ('panel', '▦'), ('dashboard', '▦'),
    ('sincronizacion', '🔄'),
    ('vincular', '🔗'), ('desvincular', '🔌'),
    ('pasantia', '💼'), ('empresa', '🏢'),
    ('buscador', '🔍'),
    ('malla curricular', '📚'), ('facultad', '🏛'), ('carrera', '🎓'),
    ('honor', '🏆'),
    ('taller', '🛠'), ('laboratorio', '🧪'),
    ('entrega', EMOJI_IMPORTAR), ('calificar', '📊'),
    ('deshacer', '↩'), ('reemplazar', '🔄'), ('insertar', '➕'),
    ('saltar', '➡'), ('entendido', '✔'), ('continuar', '➡'),
    ('autorizacion', '🔑'),
    ('usar ano actual', '📅'),
]


#Minúsculas y sin tildes, para que 'Cálcular' == 'calcular'.
def _normalizar(texto):

    texto= texto.strip().lower()
    texto= unicodedata.normalize('NFD', texto)
    return ''.join(c for c in texto if unicodedata.category(c) != 'Mn')


#Cache: texto normalizado -> QIcon (evita rebuscar el mapa mil veces)
_cache_texto= {}

#Cache de patrones compilados por palabra clave (evita recompilar el mismo regex en cada llamada; ver _coincide
#más abajo).
_cache_patrones= {}

#Excepciones puntuales: palabras clave que necesitan una condición extra además del límite de palabra normal,
#porque forman parte de una locución de uso muy común en español que NO debe iconizarse con su sentido literal.
#'nuevo' es el caso real encontrado: "Ver tutorial ... de nuevo" usa "de nuevo" con el sentido de "otra vez",
#no el de "elemento nuevo" -sin esto, 'nuevo' (que aparece antes que 'tutorial' en el mapa) se adelantaría y le
#pondría el icono de "➕ crear" a un botón que en realidad trata de un tutorial.
_PATRONES_EXCEPCION= {
    'nuevo': r'(?<!de )\bnuevo',
}


#Compila (con cache) el patrón para `kw`: coincide solo si `kw`
#empieza en un límite de palabra -así 'area' NO coincide dentro de
#'tareas', ni 'rol' dentro de 'control', ni 'tema' dentro de 'sistema'-,
#pero SÍ permite que la palabra siga después (para seguir cubriendo
#plurales/formas como 'materia' -> 'materias', 'estudiante' ->
#'estudiantes'), ya que solo se exige el límite ANTES de la palabra.
def _patron_de(kw):

    patron= _cache_patrones.get(kw)
    if patron is None:
        expresion= _PATRONES_EXCEPCION.get(kw, r'\b' + re.escape(kw))
        patron= re.compile(expresion)
        _cache_patrones[kw]= patron
    return patron


#Devuelve el QIcon coherente para un texto de botón/título/pestaña.
#
#Único punto de verdad de la app: el mismo texto produce SIEMPRE el
#mismo icono en cualquier módulo. Si nada coincide, devuelve un QIcon
#nulo (mejor un botón sin icono que un icono sin sentido).
def icono_para_texto(texto):

    clave= _normalizar(texto)
    if clave in _cache_texto:
        return _cache_texto[clave]
    icono= QIcon()
    for kw, emoji in _MAPA:
        if _patron_de(kw).search(clave):
            from src.nucleo.iconos_emoji import icono_emoji
            icono= icono_emoji(emoji)
            break
    _cache_texto[clave]= icono
    return icono


#Filtro de eventos global: rellena los iconos que falten.
#
#Nunca sobreescribe un icono ya asignado manualmente: solo actúa
#cuando `icon().isNull()` (el botón/pestaña/ventana no tiene ninguno).
#
#RENDIMIENTO (importante): la asignación se DIFIERE y se COALESA. Dos
#razones:
#1. Si se asignara el icono dentro del evento Polish que dispara el
#propio constructor del widget, PySide6 revienta (SystemError al
#volver del constructor); diferido, el widget ya está completo.
#2. Al cambiar de tema claro/oscuro, Qt re-pule (evento Polish) TODOS
#los widgets de la app de golpe. Si por cada uno se programara un
#QTimer.singleShot(0) individual, el cambio de tema se llenaría de
#miles de timers y se volvería lento. Aquí todos los widgets
#pendientes se acumulan en sendos conjuntos y UN ÚNICO timer los
#procesa todos juntos en el siguiente ciclo del bucle de eventos.
class _Iconizador(QObject):

    def __init__(self, parent=None):

        super().__init__(parent)
        self._botones= set()
        self._tabs= set()
        self._ventanas= set()
        self._timer= QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._procesar_pendientes)

    #Programa UNA sola pasada para todo lo pendiente.
    def _agendar(self):

        if not self._timer.isActive():
            self._timer.start()

    def _procesar_pendientes(self):

        botones, self._botones= self._botones, set()
        tabs, self._tabs= self._tabs, set()
        ventanas, self._ventanas= self._ventanas, set()
        for btn in botones:
            try:

                if btn.icon().isNull() and btn.text():
                    icono= icono_para_texto(btn.text())
                    if not icono.isNull():
                        btn.setIcon(icono)
                        btn.setIconSize(TAM_ICONO)
            except RuntimeError:
                pass  #el widget C++ ya fue destruido
        for tabs_w in tabs:
            try:

                barra= tabs_w.tabBar()
                for i in range(tabs_w.count()):
                    if barra.tabIcon(i).isNull() and tabs_w.tabText(i):
                        icono= icono_para_texto(tabs_w.tabText(i))
                        if not icono.isNull():
                            tabs_w.setTabIcon(i, icono)
            except RuntimeError:
                pass
        for win in ventanas:
            try:

                if win.windowIcon().isNull() and win.windowTitle():
                    icono= icono_para_texto(win.windowTitle())
                    if not icono.isNull():
                        win.setWindowIcon(icono)
            except RuntimeError:
                pass

    #Caché de clases: evita encadenar isinstance por CADA evento de CADA
    #widget (durante un cambio de tema Qt re-pule miles de widgets). Para
    #cada clase Python se calcula UNA vez si es relevante (botón / tabs / ventana) y después es solo una búsqueda
    #en diccionario.
    _cache_clases= {}
    _TAG_BOTON, _TAG_TABS, _TAG_VENTANA= 1, 2, 3

    @classmethod
    def _tag_de_clase(cls, clase):

        try:

            if issubclass(clase, (QPushButton, QToolButton)):
                return cls._TAG_BOTON
            if issubclass(clase, QTabWidget):
                return cls._TAG_TABS
            if issubclass(clase, (QDialog, QMainWindow)):
                return cls._TAG_VENTANA
        except RuntimeError:
            pass
        return 0

    def eventFilter(self, obj, event):

        t= event.type()
        if t != QEvent.Type.Polish and t != QEvent.Type.Show:
            return False
        clase= obj.__class__
        cache= self._cache_clases
        tag= cache.get(clase)
        if tag is None:
            tag= cache[clase]= self._tag_de_clase(clase)
        if not tag:
            return False
        try:

            if tag == self._TAG_BOTON:
                if obj.icon().isNull() and obj.text() \
                        and not icono_para_texto(obj.text()).isNull():
                    self._botones.add(obj)
                    self._agendar()
            elif tag == self._TAG_TABS:
                self._tabs.add(obj)
                self._agendar()
            elif tag == self._TAG_VENTANA and not isinstance(obj, QMessageBox):
                self._ventanas.add(obj)
                self._agendar()
        except RuntimeError:
            pass  #el widget C++ ya fue destruido; no importa
        return False


_instalado= False


#Instala el filtro UNA sola vez sobre la aplicación.
def instalar_iconos_automaticos(app):

    global _instalado
    if _instalado:
        return
    filtro= _Iconizador()
    #Referencia viva en la propia app para que no lo recoja el GC
    app._iconizador_auto= filtro
    app.installEventFilter(filtro)
    _instalado= True


