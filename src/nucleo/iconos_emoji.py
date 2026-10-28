#iconos_emoji.py — Reemplazo de TODOS los emojis de texto de AcaDeXI por
#iconos vectoriales multicolor dibujados con QPainter.
#
#Por qué existe
# -----------------------------------------
# la app usaba emojis Unicode sueltos (💾, 🗑, ✅, 🎓...) incrustados en el
# -----------------------------------------
#texto de botones, títulos y tooltips. Eso depende de que el sistema
#operativo tenga una fuente con esos glifos y de qué versión de esa fuente
#sea (Windows/Linux/macOS los dibujan distinto, y algunos ni los tienen),
#así que la misma pantalla se veía distinta -o directamente rota, con
#"cuadritos"- según el equipo. Este módulo sustituye cada emoji por un
#QIcon dibujado a mano, vectorial (se ve nítido en cualquier tamaño/DPI) y
#EN VARIOS COLORES -como el emoji original-, no un simple glifo monocromo.
#
#Cómo se usa desde cualquier módulo
#from iconos_emoji import icono_emoji, quitar_emojis_texto
#
#btn_guardar= QPushButton(quitar_emojis_texto("💾 Guardar"))
#btn_guardar.setIcon(icono_emoji("💾"))
#btn_guardar.setIconSize(QSize(18, 18))
#
#O, para un QLabel con el emoji suelto dentro de un texto más largo, usar
#`pixmap_emoji("🎓", 16)` y colocarlo en un QLabel aparte junto al texto.
#
#Todo el dibujo se cachea por (caracter, tamaño) así que llamar a
#`icono_emoji`/`pixmap_emoji` muchas veces (una app grande como esta lo hace
#todo el tiempo, al reconstruir listas/tablas) es barato.
import math
import weakref

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QPainterPath, QColor,
                            QLinearGradient, QPen, QBrush, QPolygonF)

TAMANO_DEFECTO= 20

_cache_pixmap= {}
_cache_icon= {}
_cache_html= {}

#Consciencia de tema (claro/oscuro) La inmensa mayoría de los íconos de este archivo usan colores SEMÁNTICOS
#(rojo para eliminar, verde para confirmar, azul para acciones...) que se leen bien tanto en fondo claro como
#oscuro, así que no necesitan saber nada del tema. Unos pocos (como el de "Filtros") usan un gris NEUTRO
#pensado para fondos claros, y se vuelven casi invisibles sobre un fondo
#oscuro. Para esos casos puntuales:
##1. main.py llama a `establecer_modo_oscuro(activo)` cada vez que la
#persona cambia de tema (y una vez al iniciar la app).
#2. Los pocos dibujos que lo necesitan preguntan `_modo_oscuro_activo`
#para elegir su color neutro.
#3. Los widgets que usan ESOS íconos puntuales se auto-registran al
#pedirlos con `icono_boton_filtro`/`pixmap_boton_filtro` (en vez de `icono_emoji`/`pixmap_emoji` directo), así
#se pueden refrescar solos sin que main.py tenga que conocer -ni encontrar- cada botón de Filtros de los ~15
#módulos que lo usan.
_modo_oscuro_activo= False
_widgets_filtro_boton= weakref.WeakSet()
_widgets_filtro_pixmap= weakref.WeakKeyDictionary()  #widget -> tamaño pedido


#Llamar tras cambiar el tema (y una vez al iniciar la app). Si el
#modo realmente cambió, limpia la cache de íconos -para que los
#PRÓXIMOS `icono_emoji`/`pixmap_emoji` reflejen el tema nuevo- y refresca
#en el acto los widgets ya construidos que dependen del tema (ver
#`icono_boton_filtro`/`pixmap_boton_filtro`).
def establecer_modo_oscuro(activo):

    global _modo_oscuro_activo
    activo= bool(activo)
    if activo == _modo_oscuro_activo:
        return
    _modo_oscuro_activo= activo
    _cache_pixmap.clear()
    _cache_icon.clear()
    for boton in list(_widgets_filtro_boton):
        try:

            boton.setIcon(icono_emoji("\uE000"))
        except RuntimeError:
            pass  #el widget C++ ya fue destruido
    for label, tamano in list(_widgets_filtro_pixmap.items()):
        try:

            label.setPixmap(pixmap_emoji("\uE000", tamano))
        except RuntimeError:
            pass


#Asigna el icono de "Filtros" a `boton` (QPushButton/QToolButton) y lo
#deja registrado para refrescarse solo si más tarde cambia el tema.
#Usar esto en vez de `boton.setIcon(icono_emoji("\uE000"))` a mano.
def icono_boton_filtro(boton):

    boton.setIcon(icono_emoji("\uE000"))
    _widgets_filtro_boton.add(boton)


#Igual que `icono_boton_filtro` pero para un QLabel con el pixmap del
#icono de Filtros suelto (cabeceras de sección, etc.).
def pixmap_boton_filtro(label, size=20):

    label.setPixmap(pixmap_emoji("\uE000", size))
    _widgets_filtro_pixmap[label]= size


#Utilidades de bajo nivel
def _nuevo_lienzo(size):

    pix= QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    pintor= QPainter(pix)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return pix, pintor


#Rect en fracción [0,1] del lienzo -> QRectF en píxeles reales.
def _r(size, x0, y0, x1, y1):

    return QRectF(x0 * size, y0 * size, (x1 - x0) * size, (y1 - y0) * size)


def _pluma(color, ancho=1.4):

    pen= QPen(QColor(color))
    pen.setWidthF(ancho)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _sin_pluma():

    return QPen(Qt.PenStyle.NoPen)


def _degradado(rect, c1, c2, vertical=True):

    g= QLinearGradient(rect.topLeft(), rect.bottomLeft() if vertical else rect.topRight())
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    return QBrush(g)


#Primitivas de forma (cada una recibe QPainter + tamaño de lienzo en px)
def _disco(pintor, size, x0, y0, x1, y1, color, borde=None):

    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_pluma(borde) if borde else _sin_pluma())
    pintor.drawEllipse(_r(size, x0, y0, x1, y1))


def _rect_redondeado(pintor, size, x0, y0, x1, y1, color, radio=0.12, borde=None):

    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_pluma(borde) if borde else _sin_pluma())
    pintor.drawRoundedRect(_r(size, x0, y0, x1, y1), radio * size, radio * size)


def _poligono(pintor, size, puntos_frac, color, borde=None):

    poly= QPolygonF([QPointF(x * size, y * size) for x, y in puntos_frac])
    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_pluma(borde) if borde else _sin_pluma())
    pintor.drawPolygon(poly)


def _linea(pintor, size, x0, y0, x1, y1, color, ancho=1.6):

    pintor.setPen(_pluma(color, ancho))
    pintor.drawLine(QPointF(x0 * size, y0 * size), QPointF(x1 * size, y1 * size))


def _check(pintor, size, color="white", x0=0.28, y0=0.52, x1=0.44, y1=0.68, x2=0.74, y2=0.32, ancho=2.2):

    pen= _pluma(color, ancho)
    pintor.setPen(pen)
    pintor.drawLine(QPointF(x0 * size, y0 * size), QPointF(x1 * size, y1 * size))
    pintor.drawLine(QPointF(x1 * size, y1 * size), QPointF(x2 * size, y2 * size))


def _cruz(pintor, size, color, x0=0.30, y0=0.30, x1=0.70, y1=0.70, ancho=2.2):

    pen= _pluma(color, ancho)
    pintor.setPen(pen)
    pintor.drawLine(QPointF(x0 * size, y0 * size), QPointF(x1 * size, y1 * size))
    pintor.drawLine(QPointF(x1 * size, y0 * size), QPointF(x0 * size, y1 * size))


def _mas(pintor, size, color, ancho=2.4, x0=0.5, y0=0.5, medio=0.24):

    pen= _pluma(color, ancho)
    pintor.setPen(pen)
    pintor.drawLine(QPointF((x0 - medio) * size, y0 * size), QPointF((x0 + medio) * size, y0 * size))
    pintor.drawLine(QPointF(x0 * size, (y0 - medio) * size), QPointF(x0 * size, (y0 + medio) * size))


def _menos(pintor, size, color, ancho=2.4, y=0.5, medio=0.24):

    pintor.setPen(_pluma(color, ancho))
    pintor.drawLine(QPointF((0.5 - medio) * size, y * size), QPointF((0.5 + medio) * size, y * size))


def _estrella(p, size, x0, y0, x1, y1, color, borde=None, puntas=5):

    cx, cy= (x0 + x1) / 2, (y0 + y1) / 2
    radio_ext, radio_int= (x1 - x0) / 2, (x1 - x0) / 2 * 0.42
    puntos= []
    for i in range(puntas * 2):
        ang= math.pi / puntas * i - math.pi / 2
        radio= radio_ext if i % 2 == 0 else radio_int
        puntos.append((cx + radio * math.cos(ang), cy + radio * math.sin(ang)))
    _poligono(p, size, puntos, color, borde)


#Flecha recta apuntando a `angulo_deg` (0 = derecha), centrada en (cx,cy).
def _flecha(pintor, size, color, angulo_deg=0, cx=0.5, cy=0.5, largo=0.34, ancho_cabeza=0.16, grosor=2.4):

    ang= math.radians(angulo_deg)
    dx, dy= math.cos(ang), math.sin(ang)
    x_ini, y_ini= cx - dx * largo, cy - dy * largo
    x_fin, y_fin= cx + dx * largo, cy + dy * largo
    pintor.setPen(_pluma(color, grosor))
    pintor.drawLine(QPointF(x_ini * size, y_ini * size), QPointF(x_fin * size, y_fin * size))
    perp= ang + math.pi / 2
    px, py= math.cos(perp) * ancho_cabeza, math.sin(perp) * ancho_cabeza
    back_x, back_y= x_fin - dx * ancho_cabeza * 1.3, y_fin - dy * ancho_cabeza * 1.3
    _poligono(pintor, size, [
        (x_fin, y_fin), (back_x + px, back_y + py), (back_x - px, back_y - py)
    ], color)


#Dos arcos con punta de flecha formando un círculo -icono de refrescar/sincronizar.
def _flechas_circulares(pintor, size, color1, color2):

    rect= _r(size, 0.16, 0.16, 0.84, 0.84)
    pintor.setPen(_pluma(color1, 2.4))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(rect, 20 * 16, 150 * 16)
    pintor.setPen(_pluma(color2, 2.4))
    pintor.drawArc(rect, 200 * 16, 150 * 16)
    _poligono(pintor, size, [(0.80, 0.30), (0.90, 0.22), (0.90, 0.40)], color1)
    _poligono(pintor, size, [(0.20, 0.70), (0.10, 0.78), (0.10, 0.60)], color2)


#tipo: 'undo' (↩ apunta a la izq.) o 'redo' (apunta a la der.).
def _flecha_curva(pintor, size, color, tipo="undo"):

    rect= _r(size, 0.20, 0.22, 0.80, 0.78)
    pintor.setPen(_pluma(color, 2.4))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    if tipo == "undo":
        pintor.drawArc(rect, 0 * 16, 270 * 16)
        _poligono(pintor, size, [(0.20, 0.50), (0.32, 0.40), (0.32, 0.62)], color)
    else:
        pintor.drawArc(rect, -90 * 16, 270 * 16)
        _poligono(pintor, size, [(0.80, 0.50), (0.68, 0.40), (0.68, 0.62)], color)


def _triangulo_alerta(pintor, size, color_fondo="#FBBF24", color_signo="#78350F"):

    _poligono(pintor, size, [(0.5, 0.12), (0.92, 0.85), (0.08, 0.85)], color_fondo, borde="#B45309")
    pintor.setPen(_pluma(color_signo, 2.6))
    pintor.drawLine(QPointF(0.5 * size, 0.40 * size), QPointF(0.5 * size, 0.62 * size))
    _disco(pintor, size, 0.475, 0.68, 0.525, 0.73, color_signo)


def _candado(pintor, size, color_cuerpo="#64748B", color_arco="#94A3B8", abierto=False):

    if abierto:
        arco= _r(size, 0.26, 0.10, 0.74, 0.56)
        pintor.setPen(_pluma(color_arco, 3.4))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawArc(arco, 40 * 16, 220 * 16)
    else:
        arco= _r(size, 0.26, 0.14, 0.74, 0.56)
        pintor.setPen(_pluma(color_arco, 3.4))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawArc(arco, 0, 180 * 16)
    _rect_redondeado(pintor, size, 0.20, 0.44, 0.80, 0.90, color_cuerpo, radio=0.10)
    _disco(pintor, size, 0.44, 0.58, 0.56, 0.70, "#1E293B")


def _llave(pintor, size, color="#EAB308"):

    _disco(pintor, size, 0.14, 0.30, 0.42, 0.58, color, borde="#A16207")
    _disco(pintor, size, 0.24, 0.40, 0.34, 0.48, "white")
    pintor.setPen(_pluma(color, 4.0))
    pintor.drawLine(QPointF(0.40 * size, 0.44 * size), QPointF(0.84 * size, 0.44 * size))
    pintor.drawLine(QPointF(0.70 * size, 0.44 * size), QPointF(0.70 * size, 0.60 * size))
    pintor.drawLine(QPointF(0.80 * size, 0.44 * size), QPointF(0.80 * size, 0.56 * size))


def _carpeta(p, size, color="#F5B942", abierta=False):

    _rect_redondeado(p, size, 0.10, 0.22, 0.46, 0.34, color, radio=0.06)
    if abierta:
        _poligono(p, size, [(0.10, 0.34), (0.14, 0.82), (0.92, 0.82), (0.88, 0.40), (0.36, 0.40), (0.30, 0.34)],
                   "#FBCB68", borde="#C88A1E")
    else:
        _rect_redondeado(p, size, 0.10, 0.30, 0.90, 0.82, "#FBCB68", radio=0.06)
    _rect_redondeado(p, size, 0.10, 0.34, 0.90, 0.40, color, radio=0.02)


def _documento(p, size, color_pagina="#F8FAFC", color_borde="#94A3B8", color_esquina="#3B82F6", lineas=True):

    _poligono(p, size, [(0.24, 0.10), (0.64, 0.10), (0.80, 0.26), (0.80, 0.90), (0.24, 0.90)],
               color_pagina, borde=color_borde)
    _poligono(p, size, [(0.64, 0.10), (0.80, 0.26), (0.64, 0.26)], color_esquina)
    if lineas:
        for i, y in enumerate((0.42, 0.55, 0.68)):
            _linea(p, size, 0.34, y, 0.70 if i != 2 else 0.58, y, "#94A3B8", 1.6)


#Registrar Nota Completiva: hoja de examen + insignia de "retomar/
#completar" (flecha circular), porque una completiva es justo eso: una
#segunda oportunidad para terminar una evaluación pendiente.
def _nota_completiva(pintor, size):

    _documento(pintor, size, color_esquina="#3B82F6")
    _disco(pintor, size, 0.54, 0.54, 0.94, 0.94, "#DBEAFE", borde="#3B82F6")
    pintor.setPen(_pluma("#2563EB", 2.1))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(_r(size, 0.605, 0.605, 0.875, 0.875), 25 * 16, 290 * 16)
    _poligono(pintor, size, [(0.855, 0.635), (0.905, 0.605), (0.905, 0.675)], "#2563EB")


#Registrar Nota Extraordinaria: hoja de examen + insignia de estrella,
#para lo "fuera de lo ordinario" -una convocatoria que no es parte del
#ciclo regular de evaluaciones-.
def _nota_extraordinaria(p, size):

    _documento(p, size, color_esquina="#F59E0B")
    _disco(p, size, 0.54, 0.54, 0.94, 0.94, "#FEF3C7", borde="#F59E0B")
    _estrella(p, size, 0.615, 0.615, 0.865, 0.865, "#D97706")


#Registrar Nota Especial: hoja de examen + insignia de escudo, para un
#caso particular con condiciones propias -mismo lenguaje visual que el
#resto de "excepciones/protegido" de la app-.
def _nota_especial(p, size):

    _documento(p, size, color_esquina="#8B5CF6")
    _disco(p, size, 0.54, 0.54, 0.94, 0.94, "#EDE9FE", borde="#8B5CF6")
    _poligono(p, size, [(0.74, 0.615), (0.815, 0.640), (0.815, 0.700),
                         (0.74, 0.760), (0.665, 0.700), (0.665, 0.640)], "#7C3AED")


#Registro de notas -para el KPI "Notas registradas (año actual)"-:
#una planilla con filas ya marcadas con check, para comunicar "cuántas
#notas se han cargado" (una cuenta de registros), en vez del genérico
#gráfico de tendencia ascendente (📈) que en el resto de la app se usa
#para "promedio/desempeño" -un concepto distinto- y que aquí no dejaba
#claro que el KPI cuenta calificaciones ya guardadas.
def _registro_notas_kpi(p, size, color="#10B981"):

    borde= "#065F46"
    claro= "#D1FAE5"
    #Hoja de la planilla.
    _rect_redondeado(p, size, 0.16, 0.06, 0.84, 0.94, "#F8FAFC", radio=0.06, borde=borde)
    #Cabecera de color (como el encabezado de una planilla de notas).
    _rect_redondeado(p, size, 0.16, 0.06, 0.84, 0.24, color, radio=0.06)
    _rect_redondeado(p, size, 0.16, 0.16, 0.84, 0.24, color, radio=0.0)
    #Filas: raya (alumno) + casilla ya marcada con check (nota registrada).
    for y in (0.38, 0.56, 0.74):
        _linea(p, size, 0.24, y, 0.56, y, "#94A3B8", 2.0)
        _rect_redondeado(p, size, 0.62, y - 0.06, 0.76, y + 0.06, claro, radio=0.25, borde=color)
        _check(p, size, color=color, x0=0.645, y0=y, x1=0.685, y1=y + 0.045,
               x2= 0.745, y2=y - 0.055, ancho=1.6)
    #Insignia grande de check en la esquina -"al día"-, mismo lenguaje visual que el resto de KPIs de esta pantalla
    #para "completo".
    _disco(p, size, 0.64, 0.66, 0.98, 1.00, "#22C55E", borde="#15803D")
    _check(p, size, color="white", x0=0.70, y0=0.83, x1=0.755, y1=0.89, x2=0.885, y2=0.75, ancho=2.0)


def _libro(pintor, size, color="#3B82F6", color_borde="#1E3A8A"):

    _poligono(pintor, size, [(0.16, 0.16), (0.50, 0.24), (0.50, 0.86), (0.16, 0.80)], color, borde=color_borde)
    _poligono(pintor, size, [(0.84, 0.16), (0.50, 0.24), (0.50, 0.86), (0.84, 0.80)], color, borde=color_borde)
    pintor.setPen(_pluma("white", 1.2))
    pintor.drawLine(QPointF(0.50 * size, 0.24 * size), QPointF(0.50 * size, 0.86 * size))


def _persona(p, size, n=1, color="#3B82F6", graduado=False):

    def _dibujar_una(cx, escala, color_piel="#3B82F6"):

        _disco(p, size, cx - 0.09 * escala, 0.18 * escala + 0.05, cx + 0.09 * escala, 0.18 * escala + 0.05 + 0.18 * escala, color_piel)
        _poligono(p, size, [
            (cx - 0.22 * escala, 0.90), (cx - 0.16 * escala, 0.52), (cx + 0.16 * escala, 0.52), (cx + 0.22 * escala, 0.90)
        ], color_piel)
    if n == 1:
        _dibujar_una(0.5, 1.0, color)
        if graduado:
            _poligono(p, size, [(0.30, 0.26), (0.5, 0.14), (0.70, 0.26), (0.5, 0.34)], "#1E293B")
            _rect_redondeado(p, size, 0.47, 0.32, 0.53, 0.46, "#1E293B", radio=0.4)
            _disco(p, size, 0.44, 0.44, 0.50, 0.50, "#EAB308")
    else:
        _dibujar_una(0.34, 0.82, "#0EA5E9")
        _dibujar_una(0.66, 0.82, "#F97316")


def _casa(p, size, color_techo="#EF4444", color_pared="#F8FAFC"):

    _poligono(p, size, [(0.5, 0.12), (0.90, 0.46), (0.10, 0.46)], color_techo)
    _rect_redondeado(p, size, 0.20, 0.44, 0.80, 0.88, color_pared, radio=0.02, borde="#94A3B8")
    _rect_redondeado(p, size, 0.44, 0.62, 0.56, 0.88, "#B45309", radio=0.02)


