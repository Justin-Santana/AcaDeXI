#Control de Paginación de AcaDeXI — optimización de rendimiento.
import math
import os
from contextlib import contextmanager
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QDialog, QLineEdit, QTextEdit, QTableWidget, QHeaderView,
    QSizePolicy, QAbstractScrollArea, QFrame, QScrollArea, QStyledItemDelegate, QStyleOptionViewItem,
    QStyle, QApplication, QGraphicsOpacityEffect)
from PySide6.QtCore import Signal, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor
from PySide6.QtCore import Qt

from src.nucleo.iconos import obtener_icono, mostrar_mensaje
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, EMOJI_PAG_PRIMERA, EMOJI_PAG_ANTERIOR,
                          EMOJI_PAG_SIGUIENTE, EMOJI_PAG_ULTIMA)


#Estructura estándar de tablas (QTableWidget) — misma base que estudiantes.py, aplicada a TODAS las tablas de
#la app. Techo absoluto (en píxeles) que puede alcanzar una columna al ensancharse por contenido en
#`ajustar_anchos_columnas`. Evita que una sola celda con un valor larguísimo (texto pegado, observación larga,
#etc.) acapare todo el ancho visible de la tabla — ver el docstring de esa función.
ANCHO_MAXIMO_COLUMNA= 420
#Deja una QTableWidget escalable, con scrollbars propias que aparecen
#solo cuando hacen falta: vertical cuando hay muchos registros y
#horizontal cuando el ancho del contenido (columnas) no cabe.
#
#IMPORTANTE: esta función es puramente ESTRUCTURAL y no toca nada visual.
#No cambia anchos de columna, alto mínimo/máximo, modo de resize de las
#columnas (Stretch/Interactive/Fixed que cada tabla ya tenga elegido),
#wordWrap, colores alternos, selección, etc. — cada tabla conserva
#exactamente el diseño que ya tenía. Solo agrega la base común que hace
#que la tabla sea "su propia área de scroll" (igual que en estudiantes.py):
#
#- sizePolicy Expanding/Expanding: la tabla aprovecha el espacio que le
#da su layout en vez de quedarse en un tamaño fijo por contenido.
#- sizeAdjustPolicy AdjustIgnored: el tamaño de la tabla no se recalcula
#en función de su contenido (evita que "empuje" el resto de la página).
#- scrollbars propias (vertical/horizontal) en modo "AsNeeded": aparecen
#solo cuando el contenido no cabe, en vez de aplastarlo o desbordarlo.
def aplicar_estructura_tabla(tabla):

    tabla.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    tabla.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    #Doble clic sobre el borde del encabezado ("auto-fit" nativo de Qt):
    #por defecto Qt calcula el nuevo ancho igual que `resizeColumnToContents`, que solo mide el QTableWidgetItem de
    #la celda -en columnas con `setCellWidget` (p. ej. "Categorías" en observaciones.py) ese item va vacío, así que
    #el resultado del doble clic quedaba corto y el contenido seguía recortado hasta que el usuario estiraba la
    #columna a mano.
    ##La corrección se difiere con QTimer.singleShot(0, ...) en vez de aplicarse directamente dentro del slot
    #conectado a la señal: el ajuste nativo de Qt no siempre ha terminado de aplicarse en el mismo instante en que
    #se emite `sectionHandleDoubleClicked` (puede resolverse en un paso posterior del bucle de eventos), así que
    #corregir "en línea" podía quedar pisado otra vez por el valor incorrecto de Qt según el orden de conexión. Al
    #diferir con singleShot(0, ...), nuestra corrección corre siempre DESPUÉS de que Qt termine su propio ajuste,
    #sin importar el orden interno de señales/slots.
    def _reajustar_tras_doble_clic(indice_columna, _t=tabla):

        def _corregir():

            base_dict= getattr(_t, "_anchos_base_columnas", None)
            base= base_dict.get(indice_columna) if base_dict else None
            if base is None:
                return
            ancho_actual= _t.columnWidth(indice_columna)
            for fila in range(_t.rowCount()):
                widget_celda= _t.cellWidget(fila, indice_columna)
                if widget_celda is not None:
                    ancho_actual= max(ancho_actual, widget_celda.sizeHint().width())
            techo= max(base, getattr(_t, "_techos_columnas", {}).get(indice_columna, ANCHO_MAXIMO_COLUMNA))
            _t.setColumnWidth(indice_columna, max(base, min(ancho_actual, techo)))
        QTimer.singleShot(0, _corregir)

    tabla.horizontalHeader().sectionHandleDoubleClicked.connect(_reajustar_tras_doble_clic)


