#Sistema de ALARMAS / ALERTAS de AcaDeXI.
#
#Objetivo: avisar al usuario, con sonido + un efecto visual llamativo (pero
#NO molesto), exactamente a la hora en que ocurre:
#
#1) Un EVENTO del Calendario institucional (tabla `eventos` de acadexi.db)
#que le corresponde ver a este usuario.
#2) Una clase de "Mis Materias"/Horario (tabla `horarios` institucional,
#o `horario_local` del Modo Docente -ver datos_locales_docente.py-)
#que empieza en este momento, según el día de la semana.
#3) Un RECORDATORIO manual que el propio usuario haya creado desde el
#diálogo de configuración de este módulo (único/diario/semanal).
#
#Todo se implementa SOLO con PySide6 (QtCore/QtGui/QtWidgets/QtMultimedia).
#No se usa ninguna librería externa: los tonos predeterminados se generan en
#el primer uso con el módulo estándar `wave` (ondas simples: campanilla,
#suave, clásico, urgente) y los tonos personalizados del usuario (.mp3, .wav,
#.ogg, etc.) se reproducen con QMediaPlayer/QAudioOutput, que decodifican con
#los backends multimedia del sistema -sigue siendo 100% PySide6-.
#
#Persistencia: igual que `datos_locales_docente.py`, la configuración de
#alarmas y los recordatorios manuales son una preferencia LOCAL de este
#usuario en este equipo (no institucional), así que viven en un SQLite propio
#dentro de la carpeta de datos de la app y NUNCA tocan acadexi.db.
#
#Integración mínima en main.py (ver comentarios "INTEGRACIÓN" al final del
#archivo para el detalle exacto):
#
#from alarmas import MotorAlarmas
#...
#self.motor_alarmas= MotorAlarmas(self)
#self.motor_alarmas.iniciar()
import json
import math
import os
import sqlite3
import struct
import wave
from datetime import datetime, timedelta

from PySide6.QtCore import (Qt, QTimer, QObject, Signal, QPropertyAnimation, QSequentialAnimationGroup,
                             QEasingCurve, QPoint, QRect, QUrl, QAbstractAnimation)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QSoundEffect
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                                QComboBox, QPushButton, QSlider, QCheckBox, QFileDialog, QTableWidget,
                                QTableWidgetItem, QHeaderView, QLineEdit, QDateEdit, QTimeEdit, QMessageBox,
                                QTabWidget, QAbstractItemView, QAbstractSpinBox, QApplication)

from src.nucleo.bd import get_app_data_dir, obtener_conexion
from src.nucleo.limite_campos import limitar_campo_texto
from src.nucleo.formato_hora import aplicar_formato_widget_hora, aplicar_formato_widget_fecha, formatear_hora, formatear_fecha
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, pixmap_emoji, quitar_emojis_texto

try:

    from src.nucleo.datos_locales_docente import _clave_docente as _clave_usuario_docente
except Exception:
    _clave_usuario_docente= None


#Tonos predeterminados (generados en el primer uso, sin assets externos)
TONOS_PREDETERMINADOS= {
    "Campanilla": "campanilla.wav",
    "Suave": "suave.wav",
    "Clásico": "clasico.wav",
    "Urgente": "urgente.wav",
}

DURACION_EFECTO_DEFECTO= 2600      #ms que dura la "vibración" visual por disparo
VOLUMEN_DEFECTO= 70                #0-100
TOLERANCIA_SEGUNDOS= 45            #ventana para no perderse el minuto exacto
INTERVALO_REVISION_MS= 10_000      #cada cuánto se revisa si toca alguna alarma


def _carpeta_tonos():

    ruta= os.path.join(get_app_data_dir(), "alarmas_tonos")
    os.makedirs(ruta, exist_ok=True)
    return ruta


#Genera un .wav mono de 16 bits combinando una secuencia de tonos
#simples (sin depender de numpy ni de ninguna librería externa).
def _generar_tono_wav(ruta, frecuencias, duraciones, forma="sine", fade=True, sample_rate=44100):

    with wave.open(ruta, "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        cuadros= bytearray()
        for freq, dur in zip(frecuencias, duraciones):
            n= int(sample_rate * dur)
            for i in range(n):
                t= i / sample_rate
                if forma == "square":
                    valor= 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
                else:
                    valor= math.sin(2 * math.pi * freq * t)
                #Envolvente simple para evitar "clics" al inicio/fin de cada nota.
                if fade:
                    borde= min(n * 0.08, sample_rate * 0.02)
                    if i < borde:
                        valor *= i / borde
                    elif i > n - borde:
                        valor *= (n - i) / borde
                amplitud= int(valor * 26000)
                cuadros += struct.pack("<h", amplitud)
        wav.writeframes(bytes(cuadros))


#Crea (si no existen ya) los 4 tonos de fábrica. Se llama una sola vez
#con costo real; luego siempre se reutilizan los archivos.
def asegurar_tonos_predeterminados():

    carpeta= _carpeta_tonos()
    rutas= {}
    definiciones= {
        "campanilla.wav": ([1046, 1318, 1568], [0.11, 0.11, 0.30], "sine"),
        "suave.wav": ([523, 659], [0.35, 0.55], "sine"),
        "clasico.wav": ([880, 0, 880, 0, 880], [0.14, 0.08, 0.14, 0.08, 0.30], "sine"),
        "urgente.wav": ([988, 784, 988, 784], [0.13, 0.13, 0.13, 0.13], "square"),
    }
    for archivo, (frecs, durs, forma) in definiciones.items():
        ruta= os.path.join(carpeta, archivo)
        rutas[archivo]= ruta
        if not os.path.exists(ruta):
            try:

                #"0" en frecs = silencio breve (pausa entre notas del tono "clásico").
                _generar_tono_wav(ruta, [f if f else 0.0001 for f in frecs], durs, forma=forma)
            except Exception:
                pass
    return rutas


#Almacén local (config + recordatorios manuales) — por usuario, por equipo
def _clave_usuario(main_window):

    if _clave_usuario_docente is not None:
        try:

            return _clave_usuario_docente(main_window)
        except Exception:
            pass
    id_usuario= getattr(main_window, "id_usuario_actual", None)
    if id_usuario is not None:
        return f"usuario_{id_usuario}"
    usuario= getattr(main_window, "usuario_actual", None)
    return f"usuario_{usuario}" if usuario else "usuario_default"


def _ruta_bd_local(main_window):

    carpeta= os.path.join(get_app_data_dir(), "alarmas_local")
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, f"{_clave_usuario(main_window)}.db")