def _edificio(p, size, color="#64748B", ventanas="#BFDBFE"):

    _rect_redondeado(p, size, 0.22, 0.14, 0.78, 0.90, color, radio=0.03)
    for fy in (0.26, 0.42, 0.58, 0.74):
        for fx in (0.32, 0.52):
            _rect_redondeado(p, size, fx, fy, fx + 0.16, fy + 0.10, ventanas, radio=0.01)


def _escuela(pintor, size):

    _edificio(pintor, size, "#F97316", "#FEF3C7")
    _poligono(pintor, size, [(0.5, 0.02), (0.5, 0.14)], "#78350F")
    pintor.setPen(_pluma("#78350F", 1.6))
    pintor.drawLine(QPointF(0.5 * size, 0.02 * size), QPointF(0.5 * size, 0.16 * size))
    _poligono(pintor, size, [(0.5, 0.02), (0.66, 0.07), (0.5, 0.12)], "#EF4444")


def _hospital(p, size):

    _rect_redondeado(p, size, 0.18, 0.20, 0.82, 0.90, "#F8FAFC", radio=0.04, borde="#94A3B8")
    _mas(p, size, "#EF4444", ancho=4.2, y0=0.48, medio=0.16)


def _castillo(p, size):

    _rect_redondeado(p, size, 0.20, 0.42, 0.80, 0.90, "#8B5CF6", radio=0.02)
    for fx in (0.24, 0.40, 0.56, 0.72):
        _rect_redondeado(p, size, fx, 0.30, fx + 0.08, 0.42, "#8B5CF6", radio=0.0)
    _poligono(p, size, [(0.5, 0.10), (0.66, 0.30), (0.34, 0.30)], "#7C3AED")


def _bombilla(p, size):

    _disco(p, size, 0.28, 0.14, 0.72, 0.58, "#FDE047", borde="#CA8A04")
    _rect_redondeado(p, size, 0.40, 0.56, 0.60, 0.78, "#94A3B8", radio=0.05)
    for y in (0.82, 0.88):
        _linea(p, size, 0.40, y, 0.60, y, "#64748B", 2.0)


def _engranaje(p, size, color="#64748B"):

    cx, cy, r_ext, r_int= 0.5, 0.5, 0.34, 0.24
    dientes= []
    n= 8
    for i in range(n * 2):
        ang= math.pi / n * i
        radio= r_ext if i % 2 == 0 else r_ext * 0.80
        dientes.append((cx + radio * math.cos(ang), cy + radio * math.sin(ang)))
    _poligono(p, size, dientes, color)
    _disco(p, size, cx - r_int * 0.5, cy - r_int * 0.5, cx + r_int * 0.5, cy + r_int * 0.5, "white")


def _llave_inglesa(pintor, size, color="#64748B"):

    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(-45)
    pintor.translate(-size * 0.5, -size * 0.5)
    _rect_redondeado(pintor, size, 0.42, 0.30, 0.58, 0.78, color, radio=0.05)
    arco= _r(size, 0.30, 0.10, 0.70, 0.42)
    pintor.setPen(_pluma(color, 4.2))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(arco, 20 * 16, 320 * 16)
    pintor.restore()


def _lupa(pintor, size, color="#3B82F6", signo=None):

    pintor.setBrush(QBrush(QColor(255, 255, 255, 60)))
    pintor.setPen(_pluma(color, 3.0))
    pintor.drawEllipse(_r(size, 0.16, 0.16, 0.62, 0.62))
    pintor.setPen(_pluma("#1E293B", 3.4))
    pintor.drawLine(QPointF(0.58 * size, 0.58 * size), QPointF(0.86 * size, 0.86 * size))
    if signo == "+":
        _mas(pintor, size, color, ancho=1.8, x0=0.39, y0=0.39, medio=0.10)
    elif signo == "-":
        _menos(pintor, size, color, ancho=1.8, y=0.39, medio=0.10)


#Lápiz de edición. Deliberadamente dibujado GRANDE (ocupa casi todo
#el lienzo, no solo una franja central) porque a tamaños de botón chicos
#(16-18px) una versión más "delgada" se perdía y costaba reconocerla.
def _lapiz(pintor, size):

    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(45)
    pintor.translate(-size * 0.5, -size * 0.5)
    _rect_redondeado(pintor, size, 0.36, 0.14, 0.64, 0.68, "#FDE047", radio=0.02)
    _poligono(pintor, size, [(0.36, 0.68), (0.64, 0.68), (0.5, 0.92)], "#B45309")
    _rect_redondeado(pintor, size, 0.36, 0.03, 0.64, 0.16, "#F87171", radio=0.4)
    pintor.restore()


#Align-justify: 4 líneas horizontales redondeadas del mismo largo
#(el icono clásico de 'filtros/columnas' de las suites modernas).
#
#A diferencia del resto de los íconos "estructurales" de este archivo,
#este SIEMPRE se dibuja en blanco puro, sin importar el tema claro/oscuro
#-por diseño: el botón/ventana de Filtros usa un fondo de color (acento)
#donde el blanco siempre contrasta bien, así que no hace falta -ni se
#quiere- que cambie de tono con el tema.
def _alineacion_justificada(pintor, size):

    paso= size * 0.9 / 4
    ancho_linea= size * 0.78
    x0= size * 0.11
    grosor= max(1.6, size * 0.075)
    pintor.setPen(_pluma("#FFFFFF", grosor))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(4):
        pos_y= size * 0.05 + paso * i + paso * 0.5
        pintor.drawLine(QPointF(x0, pos_y), QPointF(x0 + ancho_linea, pos_y))


#Icono de alineación de texto: 4 líneas de distinto largo, colocadas
#a la izquierda/centradas/a la derecha según `modo` -el mismo lenguaje
#visual que las suites de ofimática usan para estos tres botones, que
#en el editor de reportes existían con texto vacío y sin ningún dibujo
#(botones invisibles).
def _alineacion_lineas(pintor, size, modo):

    anchos_relativos= (0.78, 0.50, 0.64, 0.38)
    paso= size * 0.9 / 4
    grosor= max(1.6, size * 0.11)
    color= "#64748B"  #slate-500: se lee bien tanto en tema claro como oscuro
    pintor.setPen(_pluma(color, grosor))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    for i, ancho_rel in enumerate(anchos_relativos):
        pos_y= size * 0.09 + paso * i + paso * 0.5
        ancho= size * ancho_rel
        if modo == "izquierda":
            x0= size * 0.11
        elif modo == "derecha":
            x0= size * 0.89 - ancho
        else:
            x0= size * 0.5 - ancho / 2
        pintor.drawLine(QPointF(x0, pos_y), QPointF(x0 + ancho, pos_y))


#Documento con una insignia de "ojo" (vista previa) arriba y un
#lápiz editando apoyado sobre la esquina inferior -para que la pestaña
#"Vista Previa y Edición" comunique de un vistazo sus dos funciones a
#la vez, en vez de un 👁 o un ✏ sueltos que solo cuentan la mitad.
def _archivo_vista_edicion(pintor, size):

    #Hoja de documento con líneas de texto.
    _rect_redondeado(pintor, size, 0.14, 0.06, 0.68, 0.88, "#F8FAFC", radio=0.05, borde="#94A3B8")
    for y in (0.24, 0.36, 0.48, 0.60):
        _linea(pintor, size, 0.22, y, 0.58, y, "#CBD5E1", 1.8)
    #Insignia de "ojo" (vista previa), arriba a la derecha, superpuesta.
    pintor.setBrush(QBrush(QColor("white")))
    pintor.setPen(_pluma("#1D4ED8", 1.8))
    pintor.drawEllipse(_r(size, 0.46, 0.02, 0.98, 0.34))
    pintor.setBrush(QBrush(QColor("#1D4ED8")))
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.drawEllipse(_r(size, 0.66, 0.10, 0.80, 0.26))
    #Lápiz editando, apoyado sobre la esquina inferior derecha de la hoja.
    pintor.save()
    pintor.translate(size * 0.70, size * 0.78)
    pintor.rotate(-40)
    pintor.translate(-size * 0.70, -size * 0.78)
    _rect_redondeado(pintor, size, 0.60, 0.62, 0.80, 0.70, "#FDE047", radio=0.02, borde="#CA8A04")
    _poligono(pintor, size, [(0.60, 0.70), (0.80, 0.70), (0.70, 0.90)], "#B45309")
    _rect_redondeado(pintor, size, 0.60, 0.58, 0.80, 0.63, "#F87171", radio=0.35)
    pintor.restore()


def _papelera(p, size):

    _poligono(p, size, [(0.24, 0.28), (0.76, 0.28), (0.70, 0.90), (0.30, 0.90)], "#94A3B8", borde="#475569")
    _rect_redondeado(p, size, 0.18, 0.20, 0.82, 0.28, "#64748B", radio=0.02)
    _rect_redondeado(p, size, 0.40, 0.10, 0.60, 0.20, "#64748B", radio=0.02)
    for x in (0.40, 0.50, 0.60):
        _linea(p, size, x, 0.38, x, 0.80, "#475569", 1.4)


def _disquete(p, size):

    _rect_redondeado(p, size, 0.14, 0.14, 0.86, 0.86, "#3B82F6", radio=0.08, borde="#1E40AF")
    _rect_redondeado(p, size, 0.30, 0.14, 0.70, 0.36, "#E2E8F0", radio=0.02)
    _rect_redondeado(p, size, 0.58, 0.16, 0.66, 0.30, "#1E293B", radio=0.01)
    _rect_redondeado(p, size, 0.26, 0.52, 0.74, 0.84, "white", radio=0.02)


def _disco_optico(p, size):

    _disco(p, size, 0.10, 0.10, 0.90, 0.90, "#CBD5E1", borde="#64748B")
    _disco(p, size, 0.40, 0.40, 0.60, 0.60, "#94A3B8")
    _disco(p, size, 0.46, 0.46, 0.54, 0.54, "white")


def _campana(p, size, color="#EAB308"):

    _poligono(p, size, [(0.30, 0.70), (0.36, 0.30), (0.5, 0.16), (0.64, 0.30), (0.70, 0.70)], color, borde="#A16207")
    _rect_redondeado(p, size, 0.26, 0.70, 0.74, 0.78, color, radio=0.4)
    _disco(p, size, 0.44, 0.80, 0.56, 0.90, color)


def _ojo(pintor, size, cerrado=False):

    if cerrado:
        #Ojo "tachado" (estilo eye-off): se dibuja el mismo párpado que el ojo abierto pero un poco más comprimido
        #(entrecerrado), y encima una línea diagonal que lo cruza -icono estándar de "contraseña oculta", mucho más
        #reconocible que el simple arco/ceja de antes.
        _poligono(pintor, size, [(0.5, 0.36), (0.88, 0.52), (0.5, 0.68), (0.12, 0.52)],
                  "white", borde="#334155")
        _disco(pintor, size, 0.40, 0.44, 0.60, 0.60, "#94A3B8")
        _disco(pintor, size, 0.47, 0.51, 0.53, 0.57, "#1E293B")
        pintor.setPen(_pluma("#334155", 2.6))
        pintor.drawLine(QPointF(0.12 * size, 0.80 * size), QPointF(0.88 * size, 0.24 * size))
    else:
        _poligono(pintor, size, [(0.5, 0.28), (0.90, 0.5), (0.5, 0.72), (0.10, 0.5)], "white", borde="#334155")
        _disco(pintor, size, 0.38, 0.38, 0.62, 0.62, "#3B82F6")
        _disco(pintor, size, 0.46, 0.46, 0.54, 0.54, "#1E293B")


def _camara(p, size):

    _rect_redondeado(p, size, 0.14, 0.32, 0.86, 0.82, "#334155", radio=0.08)
    _rect_redondeado(p, size, 0.36, 0.20, 0.64, 0.34, "#334155", radio=0.10)
    _disco(p, size, 0.36, 0.42, 0.64, 0.70, "#93C5FD", borde="#1E40AF")
    _disco(p, size, 0.45, 0.51, 0.55, 0.61, "#1E3A8A")
    _disco(p, size, 0.68, 0.38, 0.76, 0.46, "#F87171")


def _eslabon(pintor, size, color="#94A3B8"):

    pintor.setPen(_pluma(color, 4.0))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawRoundedRect(_r(size, 0.12, 0.32, 0.56, 0.62), size * 0.13, size * 0.13)
    pintor.drawRoundedRect(_r(size, 0.44, 0.38, 0.88, 0.68), size * 0.13, size * 0.13)


def _corazon(pintor, size, color="#EF4444"):

    path= QPainterPath()
    s= size
    path.moveTo(0.5 * s, 0.30 * s)
    path.cubicTo(0.5 * s, 0.14 * s, 0.16 * s, 0.14 * s, 0.16 * s, 0.38 * s)
    path.cubicTo(0.16 * s, 0.58 * s, 0.5 * s, 0.80 * s, 0.5 * s, 0.90 * s)
    path.cubicTo(0.5 * s, 0.80 * s, 0.84 * s, 0.58 * s, 0.84 * s, 0.38 * s)
    path.cubicTo(0.84 * s, 0.14 * s, 0.5 * s, 0.14 * s, 0.5 * s, 0.30 * s)
    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_sin_pluma())
    pintor.drawPath(path)


def _bandera(p, size, color="#EF4444"):

    _linea(p, size, 0.22, 0.10, 0.22, 0.90, "#64748B", 2.4)
    _poligono(p, size, [(0.22, 0.14), (0.78, 0.24), (0.22, 0.46)], color)


def _trofeo(pintor, size):

    _rect_redondeado(pintor, size, 0.34, 0.72, 0.66, 0.82, "#CA8A04", radio=0.02)
    _rect_redondeado(pintor, size, 0.26, 0.82, 0.74, 0.90, "#A16207", radio=0.05)
    _poligono(pintor, size, [(0.32, 0.20), (0.68, 0.20), (0.62, 0.60), (0.38, 0.60)], "#FACC15", borde="#CA8A04")
    pintor.setPen(_pluma("#FACC15", 2.6))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(_r(size, 0.06, 0.20, 0.34, 0.46), 90 * 16, 180 * 16)
    pintor.drawArc(_r(size, 0.66, 0.20, 0.94, 0.46), -90 * 16, 180 * 16)


def _diana(p, size):

    _disco(p, size, 0.10, 0.10, 0.90, 0.90, "#EF4444", borde="#7F1D1D")
    _disco(p, size, 0.28, 0.28, 0.72, 0.72, "white")
    _disco(p, size, 0.42, 0.42, 0.58, 0.58, "#EF4444")


def _regla(pintor, size):

    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(-30)
    pintor.translate(-size * 0.5, -size * 0.5)
    _rect_redondeado(pintor, size, 0.12, 0.42, 0.88, 0.58, "#FDE047", radio=0.03, borde="#CA8A04")
    for x in (0.24, 0.36, 0.48, 0.60, 0.72, 0.84):
        _linea(pintor, size, x, 0.42, x, 0.50, "#CA8A04", 1.2)
    pintor.restore()


def _escoba(pintor, size):

    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(20)
    pintor.translate(-size * 0.5, -size * 0.5)
    _rect_redondeado(pintor, size, 0.46, 0.10, 0.54, 0.56, "#A16207", radio=0.3)
    _poligono(pintor, size, [(0.30, 0.56), (0.70, 0.56), (0.80, 0.90), (0.20, 0.90)], "#FDE047", borde="#CA8A04")
    pintor.restore()


def _paleta(pintor, size):

    pintor.setBrush(QBrush(QColor("#F59E0B")))
    pintor.setPen(_pluma("#B45309", 1.4))
    path= QPainterPath()
    path.addEllipse(_r(size, 0.10, 0.20, 0.90, 0.86))
    hueco= QPainterPath()
    hueco.addEllipse(_r(size, 0.56, 0.58, 0.76, 0.80))
    pintor.drawPath(path.subtracted(hueco))
    for cx, cy, c in ((0.30, 0.36, "#EF4444"), (0.50, 0.30, "#3B82F6"),
                      (0.68, 0.38, "#22C55E"), (0.30, 0.58, "#EAB308")):
        _disco(pintor, size, cx - 0.07, cy - 0.07, cx + 0.07, cy + 0.07, c)


def _brujula(p, size):

    _disco(p, size, 0.10, 0.10, 0.90, 0.90, "#E2E8F0", borde="#64748B")
    _poligono(p, size, [(0.5, 0.22), (0.60, 0.5), (0.5, 0.78), (0.40, 0.5)], "#EF4444")
    _disco(p, size, 0.46, 0.46, 0.54, 0.54, "#1E293B")


def _nube(pintor, size, color="#E2E8F0"):

    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_pluma("#94A3B8", 1.2))
    pintor.drawEllipse(_r(size, 0.14, 0.42, 0.50, 0.80))
    pintor.drawEllipse(_r(size, 0.36, 0.28, 0.76, 0.76))
    pintor.drawEllipse(_r(size, 0.56, 0.44, 0.92, 0.80))
    pintor.drawRect(_r(size, 0.24, 0.58, 0.80, 0.80))


def _sol(p, size):

    _disco(p, size, 0.28, 0.28, 0.72, 0.72, "#FBBF24")
    for i in range(8):
        ang= math.pi / 4 * i
        x0, y0= 0.5 + 0.30 * math.cos(ang), 0.5 + 0.30 * math.sin(ang)
        x1, y1= 0.5 + 0.44 * math.cos(ang), 0.5 + 0.44 * math.sin(ang)
        _linea(p, size, x0, y0, x1, y1, "#FBBF24", 2.4)


def _luna(pintor, size):

    path= QPainterPath()
    path.addEllipse(_r(size, 0.16, 0.16, 0.80, 0.80))
    recorte= QPainterPath()
    recorte.addEllipse(_r(size, 0.30, 0.10, 0.94, 0.74))
    pintor.setBrush(QBrush(QColor("#FDE68A")))
    pintor.setPen(_sin_pluma())
    pintor.drawPath(path.subtracted(recorte))


def _telefono(pintor, size, color="#22C55E"):

    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(-45)
    pintor.translate(-size * 0.5, -size * 0.5)
    path= QPainterPath()
    s= size
    path.moveTo(0.20 * s, 0.30 * s)
    path.cubicTo(0.10 * s, 0.40 * s, 0.10 * s, 0.50 * s, 0.20 * s, 0.60 * s)
    path.cubicTo(0.30 * s, 0.50 * s, 0.28 * s, 0.46 * s, 0.34 * s, 0.44 * s)
    path.cubicTo(0.40 * s, 0.42 * s, 0.42 * s, 0.40 * s, 0.44 * s, 0.34 * s)
    path.cubicTo(0.46 * s, 0.28 * s, 0.50 * s, 0.30 * s, 0.60 * s, 0.20 * s)
    path.cubicTo(0.70 * s, 0.10 * s, 0.80 * s, 0.10 * s, 0.90 * s, 0.20 * s)
    path.cubicTo(0.80 * s, 0.30 * s, 0.78 * s, 0.36 * s, 0.70 * s, 0.34 * s)
    path.cubicTo(0.62 * s, 0.32 * s, 0.55 * s, 0.35 * s, 0.50 * s, 0.42 * s)
    path.cubicTo(0.45 * s, 0.48 * s, 0.42 * s, 0.55 * s, 0.44 * s, 0.62 * s)
    path.cubicTo(0.46 * s, 0.68 * s, 0.52 * s, 0.70 * s, 0.62 * s, 0.62 * s)
    path.cubicTo(0.58 * s, 0.72 * s, 0.52 * s, 0.78 * s, 0.42 * s, 0.80 * s)
    path.lineTo(0.20 * s, 0.60 * s)
    path.closeSubpath()
    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_sin_pluma())
    pintor.drawPath(path)
    pintor.restore()


def _escudo(p, size, color="#3B82F6"):

    _poligono(p, size, [(0.5, 0.10), (0.84, 0.22), (0.84, 0.52), (0.5, 0.90), (0.16, 0.52), (0.16, 0.22)],
               color, borde="#1E3A8A")
    _check(p, size, "white", x0=0.34, y0=0.50, x1=0.46, y1=0.62, x2=0.68, y2=0.36, ancho=2.6)


def _impresora(p, size):

    _rect_redondeado(p, size, 0.16, 0.36, 0.84, 0.62, "#64748B", radio=0.06)
    _rect_redondeado(p, size, 0.28, 0.14, 0.72, 0.38, "white", radio=0.02, borde="#94A3B8")
    _rect_redondeado(p, size, 0.28, 0.60, 0.72, 0.90, "white", radio=0.02, borde="#94A3B8")
    _disco(p, size, 0.68, 0.44, 0.74, 0.50, "#22C55E")


