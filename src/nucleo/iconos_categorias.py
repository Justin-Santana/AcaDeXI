"""iconos_categorias.py — Iconos vectoriales para categorías de distintos
módulos de AcaDeXI. Incluye TRES secciones:

1. Monocromo (`pixmap_categoria`/`icono_categoria`, la parte original de
   este archivo): un solo trazo/color que cambia -gris inactivo, blanco
   activo- igual que el TEXTO del chip. Se usa en los "chips" seleccionables
   de categoría/naturaleza (formulario y filtros) de Observaciones, donde ese
   cambio de color según el estado es precisamente el efecto que se quiere.

2. Multicolor de Observaciones (`pixmap_categoria_color`/`icono_categoria_color`):
   el dibujo COMPLETO -varios colores fijos, como los iconos "de verdad" de
   iconos_emoji.py-, para todo lugar donde el icono se vea SOLO (no dentro de
   una pastilla con estado propio): la columna "Categorías"/"Tipo" de la
   tabla de Observaciones, el detalle de una observación, etc. Ahí un trazo
   monocromo gris se veía plano y costaba distinguir una categoría de otra a
   simple vista; la versión multicolor reutiliza, cuando encaja bien, los
   mismos dibujos ricos que ya existen en iconos_emoji.py (trofeo, lupa,
   reloj, diana, bombilla...) en vez de inventar un estilo nuevo.

3. Multicolor de Materiales (`pixmap_categoria_material`/`icono_categoria_material`,
   al final de este archivo): mismo espíritu que la sección 2, pero para las
   categorías de inventario del módulo de Materiales (Libros, Laboratorio,
   Taller, Deportivo...). Antes ese módulo dejaba que el propio usuario
   escribiera un emoji a mano en un campo de texto libre y lo mostraba tal
   cual -un glifo de fuente crudo, dependiente del sistema operativo, el
   único lugar de la app que aún hacía eso-. Ahora ofrece un selector con un
   set curado de íconos vectoriales (`CATEGORIAS_SUGERIDAS_MATERIAL`), y la
   función de dibujo resuelve en cascada: clave curada -> emoji suelto ya
   reconocido por iconos_emoji.py (retrocompatibilidad con categorías
   creadas a mano antes de este selector) -> caja genérica de respaldo.

Uso:
    from iconos_categorias import pixmap_categoria, icono_categoria
    lbl_icono.setPixmap(pixmap_categoria("puntualidad", "#F59E0B", 16))

    from iconos_categorias import pixmap_categoria_color
    lbl_icono.setPixmap(pixmap_categoria_color("puntualidad", 18))

    from iconos_categorias import pixmap_categoria_material
    lbl_icono.setPixmap(pixmap_categoria_material("laboratorio", 18))
"""
import re
import unicodedata

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QIcon, QPainterPath, QColor, QBrush, QPolygonF

from src.nucleo.iconos_emoji import (_r, _pluma, _sin_pluma, _linea, _rect_redondeado,
                           _poligono, _estrella, _check, _disco, _nuevo_lienzo,
                           _corazon, _grafico_lineas,
                           # Dibujos MULTICOLOR reutilizados tal cual para
                           # pixmap_categoria_color (ver docstring del módulo):
                           _sonrisa, _triangulo_alerta, _persona, _bombilla,
                           _lupa, _trofeo, _diana, _escudo, _reloj, _calendario,
                           _grafico_barras, _manos_saludo, _clip_tablero, _sobre,
                           # Reutilizados tal cual para pixmap_categoria_material
                           # (sección 3, ver más abajo):
                           _libro, _tubo_ensayo, _llave_inglesa, _pantalla,
                           _camara, _paleta, _paquete,
                           emoji_soportado, pixmap_emoji)


# ============================================================
# CATEGORÍAS
# ============================================================
def _cat_rendimiento(p, size, color):
    """Barras ascendentes: rendimiento académico en alza."""
    _rect_redondeado(p, size, 0.20, 0.58, 0.36, 0.82, color, radio=0.05)
    _rect_redondeado(p, size, 0.42, 0.42, 0.58, 0.82, color, radio=0.05)
    _rect_redondeado(p, size, 0.64, 0.24, 0.80, 0.82, color, radio=0.05)


