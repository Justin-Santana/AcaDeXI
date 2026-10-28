#Framework visual compartido para los wizards de configuración de AcaDeXI.
#
#El wizard institucional de Full Institutional (WizardConfiguracion en
#configuracion.py) define el lenguaje visual "bonito" del asistente: header
#con badge + stepper animado + contador de pasos, páginas como tarjetas
#elevadas ("WizardCard") con sombra suave, pie con botones Atrás/Siguiente y
#transición de deslizamiento + fundido entre pasos. Este módulo extrae ese
#diseño a una clase base (WizardEstilizado) para que los demás wizards de la
#app (Single Teacher, Side Stepper) se vean EXACTAMENTE igual, sin copiar el
#QSS ni la mecánica a mano en cada archivo.
#
#Los wizards hijos solo implementan `_construir_paginas()` (llamando a
#`self.agregar_pagina(...)` por cada paso, en orden) y opcionalmente
#`validar_paso(idx)` y `finalizar()`. El header, el stepper, los botones, el
#tema y las animaciones salen de aquí.

from PySide6.QtWidgets import (QDialog, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor

from src.nucleo.bd import obtener_carpeta_datos  #noqa: F401  (útil para quien importe este módulo)
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos import ICONO_SETUP, aplicar_icono_ventana, centrar_y_al_frente
from src.nucleo.iconos_emoji import pixmap_emoji, icono_emoji
from src.interfaz.configuracion import WizardStepper, _fundido_entrada, _RealceHover, _hex_a_rgba

try:

    from src.inicio.bienvenida import _pixmap_logo_base
except Exception:
    _pixmap_logo_base= None


#Base visual de todos los asistentes de AcaDeXI (misma apariencia que
#el wizard institucional de Full Institutional). Subclases llaman a
#`self.agregar_pagina(titulo, icono)` dentro de `_construir_paginas()`.
class WizardEstilizado(QDialog):

    def __init__(self, main_window, titulo_ventana, tamano=(760, 620),
                 icono_ventana= ICONO_SETUP, parent=None):

        super().__init__(parent if parent is not None else main_window)
        self.main_window= main_window
        self.setWindowTitle(titulo_ventana)
        if icono_ventana:
            aplicar_icono_ventana(self, icono_ventana)
        else:
            aplicar_icono_ventana(self)
        self.setMinimumSize(*tamano)
        self._titulos_pasos= []
        self._iconos_pasos= []
        self._construir_ui()
        self._aplicar_tema()
        #Wizard SOLAMENTE centrado (sin WindowStaysOnTopHint): ver centrar_y_al_frente y _FiltroCentradoDialogos en
        #main.py.
        centrar_y_al_frente(self, main_window, siempre_encima=False)

    #Construcción del esqueleto (header / stack / pie)
    def _construir_ui(self):

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(0, 0, 0, 0)
        disposicion.setSpacing(0)

        header= QFrame()
        header.setObjectName("WizardHeader")
        header.setFixedHeight(104)
        header_v= QVBoxLayout(header)
        header_v.setContentsMargins(34, 16, 34, 16)
        header_v.setSpacing(12)

        h_layout= QHBoxLayout()
        h_layout.setSpacing(12)
        #Logo real de AcaDeXI (mismo `_pixmap_logo_base` que ya usa el sidebar en main.py, con el mismo fallback: si el
        #archivo no aparece -dev sin assets o algún empaquetado raro-, cae al emblema de graduación 🎓 en vez de dejar
        #un hueco vacío). Va ANTES del badge del paso actual: el badge cambia de emoji en cada paso (es "dónde estoy"),
        #el logo es fijo (es "qué app es esta") -por eso son dos elementos separados, no uno reemplazando al otro.
        self.lbl_logo_wizard= QLabel()
        self.lbl_logo_wizard.setObjectName("WizardLogo")
        self.lbl_logo_wizard.setFixedSize(38, 38)
        self.lbl_logo_wizard.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _pixmap_base_logo= _pixmap_logo_base() if _pixmap_logo_base else None
        if _pixmap_base_logo is not None:
            self.lbl_logo_wizard.setPixmap(_pixmap_base_logo.scaled(
                28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_logo_wizard.setPixmap(pixmap_emoji("🎓", 20))
        h_layout.addWidget(self.lbl_logo_wizard)
        self.lbl_badge_paso= QLabel()
        self.lbl_badge_paso.setPixmap(pixmap_emoji("🧭", 20))
        self.lbl_badge_paso.setObjectName("WizardBadgePaso")
        self.lbl_badge_paso.setFixedSize(38, 38)
        self.lbl_badge_paso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(self.lbl_badge_paso)
        self.lbl_paso= QLabel("")
        self.lbl_paso.setObjectName("WizardPasoLabel")
        h_layout.addWidget(self.lbl_paso)
        h_layout.addStretch()
        self.lbl_contador= QLabel("")
        self.lbl_contador.setObjectName("WizardContador")
        h_layout.addWidget(self.lbl_contador)
        header_v.addLayout(h_layout)

        #El stepper se agrega DESPUÉS de construir las páginas, porque el total de pasos lo define cuántas veces llamó
        #agregar_pagina() la
        #subclase (mismo comportamiento que WizardStepper(9) del wizard
        #institucional, pero calculado solo).
        self.stepper= None
        disposicion.addWidget(header)

        #Contenedor con margen alrededor del stack: dentro se ve la tarjeta elevada de cada paso (ver agregar_pagina)
        #"flotando" sobre el fondo del diálogo, en vez de pegada borde a borde.
        contenedor_stack= QWidget()
        contenedor_stack.setObjectName("WizardStackContenedor")
        contenedor_stack_layout= QVBoxLayout(contenedor_stack)
        contenedor_stack_layout.setContentsMargins(26, 20, 26, 10)
        self.stack= QStackedWidget()
        contenedor_stack_layout.addWidget(self.stack)
        disposicion.addWidget(contenedor_stack, 1)

        #Las páginas las crea la subclase (hook).
        self._construir_paginas()

        self.stepper= WizardStepper(max(self.stack.count(), 1))
        header_v.addWidget(self.stepper)

        pie= QFrame()
        pie.setObjectName("WizardPie")
        pie.setFixedHeight(68)
        pie_layout= QHBoxLayout(pie)
        pie_layout.setContentsMargins(30, 0, 30, 0)
        self.btn_atras= QPushButton("Atrás")
        self.btn_atras.setIcon(icono_emoji("⬅"))
        self.btn_atras.setIconSize(_QSize_emoji(16, 16))
        self.btn_atras.setObjectName("BtnAccionNeutro")
        self.btn_atras.clicked.connect(self._anterior)
        pie_layout.addWidget(self.btn_atras)
        pie_layout.addStretch()
        self.btn_siguiente= QPushButton("Siguiente ")
        self.btn_siguiente.setIcon(icono_emoji("➡"))
        self.btn_siguiente.setIconSize(_QSize_emoji(16, 16))
        self.btn_siguiente.clicked.connect(self._siguiente)
        pie_layout.addWidget(self.btn_siguiente)
        disposicion.addWidget(pie)

        self.stack.currentChanged.connect(self._actualizar_encabezado)
        self._actualizar_encabezado(0)
        #Fundido de entrada solo para la primera página al abrir el asistente; los cambios de página posteriores usan
        #la transición direccional de
        #_ir_a_paso (más barata: solo anima la página entrante).
        _fundido_entrada(self.stack.currentWidget())

        #Realce (sombra que se eleva) al pasar el mouse sobre los botones.
        self._realce_wizard= _RealceHover(0, 18, 5, self)
        for boton in self.findChildren(QPushButton):
            boton.installEventFilter(self._realce_wizard)


    #Hooks para las subclases
    #La subclase crea aquí sus páginas con self.agregar_pagina(...).
    def _construir_paginas(self):

        raise NotImplementedError

    #La subclase devuelve False (mostrando su aviso) para bloquear el
    #avance desde el paso `indice`. Por defecto no valida nada.
    def validar_paso(self, indice):

        return True

    #Acción al pulsar 'Finalizar' en el último paso (por defecto,
    #aceptar el diálogo).
    def finalizar(self):

        self.accept()

    #Páginas (tarjetas elevadas, igual que _nueva_pagina del wizard Full)
    #Registra un paso y crea su tarjeta elevada. Devuelve (contenedor,
    #layout_interno) para que la subclase llene el formulario igual que
    #hacen los _crear_pasoN de WizardConfiguracion.
    def agregar_pagina(self, titulo, icono="🧭"):

        self._titulos_pasos.append(titulo)
        self._iconos_pasos.append(icono)
        contenedor= QWidget()
        externo= QVBoxLayout(contenedor)
        externo.setContentsMargins(0, 0, 0, 0)
        tarjeta= QFrame()
        tarjeta.setObjectName("WizardCard")
        tarjeta.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sombra= QGraphicsDropShadowEffect(tarjeta)
        sombra.setColor(QColor(0, 0, 0, 55))
        sombra.setOffset(0, 3)
        sombra.setBlurRadius(24)
        tarjeta.setGraphicsEffect(sombra)
        externo.addWidget(tarjeta)
        disposicion= QVBoxLayout(tarjeta)
        disposicion.setContentsMargins(46, 36, 46, 32)
        disposicion.setSpacing(12)
        self.stack.addWidget(contenedor)
        return contenedor, disposicion

    #Título grande de paso (mismo objectName/QSS que el wizard Full).
    def titulo_paso(self, texto):

        lbl= QLabel(texto)
        lbl.setObjectName("WizardSubtitulo")
        return lbl

    #Centro de una página tipo 'Bienvenida'/'Finalización': emoji grande
    #+ título WizardTitulo + descripción WizardDesc, todo centrado.
    def hero_paso(self, emoji, titulo, descripcion):

        lbl_hero= QLabel()
        lbl_hero.setPixmap(pixmap_emoji(emoji, 64))
        lbl_hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t= QLabel(titulo)
        t.setObjectName("WizardTitulo")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d= QLabel(descripcion)
        d.setObjectName("WizardDesc")
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl_hero, t, d

    #Navegación
    def _actualizar_encabezado(self, indice):

        self.lbl_paso.setText(self._titulos_pasos[indice])
        icono= self._iconos_pasos[indice] if indice < len(self._iconos_pasos) else "🧭"
        self.lbl_badge_paso.setPixmap(pixmap_emoji(icono, 20))
        self.lbl_contador.setText(f"Paso {indice + 1} de {len(self._titulos_pasos)}")
        self.btn_atras.setEnabled(indice > 0)
        ultimo= indice == len(self._titulos_pasos) - 1
        self.btn_siguiente.setText("Finalizar " if ultimo else "Siguiente ")
        self.btn_siguiente.setIcon(icono_emoji("🏁" if ultimo else "➡"))
        self.btn_siguiente.setIconSize(_QSize_emoji(16, 16))
        if self.stepper is not None:
            self.stepper.ir_a(indice)

    #Cambia de página con una transición corta de deslizamiento +
    #fundido (~220ms), en el sentido del avance —la misma mecánica del
    #wizard institucional (ver WizardConfiguracion._ir_a_paso).
    def _ir_a_paso(self, nuevo_idx, direccion=1):

        self.stack.setCurrentIndex(nuevo_idx)
        pagina= self.stack.currentWidget()
        ancho= max(self.stack.width(), 1)
        offset= int(ancho * 0.05) * (1 if direccion > 0 else -1)
        pagina.move(offset, 0)
        efecto= QGraphicsOpacityEffect(pagina)
        pagina.setGraphicsEffect(efecto)

        anim_pos= QPropertyAnimation(pagina, b"pos", pagina)
        anim_pos.setDuration(220)
        anim_pos.setStartValue(QPoint(offset, 0))
        anim_pos.setEndValue(QPoint(0, 0))
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_op= QPropertyAnimation(efecto, b"opacity", pagina)
        anim_op.setDuration(200)
        anim_op.setStartValue(0.0)
        anim_op.setEndValue(1.0)
        anim_op.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _limpiar():

            pagina.setGraphicsEffect(None)
        anim_pos.finished.connect(_limpiar)
        #Se guardan las referencias en la página para que Python no las recolecte a mitad de camino (mismo patrón que
        #_fundido_entrada).
        pagina._anim_pos_wizard= anim_pos
        pagina._anim_op_wizard= anim_op
        anim_pos.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        anim_op.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _anterior(self):

        if self.stack.currentIndex() > 0:
            self._ir_a_paso(self.stack.currentIndex() - 1, direccion=-1)

    def _siguiente(self):

        idx= self.stack.currentIndex()
        if not self.validar_paso(idx):
            return
        if idx == self.stack.count() - 1:
            self.finalizar()
        else:
            self._ir_a_paso(idx + 1, direccion=1)



    #Tema (mismo QSS que WizardConfiguracion._aplicar_tema)
    def _aplicar_tema(self):

        paleta= self.main_window.theme_palettes.get(
            self.main_window.tema_actual, self.main_window.theme_palettes["Indigo"])
        idx= 1 if self.main_window.modo_oscuro else 0
        bg_window, bg_panel= paleta["window_bg"][idx], paleta["display_bg"][idx]
        txt_prim, txt_sec= paleta["text_primary"][idx], paleta["text_secondary"][idx]
        bg_btn, accent= paleta["btn_num_bg"][idx], paleta["btn_op_bg"][idx]
        hv_accent= paleta["btn_op_hover"][idx]
        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg_window}; }}
            QFrame#WizardHeader, QFrame#WizardPie {{ background-color: {bg_panel}; }}
            QLabel#WizardBadgePaso {{
                background-color: {_hex_a_rgba(accent, 0.22 if self.main_window.modo_oscuro else 0.12)};
                border-radius: 17px; font-size: 15px; color: {accent};
            }}
            QLabel#WizardLogo {{
                background-color: {bg_panel};
                border: 1px solid {_hex_a_rgba(txt_sec, 0.18)};
                border-radius: 19px;
            }}
            QLabel#WizardPasoLabel {{ font-size: 19px; font-weight: bold; color: {accent}; }}
            QLabel#WizardContador {{
                font-size: 12px; font-weight: 600; color: {accent};
                background-color: {_hex_a_rgba(accent, 0.16)};
                padding: 4px 12px; border-radius: 10px;
            }}
            QWidget#WizardStackContenedor {{ background-color: transparent; }}
            QFrame#WizardCard {{
                background-color: {bg_panel};
                border-radius: 18px;
                border: 1px solid {_hex_a_rgba(txt_sec, 0.14)};
            }}
            QLabel#WizardTitulo {{ font-size: 26px; font-weight: 800; color: {accent}; }}
            QLabel#WizardSubtitulo {{ font-size: 20px; font-weight: bold; color: {txt_prim}; margin-bottom: 10px; }}
            QLabel#WizardDesc {{ font-size: 13px; color: {txt_sec}; }}
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
                background-color: {bg_panel}; border: 2px solid {bg_btn}; color: {txt_prim};
                padding: 7px 9px; border-radius: 9px;
            }}
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
                border: 2px solid {accent};
            }}
            QLabel {{ color: {'#FFFFFF' if self.main_window.modo_oscuro else '#000000'}; background: transparent; }}
            QPushButton {{
                background-color: {accent}; color: white; border: none; border-radius: 9px;
                padding: 10px 22px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hv_accent}; }}
            QPushButton:disabled {{ background-color: {bg_btn}; color: {txt_sec}; }}
            QPushButton#BtnAccionNeutro {{ background-color: {bg_btn}; color: {txt_prim}; }}
        """)
        if self.stepper is not None:
            self.stepper.establecer_colores(accent, bg_btn, bg_panel, txt_sec)