def _enchufe(p, size):

    _rect_redondeado(p, size, 0.30, 0.18, 0.70, 0.56, "#1E293B", radio=0.10)
    _linea(p, size, 0.42, 0.10, 0.42, 0.22, "#EAB308", 2.4)
    _linea(p, size, 0.58, 0.10, 0.58, 0.22, "#EAB308", 2.4)
    _rect_redondeado(p, size, 0.40, 0.56, 0.60, 0.86, "#64748B", radio=0.05)


def _lentes(pintor, size):

    pintor.setPen(_pluma("#1E293B", 2.4))
    pintor.setBrush(QBrush(QColor(147, 197, 253, 140)))
    pintor.drawEllipse(_r(size, 0.10, 0.36, 0.42, 0.66))
    pintor.drawEllipse(_r(size, 0.58, 0.36, 0.90, 0.66))
    pintor.drawLine(QPointF(0.42 * size, 0.48 * size), QPointF(0.58 * size, 0.48 * size))


def _maletin(p, size):

    _rect_redondeado(p, size, 0.42, 0.14, 0.58, 0.26, "#78350F", radio=0.02, borde="#78350F")
    _rect_redondeado(p, size, 0.12, 0.26, 0.88, 0.82, "#B45309", radio=0.06, borde="#78350F")
    _rect_redondeado(p, size, 0.44, 0.44, 0.56, 0.56, "#78350F", radio=0.1)
    _linea(p, size, 0.12, 0.44, 0.88, 0.44, "#78350F", 1.4)


def _cohete(pintor, size):

    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(45)
    pintor.translate(-size * 0.5, -size * 0.5)
    _poligono(pintor, size, [(0.5, 0.10), (0.66, 0.50), (0.34, 0.50)], "#EF4444")
    _rect_redondeado(pintor, size, 0.34, 0.46, 0.66, 0.78, "white", radio=0.20, borde="#94A3B8")
    _disco(pintor, size, 0.42, 0.54, 0.58, 0.70, "#3B82F6")
    _poligono(pintor, size, [(0.34, 0.72), (0.22, 0.90), (0.34, 0.84)], "#EF4444")
    _poligono(pintor, size, [(0.66, 0.72), (0.78, 0.90), (0.66, 0.84)], "#EF4444")
    pintor.restore()


def _paquete(p, size):

    _rect_redondeado(p, size, 0.14, 0.28, 0.86, 0.86, "#D6A15A", radio=0.04, borde="#92652A")
    _poligono(p, size, [(0.14, 0.28), (0.5, 0.44), (0.86, 0.28)], "#B9803F", borde="#92652A")
    _linea(p, size, 0.5, 0.44, 0.5, 0.86, "#92652A", 1.4)


def _pantalla(p, size):

    _rect_redondeado(p, size, 0.10, 0.16, 0.90, 0.66, "#334155", radio=0.05)
    _rect_redondeado(p, size, 0.15, 0.21, 0.85, 0.61, "#60A5FA", radio=0.02)
    _rect_redondeado(p, size, 0.40, 0.66, 0.60, 0.76, "#64748B", radio=0.02)
    _rect_redondeado(p, size, 0.26, 0.76, 0.74, 0.84, "#475569", radio=0.03)


def _ventana_app(p, size):

    _rect_redondeado(p, size, 0.12, 0.16, 0.88, 0.84, "#E2E8F0", radio=0.06, borde="#64748B")
    _rect_redondeado(p, size, 0.12, 0.16, 0.88, 0.30, "#3B82F6", radio=0.06)
    for i, cx in enumerate((0.78, 0.70, 0.62)):
        _disco(p, size, cx - 0.02, 0.21, cx + 0.02, 0.25, ("#EF4444", "#EAB308", "#22C55E")[i])


#Balanza de pesas -para el KPI "Módulos con pesos al 100%"- rediseñada
#con platillos RELLENOS en tono dorado/cálido (evoca "peso", como una
#balanza de joyero) en vez de los simples arcos grises de antes, más una
#pequeña insignia verde con un check en la esquina superior para reforzar
#a simple vista la idea de "cuadrado/completo al 100%" que representa
#este KPI -no solo "hay una balanza", sino "la balanza está en su punto".
def _balanza(pintor, size):

    color_cuerpo= "#FCD34D"
    color_borde= "#92400E"
    #Poste vertical y brazo horizontal (el "fiel" de la balanza).
    _linea(pintor, size, 0.5, 0.14, 0.5, 0.74, color_borde, 2.4)
    _linea(pintor, size, 0.20, 0.28, 0.80, 0.28, color_borde, 2.2)
    #Platillos: medias lunas RELLENAS (antes eran solo un arco hueco), colgando de dos hilos cortos desde cada
    #extremo del brazo.
    _linea(pintor, size, 0.18, 0.28, 0.14, 0.42, color_borde, 1.4)
    _linea(pintor, size, 0.24, 0.28, 0.22, 0.42, color_borde, 1.4)
    _linea(pintor, size, 0.76, 0.28, 0.78, 0.42, color_borde, 1.4)
    _linea(pintor, size, 0.82, 0.28, 0.86, 0.42, color_borde, 1.4)
    pintor.setPen(_pluma(color_borde, 1.6))
    pintor.setBrush(QBrush(QColor(color_cuerpo)))
    pintor.drawChord(_r(size, 0.08, 0.40, 0.32, 0.58), 0, -180 * 16)
    pintor.drawChord(_r(size, 0.68, 0.40, 0.92, 0.58), 0, -180 * 16)
    #Base y pie de la balanza.
    _rect_redondeado(pintor, size, 0.42, 0.74, 0.58, 0.84, color_cuerpo, radio=0.15, borde=color_borde)
    _rect_redondeado(pintor, size, 0.32, 0.84, 0.68, 0.90, color_cuerpo, radio=0.25, borde=color_borde)
    #Insignia verde de "check" -el mismo lenguaje visual que ya usa el resto de la app para "completo/correcto"- en
    #la esquina superior.
    _disco(pintor, size, 0.62, 0.04, 0.94, 0.36, "#22C55E", borde="#15803D")
    _check(pintor, size, color="white", x0=0.68, y0=0.19, x1=0.735, y1=0.25, x2=0.865, y2=0.11, ancho=2.0)


#Puerta de salida -para "Cerrar sesión"- con marco, hoja con paneles
#y perilla, más una flecha saliendo hacia afuera: antes era solo un
#rectángulo liso de un color plano (una "puerta" muy genérica, sin
#relieve ni detalle), que a tamaño de icono se leía como una simple
#tarjeta de color. Con marco + paneles + perilla se lee de inmediato
#como una puerta real, y la flecha -el mismo lenguaje visual que usan
#los iconos de "exportar"/"salir" en el resto de la app- deja clara la
#ACCIÓN (salir/cerrar sesión), no solo el objeto.
def _puerta_salida(p, size):

    color_marco= "#78350F"
    color_hoja= "#D97706"
    color_panel= "#B45309"
    #Marco (ligeramente más oscuro y ancho que la hoja, como el vano).
    _rect_redondeado(p, size, 0.20, 0.06, 0.66, 0.94, color_marco, radio=0.03)
    #Hoja de la puerta, inset dentro del marco.
    _rect_redondeado(p, size, 0.24, 0.11, 0.62, 0.89, color_hoja, radio=0.02)
    #Dos paneles rehundidos (detalle clásico de puerta de panel).
    _rect_redondeado(p, size, 0.29, 0.17, 0.57, 0.44, color_panel, radio=0.03, borde=color_marco)
    _rect_redondeado(p, size, 0.29, 0.52, 0.57, 0.79, color_panel, radio=0.03, borde=color_marco)
    #Perilla dorada.
    _disco(p, size, 0.50, 0.47, 0.58, 0.55, "#FDE68A", borde=color_marco)
    #Flecha saliendo del vano hacia afuera -indica la acción de salir-.
    _flecha(p, size, "#EF4444", angulo_deg=0, cx=0.80, cy=0.50, largo=0.16,
            ancho_cabeza= 0.11, grosor=3.0)


def _pieza_rompecabezas(pintor, size, color="#8B5CF6"):

    path= QPainterPath()
    s= size
    path.moveTo(0.20 * s, 0.20 * s)
    path.lineTo(0.46 * s, 0.20 * s)
    path.cubicTo(0.46 * s, 0.10 * s, 0.62 * s, 0.10 * s, 0.62 * s, 0.20 * s)
    path.lineTo(0.80 * s, 0.20 * s)
    path.lineTo(0.80 * s, 0.40 * s)
    path.cubicTo(0.90 * s, 0.40 * s, 0.90 * s, 0.56 * s, 0.80 * s, 0.56 * s)
    path.lineTo(0.80 * s, 0.80 * s)
    path.lineTo(0.56 * s, 0.80 * s)
    path.cubicTo(0.56 * s, 0.90 * s, 0.40 * s, 0.90 * s, 0.40 * s, 0.80 * s)
    path.lineTo(0.20 * s, 0.80 * s)
    path.lineTo(0.20 * s, 0.58 * s)
    path.cubicTo(0.10 * s, 0.58 * s, 0.10 * s, 0.42 * s, 0.20 * s, 0.42 * s)
    path.closeSubpath()
    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_pluma("#5B21B6", 1.2))
    pintor.drawPath(path)


def _menu_hamburguesa(p, size, color="#475569"):

    for y in (0.30, 0.50, 0.70):
        _linea(p, size, 0.16, y, 0.84, y, color, 3.0)


#Grilla de 4 paneles (2x2) de distinto tamaño -icono estándar de
#"panel de control"/"dashboard"-, cada uno en un color distinto para que
#no se confunda con "reportes"/"calificaciones" (que ya usan el gráfico
#de barras 📊).
def _panel_dashboard(p, size):

    _rect_redondeado(p, size, 0.12, 0.12, 0.56, 0.46, "#6366F1", radio=0.10)
    _rect_redondeado(p, size, 0.62, 0.12, 0.88, 0.32, "#22C55E", radio=0.10)
    _rect_redondeado(p, size, 0.62, 0.40, 0.88, 0.60, "#F59E0B", radio=0.10)
    _rect_redondeado(p, size, 0.12, 0.54, 0.88, 0.88, "#0EA5E9", radio=0.10)


def _calendario(p, size, color_top="#EF4444"):

    _rect_redondeado(p, size, 0.14, 0.20, 0.86, 0.88, "white", radio=0.04, borde="#94A3B8")
    _rect_redondeado(p, size, 0.14, 0.20, 0.86, 0.36, color_top, radio=0.04)
    _linea(p, size, 0.30, 0.12, 0.30, 0.26, "#64748B", 2.0)
    _linea(p, size, 0.70, 0.12, 0.70, 0.26, "#64748B", 2.0)
    for fy in (0.48, 0.64, 0.78):
        for fx in (0.28, 0.46, 0.64):
            _disco(p, size, fx, fy, fx + 0.06, fy + 0.06, "#CBD5E1")


def _reloj(p, size):

    _disco(p, size, 0.12, 0.12, 0.88, 0.88, "white", borde="#334155")
    _linea(p, size, 0.5, 0.5, 0.5, 0.26, "#334155", 2.2)
    _linea(p, size, 0.5, 0.5, 0.68, 0.56, "#334155", 2.2)
    _disco(p, size, 0.47, 0.47, 0.53, 0.53, "#EF4444")


#Reloj de arena para estados de 'cargando/procesando' -reemplazo del
#emoji ⏳, con la misma silueta reconocible (dos triángulos) pero en el
#trazo plano y monocromo-de-acento de esta librería.
def _reloj_arena(p, size, color_marco="#94A3B8", color_arena="#F59E0B"):

    marco_sup= [(0.24, 0.10), (0.76, 0.10), (0.76, 0.16), (0.24, 0.16)]
    marco_inf= [(0.24, 0.84), (0.76, 0.84), (0.76, 0.90), (0.24, 0.90)]
    _poligono(p, size, marco_sup, color_marco)
    _poligono(p, size, marco_inf, color_marco)
    cuerpo= [(0.28, 0.16), (0.72, 0.16), (0.52, 0.5), (0.72, 0.84), (0.28, 0.84), (0.48, 0.5)]
    _poligono(p, size, cuerpo, "white", borde=color_marco)
    arena_arriba= [(0.5, 0.5), (0.40, 0.28), (0.60, 0.28)]
    arena_abajo= [(0.5, 0.5), (0.38, 0.78), (0.62, 0.78)]
    _poligono(p, size, arena_arriba, color_arena)
    _poligono(p, size, arena_abajo, color_arena)


def _grafico_barras(p, size):

    colores= ("#3B82F6", "#22C55E", "#F59E0B")
    alturas= (0.42, 0.62, 0.30)
    for i, (c, h) in enumerate(zip(colores, alturas)):
        x0= 0.18 + i * 0.26
        _rect_redondeado(p, size, x0, 0.86 - h, x0 + 0.18, 0.86, c, radio=0.02)
    _linea(p, size, 0.12, 0.86, 0.90, 0.86, "#64748B", 1.6)


def _grafico_lineas(pintor, size, color="#22C55E"):

    pintor.setPen(_pluma(color, 2.4))
    puntos= [(0.14, 0.74), (0.36, 0.54), (0.56, 0.64), (0.80, 0.24)]
    for i in range(len(puntos) - 1):
        pintor.drawLine(QPointF(puntos[i][0] * size, puntos[i][1] * size),
                   QPointF(puntos[i + 1][0] * size, puntos[i + 1][1] * size))
    _poligono(pintor, size, [(0.80, 0.24), (0.70, 0.24), (0.80, 0.10)], color)


def _sobre(p, size):

    _rect_redondeado(p, size, 0.12, 0.24, 0.88, 0.76, "white", radio=0.04, borde="#3B82F6")
    _poligono(p, size, [(0.12, 0.26), (0.5, 0.54), (0.88, 0.26)], None if False else "#93C5FD", borde="#3B82F6")


#Bandeja abierta con una flecha vertical: hacia_abajo=True es
#"Importar" (la flecha entra a la bandeja), False es "Exportar" (la
#flecha sale de la bandeja). A propósito NO es un sobre de correo -para
#que "Importar/Exportar datos" deje de confundirse visualmente con
#"Enviar un correo", que es lo que pasaba al reutilizar 📤/📥 (basados
#en _sobre) para ambos significados en toda la app.
def _bandeja_flecha(pintor, size, color, hacia_abajo=True):

    pintor.setPen(_pluma(color, 2.6))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    bandeja= QPainterPath()
    bandeja.moveTo(0.16 * size, 0.60 * size)
    bandeja.lineTo(0.16 * size, 0.84 * size)
    bandeja.lineTo(0.84 * size, 0.84 * size)
    bandeja.lineTo(0.84 * size, 0.60 * size)
    pintor.drawPath(bandeja)
    if hacia_abajo:
        pintor.drawLine(QPointF(0.5 * size, 0.12 * size), QPointF(0.5 * size, 0.52 * size))
        _poligono(pintor, size, [(0.32, 0.38), (0.68, 0.38), (0.5, 0.60)], color)
    else:
        pintor.drawLine(QPointF(0.5 * size, 0.58 * size), QPointF(0.5 * size, 0.18 * size))
        _poligono(pintor, size, [(0.32, 0.32), (0.68, 0.32), (0.5, 0.10)], color)


#"Importar": flecha entrando a una bandeja, en el MISMO azul que
#"Exportar" (antes era verde; ahora ambos comparten color porque son la
#misma familia de acción -mover datos-, y solo el sentido de la flecha
#distingue una de otra).
def _icono_importar(p, size):

    _bandeja_flecha(p, size, "#3B82F6", hacia_abajo=True)


#"Exportar": flecha saliendo de una bandeja, en azul (igual espíritu
#de color que ya usaba la flecha de 📤 antes de este cambio).
def _icono_exportar(p, size):

    _bandeja_flecha(p, size, "#3B82F6", hacia_abajo=False)


def _pin_ubicacion(pintor, size, color="#EF4444"):

    path= QPainterPath()
    s= size
    path.moveTo(0.5 * s, 0.90 * s)
    path.cubicTo(0.5 * s, 0.90 * s, 0.80 * s, 0.58 * s, 0.80 * s, 0.38 * s)
    path.cubicTo(0.80 * s, 0.20 * s, 0.66 * s, 0.10 * s, 0.5 * s, 0.10 * s)
    path.cubicTo(0.34 * s, 0.10 * s, 0.20 * s, 0.20 * s, 0.20 * s, 0.38 * s)
    path.cubicTo(0.20 * s, 0.58 * s, 0.5 * s, 0.90 * s, 0.5 * s, 0.90 * s)
    path.closeSubpath()
    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_sin_pluma())
    pintor.drawPath(path)
    _disco(pintor, size, 0.40, 0.28, 0.60, 0.48, "white")


def _mapa(p, size):

    _poligono(p, size, [(0.10, 0.20), (0.36, 0.12), (0.64, 0.20), (0.90, 0.12), (0.90, 0.80),
                        (0.64, 0.88), (0.36, 0.80), (0.10, 0.88)], "#BBF7D0", borde="#15803D")
    _linea(p, size, 0.36, 0.12, 0.36, 0.80, "#15803D", 1.2)
    _linea(p, size, 0.64, 0.20, 0.64, 0.88, "#15803D", 1.2)
    _pin_ubicacion(p, size, "#EF4444")


def _semaforo(p, size):

    _rect_redondeado(p, size, 0.32, 0.10, 0.68, 0.90, "#1E293B", radio=0.10)
    for cy, c in zip((0.26, 0.50, 0.74), ("#EF4444", "#EAB308", "#22C55E")):
        _disco(p, size, 0.40, cy - 0.08, 0.60, cy + 0.08, c)


def _prohibido(pintor, size):

    _disco(pintor, size, 0.10, 0.10, 0.90, 0.90, "#EF4444", borde="#7F1D1D")
    pintor.setPen(_pluma("white", 3.2))
    pintor.drawLine(QPointF(0.26 * size, 0.26 * size), QPointF(0.74 * size, 0.74 * size))


def _construccion(p, size):

    for i, x0 in enumerate((0.10, 0.30, 0.50, 0.70)):
        color= "#FBBF24" if i % 2 == 0 else "#1E293B"
        _rect_redondeado(p, size, x0, 0.40, x0 + 0.20, 0.56, color, radio=0.0)


def _chispas(p, size, color="#FBBF24"):

    _estrella(p, size, 0.36, 0.16, 0.64, 0.44, color, puntas=4)
    _estrella(p, size, 0.10, 0.52, 0.34, 0.76, color, puntas=4)
    _estrella(p, size, 0.60, 0.56, 0.90, 0.86, color, puntas=4)


def _gota(pintor, size, color="#3B82F6"):

    path= QPainterPath()
    s= size
    path.moveTo(0.5 * s, 0.12 * s)
    path.cubicTo(0.72 * s, 0.42 * s, 0.82 * s, 0.58 * s, 0.82 * s, 0.68 * s)
    path.cubicTo(0.82 * s, 0.82 * s, 0.68 * s, 0.90 * s, 0.5 * s, 0.90 * s)
    path.cubicTo(0.32 * s, 0.90 * s, 0.18 * s, 0.82 * s, 0.18 * s, 0.68 * s)
    path.cubicTo(0.18 * s, 0.58 * s, 0.28 * s, 0.42 * s, 0.5 * s, 0.12 * s)
    pintor.setBrush(QBrush(QColor(color)))
    pintor.setPen(_sin_pluma())
    pintor.drawPath(path)


def _cerebro(pintor, size, color="#F472B6"):

    _disco(pintor, size, 0.14, 0.20, 0.54, 0.68, color, borde="#BE185D")
    _disco(pintor, size, 0.46, 0.20, 0.86, 0.68, color, borde="#BE185D")
    pintor.setPen(_pluma("#BE185D", 1.0))
    pintor.drawLine(QPointF(0.30 * size, 0.32 * size), QPointF(0.40 * size, 0.42 * size))
    pintor.drawLine(QPointF(0.60 * size, 0.32 * size), QPointF(0.70 * size, 0.42 * size))