def _cat_tareas(p, size, color):
    """Portapapeles con una tarea marcada."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawRoundedRect(_r(size, 0.24, 0.16, 0.76, 0.86), 0.06 * size, 0.06 * size)
    _rect_redondeado(p, size, 0.40, 0.10, 0.60, 0.20, color, radio=0.03)
    _check(p, size, color, x0=0.34, y0=0.52, x1=0.45, y1=0.62, x2=0.64, y2=0.40, ancho=2.0)
    _linea(p, size, 0.34, 0.72, 0.66, 0.72, color, 2.0)


def _cat_participacion(p, size, color):
    """Persona con el brazo en alto: participar / levantar la mano en clase."""
    p.setBrush(QBrush(QColor(color)))
    p.setPen(_sin_pluma())
    p.drawEllipse(_r(size, 0.38, 0.12, 0.58, 0.32))  # cabeza
    _rect_redondeado(p, size, 0.32, 0.38, 0.60, 0.82, color, radio=0.16)  # cuerpo
    p.setPen(_pluma(color, 3.2))
    p.drawLine(QPointF(0.56 * size, 0.44 * size), QPointF(0.82 * size, 0.14 * size))  # brazo
    p.setPen(_sin_pluma())
    _disco(p, size, 0.76, 0.06, 0.90, 0.20, color)  # mano en la punta


def _cat_comprension(p, size, color):
    """Bombilla: comprensión / entendimiento del tema."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawEllipse(_r(size, 0.28, 0.12, 0.72, 0.56))
    _linea(p, size, 0.40, 0.54, 0.40, 0.70, color, 2.0)
    _linea(p, size, 0.60, 0.54, 0.60, 0.70, color, 2.0)
    _rect_redondeado(p, size, 0.40, 0.70, 0.60, 0.80, color, radio=0.04)
    _linea(p, size, 0.42, 0.86, 0.58, 0.86, color, 2.0)


def _cat_esfuerzo(p, size, color):
    """Llama: esfuerzo y energía invertida."""
    path = QPainterPath()
    s = size
    path.moveTo(0.50 * s, 0.10 * s)
    path.cubicTo(0.74 * s, 0.32 * s, 0.68 * s, 0.48 * s, 0.58 * s, 0.40 * s)
    path.cubicTo(0.68 * s, 0.58 * s, 0.62 * s, 0.80 * s, 0.44 * s, 0.88 * s)
    path.cubicTo(0.56 * s, 0.78 * s, 0.50 * s, 0.68 * s, 0.44 * s, 0.68 * s)
    path.cubicTo(0.38 * s, 0.78 * s, 0.28 * s, 0.72 * s, 0.30 * s, 0.56 * s)
    path.cubicTo(0.18 * s, 0.66 * s, 0.22 * s, 0.28 * s, 0.50 * s, 0.10 * s)
    path.closeSubpath()
    p.setBrush(QBrush(QColor(color)))
    p.setPen(_sin_pluma())
    p.drawPath(path)


def _cat_equipo(p, size, color):
    """Dos personas lado a lado (cabeza + torso): trabajo en equipo. Antes
    eran dos círculos superpuestos -se leía como un diagrama de conjuntos
    genérico (intersección/Venn), no comunicaba 'trabajar con otros' de
    forma clara-. Con dos siluetas de persona el icono se entiende de un
    vistazo, igual que ya pasa con la versión multicolor (_manos_saludo)."""
    for cx in (0.34, 0.68):
        _disco(p, size, cx - 0.11, 0.14, cx + 0.11, 0.36, color)
        _poligono(p, size, [
            (cx - 0.20, 0.88), (cx - 0.15, 0.48), (cx + 0.15, 0.48), (cx + 0.20, 0.88)
        ], color)


def _cat_buena_conducta(p, size, color):
    """Estrella: buena conducta."""
    _estrella(p, size, 0.18, 0.16, 0.82, 0.80, color)


def _cat_conducta(p, size, color):
    """Triángulo de aviso con exclamación: conducta inadecuada."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.2))
    tri = QPolygonF([QPointF(0.5 * size, 0.14 * size), QPointF(0.88 * size, 0.82 * size),
                      QPointF(0.12 * size, 0.82 * size)])
    p.drawPolygon(tri)
    _linea(p, size, 0.5, 0.40, 0.5, 0.62, color, 2.4)
    _disco(p, size, 0.465, 0.68, 0.535, 0.75, color)


def _cat_conflicto(p, size, color):
    """Dos flechas grandes enfrentadas: choque / conflicto entre estudiantes."""
    p.setPen(_pluma(color, 3.2))
    p.drawLine(QPointF(0.12 * size, 0.5 * size), QPointF(0.40 * size, 0.5 * size))
    p.drawLine(QPointF(0.60 * size, 0.5 * size), QPointF(0.88 * size, 0.5 * size))
    p.setPen(_sin_pluma())
    _poligono(p, size, [(0.12, 0.36), (0.12, 0.64), (0.40, 0.50)], color)
    _poligono(p, size, [(0.88, 0.36), (0.88, 0.64), (0.60, 0.50)], color)


def _cat_puntualidad(p, size, color):
    """Reloj: llegar a tiempo."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawEllipse(_r(size, 0.14, 0.14, 0.86, 0.86))
    _linea(p, size, 0.5, 0.5, 0.5, 0.28, color, 2.0)
    _linea(p, size, 0.5, 0.5, 0.68, 0.56, color, 2.0)