#Ensancha una columna de `tabla` por encima de su ancho de reposo SOLO
#cuando algún registro de la página/tabla actual la necesita (un nombre,
#descripción, tutor, etc. demasiado largo para caber en el ancho normal
#de esa columna). El resto de columnas se queda en su ancho de siempre,
#así que la tabla solo saca su barra horizontal cuando de verdad hay un
#valor que no cabe -en vez de recortarlo en silencio, que es lo que
#pasaba en toda la app salvo en Estudiantes antes de este cambio-.
#
#Es el mismo mecanismo que ya usaba (de forma privada, solo para sí
#mismo) el módulo de Estudiantes; aquí se comparte para que cualquier
#tabla de la app tenga la misma escalabilidad horizontal, SIN tener que
#declarar a mano el ancho de cada columna: la PRIMERA vez que se llama
#para una tabla dada, memoriza el ancho que cada columna (Interactive/
#Fixed; se ignoran las columnas en modo Stretch, que ya administra Qt
#solo) tenga EN ESE MOMENTO -que, justo antes de la primera llamada, es
#el ancho normal/de diseño que ya traía la tabla, sin tocar- y lo usa
#como PISO para esa columna en todas las llamadas siguientes. Así una
#columna puede ensancharse para un registro puntual (una fila con un
#nombre larguísimo, por ejemplo) y volver a su ancho normal en la
#siguiente página/búsqueda si ya no hace falta.
#
#Debe llamarse DESPUÉS de llenar las filas de la tabla (setItem...); da
#igual si es antes o después de un posible resizeRowsToContents(), son
#ejes distintos (ancho de columna vs. alto de fila).
#
#IMPORTANTE - TECHO de ensanchado: además del piso (`base`), cada columna
#tiene un TECHO (`ANCHO_MAXIMO_COLUMNA`). Sin un techo, un solo valor
#extremadamente largo en una celda (por ejemplo, alguien que pega un
#bloque de texto gigante en "Departamento" u "Observaciones") hacía que
#`resizeColumnToContents` ensanchara esa columna sin límite, empujando
#literalmente TODAS las demás columnas fuera de la vista -y, si en ese
#módulo tampoco se veía la barra de scroll horizontal, el usuario se
#quedaba viendo solo esa columna gigante sin forma de llegar a las
#demás-. Con el techo, una celda así simplemente corta el texto (con
#"…" via elide, que Qt ya hace solo al no caber) dentro de un ancho
#razonable, y es la tabla la que saca su scroll horizontal para las
#columnas que si acumuladas no quepan -en vez de que una sola celda
#acapare todo el ancho disponible.
#
#`techos`: dict opcional {columna: ancho_máximo} para columnas que
#necesitan un techo distinto del general (`ANCHO_MAXIMO_COLUMNA`). Es el
#caso, por ejemplo, de una columna con un widget compuesto por varias
#piezas que YA limitan su propio texto con elide (como "Categorías" en
#observaciones.py, que puede traer varios chips): ahí el techo genérico
#-pensado para una sola celda de texto libre sin ningún límite propio-
#terminaba recortando el widget completo aunque ninguna pieza individual
#fuera un texto descontrolado.
def ajustar_anchos_columnas(tabla, techos=None):

    header= tabla.horizontalHeader()
    techos= techos or {}
    tabla._techos_columnas= techos  #usado también por el handler de doble clic en aplicar_estructura_tabla
    base_dict= getattr(tabla, "_anchos_base_columnas", None)
    if base_dict is None:
        base_dict= {}
        for col in range(tabla.columnCount()):
            if header.sectionResizeMode(col) == QHeaderView.ResizeMode.Stretch:
                continue
            base_dict[col]= tabla.columnWidth(col)
        tabla._anchos_base_columnas= base_dict
    for col, base in base_dict.items():
        if col >= tabla.columnCount() or tabla.isColumnHidden(col):
            continue
        tabla.resizeColumnToContents(col)
        ancho_actual= tabla.columnWidth(col)
        #`resizeColumnToContents` solo mide el QTableWidgetItem de cada celda. En columnas que en vez de texto usan un
        #widget compuesto (ver `setCellWidget` — p. ej. "Categorías" en observaciones.py, con varios iconos+etiquetas),
        #ese item suele ir vacío y el cálculo de arriba subestima el ancho real, dejando el contenido recortado tanto
        #aquí como en el doble clic nativo del encabezado (que usa el mismo mecanismo de Qt). Por eso se revisa también
        #el sizeHint() real de cualquier cellWidget presente en la columna.
        for fila in range(tabla.rowCount()):
            widget_celda= tabla.cellWidget(fila, col)
            if widget_celda is not None:
                ancho_actual= max(ancho_actual, widget_celda.sizeHint().width())
        if ancho_actual < base:
            tabla.setColumnWidth(col, base)
        else:
            techo= max(base, techos.get(col, ANCHO_MAXIMO_COLUMNA))
            tabla.setColumnWidth(col, min(ancho_actual, techo))


#OPTIMIZACIÓN: pausar la tabla mientras se llena
#Context manager que desactiva repintado/orden/señales de una
#QTableWidget mientras se llena con muchas filas, y lo restaura al salir.
#
#En equipos modestos, insertar cientos o miles de QTableWidgetItem con el
#repintado y el ordenamiento activados dispara un layout/paint por cada
#celda. Envolver el llenado en `with tabla_pausada(self.tabla): ...`
#evita ese costo sin cambiar ningún dato ni comportamiento visible: el
#contenido final es idéntico, solo se construye de forma más barata.
@contextmanager
def tabla_pausada(tabla):

    tenia_orden= tabla.isSortingEnabled()
    tabla.setSortingEnabled(False)
    tabla.setUpdatesEnabled(False)
    tabla.blockSignals(True)
    try:

        yield tabla
    finally:
        tabla.blockSignals(False)
        tabla.setUpdatesEnabled(True)
        tabla.setSortingEnabled(tenia_orden)


#OPTIMIZACIÓN: caché de miniaturas circulares (fotos de tabla)
_CACHE_PIXMAPS_CIRCULARES= {}
_CACHE_PIXMAPS_LIMITE= 500  #suficiente para varias páginas de fotos distintas


#Rol dedicado (fuera del rango que usan otros módulos) para guardar la RUTA real del archivo de foto sobre el
#QTableWidgetItem decorativo de la columna "Foto" (que solo trae un QPixmap pequeño para la tabla, vía
#DecorationRole). mostrar_detalle_fila() lo lee para poder mostrar la fotografía en grande arriba del detalle
#en vez de dejar ese campo vacío.
ROL_RUTA_FOTO= int(Qt.ItemDataRole.UserRole) + 1


#Igual que recortar una foto en círculo para mostrarla en una tabla,
#pero cacheado por (ruta, tamaño, fecha de modificación del archivo).
#
#Decodificar y volver a escalar/recortar un JPG/PNG cada vez que se
#repinta o pagina una tabla es de las operaciones más caras en equipos
#modestos. Como la foto de una persona casi nunca cambia entre un
#refresco de tabla y el siguiente, cachear el resultado ya recortado
#evita ese trabajo repetido. Si el archivo cambia (nueva foto), la marca
#de tiempo cambia y la caché se renueva sola: nunca se muestra una foto
#vieja.
def obtener_pixmap_circular_cacheado(ruta, tamano):

    if not ruta or not os.path.exists(ruta):
        return None
    try:

        mtime= os.path.getmtime(ruta)
    except OSError:
        return None
    clave= (ruta, tamano, mtime)
    resultado= _CACHE_PIXMAPS_CIRCULARES.get(clave)
    if resultado is not None:
        return resultado

    origen= QPixmap(ruta)
    if origen.isNull():
        return None
    fuente= origen.scaled(tamano, tamano, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
    resultado= QPixmap(tamano, tamano)
    resultado.fill(Qt.GlobalColor.transparent)
    pintor= QPainter(resultado)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    ruta_circular= QPainterPath()
    ruta_circular.addEllipse(0, 0, tamano, tamano)
    pintor.setClipPath(ruta_circular)
    pos_x= (tamano - fuente.width()) // 2
    pos_y= (tamano - fuente.height()) // 2
    pintor.drawPixmap(pos_x, pos_y, fuente)
    pintor.end()

    if len(_CACHE_PIXMAPS_CIRCULARES) >= _CACHE_PIXMAPS_LIMITE:
        _CACHE_PIXMAPS_CIRCULARES.clear()
    _CACHE_PIXMAPS_CIRCULARES[clave]= resultado
    return resultado


#Columna "foto" de las tablas — tamaño estándar + placeholder + config Diámetro estándar (px) de la miniatura
#circular en la columna "Foto" de Estudiantes/Profesores/Personal. Vive aquí -un solo lugar- para que la
#miniatura real (obtener_pixmap_circular_cacheado), el placeholder de "sin foto"
#(pixmap_placeholder_foto_tabla) y el ajuste de la propia
#columna (configurar_columna_foto) usen siempre el MISMO número: si
#alguno de los tres queda desalineado con los otros dos es exactamente lo que causaba que la foto se viera
#"cortada" en la tabla (ver abajo).
TAMANO_FOTO_TABLA= 56

_CACHE_PLACEHOLDER_FOTO= {}


#Círculo gris neutro con una silueta de persona, para la columna
#"Foto" de una tabla cuando ese registro todavía no tiene fotografía
#guardada. Antes esa celda se dejaba completamente vacía -sin ninguna
#decoración-, lo que en una columna angosta se veía como un hueco en
#blanco sin ninguna intención visual; este círculo hace explícito que
#"no hay foto" con el mismo lenguaje visual (silueta + círculo) que ya
#usan los formularios de Estudiantes/Profesores/Personal en su botón
#"Sin foto" antes de elegir una.
def pixmap_placeholder_foto_tabla(tamano=TAMANO_FOTO_TABLA):

    if tamano in _CACHE_PLACEHOLDER_FOTO:
        return _CACHE_PLACEHOLDER_FOTO[tamano]
    resultado= QPixmap(tamano, tamano)
    resultado.fill(Qt.GlobalColor.transparent)
    pintor= QPainter(resultado)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QColor("#CBD5E1"))
    pintor.drawEllipse(0, 0, tamano, tamano)
    pintor.end()
    #La silueta ya viene dibujada (vectorial, vía iconos_emoji) con su propio color; se compone encima del círculo
    #de fondo.
    silueta= pixmap_emoji("\uE034", int(tamano * 0.62))
    pintor2= QPainter(resultado)
    pintor2.setRenderHint(QPainter.RenderHint.Antialiasing)
    pos_x= (tamano - silueta.width()) // 2
    pos_y= tamano - silueta.height() - int(tamano * 0.06)
    pintor2.drawPixmap(pos_x, pos_y, silueta)
    pintor2.end()
    _CACHE_PLACEHOLDER_FOTO[tamano]= resultado
    return resultado


