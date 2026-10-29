#Sincronización (Fase A) de AcaDeXI — patrón "carpeta compartida".
#
#El usuario indica la ruta local de un cliente de nube ya instalado
#(Google Drive, OneDrive, Dropbox, Nextcloud) o de un servidor NAS montado
#en su equipo. AcaDeXI copia allí un archivo canónico `acadexi_sync.db` y
#lo compara por hash SHA-256 contra la última versión conocida por ESTE
#equipo (guardada en config.json local, no en la BD, porque cada equipo
#tiene su propio estado) para detectar:
#- Sincronizado: nada que hacer.
#- Hay novedades: el remoto cambió (otro equipo subió) -> Descargar.
#- Cambios locales: solo este equipo cambió -> Subir.
#- Conflicto: ambos cambiaron desde la última sincronización -> el usuario
#elige cuál gana, con backup de seguridad automático antes de sobrescribir.
#
#Sin credenciales OAuth ni API: depende 100% de que el cliente de escritorio
#de la nube ya sincronice esa carpeta a sus servidores. La integración
#directa (Fase B: PyDrive2/MSAL/Dropbox SDK) requeriría credenciales propias
#del usuario/institución y queda fuera de este alcance.
#
# -----------------------------------------
# capa visual: tarjetas con esquinas redondeadas, "latido" de color en el
# -----------------------------------------
#estado cuando hace falta una acción del usuario, un spinner circular propio
#(sin depender de imágenes) para las operaciones que corren en segundo plano,
#y un acordeón animado para la sección avanzada. Toda la lógica de datos es
#la misma de siempre; sólo cambió cómo se presenta.
import os
import hashlib
import shutil
import webbrowser
import zipfile
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QMessageBox, QStackedWidget, QInputDialog,
    QScrollArea, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QButtonGroup,
    QApplication)
from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup,
    QRect, QRectF, Property, Signal, QThread)
from PySide6.QtGui import QPainter, QPen, QColor

from src.nucleo.bd import RUTA_BD, crear_backup, registrar_auditoria
from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_cabecera
from src.nucleo.atajos import registrar_atajo
from src.sincronizacion import sync_backends as avanzado
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, EMOJI_SYNC_SUBIR, EMOJI_SYNC_DESCARGAR,
                           EMOJI_SYNC_SUBIR_DIRECTO, EMOJI_SYNC_DESCARGAR_DIRECTO)
from src.nucleo.rutas import buscar_dato

NOMBRE_ARCHIVO_SYNC= "acadexi_sync.db"

#Paquete exportable del servidor institucional Contenido generado al vuelo (no depende de archivos externos que
#pudieran faltar) para el botón "📦 Exportar Servidor Institucional":
#scripts de arranque con un doble clic y una guía en español con 3 formas realistas de tener el servidor
#accesible, pensadas para instituciones con presupuestos muy distintos — desde un colegio sin nada de
#presupuesto para hosting, hasta uno que sí puede pagar un VPS.
_SCRIPT_INICIO_SH= """#!/bin/bash
#Inicia el Servidor Institucional de AcaDeXI.
#En Linux/Mac: clic derecho > Propiedades > marcar "Permitir ejecutar
#como programa" (o una vez: chmod +x iniciar_servidor.sh), y luego
#doble clic. También puedes ejecutarlo desde una terminal:
#./iniciar_servidor.sh
cd "$(dirname "$0")"
echo "Iniciando Servidor Institucional AcaDeXI..."
echo "(deja esta ventana abierta mientras quieras que siga funcionando)"
python3 servidor_institucional.py
"""

_SCRIPT_INICIO_BAT= """@echo off
REM Inicia el Servidor Institucional de AcaDeXI.
REM Windows: solo haz doble clic en este archivo.
cd /d "%~dp0"
echo Iniciando Servidor Institucional AcaDeXI...
echo (deja esta ventana abierta mientras quieras que siga funcionando)
python servidor_institucional.py
pause
"""

_GUIA_SERVIDOR_TXT= """====================================================================
 SERVIDOR INSTITUCIONAL DE ACADEXI - GUIA RAPIDA
====================================================================

Este paquete pone en marcha un pequeno servidor que permite que los
equipos con AcaDeXI se sincronicen entre si de forma directa, sin
depender de que alguien tenga instalado Google Drive, Dropbox u
OneDrive.

Requiere tener Python 3.9 o mas reciente instalado:
https://www.python.org/downloads/
(En Windows, durante la instalacion marca la casilla "Add Python to
PATH" — sin eso, los pasos siguientes no van a funcionar).

--------------------------------------------------------------------
PASO 1 - Instalar lo necesario (una sola vez)
--------------------------------------------------------------------
Abre una terminal / simbolo del sistema en esta misma carpeta y
ejecuta:

    pip install -r requirements_servidor.txt

--------------------------------------------------------------------
PASO 2 - Iniciarlo
--------------------------------------------------------------------
Windows:    doble clic en  iniciar_servidor.bat
Linux/Mac:  doble clic en  iniciar_servidor.sh
            (o desde una terminal:  python3 servidor_institucional.py)

La PRIMERA vez, el servidor genera automaticamente un TOKEN de acceso
y lo muestra en pantalla junto con la direccion (URL) que debes usar.
Ya no hace falta configurar nada a mano: anota ambos datos, los vas a
necesitar en el Paso 4.

--------------------------------------------------------------------
PASO 3 - Elegir como hacerlo accesible
--------------------------------------------------------------------
Hay 3 formas realistas, de la mas sencilla y gratuita a la mas
robusta (y de pago). No hace falta ser experto en servidores para la
primera — es la que recomendamos para empezar, sobre todo si no hay
presupuesto para hosting.

OPCION A - Gratis, en un equipo del colegio
  El servidor corre en cualquier PC del colegio (puede ser uno viejo
  que ya no se use para otra cosa) conectado a internet.

  - Si TODOS los equipos con AcaDeXI estan en la MISMA red local
    (mismo edificio/wifi): usa directamente la URL local que muestra
    el servidor al iniciar (algo como http://192.168.1.50:8420) — no
    necesitas nada mas.

  - Si necesitas que equipos de OTRA sede tambien se conecten: usa un
    "tunel" gratuito para obtener una URL publica con HTTPS, sin
    configurar redes ni certificados. Con Python ya instalado:
      1. Instala cloudflared (gratis, de Cloudflare) o ngrok.
      2. Ejecuta:  cloudflared tunnel --url http://localhost:8420
      3. Te da una URL publica (algo como
         https://ejemplo.trycloudflare.com): esa es la que se
         comparte con los otros equipos.

  Nota: el PC debe permanecer encendido para que la sincronizacion
  funcione. Estas herramientas cambian con el tiempo — si algun paso
  no coincide exactamente, busca "cloudflared quick tunnel" o "ngrok
  free" para ver las instrucciones vigentes.

OPCION B - Gratis, en la nube (sin usar un equipo propio)
  Varias plataformas ofrecen un nivel gratuito para aplicaciones
  Python pequenas como esta (por ejemplo Render, Railway, Fly.io,
  PythonAnywhere, entre otras). La oferta y sus limites cambian con
  frecuencia, asi que conviene buscar "hosting gratis para apps
  Python" o "hosting gratis FastAPI" para ver que opcion esta vigente
  ahora mismo. En general el proceso es:
    1. Crea una cuenta gratuita en la plataforma elegida.
    2. Sube esta carpeta (o conectala desde un repositorio Git).
    3. Indica como comando de inicio:  python servidor_institucional.py
       (el servidor ya respeta automaticamente el puerto que la
       plataforma le asigne, no hay que tocar nada del codigo).
    4. La plataforma entrega una URL publica con HTTPS ya incluido.
  Estas plataformas suelen "dormir" la app tras un rato sin uso en su
  nivel gratuito: la primera sincronizacion del dia puede tardar unos
  segundos mas en responder mientras despierta — es normal.

OPCION C - De pago, en un VPS propio (para instituciones con
           presupuesto; la mas estable y siempre encendida)
  Un servidor privado virtual (VPS) economico (DigitalOcean, AWS
  Lightsail, Hetzner, Vultr, o un proveedor local de tu pais) desde
  unos pocos dolares al mes.
    1. Sube esta carpeta al VPS (scp, git, o el panel del proveedor).
    2. Instala Python y las dependencias (Paso 1).
    3. Ejecutalo para que quede SIEMPRE encendido (no en una terminal
       que se cierra sola), por ejemplo con systemd, pm2 o tmux/screen.
    4. Recomendado: colocalo detras de Nginx o Caddy como proxy
       inverso con HTTPS — Caddy lo deja casi automatico.

--------------------------------------------------------------------
PASO 4 - Conectar cada equipo con AcaDeXI
--------------------------------------------------------------------
En cada equipo que vaya a usar este metodo:
  Sincronizacion > Sincronizacion Directa > "Servidor institucional
  propio" > pega la URL y el token del Paso 2 > Conectar.

Cada equipo necesita conectarse por separado (este paso no se hace
una sola vez para toda la institucion).

--------------------------------------------------------------------
Seguridad
--------------------------------------------------------------------
- No compartas el token fuera de tu institucion: quien lo tenga puede
  leer y reemplazar el archivo sincronizado.
- Si sospechas que el token se filtro, borra el archivo
  token_acadexi.txt (aparece junto a servidor_institucional.py luego
  del primer inicio) y reinicia el servidor: genera uno nuevo
  automaticamente.
- Usar HTTPS evita que el token viaje "en claro" por la red. Las
  opciones A (con tunel) y B ya lo dan gratis de forma automatica; en
  la opcion C, activalo con Caddy o Nginx.
====================================================================
"""
MODOS_TRABAJO= ["Local", "Nube sincronizada", "Servidor institucional", "Sin conexión (offline)"]

