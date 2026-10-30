#Módulo de Calificaciones Técnicas de AcaDeXI — exclusivo para Politécnicos.
#
#Este módulo solo aparece en la barra lateral cuando la institución es de tipo
#Politécnico (ver `main.py` / `permisos.py`). Evalúa los MÓDULOS TÉCNICOS —
#materias marcadas en Materias con `modelo_evaluacion = 'Técnica (RA)'` — con
#un motor de evaluación distinto al currículo académico por Competencias
#Específicas que ya usa el módulo Calificaciones: aquí cada módulo técnico se
#descompone en Resultados de Aprendizaje (RA), cada uno con un peso
#porcentual, y la Calificación Final (C.F.) del módulo es la suma ponderada
#de sus RA.
#
#Dos experiencias, según `configuracion.sistema_calificacion`:
#
#- República Dominicana (SISTEMA_DOMINICANO): implementa el modelo real de la
#Educación Técnico Profesional (ETP) del MINERD tal como lo describe el
#boletín de ejemplo que dio origen a este módulo — RA con peso% (deben
#sumar 100%), notas numéricas 0-100 con decimales, nota mínima 70,
#Boletín Técnico con la Calificación Final por módulo y la "Situación
#del/de la estudiante". Incluye además un seguimiento OPCIONAL, indicado
#por el propio centro y no verificado contra una ordenanza específica, de
#la instancia posterior a la recuperación pedagógica/completiva/
#extraordinaria (Ordenanza 04-2023) para un módulo técnico no aprobado:
#traslado a un liceo regular, o bien autorización para repetir el año
#dentro del mismo politécnico según la conducta del estudiante — nunca
#una consecuencia automática de una sola nota baja. Ver el aviso en
#pantalla en esa sección.
#
#- Cualquier otro sistema de calificación: un modelo simplificado pero
#pedagógicamente real, usado en buena parte de la formación técnica y
#vocacional a nivel internacional (por ejemplo Australia, España-FP,
#Costa Rica, y el propio INFOTEP dominicano fuera del circuito MINERD):
#Unidades de Competencia calificadas de forma cualitativa como
#"Competente" / "Aún No Competente", sin pesos porcentuales que
#configurar ni boletín con traslados — deliberadamente más simple.
#
#Todas las notas se calculan siempre en caliente a partir de
#`resultados_aprendizaje` + `calificacion_ra`: nunca se guarda una
#Calificación Final "congelada" que pueda desincronizarse si luego se
#corrige un RA.
import math
import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QScrollArea, QFrame, QDialog, QDialogButtonBox, QTextEdit, QSizePolicy, QFileDialog,
    QAbstractItemView)
from PySide6.QtCore import Qt, QRectF, QPointF, QEasingCurve, QVariantAnimation, QTimer
from PySide6.QtGui import (QColor, QPainter, QPen, QBrush, QFont, QLinearGradient,
    QConicalGradient, QRadialGradient, QPainterPath)

from src.nucleo.bd import obtener_conexion, registrar_auditoria, mostrar_columna_numero_lista
from src.interfaz.filtros_curso_seccion import poblar_combo_curso, cascada_seccion_por_curso
from src.nucleo.iconos import mostrar_mensaje, centrar_y_al_frente, aplicar_icono_cabecera, aplicar_icono_ventana, ICONO_FILTRO
from src.nucleo.permisos import (puede_editar, obtener_materias_permitidas, obtener_secciones_permitidas)
from src.interfaz.paginacion import (aplicar_estructura_tabla, tabla_pausada, ControlPaginacion, agregar_boton_detalle,
    mostrar_detalle_campos, agregar_boton_pantalla_completa)
from src.interfaz.configuracion import _hex_a_rgba, _fundido_entrada, _normalizar, TabWidgetNavegable,\
    anio_academico_actual, es_sistema_dominicano, conectar_tooltip_seleccion
from src.modulos.calificaciones import (_datos_institucion, _dibujar_encabezado, _dibujar_pie_pagina,
                             _envolver_texto, _recortar_a_ancho)
from src.modulos.materias import MODELO_EVALUACION_TECNICA
from src.nucleo.atajos import registrar_atajo
from src.nucleo.limite_campos import limitar_campo_texto
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, icono_boton_filtro, pixmap_boton_filtro,
                          EMOJI_MODULOS_RA, EMOJI_REGISTRO_NOTAS_TECNICAS, EMOJI_BOLETIN_TECNICO)

#CONSTANTES Deliberadamente NO usa nota_minima_primaria/nota_minima_secundaria: la Educación
#Técnico-Profesional (ETP) es post-secundaria y no se clasifica como Primaria/Secundaria (ver
#grados.nivel_educativo en bd.py y resolver_nota_minima en configuracion.py), así que sigue con su propia nota
#mínima fija, igual que antes de ese cambio.
NOTA_MINIMA_RD= 70.0

ACCION_EN_RECUPERACION= "En recuperación / completiva / extraordinaria"
ACCION_TRASLADO= "Trasladado a Liceo Regular (tras agotar la recuperación)"
ACCION_REPITE_POLITECNICO= "Continúa en el Politécnico (repite el año, autorizado)"
ACCIONES_NO_PROMOCION= ["", ACCION_EN_RECUPERACION, ACCION_TRASLADO, ACCION_REPITE_POLITECNICO]

RESULTADOS_COMPETENCIA_OPCIONES= [
    ("⏳ Pendiente", ""),
    ("Competente", "Competente"),
    ("Aún No Competente", "No Competente"),
]


def _qcolor_alpha(color, alpha):

    c= QColor(color)
    c.setAlpha(alpha)
    return c


#Color de apoyo visual para una Calificación Final (o promedio): NO es
#una banda oficial del MINERD (que solo define el mínimo de aprobación),
#es solo para que AcaDeXI se lea de un vistazo.
def _color_cf(valor, minimo=70.0):

    if valor is None:
        return "#6B7280"
    if valor >= 90:
        return "#10B981"
    if valor >= minimo:
        return "#3B82F6"
    return "#EF4444"


def _texto_nivel_cf(valor, minimo=70.0):

    if valor is None:
        return "Sin evaluar"
    if valor >= 90:
        return "Excelente"
    if valor >= minimo:
        return "Aprobado"
    return "No Aprobado"


def _sistema_calificacion_actual():

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT sistema_calificacion FROM configuracion WHERE id=1")
    cfg= c.fetchone()
    conn.close()
    return cfg["sistema_calificacion"] if cfg else "Numérico (Personalizado)"


#Widgets pintados a mano (QPainter) — elementos visuales originales de este módulo. Ninguno depende del tamaño
#de los datos para su costo de pintado (son formas geométricas fijas), así que no afectan el rendimiento aunque
#haya muchas filas en las tablas de al lado.

#Escribe (o actualiza) la fila de `calificacion_ra` para este
#estudiante+RA+año a partir de un ajuste hecho desde Observaciones.
#Sistema numérico (RD): `ajuste` son +/- puntos sobre la nota actual del
#RA (o sobre NOTA_MINIMA_RD si todavía no tenía nota). Sistema de
#dominio: `domina` ("Competente"/"No Competente") se guarda tal cual.
def guardar_ajuste_ra(main_window, estudiante_id, ra_id, anio, ajuste, domina, texto_obs):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT nota FROM calificacion_ra
                 WHERE estudiante_id=? AND resultado_aprendizaje_id=? AND anio_academico=?""",
              (estudiante_id, ra_id, anio))
    existente= c.fetchone()
    if ajuste is not None:
        base= existente["nota"] if (existente and existente["nota"] is not None) else NOTA_MINIMA_RD
        nueva_nota= max(0, min(100, base + ajuste))
        nuevo_domina= ""
        signo= "+" if ajuste >= 0 else ""
        detalle= f"Ajuste por observación ({signo}{ajuste} pts): {texto_obs[:80]}"
    else:
        nueva_nota= None
        nuevo_domina= domina or ""
        detalle= f"Ajuste por observación ({nuevo_domina or 'sin dominio'}): {texto_obs[:80]}"
    usuario= main_window.usuario_actual
    ahora= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO calificacion_ra
                 (estudiante_id, resultado_aprendizaje_id, anio_academico, nota, domina, observacion,
                  usuario, actualizado)
                 VALUES (?,?,?,?,?,?,?,?)
                 ON CONFLICT(estudiante_id, resultado_aprendizaje_id, anio_academico) DO UPDATE SET
                    nota= excluded.nota, domina=excluded.domina, observacion=excluded.observacion,
                    usuario= excluded.usuario, actualizado=excluded.actualizado""",
              (estudiante_id, ra_id, anio, nueva_nota, nuevo_domina, detalle, usuario, ahora))
    conn.commit()
    conn.close()
    registrar_auditoria("Calificaciones Técnicas", "Ajustó RA desde una observación", usuario,
                         f"Estudiante ID {estudiante_id} - RA ID {ra_id} - Año {anio}")


#Tarjeta de indicador con una insignia HEXAGONAL (motivo técnico/
#industrial, en vez del círculo genérico de otras pantallas) y el valor
#animado con un conteo incremental cada vez que se actualiza.
class TarjetaKPITecnica(QWidget):

    def __init__(self, icono, etiqueta, color, parent=None):

        super().__init__(parent)
        self._icono= icono
        self._etiqueta= etiqueta
        self._color= QColor(color)
        self._valor_mostrado= 0.0
        self._valor_objetivo= 0.0
        self._es_texto= False
        self._texto_valor= "—"
        self.setMinimumSize(160, 92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(650)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_animar)

    #v: valor actual de la animación; se guarda como valor mostrado y se repinta.
    def _al_animar(self, v):

        self._valor_mostrado= v
        self.update()

    def poner_valor(self, valor):

        self._es_texto= False
        self._valor_objetivo= float(valor or 0)
        self._anim.stop()
        self._anim.setStartValue(self._valor_mostrado)
        self._anim.setEndValue(self._valor_objetivo)
        self._anim.start()

    def poner_texto(self, texto):

        self._es_texto= True
        self._texto_valor= texto
        self.update()

    #cx, cy: centro del hexágono; r: su radio.
    def _hexagono(self, cx, cy, r):

        path= QPainterPath()
        for i in range(6):
            ang= math.radians(60 * i - 30)
            punto= QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang))
            if i == 0:
                path.moveTo(punto)
            else:
                path.lineTo(punto)
        path.closeSubpath()
        return path

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h= self.width(), self.height()

        fondo= QPainterPath()
        fondo.addRoundedRect(QRectF(0, 0, w, h), 14, 14)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(_qcolor_alpha(self._color, 22))
        pintor.drawPath(fondo)
        pintor.setPen(QPen(_qcolor_alpha(self._color, 110), 1.2))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawPath(fondo)

        #cx, cy: centro del hexágono; r: su radio.
        cx, cy, r= 34.0, h / 2, 21.0
        hexa= self._hexagono(cx, cy, r)
        grad= QLinearGradient(cx, cy - r, cx, cy + r)
        grad.setColorAt(0, self._color.lighter(125))
        grad.setColorAt(1, self._color)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QBrush(grad))
        pintor.drawPath(hexa)
        if self._icono:
            pix_hex= pixmap_emoji(self._icono, 22)
            if not pix_hex.isNull():
                pintor.drawPixmap(int(cx - 11), int(cy - 11), pix_hex)

        area= QRectF(66, 8, w - 78, h - 16)
        pintor.setPen(self._color)
        fuente_val= QFont()
        fuente_val.setBold(True)
        fuente_val.setPointSize(17)
        pintor.setFont(fuente_val)
        texto_val= self._texto_valor if self._es_texto else f"{self._valor_mostrado:,.0f}"
        pintor.drawText(QRectF(area.x(), area.y(), area.width(), area.height() * 0.58),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, texto_val)
        pintor.setPen(QColor(127, 127, 127))
        fuente_lbl= QFont()
        fuente_lbl.setPointSize(9)
        pintor.setFont(fuente_lbl)
        pintor.drawText(QRectF(area.x(), area.y() + area.height() * 0.55, area.width(), area.height() * 0.45),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                   self._etiqueta)
        pintor.end()


#Anillo circular animado (velocímetro de C.F.). A diferencia de un
#anillo de progreso genérico, dibuja una pequeña muesca en el ángulo
#exacto de la nota mínima de aprobación, así se ve de un vistazo si el
#valor quedó por encima o por debajo del corte.
class AnilloCF(QWidget):

    def __init__(self, etiqueta="", diametro=118, grosor=13, minimo=70.0, parent=None):

        super().__init__(parent)
        self._etiqueta= etiqueta
        self._diametro= diametro
        self._grosor= grosor
        self._minimo= minimo
        self._valor_mostrado= 0.0
        self._valor_objetivo= 0.0
        self._color= QColor("#6B7280")
        self._con_datos= False
        self.setFixedSize(diametro, diametro + 28)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(750)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_animar)

    def _al_animar(self, valor):

        self._valor_mostrado= valor
        self.update()

    def poner_valor(self, valor, color=None, con_datos=True):

        self._con_datos= con_datos
        self._valor_objetivo= max(0.0, min(100.0, valor or 0.0))
        self._color= QColor(color) if color else QColor("#6B7280")
        self._anim.stop()
        self._anim.setStartValue(self._valor_mostrado)
        self._anim.setEndValue(self._valor_objetivo)
        self._anim.start()

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        d= self._diametro
        margen= self._grosor / 2 + 3
        rect= QRectF(margen, margen, d - 2 * margen, d - 2 * margen)

        pluma_fondo= QPen(QColor(127, 127, 127, 45))
        pluma_fondo.setWidth(self._grosor)
        pluma_fondo.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(pluma_fondo)
        pintor.drawArc(rect, 0, 360 * 16)

        #Muesca de la nota mínima de aprobación, en el ángulo correspondiente (medido en sentido horario desde las 12,
        #igual que el arco de valor).
        theta_min= (self._minimo / 100.0) * 360.0
        pintor.save()
        pintor.translate(rect.center())
        pintor.rotate(theta_min)
        radio_ext= rect.width() / 2 + self._grosor / 2 + 5
        muesca= QPainterPath()
        muesca.moveTo(0, -radio_ext)
        muesca.lineTo(-4, -radio_ext + 9)
        muesca.lineTo(4, -radio_ext + 9)
        muesca.closeSubpath()
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(127, 127, 127, 140))
        pintor.drawPath(muesca)
        pintor.restore()

        if self._con_datos:
            pluma= QPen(self._color)
            pluma.setWidth(self._grosor)
            pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
            pintor.setPen(pluma)
            angulo_barrido= -(self._valor_mostrado / 100.0) * 360
            pintor.drawArc(rect, 90 * 16, int(angulo_barrido * 16))

            if self._valor_objetivo >= 90 and abs(self._valor_mostrado - self._valor_objetivo) < 0.5:
                punta_angulo= math.radians(90 + angulo_barrido)
                cx= rect.center().x() + (rect.width() / 2) * math.cos(punta_angulo)
                cy= rect.center().y() - (rect.width() / 2) * math.sin(punta_angulo)
                pintor.setPen(Qt.PenStyle.NoPen)
                pintor.setBrush(QColor(255, 255, 255, 90))
                pintor.drawEllipse(QPointF(cx, cy), self._grosor / 3, self._grosor / 3)

        pintor.setPen(self._color if self._con_datos else QColor(127, 127, 127))
        fuente= QFont()
        fuente.setBold(True)
        fuente.setPointSize(int(d / 6.2))
        pintor.setFont(fuente)
        texto_valor= f"{self._valor_mostrado:.1f}" if self._con_datos else "—"
        pintor.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto_valor)

        if self._etiqueta:
            pintor.setPen(QColor(127, 127, 127))
            fuente2= QFont()
            fuente2.setPointSize(9)
            pintor.setFont(fuente2)
            pintor.drawText(QRectF(0, d - 4, d, 26), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       self._etiqueta)
        pintor.end()


#Barra horizontal 'de ribete cosido': un segmento de color por cada RA,
#ancho proporcional a su peso%, separados por una fina costura blanca.
#Crece animada desde 0 al recibir datos. El marco cambia de verde a
#ámbar según si la suma de pesos ya cierra en 100%, para detectar de un
#vistazo si falta o sobra peso por asignar.
class BarraPesosRA(QWidget):

    PALETA= ["#6366F1", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981",
              "#3B82F6", "#14B8A6", "#F97316", "#A855F7", "#EF4444"]

    def __init__(self, parent=None, alto=32):

        super().__init__(parent)
        self._alto= alto
        self.setMinimumHeight(alto + 24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._segmentos= []
        self._progreso= 0.0
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(650)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_animar)

    #v: progreso actual de la animación (0 a 1); se guarda y se repinta.
    def _al_animar(self, v):

        self._progreso= v
        self.update()

    def poner_segmentos(self, segmentos):

        self._segmentos= list(segmentos)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self.update()

    def suma_pesos(self):

        #p: peso de cada segmento (el primer valor, el color, se ignora); se suman.
        return sum(p for _c, p in self._segmentos)

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        ancho= self.width()
        pos_y= 4
        alto= self._alto
        radio= alto / 2

        suma= self.suma_pesos()
        color_marco= QColor("#10B981") if abs(suma - 100) < 0.05 else QColor("#F59E0B")

        fondo= QPainterPath()
        fondo.addRoundedRect(QRectF(0.8, pos_y, ancho - 1.6, alto), radio, radio)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(127, 127, 127, 35))
        pintor.drawPath(fondo)

        if self._segmentos and suma > 0:
            pintor.save()
            clip= QPainterPath()
            clip.addRoundedRect(QRectF(0.8, pos_y, ancho - 1.6, alto), radio, radio)
            pintor.setClipPath(clip)
            x= 0.0
            escala= min(1.0, 100.0 / suma) if suma > 100 else 1.0
            for i, (_codigo, peso) in enumerate(self._segmentos):
                w_px= (peso / 100.0) * escala * self._progreso * ancho
                color= QColor(self.PALETA[i % len(self.PALETA)])
                grad= QLinearGradient(x, 0, x + max(w_px, 1), 0)
                grad.setColorAt(0, color.lighter(112))
                grad.setColorAt(1, color)
                pintor.setPen(Qt.PenStyle.NoPen)
                pintor.setBrush(QBrush(grad))
                pintor.drawRect(QRectF(x, pos_y, w_px, alto))
                if i > 0:
                    pluma_costura= QPen(QColor(255, 255, 255, 130), 1.4)
                    pintor.setPen(pluma_costura)
                    pintor.drawLine(QPointF(x, pos_y + 3), QPointF(x, pos_y + alto - 3))
                x += w_px
            pintor.restore()

        marco= QPen(color_marco, 1.6)
        pintor.setPen(marco)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawPath(fondo)

        pintor.setPen(QColor(127, 127, 127))
        fuente= QFont()
        fuente.setPointSize(9)
        pintor.setFont(fuente)
        if abs(suma - 100) < 0.05:
            texto= f"Σ pesos = {suma:.1f}%  ✅ Suma correcta"
        elif suma < 100:
            texto= f"Σ pesos = {suma:.1f}% ⚠ Faltan {100 - suma:.1f} puntos porcentuales"
        else:
            texto= f"Σ pesos = {suma:.1f}% ⚠ Sobran {suma - 100:.1f} puntos porcentuales"
        pintor.drawText(QRectF(2, pos_y + alto + 3, ancho - 4, 18), Qt.AlignmentFlag.AlignLeft, texto)
        pintor.end()