def _sonrisa(pintor, size, color="#FBBF24"):

    _disco(pintor, size, 0.10, 0.10, 0.90, 0.90, color, borde="#B45309")
    _disco(pintor, size, 0.32, 0.38, 0.40, 0.46, "#1E293B")
    _disco(pintor, size, 0.60, 0.38, 0.68, 0.46, "#1E293B")
    pintor.setPen(_pluma("#1E293B", 2.2))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(_r(size, 0.30, 0.46, 0.70, 0.76), 200 * 16, 140 * 16)


def _manos_saludo(p, size):

    _rect_redondeado(p, size, 0.10, 0.40, 0.48, 0.62, "#F59E0B", radio=0.3)
    _rect_redondeado(p, size, 0.52, 0.40, 0.90, 0.62, "#FBBF24", radio=0.3)
    _disco(p, size, 0.40, 0.42, 0.60, 0.60, "#F59E0B")


def _tijeras(pintor, size):

    pintor.setPen(_pluma("#94A3B8", 3.0))
    pintor.drawLine(QPointF(0.20 * size, 0.20 * size), QPointF(0.80 * size, 0.80 * size))
    pintor.drawLine(QPointF(0.80 * size, 0.20 * size), QPointF(0.20 * size, 0.80 * size))
    _disco(pintor, size, 0.14, 0.14, 0.28, 0.28, "#EF4444")
    _disco(pintor, size, 0.14, 0.72, 0.28, 0.86, "#3B82F6")


#Icono para los botones de 'Elegir y Recortar' Foto/Logotipo/Firma:
#la miniatura de imagen (mismo dibujo que 🖼: marco, sol y montaña) con
#unas tijeras chiquitas superpuestas en la esquina inferior derecha,
#para distinguirlo de un botón de solo "ver" o solo "recortar" -es
#ambas cosas en un solo icono, como pide la acción real del botón.
def _foto_recortar(pintor, size):

    #Marco de imagen, un poco más chico y desplazado a la izquierda/arriba para dejarle espacio a la insignia de
    #tijeras sin que se encimen.
    _rect_redondeado(pintor, size, 0.06, 0.10, 0.78, 0.72, "white", radio=0.05, borde="#94A3B8")
    _disco(pintor, size, 0.16, 0.20, 0.30, 0.34, "#FBBF24")
    _poligono(pintor, size, [(0.12, 0.64), (0.34, 0.40), (0.50, 0.54), (0.64, 0.36), (0.72, 0.64)], "#22C55E")
    #Insignia circular con las tijeras, en la esquina inferior derecha (mismo tratamiento visual que otros iconos
    #"compuestos" de la app,
    #p.ej. 📝 = documento + lápiz).
    _disco(pintor, size, 0.52, 0.52, 0.96, 0.96, "white", borde="#CBD5E1")
    cx0, cy0, cx1, cy1= 0.58, 0.58, 0.90, 0.90
    pintor.setPen(_pluma("#64748B", 2.0))
    pintor.drawLine(QPointF((cx0 + 0.10) * size, (cy0 + 0.06) * size), QPointF((cx1 - 0.06) * size, (cy1 - 0.10) * size))
    pintor.drawLine(QPointF((cx1 - 0.06) * size, (cy0 + 0.06) * size), QPointF((cx0 + 0.10) * size, (cy1 - 0.10) * size))
    _disco(pintor, size, cx0 + 0.02, cy0 + 0.02, cx0 + 0.12, cy0 + 0.12, "#EF4444")
    _disco(pintor, size, cx0 + 0.02, cy1 - 0.12, cx0 + 0.12, cy1 - 0.02, "#3B82F6")


def _dividir(p, size, color="#475569"):

    _linea(p, size, 0.22, 0.5, 0.78, 0.5, color, 2.6)
    _disco(p, size, 0.46, 0.24, 0.54, 0.32, color)
    _disco(p, size, 0.46, 0.68, 0.54, 0.76, color)


def _control_deslizante(p, size):

    _linea(p, size, 0.16, 0.5, 0.84, 0.5, "#94A3B8", 3.0)
    _disco(p, size, 0.44, 0.36, 0.60, 0.64, "#3B82F6", borde="#1E40AF")


#Cuatro escuadras en las esquinas apuntando hacia afuera: mismo icono
#'expandir/pantalla completa' de cualquier reproductor de video, hecho a
#mano como el resto (nada de glifo crudo de la fuente del sistema).
def _pantalla_completa(p, size, color="#475569"):

    largo= 0.22
    grosor= 2.4
    _linea(p, size, 0.14, 0.14, 0.14 + largo, 0.14, color, grosor)
    _linea(p, size, 0.14, 0.14, 0.14, 0.14 + largo, color, grosor)
    _linea(p, size, 0.86, 0.14, 0.86 - largo, 0.14, color, grosor)
    _linea(p, size, 0.86, 0.14, 0.86, 0.14 + largo, color, grosor)
    _linea(p, size, 0.14, 0.86, 0.14 + largo, 0.86, color, grosor)
    _linea(p, size, 0.14, 0.86, 0.14, 0.86 - largo, color, grosor)
    _linea(p, size, 0.86, 0.86, 0.86 - largo, 0.86, color, grosor)
    _linea(p, size, 0.86, 0.86, 0.86, 0.86 - largo, color, grosor)


def _flecha_abajo_pequena(p, size, color="#475569"):

    _poligono(p, size, [(0.30, 0.38), (0.70, 0.38), (0.5, 0.66)], color)


def _tarjeta_indice(p, size):

    _rect_redondeado(p, size, 0.12, 0.20, 0.80, 0.80, "white", radio=0.04, borde="#94A3B8")
    _rect_redondeado(p, size, 0.30, 0.14, 0.88, 0.74, "#93C5FD", radio=0.04, borde="#1E40AF")
    for y in (0.34, 0.46, 0.58):
        _linea(p, size, 0.42, y, 0.76, y, "#1E3A8A", 1.4)


def _fuente_texto(pintor, size, color="#334155"):

    pintor.setPen(_pluma(color, 2.4))
    pintor.drawLine(QPointF(0.24 * size, 0.80 * size), QPointF(0.5 * size, 0.20 * size))
    pintor.drawLine(QPointF(0.5 * size, 0.20 * size), QPointF(0.76 * size, 0.80 * size))
    pintor.drawLine(QPointF(0.34 * size, 0.60 * size), QPointF(0.66 * size, 0.60 * size))


def _explosion(p, size, color="#F97316"):

    _estrella(p, size, 0.10, 0.10, 0.90, 0.90, color, puntas=8)
    _estrella(p, size, 0.26, 0.26, 0.74, 0.74, "#FDE047", puntas=6)


def _reciclaje(p, size, color="#22C55E"):

    _flechas_circulares(p, size, color, "#16A34A")


def _pergamino(p, size):

    _rect_redondeado(p, size, 0.18, 0.18, 0.82, 0.82, "#FDE68A", radio=0.02, borde="#B45309")
    for y in (0.34, 0.48, 0.62):
        _linea(p, size, 0.28, y, 0.72, y, "#B45309", 1.4)
    _disco(p, size, 0.14, 0.16, 0.24, 0.26, "#FDE68A", borde="#B45309")
    _disco(p, size, 0.14, 0.74, 0.24, 0.84, "#FDE68A", borde="#B45309")


def _archivador(p, size):

    _rect_redondeado(p, size, 0.14, 0.14, 0.86, 0.86, "#94A3B8", radio=0.05, borde="#475569")
    for y in (0.30, 0.50, 0.70):
        _rect_redondeado(p, size, 0.20, y, 0.80, y + 0.10, "#CBD5E1", radio=0.02)
        _rect_redondeado(p, size, 0.44, y + 0.02, 0.56, y + 0.08, "#475569", radio=0.02)


def _tubo_ensayo(pintor, size):

    pintor.save()
    pintor.setBrush(QBrush(QColor("#E2E8F0")))
    pintor.setPen(_pluma("#94A3B8", 1.6))
    path= QPainterPath()
    s= size
    path.moveTo(0.40 * s, 0.10 * s)
    path.lineTo(0.40 * s, 0.62 * s)
    path.cubicTo(0.40 * s, 0.82 * s, 0.60 * s, 0.82 * s, 0.60 * s, 0.62 * s)
    path.lineTo(0.60 * s, 0.10 * s)
    pintor.drawPath(path)
    _linea(pintor, size, 0.34, 0.10, 0.66, 0.10, "#94A3B8", 2.4)
    liquido= QPainterPath()
    liquido.moveTo(0.40 * s, 0.50 * s)
    liquido.lineTo(0.40 * s, 0.62 * s)
    liquido.cubicTo(0.40 * s, 0.82 * s, 0.60 * s, 0.82 * s, 0.60 * s, 0.62 * s)
    liquido.lineTo(0.60 * s, 0.50 * s)
    pintor.setBrush(QBrush(QColor("#22C55E")))
    pintor.setPen(_sin_pluma())
    pintor.drawPath(liquido)
    for cx, cy in ((0.46, 0.66), (0.54, 0.72), (0.50, 0.58)):
        _disco(pintor, size, cx - 0.02, cy - 0.02, cx + 0.02, cy + 0.02, "#BBF7D0")
    pintor.restore()


def _clip_tablero(p, size):

    _rect_redondeado(p, size, 0.16, 0.16, 0.84, 0.88, "#E2E8F0", radio=0.05, borde="#64748B")
    _rect_redondeado(p, size, 0.38, 0.10, 0.62, 0.22, "#94A3B8", radio=0.10)
    for y in (0.36, 0.50, 0.64, 0.76):
        _linea(p, size, 0.28, y, 0.72, y, "#64748B", 1.6)


#Iconos nuevos -profesor, estudiante en riesgo, secciones/grupos, copia de seguridad, auditoría y tutorial-
#pensados para reemplazar glifos genéricos (👥, 🏫, 🚨, ➕, 📇...) que no comunicaban bien su significado específico
#dentro de AcaDeXI.
#Docente de pie, con corbata, señalando con un puntero una pizarra con
#apuntes -pensado para leerse claramente como "una persona dando clase",
#a diferencia del intento anterior (una ficha de color junto a un
#rectángulo) que no se distinguía de un bloque abstracto.
def _profesor(p, size, color="#0D9488"):

    #Patas del atril de la pizarra.
    _linea(p, size, 0.60, 0.86, 0.60, 0.94, "#94A3B8", 1.6)
    _linea(p, size, 0.90, 0.86, 0.90, 0.94, "#94A3B8", 1.6)
    #Pizarra con líneas de apuntes.
    _rect_redondeado(p, size, 0.52, 0.16, 0.96, 0.62, "#F8FAFC", radio=0.05, borde="#94A3B8")
    _linea(p, size, 0.58, 0.28, 0.84, 0.28, color, 2.0)
    _linea(p, size, 0.58, 0.38, 0.90, 0.38, color, 2.0)
    _linea(p, size, 0.58, 0.48, 0.76, 0.48, color, 2.0)
    #Cabeza (tono piel) y torso (camisa/blazer del color de la tarjeta).
    _disco(p, size, 0.06, 0.14, 0.32, 0.40, "#F2C185", borde="#C9925A")
    _poligono(p, size, [(0.02, 0.94), (0.08, 0.50), (0.30, 0.50), (0.36, 0.94)], color, borde="#0F766E")
    #Cuello de camisa (triángulo blanco) + corbata, para que se lea como "vestimenta formal" y no un bulto de color
    #liso.
    _poligono(p, size, [(0.13, 0.50), (0.25, 0.50), (0.19, 0.58)], "white")
    _poligono(p, size, [(0.17, 0.50), (0.21, 0.50), (0.20, 0.62), (0.19, 0.84), (0.18, 0.62)], "#B91C1C")
    #Brazo extendido sosteniendo el puntero hacia la pizarra.
    _linea(p, size, 0.29, 0.58, 0.48, 0.50, color, 3.4)
    _disco(p, size, 0.455, 0.475, 0.505, 0.525, "#F2C185")
    _linea(p, size, 0.50, 0.50, 0.64, 0.44, "#334155", 2.2)


#Estudiante con una insignia de alerta (triángulo con exclamación)
#superpuesta -deja claro que se trata de una PERSONA en riesgo académico,
#a diferencia del genérico 🚨 (sirena), que no lo comunicaba.
def _estudiante_riesgo(pintor, size):

    pintor.save()
    pintor.translate(-0.06 * size, 0.03 * size)
    pintor.scale(0.84, 0.84)
    _persona(pintor, size, 1, "#3B82F6")
    pintor.restore()
    _disco(pintor, size, 0.58, 0.02, 0.98, 0.42, "white")
    _poligono(pintor, size, [(0.78, 0.08), (0.95, 0.38), (0.61, 0.38)], "#EF4444", borde="#7F1D1D")
    pintor.setPen(_pluma("white", 2.0))
    pintor.drawLine(QPointF(0.78 * size, 0.19 * size), QPointF(0.78 * size, 0.29 * size))
    _disco(pintor, size, 0.765, 0.32, 0.795, 0.35, "white")


#Varias fichas de curso superpuestas, cada una con su propio
#'grupo' de estudiantes -para 'Secciones/Grupos'-, en vez del edificio
#de escuela (🏫) que se confundía con 'Institución'.
def _secciones_grupos(p, size):

    _rect_redondeado(p, size, 0.08, 0.34, 0.46, 0.64, "#FDE68A", radio=0.08, borde="#B45309")
    _rect_redondeado(p, size, 0.30, 0.16, 0.68, 0.46, "#FCD34D", radio=0.08, borde="#B45309")
    _rect_redondeado(p, size, 0.54, 0.38, 0.92, 0.68, "#F59E0B", radio=0.08, borde="#92400E")
    for cx, cy, col in ((0.27, 0.49, "#92400E"), (0.49, 0.31, "#92400E"), (0.73, 0.53, "white")):
        _disco(p, size, cx - 0.035, cy - 0.035, cx + 0.035, cy + 0.035, col)


#Carpeta con una flecha circular -una copia que se guarda y se puede
#restaurar-, distinta tanto del disquete genérico (💾, 'Guardar') como
#del escudo genérico (🛡, 'Seguridad').
def _copia_seguridad(pintor, size):

    _rect_redondeado(pintor, size, 0.12, 0.28, 0.46, 0.36, "#0369A1", radio=0.03)
    _rect_redondeado(pintor, size, 0.12, 0.34, 0.88, 0.86, "#0EA5E9", radio=0.06, borde="#075985")
    rect= _r(size, 0.32, 0.42, 0.68, 0.78)
    pintor.setPen(_pluma("white", 2.6))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(rect, 20 * 16, 300 * 16)
    _poligono(pintor, size, [(0.68, 0.42), (0.77, 0.47), (0.65, 0.56)], "white")


#Hoja de registro con una lupa como insignia -para 'Auditoría'-,
#distinta del portapapeles genérico (📋) y de la ficha (📇) que se
#usaban antes para esta pantalla.
def _auditoria(pintor, size):

    _rect_redondeado(pintor, size, 0.14, 0.10, 0.72, 0.82, "#E2E8F0", radio=0.05, borde="#64748B")
    for y in (0.26, 0.38, 0.50, 0.62):
        _linea(pintor, size, 0.22, y, 0.64, y, "#64748B", 1.6)
    pintor.setBrush(QBrush(QColor("white")))
    pintor.setPen(_pluma("#0EA5E9", 2.4))
    pintor.drawEllipse(_r(size, 0.52, 0.56, 0.86, 0.90))
    pintor.setPen(_pluma("#0369A1", 2.6))
    pintor.drawLine(QPointF(0.80 * size, 0.80 * size), QPointF(0.93 * size, 0.93 * size))


#Libro abierto con una bombilla de idea encima -para 'Tutorial'-,
#distinta del gorro de graduación (dentro de 🎓) y de la bombilla sola
#(💡, ideas genéricas).
def _tutorial_guia(p, size):

    _libro(p, size, color="#8B5CF6", color_borde="#5B21B6")
    _disco(p, size, 0.40, 0.02, 0.60, 0.20, "#FDE047", borde="#CA8A04")
    _linea(p, size, 0.46, 0.20, 0.46, 0.26, "#94A3B8", 1.6)
    _linea(p, size, 0.54, 0.20, 0.54, 0.26, "#94A3B8", 1.6)


#Nota/justificante: una hoja con líneas de texto y un sello circular
#de "aprobado" en la esquina -para el estado de asistencia 'Excusado',
#que es justo eso: una ausencia con una nota/justificación aceptada.
#Distinto tanto del check verde genérico (Presente) como de cualquier
#documento neutro (📄).
def _excusa_justificante(pintor, size):

    _rect_redondeado(pintor, size, 0.14, 0.06, 0.72, 0.86, "#EFF6FF", radio=0.05, borde="#93C5FD")
    for y in (0.22, 0.34, 0.46, 0.58, 0.68):
        ancho_x1= 0.58 if y != 0.68 else 0.44
        _linea(pintor, size, 0.22, y, ancho_x1, y, "#93C5FD", 1.6)
    #Sello/ribete circular de "aceptado", superpuesto en la esquina inferior derecha.
    _disco(pintor, size, 0.52, 0.54, 0.98, 1.00, "#3B82F6", borde="#1D4ED8")
    pintor.setPen(_pluma("white", 2.0))
    pintor.drawLine(QPointF(0.63 * size, 0.77 * size), QPointF(0.72 * size, 0.86 * size))
    pintor.drawLine(QPointF(0.72 * size, 0.86 * size), QPointF(0.89 * size, 0.68 * size))


#Cruz médica clásica sobre una placa redondeada -para 'Licencia
#Médica'-, en el morado propio de este estado (para no confundirse con
#la cruz roja de emergencias/errores que ya usa la app en otros lados).
def _licencia_medica(p, size):

    _rect_redondeado(p, size, 0.08, 0.08, 0.92, 0.92, "#8B5CF6", radio=0.22, borde="#5B21B6")
    _rect_redondeado(p, size, 0.42, 0.20, 0.58, 0.80, "white", radio=0.04)
    _rect_redondeado(p, size, 0.20, 0.42, 0.80, 0.58, "white", radio=0.04)


#Mano abierta levantada -el gesto universal de "pedir/tener permiso"-
#en vez de una llave (que remite a contraseñas/acceso, no a un permiso
#de ausencia). Palma y dedos en tono piel con un pequeño distintivo
#cian (el color propio de este estado) en la muñeca.
def _permiso_mano(p, size):

    #Muñeca / brazalete distintivo (color del estado).
    _rect_redondeado(p, size, 0.30, 0.80, 0.72, 0.96, "#06B6D4", radio=0.10, borde="#0E7490")
    #Palma.
    _rect_redondeado(p, size, 0.28, 0.52, 0.74, 0.86, "#F2C185", radio=0.16, borde="#C9925A")
    #Dedos (rectángulos redondeados de distinto largo, el del medio más alto).
    _rect_redondeado(p, size, 0.30, 0.30, 0.42, 0.58, "#F2C185", radio=0.10, borde="#C9925A")
    _rect_redondeado(p, size, 0.43, 0.16, 0.55, 0.58, "#F2C185", radio=0.10, borde="#C9925A")
    _rect_redondeado(p, size, 0.56, 0.20, 0.68, 0.58, "#F2C185", radio=0.10, borde="#C9925A")
    #Pulgar, apenas separado hacia el costado.
    _poligono(p, size, [(0.28, 0.60), (0.16, 0.50), (0.16, 0.40), (0.26, 0.48), (0.30, 0.60)],
              "#F2C185", borde="#C9925A")


#Dos eslabones entrelazados en diagonal -para acciones de
#"Vincular"- pensado a propósito para que no se confunda con el
#eslabón gris neutro y plano que ya existe para 🔗 (enlaces web/genéricos):
#aquí cada eslabón tiene su propio color (índigo y celeste), con un
#pequeño brillo/resalte para dar sensación de profundidad y de que
#"encajan" entre sí, en vez de dos rectángulos superpuestos sin más.
def _vinculacion(pintor, size):

    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(-35)
    pintor.translate(-size * 0.5, -size * 0.5)
    pintor.setPen(_pluma("#3730A3", 3.6))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawRoundedRect(_r(size, 0.16, 0.32, 0.56, 0.60), size * 0.14, size * 0.14)
    pintor.setPen(_pluma("#4F46E5", 6.2))
    pintor.drawRoundedRect(_r(size, 0.16, 0.32, 0.56, 0.60), size * 0.14, size * 0.14)
    pintor.restore()
    pintor.save()
    pintor.translate(size * 0.5, size * 0.5)
    pintor.rotate(-35)
    pintor.translate(-size * 0.5, -size * 0.5)
    pintor.setPen(_pluma("#0369A1", 3.6))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawRoundedRect(_r(size, 0.44, 0.40, 0.84, 0.68), size * 0.14, size * 0.14)
    pintor.setPen(_pluma("#38BDF8", 6.2))
    pintor.drawRoundedRect(_r(size, 0.44, 0.40, 0.84, 0.68), size * 0.14, size * 0.14)
    pintor.restore()
    #Pequeño brillo blanco sobre cada eslabón, para que se lean como piezas "sólidas" y no como simples trazos.
    pintor.setPen(_pluma("white", 1.6))
    pintor.drawLine(QPointF(0.28 * size, 0.38 * size), QPointF(0.40 * size, 0.34 * size))
    pintor.drawLine(QPointF(0.58 * size, 0.48 * size), QPointF(0.70 * size, 0.44 * size))