def _cat_asistencia(p, size, color):
    """Calendario con un día marcado: registro de asistencia en general.
    Antes era un check dentro de un círculo -que significa literalmente
    'presente'-, así que quedaba directamente equivocado para plantillas
    como 'Ausencias reiteradas' o 'Llegadas tardías', que usan esta MISMA
    categoría ('asistencia' cubre presencia, tardanza y ausencia, no solo
    lo positivo). Un calendario no afirma nada sobre el resultado, solo
    que se trata de un registro de asistencia."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawRoundedRect(_r(size, 0.14, 0.22, 0.86, 0.88), 0.08 * size, 0.08 * size)
    _linea(p, size, 0.14, 0.40, 0.86, 0.40, color, 2.0)
    _linea(p, size, 0.32, 0.12, 0.32, 0.28, color, 2.2)
    _linea(p, size, 0.68, 0.12, 0.68, 0.28, color, 2.2)
    _disco(p, size, 0.42, 0.56, 0.58, 0.72, color)


def _cat_actitud(p, size, color):
    """Diana: motivación, apuntar a una meta."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 1.8))
    for radio in (0.42, 0.28, 0.14):
        p.drawEllipse(_r(size, 0.5 - radio, 0.5 - radio, 0.5 + radio, 0.5 + radio))


def _cat_bienestar(p, size, color):
    """Corazón: bienestar emocional."""
    _corazon(p, size, color)


def _cat_mejora(p, size, color):
    """Línea de tendencia ascendente: mejoría notable."""
    _grafico_lineas(p, size, color)


def _cat_reconocimiento(p, size, color):
    """Medalla: reconocimiento / logro."""
    _linea(p, size, 0.36, 0.10, 0.50, 0.46, color, 2.2)
    _linea(p, size, 0.64, 0.10, 0.50, 0.46, color, 2.2)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.2))
    p.drawEllipse(_r(size, 0.26, 0.42, 0.74, 0.90))
    _estrella(p, size, 0.40, 0.56, 0.60, 0.76, color)


def _cat_comunicacion_padres(p, size, color):
    """Globo de mensaje: comunicación con la familia."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawRoundedRect(_r(size, 0.14, 0.18, 0.86, 0.68), 0.10 * size, 0.10 * size)
    _poligono(p, size, [(0.30, 0.66), (0.30, 0.84), (0.48, 0.66)], color)


def _cat_seguimiento(p, size, color):
    """Lupa: requiere seguimiento / observar de cerca."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.2))
    p.drawEllipse(_r(size, 0.16, 0.16, 0.62, 0.62))
    _linea(p, size, 0.58, 0.58, 0.86, 0.86, color, 2.6)


def _cat_disciplinario(p, size, color):
    """Escudo con exclamación: problema disciplinario grave."""
    path = QPainterPath()
    s = size
    path.moveTo(0.5 * s, 0.10 * s)
    path.lineTo(0.82 * s, 0.22 * s)
    path.lineTo(0.82 * s, 0.52 * s)
    path.cubicTo(0.82 * s, 0.74 * s, 0.68 * s, 0.86 * s, 0.5 * s, 0.92 * s)
    path.cubicTo(0.32 * s, 0.86 * s, 0.18 * s, 0.74 * s, 0.18 * s, 0.52 * s)
    path.lineTo(0.18 * s, 0.22 * s)
    path.closeSubpath()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawPath(path)
    _linea(p, size, 0.5, 0.34, 0.5, 0.56, color, 2.2)
    _disco(p, size, 0.465, 0.62, 0.535, 0.69, color)


def _cat_todas(p, size, color):
    """Cuadrícula 2x2: "todas las categorías", sin filtrar."""
    for x0, y0 in ((0.16, 0.16), (0.54, 0.16), (0.16, 0.54), (0.54, 0.54)):
        _rect_redondeado(p, size, x0, y0, x0 + 0.30, y0 + 0.30, color, radio=0.08)