#Dibuja la columna "Foto" (fondo de selección, hover, etc. incluidos)
#forzando la decoración (la miniatura circular o su placeholder) a
#quedar centrada horizontal Y verticalmente en la celda.
#
#Por qué hace falta: el estilo de Qt por defecto (en varias plataformas)
#pega la decoración de un QTableWidgetItem contra el borde IZQUIERDO de
#la celda sin importar cuán ancha sea esa celda -`item.setTextAlignment`
#no cambia esto, porque esa propiedad solo controla el TEXTO, no la
#decoración-. Este delegado reemplaza el pintado estándar únicamente
#para forzar `decorationAlignment = AlignCenter`, dejando todo lo demás
#(colores, selección, fuente...) exactamente igual porque sigue
#delegando el dibujo real al estilo activo (`style().drawControl`).
class _DelegadoFotoCentrada(QStyledItemDelegate):

    def paint(self, painter, option, indice):

        opcion= QStyleOptionViewItem(option)
        self.initStyleOption(opcion, indice)
        opcion.decorationAlignment= Qt.AlignmentFlag.AlignCenter
        opcion.displayAlignment= Qt.AlignmentFlag.AlignCenter
        widget= opcion.widget
        style= widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opcion, painter, widget)


#Deja la columna "Foto" de `tabla` lista para mostrar la miniatura
#circular sin que se vea recortada ni descentrada -el problema real era
#que, sin `setIconSize`, Qt calculaba el alto de la fila (y el recuadro
#donde pinta la decoración) usando el tamaño de icono POR DEFECTO del
#estilo (más chico que nuestra miniatura de `tamano`px), así que la
#foto terminaba dibujándose más grande que el espacio reservado para
#ella y se veía "cortada" contra el borde de la fila.
#
#Llamar UNA VEZ al construir la tabla (después de crear las columnas),
#ANTES de la primera llamada a `ajustar_anchos_columnas` -normalmente
#junto con `aplicar_estructura_tabla`, en `_construir_ui`-. Fija además un
#ancho de columna ajustado al tamaño real de la miniatura -en vez de
#dejar que la columna "Foto" se ensanche/angoste con el resto- para que
#el círculo quede centrado en una columna a su medida y no perdido en
#un espacio mucho más ancho que su propio contenido.
#
#IMPORTANTE: a propósito NO toca `tabla._anchos_base_columnas` (el piso
#de ancho que usa `ajustar_anchos_columnas`, ver ahí arriba). Esta
#función se llama antes de que esa tabla exista todavía, y si la
#creáramos aquí a mano con una sola columna, `ajustar_anchos_columnas`
#ya no la encontraría "vacía" en su primera llamada y se saltaría por
#completo el cálculo automático del piso para TODAS las demás columnas.
#Dejando aquí solo el `setColumnWidth`, ese mismo ancho queda
#disponible normalmente cuando `ajustar_anchos_columnas` arme su propio
#piso por primera vez -antes de cargar ninguna fila-, así que la
#columna "Foto" también queda con el piso correcto sin ningún caso
#especial.
def configurar_columna_foto(tabla, columna, tamano=TAMANO_FOTO_TABLA):

    tabla.setIconSize(QSize(tamano, tamano))
    tabla.setColumnWidth(columna, tamano + 22)
    item_header= tabla.horizontalHeaderItem(columna)
    if item_header is not None:
        item_header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    #Guardamos el delegado en la propia tabla para que no lo recoja el recolector de basura de Python
    #(setItemDelegateForColumn NO se queda con una referencia fuerte por sí solo).
    delegado= _DelegadoFotoCentrada(tabla)
    setattr(tabla, f"_delegado_foto_col_{columna}", delegado)
    tabla.setItemDelegateForColumn(columna, delegado)


#Variante 'grande' de obtener_pixmap_circular_cacheado(), pensada para
#el encabezado del diálogo de detalle en vez de una celda de tabla: la
#foto recortada en círculo queda un poco más chica que `diametro` para
#dejarle espacio a un anillo de acento alrededor (el mismo tipo de
#detalle -foto redonda con borde de color- que ya usan las tarjetas de
#'Elegir Foto' de Estudiantes/Personal/Profesores), sin cachear -esta
#versión grande solo se dibuja una vez por apertura de diálogo, no en
#cada repintado de una tabla con cientos de filas.
def _pixmap_circular_con_anillo(ruta, diametro, grosor_anillo=4, color_anillo="#6366F1"):

    if not ruta or not os.path.exists(ruta):
        return None
    origen= QPixmap(ruta)
    if origen.isNull():
        return None
    diametro_foto= diametro - grosor_anillo * 2
    fuente= origen.scaled(diametro_foto, diametro_foto, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
    resultado= QPixmap(diametro, diametro)
    resultado.fill(Qt.GlobalColor.transparent)
    pintor= QPainter(resultado)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QColor(color_anillo))
    pintor.drawEllipse(0, 0, diametro, diametro)
    ruta_circular= QPainterPath()
    ruta_circular.addEllipse(grosor_anillo, grosor_anillo, diametro_foto, diametro_foto)
    pintor.setClipPath(ruta_circular)
    pos_x= grosor_anillo + (diametro_foto - fuente.width()) // 2
    pos_y= grosor_anillo + (diametro_foto - fuente.height()) // 2
    pintor.drawPixmap(pos_x, pos_y, fuente)
    pintor.end()
    return resultado