#Tarjeta de boletín con una barra de progreso ascendente encima -para
#"Boletín / Promedios"-, distinta tanto del documento genérico (📄)
#como del gráfico de tendencia suelto (📈, que ya usan otras pestañas
#de calificaciones).
def _boletin_promedios(p, size):

    _rect_redondeado(p, size, 0.12, 0.10, 0.88, 0.90, "#F8FAFC", radio=0.08, borde="#94A3B8")
    _rect_redondeado(p, size, 0.12, 0.10, 0.88, 0.30, "#3B82F6", radio=0.08)
    _rect_redondeado(p, size, 0.12, 0.22, 0.88, 0.30, "#3B82F6", radio=0.0)
    for y in (0.42, 0.54):
        _linea(p, size, 0.22, y, 0.62, y, "#CBD5E1", 2.0)
    #Barritas ascendentes ("promedios"), la última resaltada en verde.
    _rect_redondeado(p, size, 0.22, 0.72, 0.34, 0.82, "#94A3B8", radio=0.02)
    _rect_redondeado(p, size, 0.38, 0.66, 0.50, 0.82, "#94A3B8", radio=0.02)
    _rect_redondeado(p, size, 0.54, 0.58, 0.66, 0.82, "#94A3B8", radio=0.02)
    _rect_redondeado(p, size, 0.70, 0.48, 0.82, 0.82, "#22C55E", radio=0.02)


#Banderín de "marcador de seguimiento" con un reloj de arena encima
#-para "Seguimiento (RP / Incompletos)"-: comunica de un vistazo "algo
#marcado, pendiente de resolver con el tiempo", distinto de la campana
#de recordatorios genérica (🔔) y de la alerta roja de "Ausencia" (❌).
def _seguimiento_rp(pintor, size):

    _linea(pintor, size, 0.26, 0.10, 0.26, 0.92, "#64748B", 2.6)
    _poligono(pintor, size, [(0.26, 0.14), (0.80, 0.24), (0.26, 0.46)], "#F97316", borde="#C2410C")
    pintor.setBrush(QBrush(QColor("#FDE68A")))
    pintor.setPen(_pluma("#B45309", 1.8))
    pintor.drawEllipse(_r(size, 0.44, 0.56, 0.86, 0.98))
    cx, cy= 0.65 * size, 0.77 * size
    pintor.drawLine(QPointF(cx, cy), QPointF(cx, cy - 0.13 * size))
    pintor.drawLine(QPointF(cx, cy), QPointF(cx + 0.09 * size, cy))


#Bandera a cuadros de meta -para "Evaluaciones Finales"-: transmite
#"recta final/cierre" de un vistazo, muy distinta del gráfico de barras
#genérico (📊) que ya usan las evaluaciones parciales en otras pestañas.
def _evaluaciones_finales(pintor, size):

    _linea(pintor, size, 0.24, 0.08, 0.24, 0.92, "#64748B", 2.8)
    pintor.setPen(_sin_pluma())
    ancho, alto= 0.56, 0.34
    x0, y0= 0.24, 0.12
    filas, columnas= 4, 6
    cw, ch= ancho / columnas, alto / filas
    for fila in range(filas):
        for col in range(columnas):
            oscuro= (fila + col) % 2 == 0
            color= "#1E293B" if oscuro else "#F8FAFC"
            _rect_redondeado(pintor, size, x0 + col * cw, y0 + fila * ch,
                              x0 + (col + 1) * cw, y0 + (fila + 1) * ch, color, radio=0.0)


#Libro abierto con una insignia/medallón encima -para "Currículo
#(CE)"-: el libro representa el plan curricular en sí, y el medallón
#(con una marca de verificación) representa las Competencias
#Específicas evaluadas contra ese currículo. Distinto del gorro de
#graduación (dentro de 🎓, para "estudiante").
def _curriculo_ce(pintor, size):

    _libro(pintor, size, color="#0EA5E9", color_borde="#075985")
    _disco(pintor, size, 0.36, 0.02, 0.64, 0.30, "#FACC15", borde="#CA8A04")
    pintor.setPen(_pluma("#78350F", 2.2))
    pintor.drawLine(QPointF(0.44 * size, 0.16 * size), QPointF(0.49 * size, 0.22 * size))
    pintor.drawLine(QPointF(0.49 * size, 0.22 * size), QPointF(0.58 * size, 0.10 * size))


#Lista de verificación (rúbrica) con una marca de estrella al final
#-para "Notas por Competencia"-: cada renglón con su propio check
#representa una competencia evaluada individualmente, distinto tanto
#del boletín consolidado como de la bandera de evaluaciones finales.
def _notas_competencia(pintor, size):

    _rect_redondeado(pintor, size, 0.14, 0.08, 0.86, 0.92, "#F8FAFC", radio=0.06, borde="#94A3B8")
    for y in (0.24, 0.42, 0.60):
        _disco(pintor, size, 0.22, y - 0.05, 0.32, y + 0.05, "#22C55E")
        pintor.setPen(_pluma("white", 1.6))
        pintor.drawLine(QPointF(0.245 * size, y * size), QPointF(0.27 * size, (y + 0.03) * size))
        pintor.drawLine(QPointF(0.27 * size, (y + 0.03) * size), QPointF(0.305 * size, (y - 0.04) * size))
        _linea(pintor, size, 0.40, y, 0.76, y, "#CBD5E1", 2.2)
    _estrella(pintor, size, 0.62, 0.72, 0.86, 0.90, "#FBBF24", borde="#CA8A04")


#Icono clásico de "compartir" -tres nodos conectados en triángulo-
#en los colores propios de la app (azul/verde), para "Compartir
#Calificaciones": comunica "enviar esto hacia afuera (a un tercero)",
#distinto de exportar (bandeja) y de correo (sobre).
def _compartir_calificaciones(pintor, size):

    pintor.setPen(_pluma("#3B82F6", 2.2))
    pintor.drawLine(QPointF(0.30 * size, 0.50 * size), QPointF(0.72 * size, 0.26 * size))
    pintor.drawLine(QPointF(0.30 * size, 0.50 * size), QPointF(0.72 * size, 0.74 * size))
    _disco(pintor, size, 0.14, 0.38, 0.34, 0.62, "#3B82F6", borde="#1D4ED8")
    _disco(pintor, size, 0.66, 0.12, 0.86, 0.36, "#22C55E", borde="#15803D")
    _disco(pintor, size, 0.66, 0.62, 0.86, 0.86, "#22C55E", borde="#15803D")


#Tabla de despacho: caracter emoji -> función de dibujo(p, size) Cubre EXACTAMENTE los 159 emojis usados hoy en
#la app.
def _f(fn):

    return fn


_REGISTRO= {
    #Panel / Dashboard
    "▦": lambda pintor, tamano: _panel_dashboard(pintor, tamano),
    "⛶": lambda pintor, tamano: _pantalla_completa(pintor, tamano),

    #Flechas / navegación
    "←": lambda pintor, tamano: _flecha(pintor, tamano, "#475569", 180),
    "→": lambda pintor, tamano: _flecha(pintor, tamano, "#475569", 0),
    "↔": lambda pintor, tamano: (_flecha(pintor, tamano, "#475569", 0, cx=0.65), _flecha(pintor, tamano, "#475569", 180, cx=0.35)),
    "↑": lambda pintor, tamano: _flecha(pintor, tamano, "#475569", -90),
    "↓": lambda pintor, tamano: _flecha(pintor, tamano, "#475569", 90),
    "↗": lambda pintor, tamano: _flecha(pintor, tamano, "#475569", -45),
    "➡": lambda pintor, tamano: _flecha(pintor, tamano, "#3B82F6", 0),
    "⬅": lambda pintor, tamano: _flecha(pintor, tamano, "#3B82F6", 180),
    "⬆": lambda pintor, tamano: _flecha(pintor, tamano, "#22C55E", -90),
    "⬇": lambda pintor, tamano: _flecha(pintor, tamano, "#EF4444", 90),
    "↩": lambda pintor, tamano: _flecha_curva(pintor, tamano, "#475569", "undo"),
    "↶": lambda pintor, tamano: _flecha_curva(pintor, tamano, "#475569", "undo"),
    "↷": lambda pintor, tamano: _flecha_curva(pintor, tamano, "#475569", "redo"),
    "⇪": lambda pintor, tamano: _flecha(pintor, tamano, "#475569", -90, largo=0.28),
    "↺": lambda pintor, tamano: _flechas_circulares(pintor, tamano, "#3B82F6", "#60A5FA"),
    "🔁": lambda pintor, tamano: _flechas_circulares(pintor, tamano, "#22C55E", "#4ADE80"),
    "🔄": lambda pintor, tamano: _flechas_circulares(pintor, tamano, "#3B82F6", "#60A5FA"),
    "♻": lambda pintor, tamano: _reciclaje(pintor, tamano),
    "⏳": lambda pintor, tamano: _reloj_arena(pintor, tamano),
    "⌛": lambda pintor, tamano: _reloj_arena(pintor, tamano, color_arena="#EF4444"),

    #Estado / confirmación
    "✅": lambda pintor, tamano: (_disco(pintor, tamano, 0.08, 0.08, 0.92, 0.92, "#22C55E"), _check(pintor, tamano, "white")),
    "✓": lambda pintor, tamano: _check(pintor, tamano, "#22C55E", ancho=3.0),
    "✔": lambda pintor, tamano: _check(pintor, tamano, "#22C55E", ancho=3.0),
    "❌": lambda pintor, tamano: (_disco(pintor, tamano, 0.08, 0.08, 0.92, 0.92, "#EF4444"), _cruz(pintor, tamano, "white")),
    "✖": lambda pintor, tamano: _cruz(pintor, tamano, "#EF4444", ancho=3.0),
    "✕": lambda pintor, tamano: _cruz(pintor, tamano, "#EF4444", ancho=3.0),
    "⚠": lambda pintor, tamano: _triangulo_alerta(pintor, tamano),
    "❕": lambda pintor, tamano: _triangulo_alerta(pintor, tamano),
    "🚨": lambda pintor, tamano: (_disco(pintor, tamano, 0.16, 0.10, 0.84, 0.78, "#EF4444", borde="#7F1D1D"),
                        _rect_redondeado(pintor, tamano, 0.30, 0.78, 0.70, 0.90, "#1E293B", radio=0.1)),
    "🚫": lambda pintor, tamano: _prohibido(pintor, tamano),
    "⛔": lambda pintor, tamano: _prohibido(pintor, tamano),
    "🚦": lambda pintor, tamano: _semaforo(pintor, tamano),
    "🚧": lambda pintor, tamano: _construccion(pintor, tamano),

    #Símbolos
    "➕": lambda pintor, tamano: _mas(pintor, tamano, "#22C55E"),
    "➖": lambda pintor, tamano: _menos(pintor, tamano, "#EF4444"),
    "➗": lambda pintor, tamano: _dividir(pintor, tamano),
    "✂": lambda pintor, tamano: _tijeras(pintor, tamano),
    "⭐": lambda pintor, tamano: _estrella(pintor, tamano, 0.10, 0.10, 0.90, 0.90, "#FBBF24", borde="#CA8A04"),
    "🌟": lambda pintor, tamano: (_estrella(pintor, tamano, 0.14, 0.14, 0.86, 0.86, "#FBBF24", borde="#CA8A04"), _chispas(pintor, tamano)),
    "✨": lambda pintor, tamano: _chispas(pintor, tamano),
    "🔘": lambda pintor, tamano: (_disco(pintor, tamano, 0.14, 0.14, 0.86, 0.86, "white", borde="#64748B"),
                        _disco(pintor, tamano, 0.34, 0.34, 0.66, 0.66, "#3B82F6")),
    "🔲": lambda pintor, tamano: _rect_redondeado(pintor, tamano, 0.18, 0.18, 0.82, 0.82, "#334155", radio=0.10),

    #Puntos de color (semáforos de estado, indicadores)
    "🔴": lambda pintor, tamano: _disco(pintor, tamano, 0.16, 0.16, 0.84, 0.84, "#EF4444", borde="#991B1B"),
    "🟢": lambda pintor, tamano: _disco(pintor, tamano, 0.16, 0.16, 0.84, 0.84, "#22C55E", borde="#166534"),
    "🟠": lambda pintor, tamano: _disco(pintor, tamano, 0.16, 0.16, 0.84, 0.84, "#F97316", borde="#9A3412"),
    "🔵": lambda pintor, tamano: _disco(pintor, tamano, 0.16, 0.16, 0.84, 0.84, "#3B82F6", borde="#1E3A8A"),
    "🔷": lambda pintor, tamano: _poligono(pintor, tamano, [(0.5, 0.10), (0.90, 0.5), (0.5, 0.90), (0.10, 0.5)], "#3B82F6", borde="#1E3A8A"),
    "🔹": lambda pintor, tamano: _poligono(pintor, tamano, [(0.5, 0.24), (0.76, 0.5), (0.5, 0.76), (0.24, 0.5)], "#60A5FA"),
    "⚪": lambda pintor, tamano: _disco(pintor, tamano, 0.16, 0.16, 0.84, 0.84, "#F1F5F9", borde="#94A3B8"),

    #Ojos / visibilidad
    "👁": lambda pintor, tamano: _ojo(pintor, tamano),
    "🙈": lambda pintor, tamano: _ojo(pintor, tamano, cerrado=True),
    "👓": lambda pintor, tamano: _lentes(pintor, tamano),

    #Manos / gestos
    "👆": lambda pintor, tamano: _flecha(pintor, tamano, "#F59E0B", -90, largo=0.24, ancho_cabeza=0.14),
    "👇": lambda pintor, tamano: _flecha(pintor, tamano, "#F59E0B", 90, largo=0.24, ancho_cabeza=0.14),
    "🤝": lambda pintor, tamano: _manos_saludo(pintor, tamano),

    #Personas
    "👤": lambda pintor, tamano: _persona(pintor, tamano, 1, "#64748B"),
    "👥": lambda pintor, tamano: _persona(pintor, tamano, 2),
    "👨": lambda pintor, tamano: _persona(pintor, tamano, 1, "#3B82F6"),
    "🧑": lambda pintor, tamano: _persona(pintor, tamano, 1, "#F59E0B"),
    "🎓": lambda pintor, tamano: _persona(pintor, tamano, 1, "#1D4ED8", graduado=True),

    #Edificios
    "🏠": lambda pintor, tamano: _casa(pintor, tamano),
    "🏫": lambda pintor, tamano: _escuela(pintor, tamano),
    "🏢": lambda pintor, tamano: _edificio(pintor, tamano),
    "🏥": lambda pintor, tamano: _hospital(pintor, tamano),
    "🏛": lambda pintor, tamano: _castillo(pintor, tamano),
    "🚪": lambda pintor, tamano: _puerta_salida(pintor, tamano),

    #Candados / seguridad / llaves
    "🔒": lambda pintor, tamano: _candado(pintor, tamano),
    "🔐": lambda pintor, tamano: _candado(pintor, tamano, color_cuerpo="#4F46E5", color_arco="#818CF8"),
    "🔓": lambda pintor, tamano: _candado(pintor, tamano, abierto=True),
    "🔑": lambda pintor, tamano: _llave(pintor, tamano),
    "🛡": lambda pintor, tamano: _escudo(pintor, tamano),

    #Documentos / carpetas / libros
    "📁": lambda pintor, tamano: _carpeta(pintor, tamano),
    "📂": lambda pintor, tamano: _carpeta(pintor, tamano, abierta=True),
    "🗂": lambda pintor, tamano: _carpeta(pintor, tamano, color="#38BDF8", abierta=True),
    "🗄": lambda pintor, tamano: _archivador(pintor, tamano),
    "📄": lambda pintor, tamano: _documento(pintor, tamano),
    "📃": lambda pintor, tamano: _documento(pintor, tamano, lineas=False),
    "📋": lambda pintor, tamano: _clip_tablero(pintor, tamano),
    "🗒": lambda pintor, tamano: _documento(pintor, tamano, color_esquina="#F59E0B"),
    "📝": lambda pintor, tamano: (_documento(pintor, tamano, lineas=False), _lapiz(pintor, tamano)),
    "📇": lambda pintor, tamano: _tarjeta_indice(pintor, tamano),
    "📜": lambda pintor, tamano: _pergamino(pintor, tamano),
    "📔": lambda pintor, tamano: _libro(pintor, tamano, "#EF4444", "#7F1D1D"),
    "📖": lambda pintor, tamano: _libro(pintor, tamano, "#F59E0B", "#92400E"),
    "📗": lambda pintor, tamano: _libro(pintor, tamano, "#22C55E", "#166534"),
    "📘": lambda pintor, tamano: _libro(pintor, tamano, "#3B82F6", "#1E3A8A"),
    "📙": lambda pintor, tamano: _libro(pintor, tamano, "#F97316", "#9A3412"),
    "📚": lambda pintor, tamano: _libro(pintor, tamano, "#8B5CF6", "#5B21B6"),
    "🗺": lambda pintor, tamano: _mapa(pintor, tamano),
    "📜🗺": None,

    #Edición
    "✏": lambda pintor, tamano: _lapiz(pintor, tamano),
    "✎": lambda pintor, tamano: _lapiz(pintor, tamano),
    "✍": lambda pintor, tamano: _lapiz(pintor, tamano),
    "🖌": lambda pintor, tamano: _lapiz(pintor, tamano),
    "🖍": lambda pintor, tamano: _lapiz(pintor, tamano),

    #Guardar / archivos multimedia
    "💾": lambda pintor, tamano: _disquete(pintor, tamano),
    "📀": lambda pintor, tamano: _disco_optico(pintor, tamano),
    "🖼": lambda pintor, tamano: (_rect_redondeado(pintor, tamano, 0.12, 0.16, 0.88, 0.84, "white", radio=0.04, borde="#94A3B8"),
                        _disco(pintor, tamano, 0.24, 0.30, 0.38, 0.44, "#FBBF24"),
                        _poligono(pintor, tamano, [(0.18, 0.76), (0.42, 0.50), (0.60, 0.66), (0.76, 0.46), (0.82, 0.76)], "#22C55E")),
    "📷": lambda pintor, tamano: _camara(pintor, tamano),

    #Papelera / limpieza
    "🗑": lambda pintor, tamano: _papelera(pintor, tamano),
    "🧹": lambda pintor, tamano: _escoba(pintor, tamano),

    #Búsqueda
    "🔍": lambda pintor, tamano: _lupa(pintor, tamano),
    "🔎": lambda pintor, tamano: _lupa(pintor, tamano, color="#F59E0B"),

    #Config / herramientas
    "⚙": lambda pintor, tamano: _engranaje(pintor, tamano),
    "🛠": lambda pintor, tamano: (_llave_inglesa(pintor, tamano), None),
    "🔧": lambda pintor, tamano: _llave_inglesa(pintor, tamano, color="#F59E0B"),
    "🧰": lambda pintor, tamano: (_rect_redondeado(pintor, tamano, 0.12, 0.42, 0.88, 0.82, "#EF4444", radio=0.06, borde="#7F1D1D"),
                        _rect_redondeado(pintor, tamano, 0.38, 0.30, 0.62, 0.46, "#94A3B8", radio=0.05)),
    "🎚": lambda pintor, tamano: _control_deslizante(pintor, tamano),
    "🔽": lambda pintor, tamano: _flecha_abajo_pequena(pintor, tamano),
    "🔌": lambda pintor, tamano: _enchufe(pintor, tamano),

    #Puzzle / integraciones
    "🧩": lambda pintor, tamano: _pieza_rompecabezas(pintor, tamano),
    "🔗": lambda pintor, tamano: _eslabon(pintor, tamano),
    "⛓": lambda pintor, tamano: _eslabon(pintor, tamano, color="#475569"),

    #Menú / listas
    "☰": lambda pintor, tamano: _menu_hamburguesa(pintor, tamano),

    #Gráficos / reportes
    "📊": lambda pintor, tamano: _grafico_barras(pintor, tamano),
    "📈": lambda pintor, tamano: _grafico_lineas(pintor, tamano, "#22C55E"),
    "📉": lambda pintor, tamano: _grafico_lineas(pintor, tamano, "#EF4444"),
    "📐": lambda pintor, tamano: _regla(pintor, tamano),

    #Fecha / hora
    "📅": lambda pintor, tamano: _calendario(pintor, tamano),
    "📆": lambda pintor, tamano: _calendario(pintor, tamano, color_top="#3B82F6"),
    "🗓": lambda pintor, tamano: _calendario(pintor, tamano, color_top="#8B5CF6"),
    "🕐": lambda pintor, tamano: _reloj(pintor, tamano),
    "🕒": lambda pintor, tamano: _reloj(pintor, tamano),
    "🕓": lambda pintor, tamano: _reloj(pintor, tamano),

    #Envío / correo
    "✉": lambda pintor, tamano: _sobre(pintor, tamano),
    "📨": lambda pintor, tamano: _sobre(pintor, tamano),
    "📞": lambda pintor, tamano: _telefono(pintor, tamano),
    "📤": lambda pintor, tamano: (_sobre(pintor, tamano), _flecha(pintor, tamano, "#3B82F6", -90, cx=0.5, cy=0.5, largo=0.14, ancho_cabeza=0.09)),
    "📥": lambda pintor, tamano: (_sobre(pintor, tamano), _flecha(pintor, tamano, "#22C55E", 90, cx=0.5, cy=0.5, largo=0.14, ancho_cabeza=0.09)),
    "📦": lambda pintor, tamano: _paquete(pintor, tamano),

    #Ubicación
    "📌": lambda pintor, tamano: _pin_ubicacion(pintor, tamano),
    "📍": lambda pintor, tamano: _pin_ubicacion(pintor, tamano, "#3B82F6"),
    "🧭": lambda pintor, tamano: _brujula(pintor, tamano),

    #Interfaz / dispositivos
    "🖥": lambda pintor, tamano: _pantalla(pintor, tamano),
    "💻": lambda pintor, tamano: _pantalla(pintor, tamano),
    "🗔": lambda pintor, tamano: _ventana_app(pintor, tamano),
    "🪟": lambda pintor, tamano: _ventana_app(pintor, tamano),
    "🖨": lambda pintor, tamano: _impresora(pintor, tamano),
    "🔤": lambda pintor, tamano: _fuente_texto(pintor, tamano),

    #Nube
    "☁": lambda pintor, tamano: _nube(pintor, tamano),
    "🌫": lambda pintor, tamano: _nube(pintor, tamano, color="#CBD5E1"),
    "🌤": lambda pintor, tamano: (_nube(pintor, tamano, color="#E2E8F0"), _sol(pintor, tamano)),

    #Sol / luna (tema claro/oscuro)
    "☀": lambda pintor, tamano: _sol(pintor, tamano),
    "🌙": lambda pintor, tamano: _luna(pintor, tamano),
    "🌗": lambda pintor, tamano: _luna(pintor, tamano),

    #Emociones
    "😊": lambda pintor, tamano: _sonrisa(pintor, tamano),
    "🙂": lambda pintor, tamano: _sonrisa(pintor, tamano),
    "❤": lambda pintor, tamano: _corazon(pintor, tamano),
    "💙": lambda pintor, tamano: _corazon(pintor, tamano, "#3B82F6"),

    #Notificaciones
    "🔔": lambda pintor, tamano: _campana(pintor, tamano),

    #Objetivos / ideas
    "🎯": lambda pintor, tamano: _diana(pintor, tamano),
    "💡": lambda pintor, tamano: _bombilla(pintor, tamano),
    "🧠": lambda pintor, tamano: _cerebro(pintor, tamano),
    "🎨": lambda pintor, tamano: _paleta(pintor, tamano),

    #Logros
    "🏆": lambda pintor, tamano: _trofeo(pintor, tamano),
    "🏁": lambda pintor, tamano: _bandera(pintor, tamano, "#1E293B"),
    "🏷": lambda pintor, tamano: _pin_ubicacion(pintor, tamano, "#F59E0B"),
    "🎉": lambda pintor, tamano: (_chispas(pintor, tamano), _confeti(pintor, tamano) if False else None),
    "⚡": lambda pintor, tamano: _poligono(pintor, tamano, [(0.56, 0.10), (0.24, 0.56), (0.46, 0.56), (0.40, 0.90), (0.78, 0.40),
                                        (0.54, 0.40)], "#FBBF24", borde="#CA8A04"),

    #Papel/negocio
    "💼": lambda pintor, tamano: _maletin(pintor, tamano),
    "⚖": lambda pintor, tamano: _balanza(pintor, tamano),
    "🚀": lambda pintor, tamano: _cohete(pintor, tamano),
    "💥": lambda pintor, tamano: _explosion(pintor, tamano),
    "🧊": lambda pintor, tamano: _rect_redondeado(pintor, tamano, 0.20, 0.20, 0.80, 0.80, "#BAE6FD", radio=0.04, borde="#0284C7"),
    "💧": lambda pintor, tamano: _gota(pintor, tamano),
    "🧪": lambda pintor, tamano: _tubo_ensayo(pintor, tamano),
}