def _cat_destacadas(p, size, color):
    """Estrella rellena: solo las categorías destacadas."""
    _estrella(p, size, 0.14, 0.14, 0.86, 0.86, color)


def _cat_generico(p, size, color):
    """Respaldo: si aparece una clave de categoría no contemplada aquí."""
    _disco(p, size, 0.34, 0.34, 0.66, 0.66, color)


# ============================================================
# NATURALEZAS (Positiva / Informativa / Negativa)
# ============================================================
def _nat_positiva(p, size, color):
    """Carita sonriente: observación de naturaleza positiva."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawEllipse(_r(size, 0.14, 0.14, 0.86, 0.86))
    _disco(p, size, 0.33, 0.38, 0.41, 0.46, color)
    _disco(p, size, 0.59, 0.38, 0.67, 0.46, color)
    path = QPainterPath()
    path.moveTo(0.30 * size, 0.60 * size)
    path.quadTo(0.5 * size, 0.78 * size, 0.70 * size, 0.60 * size)
    p.drawPath(path)


def _nat_informativa(p, size, color):
    """"i" dentro de un círculo: observación informativa."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawEllipse(_r(size, 0.14, 0.14, 0.86, 0.86))
    _disco(p, size, 0.465, 0.28, 0.535, 0.36, color)
    _linea(p, size, 0.5, 0.44, 0.5, 0.72, color, 2.4)