TAMANOS_DEFECTO= [("10 por página", 10), ("25 por página", 25), ("50 por página", 50),
                    ("100 por página", 100), ("Todos (sin paginar)", 0)]

ICONO_TABLA= "tableico.ico"


class ControlPaginacion(QWidget):

    cambio= Signal()

    def __init__(self, tamanos=None, tamano_inicial=50, parent=None):

        super().__init__(parent)
        self.pagina_actual= 0
        self.total_registros= 0
        self._tamanos= tamanos or TAMANOS_DEFECTO

        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(0, 4, 0, 4)

        self.lbl_total= QLabel("0 registro(s)")
        self.lbl_total.setObjectName("DescModulo")
        disposicion.addWidget(self.lbl_total)
        disposicion.addStretch()

        #Iconos vectoriales propios (EMOJI_PAG_*): chevrons dibujados con QPainter en vez de los emojis ⏮/◀/▶/⏭, que
        #cambiaban de apariencia según la fuente del sistema. "Primera"/"Última" quedan como botones de solo-icono (con
        #tooltip), y "Anterior"/"Siguiente" llevan el chevron a un lado del texto.
        self.btn_primera= QPushButton("")
        self.btn_primera.setObjectName("BtnAccionNeutro")
        self.btn_primera.setFixedHeight(30)
        self.btn_primera.setFixedSize(34, 30)
        self.btn_primera.setToolTip("Primera página")
        self.btn_primera.setIcon(icono_emoji(EMOJI_PAG_PRIMERA, 18))
        self.btn_primera.setIconSize(_QSize_emoji(18, 18))
        self.btn_primera.clicked.connect(self._ir_primera)
        disposicion.addWidget(self.btn_primera)

        self.btn_anterior= QPushButton("Anterior")
        self.btn_anterior.setObjectName("BtnAccionNeutro")
        self.btn_anterior.setFixedHeight(30)
        self.btn_anterior.setIcon(icono_emoji(EMOJI_PAG_ANTERIOR, 16))
        self.btn_anterior.setIconSize(_QSize_emoji(16, 16))
        self.btn_anterior.clicked.connect(self._ir_anterior)
        disposicion.addWidget(self.btn_anterior)

        self.lbl_info= QLabel("Página 1 de 1")
        self.lbl_info.setObjectName("DescModulo")
        disposicion.addWidget(self.lbl_info)

        self.btn_siguiente= QPushButton("Siguiente")
        self.btn_siguiente.setObjectName("BtnAccionNeutro")
        self.btn_siguiente.setFixedHeight(30)
        self.btn_siguiente.setIcon(icono_emoji(EMOJI_PAG_SIGUIENTE, 16))
        self.btn_siguiente.setIconSize(_QSize_emoji(16, 16))
        self.btn_siguiente.clicked.connect(self._ir_siguiente)
        disposicion.addWidget(self.btn_siguiente)

        self.btn_ultima= QPushButton("")
        self.btn_ultima.setObjectName("BtnAccionNeutro")
        self.btn_ultima.setFixedHeight(30)
        self.btn_ultima.setFixedSize(34, 30)
        self.btn_ultima.setToolTip("Última página")
        self.btn_ultima.setIcon(icono_emoji(EMOJI_PAG_ULTIMA, 18))
        self.btn_ultima.setIconSize(_QSize_emoji(18, 18))
        self.btn_ultima.clicked.connect(self._ir_ultima)
        disposicion.addWidget(self.btn_ultima)

        disposicion.addSpacing(12)
        disposicion.addWidget(QLabel("Mostrar:"))
        self.combo_tamano= QComboBox()
        for etiqueta, valor in self._tamanos:
            self.combo_tamano.addItem(etiqueta, valor)
        idx= self.combo_tamano.findData(tamano_inicial)
        self.combo_tamano.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_tamano.currentIndexChanged.connect(self._cambio_tamano)
        #Import local (no al tope del archivo) para evitar el ciclo de imports:
        #configuracion.py ya importa de este módulo (paginacion.py).
        from src.interfaz.configuracion import conectar_tooltip_seleccion
        conectar_tooltip_seleccion(self.combo_tamano, "Cantidad de resultados por página")
        disposicion.addWidget(self.combo_tamano)

        self._actualizar_etiqueta()

    def tamano_pagina(self):

        return self.combo_tamano.currentData()

    def total_paginas(self):

        tam= self.tamano_pagina()
        if not tam:
            return 1
        return max(1, math.ceil(self.total_registros / tam))

    def rango_actual(self):

        tam= self.tamano_pagina()
        if not tam:
            return 0, self.total_registros
        inicio= self.pagina_actual * tam
        fin= min(inicio + tam, self.total_registros)
        return inicio, fin

    def establecer_total(self, total):

        self.total_registros= total
        total_paginas= self.total_paginas()
        if self.pagina_actual >= total_paginas:
            self.pagina_actual= max(0, total_paginas - 1)
        self._actualizar_etiqueta()

    def reiniciar(self):

        self.pagina_actual= 0

    def _actualizar_etiqueta(self):

        total_paginas= self.total_paginas()
        self.lbl_total.setText(f"{self.total_registros} registro(s)")
        self.lbl_info.setText(f"Página {self.pagina_actual + 1} de {total_paginas}")
        self.btn_primera.setEnabled(self.pagina_actual > 0)
        self.btn_anterior.setEnabled(self.pagina_actual > 0)
        self.btn_siguiente.setEnabled(self.pagina_actual < total_paginas - 1)
        self.btn_ultima.setEnabled(self.pagina_actual < total_paginas - 1)

    def _ir_primera(self):

        if self.pagina_actual != 0:
            self.pagina_actual= 0
            self._actualizar_etiqueta()
            self.cambio.emit()

    def _ir_ultima(self):

        ultima= self.total_paginas() - 1
        if self.pagina_actual != ultima:
            self.pagina_actual= ultima
            self._actualizar_etiqueta()
            self.cambio.emit()

    def _ir_anterior(self):

        if self.pagina_actual > 0:
            self.pagina_actual -= 1
            self._actualizar_etiqueta()
            self.cambio.emit()

    def _ir_siguiente(self):

        if self.pagina_actual < self.total_paginas() - 1:
            self.pagina_actual += 1
            self._actualizar_etiqueta()
            self.cambio.emit()

    def _cambio_tamano(self, _indice):

        self.pagina_actual= 0
        self._actualizar_etiqueta()
        self.cambio.emit()