#Explicación de cada modo, mostrada como tooltip tanto en el combo cerrado como en cada opción de la lista
#desplegable.
TOOLTIPS_MODOS_TRABAJO= {
    "Local": "Este equipo trabaja con su propia base de datos, sin depender de "
             "ninguna carpeta compartida ni servidor. Usa \u201cSubir Cambios\u201d / "
             "\u201cDescargar Novedades\u201d cuando quieras intercambiar datos con otros equipos.",
    "Nube sincronizada": "Este equipo usa una carpeta mantenida por un cliente de nube ya "
             "instalado (Google Drive, OneDrive, Dropbox, Nextcloud, etc.). AcaDeXI no se "
             "conecta a esos servicios: solo lee/escribe en la carpeta local que ese cliente "
             "mantiene sincronizada.",
    "Servidor institucional": "Este equipo trabaja contra un servidor central de la "
             "institución. Es el modo recomendado cuando varios equipos deben ver siempre "
             "los mismos datos actualizados.",
    "Sin conexión (offline)": "Este equipo trabaja completamente aislado: no sube ni "
             "descarga cambios de ninguna carpeta ni servidor. Útil para trabajar sin "
             "conexión; recuerda sincronizar manualmente cuando vuelvas a tener acceso.",
}


_CACHE_HASHES= {}  #ruta -> ((mtime_ns, tamaño), hash) — evita rehashear archivos sin cambios


def _hash_archivo(ruta):

    if not ruta or not os.path.exists(ruta):
        return None
    firma= None
    try:

        est= os.stat(ruta)
        firma= (est.st_mtime_ns, est.st_size)
    except OSError:
        pass
    if firma is not None:
        cacheado= _CACHE_HASHES.get(ruta)
        if cacheado is not None and cacheado[0] == firma:
            return cacheado[1]
    huella= hashlib.sha256()
    with open(ruta, "rb") as f:
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        for bloque in iter(lambda: f.read(65536), b""):
            huella.update(bloque)
    digest= huella.hexdigest()
    if firma is not None:
        _CACHE_HASHES[ruta]= (firma, digest)
    return digest


def _ruta_remota(carpeta):

    return os.path.join(carpeta, NOMBRE_ARCHIVO_SYNC) if carpeta else None


#Devuelve el estado de sincronización de este equipo frente a la
#carpeta compartida configurada localmente (main_window.carpeta_sincronizacion).
def obtener_estado(main_window):

    carpeta= getattr(main_window, "carpeta_sincronizacion", "") or ""
    if not carpeta or not os.path.isdir(carpeta):
        return {"estado": "sin_carpeta", "carpeta": carpeta}

    ruta_remota= _ruta_remota(carpeta)
    hash_remoto= _hash_archivo(ruta_remota)
    if hash_remoto is None:
        return {"estado": "sin_copia_remota", "carpeta": carpeta, "ruta_remota": ruta_remota}

    hash_local= _hash_archivo(RUTA_BD)
    hash_ultima_sync= getattr(main_window, "sync_ultimo_hash", "") or None

    if hash_local == hash_remoto:
        estado= "sincronizado"
    else:
        local_cambio= hash_local != hash_ultima_sync
        remoto_cambio= hash_remoto != hash_ultima_sync
        if local_cambio and remoto_cambio:
            estado= "conflicto"
        elif remoto_cambio:
            estado= "hay_novedades"
        else:
            estado= "cambios_locales"

    return {"estado": estado, "carpeta": carpeta, "ruta_remota": ruta_remota,
            "hash_local": hash_local, "hash_remoto": hash_remoto}


#Copia la BD local a la carpeta compartida; el cliente de nube ya
#instalado se encarga de subirla a sus servidores.
def subir_cambios(main_window):

    carpeta= getattr(main_window, "carpeta_sincronizacion", "") or ""
    if not carpeta or not os.path.isdir(carpeta):
        raise RuntimeError("No hay una carpeta de sincronización configurada o la ruta ya no existe.")
    destino= _ruta_remota(carpeta)
    shutil.copy2(RUTA_BD, destino)
    main_window.sync_ultimo_hash= _hash_archivo(RUTA_BD)
    main_window.sync_ultima_fecha= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    main_window.guardar_configuracion()
    return destino


#Trae la copia de la carpeta compartida a este equipo. Antes crea un
#backup de seguridad local por si hay que revertir.
def descargar_novedades(main_window):

    carpeta= getattr(main_window, "carpeta_sincronizacion", "") or ""
    if not carpeta or not os.path.isdir(carpeta):
        raise RuntimeError("No hay una carpeta de sincronización configurada o la ruta ya no existe.")
    origen= _ruta_remota(carpeta)
    if not os.path.exists(origen):
        raise RuntimeError("Todavía no hay una copia en la carpeta compartida.")
    ruta_respaldo= crear_backup(tipo="Pre-sincronización", usuario=getattr(main_window, "usuario_actual", None))
    shutil.copy2(origen, RUTA_BD)
    main_window.sync_ultimo_hash= _hash_archivo(RUTA_BD)
    main_window.sync_ultima_fecha= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    main_window.guardar_configuracion()
    return ruta_respaldo


#Capa visual — componentes reutilizables (tarjetas, spinner, animaciones)
ESTADOS_VISUAL= {
    "sin_carpeta":      {"color": "#94A3B8", "icono": "📁", "pulso": False,
                          "titulo": "Sin configurar",
                          "detalle": "No hay carpeta de sincronización configurada."},
    "sin_copia_remota": {"color": "#6366F1", "icono": "\uE002", "pulso": True,
                          "titulo": "Lista para el primer envío",
                          "detalle": "Carpeta configurada, pero aún no hay copia allí. Usa “Subir Cambios”."},
    "sincronizado":     {"color": "#22C55E", "icono": "✅", "pulso": False,
                          "titulo": "Todo sincronizado",
                          "detalle": "Este equipo y la carpeta compartida tienen la misma versión."},
    "hay_novedades":    {"color": "#3B82F6", "icono": "\uE001", "pulso": True,
                          "titulo": "Hay novedades disponibles",
                          "detalle": "La carpeta compartida cambió. Usa “Descargar Novedades”."},
    "cambios_locales":  {"color": "#F59E0B", "icono": "\uE002", "pulso": True,
                          "titulo": "Tienes cambios sin subir",
                          "detalle": "Este equipo tiene cambios locales. Usa “Subir Cambios”."},
    "conflicto":        {"color": "#EF4444", "icono": "⚠", "pulso": True,
                          "titulo": "Conflicto de sincronización",
                          "detalle": "Este equipo y la carpeta compartida cambiaron por separado."},
}


def _hex_a_rgba(color_hex, alpha):

    color_hex= color_hex.lstrip("#")
    r, g, b= int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


#Pequeño 'rebote' visual al presionar un botón.
def _animar_click(boton):

    geo= boton.geometry()
    if geo.width() <= 0 or geo.height() <= 0:
        return
    centro= geo.center()
    reducido= QRect(0, 0, max(1, int(geo.width() * 0.95)), max(1, int(geo.height() * 0.88)))
    reducido.moveCenter(centro)
    anim= QPropertyAnimation(boton, b"geometry")
    anim.setDuration(150)
    anim.setStartValue(geo)
    anim.setKeyValueAt(0.5, reducido)
    anim.setEndValue(geo)
    anim.setEasingCurve(QEasingCurve.Type.OutQuad)
    boton._anim_rebote= anim  #evita que el recolector de basura la corte a mitad de vuelo
    anim.start()