def _confeti(pintor, tamano):

    pass


#Sinónimos con clave duplicada válidos por diccionario (Python solo se queda con la última definición si se
#repite la clave literal, así que
#los siguientes se agregan explícitamente después para que ambos existan):
_REGISTRO.setdefault("📜", lambda pintor, tamano: _pergamino(pintor, tamano))
#Glifo privado (área de uso privado Unicode) para FILTROS:
#align-justify puro, sin lupa, tal como pide el diseño.
_REGISTRO.setdefault("\uE000", lambda pintor, tamano: _alineacion_justificada(pintor, tamano))
#Glifo privado para el KPI "Notas registradas (año actual)" de Calificaciones Técnicas: planilla con checks,
#ver _registro_notas_kpi. (\uE035, NO \uE001 -esa clave ya es EMOJI_IMPORTAR más abajo; usarla aquí pisaba el
#icono de "Importar" en toda la app, incluido el login).
EMOJI_NOTAS_REGISTRADAS_KPI= "\uE035"
_REGISTRO.setdefault(EMOJI_NOTAS_REGISTRADAS_KPI, lambda pintor, tamano: _registro_notas_kpi(pintor, tamano, "#10B981"))
#Glifos privados para IMPORTAR/EXPORTAR: bandeja + flecha, deliberadamente NO un sobre de correo (ver
#_bandeja_flecha). Úsense en vez de 📥/📤 en cualquier botón cuya acción sea importar/exportar datos -no enviar
#un correo-; para correo de verdad, 📨/✉ siguen siendo lo correcto.
EMOJI_IMPORTAR= "\uE001"
EMOJI_EXPORTAR= "\uE002"
_REGISTRO.setdefault(EMOJI_IMPORTAR, lambda pintor, tamano: _icono_importar(pintor, tamano))
_REGISTRO.setdefault(EMOJI_EXPORTAR, lambda pintor, tamano: _icono_exportar(pintor, tamano))
_REGISTRO.setdefault("🎓", lambda pintor, tamano: _persona(pintor, tamano, 1, "#1D4ED8", graduado=True))
_REGISTRO.pop("📜🗺", None)

#Glifos privados para iconos específicos que no tienen un emoji Unicode
#adecuado (o cuyo emoji genérico generaba confusión, ver funciones arriba).
EMOJI_PROFESOR= "\uE003"          #Docente frente a un pizarrón (antes: 👥, genérico)
EMOJI_ESTUDIANTE_RIESGO= "\uE004"  #Estudiante + insignia de alerta (antes: 🚨, sirena)
EMOJI_SECCIONES_GRUPOS= "\uE005"   #Fichas de curso superpuestas (antes: 🏫, escuela)
EMOJI_COPIA_SEGURIDAD= "\uE006"    #Carpeta con flecha circular (backup)
EMOJI_AUDITORIA= "\uE007"          #Hoja de registro + lupa (antes: 📇/📋 genéricos)
EMOJI_TUTORIAL= "\uE008"           #Libro + bombilla de idea (antes: sin icono, o ➕)
_REGISTRO.setdefault(EMOJI_PROFESOR, lambda pintor, tamano: _profesor(pintor, tamano))
_REGISTRO.setdefault(EMOJI_ESTUDIANTE_RIESGO, lambda pintor, tamano: _estudiante_riesgo(pintor, tamano))
_REGISTRO.setdefault(EMOJI_SECCIONES_GRUPOS, lambda pintor, tamano: _secciones_grupos(pintor, tamano))
_REGISTRO.setdefault(EMOJI_COPIA_SEGURIDAD, lambda pintor, tamano: _copia_seguridad(pintor, tamano))
_REGISTRO.setdefault(EMOJI_AUDITORIA, lambda pintor, tamano: _auditoria(pintor, tamano))
_REGISTRO.setdefault(EMOJI_TUTORIAL, lambda pintor, tamano: _tutorial_guia(pintor, tamano))

#Glifo privado para la pestaña "Vista Previa y Edición" de Reportes: un documento que se está VIENDO (insignia
#de ojo) y EDITANDO (lápiz apoyado sobre la hoja) al mismo tiempo -antes esa pestaña no tenía icono propio,
#solo lo que el iconizador automático adivinara por el texto.
EMOJI_VISTA_EDICION= "\uE009"
_REGISTRO.setdefault(EMOJI_VISTA_EDICION, lambda pintor, tamano: _archivo_vista_edicion(pintor, tamano))

#Glifos privados para alineación de texto (izquierda/centro/derecha): el único icono de alineación que existía
#(\uE000) era "justificado". Se usan en las barras de formato de Excel/Word/PDF del editor de reportes, que
#antes tenían estos botones con texto vacío y SIN icono -invisibles-.
EMOJI_ALINEAR_IZQUIERDA= "\uE00A"
EMOJI_ALINEAR_CENTRO= "\uE00B"
EMOJI_ALINEAR_DERECHA= "\uE00C"
_REGISTRO.setdefault(EMOJI_ALINEAR_IZQUIERDA, lambda pintor, tamano: _alineacion_lineas(pintor, tamano, "izquierda"))
_REGISTRO.setdefault(EMOJI_ALINEAR_CENTRO, lambda pintor, tamano: _alineacion_lineas(pintor, tamano, "centro"))
_REGISTRO.setdefault(EMOJI_ALINEAR_DERECHA, lambda pintor, tamano: _alineacion_lineas(pintor, tamano, "derecha"))

#Glifos privados para los 3 estados de asistencia que no tenían icono
#propio (antes: texto vacío, o -en el caso de "Permiso"- una llave 🔑
#que el iconizador automático le ponía por casualidad de texto y que no tiene ningún sentido para un
#permiso/ausencia justificada).
EMOJI_EXCUSADO= "\uE00D"           #Nota/justificante con sello de aceptado
EMOJI_LICENCIA_MEDICA= "\uE00E"    #Cruz médica
EMOJI_PERMISO= "\uE00F"            #Mano levantada pidiendo/con permiso
_REGISTRO.setdefault(EMOJI_EXCUSADO, lambda pintor, tamano: _excusa_justificante(pintor, tamano))
_REGISTRO.setdefault(EMOJI_LICENCIA_MEDICA, lambda pintor, tamano: _licencia_medica(pintor, tamano))
_REGISTRO.setdefault(EMOJI_PERMISO, lambda pintor, tamano: _permiso_mano(pintor, tamano))

#Glifos privados para Calificaciones: el botón "Vincular a Competencias Específicas" usaba 🎓 (persona graduada,
#"estudiante") sin ninguna relación con la acción de vincular, y varias pestañas de la barra de
#tabs (Boletín/Promedios, Seguimiento RP, Evaluaciones Finales, Currículo
#CE, Notas por Competencia, Compartir Calificaciones) o bien no tenían ningún icono dedicado, o el iconizador
#automático les asignaba uno genérico por coincidencia de palabra (ver iconos_auto.py) que no las distinguía
#entre sí.
EMOJI_VINCULAR= "\uE010"
EMOJI_BOLETIN_PROMEDIOS= "\uE011"
EMOJI_SEGUIMIENTO_RP= "\uE012"
EMOJI_EVALUACIONES_FINALES= "\uE013"
EMOJI_CURRICULO_CE= "\uE014"
EMOJI_NOTAS_COMPETENCIA= "\uE015"
EMOJI_COMPARTIR_CALIFICACIONES= "\uE016"
_REGISTRO.setdefault(EMOJI_VINCULAR, lambda pintor, tamano: _vinculacion(pintor, tamano))
_REGISTRO.setdefault(EMOJI_BOLETIN_PROMEDIOS, lambda pintor, tamano: _boletin_promedios(pintor, tamano))
_REGISTRO.setdefault(EMOJI_SEGUIMIENTO_RP, lambda pintor, tamano: _seguimiento_rp(pintor, tamano))
_REGISTRO.setdefault(EMOJI_EVALUACIONES_FINALES, lambda pintor, tamano: _evaluaciones_finales(pintor, tamano))
_REGISTRO.setdefault(EMOJI_CURRICULO_CE, lambda pintor, tamano: _curriculo_ce(pintor, tamano))
_REGISTRO.setdefault(EMOJI_NOTAS_COMPETENCIA, lambda pintor, tamano: _notas_competencia(pintor, tamano))
_REGISTRO.setdefault(EMOJI_COMPARTIR_CALIFICACIONES, lambda pintor, tamano: _compartir_calificaciones(pintor, tamano))

#Glifos privados para los 3 botones "Registrar Nota ___" de Evaluaciones
#Finales (Completiva/Extraordinaria/Especial): antes los tres usaban el
#mismo 📈 genérico -sin ninguna forma de distinguirlos a simple vista, obligando a leer el texto completo del
#botón cada vez-. Comparten una misma base (la hoja de examen de _documento) para leerse como una
#familia ("esto registra una nota"), y cada uno agrega una insignia
#propia -coherente con su significado- en la esquina inferior derecha.
EMOJI_NOTA_COMPLETIVA= "\uE017"      #Hoja + flecha circular: se "completa/retoma" lo pendiente
EMOJI_NOTA_EXTRAORDINARIA= "\uE018"  #Hoja + estrella: convocatoria fuera del ciclo ordinario
EMOJI_NOTA_ESPECIAL= "\uE019"        #Hoja + escudo: caso particular, con condiciones propias
_REGISTRO.setdefault(EMOJI_NOTA_COMPLETIVA, lambda pintor, tamano: _nota_completiva(pintor, tamano))
_REGISTRO.setdefault(EMOJI_NOTA_EXTRAORDINARIA, lambda pintor, tamano: _nota_extraordinaria(pintor, tamano))
_REGISTRO.setdefault(EMOJI_NOTA_ESPECIAL, lambda pintor, tamano: _nota_especial(pintor, tamano))


#Anillo de progreso (igual en espíritu al widget 'anillo_desempeno'
#que se ve DENTRO de esta misma pestaña) con una figura de estudiante
#al centro -para la pestaña "Desempeño Individual"-: el aro remarca que
#se trata del avance de UN estudiante en sus competencias fundamentales,
#a diferencia de la tarjeta de boletín (consolidado del grupo) o la
#bandera de evaluaciones finales (cierre de periodo).
def _desempeno_individual(pintor, size):

    pintor.setPen(_pluma("#E2E8F0", 7.2))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(_r(size, 0.09, 0.09, 0.91, 0.91), 0, 360 * 16)
    pintor.setPen(_pluma("#22C55E", 7.2))
    #Empieza arriba (90°) y avanza en sentido horario ~72% del aro.
    pintor.drawArc(_r(size, 0.09, 0.09, 0.91, 0.91), 90 * 16, -int(360 * 0.72 * 16))
    _disco(pintor, size, 0.41, 0.30, 0.59, 0.48, "#1E293B")
    _rect_redondeado(pintor, size, 0.35, 0.52, 0.65, 0.78, "#1E293B", radio=0.14)


#Calculadora de escritorio clásica -pantalla + rejilla de botones-
#para los botones "Calcular" de Evaluaciones Finales y Notas por
#Competencia: representa con claridad "esto computa un resultado a
#partir de tus notas", a diferencia de una lupa (buscar) o de chispas
#genéricas (que no comunican ninguna acción concreta).
def _calculadora(p, size):

    _rect_redondeado(p, size, 0.16, 0.06, 0.84, 0.94, "#1E293B", radio=0.10, borde="#0F172A")
    _rect_redondeado(p, size, 0.24, 0.14, 0.76, 0.32, "#86EFAC", radio=0.04)
    for fila in range(3):
        for col in range(3):
            x0= 0.24 + col * 0.185
            y0= 0.42 + fila * 0.165
            color= "#F59E0B" if (fila == 2 and col == 2) else "#94A3B8"
            _rect_redondeado(p, size, x0, y0, x0 + 0.145, y0 + 0.115, color, radio=0.03)


#Portapapeles con una varita/chispa "creando" una línea nueva -para
#el botón "Generar Seguimiento"-: comunica "esto arma automáticamente
#el plan de seguimiento por ti", distinto de la calculadora (que
#computa un valor numérico) y del icono de la propia pestaña
#Seguimiento (banderín + reloj de arena, que representa el estado ya
#creado, no la acción de crearlo).
def _generar_seguimiento(pintor, size):

    _rect_redondeado(pintor, size, 0.20, 0.10, 0.80, 0.92, "#F8FAFC", radio=0.08, borde="#94A3B8")
    _rect_redondeado(pintor, size, 0.38, 0.04, 0.62, 0.16, "#64748B", radio=0.04)
    _linea(pintor, size, 0.30, 0.36, 0.58, 0.36, "#CBD5E1", 2.2)
    _linea(pintor, size, 0.30, 0.50, 0.58, 0.50, "#CBD5E1", 2.2)
    pintor.setPen(_pluma("#F59E0B", 2.4))
    pintor.drawLine(QPointF(0.66 * size, 0.62 * size), QPointF(0.80 * size, 0.66 * size))
    pintor.drawLine(QPointF(0.68 * size, 0.72 * size), QPointF(0.82 * size, 0.76 * size))
    _estrella(pintor, size, 0.60, 0.58, 0.82, 0.80, "#FBBF24", borde="#CA8A04")


EMOJI_DESEMPENO_INDIVIDUAL= "\uE017"
EMOJI_CALCULADORA= "\uE018"
EMOJI_GENERAR_SEGUIMIENTO= "\uE019"
_REGISTRO.setdefault(EMOJI_DESEMPENO_INDIVIDUAL, lambda pintor, tamano: _desempeno_individual(pintor, tamano))
_REGISTRO.setdefault(EMOJI_CALCULADORA, lambda pintor, tamano: _calculadora(pintor, tamano))
_REGISTRO.setdefault(EMOJI_GENERAR_SEGUIMIENTO, lambda pintor, tamano: _generar_seguimiento(pintor, tamano))


#Glifos privados para la tab bar de Calificaciones Técnicas (calificaciones_tecnicas.py): las 3 pestañas
#-"Módulos y RA", "Registro de Notas" y "Boletín Técnico"- no tenían icono propio en la tab bar (nunca se les
#llamó setTabIcon). Cada uno se diseñó para no confundirse con su equivalente de Calificaciones "normales": el
#boletín técnico usa un certificado con sello en vez de la tarjeta con barritas de _boletin_promedios, por
#ejemplo.
#Dos fichas de módulo apiladas (currículo técnico dividido en
#módulos) con una insignia de check al frente -para "Módulos y RA"-:
#el check representa los Resultados de Aprendizaje (RA) ya alcanzados
#dentro de cada módulo, a diferencia de una carpeta genérica que no
#diría nada sobre "aprendizaje logrado".
def _modulos_ra(pintor, size):

    _rect_redondeado(pintor, size, 0.22, 0.10, 0.86, 0.46, "#94A3B8", radio=0.08, borde="#475569")
    _rect_redondeado(pintor, size, 0.14, 0.30, 0.78, 0.66, "#38BDF8", radio=0.08, borde="#0369A1")
    for y in (0.42, 0.52):
        _linea(pintor, size, 0.24, y, 0.62, y, "white", 2.0)
    _disco(pintor, size, 0.58, 0.58, 0.92, 0.92, "#22C55E", borde="#15803D")
    pintor.setPen(_pluma("white", 2.0))
    pintor.drawLine(QPointF(0.65 * size, 0.75 * size), QPointF(0.72 * size, 0.82 * size))
    pintor.drawLine(QPointF(0.72 * size, 0.82 * size), QPointF(0.85 * size, 0.66 * size))