#DEBOUNCING - Optimización para búsquedas en tiempo real
#Wrapper para QLineEdit que emite una señal solo después de un tiempo
#de inactividad (debounce). Evita que se ejecuten consultas SQL en cada
#pulsación de tecla.
class BusquedaConDebounce(QWidget):
    
    texto_buscado= Signal(str)
    
    def __init__(self, parent=None, delay_ms=300):

        super().__init__(parent)
        self._delay_ms= delay_ms
        self._timer= QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emitir_busqueda)
        
        disposicion= QHBoxLayout(self)
        disposicion.setContentsMargins(0, 0, 0, 0)
        
        self.line_edit= QLineEdit()
        limitar_campo_texto(self.line_edit, 300)
        self.line_edit.setPlaceholderText("Buscar...")
        self.line_edit.textChanged.connect(self._al_texto_cambiado)
        disposicion.addWidget(self.line_edit)
    
    def _al_texto_cambiado(self, texto):

        self._timer.stop()
        self._timer.start(self._delay_ms)
    
    def _emitir_busqueda(self):

        self.texto_buscado.emit(self.line_edit.text().strip())
    
    def text(self):

        return self.line_edit.text()
    
    def setText(self, texto):

        self.line_edit.setText(texto)
    
    def clear(self):

        self.line_edit.clear()
    
    def setPlaceholderText(self, texto):

        self.line_edit.setPlaceholderText(texto)


#Detalle de registro
class DialogoDetalleRegistro(QDialog):

    def __init__(self, parent, titulo, campos, extra_botones=None, foto_path=None):

        #Si hay una tabla en pantalla completa (diálogo modal), el detalle debe parentarse a ELLA: parentado a la
        #ventana principal quedaría por detrás del modal, invisible e inaccesible.
        super().__init__(padre_de_dialogo(parent))
        self.setWindowTitle(titulo)
        self.setWindowIcon(obtener_icono(ICONO_TABLA))
        self.setMinimumWidth(440)

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(22, 20, 22, 20)
        disposicion.setSpacing(10)

        #--- Foto (si el registro tiene una) PRIMERO, bien destacada, y el resto de los datos debajo -en vez de
        #mezclarla como un campo más de texto vacío entre los demás. ---
        pixmap_grande= _pixmap_circular_con_anillo(foto_path, 112) if foto_path else None
        if pixmap_grande is not None:
            bloque_foto= QVBoxLayout()
            bloque_foto.setSpacing(4)
            lbl_foto_grande= QLabel()
            lbl_foto_grande.setPixmap(pixmap_grande)
            lbl_foto_grande.setFixedSize(pixmap_grande.size())
            lbl_foto_grande.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fila_foto= QHBoxLayout()
            fila_foto.addStretch()
            fila_foto.addWidget(lbl_foto_grande)
            fila_foto.addStretch()
            bloque_foto.addLayout(fila_foto)
            disposicion.addLayout(bloque_foto)
            disposicion.addSpacing(2)
            separador= QFrame()
            separador.setFrameShape(QFrame.Shape.HLine)
            separador.setFrameShadow(QFrame.Shadow.Sunken)
            disposicion.addWidget(separador)
            disposicion.addSpacing(4)

        lbl_encabezado= QLabel(titulo)
        lbl_encabezado.setStyleSheet("font-size: 15px; font-weight: bold;")
        disposicion.addWidget(lbl_encabezado)

        for etiqueta, valor in campos:
            fila= QHBoxLayout()
            lbl_etiqueta= QLabel(f"{etiqueta}:")
            lbl_etiqueta.setStyleSheet("font-weight: bold;")
            lbl_etiqueta.setMinimumWidth(170)
            lbl_etiqueta.setWordWrap(True)
            fila.addWidget(lbl_etiqueta)
            texto_valor= str(valor).strip() if valor not in (None, "") else "—"
            lbl_valor= QLabel(texto_valor)
            lbl_valor.setWordWrap(True)
            fila.addWidget(lbl_valor, 1)
            disposicion.addLayout(fila)

        disposicion.addStretch()

        #Botones adicionales (ej. "Ver Descripción completa") que un módulo puede pasar para abrir contenido que no
        #cabe/no se muestra en las filas de arriba (campos largos que la tabla ni siquiera guarda como columna). Van
        #antes de "Cerrar", en el mismo estilo neutro.
        if extra_botones:
            for texto, callback in extra_botones:
                btn_extra= QPushButton(texto)
                btn_extra.setObjectName("BtnAccionNeutro")
                btn_extra.clicked.connect(callback)
                disposicion.addWidget(btn_extra)

        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.accept)
        disposicion.addWidget(btn_cerrar)


def mostrar_detalle_fila(parent, tabla, fila, titulo="Detalle del Registro", extra_botones=None):

    if fila < 0 or fila >= tabla.rowCount():
        return
    campos= []
    foto_path= None
    for col in range(tabla.columnCount()):
        #Una columna oculta (p. ej. un ID interno que la tabla ya no muestra) no debe reaparecer aquí: si se ocultó en
        #la tabla es porque no es algo que el usuario necesite ver, y el detalle no es una puerta trasera para volver a
        #mostrarla.
        if tabla.isColumnHidden(col):
            continue
        header_item= tabla.horizontalHeaderItem(col)
        etiqueta= header_item.text() if header_item else f"Columna {col + 1}"
        #Columna puramente decorativa sin encabezado (p. ej. un punto de color junto al nombre): no aporta un campo
        #propio al detalle, solo saldría con etiqueta y valor vacíos.
        if not etiqueta.strip():
            continue
        item= tabla.item(fila, col)
        #La columna "Foto" es decorativa (un QPixmap chico vía DecorationRole, sin texto): en vez de agregarla como un
        #campo más -que saldría vacío ("—")-, se saca la ruta real guardada en
        #ROL_RUTA_FOTO (ver estudiantes.py/personal.py/profesores.py) y se
        #muestra aparte, en grande, arriba de todo el detalle.
        if item is not None and etiqueta.strip().lower() == "foto":
            ruta= item.data(ROL_RUTA_FOTO)
            if ruta:
                foto_path= ruta
            continue
        #Algunas tablas (p. ej. Estudiantes vistos por Director/Admin) no tienen una columna dedicada "Foto" -esa
        #columna la ocupa "Matrícula"-, pero el registro sí tiene una fotografía guardada. En ese caso el módulo deja
        #la ruta en ROL_RUTA_FOTO sobre esa misma columna (sin decoración, para no tapar el texto) y aquí se recupera
        #como respaldo, SIN quitar el campo de la lista -a diferencia de la columna "Foto" pura, este campo sigue
        #mostrando su valor de texto normal (la matrícula) además de la foto grande.
        if item is not None and foto_path is None:
            ruta_respaldo= item.data(ROL_RUTA_FOTO)
            if ruta_respaldo:
                foto_path= ruta_respaldo
        valor= item.text() if item else ""
        if item is not None and not valor:
            #Algunas columnas se muestran con un widget decorativo encima (p. ej. la "píldora" de color de Tipo en
            #Calendario) y dejan el texto del item vacío A PROPÓSITO -si tuviera texto, se vería detrás del widget,
            #mezclado y encimado-, guardando el valor real solo como tooltip. Sin este respaldo, el detalle de esas
            #columnas salía en blanco aunque la tabla sí mostrara el dato con toda claridad.
            valor= item.toolTip()
        campos.append((etiqueta, valor))
    DialogoDetalleRegistro(parent, titulo, campos, extra_botones=extra_botones, foto_path=foto_path).exec()