def _nat_negativa(p, size, color):
    """Carita seria: observación de naturaleza negativa."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma(color, 2.0))
    p.drawEllipse(_r(size, 0.14, 0.14, 0.86, 0.86))
    _disco(p, size, 0.33, 0.38, 0.41, 0.46, color)
    _disco(p, size, 0.59, 0.38, 0.67, 0.46, color)
    path = QPainterPath()
    path.moveTo(0.30 * size, 0.72 * size)
    path.quadTo(0.5 * size, 0.56 * size, 0.70 * size, 0.72 * size)
    p.drawPath(path)


_DISPATCH = {
    "rendimiento": _cat_rendimiento,
    "tareas": _cat_tareas,
    "participacion": _cat_participacion,
    "comprension": _cat_comprension,
    "esfuerzo": _cat_esfuerzo,
    "equipo": _cat_equipo,
    "buena_conducta": _cat_buena_conducta,
    "conducta": _cat_conducta,
    "conflicto": _cat_conflicto,
    "puntualidad": _cat_puntualidad,
    "asistencia": _cat_asistencia,
    "actitud": _cat_actitud,
    "bienestar": _cat_bienestar,
    "mejora": _cat_mejora,
    "reconocimiento": _cat_reconocimiento,
    "comunicacion_padres": _cat_comunicacion_padres,
    "seguimiento": _cat_seguimiento,
    "disciplinario": _cat_disciplinario,
    "todas": _cat_todas,
    "destacadas": _cat_destacadas,
    "positiva": _nat_positiva,
    "informativa": _nat_informativa,
    "negativa": _nat_negativa,
}

_cache_categoria = {}


def pixmap_categoria(clave, color, size=20):
    """QPixmap (transparente, `size`x`size`) del icono de la categoría/
    naturaleza `clave`, dibujado en un solo `color`. Cacheado por
    (clave, color, size)."""
    clave_norm = (clave or "").strip().lower()
    llave_cache = (clave_norm, color, size)
    if llave_cache in _cache_categoria:
        return _cache_categoria[llave_cache]
    pix, p = _nuevo_lienzo(size)
    dibujar = _DISPATCH.get(clave_norm, _cat_generico)
    try:
        dibujar(p, size, color)
    finally:
        p.end()
    _cache_categoria[llave_cache] = pix
    return pix


def icono_categoria(clave, color, size=20):
    """QIcon equivalente a `pixmap_categoria` (ver esa función)."""
    return QIcon(pixmap_categoria(clave, color, size))


# ============================================================
# VERSIÓN MULTICOLOR (ver docstring del módulo, sección 2)
# ============================================================
def _catc_rendimiento(p, size):
    _grafico_barras(p, size)


def _catc_tareas(p, size):
    _clip_tablero(p, size)


def _catc_participacion(p, size):
    _persona(p, size, 1, "#0EA5E9")


def _catc_comprension(p, size):
    _bombilla(p, size)


def _catc_esfuerzo(p, size):
    """Llama en degradado naranja/amarillo -mismo trazo que la versión
    monocromo (_cat_esfuerzo), pero con dos tonos en vez de un solo color."""
    path = QPainterPath()
    s = size
    path.moveTo(0.50 * s, 0.10 * s)
    path.cubicTo(0.74 * s, 0.32 * s, 0.68 * s, 0.48 * s, 0.58 * s, 0.40 * s)
    path.cubicTo(0.68 * s, 0.58 * s, 0.62 * s, 0.80 * s, 0.44 * s, 0.88 * s)
    path.cubicTo(0.56 * s, 0.78 * s, 0.50 * s, 0.68 * s, 0.44 * s, 0.68 * s)
    path.cubicTo(0.38 * s, 0.78 * s, 0.28 * s, 0.72 * s, 0.30 * s, 0.56 * s)
    path.cubicTo(0.18 * s, 0.66 * s, 0.22 * s, 0.28 * s, 0.50 * s, 0.10 * s)
    path.closeSubpath()
    p.setBrush(QBrush(QColor("#F97316")))
    p.setPen(_sin_pluma())
    p.drawPath(path)
    nucleo = QPainterPath()
    nucleo.moveTo(0.50 * s, 0.32 * s)
    nucleo.cubicTo(0.60 * s, 0.44 * s, 0.56 * s, 0.58 * s, 0.48 * s, 0.66 * s)
    nucleo.cubicTo(0.42 * s, 0.58 * s, 0.40 * s, 0.46 * s, 0.50 * s, 0.32 * s)
    nucleo.closeSubpath()
    p.setBrush(QBrush(QColor("#FDE047")))
    p.drawPath(nucleo)


def _catc_equipo(p, size):
    _manos_saludo(p, size)


def _catc_buena_conducta(p, size):
    _estrella(p, size, 0.16, 0.14, 0.84, 0.82, "#FBBF24", borde="#CA8A04")


def _catc_conducta(p, size):
    _triangulo_alerta(p, size)


def _catc_conflicto(p, size):
    """Dos flechas enfrentadas en rojo/naranja -misma composición que la
    versión monocromo, con un tono distinto por lado para que se lea como
    un choque entre dos partes, no una sola figura repetida."""
    p.setPen(_pluma("#EF4444", 3.2))
    p.drawLine(QPointF(0.12 * size, 0.5 * size), QPointF(0.40 * size, 0.5 * size))
    p.setPen(_pluma("#F97316", 3.2))
    p.drawLine(QPointF(0.60 * size, 0.5 * size), QPointF(0.88 * size, 0.5 * size))
    p.setPen(_sin_pluma())
    _poligono(p, size, [(0.12, 0.36), (0.12, 0.64), (0.40, 0.50)], "#EF4444")
    _poligono(p, size, [(0.88, 0.36), (0.88, 0.64), (0.60, 0.50)], "#F97316")


def _catc_puntualidad(p, size):
    _reloj(p, size)


def _catc_asistencia(p, size):
    """Calendario: registro de asistencia en general. Antes era un disco
    verde con check blanco -que se leía como 'presente'- y quedaba mal
    para entradas de esta misma categoría que son justo lo contrario,
    como la plantilla 'Ausencias reiteradas' o 'Llegadas tardías'."""
    _calendario(p, size, color_top="#22C55E")


def _catc_actitud(p, size):
    _diana(p, size)


def _catc_bienestar(p, size):
    _corazon(p, size, "#EC4899")


def _catc_mejora(p, size):
    _grafico_lineas(p, size, "#22C55E")


def _catc_reconocimiento(p, size):
    _trofeo(p, size)


def _catc_comunicacion_padres(p, size):
    _sobre(p, size)


def _catc_seguimiento(p, size):
    _lupa(p, size, color="#3B82F6")


def _catc_disciplinario(p, size):
    _escudo(p, size, color="#DC2626")


def _catc_todas(p, size):
    """Cuadrícula 2x2 arcoíris -una casilla por tono- para "todas las
    categorías": deliberadamente multicolor, ya que representa el conjunto
    completo y no una categoría concreta."""
    colores = ("#3B82F6", "#22C55E", "#F59E0B", "#8B5CF6")
    for (x0, y0), color in zip(((0.16, 0.16), (0.54, 0.16), (0.16, 0.54), (0.54, 0.54)), colores):
        _rect_redondeado(p, size, x0, y0, x0 + 0.30, y0 + 0.30, color, radio=0.08)


def _catc_destacadas(p, size):
    _estrella(p, size, 0.14, 0.12, 0.86, 0.84, "#F59E0B", borde="#B45309")


def _catc_generico(p, size):
    _disco(p, size, 0.30, 0.30, 0.70, 0.70, "#94A3B8", borde="#64748B")


def _catc_positiva(p, size):
    _sonrisa(p, size, "#22C55E")


def _catc_informativa(p, size):
    """"i" blanca sobre un disco azul -la variante multicolor del aro con
    la "i" trazada, para que se distinga a simple vista del resto."""
    _disco(p, size, 0.12, 0.12, 0.88, 0.88, "#3B82F6", borde="#1D4ED8")
    _disco(p, size, 0.44, 0.22, 0.56, 0.34, "white")
    p.setPen(_pluma("white", 3.0))
    p.drawLine(QPointF(0.5 * size, 0.44 * size), QPointF(0.5 * size, 0.72 * size))


def _catc_negativa(p, size):
    """Carita seria en rojo -mismo gesto que la versión monocromo, sobre un
    disco de color en vez de solo el trazo del aro."""
    _disco(p, size, 0.12, 0.12, 0.88, 0.88, "#EF4444", borde="#B91C1C")
    _disco(p, size, 0.33, 0.38, 0.41, 0.46, "white")
    _disco(p, size, 0.59, 0.38, 0.67, 0.46, "white")
    p.setPen(_pluma("white", 2.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(0.30 * size, 0.68 * size)
    path.quadTo(0.5 * size, 0.54 * size, 0.70 * size, 0.68 * size)
    p.drawPath(path)


_DISPATCH_COLOR = {
    "rendimiento": _catc_rendimiento,
    "tareas": _catc_tareas,
    "participacion": _catc_participacion,
    "comprension": _catc_comprension,
    "esfuerzo": _catc_esfuerzo,
    "equipo": _catc_equipo,
    "buena_conducta": _catc_buena_conducta,
    "conducta": _catc_conducta,
    "conflicto": _catc_conflicto,
    "puntualidad": _catc_puntualidad,
    "asistencia": _catc_asistencia,
    "actitud": _catc_actitud,
    "bienestar": _catc_bienestar,
    "mejora": _catc_mejora,
    "reconocimiento": _catc_reconocimiento,
    "comunicacion_padres": _catc_comunicacion_padres,
    "seguimiento": _catc_seguimiento,
    "disciplinario": _catc_disciplinario,
    "todas": _catc_todas,
    "destacadas": _catc_destacadas,
    "positiva": _catc_positiva,
    "informativa": _catc_informativa,
    "negativa": _catc_negativa,
}

_cache_categoria_color = {}


def pixmap_categoria_color(clave, size=20):
    """QPixmap (transparente, `size`x`size`) MULTICOLOR del icono de la
    categoría/naturaleza `clave` (ver sección 2 del docstring del módulo).
    Cacheado por (clave, size) -a diferencia de `pixmap_categoria`, aquí no
    hace falta cachear por color porque el dibujo ya trae sus colores fijos."""
    clave_norm = (clave or "").strip().lower()
    llave_cache = (clave_norm, size)
    if llave_cache in _cache_categoria_color:
        return _cache_categoria_color[llave_cache]
    pix, p = _nuevo_lienzo(size)
    dibujar = _DISPATCH_COLOR.get(clave_norm, _catc_generico)
    try:
        dibujar(p, size)
    finally:
        p.end()
    _cache_categoria_color[llave_cache] = pix
    return pix


def icono_categoria_color(clave, size=20):
    """QIcon equivalente a `pixmap_categoria_color` (ver esa función)."""
    return QIcon(pixmap_categoria_color(clave, size))


# ============================================================
# 3. MATERIALES (ver sección 3 del docstring del módulo)
# ============================================================
# Dibujos reutilizados TAL CUAL desde iconos_emoji.py (misma composición que
# usan sus emojis equivalentes -📚🧪🔧🖥📷🎨📦-, así se ven consistentes con
# el resto de la app en vez de inventar un estilo aparte):
#   libros -> _libro · laboratorio -> _tubo_ensayo · taller -> _llave_inglesa
#   tecnologia -> _pantalla · audiovisual -> _camara · arte -> _paleta
#   otro -> _paquete
# Los que no tenían un emoji "de verdad" ya dibujado en iconos_emoji.py se
# crean aquí mismo, con las mismas primitivas (_disco, _linea, _poligono...).
def _matc_deportivo(p, size):
    """Balón: disco naranja con costuras curvas -material deportivo."""
    _disco(p, size, 0.12, 0.12, 0.88, 0.88, "#F97316", borde="#9A3412")
    p.setPen(_pluma("#9A3412", 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(0.5 * size, 0.14 * size), QPointF(0.5 * size, 0.86 * size))
    arco = _r(size, 0.12, 0.12, 0.88, 0.88)
    p.drawArc(arco, 55 * 16, 70 * 16)
    p.drawArc(arco, 235 * 16, 70 * 16)


def _matc_musica(p, size):
    """Corchea (nota musical): cabeza + plica + bandera -instrumentos/música."""
    color = "#EC4899"
    _disco(p, size, 0.24, 0.62, 0.44, 0.80, color)
    p.setPen(_pluma(color, 3.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(0.43 * size, 0.71 * size), QPointF(0.43 * size, 0.18 * size))
    bandera = QPainterPath()
    s = size
    bandera.moveTo(0.43 * s, 0.18 * s)
    bandera.cubicTo(0.62 * s, 0.24 * s, 0.66 * s, 0.38 * s, 0.54 * s, 0.48 * s)
    p.drawPath(bandera)


def _matc_uniforme(p, size):
    """Silueta simple de camiseta -uniformes y vestuario."""
    s = size
    color, borde = "#06B6D4", "#0E7490"
    path = QPainterPath()
    path.moveTo(0.36 * s, 0.14 * s)
    path.lineTo(0.14 * s, 0.26 * s)
    path.lineTo(0.22 * s, 0.42 * s)
    path.lineTo(0.30 * s, 0.36 * s)
    path.lineTo(0.30 * s, 0.86 * s)
    path.lineTo(0.70 * s, 0.86 * s)
    path.lineTo(0.70 * s, 0.36 * s)
    path.lineTo(0.78 * s, 0.42 * s)
    path.lineTo(0.86 * s, 0.26 * s)
    path.lineTo(0.64 * s, 0.14 * s)
    path.cubicTo(0.60 * s, 0.24 * s, 0.40 * s, 0.24 * s, 0.36 * s, 0.14 * s)
    path.closeSubpath()
    p.setBrush(QBrush(QColor(color)))
    p.setPen(_pluma(borde, 1.4))
    p.drawPath(path)


def _matc_mobiliario(p, size):
    """Silla simple -mobiliario y equipamiento."""
    color = "#78716C"
    _rect_redondeado(p, size, 0.30, 0.12, 0.70, 0.48, color, radio=0.06)
    _rect_redondeado(p, size, 0.22, 0.48, 0.78, 0.62, color, radio=0.05)
    p.setPen(_pluma(color, 3.0))
    p.drawLine(QPointF(0.26 * size, 0.62 * size), QPointF(0.20 * size, 0.90 * size))
    p.drawLine(QPointF(0.74 * size, 0.62 * size), QPointF(0.80 * size, 0.90 * size))


def _matc_papeleria(p, size):
    """Libreta con espiral + lápiz diagonal -papelería y útiles de oficina."""
    _rect_redondeado(p, size, 0.16, 0.14, 0.72, 0.88, "#FFFFFF", radio=0.05, borde="#94A3B8")
    for y in (0.28, 0.40, 0.52, 0.64, 0.76):
        _linea(p, size, 0.24, y, 0.64, y, "#CBD5E1", 1.4)
    for x in (0.22, 0.30, 0.38):
        _disco(p, size, x - 0.02, 0.10, x + 0.02, 0.18, "#94A3B8")
    p.setPen(_pluma("#FDE047", 5.0))
    p.drawLine(QPointF(0.62 * size, 0.90 * size), QPointF(0.86 * size, 0.66 * size))
    p.setPen(_pluma("#78350F", 2.2))
    p.drawLine(QPointF(0.855 * size, 0.655 * size), QPointF(0.90 * size, 0.62 * size))


def _matc_salud(p, size):
    """Maletín blanco con cruz roja -salud / primeros auxilios."""
    _rect_redondeado(p, size, 0.42, 0.14, 0.58, 0.24, "#94A3B8", radio=0.02)
    _rect_redondeado(p, size, 0.12, 0.24, 0.88, 0.84, "#FFFFFF", radio=0.08, borde="#CBD5E1")
    _linea(p, size, 0.12, 0.44, 0.88, 0.44, "#CBD5E1", 1.2)
    _rect_redondeado(p, size, 0.44, 0.34, 0.56, 0.70, "#EF4444", radio=0.02)
    _rect_redondeado(p, size, 0.32, 0.46, 0.68, 0.58, "#EF4444", radio=0.02)


def _matc_libros(p, size):
    _libro(p, size, "#8B5CF6", "#5B21B6")


def _matc_laboratorio(p, size):
    _tubo_ensayo(p, size)


def _matc_taller(p, size):
    _llave_inglesa(p, size, "#F59E0B")


def _matc_tecnologia(p, size):
    _pantalla(p, size)


def _matc_audiovisual(p, size):
    _camara(p, size)


def _matc_arte(p, size):
    _paleta(p, size)


def _matc_otro(p, size):
    _paquete(p, size)


# Claves normalizadas (sin tildes/espacios/mayúsculas, ver _normalizar_clave_material)
# -> función de dibujo. Varios alias apuntan al mismo dibujo para que el
# selector y una clave escrita a mano (o heredada de una versión anterior)
# coincidan igual.
_DISPATCH_MATERIAL = {
    "libros": _matc_libros,
    "biblioteca": _matc_libros,
    "laboratorio": _matc_laboratorio,
    "taller": _matc_taller,
    "herramientas": _matc_taller,
    "tecnologia": _matc_tecnologia,
    "informatica": _matc_tecnologia,
    "audiovisual": _matc_audiovisual,
    "arte": _matc_arte,
    "deportivo": _matc_deportivo,
    "deporte": _matc_deportivo,
    "musica": _matc_musica,
    "uniforme": _matc_uniforme,
    "uniformes": _matc_uniforme,
    "mobiliario": _matc_mobiliario,
    "papeleria": _matc_papeleria,
    "oficina": _matc_papeleria,
    "salud": _matc_salud,
    "primerosauxilios": _matc_salud,
    "botiquin": _matc_salud,
    "otro": _matc_otro,
    "general": _matc_otro,
}

# Set curado que ofrece el selector de íconos de "Gestionar categorías" en
# materiales.py: (clave a guardar en categorias_material.icono, etiqueta).
# El orden aquí es el orden en que se muestran en la grilla del selector.
CATEGORIAS_SUGERIDAS_MATERIAL = [
    ("libros", "Libros / Biblioteca"),
    ("laboratorio", "Laboratorio"),
    ("taller", "Taller / Herramientas"),
    ("tecnologia", "Tecnología"),
    ("audiovisual", "Audiovisual"),
    ("arte", "Artes plásticas"),
    ("deportivo", "Deportivo"),
    ("musica", "Música"),
    ("uniforme", "Uniformes"),
    ("mobiliario", "Mobiliario"),
    ("papeleria", "Papelería / Oficina"),
    ("salud", "Salud / Botiquín"),
    ("otro", "Otro / General"),
]

_cache_categoria_material = {}


def _normalizar_clave_material(texto):
    """Quita tildes/mayúsculas/espacios para que 'Laboratorio', 'laboratorio'
    y 'Laboratório' (o una clave vieja con espacios) resuelvan al mismo
    dibujo. Un emoji Unicode se queda vacío tras esto (no tiene forma
    ascii) y por lo tanto nunca choca por accidente con una clave curada."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", sin_tildes.lower())