#Hoja de calificaciones con filas marcadas y una insignia "%" -para
#"Registro de Notas" (técnicas)-: distinto del lápiz+documento genérico
#(📝) que ya usan otros módulos para "registrar algo" en general, este
#deja claro de un vistazo que lo que se registra son notas numéricas.
def _registro_notas_tecnicas(pintor, size):

    _rect_redondeado(pintor, size, 0.16, 0.08, 0.84, 0.92, "#F8FAFC", radio=0.07, borde="#94A3B8")
    _rect_redondeado(pintor, size, 0.34, 0.02, 0.66, 0.16, "#64748B", radio=0.04)
    for y, marcada in ((0.32, True), (0.48, False), (0.64, True)):
        color_check= "#22C55E" if marcada else "#CBD5E1"
        _disco(pintor, size, 0.24, y - 0.045, 0.34, y + 0.045, color_check)
        if marcada:
            pintor.setPen(_pluma("white", 1.5))
            pintor.drawLine(QPointF(0.262 * size, y * size), QPointF(0.29 * size, (y + 0.035) * size))
            pintor.drawLine(QPointF(0.29 * size, (y + 0.035) * size), QPointF(0.325 * size, (y - 0.04) * size))
        _linea(pintor, size, 0.42, y, 0.72, y, "#CBD5E1", 2.0)
    _disco(pintor, size, 0.58, 0.72, 0.92, 0.98, "#F59E0B", borde="#B45309")
    from PySide6.QtGui import QFont
    fuente= QFont()
    fuente.setPixelSize(int(size * 0.16))
    fuente.setBold(True)
    pintor.setFont(fuente)
    pintor.setPen(_pluma("white", 1.0))
    pintor.drawText(_r(size, 0.58, 0.715, 0.92, 0.98), Qt.AlignmentFlag.AlignCenter, "%")


#Certificado con sello -para "Boletín Técnico"-: a propósito
#distinto de la tarjeta con barritas ascendentes de _boletin_promedios
#(Calificaciones "normales"), porque un boletín de Educación Técnica
#se percibe/entrega como un certificado formal de la carrera/área
#técnica cursada, no solo como un resumen de promedios.
def _boletin_tecnico(pintor, size):

    _rect_redondeado(pintor, size, 0.10, 0.08, 0.90, 0.72, "#F8FAFC", radio=0.06, borde="#0EA5E9")
    _linea(pintor, size, 0.20, 0.22, 0.80, 0.22, "#0EA5E9", 2.4)
    for y in (0.34, 0.44, 0.54):
        _linea(pintor, size, 0.20, y, 0.62, y, "#CBD5E1", 1.8)
    pintor.save()
    pintor.translate(size * 0.5, size * 0.86)
    pintor.rotate(-20)
    pintor.translate(-size * 0.5, -size * 0.86)
    _linea(pintor, size, 0.5, 0.62, 0.5, 0.98, "#0284C7", 8.0)
    pintor.restore()
    pintor.save()
    pintor.translate(size * 0.5, size * 0.86)
    pintor.rotate(20)
    pintor.translate(-size * 0.5, -size * 0.86)
    _linea(pintor, size, 0.5, 0.62, 0.5, 0.98, "#0284C7", 8.0)
    pintor.restore()
    _disco(pintor, size, 0.36, 0.62, 0.64, 0.90, "#FACC15", borde="#CA8A04")
    _estrella(pintor, size, 0.42, 0.68, 0.58, 0.84, "#FEF3C7", borde="#CA8A04", puntas=5)


EMOJI_MODULOS_RA= "\uE01A"
EMOJI_REGISTRO_NOTAS_TECNICAS= "\uE01B"
EMOJI_BOLETIN_TECNICO= "\uE01C"
_REGISTRO.setdefault(EMOJI_MODULOS_RA, lambda pintor, tamano: _modulos_ra(pintor, tamano))
_REGISTRO.setdefault(EMOJI_REGISTRO_NOTAS_TECNICAS, lambda pintor, tamano: _registro_notas_tecnicas(pintor, tamano))
_REGISTRO.setdefault(EMOJI_BOLETIN_TECNICO, lambda pintor, tamano: _boletin_tecnico(pintor, tamano))


#Glifos privados para politecnico.py: varias tarjetas de sección y la tab bar (que no tenía ningún icono en
#absoluto -6 pestañas sin setTabIcon-) usaban emojis genéricos (🛠 martillo+destornillador, 🏫 escuela, 💼
#maletín) que no comunicaban nada específico de Educación Técnico-Profesional. Cada uno de estos se diseñó para
#representar su concepto concreto y no confundirse entre sí.
def _hexagono(p, size, cx, cy, r, color, borde=None, rot=90):

    pts= []
    for i in range(6):
        ang= math.radians(60 * i - rot)
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    _poligono(p, size, pts, color, borde=borde)


#Tubo de ensayo (laboratorio) + llave inglesa (taller) compartiendo
#una placa base -para "Talleres y Laboratorios"-: une ambos conceptos
#en un solo glifo, a diferencia del martillo+destornillador genérico
#(🛠) que no decía nada sobre el componente de laboratorio.
def _talleres_laboratorios(pintor, size):

    _rect_redondeado(pintor, size, 0.06, 0.68, 0.94, 0.90, "#E2E8F0", radio=0.08, borde="#94A3B8")
    pintor.save()
    pintor.translate(size * 0.02, size * 0.00)
    pintor.scale(0.56, 0.56)
    _tubo_ensayo(pintor, size)
    pintor.restore()
    pintor.save()
    pintor.translate(size * 0.28, size * 0.24)
    pintor.scale(0.60, 0.60)
    _llave_inglesa(pintor, size, color="#64748B")
    pintor.restore()


#Tres fichas hexagonales superpuestas, cada una de un color -para
#"Áreas Técnicas"-: cada hexágono representa un área/especialidad
#técnica distinta agrupada bajo el mismo programa, a diferencia del
#edificio de escuela genérico (🏫) que no distingue "varias áreas".
def _areas_tecnicas(p, size):

    _hexagono(p, size, 0.36, 0.42, 0.26, "#38BDF8", borde="#0369A1")
    _hexagono(p, size, 0.64, 0.42, 0.26, "#818CF8", borde="#3730A3")
    _hexagono(p, size, 0.50, 0.70, 0.26, "#34D399", borde="#047857")


#Pequeño edificio de oficina con una insignia de check -para
#"Empresas de Pasantía"-: representa la empresa aliada externa donde
#el estudiante hace su pasantía, distinto del maletín genérico (💼) que
#ya se asocia en la app con "trabajo/negocios" en general, sin indicar
#que se trata de una alianza institucional.
def _empresa_pasantia(pintor, size):

    _rect_redondeado(pintor, size, 0.16, 0.14, 0.84, 0.90, "#0EA5E9", radio=0.05, borde="#075985")
    for fila in range(3):
        for col in range(2):
            x0= 0.26 + col * 0.28
            y0= 0.24 + fila * 0.20
            _rect_redondeado(pintor, size, x0, y0, x0 + 0.16, y0 + 0.12, "#E0F2FE", radio=0.02)
    _rect_redondeado(pintor, size, 0.42, 0.74, 0.58, 0.90, "#075985", radio=0.02)
    _disco(pintor, size, 0.62, 0.06, 0.94, 0.38, "#22C55E", borde="#15803D")
    pintor.setPen(_pluma("white", 2.0))
    pintor.drawLine(QPointF(0.69 * size, 0.22 * size), QPointF(0.76 * size, 0.29 * size))
    pintor.drawLine(QPointF(0.76 * size, 0.29 * size), QPointF(0.88 * size, 0.13 * size))


#Maletín de pasantía con un aro de progreso alrededor -para
#"Control de Pasantías"-: el aro comunica "seguimiento/supervisión a lo
#largo del tiempo" (mismo lenguaje visual que otros anillos de progreso
#de la app), sobre el propio maletín que ya representa la pasantía en
#sí, a diferencia del portapapeles genérico (📋) que no distinguía esta
#sección de cualquier otro listado.
def _control_pasantias(pintor, size):

    pintor.setPen(_pluma("#E2E8F0", 5.0))
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(_r(size, 0.06, 0.06, 0.94, 0.94), 0, 360 * 16)
    pintor.setPen(_pluma("#22C55E", 5.0))
    pintor.drawArc(_r(size, 0.06, 0.06, 0.94, 0.94), 90 * 16, -int(360 * 0.68 * 16))
    pintor.save()
    pintor.translate(size * 0.16, size * 0.16)
    pintor.scale(0.68, 0.68)
    _maletin(pintor, size)
    pintor.restore()


EMOJI_TALLERES_LABORATORIOS= "\uE01D"
EMOJI_AREAS_TECNICAS= "\uE01E"
EMOJI_EMPRESA_PASANTIA= "\uE01F"
EMOJI_CONTROL_PASANTIAS= "\uE020"
_REGISTRO.setdefault(EMOJI_TALLERES_LABORATORIOS, lambda pintor, tamano: _talleres_laboratorios(pintor, tamano))
_REGISTRO.setdefault(EMOJI_AREAS_TECNICAS, lambda pintor, tamano: _areas_tecnicas(pintor, tamano))
_REGISTRO.setdefault(EMOJI_EMPRESA_PASANTIA, lambda pintor, tamano: _empresa_pasantia(pintor, tamano))
_REGISTRO.setdefault(EMOJI_CONTROL_PASANTIAS, lambda pintor, tamano: _control_pasantias(pintor, tamano))


#Glifos privados para las tab bar de banco_tareas.py (pestaña "Entregas") y configuracion.py (pestañas
#"Académico", "Usuarios y Roles" y "Auditoría"). Las otras pestañas de esos módulos no se rediseñan porque su
#icono automático ya es coherente con su contenido (Catálogo de Tareas -> 📋 tarea, Institución -> 🏛, Apariencia
#-> 🎨, Seguridad y Backups -> 🛡, Mi Cuenta -> 👤); en cambio "Entregas" heredaba la bandeja de importar
#(EMOJI_IMPORTAR) por el keyword genérico 'entrega', "Académico" no coincide con ningún keyword (quedaba sin
#icono), y "Usuarios y Roles"/"Auditoría" caían en 👤 y 🛡 -exactamente los mismos dibujos que "Mi Cuenta" y
#"Seguridad y Backups" en la MISMA tab bar-, así que cada uno tiene un diseño propio:

#Bandeja de recepción con un documento entrando y un check -para
#la pestaña "Entregas" del Banco de Tareas: comunica "el estudiante
#entrega / el docente recibe y confirma", a diferencia de la bandeja
#con flecha de importar/exportar que solo habla de mover archivos.
def _entregas_tab(pintor, size):

    _rect_redondeado(pintor, size, 0.28, 0.10, 0.68, 0.58, "#F8FAFC", radio=0.05, borde="#94A3B8")
    for y in (0.22, 0.32, 0.42):
        _linea(pintor, size, 0.36, y, 0.60, y, "#CBD5E1", 1.8)
    _rect_redondeado(pintor, size, 0.10, 0.52, 0.90, 0.88, "#0EA5E9", radio=0.08, borde="#075985")
    _rect_redondeado(pintor, size, 0.24, 0.52, 0.76, 0.70, "#0369A1", radio=0.05)
    _disco(pintor, size, 0.56, 0.56, 0.92, 0.92, "#22C55E", borde="#15803D")
    pintor.setPen(_pluma("white", 2.0))
    pintor.drawLine(QPointF(0.65 * size, 0.74 * size), QPointF(0.72 * size, 0.81 * size))
    pintor.drawLine(QPointF(0.72 * size, 0.81 * size), QPointF(0.84 * size, 0.66 * size))


#Birrete sobre libro abierto -para la pestaña "Académico" de
#Configuración: el birrete representa lo estrictamente académico
#(grados, curriculum) y el libro abierto los parámetros de materias/
#grados/periodos que se configuran ahí, en vez del genérico 🎓 que la
#app ya reserva para "estudiante".
def _academico_tab(p, size):

    _poligono(p, size, [(0.08, 0.60), (0.50, 0.72), (0.50, 0.90), (0.08, 0.78)], "#F8FAFC", borde="#94A3B8")
    _poligono(p, size, [(0.92, 0.60), (0.50, 0.72), (0.50, 0.90), (0.92, 0.78)], "#E2E8F0", borde="#94A3B8")
    _poligono(p, size, [(0.50, 0.10), (0.94, 0.28), (0.50, 0.46), (0.06, 0.28)], "#1E293B", borde="#0F172A")
    _rect_redondeado(p, size, 0.42, 0.40, 0.58, 0.50, "#334155", radio=0.02)
    _linea(p, size, 0.90, 0.30, 0.90, 0.56, "#1E293B", 2.0)
    _disco(p, size, 0.84, 0.56, 0.96, 0.68, "#FACC15", borde="#CA8A04")


#Dos personas con una insignia de rol -para "Usuarios y Roles":
#la persona doble distingue la gestión multiusuario del 👤 solitario
#de "Mi Cuenta", y la insignia violeta (distinta del escudo verde de
#permisos/seguridad) representa los ROLES asignados a cada quien.
def _usuarios_roles_tab(p, size):

    _disco(p, size, 0.48, 0.10, 0.74, 0.36, "#94A3B8")
    _rect_redondeado(p, size, 0.40, 0.40, 0.82, 0.74, "#94A3B8", radio=0.10)
    _disco(p, size, 0.08, 0.14, 0.44, 0.50, "#38BDF8", borde="#0369A1")
    _rect_redondeado(p, size, 0.02, 0.54, 0.50, 0.94, "#38BDF8", radio=0.10, borde="#0369A1")
    _disco(p, size, 0.58, 0.56, 0.96, 0.94, "#8B5CF6", borde="#6D28D9")
    _estrella(p, size, 0.67, 0.65, 0.87, 0.85, "#EDE9FE", borde="#6D28D9", puntas=5)


#Bitácora con marcas de revisión y lupa -para la pestaña
#"Auditoría": renglones verificados (acciones registradas y
#revisables) + la lupa de "inspección del historial", con paleta
#violeta para no confundirse con el escudo 🛡 de "Seguridad y
#Backups" en la misma tab bar.
def _auditoria_tab(pintor, size):

    _rect_redondeado(pintor, size, 0.12, 0.06, 0.78, 0.84, "#F8FAFC", radio=0.06, borde="#94A3B8")
    _rect_redondeado(pintor, size, 0.28, 0.02, 0.62, 0.14, "#8B5CF6", radio=0.04)
    for y, marcada in ((0.28, True), (0.42, True), (0.56, False)):
        _disco(pintor, size, 0.20, y - 0.045, 0.30, y + 0.045, "#22C55E" if marcada else "#CBD5E1")
        if marcada:
            pintor.setPen(_pluma("white", 1.5))
            pintor.drawLine(QPointF(0.22 * size, y * size), QPointF(0.245 * size, (y + 0.032) * size))
            pintor.drawLine(QPointF(0.245 * size, (y + 0.032) * size), QPointF(0.285 * size, (y - 0.035) * size))
        _linea(pintor, size, 0.38, y, 0.68, y, "#CBD5E1", 1.8)
    _disco(pintor, size, 0.48, 0.46, 0.84, 0.82, "#C4B5FD", borde="#6D28D9")
    _disco(pintor, size, 0.54, 0.52, 0.78, 0.76, "#F5F3FF")
    _linea(pintor, size, 0.82, 0.80, 0.94, 0.92, "#6D28D9", 4.0)


#Edificio universitario con tres accesos: Facultades.
def _facultades_universidad_tab(p, size):

    _poligono(p, size, [(0.08, 0.34), (0.50, 0.10), (0.92, 0.34)], "#4F46E5", borde="#3730A3")
    _rect_redondeado(p, size, 0.14, 0.34, 0.86, 0.84, "#EEF2FF", radio=0.03, borde="#818CF8")
    for x in (0.25, 0.45, 0.65):
        _rect_redondeado(p, size, x, 0.48, x + 0.11, 0.84, "#6366F1", radio=0.02)
    _linea(p, size, 0.10, 0.88, 0.90, 0.88, "#3730A3", 2.3)


#Ruta académica con meta: Carreras.
def _carreras_universidad_tab(p, size):

    _linea(p, size, 0.16, 0.78, 0.43, 0.55, "#0EA5E9", 3.0)
    _linea(p, size, 0.43, 0.55, 0.70, 0.32, "#0EA5E9", 3.0)
    _poligono(p, size, [(0.66, 0.20), (0.90, 0.27), (0.73, 0.47)], "#0284C7", borde="#0369A1")
    _disco(p, size, 0.08, 0.70, 0.30, 0.92, "#38BDF8", borde="#0369A1")
    _disco(p, size, 0.34, 0.46, 0.53, 0.65, "#FACC15", borde="#CA8A04")


#Malla de asignaturas conectadas: Malla Curricular.
def _pensum_universidad_tab(p, size):

    for y in (0.20, 0.48, 0.76):
        _linea(p, size, 0.22, y, 0.78, y, "#94A3B8", 1.6)
    for x in (0.22, 0.50, 0.78):
        _linea(p, size, x, 0.20, x, 0.76, "#94A3B8", 1.6)
    for x, y, color in ((0.22, 0.20, "#8B5CF6"), (0.50, 0.48, "#22C55E"), (0.78, 0.76, "#F97316")):
        _rect_redondeado(p, size, x - 0.10, y - 0.09, x + 0.10, y + 0.09, color, radio=0.04)


EMOJI_TAB_ENTREGAS= "\uE021"
EMOJI_TAB_ACADEMICO= "\uE022"
EMOJI_TAB_USUARIOS_ROLES= "\uE023"
EMOJI_TAB_AUDITORIA= "\uE024"
EMOJI_TAB_FACULTADES= "\uE025"
EMOJI_TAB_CARRERAS= "\uE026"
EMOJI_TAB_PENSUM= "\uE027"
_REGISTRO.setdefault(EMOJI_TAB_ENTREGAS, lambda pintor, tamano: _entregas_tab(pintor, tamano))
_REGISTRO.setdefault(EMOJI_TAB_ACADEMICO, lambda pintor, tamano: _academico_tab(pintor, tamano))
_REGISTRO.setdefault(EMOJI_TAB_USUARIOS_ROLES, lambda pintor, tamano: _usuarios_roles_tab(pintor, tamano))
_REGISTRO.setdefault(EMOJI_TAB_AUDITORIA, lambda pintor, tamano: _auditoria_tab(pintor, tamano))
_REGISTRO.setdefault(EMOJI_TAB_FACULTADES, lambda pintor, tamano: _facultades_universidad_tab(pintor, tamano))
_REGISTRO.setdefault(EMOJI_TAB_CARRERAS, lambda pintor, tamano: _carreras_universidad_tab(pintor, tamano))
_REGISTRO.setdefault(EMOJI_TAB_PENSUM, lambda pintor, tamano: _pensum_universidad_tab(pintor, tamano))


#Glifos privados para los 4 botones de acción del módulo de Sincronización ("Subir Cambios", "Descargar
#Novedades", "Subir (directo)" y "Descargar (directo)"). Antes todos caían en la misma bandeja de
#importar/exportar (EMOJI_IMPORTAR/ EMOJI_EXPORTAR vía el keyword genérico 'subir'/'descargar' de iconos_auto),
#así que los 4 botones eran indistinguibles entre sí y con cualquier otro botón de importar/exportar de la app.
#Cada uno combina: el ORIGEN/DESTINO (nube = carpeta sincronizada tipo Drive/OneDrive; monitor/servidor =
#conexión directa vía backend/OAuth), la DIRECCIÓN (flecha verde arriba = envía; flecha azul abajo = recibe) y
#la base de datos local que se mueve.

#Silueta de nube (carpeta sincronizada por cliente de nube).
def _nube_sincronizacion(p, size):

    _rect_redondeado(p, size, 0.20, 0.16, 0.80, 0.34, "#E2E8F0", radio=0.08)
    _disco(p, size, 0.26, 0.06, 0.56, 0.36, "#E2E8F0")
    _disco(p, size, 0.48, 0.08, 0.76, 0.32, "#E2E8F0")