def mostrar_detalle_campos(parent, titulo, campos, extra_botones=None, foto_path=None):

    DialogoDetalleRegistro(parent, titulo, campos, extra_botones=extra_botones, foto_path=foto_path).exec()


#Ventana simple de solo-lectura para mostrar un texto que puede ser
#largo (ej. la descripción completa de una tarea/calificación) sin
#truncarlo ni forzarlo dentro de una fila de detalle.
def mostrar_texto_largo(parent, titulo, texto):

    dialogo= QDialog(padre_de_dialogo(parent))
    dialogo.setWindowTitle(titulo)
    dialogo.setWindowIcon(obtener_icono(ICONO_TABLA))
    dialogo.setMinimumSize(440, 320)
    disposicion= QVBoxLayout(dialogo)
    disposicion.setContentsMargins(22, 20, 22, 20)
    disposicion.setSpacing(10)
    lbl_encabezado= QLabel(titulo)
    lbl_encabezado.setStyleSheet("font-size: 15px; font-weight: bold;")
    disposicion.addWidget(lbl_encabezado)
    in_caja_texto= QTextEdit()
    limitar_campo_texto(in_caja_texto, 5000)
    in_caja_texto.setReadOnly(True)
    in_caja_texto.setPlainText(texto.strip() if texto else "— Sin descripción —")
    disposicion.addWidget(in_caja_texto, 1)
    btn_cerrar= QPushButton("Cerrar")
    btn_cerrar.setIcon(icono_emoji("✖"))
    btn_cerrar.setIconSize(_QSize_emoji(16, 16))
    btn_cerrar.setObjectName("BtnAccionNeutro")
    btn_cerrar.clicked.connect(dialogo.accept)
    disposicion.addWidget(btn_cerrar)
    dialogo.exec()


#proveedor_extra_botones (opcional): función que recibe la fila
#seleccionada (índice) y devuelve una lista de (texto, callback) para
#agregarse como botones extra dentro del diálogo de detalle.
def agregar_boton_detalle(layout_botones, tabla, parent, titulo="Detalle del Registro", texto_boton="Ver Detalle",
                           proveedor_extra_botones= None):

    btn_detalle= QPushButton(texto_boton)
    btn_detalle.setObjectName("BtnAccionNeutro")

    def _abrir():

        fila_sel= tabla.currentRow()
        if fila_sel < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un registro de la tabla.", parent)
            return
        extra_botones= proveedor_extra_botones(fila_sel) if proveedor_extra_botones else None
        mostrar_detalle_fila(parent, tabla, fila_sel, titulo, extra_botones=extra_botones)

    btn_detalle.clicked.connect(_abrir)
    if layout_botones is not None:
        layout_botones.addWidget(btn_detalle)
    return btn_detalle


#Pantalla completa para tablas Solo puede haber una tabla en pantalla completa abierta a la vez en TODA la app
#(no una por módulo): si ya hay una abierta, el botón ⛶ de cualquier otro lugar debe limitarse a traerla al
#frente, nunca apilar una segunda instancia encima.
_ESTADO_PANTALLA_COMPLETA= {"dialogo": None}


#Devuelve el diálogo de pantalla completa abierto ahora mismo, o None.
#
#Los módulos lo usan para parentar a él cualquier ventana que abran
#(filtros, detalle, mensajes): el diálogo de pantalla completa es MODAL,
#así que cualquier ventana parentada a la ventana principal queda DETRÁS
#de él e inaccesible -se ve el problema al abrir los filtros estando en
#pantalla completa-. Mismo criterio que reportes_editor._padre_dialogo.
def dialogo_pantalla_completa_activo():

    return _ESTADO_PANTALLA_COMPLETA["dialogo"]


#Devuelve el padre que debe usar un diálogo que se abre desde `parent`:
#el diálogo de pantalla completo si hay uno activo (ver
#`dialogo_pantalla_completa_activo`), o `parent` tal cual si no.
def padre_de_dialogo(parent):

    activo= _ESTADO_PANTALLA_COMPLETA["dialogo"]
    if activo is not None and parent is not None:
        return activo
    return parent


#Busca, recursivamente dentro de `layout` (bajando por sub-layouts
#anidados con addLayout, p. ej. el `contenido` de TarjetaSeccion en
#configuracion.py), el layout que contiene a `widget` DIRECTAMENTE.
#
#`QLayout.indexOf(widget)` -usado más abajo- NO es recursivo: solo
#encuentra widgets agregados directamente a ESE layout, no a un
#sub-layout suyo. Sin esto, para cualquier widget que viva dentro de un
#layout anidado (como TarjetaSeccion.contenido, que a su vez está
#metido dentro del layout raíz de la tarjeta), `layout.indexOf(widget)`
#siempre da -1 y, al restaurar, el widget termina agregado al FINAL del
#layout raíz en vez de volver a su posición real dentro del anidado
#-reordenando visualmente el resto de la tarjeta cada vez que se sale
#de pantalla completa-.
#
#Devuelve el sub-layout directo, o None si no se encuentra (p. ej. el
#widget está suelto sin layout todavía).
def _buscar_layout_directo(disposicion, widget):

    if disposicion is None:
        return None
    if disposicion.indexOf(widget) >= 0:
        return disposicion
    for i in range(disposicion.count()):
        item= disposicion.itemAt(i)
        sub= item.layout()
        if sub is not None:
            encontrado= _buscar_layout_directo(sub, widget)
            if encontrado is not None:
                return encontrado
    return None