def _conexion_local(main_window):

    conn= sqlite3.connect(_ruta_bd_local(main_window))
    conn.row_factory= sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        tono_defecto TEXT DEFAULT 'Campanilla',
        tono_defecto_ruta TEXT,
        volumen INTEGER DEFAULT 70,
        efecto_visual INTEGER DEFAULT 1,
        duracion_efecto INTEGER DEFAULT 2600,
        sonido_en_bucle INTEGER DEFAULT 1,
        avisar_eventos INTEGER DEFAULT 1,
        avisar_clases INTEGER DEFAULT 1,
        minutos_anticipacion INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS recordatorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        fecha TEXT NOT NULL,
        hora TEXT NOT NULL,
        repetir TEXT DEFAULT 'unica',
        tono TEXT,
        tono_ruta TEXT,
        activo INTEGER DEFAULT 1
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS disparadas (
        clave TEXT PRIMARY KEY,
        fecha TEXT
    )""")
    conn.commit()
    return conn


def obtener_config(main_window):

    conn= _conexion_local(main_window)
    fila= conn.execute("SELECT * FROM config WHERE id=1").fetchone()
    if not fila:
        conn.execute("INSERT INTO config (id) VALUES (1)")
        conn.commit()
        fila= conn.execute("SELECT * FROM config WHERE id=1").fetchone()
    conn.close()
    return dict(fila)


def guardar_config(main_window, **campos):

    conn= _conexion_local(main_window)
    obtener_config(main_window)  #asegura que exista la fila
    sets= ", ".join(f"{k}=?" for k in campos)
    conn.execute(f"UPDATE config SET {sets} WHERE id=1", tuple(campos.values()))
    conn.commit()
    conn.close()


def listar_recordatorios(main_window):

    conn= _conexion_local(main_window)
    filas= conn.execute("SELECT * FROM recordatorios ORDER BY fecha, hora").fetchall()
    conn.close()
    return [dict(f) for f in filas]


def guardar_recordatorio(main_window, id_edicion, titulo, fecha, hora, repetir, tono, tono_ruta, activo=1):

    conn= _conexion_local(main_window)
    if id_edicion is None:
        conn.execute("""INSERT INTO recordatorios (titulo, fecha, hora, repetir, tono, tono_ruta, activo)
                        VALUES (?,?,?,?,?,?,?)""", (titulo, fecha, hora, repetir, tono, tono_ruta, activo))
    else:
        conn.execute("""UPDATE recordatorios SET titulo=?, fecha=?, hora=?, repetir=?, tono=?, tono_ruta=?,
                        activo= ? WHERE id=?""",
                     (titulo, fecha, hora, repetir, tono, tono_ruta, activo, id_edicion))
        #CLAVE: al editar fecha/hora hay que "re-armsarlo". Si este recordatorio ya había sonado hoy, su clave
        #`recordatorio_{id}_{fecha}` sigue en `disparadas` y el motor lo ignoraría aunque la nueva hora acabe de
        #llegar. Borramos sus marcas para que vuelva a dispararse.
        conn.execute("DELETE FROM disparadas WHERE clave LIKE ?", (f"recordatorio_{id_edicion}_%",))
    conn.commit()
    conn.close()


def eliminar_recordatorio(main_window, id_recordatorio):

    conn= _conexion_local(main_window)
    conn.execute("DELETE FROM recordatorios WHERE id=?", (id_recordatorio,))
    #Su entrada en `disparadas` ya no tiene sentido: si se vuelve a crear un recordatorio con el mismo id (SQLite
    #reutiliza ids), debe poder sonar.
    conn.execute("DELETE FROM disparadas WHERE clave LIKE ?", (f"recordatorio_{id_recordatorio}_%",))
    conn.commit()
    conn.close()


#Re-arma la alarma de un EVENTO del Calendario tras ser editado o
#eliminado: borra sus marcas de `disparadas` (`evento_{id}_{fecha}`) en la
#BD local de alarmas de TODOS los usuarios de este equipo, para que si se
#cambió su fecha/hora vuelva a sonar en el nuevo momento (y no quede
#silenciado por haber sonado antes con la hora vieja).
def rearmar_alarmas_evento(id_evento):

    try:

        carpeta= os.path.join(get_app_data_dir(), "alarmas_local")
        patron= f"evento_{id_evento}_%"
        if not os.path.isdir(carpeta):
            return
        for archivo in os.listdir(carpeta):
            if not archivo.endswith(".db"):
                continue
            try:

                conn= sqlite3.connect(os.path.join(carpeta, archivo))
                conn.execute("DELETE FROM disparadas WHERE clave LIKE ?", (patron,))
                conn.commit()
                conn.close()
            except Exception:
                pass
    except Exception:
        pass


def _ya_disparada(conn, clave):

    return conn.execute("SELECT 1 FROM disparadas WHERE clave=?", (clave,)).fetchone() is not None


def _marcar_disparada(conn, clave):

    hoy= datetime.now().strftime("%Y-%m-%d")
    conn.execute("INSERT OR REPLACE INTO disparadas (clave, fecha) VALUES (?, ?)", (clave, hoy))
    conn.commit()


def _limpiar_disparadas_viejas(conn):

    limite= (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    conn.execute("DELETE FROM disparadas WHERE fecha < ?", (limite,))
    conn.commit()


#MOTOR: revisa periódicamente si hay que disparar alguna alarma
#Orquesta todo: revisión periódica, sonido, efecto visual y botón de
#detener. Una sola instancia por MainWindow.
class MotorAlarmas(QObject):

    alarma_disparada= Signal(str, str)   #(titulo, subtitulo) — por si algún módulo quiere reaccionar

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        asegurar_tonos_predeterminados()

        self._timer= QTimer(self)
        self._timer.setInterval(INTERVALO_REVISION_MS)
        self._timer.timeout.connect(self._revisar)

        #El reproductor se crea la primera vez que suena una alarma (ver _asegurar_reproductor):
        #crearlo al arrancar hacía caer la app en algunos equipos sin backend de audio.
        self._reproductor= None
        self._salida_audio= None
        self._en_bucle= True
        self._sonando= False

        self.overlay= OverlayEfectoAlarma(main_window)
        self.boton_detener= BotonDetenerAlarma(main_window)
        self.boton_detener.clicked.connect(self.detener_alarma_activa)
        self.overlay.hide()
        self.boton_detener.hide()

        self._dialogo_config= None

        #BARRA ESPACIADORA = detener la alarma. Se instala un filtro de
        #eventos a nivel de aplicación: SOLO actúa mientras hay una alarma sonando, así que no interfiere con la
        #escritura normal (espacios en textos, activar botones, etc.) cuando no hay alarma activa.
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):

        if self._sonando and event.type() == event.Type.KeyPress and\
                event.key() == Qt.Key.Key_Space:
            try:

                self.detener_alarma_activa()
            except Exception:
                pass
            return True  #consumimos la tecla
        return super().eventFilter(obj, event)

    #---------------- ciclo de vida ----------------
    def iniciar(self):

        self._revisar()  #primera pasada inmediata
        self._timer.start()

    def detener_motor(self):

        self._timer.stop()
        self.detener_alarma_activa()

    #Debe llamarse desde resizeEvent()/showEvent() del MainWindow.
    def reposicionar(self):

        self.overlay.reposicionar()
        self.boton_detener.reposicionar()

    #Ventana emergente opcional con la configuración de alarmas. El
    #lugar recomendado para que el usuario la edite es Configuración ▸
    #Mi Cuenta ▸ Preferencias (ver PanelAlarmas más abajo), pero este
    #método queda disponible por si algún módulo necesita abrirla aparte.
    def abrir_configuracion(self):

        if self._dialogo_config is None:
            self._dialogo_config= ConfigurarAlarmasDialog(self.main_window)
        self._dialogo_config.panel.cargar()
        self._dialogo_config.exec()

    #---------------- revisión de disparos ----------------
    def _revisar(self):

        try:

            self._revisar_impl()
        except Exception:
            #Una alarma nunca debe poder tumbar la aplicación.
            pass

    def _revisar_impl(self):

        mw= self.main_window
        if getattr(mw, "id_usuario_actual", None) is None and getattr(mw, "usuario_actual", None) is None:
            return  #nadie ha iniciado sesión todavía

        ahora= datetime.now()
        conn= _conexion_local(mw)
        _limpiar_disparadas_viejas(conn)
        cfg= obtener_config(mw)

        candidatos= []  #(clave_unica, titulo, subtitulo, tono, tono_ruta)
        candidatos += self._candidatos_recordatorios(conn, ahora)
        if cfg.get("avisar_eventos", 1):
            candidatos += self._candidatos_eventos(mw, ahora, cfg)
        if cfg.get("avisar_clases", 1):
            candidatos += self._candidatos_clases(mw, ahora, cfg)

        for clave, titulo, subtitulo, tono, tono_ruta in candidatos:
            if _ya_disparada(conn, clave):
                continue
            _marcar_disparada(conn, clave)
            self._disparar(titulo, subtitulo, tono, tono_ruta, cfg)
            break  #una alarma a la vez; las demás esperan a la siguiente revisión
        conn.close()

    def _dentro_de_tolerancia(self, ahora, fecha_str, hora_str):

        try:

            objetivo= datetime.strptime(f"{fecha_str} {hora_str[:5]}", "%Y-%m-%d %H:%M")
        except ValueError:
            return False
        return abs((ahora - objetivo).total_seconds()) <= TOLERANCIA_SEGUNDOS

    def _candidatos_recordatorios(self, conn, ahora):

        salida= []
        hoy_iso= ahora.strftime("%Y-%m-%d")
        dia_semana= ahora.strftime("%A")
        for r in conn.execute("SELECT * FROM recordatorios WHERE activo=1").fetchall():
            r= dict(r)
            aplica_hoy= False
            if r["repetir"] == "unica" and r["fecha"] == hoy_iso:
                aplica_hoy= True
            elif r["repetir"] == "diario":
                aplica_hoy= True
            elif r["repetir"] == "semanal":
                try:

                    fecha_base= datetime.strptime(r["fecha"], "%Y-%m-%d")
                    aplica_hoy= fecha_base.weekday() == ahora.weekday()
                except ValueError:
                    aplica_hoy= False
            if not aplica_hoy:
                continue
            if self._dentro_de_tolerancia(ahora, hoy_iso, r["hora"]):
                clave= f"recordatorio_{r['id']}_{hoy_iso}"
                salida.append((clave, r["titulo"], "Recordatorio", r.get("tono"), r.get("tono_ruta")))
        return salida

    #Eventos institucionales del Calendario (tabla `eventos`) que le
    #corresponden a este usuario: institucionales/públicos siempre, y los
    #de su(s) materia(s)/sección si es el profesor asignado.
    def _candidatos_eventos(self, mw, ahora, cfg):

        salida= []
        try:

            conn_inst= obtener_conexion()
            hoy_iso= ahora.strftime("%Y-%m-%d")
            filas= conn_inst.execute(
                "SELECT * FROM eventos WHERE fecha=? AND hora IS NOT NULL AND hora <> ''", (hoy_iso,)
            ).fetchall()
            profesor_id= self._profesor_id_actual(mw, conn_inst)
            for f in filas:
                f= dict(f)
                visible= f.get("visibilidad") in (None, "", "Institucional", "Pública", "Publica")
                if not visible and profesor_id and f.get("materia_id"):
                    fila_mp= conn_inst.execute(
                        "SELECT 1 FROM materia_profesores WHERE materia_id=? AND profesor_id=?",
                        (f["materia_id"], profesor_id)).fetchone()
                    visible= fila_mp is not None
                if not visible and getattr(mw, "id_usuario_actual", None) == f.get("usuario_id"):
                    visible= True
                if not visible:
                    continue
                if self._dentro_de_tolerancia(ahora, hoy_iso, f["hora"]):
                    clave= f"evento_{f['id']}_{hoy_iso}"
                    salida.append((clave, f["titulo"], "Evento del calendario", None, None))
            conn_inst.close()
        except Exception:
            pass
        return salida

    #Clases que empiezan ahora: horario institucional (si el usuario es
    #el profesor asignado) + horario personal del Modo Docente.
    #
    #Para el horario institucional se usa EXACTAMENTE la misma regla de
    #filtrado del módulo Horario en Modo Docente (horario.py ▸ _cargar_datos):
    #`obtener_materias_permitidas`, que incluye tanto materias académicas
    #como MÓDULOS TÉCNICOS que el docente imparte — sea titular directo
    #(materias.profesor_id) o asignado vía materia_profesores (Titular,
    #Auxiliar, etc., incluso cuando la asignación no indica sección). Así
    #la alarma suena para todo lo que el docente ve en su horario, y NADA
    #de lo que no le corresponde.
    def _candidatos_clases(self, mw, ahora, cfg):

        salida= []
        dias_map= {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        dia_hoy= dias_map[ahora.weekday()]
        hoy_iso= ahora.strftime("%Y-%m-%d")
        try:

            conn_inst= obtener_conexion()
            filas= []
            materias_permitidas= None
            try:

                from src.nucleo.permisos import obtener_materias_permitidas
                materias_permitidas= obtener_materias_permitidas(mw)
            except Exception:
                materias_permitidas= None
            if materias_permitidas is not None:
                #Profesor (Modo Docente o no): solo las clases de las materias
                #y módulos técnicos que ÉL imparte — igual que su vista de Horario.
                if materias_permitidas:
                    marcadores= ",".join("?" * len(materias_permitidas))
                    filas= conn_inst.execute(
                        f"""SELECT h.id, h.hora_inicio, m.nombre AS materia
                            FROM horarios h
                            LEFT JOIN materias m ON m.id = h.materia_id
                            WHERE h.dia=? AND h.materia_id IN ({marcadores})""",
                        (dia_hoy, *materias_permitidas)).fetchall()
            else:
                #Rol gerencial u obtención de permisos no disponible: la alarma de clases no aplica al horario institucional
                #(los gerenciales no tienen "su" horario), así que no se emite ninguna clase.
                pass
            for f in filas:
                f= dict(f)
                if f.get("hora_inicio") and self._dentro_de_tolerancia(ahora, hoy_iso, f["hora_inicio"]):
                    clave= f"clase_{f['id']}_{hoy_iso}"
                    titulo= f.get("materia") or "Clase"
                    salida.append((clave, titulo, "Tu clase empieza ahora", None, None))
            conn_inst.close()
        except Exception:
            pass
        try:

            from src.nucleo.datos_locales_docente import listar_horario_local
            for h in listar_horario_local(mw):
                if h.get("dia") == dia_hoy and h.get("hora_inicio") and\
                        self._dentro_de_tolerancia(ahora, hoy_iso, h["hora_inicio"]):
                    clave= f"clase_local_{h['id']}_{hoy_iso}"
                    titulo= h.get("notas") or "Clase (horario personal)"
                    salida.append((clave, titulo, "Tu clase empieza ahora", None, None))
        except Exception:
            pass
        return salida

    def _profesor_id_actual(self, mw, conn_inst):

        id_usuario= getattr(mw, "id_usuario_actual", None)
        if id_usuario is None:
            return None
        fila= conn_inst.execute("SELECT id FROM profesores WHERE usuario_id=?", (id_usuario,)).fetchone()
        return fila["id"] if fila else None

    #---------------- disparo real: sonido + efecto + botón ----------------
    def _disparar(self, titulo, subtitulo, tono_nombre, tono_ruta, cfg):

        ruta= self._resolver_ruta_tono(tono_nombre, tono_ruta, cfg)
        if not self._asegurar_reproductor():
            return
        self._reproductor.setSource(QUrl.fromLocalFile(ruta) if ruta else QUrl())
        self._salida_audio.setVolume(max(0.0, min(1.0, cfg.get("volumen", VOLUMEN_DEFECTO) / 100)))
        self._en_bucle= bool(cfg.get("sonido_en_bucle", 1))
        self._sonando= True
        if ruta:
            self._reproductor.play()

        #El efecto visual acompaña a la alarma cuando está activado en la
        #configuración (por defecto sí). Si el tono falla, igualmente se
        #intenta mostrar el efecto: la alarma siempre hace acto de presencia.
        if cfg.get("efecto_visual", 1):
            try:

                self.overlay.disparar()  #efecto continuo hasta detener la alarma
            except Exception:
                pass
        self.boton_detener.mostrar_para_alarma(titulo, subtitulo)
        self.alarma_disparada.emit(titulo, subtitulo)

    def _resolver_ruta_tono(self, tono_nombre, tono_ruta, cfg):

        if tono_ruta and os.path.exists(tono_ruta):
            return tono_ruta
        nombre= tono_nombre or cfg.get("tono_defecto") or "Campanilla"
        if nombre in TONOS_PREDETERMINADOS:
            ruta= os.path.join(_carpeta_tonos(), TONOS_PREDETERMINADOS[nombre])
            if os.path.exists(ruta):
                return ruta
        ruta_defecto= cfg.get("tono_defecto_ruta")
        if ruta_defecto and os.path.exists(ruta_defecto):
            return ruta_defecto
        return os.path.join(_carpeta_tonos(), TONOS_PREDETERMINADOS["Campanilla"])

    #Crea el reproductor de audio si aún no existe. Devuelve False si el sistema no tiene audio.
    def _asegurar_reproductor(self):

        if self._reproductor is not None:
            return True
        try:

            self._reproductor= QMediaPlayer(self)
            self._salida_audio= QAudioOutput(self)
            self._reproductor.setAudioOutput(self._salida_audio)
            self._reproductor.mediaStatusChanged.connect(self._al_cambiar_estado_media)
            return True
        except Exception:
            self._reproductor= None
            self._salida_audio= None
            return False

    def _al_cambiar_estado_media(self, estado):

        if estado == QMediaPlayer.MediaStatus.EndOfMedia and self._sonando and self._en_bucle:
            self._reproductor.setPosition(0)
            self._reproductor.play()

    def detener_alarma_activa(self):

        self._sonando= False
        if self._reproductor is not None:
            self._reproductor.stop()
        self.overlay.detener()
        self.boton_detener.ocultar_con_fundido()


#Efecto visual: "vibración" sutil + resplandor con el color del tema
#Capa transparente sobre TODA la ventana (todos los módulos, sin
#importar cuál esté abierto) que dibuja un resplandor pulsante en los
#bordes, con el color de acento del tema activo. Además hace vibrar
#suavemente el contenido central (unos pocos píxeles) para dar la
#sensación de aviso sin llegar a ser molesto ni a tapar el contenido.
class OverlayEfectoAlarma(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._intensidad= 0.0
        self._activo= False

        self._anim_pulso= QPropertyAnimation(self, b"intensidad", self)
        self._anim_pulso.setStartValue(0.0)
        self._anim_pulso.setKeyValueAt(0.5, 1.0)
        self._anim_pulso.setEndValue(0.0)
        self._anim_pulso.setDuration(1100)
        self._anim_pulso.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim_pulso.setLoopCount(-1)

        #El efecto dura MIENTRAS la alarma siga sonando: el resplandor pulsa en bucle y la vibración se repite
        #periódicamente hasta que el usuario detenga la alarma (no hay apagado automático por tiempo).
        self._timer_vibracion= QTimer(self)
        self._timer_vibracion.setInterval(4000)
        self._timer_vibracion.timeout.connect(self._vibrar_contenido)

        self._grupo_vibracion= None

    def _leer_intensidad(self):

        return self._intensidad

    def _poner_intensidad(self, v):

        self._intensidad= v
        self.update()

    from PySide6.QtCore import Property
    intensidad= Property(float, _leer_intensidad, _poner_intensidad)

    def _color_acento(self):

        try:

            mw= self.main_window
            paleta= mw.theme_palettes.get(mw.tema_actual, {})
            idx= 1 if getattr(mw, "modo_oscuro", False) else 0
            hexcolor= paleta.get("btn_op_bg", ("#4F8EF7", "#3B82F6"))[idx]
            return QColor(hexcolor)
        except Exception:
            return QColor("#4F8EF7")

    def reposicionar(self):

        contenedor= self.main_window.centralWidget()
        if contenedor is not None:
            #Re-parentarlo al central widget garantiza que la capa quede SIEMPRE por encima del contenido y bien alineada,
            #sin importar en qué módulo esté parado el usuario cuando suene la alarma.
            if self.parent() is not contenedor:
                self.setParent(contenedor)
            self.setGeometry(contenedor.rect())
        self.raise_()

    #Activa el efecto de forma CONTINUA: sigue hasta que se llame a
    #detener() (es decir, hasta que el usuario pare la alarma). El
    #parámetro duracion_ms se mantiene por compatibilidad pero se ignora.
    def disparar(self, duracion_ms=None):

        self.reposicionar()
        self.show()
        self.raise_()
        self._activo= True
        if self._anim_pulso.state() != QAbstractAnimation.State.Running:
            self._anim_pulso.start()
        if not self._timer_vibracion.isActive():
            self._vibrar_contenido()
            self._timer_vibracion.start()

    #Micro-oscilación horizontal del panel central: un 'temblor' muy
    #leve (pocos píxeles) que se nota pero no marea ni desordena la vista.
    def _vibrar_contenido(self):

        contenedor= self.main_window.centralWidget()
        if contenedor is None:
            return
        if self._grupo_vibracion is not None:
            self._grupo_vibracion.stop()
        base= contenedor.pos()
        grupo= QSequentialAnimationGroup(self)
        desplazamientos= [6, -6, 4, -4, 2, -2, 0]
        for dx in desplazamientos:
            paso= QPropertyAnimation(contenedor, b"pos", self)
            paso.setDuration(55)
            paso.setEndValue(QPoint(base.x() + dx, base.y()))
            grupo.addAnimation(paso)
        grupo.finished.connect(lambda: contenedor.move(base))
        self._grupo_vibracion= grupo
        grupo.start()

    def _apagar_pulso(self):

        self._activo= False
        self._anim_pulso.stop()
        self._intensidad= 0.0
        self.update()
        self.hide()

    def detener(self):

        self._timer_vibracion.stop()
        self._apagar_pulso()

    def paintEvent(self, event):

        if not self._activo and self._intensidad <= 0:
            return
        p= QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color= self._color_acento()
        grosor= 3 + 10 * self._intensidad
        alpha= int(40 + 130 * self._intensidad)
        color.setAlpha(alpha)
        pluma= QPen(color)
        pluma.setWidth(int(grosor))
        p.setPen(pluma)
        margen= grosor / 2
        p.drawRoundedRect(self.rect().adjusted(int(margen), int(margen), -int(margen), -int(margen)), 18, 18)


#Botón flotante para detener la alarma
#Botón circular semitransparente, flotante en la esquina inferior
#derecha, que aparece con un fundido cuando suena una alarma y desaparece
#igual al pararla. Incluye título/subtítulo de la alarma.
class BotonDetenerAlarma(QWidget):

    from PySide6.QtCore import Signal as _Signal
    clicked= _Signal()

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(260, 92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Detener el sonido y el efecto de esta alarma (o pulsa la barra espaciadora).")
        self._opacidad= 0.0
        self._titulo= ""
        self._subtitulo= ""
        self._ocultando= False  #True mientras el fundido en curso es el de "salida"

        self._anim= QPropertyAnimation(self, b"opacidadWidget", self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        #Conectado UNA sola vez y para siempre: así nunca hace falta desconectar/reconectar "finished" (desconectar una
        #señal que no tiene ninguna conexión -como pasaba al mostrar la alarma antes de ocultarla una primera vez- hace
        #que libpyside imprima "Failed to
        #disconnect (None) from signal" en la consola; ese aviso lo emite
        #la capa C++ ANTES de que Python pueda atraparlo con un
        #try/except, así que no hay forma de "silenciarlo" ahí -solo
        #evitando el disconnect() de entrada-).
        self._anim.finished.connect(self._al_terminar_fundido)

    def _leer_opacidad(self):

        return self._opacidad

    def _poner_opacidad(self, v):

        self._opacidad= v
        self.update()

    from PySide6.QtCore import Property as _Property
    opacidadWidget= _Property(float, _leer_opacidad, _poner_opacidad)

    def reposicionar(self):

        contenedor= self.main_window.centralWidget()
        if contenedor is None:
            return
        margen= 28
        x= contenedor.width() - self.width() - margen
        y= contenedor.height() - self.height() - margen
        self.move(max(0, x), max(0, y))
        self.raise_()

    def mostrar_para_alarma(self, titulo, subtitulo):

        self._titulo, self._subtitulo= titulo, subtitulo
        self.reposicionar()
        self.show()
        self.raise_()
        self._anim.stop()
        self._ocultando= False
        self._anim.setStartValue(self._opacidad)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self.update()

    def ocultar_con_fundido(self):

        self._anim.stop()
        self._ocultando= True
        self._anim.setStartValue(self._opacidad)
        self._anim.setEndValue(0.0)
        self._anim.start()

    #Único receptor de 'finished', conectado una sola vez desde el
    #__init__. Solo oculta el widget si el fundido que acaba de terminar
    #era el de salida (ocultar_con_fundido); si era el de entrada
    #(mostrar_para_alarma) no hay que hacer nada más.
    def _al_terminar_fundido(self):

        if self._ocultando:
            self.hide()

    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def _color_acento(self):

        try:

            mw= self.main_window
            paleta= mw.theme_palettes.get(mw.tema_actual, {})
            idx= 1 if getattr(mw, "modo_oscuro", False) else 0
            return QColor(paleta.get("btn_op_bg", ("#4F8EF7", "#3B82F6"))[idx])
        except Exception:
            return QColor("#4F8EF7")

    def paintEvent(self, event):

        if self._opacidad <= 0.01:
            return
        p= QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color= self._color_acento()

        fondo= QColor(20, 22, 30, int(210 * self._opacidad))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fondo))
        p.drawRoundedRect(self.rect(), 20, 20)

        borde= QColor(color)
        borde.setAlpha(int(220 * self._opacidad))
        p.setPen(QPen(borde, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)

        circulo_rect= QRect(16, 16, 60, 60)
        relleno_circulo= QColor(color)
        relleno_circulo.setAlpha(int(200 * self._opacidad))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(relleno_circulo))
        p.drawEllipse(circulo_rect)
        p.setPen(QColor(255, 255, 255, int(255 * self._opacidad)))
        fuente= QFont()
        fuente.setPointSize(16)
        p.setFont(fuente)
        p.drawText(circulo_rect, Qt.AlignmentFlag.AlignCenter, "⏹")

        texto_rect= QRect(88, 14, self.width() - 100, self.height() - 28)
        p.setPen(QColor(255, 255, 255, int(255 * self._opacidad)))
        fuente_t= QFont()
        fuente_t.setPointSize(10)
        fuente_t.setBold(True)
        p.setFont(fuente_t)
        p.drawText(QRect(texto_rect.x(), texto_rect.y(), texto_rect.width(), 22),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._elidir(self._titulo, 24))
        fuente_s= QFont()
        fuente_s.setPointSize(9)
        p.setFont(fuente_s)
        p.setPen(QColor(230, 230, 240, int(230 * self._opacidad)))
        p.drawText(QRect(texto_rect.x(), texto_rect.y() + 22, texto_rect.width(), 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._elidir(self._subtitulo, 30))
        p.setPen(QColor(210, 214, 230, int(200 * self._opacidad)))
        fuente_toque= QFont()
        fuente_toque.setPointSize(8)
        p.setFont(fuente_toque)
        p.drawText(QRect(texto_rect.x(), texto_rect.y() + 42, texto_rect.width(), 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Toca para detener")

    @staticmethod
    def _elidir(texto, largo):

        texto= texto or ""
        return texto if len(texto) <= largo else texto[:largo - 1] + "…"


#Diálogo de configuración
#Widget EMBEBIBLE con toda la configuración de Alarmas y Recordatorios
#(pestañas "General" y "Recordatorios"). Pensado para vivir dentro de
#Configuración ▸ Mi Cuenta ▸ Preferencias (junto a las demás preferencias
#del propio usuario/equipo), no en una ventana aparte -por eso no hereda
#de QDialog-. `ConfigurarAlarmasDialog`, más abajo, es solo un envoltorio
#por si algún módulo prefiere abrirlo como ventana emergente.
class PanelAlarmas(QWidget):

    def __init__(self, main_window, parent=None):

        super().__init__(parent)
        self.main_window= main_window
        self._tono_prueba= None   #se crea al pulsar "probar" (ver _asegurar_tono_prueba)
        self._salida_prueba= None
        self._id_edicion= None

        layout= QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs= QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(self._tab_general(), "General")
        tabs.addTab(self._tab_recordatorios(), "Recordatorios")

        self.cargar()

    #---------------- pestaña General ----------------
    def _tab_general(self):

        w= QWidget()
        form= QFormLayout(w)

        self.combo_tono= QComboBox()
        self.combo_tono.addItems(list(TONOS_PREDETERMINADOS.keys()))
        self.combo_tono.setToolTip("Tono que sonará si no elegiste uno personalizado.")
        form.addRow("Tono predeterminado:", self.combo_tono)

        fila_personalizado= QHBoxLayout()
        self.lbl_tono_personalizado= QLabel("(ninguno)")
        self.lbl_tono_personalizado.setWordWrap(True)
        btn_examinar= QPushButton("Examinar…")
        btn_examinar.setToolTip("Usa tu propio archivo de audio como tono de alarma.")
        btn_examinar.clicked.connect(self._elegir_tono_personalizado)
        btn_quitar_personalizado= QPushButton("Quitar")
        btn_quitar_personalizado.setToolTip("Vuelve a usar el tono predeterminado de arriba.")
        btn_quitar_personalizado.clicked.connect(self._quitar_tono_personalizado)
        fila_personalizado.addWidget(self.lbl_tono_personalizado, 1)
        fila_personalizado.addWidget(btn_examinar)
        fila_personalizado.addWidget(btn_quitar_personalizado)
        form.addRow("Tono personalizado (.mp3/.wav/…):", fila_personalizado)

        fila_prueba= QHBoxLayout()
        btn_probar= QPushButton("▶ Probar tono")
        btn_probar.setToolTip("Reproduce el tono actual, sin activar el efecto visual.")
        btn_probar.clicked.connect(self._probar_tono)
        btn_detener= QPushButton("⏹ Detener alarma activa")
        btn_detener.setToolTip("Corta el sonido y el efecto visual si hay una alarma sonando ahora.")
        btn_detener.clicked.connect(self._detener_alarma_activa)
        fila_prueba.addWidget(btn_probar)
        fila_prueba.addWidget(btn_detener)
        form.addRow("", fila_prueba)

        self.slider_volumen= QSlider(Qt.Orientation.Horizontal)
        self.slider_volumen.setRange(0, 100)
        self.slider_volumen.setToolTip("Volumen del tono de alarma.")
        form.addRow("Volumen:", self.slider_volumen)

        self.chk_bucle= QCheckBox("Repetir el tono en bucle hasta detenerla")
        self.chk_bucle.setToolTip("Si lo desactivas, el tono suena una sola vez.")
        form.addRow("", self.chk_bucle)

        self.chk_efecto= QCheckBox("Mostrar efecto visual en pantalla")
        self.chk_efecto.setChecked(True)
        self.chk_efecto.setToolTip("Resplandor y vibración suave al sonar una alarma.")
        form.addRow("", self.chk_efecto)

        self.slider_duracion= QSlider(Qt.Orientation.Horizontal)
        self.slider_duracion.setRange(1000, 6000)
        self.slider_duracion.setSingleStep(200)
        self.slider_duracion.setToolTip("El efecto visual ahora es CONTINUO hasta detener la alarma; este ajuste quedó obsoleto.")
        form.addRow("Duración del efecto visual (ms):", self.slider_duracion)

        self.chk_eventos= QCheckBox("Avisar sobre eventos del Calendario")
        self.chk_eventos.setToolTip("Alarma automática cuando llega la hora de un evento tuyo.")
        form.addRow("", self.chk_eventos)
        self.chk_clases= QCheckBox("Avisar cuando empieza una clase de mi horario")
        self.chk_clases.setToolTip("Alarma automática al iniciar cada clase de tu horario.")
        form.addRow("", self.chk_clases)

        for widget in (self.combo_tono, self.slider_volumen, self.chk_bucle, self.chk_efecto,
                       self.slider_duracion, self.chk_eventos, self.chk_clases):
            señal= widget.valueChanged if hasattr(widget, "valueChanged") else (
                widget.toggled if hasattr(widget, "toggled") else widget.currentIndexChanged)
            señal.connect(self._guardar_general)
        return w

    def _elegir_tono_personalizado(self):

        ruta, _= QFileDialog.getOpenFileName(
            self, "Elegir tono de alarma", "",
            "Audio (*.mp3 *.wav *.ogg *.m4a *.flac *.aac);;Todos los archivos (*.*)")
        if ruta:
            self._ruta_personalizada= ruta
            self.lbl_tono_personalizado.setText(os.path.basename(ruta))
            self._guardar_general()

    def _quitar_tono_personalizado(self):

        self._ruta_personalizada= ""
        self.lbl_tono_personalizado.setText("(ninguno)")
        self._guardar_general()

    def _probar_tono(self):

        cfg= obtener_config(self.main_window)
        ruta_personalizada= getattr(self, "_ruta_personalizada", "") or cfg.get("tono_defecto_ruta") or ""
        if ruta_personalizada and os.path.exists(ruta_personalizada):
            ruta= ruta_personalizada
        else:
            nombre= self.combo_tono.currentText()
            ruta= os.path.join(_carpeta_tonos(), TONOS_PREDETERMINADOS.get(nombre, "campanilla.wav"))
        if not self._asegurar_tono_prueba():
            return
        self._salida_prueba.setVolume(self.slider_volumen.value() / 100)
        self._tono_prueba.setSource(QUrl.fromLocalFile(ruta))
        self._tono_prueba.play()

    def _asegurar_tono_prueba(self):

        if self._tono_prueba is not None:
            return True
        try:

            self._tono_prueba= QMediaPlayer(self)
            self._salida_prueba= QAudioOutput(self)
            self._tono_prueba.setAudioOutput(self._salida_prueba)
            return True
        except Exception:
            self._tono_prueba= None
            self._salida_prueba= None
            return False

    def _detener_alarma_activa(self):

        motor= getattr(self.main_window, "motor_alarmas", None)
        if motor is not None:
            motor.detener_alarma_activa()
        if self._tono_prueba is not None:
            self._tono_prueba.stop()

    def _guardar_general(self, *_args):

        guardar_config(
            self.main_window,
            tono_defecto= self.combo_tono.currentText(),
            tono_defecto_ruta= getattr(self, "_ruta_personalizada", "") or None,
            volumen= self.slider_volumen.value(),
            sonido_en_bucle= 1 if self.chk_bucle.isChecked() else 0,
            efecto_visual= 1 if self.chk_efecto.isChecked() else 0,
            duracion_efecto= self.slider_duracion.value(),
            avisar_eventos= 1 if self.chk_eventos.isChecked() else 0,
            avisar_clases= 1 if self.chk_clases.isChecked() else 0,
        )

    #---------------- pestaña Recordatorios ----------------
    def _tab_recordatorios(self):

        w= QWidget()
        layout= QVBoxLayout(w)

        form= QFormLayout()
        self.in_titulo_rec= QLineEdit()
        limitar_campo_texto(self.in_titulo_rec, 150)
        self.in_titulo_rec.setPlaceholderText("Ej. Entregar planificación")
        self.in_titulo_rec.setToolTip("Lo que verás cuando suene esta alarma.")
        form.addRow("Título:", self.in_titulo_rec)

        fila_fh= QHBoxLayout()
        self.date_rec= QDateEdit(calendarPopup=True)
        aplicar_formato_widget_fecha(self.date_rec, self.main_window)
        self.date_rec.setToolTip("Fecha en que debe sonar (o el día base si es semanal).")
        self.time_rec= QTimeEdit()
        self.time_rec.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        aplicar_formato_widget_hora(self.time_rec, self.main_window)
        self.time_rec.setToolTip("Hora exacta en que debe sonar.")
        fila_fh.addWidget(self.date_rec)
        fila_fh.addWidget(self.time_rec)
        form.addRow("Fecha y hora:", fila_fh)

        self.combo_repetir= QComboBox()
        self.combo_repetir.addItem("Una sola vez", "unica")
        self.combo_repetir.addItem("Todos los días", "diario")
        self.combo_repetir.addItem("Semanalmente (mismo día)", "semanal")
        self.combo_repetir.setToolTip("Con qué frecuencia se repite este recordatorio.")
        form.addRow("Repetir:", self.combo_repetir)

        layout.addLayout(form)

        fila_botones_rec= QHBoxLayout()
        self.btn_guardar_rec= QPushButton("Agregar recordatorio")
        self.btn_guardar_rec.setIcon(icono_emoji("💾"))
        self.btn_guardar_rec.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar_rec.setToolTip("Guarda este recordatorio en la lista de abajo.")
        self.btn_guardar_rec.clicked.connect(self._guardar_recordatorio)
        self.btn_cancelar_edicion= QPushButton("Cancelar edición")
        self.btn_cancelar_edicion.setVisible(False)
        self.btn_cancelar_edicion.clicked.connect(self._cancelar_edicion)
        fila_botones_rec.addWidget(self.btn_guardar_rec)
        fila_botones_rec.addWidget(self.btn_cancelar_edicion)
        fila_botones_rec.addStretch()
        layout.addLayout(fila_botones_rec)

        self.tabla_rec= QTableWidget(0, 5)
        self.tabla_rec.setHorizontalHeaderLabels(["Título", "Fecha", "Hora", "Repetir", ""])
        self.tabla_rec.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_rec.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_rec.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.tabla_rec, 1)
        return w

    def _guardar_recordatorio(self):

        titulo= self.in_titulo_rec.text().strip()
        if not titulo:
            QMessageBox.warning(self, "Falta el título", "Escribe un título para el recordatorio.")
            return
        fecha= self.date_rec.date().toString("yyyy-MM-dd")
        hora= self.time_rec.time().toString("HH:mm")
        repetir= self.combo_repetir.currentData()
        guardar_recordatorio(self.main_window, self._id_edicion, titulo, fecha, hora, repetir, None, None)
        self._cancelar_edicion()
        self._recargar_tabla_recordatorios()

    def _cancelar_edicion(self):

        self._id_edicion= None
        self.in_titulo_rec.clear()
        self.btn_guardar_rec.setText("Agregar recordatorio")
        self.btn_cancelar_edicion.setVisible(False)

    def _recargar_tabla_recordatorios(self):

        recordatorios= listar_recordatorios(self.main_window)
        self.tabla_rec.setRowCount(len(recordatorios))
        etiquetas_repetir= {"unica": "Una vez", "diario": "Diario", "semanal": "Semanal"}
        for fila, r in enumerate(recordatorios):
            self.tabla_rec.setItem(fila, 0, QTableWidgetItem(r["titulo"]))
            self.tabla_rec.setItem(fila, 1, QTableWidgetItem(formatear_fecha(r["fecha"], self.main_window)))
            self.tabla_rec.setItem(fila, 2, QTableWidgetItem(formatear_hora(r["hora"], self.main_window)))
            self.tabla_rec.setItem(fila, 3, QTableWidgetItem(etiquetas_repetir.get(r["repetir"], r["repetir"])))

            celda_acciones= QWidget()
            lay_acciones= QHBoxLayout(celda_acciones)
            lay_acciones.setContentsMargins(2, 2, 2, 2)
            btn_editar= QPushButton("")
            btn_editar.setIcon(icono_emoji("✏"))
            btn_editar.setIconSize(_QSize_emoji(16, 16))
            btn_editar.setFixedWidth(28)
            btn_editar.setToolTip("Editar este recordatorio.")
            btn_editar.clicked.connect(lambda _c=False, rid=r["id"]: self._editar_recordatorio(rid))
            btn_borrar= QPushButton("")
            btn_borrar.setIcon(icono_emoji("🗑"))
            btn_borrar.setIconSize(_QSize_emoji(16, 16))
            btn_borrar.setFixedWidth(28)
            btn_borrar.setToolTip("Eliminar este recordatorio.")
            btn_borrar.clicked.connect(lambda _c=False, rid=r["id"]: self._borrar_recordatorio(rid))
            lay_acciones.addWidget(btn_editar)
            lay_acciones.addWidget(btn_borrar)
            self.tabla_rec.setCellWidget(fila, 4, celda_acciones)

    def _editar_recordatorio(self, id_recordatorio):

        recordatorios= {r["id"]: r for r in listar_recordatorios(self.main_window)}
        r= recordatorios.get(id_recordatorio)
        if not r:
            return
        self._id_edicion= id_recordatorio
        self.in_titulo_rec.setText(r["titulo"])
        y, m, d= [int(x) for x in r["fecha"].split("-")]
        from PySide6.QtCore import QDate, QTime
        self.date_rec.setDate(QDate(y, m, d))
        hh, mm= [int(x) for x in r["hora"].split(":")[:2]]
        self.time_rec.setTime(QTime(hh, mm))
        idx= self.combo_repetir.findData(r["repetir"])
        if idx >= 0:
            self.combo_repetir.setCurrentIndex(idx)
        self.btn_guardar_rec.setText("Guardar cambios")
        self.btn_cancelar_edicion.setVisible(True)

    def _borrar_recordatorio(self, id_recordatorio):

        respuesta= QMessageBox.question(self, "Eliminar recordatorio",
                                          "¿Eliminar este recordatorio?")
        if respuesta == QMessageBox.StandardButton.Yes:
            eliminar_recordatorio(self.main_window, id_recordatorio)
            self._recargar_tabla_recordatorios()

    #---------------- carga inicial al abrir el diálogo ----------------
    def cargar(self):

        cfg= obtener_config(self.main_window)
        self.combo_tono.blockSignals(True)
        idx= self.combo_tono.findText(cfg.get("tono_defecto", "Campanilla"))
        self.combo_tono.setCurrentIndex(max(0, idx))
        self.combo_tono.blockSignals(False)

        self._ruta_personalizada= cfg.get("tono_defecto_ruta") or ""
        self.lbl_tono_personalizado.setText(
            os.path.basename(self._ruta_personalizada) if self._ruta_personalizada else "(ninguno)")

        for widget, valor in (
            (self.slider_volumen, cfg.get("volumen", VOLUMEN_DEFECTO)),
            (self.slider_duracion, cfg.get("duracion_efecto", DURACION_EFECTO_DEFECTO)),
        ):
            widget.blockSignals(True)
            widget.setValue(valor)
            widget.blockSignals(False)

        for chk, campo in ((self.chk_bucle, "sonido_en_bucle"), (self.chk_efecto, "efecto_visual"),
                            (self.chk_eventos, "avisar_eventos"), (self.chk_clases, "avisar_clases")):
            chk.blockSignals(True)
            chk.setChecked(bool(cfg.get(campo, 1)))
            chk.blockSignals(False)

        self._cancelar_edicion()
        self._recargar_tabla_recordatorios()


#Envoltorio de `PanelAlarmas` como ventana emergente. No se usa desde
#el panel lateral (la configuración vive en Configuración ▸ Mi Cuenta ▸
#Preferencias), pero se deja disponible por si se necesita en otro lugar.
class ConfigurarAlarmasDialog(QDialog):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self.setWindowTitle("Alarmas y recordatorios")
        self.setMinimumWidth(560)
        layout= QVBoxLayout(self)
        self.panel= PanelAlarmas(main_window, self)
        layout.addWidget(self.panel)
        fila_botones= QHBoxLayout()
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.clicked.connect(self.accept)
        fila_botones.addWidget(btn_cerrar)
        layout.addLayout(fila_botones)


#INTEGRACIÓN (referencia rápida — ver también los cambios ya aplicados en main.py y configuracion.py):  1)
#Import arriba del todo de main.py: from alarmas import MotorAlarmas  2) Dentro de MainWindow.__init__, justo
#después de main_layout.addWidget(self.stacked_widget) self.aplicar_tema() agregar: self.motor_alarmas =
#MotorAlarmas(self) self.motor_alarmas.iniciar()  3) En MainWindow.resizeEvent, agregar: if hasattr(self,
#"motor_alarmas"): self.motor_alarmas.reposicionar()  4) En MainWindow.closeEvent / al cerrar sesión,
#opcionalmente: if hasattr(self, "motor_alarmas"): self.motor_alarmas.detener_motor()  5) Configuración visible
#al usuario: en configuracion.py, dentro de ModuloConfiguracion._tab_mi_cuenta(), en la sección de
#"Preferencias de la Aplicación", se agrega una TarjetaSeccion que embebe: from alarmas import PanelAlarmas
#self.panel_alarmas = PanelAlarmas(self.main_window) t_alarmas.contenido.addWidget(self.panel_alarmas) (ver el
#bloque ya insertado en _tab_mi_cuenta, justo después de la tarjeta "Preferencias de la Aplicación").