def _crear_sombra(color="#000000", blur=20, y=5, alpha=110):

    efecto= QGraphicsDropShadowEffect()
    c= QColor(color)
    c.setAlpha(alpha)
    efecto.setColor(c)
    efecto.setBlurRadius(blur)
    efecto.setOffset(0, y)
    return efecto


#Animación de 'respiración' (sube y baja en bucle) sobre una propiedad Qt.
#Se usa para dar un latido sutil a las tarjetas que requieren atención.
def _crear_pulso(objetivo, propiedad, minimo, maximo, duracion=950):

    grupo= QSequentialAnimationGroup(objetivo)
    subir= QPropertyAnimation(objetivo, propiedad)
    subir.setStartValue(minimo)
    subir.setEndValue(maximo)
    subir.setDuration(duracion)
    subir.setEasingCurve(QEasingCurve.Type.InOutSine)
    bajar= QPropertyAnimation(objetivo, propiedad)
    bajar.setStartValue(maximo)
    bajar.setEndValue(minimo)
    bajar.setDuration(duracion)
    bajar.setEasingCurve(QEasingCurve.Type.InOutSine)
    grupo.addAnimation(subir)
    grupo.addAnimation(bajar)
    grupo.setLoopCount(-1)
    return grupo


#Aplica un fundido de entrada (opacidad 0→1) a `widget` y, esto es lo
#importante, DESPRENDE el QGraphicsOpacityEffect apenas termina
#(setGraphicsEffect(None)). Un efecto que se queda pegado permanentemente
#a un widget hace que Qt, en ciertos casos, no repinte correctamente
#actualizaciones que llegan después de que la animación terminó — el
#widget queda invisible hasta la próxima interacción manual del usuario
#(mover el mouse encima, hacer click, etc.). Se usa cada vez que un panel
#o tarjeta aparece o cambia de contenido.
def _fundido_entrada(widget, duracion=260):

    efecto= QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(efecto)
    anim= QPropertyAnimation(efecto, b"opacity", widget)
    anim.setDuration(duracion)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    #_v: valor animado que no se usa; w= fija el widget que se repinta
    anim.valueChanged.connect(lambda _v, w=widget: w.update())
    widget._anim_fundido= anim  #evita que el recolector de basura la corte a mitad de vuelo

    def _limpiar(w=widget):

        w.setGraphicsEffect(None)
        w.update()

    anim.finished.connect(_limpiar)
    anim.start()


#Indicador de carga circular animado (arco giratorio), dibujado a mano
#para no depender de ningún archivo de imagen/GIF.
class SpinnerCircular(QWidget):

    def __init__(self, parent=None, diametro=20, color="#6366F1", grosor=3):

        super().__init__(parent)
        self._angulo= 0.0
        self._color= QColor(color)
        self._grosor= grosor
        self.setFixedSize(diametro, diametro)
        self._anim= QPropertyAnimation(self, b"angulo", self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(360.0)
        self._anim.setDuration(850)
        self._anim.setLoopCount(-1)
        self.hide()

    def _leer_angulo(self):

        return self._angulo

    def _poner_angulo(self, valor):

        self._angulo= valor
        self.update()

    angulo= Property(float, _leer_angulo, _poner_angulo)

    def poner_color(self, color):

        self._color= QColor(color)
        self.update()

    def iniciar(self):

        self.show()
        self._anim.start()

    def detener(self):

        self._anim.stop()
        self.hide()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margen= self._grosor
        rect= QRectF(margen, margen, self.width() - 2 * margen, self.height() - 2 * margen)
        pluma= QPen(self._color)
        pluma.setWidth(self._grosor)
        pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pluma)
        painter.drawArc(rect, int(-self._angulo * 16), 100 * 16)


#Ejecuta una operación de sincronización (copiar/subir/descargar) en
#segundo plano para que la interfaz no se congele y el spinner se anime
#con fluidez mientras dura la operación.
class _HiloOperacionSync(QThread):

    terminado= Signal(object, object)  #(resultado, excepción o None)

    def __init__(self, funcion, parent=None):

        super().__init__(parent)
        self._funcion= funcion

    def run(self):

        try:

            resultado= self._funcion()
            self.terminado.emit(resultado, None)
        except Exception as error:  #se reporta al usuario en el hilo principal, no se silencia
            self.terminado.emit(None, error)


#Tarjeta grande que resume el estado de sincronización, con un latido
#de color sutil cuando hace falta una acción del usuario.
class TarjetaEstado(QFrame):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setObjectName("TarjetaEstadoSync")
        self._pulso= None
        self._sombra= _crear_sombra(blur=22, y=6, alpha=90)
        self.setGraphicsEffect(self._sombra)

        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(20, 18, 20, 18)
        disposicion.setSpacing(16)

        self.lbl_icono= QLabel()
        self.lbl_icono.setPixmap(pixmap_emoji("➕", 20))
        self.lbl_icono.setFixedSize(46, 46)
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icono.setObjectName("IconoEstadoSync")
        disposicion.addWidget(self.lbl_icono)

        columna= QVBoxLayout()
        columna.setSpacing(2)
        self.lbl_titulo= QLabel("Verificando…")
        self.lbl_titulo.setObjectName("TituloEstadoSync")
        columna.addWidget(self.lbl_titulo)
        self.lbl_detalle= QLabel("")
        self.lbl_detalle.setObjectName("DetalleEstadoSync")
        self.lbl_detalle.setWordWrap(True)
        columna.addWidget(self.lbl_detalle)
        disposicion.addLayout(columna, 1)

        self.spinner= SpinnerCircular(self, diametro=22, color="#6366F1")
        disposicion.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignVCenter)

        self._color_actual= "#94A3B8"

    def actualizar(self, clave_estado):

        info= ESTADOS_VISUAL.get(clave_estado, ESTADOS_VISUAL["sin_carpeta"])
        color= info["color"]
        self._color_actual= color
        #setPixmap (no setText): lbl_icono se construyó con un pixmap
        #vectorial (ver __init__); usar setText aquí lo cambiaría a modo
        #texto y perdería la coherencia con el resto de los íconos de la app.
        self.lbl_icono.setPixmap(pixmap_emoji(info["icono"], 20))
        self.lbl_titulo.setText(info["titulo"])
        self.lbl_detalle.setText(info["detalle"])
        self.setStyleSheet(f"""
            QFrame#TarjetaEstadoSync {{
                background-color: {_hex_a_rgba(color, 0.10)};
                border: 1px solid {_hex_a_rgba(color, 0.35)};
                border-radius: 14px;
            }}
            QLabel#IconoEstadoSync {{
                background-color: {_hex_a_rgba(color, 0.18)};
                border-radius: 23px;
                font-size: 20px;
            }}
            QLabel#TituloEstadoSync {{
                font-size: 16px;
                font-weight: 800;
                color: {color};
                background: transparent;
            }}
            QLabel#DetalleEstadoSync {{
                font-size: 12px;
                background: transparent;
            }}
        """)
        self._sombra.setColor(QColor(color))
        if self._pulso:
            self._pulso.stop()
            self._pulso= None
        self._sombra.setBlurRadius(22)
        if info["pulso"]:
            self._pulso= _crear_pulso(self._sombra, b"blurRadius", 16, 34, duracion=1000)
            self._pulso.start()

    def mostrar_ocupado(self, texto="Sincronizando…"):

        self.lbl_titulo.setText(texto)
        self.spinner.poner_color(self._color_actual)
        self.spinner.iniciar()

    def ocultar_ocupado(self):

        self.spinner.detener()