#Pastilla de estado pintada a mano (check / X / reloj de arena dibujados
#con QPainterPath, no emoji del sistema) para el modo internacional
#simplificado. Hace un pequeño 'pop' elástico cuando el estado cambia.
class ChipEstadoCompetencia(QWidget):

    ESTADOS= {
        "": ("#9CA3AF", "Pendiente"),
        "Competente": ("#10B981", "Competente"),
        "No Competente": ("#EF4444", "Aún No Competente"),
    }

    def __init__(self, parent=None):

        super().__init__(parent)
        self._estado= ""
        self._escala= 1.0
        self.setFixedSize(158, 30)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._al_animar)

    #v: escala actual de la animación; se guarda y se repinta.
    def _al_animar(self, v):

        self._escala= v
        self.update()

    def estado(self):

        return self._estado

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        color_hex, texto= self.ESTADOS.get(self._estado, self.ESTADOS[""])
        color= QColor(color_hex)

        pintor.translate(self.width() / 2, self.height() / 2)
        pintor.scale(self._escala, self._escala)
        pintor.translate(-self.width() / 2, -self.height() / 2)

        fondo= QPainterPath()
        fondo.addRoundedRect(QRectF(0, 2, self.width(), self.height() - 4), 13, 13)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(_qcolor_alpha(color, 40))
        pintor.drawPath(fondo)
        pintor.setPen(QPen(color, 1.3))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawPath(fondo)

        #cx, cy: centro del círculo indicador; r: su radio.
        cx, cy, r= 16.0, self.height() / 2, 6.0
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(color)
        pintor.drawEllipse(QPointF(cx, cy), r, r)

        pen_icono= QPen(QColor("white"), 1.6)
        pen_icono.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_icono.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pintor.setPen(pen_icono)
        icono= QPainterPath()
        if self._estado == "Competente":
            icono.moveTo(cx - 3, cy)
            icono.lineTo(cx - 1, cy + 2.6)
            icono.lineTo(cx + 3.4, cy - 3)
        elif self._estado == "No Competente":
            icono.moveTo(cx - 2.6, cy - 2.6)
            icono.lineTo(cx + 2.6, cy + 2.6)
            icono.moveTo(cx + 2.6, cy - 2.6)
            icono.lineTo(cx - 2.6, cy + 2.6)
        else:
            icono.moveTo(cx - 2.6, cy - 3)
            icono.lineTo(cx + 2.6, cy - 3)
            icono.lineTo(cx - 1.4, cy)
            icono.lineTo(cx + 2.6, cy + 3)
            icono.lineTo(cx - 2.6, cy + 3)
            icono.lineTo(cx + 1.4, cy)
            icono.closeSubpath()
        pintor.drawPath(icono)

        pintor.setPen(color)
        fuente= QFont()
        fuente.setPointSize(9)
        fuente.setBold(True)
        pintor.setFont(fuente)
        pintor.drawText(QRectF(28, 0, self.width() - 32, self.height()), Qt.AlignmentFlag.AlignVCenter, texto)
        pintor.end()


#El elemento más vistoso del Boletín Técnico: una medalla circular con
#bisel (degradado radial) y un arco cónico interior que se llena según la
#Calificación Final promedio, con marcas cada 10% como un reloj, y la
#etiqueta de nivel debajo del número grande.
class MedallonBoletin(QWidget):

    def __init__(self, diametro=172, minimo=70.0, parent=None):

        super().__init__(parent)
        self._d= diametro
        self._minimo= minimo
        self._valor_mostrado= 0.0
        self._valor_objetivo= 0.0
        self._color= QColor("#6B7280")
        self._nivel= "Sin evaluar"
        self.setFixedSize(diametro, diametro + 36)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(950)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_animar)

    #v: valor actual de la animación; se guarda como valor mostrado y se repinta.
    def _al_animar(self, v):

        self._valor_mostrado= v
        self.update()

    def poner_valor(self, valor, color, nivel):

        self._color= QColor(color)
        self._nivel= nivel
        self._valor_objetivo= max(0.0, min(100.0, valor or 0.0))
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(self._valor_objetivo)
        self._anim.start()

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        d= self._d
        rect= QRectF(6, 6, d - 12, d - 12)

        bisel= QRadialGradient(rect.center(), rect.width() / 2)
        bisel.setColorAt(0.78, QColor(0, 0, 0, 0))
        bisel.setColorAt(0.90, _qcolor_alpha(self._color, 65))
        bisel.setColorAt(1.0, _qcolor_alpha(self._color, 15))
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QBrush(bisel))
        pintor.drawEllipse(rect)

        grosor= 15
        interior= rect.adjusted(grosor, grosor, -grosor, -grosor)

        pluma_fondo= QPen(QColor(127, 127, 127, 40))
        pluma_fondo.setWidth(grosor)
        pintor.setPen(pluma_fondo)
        pintor.drawArc(interior, 0, 360 * 16)

        pintor.save()
        pintor.translate(interior.center())
        r1= interior.width() / 2 + grosor / 2 + 2
        r2= r1 + 5
        for i in range(10):
            pintor.save()
            pintor.rotate(i * 36)
            pintor.setPen(QPen(QColor(127, 127, 127, 100), 1.2))
            pintor.drawLine(QPointF(0, -r1), QPointF(0, -r2))
            pintor.restore()
        pintor.restore()

        conica= QConicalGradient(interior.center(), 90)
        conica.setColorAt(0.0, self._color.lighter(130))
        conica.setColorAt(1.0, self._color)
        pluma= QPen(QBrush(conica), grosor)
        pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(pluma)
        pintor.drawArc(interior, 90 * 16, int(-(self._valor_mostrado / 100.0) * 360 * 16))

        pintor.setPen(self._color)
        fuente= QFont()
        fuente.setBold(True)
        fuente.setPointSize(int(d / 5.4))
        pintor.setFont(fuente)
        pintor.drawText(interior, Qt.AlignmentFlag.AlignCenter, f"{self._valor_mostrado:.1f}")

        pintor.setPen(QColor(127, 127, 127))
        fuente2= QFont()
        fuente2.setPointSize(10)
        fuente2.setBold(True)
        pintor.setFont(fuente2)
        pintor.drawText(QRectF(0, d - 2, d, 24), Qt.AlignmentFlag.AlignHCenter, self._nivel)
        pintor.end()


#Dona de tres arcos (Aprobados / No Aprobados / Pendientes) para el
#resumen del grupo en Registro de Notas, con leyenda pintada a mano.
class DonutResumenGrupo(QWidget):

    def __init__(self, diametro=108, grosor=14, parent=None):

        super().__init__(parent)
        self._d= diametro
        self._grosor= grosor
        self._valores= {"ok": 0, "no": 0, "pendiente": 0}
        self._progreso= 0.0
        self.setFixedSize(diametro + 92, diametro)
        self._anim= QVariantAnimation(self)
        self._anim.setDuration(750)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._al_animar)

    #v: progreso actual de la animación; se guarda y se repinta.
    def _al_animar(self, v):

        self._progreso= v
        self.update()

    def poner_valores(self, ok, no, pendiente):

        self._valores= {"ok": ok, "no": no, "pendiente": pendiente}
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, evento):

        pintor= QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        d= self._d
        rect= QRectF(self._grosor / 2 + 2, self._grosor / 2 + 2, d - self._grosor - 4, d - self._grosor - 4)
        total= sum(self._valores.values())

        pluma_fondo= QPen(QColor(127, 127, 127, 40))
        pluma_fondo.setWidth(self._grosor)
        pintor.setPen(pluma_fondo)
        pintor.drawArc(rect, 0, 360 * 16)

        if total > 0:
            colores= {"ok": QColor("#10B981"), "no": QColor("#EF4444"), "pendiente": QColor("#9CA3AF")}
            inicio= 90 * 16
            for clave in ("ok", "no", "pendiente"):
                frac= self._valores[clave] / total
                if frac <= 0:
                    continue
                barrido= -frac * 360 * 16 * self._progreso
                pluma= QPen(colores[clave])
                pluma.setWidth(self._grosor)
                pluma.setCapStyle(Qt.PenCapStyle.FlatCap)
                pintor.setPen(pluma)
                pintor.drawArc(rect, int(inicio), int(barrido))
                inicio += barrido

        pintor.setPen(QColor(127, 127, 127) if total == 0 else QColor("#111827"))
        fuente= QFont()
        fuente.setBold(True)
        fuente.setPointSize(15)
        pintor.setFont(fuente)
        pintor.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self._valores['ok']}/{total}" if total else "—")

        fuente_leyenda= QFont()
        fuente_leyenda.setPointSize(8)
        pintor.setFont(fuente_leyenda)
        x0= d + 8
        leyenda= [("#10B981", "Aprobado"), ("#EF4444", "No aprobado"), ("#9CA3AF", "Pendiente")]
        y0= (d - len(leyenda) * 18) / 2
        for i, (color, texto) in enumerate(leyenda):
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(QColor(color))
            pintor.drawEllipse(QPointF(x0 + 4, y0 + i * 18 + 7), 4, 4)
            pintor.setPen(QColor(127, 127, 127))
            pintor.drawText(QRectF(x0 + 12, y0 + i * 18, self.width() - x0 - 14, 16),
                       Qt.AlignmentFlag.AlignVCenter, texto)
        pintor.end()


#DIÁLOGO: alta/edición de un RA (o Unidad de Competencia)
#Icono de lupa dibujado a mano (mismo diseño que el resto de AcaDeXI:
#horario.py / estudiantes.py) para las barras de búsqueda de este módulo.
class IconoLupaCT(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setFixedSize(17, 17)
        self._color= "#64748B"

    def establecer_color(self, color):

        self._color= color
        self.update()

    def paintEvent(self, evento):

        painter= QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen= QPen(QColor(self._color), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(1.5, 1.5, 9.5, 9.5))
        painter.drawLine(QPointF(9.7, 9.7), QPointF(15, 15))


class DialogoRA(QDialog):

    def __init__(self, parent, modo_simplificado, datos_actuales=None, codigo_sugerido=""):

        super().__init__(parent)
        self.modo_simplificado= modo_simplificado
        titulo_tipo= "Unidad de Competencia" if modo_simplificado else "Resultado de Aprendizaje (RA)"
        self.setWindowTitle(f"{'Editar' if datos_actuales else 'Nuevo'} {titulo_tipo}")
        self.setMinimumWidth(460)

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(22, 20, 22, 20)
        disposicion.setSpacing(12)

        lbl_encabezado= QLabel(f"{'' if datos_actuales else ''} {titulo_tipo}")
        fuente= lbl_encabezado.font()
        fuente.setBold(True)
        fuente.setPointSize(13)
        lbl_encabezado.setFont(fuente)
        disposicion.addWidget(lbl_encabezado)

        grid= QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("Unidad:" if modo_simplificado else "RA:"), 0, 0)
        self.in_codigo= QLineEdit(codigo_sugerido)
        limitar_campo_texto(self.in_codigo, 300)
        self.in_codigo.setPlaceholderText("U1" if modo_simplificado else "RA1")
        grid.addWidget(self.in_codigo, 0, 1)

        grid.addWidget(QLabel("Descripción:"), 1, 0)
        self.in_descripcion= QTextEdit()
        limitar_campo_texto(self.in_descripcion, 5000)
        self.in_descripcion.setPlaceholderText(
            "Ej.: Maneja el procesador de texto para crear documentos con formato profesional."
            if modo_simplificado else
            "Ej.: Elabora documentos ofimáticos aplicando formato, estilos y tablas avanzadas.")
        self.in_descripcion.setFixedHeight(80)
        grid.addWidget(self.in_descripcion, 1, 1)

        self.spin_peso= None
        if not modo_simplificado:
            grid.addWidget(QLabel("Peso (%):"), 2, 0)
            self.spin_peso= QDoubleSpinBox()
            self.spin_peso.setRange(0, 100)
            self.spin_peso.setDecimals(1)
            self.spin_peso.setSingleStep(5)
            self.spin_peso.setSuffix(" %")
            self.spin_peso.setToolTip(
                "Peso de este RA dentro de la Calificación Final (C.F.) del módulo. La suma de los "
                "pesos de TODOS los RA del módulo debería totalizar 100% (la pestaña anterior lo "
                "muestra con una barra de colores).")
            grid.addWidget(self.spin_peso, 2, 1)
        else:
            lbl_nota_info= QLabel(
                "ℹ En el modo simplificado cada unidad se evalúa como Competente / Aún No Competente,"
                "sin porcentajes que configurar: no hace falta asignar un peso.")
            lbl_nota_info.setWordWrap(True)
            lbl_nota_info.setStyleSheet("color: #6B7280; font-size: 11px;")
            grid.addWidget(lbl_nota_info, 2, 0, 1, 2)

        disposicion.addLayout(grid)

        if datos_actuales:
            self.in_codigo.setText(datos_actuales.get("codigo", ""))
            self.in_descripcion.setPlainText(datos_actuales.get("descripcion", ""))
            if self.spin_peso is not None:
                self.spin_peso.setValue(float(datos_actuales.get("peso") or 0))

        botones= QHBoxLayout()
        btn_cancelar= QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.setObjectName("BtnAccionNeutro")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar= QPushButton("Guardar")
        btn_guardar.setIcon(icono_emoji("💾"))
        btn_guardar.setIconSize(_QSize_emoji(16, 16))
        btn_guardar.setObjectName("BtnAccionAgregar")
        btn_guardar.clicked.connect(self._validar_y_aceptar)
        botones.addStretch()
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        disposicion.addLayout(botones)

        centrar_y_al_frente(self, parent)

    def _validar_y_aceptar(self):

        if not self.in_codigo.text().strip():
            mostrar_mensaje("advertencia", "Falta el código", "Escribe un código corto (ej. RA1, U1).", self)
            return
        if not self.in_descripcion.toPlainText().strip():
            mostrar_mensaje("advertencia", "Falta la descripción", "Describe brevemente qué evalúa.", self)
            return
        self.accept()

    def valores(self):

        return {
            "codigo": self.in_codigo.text().strip(),
            "descripcion": self.in_descripcion.toPlainText().strip(),
            "peso": self.spin_peso.value() if self.spin_peso is not None else 0.0,
        }


#Ajuste de RA desde observaciones (ver observaciones.py)  Equivalente técnico de DialogoAjusteCompetencia
#(observaciones.py): deja sumar/restar puntos -o marcar Competente/No Competente, según el sistema de
#calificación activo- en el Resultado de Aprendizaje que el docente elija, a raíz de una observación. No es
#automático: el docente escoge el módulo técnico, el RA y el año académico. Por debajo escribe la MISMA fila de
#`calificacion_ra` que usa el Registro de Notas normal (nunca un número suelto sin trazabilidad), dejando un
#rastro en su campo `observacion`.
class DialogoAjusteRA(QDialog):

    def __init__(self, main_window, estudiante_id, texto_observacion, naturaleza, parent=None,
                 materia_id_sugerida= None):

        super().__init__(parent)
        self.main_window= main_window
        self.estudiante_id= estudiante_id
        self._dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        self.setWindowTitle("Ajustar Resultado de Aprendizaje por Observación")
        self.setMinimumWidth(460)

        disposicion= QVBoxLayout(self)
        lbl_info= QLabel("Esto guarda (o actualiza) la nota de este estudiante en el Resultado de Aprendizaje "
                       "que elijas, dentro del Registro de Notas técnico normal — no reemplaza la evaluación "
                       "del módulo, solo la complementa.")
        lbl_info.setWordWrap(True)
        disposicion.addWidget(lbl_info)

        lbl_cita= QLabel(f"“{texto_observacion[:140]}{'…' if len(texto_observacion) > 140 else ''}”")
        lbl_cita.setWordWrap(True)
        lbl_cita.setStyleSheet("font-style: italic; color: #6B7280;")
        disposicion.addWidget(lbl_cita)

        form= QGridLayout()
        self.combo_materia= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia, "Módulo técnico")
        self.combo_materia.currentIndexChanged.connect(self._cargar_ra)
        form.addWidget(QLabel("Módulo:"), 0, 0)
        form.addWidget(self.combo_materia, 0, 1)

        self.combo_ra= QComboBox()
        conectar_tooltip_seleccion(self.combo_ra, "Resultado de Aprendizaje evaluado")
        form.addWidget(QLabel("RA:" if self._dominicano else "Unidad:"), 1, 0)
        form.addWidget(self.combo_ra, 1, 1)

        self.in_anio= QLineEdit(anio_academico_actual())
        limitar_campo_texto(self.in_anio, 300)
        conectar_tooltip_seleccion(self.in_anio, "Año académico")
        form.addWidget(QLabel("Año académico:"), 2, 0)
        form.addWidget(self.in_anio, 2, 1)

        if self._dominicano:
            self.spin_ajuste= QSpinBox()
            self.spin_ajuste.setRange(-20, 20)
            self.spin_ajuste.setSuffix(" pts")
            self.spin_ajuste.setValue(5 if naturaleza == "Positiva" else (-5 if naturaleza == "Negativa" else 0))
            form.addWidget(QLabel("Ajuste (+/-):"), 3, 0)
            form.addWidget(self.spin_ajuste, 3, 1)
            self.combo_domina= None
        else:
            self.combo_domina= QComboBox()
            self.combo_domina.addItem("— Elegir —", "")
            self.combo_domina.addItem("Competente", "Competente")
            self.combo_domina.addItem("No Competente", "No Competente")
            if naturaleza == "Positiva":
                self.combo_domina.setCurrentIndex(1)
            elif naturaleza == "Negativa":
                self.combo_domina.setCurrentIndex(2)
            conectar_tooltip_seleccion(self.combo_domina, "Dominio del Resultado de Aprendizaje")
            form.addWidget(QLabel("Dominio:"), 3, 0)
            form.addWidget(self.combo_domina, 3, 1)
            self.spin_ajuste= None
        disposicion.addLayout(form)

        self._cargar_materias_tecnicas(materia_id_sugerida)
        self.aviso= QLabel("No hay módulos técnicos disponibles para tu usuario"
                             "(Materias ▸ Modelo: Módulo Técnico RA).")
        self.aviso.setWordWrap(True)
        self.aviso.setVisible(self.combo_materia.count() == 0)
        disposicion.addWidget(self.aviso)

        botones= QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        disposicion.addWidget(botones)
        self._cargar_ra()
        centrar_y_al_frente(self, parent)

    def _cargar_materias_tecnicas(self, materia_id_sugerida):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, nombre FROM materias WHERE modelo_evaluacion=? AND estado='Activa'
                     ORDER BY nombre""", (MODELO_EVALUACION_TECNICA,))
        filas= [dict(fila) for fila in c.fetchall()]
        conn.close()
        permitidas= obtener_materias_permitidas(self.main_window)
        if permitidas is not None:
            filas= [fila for fila in filas if fila["id"] in permitidas]
        for fila in filas:
            self.combo_materia.addItem(fila["nombre"], fila["id"])
        if materia_id_sugerida is not None:
            idx= self.combo_materia.findData(materia_id_sugerida)
            if idx >= 0:
                self.combo_materia.setCurrentIndex(idx)

    def _cargar_ra(self):

        self.combo_ra.clear()
        materia_id= self.combo_materia.currentData()
        if materia_id is None:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, codigo, descripcion FROM resultados_aprendizaje
                     WHERE materia_id=? AND estado='Activo' ORDER BY orden""", (materia_id,))
        for fila in c.fetchall():
            self.combo_ra.addItem(f"{fila['codigo']} — {fila['descripcion']}", fila["id"])
        conn.close()

    def datos(self):

        return {
            "materia_id": self.combo_materia.currentData(),
            "ra_id": self.combo_ra.currentData(),
            "anio": self.in_anio.text().strip() or anio_academico_actual(),
            "ajuste": self.spin_ajuste.value() if self.spin_ajuste is not None else None,
            "domina": self.combo_domina.currentData() if self.combo_domina is not None else None,
        }