#Diálogo maximizado que "toma prestados" temporalmente los widgets
#reales de un módulo (filtros + tabla + paginación) en vez de duplicar
#su lógica. Como son los MISMOS objetos -no copias-, la búsqueda, los
#combos, los chips de filtro, la paginación y cualquier señal ya
#conectada siguen funcionando exactamente igual dentro del diálogo, sin
#tener que volver a cablear nada.
#
#Al cerrarse, cada widget vuelve a su layout y posición original -el
#resto de la pantalla queda exactamente como estaba antes de expandir.
#
#Solo puede haber UNA instancia abierta en toda la app a la vez (ver
#`_ESTADO_PANTALLA_COMPLETA`): no tendría sentido -ni cabría en la
#pantalla- apilar una tabla en pantalla completa sobre otra.
class _DialogoTablaCompleta(QDialog):

    def __init__(self, widgets, titulo="Tabla", parent=None):

        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setWindowIcon(obtener_icono(ICONO_TABLA))
        self.setModal(True)
        #Libera el objeto de C++ apenas se cierra en vez de esperar al recolector de basura de Python -no queda
        #colgando en memoria entre una apertura y la siguiente.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._widgets= widgets
        self._cerrando= False
        #(padre_original, layout_original, índice_original, stretch) de cada widget, para poder devolverlo exactamente
        #a su sitio.
        self._ubicaciones= []
        #Algunas tablas traen un tope de alto pensado para su tarjeta
        #normal (p. ej. setMaximumHeight(580)) -aquí, en pantalla
        #completa, ese tope hay que quitarlo temporalmente o la tabla se queda chica aunque el diálogo ocupe toda la
        #pantalla.
        self._topes_alto_originales= []
        #Fuente y alto de fila agrandados mientras dura la pantalla completa -para que de verdad se vea "más grande y
        #mejor", no solo con más aire alrededor de la misma tabla chica.
        self._fuentes_originales= []
        self._alto_fila_original= []

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(24, 18, 24, 20)
        disposicion.setSpacing(12)

        #---------- Contenido dentro de un QScrollArea ---------- Si al expandir algo (p. ej. el panel de "Más filtros"
        #de observaciones) el contenido excede la altura de la ventana, el scroll vertical aparece en vez de dejar los
        #botones de abajo fuera de la vista e inaccesibles. La tabla sigue llevándose el espacio extra: el scroll SOLO
        #aparece si de verdad hace falta.
        self._contenido_scroll= QWidget()
        layout_contenido= QVBoxLayout(self._contenido_scroll)
        layout_contenido.setContentsMargins(0, 0, 0, 0)
        layout_contenido.setSpacing(12)
        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(self._contenido_scroll)
        disposicion.addWidget(scroll, 1)

        #---------- Encabezado: icono + título a la izquierda, atajo y botón de salida a la derecha ----------
        fila_cabecera= QHBoxLayout()
        fila_cabecera.setSpacing(10)
        lbl_icono_cabecera= QLabel()
        lbl_icono_cabecera.setPixmap(pixmap_emoji("⛶", 22))
        fila_cabecera.addWidget(lbl_icono_cabecera)
        lbl_titulo_cabecera= QLabel(titulo)
        lbl_titulo_cabecera.setObjectName("TituloPantallaCompleta")
        lbl_titulo_cabecera.setStyleSheet("font-size: 17px; font-weight: 600;")
        fila_cabecera.addWidget(lbl_titulo_cabecera)
        fila_cabecera.addStretch()

        lbl_atajo= QLabel("Esc")
        lbl_atajo.setToolTip("También puedes presionar Esc para salir")
        lbl_atajo.setStyleSheet(
            "QLabel { background: rgba(127,127,127,0.16); border-radius: 6px;"
            " padding: 3px 8px; font-size: 11px; font-weight: 600; }")
        fila_cabecera.addWidget(lbl_atajo)

        self.btn_salir= QPushButton(" Salir de pantalla completa")
        self.btn_salir.setObjectName("BtnAccionNeutro")
        self.btn_salir.setIcon(icono_emoji("⛶"))
        self.btn_salir.setIconSize(QSize(15, 15))
        self.btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salir.setToolTip("Cerrar la pantalla completa y volver a la vista normal (Esc)")
        self.btn_salir.clicked.connect(self.accept)
        fila_cabecera.addWidget(self.btn_salir)
        disposicion.addLayout(fila_cabecera)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setFrameShadow(QFrame.Shadow.Sunken)
        disposicion.addWidget(separador)

        for widget in widgets:
            padre= widget.parentWidget()
            layout_top= padre.layout() if padre is not None else None
            #Encuentra el sub-layout DIRECTO que contiene al widget (puede ser el layout_top mismo, o uno anidado varios
            #niveles adentro -ver _buscar_layout_directo-), para poder devolverlo exactamente a su sitio real al cerrar la
            #pantalla completa.
            layout_padre= _buscar_layout_directo(layout_top, widget)
            indice= layout_padre.indexOf(widget) if layout_padre is not None else -1
            stretch= 0
            if layout_padre is not None and hasattr(layout_padre, "stretch"):
                try:

                    stretch= layout_padre.stretch(indice)
                except Exception:
                    stretch= 0
            self._ubicaciones.append((widget, layout_padre, indice, stretch))

            #Si el widget ES en sí una tabla (no solo un contenedor que la contiene), también hay que quitarle su tope de
            #alto y agrandar su fuente: findChildren no incluye al propio widget, y varios
            #módulos (asistencia, profesores, calendario...) pasan la tabla
            #DIRECTAMENTE en la lista de widgets. Sin esto, la tabla quedaba con el máximo pensado para su tarjeta normal y
            #el espacio extra de la pantalla completa se repartía en huecos vacíos alrededor.
            tablas_dentro= widget.findChildren(QTableWidget)
            propias= ([widget] if isinstance(widget, QTableWidget) else []) + tablas_dentro
            for tabla in propias:
                self._topes_alto_originales.append((tabla, tabla.maximumHeight()))
                tabla.setMaximumHeight(16_777_215)  #sin tope (QWIDGETSIZE_MAX)

                self._fuentes_originales.append((tabla, tabla.font()))
                fuente_grande= tabla.font()
                fuente_grande.setPointSize(fuente_grande.pointSize() + 2)
                tabla.setFont(fuente_grande)
                cabecera_h= tabla.horizontalHeader()
                self._fuentes_originales.append((cabecera_h, cabecera_h.font()))
                fuente_cab= cabecera_h.font()
                fuente_cab.setPointSize(fuente_cab.pointSize() + 2)
                cabecera_h.setFont(fuente_cab)

                v_header= tabla.verticalHeader()
                self._alto_fila_original.append((v_header, v_header.defaultSectionSize()))
                v_header.setDefaultSectionSize(int(v_header.defaultSectionSize() * 1.35))

            if layout_padre is not None:
                layout_padre.removeWidget(widget)
            widget.setParent(self._contenido_scroll)
            es_tabla= isinstance(widget, QTableWidget) or bool(tablas_dentro)
            #La tarjeta de la tabla se lleva casi todo el espacio extra (stretch 6); filtros y paginación se quedan con su
            #alto
            #natural (stretch 0), así la tabla es lo que de verdad crece.
            layout_contenido.addWidget(widget, stretch=6 if es_tabla else 0)

        _ESTADO_PANTALLA_COMPLETA["dialogo"]= self
        self.showMaximized()

        #Entrada suave (fundido de 0% a 100% de opacidad) en vez de un golpe seco de pantalla completa -mismo tipo de
        #detalle que ya usa el resto de la app (ver _fundido_entrada en configuracion.py). Se guarda como atributo
        #(self._animacion) para que Python no lo recolecte a medio camino: sin esa referencia viva, la animación se
        #corta de golpe apenas termina este método.
        self._efecto_opacidad= QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._efecto_opacidad)
        self._animacion= QPropertyAnimation(self._efecto_opacidad, b"opacity", self)
        self._animacion.setDuration(180)
        self._animacion.setStartValue(0.0)
        self._animacion.setEndValue(1.0)
        self._animacion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animacion.start()

    def _restaurar(self):

        #El efecto de opacidad ya cumplió su función en la entrada; si se queda puesto durante el cierre, Qt puede
        #repintar de más -se quita antes de devolver los widgets a su sitio.
        self.setGraphicsEffect(None)
        try:

            for tabla, tope in self._topes_alto_originales:
                tabla.setMaximumHeight(tope)
            for objeto, fuente in self._fuentes_originales:
                objeto.setFont(fuente)
            for v_header, alto in self._alto_fila_original:
                v_header.setDefaultSectionSize(alto)
            #Se reinsertan en orden INVERSO al que se quitaron (ver el loop de `widgets` en __init__). Los tres widgets
            #comparten el mismo layout_padre, así que cada índice quedó grabado en el momento en que a ESE widget le tocaba
            #salir -es decir, relativo a un layout que todavía tenía a los widgets restantes puestos-. Reinsertar en el
            #mismo orden (en vez de invertido) usa esos índices contra un layout que ya tiene a los OTROS widgets de vuelta
            #adentro, y el resultado queda intercalado/desordenado (paginación arriba de la tabla, botonera en medio, etc.
            #-el reporte de este bug-). Deshacer en orden inverso al de la remoción es la forma correcta de revertir una
            #serie de remociones sobre un mismo layout.
            for widget, layout_padre, indice, stretch in reversed(self._ubicaciones):
                #Los widgets viven dentro del contenedor del scroll (ver __init__), no directo en el layout del diálogo.
                if self._contenido_scroll is not None and widget.parent() is self._contenido_scroll:
                    self._contenido_scroll.layout().removeWidget(widget)
                elif self.layout() is not None:
                    self.layout().removeWidget(widget)
                widget.setParent(layout_padre.parentWidget() if layout_padre is not None else None)
                if layout_padre is not None:
                    if indice < 0 or indice > layout_padre.count():
                        layout_padre.addWidget(widget)
                    else:
                        try:

                            layout_padre.insertWidget(indice, widget, stretch=stretch)
                        except TypeError:
                            #Layout sin soporte de stretch en insertWidget (p. ej. QGridLayout): se reinserta sin él.
                            layout_padre.insertWidget(indice, widget)
        except Exception:
            #Nunca dejar la restauración a medias: si algo falla al devolver un widget, los restantes DEBEN volver a su
            #sitio -si no, el módulo se queda despoblado y el diálogo pegado-.
            import traceback
            traceback.print_exc()
        finally:
            if _ESTADO_PANTALLA_COMPLETA["dialogo"] is self:
                _ESTADO_PANTALLA_COMPLETA["dialogo"]= None

    def accept(self):

        if self._cerrando:
            return
        self._cerrando= True
        self._restaurar()
        super().accept()

    def reject(self):

        if self._cerrando:
            return
        self._cerrando= True
        self._restaurar()
        #super().reject() llama a done(Rejected), que es lo que TERMINA el
        #loop de exec() -sin esto, el diálogo modal queda vivo aunque sus widgets ya se hayan devuelto al módulo:
        #ventana vacía y app bloqueada hasta forzar el cierre.
        super().reject()

    def closeEvent(self, evento):

        #La X de la barra de título: se trata EXACTAMENTE como un rechazo. NO basta con aceptar el evento: QDialog
        #cierra vía reject() y, si _cerrando ya estaba puesto, el override anterior se comía la llamada a
        #super().reject() dejando el exec() colgado para siempre.
        evento.accept()
        if not self._cerrando:
            self.reject()