#Arma, al vuelo, un ZIP autocontenido con servidor_institucional.py,
#sus dependencias, scripts para iniciarlo con un doble clic (sin
#terminal) y una guía en español con 3 formas reales de tenerlo
#accesible — de gratis (un equipo del colegio, o una capa gratuita en
#la nube) a de pago (un VPS propio) — pensadas para instituciones con
#presupuestos muy distintos, no solo para las que puedan pagar un
#servidor dedicado. Es una función de módulo (no un método) para que
#tanto el panel de Sincronización como el Asistente de Configuración
#puedan ofrecer el mismo botón sin duplicar esta lógica.
#
#`padre` es el widget que sirve de contexto para los diálogos (el
#propio panel o la página del asistente que llama a esta función).
def exportar_paquete_servidor(main_window, padre):

    ruta_servidor= buscar_dato("servidor_institucional.py")
    ruta_requisitos= buscar_dato("requirements_servidor.txt")
    if not os.path.exists(ruta_servidor) or not os.path.exists(ruta_requisitos):
        mostrar_mensaje("advertencia", "Archivos no encontrados",
                        "No se encontraron servidor_institucional.py y/o "
                        "requirements_servidor.txt junto a la aplicación.", padre)
        return

    destino, _= QFileDialog.getSaveFileName(
        padre, "Exportar Servidor Institucional",
        "AcaDeXI_Servidor_Institucional.zip", "Archivo ZIP (*.zip)")
    if not destino:
        return
    if not destino.lower().endswith(".zip"):
        destino += ".zip"

    try:

        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(ruta_servidor, "servidor_institucional.py")
            z.write(ruta_requisitos, "requirements_servidor.txt")
            z.writestr("iniciar_servidor.sh", _SCRIPT_INICIO_SH)
            z.writestr("iniciar_servidor.bat", _SCRIPT_INICIO_BAT)
            z.writestr("LEEME_PRIMERO.txt", _GUIA_SERVIDOR_TXT)
    except Exception as error:
        mostrar_mensaje("error", "Error", f"No se pudo crear el paquete:\n{error}", padre)
        return

    if main_window is not None:
        registrar_auditoria("Sistema", "Exportó el paquete del Servidor Institucional",
                            getattr(main_window, "usuario_actual", None), destino)
    mostrar_mensaje("exito", "Paquete exportado",
                    f"Se guardó en:\n{destino}\n\n"
                    "Contiene el servidor, sus dependencias, scripts para iniciarlo con "
                    "un doble clic (sin necesitar terminal) y una guía — LEEME_PRIMERO.txt "
                    "— con 3 formas de tenerlo accesible, de gratis a de pago. Compártelo "
                    "con quien vaya a ponerlo en marcha (por ejemplo, por correo o USB).", padre)