#Módulo principal
class ModuloCalificacionesTecnicas(QWidget):

    def __init__(self, main_window):

        super().__init__(main_window)
        self.main_window= main_window
        self._dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        self._nota_minima= NOTA_MINIMA_RD if self._dominicano else 70.0
        self._ra_actual_editor= []
        self._ra_actual_registro= []
        self._estudiantes_grid_todos= []
        self._notas_cache= {}
        self._num_columnas_notas= 0
        self._widgets_notas= {}
        self._labels_cf= {}
        self._cargando_grid= False
        self._tarjetas_modulo_boletin= []
        self._ultimo_boletin= None
        self._tabs_cargados= set()
        self._construir_ui()
        self.refrescar()
        self.actualizar_tema()
        self._registrar_atajos_teclado()

    def _registrar_atajos_teclado(self):

        self._titulo_modulo_atajos= "Calificaciones Técnicas"
        registrar_atajo(self, self.main_window, "Ctrl+G", "Guardar notas técnicas", self._guardar_notas_grid)
        registrar_atajo(self, self.main_window, "Ctrl+B", "Generar boletín técnico", self._generar_boletin)
        registrar_atajo(self, self.main_window, "Ctrl+P", "Exportar boletín a PDF",
                         self._exportar_pdf_boletin)

    #Construcción de interfaz
    def _construir_ui(self):

        layout_raiz= QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        scroll= QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        contenido= QWidget()
        disposicion= QVBoxLayout(contenido)
        disposicion.setContentsMargins(30, 25, 30, 25)
        disposicion.setSpacing(14)

        self.frame_cabecera= QFrame()
        self.frame_cabecera.setObjectName("TarjetaCabeceraCT")
        cab= QHBoxLayout(self.frame_cabecera)
        cab.setContentsMargins(22, 18, 22, 18)
        cab.setSpacing(14)
        lbl_icono= QLabel()
        lbl_icono.setPixmap(pixmap_emoji("📊", 20))
        lbl_icono.setObjectName("IconoCabeceraCT")
        lbl_icono.setFixedSize(46, 46)
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aplicar_icono_cabecera(lbl_icono, "Calificaciones Técnicas")
        cab.addWidget(lbl_icono)
        bloque_titulo= QVBoxLayout()
        bloque_titulo.setSpacing(2)
        lbl_titulo= QLabel("Calificaciones Técnicas")
        lbl_titulo.setObjectName("TituloCabeceraCT")
        self.lbl_subtitulo_cabecera= QLabel("")
        self.lbl_subtitulo_cabecera.setObjectName("SubtituloCabeceraCT")
        self.lbl_subtitulo_cabecera.setWordWrap(True)
        bloque_titulo.addWidget(lbl_titulo)
        bloque_titulo.addWidget(self.lbl_subtitulo_cabecera)
        cab.addLayout(bloque_titulo, 1)
        disposicion.addWidget(self.frame_cabecera)

        fila_kpi= QHBoxLayout()
        fila_kpi.setSpacing(12)
        self.kpi_modulos= TarjetaKPITecnica("🧰", "Módulos Técnicos activos", "#6366F1")
        self.kpi_ra= TarjetaKPITecnica("🎯", "RA / Unidades definidos", "#8B5CF6")
        self.kpi_pesos= TarjetaKPITecnica("⚖", "Módulos con pesos al 100%", "#F59E0B")
        self.kpi_notas= TarjetaKPITecnica("\uE035", "Notas registradas (año actual)", "#10B981")
        for kpi in (self.kpi_modulos, self.kpi_ra, self.kpi_pesos, self.kpi_notas):
            fila_kpi.addWidget(kpi)
        disposicion.addLayout(fila_kpi)

        self.tabs= TabWidgetNavegable()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        disposicion.addWidget(self.tabs)
        self.tabs.addTab(self._tab_ra(), "Módulos y RA")
        self.tabs.addTab(self._tab_registro(), "Registro de Notas")
        self.tabs.addTab(self._tab_boletin(), "Boletín Técnico")
        self.tabs.setTabIcon(0, icono_emoji(EMOJI_MODULOS_RA))
        self.tabs.setTabIcon(1, icono_emoji(EMOJI_REGISTRO_NOTAS_TECNICAS))
        self.tabs.setTabIcon(2, icono_emoji(EMOJI_BOLETIN_TECNICO))
        self.tabs.currentChanged.connect(self._al_cambiar_pestana)

        scroll.setWidget(contenido)
        layout_raiz.addWidget(scroll, 1)

        for boton in self.findChildren(QPushButton):
            boton.setCursor(Qt.CursorShape.PointingHandCursor)

    def _al_cambiar_pestana(self, idx):

        _fundido_entrada(self.tabs.widget(idx), 200)
        if idx in self._tabs_cargados:
            return
        self._tabs_cargados.add(idx)
        if idx == 0:
            self._cargar_materias_tecnicas_combo(self.combo_materia_ra)
            self._cargar_ra_de_materia()
        elif idx == 1:
            self._cargar_grados_registro()
            self._cargar_materias_tecnicas_combo(self.combo_materia_registro)
            self._cargar_secciones_de_materia()
        elif idx == 2:
            self._cargar_grados_boletin()
            self._cargar_secciones_filtro_boletin()
            self._cargar_especialidad_carrera_filtro_boletin()

    def _tarjeta_formulario(self, titulo_seccion=None):

        frame= QFrame()
        frame.setObjectName("TarjetaFormularioCT")
        contenedor= QVBoxLayout(frame)
        contenedor.setContentsMargins(18, 16, 18, 16)
        contenedor.setSpacing(10)
        if titulo_seccion:
            lbl= QLabel(titulo_seccion)
            fuente= lbl.font()
            fuente.setBold(True)
            fuente.setPointSize(11)
            lbl.setFont(fuente)
            lbl.setStyleSheet("background: transparent;")
            contenedor.addWidget(lbl)
        grid= QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        contenedor.addLayout(grid)
        return frame, grid

    def _tarjeta_resultados(self):

        frame= QFrame()
        frame.setObjectName("TarjetaFormularioCT")
        contenedor= QVBoxLayout(frame)
        contenedor.setContentsMargins(16, 14, 16, 14)
        contenedor.setSpacing(10)
        return frame, contenedor

    #Caja de búsqueda redondeada con lupa pintada a mano (mismo diseño
    #que Estudiantes/Horario/Profesores) para filtrar una tabla.
    def _crear_barra_busqueda(self, placeholder):

        marco= QFrame()
        marco.setObjectName("MarcoBusquedaCT")
        lay= QHBoxLayout(marco)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(6)
        icono= IconoLupaCT()
        lay.addWidget(icono)
        in_buscar= QLineEdit()
        limitar_campo_texto(in_buscar, 150)
        in_buscar.setPlaceholderText(placeholder)
        in_buscar.setObjectName("CampoBusquedaCT")
        lay.addWidget(in_buscar, 1)
        return marco, in_buscar, icono

    #TAB 1 — Módulos y Resultados de Aprendizaje
    def _tab_ra(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)

        frame_form, form= self._tarjeta_formulario("Selecciona el Módulo Técnico")
        self.combo_materia_ra= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia_ra,
            "Solo aparecen materias marcadas como 'Módulo Técnico (RA)' en Materias Datos de la "
            "Materia Modelo de evaluación.")
        self.combo_materia_ra.currentIndexChanged.connect(self._cargar_ra_de_materia)
        form.addWidget(QLabel("Módulo técnico:"), 0, 0)
        form.addWidget(self.combo_materia_ra, 0, 1, 1, 3)
        disposicion.addWidget(frame_form)

        self.barra_pesos= BarraPesosRA()
        disposicion.addWidget(self.barra_pesos)

        marco_busqueda, self.in_buscar_ra, self._icono_busqueda_ra=\
            self._crear_barra_busqueda("Buscar por código o descripción…")
        self._temporizador_busqueda_ra= QTimer(self)
        self._temporizador_busqueda_ra.setSingleShot(True)
        self._temporizador_busqueda_ra.setInterval(150)
        self._temporizador_busqueda_ra.timeout.connect(self._filtrar_ra)
        #_t: texto escrito (no se usa); cada cambio reinicia el temporizador que filtra la tabla.
        self.in_buscar_ra.textChanged.connect(lambda _t: self._temporizador_busqueda_ra.start())
        disposicion.addWidget(marco_busqueda)

        frame_res, lr= self._tarjeta_resultados()
        self.tabla_ra= QTableWidget(0, 3)
        aplicar_estructura_tabla(self.tabla_ra)

        self.tabla_ra.setHorizontalHeaderLabels(["RA" if self._dominicano else "Unidad", "Descripción", "Peso %"])
        self.tabla_ra.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_ra.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_ra.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_ra.verticalHeader().setVisible(False)
        self.tabla_ra.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_ra.setAlternatingRowColors(True)

        botones= QHBoxLayout()
        btn_agregar= QPushButton("Agregar")
        btn_agregar.setIcon(icono_emoji("➕"))
        btn_agregar.setIconSize(_QSize_emoji(16, 16))
        btn_agregar.setObjectName("BtnAccionAgregar")
        btn_agregar.clicked.connect(self._abrir_dialogo_ra_nuevo)
        btn_editar= QPushButton("Editar seleccionado")
        btn_editar.setIcon(icono_emoji("✏"))
        btn_editar.setIconSize(_QSize_emoji(16, 16))
        btn_editar.setObjectName("BtnAccionAjustar")
        btn_editar.clicked.connect(self._abrir_dialogo_ra_editar)
        btn_eliminar= QPushButton("Eliminar seleccionado")
        btn_eliminar.setIcon(icono_emoji("🗑"))
        btn_eliminar.setIconSize(_QSize_emoji(16, 16))
        btn_eliminar.setObjectName("BtnAccionEliminar")
        btn_eliminar.clicked.connect(self._eliminar_ra_seleccionado)
        botones.addWidget(btn_agregar)
        botones.addWidget(btn_editar)
        botones.addWidget(btn_eliminar)
        botones.addStretch()
        btn_detalle_ra= agregar_boton_detalle(botones, self.tabla_ra, self, titulo="Detalle del RA",
                               texto_boton= "Ver Detalle")
        #*_: argumentos de la señal (no se usan); doble clic equivale a pulsar 'Ver Detalle'.
        self.tabla_ra.doubleClicked.connect(lambda *_: btn_detalle_ra.click())
        lr.addLayout(botones)

        self.lbl_vacio_ra= QLabel("Ningún RA/unidad coincide con la búsqueda.")
        self.lbl_vacio_ra.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio_ra.setStyleSheet("color: #9CA3AF; padding: 10px;")
        self.lbl_vacio_ra.setVisible(False)
        lr.addWidget(self.lbl_vacio_ra)

        fila_cabecera_tabla_ra= QHBoxLayout()
        fila_cabecera_tabla_ra.addStretch()
        lr.addLayout(fila_cabecera_tabla_ra)
        lr.addWidget(self.tabla_ra, 1)
        self.paginacion_ra= ControlPaginacion(tamanos=[("5 por página", 5), ("10 por página", 10),
                                                         ("25 por página", 25)], tamano_inicial=5)
        self.paginacion_ra.cambio.connect(self._filtrar_ra)
        lr.addWidget(self.paginacion_ra)
        agregar_boton_pantalla_completa(
            fila_cabecera_tabla_ra, [self.tabla_ra, self.paginacion_ra],
            titulo= "RA / Unidades", parent=self)
        disposicion.addWidget(frame_res)
        disposicion.addStretch()
        return contenedor

    def _materias_tecnicas_permitidas(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT id, nombre, codigo FROM materias
                     WHERE modelo_evaluacion=? AND estado='Activa' ORDER BY nombre""",
                  (MODELO_EVALUACION_TECNICA,))
        filas= [dict(fila) for fila in c.fetchall()]
        conn.close()
        permitidas= obtener_materias_permitidas(self.main_window)
        if permitidas is not None:
            filas= [fila for fila in filas if fila["id"] in permitidas]
        return filas

    def _cargar_materias_tecnicas_combo(self, combo):

        seleccion_previa= combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        materias= self._materias_tecnicas_permitidas()
        if not materias:
            combo.addItem("— No hay módulos técnicos: créalos en Materias (Modelo: Módulo Técnico RA) —", None)
        else:
            for materia in materias:
                etiqueta= f"{materia['codigo']} — {materia['nombre']}" if materia["codigo"] else materia["nombre"]
                combo.addItem(etiqueta, materia["id"])
            idx= combo.findData(seleccion_previa)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        return materias

    def _cargar_ra_de_materia(self):

        materia_id= self.combo_materia_ra.currentData()
        self._ra_actual_editor= []
        if hasattr(self, "in_buscar_ra"):
            self.in_buscar_ra.blockSignals(True)
            self.in_buscar_ra.clear()
            self.in_buscar_ra.blockSignals(False)
        if hasattr(self, "paginacion_ra"):
            self.paginacion_ra.reiniciar()
        if materia_id is None:
            self.tabla_ra.setRowCount(0)
            self.barra_pesos.poner_segmentos([])
            if hasattr(self, "lbl_vacio_ra"):
                self.lbl_vacio_ra.setVisible(False)
            if hasattr(self, "paginacion_ra"):
                self.paginacion_ra.establecer_total(0)
            self._actualizar_kpis()
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT * FROM resultados_aprendizaje WHERE materia_id=? AND estado='Activo'
                     ORDER BY orden, codigo""", (materia_id,))
        filas= [dict(fila) for fila in c.fetchall()]
        conn.close()
        self._ra_actual_editor= filas
        if self._dominicano:
            self.barra_pesos.poner_segmentos([(fila["codigo"], fila["peso"] or 0) for fila in filas])
            self.barra_pesos.setVisible(True)
        else:
            self.barra_pesos.setVisible(False)
        self._filtrar_ra()
        self._actualizar_kpis()

    #Aplica la búsqueda y la página actual sobre self._ra_actual_editor
    #(ya cargado desde la BD) y (re)dibuja solo esa porción en la tabla.
    def _filtrar_ra(self):

        if not hasattr(self, "tabla_ra"):
            return
        texto= _normalizar(self.in_buscar_ra.text().strip()) if hasattr(self, "in_buscar_ra") else ""
        todos= self._ra_actual_editor
        if texto:
            filtrados= [todo for todo in todos if texto in _normalizar(f"{todo['codigo']} {todo['descripcion']}")]
        else:
            filtrados= todos
        self.paginacion_ra.establecer_total(len(filtrados))
        inicio, fin= self.paginacion_ra.rango_actual()
        pagina= filtrados[inicio:fin]
        self.lbl_vacio_ra.setVisible(len(todos) > 0 and len(filtrados) == 0)
        with tabla_pausada(self.tabla_ra):
            self.tabla_ra.setRowCount(len(pagina))
            #f: fila de datos del RA en esta página; con ella se llenan las celdas de la fila row.
            for row, f in enumerate(pagina):
                item_codigo= QTableWidgetItem(f["codigo"])
                item_codigo.setData(Qt.ItemDataRole.UserRole, f["id"])
                self.tabla_ra.setItem(row, 0, item_codigo)
                self.tabla_ra.setItem(row, 1, QTableWidgetItem(f["descripcion"]))
                texto_peso= f"{f['peso']:.1f} %" if self._dominicano else "—"
                self.tabla_ra.setItem(row, 2, QTableWidgetItem(texto_peso))

    def _siguiente_codigo_sugerido(self):

        prefijo= "RA" if self._dominicano else "U"
        return f"{prefijo}{len(self._ra_actual_editor) + 1}"

    def _abrir_dialogo_ra_nuevo(self):

        materia_id= self.combo_materia_ra.currentData()
        if materia_id is None:
            mostrar_mensaje("advertencia", "Selecciona un módulo",
                             "Primero elige (o crea en Materias) un módulo técnico.", self)
            return
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede editar el currículo técnico.", self)
            return
        dialogo= DialogoRA(self, modo_simplificado=not self._dominicano,
                             codigo_sugerido= self._siguiente_codigo_sugerido())
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            #v: valores que el usuario capturó en el diálogo del RA.
            v= dialogo.valores()
            try:

                self._insertar_ra(materia_id, v["codigo"], v["descripcion"], v["peso"])
            except ValueError as error:
                mostrar_mensaje("error", "No se pudo guardar", str(error), self)
                return
            self._cargar_ra_de_materia()
            registrar_auditoria("Calificaciones Técnicas", "Agregó RA/Unidad", self.main_window.usuario_actual,
                                 f"Materia {materia_id} - {v['codigo']}")

    def _insertar_ra(self, materia_id, codigo, descripcion, peso, estado="Activo"):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT COALESCE(MAX(orden), 0) + 1 AS sig FROM resultados_aprendizaje WHERE materia_id=?",
                  (materia_id,))
        orden= c.fetchone()["sig"]
        try:

            c.execute("""INSERT INTO resultados_aprendizaje (materia_id, codigo, descripcion, peso, orden, estado)
                         VALUES (?,?,?,?,?,?)""", (materia_id, codigo, descripcion, peso, orden, estado))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            raise ValueError(f"Ya existe un RA/unidad con el código '{codigo}' en este módulo.")
        conn.close()

    def _abrir_dialogo_ra_editar(self):

        row= self.tabla_ra.currentRow()
        if row < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un RA/unidad de la tabla.", self)
            return
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede editar el currículo técnico.", self)
            return
        ra_id= self.tabla_ra.item(row, 0).data(Qt.ItemDataRole.UserRole)
        #f: cada RA cargado en el editor; se busca el que tiene el id seleccionado.
        datos= next((f for f in self._ra_actual_editor if f["id"] == ra_id), None)
        if datos is None:
            return
        dialogo= DialogoRA(self, modo_simplificado=not self._dominicano, datos_actuales=datos)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            #v: valores que el usuario capturó en el diálogo del RA.
            v= dialogo.valores()
            conn= obtener_conexion()
            c= conn.cursor()
            try:

                c.execute("UPDATE resultados_aprendizaje SET codigo=?, descripcion=?, peso=? WHERE id=?",
                          (v["codigo"], v["descripcion"], v["peso"], ra_id))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                mostrar_mensaje("error", "Código repetido",
                                 f"Ya existe otro RA/unidad con el código '{v['codigo']}' en este módulo.", self)
                return
            conn.close()
            self._cargar_ra_de_materia()
            registrar_auditoria("Calificaciones Técnicas", "Editó RA/Unidad", self.main_window.usuario_actual,
                                 v["codigo"])

    def _eliminar_ra_seleccionado(self):

        row= self.tabla_ra.currentRow()
        if row < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un RA/unidad de la tabla.", self)
            return
        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede eliminar del currículo técnico.", self)
            return
        ra_id= self.tabla_ra.item(row, 0).data(Qt.ItemDataRole.UserRole)
        codigo= self.tabla_ra.item(row, 0).text()
        if mostrar_mensaje("pregunta", "Confirmar",
                            f"¿Eliminar '{codigo}'? También se borrarán las notas ya registradas en él.",
                            self) != QMessageBox.StandardButton.Yes:
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("DELETE FROM resultados_aprendizaje WHERE id=?", (ra_id,))
        conn.commit()
        conn.close()
        self._cargar_ra_de_materia()
        registrar_auditoria("Calificaciones Técnicas", "Eliminó RA/Unidad", self.main_window.usuario_actual, codigo)

    def _actualizar_kpis(self):

        if not hasattr(self, "kpi_modulos"):
            return
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT COUNT(*) AS n FROM materias WHERE modelo_evaluacion=? AND estado='Activa'",
                  (MODELO_EVALUACION_TECNICA,))
        total_modulos= c.fetchone()["n"]
        c.execute("""SELECT COUNT(*) AS n FROM resultados_aprendizaje ra
                     JOIN materias m ON ra.materia_id = m.id
                     WHERE ra.estado='Activo' AND m.modelo_evaluacion=? AND m.estado='Activa'""",
                  (MODELO_EVALUACION_TECNICA,))
        total_ra= c.fetchone()["n"]
        anio= anio_academico_actual()
        c.execute("""SELECT COUNT(*) AS n FROM calificacion_ra
                     WHERE anio_academico=? AND (nota IS NOT NULL OR domina != '')""", (anio,))
        total_notas= c.fetchone()["n"]
        modulos_ok, total_con_ra= 0, 0
        if self._dominicano:
            c.execute("""SELECT m.id AS materia_id, SUM(ra.peso) AS suma FROM materias m
                         JOIN resultados_aprendizaje ra ON ra.materia_id = m.id AND ra.estado='Activo'
                         WHERE m.modelo_evaluacion=? AND m.estado='Activa' GROUP BY m.id""",
                      (MODELO_EVALUACION_TECNICA,))
            sumas= c.fetchall()
            total_con_ra= len(sumas)
            modulos_ok= sum(1 for suma in sumas if abs((suma["suma"] or 0) - 100) < 0.05)
        conn.close()

        self.kpi_modulos.poner_valor(total_modulos)
        self.kpi_ra.poner_valor(total_ra)
        self.kpi_notas.poner_valor(total_notas)
        if self._dominicano:
            self.kpi_pesos.poner_texto(f"{modulos_ok}/{total_con_ra}" if total_con_ra else "—")
        else:
            self.kpi_pesos.poner_texto("N/A")

    #TAB 2 — Registro de Notas
    def _tab_registro(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)

        frame_form, form= self._tarjeta_formulario("Selecciona el Módulo Técnico y el Año académico")
        self.combo_materia_registro= QComboBox()
        conectar_tooltip_seleccion(self.combo_materia_registro, "Módulo técnico para el que se registra la calificación")
        self.combo_materia_registro.currentIndexChanged.connect(self._cargar_secciones_de_materia)
        self.in_anio_registro= QLineEdit(anio_academico_actual())
        limitar_campo_texto(self.in_anio_registro, 300)
        self.in_anio_registro.setPlaceholderText("2025-2026")
        self.in_anio_registro.editingFinished.connect(self._cargar_grid_notas)
        form.addWidget(QLabel("Módulo técnico:"), 0, 0)
        form.addWidget(self.combo_materia_registro, 0, 1)
        form.addWidget(QLabel("Año académico:"), 0, 2)
        form.addWidget(self.in_anio_registro, 0, 3)
        disposicion.addWidget(frame_form)

        #Grado/Curso, Sección, Área Técnica y Carrera pasan a la ventana de "☰ Filtros" (igual que en Calendario/Banco
        #de Tareas): son los datos que acotan qué estudiantes aparecen en la tabla de abajo, así que viven aparte para
        #no apilar combos en la pantalla principal. Se crean aquí como atributos normales del módulo; se colocan dentro
        #del diálogo en _construir_dialogo_filtros_registro.
        self.combo_grado_registro= QComboBox()
        self.combo_grado_registro.currentIndexChanged.connect(self._cargar_secciones_de_materia)
        self.combo_seccion_registro= QComboBox()
        self.combo_seccion_registro.currentIndexChanged.connect(self._al_cambiar_filtro_registro)
        conectar_tooltip_seleccion(self.combo_seccion_registro, "Sección para la que se registra la calificación")
        self.lbl_filtro_especialidad_registro= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_registro= QComboBox()
        self.combo_filtro_especialidad_registro.setToolTip("Filtrar por área técnica del estudiante (Politécnico)")
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_registro,
            "Filtrar por área técnica del estudiante (Politécnico)")
        self.combo_filtro_especialidad_registro.currentIndexChanged.connect(self._al_cambiar_filtro_registro)
        self.lbl_filtro_carrera_registro= QLabel("Carrera:")
        self.combo_filtro_carrera_registro= QComboBox()
        self.combo_filtro_carrera_registro.setToolTip("Filtrar por carrera del estudiante (Universidad)")
        conectar_tooltip_seleccion(self.combo_filtro_carrera_registro, "Filtrar por carrera del estudiante (Universidad)")
        self.combo_filtro_carrera_registro.currentIndexChanged.connect(self._al_cambiar_filtro_registro)
        self._construir_dialogo_filtros_registro()

        fila_busqueda= QHBoxLayout()
        marco_busqueda, self.in_buscar_notas, self._icono_busqueda_notas=\
            self._crear_barra_busqueda("Buscar estudiante en la tabla por nombre, apellido o matrícula…")
        self._temporizador_busqueda_notas= QTimer(self)
        self._temporizador_busqueda_notas.setSingleShot(True)
        self._temporizador_busqueda_notas.setInterval(150)
        self._temporizador_busqueda_notas.timeout.connect(self._filtrar_grid_notas)
        #_t: texto escrito (no se usa); cada cambio reinicia el temporizador que filtra la tabla.
        self.in_buscar_notas.textChanged.connect(lambda _t: self._temporizador_busqueda_notas.start())
        fila_busqueda.addWidget(marco_busqueda, 1)
        self.btn_filtros_registro= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_registro)
        self.btn_filtros_registro.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_registro.setObjectName("BtnAccionNeutro")
        self.btn_filtros_registro.setToolTip("Filtrar por curso, sección, área técnica/carrera")
        self.btn_filtros_registro.clicked.connect(self._abrir_dialogo_filtros_registro)
        fila_busqueda.addWidget(self.btn_filtros_registro)
        disposicion.addLayout(fila_busqueda)

        self.lbl_resumen_filtros_registro= QLabel("")
        self.lbl_resumen_filtros_registro.setWordWrap(True)
        disposicion.addWidget(self.lbl_resumen_filtros_registro)

        fila_resumen= QHBoxLayout()
        fila_resumen.setSpacing(18)
        self.anillo_promedio_grupo= AnilloCF("Promedio del grupo", minimo=self._nota_minima)
        self.donut_grupo= DonutResumenGrupo()
        fila_resumen.addWidget(self.anillo_promedio_grupo)
        fila_resumen.addWidget(self.donut_grupo)
        fila_resumen.addStretch()
        self.btn_guardar_notas= QPushButton("Guardar Todos los Cambios")
        self.btn_guardar_notas.setIcon(icono_emoji("💾"))
        self.btn_guardar_notas.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar_notas.setObjectName("BtnAccionAgregar")
        #Lambda sin argumentos: ignora los del clic y guarda las notas de la cuadrícula.
        self.btn_guardar_notas.clicked.connect(lambda: self._guardar_notas_grid())
        fila_resumen.addWidget(self.btn_guardar_notas, 0, Qt.AlignmentFlag.AlignBottom)
        disposicion.addLayout(fila_resumen)

        frame_res, lr= self._tarjeta_resultados()
        self.lbl_vacio_notas= QLabel("Ningún estudiante coincide con la búsqueda.")
        self.lbl_vacio_notas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio_notas.setStyleSheet("color: #9CA3AF; padding: 10px;")
        self.lbl_vacio_notas.setVisible(False)
        lr.addWidget(self.lbl_vacio_notas)
        self.tabla_notas= QTableWidget(0, 0)
        aplicar_estructura_tabla(self.tabla_notas)

        self.tabla_notas.verticalHeader().setVisible(False)
        self.tabla_notas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_notas.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_notas.setAlternatingRowColors(True)
        lr.addWidget(self.tabla_notas, 1)
        self.paginacion_notas= ControlPaginacion(tamanos=[("8 por página", 8), ("15 por página", 15),
                                                            ("30 por página", 30)], tamano_inicial=8)
        self.paginacion_notas.cambio.connect(self._render_pagina_notas)
        lr.addWidget(self.paginacion_notas)
        btn_detalle_notas= agregar_boton_detalle(None, self.tabla_notas, self, titulo="Detalle de Notas Técnicas",
                                                    texto_boton= "Ver Detalle del Seleccionado")
        btn_detalle_notas.clicked.disconnect()
        btn_detalle_notas.clicked.connect(self._ver_detalle_estudiante_notas)
        #*_: argumentos de la señal (no se usan); doble clic equivale a pulsar 'Ver Detalle'.
        self.tabla_notas.doubleClicked.connect(lambda *_: btn_detalle_notas.click())
        lr.addWidget(btn_detalle_notas)
        disposicion.addWidget(frame_res)
        disposicion.addStretch()

        #Pantalla completa: se incluyen la tabla, su paginación, el botón de detalle y "Guardar Todos los Cambios" -sin
        #este último, en pantalla completa se podría ver la nota pero no guardarla, lo que dejaría el registro de notas
        #técnicas incompleto ahí adentro (mismo criterio que asistencia.py con su botón "Guardar").
        agregar_boton_pantalla_completa(
            None,
            [self.tabla_notas, self.paginacion_notas, btn_detalle_notas, self.btn_guardar_notas],
            titulo= "Registro de Notas Técnicas", parent=self)
        return contenedor

    #Ventanita (no modal) con Curso/Grado, Sección, Área Técnica y
    #Carrera para la pestaña "Registro de Notas" — mismo patrón que usan
    #calendario.py/banco_tareas.py: los combos viven aquí para no
    #apilarlos en la pantalla principal.
    def _construir_dialogo_filtros_registro(self):

        self.dialogo_filtros_registro= QDialog(self)
        self.dialogo_filtros_registro.setObjectName("DialogoFiltrosCT")
        self.dialogo_filtros_registro.setWindowTitle("Filtros de Registro de Notas")
        aplicar_icono_ventana(self.dialogo_filtros_registro, ICONO_FILTRO)
        self.dialogo_filtros_registro.setModal(False)
        self.dialogo_filtros_registro.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_registro)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        lbl_icono_encabezado= QLabel()
        pixmap_boton_filtro(lbl_icono_encabezado, 20)
        lbl_icono_encabezado.setObjectName("IconoEncabezadoFiltrosCT")
        fila_encabezado.addWidget(lbl_icono_encabezado)
        lbl_titulo_encabezado= QLabel("Filtros")
        lbl_titulo_encabezado.setObjectName("TituloEncabezadoFiltrosCT")
        fila_encabezado.addWidget(lbl_titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        lbl_subtitulo= QLabel("Curso/Grado y Sección son obligatorios para poder ver la tabla de estudiantes. "
                            "Área Técnica y Carrera son opcionales.")
        lbl_subtitulo.setObjectName("SubtituloFiltrosCT")
        lbl_subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(lbl_subtitulo)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setObjectName("SeparadorFiltrosCT")
        lay_dialogo.addWidget(separador)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            (None, self.combo_filtro_especialidad_registro),
            (None, self.combo_filtro_carrera_registro),
            ("Curso/Grado:", self.combo_grado_registro),
            ("Sección:", self.combo_seccion_registro),
        ):
            if combo is self.combo_filtro_especialidad_registro:
                grid.addWidget(self.lbl_filtro_especialidad_registro, fila, 0)
            elif combo is self.combo_filtro_carrera_registro:
                grid.addWidget(self.lbl_filtro_carrera_registro, fila, 0)
            else:
                grid.addWidget(QLabel(etiqueta), fila, 0)
            grid.addWidget(combo, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.dialogo_filtros_registro.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros_registro(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_registro.parent() is not _fc:
            self.dialogo_filtros_registro.setParent(_fc)
        self.dialogo_filtros_registro.show()
        self.dialogo_filtros_registro.raise_()
        self.dialogo_filtros_registro.activateWindow()

    def _al_cambiar_filtro_registro(self):

        self._actualizar_resumen_filtros_registro()
        self._cargar_grid_notas()

    #Como Curso/Sección/Área Técnica/Carrera ahora viven en la ventana
    #de Filtros (oculta por defecto), esta línea deja a la vista, sin
    #tener que abrir el diálogo, qué se está mostrando en la tabla.
    def _actualizar_resumen_filtros_registro(self):

        if not hasattr(self, "lbl_resumen_filtros_registro"):
            return
        partes= []
        if self.combo_grado_registro.currentData() is not None:
            partes.append(f"🎓 {self.combo_grado_registro.currentText()}")
        else:
            partes.append("Selecciona un curso/grado…")
        if self.combo_seccion_registro.currentData() is not None:
            partes.append(f"🏫 {self.combo_seccion_registro.currentText()}")
        if self._es_politecnico() and self.combo_filtro_especialidad_registro.currentData() is not None:
            partes.append(f"🧩 {self.combo_filtro_especialidad_registro.currentText()}")
        if self._es_universidad() and self.combo_filtro_carrera_registro.currentData() is not None:
            partes.append(f"🎓 {self.combo_filtro_carrera_registro.currentText()}")
        self.lbl_resumen_filtros_registro.setText(" · ".join(partes))

    def _cargar_grados_registro(self):

        poblar_combo_curso(self.combo_grado_registro, incluir_todos=False)
        self._cargar_especialidad_carrera_filtro_registro()
        self._actualizar_resumen_filtros_registro()

    #Igual que TODOS los combos Curso->Sección de AcaDeXI: Curso es
    #obligatorio primero. Aquí además depende de la Materia/Módulo elegida
    #(para saber en qué secciones se imparte según el Horario), así que
    #Sección solo se llena cuando AMBOS, Curso y Materia, están elegidos.
    def _cargar_secciones_de_materia(self):

        materia_id= self.combo_materia_registro.currentData()
        grado_id= self.combo_grado_registro.currentData() if hasattr(self, "combo_grado_registro") else None
        self.combo_seccion_registro.blockSignals(True)
        self.combo_seccion_registro.clear()
        if grado_id is None:
            self.combo_seccion_registro.addItem("Selecciona primero un curso/grado…", None)
        elif materia_id is None:
            self.combo_seccion_registro.addItem("Selecciona una materia/módulo…", None)
        else:
            self.combo_seccion_registro.addItem("Selecciona una sección…", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT DISTINCT secciones.id, secciones.nombre, secciones.grado_id AS grado_id_val
                         FROM horarios JOIN secciones ON horarios.seccion_id = secciones.id
                         WHERE horarios.materia_id=? AND secciones.grado_id=?
                         ORDER BY secciones.nombre""", (materia_id, grado_id))
            secciones= [dict(fila) for fila in c.fetchall()]
            if not secciones:
                #El módulo aún no está en el Horario para este curso: no bloqueamos al usuario, se ofrecen todas las secciones
                #de ese curso para que pueda igual registrar notas.
                c.execute("""SELECT id, nombre, grado_id AS grado_id_val FROM secciones
                             WHERE grado_id=? ORDER BY nombre""", (grado_id,))
                secciones= [dict(fila) for fila in c.fetchall()]
            conn.close()
            permitidas= obtener_secciones_permitidas(self.main_window)
            if permitidas is not None:
                secciones= [seccion for seccion in secciones if seccion["id"] in permitidas]
            for seccion in secciones:
                self.combo_seccion_registro.addItem(seccion["nombre"], seccion["id"])
        self.combo_seccion_registro.blockSignals(False)
        self._actualizar_resumen_filtros_registro()
        self._cargar_grid_notas()

    #Carga desde la BD el módulo/sección/año elegido: RA, estudiantes y
    #sus notas actuales (en self._notas_cache, la memoria de edición). El
    #dibujado de la tabla en sí (una página a la vez) lo hace
    #_render_pagina_notas(), para no perder ediciones sin guardar al
    #buscar o cambiar de página.
    def _cargar_grid_notas(self):

        materia_id= self.combo_materia_registro.currentData()
        seccion_id= self.combo_seccion_registro.currentData()
        anio= self.in_anio_registro.text().strip() or anio_academico_actual()
        self.tabla_notas.clear()
        self.tabla_notas.setRowCount(0)
        self.tabla_notas.setColumnCount(0)
        self._widgets_notas= {}
        self._labels_cf= {}
        self._ra_actual_registro= []
        self._estudiantes_grid_todos= []
        self._notas_cache= {}
        self._num_columnas_notas= 0
        if hasattr(self, "in_buscar_notas"):
            self.in_buscar_notas.blockSignals(True)
            self.in_buscar_notas.clear()
            self.in_buscar_notas.blockSignals(False)
        if hasattr(self, "paginacion_notas"):
            self.paginacion_notas.reiniciar()
        if hasattr(self, "lbl_vacio_notas"):
            self.lbl_vacio_notas.setVisible(False)
        if materia_id is None or seccion_id is None:
            self._actualizar_resumen_grid()
            return

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT * FROM resultados_aprendizaje WHERE materia_id=? AND estado='Activo'
                     ORDER BY orden, codigo""", (materia_id,))
        self._ra_actual_registro= [dict(fila) for fila in c.fetchall()]
        c.execute("""SELECT id, matricula, nombre, apellidos, especialidad_id, carrera_id, numero_lista
                     FROM estudiantes
                     WHERE seccion_id=? AND estado='Activo'
                     ORDER BY numero_lista IS NULL, numero_lista, apellidos, nombre""", (seccion_id,))
        especialidad_id= self.combo_filtro_especialidad_registro.currentData() if self._es_politecnico() else None
        carrera_id= self.combo_filtro_carrera_registro.currentData() if self._es_universidad() else None
        estudiantes_todos= [dict(fila) for fila in c.fetchall()]
        if especialidad_id is not None:
            estudiantes_todos= [estudiantes_todo for estudiantes_todo in estudiantes_todos if estudiantes_todo["especialidad_id"] == especialidad_id]
        if carrera_id is not None:
            estudiantes_todos= [estudiantes_todo for estudiantes_todo in estudiantes_todos if estudiantes_todo["carrera_id"] == carrera_id]
        self._estudiantes_grid_todos= estudiantes_todos

        if self._ra_actual_registro and self._estudiantes_grid_todos:
            #r: cada RA del registro actual; se toma su id.
            ids_ra= [r["id"] for r in self._ra_actual_registro]
            marcadores= ",".join("?" * len(ids_ra))
            c.execute(f"""SELECT * FROM calificacion_ra WHERE anio_academico=?
                         AND resultado_aprendizaje_id IN ({marcadores})""", [anio] + ids_ra)
            for fila in c.fetchall():
                if self._dominicano:
                    valor= fila["nota"] if fila["nota"] is not None else -1
                else:
                    valor= fila["domina"] or ""
                self._notas_cache[(fila["estudiante_id"], fila["resultado_aprendizaje_id"])]= valor
        conn.close()

        if not self._ra_actual_registro:
            self._actualizar_resumen_grid()
            if materia_id is not None:
                mostrar_mensaje(
                    "info",
                    "Sin Resultados de Aprendizaje" if self._dominicano else "Sin Unidades de Competencia",
                    "Este módulo todavía no tiene " +
                    ("RA definidos" if self._dominicano else "unidades definidas") +
                    ". Ve a la pestaña 'Módulos y RA' para crearlos.", self)
            return

        #r: cada RA del registro actual; se toma su código como título de columna.
        columnas= ["No.", "Matrícula", "Nombre"] + [r["codigo"] for r in self._ra_actual_registro] +\
                   (["C.F."] if self._dominicano else ["Estado del Módulo"])
        self.tabla_notas.setColumnCount(len(columnas))
        self.tabla_notas.setHorizontalHeaderLabels(columnas)
        #i: posición del RA; r: el RA, cuya descripción se pone como tooltip de su encabezado.
        for i, r in enumerate(self._ra_actual_registro):
            header_item= self.tabla_notas.horizontalHeaderItem(3 + i)
            if header_item is not None:
                header_item.setToolTip(r["descripcion"])
        self._num_columnas_notas= len(columnas)
        self.tabla_notas.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        #El "No." solo tiene sentido si, además de la Sección (obligatoria para llegar hasta aquí), también se filtró
        #Área Técnica/Carrera cuando la institución las usa -ver bd.mostrar_columna_numero_lista-, para no mezclar
        #numeración de varios grupos dentro de la misma sección como si fuera un único orden.
        self._mostrar_columna_numero_notas= mostrar_columna_numero_lista(
            self.main_window, seccion_id, especialidad_id, carrera_id)
        self.tabla_notas.setColumnHidden(0, not self._mostrar_columna_numero_notas)

        self._render_pagina_notas()
        self._actualizar_resumen_grid()

    #(Re)dibuja SOLO la página actual (según búsqueda + paginación) a
    #partir de self._estudiantes_grid_todos, leyendo el valor inicial de
    #cada celda desde self._notas_cache — así cambiar de página o filtrar
    #nunca descarta una edición que el usuario ya hizo pero no ha
    #guardado todavía.
    def _render_pagina_notas(self):

        if not hasattr(self, "tabla_notas") or not self._num_columnas_notas:
            self.tabla_notas.setRowCount(0)
            return
        texto= _normalizar(self.in_buscar_notas.text().strip()) if hasattr(self, "in_buscar_notas") else ""
        todos= self._estudiantes_grid_todos
        if texto:
            filtrados= [todo for todo in todos
                         if texto in _normalizar(f"{todo['matricula'] or ''} {todo['apellidos'] or ''} {todo['nombre']}")]
        else:
            filtrados= todos
        self.paginacion_notas.establecer_total(len(filtrados))
        inicio, fin= self.paginacion_notas.rango_actual()
        pagina= filtrados[inicio:fin]
        self.lbl_vacio_notas.setVisible(len(todos) > 0 and len(filtrados) == 0)

        puede= puede_editar(self.main_window)
        self._widgets_notas= {}
        self._labels_cf= {}
        self._cargando_grid= True
        with tabla_pausada(self.tabla_notas):
            self.tabla_notas.setRowCount(len(pagina))
            for row, est in enumerate(pagina):
                if getattr(self, "_mostrar_columna_numero_notas", False):
                    numero_lista= est["numero_lista"] if "numero_lista" in est.keys() else None
                    item_numero= QTableWidgetItem()
                    item_numero.setData(Qt.ItemDataRole.DisplayRole,
                                         numero_lista if numero_lista is not None else "—")
                    item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tabla_notas.setItem(row, 0, item_numero)
                item_mat= QTableWidgetItem(est["matricula"] or "")
                item_mat.setData(Qt.ItemDataRole.UserRole, est["id"])
                self.tabla_notas.setItem(row, 1, item_mat)
                self.tabla_notas.setItem(row, 2,
                    QTableWidgetItem(f"{est['apellidos'] or ''} {est['nombre']}".strip()))
                for col, ra in enumerate(self._ra_actual_registro):
                    valor_cache= self._notas_cache.get((est["id"], ra["id"]), -1 if self._dominicano else "")
                    if self._dominicano:
                        in_spin= QDoubleSpinBox()
                        in_spin.setRange(-1, 100)
                        in_spin.setDecimals(2)
                        in_spin.setSingleStep(0.5)
                        in_spin.setSpecialValueText("—")
                        in_spin.setValue(valor_cache if valor_cache is not None else -1)
                        in_spin.setEnabled(puede)
                        in_spin.valueChanged.connect(
                            #Lambda: _v es el valor nuevo (no se usa); r=fila, eid=id del estudiante, raid=id del RA y
                            #w=el spinbox se fijan al crearla. Avisa a _al_nota_cambiada que esa nota cambió.
                            lambda _v, r=row, eid=est["id"], raid=ra["id"], w=in_spin:
                            self._al_nota_cambiada(r, eid, raid, w))
                        self.tabla_notas.setCellWidget(row, 3 + col, in_spin)
                        self._widgets_notas[(row, ra["id"])]= in_spin
                    else:
                        combo= QComboBox()
                        for etiqueta, valor in RESULTADOS_COMPETENCIA_OPCIONES:
                            combo.addItem(etiqueta, valor)
                        idxc= combo.findData(valor_cache or "")
                        combo.setCurrentIndex(idxc if idxc >= 0 else 0)
                        combo.setEnabled(puede)
                        conectar_tooltip_seleccion(combo, f"Resultado de {est['nombre']} en {ra['codigo']}")
                        combo.currentIndexChanged.connect(
                            #Lambda: _i es el índice nuevo (no se usa); r=fila, eid=id del estudiante, raid=id del RA y
                            #w=el combo se fijan al crearla. Avisa a _al_nota_cambiada que esa nota cambió.
                            lambda _i, r=row, eid=est["id"], raid=ra["id"], w=combo:
                            self._al_nota_cambiada(r, eid, raid, w))
                        self.tabla_notas.setCellWidget(row, 3 + col, combo)
                        self._widgets_notas[(row, ra["id"])]= combo
                lbl_cf= QLabel("—")
                lbl_cf.setAlignment(Qt.AlignmentFlag.AlignCenter)
                fuente_cf= lbl_cf.font()
                fuente_cf.setBold(True)
                lbl_cf.setFont(fuente_cf)
                self.tabla_notas.setCellWidget(row, self._num_columnas_notas - 1, lbl_cf)
                self._labels_cf[row]= lbl_cf
        self._cargando_grid= False

        for row in range(len(pagina)):
            self._recalcular_fila(row)

    #Callback de la barra de búsqueda: vuelve a la página 1 y redibuja.
    def _filtrar_grid_notas(self):

        if hasattr(self, "paginacion_notas"):
            self.paginacion_notas.reiniciar()
        self._render_pagina_notas()

    def _al_nota_cambiada(self, row, estudiante_id, ra_id, widget):

        if self._cargando_grid:
            return
        valor= widget.value() if self._dominicano else widget.currentData()
        self._notas_cache[(estudiante_id, ra_id)]= valor
        self._recalcular_fila(row)

    def _ver_detalle_estudiante_notas(self):

        fila= self.tabla_notas.currentRow()
        if fila < 0:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona un estudiante de la tabla.", self)
            return
        item_mat= self.tabla_notas.item(fila, 1)
        item_nom= self.tabla_notas.item(fila, 2)
        campos= [("Matrícula", item_mat.text() if item_mat else ""),
                  ("Nombre", item_nom.text() if item_nom else "")]
        for ra in self._ra_actual_registro:
            widget= self._widgets_notas.get((fila, ra["id"]))
            if widget is None:
                continue
            if self._dominicano:
                val= widget.value()
                texto_val= f"{val:.2f}" if val >= 0 else "Sin evaluar"
                etiqueta_ra= f"{ra['codigo']} ({ra['peso']:.1f}%) — {ra['descripcion']}"
            else:
                texto_val= widget.currentText()
                etiqueta_ra= f"{ra['codigo']} — {ra['descripcion']}"
            campos.append((etiqueta_ra, texto_val))
        lbl= self._labels_cf.get(fila)
        campos.append(("Calificación Final (C.F.)" if self._dominicano else "Estado del módulo",
                        lbl.text() if lbl else "—"))
        mostrar_detalle_campos(self, "Detalle de Notas Técnicas", campos)

    def _recalcular_fila(self, row):

        if self._cargando_grid:
            return
        lbl= self._labels_cf.get(row)
        if lbl is None or not self._ra_actual_registro:
            return
        if self._dominicano:
            notas, pesos, incompleto= [], [], False
            for ra in self._ra_actual_registro:
                widget= self._widgets_notas.get((row, ra["id"]))
                if widget is None:
                    continue
                val= widget.value()
                if val < 0:
                    incompleto= True
                notas.append(val)
                pesos.append(ra["peso"] or 0)
            if incompleto:
                lbl.setText("Incompleto")
                lbl.setStyleSheet("color: #9CA3AF;")
            else:
                suma_pesos= sum(pesos)
                #n: cada nota; p: el peso de su RA. Promedio ponderado; si los pesos suman 0, promedio simple.
                cf= (sum(n * p for n, p in zip(notas, pesos)) / suma_pesos) if suma_pesos > 0 else\
                    (sum(notas) / len(notas) if notas else 0)
                lbl.setText(f"{cf:.1f}")
                lbl.setStyleSheet(f"color: {_color_cf(cf, self._nota_minima)};")
        else:
            estados= []
            for ra in self._ra_actual_registro:
                widget= self._widgets_notas.get((row, ra["id"]))
                if widget is not None:
                    estados.append(widget.currentData())
            if any(estado == "No Competente" for estado in estados):
                lbl.setText("Aún No Competente")
                lbl.setStyleSheet("color: #EF4444;")
            elif estados and all(estado == "Competente" for estado in estados):
                lbl.setText("Competente")
                lbl.setStyleSheet("color: #10B981;")
            elif any(estado == "Competente" for estado in estados):
                lbl.setText("En Progreso")
                lbl.setStyleSheet("color: #F59E0B;")
            else:
                lbl.setText("Pendiente")
                lbl.setStyleSheet("color: #9CA3AF;")
        self._actualizar_resumen_grid()

    #Calculado siempre sobre TODO el listado cargado (self._notas_cache
    #+ self._estudiantes_grid_todos), no solo sobre la página visible.
    def _actualizar_resumen_grid(self):

        if not hasattr(self, "anillo_promedio_grupo"):
            return
        estudiantes= getattr(self, "_estudiantes_grid_todos", [])
        if not estudiantes or not self._ra_actual_registro:
            self.anillo_promedio_grupo.poner_valor(0, con_datos=False)
            self.donut_grupo.poner_valores(0, 0, 0)
            return
        if self._dominicano:
            valores, ok, no, pendiente= [], 0, 0, 0
            for est in estudiantes:
                notas, pesos, incompleto= [], [], False
                for ra in self._ra_actual_registro:
                    val= self._notas_cache.get((est["id"], ra["id"]), -1)
                    if val is None or val < 0:
                        incompleto= True
                        val= 0
                    notas.append(val)
                    pesos.append(ra["peso"] or 0)
                if incompleto:
                    pendiente += 1
                    continue
                suma_pesos= sum(pesos)
                #n: cada nota; p: el peso de su RA. Promedio ponderado; si los pesos suman 0, promedio simple.
                cf= (sum(n * p for n, p in zip(notas, pesos)) / suma_pesos) if suma_pesos > 0 else\
                    (sum(notas) / len(notas) if notas else 0)
                valores.append(cf)
                if cf >= self._nota_minima:
                    ok += 1
                else:
                    no += 1
            promedio= sum(valores) / len(valores) if valores else 0
            self.anillo_promedio_grupo.poner_valor(promedio, _color_cf(promedio, self._nota_minima),
                                                  con_datos= bool(valores))
            self.donut_grupo.poner_valores(ok, no, pendiente)
        else:
            ok= no= pendiente= 0
            for est in estudiantes:
                estados= [self._notas_cache.get((est["id"], ra["id"]), "") for ra in self._ra_actual_registro]
                if any(estado == "No Competente" for estado in estados):
                    no += 1
                elif estados and all(estado == "Competente" for estado in estados):
                    ok += 1
                else:
                    pendiente += 1
            total= len(estudiantes)
            pct= (ok / total) * 100 if total else 0
            self.anillo_promedio_grupo.poner_valor(pct, _color_cf(pct, 50), con_datos=total > 0)
            self.donut_grupo.poner_valores(ok, no, pendiente)

    def _guardar_notas_grid(self, silencioso=False):

        if not puede_editar(self.main_window):
            if not silencioso:
                mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede registrar notas técnicas.", self)
            return
        if not self._ra_actual_registro or not self._estudiantes_grid_todos:
            if not silencioso:
                mostrar_mensaje("advertencia", "Sin datos", "Carga un módulo, sección y año antes de guardar.", self)
            return
        anio= self.in_anio_registro.text().strip() or anio_academico_actual()
        usuario= self.main_window.usuario_actual
        ahora= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn= obtener_conexion()
        c= conn.cursor()
        guardadas= 0
        #Se guarda TODO lo cargado (self._estudiantes_grid_todos), no solo la página visible: la búsqueda/paginación
        #son solo de visualización.
        for est in self._estudiantes_grid_todos:
            for ra in self._ra_actual_registro:
                valor_cache= self._notas_cache.get((est["id"], ra["id"]))
                if self._dominicano:
                    nota= None if (valor_cache is None or valor_cache < 0) else valor_cache
                    domina= ""
                else:
                    domina= valor_cache or ""
                    nota= {"Competente": 100.0, "No Competente": 0.0}.get(domina)
                if nota is None and not domina:
                    c.execute("""DELETE FROM calificacion_ra
                                 WHERE estudiante_id=? AND resultado_aprendizaje_id=? AND anio_academico=?""",
                              (est["id"], ra["id"], anio))
                    continue
                c.execute("""INSERT INTO calificacion_ra
                             (estudiante_id, resultado_aprendizaje_id, anio_academico, nota, domina, usuario,
                              actualizado)
                             VALUES (?,?,?,?,?,?,?)
                             ON CONFLICT(estudiante_id, resultado_aprendizaje_id, anio_academico) DO UPDATE SET
                                nota= excluded.nota, domina=excluded.domina, usuario=excluded.usuario,
                                actualizado= excluded.actualizado""",
                          (est["id"], ra["id"], anio, nota, domina, usuario, ahora))
                guardadas += 1
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones Técnicas", "Guardó notas técnicas", usuario,
                             f"Materia {self.combo_materia_registro.currentData()} - Sección "
                             f"{self.combo_seccion_registro.currentData()} - {anio}")
        self._actualizar_kpis()
        if not silencioso:
            mostrar_mensaje("exito", "Notas guardadas", f"Se guardaron {guardadas} registros.", self)

    #TAB 3 — Boletín Técnico
    def _tab_boletin(self):

        contenedor= QWidget()
        disposicion= QVBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 12, 4, 4)
        disposicion.setSpacing(14)

        frame_form, form= self._tarjeta_formulario("Año académico del boletín")
        self.in_anio_boletin= QLineEdit(anio_academico_actual())
        limitar_campo_texto(self.in_anio_boletin, 300)
        self.in_anio_boletin.setPlaceholderText("2025-2026")
        form.addWidget(QLabel("Año académico:"), 0, 0)
        form.addWidget(self.in_anio_boletin, 0, 1)
        disposicion.addWidget(frame_form)

        #Grado/Curso, Sección, Área Técnica y Carrera pasan a la ventana de "☰ Filtros" (igual que en Registro de Notas
        #más arriba): se crean aquí como atributos normales del módulo y se colocan dentro del diálogo en
        #_construir_dialogo_filtros_boletin.
        self.lbl_filtro_especialidad_boletin= QLabel("Área Técnica:")
        self.combo_filtro_especialidad_boletin= QComboBox()
        self.combo_filtro_especialidad_boletin.setToolTip("Filtrar por área técnica del estudiante (Politécnico)")
        conectar_tooltip_seleccion(self.combo_filtro_especialidad_boletin,
                                    "Filtrar por área técnica del estudiante (Politécnico)")
        self.combo_filtro_especialidad_boletin.currentIndexChanged.connect(self._al_cambiar_filtro_boletin)
        self.lbl_filtro_carrera_boletin= QLabel("Carrera:")
        self.combo_filtro_carrera_boletin= QComboBox()
        self.combo_filtro_carrera_boletin.setToolTip("Filtrar por carrera del estudiante (Universidad)")
        conectar_tooltip_seleccion(self.combo_filtro_carrera_boletin,
                                    "Filtrar por carrera del estudiante (Universidad)")
        self.combo_filtro_carrera_boletin.currentIndexChanged.connect(self._al_cambiar_filtro_boletin)
        self.combo_grado_boletin= QComboBox()
        self.combo_grado_boletin.currentIndexChanged.connect(self._cargar_secciones_filtro_boletin)
        self.combo_seccion_boletin= QComboBox()
        self.combo_seccion_boletin.currentIndexChanged.connect(self._al_cambiar_filtro_boletin)
        self._construir_dialogo_filtros_boletin()

        fila_busqueda= QHBoxLayout()
        marco_busqueda, self.in_buscar_boletin, self._icono_busqueda_boletin=\
            self._crear_barra_busqueda("Buscar estudiante por nombre, apellido o matrícula…")
        self._temporizador_busqueda_boletin= QTimer(self)
        self._temporizador_busqueda_boletin.setSingleShot(True)
        self._temporizador_busqueda_boletin.setInterval(150)
        self._temporizador_busqueda_boletin.timeout.connect(self._recargar_tabla_boletin)
        #_t: texto escrito (no se usa); cada cambio reinicia el temporizador que filtra la tabla.
        self.in_buscar_boletin.textChanged.connect(lambda _t: self._temporizador_busqueda_boletin.start())
        fila_busqueda.addWidget(marco_busqueda, 1)
        self.btn_filtros_boletin= QPushButton("Filtros")
        icono_boton_filtro(self.btn_filtros_boletin)
        self.btn_filtros_boletin.setIconSize(_QSize_emoji(16, 16))
        self.btn_filtros_boletin.setObjectName("BtnAccionNeutro")
        self.btn_filtros_boletin.setToolTip("Filtrar por curso, sección, área técnica/carrera")
        self.btn_filtros_boletin.clicked.connect(self._abrir_dialogo_filtros_boletin)
        fila_busqueda.addWidget(self.btn_filtros_boletin)
        disposicion.addLayout(fila_busqueda)

        self.lbl_resumen_filtros_boletin= QLabel("")
        self.lbl_resumen_filtros_boletin.setWordWrap(True)
        disposicion.addWidget(self.lbl_resumen_filtros_boletin)

        frame_tabla, lt= self._tarjeta_resultados()
        self.lbl_vacio_boletin= QLabel("No se encontraron estudiantes con los filtros actuales.")
        self.lbl_vacio_boletin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio_boletin.setStyleSheet("color: #9CA3AF; padding: 10px;")
        self.lbl_vacio_boletin.setVisible(False)
        lt.addWidget(self.lbl_vacio_boletin)
        self.tabla_estudiantes_boletin= QTableWidget(0, 4)
        aplicar_estructura_tabla(self.tabla_estudiantes_boletin)

        self.tabla_estudiantes_boletin.setHorizontalHeaderLabels(["Matrícula", "Nombre", "Grado", "Sección"])
        self.tabla_estudiantes_boletin.verticalHeader().setVisible(False)
        self.tabla_estudiantes_boletin.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_estudiantes_boletin.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_estudiantes_boletin.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_estudiantes_boletin.setAlternatingRowColors(True)
        self.tabla_estudiantes_boletin.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lt.addWidget(self.tabla_estudiantes_boletin, 1)
        self.paginacion_boletin= ControlPaginacion(tamanos=[("8 por página", 8), ("15 por página", 15),
                                                              ("30 por página", 30)], tamano_inicial=8)
        self.paginacion_boletin.cambio.connect(self._cargar_tabla_estudiantes_boletin)
        lt.addWidget(self.paginacion_boletin)

        fila_botones= QHBoxLayout()
        btn_generar= QPushButton("Generar Boletín del Seleccionado")
        btn_generar.setIcon(icono_emoji(EMOJI_BOLETIN_TECNICO))
        btn_generar.setIconSize(_QSize_emoji(16, 16))
        btn_generar.setObjectName("BtnAccionAjustar")
        btn_generar.setToolTip(
            "Arma la vista previa del boletín del estudiante seleccionado justo debajo "
            "(medallón con el promedio, resumen y tarjetas por módulo/RA). Desde ahí puedes "
            "usar 'Exportar PDF' para guardarlo.")
        btn_generar.clicked.connect(self._generar_boletin)
        self.btn_exportar_boletin= QPushButton("Exportar PDF")
        self.btn_exportar_boletin.setIcon(icono_emoji("\uE002"))
        self.btn_exportar_boletin.setIconSize(_QSize_emoji(16, 16))
        self.btn_exportar_boletin.setObjectName("BtnAccionNeutro")
        self.btn_exportar_boletin.clicked.connect(self._exportar_pdf_boletin)
        fila_botones.addWidget(btn_generar)
        fila_botones.addWidget(self.btn_exportar_boletin)
        fila_botones.addStretch()
        self.btn_detalle_boletin= agregar_boton_detalle(
            fila_botones, self.tabla_estudiantes_boletin, self,
            titulo= "Detalle del Estudiante", texto_boton="Ver Detalle")
        self.tabla_estudiantes_boletin.cellDoubleClicked.connect(
            #_r, _c: fila y columna del doble clic (no se usan); equivale a pulsar 'Ver Detalle'.
            lambda _r, _c: self.btn_detalle_boletin.click())
        lt.addLayout(fila_botones)
        agregar_boton_pantalla_completa(
            None,
            [self.tabla_estudiantes_boletin, self.paginacion_boletin],
            titulo= "Boletín Técnico — Estudiantes", parent=self)
        disposicion.addWidget(frame_tabla)

        self.lbl_titulo_preview_boletin= QLabel("Vista previa del boletín")
        f_prev= self.lbl_titulo_preview_boletin.font()
        f_prev.setBold(True)
        f_prev.setPointSize(11)
        self.lbl_titulo_preview_boletin.setFont(f_prev)
        self.lbl_titulo_preview_boletin.setStyleSheet("color: #6B7280; margin-top: 6px;")
        disposicion.addWidget(self.lbl_titulo_preview_boletin)

        fila_medallon= QHBoxLayout()
        fila_medallon.setSpacing(18)
        self.medallon_boletin= MedallonBoletin(minimo=self._nota_minima)
        fila_medallon.addWidget(self.medallon_boletin)
        bloque_info= QVBoxLayout()
        self.lbl_nombre_boletin= QLabel("Selecciona un estudiante de la tabla y presiona 'Generar Boletín'.")
        fuente= self.lbl_nombre_boletin.font()
        fuente.setBold(True)
        fuente.setPointSize(14)
        self.lbl_nombre_boletin.setFont(fuente)
        self.lbl_nombre_boletin.setWordWrap(True)
        self.lbl_situacion_boletin= QLabel("")
        self.lbl_situacion_boletin.setWordWrap(True)
        bloque_info.addWidget(self.lbl_nombre_boletin)
        bloque_info.addWidget(self.lbl_situacion_boletin)
        bloque_info.addStretch()
        fila_medallon.addLayout(bloque_info, 1)
        disposicion.addLayout(fila_medallon)

        self.contenedor_modulos_boletin= QVBoxLayout()
        self.contenedor_modulos_boletin.setSpacing(12)
        contenedor_widget= QWidget()
        contenedor_widget.setLayout(self.contenedor_modulos_boletin)
        disposicion.addWidget(contenedor_widget)

        self.frame_situacion_politecnico= self._construir_panel_situacion_politecnico()
        disposicion.addWidget(self.frame_situacion_politecnico)
        self.frame_situacion_politecnico.setVisible(self._dominicano)

        disposicion.addStretch()
        return contenedor

    def _construir_panel_situacion_politecnico(self):

        frame, lay= self._tarjeta_resultados()
        lbl_titulo= QLabel("Situación del Estudiante (Politécnico, República Dominicana)")
        fuente= lbl_titulo.font()
        fuente.setBold(True)
        lbl_titulo.setFont(fuente)
        lay.addWidget(lbl_titulo)

        self.lbl_decision_actual= QLabel("Decisión final: —")
        self.lbl_decision_actual.setWordWrap(True)
        lay.addWidget(self.lbl_decision_actual)

        fila= QHBoxLayout()
        self.combo_accion_no_promocion= QComboBox()
        for valor in ACCIONES_NO_PROMOCION:
            self.combo_accion_no_promocion.addItem(valor if valor else "— Sin definir —", valor)
        conectar_tooltip_seleccion(self.combo_accion_no_promocion,
                                    "Acción tomada ante la no promoción del estudiante")
        self.in_motivo_conducta= QLineEdit()
        limitar_campo_texto(self.in_motivo_conducta, 300)
        self.in_motivo_conducta.setPlaceholderText("Motivo / observación sobre la conducta (opcional)")
        btn_guardar_situacion= QPushButton("Guardar Situación")
        btn_guardar_situacion.setIcon(icono_emoji("💾"))
        btn_guardar_situacion.setIconSize(_QSize_emoji(16, 16))
        btn_guardar_situacion.setObjectName("BtnAccionAgregar")
        btn_guardar_situacion.clicked.connect(self._guardar_situacion_politecnico)
        fila.addWidget(QLabel("Acción:"))
        fila.addWidget(self.combo_accion_no_promocion, 1)
        fila.addWidget(self.in_motivo_conducta, 2)
        fila.addWidget(btn_guardar_situacion)
        lay.addLayout(fila)
        return frame

    def _secciones_con_modulos_tecnicos(self):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT DISTINCT horarios.seccion_id AS id FROM horarios
                     JOIN materias ON horarios.materia_id = materias.id
                     WHERE materias.modelo_evaluacion=?""", (MODELO_EVALUACION_TECNICA,))
        ids= [fila["id"] for fila in c.fetchall() if fila["id"] is not None]
        conn.close()
        permitidas= obtener_secciones_permitidas(self.main_window)
        if permitidas is not None:
            ids= [i for i in ids if i in permitidas]
        return ids

    #True si la institución es de tipo Politécnico (o Personalizado con el
    #módulo Politécnico activo). Mismo criterio usado en estudiantes.py.
    def _es_politecnico(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Politécnico" or (tipo == "Personalizado" and "Politécnico" in personalizados)

    #True si la institución es de tipo Universidad (o Personalizado con el
    #módulo Universidad activo). Mismo criterio usado en estudiantes.py.
    def _es_universidad(self):

        try:

            tipo, personalizados= self.main_window._tipo_institucion()
        except Exception:
            return False
        return tipo == "Universidad" or (tipo == "Personalizado" and "Universidad" in personalizados)

    #Igual que en el Boletín Técnico: los combos de Área Técnica y
    #Carrera de 'Registro de Notas' solo se muestran/pueblan si la
    #institución tiene ese módulo activo.
    def _cargar_especialidad_carrera_filtro_registro(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_registro.setVisible(es_poli)
        self.combo_filtro_especialidad_registro.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_registro.currentData()
            self.combo_filtro_especialidad_registro.blockSignals(True)
            self.combo_filtro_especialidad_registro.clear()
            self.combo_filtro_especialidad_registro.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_especialidad_registro.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_registro.findData(actual)
            self.combo_filtro_especialidad_registro.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_registro.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_registro.setVisible(es_uni)
        self.combo_filtro_carrera_registro.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_registro.currentData()
            self.combo_filtro_carrera_registro.blockSignals(True)
            self.combo_filtro_carrera_registro.clear()
            self.combo_filtro_carrera_registro.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_carrera_registro.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_carrera_registro.findData(actual)
            self.combo_filtro_carrera_registro.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_registro.blockSignals(False)

    #Igual que en Estudiantes: los combos de Área Técnica y Carrera del
    #Boletín Técnico solo se muestran/pueblan si la institución tiene ese
    #módulo activo.
    def _cargar_especialidad_carrera_filtro_boletin(self):

        es_poli= self._es_politecnico()
        self.lbl_filtro_especialidad_boletin.setVisible(es_poli)
        self.combo_filtro_especialidad_boletin.setVisible(es_poli)
        if es_poli:
            actual= self.combo_filtro_especialidad_boletin.currentData()
            self.combo_filtro_especialidad_boletin.blockSignals(True)
            self.combo_filtro_especialidad_boletin.clear()
            self.combo_filtro_especialidad_boletin.addItem("Todas las áreas técnicas", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM especialidades ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_especialidad_boletin.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_especialidad_boletin.findData(actual)
            self.combo_filtro_especialidad_boletin.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_especialidad_boletin.blockSignals(False)

        es_uni= self._es_universidad()
        self.lbl_filtro_carrera_boletin.setVisible(es_uni)
        self.combo_filtro_carrera_boletin.setVisible(es_uni)
        if es_uni:
            actual= self.combo_filtro_carrera_boletin.currentData()
            self.combo_filtro_carrera_boletin.blockSignals(True)
            self.combo_filtro_carrera_boletin.clear()
            self.combo_filtro_carrera_boletin.addItem("Todas las carreras", None)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("SELECT id, nombre FROM carreras ORDER BY nombre")
            for fila in c.fetchall():
                self.combo_filtro_carrera_boletin.addItem(fila["nombre"], fila["id"])
            conn.close()
            idx= self.combo_filtro_carrera_boletin.findData(actual)
            self.combo_filtro_carrera_boletin.setCurrentIndex(idx if idx >= 0 else 0)
            self.combo_filtro_carrera_boletin.blockSignals(False)

    def _cargar_grados_boletin(self):

        poblar_combo_curso(self.combo_grado_boletin, incluir_todos=False)
        self._actualizar_resumen_filtros_boletin()

    def _cargar_secciones_filtro_boletin(self):

        cascada_seccion_por_curso(self.combo_grado_boletin, self.combo_seccion_boletin, incluir_todas=False,
                                   secciones_permitidas= obtener_secciones_permitidas(self.main_window))
        self._actualizar_resumen_filtros_boletin()
        self._cargar_tabla_estudiantes_boletin()

    def _recargar_tabla_boletin(self):

        if hasattr(self, "paginacion_boletin"):
            self.paginacion_boletin.reiniciar()
        self._cargar_tabla_estudiantes_boletin()

    #Ventanita (no modal) con Curso/Grado, Sección, Área Técnica y
    #Carrera para la pestaña "Boletín" — mismo patrón que el diálogo de
    #Registro de Notas.
    def _construir_dialogo_filtros_boletin(self):

        self.dialogo_filtros_boletin= QDialog(self)
        self.dialogo_filtros_boletin.setObjectName("DialogoFiltrosCT")
        self.dialogo_filtros_boletin.setWindowTitle("Filtros del Boletín")
        aplicar_icono_ventana(self.dialogo_filtros_boletin, ICONO_FILTRO)
        self.dialogo_filtros_boletin.setModal(False)
        self.dialogo_filtros_boletin.setMinimumWidth(340)
        lay_dialogo= QVBoxLayout(self.dialogo_filtros_boletin)
        lay_dialogo.setContentsMargins(20, 18, 20, 18)
        lay_dialogo.setSpacing(12)

        fila_encabezado= QHBoxLayout()
        fila_encabezado.setSpacing(8)
        lbl_icono_encabezado= QLabel()
        pixmap_boton_filtro(lbl_icono_encabezado, 20)
        lbl_icono_encabezado.setObjectName("IconoEncabezadoFiltrosCT")
        fila_encabezado.addWidget(lbl_icono_encabezado)
        lbl_titulo_encabezado= QLabel("Filtros")
        lbl_titulo_encabezado.setObjectName("TituloEncabezadoFiltrosCT")
        fila_encabezado.addWidget(lbl_titulo_encabezado)
        fila_encabezado.addStretch()
        lay_dialogo.addLayout(fila_encabezado)

        lbl_subtitulo= QLabel("Curso/Grado y Sección son obligatorios para poder ver la tabla de estudiantes. "
                            "Área Técnica y Carrera son opcionales.")
        lbl_subtitulo.setObjectName("SubtituloFiltrosCT")
        lbl_subtitulo.setWordWrap(True)
        lay_dialogo.addWidget(lbl_subtitulo)

        separador= QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setObjectName("SeparadorFiltrosCT")
        lay_dialogo.addWidget(separador)

        grid= QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        fila= 0
        for etiqueta, combo in (
            (None, self.combo_filtro_especialidad_boletin),
            (None, self.combo_filtro_carrera_boletin),
            ("Curso/Grado:", self.combo_grado_boletin),
            ("Sección:", self.combo_seccion_boletin),
        ):
            if combo is self.combo_filtro_especialidad_boletin:
                grid.addWidget(self.lbl_filtro_especialidad_boletin, fila, 0)
            elif combo is self.combo_filtro_carrera_boletin:
                grid.addWidget(self.lbl_filtro_carrera_boletin, fila, 0)
            else:
                grid.addWidget(QLabel(etiqueta), fila, 0)
            grid.addWidget(combo, fila, 1)
            fila += 1
        lay_dialogo.addLayout(grid)

        fila_botones= QHBoxLayout()
        fila_botones.addStretch()
        btn_cerrar= QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar.setObjectName("BtnAccionNeutro")
        btn_cerrar.clicked.connect(self.dialogo_filtros_boletin.hide)
        fila_botones.addWidget(btn_cerrar)
        lay_dialogo.addLayout(fila_botones)

    def _abrir_dialogo_filtros_boletin(self):

        from src.interfaz.paginacion import dialogo_pantalla_completa_activo
        _fc= dialogo_pantalla_completa_activo()
        if _fc is not None and self.dialogo_filtros_boletin.parent() is not _fc:
            self.dialogo_filtros_boletin.setParent(_fc)
        self.dialogo_filtros_boletin.show()
        self.dialogo_filtros_boletin.raise_()
        self.dialogo_filtros_boletin.activateWindow()

    def _al_cambiar_filtro_boletin(self):

        self._actualizar_resumen_filtros_boletin()
        self._recargar_tabla_boletin()

    #Como Curso/Sección/Área Técnica/Carrera ahora viven en la ventana
    #de Filtros (oculta por defecto), esta línea deja a la vista, sin
    #tener que abrir el diálogo, qué se está mostrando en la tabla.
    def _actualizar_resumen_filtros_boletin(self):

        if not hasattr(self, "lbl_resumen_filtros_boletin"):
            return
        partes= []
        if self.combo_grado_boletin.currentData() is not None:
            partes.append(f"🎓 {self.combo_grado_boletin.currentText()}")
        else:
            partes.append("Selecciona un curso/grado…")
        if self.combo_seccion_boletin.currentData() is not None:
            partes.append(f"🏫 {self.combo_seccion_boletin.currentText()}")
        if self._es_politecnico() and self.combo_filtro_especialidad_boletin.currentData() is not None:
            partes.append(f"🧩 {self.combo_filtro_especialidad_boletin.currentText()}")
        if self._es_universidad() and self.combo_filtro_carrera_boletin.currentData() is not None:
            partes.append(f"🎓 {self.combo_filtro_carrera_boletin.currentText()}")
        self.lbl_resumen_filtros_boletin.setText(" · ".join(partes))

    #Estudiantes visibles en la tabla del Boletín Técnico: solo los que
    #cursan (o ya tienen notas en) algún módulo técnico, respetando los
    #filtros de grado/sección/búsqueda y las restricciones del rol.
    def _estudiantes_filtrados_boletin(self):

        grado_id= self.combo_grado_boletin.currentData() if hasattr(self, "combo_grado_boletin") else None
        seccion_id= self.combo_seccion_boletin.currentData() if hasattr(self, "combo_seccion_boletin") else None
        texto= _normalizar(self.in_buscar_boletin.text().strip()) if hasattr(self, "in_buscar_boletin") else ""
        especialidad_id= (self.combo_filtro_especialidad_boletin.currentData()
                            if self._es_politecnico() else None)
        carrera_id= self.combo_filtro_carrera_boletin.currentData() if self._es_universidad() else None

        conn= obtener_conexion()
        c= conn.cursor()
        condiciones= ["estudiantes.estado='Activo'"]
        params= []

        secciones_tecnicas= self._secciones_con_modulos_tecnicos()
        if secciones_tecnicas:
            marcadores= ",".join("?" * len(secciones_tecnicas))
            condiciones.append(f"estudiantes.seccion_id IN ({marcadores})")
            params.extend(secciones_tecnicas)

        permitidas= obtener_secciones_permitidas(self.main_window)
        if permitidas is not None:
            if not permitidas:
                condiciones.append("0")
            else:
                marcadores2= ",".join("?" * len(permitidas))
                condiciones.append(f"estudiantes.seccion_id IN ({marcadores2})")
                params.extend(permitidas)

        if seccion_id is not None:
            condiciones.append("estudiantes.seccion_id=?")
            params.append(seccion_id)
        elif grado_id is not None:
            condiciones.append("secciones.grado_id=?")
            params.append(grado_id)

        if especialidad_id is not None:
            condiciones.append("estudiantes.especialidad_id=?")
            params.append(especialidad_id)
        if carrera_id is not None:
            condiciones.append("estudiantes.carrera_id=?")
            params.append(carrera_id)

        query= f"""SELECT estudiantes.id, estudiantes.matricula, estudiantes.nombre, estudiantes.apellidos,
                    secciones.nombre AS seccion_nombre, grados.nombre AS grado_nombre
                    FROM estudiantes LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                    LEFT JOIN grados ON secciones.grado_id = grados.id
                    WHERE {' AND '.join(condiciones)} ORDER BY estudiantes.apellidos, estudiantes.nombre"""
        c.execute(query, params)
        filas= [dict(fila) for fila in c.fetchall()]
        conn.close()
        if texto:
            filas= [fila for fila in filas if texto in
                     _normalizar(f"{fila['matricula'] or ''} {fila['nombre']} {fila['apellidos'] or ''}")]
        return filas

    def _cargar_tabla_estudiantes_boletin(self):

        filas= self._estudiantes_filtrados_boletin()
        self.paginacion_boletin.establecer_total(len(filas))
        inicio, fin= self.paginacion_boletin.rango_actual()
        pagina= filas[inicio:fin]
        with tabla_pausada(self.tabla_estudiantes_boletin):
            self.tabla_estudiantes_boletin.setRowCount(len(pagina))
            #f: fila de datos del estudiante en esta página; con ella se llenan las celdas de la fila row.
            for row, f in enumerate(pagina):
                item_mat= QTableWidgetItem(f["matricula"] or "")
                item_mat.setData(Qt.ItemDataRole.UserRole, f["id"])
                self.tabla_estudiantes_boletin.setItem(row, 0, item_mat)
                self.tabla_estudiantes_boletin.setItem(row, 1,
                    QTableWidgetItem(f"{f['apellidos'] or ''} {f['nombre']}".strip()))
                self.tabla_estudiantes_boletin.setItem(row, 2, QTableWidgetItem(f["grado_nombre"] or ""))
                self.tabla_estudiantes_boletin.setItem(row, 3, QTableWidgetItem(f["seccion_nombre"] or ""))
        self.lbl_vacio_boletin.setVisible(len(filas) == 0)
        #Sin esto, la tabla se recarga sin ninguna fila seleccionada y "Generar Boletín del Seleccionado" no hace nada
        #útil (muestra "Selecciona un estudiante" y no avanza) hasta que el usuario haga clic manualmente en una fila
        #-algo que ni la propia interfaz ni el Tutorial Detallado dejaban claro que hacía falta.
        if self.tabla_estudiantes_boletin.rowCount() > 0:
            self.tabla_estudiantes_boletin.selectRow(0)

    def _generar_boletin(self):

        fila_sel= self.tabla_estudiantes_boletin.currentRow()
        if fila_sel < 0:
            mostrar_mensaje("advertencia", "Sin estudiante", "Selecciona un estudiante de la tabla.", self)
            return
        item= self.tabla_estudiantes_boletin.item(fila_sel, 0)
        estudiante_id= item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if estudiante_id is None:
            return
        anio= self.in_anio_boletin.text().strip() or anio_academico_actual()

        while self.contenedor_modulos_boletin.count():
            item= self.contenedor_modulos_boletin.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tarjetas_modulo_boletin= []

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("SELECT * FROM estudiantes WHERE id=?", (estudiante_id,))
        est= c.fetchone()
        if est is None:
            conn.close()
            return
        c.execute("""SELECT DISTINCT materias.id, materias.nombre, materias.codigo
                     FROM horarios JOIN materias ON horarios.materia_id = materias.id
                     JOIN secciones ON horarios.seccion_id = secciones.id
                     WHERE secciones.id=? AND materias.modelo_evaluacion=?""",
                  (est["seccion_id"], MODELO_EVALUACION_TECNICA))
        modulos= [dict(fila) for fila in c.fetchall()]
        if not modulos:
            c.execute("""SELECT DISTINCT materias.id, materias.nombre, materias.codigo FROM calificacion_ra
                         JOIN resultados_aprendizaje ra ON calificacion_ra.resultado_aprendizaje_id = ra.id
                         JOIN materias ON ra.materia_id = materias.id
                         WHERE calificacion_ra.estudiante_id=? AND calificacion_ra.anio_academico=?
                         AND materias.modelo_evaluacion=?""",
                      (estudiante_id, anio, MODELO_EVALUACION_TECNICA))
            modulos= [dict(fila) for fila in c.fetchall()]

        filas_pdf= []
        valores_cf= []
        for modulo in modulos:
            c.execute("""SELECT * FROM resultados_aprendizaje WHERE materia_id=? AND estado='Activo'
                         ORDER BY orden, codigo""", (modulo["id"],))
            ra_lista= [dict(fila) for fila in c.fetchall()]
            notas= {}
            for ra in ra_lista:
                c.execute("""SELECT * FROM calificacion_ra WHERE estudiante_id=? AND resultado_aprendizaje_id=?
                             AND anio_academico=?""", (estudiante_id, ra["id"], anio))
                fila_nota= c.fetchone()
                notas[ra["id"]]= dict(fila_nota) if fila_nota else None
            tarjeta, valor_resumen, texto_pdf= self._construir_tarjeta_modulo_boletin(modulo, ra_lista, notas)
            self.contenedor_modulos_boletin.addWidget(tarjeta)
            self._tarjetas_modulo_boletin.append(tarjeta)
            filas_pdf.append((modulo["nombre"], len(ra_lista), texto_pdf))
            if valor_resumen is not None:
                valores_cf.append(valor_resumen)
        conn.close()

        if not modulos:
            lbl_vacio= QLabel("Este estudiante no tiene módulos técnicos asignados todavía.")
            lbl_vacio.setStyleSheet("color: #6B7280;")
            self.contenedor_modulos_boletin.addWidget(lbl_vacio)
            self._tarjetas_modulo_boletin.append(lbl_vacio)

        self.lbl_nombre_boletin.setText(
            f"{est['nombre']} {est['apellidos'] or ''}".strip() +
            (f"  ·  Mat. {est['matricula']}" if est["matricula"] else "") + f"  ·  {anio}")

        if valores_cf:
            promedio= sum(valores_cf) / len(valores_cf)
            color= _color_cf(promedio, self._nota_minima)
            if self._dominicano:
                nivel= _texto_nivel_cf(promedio, self._nota_minima)
            else:
                nivel= "Competente" if promedio >= 99.9 else ("En Progreso" if promedio > 0 else "Aún No Competente")
            self.medallon_boletin.poner_valor(promedio, color, nivel)
        else:
            self.medallon_boletin.poner_valor(0, "#6B7280", "Sin evaluar")

        if self._dominicano:
            self._cargar_situacion_politecnico(estudiante_id, anio)
        self.frame_situacion_politecnico.setVisible(self._dominicano)

        self._ultimo_boletin= {
            "estudiante": dict(est), "anio": anio, "modulos_pdf": filas_pdf,
            "promedio": (sum(valores_cf) / len(valores_cf)) if valores_cf else None,
        }

        #El botón no abre nada nuevo: arma la vista previa (medallón + tarjetas) justo debajo. Como eso puede quedar
        #fuera de la pantalla, se confirma con un aviso y se hace scroll automático hasta esa vista previa para que
        #quede claro que el clic sí funcionó.
        mostrar_mensaje("exito", "Boletín generado",
                         "Se armó la vista previa del boletín más abajo. Usa 'Exportar PDF' para guardarlo.", self)
        scroll_ancestro= self.lbl_titulo_preview_boletin.parentWidget()
        while scroll_ancestro is not None and not isinstance(scroll_ancestro, QScrollArea):
            scroll_ancestro= scroll_ancestro.parentWidget()
        if scroll_ancestro is not None:
            scroll_ancestro.ensureWidgetVisible(self.lbl_titulo_preview_boletin)

    def _construir_tarjeta_modulo_boletin(self, modulo, ra_lista, notas):

        frame, lay= self._tarjeta_resultados()
        lbl_titulo= QLabel(f"🛠 {modulo['nombre']}" + (f"  ({modulo['codigo']})" if modulo.get("codigo") else ""))
        fuente= lbl_titulo.font()
        fuente.setBold(True)
        fuente.setPointSize(12)
        lbl_titulo.setFont(fuente)
        lay.addWidget(lbl_titulo)
        lbl_sub= QLabel(f"{len(ra_lista)} " +
                     ("Resultados de Aprendizaje (RA)" if self._dominicano else "Unidades de Competencia"))
        lbl_sub.setStyleSheet("color: #6B7280; font-size: 11px;")
        lay.addWidget(lbl_sub)

        if not ra_lista:
            lbl_vacio= QLabel("Este módulo todavía no tiene RA/unidades definidos.")
            lbl_vacio.setStyleSheet("color: #9CA3AF;")
            lay.addWidget(lbl_vacio)
            return frame, None, "Sin definir"

        tabla= QTableWidget(len(ra_lista), 4 if self._dominicano else 2)
        aplicar_estructura_tabla(tabla)

        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tabla.verticalHeader().setVisible(False)
        if self._dominicano:
            tabla.setHorizontalHeaderLabels(["RA", "Resultado de Aprendizaje", "Peso %", "Nota"])
        else:
            tabla.setHorizontalHeaderLabels(["Unidad", "Resultado"])

        notas_validas, pesos_validos= [], []
        todos_competentes, hay_no_competente, hay_dato= True, False, False
        for row, ra in enumerate(ra_lista):
            existente= notas.get(ra["id"])
            tabla.setItem(row, 0, QTableWidgetItem(ra["codigo"]))
            if self._dominicano:
                tabla.setItem(row, 1, QTableWidgetItem(ra["descripcion"]))
                tabla.setItem(row, 2, QTableWidgetItem(f"{ra['peso']:.1f}%"))
                nota_val= existente["nota"] if existente and existente["nota"] is not None else None
                item_nota= QTableWidgetItem(f"{nota_val:.2f}" if nota_val is not None else "—")
                if nota_val is not None:
                    item_nota.setForeground(QColor(_color_cf(nota_val, self._nota_minima)))
                    notas_validas.append(nota_val)
                    pesos_validos.append(ra["peso"] or 0)
                tabla.setItem(row, 3, item_nota)
            else:
                domina= (existente["domina"] if existente else "") or ""
                hay_dato= hay_dato or bool(domina)
                if domina == "No Competente":
                    hay_no_competente= True
                    todos_competentes= False
                elif domina != "Competente":
                    todos_competentes= False
                texto= {"Competente": "Competente",
                         "No Competente": "Aún No Competente"}.get(domina, "⏳ Pendiente")
                item_estado= QTableWidgetItem(texto)
                item_estado.setForeground(
                    QColor({"Competente": "#10B981", "No Competente": "#EF4444"}.get(domina, "#9CA3AF")))
                tabla.setItem(row, 1, item_estado)
        tabla.resizeColumnsToContents()
        tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(tabla, 1)

        if self._dominicano:
            suma_pesos= sum(pesos_validos)
            cf= None
            if notas_validas and len(notas_validas) == len(ra_lista) and suma_pesos > 0:
                #n: cada nota válida; p: el peso de su RA. Calificación final ponderada.
                cf= sum(n * p for n, p in zip(notas_validas, pesos_validos)) / suma_pesos
            lbl_cf= QLabel(f"Calificación Final (C.F.): {cf:.1f}" if cf is not None
                             else "Calificación Final (C.F.): pendiente")
            f2= lbl_cf.font()
            f2.setBold(True)
            f2.setPointSize(12)
            lbl_cf.setFont(f2)
            if cf is not None:
                lbl_cf.setStyleSheet(f"color: {_color_cf(cf, self._nota_minima)};")
            lay.addWidget(lbl_cf)
            resumen_pdf= f"{cf:.1f}" if cf is not None else "Pendiente"
            return frame, cf, resumen_pdf

        if not hay_dato:
            estado_txt, color_estado, valor_pct= "Pendiente", "#9CA3AF", None
        elif hay_no_competente:
            estado_txt, color_estado, valor_pct= "Aún No Competente", "#EF4444", 0.0
        elif todos_competentes:
            estado_txt, color_estado, valor_pct= "Competente", "#10B981", 100.0
        else:
            estado_txt, color_estado, valor_pct= "En Progreso", "#F59E0B", None
        lbl_estado= QLabel(f"Estado del módulo: {estado_txt}")
        f2= lbl_estado.font()
        f2.setBold(True)
        f2.setPointSize(12)
        lbl_estado.setFont(f2)
        lbl_estado.setStyleSheet(f"color: {color_estado};")
        lay.addWidget(lbl_estado)
        return frame, valor_pct, estado_txt

    def _cargar_situacion_politecnico(self, estudiante_id, anio):

        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""SELECT decision, accion_no_promocion, motivo_conducta FROM decision_promocion
                     WHERE estudiante_id=? AND anio_academico=?""", (estudiante_id, anio))
        fila= c.fetchone()
        conn.close()
        decision= fila["decision"] if fila else "Pendiente"
        self.lbl_decision_actual.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_decision_actual.setText(
            f"Decisión final del año: <b>{decision}</b> &nbsp; "
            f"<span style='color:#6B7280;'>(se gestiona en Calificaciones → Evaluaciones Finales)</span>")
        accion_actual= (fila["accion_no_promocion"] if fila else "") or ""
        idx= self.combo_accion_no_promocion.findData(accion_actual)
        self.combo_accion_no_promocion.setCurrentIndex(idx if idx >= 0 else 0)
        self.in_motivo_conducta.setText((fila["motivo_conducta"] if fila else "") or "")
        relevante= decision == "Repite el Grado"
        self.combo_accion_no_promocion.setEnabled(relevante)
        self.in_motivo_conducta.setEnabled(relevante)

    def _guardar_situacion_politecnico(self):

        if not puede_editar(self.main_window):
            mostrar_mensaje("advertencia", "Sin permisos", "Tu rol no puede editar la situación del estudiante.",
                             self)
            return
        estudiante_id= self._ultimo_boletin["estudiante"]["id"] if self._ultimo_boletin else None
        if estudiante_id is None:
            mostrar_mensaje("advertencia", "Sin boletín", "Genera primero el boletín del estudiante.", self)
            return
        anio= self.in_anio_boletin.text().strip() or anio_academico_actual()
        accion= self.combo_accion_no_promocion.currentData() or ""
        motivo= self.in_motivo_conducta.text().strip()
        conn= obtener_conexion()
        c= conn.cursor()
        c.execute("""INSERT INTO decision_promocion (estudiante_id, anio_academico, decision, accion_no_promocion,
                     motivo_conducta, usuario, fecha) VALUES (?,?,'Pendiente',?,?,?,?)
                     ON CONFLICT(estudiante_id, anio_academico) DO UPDATE SET
                        accion_no_promocion= excluded.accion_no_promocion, motivo_conducta=excluded.motivo_conducta,
                        usuario= excluded.usuario, fecha=excluded.fecha""",
                  (estudiante_id, anio, accion, motivo, self.main_window.usuario_actual,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        registrar_auditoria("Calificaciones Técnicas", "Actualizó situación Politécnico",
                             self.main_window.usuario_actual, f"Estudiante {estudiante_id} - {accion or 'sin definir'}")
        mostrar_mensaje("exito", "Guardado", "Situación del estudiante actualizada.", self)
        self._cargar_situacion_politecnico(estudiante_id, anio)

    def _exportar_pdf_boletin(self):

        if not self._ultimo_boletin:
            mostrar_mensaje("advertencia", "Sin boletín", "Genera el boletín antes de exportar.", self)
            return
        ruta, _= QFileDialog.getSaveFileName(self, "Guardar Boletín Técnico", "boletin_tecnico.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        institucion= _datos_institucion()
        datos= self._ultimo_boletin

        #Boletín Oficial RD (Fase 2, ver boletin_tecnico_minerd.py): grilla RA1-RA9% + C.F. igual a la plantilla del
        #Politécnico. Se activa desde Configuración > Calificaciones (mismo interruptor que el boletín general); si no,
        #sigue el resumen simple de abajo.
        try:

            from src.boletines.boletin_minerd import formato_boletin_general
            from src.boletines.boletin_tecnico_minerd import exportar_boletin_tecnico_oficial_pdf
        except ImportError:
            #Lambda sin argumentos: reemplaza la función ausente y siempre devuelve el formato 'simple'.
            formato_boletin_general= lambda: "simple"
        if formato_boletin_general() == "oficial_rd":
            estudiante_id= datos["estudiante"]["id"]
            boletin= exportar_boletin_tecnico_oficial_pdf(estudiante_id, ruta, institucion, anio_academico=datos["anio"])
            if boletin is None:
                mostrar_mensaje("error", "Sin datos", "No se encontró el estudiante seleccionado.", self)
                return
            registrar_auditoria("Calificaciones Técnicas", "Exportó boletín técnico PDF (formato oficial RD)",
                               self.main_window.usuario_actual, ruta)
            mostrar_mensaje("exito", "Boletín exportado", f"Boletín guardado en:\n{ruta}", self)
            return

        try:

            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            mostrar_mensaje("error", "Falta dependencia",
                             "Instala 'reportlab' (pip install reportlab) para exportar boletines en PDF.", self)
            return
        from reportlab.lib.colors import HexColor

        COLOR_BANDA= HexColor("#0E7490")
        COLOR_BANDA_TEXTO= HexColor("#FFFFFF")
        COLOR_ZEBRA= HexColor("#F5F6FA")
        COLOR_BORDE= HexColor("#E2E4EA")
        COLOR_TEXTO= HexColor("#1F2430")
        COLOR_TARJETA= HexColor("#F3F4F8")
        COLORES_ESTADO_TXT= {"Competente": "#10B981", "Aún No Competente": "#EF4444",
                              "En Progreso": "#F59E0B", "Pendiente": "#9CA3AF"}

        est= datos["estudiante"]
        subtitulo= "Boletín de Calificaciones Técnicas" if self._dominicano else "Boletín de Competencias Técnicas"

        cvs= canvas.Canvas(ruta, pagesize=letter)
        ancho, alto= letter
        margen= 50
        ancho_util= ancho - 2 * margen
        y= _dibujar_encabezado(cvs, ancho, alto, institucion, subtitulo)

        #--- Tarjeta con los datos del estudiante ---
        nombre_completo= f"{est['nombre']} {est['apellidos'] or ''}".strip()
        alto_tarjeta= 40
        cvs.setFillColor(COLOR_TARJETA)
        cvs.roundRect(margen, y - alto_tarjeta, ancho_util, alto_tarjeta, 6, fill=1, stroke=0)
        cvs.setFillColor(COLOR_TEXTO)
        cvs.setFont("Helvetica-Bold", 10.5)
        cvs.drawString(margen + 14, y - 17, _recortar_a_ancho(cvs, f"Estudiante: {nombre_completo}",
                                                               "Helvetica-Bold", 10.5, ancho_util * 0.6))
        if est.get("matricula"):
            cvs.setFont("Helvetica", 9)
            cvs.drawString(margen + 14, y - 31, f"Matrícula: {est['matricula']}")
        cvs.setFont("Helvetica", 8.5)
        cvs.drawRightString(ancho - margen - 14, y - 17, f"Año académico: {datos['anio']}")
        cvs.drawRightString(ancho - margen - 14, y - 31, f"Emitido: {datetime.now().strftime('%Y-%m-%d')}")
        y -= alto_tarjeta + 16

        #--- Columnas de la tabla ---
        col_modulo_w= ancho_util * 0.58
        col_ra_w= ancho_util * 0.20
        col_cf_w= ancho_util * 0.22
        x_modulo= margen
        x_ra= x_modulo + col_modulo_w
        x_cf= x_ra + col_ra_w
        etiqueta_ra= "N.º DE RA" if self._dominicano else "N.º UNIDADES"
        etiqueta_cf= "C.F. OBTENIDA" if self._dominicano else "RESULTADO"

        def _dibujar_cabecera_tabla(y_top):

            alto_enc= 22
            cvs.setFillColor(COLOR_BANDA)
            cvs.roundRect(margen, y_top - alto_enc, ancho_util, alto_enc, 4, fill=1, stroke=0)
            cvs.rect(margen, y_top - alto_enc, ancho_util, alto_enc / 2, fill=1, stroke=0)
            cvs.setFillColor(COLOR_BANDA_TEXTO)
            cvs.setFont("Helvetica-Bold", 8.5)
            cvs.drawString(x_modulo + 10, y_top - 15, "MÓDULO / MATERIA TÉCNICA")
            cvs.drawCentredString(x_ra + col_ra_w / 2, y_top - 15, etiqueta_ra)
            cvs.drawCentredString(x_cf + col_cf_w / 2, y_top - 15, etiqueta_cf)
            return y_top - alto_enc

        y= _dibujar_cabecera_tabla(y)

        alto_linea= 11
        zebra= False
        for nombre_modulo, n_ra, resumen in datos["modulos_pdf"]:
            lineas_modulo= _envolver_texto(cvs, nombre_modulo, "Helvetica", 9, col_modulo_w - 20)
            alto_fila= max(len(lineas_modulo) * alto_linea + 8, 22)

            if y - alto_fila < 130:
                _dibujar_pie_pagina(cvs, ancho, institucion)
                cvs.showPage()
                y= _dibujar_encabezado(cvs, ancho, alto, institucion, subtitulo)
                y= _dibujar_cabecera_tabla(y)
                zebra= False

            if zebra:
                cvs.setFillColor(COLOR_ZEBRA)
                cvs.rect(margen, y - alto_fila, ancho_util, alto_fila, fill=1, stroke=0)
            zebra= not zebra

            cvs.setStrokeColor(COLOR_BORDE)
            cvs.setLineWidth(0.5)
            cvs.rect(margen, y - alto_fila, ancho_util, alto_fila, fill=0, stroke=1)

            bloque_alto= len(lineas_modulo) * alto_linea
            y_texto= y - (alto_fila - bloque_alto) / 2 - alto_linea + 2
            cvs.setFillColor(COLOR_TEXTO)
            cvs.setFont("Helvetica", 9)
            for linea in lineas_modulo:
                cvs.drawString(x_modulo + 10, y_texto, linea)
                y_texto -= alto_linea

            y_centro= y - alto_fila / 2 - 3
            cvs.setFont("Helvetica", 9)
            cvs.setFillColor(COLOR_TEXTO)
            cvs.drawCentredString(x_ra + col_ra_w / 2, y_centro, str(n_ra))

            resumen_txt= str(resumen)
            if self._dominicano:
                try:

                    color_resumen= _color_cf(float(resumen_txt), self._nota_minima)
                except (TypeError, ValueError):
                    color_resumen= "#6B7280"
            else:
                color_resumen= COLORES_ESTADO_TXT.get(resumen_txt, "#4B5563")
            cvs.setFillColor(HexColor(color_resumen))
            cvs.setFont("Helvetica-Bold", 9)
            cvs.drawCentredString(x_cf + col_cf_w / 2, y_centro,
                                  _recortar_a_ancho(cvs, resumen_txt, "Helvetica-Bold", 9, col_cf_w - 8))
            cvs.setFillColor(COLOR_TEXTO)

            y -= alto_fila

        if not datos["modulos_pdf"]:
            cvs.setFont("Helvetica-Oblique", 9.5)
            cvs.setFillColor(HexColor("#6B7280"))
            cvs.drawCentredString(ancho / 2, y - 20, "Este estudiante no tiene módulos técnicos registrados.")
            cvs.setFillColor(COLOR_TEXTO)
            y -= 36

        #--- Promedio general, en tarjeta destacada ---
        if datos["promedio"] is not None:
            y -= 14
            color_promedio= _color_cf(datos["promedio"], self._nota_minima)
            alto_badge= 30
            cvs.setFillColor(HexColor(color_promedio))
            cvs.roundRect(margen, y - alto_badge, ancho_util, alto_badge, 6, fill=1, stroke=0)
            cvs.setFillColor(HexColor("#FFFFFF"))
            cvs.setFont("Helvetica-Bold", 12)
            cvs.drawCentredString(ancho / 2, y - alto_badge / 2 - 4, f"Promedio General: {datos['promedio']:.1f}")
            cvs.setFillColor(COLOR_TEXTO)
            y -= alto_badge + 14

        if self._dominicano:
            if y < 130:
                _dibujar_pie_pagina(cvs, ancho, institucion)
                cvs.showPage()
                y= _dibujar_encabezado(cvs, ancho, alto, institucion, subtitulo)
            conn= obtener_conexion()
            c= conn.cursor()
            c.execute("""SELECT decision, accion_no_promocion FROM decision_promocion
                         WHERE estudiante_id=? AND anio_academico=?""", (est["id"], datos["anio"]))
            fila= c.fetchone()
            conn.close()
            decision= fila["decision"] if fila else "Pendiente"
            alto_caja= 46 if (fila and fila["accion_no_promocion"]) else 34
            cvs.setFillColor(COLOR_TARJETA)
            cvs.roundRect(margen, y - alto_caja, ancho_util, alto_caja, 6, fill=1, stroke=0)
            cvs.setFillColor(COLOR_TEXTO)
            cvs.setFont("Helvetica-Bold", 9.5)
            cvs.drawString(margen + 14, y - 15, "SITUACIÓN DEL/DE LA ESTUDIANTE")
            cvs.setFont("Helvetica", 9)
            cvs.drawString(margen + 14, y - 29, f"Condición final: {decision}")
            if fila and fila["accion_no_promocion"]:
                cvs.drawString(margen + 14, y - 41, f"Acción (Politécnico): {fila['accion_no_promocion']}")
            y -= alto_caja

        _dibujar_pie_pagina(cvs, ancho, institucion)
        cvs.save()
        registrar_auditoria("Calificaciones Técnicas", "Exportó boletín técnico PDF",
                             self.main_window.usuario_actual, ruta)
        mostrar_mensaje("exito", "Boletín exportado", f"Boletín guardado en:\n{ruta}", self)

    #Refresco / tema
    def _aplicar_modo(self):

        self.tabs.setTabText(0, "Módulos y RA" if self._dominicano else "Módulos y Unidades")
        self.lbl_subtitulo_cabecera.setText(
            "Evaluación por Resultados de Aprendizaje (RA) ponderados."
            if self._dominicano else
            "Evaluación por Unidades de Competencia (Competente / Aún No Competente).")
        if hasattr(self, "barra_pesos"):
            self.barra_pesos.setVisible(self._dominicano)
        if hasattr(self, "frame_situacion_politecnico"):
            self.frame_situacion_politecnico.setVisible(self._dominicano)
        if hasattr(self, "anillo_promedio_grupo"):
            self.anillo_promedio_grupo._minimo= self._nota_minima
        if hasattr(self, "medallon_boletin"):
            self.medallon_boletin._minimo= self._nota_minima

    def refrescar(self):

        self._dominicano= es_sistema_dominicano(_sistema_calificacion_actual())
        self._nota_minima= NOTA_MINIMA_RD if self._dominicano else 70.0
        self._aplicar_modo()
        self._tabs_cargados= set()
        self._cargar_materias_tecnicas_combo(self.combo_materia_ra)
        self._cargar_ra_de_materia()
        self._cargar_grados_registro()
        self._cargar_materias_tecnicas_combo(self.combo_materia_registro)
        self._cargar_secciones_de_materia()
        self._cargar_grados_boletin()
        self._cargar_secciones_filtro_boletin()
        self._cargar_especialidad_carrera_filtro_boletin()
        self._actualizar_resumen_filtros_registro()
        self._actualizar_resumen_filtros_boletin()
        self._actualizar_kpis()
        self._tabs_cargados= {0, 1, 2}


    def actualizar_tema(self):

        mw= self.main_window
        paletas= getattr(mw, "theme_palettes", None)
        if not paletas:
            return
        tema_actual= getattr(mw, "tema_actual", "Colorful (Multicolor)")
        paleta= paletas.get(tema_actual) or paletas.get("Colorful (Multicolor)")
        idx= 1 if getattr(mw, "modo_oscuro", True) else 0
        bg_panel= paleta["display_bg"][idx]
        bg_borde= paleta["btn_num_bg"][idx]
        txt_prim= paleta["text_primary"][idx]
        txt_sec= paleta["text_secondary"][idx]
        accent= paleta["btn_op_bg"][idx]
        accent_hover= paleta.get("btn_op_hover", [accent, accent])[idx]
        modo_oscuro= getattr(mw, "modo_oscuro", True)

        self.setStyleSheet(f"""
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {bg_borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QFrame#TarjetaCabeceraCT {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_hex_a_rgba(accent, 0.20 if modo_oscuro else 0.10)},
                    stop:1 {_hex_a_rgba(accent, 0.03)});
                border: 1px solid {_hex_a_rgba(accent, 0.30)};
                border-radius: 16px;
            }}
            QLabel#IconoCabeceraCT {{
                background-color: {_hex_a_rgba(accent, 0.22)};
                border-radius: 23px;
                font-size: 22px;
                color: {accent};
            }}
            QLabel#TituloCabeceraCT {{
                color: {txt_prim}; font-size: 18px; font-weight: 800; background: transparent;
            }}
            QLabel#SubtituloCabeceraCT {{ color: {txt_sec}; font-size: 12px; background: transparent; }}
            QFrame#TarjetaFormularioCT {{
                background-color: {_hex_a_rgba(accent, 0.05)};
                border: 1px solid {_hex_a_rgba(txt_sec, 0.20)};
                border-radius: 14px;
            }}
            QFrame#MarcoBusquedaCT {{
                background-color: {_hex_a_rgba(txt_sec, 0.10)};
                border-radius: 16px;
            }}
            QLineEdit#CampoBusquedaCT {{
                border: none;
                background: transparent;
                padding: 8px 0;
                color: {txt_prim};
            }}
            QTableWidget {{
                background-color: {bg_panel};
                alternate-background-color: {_hex_a_rgba(accent, 0.06)};
                gridline-color: {_hex_a_rgba(txt_sec, 0.15)};
                color: {txt_prim};
                border: 1px solid {bg_borde};
                border-radius: 10px;
            }}
            QHeaderView::section {{
                background-color: {_hex_a_rgba(accent, 0.18)};
                color: {txt_prim};
                padding: 6px;
                border: none;
                font-weight: 600;
            }}
            QTabWidget::pane {{
                border: none;
                font-weight: 600;
            }}
            QTabBar {{
                background: transparent;
            }}
            QTabBar::tab {{
                background: {_hex_a_rgba(txt_sec, 0.10)};
                color: {txt_sec};
                padding: 9px 20px;
                margin-right: 8px;
                margin-bottom: 4px;
                border-radius: 12px;
                border: 1px solid {_hex_a_rgba(txt_sec, 0.16)};
                font-weight: 600;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 {accent_hover});
                color: white;
                border: 1px solid transparent;
                font-weight: 700;
            }}
            QTabBar::tab:!selected:hover {{
                background-color: {_hex_a_rgba(accent, 0.20)};
                color: {txt_prim};
                border: 1px solid {_hex_a_rgba(accent, 0.35)};
            }}
        """)
        for icono in (getattr(self, "_icono_busqueda_notas", None), getattr(self, "_icono_busqueda_boletin", None)):
            if icono is not None:
                icono.establecer_color(txt_sec)

        estilo_dialogo_filtros= f"""
            QDialog#DialogoFiltrosCT {{
                background-color: {bg_panel};
            }}
            /* Repite aquí el mismo QToolTip que usa la ventana principal:
               este diálogo es una ventana de nivel superior aparte, y su
               propio setStyleSheet() reemplaza -para todo lo que esté
               dentro- cualquier regla heredada, incluido el QToolTip global.
               Sin esto, los tooltips de los combos aquí adentro caían al
               estilo nativo de Qt (gris claro/texto negro), inconsistente
               con el resto de AcaDeXI. */
            QToolTip {{
                background-color: {bg_panel};
                color: {txt_prim};
                border: 1px solid {bg_borde};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QLabel#IconoEncabezadoFiltrosCT {{
                background-color: {accent};
                color: white;
                border-radius: 15px;
                min-width: 30px; max-width: 30px;
                min-height: 30px; max-height: 30px;
                font-size: 14px;
                qproperty-alignment: AlignCenter;
            }}
            QLabel#TituloEncabezadoFiltrosCT {{
                font-size: 16px;
                font-weight: 800;
                color: {txt_prim};
                background: transparent;
            }}
            QLabel#SubtituloFiltrosCT {{
                font-size: 11.5px;
                color: {txt_sec};
                background: transparent;
            }}
            QFrame#SeparadorFiltrosCT {{
                background-color: {bg_borde};
                max-height: 1px;
                border: none;
            }}
            QLabel {{
                color: {txt_prim};
                font-weight: 700;
                font-size: 12.5px;
                background: transparent;
            }}
        """
        for dialogo in (getattr(self, "dialogo_filtros_registro", None), getattr(self, "dialogo_filtros_boletin", None)):
            if dialogo is not None:
                dialogo.setStyleSheet(estilo_dialogo_filtros)
        for lbl_resumen in (getattr(self, "lbl_resumen_filtros_registro", None),
                             getattr(self, "lbl_resumen_filtros_boletin", None)):
            if lbl_resumen is not None:
                lbl_resumen.setStyleSheet(f"color: {txt_sec}; font-size: 11.5px; background: transparent;")