#Agrega un botón cuadrado con el icono ⛶ a `layout_cabecera` (p. ej.
#una fila QHBoxLayout puesta como encabezado de la tarjeta de la tabla)
#que abre `widgets` -típicamente [tarjeta_filtros, tarjeta_tabla,
#control_paginacion]- dentro de un diálogo maximizado, con búsqueda y
#filtros funcionando exactamente igual que en la pantalla normal.
#
#El mismo botón sirve para entrar y para salir: si esta tabla ya está
#en pantalla completa, volver a pulsarlo la cierra. Si hay OTRA tabla
#en pantalla completa abierta (de otro módulo), en vez de abrir una
#segunda instancia simplemente la trae al frente -solo puede existir
#una a la vez en toda la app-.
#
#`parent` debe ser el propio módulo/página (para que el diálogo se
#centre sobre la ventana principal); si se omite, se usa el primer
#widget de la lista.
#
#Uso típico, justo después de armar tarjeta_filtros/tarjeta_tabla/pagina:
#agregar_boton_pantalla_completa(
#None,  #o una QHBoxLayout donde alojar el botón
#[self.tarjeta_filtros, self.tarjeta_tabla, self.pagina],
#titulo= "Materiales", parent=self)
#Con layout_cabecera=None el botón ⛶ vive a la derecha del control de
#paginación (o del primer widget si no hay paginación).
def agregar_boton_pantalla_completa(layout_cabecera, widgets, titulo="Tabla", parent=None):

    btn= QPushButton()
    btn.setObjectName("BtnPantallaCompleta")
    btn.setIcon(icono_emoji("⛶"))
    btn.setIconSize(QSize(16, 16))
    btn.setFixedSize(30, 30)
    btn.setToolTip("Abrir en pantalla completa (búsqueda y filtros completos)")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)

    estado= {"dialogo_propio": None}

    def _abrir():

        activo= _ESTADO_PANTALLA_COMPLETA["dialogo"]
        if activo is not None:
            if activo is estado["dialogo_propio"]:
                #Ya es esta misma tabla: el botón actúa como "salir".
                activo.accept()
            else:
                #Hay OTRA tabla en pantalla completa: no se apila una segunda, solo se trae al frente la que ya está abierta.
                activo.raise_()
                activo.activateWindow()
            return
        dialogo_ref= _DialogoTablaCompleta(widgets, titulo=titulo, parent=parent or widgets[0])
        estado["dialogo_propio"]= dialogo_ref
        dialogo_ref.finished.connect(lambda _: estado.__setitem__("dialogo_propio", None))
        dialogo_ref.exec()

    btn.clicked.connect(_abrir)
    if layout_cabecera is None:
        #Los labels de cabecera de las tablas se quitaron (ocupaban una fila entera solo para decir de qué era la
        #tabla), así que varios módulos ya no tienen esa fila donde alojar el botón ⛶. En ese caso el botón vive dentro
        #del control de paginación de la propia tabla (a su derecha), o -si el módulo no tiene paginación- en el primer
        #widget de la lista (típicamente la barra de búsqueda).
        destino= None
        for widget in widgets:
            pag= widget if isinstance(widget, ControlPaginacion) else widget.findChild(ControlPaginacion)
            if pag is not None:
                destino= pag.layout()
                break
        if destino is None:
            for widget in widgets:
                if widget.layout() is not None:
                    destino= widget.layout()
                    break
        if destino is not None:
            destino.addWidget(btn)
    else:
        layout_cabecera.addWidget(btn)
    return btn