#Módulo principal
#Vista de 'este equipo': modo de trabajo, carpeta compartida y las
#acciones reales de sincronización (Fase A, sin OAuth).
class ModuloSincronizacion(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._hilo= None
        self._hilo_avanzado= None
        self._hilo_estado= None
        self._avanzado_abierto= False
        self._metodo_avanzado_actual_clave= None
        self._titulo_modulo_atajos= "Sincronización"
        self._construir_ui()
        self._configurar_atajos()
        self.actualizar_tema()
        self.refrescar()

    #Atajos de teclado (ver atajos.py)
    def _configurar_atajos(self):

        registrar_atajo(self, self.main_window, "Ctrl+Up", "Subir cambios", self._subir)
        registrar_atajo(self, self.main_window, "Ctrl+Down", "Descargar novedades", self._descargar)
        registrar_atajo(self, self.main_window, "Ctrl+R", "Verificar ahora", self._refrescar_estado)
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar preferencia de este equipo", self._guardar)
        registrar_atajo(self, self.main_window, "Ctrl+E", "Elegir carpeta de sincronización", self._elegir_carpeta)

    #Construcción de la interfaz
    def _construir_ui(self):

        layout_externo= QVBoxLayout(self)
        layout_externo.setContentsMargins(0, 0, 0, 0)

        contenido= QWidget()
        self._contenido= contenido
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(16)

        #--- Cabecera tipo "hero": icono + título + descripción ---
        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabecera")
        cabecera_layout= QHBoxLayout(self.frame_cabecera)
        cabecera_layout.setContentsMargins(22, 18, 22, 18)
        cabecera_layout.setSpacing(14)

        self.lbl_icono_modulo= QLabel()
        self.lbl_icono_modulo.setPixmap(pixmap_emoji("💡", 20))
        self.lbl_icono_modulo.setObjectName("IconoCabeceraModulo")
        self.lbl_icono_modulo.setFixedSize(46, 46)
        self.lbl_icono_modulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(self.lbl_icono_modulo, "Sincronización")
        cabecera_layout.addWidget(self.lbl_icono_modulo)

        bloque_titulo_cabecera= QVBoxLayout()
        bloque_titulo_cabecera.setSpacing(2)
        self.lbl_titulo_cabecera= QLabel("Sincronización")
        self.lbl_titulo_cabecera.setObjectName("TituloCabeceraModulo")
        self.lbl_subtitulo_cabecera= QLabel(
            "Configura cómo trabaja ESTE equipo. Si usas una carpeta sincronizada por un "
            "cliente de nube ya instalado (Google Drive, OneDrive, Dropbox, Nextcloud, etc.), "
            "indica aquí su ruta local; AcaDeXI no se conecta directamente a esos servicios, "
            "depende de que el cliente de escritorio ya la mantenga sincronizada.")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraModulo")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo_cabecera.addWidget(self.lbl_titulo_cabecera)
        bloque_titulo_cabecera.addWidget(self.lbl_subtitulo_cabecera)
        cabecera_layout.addLayout(bloque_titulo_cabecera, 1)

        disposicion.addWidget(self.frame_cabecera)

        #--- Estado de sincronización ---
        self.tarjeta_estado= TarjetaEstado()
        disposicion.addWidget(self.tarjeta_estado)

        fila_acciones= QHBoxLayout()
        fila_acciones.setSpacing(10)
        self.btn_subir= self._boton_accion("Subir Cambios", "BtnAccionAgregar", self._subir)
        #Iconos únicos por botón (EMOJI_SYNC_*): el iconizador automático les pondría la MISMA bandeja de
        #importar/exportar a los cuatro.
        self.btn_subir.setIcon(icono_emoji(EMOJI_SYNC_SUBIR))
        self.btn_subir.setIconSize(_QSize_emoji(18, 18))
        fila_acciones.addWidget(self.btn_subir)
        self.btn_descargar= self._boton_accion("Descargar Novedades", "BtnAccionAjustar", self._descargar)
        self.btn_descargar.setIcon(icono_emoji(EMOJI_SYNC_DESCARGAR))
        self.btn_descargar.setIconSize(_QSize_emoji(18, 18))
        fila_acciones.addWidget(self.btn_descargar)
        btn_refrescar= self._boton_accion("Verificar Ahora", "BtnAccionNeutro", self._refrescar_estado)
        fila_acciones.addWidget(btn_refrescar)
        fila_acciones.addStretch()
        disposicion.addLayout(fila_acciones)

        #--- Este equipo ---
        disposicion.addWidget(self._tarjeta_este_equipo())

        #--- Sincronización directa (avanzada, colapsable) ---
        disposicion.addWidget(self._tarjeta_avanzada())

        disposicion.addStretch()

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(contenido)
        layout_externo.addWidget(scroll)

    def _boton_accion(self, texto, object_name, callback):

        btn_boton= QPushButton(texto)
        btn_boton.setObjectName(object_name)
        btn_boton.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_boton.clicked.connect(callback)
        #El estilo global vuelve el texto casi ilegible cuando el botón está
        #deshabilitado (fondo y letra quedan casi del mismo tono). Se busca
        #que se note que "no se puede pulsar ahora mismo" sin sacrificar la lectura: fondo apagado con buen contraste,
        #sin importar el tema.
        btn_boton.setStyleSheet("""
            QPushButton:disabled {
                color: rgba(148, 163, 184, 0.95);
                background-color: rgba(100, 116, 139, 0.18);
                border: 1px solid rgba(148, 163, 184, 0.25);
            }
        """)
        return btn_boton

    def _tarjeta_este_equipo(self):

        tarjeta= QFrame()
        tarjeta.setObjectName("TarjetaSeccionSync")
        tarjeta.setGraphicsEffect(_crear_sombra(blur=16, y=3, alpha=55))
        disposicion= QVBoxLayout(tarjeta)
        disposicion.setContentsMargins(20, 16, 20, 18)
        disposicion.setSpacing(8)

        cab= QHBoxLayout()
        lbl_icono= QLabel()
        lbl_icono.setPixmap(pixmap_emoji("➕", 20))
        lbl_icono.setObjectName("IconoSeccionSync")
        cab.addWidget(lbl_icono)
        lbl_titulo_seccion= QLabel("Este equipo")
        lbl_titulo_seccion.setObjectName("TituloSeccionSync")
        cab.addWidget(lbl_titulo_seccion)
        cab.addStretch()
        disposicion.addLayout(cab)

        disposicion.addWidget(QLabel("Modo de trabajo de este equipo:"))
        self.combo_modo= QComboBox()
        self.combo_modo.addItems(MODOS_TRABAJO)
        for i, modo in enumerate(MODOS_TRABAJO):
            self.combo_modo.setItemData(i, TOOLTIPS_MODOS_TRABAJO.get(modo, ""), Qt.ItemDataRole.ToolTipRole)
        self.combo_modo.setToolTip(TOOLTIPS_MODOS_TRABAJO.get(self.combo_modo.currentText(), ""))
        self.combo_modo.currentTextChanged.connect(
            #texto: modo de trabajo elegido; su descripción se muestra como tooltip
            lambda texto: self.combo_modo.setToolTip(TOOLTIPS_MODOS_TRABAJO.get(texto, "")))
        disposicion.addWidget(self.combo_modo)

        disposicion.addWidget(QLabel("Carpeta de sincronización (opcional):"))
        fila= QHBoxLayout()
        self.in_carpeta= QLineEdit()
        limitar_campo_texto(self.in_carpeta, 300)
        self.in_carpeta.setPlaceholderText("Sin carpeta de sincronización")
        fila.addWidget(self.in_carpeta)
        btn_examinar= QPushButton("")
        btn_examinar.setIcon(icono_emoji("📁"))
        btn_examinar.setIconSize(_QSize_emoji(16, 16))
        btn_examinar.setObjectName("BtnAccionNeutro")
        btn_examinar.setFixedWidth(44)
        btn_examinar.setToolTip("Elegir carpeta en este equipo")
        btn_examinar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_examinar.clicked.connect(self._elegir_carpeta)
        fila.addWidget(btn_examinar)
        disposicion.addLayout(fila)

        btn_guardar= self._boton_accion("Guardar Preferencia de este Equipo", "BtnAccionEditar", self._guardar)
        disposicion.addWidget(btn_guardar)

        return tarjeta

    def _tarjeta_avanzada(self):

        tarjeta= QFrame()
        tarjeta.setObjectName("TarjetaSeccionSync")
        tarjeta.setGraphicsEffect(_crear_sombra(blur=16, y=3, alpha=55))
        disposicion= QVBoxLayout(tarjeta)
        disposicion.setContentsMargins(20, 16, 20, 12)
        disposicion.setSpacing(6)

        self.btn_toggle_avanzado= QPushButton("▸  Sincronización Directa (avanzada, opcional)")
        self.btn_toggle_avanzado.setObjectName("BtnToggleAvanzadoSync")
        self.btn_toggle_avanzado.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_avanzado.clicked.connect(self._alternar_avanzado)
        disposicion.addWidget(self.btn_toggle_avanzado)

        #El contenido (formularios de Google/Dropbox/OneDrive/Servidor) es relativamente costoso de construir y casi
        #nunca se usa de entrada, así que el panel arranca vacío: se rellena recién la primera vez que el usuario lo
        #despliega (ver _construir_contenido_avanzado).
        self.panel_avanzado= QWidget()
        self.panel_avanzado.setMaximumHeight(0)
        self.panel_avanzado.setMinimumHeight(0)
        disposicion.addWidget(self.panel_avanzado)
        self._contenido_avanzado_listo= False

        self._anim_avanzado= QPropertyAnimation(self.panel_avanzado, b"maximumHeight", self)
        self._anim_avanzado.setDuration(260)
        self._anim_avanzado.setEasingCurve(QEasingCurve.Type.InOutCubic)

        return tarjeta

    #Construye los formularios de los backends avanzados. Se llama una
    #sola vez, la primera vez que el usuario despliega esta sección.
    def _construir_contenido_avanzado(self):

        if self._contenido_avanzado_listo:
            return
        self._contenido_avanzado_listo= True

        contenido_av= QVBoxLayout(self.panel_avanzado)
        contenido_av.setContentsMargins(2, 8, 2, 2)
        contenido_av.setSpacing(12)

        lbl_desc_avanzada= QLabel("Alternativa a la carpeta compartida: conecta directamente una cuenta "
                               "de nube o tu propio servidor institucional, sin depender de un cliente "
                               "de escritorio ya instalado. Requiere credenciales propias de tu "
                               "institución (ver detalles en cada panel).")
        lbl_desc_avanzada.setObjectName("DescModulo")
        lbl_desc_avanzada.setWordWrap(True)
        contenido_av.addWidget(lbl_desc_avanzada)

        fila_asistente= QHBoxLayout()
        fila_asistente.setSpacing(10)
        btn_asistente= self._boton_accion("Asistente de Configuración", "BtnAccionAjustar", self._abrir_asistente)
        fila_asistente.addWidget(btn_asistente)
        btn_guia_pdf= self._boton_accion("Descargar Guía (PDF)", "BtnAccionNeutro", self._descargar_guia_pdf)
        fila_asistente.addWidget(btn_guia_pdf)
        fila_asistente.addStretch()
        contenido_av.addLayout(fila_asistente)

        #Fila aparte para "Exportar Servidor Institucional": su etiqueta es larga y, junto a los otros dos botones en
        #una sola fila, el ancho total podía superar el ancho visible del panel (dentro del scroll area) sin que
        #hubiera una barra de scroll horizontal obvia — el botón quedaba técnicamente presente pero fuera de vista.
        #Separarlo en su propia fila garantiza que los tres se vean siempre.
        fila_exportar= QHBoxLayout()
        fila_exportar.setSpacing(10)
        btn_exportar_servidor= self._boton_accion(
            "Exportar Servidor Institucional", "BtnAccionNeutro", self._exportar_paquete_servidor)
        fila_exportar.addWidget(btn_exportar_servidor)
        fila_exportar.addStretch()
        contenido_av.addLayout(fila_exportar)

        contenido_av.addWidget(QLabel("Método:"))
        fila_chips= QHBoxLayout()
        fila_chips.setSpacing(8)
        self.grupo_backends= QButtonGroup(self)
        self.grupo_backends.setExclusive(True)
        self._chips_backend= {}
        #Los íconos de cada backend (nube para Drive/Dropbox/OneDrive, equipo para el servidor propio) los agrega
        #automáticamente iconos_auto.py a partir del propio texto del botón -no hace falta anteponer un emoji a mano
        #aquí, y así se ve igual de coherente que cualquier otro botón de la app.
        claves= [c for c in avanzado.METODOS if c != "carpeta"]
        for i, clave in enumerate(claves):
            btn_chip= QPushButton(avanzado.METODOS[clave])
            btn_chip.setObjectName("ChipBackendSync")
            btn_chip.setCheckable(True)
            btn_chip.setCursor(Qt.CursorShape.PointingHandCursor)
            #el primer parámetro absorbe el checked de la señal y no se usa; el valor por defecto fija el de esta vuelta del bucle
            btn_chip.clicked.connect(lambda checked, idx=i, cl=clave: self._cambiar_metodo_avanzado(idx, cl))
            self.grupo_backends.addButton(btn_chip, i)
            self._chips_backend[clave]= btn_chip
            fila_chips.addWidget(btn_chip)
        fila_chips.addStretch()
        contenido_av.addLayout(fila_chips)

        self.stack_config_avanzada= QStackedWidget()
        creadores= {
            "google_drive": self._crear_panel_google,
            "dropbox": self._crear_panel_dropbox,
            "onedrive": self._crear_panel_onedrive,
            "servidor": self._crear_panel_servidor,
        }
        for clave in claves:
            self.stack_config_avanzada.addWidget(creadores[clave]())
        contenido_av.addWidget(self.stack_config_avanzada)

        if claves:
            self._chips_backend[claves[0]].setChecked(True)
            self._metodo_avanzado_actual_clave= claves[0]

        self.lbl_estado_avanzado= QLabel("")
        self.lbl_estado_avanzado.setObjectName("DescModulo")
        self.lbl_estado_avanzado.setWordWrap(True)
        contenido_av.addWidget(self.lbl_estado_avanzado)

        fila_avanzada= QHBoxLayout()
        fila_avanzada.setSpacing(10)
        self.btn_subir_avanzado= self._boton_accion("Subir (directo)", "BtnAccionAgregar", self._subir_avanzado)
        self.btn_subir_avanzado.setIcon(icono_emoji(EMOJI_SYNC_SUBIR_DIRECTO))
        self.btn_subir_avanzado.setIconSize(_QSize_emoji(18, 18))
        fila_avanzada.addWidget(self.btn_subir_avanzado)
        self.btn_descargar_avanzado= self._boton_accion("Descargar (directo)", "BtnAccionAjustar", self._descargar_avanzado)
        self.btn_descargar_avanzado.setIcon(icono_emoji(EMOJI_SYNC_DESCARGAR_DIRECTO))
        self.btn_descargar_avanzado.setIconSize(_QSize_emoji(18, 18))
        fila_avanzada.addWidget(self.btn_descargar_avanzado)
        #"Romper" la conexión con el backend seleccionado, por si quedó en mal estado (token vencido/corrupto,
        #credenciales equivocadas, cuenta que ya no corresponde) y hay que volver a conectarlo desde cero. Reutiliza el
        #mismo estilo "eliminar" (rojo) que ya usa el resto de la app para acciones destructivas, así que no introduce
        #un lenguaje visual nuevo.
        self.btn_desvincular_avanzado= self._boton_accion("Desvincular", "BtnAccionEliminar", self._desvincular_avanzado)
        fila_avanzada.addWidget(self.btn_desvincular_avanzado)
        self.spinner_avanzado= SpinnerCircular(diametro=18, color=self._paleta()["accent"])
        fila_avanzada.addWidget(self.spinner_avanzado)
        fila_avanzada.addStretch()
        contenido_av.addLayout(fila_avanzada)

        self._refrescar_estado_avanzado()

    #Paneles de configuración por backend avanzado
    def _crear_panel_google(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(0, 4, 0, 0)
        disposicion.setSpacing(6)
        disposicion.addWidget(QLabel("Client ID (app OAuth tipo 'Desktop' en Google Cloud Console):"))
        self.in_google_client_id= QLineEdit()
        limitar_campo_texto(self.in_google_client_id, 300)
        disposicion.addWidget(self.in_google_client_id)
        disposicion.addWidget(QLabel("Client Secret:"))
        self.in_google_client_secret= QLineEdit()
        limitar_campo_texto(self.in_google_client_secret, 128)
        self.in_google_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        disposicion.addWidget(self.in_google_client_secret)
        btn= self._boton_accion("Conectar con Google Drive", "BtnAccionEditar", self._conectar_google)
        disposicion.addWidget(btn)
        return contenedor

    def _crear_panel_dropbox(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(0, 4, 0, 0)
        disposicion.setSpacing(6)
        disposicion.addWidget(QLabel("App Key (app registrada en Dropbox App Console):"))
        self.in_dropbox_key= QLineEdit()
        limitar_campo_texto(self.in_dropbox_key, 128)
        disposicion.addWidget(self.in_dropbox_key)
        disposicion.addWidget(QLabel("App Secret:"))
        self.in_dropbox_secret= QLineEdit()
        limitar_campo_texto(self.in_dropbox_secret, 128)
        self.in_dropbox_secret.setEchoMode(QLineEdit.EchoMode.Password)
        disposicion.addWidget(self.in_dropbox_secret)
        btn= self._boton_accion("Conectar con Dropbox", "BtnAccionEditar", self._conectar_dropbox)
        disposicion.addWidget(btn)
        return contenedor

    def _crear_panel_onedrive(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(0, 4, 0, 0)
        disposicion.setSpacing(6)
        disposicion.addWidget(QLabel("Client ID (app registrada en Microsoft Entra ID / Azure AD):"))
        self.in_onedrive_client_id= QLineEdit()
        limitar_campo_texto(self.in_onedrive_client_id, 300)
        disposicion.addWidget(self.in_onedrive_client_id)
        btn= self._boton_accion("Conectar con OneDrive", "BtnAccionEditar", self._conectar_onedrive)
        disposicion.addWidget(btn)
        return contenedor

    def _crear_panel_servidor(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(0, 4, 0, 0)
        disposicion.setSpacing(6)
        disposicion.addWidget(QLabel("URL del servidor institucional (ej. https://sync.miescuela.edu):"))
        self.in_servidor_url= QLineEdit()
        limitar_campo_texto(self.in_servidor_url, 200)
        disposicion.addWidget(self.in_servidor_url)
        disposicion.addWidget(QLabel("Token de acceso (definido en el servidor):"))
        self.in_servidor_token= QLineEdit()
        limitar_campo_texto(self.in_servidor_token, 128)
        self.in_servidor_token.setEchoMode(QLineEdit.EchoMode.Password)
        disposicion.addWidget(self.in_servidor_token)
        btn= self._boton_accion("Conectar con Servidor", "BtnAccionEditar", self._conectar_servidor)
        disposicion.addWidget(btn)
        return contenedor

    #Acordeón / selector de backend (animaciones de interfaz)
    def _alternar_avanzado(self):

        if not self._contenido_avanzado_listo:
            self._construir_contenido_avanzado()
            #Qt encola (no ejecuta al instante) las peticiones de recálculo de geometría de los widgets recién creados — y
            #aquí hay varias anidadas: el panel en sí, y dentro el QStackedWidget con los 4 formularios de backends.
            #activate() por sí solo sólo resuelve el layout de más afuera; las peticiones internas seguían pendientes, por
            #eso la primera apertura salía "cortada" y había que cerrar y volver a abrir para que ya estuvieran resueltas.
            #processEvents() las fuerza a resolverse todas de una vez, antes de leer sizeHint().
            QApplication.processEvents()
            self.panel_avanzado.layout().activate()
            self.panel_avanzado.adjustSize()
        objetivo_abierto= not self._avanzado_abierto
        self._avanzado_abierto= objetivo_abierto
        self._anim_avanzado.stop()
        if objetivo_abierto:
            self.panel_avanzado.setMaximumHeight(16777215)
            alto_objetivo= self.panel_avanzado.sizeHint().height()
            self.panel_avanzado.setMaximumHeight(0)
            self._anim_avanzado.setStartValue(0)
            self._anim_avanzado.setEndValue(alto_objetivo)
            self.btn_toggle_avanzado.setText("▾  Sincronización Directa (avanzada, opcional)")
        else:
            self._anim_avanzado.setStartValue(self.panel_avanzado.height())
            self._anim_avanzado.setEndValue(0)
            self.btn_toggle_avanzado.setText("▸  Sincronización Directa (avanzada, opcional)")
        self._anim_avanzado.start()

    def _cambiar_metodo_avanzado(self, indice, clave):

        self._metodo_avanzado_actual_clave= clave
        self.stack_config_avanzada.setCurrentIndex(indice)
        self._efecto_transicion_panel()
        self._refrescar_estado_avanzado()

    def _efecto_transicion_panel(self):

        widget= self.stack_config_avanzada.currentWidget()
        if widget is None:
            return
        widget.show()
        widget.update()
        self.stack_config_avanzada.update()
        _fundido_entrada(widget, duracion=220)

    def _abrir_asistente(self):

        from src.sincronizacion.asistente_sincronizacion import AsistenteSincronizacion
        asistente= AsistenteSincronizacion(self.main_window)
        asistente.exec()
        self._refrescar_estado_avanzado()

    def _descargar_guia_pdf(self):

        ruta_guia= buscar_dato("guia_sincronizacion_directa.pdf")
        if not os.path.exists(ruta_guia):
            mostrar_mensaje("advertencia", "Guía no encontrada",
                            "No se encontró guia_sincronizacion_directa.pdf junto a la aplicación.", self)
            return
        destino, _= QFileDialog.getSaveFileName(
            self, "Guardar Guía de Sincronización Directa",
            "Guia_Sincronizacion_Directa_AcaDeXI.pdf", "PDF (*.pdf)")
        if not destino:
            return
        try:

            shutil.copy2(ruta_guia, destino)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo guardar la guía:\n{error}", self)
            return
        registrar_auditoria("Sistema", "Descargó la Guía de Sincronización Directa (PDF)",
                            self.main_window.usuario_actual, destino)
        mostrar_mensaje("exito", "Guía guardada", f"La guía se guardó en:\n{destino}", self)

    def _exportar_paquete_servidor(self):

        exportar_paquete_servidor(self.main_window, self)

    def _metodo_avanzado_actual(self):

        return self._metodo_avanzado_actual_clave

    def _refrescar_estado_avanzado(self):

        if not self._contenido_avanzado_listo:
            return  #el panel avanzado aún no se ha construido (carga perezosa)
        metodo= self._metodo_avanzado_actual()
        if metodo is None:
            return
        conectado= avanzado.conectado(metodo)
        if conectado:
            self.lbl_estado_avanzado.setText(f"✅ {avanzado.METODOS[metodo]}: conectado.")
        else:
            self.lbl_estado_avanzado.setText(f"⚪ {avanzado.METODOS[metodo]}: no conectado todavía.")
        if hasattr(self, "btn_desvincular_avanzado"):
            self.btn_desvincular_avanzado.setEnabled(conectado)

    #Conexión OAuth / servidor por backend (sin cambios de lógica)
    def _conectar_google(self):

        client_id= self.in_google_client_id.text().strip()
        client_secret= self.in_google_client_secret.text().strip()
        if not client_id or not client_secret:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa el Client ID y Client Secret.", self)
            return
        mostrar_mensaje("info", "Conectar Google Drive",
                        "Se abrirá tu navegador para autorizar el acceso. Vuelve a la aplicación "
                        "después de aceptar.", self)
        try:

            avanzado.google_drive_conectar(client_id, client_secret)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo conectar Google Drive:\n{error}", self)
            return
        mostrar_mensaje("exito", "Conectado", "Google Drive se conectó correctamente.", self)
        self._refrescar_estado_avanzado()

    def _conectar_dropbox(self):

        app_key= self.in_dropbox_key.text().strip()
        app_secret= self.in_dropbox_secret.text().strip()
        if not app_key or not app_secret:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa el App Key y App Secret.", self)
            return
        try:

            flow, url= avanzado.dropbox_conectar(app_key, app_secret)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo iniciar la conexión con Dropbox:\n{error}", self)
            return
        webbrowser.open(url)
        codigo, ok= QInputDialog.getText(
            self, "Conectar Dropbox",
            f"Se abrió tu navegador para autorizar el acceso.\nSi no se abrió, visita:\n{url}\n\n"
            "Pega aquí el código de autorización que te muestra Dropbox:")
        if not ok or not codigo.strip():
            return
        try:

            avanzado.dropbox_finalizar_conexion(flow, codigo, app_key, app_secret)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo completar la conexión con Dropbox:\n{error}", self)
            return
        mostrar_mensaje("exito", "Conectado", "Dropbox se conectó correctamente.", self)
        self._refrescar_estado_avanzado()

    def _conectar_onedrive(self):

        client_id= self.in_onedrive_client_id.text().strip()
        if not client_id:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa el Client ID.", self)
            return
        try:

            app, flujo= avanzado.onedrive_conectar(client_id)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo iniciar la conexión con OneDrive:\n{error}", self)
            return
        if mostrar_mensaje("pregunta", "Conectar OneDrive",
                f"{flujo['message']}\n\n¿Ya completaste el inicio de sesión en el navegador?",
                self) != QMessageBox.StandardButton.Yes:
            return
        try:

            avanzado.onedrive_finalizar_conexion(app, flujo, client_id)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo completar la conexión con OneDrive:\n{error}", self)
            return
        mostrar_mensaje("exito", "Conectado", "OneDrive se conectó correctamente.", self)
        self._refrescar_estado_avanzado()

    def _conectar_servidor(self):

        url= self.in_servidor_url.text().strip()
        token= self.in_servidor_token.text().strip()
        if not url or not token:
            mostrar_mensaje("advertencia", "Datos incompletos", "Ingresa la URL y el token.", self)
            return
        try:

            avanzado.servidor_conectar(url, token)
        except Exception as error:
            mostrar_mensaje("error", "Error", f"No se pudo conectar con el servidor:\n{error}", self)
            return
        mostrar_mensaje("exito", "Conectado", "Servidor institucional conectado correctamente.", self)
        self._refrescar_estado_avanzado()

    #Rompe la conexión con el backend actualmente seleccionado en los
    #chips (Google Drive / Dropbox / OneDrive / Servidor). Pensado como
    #vía de recuperación: si algo falló (token vencido, credenciales
    #equivocadas, etc.), esto borra la conexión guardada en este equipo
    #para poder volver a conectarla desde cero, sin tocar nada remoto.
    def _desvincular_avanzado(self):

        metodo= self._metodo_avanzado_actual()
        if metodo is None or not avanzado.conectado(metodo):
            return
        nombre= avanzado.METODOS[metodo]
        if mostrar_mensaje("pregunta", "Desvincular",
                f"¿Desvincular {nombre} de este equipo?\n\n"
                "Se borrarán las credenciales/tokens guardados localmente. Esto NO borra "
                "los archivos ya subidos allí ni afecta a otros equipos: solo rompe la "
                f"conexión en ESTE equipo. Podrás volver a conectar {nombre} cuando quieras.",
                self) != QMessageBox.StandardButton.Yes:
            return
        avanzado.desvincular(metodo)
        self._limpiar_campos_backend(metodo)
        registrar_auditoria("Sistema", f"Desvinculó {nombre}", self.main_window.usuario_actual, "")
        mostrar_mensaje("exito", "Desvinculado", f"{nombre} se desvinculó de este equipo.", self)
        self._refrescar_estado_avanzado()

    #Vacía los campos de credenciales del formulario del backend
    #recién desvinculado, para que no queden datos viejos a la vista si
    #el usuario decide volver a conectarlo.
    def _limpiar_campos_backend(self, metodo):

        campos= {
            "google_drive": [self.in_google_client_id, self.in_google_client_secret],
            "dropbox": [self.in_dropbox_key, self.in_dropbox_secret],
            "onedrive": [self.in_onedrive_client_id],
            "servidor": [self.in_servidor_url, self.in_servidor_token],
        }
        for campo in campos.get(metodo, []):
            campo.clear()

    #Subir / Descargar (carpeta compartida) — corren en segundo plano
    def _ejecutar_en_hilo(self, funcion, texto_ocupado, al_terminar):

        if self._hilo is not None and self._hilo.isRunning():
            return
        self._alternar_botones_ocupado(True)
        self.tarjeta_estado.mostrar_ocupado(texto_ocupado)
        self._hilo= _HiloOperacionSync(funcion, self)

        def _al_finalizar(resultado, error):

            self.tarjeta_estado.ocultar_ocupado()
            self._alternar_botones_ocupado(False)
            al_terminar(resultado, error)

        self._hilo.terminado.connect(_al_finalizar)
        self._hilo.start()

    def _alternar_botones_ocupado(self, ocupado):

        self.btn_subir.setEnabled(not ocupado)
        self.btn_descargar.setEnabled(not ocupado)

    def _subir(self):

        estado= obtener_estado(self.main_window)
        if estado["estado"] == "conflicto":
            if mostrar_mensaje("pregunta", "Conflicto de sincronización",
                    "Este equipo Y la carpeta compartida tienen cambios distintos desde la "
                    "última sincronización. Subir AHORA sobrescribirá la copia compartida "
                    "(los cambios hechos en otros equipos se perderán).\n\n"
                    "¿Confirmas que quieres subir de todas formas?", self) != QMessageBox.StandardButton.Yes:
                return
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._ejecutar_en_hilo(lambda: subir_cambios(self.main_window),
                               "Subiendo cambios…", self._al_terminar_subir)

    def _al_terminar_subir(self, destino, error):

        if error is not None:
            mostrar_mensaje("error", "Error", f"No se pudo subir:\n{error}", self)
        else:
            registrar_auditoria("Sistema", "Subió cambios a carpeta sincronizada",
                                self.main_window.usuario_actual, destino)
            mostrar_mensaje("exito", "Subido", f"Cambios subidos a:\n{destino}\n\n"
                           "Tu cliente de nube los sincronizará al resto de equipos.", self)
        self._refrescar_estado()

    def _descargar(self):

        estado= obtener_estado(self.main_window)
        if estado["estado"] == "conflicto":
            if mostrar_mensaje("pregunta", "Conflicto de sincronización",
                    "Este equipo Y la carpeta compartida tienen cambios distintos desde la "
                    "última sincronización. Descargar AHORA sobrescribirá los datos de ESTE "
                    "equipo (se hará un backup de seguridad automático antes, por si hay que "
                    "revertir).\n\n¿Confirmas que quieres descargar de todas formas?", self) != QMessageBox.StandardButton.Yes:
                return
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._ejecutar_en_hilo(lambda: descargar_novedades(self.main_window),
                               "Descargando novedades…", self._al_terminar_descargar)

    def _al_terminar_descargar(self, respaldo, error):

        if error is not None:
            mostrar_mensaje("error", "Error", f"No se pudo descargar:\n{error}", self)
        else:
            registrar_auditoria("Sistema", "Descargó novedades de carpeta sincronizada",
                                self.main_window.usuario_actual, respaldo)
            mostrar_mensaje("exito", "Actualizado", "Se descargaron las novedades. Se guardó un "
                           f"respaldo de seguridad previo en:\n{respaldo}\n\nReinicia la aplicación.", self)
        self._refrescar_estado()

    #Subir / Descargar con el backend avanzado seleccionado
    def _subir_avanzado(self):

        metodo= self._metodo_avanzado_actual()
        if not avanzado.conectado(metodo):
            mostrar_mensaje("advertencia", "No conectado", f"Primero conecta {avanzado.METODOS[metodo]}.", self)
            return
        self._alternar_botones_avanzado_ocupado(True)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._hilo_avanzado= _HiloOperacionSync(lambda: avanzado.subir(metodo), self)

        def _terminado(destino, error):

            self._alternar_botones_avanzado_ocupado(False)
            if error is not None:
                mostrar_mensaje("error", "Error", f"No se pudo subir:\n{error}", self)
            else:
                registrar_auditoria("Sistema", f"Subió cambios ({avanzado.METODOS[metodo]})",
                                    self.main_window.usuario_actual, str(destino))
                mostrar_mensaje("exito", "Subido", f"Cambios subidos a {avanzado.METODOS[metodo]}.", self)

        self._hilo_avanzado.terminado.connect(_terminado)
        self._hilo_avanzado.start()

    def _descargar_avanzado(self):

        metodo= self._metodo_avanzado_actual()
        if not avanzado.conectado(metodo):
            mostrar_mensaje("advertencia", "No conectado", f"Primero conecta {avanzado.METODOS[metodo]}.", self)
            return
        self._alternar_botones_avanzado_ocupado(True)
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._hilo_avanzado= _HiloOperacionSync(lambda: avanzado.descargar(metodo), self)

        def _terminado(respaldo, error):

            self._alternar_botones_avanzado_ocupado(False)
            if error is not None:
                mostrar_mensaje("error", "Error", f"No se pudo descargar:\n{error}", self)
            else:
                registrar_auditoria("Sistema", f"Descargó novedades ({avanzado.METODOS[metodo]})",
                                    self.main_window.usuario_actual, str(respaldo))
                mostrar_mensaje("exito", "Actualizado",
                               f"Se descargaron las novedades desde {avanzado.METODOS[metodo]}. "
                               f"Respaldo previo:\n{respaldo}\n\nReinicia la aplicación.", self)

        self._hilo_avanzado.terminado.connect(_terminado)
        self._hilo_avanzado.start()

    def _alternar_botones_avanzado_ocupado(self, ocupado):

        self.btn_subir_avanzado.setEnabled(not ocupado)
        self.btn_descargar_avanzado.setEnabled(not ocupado)
        if ocupado:
            self.spinner_avanzado.iniciar()
        else:
            self.spinner_avanzado.detener()

    #Carpeta / preferencias de este equipo
    def _elegir_carpeta(self):

        carpeta= QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de sincronización")
        if carpeta:
            self.in_carpeta.setText(carpeta)

    def _guardar(self):

        self.main_window.modo_trabajo= self.combo_modo.currentText()
        self.main_window.carpeta_sincronizacion= self.in_carpeta.text().strip()
        self.main_window.guardar_configuracion()
        registrar_auditoria("Sistema", "Actualizó preferencia de sincronización local",
                            self.main_window.usuario_actual, self.main_window.modo_trabajo)
        mostrar_mensaje("exito", "Guardado", "Preferencia de este equipo actualizada.", self)
        self._refrescar_estado()

    #Consulta el estado (implica hashear archivos) en un hilo aparte para
    #que abrir el módulo o pulsar 'Verificar Ahora' nunca congele la UI.
    def _refrescar_estado(self):

        if self._hilo_estado is not None and self._hilo_estado.isRunning():
            return
        self.tarjeta_estado.mostrar_ocupado("Verificando…")
        #lambda sin argumentos: la señal no trae datos y aquí se necesita una llamada ya armada
        self._hilo_estado= _HiloOperacionSync(lambda: obtener_estado(self.main_window), self)

        def _listo(estado, error):

            self.tarjeta_estado.ocultar_ocupado()
            if error is not None or not estado:
                self.tarjeta_estado.actualizar("sin_carpeta")
                return
            self.tarjeta_estado.actualizar(estado["estado"])
            habilitar= estado["estado"] != "sin_carpeta"
            self.btn_subir.setEnabled(habilitar)
            self.btn_descargar.setEnabled(habilitar and estado["estado"] != "sin_copia_remota")

        self._hilo_estado.terminado.connect(_listo)
        self._hilo_estado.start()

    #Ciclo de vida del módulo
    def refrescar(self):

        self.combo_modo.setCurrentText(getattr(self.main_window, "modo_trabajo", "Local"))
        self.in_carpeta.setText(getattr(self.main_window, "carpeta_sincronizacion", "") or "")
        self._refrescar_estado()
        self._refrescar_estado_avanzado()

    def showEvent(self, evento):

        super().showEvent(evento)
        if self.tarjeta_estado._pulso is not None:
            self.tarjeta_estado._pulso.resume()
        #Antes se reutilizaba un único QGraphicsOpacityEffect que se dejaba pegado a `contenido` para siempre. Un
        #efecto que nunca se desprende hace que Qt, en ciertos casos, no repinte correctamente actualizaciones que
        #llegan después de que la animación terminó — por ejemplo la tarjeta de estado pasando de "Verificando…" a su
        #resultado real tras pulsar "Verificar Ahora", o al volver a esta pestaña. Resultado: la tarjeta "Sin
        #configurar" (o cualquier otro estado) se quedaba invisible hasta la próxima interacción manual. Usamos el
        #mismo patrón ya usado en _efecto_transicion_panel: un efecto nuevo cada vez que se desprende solo al terminar.
        _fundido_entrada(self._contenido, duracion=380)

    def hideEvent(self, evento):

        super().hideEvent(evento)
        #El módulo pasa a segundo plano (otra pestaña de la sidebar está activa): pausamos el 'latido' de la tarjeta de
        #estado para no gastar ciclos de CPU en una animación que nadie está viendo.
        if self.tarjeta_estado._pulso is not None:
            self.tarjeta_estado._pulso.pause()

    def _paleta(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        tema= getattr(mw, "tema_actual", None)
        if not paletas or tema not in paletas:
            return {"accent": "#6366F1", "accent_hv": "#4F46E5", "bg_panel": "#FFFFFF", "bg_btn": "#E2E8F0",
                    "txt_prim": "#0F172A", "txt_sec": "#64748B"}
        #p: paleta del tema actual; cada color trae dos valores, 0 para claro y 1 para oscuro
        p= paletas[tema]
        idx= 1 if getattr(mw, "modo_oscuro", False) else 0
        return {"accent": p["btn_op_bg"][idx],
                "accent_hv": p["btn_op_hover"][idx] if "btn_op_hover" in p else p["btn_op_bg"][idx],
                "bg_panel": p["display_bg"][idx],
                "bg_btn": p["btn_num_bg"][idx], "txt_prim": p["text_primary"][idx],
                "txt_sec": p["text_secondary"][idx]}

    def actualizar_tema(self):

        c= self._paleta()
        accent_suave= _hex_a_rgba(c["accent"], 0.14)
        accent_borde= _hex_a_rgba(c["accent"], 0.45)
        self.setStyleSheet(f"""
            QFrame#TarjetaSeccionSync {{
                background-color: {c['bg_panel']};
                border: 1px solid {c['bg_btn']};
                border-radius: 14px;
            }}
            QLabel#IconoSeccionSync {{ font-size: 18px; background: transparent; }}
            QLabel#TituloSeccionSync {{
                font-size: 15px; font-weight: 800; color: {c['txt_prim']}; background: transparent;
            }}
            QPushButton#BtnToggleAvanzadoSync {{
                text-align: left;
                background-color: transparent;
                color: {c['txt_prim']};
                border: none;
                font-size: 14px;
                font-weight: 700;
                padding: 2px 0px;
            }}
            QPushButton#BtnToggleAvanzadoSync:hover {{ color: {c['accent']}; }}
            QPushButton#ChipBackendSync {{
                background-color: {c['bg_btn']};
                color: {c['txt_prim']};
                border: 2px solid transparent;
                border-radius: 18px;
                padding: 8px 16px;
                font-weight: 700;
            }}
            QPushButton#ChipBackendSync:checked {{
                background-color: {accent_suave};
                border: 2px solid {c['accent']};
                color: {c['accent']};
            }}
            QPushButton#ChipBackendSync:hover {{ border: 2px solid {accent_borde}; }}
        """)
        if hasattr(self, "frame_cabecera"):
            self.frame_cabecera.setStyleSheet(f"""
                QFrame#TarjetaCabecera {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {c['accent']}, stop:1 {c['accent_hv']});
                    border-radius: 18px;
                }}
                QLabel#IconoCabeceraModulo {{
                    background-color: rgba(255, 255, 255, 40);
                    border-radius: 23px;
                    font-size: 22px;
                    color: white;
                }}
                QLabel#TituloCabeceraModulo {{
                    font-size: 22px;
                    font-weight: 800;
                    color: white;
                    background: transparent;
                }}
                QLabel#SubtituloCabeceraModulo {{
                    font-size: 12px;
                    color: rgba(255, 255, 255, 210);
                    background: transparent;
                }}
            """)
        if hasattr(self, "tarjeta_estado"):
            self.tarjeta_estado.spinner.poner_color(c["accent"])
        if hasattr(self, "spinner_avanzado"):
            self.spinner_avanzado.poner_color(c["accent"])