#Monitor/servidor (conexión directa al backend vía OAuth/API).
def _servidor_directo(p, size):

    _rect_redondeado(p, size, 0.22, 0.02, 0.78, 0.30, "#64748B", radio=0.05, borde="#334155")
    _rect_redondeado(p, size, 0.28, 0.08, 0.72, 0.24, "#0EA5E9", radio=0.02)
    _rect_redondeado(p, size, 0.46, 0.30, 0.54, 0.38, "#475569", radio=0.02)


#Cilindro estilizado: la base de datos local que se envía/recibe.
def _base_datos_local(p, size):

    _rect_redondeado(p, size, 0.14, 0.76, 0.86, 0.96, "#0EA5E9", radio=0.06, borde="#075985")
    _rect_redondeado(p, size, 0.20, 0.81, 0.80, 0.88, "#7DD3FC", radio=0.03)


#Flecha gruesa de dirección (verde arriba = envía, azul abajo = recibe).
def _flecha_sincronizacion(p, size, hacia_arriba, color, borde):

    if hacia_arriba:
        _rect_redondeado(p, size, 0.44, 0.50, 0.56, 0.74, color, radio=0.02, borde=borde)
        _poligono(p, size, [(0.50, 0.30), (0.72, 0.54), (0.28, 0.54)], color, borde=borde)
    else:
        _rect_redondeado(p, size, 0.44, 0.30, 0.56, 0.54, color, radio=0.02, borde=borde)
        _poligono(p, size, [(0.50, 0.74), (0.28, 0.50), (0.72, 0.50)], color, borde=borde)


#Nube + flecha verde hacia arriba + base de datos -"Subir Cambios":
#los datos locales de este equipo viajan hacia la carpeta sincronizada.
def _sync_subir(p, size):

    _nube_sincronizacion(p, size)
    _base_datos_local(p, size)
    _flecha_sincronizacion(p, size, True, "#22C55E", "#15803D")


#Nube + flecha azul hacia abajo + base de datos -"Descargar Novedades":
#los cambios que otros equipos subieron a la carpeta llegan a este equipo.
def _sync_descargar(p, size):

    _nube_sincronizacion(p, size)
    _base_datos_local(p, size)
    _flecha_sincronizacion(p, size, False, "#3B82F6", "#1D4ED8")


#Servidor + flecha verde hacia arriba + base de datos -"Subir (directo)":
#como Subir Cambios, pero hablando directo con el backend/API (Drive,
#Dropbox, OneDrive, servidor institucional) en vez de la carpeta local.
def _sync_subir_directo(p, size):

    _servidor_directo(p, size)
    _base_datos_local(p, size)
    _flecha_sincronizacion(p, size, True, "#22C55E", "#15803D")


#Servidor + flecha azul hacia abajo + base de datos -"Descargar (directo)":
#espejo de Subir (directo), trayendo cambios directo desde el backend.
def _sync_descargar_directo(p, size):

    _servidor_directo(p, size)
    _base_datos_local(p, size)
    _flecha_sincronizacion(p, size, False, "#3B82F6", "#1D4ED8")


EMOJI_SYNC_SUBIR= "\uE025"
EMOJI_SYNC_DESCARGAR= "\uE026"
EMOJI_SYNC_SUBIR_DIRECTO= "\uE027"
EMOJI_SYNC_DESCARGAR_DIRECTO= "\uE028"
_REGISTRO.setdefault(EMOJI_SYNC_SUBIR, lambda pintor, tamano: _sync_subir(pintor, tamano))
_REGISTRO.setdefault(EMOJI_SYNC_DESCARGAR, lambda pintor, tamano: _sync_descargar(pintor, tamano))
_REGISTRO.setdefault(EMOJI_SYNC_SUBIR_DIRECTO, lambda pintor, tamano: _sync_subir_directo(pintor, tamano))
_REGISTRO.setdefault(EMOJI_SYNC_DESCARGAR_DIRECTO, lambda pintor, tamano: _sync_descargar_directo(pintor, tamano))


#Glifos privados para los botones de paginación de las tablas (paginacion.py:
#primera/anterior/siguiente/última). Antes usaban los emojis de teclado multimedia ⏮/⏭ y los triángulos ▶/◀ (o
#se apoyaban en las flechas ⬅/➡ del mapa automático), que se ven distinto según la fuente del sistema. Cada uno
#es un CHEVRON redondeado con terminaciones "round cap" —mismo lenguaje visual que el resto de iconos
#vectoriales de la app— en celeste (#38BDF8), con una barra gris vertical para "primera"/"última" (el clásico
#|◀ y ▶| que comunica "salto al extremo").

#Chevron (>) redondeado sin mango de flecha, celeste.
def _chevron_paginacion(pintor, size, hacia_izquierda, x0=0.36, x1=0.64):

    pen= _pluma("#38BDF8", size * 0.16)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pintor.setPen(pen)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    if hacia_izquierda:
        puntos= [(x1, 0.22), (x0, 0.50), (x1, 0.78)]
    else:
        puntos= [(x0, 0.22), (x1, 0.50), (x0, 0.78)]
    pintor.drawPolyline(QPolygonF([QPointF(x * size, y * size) for x, y in puntos]))


#Barra vertical gris del salto-a-extremo (|◀ / ▶|).
def _barra_extremo_paginacion(p, size, pos_x):

    _rect_redondeado(p, size, pos_x, 0.20, pos_x + 0.11, 0.80, "#64748B", radio=0.045)


def _pag_primera(p, size):

    _barra_extremo_paginacion(p, size, 0.10)
    _chevron_paginacion(p, size, True, 0.40, 0.66)


def _pag_anterior(p, size):

    _chevron_paginacion(p, size, True, 0.32, 0.68)


def _pag_siguiente(p, size):

    _chevron_paginacion(p, size, False, 0.32, 0.68)


def _pag_ultima(p, size):

    _barra_extremo_paginacion(p, size, 0.79)
    _chevron_paginacion(p, size, False, 0.34, 0.60)


EMOJI_PAG_PRIMERA= "\uE029"
EMOJI_PAG_ANTERIOR= "\uE02A"
EMOJI_PAG_SIGUIENTE= "\uE02B"
EMOJI_PAG_ULTIMA= "\uE02C"
_REGISTRO.setdefault(EMOJI_PAG_PRIMERA, lambda pintor, tamano: _pag_primera(pintor, tamano))
_REGISTRO.setdefault(EMOJI_PAG_ANTERIOR, lambda pintor, tamano: _pag_anterior(pintor, tamano))
_REGISTRO.setdefault(EMOJI_PAG_SIGUIENTE, lambda pintor, tamano: _pag_siguiente(pintor, tamano))
_REGISTRO.setdefault(EMOJI_PAG_ULTIMA, lambda pintor, tamano: _pag_ultima(pintor, tamano))


#Glifos privados para la barra de herramientas del modo Excel del editor de reportes (reportes_editor.py):
#insertar/eliminar fila y columna. Estructura común: una CUADRÍCULA de hoja (3×3) con la fila/columna central
#resaltada (verde = se inserta, rojo = se elimina) y un disco con el signo +/− en la esquina inferior derecha
#que desambigua la operación de un vistazo.

#Marco + cuadrícula 3x3 que representa la hoja de cálculo.
def _cuadricula_hoja(p, size, color="#94A3B8"):

    for y in (0.08, 0.36, 0.64, 0.92):
        _linea(p, size, 0.08, y, 0.92, y, color, 1.6)
    for x in (0.08, 0.36, 0.64, 0.92):
        _linea(p, size, x, 0.08, x, 0.92, color, 1.6)


#Banda central de la cuadrícula (fila o columna afectada).
def _banda_hoja(p, size, color):

    _rect_redondeado(p, size, 0.09, 0.37, 0.91, 0.63, color, radio=0.02)


#Disco con + (insertar, verde) o − (eliminar, rojo) en la esquina.
def _signo_operacion(pintor, size, insertar):

    color, borde= ("#22C55E", "#15803D") if insertar else ("#EF4444", "#B91C1C")
    _disco(pintor, size, 0.60, 0.60, 0.94, 0.94, color, borde=borde)
    pintor.setPen(_pluma("white", 2.4))
    pintor.drawLine(QPointF(0.69 * size, 0.77 * size), QPointF(0.85 * size, 0.77 * size))
    if insertar:
        pintor.drawLine(QPointF(0.77 * size, 0.69 * size), QPointF(0.77 * size, 0.85 * size))


def _insertar_fila_hoja(p, size):

    _banda_hoja(p, size, "#BBF7D0")
    _cuadricula_hoja(p, size)
    _signo_operacion(p, size, True)


def _eliminar_fila_hoja(p, size):

    _banda_hoja(p, size, "#FECACA")
    _cuadricula_hoja(p, size)
    _signo_operacion(p, size, False)


def _insertar_columna_hoja(p, size):

    _rect_redondeado(p, size, 0.37, 0.09, 0.63, 0.91, "#BBF7D0", radio=0.02)
    _cuadricula_hoja(p, size)
    _signo_operacion(p, size, True)


def _eliminar_columna_hoja(p, size):

    _rect_redondeado(p, size, 0.37, 0.09, 0.63, 0.91, "#FECACA", radio=0.02)
    _cuadricula_hoja(p, size)
    _signo_operacion(p, size, False)


EMOJI_INSERTAR_FILA= "\uE02D"
EMOJI_ELIMINAR_FILA= "\uE02E"
EMOJI_INSERTAR_COLUMNA= "\uE02F"
EMOJI_ELIMINAR_COLUMNA= "\uE030"
_REGISTRO.setdefault(EMOJI_INSERTAR_FILA, lambda pintor, tamano: _insertar_fila_hoja(pintor, tamano))
_REGISTRO.setdefault(EMOJI_ELIMINAR_FILA, lambda pintor, tamano: _eliminar_fila_hoja(pintor, tamano))
_REGISTRO.setdefault(EMOJI_INSERTAR_COLUMNA, lambda pintor, tamano: _insertar_columna_hoja(pintor, tamano))
_REGISTRO.setdefault(EMOJI_ELIMINAR_COLUMNA, lambda pintor, tamano: _eliminar_columna_hoja(pintor, tamano))


#Cuadro de texto para el modo Excel del editor de reportes: un
#recuadro con borde y una "T" dibujada con trazos (sin depender de
#fuentes del sistema), el glifo que Word/Excel usan para su botón
#de cuadro de texto.
def _cuadro_texto_hoja(pintor, size):

    _rect_redondeado(pintor, size, 0.10, 0.16, 0.90, 0.84, "#F8FAFC", radio=0.10, borde="#64748B")
    pintor.setPen(_pluma("#0EA5E9", size * 0.13))
    pintor.setPen(_pluma("#0EA5E9", max(1.0, size * 0.11)))
    cap= pintor.pen()
    cap.setCapStyle(Qt.PenCapStyle.RoundCap)
    pintor.setPen(cap)
    #Techo de la T
    pintor.drawLine(QPointF(0.32 * size, 0.36 * size), QPointF(0.68 * size, 0.36 * size))
    #Palo central de la T
    pintor.drawLine(QPointF(0.50 * size, 0.36 * size), QPointF(0.50 * size, 0.70 * size))


EMOJI_CUADRO_TEXTO= "\uE031"
_REGISTRO.setdefault(EMOJI_CUADRO_TEXTO, lambda pintor, tamano: _cuadro_texto_hoja(pintor, tamano))


#Saludo del dashboard (día / noche) — versión "hero", más detallada y con más presencia que el ☀/🌙 genérico de
#arriba (pensados para 16-20px sueltos en medio de una frase). Estos dos son los únicos iconos que necesita la
#cabecera del Dashboard, así que llevan degradado, halo suave y -en el caso nocturno- un par de estrellas, para
#que se vean bien a los ~26-30px con los que se usan junto al saludo ("Buenos días" / "Buenas tardes" / "Buenas
#noches"): mañana y tarde comparten el icono de sol -ambas son "de día"-, y la noche usa la luna con estrellas.
#Sol con halo degradado y rayos de grosor variable -más lleno y con
#más profundidad que el `_sol` genérico usado suelto en frases.
def _saludo_dia(pintor, size):

    halo= _r(size, 0.10, 0.10, 0.90, 0.90)
    pintor.setPen(_sin_pluma())
    pintor.setBrush(_degradado(halo, "#FDE68A", "#FBBF2400"))
    pintor.drawEllipse(halo)
    for i in range(12):
        ang= math.pi / 6 * i
        largo= 0.40 if i % 3 == 0 else 0.35
        x0, y0= 0.5 + 0.30 * math.cos(ang), 0.5 + 0.30 * math.sin(ang)
        x1, y1= 0.5 + largo * math.cos(ang), 0.5 + largo * math.sin(ang)
        _linea(pintor, size, x0, y0, x1, y1, "#F59E0B", 2.6 if i % 3 == 0 else 1.8)
    nucleo= _r(size, 0.26, 0.26, 0.74, 0.74)
    pintor.setBrush(_degradado(nucleo, "#FDE047", "#F59E0B"))
    pintor.setPen(_pluma("#EAB308", 1.0))
    pintor.drawEllipse(nucleo)
    brillo= _r(size, 0.36, 0.33, 0.52, 0.46)
    pintor.setPen(_sin_pluma())
    pintor.setBrush(QBrush(QColor(255, 255, 255, 140)))
    pintor.drawEllipse(brillo)


#Luna creciente con degradado y un par de estrellas -más lleno y con
#más profundidad que el `_luna` genérico usado suelto en frases.
def _saludo_noche(pintor, size):

    path= QPainterPath()
    path.addEllipse(_r(size, 0.14, 0.14, 0.82, 0.82))
    recorte= QPainterPath()
    recorte.addEllipse(_r(size, 0.30, 0.06, 0.98, 0.74))
    cuerpo= path.subtracted(recorte)
    pintor.setBrush(_degradado(_r(size, 0.14, 0.14, 0.82, 0.82), "#E0E7FF", "#A5B4FC"))
    pintor.setPen(_pluma("#818CF8", 1.0))
    pintor.drawPath(cuerpo)
    _estrella(pintor, size, 0.68, 0.14, 0.86, 0.32, "#FDE68A", puntas=4)
    _estrella(pintor, size, 0.80, 0.42, 0.92, 0.54, "#FDE68A", puntas=4)


EMOJI_SALUDO_DIA= "\uE032"
EMOJI_SALUDO_NOCHE= "\uE033"
_REGISTRO.setdefault(EMOJI_SALUDO_DIA, lambda pintor, tamano: _saludo_dia(pintor, tamano))
_REGISTRO.setdefault(EMOJI_SALUDO_NOCHE, lambda pintor, tamano: _saludo_noche(pintor, tamano))


#Silueta "sin foto" — usada por paginacion.py como placeholder en la columna "Foto" de las tablas
#(Estudiantes/Profesores/Personal) cuando el registro todavía no tiene fotografía guardada. Un solo tono claro
#y semi-transparente, pensada para dibujarse SOBRE un círculo de fondo (ver pixmap_placeholder_foto_tabla en
#paginacion.py) -por eso no lleva su propio fondo, a diferencia de EMOJI_SALUDO_DIA/NOCHE de arriba.
def _silueta_persona_placeholder(pintor, size):

    color= QColor("#FFFFFF")
    color.setAlpha(235)
    pintor.setPen(_sin_pluma())
    pintor.setBrush(QBrush(color))
    pintor.drawEllipse(_r(size, 0.30, 0.06, 0.70, 0.46))
    pintor.drawEllipse(_r(size, 0.06, 0.52, 0.94, 1.30))


EMOJI_SILUETA_PLACEHOLDER= "\uE034"
_REGISTRO.setdefault(EMOJI_SILUETA_PLACEHOLDER, lambda pintor, tamano: _silueta_persona_placeholder(pintor, tamano))

#Glifo privado para los botones "Elegir/Cambiar y Recortar" de imágenes (Foto de estudiante/personal/profesor,
#Logotipo, Firma Digital): imagen + tijeras -ver _foto_recortar-, en vez de solo las tijeras sueltas (✂) que
#usaban antes y no dejaban claro que el botón abre un selector de imagen.
EMOJI_FOTO_RECORTAR= "\uE036"
_REGISTRO.setdefault(EMOJI_FOTO_RECORTAR, lambda pintor, tamano: _foto_recortar(pintor, tamano))


#Respaldo genérico (por si algún emoji nuevo aparece en el futuro y todavía no tiene una forma dedicada
#arriba): círculo de color derivado del propio caracter + su primera letra/silueta genérica, para que nunca se
#quede sin icono ni rompa la UI.
_PALETA_RESPALDO= ["#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4", "#F472B6"]


#Respaldo para emojis futuros sin dibujo dedicado: ficha redondeada
#con degradado y el propio caracter dibujado encima (nunca un círculo
#anónimo y repetitivo).
def _dibujar_respaldo(pintor, size, caracter):

    color= _PALETA_RESPALDO[abs(hash(caracter)) % len(_PALETA_RESPALDO)]
    ficha= _r(size, 0.08, 0.08, 0.92, 0.92)
    pintor.setBrush(_degradado(ficha, color, "#1E293B"))
    pintor.setPen(_pluma("#1E293B", 1.2))
    pintor.drawRoundedRect(ficha, size * 0.18, size * 0.18)
    from PySide6.QtGui import QFont
    fuente= QFont()
    fuente.setPixelSize(max(8, int(size * 0.55)))
    fuente.setBold(True)
    pintor.setFont(fuente)
    pintor.setPen(QColor("white"))
    pintor.drawText(ficha, Qt.AlignmentFlag.AlignCenter, caracter[0] if caracter else "?")


#API PÚBLICA
#Devuelve un QPixmap (transparente, cuadrado `size`x`size`) con el
#icono multicolor equivalente a `caracter`. Cacheado.
def pixmap_emoji(caracter, size=TAMANO_DEFECTO):

    clave= (caracter, size)
    if clave in _cache_pixmap:
        return _cache_pixmap[clave]
    pix, p= _nuevo_lienzo(size)
    dibujar= _REGISTRO.get(caracter)
    try:

        if dibujar:
            dibujar(p, size)
        else:
            _dibujar_respaldo(p, size, caracter)
    finally:
        p.end()
    _cache_pixmap[clave]= pix
    return pix


#Devuelve un QIcon cacheado equivalente a `caracter` (mismo tamaño
#base para todos los estados; Qt lo escala si se pide otro size).
def icono_emoji(caracter, size=TAMANO_DEFECTO):

    clave= (caracter, size)
    if clave in _cache_icon:
        return _cache_icon[clave]
    icono= QIcon(pixmap_emoji(caracter, size))
    _cache_icon[clave]= icono
    return icono


#True si `caracter` tiene un dibujo dedicado (no el respaldo genérico).
def emoji_soportado(caracter):

    return caracter in _REGISTRO


#Quita del `texto` cualquier caracter que tenga icono dedicado aquí
#(y cualquier espacio duplicado que quede), para usarlo como el texto
#puro de un botón/label que ahora lleva el emoji como QIcon aparte.
#
#Ej.: quitar_emojis_texto("💾 Guardar")  ->  "Guardar"
def quitar_emojis_texto(texto):

    resultado= []
    for ch in texto:
        if ch in _REGISTRO:
            continue
        resultado.append(ch)
    limpio= "".join(resultado)
    return " ".join(limpio.split())


#Devuelve un tag <img> en base64 con el icono equivalente a `caracter`,
#listo para insertar en texto enriquecido (QMessageBox.setText, un QLabel
#con texto HTML, etc.) donde no se puede colocar un QIcon aparte -por
#ejemplo, dentro de una lista de detalles como '🎓 Curso: 5to A'.
#Al ir incrustado como imagen (no como el propio caracter emoji), se ve
#con el MISMO dibujo plano y consistente que el resto de la app, en vez
#de depender de la fuente de emoji del sistema operativo.
def html_icono_emoji(caracter, size=14):

    from PySide6.QtCore import QBuffer
    import base64
    clave= (caracter, size)
    if clave in _cache_html:
        return _cache_html[clave]
    pix= pixmap_emoji(caracter, size)
    buffer= QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pix.save(buffer, "PNG")
    b64= base64.b64encode(bytes(buffer.data())).decode("ascii")
    tag= (f'<img src="data:image/png;base64,{b64}" width="{size}" height="{size}" '
           f'style="vertical-align:middle;">')
    _cache_html[clave]= tag
    return tag