def pixmap_categoria_material(valor, size=20):
    """QPixmap (transparente, `size`x`size`) MULTICOLOR para el ícono de una
    categoría de Materiales. `valor` es lo que trae guardado
    `categorias_material.icono`, y puede ser:

      1. Una clave curada de CATEGORIAS_SUGERIDAS_MATERIAL (lo normal si se
         eligió con el selector de íconos) -> se dibuja su ícono dedicado.
      2. Un emoji suelto que YA tiene dibujo propio en iconos_emoji.py
         (categorías creadas a mano antes de que existiera el selector,
         ej. alguien escribió "📚") -> se reutiliza ese dibujo tal cual, sin
         pedirle que vuelva a elegir nada.
      3. Cualquier otra cosa (vacío, texto libre sin coincidencia, un emoji
         no reconocido) -> la caja genérica ("otro"), NUNCA una letra suelta
         ni el glifo de fuente crudo del sistema operativo.

    Cacheado por (valor, size), igual que el resto de este archivo."""
    valor = valor or ""
    llave_cache = (valor, size)
    if llave_cache in _cache_categoria_material:
        return _cache_categoria_material[llave_cache]
    clave = _normalizar_clave_material(valor)
    dibujar = _DISPATCH_MATERIAL.get(clave)
    if dibujar is None and emoji_soportado(valor):
        pix = pixmap_emoji(valor, size)  # ya cacheado dentro de iconos_emoji.py
        _cache_categoria_material[llave_cache] = pix
        return pix
    pix, p = _nuevo_lienzo(size)
    try:
        (dibujar or _matc_otro)(p, size)
    finally:
        p.end()
    _cache_categoria_material[llave_cache] = pix
    return pix


def icono_categoria_material(valor, size=20):
    """QIcon equivalente a `pixmap_categoria_material` (ver esa función)."""
    return QIcon(pixmap_categoria_material(valor, size))
