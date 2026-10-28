#Utilidades compartidas para el manejo de fotografías en AcaDeXI:
#- VisorFotoDialog: muestra la foto ampliada en una ventana emergente.
#- DialogoRecorteFoto: permite seleccionar y recortar una región de la imagen antes de guardarla.
#- seleccionar_y_recortar_foto(): flujo completo (elegir archivo -> recortar -> guardar) reutilizable
#desde cualquier módulo (Estudiantes, Configuración/Logotipo, etc.).
import os
import uuid

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QRubberBand, QSizePolicy)
from PySide6.QtCore import Qt, QRect, QPoint, QSize
from PySide6.QtGui import QPixmap, QImage

from src.nucleo.iconos import mostrar_mensaje, aplicar_icono_ventana, centrar_y_al_frente, ICONO_RECORTE
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import icono_emoji, pixmap_emoji, quitar_emojis_texto


#Ventana emergente que muestra una fotografía ampliada.
class VisorFotoDialog(QDialog):

    def __init__(self, ruta_imagen, parent=None, titulo="Fotografía"):

        super().__init__(parent)
        self.setWindowTitle(titulo)
        aplicar_icono_ventana(self, ICONO_RECORTE)
        self.setMinimumSize(360, 360)

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(16, 16, 16, 16)

        lbl_imagen= QLabel()
        lbl_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap= QPixmap(ruta_imagen)
        if not pixmap.isNull():
            pixmap= pixmap.scaled(560, 560, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
            lbl_imagen.setPixmap(pixmap)
        else:
            lbl_imagen.setText("No se pudo cargar la imagen.")
        disposicion.addWidget(lbl_imagen)

        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.clicked.connect(self.accept)
        disposicion.addWidget(btn_cerrar)

        centrar_y_al_frente(self, parent)


#Permite seleccionar (arrastrando el mouse) una región rectangular de la imagen
#y devuelve la imagen recortada en self.imagen_recortada (QImage) si se acepta.
class DialogoRecorteFoto(QDialog):

    LADO_MAXIMO= 480

    def __init__(self, ruta_imagen, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Recortar Fotografía")
        aplicar_icono_ventana(self, ICONO_RECORTE)
        self.imagen_original= QImage(ruta_imagen)
        self.imagen_recortada= None
        self.origen_seleccion= QPoint()
        self.rubber_band= None
        self._rect_seleccion= QRect()

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(16, 16, 16, 16)

        lbl_info= QLabel("Arrastra sobre la imagen para seleccionar el área a recortar. "
                      "Si no seleccionas nada, se usará la imagen completa.")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        self.lbl_imagen= QLabel()
        self.lbl_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_imagen.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.pixmap_mostrado= QPixmap.fromImage(self.imagen_original).scaled(
            self.LADO_MAXIMO, self.LADO_MAXIMO, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.lbl_imagen.setPixmap(self.pixmap_mostrado)
        self.lbl_imagen.setFixedSize(self.pixmap_mostrado.size())

        fila_centrada= QHBoxLayout()
        fila_centrada.addStretch()
        fila_centrada.addWidget(self.lbl_imagen)
        fila_centrada.addStretch()
        disposicion.addLayout(fila_centrada)

        self.lbl_imagen.installEventFilter(self)
        self.rubber_band= QRubberBand(QRubberBand.Shape.Rectangle, self.lbl_imagen)

        fila_botones= QHBoxLayout()
        btn_reiniciar= QPushButton("Quitar selección")
        btn_reiniciar.setIcon(icono_emoji("🗑"))
        btn_reiniciar.setIconSize(_QSize_emoji(16, 16))
        btn_reiniciar.clicked.connect(self._quitar_seleccion)
        fila_botones.addWidget(btn_reiniciar)
        fila_botones.addStretch()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)
        btn_aceptar= QPushButton("Recortar y usar")
        btn_aceptar.setIcon(icono_emoji("✂"))
        btn_aceptar.setIconSize(_QSize_emoji(16, 16))
        btn_aceptar.clicked.connect(self._confirmar)
        fila_botones.addWidget(btn_aceptar)
        disposicion.addLayout(fila_botones)

        centrar_y_al_frente(self, parent)

    def _quitar_seleccion(self):

        self._rect_seleccion= QRect()
        self.rubber_band.hide()

    def eventFilter(self, objeto, evento):

        if objeto is self.lbl_imagen:
            if evento.type() == evento.Type.MouseButtonPress:
                self.origen_seleccion= evento.position().toPoint() if hasattr(evento, "position") else evento.pos()
                self.rubber_band.setGeometry(QRect(self.origen_seleccion, QSize()))
                self.rubber_band.show()
                return True
            elif evento.type() == evento.Type.MouseMove and self.rubber_band.isVisible():
                pos_actual= evento.position().toPoint() if hasattr(evento, "position") else evento.pos()
                self.rubber_band.setGeometry(QRect(self.origen_seleccion, pos_actual).normalized())
                return True
            elif evento.type() == evento.Type.MouseButtonRelease and self.rubber_band.isVisible():
                self._rect_seleccion= self.rubber_band.geometry()
                return True
        return super().eventFilter(objeto, evento)

    def _confirmar(self):

        if self._rect_seleccion.isValid() and self._rect_seleccion.width() > 10 and self._rect_seleccion.height() > 10:
            factor_x= self.imagen_original.width() / self.pixmap_mostrado.width()
            factor_y= self.imagen_original.height() / self.pixmap_mostrado.height()
            rect_real= QRect(
                int(self._rect_seleccion.x() * factor_x),
                int(self._rect_seleccion.y() * factor_y),
                int(self._rect_seleccion.width() * factor_x),
                int(self._rect_seleccion.height() * factor_y),
            )
            rect_real= rect_real.intersected(self.imagen_original.rect())
            if rect_real.isEmpty():
                mostrar_mensaje("advertencia", "Selección inválida", "Selecciona un área válida dentro de la imagen.", self)
                return
            self.imagen_recortada= self.imagen_original.copy(rect_real)
        else:
            self.imagen_recortada= self.imagen_original
        self.accept()


#Flujo completo: abre selector de archivo -> diálogo de recorte -> guarda en carpeta_destino.
#Devuelve la ruta del archivo guardado, o None si el usuario cancela.
def seleccionar_y_recortar_foto(parent, carpeta_destino, prefijo="foto"):

    ruta_origen, _= QFileDialog.getOpenFileName(
        parent, "Seleccionar Fotografía", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)")
    if not ruta_origen:
        return None

    try:

        dialogo= DialogoRecorteFoto(ruta_origen, parent)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return None

        os.makedirs(carpeta_destino, exist_ok=True)
        nombre_archivo= f"{prefijo}_{uuid.uuid4().hex[:10]}.png"
        destino= os.path.join(carpeta_destino, nombre_archivo)
        imagen_final= dialogo.imagen_recortada or QImage(ruta_origen)
        imagen_final.save(destino, "PNG")
        return destino
    except Exception as error:
        mostrar_mensaje("error", "Error", f"No se pudo procesar la fotografía:\n{error}", parent)
        return None
