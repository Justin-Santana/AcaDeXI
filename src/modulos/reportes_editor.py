# ============================================================
# reportes_editor.py - Visor y editor avanzado de reportes generados
# ------------------------------------------------------------
# Widget reutilizable (pensado para vivir dentro de una pestaña de
# reportes.py) que permite ABRIR, PREVISUALIZAR y EDITAR los archivos que
# el módulo de Reportes exporta: CSV, Excel (.xlsx), Word (.docx) y PDF.
# También permite imprimir directamente el archivo que se esté viendo.
#
# No depende de reportes.py: solo necesita `main_window` (para el registro
# de auditoría y los mensajes con el estilo de la app) y expone
# `agregar_reciente(ruta)` para que otros módulos puedan avisarle "acabo
# de generar este archivo" y aparezca en el desplegable de recientes.
#
# Dependencias opcionales (se avisa con un mensaje amigable si faltan,
# igual que ya hace reportes.py con openpyxl/reportlab):
#   - openpyxl        -> edición/previsualización de Excel
#   - PyMuPDF (fitz)  -> previsualización/edición de PDF (y su impresión)
#   - python-docx     -> edición/previsualización de Word
# ============================================================
import csv
import os
import sys
import re
import math
import shutil
import string
import base64
import io
from collections import deque
from datetime import datetime, date
from src.nucleo.formato_hora import formatear_hora
from src.interfaz.configuracion import conectar_tooltip_seleccion
from src.nucleo.atajos import registrar_atajo, atajos_de

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFileDialog, QTableWidget, QTableWidgetItem, QLineEdit,
    QSpinBox, QSlider, QColorDialog, QFrame, QMessageBox, QScrollArea, QPlainTextEdit,
    QStackedWidget, QToolButton, QCheckBox, QDialog, QFormLayout,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QAbstractItemView, QSizePolicy, QTextEdit, QMenu,
    QStyledItemDelegate, QInputDialog, QApplication, QToolTip, QTableWidgetSelectionRange,
    QGraphicsView, QGraphicsScene, QButtonGroup)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSizeF, QRectF, QRect, QTimer, QUrl, QEvent, QPoint, QBuffer, Signal
from PySide6.QtGui import (QPixmap, QImage, QColor, QBrush, QTextCharFormat, QFont, QTextCursor,
    QTextDocument, QTextBlockFormat, QTextListFormat, QPainter, QTextImageFormat, QImageReader,
    QCursor, QAction, QKeySequence, QDesktopServices, QIcon)

from src.nucleo.iconos import (mostrar_mensaje, centrar_y_al_frente, aplicar_icono_ventana,
    ICONO_DOCUMENTO, ICONO_COLOR, ICONO_CARGA)
from src.nucleo.limite_campos import limitar_campo_texto
from src.interfaz.paginacion import aplicar_estructura_tabla
from PySide6.QtCore import QSize as _QSize_emoji
from src.nucleo.iconos_emoji import (icono_emoji, pixmap_emoji, quitar_emojis_texto,
    EMOJI_ALINEAR_IZQUIERDA, EMOJI_ALINEAR_CENTRO, EMOJI_ALINEAR_DERECHA,
    EMOJI_INSERTAR_FILA, EMOJI_ELIMINAR_FILA,
    EMOJI_INSERTAR_COLUMNA, EMOJI_ELIMINAR_COLUMNA,
    EMOJI_CUADRO_TEXTO)

try:
    from src.nucleo.bd import registrar_auditoria
except Exception:  # pragma: no cover - por si se usa este visor fuera de AcaDeXI
    def registrar_auditoria(*args, **kwargs):
        pass

try:
    from src.nucleo.hilo_trabajo import WorkerHilo
except Exception:  # pragma: no cover
    WorkerHilo = None


EXTENSIONES_SOPORTADAS = ("csv", "xlsx", "docx", "pdf")
FILTRO_ABRIR = ("Reportes (*.csv *.xlsx *.docx *.pdf);;CSV (*.csv);;Excel (*.xlsx);;"
                 "Word (*.docx);;PDF (*.pdf)")

# A partir de este tamaño, medir cada celda para autoajustar una columna puede
# tardar más que la propia carga. La muestra conserva el mismo criterio de
# ancho y evita un recorrido adicional gigantesco en reportes masivos.
_UMBRAL_CELDAS_AUTOAJUSTE_MUESTREO = 50_000
_FILAS_MUESTREO_AUTOAJUSTE = 400

# Tipografías ofrecidas en los selectores de fuente de los modos Word y
# Excel -un surtido reducido pero representativo de las más usadas en
# documentos y hojas de cálculo (clásicas de máquina de escribir/serif,
# palo seco de oficina, y alguna más informal/decorativa). Si el sistema no
# tiene instalada alguna de estas, Qt hace su propio reemplazo automático
# por la fuente más parecida disponible -no rompe nada, solo se ve distinto-.
FUENTES_DISPONIBLES = [
    "Calibri", "Arial", "Arial Black", "Times New Roman", "Georgia",
    "Garamond", "Century Gothic", "Verdana", "Trebuchet MS", "Open Sans",
    "Comic Sans MS", "School Teacher",
]


def _extension(ruta):
    return os.path.splitext(ruta)[1].lower().lstrip(".")


def _qss_scrollbar_editor(c, prefijo=""):
    """Estilo de scrollbar único para TODO el editor (hoja de cálculo, Word y
    PDF): grueso y fácil de agarrar -no la delgadita por defecto del sistema,
    fácil de pasar por alto- y sigue el tema claro/oscuro de la app. Se usa
    en los tres modos para que se vean exactamente igual sin importar cuál
    se esté editando. `prefijo` acota el estilo a un widget concreto (por
    ejemplo "QTableWidget ") para no afectar sin querer otras barras."""
    return f"""
        {prefijo}QScrollBar:horizontal {{
            height: 16px;
            background: {c['bg_panel']};
            margin: 0px;
            border-top: 1px solid {c['bg_btn']};
        }}
        {prefijo}QScrollBar::handle:horizontal {{
            background: {c['bg_btn']};
            min-width: 30px;
            border-radius: 7px;
            margin: 2px;
        }}
        {prefijo}QScrollBar::handle:horizontal:hover {{
            background: {c['accent']};
        }}
        {prefijo}QScrollBar::add-line:horizontal, {prefijo}QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        {prefijo}QScrollBar:vertical {{
            width: 16px;
            background: {c['bg_panel']};
            margin: 0px;
            border-left: 1px solid {c['bg_btn']};
        }}
        {prefijo}QScrollBar::handle:vertical {{
            background: {c['bg_btn']};
            min-height: 30px;
            border-radius: 7px;
            margin: 2px;
        }}
        {prefijo}QScrollBar::handle:vertical:hover {{
            background: {c['accent']};
        }}
        {prefijo}QScrollBar::add-line:vertical, {prefijo}QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """


def _letra_columna(indice):
    """0 -> 'A', 1 -> 'B', ... 26 -> 'AA' (estilo Excel), para nombrar columnas nuevas."""
    letras = string.ascii_uppercase
    indice += 1
    resultado = ""
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        resultado = letras[resto] + resultado
    return resultado


def _color_texto_contrastado(color_fondo):
    """Dado un color de fondo (QColor), devuelve negro o blanco -el que mejor
    contraste ofrezca- para el texto. Así una celda con relleno claro (por
    ejemplo blanco, típico de un Excel exportado) sigue siendo legible aunque
    la app esté en modo oscuro -donde el texto por defecto es claro y, sobre
    un fondo también claro, se volvería invisible- y viceversa en modo claro."""
    luminancia = (0.299 * color_fondo.red() + 0.587 * color_fondo.green() + 0.114 * color_fondo.blue())
    return QColor("#0F172A") if luminancia > 140 else QColor("#F8FAFC")


def _elegir_color_con_icono(color_inicial, parent, titulo=""):
    """Equivalente a QColorDialog.getColor(...), pero con una instancia
    propia (en vez del atajo estático) para poder ponerle el icono de
    ventana correcto: toda ventana de selección de color en AcaDeXI usa
    ICONO_COLOR ("colorico.ico"), no el icono genérico de la app -el atajo
    estático crea su diálogo por dentro y no deja tocarlo antes de mostrarlo."""
    dialogo = QColorDialog(QColor(color_inicial), parent)
    if titulo:
        dialogo.setWindowTitle(titulo)
    aplicar_icono_ventana(dialogo, ICONO_COLOR)
    if dialogo.exec() == QDialog.DialogCode.Accepted:
        return dialogo.selectedColor()
    return QColor()  # inválido: mismo contrato que QColorDialog.getColor() cancelado


# ============================================================
# MOTOR DE FÓRMULAS DE LA HOJA DE CÁLCULO
# ------------------------------------------------------------
# Réplica reducida -pero funcional- de lo esencial de un motor de
# fórmulas tipo Excel: referencias de celda (A1, $A$1), rangos (A1:B10),
# operadores aritméticos/comparación/concatenación y un conjunto de
# funciones habituales (en español e inglés). Cada celda "cruda" (lo que
# realmente escribió la persona, o lo que traía el .xlsx) se guarda aparte
# del texto ya calculado/formateado que se ve en la grilla -tal como hace
# Excel al mostrar el resultado pero dejar ver la fórmula al editar.
# ============================================================

# Roles de datos propios que se guardan en cada QTableWidgetItem, además
# del texto visible (DisplayRole) que ya usa Qt:
ROL_CRUDO = int(Qt.ItemDataRole.UserRole) + 1        # contenido tal cual se escribió/leyó
ROL_FORMATO_NUM = int(Qt.ItemDataRole.UserRole) + 2  # "moneda" | "porcentaje" | "fecha" | None
ROL_VALOR_CACHE = int(Qt.ItemDataRole.UserRole) + 3  # último resultado que Excel calculó (respaldo)
ROL_TAMANO_BASE = int(Qt.ItemDataRole.UserRole) + 4  # tamaño de letra "real" (100%) de la celda, para el zoom
ROL_ES_CUADRO_TEXTO = int(Qt.ItemDataRole.UserRole) + 5  # True si la celda es la alternativa a un cuadro de texto flotante
ROL_HIPERVINCULO = int(Qt.ItemDataRole.UserRole) + 6  # URL del hipervínculo de la celda, o None
ROL_FILA_ORIGEN = int(Qt.ItemDataRole.UserRole) + 7  # fila donde estaba una celda ANTES de ordenar (para traducir referencias)

# Paletas de acento disponibles para el tema PROPIO del editor de reportes.
_TEMAS_ACENTO_EDITOR = [
    ("Azul", "#2563EB"), ("Violeta", "#7C3AED"), ("Verde", "#059669"),
    ("Naranja", "#D97706"), ("Rosa", "#DB2777"), ("Turquesa", "#0891B2"),
    ("Índigo", "#4F46E5"), ("Esmeralda", "#10B981"), ("Rojo", "#DC2626"),
    ("Ámbar", "#F59E0B"), ("Fucsia", "#C026D3"), ("Cian", "#06B6D4"),
    ("Lima", "#65A30D"), ("Coral", "#F97316"), ("Grafito", "#475569"),
    ("Vino", "#9F1239"),
]

# ============================================================
# SEGURIDAD DE HIPERVÍNCULOS
# ============================================================
# QDesktopServices.openUrl() delega en el manejador del sistema operativo
# para lo que sea que diga el esquema de la URL -no es un navegador, así
# que no hay sandbox propio. Un esquema sin filtrar puede:
#   - abrir/ejecutar un archivo local o un .exe/.bat/.lnk vía "file://",
#   - forzar una autenticación SMB (fuga de hash NTLM) vía una ruta UNC
#     "file://\\servidor-atacante\recurso",
#   - invocar un esquema personalizado registrado por otra app instalada
#     (ha habido cadenas de RCE reales abusando de esquemas como
#     "ms-msdt:" o "search-ms:" en documentos maliciosos).
# Los enlaces que llegan a este editor NO siempre los escribe la persona
# que los abre: también se cargan automáticamente desde un PDF o un XLSX
# importado (ver get_links()/celda.hyperlink más abajo), así que no basta
# con confiar en quien los tipeó -hay que filtrar el esquema en TODOS los
# puntos de entrada y, otra vez, justo antes de abrir cualquier enlace.
ESQUEMAS_ENLACE_PERMITIDOS = {"http", "https", "mailto"}


def _esquema_enlace(url_texto):
    try:
        return (QUrl(url_texto or "").scheme() or "").lower()
    except Exception:
        return ""


def enlace_es_seguro(url_texto):
    """True solo si el esquema está en la lista blanca. Cualquier otra cosa
    (file, ftp, esquemas personalizados de otras apps, o directamente sin
    esquema reconocible) se considera no seguro para abrir automáticamente."""
    return bool(url_texto) and _esquema_enlace(url_texto) in ESQUEMAS_ENLACE_PERMITIDOS


def abrir_enlace_externo(url_texto, padre=None):
    """Único punto por el que este editor abre un hipervínculo con el
    sistema operativo. Si el esquema no es seguro, NO se abre -se avisa y
    se muestra la URL cruda para que la persona pueda decidir copiarla y
    revisarla por su cuenta, en vez de que la app la abra a ciegas."""
    if enlace_es_seguro(url_texto):
        QDesktopServices.openUrl(QUrl(url_texto))
        return True
    mostrar_mensaje(
        "advertencia", "Enlace bloqueado",
        "Este hipervínculo no se abrió porque su tipo de dirección no es seguro para abrir "
        f"automáticamente (solo se permiten http, https y mailto):\n\n{url_texto}\n\n"
        "Si confías en el origen de este documento, copia la dirección manualmente para revisarla.",
        padre)
    return False


class _ErrorFormulaValor(Exception):
    """Representa un error de fórmula al estilo Excel (#¡DIV/0!, #¡REF!, ...).
    Se usa tanto como excepción (para cortar la evaluación) como valor
    (el resultado final que queda mostrado en la celda)."""

    def __init__(self, codigo):
        super().__init__(codigo)
        self.codigo = codigo

    def __str__(self):
        return self.codigo

    def __repr__(self):
        return self.codigo


def _col_index_desde_letras(letras):
    """'A' -> 0, 'B' -> 1, ..., 'Z' -> 25, 'AA' -> 26 ... (inverso de _letra_columna)."""
    indice = 0
    for ch in letras.upper():
        indice = indice * 26 + (ord(ch) - ord("A") + 1)
    return indice - 1


def _celda_a_indices(ref):
    """'B3' (o '$B$3') -> (fila 0-indexada, columna 0-indexada). (None, None) si no es válida."""
    m = re.match(r"^\$?([A-Za-z]{1,3})\$?(\d+)$", ref)
    if not m:
        return None, None
    letras, numero = m.group(1), int(m.group(2))
    return numero - 1, _col_index_desde_letras(letras)


def _traducir_filas_formula(formula, delta):
    """Desplaza las referencias RELATIVAS de fila de una fórmula en `delta`
    filas (traducción estilo Excel al reordenar). Los componentes con "$"
    antes del número (B$2, $B$2) quedan fijos, y los literales entre comillas
    y los nombres de función (seguidos de paréntesis, p. ej. LOG10) no se
    tocan. `formula` incluye el "=" inicial."""
    partes = formula.split('"')  # alterna fuera/dentro de literales de texto
    for i in range(0, len(partes), 2):  # solo los trozos FUERA de comillas
        partes[i] = re.sub(
            r"(\$?)([A-Za-z]{1,3})(\$?)(\d+)(?![\w($])",
            lambda m: (m.group(1) + m.group(2) + m.group(3) +
                       (m.group(4) if m.group(3) == "$"
                        else str(max(1, int(m.group(4)) + delta)))),
            partes[i],
        )
    return '"'.join(partes)


def _analizar_crudo(crudo):
    """A partir del contenido "crudo" de una celda (tal como se escribió a
    mano o se leyó del propio Excel) determina su valor ya TIPADO -número,
    booleano, fecha o texto- y, si corresponde, qué formato de número de
    Excel conviene aplicarle (moneda/porcentaje) para que se muestre y se
    guarde correctamente. Las fórmulas (texto que empieza con "=") no se
    tocan aquí: las resuelve el motor de fórmulas."""
    if crudo is None:
        return None, None
    if isinstance(crudo, bool):
        return crudo, None
    if isinstance(crudo, (int, float)):
        return crudo, None
    if isinstance(crudo, (datetime, date)):
        return crudo, "fecha"
    if not isinstance(crudo, str):
        return crudo, None

    texto = crudo.strip()
    if texto == "" or texto.startswith("="):
        return (None if texto == "" else texto), None

    superior = texto.upper()
    if superior in ("VERDADERO", "TRUE"):
        return True, None
    if superior in ("FALSO", "FALSE"):
        return False, None

    # Porcentaje: "25%" -> 0.25, con formato "porcentaje"
    if texto.endswith("%"):
        cuerpo = texto[:-1].strip().replace(",", "")
        try:
            return float(cuerpo) / 100.0, "porcentaje"
        except ValueError:
            pass

    # Moneda: "$1,234.56" / "€1234,56" -> número, con formato "moneda"
    if texto and texto[0] in "$€£¥":
        cuerpo = texto[1:].strip().replace(",", "")
        try:
            return float(cuerpo), "moneda"
        except ValueError:
            pass

    # Número normal (admite separador de miles con coma)
    cuerpo = texto.replace(",", "")
    try:
        if re.fullmatch(r"-?\d+", cuerpo):
            return int(cuerpo), None
        return float(cuerpo), None
    except ValueError:
        pass

    # Fecha (formatos habituales)
    for patron in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, patron).date(), "fecha"
        except ValueError:
            continue

    return texto, None


def _convertir_valor(texto):
    """Intenta convertir el texto de una celda a su valor tipado (número,
    booleano o fecha) para que las columnas numéricas de Excel se
    mantengan usables tras editar en la grilla; si no, se guarda como
    texto tal cual. (Se conserva esta función -usada en otros puntos del
    módulo- como envoltorio fino sobre _analizar_crudo.)"""
    valor, _formato = _analizar_crudo(texto)
    return valor


def _clasificar_formato_excel(formato_excel):
    """A partir del `number_format` de openpyxl (p.ej. '"$"#,##0.00',
    '0.00%', 'dd/mm/yyyy') deduce una categoría simple: moneda, porcentaje,
    fecha o None (formato general)."""
    if not formato_excel or formato_excel == "General":
        return None
    fmt = formato_excel.lower()
    if "%" in fmt:
        return "porcentaje"
    if any(s in formato_excel for s in ("$", "€", "£", "¥")) or "[$" in fmt:
        return "moneda"
    if any(s in fmt for s in ("yy", "dd", "mmm")) and "h" not in fmt.replace("mmm", ""):
        return "fecha"
    return None


def _formatear_numero_general(valor):
    """Formatea un número (sin moneda/porcentaje) con separador de miles,
    igual que Excel en formato general: enteros sin decimales, decimales
    recortando ceros sobrantes."""
    if isinstance(valor, float) and valor.is_integer():
        return f"{int(valor):,}"
    if isinstance(valor, float):
        texto = f"{valor:,.4f}".rstrip("0").rstrip(".")
        return texto
    return f"{valor:,}"


def _formatear_para_mostrar(valor, formato_num=None):
    """Convierte un valor ya calculado/tipado en el texto que se ve en la
    celda, aplicando el formato de número (moneda/porcentaje/fecha) que
    corresponda -tal como Excel muestra "$1,234.56" aunque el valor
    guardado sea 1234.56."""
    if isinstance(valor, _ErrorFormulaValor):
        return valor.codigo
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "VERDADERO" if valor else "FALSO"
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, (int, float)):
        if formato_num == "moneda":
            return f"${valor:,.2f}"
        if formato_num == "porcentaje":
            texto = f"{valor * 100:.2f}".rstrip("0").rstrip(".")
            return f"{texto}%"
        return _formatear_numero_general(valor)
    return str(valor)


def _texto_crudo_como_str(crudo):
    """Representación en texto editable de un valor crudo (lo que se ve al
    hacer doble clic para editar la celda)."""
    if crudo is None:
        return ""
    if isinstance(crudo, bool):
        return "VERDADERO" if crudo else "FALSO"
    if isinstance(crudo, (datetime, date)):
        return crudo.strftime("%d/%m/%Y")
    if isinstance(crudo, float) and crudo.is_integer():
        return str(int(crudo))
    return str(crudo)


def _num(valor):
    """Coacciona un valor de fórmula a número; propaga errores; lanza
    #¡VALOR! si no es convertible."""
    if isinstance(valor, _ErrorFormulaValor):
        raise valor
    if valor is None:
        return 0
    if isinstance(valor, bool):
        return 1 if valor else 0
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, (datetime, date)):
        return valor.toordinal()
    if isinstance(valor, str):
        tipado, _f = _analizar_crudo(valor)
        if isinstance(tipado, (int, float)) and not isinstance(tipado, bool):
            return tipado
        raise _ErrorFormulaValor("#¡VALOR!")
    raise _ErrorFormulaValor("#¡VALOR!")


def _texto_formula(valor):
    """Coacciona un valor de fórmula a texto (para & y funciones de texto)."""
    if isinstance(valor, _ErrorFormulaValor):
        raise valor
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "VERDADERO" if valor else "FALSO"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def _aplicar_comparacion(op, izq, der):
    if isinstance(izq, _ErrorFormulaValor):
        raise izq
    if isinstance(der, _ErrorFormulaValor):
        raise der
    if isinstance(izq, str) or isinstance(der, str):
        a, b = _texto_formula(izq).upper(), _texto_formula(der).upper()
    else:
        a, b = (izq if izq is not None else 0), (der if der is not None else 0)
    try:
        if op == "=":
            return a == b
        if op == "<>":
            return a != b
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        if op == ">=":
            return a >= b
    except TypeError:
        return False
    return False


def _aplanar(argumentos):
    resultado = []
    for a in argumentos:
        if isinstance(a, list):
            resultado.extend(a)
        else:
            resultado.append(a)
    return resultado


def _numeros(argumentos):
    numeros = []
    for v in _aplanar(argumentos):
        if isinstance(v, _ErrorFormulaValor):
            raise v
        if v is None or isinstance(v, bool) or isinstance(v, str):
            continue
        if isinstance(v, (int, float)):
            numeros.append(v)
    return numeros


def _cumple_criterio(valor, criterio):
    if isinstance(criterio, str) and criterio[:2] in (">=", "<="):
        op, resto = criterio[:2], criterio[2:]
    elif isinstance(criterio, str) and criterio[:1] in (">", "<"):
        op, resto = criterio[:1], criterio[1:]
    else:
        op, resto = "=", criterio
    try:
        objetivo = float(resto)
        actual = _num(valor)
    except (ValueError, TypeError, _ErrorFormulaValor):
        objetivo = _texto_formula(resto).upper()
        actual = _texto_formula(valor).upper()
    if op == ">":
        return actual > objetivo
    if op == "<":
        return actual < objetivo
    if op == ">=":
        return actual >= objetivo
    if op == "<=":
        return actual <= objetivo
    return actual == objetivo


def _f_sum(a): return sum(_numeros(a))


def _f_product(a):
    numeros = _numeros(a)
    total = 1
    for n in numeros:
        total *= n
    return total


def _f_average(a):
    n = _numeros(a)
    if not n:
        raise _ErrorFormulaValor("#¡DIV/0!")
    return sum(n) / len(n)


def _f_min(a):
    n = _numeros(a)
    return min(n) if n else 0


def _f_max(a):
    n = _numeros(a)
    return max(n) if n else 0


def _f_count(a): return len(_numeros(a))


def _f_counta(a): return len([v for v in _aplanar(a) if v is not None and v != ""])


def _f_if(a):
    if not a:
        raise _ErrorFormulaValor("#¡VALOR!")
    cond = a[0]
    if isinstance(cond, _ErrorFormulaValor):
        raise cond
    if cond:
        return a[1] if len(a) > 1 else True
    return a[2] if len(a) > 2 else False


def _f_round(a):
    if not a:
        raise _ErrorFormulaValor("#¡VALOR!")
    numero = _num(a[0])
    decimales = int(_num(a[1])) if len(a) > 1 else 0
    return round(numero, decimales)


def _f_abs(a): return abs(_num(a[0]))


def _f_sqrt(a):
    v = _num(a[0])
    if v < 0:
        raise _ErrorFormulaValor("#¡NUM!")
    return math.sqrt(v)


def _f_power(a): return _num(a[0]) ** _num(a[1])


def _f_mod(a):
    divisor = _num(a[1])
    if divisor == 0:
        raise _ErrorFormulaValor("#¡DIV/0!")
    return _num(a[0]) % divisor


def _f_int(a): return math.floor(_num(a[0]))


def _f_concatenate(a): return "".join(_texto_formula(v) for v in _aplanar(a))


def _f_and(a): return all(bool(v) for v in _aplanar(a))


def _f_or(a): return any(bool(v) for v in _aplanar(a))


def _f_not(a): return not bool(a[0]) if a else True


def _f_today(a): return datetime.now().date()


def _f_now(a): return datetime.now()


def _f_len(a): return len(_texto_formula(a[0])) if a else 0


def _f_upper(a): return _texto_formula(a[0]).upper() if a else ""


def _f_lower(a): return _texto_formula(a[0]).lower() if a else ""


def _f_trim(a): return " ".join(_texto_formula(a[0]).split()) if a else ""


def _f_iferror(a):
    if not a:
        return ""
    valor = a[0]
    if isinstance(valor, _ErrorFormulaValor):
        return a[1] if len(a) > 1 else ""
    return valor


def _f_sumif(a):
    if len(a) < 2:
        raise _ErrorFormulaValor("#¡VALOR!")
    rango_criterio = a[0] if isinstance(a[0], list) else [a[0]]
    criterio = a[1]
    rango_suma = (a[2] if isinstance(a[2], list) else [a[2]]) if len(a) > 2 else rango_criterio
    total = 0.0
    for i, v in enumerate(rango_criterio):
        if _cumple_criterio(v, criterio):
            objetivo = rango_suma[i] if i < len(rango_suma) else 0
            if isinstance(objetivo, (int, float)) and not isinstance(objetivo, bool):
                total += objetivo
    return total


def _f_countif(a):
    if len(a) < 2:
        raise _ErrorFormulaValor("#¡VALOR!")
    rango = a[0] if isinstance(a[0], list) else [a[0]]
    criterio = a[1]
    return sum(1 for v in rango if _cumple_criterio(v, criterio))


_FUNCIONES_FORMULA = {
    "SUM": _f_sum, "SUMA": _f_sum,
    "PRODUCT": _f_product, "PRODUCTO": _f_product,
    "AVERAGE": _f_average, "PROMEDIO": _f_average,
    "MIN": _f_min, "MAX": _f_max,
    "COUNT": _f_count, "CONTAR": _f_count,
    "COUNTA": _f_counta, "CONTARA": _f_counta,
    "IF": _f_if, "SI": _f_if,
    "ROUND": _f_round, "REDONDEAR": _f_round,
    "ABS": _f_abs,
    "SQRT": _f_sqrt, "RAIZ": _f_sqrt,
    "POWER": _f_power, "POTENCIA": _f_power,
    "MOD": _f_mod, "RESIDUO": _f_mod,
    "INT": _f_int, "ENTERO": _f_int,
    "CONCATENATE": _f_concatenate, "CONCATENAR": _f_concatenate, "CONCAT": _f_concatenate,
    "AND": _f_and, "Y": _f_and,
    "OR": _f_or, "O": _f_or,
    "NOT": _f_not, "NO": _f_not,
    "TODAY": _f_today, "HOY": _f_today,
    "NOW": _f_now, "AHORA": _f_now,
    "LEN": _f_len, "LARGO": _f_len,
    "UPPER": _f_upper, "MAYUSC": _f_upper,
    "LOWER": _f_lower, "MINUSC": _f_lower,
    "TRIM": _f_trim, "ESPACIOS": _f_trim,
    "IFERROR": _f_iferror, "SI.ERROR": _f_iferror,
    "SUMIF": _f_sumif, "SUMAR.SI": _f_sumif,
    "COUNTIF": _f_countif, "CONTAR.SI": _f_countif,
}


_PATRON_TOKEN_FORMULA = re.compile(r"""
      (?P<WS>\s+)
    | (?P<RANGE>\$?[A-Za-z]{1,3}\$?\d+:\$?[A-Za-z]{1,3}\$?\d+)
    | (?P<FUNC>[A-Za-zÁÉÍÓÚÑ_][A-Za-zÁÉÍÓÚÑ_.0-9]*(?=\())
    | (?P<CELL>\$?[A-Za-z]{1,3}\$?\d+)
    | (?P<NUM>\d+(?:\.\d+)?)
    | (?P<STR>"(?:[^"\\]|\\.)*")
    | (?P<NAME>[A-Za-zÁÉÍÓÚÑ_][A-Za-zÁÉÍÓÚÑ_.0-9]*)
    | (?P<OP><>|<=|>=|[+\-*/^&=<>%])
    | (?P<LPAREN>\()
    | (?P<RPAREN>\))
    | (?P<COMMA>[,;])
""", re.VERBOSE)


def _tokenizar_formula(texto):
    tokens = []
    pos, largo = 0, len(texto)
    while pos < largo:
        m = _PATRON_TOKEN_FORMULA.match(texto, pos)
        if not m:
            raise _ErrorFormulaValor("#¡ERROR!")
        tipo = m.lastgroup
        if tipo != "WS":
            tokens.append((tipo, m.group(tipo)))
        pos = m.end()
    return tokens


class _AnalizadorFormula:
    """Parser recursivo-descendente de expresiones de fórmula (precedencia:
    comparación < concatenación (&) < suma/resta < mult/div < potencia)."""

    def __init__(self, tokens, motor):
        self.tokens = tokens
        self.pos = 0
        self.motor = motor

    def _actual(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _avanzar(self):
        tok = self._actual()
        self.pos += 1
        return tok

    def _esperar(self, tipo):
        tok = self._actual()
        if tok[0] != tipo:
            raise _ErrorFormulaValor("#¡ERROR!")
        return self._avanzar()

    def parsear(self):
        valor = self.comparacion()
        if self.pos != len(self.tokens):
            raise _ErrorFormulaValor("#¡ERROR!")
        return valor

    def comparacion(self):
        izq = self.concatenacion()
        while self._actual()[0] == "OP" and self._actual()[1] in ("=", "<>", "<", "<=", ">", ">="):
            op = self._avanzar()[1]
            der = self.concatenacion()
            izq = _aplicar_comparacion(op, izq, der)
        return izq

    def concatenacion(self):
        izq = self.aditiva()
        while self._actual()[0] == "OP" and self._actual()[1] == "&":
            self._avanzar()
            der = self.aditiva()
            izq = _texto_formula(izq) + _texto_formula(der)
        return izq

    def aditiva(self):
        izq = self.multiplicativa()
        while self._actual()[0] == "OP" and self._actual()[1] in ("+", "-"):
            op = self._avanzar()[1]
            der = self.multiplicativa()
            izq = _num(izq) + _num(der) if op == "+" else _num(izq) - _num(der)
        return izq

    def multiplicativa(self):
        izq = self.potencia()
        while self._actual()[0] == "OP" and self._actual()[1] in ("*", "/"):
            op = self._avanzar()[1]
            der = self.potencia()
            if op == "*":
                izq = _num(izq) * _num(der)
            else:
                divisor = _num(der)
                if divisor == 0:
                    raise _ErrorFormulaValor("#¡DIV/0!")
                izq = _num(izq) / divisor
        return izq

    def potencia(self):
        base = self.unario()
        if self._actual()[0] == "OP" and self._actual()[1] == "^":
            self._avanzar()
            exponente = self.potencia()
            base = _num(base) ** _num(exponente)
        return base

    def unario(self):
        if self._actual()[0] == "OP" and self._actual()[1] in ("+", "-"):
            op = self._avanzar()[1]
            valor = _num(self.unario())
            return valor if op == "+" else -valor
        return self.porcentaje()

    def porcentaje(self):
        valor = self.primario()
        if self._actual()[0] == "OP" and self._actual()[1] == "%":
            self._avanzar()
            return _num(valor) / 100.0
        return valor

    def primario(self):
        tipo, texto = self._actual()
        if tipo == "NUM":
            self._avanzar()
            return float(texto) if "." in texto else int(texto)
        if tipo == "STR":
            self._avanzar()
            return texto[1:-1].replace('\\"', '"')
        if tipo == "NAME":
            self._avanzar()
            superior = texto.upper()
            if superior in ("VERDADERO", "TRUE"):
                return True
            if superior in ("FALSO", "FALSE"):
                return False
            raise _ErrorFormulaValor("#¿NOMBRE?")
        if tipo == "FUNC":
            self._avanzar()
            self._esperar("LPAREN")
            argumentos = []
            if self._actual()[0] != "RPAREN":
                argumentos.append(self.comparacion())
                while self._actual()[0] == "COMMA":
                    self._avanzar()
                    argumentos.append(self.comparacion())
            self._esperar("RPAREN")
            return self.motor.llamar_funcion(texto.upper(), argumentos)
        if tipo == "RANGE":
            self._avanzar()
            return self.motor.valores_rango(texto)
        if tipo == "CELL":
            self._avanzar()
            return self.motor.valor_referencia(texto)
        if tipo == "LPAREN":
            self._avanzar()
            valor = self.comparacion()
            self._esperar("RPAREN")
            return valor
        raise _ErrorFormulaValor("#¡ERROR!")


class _MotorFormulas:
    """Evalúa las fórmulas de una hoja, resolviendo referencias/rangos y
    memorizando resultados para no recalcular la misma celda varias veces
    en una misma pasada -y detectando referencias circulares."""

    def __init__(self, obtener_crudo):
        self._obtener_crudo = obtener_crudo
        self._cache = {}
        self._en_curso = set()

    def valor_celda(self, r, c):
        clave = (r, c)
        if clave in self._cache:
            return self._cache[clave]
        if clave in self._en_curso:
            # Se LANZA (no se devuelve como valor): así el error no queda
            # cacheado en las celdas intermedias de la cadena -antes, una
            # sola detección de ciclo contaminaba con "#¡CIRC!" a toda la
            # cadena de dependientes aunque el ciclo real fuera otro-.
            raise _ErrorFormulaValor("#¡CIRC!")
        crudo = self._obtener_crudo(r, c)
        if crudo is None or (isinstance(crudo, str) and crudo.strip() == ""):
            valor = None
        elif isinstance(crudo, str) and crudo.strip().startswith("=") and len(crudo.strip()) > 1:
            self._en_curso.add(clave)
            try:
                valor = self._evaluar(crudo.strip()[1:])
            except _ErrorFormulaValor as err:
                valor = err
            except Exception:
                valor = _ErrorFormulaValor("#¡ERROR!")
            finally:
                self._en_curso.discard(clave)
        else:
            valor, _formato = _analizar_crudo(crudo)
        self._cache[clave] = valor
        return valor

    def _evaluar(self, expresion):
        tokens = _tokenizar_formula(expresion)
        return _AnalizadorFormula(tokens, self).parsear()

    def valor_referencia(self, ref_texto):
        r, c = _celda_a_indices(ref_texto)
        if r is None:
            raise _ErrorFormulaValor("#¡REF!")
        return self.valor_celda(r, c)

    def valores_rango(self, rango_texto):
        inicio, fin = rango_texto.split(":")
        r1, c1 = _celda_a_indices(inicio)
        r2, c2 = _celda_a_indices(fin)
        if r1 is None or r2 is None:
            raise _ErrorFormulaValor("#¡REF!")
        valores = []
        for r in range(min(r1, r2), max(r1, r2) + 1):
            for c in range(min(c1, c2), max(c1, c2) + 1):
                valores.append(self.valor_celda(r, c))
        return valores

    def llamar_funcion(self, nombre, argumentos):
        funcion = _FUNCIONES_FORMULA.get(nombre)
        if funcion is None:
            raise _ErrorFormulaValor("#¿NOMBRE?")
        try:
            return funcion(argumentos)
        except _ErrorFormulaValor:
            raise
        except ZeroDivisionError:
            raise _ErrorFormulaValor("#¡DIV/0!")
        except Exception:
            raise _ErrorFormulaValor("#¡VALOR!")


class _ManijaRelleno(QWidget):
    """El cuadradito que aparece en la esquina inferior derecha de la celda/
    rango seleccionado en la hoja de cálculo -igual que en Excel-: se
    arrastra hacia abajo para autocompletar las celdas de debajo, copiando
    el valor o continuando una serie (números, fechas, texto con número al
    final...). Solo avisa a `editor` (el VisorEditorReportes) de los tres
    eventos de mouse; toda la lógica de qué hacer vive ahí."""

    TAMANO = 8

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setFixedSize(self.TAMANO, self.TAMANO)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(f"""
            background-color: {editor._color_acento_actual()};
            border: 1px solid white;
        """)
        self.hide()

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self._editor._iniciar_arrastre_relleno()
            self.grabMouse()
            evento.accept()
            return
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):
        self._editor._arrastrar_relleno(self.mapToGlobal(evento.position().toPoint()))
        evento.accept()

    def mouseReleaseEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self.releaseMouse()
            self._editor._soltar_relleno()
            evento.accept()
            return
        super().mouseReleaseEvent(evento)


class _DelegadoHojaCalculo(QStyledItemDelegate):
    """Al iniciar la edición de una celda muestra su contenido CRUDO -la
    fórmula tal cual se escribió, p.ej. '=A1+B2', o el número/texto sin
    formatear- en vez del resultado ya calculado, igual que hace Excel; así
    se puede seguir editando la fórmula original en vez de su resultado.
    También es el punto donde se registra el estado "antes" para deshacer
    (ver VisorEditorReportes._registrar_deshacer_hoja): es el único momento
    fiable en el que se sabe con certeza que el usuario está a punto de
    cambiar una celda escribiendo directamente, antes de que el cambio
    ocurra."""

    def __init__(self, tabla, editor=None, parent=None):
        super().__init__(parent)
        self._tabla = tabla
        self._editor = editor

    def setEditorData(self, editor, index):
        if self._editor is not None:
            self._editor._registrar_deshacer_hoja()
        item = self._tabla.itemFromIndex(index)
        crudo = item.data(ROL_CRUDO) if item is not None else None
        texto = _texto_crudo_como_str(crudo) if crudo is not None else (item.text() if item else "")
        if hasattr(editor, "setText"):
            editor.setText(texto)
        else:
            super().setEditorData(editor, index)


class _DialogoEditorPaginaPDF(QDialog):
    """Editor de texto con formato -negrita/cursiva/fuente/tamaño/color/
    alineación- para reemplazar el contenido de una página de PDF (en
    blanco o ya existente). El resultado se aplica a la página con
    `page.insert_htmlbox(...)` de PyMuPDF, así que el HTML generado aquí
    queda con el formato real (no es solo texto plano)."""

    _ultima_fuente = None
    _ultimo_tamano = "12"

    def __init__(self, parent=None, texto_inicial="", css_editor=""):
        super().__init__(parent)
        self.setWindowTitle("Editar página")
        aplicar_icono_ventana(self, ICONO_DOCUMENTO)
        self.resize(760, 620)
        self.setMinimumSize(520, 400)
        # Este diálogo es una ventana de nivel superior aparte (no un hijo
        # dentro del árbol de widgets del editor pesado), así que un
        # stylesheet puesto en `self`/`editor_pesado` NUNCA le llega solo:
        # Qt no propaga stylesheets entre ventanas top-level distintas,
        # aunque una sea "parent" de la otra a efectos de gestión de
        # ventana. Sin esto, sus QToolButton (negrita/cursiva/subrayado/
        # alinear) caían al estilo nativo de Qt -sin el padding/tamaño
        # mínimo/hover que sí tienen esos mismos botones en la cinta
        # lateral-, lo que los hacía verse amontonados y con posiciones
        # "raras". Recibiendo aquí el mismo CSS del editor (ver
        # _pdf_editar_pagina_actual, que lo pasa), quedan idénticos.
        if css_editor:
            self.setStyleSheet(css_editor)
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.combo_fuente = QComboBox()
        self.combo_fuente.addItems(FUENTES_DISPONIBLES)
        if _DialogoEditorPaginaPDF._ultima_fuente in FUENTES_DISPONIBLES:
            self.combo_fuente.setCurrentText(_DialogoEditorPaginaPDF._ultima_fuente)
        self.combo_fuente.setMinimumWidth(140)
        conectar_tooltip_seleccion(self.combo_fuente, "Tipografía del texto")
        barra.addWidget(self.combo_fuente)
        self.combo_tamano = QComboBox()
        self.combo_tamano.addItems(["10", "11", "12", "14", "16", "18", "20", "24", "28"])
        self.combo_tamano.setCurrentText(_DialogoEditorPaginaPDF._ultimo_tamano)
        conectar_tooltip_seleccion(self.combo_tamano, "Tamaño de letra")
        barra.addWidget(self.combo_tamano)
        # NOTA: la tipografía de estos 3 botones se marca con QFont (setBold/
        # setItalic/setUnderline), NO con un QSS local de "font-weight"/
        # "font-style"/"text-decoration" -un setStyleSheet() propio en un
        # QToolButton reemplaza POR COMPLETO cualquier QSS heredado del
        # padre para ESE widget (Qt no combina propiedades entre el
        # stylesheet del padre y el del propio widget cuando ambos
        # apuntan al mismo tipo/selector), así que el botón perdía su
        # relleno, radio de borde y color de resaltado al pasar el cursor,
        # y volvía al estilo nativo de Qt -de ahí el resaltado "raro" que
        # tapaba el texto-. Usando QFont, el botón conserva íntegro el
        # estilo (incluido el hover) del resto de la barra.
        btn_negrita = QToolButton(); btn_negrita.setText("B"); btn_negrita.setCheckable(True)
        _f = btn_negrita.font(); _f.setBold(True); btn_negrita.setFont(_f)
        btn_cursiva = QToolButton(); btn_cursiva.setText("I"); btn_cursiva.setCheckable(True)
        _f = btn_cursiva.font(); _f.setItalic(True); btn_cursiva.setFont(_f)
        btn_subrayado = QToolButton(); btn_subrayado.setText("S"); btn_subrayado.setCheckable(True)
        _f = btn_subrayado.font(); _f.setUnderline(True); btn_subrayado.setFont(_f)
        barra.addWidget(btn_negrita); barra.addWidget(btn_cursiva); barra.addWidget(btn_subrayado)
        btn_color = QToolButton(); btn_color.setText("Color")
        barra.addWidget(btn_color)
        # Checkables y mutuamente excluyentes -mismo QButtonGroup exclusivo
        # que en la cinta de opciones del editor de reportes (ver
        # self._grupo_alinear_word)-, así el botón de la alineación activa
        # queda resaltado con el mismo indicador visual (QToolButton:checked
        # del stylesheet compartido, ver css_editor más arriba) y se
        # desmarca solo al elegir otra alineación.
        btn_izq = QToolButton(); btn_izq.setText(""); btn_izq.setCheckable(True)
        btn_izq.setIcon(icono_emoji(EMOJI_ALINEAR_IZQUIERDA)); btn_izq.setIconSize(_QSize_emoji(16, 16))
        btn_izq.setToolTip("Alinear a la izquierda")
        btn_centro = QToolButton(); btn_centro.setText(""); btn_centro.setCheckable(True)
        btn_centro.setIcon(icono_emoji(EMOJI_ALINEAR_CENTRO)); btn_centro.setIconSize(_QSize_emoji(16, 16))
        btn_centro.setToolTip("Centrar")
        btn_der = QToolButton(); btn_der.setText(""); btn_der.setCheckable(True)
        btn_der.setIcon(icono_emoji(EMOJI_ALINEAR_DERECHA)); btn_der.setIconSize(_QSize_emoji(16, 16))
        btn_der.setToolTip("Alinear a la derecha")
        self._grupo_alinear_pdf = QButtonGroup(self)
        self._grupo_alinear_pdf.setExclusive(True)
        for _b_align_pdf in (btn_izq, btn_centro, btn_der):
            self._grupo_alinear_pdf.addButton(_b_align_pdf)
        btn_izq.setChecked(True)
        barra.addWidget(btn_izq); barra.addWidget(btn_centro); barra.addWidget(btn_der)
        barra.addStretch()
        layout.addLayout(barra)

        self.editor = QTextEdit()
        limitar_campo_texto(self.editor, 5000)
        self.editor.setPlainText(texto_inicial)
        _f_inicial = QFont(self.combo_fuente.currentText())
        try:
            _f_inicial.setPointSize(int(self.combo_tamano.currentText()))
        except ValueError:
            pass
        self.editor.setFont(_f_inicial)
        layout.addWidget(self.editor, 1)

        def _formato_actual():
            return self.editor.textCursor().charFormat() if self.editor.textCursor().hasSelection() else self.editor.currentCharFormat()

        def _aplicar(formato):
            cursor = self.editor.textCursor()
            if not cursor.hasSelection():
                self.editor.setCurrentCharFormat(formato)
                return
            cursor.mergeCharFormat(formato)
            self.editor.setTextCursor(cursor)

        def _cambiar_fuente(_i=None):
            f = QTextCharFormat(); f.setFontFamilies([self.combo_fuente.currentText()]); _aplicar(f)

        def _cambiar_tamano(_i=None):
            try:
                f = QTextCharFormat(); f.setFontPointSize(float(self.combo_tamano.currentText())); _aplicar(f)
            except ValueError:
                pass

        def _alternar_negrita(activo):
            f = QTextCharFormat(); f.setFontWeight(QFont.Weight.Bold if activo else QFont.Weight.Normal); _aplicar(f)

        def _alternar_cursiva(activo):
            f = QTextCharFormat(); f.setFontItalic(activo); _aplicar(f)

        def _alternar_subrayado(activo):
            f = QTextCharFormat(); f.setFontUnderline(activo); _aplicar(f)

        def _elegir_color():
            color = _elegir_color_con_icono(QColor("#000000"), self, "Color del texto")
            if color.isValid():
                f = QTextCharFormat(); f.setForeground(color); _aplicar(f)

        self.combo_fuente.activated.connect(_cambiar_fuente)
        self.combo_tamano.activated.connect(_cambiar_tamano)
        btn_negrita.toggled.connect(_alternar_negrita)
        btn_cursiva.toggled.connect(_alternar_cursiva)
        btn_subrayado.toggled.connect(_alternar_subrayado)
        btn_color.clicked.connect(_elegir_color)
        btn_izq.toggled.connect(lambda marcado: self.editor.setAlignment(Qt.AlignmentFlag.AlignLeft) if marcado else None)
        btn_centro.toggled.connect(lambda marcado: self.editor.setAlignment(Qt.AlignmentFlag.AlignHCenter) if marcado else None)
        btn_der.toggled.connect(lambda marcado: self.editor.setAlignment(Qt.AlignmentFlag.AlignRight) if marcado else None)

        def _sincronizar_alineacion():
            """Refleja en los botones la alineación del párrafo donde está el
            cursor ahora mismo, tal como hace _word_sincronizar_barra en la
            cinta de opciones."""
            alineacion = self.editor.alignment()
            for boton in (btn_izq, btn_centro, btn_der):
                boton.blockSignals(True)
            btn_izq.setChecked(bool(alineacion & Qt.AlignmentFlag.AlignLeft))
            btn_centro.setChecked(bool(alineacion & Qt.AlignmentFlag.AlignHCenter))
            btn_der.setChecked(bool(alineacion & Qt.AlignmentFlag.AlignRight))
            for boton in (btn_izq, btn_centro, btn_der):
                boton.blockSignals(False)

        self.editor.cursorPositionChanged.connect(_sincronizar_alineacion)

        botones = QHBoxLayout()
        botones.addStretch()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.clicked.connect(self.reject)
        btn_aplicar = QPushButton("Aplicar a la página")
        btn_aplicar.setIcon(icono_emoji("✅"))
        btn_aplicar.setIconSize(_QSize_emoji(16, 16))
        def _guardar_preferencias():
            _DialogoEditorPaginaPDF._ultima_fuente = self.combo_fuente.currentText()
            _DialogoEditorPaginaPDF._ultimo_tamano = self.combo_tamano.currentText()
            self.accept()
        btn_aplicar.clicked.connect(_guardar_preferencias)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_aplicar)
        layout.addLayout(botones)
        centrar_y_al_frente(self, parent)


    def obtener_html(self):
        return self.editor.toHtml()


class _EtiquetaPaginaPDFSeleccionable(QLabel):
    """QLabel de una página de PDF que permite SELECCIONAR el texto con el
    mouse -arrastrando por encima, igual que en Microsoft Edge/el visor de
    PDF de Windows- en vez de ser solo una imagen fija. No es edición: es
    selección/copiado de texto real, resaltando sobre la imagen renderizada
    las palabras que toca el arrastre, y copiando el texto al portapapeles
    al soltar (o con clic derecho -> Copiar)."""

    def __init__(self, visor, indice_pagina, palabras, parent=None):
        super().__init__(parent)
        self._visor = visor
        self.indice_pagina = indice_pagina
        # palabras: lista de tuplas (x0, y0, x1, y1, texto, bloque, linea, num)
        # ya escaladas al mismo zoom con el que se renderizó el pixmap.
        self.palabras = palabras
        # enlaces: lista de (QRect en píxeles de esta página renderizada, uri)
        # -tanto los que ya traía el PDF original como los que se agreguen
        # aquí con "🔗 Enlace"-.
        self.enlaces = []
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setMouseTracking(True)
        self._inicio = None
        self._fin = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu_contextual)

    def _enlace_en(self, punto):
        for rect, uri in self.enlaces:
            if rect.contains(punto):
                return uri
        return None

    def _rect_seleccion(self):
        if self._inicio is None or self._fin is None:
            return None
        return QRect(self._inicio, self._fin).normalized()

    def _palabras_en_rango(self):
        rect = self._rect_seleccion()
        if rect is None or (rect.width() < 3 and rect.height() < 3):
            return []
        seleccionadas = []
        for p in self.palabras:
            wrect = QRect(int(p[0]), int(p[1]), max(1, int(p[2] - p[0])), max(1, int(p[3] - p[1])))
            if rect.intersects(wrect):
                seleccionadas.append(p)
        # Orden de lectura real: bloque -> línea -> número de palabra (así
        # como lo entrega PyMuPDF), no el orden en que el mouse las tocó.
        seleccionadas.sort(key=lambda p: (p[5], p[6], p[7]))
        return seleccionadas

    def texto_seleccionado(self):
        return " ".join(p[4] for p in self._palabras_en_rango())

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            if evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
                enlace = self._enlace_en(evento.position().toPoint())
                if enlace:
                    abrir_enlace_externo(enlace, self)
                    return
            self._inicio = evento.position().toPoint()
            self._fin = self._inicio
            self.update()
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):
        if self._inicio is not None and (evento.buttons() & Qt.MouseButton.LeftButton):
            self._fin = evento.position().toPoint()
            self.update()
        elif evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
            enlace = self._enlace_en(evento.position().toPoint())
            if enlace:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                QToolTip.showText(evento.globalPosition().toPoint(), f"Ctrl+clic para abrir:\n{enlace}")
            else:
                self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento):
        if self._inicio is not None and evento.button() == Qt.MouseButton.LeftButton:
            self._fin = evento.position().toPoint()
            texto = self.texto_seleccionado()
            self.update()
            if texto:
                QApplication.clipboard().setText(texto)
                QToolTip.showText(evento.globalPosition().toPoint(), "Copiado", self)
        super().mouseReleaseEvent(evento)

    def mouseDoubleClickEvent(self, evento):
        # Doble clic: selecciona la palabra bajo el cursor (como en Edge).
        punto = evento.position().toPoint()
        for p in self.palabras:
            wrect = QRect(int(p[0]), int(p[1]), max(1, int(p[2] - p[0])), max(1, int(p[3] - p[1])))
            if wrect.contains(punto):
                self._inicio = QPoint(int(p[0]), int(p[1]))
                self._fin = QPoint(int(p[2]), int(p[3]))
                texto = self.texto_seleccionado()
                self.update()
                if texto:
                    QApplication.clipboard().setText(texto)
                    QToolTip.showText(evento.globalPosition().toPoint(), "Copiado", self)
                break
        super().mouseDoubleClickEvent(evento)

    def _menu_contextual(self, punto):
        menu = QMenu(self)
        accion_copiar = menu.addAction("Copiar selección")
        accion_copiar.setEnabled(bool(self.texto_seleccionado()))
        accion_todo = menu.addAction("Seleccionar todo el texto de la página")
        enlace_bajo_cursor = self._enlace_en(punto)
        accion_abrir_enlace = None
        accion_insertar_enlace = None
        if enlace_bajo_cursor:
            menu.addSeparator()
            accion_abrir_enlace = menu.addAction("Abrir enlace")
        elif self.texto_seleccionado():
            menu.addSeparator()
            accion_insertar_enlace = menu.addAction("Convertir selección en hipervínculo…")
        elegido = menu.exec(self.mapToGlobal(punto))
        if elegido == accion_copiar:
            texto = self.texto_seleccionado()
            if texto:
                QApplication.clipboard().setText(texto)
        elif elegido == accion_todo:
            if self.palabras:
                xs0 = min(p[0] for p in self.palabras); ys0 = min(p[1] for p in self.palabras)
                xs1 = max(p[2] for p in self.palabras); ys1 = max(p[3] for p in self.palabras)
                self._inicio = QPoint(int(xs0), int(ys0))
                self._fin = QPoint(int(xs1), int(ys1))
                self.update()
                texto = self.texto_seleccionado()
                if texto:
                    QApplication.clipboard().setText(texto)
        elif accion_abrir_enlace is not None and elegido == accion_abrir_enlace:
            abrir_enlace_externo(enlace_bajo_cursor, self)
        elif accion_insertar_enlace is not None and elegido == accion_insertar_enlace:
            self._visor._pdf_insertar_enlace()

    def limpiar_seleccion(self):
        self._inicio = None
        self._fin = None
        self.update()

    def paintEvent(self, evento):
        super().paintEvent(evento)
        rect = self._rect_seleccion()
        if rect is None:
            return
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(37, 99, 235, 90))
        for p in self._palabras_en_rango():
            painter.drawRect(int(p[0]), int(p[1]), max(1, int(p[2] - p[0])), max(1, int(p[3] - p[1])))
        painter.end()


class _EtiquetaImagenArrastrable(QLabel):
    """Miniatura de una imagen incrustada en una celda de Excel que se puede
    ARRASTRAR con el mouse para moverla a otra celda -tanto en la grilla
    como en el ancla real de la imagen dentro del .xlsx (openpyxl)-. Es un
    reposicionamiento "encajado a la cuadrícula" (a la celda más cercana),
    no un arrastre libre a nivel de píxel como en Excel real."""

    def __init__(self, visor, fila, col, ruta_original=None, parent=None):
        super().__init__(parent)
        self._visor = visor
        self.fila = fila
        self.col = col
        self.ruta_original = ruta_original  # archivo de origen, para poder re-generar el PNG al cambiar opacidad
        self.opacidad = 1.0  # 1.0 = totalmente opaca (por defecto, igual que antes)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._arrastrando = False
        # El arrastre ya se inicia con solo presionar y mantener el clic
        # -no hace falta "seleccionar"/subrayar la imagen antes-. Si en la
        # práctica el primer clic parecía "no hacer nada", normalmente es
        # porque ese primer clic solo estaba dando foco a la celda de la
        # tabla por debajo; con setFocusPolicy en None evitamos que la
        # propia etiqueta le dispute el foco a la tabla y el clic-y-arrastre
        # queda disponible de inmediato, sin un primer clic "perdido".
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self._arrastrando = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(evento)

    def mouseReleaseEvent(self, evento):
        if self._arrastrando and evento.button() == Qt.MouseButton.LeftButton:
            self._arrastrando = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._visor._soltar_imagen_arrastrada(self, evento.globalPosition().toPoint())
        super().mouseReleaseEvent(evento)

    def mouseDoubleClickEvent(self, evento):
        # Doble clic: abre las opciones de la imagen (transparencia, quitar),
        # igual que hacer doble clic en una imagen en Word.
        self._visor._editar_opciones_imagen(self)
        super().mouseDoubleClickEvent(evento)


class _DialogoMarcaDeAgua(QDialog):
    """Recoge las opciones de la marca de agua de texto que se insertará en el PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insertar marca de agua")
        aplicar_icono_ventana(self, ICONO_COLOR)
        self.setMinimumWidth(360)
        layout = QFormLayout(self)

        self.in_texto = QLineEdit("CONFIDENCIAL")
        limitar_campo_texto(self.in_texto, 300)
        layout.addRow("Texto:", self.in_texto)

        self.spin_tamano = QSpinBox()
        self.spin_tamano.setRange(8, 160)
        self.spin_tamano.setValue(48)
        layout.addRow("Tamaño de fuente:", self.spin_tamano)

        self.slider_opacidad = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacidad.setRange(5, 100)
        self.slider_opacidad.setValue(25)
        self.lbl_opacidad = QLabel("25%")
        self.slider_opacidad.valueChanged.connect(lambda v: self.lbl_opacidad.setText(f"{v}%"))
        fila_opacidad = QHBoxLayout()
        fila_opacidad.addWidget(self.slider_opacidad, 1)
        fila_opacidad.addWidget(self.lbl_opacidad)
        layout.addRow("Opacidad:", fila_opacidad)

        self.combo_rotacion = QComboBox()
        self.combo_rotacion.addItem("Horizontal (0°)", 0)
        self.combo_rotacion.addItem("Diagonal ascendente (90°)", 90)
        self.combo_rotacion.addItem("Invertida (180°)", 180)
        self.combo_rotacion.addItem("Diagonal descendente (270°)", 270)
        conectar_tooltip_seleccion(self.combo_rotacion, "Orientación de la marca de agua")
        layout.addRow("Orientación:", self.combo_rotacion)

        self._color = QColor("#94A3B8")
        self.btn_color = QPushButton()
        self._pintar_boton_color()
        self.btn_color.clicked.connect(self._elegir_color)
        layout.addRow("Color:", self.btn_color)

        self.chk_todas = QCheckBox("Aplicar a todas las páginas")
        self.chk_todas.setChecked(True)
        layout.addRow("", self.chk_todas)

        fila_botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.clicked.connect(self.reject)
        btn_aceptar = QPushButton("Insertar")
        btn_aceptar.setObjectName("BtnAccionAgregar")
        btn_aceptar.clicked.connect(self.accept)
        fila_botones.addStretch()
        fila_botones.addWidget(btn_cancelar)
        fila_botones.addWidget(btn_aceptar)
        layout.addRow(fila_botones)
        centrar_y_al_frente(self, parent)


    def _pintar_boton_color(self):
        self.btn_color.setStyleSheet(f"background-color: {self._color.name()}; min-width: 60px;")

    def _elegir_color(self):
        color = _elegir_color_con_icono(self._color, self, "Color de la marca de agua")
        if color.isValid():
            self._color = color
            self._pintar_boton_color()

    def valores(self):
        return {
            "texto": self.in_texto.text().strip() or "MARCA DE AGUA",
            "tamano": self.spin_tamano.value(),
            "opacidad": self.slider_opacidad.value() / 100.0,
            "rotacion": self.combo_rotacion.currentData(),
            "color": (self._color.redF(), self._color.greenF(), self._color.blueF()),
            "todas": self.chk_todas.isChecked(),
        }


class _DialogoRedimensionarImagen(QDialog):
    """Diálogo tipo Word/Excel para cambiar el tamaño de una imagen ya
    insertada en el documento: ancho/alto en píxeles con proporción
    bloqueada por defecto, y un control de escala rápida (%)."""

    def __init__(self, ancho_actual, alto_actual, ancho_natural, alto_natural, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cambiar tamaño de la imagen")
        aplicar_icono_ventana(self, ICONO_CARGA)
        self.setMinimumWidth(320)
        self._proporcion = (alto_natural / ancho_natural) if ancho_natural else 1
        self._ancho_natural = ancho_natural or ancho_actual or 1
        self._actualizando = False
        layout = QFormLayout(self)

        self.spin_ancho = QSpinBox()
        self.spin_ancho.setRange(10, 4000)
        self.spin_ancho.setValue(max(10, int(ancho_actual)))
        layout.addRow("Ancho (px):", self.spin_ancho)

        self.spin_alto = QSpinBox()
        self.spin_alto.setRange(10, 4000)
        self.spin_alto.setValue(max(10, int(alto_actual)))
        layout.addRow("Alto (px):", self.spin_alto)

        self.chk_proporcion = QCheckBox("Mantener proporción")
        self.chk_proporcion.setChecked(True)
        layout.addRow("", self.chk_proporcion)

        fila_slider = QHBoxLayout()
        fila_slider.addWidget(QLabel("Escala rápida:"))
        self.slider_pct = QSlider(Qt.Orientation.Horizontal)
        self.slider_pct.setRange(10, 300)
        self.slider_pct.setValue(round(100 * ancho_actual / self._ancho_natural) if self._ancho_natural else 100)
        fila_slider.addWidget(self.slider_pct)
        self.lbl_pct = QLabel(f"{self.slider_pct.value()}%")
        fila_slider.addWidget(self.lbl_pct)
        layout.addRow(fila_slider)

        self.spin_ancho.valueChanged.connect(self._sincronizar_desde_ancho)
        self.spin_alto.valueChanged.connect(self._sincronizar_desde_alto)
        self.slider_pct.valueChanged.connect(self._aplicar_porcentaje)

        fila_botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_cancelar.clicked.connect(self.reject)
        btn_aceptar = QPushButton("Aplicar")
        btn_aceptar.setObjectName("BtnAccionAgregar")
        btn_aceptar.clicked.connect(self.accept)
        fila_botones.addStretch()
        fila_botones.addWidget(btn_cancelar)
        fila_botones.addWidget(btn_aceptar)
        layout.addRow(fila_botones)
        centrar_y_al_frente(self, parent)


    def _sincronizar_desde_ancho(self, valor):
        if self._actualizando:
            return
        self._actualizando = True
        if self.chk_proporcion.isChecked():
            self.spin_alto.setValue(max(10, round(valor * self._proporcion)))
        self.slider_pct.setValue(max(10, min(300, round(100 * valor / self._ancho_natural))))
        self.lbl_pct.setText(f"{self.slider_pct.value()}%")
        self._actualizando = False

    def _sincronizar_desde_alto(self, valor):
        if self._actualizando:
            return
        self._actualizando = True
        if self.chk_proporcion.isChecked() and self._proporcion:
            self.spin_ancho.setValue(max(10, round(valor / self._proporcion)))
        self._actualizando = False

    def _aplicar_porcentaje(self, valor):
        if self._actualizando:
            return
        self.lbl_pct.setText(f"{valor}%")
        self._actualizando = True
        nuevo_ancho = max(10, round(self._ancho_natural * valor / 100))
        self.spin_ancho.setValue(nuevo_ancho)
        self.spin_alto.setValue(max(10, round(nuevo_ancho * self._proporcion)))
        self._actualizando = False

    def valores(self):
        return self.spin_ancho.value(), self.spin_alto.value()


def _colores_tema(main_window):
    """Lee la paleta/tema activo de la ventana principal (mismo criterio que
    usa reportes.py) para que el editor -y en particular el recuadro que
    aparece al escribir sobre una celda- respete el tema y el modo claro/
    oscuro elegidos en vez de quedarse con colores fijos."""
    try:
        paleta = main_window.theme_palettes[main_window.tema_actual]
        idx = 1 if getattr(main_window, "modo_oscuro", False) else 0
        return {
            "bg_panel": paleta["display_bg"][idx],
            "bg_btn": paleta["btn_num_bg"][idx],
            "txt_prim": paleta["text_primary"][idx],
            "txt_sec": paleta["text_secondary"][idx],
            "accent": paleta["btn_op_bg"][idx],
            "accent_hv": paleta["btn_op_hover"][idx],
        }
    except Exception:
        return {"bg_panel": "#FFFFFF", "bg_btn": "#E2E8F0", "txt_prim": "#0F172A",
                "txt_sec": "#64748B", "accent": "#2563EB", "accent_hv": "#1D4ED8"}


class _LabelElidido(QLabel):
    """QLabel que recorta su texto con «…» cuando no cabe en el ancho
    disponible, en vez de dejar que un nombre de archivo largo se corte a la
    mitad contra el siguiente botón (como pasaba antes) o empuje el ancho de
    toda la barra. El texto completo siempre queda disponible como tooltip."""

    def __init__(self, texto="", parent=None):
        super().__init__(parent)
        self._texto_completo = texto
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setTextoCompleto(texto)

    def setTextoCompleto(self, texto):
        self._texto_completo = texto or ""
        self.setToolTip(self._texto_completo)
        self._actualizar_elidido()

    def _actualizar_elidido(self):
        metrica = self.fontMetrics()
        ancho_disponible = max(0, self.width())
        super().setText(metrica.elidedText(self._texto_completo, Qt.TextElideMode.ElideMiddle, ancho_disponible))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._actualizar_elidido()


class _VentanaPantallaCompletaEditor(QWidget):
    """Ventana de nivel superior "vacía": solo sirve de contenedor cuando el
    editor entra en modo pantalla completa. El contenido pesado del editor
    (barra + tabla/PDF/Word) se reparenta dentro de ella temporalmente y
    vuelve a su sitio de siempre al salir -con Esc o cerrando la ventana con
    la X-, así que aquí no hay que reconstruir ni duplicar nada."""

    def __init__(self, al_cerrar, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        aplicar_icono_ventana(self, ICONO_DOCUMENTO)
        self._al_cerrar = al_cerrar
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.layout_contenido = layout

    def closeEvent(self, event):
        # Si cierran con la X, hay que devolver el editor a su sitio original
        # antes de dejar que Qt oculte/destruya esta ventana -si no, el editor
        # (que vive dentro de ella) desaparecería con la ventana.
        self._al_cerrar()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._al_cerrar()
            return
        super().keyPressEvent(event)


class VisorEditorReportes(QWidget):
    """Panel de previsualización y edición avanzada de reportes exportados
    (CSV / Excel / PDF). Autónomo: se puede insertar como una pestaña más
    dentro de `ModuloReportes` sin que el resto del módulo dependa de él."""

    # Se emite cuando el usuario presiona "Terminar de editar" en el panel
    # de bienvenida: le avisa a ModuloReportes (dueño real de esta
    # instancia) que debe destruirla por completo -no solo ocultarla- para
    # liberar de verdad la memoria/CPU que tenía reservada (documento PDF
    # abierto, workbook de Excel en memoria, etc.). Este widget no puede
    # autodestruirse limpiamente desde dentro de su propio botón.
    solicitud_terminar_edicion = Signal()

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.ruta_actual = None
        self.tipo_actual = None
        self._delimitador_csv = ","
        self._wb = None
        self._wb_valores_cache = None
        self._tema_colores_excel = None
        self._cerrando = False  # True desde que arranca el cierre de la app (ver _limpiar_antes_de_salir)
        self._hoja_actual = None
        self._sincronizando = False
        self._recalculando = False  # evita recursión al recalcular fórmulas
        self._zoom_word = 100
        self._zoom_hoja = 100
        self._recientes = []  # [(ruta, etiqueta)]

        self._doc_pdf = None
        self._paginas_pdf_editables = set()
        self._cola_render_pdf = deque()
        self._token_render_pdf = 0
        self._indice_pagina_pdf = 0
        self._zoom_pdf = 1.4
        self._rotaciones_originales = {}
        self._pila_deshacer_pdf = []
        self._pila_rehacer_pdf = []

        # Estado del modo "pantalla completa" (ver _entrar/_salir_pantalla_completa).
        self._ventana_pantalla_completa = None
        # Barras de herramientas envueltas en scroll horizontal (ver
        # _barra_desplazable / _recalcular_barras_desplazables).
        self._barras_desplazables = []

        self._build_ui()
        self._mostrar_pagina("vacio")
        self.actualizar_tema()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._limpiar_antes_de_salir)

    # ------------------------------------------------------------
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ------------------------------------------------------------
    def _build_ui(self):
        # DISEÑO: para que la pestaña del editor jamás vuelva a "deformar" el
        # módulo entero, el contenido pesado (barras de herramientas, tabla,
        # visor de PDF, editor de Word) YA NO vive nunca dentro de esta
        # pestaña. Aquí, en `self`, solo hay un panel de bienvenida ligero
        # y fijo (self.panel_estado). Todo lo demás vive en un widget aparte
        # (self.editor_pesado) que se crea una sola vez, empieza "desconectado"
        # (sin layout que lo contenga) y solo se engancha dentro de la ventana
        # de pantalla completa cuando hay un archivo abierto -que ahora se abre
        # automáticamente en cuanto se carga un archivo-. Al cerrar esa
        # ventana, el editor_pesado simplemente se desconecta de nuevo (sin
        # destruirse: conserva todo lo escrito) y esta pestaña vuelve a verse
        # exactamente igual que siempre, porque nunca cambió.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.panel_estado = self._construir_panel_estado()
        layout.addWidget(self.panel_estado)

        self.editor_pesado = self._construir_editor_pesado()
        self.editor_pesado.setParent(self)
        self.editor_pesado.hide()

    # ---------------- Panel de bienvenida (siempre visible, ligero) ----------------
    def _construir_panel_estado(self):
        panel = QFrame()
        panel.setObjectName("TarjetaFiltros")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(28, 26, 28, 26)
        lay.setSpacing(6)

        self.lbl_icono_estado = QLabel("")
        self.lbl_icono_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from src.nucleo.iconos_emoji import pixmap_emoji
        self.lbl_icono_estado.setPixmap(pixmap_emoji("📝", 42))
        lay.addWidget(self.lbl_icono_estado)

        self.lbl_titulo_estado = QLabel("Editor de reportes")
        self.lbl_titulo_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_titulo_estado.setStyleSheet("font-size: 17px; font-weight: 700;")
        lay.addWidget(self.lbl_titulo_estado)

        self.lbl_texto_estado = QLabel(
            "Abre un PDF, Excel, Word o CSV para previsualizarlo y editarlo en una vista "
            "grande y cómoda -se abre automáticamente en pantalla completa-. También puedes "
            "usar los reportes recién exportados desde las otras pestañas: aparecerán en «Archivos recientes»."
        )
        self.lbl_texto_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_texto_estado.setObjectName("DescModulo")
        self.lbl_texto_estado.setWordWrap(True)
        self.lbl_texto_estado.setMaximumWidth(620)
        lay.addWidget(self.lbl_texto_estado, alignment=Qt.AlignmentFlag.AlignHCenter)

        fila_acciones = QHBoxLayout()
        fila_acciones.setSpacing(10)
        fila_acciones.addStretch()

        btn_abrir = QPushButton("Abrir archivo…")
        btn_abrir.setIcon(icono_emoji("📂"))
        btn_abrir.setIconSize(_QSize_emoji(16, 16))
        btn_abrir.setObjectName("BtnAccionNeutro")
        btn_abrir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_abrir.clicked.connect(self._abrir_dialogo)
        fila_acciones.addWidget(btn_abrir)

        self.combo_recientes = QComboBox()
        self.combo_recientes.setMinimumWidth(220)
        self.combo_recientes.addItem("Archivos recientes de esta sesión…", None)
        self.combo_recientes.currentIndexChanged.connect(self._seleccionar_reciente)
        conectar_tooltip_seleccion(self.combo_recientes, "Archivo reciente de esta sesión")
        fila_acciones.addWidget(self.combo_recientes)

        self.btn_continuar_editando = QPushButton("Continuar editando")
        self.btn_continuar_editando.setIcon(icono_emoji("✏"))
        self.btn_continuar_editando.setIconSize(_QSize_emoji(16, 16))
        self.btn_continuar_editando.setObjectName("BtnAccionEditar")
        self.btn_continuar_editando.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_continuar_editando.clicked.connect(self._entrar_pantalla_completa)
        self.btn_continuar_editando.setVisible(False)
        fila_acciones.addWidget(self.btn_continuar_editando)

        # "Terminar de editar": a diferencia de "Continuar editando" (que
        # solo vuelve a mostrar la ventana de pantalla completa con TODO
        # el archivo ya cargado en memoria), este botón cierra el editor
        # pesado por completo -workbook de Excel, documento PDF abierto,
        # contenido de Word, etc.- para no seguir gastando recursos en
        # segundo plano cuando el usuario ya terminó de trabajar con el
        # archivo. Ver _terminar_de_editar() y, del lado de reportes.py,
        # ModuloReportes._terminar_editor_reportes().
        self.btn_terminar_editar = QPushButton("Terminar de editar")
        self.btn_terminar_editar.setIcon(icono_emoji("🏁"))
        self.btn_terminar_editar.setIconSize(_QSize_emoji(16, 16))
        self.btn_terminar_editar.setObjectName("BtnAccionNeutro")
        self.btn_terminar_editar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_terminar_editar.clicked.connect(self._terminar_de_editar)
        self.btn_terminar_editar.setVisible(False)
        fila_acciones.addWidget(self.btn_terminar_editar)

        fila_acciones.addStretch()
        lay.addSpacing(8)
        lay.addLayout(fila_acciones)
        self._aplicar_sombra(panel)
        return panel

    # ---------------- Contenido pesado: barra + páginas (solo vive en pantalla completa) ----------------
    def _css_editor(self):
        """Hoja de estilos del TEMA PROPIO del editor. Se aplica SOLO al
        subárbol del editor (self y editor_pesado / la ventana de pantalla
        completa), así que nunca toca el tema de la app. La cinta de
        opciones (barras, botones, combos, pestañas) adopta el modo y el
        color de acento —hovers, bordes, focos, selección y controles
        marcados, no solo los botones primarios—; el CONTENIDO (hoja de
        cálculo, documento Word, visor PDF) NO se tiñe del acento: fondo
        blanco en modo claro y casi negro en modo oscuro."""
        oscuro = self._tema_modo_editor == "oscuro"
        acento = self._tema_acento_editor
        _c_acento = QColor(acento)
        if not _c_acento.isValid():
            _c_acento = QColor("#2563EB")
        acento_oscuro = _c_acento.darker(115).name()
        acento_claro = _c_acento.lighter(115).name()

        def _rgba(alpha):
            return f"rgba({_c_acento.red()},{_c_acento.green()},{_c_acento.blue()},{alpha})"

        if oscuro:
            fondo, panel, panel_alt = "#12161F", "#1C2330", "#232C3D"
            texto, texto_suave = "#E6EAF3", "#9AA6BC"
            sutil, borde, hover = "#26303F", "#36415A", "rgba(255,255,255,0.07)"
        else:
            fondo, panel, panel_alt = "#E9EDF5", "#FFFFFF", "#F5F7FC"
            texto, texto_suave = "#1E293B", "#64748B"
            sutil, borde, hover = "#EDF1F8", "#D3DCEA", "rgba(15,23,42,0.05)"
        # El CONTENIDO (hoja de cálculo, documento Word, visor PDF) se
        # mantiene SIEMPRE blanco/negro, sea cual sea el modo (claro u
        # oscuro) o el color de acento elegido -antes, en modo oscuro, se
        # volvía "#101418" (casi negro), lo que además de tapar el contraste
        # esperado por quien edita, oscurecía celdas vacías/sin datos que
        # antes se veían blancas, dando la falsa impresión de que la hoja
        # tenía relleno negro. Ahora el contenido no depende de `oscuro`.
        contenido_fondo, contenido_texto = "#FFFFFF", "#111827"
        css = """
        QWidget { background: @fondo; color: @texto; font-size: 12px; }
        QLabel { background: transparent; color: @texto; }
        QLabel#DescModulo { color: @texto_suave; }

        /* Cinta de opciones: tarjetas con filo de acento */
        QFrame#TarjetaFiltros { background: @panel; border: 1px solid @borde;
                                border-bottom: 3px solid @acento;
                                border-radius: 10px; }

        /* Grupos de la cinta (tipo Office: botones arriba, etiqueta abajo)
           y el separador vertical delgado entre uno y otro. */
        QWidget#GrupoRibbon { background: transparent; }
        QWidget#ContenedorSeparadorRibbon { background: transparent; }
        QLabel#EtiquetaGrupoRibbon { color: @texto_suave; font-size: 9px; font-weight: 700;
                                     letter-spacing: 0.4px; padding-top: 1px; }
        QFrame#SeparadorRibbon { background: @borde; max-width: 1px; min-width: 1px; border: none; }

        /* Control de zoom "en píldora": el -, el campo y el + comparten un
           único borde redondeado en vez de verse como tres piezas sueltas. */
        QWidget#PillZoom { background: @panel_alt; border: 1px solid @borde; border-radius: 15px; }
        QWidget#PillZoom QToolButton { border: none; border-radius: 13px; background: transparent;
                                        color: @texto; font-weight: 700; }
        QWidget#PillZoom QToolButton:hover { background: @acento_suave; color: @texto; }
        QWidget#PillZoom QToolButton:pressed { background: @acento_media; color: @texto; }
        QWidget#PillZoom QLineEdit { border: none; background: transparent; border-radius: 0px; padding: 0;
                                      color: @texto; }

        /* Botones: hover/foco con tinte del acento */
        QPushButton { background: @panel; color: @texto; border: 1px solid @borde;
                      border-radius: 8px; padding: 5px 12px; }
        QPushButton:hover { background: @acento_suave; border: 1px solid @acento_media; }
        QPushButton:pressed { background: @acento_media; }
        QPushButton:focus { border: 1px solid @acento; }
        QPushButton:disabled { color: rgba(127,127,127,0.5); background: @panel_alt; }
        QPushButton#BtnAccionAgregar, QPushButton#BtnAccionEditar {
            background: @acento; color: #FFFFFF; border: 1px solid @acento; font-weight: 600; }
        QPushButton#BtnAccionAgregar:hover, QPushButton#BtnAccionEditar:hover {
            background: @acento_variant; border: 1px solid @acento_variant; }
        QPushButton#BtnAccionAgregar:pressed, QPushButton#BtnAccionEditar:pressed {
            background: @acento_oscuro; }
        QPushButton#BtnAccionEliminar { background: #DC2626; color: #FFFFFF; border: 1px solid #B91C1C; }
        QToolButton { background: @panel; color: @texto; border: 1px solid @borde;
                      border-radius: 8px; padding: 3px 8px; min-height: 22px; }
        QToolButton:hover { background: @acento_suave; border: 1px solid @acento_media; }
        QToolButton:pressed { background: @acento_media; }
        QToolButton:checked { background: @acento; color: #FFFFFF; border: 1px solid @acento; }
        QToolButton:disabled { color: rgba(127,127,127,0.5); }

        /* Combos y entradas: foco con acento */
        QComboBox { background: @panel; color: @texto; border: 1px solid @borde;
                    border-radius: 8px; padding: 3px 10px; }
        QComboBox:hover { border: 1px solid @acento_media; background: @acento_suave; }
        QComboBox:focus { border: 1px solid @acento; }
        QComboBox::drop-down { border: none; width: 20px; }
        QComboBox QAbstractItemView { background: @panel; color: @texto;
            border: 1px solid @borde; selection-background-color: @acento;
            selection-color: #FFFFFF; outline: 0; }
        QLineEdit { background: @panel; color: @texto; border: 1px solid @borde;
                    border-radius: 8px; padding: 3px 10px; }
        QLineEdit:focus { border: 1px solid @acento; }
        QSpinBox { background: @panel; color: @texto; border: 1px solid @borde;
                   border-radius: 6px; }
        QSpinBox:focus { border: 1px solid @acento; }
        QCheckBox { background: transparent; color: @texto; spacing: 6px; }
        QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid @borde;
                               border-radius: 4px; background: @panel; }
        QCheckBox::indicator:hover { border: 1px solid @acento; }
        QCheckBox::indicator:checked { background: @acento; border: 1px solid @acento; }

        /* Pestañas de modo (Hoja / PDF / Word) */
        QTabWidget::pane { border: none; background: transparent; }
        QTabBar::tab { background: @sutil; color: @texto_suave; border-radius: 8px;
                       padding: 6px 16px; margin-right: 4px; font-weight: 600; }
        QTabBar::tab:hover { background: @acento_suave; color: @texto; }
        QTabBar::tab:selected { background: @acento; color: #FFFFFF; }

        /* Menús y scrollbars con acento sutil */
        QMenu { background: @panel; color: @texto; border: 1px solid @borde;
                border-radius: 8px; padding: 4px; }
        QMenu::item { border-radius: 6px; padding: 5px 18px; }
        QMenu::item:selected { background: @acento; color: #FFFFFF; }
        QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
        QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
        QScrollBar::handle { background: @borde; border-radius: 4px;
                             min-width: 24px; min-height: 24px; }
        QScrollBar::handle:hover { background: @acento_media; }
        QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
        QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

        /* CONTENIDO: nunca se tiñe del acento (blanco/negro según el modo) */
        QTableWidget { background: @contenido_fondo; color: @contenido_texto;
                       gridline-color: @borde; border: 1px solid @borde;
                       selection-background-color: @acento; selection-color: #FFFFFF; }
        QTableWidget::item:selected { background: @acento; color: #FFFFFF; }
        QHeaderView::section { background: @sutil; color: @texto;
                               border: none; border-right: 1px solid @borde;
                               border-bottom: 2px solid @acento; padding: 4px; }
        QTextEdit { background: @contenido_fondo; color: @contenido_texto;
                    border: 1px solid @borde; }
        QTextEdit:focus { border: 1px solid @acento; }
        QGraphicsView { background: @contenido_fondo; border: 1px solid @borde; }

        /* Solo el/los QScrollArea que envuelven CONTENIDO real (el visor
           de PDF; el lienzo de Word ya es un QGraphicsView, cubierto arriba)
           se dejan blanco/negro plano. El QScrollArea que envuelve la
           BARRA DE HERRAMIENTAS (cinta/ribbon, ver _barra_desplazable) NO
           es contenido: antes caía en esta misma regla genérica y por eso,
           en modo oscuro, la cinta entera -y su viewport interno con los
           botones- se quedaba blanca en vez de adoptar el tema. */
        QScrollArea#ScrollContenidoPDF, QScrollArea#ScrollContenidoPDF > QWidget > QWidget {
            background: @contenido_fondo; border: none; }
        QScrollArea#ScrollBarraHerramientas { background: transparent; border: none; }
        QScrollArea#ScrollBarraHerramientas > QWidget > QWidget { background: transparent; }

        /* Cuadrito de la esquina superior izquierda de toda tabla (donde se
           cruzan los encabezados de fila y columna): sin esta regla, Qt lo
           pinta con el estilo nativo del sistema (blanco), aunque el resto
           de la tabla ya esté en el tema correspondiente. */
        QTableCornerButton::section { background: @sutil; border: none;
            border-right: 1px solid @borde; border-bottom: 2px solid @acento; }

        /* Tooltips con el mismo estilo redondeado que el resto de AcaDeXI */
        QToolTip {
            background-color: @panel;
            color: @texto;
            border: 1px solid @borde;
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 12px;
        }
        """
        sustituciones = {
            "@fondo": fondo, "@panel": panel, "@panel_alt": panel_alt,
            "@texto": texto, "@texto_suave": texto_suave, "@sutil": sutil,
            "@borde": borde, "@hover": hover,
            "@acento": acento, "@acento_suave": _rgba(0.14),
            "@acento_media": _rgba(0.30), "@acento_oscuro": acento_oscuro,
            "@acento_variant": acento_oscuro if oscuro else acento_claro,
            "@contenido_fondo": contenido_fondo,
            "@contenido_texto": contenido_texto,
        }
        # OJO: reemplazar por orden de aparición del diccionario (como se
        # hacía antes) es un error sutil -"@panel" es una subcadena de
        # "@panel_alt", "@texto" lo es de "@texto_suave", y "@acento" lo es
        # de "@acento_suave"/"@acento_media"/"@acento_oscuro"/"@acento_variant"-,
        # así que reemplazar el token corto PRIMERO deja el token largo a
        # medio comer (p. ej. "@panel_alt" quedaba como "#FFFFFF_alt", un
        # color inválido que Qt simplemente ignoraba en silencio). Eso hacía
        # que varios detalles finos -texto secundario, hover/pulsado con
        # tinte de acento, fondo de los botones deshabilitados- nunca se
        # llegaran a aplicar. Reemplazando primero los tokens más largos se
        # evita el problema.
        for clave in sorted(sustituciones, key=len, reverse=True):
            css = css.replace(clave, sustituciones[clave])
        return css

    def _aplicar_tema_editor(self):
        """Aplica el tema propio del editor a TODAS las raíces donde puede
        vivir su interfaz: el widget del módulo (self), el contenedor
        editor_pesado (que se re-parenta a la ventana de pantalla completa)
        y, si está abierta, la propia ventana. Un widget-level stylesheet
        solo afecta a su subárbol, por eso la app conserva su tema."""
        self._css_editor_actual = self._css_editor()
        for widget in (self, getattr(self, "editor_pesado", None),
                       getattr(self, "_ventana_pantalla_completa", None)):
            if widget is not None:
                try:
                    widget.setStyleSheet(self._css_editor_actual)
                except RuntimeError:
                    pass  # widget C++ ya destruido (ventana cerrada)
        # El icono "alinear justificado" sale blanco de fábrica (está pensado
        # para el botón de Filtros con fondo de acento); aquí se re-tiñe
        # según el modo del editor para que contraste con la cinta.
        if getattr(self, "btn_alinear_just_word", None) is not None:
            self.btn_alinear_just_word.setIcon(self._icono_alinear_justificado())

    def _icono_alinear_justificado(self):
        """Icono de "alinear justificado" (\\uE000) adaptado al modo del
        editor: en modo CLARO se tiñe de negro (sobre la cinta clara el
        blanco no se veía), y en modo oscuro se mantiene el blanco original.
        El tinte se calcula UNA vez por modo y queda cacheado."""
        if getattr(self, "_tema_modo_editor", "claro") != "claro":
            return icono_emoji("\uE000")
        icono = getattr(self, "_icono_just_negro_cache", None)
        if icono is None:
            base = pixmap_emoji("\uE000", 16)
            tinte = QPixmap(base.size())
            tinte.fill(Qt.GlobalColor.transparent)
            pintor = QPainter(tinte)
            pintor.drawPixmap(0, 0, base)
            pintor.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            pintor.fillRect(0, 0, tinte.width(), tinte.height(), QColor("#000000"))
            pintor.end()
            icono = QIcon(tinte)
            self._icono_just_negro_cache = icono
        return icono

    def _construir_editor_pesado(self):
        contenedor = QWidget()
        contenedor.setObjectName("EditorPesadoRaiz")

        # Envoltorio horizontal que centra el editor: deja un margen elástico
        # a cada lado en pantallas muy anchas, pero desaparece (el editor ocupa
        # todo el ancho) en pantallas normales o cuando la ventana está reducida.
        outer = QHBoxLayout(contenedor)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Widget interior real (el que tenía antes el papel de «contenedor»)
        inner_w = QWidget()
        inner_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(inner_w)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        barra = QFrame()
        barra.setObjectName("TarjetaFiltros")
        lay_barra = QHBoxLayout(barra)
        lay_barra.setContentsMargins(14, 10, 14, 10)
        lay_barra.setSpacing(10)

        # Deshacer/Rehacer: dos botones circulares chiquitos, igual que en
        # la barra de título de Word/Excel/PowerPoint reales (junto a
        # "Guardar"). A propósito NO están dentro de la barra de cada
        # pestaña (hoja/PDF/Word): viven aquí, en la barra superior común a
        # las tres, para que se sientan como una sola acción global del
        # editor -tal como en Office- y no como algo distinto por pestaña.
        self.btn_deshacer = QToolButton()
        self.btn_deshacer.setText("")
        self.btn_deshacer.setIcon(icono_emoji("↩"))
        self.btn_deshacer.setIconSize(_QSize_emoji(16, 16))
        self.btn_deshacer.setToolTip("Deshacer (Ctrl+Z)")
        self.btn_deshacer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_deshacer.setFixedSize(30, 30)
        self.btn_deshacer.clicked.connect(self._deshacer_global)
        self.btn_deshacer.setEnabled(False)
        lay_barra.addWidget(self.btn_deshacer)

        self.btn_rehacer = QToolButton()
        self.btn_rehacer.setText("")
        self.btn_rehacer.setIcon(icono_emoji("↷"))
        self.btn_rehacer.setIconSize(_QSize_emoji(16, 16))
        self.btn_rehacer.setToolTip("Rehacer (Ctrl+Y)")
        self.btn_rehacer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rehacer.setFixedSize(30, 30)
        self.btn_rehacer.clicked.connect(self._rehacer_global)
        self.btn_rehacer.setEnabled(False)
        lay_barra.addWidget(self.btn_rehacer)

        for boton in (self.btn_deshacer, self.btn_rehacer):
            boton.setStyleSheet("""
                QToolButton {
                    background: rgba(127,127,127,0.14);
                    border: none;
                    border-radius: 15px;
                    font-size: 15px;
                }
                QToolButton:hover:!disabled { background: rgba(127,127,127,0.26); }
                QToolButton:pressed { background: rgba(127,127,127,0.36); }
                QToolButton:disabled { color: rgba(127,127,127,0.45); }
            """)

        btn_abrir_otro = QPushButton("Abrir otro archivo…")
        btn_abrir_otro.setIcon(icono_emoji("📂"))
        btn_abrir_otro.setIconSize(_QSize_emoji(16, 16))
        btn_abrir_otro.setObjectName("BtnAccionNeutro")
        btn_abrir_otro.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_abrir_otro.clicked.connect(self._abrir_dialogo)
        lay_barra.addWidget(btn_abrir_otro)

        self.lbl_archivo_actual = _LabelElidido("Ningún archivo abierto")
        self.lbl_archivo_actual.setObjectName("DescModulo")
        self.lbl_archivo_actual.setMaximumWidth(340)
        lay_barra.addWidget(self.lbl_archivo_actual, 2)

        self.btn_guardar = QPushButton("Guardar")
        self.btn_guardar.setIcon(icono_emoji("💾"))
        self.btn_guardar.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar.setObjectName("BtnAccionEditar")
        self.btn_guardar.clicked.connect(self._guardar)
        self.btn_guardar.setEnabled(False)
        lay_barra.addWidget(self.btn_guardar)

        self.btn_guardar_como = QPushButton("Guardar como…")
        self.btn_guardar_como.setIcon(icono_emoji("💾"))
        self.btn_guardar_como.setIconSize(_QSize_emoji(16, 16))
        self.btn_guardar_como.setObjectName("BtnAccionAgregar")
        self.btn_guardar_como.clicked.connect(self._guardar_como)
        self.btn_guardar_como.setEnabled(False)
        lay_barra.addWidget(self.btn_guardar_como)

        self.btn_exportar = QPushButton("Exportar a…")
        self.btn_exportar.setIcon(icono_emoji("\uE002"))
        self.btn_exportar.setIconSize(_QSize_emoji(16, 16))
        self.btn_exportar.setObjectName("BtnAccionAjustar")
        self.btn_exportar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_exportar = QMenu(self.btn_exportar)
        self.btn_exportar.setMenu(self.menu_exportar)
        self.btn_exportar.setEnabled(False)
        lay_barra.addWidget(self.btn_exportar)

        self.btn_imprimir = QPushButton("Imprimir")
        self.btn_imprimir.setIcon(icono_emoji("🖨"))
        self.btn_imprimir.setIconSize(_QSize_emoji(16, 16))
        self.btn_imprimir.setObjectName("BtnAccionNeutro")
        self.btn_imprimir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_imprimir.setToolTip("Imprimir directamente el archivo que estás viendo/editando")
        self.btn_imprimir.clicked.connect(self._imprimir)
        self.btn_imprimir.setEnabled(False)
        lay_barra.addWidget(self.btn_imprimir)

        # ---- Tema PROPIO del editor (independiente de la app) ----
        # Por defecto: modo CLARO con acento azul. Solo la "cinta de
        # opciones" (barras, botones, combos, pestañas) adopta el tema;
        # el CONTENIDO (hoja, documento Word, PDF) no se tiñe del color
        # de acento: se ve blanco en modo claro y casi negro en oscuro.
        self._tema_modo_editor = "claro"
        self._tema_acento_editor = "#2563EB"
        self._css_editor_actual = ""
        lay_barra.addSpacing(12)
        self.combo_modo_editor = QComboBox()
        self.combo_modo_editor.addItems(["Claro", "Oscuro"])
        self.combo_modo_editor.setToolTip("Modo del editor (solo afecta a esta ventana, no a la app)")
        self.combo_modo_editor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_modo_editor.currentTextChanged.connect(
            lambda texto: (setattr(self, "_tema_modo_editor", texto.strip().lower()),
                           self._aplicar_tema_editor()))
        lay_barra.addWidget(self.combo_modo_editor)
        self.combo_acento_editor = QComboBox()
        for _nombre, _color in _TEMAS_ACENTO_EDITOR:
            self.combo_acento_editor.addItem(_nombre, _color)
        self.combo_acento_editor.setToolTip("Color de acento del editor (solo afecta a esta ventana)")
        self.combo_acento_editor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_acento_editor.currentIndexChanged.connect(
            lambda _: (setattr(self, "_tema_acento_editor",
                               self.combo_acento_editor.currentData() or "#2563EB"),
                       self._aplicar_tema_editor()))
        lay_barra.addWidget(self.combo_acento_editor)
        self._aplicar_tema_editor()

        # Igual que las barras de formato de cada página (hoja de cálculo,
        # PDF, Word): envuelta en scroll horizontal para que su ancho mínimo
        # (botones + nombre de archivo) JAMÁS se imponga como ancho mínimo de
        # toda la ventana de pantalla completa. Sin esto, en pantallas/monitores
        # más angostos que la suma de esos botones (p. ej. 1366px), Windows no
        # podía maximizar la ventana a ese ancho -el mensaje
        # "QWindowsWindow::setGeometry: Unable to set geometry..." que se veía
        # en consola- y la ventana quedaba con un tamaño roto hasta restaurarla
        # y volver a maximizarla a mano.
        layout.addWidget(self._barra_desplazable(barra))

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.stack, 1)

        self.stack.addWidget(self._pagina_vacia())
        self.stack.addWidget(self._pagina_hoja_calculo())
        self.stack.addWidget(self._pagina_pdf())
        self.stack.addWidget(self._pagina_word())

        self._crear_atajos_teclado(contenedor)

        # Ensamblar el contenedor centrado
        outer.addWidget(inner_w, 1)

        return contenedor

    def _crear_atajos_teclado(self, contenedor_editor):
        """Atajos de teclado del editor, activos mientras el editor o
        cualquiera de sus widgets hijos tenga el foco (WidgetWithChildrenShortcut).
        Cada atajo revisa en qué pestaña (hoja/PDF/Word) está el usuario y
        actúa en consecuencia -no todos los atajos aplican a todas las
        pestañas-.

        IMPORTANTE -por qué se registran en `contenedor_editor` (el widget
        que luego se guarda como self.editor_pesado) y NO en `self`:
        GestorAtajos._widget_activo() (atajos.py) encuentra el módulo activo
        subiendo por la cadena de padres desde el widget con foco real,
        buscando el primer ancestro con `_atajos_registrados`. Pero
        `editor_pesado` se DESPARENTA de `self` y se reengancha dentro de su
        propia ventana de pantalla completa en cuanto se abre un archivo
        (ver _entrar_pantalla_completa: `self.editor_pesado.setParent(None)`
        y luego se reparenta en `ventana`) -así que, mientras se edita de
        verdad (que es prácticamente siempre: el editor se abre a pantalla
        completa automáticamente al cargar un archivo), `self` DEJA DE SER
        ANCESTRO de la tabla/Word/PDF con foco. Registrar los atajos en
        `self` los dejaba matemáticamente inalcanzables para esa búsqueda
        ascendente en cuanto el editor estaba realmente en uso -la
        ventanita nunca los encontraba, aunque los QShortcut sí funcionaran
        (esos no dependen de esta cadena de padres, solo del foco). Al
        registrarlos en `contenedor_editor`, que es el mismo objeto en
        ambos casos (embebido en `self` o reenganchado en la ventana de
        pantalla completa), la búsqueda ascendente SIEMPRE lo encuentra."""
        # Título que mostrará la ventanita flotante de ayuda (Alt mantenido,
        # ver atajos.py) mientras el editor tenga el foco.
        contenedor_editor._titulo_modulo_atajos = "Editor de reportes"
        self._contenedor_atajos_editor = contenedor_editor  # ver _mostrar_atajos_disponibles

        def _atajo(secuencia, funcion, descripcion=""):
            # Usa registrar_atajo (atajos.py) en vez de un QShortcut suelto:
            # así, además de crear el atajo de verdad, queda anotado en
            # contenedor_editor._atajos_registrados y la ventanita de ayuda
            # (mantener presionada Alt) puede mostrarlo -mismo mecanismo que
            # ya usan estudiantes.py, personal.py, profesores.py, etc.
            return registrar_atajo(contenedor_editor, self.main_window, secuencia, descripcion, funcion)

        def _pagina_actual():
            return {0: "vacio", 1: "hoja", 2: "pdf", 3: "word"}.get(self.stack.currentIndex())

        def _negrita():
            pagina = _pagina_actual()
            if pagina == "hoja":
                self._alternar_negrita()
            elif pagina == "word":
                self.editor_word.setFontWeight(QFont.Weight.Bold if not self.editor_word.fontWeight() == QFont.Weight.Bold else QFont.Weight.Normal)

        def _cursiva():
            pagina = _pagina_actual()
            if pagina == "hoja":
                self._alternar_cursiva()
            elif pagina == "word":
                self.editor_word.setFontItalic(not self.editor_word.fontItalic())

        def _subrayado():
            pagina = _pagina_actual()
            if pagina == "hoja":
                self._alternar_subrayado()
            elif pagina == "word":
                self.editor_word.setFontUnderline(not self.editor_word.fontUnderline())

        def _buscar():
            pagina = _pagina_actual()
            if pagina == "hoja":
                self.in_buscar_celda.setFocus()
                self.in_buscar_celda.selectAll()
            elif pagina == "word":
                self.in_buscar_word.setFocus()
                self.in_buscar_word.selectAll()
            elif pagina == "pdf" and hasattr(self, "btn_texto_pdf"):
                self.btn_texto_pdf.setChecked(True)

        def _copiar_seleccion_pdf():
            if _pagina_actual() == "pdf":
                self._pdf_copiar_seleccion()

        def _borrar():
            pagina = _pagina_actual()
            if pagina == "hoja":
                self._borrar_contenido_celdas_seleccionadas()
            elif pagina == "word":
                cursor = self.editor_word.textCursor()
                if cursor.hasSelection():
                    cursor.removeSelectedText()

        def _seleccionar_todo():
            pagina = _pagina_actual()
            if pagina == "hoja":
                self.tabla_editor.selectAll()
            elif pagina == "word":
                self.editor_word.selectAll()

        # Ctrl+S: guardar (en cualquier pestaña).
        _atajo("Ctrl+S", self._guardar, "Guardar")
        # Ctrl+B / Ctrl+I / Ctrl+U: negrita/cursiva/subrayado -en la hoja de
        # cálculo actúan sobre las celdas seleccionadas; en Word, sobre el
        # texto seleccionado del cursor (igual que en cualquier procesador
        # de texto).
        _atajo("Ctrl+B", _negrita, "Negrita")
        _atajo("Ctrl+I", _cursiva, "Cursiva")
        _atajo("Ctrl+U", _subrayado, "Subrayado")
        # Ctrl+F: buscar -en la hoja/Word enfoca el campo de búsqueda; en el
        # PDF abre el panel de texto para buscar/seleccionar.
        _atajo("Ctrl+F", _buscar, "Buscar")
        # Ctrl+K: insertar/editar hipervínculo -solo tiene sentido en Word,
        # así que no hace nada si esa pestaña no está visible-.
        # Ctrl+K: insertar/editar hipervínculo -en la hoja aplica a la
        # celda actual, en Word al texto seleccionado/bajo el cursor-.
        def _insertar_enlace_segun_pagina():
            indice = self.stack.currentIndex()
            if indice == 1:
                self._hoja_insertar_enlace()
            elif indice == 3:
                self._word_insertar_enlace()
        _atajo("Ctrl+K", _insertar_enlace_segun_pagina, "Insertar/editar hipervínculo")
        # Delete: borra el contenido de las celdas seleccionadas en la hoja
        # (como en Excel: NO borra formato, solo el valor), o el texto
        # seleccionado en Word. A propósito NO se registra "Backspace" como
        # atajo global: si se hiciera, cada vez que borrases una letra
        # escribiendo dentro de una celda o en Word se dispararía TAMBIÉN
        # esta función -rompiendo el borrado normal de texto mientras
        # escribes-. "Delete" es seguro porque, mientras se está escribiendo
        # de verdad (editor de celda o cursor de Word activo), esos widgets
        # ya interceptan esa tecla ellos mismos para su borrado normal
        # -nuestro atajo solo llega a dispararse cuando NO se está editando
        # texto, exactamente como en Excel real-.
        _atajo("Delete", _borrar, "Borrar contenido de la selección")
        # Ctrl+A: seleccionar todo (celdas de la hoja, o todo el texto en Word).
        _atajo("Ctrl+A", _seleccionar_todo, "Seleccionar todo")
        # Ctrl+Shift+C: copiar el texto seleccionado de una página de PDF
        # (arrastrando el mouse) -alternativa por teclado al botón/menú.
        _atajo("Ctrl+Shift+C", _copiar_seleccion_pdf, "Copiar selección de texto (PDF)")
        # Ctrl++ / Ctrl+- / Ctrl+0: zoom -aplica al PDF, la hoja o Word,
        # el que esté visible en ese momento-.
        _atajo("Ctrl++", self._zoom_acercar_pagina_actual, "Acercar zoom")
        _atajo("Ctrl+=", self._zoom_acercar_pagina_actual)  # el "+" real suele venir con Shift en muchos teclados -mismo atajo, no se repite en la ventanita de ayuda
        _atajo("Ctrl+-", self._zoom_alejar_pagina_actual, "Alejar zoom")
        _atajo("Ctrl+0", self._zoom_restablecer_pagina_actual, "Restablecer zoom")
        # Ctrl+Z / Ctrl+Y (o Ctrl+Shift+Z): deshacer/rehacer -funciona en
        # las tres pestañas (hoja, PDF y Word), cada una con su propio
        # historial independiente.
        _atajo("Ctrl+Z", self._deshacer_global, "Deshacer")
        _atajo("Ctrl+Y", self._rehacer_global, "Rehacer")
        _atajo("Ctrl+Shift+Z", self._rehacer_global)  # alternativa del mismo atajo -no se repite en la ventanita de ayuda

        # ------------------------------------------------------------
        # Atajos propios de la HOJA DE CÁLCULO (grupos "Filas y columnas"
        # y "Datos" de la cinta): antes solo eran accesibles con el mouse.
        # Todos revisan que la pestaña "hoja" esté activa antes de actuar
        # -igual que el resto de funciones de este método-, así que no
        # interfieren con Word ni con el visor de PDF.
        # ------------------------------------------------------------
        def _si_hoja(funcion):
            """Envuelve `funcion` para que solo se ejecute con la pestaña
            de hoja de cálculo visible -evita, por ejemplo, insertar una
            fila "fantasma" si el atajo se dispara estando en Word/PDF."""
            def _envoltura():
                if _pagina_actual() == "hoja":
                    funcion()
            return _envoltura

        # Insertar/eliminar fila o columna: mismo mnemónico que usa Excel
        # (+ inserta, - elimina), pero con Shift/Alt para no chocar con el
        # zoom que ya vive en Ctrl+Plus/Ctrl+Minus -Shift = fila, Alt =
        # columna, así el propio atajo recuerda qué eje afecta-.
        _atajo("Ctrl+Shift++", _si_hoja(self._insertar_fila), "Insertar fila (hoja)")
        _atajo("Ctrl+Shift+=", _si_hoja(self._insertar_fila))  # el "+" real suele venir con Shift -mismo atajo, no se repite en la ventanita de ayuda
        _atajo("Ctrl+Shift+-", _si_hoja(self._eliminar_fila), "Eliminar fila (hoja)")
        _atajo("Ctrl+Alt++", _si_hoja(self._insertar_columna), "Insertar columna (hoja)")
        _atajo("Ctrl+Alt+=", _si_hoja(self._insertar_columna))
        _atajo("Ctrl+Alt+-", _si_hoja(self._eliminar_columna), "Eliminar columna (hoja)")

        # Ordenar ascendente/descendente por la columna de la celda actual
        # -mismo comportamiento que los botones "AZ"/"ZA" de la cinta-.
        _atajo("Ctrl+Shift+A", _si_hoja(lambda: self._ordenar(Qt.SortOrder.AscendingOrder)), "Ordenar ascendente (hoja)")
        _atajo("Ctrl+Shift+D", _si_hoja(lambda: self._ordenar(Qt.SortOrder.DescendingOrder)), "Ordenar descendente (hoja)")

        # Autoajustar el ancho de las columnas -mismo botón "Autoajustar"
        # de la cinta-.
        _atajo("Ctrl+Shift+W", _si_hoja(self._autoajustar_columnas), "Autoajustar columnas (hoja)")

    def _mostrar_atajos_disponibles(self):
        """Devuelve [(secuencia, descripción), ...] con TODOS los atajos de
        este editor. Ahora es solo un envoltorio sobre atajos_de(self):
        cada atajo ya quedó anotado por registrar_atajo() al crearse (ver
        _crear_atajos_teclado), así que no hace falta mantener esta lista
        a mano por separado -antes se podía desincronizar de los atajos
        reales-. Se conserva el método por compatibilidad con quien ya lo
        llamaba. Lee de `self._contenedor_atajos_editor` (el widget real
        donde se registraron, ver _crear_atajos_teclado) y no de `self`,
        que ya no los tiene anotados."""
        widget = getattr(self, "_contenedor_atajos_editor", self)
        return atajos_de(widget)

    def _deshacer_global(self):
        """Deshacer -botón circular de la barra superior o Ctrl+Z-: aplica
        al modo que esté visible en ese momento (hoja/PDF/Word), cada uno
        con su propio historial independiente."""
        if self._cerrando:
            return
        pagina = {0: "vacio", 1: "hoja", 2: "pdf", 3: "word"}.get(self.stack.currentIndex())
        if pagina == "hoja":
            self._deshacer_hoja()
        elif pagina == "pdf":
            self._deshacer_pdf()
        elif pagina == "word":
            self.editor_word.undo()
        self._actualizar_botones_deshacer()

    def _rehacer_global(self):
        if self._cerrando:
            return
        pagina = {0: "vacio", 1: "hoja", 2: "pdf", 3: "word"}.get(self.stack.currentIndex())
        if pagina == "hoja":
            self._rehacer_hoja()
        elif pagina == "pdf":
            self._rehacer_pdf()
        elif pagina == "word":
            self.editor_word.redo()
        self._actualizar_botones_deshacer()

    def _actualizar_botones_deshacer(self):
        """Habilita/deshabilita los dos botones circulares según si hay algo
        que deshacer/rehacer EN EL MODO ACTUAL -se llama después de
        cualquier acción que modifique el historial (registrar, deshacer,
        rehacer, cambiar de pestaña, abrir un archivo nuevo...)."""
        if not hasattr(self, "btn_deshacer"):
            return
        pagina = {0: "vacio", 1: "hoja", 2: "pdf", 3: "word"}.get(self.stack.currentIndex())
        if pagina == "hoja":
            self.btn_deshacer.setEnabled(bool(self._pila_deshacer_hoja))
            self.btn_rehacer.setEnabled(bool(self._pila_rehacer_hoja))
        elif pagina == "pdf":
            self.btn_deshacer.setEnabled(bool(self._pila_deshacer_pdf))
            self.btn_rehacer.setEnabled(bool(self._pila_rehacer_pdf))
        elif pagina == "word":
            self.btn_deshacer.setEnabled(self.editor_word.document().isUndoAvailable())
            self.btn_rehacer.setEnabled(self.editor_word.document().isRedoAvailable())
        else:
            self.btn_deshacer.setEnabled(False)
            self.btn_rehacer.setEnabled(False)

    def _zoom_acercar_pagina_actual(self):
        pagina = {0: "vacio", 1: "hoja", 2: "pdf", 3: "word"}.get(self.stack.currentIndex())
        if pagina == "pdf":
            self._pdf_zoom(0.2)
        elif pagina == "hoja":
            self._zoom_hoja_cambiar(10)
        elif pagina == "word":
            self._word_zoom(20)

    def _zoom_alejar_pagina_actual(self):
        pagina = {0: "vacio", 1: "hoja", 2: "pdf", 3: "word"}.get(self.stack.currentIndex())
        if pagina == "pdf":
            self._pdf_zoom(-0.2)
        elif pagina == "hoja":
            self._zoom_hoja_cambiar(-10)
        elif pagina == "word":
            self._word_zoom(-20)

    def _zoom_restablecer_pagina_actual(self):
        pagina = {0: "vacio", 1: "hoja", 2: "pdf", 3: "word"}.get(self.stack.currentIndex())
        if pagina == "pdf":
            self._pdf_ajustar_zoom_al_ancho()
        elif pagina == "hoja":
            self._zoom_hoja_cambiar(100 - self._zoom_hoja)
        elif pagina == "word":
            self._word_ajustar_zoom_al_ancho()

    def _barra_desplazable(self, frame):
        """Envuelve una barra de herramientas (QFrame con muchos botones en fila)
        en un QScrollArea horizontal, con flechas "‹ ›" visibles a los lados
        -antes solo había una barrita de scroll delgada y fácil de pasar por
        alto, así que cuando la barra no cabía (ventana angosta, muchos
        botones) los últimos botones quedaban cortados sin que se notara que
        había más contenido con solo desplazarse-. Las flechas se habilitan/
        deshabilitan solas según si realmente hay más contenido hacia ese
        lado, y quedan ocultas del todo si todo cabe sin scroll."""
        contenedor = QScrollArea()
        # OJO tema oscuro: esta clase (QScrollArea) también la usa el visor
        # de PDF (self.scroll_pdf) para envolver CONTENIDO -que siempre debe
        # verse blanco/negro plano, nunca teñido-. Como el QSS no puede
        # distinguir "este QScrollArea sí es contenido, este otro no" sin
        # ayuda, aquí marcamos explícitamente que ESTA instancia envuelve
        # una barra de herramientas (cinta/ribbon), no contenido, para que
        # _css_editor() pueda darle el fondo de PANEL correspondiente al
        # modo claro/oscuro en vez de forzarle el blanco fijo del contenido
        # -que era justo lo que se veía "en blanco" de más en modo oscuro-.
        contenedor.setObjectName("ScrollBarraHerramientas")
        contenedor.setWidget(frame)
        contenedor.setWidgetResizable(False)
        contenedor.setFrameShape(QFrame.Shape.NoFrame)
        contenedor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        contenedor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contenedor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # OJO: en este momento (construcción de la UI) el frame TODAVÍA no
        # tiene aplicado el QSS del tema (eso pasa después, en actualizar_tema),
        # así que su sizeHint() aquí no incluye el padding/borde que le vamos a
        # añadir. Si fijáramos la altura ya mismo, quedaría un poco corta y el
        # texto de los botones/combos se vería cortado. Por eso solo damos un
        # valor de arranque razonable, y _recalcular_barras_desplazables()
        # -llamado desde actualizar_tema(), ya con el QSS puesto- la ajusta al
        # tamaño real.
        contenedor.setFixedHeight(frame.sizeHint().height() + 14)
        contenedor.setMinimumWidth(160)
        contenedor.horizontalScrollBar().setSingleStep(40)

        envoltura = QWidget()
        envoltura.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        fila = QHBoxLayout(envoltura)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(2)
        btn_izq = QToolButton()
        btn_izq.setText("‹")
        btn_izq.setToolTip("Ver los botones anteriores de esta barra")
        btn_izq.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_izq.setFixedWidth(20)
        btn_der = QToolButton()
        btn_der.setText("›")
        btn_der.setToolTip("Ver más botones de esta barra (hay más a la derecha)")
        btn_der.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_der.setFixedWidth(20)
        barra_scroll = contenedor.horizontalScrollBar()
        btn_izq.clicked.connect(lambda: barra_scroll.setValue(barra_scroll.value() - 120))
        btn_der.clicked.connect(lambda: barra_scroll.setValue(barra_scroll.value() + 120))

        def _actualizar_flechas(*_args):
            hay_overflow = barra_scroll.maximum() > 0
            btn_izq.setVisible(hay_overflow)
            btn_der.setVisible(hay_overflow)
            btn_izq.setEnabled(barra_scroll.value() > barra_scroll.minimum())
            btn_der.setEnabled(barra_scroll.value() < barra_scroll.maximum())

        barra_scroll.valueChanged.connect(_actualizar_flechas)
        barra_scroll.rangeChanged.connect(_actualizar_flechas)
        _actualizar_flechas()

        fila.addWidget(btn_izq)
        fila.addWidget(contenedor, 1)
        fila.addWidget(btn_der)
        self._barras_desplazables.append((contenedor, frame))
        return envoltura

    def _recalcular_barras_desplazables(self):
        """Vuelve a medir cada barra de herramientas envuelta por
        _barra_desplazable() ahora que ya tiene el QSS del tema puesto, para
        que la altura reservada sea la real (con su padding/borde) y no se
        corten ni el texto de los botones ni el de los combos."""
        for contenedor, frame in self._barras_desplazables:
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            frame.adjustSize()
            contenedor.setFixedHeight(frame.sizeHint().height() + 14)

    # ---------------- Helpers de diseño de la cinta de opciones ----------------
    def _aplicar_sombra(self, widget, blur=22, y=4, alpha=32):
        """Sombra suave (elevación tipo "tarjeta flotante") para que la
        cinta de opciones y la barra superior se despeguen visualmente del
        fondo en vez de verse pegadas/planas contra él."""
        efecto = QGraphicsDropShadowEffect(widget)
        efecto.setBlurRadius(blur)
        efecto.setOffset(0, y)
        efecto.setColor(QColor(15, 23, 42, alpha))
        widget.setGraphicsEffect(efecto)

    def _separador_ribbon(self):
        """Línea vertical delgada que marca dónde termina un grupo de la
        cinta de opciones y empieza el siguiente -mismo lenguaje visual que
        usa Word/Excel real para separar "Fuente" de "Alineación", etc.-.
        Antes la línea se pegaba directo a los botones de ambos lados (sin
        margen), así que dos grupos consecutivos como Fuente/Alinear se
        veían fundidos en una sola caja. Ahora va envuelta en un contenedor
        con margen horizontal para que quede un respiro real a cada lado."""
        contenedor = QWidget()
        contenedor.setObjectName("ContenedorSeparadorRibbon")
        lay = QHBoxLayout(contenedor)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(0)
        linea = QFrame()
        linea.setObjectName("SeparadorRibbon")
        linea.setFrameShape(QFrame.Shape.VLine)
        linea.setFixedWidth(1)
        lay.addWidget(linea)
        return contenedor

    def _crear_grupo_ribbon(self, titulo):
        """Crea un "grupo" de la cinta de opciones: una fila de controles
        arriba y una etiqueta pequeña centrada debajo (p. ej. "FUENTE",
        "ALINEAR"), igual que los grupos de Word/Excel. Antes todos los
        botones de la barra iban sueltos uno tras otro -sin más separación
        que un hueco en blanco cada tanto-, lo que hacía difícil distinguir
        de un vistazo qué botones estaban relacionados entre sí. Devuelve
        (widget_del_grupo, layout_horizontal_donde_agregar_los_controles)."""
        contenedor = QWidget()
        contenedor.setObjectName("GrupoRibbon")
        v = QVBoxLayout(contenedor)
        v.setContentsMargins(4, 2, 4, 0)
        v.setSpacing(2)
        fila = QHBoxLayout()
        fila.setSpacing(5)
        v.addLayout(fila, 1)
        etiqueta = QLabel(titulo.upper())
        etiqueta.setObjectName("EtiquetaGrupoRibbon")
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(etiqueta)
        return contenedor, fila

    def _crear_pill_zoom(self, valor_inicial, al_restar, al_sumar, al_fijar, tooltip_campo):
        """Control de zoom "−  100%  +" compacto, con los tres controles
        compartiendo un único borde redondeado en vez de verse como tres
        piezas sueltas flotando en la barra. Devuelve (widget, campo_texto)
        -el campo se guarda tal cual lo esperaba el resto del código
        (self.in_zoom_hoja / self.in_zoom_pdf / self.in_zoom_word)-."""
        pill = QWidget()
        pill.setObjectName("PillZoom")
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(2, 2, 2, 2)
        pl.setSpacing(0)

        btn_menos = QToolButton()
        btn_menos.setText("−")
        btn_menos.setToolTip("Alejar (Ctrl+−)")
        btn_menos.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menos.setFixedSize(26, 26)
        btn_menos.clicked.connect(al_restar)
        pl.addWidget(btn_menos)

        campo = QLineEdit(valor_inicial)
        campo.setFixedWidth(46)
        campo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        campo.setToolTip(tooltip_campo)
        campo.returnPressed.connect(lambda: al_fijar(campo.text()))
        campo.editingFinished.connect(lambda: al_fijar(campo.text()))
        pl.addWidget(campo)

        btn_mas = QToolButton()
        btn_mas.setText("+")
        btn_mas.setToolTip("Acercar (Ctrl++)")
        btn_mas.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_mas.setFixedSize(26, 26)
        btn_mas.clicked.connect(al_sumar)
        pl.addWidget(btn_mas)

        return pill, campo

    def _pagina_vacia(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addStretch()
        icono = QLabel("")
        icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from src.nucleo.iconos_emoji import pixmap_emoji
        icono.setPixmap(pixmap_emoji("📄", 46))
        l.addWidget(icono)
        texto = QLabel("Abre un PDF, Excel, Word o CSV para previsualizarlo y editarlo aquí.\n"
                       "También puedes usar los reportes que acabas de exportar desde\n"
                       "las otras pestañas: aparecerán en «Archivos recientes».")
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto.setObjectName("DescModulo")
        texto.setWordWrap(True)
        l.addWidget(texto)
        l.addStretch()
        return w

    # ---------------- Página de hoja de cálculo (CSV / XLSX) ----------------
    def _pagina_hoja_calculo(self):
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        l = QVBoxLayout(w)
        l.setSpacing(8)

        fila_hojas = QHBoxLayout()
        self.lbl_hojas = QLabel("Hoja:")
        self.combo_hojas = QComboBox()
        self.combo_hojas.currentTextChanged.connect(self._cambiar_hoja)
        conectar_tooltip_seleccion(self.combo_hojas, "Hoja del archivo Excel")
        fila_hojas.addWidget(self.lbl_hojas)
        fila_hojas.addWidget(self.combo_hojas)
        self.btn_info_excel = QToolButton()
        self.btn_info_excel.setText("ⓘ")
        self.btn_info_excel.setToolTip("Qué se puede y qué no se puede hacer aquí con un Excel")
        self.btn_info_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_info_excel.setStyleSheet(
            "QToolButton { border-radius: 10px; min-width: 20px; max-width: 20px; min-height: 20px; "
            "max-height: 20px; font-weight: bold; color: #2563EB; border: 1px solid #93C5FD; "
            "background-color: rgba(37, 99, 235, 25); } "
            "QToolButton:hover { background-color: rgba(37, 99, 235, 55); }")
        self.btn_info_excel.clicked.connect(self._mostrar_info_limitaciones_excel)
        self.btn_info_excel.setVisible(False)
        fila_hojas.addWidget(self.btn_info_excel)
        fila_hojas.addStretch()
        self.lbl_celdas = QLabel("")
        self.lbl_celdas.setObjectName("DescModulo")
        fila_hojas.addWidget(self.lbl_celdas)
        l.addLayout(fila_hojas)

        toolbar = QFrame()
        toolbar.setObjectName("TarjetaFiltros")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 8, 12, 6)
        tb.setSpacing(6)

        # ============================================================
        # CINTA DE OPCIONES - reescrita de forma simple y robusta:
        # - Cada botón cuadrado usa exactamente el mismo tamaño fijo
        #   (ancho y alto), así ninguno se ve más chico/grande que sus
        #   vecinos ni se encoge a un puntito.
        # - El combo de fuente se autoajusta a su propio contenido
        #   (AdjustToContents) en vez de depender de un ancho fijo
        #   adivinado a mano, que se rompe apenas cambia el tema o el
        #   tamaño de letra.
        # - Cada grupo se dimensiona solo a partir de lo que realmente
        #   contiene (sin anchos mínimos artificiales), así la etiqueta
        #   ("FUENTE", "ALINEAR", etc.) queda centrada bajo sus propios
        #   controles y no se confunde con el grupo vecino.
        # ============================================================
        TAM_BOTON_CUADRADO = 32

        def _boton(fila, texto, tooltip, callback, ancho=None):
            btn = QToolButton()
            btn.setText(texto)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(callback)
            btn.setMinimumWidth(ancho if ancho else TAM_BOTON_CUADRADO)
            btn.setMinimumHeight(TAM_BOTON_CUADRADO)
            fila.addWidget(btn)
            return btn

        # Grupo "Filas y columnas": iconos vectoriales propios
        # (EMOJI_*_FILA/COLUMNA) con cuadrícula + disco verde "+"/rojo "−",
        # en vez de los botones de texto "Fila"/"Columna" indistinguibles.
        g_filas, f_filas = self._crear_grupo_ribbon("Filas y columnas")
        _b_ins_fila = _boton(f_filas, "", "Insertar fila debajo de la selección", self._insertar_fila)
        _b_ins_fila.setIcon(icono_emoji(EMOJI_INSERTAR_FILA)); _b_ins_fila.setIconSize(_QSize_emoji(16, 16))
        _b_eli_fila = _boton(f_filas, "", "Eliminar fila(s) seleccionada(s)", self._eliminar_fila)
        _b_eli_fila.setIcon(icono_emoji(EMOJI_ELIMINAR_FILA)); _b_eli_fila.setIconSize(_QSize_emoji(16, 16))
        _b_ins_col = _boton(f_filas, "", "Insertar columna a la derecha de la selección", self._insertar_columna)
        _b_ins_col.setIcon(icono_emoji(EMOJI_INSERTAR_COLUMNA)); _b_ins_col.setIconSize(_QSize_emoji(16, 16))
        _b_eli_col = _boton(f_filas, "", "Eliminar columna(s) seleccionada(s)", self._eliminar_columna)
        _b_eli_col.setIcon(icono_emoji(EMOJI_ELIMINAR_COLUMNA)); _b_eli_col.setIconSize(_QSize_emoji(16, 16))
        tb.addWidget(g_filas)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Fuente": tipografía, negrita/cursiva/subrayado, relleno y
        # color de texto.
        g_fuente, f_fuente = self._crear_grupo_ribbon("Fuente")
        self.combo_fuente_hoja = QComboBox()
        self.combo_fuente_hoja.addItems(FUENTES_DISPONIBLES)
        self.combo_fuente_hoja.setEditable(False)
        # Sin ancho máximo fijo: el combo se autoajusta a su propio
        # contenido (el nombre de fuente más largo de la lista), así nunca
        # trunca el texto sea cual sea el tema o el tamaño de letra activo.
        self.combo_fuente_hoja.setMinimumWidth(140)
        self.combo_fuente_hoja.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_fuente_hoja.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.combo_fuente_hoja.activated.connect(self._cambiar_fuente_hoja)
        conectar_tooltip_seleccion(self.combo_fuente_hoja, "Tipografía de las celdas seleccionadas")
        f_fuente.addWidget(self.combo_fuente_hoja)
        f_fuente.addSpacing(8)
        # NOTA: se marca la tipografía del GLIFO del botón (B/I/U/Aa) con
        # QFont, no con un setStyleSheet() local -eso reemplazaría por
        # completo el QSS de la cinta para ESE botón puntual (Qt no
        # combina el stylesheet propio de un widget con el heredado del
        # padre), dejándolo sin el relleno/radio/resaltado del resto de
        # la barra y con el resaltado nativo de Qt al pasar el cursor,
        # que es justo lo que tapaba el texto.
        self.btn_negrita = _boton(f_fuente, "B", "Negrita", self._alternar_negrita)
        _f = self.btn_negrita.font(); _f.setBold(True); self.btn_negrita.setFont(_f)
        self.btn_cursiva = _boton(f_fuente, "I", "Cursiva", self._alternar_cursiva)
        _f = self.btn_cursiva.font(); _f.setItalic(True); self.btn_cursiva.setFont(_f)
        self.btn_subrayado = _boton(f_fuente, "U", "Subrayado", self._alternar_subrayado)
        _f = self.btn_subrayado.font(); _f.setUnderline(True); self.btn_subrayado.setFont(_f)
        f_fuente.addSpacing(8)
        _b_relleno = _boton(f_fuente, "", "Color de relleno de las celdas seleccionadas",
                             self._elegir_color_relleno)
        _b_relleno.setIcon(icono_emoji("🎨")); _b_relleno.setIconSize(_QSize_emoji(16, 16))
        _b_color_texto = _boton(f_fuente, "Aa", "Color de la letra de las celdas seleccionadas",
                                 self._elegir_color_texto)
        _f = _b_color_texto.font(); _f.setBold(True); _b_color_texto.setFont(_f)
        tb.addWidget(g_fuente)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Alinear"
        g_alinear, f_alinear = self._crear_grupo_ribbon("Alinear")
        _b_alinear_izq = _boton(f_alinear, "", "Alinear a la izquierda", lambda: self._alinear(Qt.AlignmentFlag.AlignLeft))
        _b_alinear_izq.setIcon(icono_emoji(EMOJI_ALINEAR_IZQUIERDA)); _b_alinear_izq.setIconSize(_QSize_emoji(16, 16))
        _b_alinear_centro = _boton(f_alinear, "", "Centrar", lambda: self._alinear(Qt.AlignmentFlag.AlignHCenter))
        _b_alinear_centro.setIcon(icono_emoji(EMOJI_ALINEAR_CENTRO)); _b_alinear_centro.setIconSize(_QSize_emoji(16, 16))
        _b_alinear_der = _boton(f_alinear, "", "Alinear a la derecha", lambda: self._alinear(Qt.AlignmentFlag.AlignRight))
        _b_alinear_der.setIcon(icono_emoji(EMOJI_ALINEAR_DERECHA)); _b_alinear_der.setIconSize(_QSize_emoji(16, 16))
        tb.addWidget(g_alinear)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Datos"
        g_datos, f_datos = self._crear_grupo_ribbon("Datos")
        _boton(f_datos, "AZ", "Ordenar ascendente por la columna seleccionada", lambda: self._ordenar(Qt.SortOrder.AscendingOrder))
        _boton(f_datos, "ZA", "Ordenar descendente por la columna seleccionada", lambda: self._ordenar(Qt.SortOrder.DescendingOrder))
        _boton(f_datos, "Autoajustar", "Autoajustar el ancho de las columnas", self._autoajustar_columnas)
        tb.addWidget(g_datos)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Calcular": operaciones rápidas -tipo "Autosuma" de Excel-:
        # se selecciona un rango de celdas y, sin escribir ninguna fórmula a
        # mano, se inserta el resultado (como fórmula real, recalculable)
        # justo debajo/al lado de la selección.
        g_calcular, f_calcular = self._crear_grupo_ribbon("Calcular")
        btn_operacion = QToolButton()
        btn_operacion.setText("∑ Operación")
        btn_operacion.setToolTip("Selecciona un rango de celdas y aplica una operación automáticamente")
        btn_operacion.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_operacion.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_operacion = QMenu(btn_operacion)
        for etiqueta, funcion_excel in (
            ("Sumar (+)", "SUMA"), ("Multiplicar (×)", "PRODUCTO"),
            ("Promedio", "PROMEDIO"), ("Mínimo", "MIN"), ("Máximo", "MAX"),
            ("Contar números", "CONTAR"), ("Contar no vacías", "CONTARA"),
        ):
            accion = menu_operacion.addAction(etiqueta)
            accion.triggered.connect(lambda _chk=False, f=funcion_excel: self._insertar_operacion_rapida(f))
        menu_operacion.addSeparator()
        for etiqueta, operador in (("Restar (−)", "-"), ("Dividir (÷)", "/")):
            accion = menu_operacion.addAction(etiqueta)
            accion.triggered.connect(lambda _chk=False, op=operador: self._insertar_operacion_encadenada(op))
        btn_operacion.setMenu(menu_operacion)
        f_calcular.addWidget(btn_operacion)
        tb.addWidget(g_calcular)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Insertar"
        g_insertar, f_insertar = self._crear_grupo_ribbon("Insertar")
        _boton(f_insertar, "Imagen", "Insertar una imagen en la celda seleccionada", self._insertar_imagen_hoja)
        _boton(f_insertar, "Enlace", "Insertar o editar un hipervínculo en la celda seleccionada", lambda: self._hoja_insertar_enlace())
        _boton(f_insertar, "Gráfico", "Crear un gráfico nativo de Excel a partir de los datos seleccionados", self._insertar_grafico_hoja)
        _b_cuadro = _boton(f_insertar, "Cuadro de texto", "Insertar un cuadro de texto (celda con borde y relleno) en la posición seleccionada", self._insertar_cuadro_texto_hoja)
        _b_cuadro.setIcon(icono_emoji(EMOJI_CUADRO_TEXTO)); _b_cuadro.setIconSize(_QSize_emoji(16, 16))
        tb.addWidget(g_insertar)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Vista": zoom en píldora compacta
        g_vista, f_vista = self._crear_grupo_ribbon("Vista")
        pill_zoom, self.in_zoom_hoja = self._crear_pill_zoom(
            "100%",
            lambda: self._zoom_hoja_cambiar(-10),
            lambda: self._zoom_hoja_cambiar(10),
            self._zoom_hoja_set,
            "Escribe el porcentaje de zoom (10%–400%) y pulsa Enter para aplicarlo",
        )
        f_vista.addWidget(pill_zoom)
        tb.addWidget(g_vista)

        tb.addStretch()
        l.addWidget(self._barra_desplazable(toolbar))

        fila_buscar = QHBoxLayout()
        self.in_buscar_celda = QLineEdit()
        limitar_campo_texto(self.in_buscar_celda, 150)
        self.in_buscar_celda.setPlaceholderText("Buscar en la hoja…")
        fila_buscar.addWidget(self.in_buscar_celda, 1)
        self.in_reemplazar_celda = QLineEdit()
        limitar_campo_texto(self.in_reemplazar_celda, 300)
        self.in_reemplazar_celda.setPlaceholderText("Reemplazar por…")
        fila_buscar.addWidget(self.in_reemplazar_celda, 1)
        btn_buscar = QPushButton("Buscar")
        btn_buscar.setIcon(icono_emoji("🔍"))
        btn_buscar.setIconSize(_QSize_emoji(16, 16))
        btn_buscar.clicked.connect(self._buscar_en_hoja)
        fila_buscar.addWidget(btn_buscar)
        btn_reemplazar = QPushButton("Reemplazar todo")
        btn_reemplazar.setIcon(icono_emoji("🔍"))
        btn_reemplazar.setIconSize(_QSize_emoji(16, 16))
        btn_reemplazar.clicked.connect(self._reemplazar_en_hoja)
        fila_buscar.addWidget(btn_reemplazar)
        l.addLayout(fila_buscar)

        self.tabla_editor = QTableWidget(0, 0)
        aplicar_estructura_tabla(self.tabla_editor)
        self.tabla_editor.setAlternatingRowColors(True)
        # Delegado propio: al editar una celda muestra la fórmula/valor crudo
        # (no el resultado ya calculado) -ver _DelegadoHojaCalculo.
        self.tabla_editor.setItemDelegate(_DelegadoHojaCalculo(self.tabla_editor, self, self.tabla_editor))
        self.tabla_editor.itemChanged.connect(self._on_celda_editada)
        # Permite ARRASTRAR con el mouse un "cuadro de texto" (una celda
        # normal marcada con ROL_ES_CUADRO_TEXTO, no un widget aparte como
        # las imágenes) hacia otra celda -ver eventFilter más abajo.
        self.tabla_editor.setMouseTracking(True)
        self.tabla_editor.viewport().installEventFilter(self)
        self.tabla_editor.installEventFilter(self)
        self._arrastre_cuadro_texto_origen = None
        # Manija de relleno (la del cuadradito, ver _ManijaRelleno): se
        # reposiciona sola cada vez que cambia la selección o se hace scroll.
        self._manija_relleno = _ManijaRelleno(self, self.tabla_editor.viewport())
        self._relleno_origen = None
        self._relleno_fila_hasta = None
        self._arrastrando_relleno = False
        self._portapapeles_hoja = None
        self._pila_deshacer_hoja = []
        self._pila_rehacer_hoja = []
        self.tabla_editor.itemSelectionChanged.connect(self._actualizar_manija_relleno)
        self.tabla_editor.itemSelectionChanged.connect(self._sincronizar_combo_fuente_hoja)
        self.tabla_editor.horizontalScrollBar().valueChanged.connect(self._actualizar_manija_relleno)
        self.tabla_editor.verticalScrollBar().valueChanged.connect(self._actualizar_manija_relleno)
        # Menú contextual (clic derecho): cortar/copiar/pegar/eliminar/etc.
        self.tabla_editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla_editor.customContextMenuRequested.connect(self._mostrar_menu_contextual_hoja)
        # Filas un poco más altas: el recuadro que aparece al hacer doble clic
        # para escribir en una celda (el editor interno de la tabla) trae su
        # propio borde y relleno, y con la altura de fila por defecto (muy
        # justa) ese recuadro no cabía entero y se veía cortado/entrecortado.
        self.tabla_editor.verticalHeader().setDefaultSectionSize(32)
        self.tabla_editor.verticalHeader().setMinimumSectionSize(28)
        # Política de tamaño expansiva + una altura mínima real para que la
        # tabla ocupe el espacio disponible de la pestaña (en vez de encogerse
        # a un puñado de filas y dejar un hueco en blanco debajo). Con esto la
        # propia tabla muestra sus barras de desplazamiento y responde a la
        # rueda del ratón con normalidad, sin depender de mover "la cámara"
        # con las flechas del teclado.
        self.tabla_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabla_editor.setMinimumHeight(380)
        # Desplazamiento por píxel (no por celda completa) en ambas
        # direcciones: la rueda del ratón y las barras se sienten continuas
        # en vez de saltar de celda en celda.
        self.tabla_editor.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabla_editor.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabla_editor.horizontalScrollBar().setSingleStep(24)
        self.tabla_editor.verticalScrollBar().setSingleStep(24)
        l.addWidget(self.tabla_editor, 1)

        fila_opciones_guardado = QHBoxLayout()
        self.chk_congelar_encabezado = QCheckBox("Congelar la primera fila al guardar (Excel)")
        self.chk_congelar_encabezado.setChecked(True)
        fila_opciones_guardado.addWidget(self.chk_congelar_encabezado)
        self.chk_autofiltro = QCheckBox("Activar autofiltro al guardar (Excel)")
        self.chk_autofiltro.setChecked(True)
        fila_opciones_guardado.addWidget(self.chk_autofiltro)
        fila_opciones_guardado.addStretch()
        l.addLayout(fila_opciones_guardado)

        return w

    # ---------------- Página de PDF ----------------
    def _pagina_pdf(self):
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        l = QVBoxLayout(w)
        l.setSpacing(8)

        toolbar = QFrame()
        toolbar.setObjectName("TarjetaFiltros")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 8, 12, 6)
        tb.setSpacing(6)

        def _boton(fila, texto, tooltip, callback):
            btn = QToolButton()
            btn.setText(texto)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(callback)
            fila.addWidget(btn)
            return btn

        # Grupo "Navegación"
        g_nav, f_nav = self._crear_grupo_ribbon("Navegación")
        _boton(f_nav, "⏮", "Primera página", self._pdf_primera)
        _boton(f_nav, "◀", "Página anterior", self._pdf_anterior)
        self.spin_pagina_pdf = QSpinBox()
        self.spin_pagina_pdf.setMinimum(1)
        self.spin_pagina_pdf.valueChanged.connect(self._pdf_ir_a_pagina)
        f_nav.addWidget(self.spin_pagina_pdf)
        self.lbl_total_paginas = QLabel("/ 0")
        f_nav.addWidget(self.lbl_total_paginas)
        _boton(f_nav, "▶", "Página siguiente", self._pdf_siguiente)
        _boton(f_nav, "⏭", "Última página", self._pdf_ultima)
        tb.addWidget(g_nav)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Vista": zoom en píldora compacta
        g_vista, f_vista = self._crear_grupo_ribbon("Vista")
        pill_zoom_pdf, self.in_zoom_pdf = self._crear_pill_zoom(
            "140%",
            lambda: self._pdf_zoom(-0.2),
            lambda: self._pdf_zoom(0.2),
            self._pdf_zoom_set,
            "Escribe el porcentaje de zoom (10%–400%) y pulsa Enter para aplicarlo",
        )
        f_vista.addWidget(pill_zoom_pdf)
        tb.addWidget(g_vista)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Página"
        g_pagina, f_pagina = self._crear_grupo_ribbon("Página")
        _boton(f_pagina, "Rotar", "Rotar la página actual 90°", self._pdf_rotar)
        _boton(f_pagina, "Eliminar", "Eliminar la página actual", self._pdf_eliminar_pagina)
        _boton(f_pagina, "Insertar", "Insertar una página en blanco después de esta", self._pdf_insertar_pagina)
        _boton(f_pagina, "Editar página", "Escribir/editar el contenido de la página actual con texto con formato "
                                     "(sirve tanto para páginas en blanco como para reemplazar el contenido de una existente)",
               self._pdf_editar_pagina_actual)
        btn_mover_arriba = _boton(f_pagina, "", "Mover la página actual hacia arriba", self._pdf_mover_arriba)
        btn_mover_arriba.setIcon(icono_emoji("↑")); btn_mover_arriba.setIconSize(_QSize_emoji(16, 16))
        btn_mover_abajo = _boton(f_pagina, "", "Mover la página actual hacia abajo", self._pdf_mover_abajo)
        btn_mover_abajo.setIcon(icono_emoji("↓")); btn_mover_abajo.setIconSize(_QSize_emoji(16, 16))
        tb.addWidget(g_pagina)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Seleccionar"
        g_sel, f_sel = self._crear_grupo_ribbon("Seleccionar")
        _boton(f_sel, "Copiar selección", "Copia al portapapeles el texto que hayas seleccionado arrastrando "
                                       "el mouse sobre la página (como en Edge)", self._pdf_copiar_seleccion)
        _boton(f_sel, "Enlace", "Convierte el texto seleccionado (arrastrando el mouse) en un hipervínculo",
               self._pdf_insertar_enlace)
        tb.addWidget(g_sel)

        tb.addStretch()
        l.addWidget(self._barra_desplazable(toolbar))

        toolbar2 = QFrame()
        toolbar2.setObjectName("TarjetaFiltros")
        tb2 = QHBoxLayout(toolbar2)
        tb2.setContentsMargins(12, 8, 12, 6)
        tb2.setSpacing(6)
        # A diferencia de los demás grupos de la cinta, esta barra tiene un
        # único grupo -no tiene sentido repetir el patrón "fila de botones +
        # etiqueta pequeña centrada debajo", que aquí solo desperdiciaba
        # todo el espacio vacío a la derecha de los botones. En su lugar, el
        # título va DENTRO de la misma fila, a la derecha de los botones
        # (como un rótulo de sección), en vez de como pie de página.
        g_extra = QWidget()
        f_extra = QHBoxLayout(g_extra)
        f_extra.setContentsMargins(0, 0, 0, 0)
        f_extra.setSpacing(5)
        btn_marca = QToolButton()
        btn_marca.setText("Marca de agua…")
        btn_marca.setToolTip("Insertar una marca de agua de texto en la página actual o en todas las páginas del PDF")
        btn_marca.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_marca.clicked.connect(self._pdf_marca_de_agua)
        f_extra.addWidget(btn_marca)
        btn_combinar = QToolButton()
        btn_combinar.setText("Combinar con otro PDF…")
        btn_combinar.setToolTip("Agregar las páginas de otro archivo PDF al final de este documento")
        btn_combinar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_combinar.clicked.connect(self._pdf_combinar)
        f_extra.addWidget(btn_combinar)
        btn_exportar_img = QToolButton()
        btn_exportar_img.setText("Exportar página como imagen…")
        btn_exportar_img.setToolTip("Guardar la página actual del PDF como imagen PNG de alta resolución")
        btn_exportar_img.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exportar_img.clicked.connect(self._pdf_exportar_imagen)
        f_extra.addWidget(btn_exportar_img)
        self.btn_texto_pdf = QToolButton()
        self.btn_texto_pdf.setText("Ver texto de la página")
        self.btn_texto_pdf.setToolTip("Mostrar/ocultar el panel lateral con el texto extraíble de la página actual "
                                      "(útil para copiar párrafos de texto del PDF)")
        self.btn_texto_pdf.setCheckable(True)
        self.btn_texto_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_texto_pdf.toggled.connect(self._pdf_alternar_panel_texto)
        f_extra.addWidget(self.btn_texto_pdf)
        tb2.addWidget(g_extra)
        etiqueta_extra = QLabel("HERRAMIENTAS DE DOCUMENTO")
        etiqueta_extra.setObjectName("EtiquetaGrupoRibbon")
        tb2.addWidget(etiqueta_extra)
        tb2.addStretch()
        l.addWidget(self._barra_desplazable(toolbar2))

        cuerpo = QHBoxLayout()
        self.scroll_pdf = QScrollArea()
        # Este sí es CONTENIDO (el lienzo de la página de PDF), así que se
        # marca aparte de "ScrollBarraHerramientas" para que _css_editor()
        # lo deje siempre blanco/negro plano, sin importar el modo del
        # editor -ver el comentario en _barra_desplazable().
        self.scroll_pdf.setObjectName("ScrollContenidoPDF")
        self.scroll_pdf.setWidgetResizable(True)
        self.scroll_pdf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_pdf.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_pdf.setMinimumHeight(380)
        self.scroll_pdf.verticalScrollBar().setSingleStep(24)
        self.scroll_pdf.horizontalScrollBar().setSingleStep(24)
        # Vista "de libro": en vez de un único QLabel con la página actual (que
        # obligaba a usar los botones ◀/▶ para avanzar), el documento entero se
        # renderiza como una columna continua de páginas dentro de este scroll.
        # Así, deslizar la barra (o hacer scroll con la rueda/trackpad) pasa de
        # página de forma natural, igual que en un lector de PDF o en Word.
        self._labels_paginas_pdf = []
        self._render_en_progreso = False
        self.cont_paginas_pdf = QWidget()
        self._layout_paginas_pdf = QVBoxLayout(self.cont_paginas_pdf)
        self._layout_paginas_pdf.setSpacing(18)
        self._layout_paginas_pdf.setContentsMargins(10, 16, 10, 16)
        self.scroll_pdf.setWidget(self.cont_paginas_pdf)
        self.scroll_pdf.verticalScrollBar().valueChanged.connect(self._pdf_pagina_por_scroll)
        cuerpo.addWidget(self.scroll_pdf, 3)

        self.panel_texto_pdf = QPlainTextEdit()
        limitar_campo_texto(self.panel_texto_pdf, 5000)
        self.panel_texto_pdf.setReadOnly(True)
        # Aunque es de solo lectura (no se edita el PDF desde aquí -para eso
        # está "✏ Editar página"-), el texto se puede seleccionar y copiar
        # con normalidad, igual que en el visor de un navegador.
        self.panel_texto_pdf.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.panel_texto_pdf.setPlaceholderText("El texto extraído de la página aparecerá aquí…")
        self.panel_texto_pdf.setVisible(False)
        self.panel_texto_pdf.setMaximumWidth(320)
        panel_lateral = QVBoxLayout()
        panel_lateral.addWidget(self.panel_texto_pdf, 1)
        self.btn_copiar_texto_pdf = QPushButton("Copiar todo el texto")
        self.btn_copiar_texto_pdf.setIcon(icono_emoji("📋"))
        self.btn_copiar_texto_pdf.setIconSize(_QSize_emoji(16, 16))
        self.btn_copiar_texto_pdf.clicked.connect(lambda: (self.panel_texto_pdf.selectAll(), self.panel_texto_pdf.copy()))
        self.btn_copiar_texto_pdf.setVisible(False)
        panel_lateral.addWidget(self.btn_copiar_texto_pdf)
        cuerpo.addLayout(panel_lateral, 1)

        l.addLayout(cuerpo, 1)
        return w

    # ---------------- Página de Word (.docx) ----------------
    def _pagina_word(self):
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        l = QVBoxLayout(w)
        l.setSpacing(8)

        toolbar = QFrame()
        toolbar.setObjectName("TarjetaFiltros")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 8, 12, 6)
        tb.setSpacing(6)

        def _boton(fila, texto, tooltip, callback, checable=False):
            btn = QToolButton()
            btn.setText(texto)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(checable)
            if checable:
                btn.toggled.connect(callback)
            else:
                btn.clicked.connect(callback)
            fila.addWidget(btn)
            return btn

        # Grupo "Estilo": los tres combos (estilo de párrafo, tipografía,
        # tamaño) se veían pegados entre sí y con el texto pegado al borde
        # -antes solo tenían el padding genérico del tema (3px 10px) y muy
        # poco aire entre uno y otro-. Se les da más "breathing room": más
        # separación horizontal entre combos y más padding interno para
        # cada uno, aunque eso implique que este grupo (y por lo tanto la
        # cinta completa) ocupe más ancho -la barra ya es desplazable
        # (ver _barra_desplazable más abajo), así que no hay problema en
        # que crezca-.
        _ESTILO_PADDING = "padding: 6px 16px;"
        g_estilo, f_estilo = self._crear_grupo_ribbon("Estilo")
        f_estilo.setSpacing(22)
        self.combo_estilo_word = QComboBox()
        self.combo_estilo_word.addItems(["Normal", "Título 1", "Título 2", "Título 3"])
        self.combo_estilo_word.setMinimumWidth(120)
        self.combo_estilo_word.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_estilo_word.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.combo_estilo_word.setStyleSheet(_ESTILO_PADDING)
        self.combo_estilo_word.activated.connect(self._word_aplicar_estilo)
        conectar_tooltip_seleccion(self.combo_estilo_word, "Estilo del párrafo donde está el cursor")
        f_estilo.addWidget(self.combo_estilo_word)
        f_estilo.addSpacing(10)
        self.combo_fuente_word = QComboBox()
        self.combo_fuente_word.addItems(FUENTES_DISPONIBLES)
        self.combo_fuente_word.setEditable(False)
        self.combo_fuente_word.setMinimumWidth(130)
        self.combo_fuente_word.setMaximumWidth(170)
        self.combo_fuente_word.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.combo_fuente_word.setStyleSheet(_ESTILO_PADDING)
        self.combo_fuente_word.activated.connect(self._word_cambiar_fuente)
        conectar_tooltip_seleccion(self.combo_fuente_word, "Tipografía del texto seleccionado")
        f_estilo.addWidget(self.combo_fuente_word)
        f_estilo.addSpacing(18)
        self.combo_tamano_word = QComboBox()
        self.combo_tamano_word.addItems(["8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "32"])
        self.combo_tamano_word.setCurrentText("11")
        self.combo_tamano_word.setEditable(False)
        self.combo_tamano_word.setMinimumWidth(70)
        self.combo_tamano_word.setStyleSheet(_ESTILO_PADDING)
        conectar_tooltip_seleccion(self.combo_tamano_word, "Tamaño de letra")
        self.combo_tamano_word.activated.connect(self._word_cambiar_tamano)
        f_estilo.addWidget(self.combo_tamano_word)
        tb.addWidget(g_estilo)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Formato"
        g_formato, f_formato = self._crear_grupo_ribbon("Formato")
        # NOTA: igual que en la hoja de cálculo, la tipografía del glifo
        # (B/I/U) se marca con QFont y NO con setStyleSheet() local -un
        # QSS propio en el botón anula por completo el de la cinta para
        # ese botón (relleno, radio, color de fondo al pasar el cursor y
        # al estar marcado/"checked"), dejándolo con el resaltado nativo
        # de Qt, que es lo que se veía "raro" y tapaba el texto en los
        # modos PDF y Word.
        self.btn_negrita_word = _boton(f_formato, "B", "Negrita", self._word_alternar_negrita, checable=True)
        self.btn_negrita_word.setMinimumWidth(30)
        _f = self.btn_negrita_word.font(); _f.setBold(True); self.btn_negrita_word.setFont(_f)
        self.btn_cursiva_word = _boton(f_formato, "I", "Cursiva", self._word_alternar_cursiva, checable=True)
        self.btn_cursiva_word.setMinimumWidth(30)
        _f = self.btn_cursiva_word.font(); _f.setItalic(True); self.btn_cursiva_word.setFont(_f)
        self.btn_subrayado_word = _boton(f_formato, "U", "Subrayado", self._word_alternar_subrayado, checable=True)
        self.btn_subrayado_word.setMinimumWidth(30)
        _f = self.btn_subrayado_word.font(); _f.setUnderline(True); self.btn_subrayado_word.setFont(_f)
        _boton(f_formato, "Texto", "Color del texto", self._word_elegir_color_texto)
        _boton(f_formato, "Resaltado", "Color de resaltado del texto seleccionado", self._word_elegir_color_resaltado)
        tb.addWidget(g_formato)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Alinear"
        # Los 4 botones son mutuamente excluyentes -exactamente como en Word-:
        # al elegir una alineación, la anterior se desmarca sola. Para lograrlo
        # se agrupan en un QButtonGroup exclusivo y el callback solo actúa
        # cuando el botón pasa a estado "marcado" (evita que el des-marcado
        # del botón anterior dispare de nuevo su propia alineación y "pise"
        # la que se acaba de elegir, que era la causa de que la alineación
        # vieja pareciera "mantenerse").
        g_alinear_w, f_alinear_w = self._crear_grupo_ribbon("Alinear")
        self.btn_alinear_izq_word = _boton(f_alinear_w, "", "Alinear a la izquierda", lambda marcado: self._word_alinear(Qt.AlignmentFlag.AlignLeft) if marcado else None, checable=True)
        self.btn_alinear_izq_word.setIcon(icono_emoji(EMOJI_ALINEAR_IZQUIERDA)); self.btn_alinear_izq_word.setIconSize(_QSize_emoji(16, 16))
        self.btn_alinear_centro_word = _boton(f_alinear_w, "", "Centrar", lambda marcado: self._word_alinear(Qt.AlignmentFlag.AlignHCenter) if marcado else None, checable=True)
        self.btn_alinear_centro_word.setIcon(icono_emoji(EMOJI_ALINEAR_CENTRO)); self.btn_alinear_centro_word.setIconSize(_QSize_emoji(16, 16))
        self.btn_alinear_der_word = _boton(f_alinear_w, "", "Alinear a la derecha", lambda marcado: self._word_alinear(Qt.AlignmentFlag.AlignRight) if marcado else None, checable=True)
        self.btn_alinear_der_word.setIcon(icono_emoji(EMOJI_ALINEAR_DERECHA)); self.btn_alinear_der_word.setIconSize(_QSize_emoji(16, 16))
        self.btn_alinear_just_word = _boton(f_alinear_w, "", "Justificar", lambda marcado: self._word_alinear(Qt.AlignmentFlag.AlignJustify) if marcado else None, checable=True)
        self.btn_alinear_just_word.setIcon(self._icono_alinear_justificado()); self.btn_alinear_just_word.setIconSize(_QSize_emoji(16, 16))
        self._grupo_alinear_word = QButtonGroup(self)
        self._grupo_alinear_word.setExclusive(True)
        for _b_align in (self.btn_alinear_izq_word, self.btn_alinear_centro_word,
                         self.btn_alinear_der_word, self.btn_alinear_just_word):
            self._grupo_alinear_word.addButton(_b_align)
        tb.addWidget(g_alinear_w)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Listas"
        g_listas, f_listas = self._crear_grupo_ribbon("Listas")
        _boton(f_listas, "• Lista", "Lista con viñetas", self._word_lista_vinetas)
        _boton(f_listas, "1. Lista", "Lista numerada", self._word_lista_numerada)
        tb.addWidget(g_listas)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Insertar"
        g_insertar_w, f_insertar_w = self._crear_grupo_ribbon("Insertar")
        _boton(f_insertar_w, "Imagen", "Insertar una imagen en el punto del cursor", self._word_insertar_imagen)
        _boton(f_insertar_w, "Enlace", "Insertar o editar un hipervínculo", self._word_insertar_enlace)
        tb.addWidget(g_insertar_w)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Herramientas": equivalente a la barra "HERRAMIENTAS DE
        # DOCUMENTO" del modo PDF (marca de agua, combinar, exportar imagen,
        # ver texto), pero adaptado a lo que tiene sentido en un documento
        # de Word editable. Los botones viven dentro de un menú desplegable
        # para no ocupar espacio permanente en la cinta.
        g_herr_w, f_herr_w = self._crear_grupo_ribbon("Herramientas")
        self._marca_agua_word = None
        btn_herr_word = QToolButton()
        btn_herr_word.setText("Herramientas")
        btn_herr_word.setIcon(icono_emoji("🛠"))
        btn_herr_word.setIconSize(_QSize_emoji(16, 16))
        btn_herr_word.setToolTip(
            "Herramientas de documento:\n"
            "• Marca de agua (se aplica al guardar el .docx)\n"
            "• Insertar el contenido de otro documento\n"
            "• Exportar la hoja como imagen\n"
            "• Estadísticas del documento")
        btn_herr_word.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_herr_word.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_herr = QMenu(btn_herr_word)
        self._accion_marca_agua_word = menu_herr.addAction(icono_emoji("💧"), "Marca de agua…")
        self._accion_marca_agua_word.triggered.connect(self._word_marca_de_agua)
        accion_combinar_word = menu_herr.addAction(icono_emoji("📎"), "Insertar contenido de otro documento…")
        accion_combinar_word.setToolTip(
            "Agrega al final de este documento el texto de otro archivo "
            "(.docx, .txt o .html) — la versión Word de «Combinar con otro PDF»")
        accion_combinar_word.triggered.connect(self._word_insertar_documento_externo)
        accion_exportar_img_word = menu_herr.addAction(icono_emoji("🖼"), "Exportar hoja como imagen…")
        accion_exportar_img_word.setToolTip(
            "Guardar la hoja del documento como imagen PNG — la versión "
            "Word de «Exportar página como imagen» del modo PDF")
        accion_exportar_img_word.triggered.connect(self._word_exportar_imagen)
        menu_herr.addSeparator()
        accion_stats_word = menu_herr.addAction(icono_emoji("📊"), "Estadísticas del documento…")
        accion_stats_word.setToolTip(
            "Palabras, caracteres, párrafos e imágenes del documento — "
            "la versión Word de «Ver texto de la página» (aquí el contenido "
            "ya es texto editable, así que lo útil son las cifras)")
        accion_stats_word.triggered.connect(self._word_estadisticas)
        btn_herr_word.setMenu(menu_herr)
        f_herr_w.addWidget(btn_herr_word)
        tb.addWidget(g_herr_w)
        tb.addWidget(self._separador_ribbon())

        # Grupo "Vista": zoom en píldora compacta
        g_vista_w, f_vista_w = self._crear_grupo_ribbon("Vista")
        pill_zoom_word, self.in_zoom_word = self._crear_pill_zoom(
            "100%",
            lambda: self._word_zoom(-20),
            lambda: self._word_zoom(20),
            self._word_zoom_set,
            "Escribe el porcentaje de zoom (10%–400%) y pulsa Enter para aplicarlo",
        )
        f_vista_w.addWidget(pill_zoom_word)
        tb.addWidget(g_vista_w)

        tb.addStretch()
        l.addWidget(self._barra_desplazable(toolbar))

        fila_busqueda = QHBoxLayout()
        self.in_buscar_word = QLineEdit()
        limitar_campo_texto(self.in_buscar_word, 150)
        self.in_buscar_word.setPlaceholderText("Buscar en el documento…")
        self.in_buscar_word.returnPressed.connect(self._word_buscar_siguiente)
        fila_busqueda.addWidget(self.in_buscar_word, 2)
        btn_buscar_word = QPushButton("Buscar")
        btn_buscar_word.setIcon(icono_emoji("🔍"))
        btn_buscar_word.setIconSize(_QSize_emoji(16, 16))
        btn_buscar_word.setObjectName("BtnAccionNeutro")
        btn_buscar_word.clicked.connect(self._word_buscar_siguiente)
        fila_busqueda.addWidget(btn_buscar_word)
        self.in_reemplazar_word = QLineEdit()
        limitar_campo_texto(self.in_reemplazar_word, 300)
        self.in_reemplazar_word.setPlaceholderText("Reemplazar por…")
        fila_busqueda.addWidget(self.in_reemplazar_word, 2)
        btn_reemplazar_word = QPushButton("Reemplazar todo")
        btn_reemplazar_word.setIcon(icono_emoji("🔍"))
        btn_reemplazar_word.setIconSize(_QSize_emoji(16, 16))
        btn_reemplazar_word.setObjectName("BtnAccionNeutro")
        btn_reemplazar_word.clicked.connect(self._word_reemplazar_todo)
        fila_busqueda.addWidget(btn_reemplazar_word)
        l.addLayout(fila_busqueda)

        self.editor_word = QTextEdit()
        limitar_campo_texto(self.editor_word, 5000)
        self.editor_word.setAcceptRichText(True)
        # El "page" object mismo NO se desplaza ni escala solo -eso lo hace
        # el QGraphicsView que lo envuelve (ver más abajo)-, así que se le
        # apaga su scroll propio y se le da un ancho fijo tipo hoja de
        # carta; el alto se ajusta solo al contenido (ver
        # _word_ajustar_alto_pagina) para que se sienta como una hoja de
        # verdad, no como una caja de texto sin límites.
        self.editor_word.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor_word.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor_word.setFixedWidth(816)  # ~ ancho carta a 96dpi, igual de referencia que usa PDF
        self.editor_word.setMinimumHeight(1056)
        self.editor_word.textChanged.connect(self._word_marcar_editado)
        self.editor_word.textChanged.connect(self._word_ajustar_alto_pagina)
        self.editor_word.textChanged.connect(self._word_seguir_cursor)
        self.editor_word.cursorPositionChanged.connect(self._word_sincronizar_barra)
        self.editor_word.cursorPositionChanged.connect(self._word_seguir_cursor)
        self.editor_word.document().undoAvailable.connect(lambda _: self._actualizar_botones_deshacer())
        self.editor_word.document().redoAvailable.connect(lambda _: self._actualizar_botones_deshacer())
        # Interacción con imágenes al estilo Word: doble clic sobre una imagen
        # abre el diálogo de tamaño, y el clic derecho ofrece las mismas
        # acciones rápidas (100%, 50%, ajustar al ancho, eliminar).
        self.editor_word.setMouseTracking(True)
        self.editor_word.viewport().installEventFilter(self)
        self.editor_word.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor_word.customContextMenuRequested.connect(self._word_menu_contextual)

        # La "página" se mete en una escena/vista de gráficos -el mismo
        # mecanismo que usa Qt para escalar cualquier widget como una unidad
        # visual completa- para que el zoom agrande/achique la hoja entera
        # (texto, márgenes, todo junto), tal como hace el modo PDF con la
        # imagen de cada página, y NO solo el tamaño de letra.
        self._escena_word = QGraphicsScene()
        self._proxy_word = self._escena_word.addWidget(self.editor_word)
        self._vista_word = QGraphicsView(self._escena_word)
        self._vista_word.setFrameShape(QFrame.Shape.NoFrame)
        self._vista_word.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._vista_word.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._vista_word.setMinimumHeight(380)
        self._vista_word.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                                         | QPainter.RenderHint.SmoothPixmapTransform)
        self._vista_word.verticalScrollBar().setSingleStep(24)
        l.addWidget(self._vista_word, 1)

        # Herramientas de documento al guardar, igual que las de la hoja de
        # cálculo (self.chk_congelar_encabezado / self.chk_autofiltro) pero
        # con las modificaciones obvias que pide un documento de Word en vez
        # de una hoja: aquí no hay filas que congelar ni datos que filtrar,
        # así que las opciones equivalentes son numerar las páginas al pie
        # y, opcionalmente, justificar los párrafos sueltos (alineados a la
        # izquierda por defecto) al momento de guardar.
        fila_opciones_guardado_word = QHBoxLayout()
        self.chk_numeracion_paginas_word = QCheckBox("Agregar numeración de páginas al guardar (Word)")
        self.chk_numeracion_paginas_word.setChecked(True)
        self.chk_numeracion_paginas_word.setToolTip(
            "Añade el número de página en el pie de cada hoja del documento al guardarlo")
        fila_opciones_guardado_word.addWidget(self.chk_numeracion_paginas_word)
        self.chk_justificar_auto_word = QCheckBox("Justificar párrafos sin alinear al guardar (Word)")
        self.chk_justificar_auto_word.setChecked(False)
        self.chk_justificar_auto_word.setToolTip(
            "Los párrafos que se dejaron con la alineación por defecto (izquierda) "
            "se guardan justificados en vez de con el margen derecho irregular")
        fila_opciones_guardado_word.addWidget(self.chk_justificar_auto_word)
        fila_opciones_guardado_word.addStretch()
        l.addLayout(fila_opciones_guardado_word)

        return w

    def _mostrar_pagina(self, nombre):
        indice = {"vacio": 0, "hoja": 1, "pdf": 2, "word": 3}.get(nombre, 0)
        self.stack.setCurrentIndex(indice)
        self._actualizar_botones_deshacer()
        efecto = QGraphicsOpacityEffect(self.stack.currentWidget())
        self.stack.currentWidget().setGraphicsEffect(efecto)
        anim = QPropertyAnimation(efecto, b"opacity", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self.stack.currentWidget().setGraphicsEffect(None))
        anim.start()
        self._anim_pagina = anim

    # ------------------------------------------------------------
    # TEMA (claro/oscuro)
    # ------------------------------------------------------------
    def actualizar_tema(self):
        """Vuelve a pintar SOLO la "cinta de opciones" (ribbon/toolbar) del
        editor pesado, adaptada al tema claro/oscuro activo -el CONTENIDO
        (la grilla de Excel, el lienzo de Word) se deja siempre en blanco/
        colores planos, como una hoja de Excel o Word real, y NO seaplica
        el tema de la app ahí: antes se tintaba de oscuro el fondo de toda
        la zona de contenido (#EditorPesadoRaiz) y eso hacía que los
        colores de celda que sí trae el propio archivo (rellenos, texto)
        se vieran mal/con poco contraste encima de un fondo que no es el
        que el archivo espera."""
        c = _colores_tema(self.main_window)
        self._c_tema_editor = c
        self.tabla_editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabla_editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabla_editor.setStyleSheet(f"""
            QTableWidget {{
                background-color: #FFFFFF;
                color: #0F172A;
                gridline-color: #D9DEE7;
            }}
            QHeaderView::section {{
                background-color: #F1F5F9;
                color: #0F172A;
                border: 1px solid #D9DEE7;
            }}
            QLineEdit {{
                background-color: #FFFFFF;
                color: #0F172A;
                border: 2px solid {c['accent']};
                border-radius: 3px;
                padding: 1px 3px;
                margin: 0px;
                selection-background-color: {c['accent']};
                selection-color: white;
            }}
            /* Scrollbar horizontal/vertical de la hoja: se deja bien visible
               y "agarrable" -no como la delgadita por defecto de Qt, fácil
               de pasar por alto en hojas con muchas filas/columnas- y SÍ
               sigue el tema oscuro/claro de la app (a diferencia del
               contenido de la grilla, que se deja siempre en blanco). Es la
               MISMA barra que usan los modos Word y PDF, para que el editor
               se sienta consistente sin importar qué se esté editando. */
            {_qss_scrollbar_editor(c, "QTableWidget ")}
        """)
        self._aplicar_estilo_editor_word()
        self.scroll_pdf.setStyleSheet(_qss_scrollbar_editor(c, "QScrollArea "))
        # IMPORTANTE: la cinta de opciones (barras, botones, combos, tooltips)
        # NO se repinta aquí con los colores de la app. El editor tiene su
        # PROPIO tema independiente (ver combo_modo_editor/combo_acento_editor
        # y _aplicar_tema_editor/_css_editor más arriba), y antes este método
        # sobrescribía por completo el stylesheet de editor_pesado con una
        # segunda definición de QToolTip/QToolButton/TarjetaFiltros basada en
        # el tema de la APP, que competía con la de _aplicar_tema_editor()
        # -cualquiera de las dos "ganaba" según cuál se hubiera llamado por
        # última vez-. Eso era la causa de que los tooltips y el resaltado al
        # pasar el cursor sobre los botones (modos PDF/Word) cambiaran de
        # aspecto de forma impredecible, y de que a veces el texto del
        # tooltip no saliera en blanco en modo oscuro (la paleta de la app y
        # la del editor no siempre coinciden). Ahora hay una sola fuente de
        # verdad: se vuelve a aplicar el tema PROPIO del editor.
        self._aplicar_tema_editor()
        # Si el tema cambia mientras el editor está en pantalla completa, esa
        # ventana (al ser una ventana de nivel superior aparte) necesita que
        # le volvamos a copiar el QSS global -si no, se quedaría con los
        # colores del tema anterior aunque el resto de la app ya haya cambiado.
        if self._ventana_pantalla_completa is not None:
            try:
                self._ventana_pantalla_completa.setStyleSheet(self.window().styleSheet())
            except Exception:
                pass
        self._recalcular_barras_desplazables()

    # ------------------------------------------------------------
    # PANTALLA COMPLETA (única forma de editar: se activa sola al abrir un archivo)
    # ------------------------------------------------------------
    def _padre_dialogo(self):
        """Con qué widget hay que parentar los diálogos (QFileDialog, mensajes,
        etc.). Mientras el editor está en pantalla completa, ese contenido vive
        en una ventana de nivel superior aparte (self._ventana_pantalla_completa);
        si los diálogos se parentaran a `self` -que sigue viviendo dentro de la
        ventana principal, aunque esté oculta detrás- el gestor de ventanas
        terminaba trayendo al frente la ventana principal en vez de quedarse
        sobre la de pantalla completa, muy molesto para el usuario. Parentando
        siempre a la ventana que esté realmente visible se evita ese salto."""
        return self._ventana_pantalla_completa if self._ventana_pantalla_completa is not None else self

    def _entrar_pantalla_completa(self):
        if self._ventana_pantalla_completa is not None:
            # Ya hay una ventana de edición abierta (p. ej. el usuario le dio
            # a "Continuar editando" con el editor ya abierto en segundo
            # plano, o volvió a hacer clic por accidente): en vez de no
            # hacer nada -que dejaba al usuario pensando que el botón no
            # respondía, mientras la ventana real seguía escondida detrás
            # de la principal-, la traemos al frente y le damos el foco,
            # restaurándola primero si estaba minimizada.
            ventana = self._ventana_pantalla_completa
            try:
                if ventana.isMinimized():
                    ventana.showNormal()
                ventana.raise_()
                ventana.activateWindow()
            except RuntimeError:
                # Widget C++ ya destruido a pesar de la referencia (caso muy
                # raro): se limpia y se deja continuar para abrir una nueva.
                self._ventana_pantalla_completa = None
            else:
                return
        if self.ruta_actual is None:
            return
        ventana_app = self.window()
        titulo = f"{ventana_app.windowTitle()} — {os.path.basename(self.ruta_actual)}" if ventana_app else "Editor de reportes"

        ventana = _VentanaPantallaCompletaEditor(self._salir_pantalla_completa)
        ventana.setWindowTitle(titulo)
        # El ícono NO se copia del de la ventana principal (a diferencia del
        # título): esta ventana es el Editor de Reportes, así que conserva el
        # ícono con el que ya nace (ICONO_DOCUMENTO, "documentico.ico" — ver
        # aplicar_icono_ventana en _VentanaPantallaCompletaEditor.__init__).
        # CLAVE: esta ventana es una ventana de nivel superior nueva, no un
        # hijo de la ventana principal -así que NO hereda automáticamente el
        # QSS del tema (claro/oscuro) que main.py aplica solo sobre sí misma.
        # Sin esto, todos los botones, tarjetas y fondos de aquí adentro se
        # veían "en blanco" con el estilo nativo del sistema operativo, sin
        # colores ni el resto del aspecto de la app. Copiamos el mismo QSS
        # tal cual para que se vea -y se comporte con el tema- exactamente
        # igual que el resto de AcaDeXI.
        try:
            ventana.setStyleSheet(ventana_app.styleSheet())
        except Exception:
            pass
        self.editor_pesado.setParent(None)  # se saca del "limbo" antes de reengancharlo en la ventana
        ventana.layout_contenido.addWidget(self.editor_pesado)
        self.editor_pesado.show()

        self._ventana_pantalla_completa = ventana
        # La ventana de pantalla completa también adopta el tema PROPIO del
        # editor (modo claro/oscuro + acento), nunca el tema de la app.
        ventana.setStyleSheet(self._css_editor_actual or self._css_editor())
        ventana.showMaximized()
        # Traerla al frente por encima de la ventana principal: showMaximized()
        # por sí solo no siempre basta -en algunos gestores de ventanas la deja
        # detrás si la ventana principal tenía el foco- así que se refuerza con
        # raise_() (la sube por encima) y activateWindow() (le da el foco).
        ventana.raise_()
        ventana.activateWindow()
        if self.tipo_actual == "xlsx":
            # El autoajuste de columnas ya se hizo al cargar la hoja, pero en
            # ese momento la tabla todavía vivía oculta (fuera de esta
            # ventana, que ni existía aún). Se repite una vez más, ya con la
            # ventana visible y maximizada, para que el ancho final quede
            # calculado sobre las medidas reales -por si el sistema operativo
            # devuelve métricas de fuente distintas para un widget oculto.
            QTimer.singleShot(0, self._autoajustar_columnas)
        # Aparición suave (una sola animación, muy barata) en vez de un
        # "salto" brusco a pantalla completa.
        ventana.setWindowOpacity(0.0)
        anim = QPropertyAnimation(ventana, b"windowOpacity", ventana)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        ventana._anim_entrada = anim

    def _salir_pantalla_completa(self):
        ventana = self._ventana_pantalla_completa
        if ventana is None:
            return
        self._ventana_pantalla_completa = None
        self.editor_pesado.setParent(self)
        self.editor_pesado.hide()
        ventana.deleteLater()

    def _terminar_de_editar(self):
        """Botón "Terminar de editar" del panel de bienvenida: a diferencia
        de simplemente salir de pantalla completa (que deja todo el
        archivo -workbook, PDF abierto, contenido de Word- vivo en
        memoria por si el usuario quiere "Continuar editando"), esto
        cierra el editor de verdad. Libera lo que se pueda liberar desde
        acá mismo (documento PDF abierto, principalmente) y luego avisa
        a ModuloReportes -vía la señal- para que destruya esta instancia
        completa y vuelva a dejar la pestaña en su estado liviano
        original, sin gastar recursos en segundo plano."""
        if self._ventana_pantalla_completa is not None:
            self._salir_pantalla_completa()
        try:
            if self._doc_pdf is not None:
                self._doc_pdf.close()
                self._doc_pdf = None
        except Exception:
            pass
        self.solicitud_terminar_edicion.emit()

    # ------------------------------------------------------------
    # RECIENTES / APERTURA
    # ------------------------------------------------------------
    def agregar_reciente(self, ruta):
        """Otras pestañas de Reportes llaman aquí justo después de exportar
        un archivo, para que quede disponible de inmediato en este visor."""
        if not ruta or not os.path.exists(ruta):
            return
        self._recientes = [(r, e) for r, e in self._recientes if r != ruta]
        etiqueta = f"{os.path.basename(ruta)}  ·  {formatear_hora(datetime.now().strftime('%H:%M'), self.main_window)}"
        self._recientes.insert(0, (ruta, etiqueta))
        self._recientes = self._recientes[:10]
        self.combo_recientes.blockSignals(True)
        self.combo_recientes.clear()
        self.combo_recientes.addItem("Archivos recientes de esta sesión…", None)
        for r, e in self._recientes:
            self.combo_recientes.addItem(e, r)
        self.combo_recientes.setCurrentIndex(1)
        self.combo_recientes.blockSignals(False)

    def _seleccionar_reciente(self, indice):
        ruta = self.combo_recientes.itemData(indice)
        if ruta:
            self.abrir_archivo(ruta)

    def _abrir_dialogo(self):
        ruta, _ = QFileDialog.getOpenFileName(self._padre_dialogo(), "Abrir reporte", "", FILTRO_ABRIR)
        if ruta:
            self.abrir_archivo(ruta)

    def abrir_archivo(self, ruta):
        ext = _extension(ruta)
        if ext not in EXTENSIONES_SOPORTADAS:
            mostrar_mensaje("advertencia", "Formato no soportado",
                           "Solo se pueden previsualizar/editar archivos .csv, .xlsx, .docx y .pdf.", self._padre_dialogo())
            return
        try:
            if ext == "csv":
                self._abrir_csv(ruta)
            elif ext == "xlsx":
                self._abrir_xlsx(ruta)
            elif ext == "docx":
                self._abrir_docx(ruta)
            elif ext == "pdf":
                self._abrir_pdf(ruta)
        except Exception as e:
            mostrar_mensaje("error", "No se pudo abrir el archivo", str(e), self._padre_dialogo())
            return
        self.ruta_actual = ruta
        self.tipo_actual = ext
        self.lbl_archivo_actual.setTextoCompleto(f"{os.path.basename(ruta)}  —  {ruta}")
        self.btn_guardar.setEnabled(True)
        self.btn_guardar_como.setEnabled(True)
        self.btn_imprimir.setEnabled(True)
        self._actualizar_menu_exportar()
        self.agregar_reciente(ruta)
        self.lbl_titulo_estado.setText(os.path.basename(ruta))
        self.lbl_texto_estado.setText(f"Tienes este archivo abierto en el editor: {ruta}")
        self.btn_continuar_editando.setVisible(True)
        self.btn_terminar_editar.setVisible(True)
        # Se abre automáticamente en pantalla completa: es donde vive todo el
        # contenido de edición, así la pestaña de Reportes nunca se deforma.
        if self._ventana_pantalla_completa is None:
            self._entrar_pantalla_completa()

    # ------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------
    def _detectar_delimitador(self, ruta):
        try:
            with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
                muestra = f.read(4096)
            return csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
        except Exception:
            return ","

    def _abrir_csv(self, ruta):
        self._wb = None
        self._wb_valores_cache = None
        self._pila_deshacer_hoja.clear()
        self._pila_rehacer_hoja.clear()
        self.combo_hojas.setVisible(False)
        self.lbl_hojas.setVisible(False)
        self.btn_info_excel.setVisible(False)
        self._delimitador_csv = self._detectar_delimitador(ruta)
        self._poblar_csv_desde_archivo(ruta)
        self.chk_congelar_encabezado.setVisible(False)
        self.chk_autofiltro.setVisible(False)
        self.chk_numeracion_paginas_word.setVisible(False)
        self.chk_justificar_auto_word.setVisible(False)
        self._mostrar_pagina("hoja")

    def _poblar_csv_desde_archivo(self, ruta):
        """Carga CSV en dos pasadas para no duplicar un archivo grande en RAM.

        La primera solo obtiene las dimensiones; la segunda crea los items
        directamente en la grilla. Antes ``list(csv.reader(...))`` mantenía
        todas las filas además de todos los QTableWidgetItem ya creados, una
        duplicación que podía agotar la memoria con exportaciones extensas.
        """
        n_filas = n_columnas = 0
        with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
            for fila in csv.reader(f, delimiter=self._delimitador_csv):
                n_filas += 1
                n_columnas = max(n_columnas, len(fila))

        self._sincronizando = True
        self.tabla_editor.clear()
        self.tabla_editor.setUpdatesEnabled(False)
        self.tabla_editor.blockSignals(True)
        hay_formulas = False
        try:
            self.tabla_editor.setRowCount(n_filas)
            self.tabla_editor.setColumnCount(n_columnas)
            self.tabla_editor.setHorizontalHeaderLabels([_letra_columna(i) for i in range(n_columnas)])
            with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
                for r, fila in enumerate(csv.reader(f, delimiter=self._delimitador_csv)):
                    for c, valor in enumerate(fila):
                        item = QTableWidgetItem("")
                        item.setData(ROL_CRUDO, valor)
                        es_formula = valor.strip().startswith("=") and len(valor.strip()) > 1
                        hay_formulas = hay_formulas or es_formula
                        if not es_formula:
                            item.setText(valor)
                        self.tabla_editor.setItem(r, c, item)
        finally:
            self.tabla_editor.blockSignals(False)
            self.tabla_editor.setUpdatesEnabled(True)
            self._sincronizando = False
        self._autoajustar_columnas()
        if hay_formulas:
            self._recalcular_hoja()
        self.lbl_celdas.setText(f"{n_filas} filas × {n_columnas} columnas")

    def _guardar_csv(self, ruta):
        filas = self._extraer_filas_de_tabla()
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=self._delimitador_csv)
            writer.writerows(filas)

    # ------------------------------------------------------------
    # XLSX
    # ------------------------------------------------------------
    def _cargar_openpyxl(self):
        try:
            import openpyxl
            return openpyxl
        except ImportError:
            mostrar_mensaje("error", "Función no disponible",
                           "No se pudo abrir el editor de Excel en este equipo. Contacta a soporte técnico.", self._padre_dialogo())
            return None

    def _mostrar_info_limitaciones_excel(self):
        """Diálogo pequeño y discreto (se abre solo si se pulsa el botón
        "ⓘ", nunca solo/automático) con lo que sí y lo que no se puede
        hacer editando un Excel aquí -antes esto se mostraba como un
        banner permanente encima de la hoja, ocupando espacio siempre."""
        dialogo = QDialog(self._padre_dialogo())
        dialogo.setWindowTitle("Sobre editar Excel aquí")
        aplicar_icono_ventana(dialogo, ICONO_DOCUMENTO)
        dialogo.setMinimumWidth(420)
        layout = QVBoxLayout(dialogo)
        texto = QLabel(
            "<b> Esto sí funciona con total confianza:</b><br>"
            "• Editar celdas, fórmulas (con recálculo propio) y formato de texto/número.<br>"
            "• Insertar/eliminar filas y columnas, buscar y reemplazar.<br>"
            "• Colorear celdas, poner negrita/cursiva/subrayado, insertar imágenes.<br>"
            "• Gráficos: se crean como gráficos <i>nativos</i> de Excel (editables de verdad "
            "al abrir el archivo en Excel o LibreOffice).<br><br>"
            "<b> Limitaciones a tener en cuenta:</b><br>"
            "• Los <b>cuadros de texto y formas flotantes</b> reales de Excel no se pueden crear ni "
            "mostrar aquí -se usa una celda con relleno como alternativa visual-.<br>"
            "• Los <b>colores de relleno que ya trae el archivo</b> no siempre se detectan bien "
            "(dependen de cómo Excel los haya guardado internamente), así que esta vista se muestra "
            "en blanco/plano por defecto: los colores que TÚ apliques aquí con « Relleno» sí se "
            "guardan correctamente en el archivo.<br>"
            "• No hay una integración con Microsoft Excel real: es un editor propio compatible con el formato.")
        texto.setWordWrap(True)
        texto.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(texto)
        btn_cerrar = QPushButton("Entendido")
        btn_cerrar.clicked.connect(dialogo.accept)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(btn_cerrar)
        layout.addLayout(fila)
        dialogo.exec()

    def _extraer_tema_colores(self, ruta):
        """Lee xl/theme/theme1.xml directamente del .xlsx (es un zip) y
        devuelve los 10 colores de la paleta de tema del libro, EN EL ORDEN
        REAL que usa Excel para los índices de color de tema (0-9) -que no
        es el orden en que aparecen en el XML: Excel intercambia lt1↔dk1 y
        lt2↔dk2 por compatibilidad histórica con versiones antiguas de
        Office-. openpyxl expone qué índice de tema tiene una celda, pero
        NO resuelve el color real: por eso antes los colores de tema del
        archivo original se perdían/ignoraban por completo. Devuelve una
        lista de 10 strings "RRGGBB" (o None si no se pudo leer nada, p.ej.
        un archivo .xlsx dañado o sin tema)."""
        import zipfile
        import re as _re
        try:
            with zipfile.ZipFile(ruta) as z:
                xml = z.read("xl/theme/theme1.xml").decode("utf-8", errors="ignore")
        except Exception:
            return None
        # Los nodos vienen en este orden en el XML: dk1, lt1, dk2, lt2,
        # accent1..accent6, hlink, folHlink -dentro de <a:clrScheme>-.
        nombres_xml = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2",
                       "accent3", "accent4", "accent5", "accent6"]
        crudos = {}
        for nombre in nombres_xml:
            m = _re.search(rf'<a:{nombre}>\s*<a:(?:srgbClr val="([0-9A-Fa-f]{{6}})"|sysClr[^>]*lastClr="([0-9A-Fa-f]{{6}})")', xml)
            if m:
                crudos[nombre] = (m.group(1) or m.group(2)).upper()
        if not crudos:
            return None
        # Orden real de los ÍNDICES de tema (0-9) que usa un fgColor con
        # type="theme": Excel intercambia claro/oscuro respecto al orden del
        # XML -esto es un detalle documentado del formato OOXML, no un
        # capricho nuestro-.
        orden_indices = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2",
                          "accent3", "accent4", "accent5", "accent6"]
        return [crudos.get(n, "FFFFFF") for n in orden_indices]

    def _aplicar_tinte_excel(self, hex_rgb, tint):
        """Aplica el mismo ajuste de "tint" (más claro/oscuro) que Excel le
        aplica a un color de tema -Excel guarda el color BASE del tema más
        un tint por celda (p.ej. "Azul, énfasis 1, más claro 40%"), y sin
        aplicar esta fórmula el color se ve del tono base equivocado."""
        if not tint:
            return hex_rgb
        import colorsys
        r = int(hex_rgb[0:2], 16) / 255.0
        g = int(hex_rgb[2:4], 16) / 255.0
        b = int(hex_rgb[4:6], 16) / 255.0
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        if tint < 0:
            l = l * (1.0 + tint)
        else:
            l = l * (1.0 - tint) + tint
        l = max(0.0, min(1.0, l))
        r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
        return f"{int(round(r2*255)):02X}{int(round(g2*255)):02X}{int(round(b2*255)):02X}"

    def _resolver_color_relleno(self, fill):
        """Devuelve el color "RRGGBB" real de un PatternFill sólido de
        openpyxl -incluyendo colores de TEMA (resolviendo índice+tint contra
        el theme1.xml real del archivo) e INDEXADOS (paleta heredada de
        Excel 97-2003)- o None si de verdad no hay relleno/no se pudo
        resolver con confianza. Antes solo se leía fgColor.rgb tal cual, que
        openpyxl únicamente rellena para colores RGB directos -los de tema e
        indexados quedaban sin detectar-."""
        if not fill or getattr(fill, "patternType", None) != "solid" or not fill.fgColor:
            return None
        fg = fill.fgColor
        tipo = getattr(fg, "type", None)
        if tipo == "rgb" and isinstance(fg.rgb, str) and len(fg.rgb) >= 6:
            rgb_txt = fg.rgb[-6:]
            if rgb_txt in ("000000",) and fg.rgb in ("00000000",):
                return None  # "sin color" por defecto de openpyxl, no negro real
            return rgb_txt
        if tipo == "theme" and getattr(fg, "theme", None) is not None:
            paleta = getattr(self, "_tema_colores_excel", None)
            if paleta and 0 <= fg.theme < len(paleta):
                base = paleta[fg.theme]
                return self._aplicar_tinte_excel(base, getattr(fg, "tint", 0) or 0)
            return None
        if tipo == "indexed" and getattr(fg, "indexed", None) is not None:
            try:
                from openpyxl.styles.colors import COLOR_INDEX
                argb = COLOR_INDEX[fg.indexed]
                if argb and len(argb) >= 6:
                    return argb[-6:]
            except Exception:
                return None
        return None

    def _resolver_color_fuente(self, color_obj):
        """Devuelve el color 'RRGGBB' real del color de fuente (texto) de
        una celda openpyxl, o None si no hay color explícito o no se puede
        resolver. Usa la misma estrategia de tres niveles que
        _resolver_color_relleno (RGB directo → tema+tint → indexado).
        El negro automático (openpyxl rellena 'FF000000' como valor por
        defecto cuando no hay color real asignado) se descarta para no
        sobreescribir el color de texto del tema del editor."""
        if color_obj is None:
            return None
        tipo = getattr(color_obj, "type", None)
        if tipo == "rgb" and isinstance(getattr(color_obj, "rgb", None), str):
            raw = color_obj.rgb
            if len(raw) >= 6:
                rgb_txt = raw[-6:]
                # Descartar el negro automático de openpyxl (no es un negro real)
                if raw in ("FF000000", "00000000"):
                    return None
                return rgb_txt
        if tipo == "theme" and getattr(color_obj, "theme", None) is not None:
            paleta = getattr(self, "_tema_colores_excel", None)
            if paleta and 0 <= color_obj.theme < len(paleta):
                base = paleta[color_obj.theme]
                return self._aplicar_tinte_excel(base, getattr(color_obj, "tint", 0) or 0)
            return None
        if tipo == "indexed" and getattr(color_obj, "indexed", None) is not None:
            try:
                from openpyxl.styles.colors import COLOR_INDEX
                argb = COLOR_INDEX[color_obj.indexed]
                if argb and len(argb) >= 6:
                    return argb[-6:]
            except Exception:
                return None
        return None

    def _abrir_xlsx(self, ruta):
        openpyxl = self._cargar_openpyxl()
        if openpyxl is None:
            raise RuntimeError("openpyxl no disponible")
        # Las dos llamadas a load_workbook son la parte pesada (pueden tomar
        # 1-10s en archivos grandes). Se mueven a un hilo secundario para no
        # congelar la UI. El resto (poblar widgets Qt) se ejecuta en el hilo
        # principal via la señal `terminado`.
        if WorkerHilo is not None:
            self._bloquear_controles_xlsx(True)
            def _tarea_io():
                wb = openpyxl.load_workbook(ruta)
                try:
                    wb_cache = openpyxl.load_workbook(ruta, data_only=True)
                except Exception:
                    wb_cache = None
                tema = self._extraer_tema_colores(ruta)
                return wb, wb_cache, tema
            self._hilo_abrir_xlsx = WorkerHilo(_tarea_io)
            self._hilo_abrir_xlsx.terminado.connect(
                lambda res: self._on_xlsx_cargado(res[0], res[1], res[2]))
            self._hilo_abrir_xlsx.error.connect(
                lambda msg: (self._bloquear_controles_xlsx(False),
                             mostrar_mensaje("error", "Error al abrir Excel",
                                             msg.split("\n")[0], self._padre_dialogo())))
            self._hilo_abrir_xlsx.finished.connect(
                lambda: self._bloquear_controles_xlsx(False))
            self._hilo_abrir_xlsx.start()
        else:
            # Fallback síncrono si WorkerHilo no está disponible
            self._wb = openpyxl.load_workbook(ruta)
            try:
                self._wb_valores_cache = openpyxl.load_workbook(ruta, data_only=True)
            except Exception:
                self._wb_valores_cache = None
            self._tema_colores_excel = self._extraer_tema_colores(ruta)
            self._on_xlsx_cargado(self._wb, self._wb_valores_cache, self._tema_colores_excel)

    def _on_xlsx_cargado(self, wb, wb_cache, tema):
        """Slot que se ejecuta en el hilo principal cuando openpyxl terminó
        de cargar el workbook en segundo plano. Actualiza todos los widgets Qt."""
        self._wb = wb
        self._wb_valores_cache = wb_cache
        self._tema_colores_excel = tema
        self.combo_hojas.setVisible(True)
        self.lbl_hojas.setVisible(True)
        self.btn_info_excel.setVisible(True)
        self.chk_congelar_encabezado.setVisible(True)
        self.chk_autofiltro.setVisible(True)
        self.chk_numeracion_paginas_word.setVisible(False)
        self.chk_justificar_auto_word.setVisible(False)
        self.combo_hojas.blockSignals(True)
        self.combo_hojas.clear()
        self.combo_hojas.addItems(self._wb.sheetnames)
        self.combo_hojas.blockSignals(False)
        self._hoja_actual = self._wb.sheetnames[0]
        self._cargar_hoja(self._hoja_actual)
        self._mostrar_pagina("hoja")

    def _bloquear_controles_xlsx(self, bloqueado):
        """Deshabilita/habilita los controles del editor mientras una operación
        de I/O de Excel corre en segundo plano, para evitar dobles aperturas
        o guardados concurrentes que corrompan el workbook."""
        cursor = Qt.CursorShape.WaitCursor if bloqueado else Qt.CursorShape.ArrowCursor
        QApplication.setOverrideCursor(cursor) if bloqueado else QApplication.restoreOverrideCursor()
        for w in (getattr(self, "btn_exportar", None),
                  getattr(self, "btn_guardar", None),
                  getattr(self, "btn_abrir", None)):
            if w is not None:
                w.setEnabled(not bloqueado)

    def _cargar_hoja(self, nombre_hoja):
        if not nombre_hoja or self._wb is None:
            return
        self._pila_deshacer_hoja.clear()
        self._pila_rehacer_hoja.clear()
        ws = self._wb[nombre_hoja]
        ws_valores = None
        if self._wb_valores_cache is not None and nombre_hoja in self._wb_valores_cache.sheetnames:
            ws_valores = self._wb_valores_cache[nombre_hoja]
        filas = max(ws.max_row, 1)
        columnas = max(ws.max_column, 1)
        self._sincronizando = True
        # clear() no siempre quita los widgets de celda (las miniaturas de
        # imagen de una hoja abierta previamente); los quitamos a mano para
        # no dejar imágenes "fantasma" de otra hoja/otro archivo.
        for r in range(self.tabla_editor.rowCount()):
            for c in range(self.tabla_editor.columnCount()):
                if self.tabla_editor.cellWidget(r, c) is not None:
                    self.tabla_editor.removeCellWidget(r, c)
        self.tabla_editor.clear()
        # setUpdatesEnabled(False) + blockSignals(True): una hoja de cálculo
        # puede traer miles de celdas, y sin esto cada setItem() dispara un
        # repintado Y una llamada a _on_celda_editada (aunque _sincronizando
        # ya la descarta, el propio despacho de la señal cuesta tiempo). En
        # equipos modestos esa es la diferencia entre abrir un Excel grande
        # al instante o que la app se quede "congelada" varios segundos.
        self.tabla_editor.setUpdatesEnabled(False)
        self.tabla_editor.blockSignals(True)
        self.tabla_editor.setRowCount(filas)
        self.tabla_editor.setColumnCount(columnas)
        self.tabla_editor.setHorizontalHeaderLabels([_letra_columna(i) for i in range(columnas)])
        # OPTIMIZACIÓN: antes se pedía cada celda con ws.cell(row=r,
        # column=c) dentro del doble for -openpyxl hace una búsqueda/creación
        # de celda POR CADA llamada, que para una hoja grande (miles de
        # celdas) se nota mucho-. ws.iter_rows() recorre las celdas ya
        # generadas de forma secuencial y es sustancialmente más rápido
        # -en hojas de varios miles de celdas, la diferencia es de segundos
        # a un abrir casi instantáneo-. Igual para la copia de valores en
        # caché (ws_valores), si existe.
        filas_valores_iter = None
        if ws_valores is not None:
            filas_valores_iter = ws_valores.iter_rows(min_row=1, max_row=filas, min_col=1, max_col=columnas)
        hay_formulas = False
        for r, fila_celdas in enumerate(ws.iter_rows(min_row=1, max_row=filas, min_col=1, max_col=columnas), start=1):
            fila_valores = next(filas_valores_iter, None) if filas_valores_iter is not None else None
            for c, celda in enumerate(fila_celdas, start=1):
                # data_type == 'f' -> es una fórmula: el crudo que se guarda
                # es la fórmula tal cual (celda.value ya trae el "=" inicial)
                # para que el motor propio pueda evaluarla de verdad.
                crudo = celda.value
                item = QTableWidgetItem("")
                item.setData(ROL_CRUDO, crudo)
                formato_celda = _clasificar_formato_excel(getattr(celda, "number_format", None))
                if formato_celda is None and getattr(celda, "is_date", False):
                    formato_celda = "fecha"
                if formato_celda is not None:
                    item.setData(ROL_FORMATO_NUM, formato_celda)
                es_formula = getattr(celda, "data_type", None) == "f"
                hay_formulas = hay_formulas or es_formula
                # Las celdas sin fórmula no necesitan una segunda pasada de
                # cálculo para mostrar exactamente su valor formateado. En
                # libros grandes de datos esto elimina un recorrido completo
                # por la grilla y miles de cambios de QTableWidgetItem.
                if not es_formula:
                    valor, formato_sugerido = _analizar_crudo(crudo)
                    formato_mostrar = formato_celda or formato_sugerido
                    item.setText(_formatear_para_mostrar(valor, formato_mostrar))
                    es_numero = isinstance(valor, (int, float)) and not isinstance(valor, bool)
                    alineacion = Qt.AlignmentFlag.AlignRight if es_numero else Qt.AlignmentFlag.AlignLeft
                    item.setTextAlignment(int(alineacion | Qt.AlignmentFlag.AlignVCenter))
                # OPTIMIZACIÓN: item.font() clonaba un QFont nuevo cada vez
                # que se llamaba -antes se llamaba hasta 3 veces por celda
                # (negrita/cursiva/subrayado)-; ahora se pide una sola vez y
                # se reutiliza la misma instancia para las tres comprobaciones.
                fnt = celda.font
                if fnt and (fnt.bold or fnt.italic or fnt.underline):
                    f = item.font()
                    if fnt.bold:
                        f.setBold(True)
                    if fnt.italic:
                        f.setItalic(True)
                    if fnt.underline:
                        f.setUnderline(True)
                    item.setFont(f)
                # Detección mejorada del color de relleno que YA trae el
                # archivo -incluye colores de tema (resueltos contra el
                # theme1.xml real del libro, con su tint) e indexados
                # (paleta heredada de Excel 97-2003), no solo RGB directo
                # como antes. Si de verdad no se puede resolver con
                # confianza, la celda se deja en blanco -mejor sin pintar
                # que pintada mal-.
                hex_relleno = self._resolver_color_relleno(celda.fill)
                if hex_relleno:
                    color_fondo = QColor(f"#{hex_relleno}")
                    item.setBackground(color_fondo)
                    item.setForeground(_color_texto_contrastado(color_fondo))
                # Color de fuente (texto) que ya trae el archivo original:
                # RGB directo, colores de tema e indexados (misma estrategia
                # de tres niveles que el relleno). Si hay relleno, el color
                # de contraste ya se aplicó arriba -el color de fuente lo
                # sobreescribe solo si REALMENTE viene del archivo (no es el
                # negro automático de openpyxl). Los hipervínculos prevalecen
                # sobre todo (se aplican más abajo).
                color_fuente_obj = getattr(fnt, "color", None) if fnt else None
                hex_fuente = self._resolver_color_fuente(color_fuente_obj)
                if hex_fuente and not hex_relleno:
                    # Sin relleno: aplicar directamente el color de texto
                    item.setForeground(QColor(f"#{hex_fuente}"))
                elif hex_fuente and hex_relleno:
                    # Con relleno: el color de fuente del archivo prevalece
                    # sobre el color de contraste calculado automáticamente
                    item.setForeground(QColor(f"#{hex_fuente}"))
                # Si la celda ya traía un hipervínculo del archivo original
                # (insertado desde Excel real), se conserva y se pinta igual
                # que los que se insertan aquí -azul y subrayado-. Igual que
                # con los enlaces de un PDF importado, este archivo puede venir
                # de fuera de la institución, así que se descarta aquí mismo
                # cualquier destino que no sea http/https/mailto.
                enlace_celda = getattr(celda, "hyperlink", None)
                if (enlace_celda is not None and getattr(enlace_celda, "target", None)
                        and enlace_es_seguro(enlace_celda.target)):
                    item.setData(ROL_HIPERVINCULO, enlace_celda.target)
                    item.setForeground(QColor("#2563EB"))
                    f = item.font(); f.setUnderline(True); item.setFont(f)
                self.tabla_editor.setItem(r - 1, c - 1, item)
                # Respaldo: si la celda es una fórmula y trae un resultado ya
                # calculado en caché (de la copia data_only), lo guardamos
                # aparte para poder usarlo si nuestro motor no la soporta.
                if fila_valores is not None and getattr(celda, "data_type", None) == "f":
                    try:
                        item.setData(ROL_VALOR_CACHE, fila_valores[c - 1].value)
                    except Exception:
                        pass
        self.tabla_editor.blockSignals(False)
        self.tabla_editor.setUpdatesEnabled(True)
        self._mostrar_imagenes_xlsx(ws)
        self._mostrar_graficos_xlsx(ws)
        if hay_formulas:
            self._recalcular_hoja()
        # Autoajuste automático SIEMPRE al abrir, sin importar filas/columnas
        # -igual que al darle a mano al botón "↔ Autoajustar"-. Se hace AQUÍ,
        # al final, después de recalcular fórmulas e insertar imágenes: si se
        # hiciera antes, mediría el ancho con el texto crudo de las fórmulas
        # (p. ej. "=SUMA(A1:A2)") en vez del resultado ya calculado, y el
        # ajuste salía mal o parecía no hacer nada.
        self._autoajustar_columnas()
        self._sincronizando = False
        self._hoja_actual = nombre_hoja
        self.lbl_celdas.setText(f"{filas} filas × {columnas} columnas")

    def _mostrar_imagenes_xlsx(self, ws):
        """openpyxl mantiene las imágenes incrustadas de la hoja aparte de las
        celdas (en ws._images), así que aunque los VALORES de las celdas se
        lean bien, las imágenes no aparecían en la tabla. Aquí las mostramos
        como una miniatura anclada a su celda de origen -y como nunca tocamos
        ws._images al guardar (solo reescribimos valores/formato de celdas),
        se conservan intactas al guardar sin que haga falta nada más."""
        imagenes = list(getattr(ws, "_images", None) or [])
        for img in imagenes:
            try:
                fila, col = self._anchor_imagen_xlsx(img)
                if fila is None or col is None:
                    continue
                datos = img._data()
                pixmap = QPixmap()
                if not pixmap.loadFromData(datos):
                    continue
                pixmap = pixmap.scaled(120, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
                if fila >= self.tabla_editor.rowCount():
                    self.tabla_editor.setRowCount(fila + 1)
                if col >= self.tabla_editor.columnCount():
                    self.tabla_editor.setColumnCount(col + 1)
                    self.tabla_editor.setHorizontalHeaderLabels(
                        [_letra_columna(i) for i in range(self.tabla_editor.columnCount())])
                etiqueta = _EtiquetaImagenArrastrable(self, fila, col)
                etiqueta.setPixmap(pixmap)
                etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
                etiqueta.setToolTip("Imagen incrustada del Excel original (se conserva al guardar). Arrástrala para moverla de celda.")
                self.tabla_editor.setRowHeight(fila, max(self.tabla_editor.rowHeight(fila), pixmap.height() + 10))
                self.tabla_editor.setColumnWidth(col, max(self.tabla_editor.columnWidth(col), pixmap.width() + 10))
                self.tabla_editor.setCellWidget(fila, col, etiqueta)
            except Exception:
                continue

    def _anchor_imagen_xlsx(self, img):
        """Fila/columna (0-indexadas) donde openpyxl ancló la imagen."""
        ancla = getattr(img, "anchor", None)
        # Una imagen recién agregada en esta misma sesión con
        # ws.add_image(img, "D1") guarda el ancla como texto plano ("D1")
        # hasta que se guarda el archivo -openpyxl solo la convierte a un
        # objeto de anclaje al escribir el .xlsx-, así que hay que admitir
        # también ese caso además del objeto ya "resuelto".
        if isinstance(ancla, str):
            try:
                from openpyxl.utils.cell import coordinate_to_tuple
                fila, col = coordinate_to_tuple(ancla)
                return fila - 1, col - 1
            except Exception:
                return None, None
        try:
            desde = ancla._from
            return desde.row, desde.col
        except Exception:
            pass
        try:
            from openpyxl.utils.cell import coordinate_to_tuple
            fila, col = coordinate_to_tuple(img.ref)
            return fila - 1, col - 1
        except Exception:
            return None, None

    def _anchor_grafico_xlsx(self, grafico):
        """Igual que _anchor_imagen_xlsx pero para un gráfico (ws._charts):
        devuelve la (fila, columna) donde está anclado, o (None, None) si no
        se pudo determinar."""
        ancla = getattr(grafico, "anchor", None)
        fila, col = None, None
        if ancla is not None:
            try:
                desde = ancla._from
                fila, col = desde.row, desde.col
            except Exception:
                pass
            if fila is None:
                try:
                    from openpyxl.utils.cell import coordinate_to_tuple
                    fila, col = coordinate_to_tuple(str(ancla))
                    fila -= 1
                    col -= 1
                except Exception:
                    pass
        return fila, col

    def _mostrar_graficos_xlsx(self, ws):
        """Muestra marcadores visuales para los gráficos incrustados en la
        hoja (ws._charts). openpyxl puede leer los metadatos del gráfico
        (tipo, título, anclaje) pero no puede renderizarlo como imagen sin
        librerías externas, así que se muestra un placeholder con icono 📊
        y el tipo/título del gráfico en la celda de anclaje del gráfico."""
        graficos = list(getattr(ws, "_charts", None) or [])
        if not graficos:
            return
        tipo_nombres = {
            "BarChart": "Barras", "LineChart": "Líneas", "PieChart": "Circular",
            "AreaChart": "Área", "ScatterChart": "Dispersión",
            "BubbleChart": "Burbujas", "RadarChart": "Radar",
            "DoughnutChart": "Anillo", "StockChart": "Cotizaciones",
            "SurfaceChart": "Superficie",
        }
        for grafico in graficos:
            try:
                fila, col = self._anchor_grafico_xlsx(grafico)
                if fila is None or col is None:
                    continue
                # Nombre amigable del tipo de gráfico
                tipo_clase = type(grafico).__name__
                tipo_amigable = tipo_nombres.get(tipo_clase, tipo_clase.replace("Chart", ""))
                # Título del gráfico (puede estar en grafico.title o grafico.title.tx...).
                # OJO: grafico.title puede ser un objeto openpyxl.chart.title.Title
                # con texto "enriquecido" (rich text) en vez de un string simple;
                # hacer str(t.tx) sobre ese objeto NO da el texto real, da la
                # representación en crudo de Python del objeto (algo como
                # "<openpyxl.chart.text.Text object at 0x...>", que es justo el
                # texto ilegible que aparecía en la celda). Aquí se camina la
                # estructura real (tx.rich.paragraphs -> r -> t) para sacar el
                # texto de verdad, y si no se puede, simplemente se omite el
                # título en vez de mostrar basura.
                titulo = ""
                try:
                    t = grafico.title
                    if isinstance(t, str):
                        titulo = t.strip()
                    elif hasattr(t, "tx") and t.tx is not None:
                        rich = getattr(t.tx, "rich", None)
                        if rich is not None:
                            partes = []
                            for parrafo in getattr(rich, "paragraphs", None) or []:
                                for corrida in getattr(parrafo, "r", None) or []:
                                    if getattr(corrida, "t", None):
                                        partes.append(corrida.t)
                            titulo = "".join(partes).strip()
                    titulo = titulo[:40]
                except Exception:
                    titulo = ""
                etiqueta_texto = f"Gráfico de {tipo_amigable}"
                if titulo:
                    etiqueta_texto += f"\n\"{titulo}\""
                if fila >= self.tabla_editor.rowCount():
                    self.tabla_editor.setRowCount(fila + 1)
                if col >= self.tabla_editor.columnCount():
                    self.tabla_editor.setColumnCount(col + 1)
                    self.tabla_editor.setHorizontalHeaderLabels(
                        [_letra_columna(i) for i in range(self.tabla_editor.columnCount())]
                    )
                # Antes esto era un QLabel simple -sin la clase
                # _EtiquetaImagenArrastrable-, por lo que no tenía ni el
                # arrastre con el mouse ni el doble clic para quitarlo (a
                # diferencia de las imágenes y de los gráficos NUEVOS creados
                # desde este mismo editor, que sí usan esa clase). Con esto
                # los gráficos que ya venían en el Excel original quedan con
                # el mismo comportamiento: se pueden arrastrar a otra celda o
                # quitar con doble clic.
                etiqueta = _EtiquetaImagenArrastrable(self, fila, col)
                etiqueta.setText(etiqueta_texto)
                etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
                etiqueta.setWordWrap(True)
                etiqueta.setToolTip(
                    f"Gráfico de tipo '{tipo_amigable}' incrustado en el Excel original.\n"
                    "Se conserva al guardar. Arrástralo para moverlo de celda, o haz doble clic para quitarlo."
                )
                etiqueta.setStyleSheet(
                    "QLabel { background: #EFF6FF; color: #1D4ED8; border: 2px dashed #93C5FD;"
                    " border-radius: 8px; padding: 12px; font-size: 12px; }"
                )
                self.tabla_editor.setRowHeight(fila, max(self.tabla_editor.rowHeight(fila), 90))
                self.tabla_editor.setColumnWidth(col, max(self.tabla_editor.columnWidth(col), 180))
                self.tabla_editor.setCellWidget(fila, col, etiqueta)
            except Exception:
                continue

    def _celda_actual_o_primera_seleccion(self):
        fila, col = self.tabla_editor.currentRow(), self.tabla_editor.currentColumn()
        if fila < 0 or col < 0:
            rangos = self.tabla_editor.selectedRanges()
            if rangos:
                fila, col = rangos[0].topRow(), rangos[0].leftColumn()
            else:
                fila, col = 0, 0
        return fila, col

    def _rango_seleccionado(self):
        """(fila_inicio, fila_fin, col_inicio, col_fin) -0-indexado, ambos
        extremos incluidos- del primer rango seleccionado en la grilla, o
        None si no hay nada seleccionado."""
        rangos = self.tabla_editor.selectedRanges()
        if not rangos:
            return None
        r = rangos[0]
        return r.topRow(), r.bottomRow(), r.leftColumn(), r.rightColumn()

    def _insertar_imagen_hoja(self):
        """Inserta una imagen en la hoja de Excel, anclada a la celda
        seleccionada -incrustada con openpyxl (imagen real dentro del
        .xlsx) y visible/arrastrable de inmediato en la grilla (encajada a
        la celda más cercana al soltarla)."""
        if self._wb is None:
            mostrar_mensaje("advertencia", "Solo disponible en Excel",
                           "Insertar imágenes en la hoja solo está disponible al editar un archivo .xlsx (no en CSV).",
                           self._padre_dialogo())
            return
        ruta, _filtro = QFileDialog.getOpenFileName(
            self._padre_dialogo(), "Insertar imagen", "", "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not ruta:
            return
        fila, col = self._celda_actual_o_primera_seleccion()
        self._insertar_imagen_openpyxl(fila, col, ruta)

    def _insertar_imagen_openpyxl(self, fila, col, ruta):
        """Imagen incrustada REAL en el .xlsx (openpyxl la conserva junto con
        el resto de imágenes de la hoja, ver _mostrar_imagenes_xlsx) y
        visible/arrastrable de inmediato en la grilla (encajada a la celda
        más cercana al soltarla)."""
        try:
            from openpyxl.drawing.image import Image as ImagenExcel
            img_excel = ImagenExcel(ruta)
            ANCHO_MAX = 220
            if img_excel.width > ANCHO_MAX:
                factor = ANCHO_MAX / img_excel.width
                img_excel.width = int(img_excel.width * factor)
                img_excel.height = int(img_excel.height * factor)
            celda_ancla = f"{_letra_columna(col)}{fila + 1}"
            ws = self._wb[self._hoja_actual]
            ws.add_image(img_excel, celda_ancla)
        except Exception as e:
            mostrar_mensaje("error", "No se pudo insertar", f"No se pudo insertar la imagen: {e}", self._padre_dialogo())
            return
        pixmap = QPixmap(ruta)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(120, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
            etiqueta = _EtiquetaImagenArrastrable(self, fila, col)
            etiqueta.setPixmap(pixmap)
            etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
            etiqueta.setToolTip("Imagen insertada (se guardará al presionar Guardar). Arrástrala para moverla de celda.")
            self.tabla_editor.setRowHeight(fila, max(self.tabla_editor.rowHeight(fila), pixmap.height() + 10))
            self.tabla_editor.setColumnWidth(col, max(self.tabla_editor.columnWidth(col), pixmap.width() + 10))
            self.tabla_editor.setCellWidget(fila, col, etiqueta)
        mostrar_mensaje("exito", "Imagen insertada",
                       "La imagen se agregó a la hoja; quedará guardada al presionar Guardar.", self._padre_dialogo())

    def _limpiar_antes_de_salir(self):
        """Se llama una sola vez, justo antes de que la aplicación termine
        de verdad (conectado a QApplication.aboutToQuit en __init__). Es la
        limpieza real: al ser un widget EMBEBIDO dentro de la pestaña de
        Reportes (no una ventana propia), este editor nunca recibe su
        propio closeEvent -por eso no alcanza con overridear closeEvent
        aquí; aboutToQuit es el único punto garantizado que se dispara
        siempre, sin importar si el usuario cerró primero el editor,
        primero la ventana principal, o directamente le dio a \"Salir\"
        desde el icono de la bandeja del sistema con todo de fondo."""
        if self._cerrando:
            return
        self._cerrando = True
        try:
            if hasattr(self, "tabla_editor"):
                self.tabla_editor.removeEventFilter(self)
                self.tabla_editor.viewport().removeEventFilter(self)
            if hasattr(self, "editor_word"):
                self.editor_word.viewport().removeEventFilter(self)
        except RuntimeError:
            pass  # el widget ya podría estar en proceso de destruirse
        try:
            if self._doc_pdf is not None:
                self._doc_pdf.close()
                self._doc_pdf = None
        except Exception:
            pass
        # Cerrar cualquier hilo de trabajo secundario que pudiera estar corriendo
        # (guardado/exportación en curso). Se espera hasta 3 s para que el hilo
        # pueda finalizar limpiamente; si no lo hace en ese tiempo, Qt lo
        # terminará al destruir el proceso de todas formas.
        for attr in ("_hilo_abrir_xlsx", "_hilo_guardado", "_hilo_guardado_como",
                     "_hilo_exportar_pdf", "_hilo_exportar_xlsx", "_hilo_exportar_docx"):
            hilo = getattr(self, attr, None)
            if hilo is None:
                continue
            try:
                # hilo.isRunning() también puede fallar: gracias al
                # finished.connect(self.deleteLater) de WorkerHilo, el
                # objeto C++ puede haberse destruido solo ya (hilo
                # terminado y recolectado) entre que se guardó la
                # referencia y este chequeo -por eso isRunning() va
                # DENTRO del mismo try, no antes.
                if hilo.isRunning():
                    hilo.quit()
                    hilo.wait(3000)
            except RuntimeError:
                pass  # el objeto C++ del hilo ya fue destruido (deleteLater)
            except Exception:
                pass

    def eventFilter(self, obj, evento):
        """Punto de entrada real de Qt. Delega todo el trabajo a
        _eventFilter_impl() envuelto en un try/except: durante el cierre de
        la aplicación (sobre todo si el usuario cierra AcaDeXI completo
        desde el icono de la bandeja del sistema, con este editor todavía
        vivo en segundo plano) Qt puede seguir entregando eventos ya
        encoladas después de que el lado C++ de algún widget (típicamente
        editor_word) se haya destruido. Sin esta protección, PySide lanza
        un RuntimeError ('... already deleted') dentro de un eventFilter, y
        Qt no sabe qué hacer con una excepción ahí -el resultado es el
        traceback en cascada de 'Error calling Python override of
        QObject::eventFilter()' repetido decenas de veces que se ve en la
        terminal al cerrar. Atajarlo aquí y devolver False dice
        simplemente 'seguí con el procesamiento normal', que es
        inofensivo porque la app se está cerrando de todas formas."""
        try:
            return self._eventFilter_impl(obj, evento)
        except RuntimeError:
            return False

    def _eventFilter_impl(self, obj, evento):
        """Tres cosas distintas se filtran aquí (unificado en un solo
        método: tener dos `def eventFilter` en la misma clase es un bug de
        Python -el segundo pisa por completo al primero-, así que la
        detección de doble clic sobre una imagen de Word se había quedado
        sin funcionar de hecho hasta esta fusión):

        1) Doble clic sobre una imagen del editor de Word -abre el diálogo
           de tamaño-.
        2) ShortcutOverride -causa real de que "algunos atajos no
           funcionaran"-: QTextEdit y QTableWidget interceptan por defecto
           muchas combinaciones Ctrl+letra ANTES de que le lleguen al
           QShortcut registrado en _crear_atajos_teclado -es un
           comportamiento defensivo estándar de Qt en widgets de edición,
           para proteger sus propios atajos internos (copiar/pegar/
           deshacer)-, así que Ctrl+B/I/U/F, por ejemplo, nunca llegaban a
           disparar nuestra función mientras el foco estaba DENTRO del
           editor de texto o de la tabla. Aquí se detecta ese evento para
           nuestras combinaciones específicas y se llama a evento.ignore()
           -le dice a Qt "este widget no lo va a manejar él mismo"-, lo que
           hace que el QShortcut sí se dispare con normalidad.
        3) Arrastre de "cuadro de texto" sobre el viewport de la tabla (ver
           _mover_cuadro_texto)."""
        if self._cerrando:
            return False
        if (hasattr(self, "editor_word") and obj is self.editor_word.viewport()
                and evento.type() == QEvent.Type.MouseButtonDblClick):
            cursor_img = self._word_cursor_sobre_imagen(evento.pos())
            if cursor_img is not None:
                self._word_redimensionar_imagen_en(cursor_img)
                return True
        if hasattr(self, "editor_word") and obj is self.editor_word.viewport():
            # Ctrl+clic sobre un hipervínculo lo abre -igual que en Word/
            # Office real-. Sin Ctrl, un clic sobre el enlace simplemente
            # posiciona el cursor de edición ahí, como en cualquier texto.
            if (evento.type() == QEvent.Type.MouseButtonRelease
                    and evento.button() == Qt.MouseButton.LeftButton
                    and evento.modifiers() & Qt.KeyboardModifier.ControlModifier):
                enlace = self.editor_word.anchorAt(evento.pos())
                if enlace:
                    abrir_enlace_externo(enlace, self)
                    return True
            elif evento.type() == QEvent.Type.MouseMove:
                enlace = self.editor_word.anchorAt(evento.pos())
                if enlace and (evento.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self.editor_word.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                    QToolTip.showText(evento.globalPosition().toPoint(), f"Ctrl+clic para abrir:\n{enlace}")
                elif enlace:
                    self.editor_word.viewport().setCursor(Qt.CursorShape.IBeamCursor)
                    QToolTip.showText(evento.globalPosition().toPoint(), "Ctrl+clic para abrir el enlace")
                else:
                    self.editor_word.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        if hasattr(self, "tabla_editor") and obj is self.tabla_editor.viewport():
            # Mismo comportamiento que en Word: Ctrl+clic sobre una celda con
            # hipervínculo lo abre; sin Ctrl, un clic normal solo selecciona
            # la celda como siempre.
            if (evento.type() == QEvent.Type.MouseButtonRelease
                    and evento.button() == Qt.MouseButton.LeftButton
                    and evento.modifiers() & Qt.KeyboardModifier.ControlModifier):
                item = self.tabla_editor.itemAt(evento.pos())
                enlace = item.data(ROL_HIPERVINCULO) if item else None
                if enlace:
                    abrir_enlace_externo(enlace, self)
                    return True
            elif evento.type() == QEvent.Type.MouseMove:
                item = self.tabla_editor.itemAt(evento.pos())
                enlace = item.data(ROL_HIPERVINCULO) if item else None
                if enlace and (evento.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self.tabla_editor.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                    QToolTip.showText(evento.globalPosition().toPoint(), f"Ctrl+clic para abrir:\n{enlace}")
                elif enlace:
                    self.tabla_editor.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                    QToolTip.showText(evento.globalPosition().toPoint(), "Ctrl+clic para abrir el enlace")
                else:
                    self.tabla_editor.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        if evento.type() == QEvent.Type.ShortcutOverride:
            # OJO: aquí solo se fuerzan las combinaciones que NO tienen
            # ningún significado de edición de texto estándar (B/I/U/F/S/
            # zoom) -Ctrl+A y Delete a propósito NO se fuerzan: esas SÍ
            # tienen un comportamiento nativo esperado mientras se está
            # editando texto de verdad (Ctrl+A selecciona el texto de la
            # celda/documento actual, Delete borra el carácter siguiente), y
            # forzarlas rompería ese comportamiento normal de escritura. Sin
            # forzar nada, nuestro QShortcut para esas dos igual se dispara
            # solo cuando NO se está editando texto activamente -que es
            # exactamente el comportamiento de Excel/Word reales-.
            # NOTA: esta condición solo mira "¿está Ctrl presionado?" y la
            # tecla base (Plus/Equal/Minus/etc.), sin importar si además hay
            # Shift/Alt encima -por eso los atajos nuevos de insertar/
            # eliminar fila y columna (Ctrl+Shift+Plus, Ctrl+Alt+Minus, …)
            # quedan cubiertos automáticamente por este mismo bloque, sin
            # necesidad de agregarlos aparte.
            if evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if evento.key() in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U, Qt.Key.Key_F,
                                    Qt.Key.Key_S, Qt.Key.Key_Plus, Qt.Key.Key_Equal,
                                    Qt.Key.Key_Minus, Qt.Key.Key_0):
                    evento.ignore()
                    return True
        if obj is self.tabla_editor.viewport():
            if evento.type() == QEvent.Type.MouseButtonPress and evento.button() == Qt.MouseButton.LeftButton:
                indice = self.tabla_editor.indexAt(evento.pos())
                if indice.isValid():
                    item = self.tabla_editor.item(indice.row(), indice.column())
                    if item is not None and item.data(ROL_ES_CUADRO_TEXTO):
                        self._arrastre_cuadro_texto_origen = (indice.row(), indice.column())
                        self.tabla_editor.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                        return True  # se consume: no inicia la selección normal de celdas
            elif evento.type() == QEvent.Type.MouseButtonRelease and evento.button() == Qt.MouseButton.LeftButton:
                origen = self._arrastre_cuadro_texto_origen
                if origen is not None:
                    self._arrastre_cuadro_texto_origen = None
                    self.tabla_editor.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                    indice = self.tabla_editor.indexAt(evento.pos())
                    if indice.isValid():
                        self._mover_cuadro_texto(origen, (indice.row(), indice.column()))
                    return True
        return super().eventFilter(obj, evento)

    def _mover_cuadro_texto(self, origen, destino):
        """Mueve el contenido/formato de un "cuadro de texto" de la celda
        `origen` a la celda `destino` -copia todo lo relevante y limpia el
        origen, ya que no es un widget aparte sino una celda normal con
        estilo especial."""
        if origen == destino:
            return
        fila_o, col_o = origen
        fila_d, col_d = destino
        item_o = self.tabla_editor.item(fila_o, col_o)
        if item_o is None or not item_o.data(ROL_ES_CUADRO_TEXTO):
            return
        item_d = self.tabla_editor.item(fila_d, col_d)
        if item_d is not None and (item_d.text() or item_d.data(ROL_CRUDO)):
            mostrar_mensaje("advertencia", "Celda ocupada",
                           "Ya hay contenido en esa celda; suelta en una celda libre.", self._padre_dialogo())
            return
        texto = item_o.data(ROL_CRUDO)
        self._sincronizando = True
        if item_d is None:
            item_d = QTableWidgetItem("")
            self.tabla_editor.setItem(fila_d, col_d, item_d)
        item_d.setData(ROL_CRUDO, texto)
        item_d.setData(ROL_FORMATO_NUM, None)
        item_d.setData(ROL_ES_CUADRO_TEXTO, True)
        item_d.setBackground(item_o.background())
        item_d.setForeground(item_o.foreground())
        item_d.setFont(item_o.font())
        item_d.setText(item_o.text())
        item_d.setToolTip(item_o.toolTip())
        self.tabla_editor.setRowHeight(fila_d, max(self.tabla_editor.rowHeight(fila_d), self.tabla_editor.rowHeight(fila_o)))
        self.tabla_editor.setColumnWidth(col_d, max(self.tabla_editor.columnWidth(col_d), self.tabla_editor.columnWidth(col_o)))
        # Se limpia el origen (queda como una celda vacía normal). OJO:
        # usar QColor() aquí sería un error -QColor() se convierte
        # implícitamente en un QBrush SÓLIDO (con color inválido), no en
        # "sin color de fondo"- y reintroduciría el mismo bug del relleno
        # negro por defecto que se arregló antes. QBrush() (sin argumentos)
        # sí tiene estilo NoBrush de verdad.
        item_o.setData(ROL_CRUDO, None)
        item_o.setData(ROL_ES_CUADRO_TEXTO, None)
        item_o.setBackground(QBrush())
        item_o.setForeground(QBrush())
        f = item_o.font(); f.setItalic(False); item_o.setFont(f)
        item_o.setText("")
        item_o.setToolTip("")
        self._sincronizando = False

    def _soltar_imagen_arrastrada(self, etiqueta, punto_global):
        """Al soltar una imagen arrastrada (_EtiquetaImagenArrastrable),
        la mueve a la celda de la grilla que quedó bajo el cursor -tanto
        visualmente como el ancla real de la imagen dentro del .xlsx-.

        CRASH ARREGLADO AQUÍ DE VERDAD (la causa real de "la app se
        crashea al arrastrar"): `QTableWidget.removeCellWidget()` SIEMPRE
        programa la destrucción (`deleteLater()`) del widget que hubiera en
        esa celda -sin importar desde dónde se lo llame-. El intento
        anterior (diferir todo con QTimer) no arreglaba el problema de
        fondo porque, dentro de ese mismo bloque diferido, se seguía
        REUTILIZANDO el mismo objeto `etiqueta` después de llamar a
        removeCellWidget() sobre él -tarde o temprano Qt procesa esa
        eliminación programada y destruye el objeto C++ mientras Python
        todavía lo tiene "puesto" en la celda nueva, provocando el crash
        ("Internal C++ object already deleted") apenas se vuelve a tocar.
        La solución correcta es no reutilizar NUNCA un widget después de
        quitarlo de una celda con removeCellWidget(): aquí se guarda su
        contenido (pixmap o texto, tooltip, opacidad) ANTES de quitarlo, se
        quita, y se crea una etiqueta NUEVA para la celda de destino."""
        tabla = self.tabla_editor
        punto_tabla = tabla.viewport().mapFromGlobal(punto_global)
        fila_destino = tabla.rowAt(punto_tabla.y())
        col_destino = tabla.columnAt(punto_tabla.x())
        if fila_destino < 0 or col_destino < 0:
            return  # se soltó fuera de la grilla: se queda donde estaba
        if (fila_destino, col_destino) == (etiqueta.fila, etiqueta.col):
            return
        if tabla.cellWidget(fila_destino, col_destino) is not None:
            mostrar_mensaje("advertencia", "Celda ocupada",
                           "Ya hay otra imagen en esa celda; suelta en una celda libre.", self._padre_dialogo())
            return
        fila_origen, col_origen = etiqueta.fila, etiqueta.col
        # Se copia TODO el contenido/estado visual antes de tocar nada.
        pixmap_original = etiqueta.pixmap()
        texto_original = etiqueta.text()
        tooltip_original = etiqueta.toolTip()
        opacidad_original = etiqueta.opacidad
        ruta_original = etiqueta.ruta_original

        def _mover_de_verdad():
            if self._cerrando:
                return
            tabla.removeCellWidget(fila_origen, col_origen)  # destruye la etiqueta VIEJA; no se vuelve a tocar
            nueva = _EtiquetaImagenArrastrable(self, fila_destino, col_destino, ruta_original)
            if pixmap_original is not None and not pixmap_original.isNull():
                nueva.setPixmap(pixmap_original)
            elif texto_original:
                nueva.setText(texto_original)
            nueva.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nueva.setStyleSheet(etiqueta.styleSheet())
            nueva.setToolTip(tooltip_original)
            nueva.opacidad = opacidad_original
            if opacidad_original < 1.0:
                efecto = QGraphicsOpacityEffect(nueva)
                efecto.setOpacity(opacidad_original)
                nueva.setGraphicsEffect(efecto)
            # BUG arreglado aquí también: al insertar una imagen SÍ se
            # agranda la fila y columna de destino para que quepa completa
            # (ver _insertar_imagen_openpyxl), pero al ARRASTRARLA a otra
            # celda nunca se hacía lo mismo -la imagen quedaba encogida
            # dentro de una celda de tamaño normal (~20px de alto),
            # prácticamente invisible. Ahora se agranda igual la fila/
            # columna de destino, usando el tamaño real del contenido.
            if pixmap_original is not None and not pixmap_original.isNull():
                tabla.setRowHeight(fila_destino, max(tabla.rowHeight(fila_destino), pixmap_original.height() + 10))
                tabla.setColumnWidth(col_destino, max(tabla.columnWidth(col_destino), pixmap_original.width() + 10))
            else:
                # Marcadores sin imagen real (p.ej. el de un gráfico, que
                # solo tiene texto) no tienen pixmap: se usa su tamaño
                # "natural" (sizeHint) en su lugar, para que igual quede
                # visible completo en la celda de destino.
                sugerido = nueva.sizeHint()
                tabla.setRowHeight(fila_destino, max(tabla.rowHeight(fila_destino), sugerido.height() + 10))
                tabla.setColumnWidth(col_destino, max(tabla.columnWidth(col_destino), sugerido.width() + 10))
            tabla.setCellWidget(fila_destino, col_destino, nueva)
            nueva.show()
            # Se actualiza también el ancla REAL de la imagen dentro del
            # .xlsx (openpyxl), para que la nueva posición se conserve al
            # guardar.
            if self._wb is not None and self._hoja_actual in self._wb.sheetnames:
                ws = self._wb[self._hoja_actual]
                nueva_celda = f"{_letra_columna(col_destino)}{fila_destino + 1}"
                for img in list(getattr(ws, "_images", None) or []):
                    fila_img, col_img = self._anchor_imagen_xlsx(img)
                    if (fila_img, col_img) == (fila_origen, col_origen):
                        img.anchor = nueva_celda
                        break
                # Los gráficos (ws._charts) se anclan igual que las imágenes,
                # pero viven en una lista aparte -sin este bloque, arrastrar
                # un gráfico a otra celda solo se veía "movido" en pantalla,
                # y al guardar el archivo el gráfico real volvía a aparecer
                # en su celda original.
                for grafico in list(getattr(ws, "_charts", None) or []):
                    fila_g, col_g = self._anchor_grafico_xlsx(grafico)
                    if (fila_g, col_g) == (fila_origen, col_origen):
                        grafico.anchor = nueva_celda
                        break

        QTimer.singleShot(0, _mover_de_verdad)

    def _editar_opciones_imagen(self, etiqueta):
        """Panel de opciones al hacer doble clic sobre una imagen insertada
        en la hoja: transparencia (como en Word) y quitar la imagen. La
        opacidad se aplica tanto a la vista previa (QGraphicsOpacityEffect)
        como -al guardar- al PNG real incrustado en el .xlsx, mezclando el
        canal alfa con PIL para que se conserve al abrir el archivo en
        Excel/LibreOffice."""
        # Si la etiqueta no tiene un pixmap real (por ejemplo el marcador de
        # un gráfico, que solo tiene texto), no tiene sentido mostrarle un
        # control de "transparencia" -eso solo aplica a imágenes de verdad-;
        # en ese caso el diálogo se reduce a poder quitarlo.
        es_imagen_real = not etiqueta.pixmap().isNull() if hasattr(etiqueta, "pixmap") else False
        dialogo = QDialog(self._padre_dialogo())
        dialogo.setWindowTitle("Opciones de imagen" if es_imagen_real else "Opciones del gráfico")
        aplicar_icono_ventana(dialogo, ICONO_DOCUMENTO)
        layout = QVBoxLayout(dialogo)
        slider = None
        if es_imagen_real:
            layout.addWidget(QLabel("Transparencia:"))
            fila_op = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int((1.0 - etiqueta.opacidad) * 100))
            lbl_valor = QLabel(f"{slider.value()}%")
            slider.valueChanged.connect(lambda v: lbl_valor.setText(f"{v}%"))
            fila_op.addWidget(slider, 1)
            fila_op.addWidget(lbl_valor)
            layout.addLayout(fila_op)
        else:
            layout.addWidget(QLabel("¿Qué quieres hacer con este gráfico?"))

        botones = QHBoxLayout()
        btn_quitar = QPushButton("Quitar imagen" if es_imagen_real else "Quitar gráfico")
        btn_quitar.setIcon(icono_emoji("🗑"))
        btn_quitar.setIconSize(_QSize_emoji(16, 16))
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setIcon(icono_emoji("✖"))
        btn_cerrar.setIconSize(_QSize_emoji(16, 16))
        botones.addWidget(btn_quitar)
        botones.addStretch()
        botones.addWidget(btn_cerrar)
        if es_imagen_real:
            btn_aplicar = QPushButton("Aplicar")
            btn_aplicar.setIcon(icono_emoji("✅"))
            btn_aplicar.setIconSize(_QSize_emoji(16, 16))
            botones.addWidget(btn_aplicar)
        layout.addLayout(botones)

        def _aplicar():
            porcentaje_transparencia = slider.value()
            etiqueta.opacidad = 1.0 - (porcentaje_transparencia / 100.0)
            efecto = QGraphicsOpacityEffect(etiqueta)
            efecto.setOpacity(etiqueta.opacidad)
            etiqueta.setGraphicsEffect(efecto)
            self._sincronizando = True
            self._sincronizando = False
            dialogo.accept()

        def _quitar():
            self.tabla_editor.removeCellWidget(etiqueta.fila, etiqueta.col)
            if self._wb is not None and self._hoja_actual in self._wb.sheetnames:
                ws = self._wb[self._hoja_actual]
                for img in list(getattr(ws, "_images", None) or []):
                    fila_img, col_img = self._anchor_imagen_xlsx(img)
                    if (fila_img, col_img) == (etiqueta.fila, etiqueta.col):
                        ws._images.remove(img)
                        break
                # Los gráficos (ver _anchor_grafico_xlsx) viven en una lista
                # aparte de las imágenes -sin esto, "Quitar gráfico" solo lo
                # quitaba de la vista pero seguía guardándose en el Excel-.
                for grafico in list(getattr(ws, "_charts", None) or []):
                    fila_g, col_g = self._anchor_grafico_xlsx(grafico)
                    if (fila_g, col_g) == (etiqueta.fila, etiqueta.col):
                        ws._charts.remove(grafico)
                        break
            dialogo.accept()

        if es_imagen_real:
            btn_aplicar.clicked.connect(_aplicar)
        btn_quitar.clicked.connect(_quitar)
        btn_cerrar.clicked.connect(dialogo.reject)
        dialogo.exec()

    def _insertar_grafico_hoja(self):
        """Punto de entrada del botón "📊 Gráfico": crea un gráfico NATIVO
        de Excel con openpyxl.chart -totalmente editable al abrir el
        archivo en Excel/LibreOffice, con sus datos vivos-, y muestra un
        marcador en la grilla (Qt no puede renderizar un gráfico de Excel
        dentro de la tabla)."""
        if self._wb is None:
            mostrar_mensaje("advertencia", "Solo disponible en Excel",
                           "Insertar gráficos solo está disponible al editar un archivo .xlsx (no en CSV).",
                           self._padre_dialogo())
            return
        rango = self._rango_seleccionado()
        if rango is None:
            mostrar_mensaje("advertencia", "Selecciona los datos",
                           "Selecciona primero el rango de celdas con los datos del gráfico "
                           "(idealmente con encabezados en la primera fila y las categorías en la primera columna).",
                           self._padre_dialogo())
            return
        r1, r2, c1, c2 = rango
        if r1 == r2 and c1 == c2:
            mostrar_mensaje("advertencia", "Selecciona más de una celda",
                           "Selecciona un rango con al menos una columna de categorías y una de datos.",
                           self._padre_dialogo())
            return
        tipo, ok = QInputDialog.getItem(
            self._padre_dialogo(), "Tipo de gráfico", "Elige el tipo de gráfico:",
            ["Barras", "Líneas", "Circular"], 0, False)
        if not ok:
            return
        self._insertar_grafico_openpyxl(tipo, rango)

    def _insertar_grafico_openpyxl(self, tipo, rango):
        """Gráfico NATIVO de Excel creado con openpyxl.chart -totalmente
        editable al abrir el archivo en Excel/LibreOffice, con sus datos
        vivos-. Como Qt no puede renderizar un gráfico de Excel dentro de
        la grilla, se muestra un marcador en su lugar."""
        r1, r2, c1, c2 = rango
        # Se sincronizan primero los valores actuales de la grilla hacia la
        # hoja de openpyxl -el gráfico se arma sobre esos datos-.
        self._sincronizar_grid_a_hoja(self._hoja_actual)
        ws = self._wb[self._hoja_actual]
        from openpyxl.chart import BarChart, LineChart, PieChart, Reference
        clase_grafico = {"Barras": BarChart, "Líneas": LineChart, "Circular": PieChart}.get(tipo, BarChart)
        grafico = clase_grafico()
        grafico.title = "Gráfico"
        grafico.height, grafico.width = 8, 14
        # Se asume -como en el "gráfico rápido" de Excel- que la primera
        # columna del rango son las categorías y el resto son las series de
        # datos, con los nombres de cada serie en la primera fila. Si solo
        # se seleccionó una columna, esa misma columna se usa como única
        # serie (sin columna de categorías aparte).
        if c2 > c1:
            datos = Reference(ws, min_col=c1 + 2, max_col=c2 + 1, min_row=r1 + 1, max_row=r2 + 1)
            categorias = Reference(ws, min_col=c1 + 1, max_col=c1 + 1, min_row=r1 + 2, max_row=r2 + 1)
            grafico.add_data(datos, titles_from_data=True)
            grafico.set_categories(categorias)
        else:
            datos = Reference(ws, min_col=c1 + 1, max_col=c1 + 1, min_row=r1 + 1, max_row=r2 + 1)
            grafico.add_data(datos, titles_from_data=True)
        col_ancla = c2 + 2
        celda_ancla = f"{_letra_columna(col_ancla)}{r1 + 1}"
        ws.add_chart(grafico, celda_ancla)
        # Marcador visual en la grilla (el gráfico real se ve/edita al abrir
        # el .xlsx en Excel o LibreOffice).
        if r1 >= self.tabla_editor.rowCount():
            self.tabla_editor.setRowCount(r1 + 1)
        if col_ancla >= self.tabla_editor.columnCount():
            self.tabla_editor.setColumnCount(col_ancla + 1)
            self.tabla_editor.setHorizontalHeaderLabels(
                [_letra_columna(i) for i in range(self.tabla_editor.columnCount())])
        etiqueta = _EtiquetaImagenArrastrable(self, r1, col_ancla)
        etiqueta.setText(tipo)
        etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        etiqueta.setStyleSheet("border: 1px dashed #64748B; border-radius: 6px; padding: 6px;")
        etiqueta.setToolTip("Gráfico nativo de Excel: editable con todo detalle al abrir el archivo en Excel/LibreOffice. "
                           "(Aquí no hay Excel real disponible para mostrarlo en vivo -ver el aviso sobre la hoja-.) "
                           "Se puede arrastrar para reubicarlo, igual que una imagen.")
        self.tabla_editor.setRowHeight(r1, max(self.tabla_editor.rowHeight(r1), 70))
        self.tabla_editor.setColumnWidth(col_ancla, max(self.tabla_editor.columnWidth(col_ancla), 130))
        self.tabla_editor.setCellWidget(r1, col_ancla, etiqueta)
        mostrar_mensaje("exito", "Gráfico insertado",
                       "Se insertó un gráfico nativo de Excel con los datos seleccionados; se guardará "
                       "al presionar Guardar y se verá -y podrá seguir editando- con todo detalle en Excel.",
                       self._padre_dialogo())

    def _insertar_cuadro_texto_hoja(self):
        """Punto de entrada del botón "🔲 Cuadro de texto": como openpyxl no
        puede crear ni editar formas flotantes de manera confiable, se usa
        la alternativa práctica -una celda con relleno y borde propio-."""
        if not self._seleccion_valida():
            return
        fila, col = self._celda_actual_o_primera_seleccion()
        texto, ok = QInputDialog.getMultiLineText(
            self._padre_dialogo(), "Cuadro de texto", "Escribe el contenido del cuadro de texto:")
        if not ok or not texto.strip():
            return
        self._insertar_cuadro_texto_openpyxl(fila, col, texto)

    def _insertar_cuadro_texto_openpyxl(self, fila, col, texto):
        """Como openpyxl no puede crear ni editar formas flotantes de forma
        confiable, se usa una alternativa práctica y 100% compatible: una
        celda con relleno y borde propio para texto libre, que se comporta
        visualmente como un cuadro de texto."""
        item = self.tabla_editor.item(fila, col)
        if item is None:
            item = QTableWidgetItem("")
            self.tabla_editor.setItem(fila, col, item)
        self._sincronizando = True
        item.setData(ROL_CRUDO, texto)
        item.setData(ROL_FORMATO_NUM, None)
        item.setData(ROL_ES_CUADRO_TEXTO, True)
        color_fondo = QColor("#FEF9C3")
        item.setBackground(color_fondo)
        item.setForeground(_color_texto_contrastado(color_fondo))
        f = item.font(); f.setItalic(True); item.setFont(f)
        item.setText(texto)
        item.setToolTip("Cuadro de texto (celda con relleno y borde: openpyxl no puede crear formas flotantes "
                        "reales). Se puede arrastrar con clic sostenido a otra celda, igual que una imagen.")
        self._sincronizando = False
        self.tabla_editor.setRowHeight(fila, max(self.tabla_editor.rowHeight(fila), 20 * (texto.count("\n") + 2)))

    def _insertar_operacion_rapida(self, funcion_excel):
        """Autosuma-como-en-Excel: toma el rango seleccionado y, sin que la
        persona escriba ninguna fórmula, inserta el resultado -como una
        fórmula real y recalculable- justo debajo (si la selección es más
        alta que ancha) o a la derecha (si es más ancha que alta) de ella."""
        rango = self._rango_seleccionado()
        if rango is None:
            mostrar_mensaje("advertencia", "Selecciona un rango",
                           "Selecciona primero las celdas (una fila o columna, por ejemplo) sobre las que "
                           "quieres calcular la operación.", self._padre_dialogo())
            return
        r1, r2, c1, c2 = rango
        inicio = f"{_letra_columna(c1)}{r1 + 1}"
        fin = f"{_letra_columna(c2)}{r2 + 1}"
        formula = f"={funcion_excel}({inicio}:{fin})" if (r1, c1) != (r2, c2) else f"={funcion_excel}({inicio})"
        self._colocar_resultado_operacion(rango, formula)

    def _insertar_operacion_encadenada(self, operador):
        """Restar/Dividir no tienen una función nativa de Excel que acepte un
        rango entero (a diferencia de SUMA o PRODUCTO), así que se arma una
        fórmula explícita encadenando cada celda del rango con el operador,
        p.ej. "=A1-A2-A3" o "=A1/A2/A3" -100% compatible con Excel real,
        sin inventar ninguna función que Excel no reconocería-."""
        rango = self._rango_seleccionado()
        if rango is None:
            mostrar_mensaje("advertencia", "Selecciona un rango",
                           "Selecciona primero las celdas sobre las que quieres calcular la operación "
                           "(el resultado se calcula en el orden en que aparecen: la primera menos/entre las demás).",
                           self._padre_dialogo())
            return
        r1, r2, c1, c2 = rango
        referencias = []
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                referencias.append(f"{_letra_columna(c)}{r + 1}")
        if len(referencias) < 2:
            mostrar_mensaje("advertencia", "Selecciona al menos 2 celdas",
                           "Esta operación necesita al menos dos celdas para poder restar/dividir entre ellas.",
                           self._padre_dialogo())
            return
        formula = "=" + f" {operador} ".join(referencias).replace(" ", "")
        self._colocar_resultado_operacion(rango, formula)

    def _colocar_resultado_operacion(self, rango, formula):
        """Inserta `formula` en una celda nueva justo debajo (selección más
        alta que ancha) o a la derecha (más ancha que alta) del `rango`
        dado, agregando una fila/columna si hace falta para no pisar datos
        existentes -igual que hace Excel con el botón de Autosuma-."""
        self._registrar_deshacer_hoja()
        r1, r2, c1, c2 = rango
        vertical = (r2 - r1) >= (c2 - c1)

        self._sincronizando = True
        try:
            if vertical:
                fila_destino = r2 + 1
                if fila_destino >= self.tabla_editor.rowCount() or self._celda_ocupada(fila_destino, c1):
                    self.tabla_editor.insertRow(fila_destino)
                    for c in range(self.tabla_editor.columnCount()):
                        self.tabla_editor.setItem(fila_destino, c, QTableWidgetItem(""))
                destino_r, destino_c = fila_destino, c1
            else:
                col_destino = c2 + 1
                if col_destino >= self.tabla_editor.columnCount() or self._celda_ocupada(r1, col_destino):
                    self.tabla_editor.insertColumn(col_destino)
                    self.tabla_editor.setHorizontalHeaderLabels(
                        [_letra_columna(i) for i in range(self.tabla_editor.columnCount())])
                    for r in range(self.tabla_editor.rowCount()):
                        self.tabla_editor.setItem(r, col_destino, QTableWidgetItem(""))
                destino_r, destino_c = r1, col_destino

            item_destino = self.tabla_editor.item(destino_r, destino_c)
            if item_destino is None:
                item_destino = QTableWidgetItem("")
                self.tabla_editor.setItem(destino_r, destino_c, item_destino)
            item_destino.setData(ROL_CRUDO, formula)
            item_destino.setData(ROL_FORMATO_NUM, None)
        finally:
            self._sincronizando = False

        self._recalcular_hoja()
        self.tabla_editor.setCurrentCell(destino_r, destino_c)
        self.tabla_editor.scrollToItem(item_destino)

    def _celda_ocupada(self, fila, col):
        if fila < 0 or col < 0 or fila >= self.tabla_editor.rowCount() or col >= self.tabla_editor.columnCount():
            return False
        item = self.tabla_editor.item(fila, col)
        return item is not None and item.text().strip() != ""

    def _cambiar_hoja(self, nombre_hoja):
        if self._wb is None or not nombre_hoja or self._sincronizando:
            return
        if self._hoja_actual and self._hoja_actual in self._wb.sheetnames:
            self._sincronizar_grid_a_hoja(self._hoja_actual)
        self._cargar_hoja(nombre_hoja)

    # Formatos de número de Excel usados al guardar, según la categoría
    # detectada/asignada a cada celda (ver ROL_FORMATO_NUM).
    _FORMATOS_NUMERO_EXCEL = {
        "moneda": '"$"#,##0.00',
        "porcentaje": "0.00%",
        "fecha": "dd/mm/yyyy",
    }

    def _sincronizar_grid_a_hoja(self, nombre_hoja):
        """Vuelca lo que hay en la tabla visible sobre la hoja de openpyxl en
        memoria: valores/fórmulas con su TIPO real (número, fecha, booleano,
        fórmula) -no como texto plano-, su formato de número (moneda,
        porcentaje, fecha) y el formato básico (negrita/cursiva/relleno)."""
        if self._wb is None or nombre_hoja not in self._wb.sheetnames:
            return
        from openpyxl.styles import Font, PatternFill
        ws = self._wb[nombre_hoja]
        filas = self.tabla_editor.rowCount()
        columnas = self.tabla_editor.columnCount()
        for r in range(filas):
            for c in range(columnas):
                item = self.tabla_editor.item(r, c)
                celda = ws.cell(row=r + 1, column=c + 1)
                if item is None:
                    celda.value = None
                    continue
                crudo = item.data(ROL_CRUDO)
                if crudo is None:
                    crudo = item.text()
                formato_cat = item.data(ROL_FORMATO_NUM)
                if isinstance(crudo, str) and crudo.strip().startswith("=") and len(crudo.strip()) > 1:
                    # Fórmula: se guarda tal cual -openpyxl la escribe como
                    # una fórmula real de Excel, que se recalculará al abrir
                    # el archivo en Excel/Sheets/LibreOffice.
                    celda.value = crudo.strip()
                else:
                    valor_tipado, formato_sugerido = _analizar_crudo(crudo)
                    celda.value = valor_tipado
                    formato_cat = formato_cat or formato_sugerido
                if formato_cat in self._FORMATOS_NUMERO_EXCEL:
                    celda.number_format = self._FORMATOS_NUMERO_EXCEL[formato_cat]
                fuente = item.font()
                fondo_brush = item.background()
                color_texto_brush = item.foreground()
                # Antes se reconstruía el Font desde cero en TODAS las
                # celdas (incluso sin ningún cambio de formato), perdiendo
                # el nombre de fuente/tamaño original del archivo, y sin
                # guardar el subrayado -por eso "U" no se conservaba al
                # guardar-. Ahora se preserva nombre/tamaño/color existentes
                # y se agrega underline.
                nombre_fuente = fuente.family() or (celda.font.name if celda.font else None)
                tamano_fuente = fuente.pointSize() if fuente.pointSize() > 0 else (celda.font.size if celda.font else None)
                color_fuente = celda.font.color if celda.font else None
                # BUG GRAVE arreglado aquí: un QBrush() "vacío" (estilo
                # NoBrush, es decir NUNCA se llamó setForeground/setBackground
                # en esa celda) igual devuelve un QColor "válido" al pedir
                # .color() -por defecto NEGRO opaco (alpha 255)-. Antes solo
                # se comprobaba isValid()/alpha()>0, que es cierto para ESE
                # negro por defecto también, así que prácticamente TODA
                # celda sin formato terminaba guardándose con relleno negro
                # sólido -eso era lo que dejaba el archivo casi completamente
                # negro al abrirlo en Excel real-. Ahora se exige además que
                # el estilo del brush NO sea NoBrush, o sea que alguien de
                # verdad haya llamado setBackground/setForeground en esa
                # celda (el color de relleno del propio "🎨 Relleno", el
                # resaltado de cuadro de texto, etc.).
                if (color_texto_brush.style() != Qt.BrushStyle.NoBrush and
                        color_texto_brush.color().isValid() and color_texto_brush.color().alpha() > 0):
                    color_fuente = "FF" + color_texto_brush.color().name().lstrip("#").upper()
                celda.font = Font(name=nombre_fuente, size=tamano_fuente, bold=fuente.bold(),
                                   italic=fuente.italic(), underline="single" if fuente.underline() else None,
                                   color=color_fuente)
                if (fondo_brush.style() != Qt.BrushStyle.NoBrush and
                        fondo_brush.color().isValid() and fondo_brush.color().alpha() > 0):
                    fondo = fondo_brush.color()
                    # openpyxl espera ARGB de 8 dígitos; QColor.name() devuelve
                    # "#RRGGBB" (6 dígitos sin alpha). Si se pasan solo 6 dígitos,
                    # openpyxl rellena con "00" al frente → alpha=0 → transparente
                    # → Excel no muestra ningún relleno. Se antepone "FF" para
                    # indicar opacidad total y que el color se vea en Excel.
                    hex_fondo = "FF" + fondo.name().lstrip("#").upper()
                    celda.fill = PatternFill(start_color=hex_fondo,
                                              end_color=hex_fondo, fill_type="solid")
                else:
                    celda.fill = PatternFill(fill_type=None)
                enlace = item.data(ROL_HIPERVINCULO)
                if enlace:
                    celda.hyperlink = enlace
                elif celda.hyperlink is not None:
                    celda.hyperlink = None
        if self.chk_congelar_encabezado.isChecked():
            ws.freeze_panes = "A2"
        else:
            ws.freeze_panes = None
        if self.chk_autofiltro.isChecked() and filas > 0 and columnas > 0:
            ws.auto_filter.ref = ws.dimensions
        else:
            ws.auto_filter.ref = None

    # ------------------------------------------------------------
    # Utilidades comunes de la tabla (CSV y XLSX comparten grilla)
    # ------------------------------------------------------------
    def _poblar_tabla(self, filas):
        self._sincronizando = True
        self.tabla_editor.clear()
        n_filas = len(filas)
        n_columnas = max((len(f) for f in filas), default=0)
        self.tabla_editor.setUpdatesEnabled(False)
        self.tabla_editor.blockSignals(True)
        self.tabla_editor.setRowCount(n_filas)
        self.tabla_editor.setColumnCount(n_columnas)
        self.tabla_editor.setHorizontalHeaderLabels([_letra_columna(i) for i in range(n_columnas)])
        hay_formulas = False
        for r, fila in enumerate(filas):
            for c in range(n_columnas):
                valor = fila[c] if c < len(fila) else ""
                item = QTableWidgetItem("")
                item.setData(ROL_CRUDO, valor)
                es_formula = isinstance(valor, str) and valor.strip().startswith("=") and len(valor.strip()) > 1
                hay_formulas = hay_formulas or es_formula
                if not es_formula:
                    item.setText(str(valor) if valor is not None else "")
                self.tabla_editor.setItem(r, c, item)
        self.tabla_editor.blockSignals(False)
        self.tabla_editor.setUpdatesEnabled(True)
        self._autoajustar_columnas()
        if hay_formulas:
            self._recalcular_hoja()
        self._sincronizando = False
        self.lbl_celdas.setText(f"{n_filas} filas × {n_columnas} columnas")

    def _extraer_filas_de_tabla(self):
        """Filas con el texto TAL COMO SE VE en la grilla (valores ya
        calculados/formateados) -lo que corresponde al exportar a CSV, que
        no admite fórmulas ni tipos propios."""
        filas = []
        for r in range(self.tabla_editor.rowCount()):
            fila = []
            for c in range(self.tabla_editor.columnCount()):
                item = self.tabla_editor.item(r, c)
                fila.append(item.text() if item else "")
            filas.append(fila)
        return filas

    def _extraer_filas_crudas_de_tabla(self):
        """Filas con el contenido CRUDO de cada celda (fórmulas incluidas,
        valores ya tipados) -lo que corresponde al exportar/guardar a Excel."""
        filas = []
        for r in range(self.tabla_editor.rowCount()):
            fila = []
            for c in range(self.tabla_editor.columnCount()):
                item = self.tabla_editor.item(r, c)
                crudo = item.data(ROL_CRUDO) if item else None
                if crudo is None and item is not None:
                    crudo = item.text()
                fila.append(crudo)
            filas.append(fila)
        return filas

    def _on_celda_editada(self, item):
        if self._sincronizando or self._recalculando:
            return
        # El delegado de edición (_DelegadoHojaCalculo) deja en item.text()
        # justo lo que la persona escribió (fórmula o valor crudo, no un
        # resultado ya calculado); lo guardamos como el nuevo "crudo" de la
        # celda y recalculamos toda la hoja -las fórmulas de otras celdas
        # pueden depender de esta-.
        nuevo_crudo = item.text()
        formato_anterior = item.data(ROL_FORMATO_NUM)
        # El formato (moneda/porcentaje) de una celda se CONSERVA al volver
        # a editarla, salvo que lo que se escribió traiga una marca de
        # formato explícita distinta (p.ej. escribir "$50" en una celda que
        # era porcentaje). Así, si al editar una celda en "18%" se confirma
        # sin tocar nada (o cambiando solo el número), la celda vuelve a
        # mostrarse como porcentaje en vez de quedar "pelada".
        valor_tipado, formato_sugerido = _analizar_crudo(nuevo_crudo)
        # CASO ESPECIAL -porcentaje-: a diferencia de la moneda (que solo
        # antepone "$" sin tocar el valor), el formato porcentaje SÍ
        # reescala el valor mostrado (x100). Si la celda ya era porcentaje
        # y se escribió un número "pelado" (sin el símbolo %), hay que
        # tratarlo tal como lo haría Excel: escribir "50" sobre una celda
        # porcentaje da 50% (0.50), NO 5000%. Sin este ajuste, el valor
        # crudo se guardaría tal cual (50) pero se MOSTRARÍA multiplicado
        # por 100 igual, dando un resultado disparatado en pantalla -y en
        # cualquier fórmula que dependa de esta celda-.
        if (formato_sugerido is None and formato_anterior == "porcentaje"
                and isinstance(valor_tipado, (int, float)) and not isinstance(valor_tipado, bool)):
            nuevo_crudo = f"{nuevo_crudo.strip()}%"
            formato_sugerido = "porcentaje"
        item.setData(ROL_CRUDO, nuevo_crudo)
        item.setData(ROL_FORMATO_NUM, formato_sugerido or formato_anterior)
        self._recalcular_hoja()

    def _recalcular_hoja(self):
        """Recorre toda la grilla, evalúa las fórmulas con el motor propio
        (_MotorFormulas) y actualiza el texto visible de cada celda con el
        resultado ya formateado (moneda/porcentaje/fecha/número/texto).
        Es el corazón de "que las operaciones matemáticas se efectúen"."""
        self._recalculando = True
        # OPTIMIZACIÓN: esta función se llama en CADA edición de celda (una
        # hoja grande puede tener miles de celdas), y antes no bloqueaba
        # señales ni el repintado -cada item.setText() disparaba un
        # itemChanged (que _on_celda_editada descarta enseguida por
        # _recalculando, pero el propio despacho de la señal ya cuesta
        # tiempo) y un repintado parcial. Igual que en la carga inicial, se
        # bloquean señales/actualizaciones mientras se recalculan todas las
        # celdas, y se reactivan al final.
        self.tabla_editor.blockSignals(True)
        self.tabla_editor.setUpdatesEnabled(False)
        try:
            filas = self.tabla_editor.rowCount()
            columnas = self.tabla_editor.columnCount()

            def obtener_crudo(r, c):
                if r < 0 or c < 0 or r >= filas or c >= columnas:
                    return None
                it = self.tabla_editor.item(r, c)
                if it is None:
                    return None
                crudo = it.data(ROL_CRUDO)
                if crudo is None:
                    crudo = it.text() or None
                    # El texto mostrado NUNCA debe alimentar el motor cuando
                    # es un error de fórmula ya renderizado ("#¡DIV/0!",
                    # "#¡CIRC!", "#¿NOMBRE?"...): si una celda quedó con un
                    # error de una pasada anterior y su crudo se perdió,
                    # devolver el string del error convertía ese error en
                    # un "valor" que se propagaba en cadena a TODAS las
                    # fórmulas vecinas (los #¡DIV/0! y #¡CIRC! fantasma que
                    # aparecían al ordenar/autoajustar). Se trata como celda
                    # vacía y punto.
                    if isinstance(crudo, str) and crudo.startswith("#") and any(
                            s in crudo for s in ("¡", "¿", "/")):
                        return None
                return crudo

            motor = _MotorFormulas(obtener_crudo)
            for r in range(filas):
                for c in range(columnas):
                    item = self.tabla_editor.item(r, c)
                    if item is None:
                        continue
                    crudo = item.data(ROL_CRUDO)
                    if crudo is None:
                        crudo = item.text()
                        item.setData(ROL_CRUDO, crudo if crudo != "" else None)
                    formato_cat = item.data(ROL_FORMATO_NUM)
                    es_formula = isinstance(crudo, str) and crudo.strip().startswith("=") and len(crudo.strip()) > 1
                    if es_formula:
                        valor = motor.valor_celda(r, c)
                        # Si nuestro motor no pudo resolverla (función no
                        # soportada, etc.) pero el propio Excel había dejado
                        # un resultado calculado en caché, se usa ese como
                        # respaldo -para no mostrar un error donde Excel no
                        # lo mostraría-.
                        if isinstance(valor, _ErrorFormulaValor) and valor.codigo == "#¿NOMBRE?":
                            respaldo = item.data(ROL_VALOR_CACHE)
                            if respaldo is not None:
                                valor = respaldo
                    else:
                        valor, formato_sugerido = _analizar_crudo(crudo)
                        if formato_cat is None and formato_sugerido is not None:
                            formato_cat = formato_sugerido
                            item.setData(ROL_FORMATO_NUM, formato_cat)
                    texto_mostrar = _formatear_para_mostrar(valor, formato_cat)
                    if item.text() != texto_mostrar:
                        item.setText(texto_mostrar)
                    es_numero = isinstance(valor, (int, float)) and not isinstance(valor, bool)
                    alineacion = (Qt.AlignmentFlag.AlignRight if es_numero else Qt.AlignmentFlag.AlignLeft)
                    item.setTextAlignment(int(alineacion | Qt.AlignmentFlag.AlignVCenter))
        finally:
            self.tabla_editor.blockSignals(False)
            self.tabla_editor.setUpdatesEnabled(True)
            self._recalculando = False

    def _seleccion_valida(self):
        if self.tabla_editor.rowCount() == 0 or self.tabla_editor.columnCount() == 0:
            mostrar_mensaje("advertencia", "Sin datos", "Abre primero un archivo con contenido.", self._padre_dialogo())
            return False
        return True

    def _insertar_fila(self):
        if not self._seleccion_valida():
            return
        self._registrar_deshacer_hoja()
        fila = self.tabla_editor.currentRow()
        pos = fila + 1 if fila >= 0 else self.tabla_editor.rowCount()
        self.tabla_editor.insertRow(pos)
        for c in range(self.tabla_editor.columnCount()):
            self.tabla_editor.setItem(pos, c, QTableWidgetItem(""))
        self.lbl_celdas.setText(f"{self.tabla_editor.rowCount()} filas × {self.tabla_editor.columnCount()} columnas")
        # Nota: al igual que un "pegado de valores" en Excel, las fórmulas
        # existentes NO desplazan automáticamente sus referencias al
        # insertar filas/columnas -se recalcula igualmente para que la hoja
        # quede internamente consistente con las posiciones nuevas-.
        self._recalcular_hoja()

    def _eliminar_fila(self):
        filas = sorted({i.row() for i in self.tabla_editor.selectedIndexes()}, reverse=True)
        if not filas:
            mostrar_mensaje("advertencia", "Selecciona una fila", "Selecciona primero la(s) fila(s) a eliminar.", self._padre_dialogo())
            return
        self._registrar_deshacer_hoja()
        for f in filas:
            self.tabla_editor.removeRow(f)
        self.lbl_celdas.setText(f"{self.tabla_editor.rowCount()} filas × {self.tabla_editor.columnCount()} columnas")
        self._recalcular_hoja()

    def _insertar_columna(self):
        if not self._seleccion_valida():
            return
        self._registrar_deshacer_hoja()
        col = self.tabla_editor.currentColumn()
        pos = col + 1 if col >= 0 else self.tabla_editor.columnCount()
        self.tabla_editor.insertColumn(pos)
        for r in range(self.tabla_editor.rowCount()):
            self.tabla_editor.setItem(r, pos, QTableWidgetItem(""))
        self.tabla_editor.setHorizontalHeaderLabels(
            [_letra_columna(i) for i in range(self.tabla_editor.columnCount())])
        self._recalcular_hoja()

    def _eliminar_columna(self):
        columnas = sorted({i.column() for i in self.tabla_editor.selectedIndexes()}, reverse=True)
        if not columnas:
            mostrar_mensaje("advertencia", "Selecciona una columna", "Selecciona primero la(s) columna(s) a eliminar.", self._padre_dialogo())
            return
        self._registrar_deshacer_hoja()
        for c in columnas:
            self.tabla_editor.removeColumn(c)
        self.tabla_editor.setHorizontalHeaderLabels(
            [_letra_columna(i) for i in range(self.tabla_editor.columnCount())])
        self._recalcular_hoja()

    def _borrar_contenido_celdas_seleccionadas(self):
        """Comportamiento de la tecla Delete en Excel real: borra el VALOR
        de las celdas seleccionadas, pero conserva su formato (color,
        negrita, etc.) -a propósito no usa _celdas_seleccionadas() porque
        esa muestra un aviso si no hay selección, y aquí eso sería molesto
        (la tecla Delete puede presionarse sin querer sin nada seleccionado)."""
        items = self.tabla_editor.selectedItems()
        if not items:
            return
        self._registrar_deshacer_hoja()
        self._sincronizando = True
        for item in items:
            item.setData(ROL_CRUDO, None)
            item.setData(ROL_FORMATO_NUM, None)
            item.setData(ROL_ES_CUADRO_TEXTO, None)
            item.setText("")
        self._sincronizando = False
        self._recalcular_hoja()

    def _celdas_seleccionadas(self):
        tabla = self.tabla_editor
        rangos = tabla.selectedRanges()
        if not rangos:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una o varias celdas primero.", self._padre_dialogo())
            return []
        # Antes se usaba selectedItems(), que SOLO devuelve celdas que ya
        # tienen un QTableWidgetItem creado -las celdas vacías de una fila o
        # columna (sin ningún valor escrito) nunca lo tienen, así que al
        # colorear "toda la fila/columna" esas celdas vacías se quedaban sin
        # pintar y el resultado se veía a rayas/incompleto. Aquí se recorre
        # el RANGO seleccionado (no solo los ítems existentes) y se crea un
        # ítem vacío donde falte, para que el color/formato cubra la
        # selección completa tal como se ve en Excel.
        self._sincronizando = True
        for rango in rangos:
            for r in range(rango.topRow(), rango.bottomRow() + 1):
                for c in range(rango.leftColumn(), rango.rightColumn() + 1):
                    if tabla.item(r, c) is None:
                        tabla.setItem(r, c, QTableWidgetItem(""))
        self._sincronizando = False
        items = tabla.selectedItems()
        if not items:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una o varias celdas primero.", self._padre_dialogo())
        return items

    # ------------------------------------------------------------
    # PORTAPAPELES DE LA HOJA (clic derecho: cortar/copiar/pegar/eliminar/operación)
    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # DESHACER / REHACER (hoja de cálculo)
    # ------------------------------------------------------------
    # Estrategia: instantánea completa de la hoja antes de cada acción, no
    # un diff puntual por celda. Estas hojas son chicas (decenas de filas x
    # columnas, no miles), así que el costo de memoria es insignificante, y
    # a cambio el undo cubre CUALQUIER tipo de acción -escribir, pegar,
    # rellenar, formato, colores, insertar/eliminar filas o columnas,
    # ordenar, buscar y reemplazar, operaciones rápidas...- sin tener que
    # programar la lógica de deshacer por separado para cada una.
    LIMITE_DESHACER_HOJA = 50

    def _capturar_snapshot_hoja(self):
        filas, columnas = self.tabla_editor.rowCount(), self.tabla_editor.columnCount()
        datos = []
        for r in range(filas):
            fila = []
            for c in range(columnas):
                item = self.tabla_editor.item(r, c)
                if item is None:
                    fila.append(None)
                    continue
                fila.append({
                    "crudo": item.data(ROL_CRUDO),
                    "formato_num": item.data(ROL_FORMATO_NUM),
                    "tamano_base": item.data(ROL_TAMANO_BASE),
                    "es_cuadro_texto": item.data(ROL_ES_CUADRO_TEXTO),
                    "hipervinculo": item.data(ROL_HIPERVINCULO),
                    "fondo": item.background(),
                    "frente": item.foreground(),
                    "fuente": item.font(),
                    "alineacion": item.textAlignment(),
                })
            datos.append(fila)
        return {"filas": filas, "columnas": columnas, "datos": datos}

    def _restaurar_snapshot_hoja(self, snap):
        self._sincronizando = True
        self.tabla_editor.setRowCount(snap["filas"])
        self.tabla_editor.setColumnCount(snap["columnas"])
        for r, fila in enumerate(snap["datos"]):
            for c, celda in enumerate(fila):
                item = self.tabla_editor.item(r, c)
                if celda is None:
                    if item is not None:
                        item.setData(ROL_CRUDO, None)
                        item.setData(ROL_FORMATO_NUM, None)
                        item.setData(ROL_TAMANO_BASE, None)
                        item.setData(ROL_ES_CUADRO_TEXTO, None)
                        item.setData(ROL_HIPERVINCULO, None)
                        item.setText("")
                    continue
                if item is None:
                    item = QTableWidgetItem("")
                    self.tabla_editor.setItem(r, c, item)
                item.setData(ROL_CRUDO, celda["crudo"])
                item.setData(ROL_FORMATO_NUM, celda["formato_num"])
                item.setData(ROL_TAMANO_BASE, celda["tamano_base"])
                item.setData(ROL_ES_CUADRO_TEXTO, celda["es_cuadro_texto"])
                item.setData(ROL_HIPERVINCULO, celda.get("hipervinculo"))
                item.setBackground(celda["fondo"])
                item.setForeground(celda["frente"])
                item.setFont(celda["fuente"])
                if celda["alineacion"]:
                    item.setTextAlignment(int(celda["alineacion"]))
        self._sincronizando = False
        self._recalcular_hoja()
        self._actualizar_manija_relleno()

    def _registrar_deshacer_hoja(self):
        """Guarda el estado ACTUAL de la hoja en la pila de deshacer, antes
        de aplicar un cambio -se llama al INICIO de cada acción que
        modifica la hoja, antes de que el cambio ocurra."""
        self._pila_deshacer_hoja.append(self._capturar_snapshot_hoja())
        if len(self._pila_deshacer_hoja) > self.LIMITE_DESHACER_HOJA:
            self._pila_deshacer_hoja.pop(0)
        self._pila_rehacer_hoja.clear()  # un cambio nuevo invalida el "rehacer" pendiente
        self._actualizar_botones_deshacer()

    def _deshacer_hoja(self):
        if not self._pila_deshacer_hoja:
            return
        self._pila_rehacer_hoja.append(self._capturar_snapshot_hoja())
        self._restaurar_snapshot_hoja(self._pila_deshacer_hoja.pop())
        self._actualizar_botones_deshacer()

    def _rehacer_hoja(self):
        if not self._pila_rehacer_hoja:
            return
        self._pila_deshacer_hoja.append(self._capturar_snapshot_hoja())
        self._restaurar_snapshot_hoja(self._pila_rehacer_hoja.pop())
        self._actualizar_botones_deshacer()

    def _color_acento_actual(self):
        return _colores_tema(self.main_window)["accent"]

    def _extraer_bloque_hoja(self, fila_ini, fila_fin, col_ini, col_fin):
        """Snapshot completo (valor + formato de número + estilo) de un
        rango de celdas, para poder pegarlo tal cual -no solo el texto- en
        otro lugar de la hoja."""
        bloque = []
        for r in range(fila_ini, fila_fin + 1):
            fila = []
            for c in range(col_ini, col_fin + 1):
                item = self.tabla_editor.item(r, c)
                if item is None:
                    fila.append(None)
                    continue
                fila.append({
                    "crudo": item.data(ROL_CRUDO),
                    "formato_num": item.data(ROL_FORMATO_NUM),
                    "tamano_base": item.data(ROL_TAMANO_BASE),
                    "hipervinculo": item.data(ROL_HIPERVINCULO),
                    "fondo": item.background(),
                    "frente": item.foreground(),
                    "fuente": item.font(),
                    "alineacion": item.textAlignment(),
                })
            bloque.append(fila)
        return bloque

    def _bloque_a_texto_plano(self, bloque):
        """Igual que copia Excel al portapapeles del sistema: valores
        separados por tabulaciones/saltos de línea, para poder pegar hacia
        otra hoja externa (o pegar aquí lo copiado desde una externa)."""
        filas_txt = []
        for fila in bloque:
            celdas = []
            for celda in fila:
                crudo = celda["crudo"] if celda else None
                celdas.append(_texto_crudo_como_str(crudo) if crudo is not None else "")
            filas_txt.append("\t".join(celdas))
        return "\n".join(filas_txt)

    def _hoja_copiar_seleccion(self):
        rango = self._rango_seleccionado()
        if rango is None:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una o varias celdas primero.", self._padre_dialogo())
            return
        fila_ini, fila_fin, col_ini, col_fin = rango
        bloque = self._extraer_bloque_hoja(fila_ini, fila_fin, col_ini, col_fin)
        self._portapapeles_hoja = bloque
        QApplication.clipboard().setText(self._bloque_a_texto_plano(bloque))

    def _hoja_cortar_seleccion(self):
        rango = self._rango_seleccionado()
        if rango is None:
            mostrar_mensaje("advertencia", "Sin selección", "Selecciona una o varias celdas primero.", self._padre_dialogo())
            return
        self._hoja_copiar_seleccion()
        self._borrar_contenido_celdas_seleccionadas()

    def _combinar_operacion(self, crudo_actual, crudo_pegado, operacion):
        """'Pegado especial > Operación' de Excel: en vez de reemplazar el
        valor de la celda destino, lo combina matemáticamente con el
        pegado. Si cualquiera de los dos no es un número, se pega tal cual
        (no tiene sentido "sumar" texto)."""
        actual, _ = _analizar_crudo(crudo_actual)
        pegado, _ = _analizar_crudo(crudo_pegado)
        try:
            if actual is None:
                actual = 0.0
            if pegado is None:
                return crudo_pegado
            actual, pegado = float(actual), float(pegado)
        except (TypeError, ValueError):
            return crudo_pegado
        if operacion == "sumar":
            return actual + pegado
        if operacion == "restar":
            return actual - pegado
        if operacion == "multiplicar":
            return actual * pegado
        if operacion == "dividir":
            return actual / pegado if pegado != 0 else actual
        return pegado

    def _pegar_bloque_en(self, fila_destino, col_destino, bloque, operacion=None):
        """Pega `bloque` con su esquina superior izquierda en (fila_destino,
        col_destino), agregando filas/columnas a la hoja si hace falta."""
        if not bloque or not bloque[0]:
            return
        self._registrar_deshacer_hoja()
        filas_necesarias = fila_destino + len(bloque)
        cols_necesarias = col_destino + len(bloque[0])
        while self.tabla_editor.rowCount() < filas_necesarias:
            self.tabla_editor.insertRow(self.tabla_editor.rowCount())
        while self.tabla_editor.columnCount() < cols_necesarias:
            self.tabla_editor.insertColumn(self.tabla_editor.columnCount())
        self._sincronizando = True
        for dr, fila in enumerate(bloque):
            for dc, celda in enumerate(fila):
                r, c = fila_destino + dr, col_destino + dc
                item = self.tabla_editor.item(r, c)
                if item is None:
                    item = QTableWidgetItem("")
                    self.tabla_editor.setItem(r, c, item)
                if celda is None:
                    continue
                crudo_nuevo = celda["crudo"]
                if operacion is not None:
                    crudo_nuevo = self._combinar_operacion(item.data(ROL_CRUDO), crudo_nuevo, operacion)
                item.setData(ROL_CRUDO, crudo_nuevo)
                item.setData(ROL_FORMATO_NUM, celda["formato_num"])
                item.setData(ROL_TAMANO_BASE, celda["tamano_base"])
                item.setData(ROL_HIPERVINCULO, celda.get("hipervinculo"))
                if celda["fondo"] is not None:
                    item.setBackground(celda["fondo"])
                if celda["frente"] is not None:
                    item.setForeground(celda["frente"])
                if celda["fuente"] is not None:
                    item.setFont(celda["fuente"])
                if celda["alineacion"]:
                    item.setTextAlignment(int(celda["alineacion"]))
        self._sincronizando = False
        self._recalcular_hoja()

    def _hoja_pegar_seleccion(self, operacion=None):
        fila_destino, col_destino = self._celda_actual_o_primera_seleccion()
        bloque = getattr(self, "_portapapeles_hoja", None)
        if bloque is None:
            # Nada copiado dentro del editor: se intenta con el portapapeles
            # del sistema (texto separado por tabulaciones, como el que
            # copian Excel/Sheets), por si se está pegando desde afuera.
            texto = QApplication.clipboard().text()
            if not texto:
                return
            filas = [f.split("\t") for f in texto.replace("\r\n", "\n").rstrip("\n").split("\n")]
            ancho = max((len(f) for f in filas), default=0)
            bloque = [[{"crudo": (f[i] if i < len(f) and f[i] != "" else None), "formato_num": None,
                       "tamano_base": None, "fondo": None, "frente": None, "fuente": None, "alineacion": None}
                      for i in range(ancho)] for f in filas]
        self._pegar_bloque_en(fila_destino, col_destino, bloque, operacion)

    def _mostrar_menu_contextual_hoja(self, punto):
        """Menú de clic derecho sobre la hoja: cortar/copiar/pegar/pegado
        especial (operación)/∑ Operación (autosuma y similares)/eliminar
        contenido."""
        indice = self.tabla_editor.indexAt(punto)
        if indice.isValid() and not self.tabla_editor.selectionModel().isSelected(indice):
            self.tabla_editor.setCurrentCell(indice.row(), indice.column())
        hay_seleccion = self._rango_seleccionado() is not None
        hay_para_pegar = bool(getattr(self, "_portapapeles_hoja", None)) or bool(QApplication.clipboard().text())

        menu = QMenu(self.tabla_editor)
        accion_cortar = menu.addAction("Cortar")
        accion_cortar.setShortcut(QKeySequence.StandardKey.Cut)
        accion_cortar.setEnabled(hay_seleccion)
        accion_cortar.triggered.connect(self._hoja_cortar_seleccion)

        accion_copiar = menu.addAction("Copiar")
        accion_copiar.setShortcut(QKeySequence.StandardKey.Copy)
        accion_copiar.setEnabled(hay_seleccion)
        accion_copiar.triggered.connect(self._hoja_copiar_seleccion)

        accion_pegar = menu.addAction("Pegar")
        accion_pegar.setShortcut(QKeySequence.StandardKey.Paste)
        accion_pegar.setEnabled(hay_para_pegar)
        accion_pegar.triggered.connect(lambda: self._hoja_pegar_seleccion())

        menu_especial = menu.addMenu("Pegado especial (operación)")
        menu_especial.setEnabled(hay_para_pegar)
        for etiqueta, clave in (("Sumar", "sumar"), ("Restar", "restar"),
                                ("Multiplicar", "multiplicar"), ("Dividir", "dividir")):
            accion_op = menu_especial.addAction(etiqueta)
            accion_op.triggered.connect(lambda checked=False, op=clave: self._hoja_pegar_seleccion(operacion=op))

        menu.addSeparator()
        # Mismo menú "∑ Operación" que la barra de herramientas: calcula el
        # resultado del rango seleccionado (suma, promedio, etc.) y lo coloca
        # como fórmula justo al lado -no toca el contenido de la selección,
        # así que no depende de tener 2 celdas exactas para las funciones de
        # Excel (SUMA, PROMEDIO...); solo Restar/Dividir piden 2 o más-.
        menu_operacion = menu.addMenu("∑  Operación")
        menu_operacion.setEnabled(hay_seleccion)
        for etiqueta, funcion_excel in (
            ("Sumar (+)", "SUMA"), ("Multiplicar (×)", "PRODUCTO"),
            ("Promedio", "PROMEDIO"), ("Mínimo", "MIN"), ("Máximo", "MAX"),
            ("Contar números", "CONTAR"), ("Contar no vacías", "CONTARA"),
        ):
            accion_op = menu_operacion.addAction(etiqueta)
            accion_op.triggered.connect(lambda checked=False, f=funcion_excel: self._insertar_operacion_rapida(f))
        menu_operacion.addSeparator()
        for etiqueta, operador in (("Restar (−)", "-"), ("Dividir (÷)", "/")):
            accion_op = menu_operacion.addAction(etiqueta)
            accion_op.triggered.connect(lambda checked=False, op=operador: self._insertar_operacion_encadenada(op))

        menu.addSeparator()
        celda_bajo_cursor = self.tabla_editor.itemAt(punto)
        enlace_actual = celda_bajo_cursor.data(ROL_HIPERVINCULO) if celda_bajo_cursor else None
        if enlace_actual:
            accion_abrir_link = menu.addAction("Abrir enlace")
            accion_editar_link = menu.addAction("Editar hipervínculo…")
            accion_quitar_link = menu.addAction("Quitar hipervínculo")
            accion_abrir_link.triggered.connect(lambda: abrir_enlace_externo(enlace_actual, self))
            accion_editar_link.triggered.connect(lambda: self._hoja_insertar_enlace(celda_bajo_cursor))
            accion_quitar_link.triggered.connect(lambda: self._hoja_quitar_enlace(celda_bajo_cursor))
        else:
            accion_link = menu.addAction("Insertar hipervínculo…")
            accion_link.setEnabled(hay_seleccion)
            accion_link.triggered.connect(lambda: self._hoja_insertar_enlace())

        menu.addSeparator()
        accion_eliminar = menu.addAction("Eliminar contenido")
        accion_eliminar.setShortcut(QKeySequence.StandardKey.Delete)
        accion_eliminar.setEnabled(hay_seleccion)
        accion_eliminar.triggered.connect(self._borrar_contenido_celdas_seleccionadas)

        menu.exec(self.tabla_editor.viewport().mapToGlobal(punto))

    # ------------------------------------------------------------
    # MANIJA DE RELLENO (fill handle: arrastrar hacia abajo para autocompletar)
    # ------------------------------------------------------------
    _RE_TEXTO_NUM_FINAL = re.compile(r"^(.*?)(\d+)(\D*)$")
    _RE_REF_CELDA_FORMULA = re.compile(r"(\$?)([A-Za-z]{1,3})(\$?)(\d+)")

    def _desplazar_referencias_formula(self, formula, delta_fila):
        """Ajusta las referencias de FILA de una fórmula al copiarla hacia
        abajo -'=A5+B5' arrastrada una fila hacia abajo pasa a '=A6+B6'-,
        respetando las referencias absolutas ($A$5 o A$5 no se mueven),
        igual que Excel al arrastrar el relleno."""
        def reemplazar(m):
            abs_col, letras, abs_fila, numero = m.groups()
            if abs_fila == "$":
                return m.group(0)
            nuevo = int(numero) + delta_fila
            if nuevo < 1:
                return m.group(0)
            return f"{abs_col}{letras}{abs_fila}{nuevo}"
        return self._RE_REF_CELDA_FORMULA.sub(reemplazar, formula)

    def _actualizar_manija_relleno(self):
        """Reposiciona (o esconde) el cuadradito de relleno según la
        selección actual -esquina inferior derecha del rango seleccionado."""
        if getattr(self, "_arrastrando_relleno", False):
            return
        if self.stack.currentIndex() != 1:  # solo aplica en la pestaña de hoja
            self._manija_relleno.hide()
            return
        rango = self._rango_seleccionado()
        if rango is None:
            self._manija_relleno.hide()
            return
        _fi, fila_fin, _ci, col_fin = rango
        rect = self.tabla_editor.visualRect(self.tabla_editor.model().index(fila_fin, col_fin))
        if not rect.isValid() or rect.isEmpty():
            self._manija_relleno.hide()
            return
        mitad = _ManijaRelleno.TAMANO // 2
        self._manija_relleno.move(rect.right() - mitad + 1, rect.bottom() - mitad + 1)
        self._manija_relleno.show()
        self._manija_relleno.raise_()

    def _iniciar_arrastre_relleno(self):
        rango = self._rango_seleccionado()
        if rango is None:
            return
        self._arrastrando_relleno = True
        self._relleno_origen = rango
        self._relleno_fila_hasta = rango[1]

    def _arrastrar_relleno(self, punto_global):
        if not getattr(self, "_arrastrando_relleno", False) or self._relleno_origen is None:
            return
        fila_ini, fila_fin, col_ini, col_fin = self._relleno_origen
        punto_local = self.tabla_editor.viewport().mapFromGlobal(punto_global)
        fila_bajo_cursor = self.tabla_editor.rowAt(punto_local.y())
        if fila_bajo_cursor == -1:
            ultima_fila = self.tabla_editor.rowCount() - 1
            rect_ultima = self.tabla_editor.visualRect(self.tabla_editor.model().index(ultima_fila, col_fin))
            if punto_local.y() > rect_ultima.bottom():
                # Se arrastró más abajo de la última fila: se extiende la
                # hoja (como en Excel real), estimando cuántas filas nuevas
                # hacen falta según la altura de fila -con un tope para que
                # un arrastre accidental no cree miles de filas de golpe-.
                alto_fila = max(1, rect_ultima.height())
                filas_extra = min(500, max(1, round((punto_local.y() - rect_ultima.bottom()) / alto_fila)))
                fila_bajo_cursor = ultima_fila + filas_extra
            else:
                fila_bajo_cursor = ultima_fila
        fila_hasta = max(fila_fin, fila_bajo_cursor)  # el relleno solo se extiende hacia ABAJO
        if fila_hasta == self._relleno_fila_hasta:
            return
        self._relleno_fila_hasta = fila_hasta
        if fila_hasta >= self.tabla_editor.rowCount():
            self.tabla_editor.setRowCount(fila_hasta + 1)
        self.tabla_editor.blockSignals(True)
        self.tabla_editor.clearSelection()
        self.tabla_editor.setRangeSelected(
            QTableWidgetSelectionRange(fila_ini, col_ini, fila_hasta, col_fin), True)
        self.tabla_editor.blockSignals(False)
        mitad = _ManijaRelleno.TAMANO // 2
        rect = self.tabla_editor.visualRect(self.tabla_editor.model().index(fila_hasta, col_fin))
        if rect.isValid():
            self._manija_relleno.move(rect.right() - mitad + 1, rect.bottom() - mitad + 1)

    def _soltar_relleno(self):
        origen = self._relleno_origen
        fila_hasta = self._relleno_fila_hasta
        self._arrastrando_relleno = False
        self._relleno_origen = None
        self._relleno_fila_hasta = None
        if origen is not None and fila_hasta is not None and fila_hasta > origen[1]:
            self._aplicar_relleno(*origen, fila_hasta)
        self._actualizar_manija_relleno()

    def _aplicar_relleno(self, fila_ini, fila_fin, col_ini, col_fin, fila_hasta):
        """Autocompleta hacia abajo desde el patrón (fila_ini..fila_fin) de
        cada columna del rango:
        - Si el patrón son puras fórmulas, las copia ajustando referencias.
        - Si es una secuencia numérica (2+ filas con el mismo "paso" entre
          ellas, ej. 1,2 o 5,10), continúa la progresión.
        - Si es una sola celda de texto terminado en número (ej. "Fila 1"),
          incrementa el número.
        - En cualquier otro caso, repite el patrón en ciclo (como hace
          Excel con un patrón de varias filas sin secuencia detectable).
        El formato/estilo de cada celda rellenada siempre se copia del
        patrón (cíclicamente), sin importar cuál de los casos anteriores
        aplique."""
        self._registrar_deshacer_hoja()
        if fila_hasta >= self.tabla_editor.rowCount():
            self.tabla_editor.setRowCount(fila_hasta + 1)
        alto_patron = fila_fin - fila_ini + 1
        self._sincronizando = True
        for c in range(col_ini, col_fin + 1):
            patron = []
            for r in range(fila_ini, fila_fin + 1):
                item = self.tabla_editor.item(r, c)
                if item is None:
                    item = QTableWidgetItem("")
                    self.tabla_editor.setItem(r, c, item)
                patron.append(item)
            crudos = [it.data(ROL_CRUDO) for it in patron]

            no_vacios = [cr for cr in crudos if cr is not None and cr != ""]
            son_formulas = bool(no_vacios) and all(
                isinstance(cr, str) and cr.strip().startswith("=") for cr in no_vacios)

            valores_num, son_numeros = [], True
            for cr in crudos:
                val, _ = _analizar_crudo(cr)
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    son_numeros = False
                    break
                valores_num.append(val)
            paso = None
            if son_numeros and len(valores_num) >= 2:
                pasos = [valores_num[i + 1] - valores_num[i] for i in range(len(valores_num) - 1)]
                if len(set(pasos)) == 1:
                    paso = pasos[0]

            texto_incremental = None
            if alto_patron == 1 and not son_formulas and isinstance(crudos[0], str):
                m = self._RE_TEXTO_NUM_FINAL.match(crudos[0])
                if m and m.group(2) and (not son_numeros):
                    texto_incremental = m

            for r in range(fila_fin + 1, fila_hasta + 1):
                idx_patron = (r - fila_fin - 1) % alto_patron
                item_patron = patron[idx_patron]
                fila_patron_original = fila_ini + idx_patron
                crudo_patron = item_patron.data(ROL_CRUDO)
                if crudo_patron is None:
                    crudo_patron = item_patron.text()

                if son_formulas and isinstance(crudo_patron, str) and crudo_patron.strip().startswith("="):
                    nuevo_crudo = self._desplazar_referencias_formula(crudo_patron, r - fila_patron_original)
                elif paso is not None:
                    nuevo_crudo = valores_num[0] + paso * (r - fila_ini)
                elif texto_incremental is not None:
                    prefijo, numero, sufijo = texto_incremental.groups()
                    nuevo_crudo = f"{prefijo}{int(numero) + (r - fila_fin)}{sufijo}"
                else:
                    nuevo_crudo = crudo_patron

                item_destino = self.tabla_editor.item(r, c)
                if item_destino is None:
                    item_destino = QTableWidgetItem("")
                    self.tabla_editor.setItem(r, c, item_destino)
                item_destino.setData(ROL_CRUDO, nuevo_crudo)
                item_destino.setData(ROL_FORMATO_NUM, item_patron.data(ROL_FORMATO_NUM))
                item_destino.setData(ROL_TAMANO_BASE, item_patron.data(ROL_TAMANO_BASE))
                item_destino.setBackground(item_patron.background())
                item_destino.setForeground(item_patron.foreground())
                item_destino.setFont(item_patron.font())
                if item_patron.textAlignment():
                    item_destino.setTextAlignment(item_patron.textAlignment())
        self._sincronizando = False
        self._recalcular_hoja()

    def _sincronizar_combo_fuente_hoja(self):
        """Refleja en el combo 'Fuente' la tipografía real de la celda activa
        cada vez que cambia la selección. Antes el combo se quedaba fijo en
        el primer valor de la lista (Calibri) sin importar qué celda se
        seleccionara, porque solo estaba conectado en el sentido
        combo -> celdas y nunca al revés (celda -> combo), a diferencia del
        editor Word que sí hace este mismo ajuste (ver _word_actualizar_
        controles_formato). Se bloquean las señales para no disparar
        _cambiar_fuente_hoja al fijar el texto aquí."""
        if getattr(self, "_sincronizando", False):
            return
        items = self._celdas_seleccionadas()
        if not items:
            return
        familia = items[0].font().family() or "Calibri"
        self.combo_fuente_hoja.blockSignals(True)
        indice = self.combo_fuente_hoja.findText(familia, Qt.MatchFlag.MatchFixedString)
        if indice >= 0:
            self.combo_fuente_hoja.setCurrentIndex(indice)
        else:
            # La celda usa una tipografía fuera de la lista reducida
            # (p. ej. viene de un .xlsx externo): se agrega temporalmente
            # al final para no perder la información, igual que hace el
            # editor Word en este mismo caso.
            self.combo_fuente_hoja.addItem(familia)
            self.combo_fuente_hoja.setCurrentIndex(self.combo_fuente_hoja.count() - 1)
        self.combo_fuente_hoja.blockSignals(False)

    def _cambiar_fuente_hoja(self, _indice=None):
        items = self._celdas_seleccionadas()
        if not items:
            return
        self._registrar_deshacer_hoja()
        familia = self.combo_fuente_hoja.currentText()
        self._sincronizando = True
        for item in items:
            f = item.font(); f.setFamily(familia); item.setFont(f)
        self._sincronizando = False

    def _alternar_negrita(self):
        items = self._celdas_seleccionadas()
        if not items:
            return
        self._registrar_deshacer_hoja()
        activar = not items[0].font().bold()
        # _sincronizando evita que estos cambios de SOLO formato (no de
        # contenido) disparen _on_celda_editada -que interpretaría el texto
        # ya calculado que se ve como si fuera un nuevo valor escrito a mano
        # y "aplanaría" cualquier fórmula que hubiera en la celda-.
        self._sincronizando = True
        for item in items:
            f = item.font(); f.setBold(activar); item.setFont(f)
        self._sincronizando = False

    def _alternar_cursiva(self):
        items = self._celdas_seleccionadas()
        if not items:
            return
        self._registrar_deshacer_hoja()
        activar = not items[0].font().italic()
        self._sincronizando = True
        for item in items:
            f = item.font(); f.setItalic(activar); item.setFont(f)
        self._sincronizando = False

    def _alternar_subrayado(self):
        items = self._celdas_seleccionadas()
        if not items:
            return
        self._registrar_deshacer_hoja()
        activar = not items[0].font().underline()
        self._sincronizando = True
        for item in items:
            f = item.font(); f.setUnderline(activar); item.setFont(f)
        self._sincronizando = False

    def _elegir_color_relleno(self):
        items = self._celdas_seleccionadas()
        if not items:
            return
        color = _elegir_color_con_icono(QColor("#FEF08A"), self._padre_dialogo(), "Color de relleno")
        if color.isValid():
            self._registrar_deshacer_hoja()
            texto_contraste = _color_texto_contrastado(color)
            self._sincronizando = True
            for item in items:
                item.setBackground(color)
                # Ajustamos también el texto para que siga siendo legible sobre
                # el nuevo relleno, sin importar si la app está en modo claro
                # u oscuro (el usuario puede afinarlo después con "Texto" si quiere).
                item.setForeground(texto_contraste)
            self._sincronizando = False

    def _elegir_color_texto(self):
        items = self._celdas_seleccionadas()
        if not items:
            return
        color = _elegir_color_con_icono(QColor("#0F172A"), self._padre_dialogo(), "Color del texto")
        if color.isValid():
            self._registrar_deshacer_hoja()
            self._sincronizando = True
            for item in items:
                item.setForeground(color)
            self._sincronizando = False

    def _hoja_insertar_enlace(self, item=None):
        """Inserta o edita el hipervínculo de una celda -mismo flujo que en
        Word (Ctrl+K): si ya tiene uno, se precarga la URL para editarla;
        si no, se pregunta. Solo aplica a UNA celda a la vez -a diferencia
        del resto del formato, un enlace no tiene sentido "repetido" igual
        en varias celdas seleccionadas-."""
        if not isinstance(item, QTableWidgetItem):
            # Si esta función se conecta directamente a una señal Qt (p.ej.
            # QToolButton.clicked), Qt puede pasar como primer argumento un
            # bool ("checked") en vez de una celda real -se ignora y se
            # resuelve la celda actual, igual que si item=None-.
            fila, col = self._celda_actual_o_primera_seleccion()
            item = self.tabla_editor.item(fila, col)
            if item is None:
                item = QTableWidgetItem("")
                self.tabla_editor.setItem(fila, col, item)
        url_actual = item.data(ROL_HIPERVINCULO) or ""
        url, ok = QInputDialog.getText(
            self._padre_dialogo(), "Insertar hipervínculo",
            "Dirección del enlace (URL) -déjalo vacío para quitar el enlace-:", text=url_actual)
        if not ok:
            return
        url = url.strip()
        if url and "://" not in url and not url.lower().startswith("mailto:"):
            url = "https://" + url
        if url and not enlace_es_seguro(url):
            mostrar_mensaje(
                "advertencia", "Tipo de enlace no permitido",
                "Solo se admiten direcciones http, https o mailto. No se guardó el hipervínculo:\n\n" + url,
                self._padre_dialogo())
            return
        self._registrar_deshacer_hoja()
        self._sincronizando = True
        if url:
            item.setData(ROL_HIPERVINCULO, url)
            item.setForeground(QColor("#2563EB"))
            f = item.font(); f.setUnderline(True); item.setFont(f)
            if not item.text().strip():
                item.setText(url)
                item.setData(ROL_CRUDO, url)
        else:
            item.setData(ROL_HIPERVINCULO, None)
            item.setForeground(QColor("#0F172A"))
            f = item.font(); f.setUnderline(False); item.setFont(f)
        self._sincronizando = False

    def _hoja_quitar_enlace(self, item):
        if item is None or not item.data(ROL_HIPERVINCULO):
            return
        self._registrar_deshacer_hoja()
        self._sincronizando = True
        item.setData(ROL_HIPERVINCULO, None)
        item.setForeground(QColor("#0F172A"))
        f = item.font(); f.setUnderline(False); item.setFont(f)
        self._sincronizando = False

    def _alinear(self, alineacion):
        items = self._celdas_seleccionadas()
        if not items:
            return
        self._registrar_deshacer_hoja()
        self._sincronizando = True
        for item in items:
            item.setTextAlignment(int(alineacion | Qt.AlignmentFlag.AlignVCenter))
        self._sincronizando = False

    def _ordenar(self, orden):
        if not self._seleccion_valida():
            return
        self._registrar_deshacer_hoja()
        columna = self.tabla_editor.currentColumn()
        if columna < 0:
            columna = 0
        tabla = self.tabla_editor
        filas = tabla.rowCount()
        columnas = tabla.columnCount()
        # Referencias relativas al estilo Excel: al ordenar, las fórmulas
        # viajan con su fila y sus referencias RELATIVAS de fila deben
        # desplazarse junto con ella (misma delta). Sin esto, una fórmula
        # "=B2/C2" que estaba en la fila 5 y aterrizó en la fila 2 seguía
        # mirando la fila 2 (datos de OTRA persona/registro): producía
        # divisiones por cero/celdas equivocadas, e incluso "#¡CIRC!"
        # falsos cuando la referencia vieja coincidía con su nueva propia
        # posición. Las referencias ancladas con "$" (p. ej. B$2 o $B$2)
        # NO se mueven, igual que en Excel.
        #
        # OPTIMIZACIÓN / CORRECCIÓN DE FONDO: antes el bloqueo de señales
        # (self._sincronizando = True) se activaba recién DESPUÉS de este
        # primer bucle de etiquetado. Cada item.setData(ROL_FILA_ORIGEN, r)
        # disparaba itemChanged -> _on_celda_editada, que -al no estar
        # todavía _sincronizando activo- ejecutaba una RECALCULACIÓN
        # COMPLETA DE TODA LA HOJA por cada celda etiquetada. En una hoja de
        # 1000 filas x 20 columnas eso son 20 000 recálculos completos antes
        # de siquiera empezar a ordenar -el origen real de la lentitud y de
        # valores/fórmulas inconsistentes a medio camino-. Ahora se bloquean
        # señales y repintado desde ANTES del primer bucle, envolviendo toda
        # la operación en un único try/finally para no dejar la tabla
        # "trabada" (señales bloqueadas para siempre) si algo falla a mitad
        # de camino.
        self._sincronizando = True
        tabla.blockSignals(True)
        tabla.setUpdatesEnabled(False)
        try:
            for r in range(filas):
                for c in range(columnas):
                    item = tabla.item(r, c)
                    if item is not None:
                        item.setData(ROL_FILA_ORIGEN, r)
            tabla.sortItems(columna, orden)
            for r in range(filas):
                for c in range(columnas):
                    item = tabla.item(r, c)
                    if item is None:
                        continue
                    fila_origen = item.data(ROL_FILA_ORIGEN)
                    if fila_origen is None or fila_origen == r:
                        continue
                    crudo = item.data(ROL_CRUDO)
                    if isinstance(crudo, str) and crudo.strip().startswith("="):
                        item.setData(ROL_CRUDO, _traducir_filas_formula(crudo, r - fila_origen))
        finally:
            tabla.blockSignals(False)
            tabla.setUpdatesEnabled(True)
            self._sincronizando = False
        # Las fórmulas quedan referidas a las posiciones originales de las
        # celdas (igual que un "pegado de valores"): tras reordenar filas se
        # recalcula la hoja UNA SOLA VEZ (no una vez por celda) para que lo
        # que se ve siga siendo consistente.
        self._recalcular_hoja()

    def _autoajustar_columnas(self, maximo=380):
        """Autoajuste REAL del ancho de columnas, medido a mano.

        Se reemplazó `resizeColumnsToContents()` porque NO funcionaba igual
        en todos los archivos: con `wordWrap` activo (el default de
        QTableWidget), el sizeHint de los items NO incluye el ancho completo
        del texto (Qt lo "envuelve" al medir), así que las columnas con
        textos largos quedaban estrechas como si el ajuste no hiciera nada.
        Aquí se mide el texto mostrado de cada celda con las métricas de SU
        propia fuente (respeta negrita/cursiva, la fuente elegida y el zoom
        de la hoja), con tope en `maximo` px para que una celda con un
        párrafo entero no se coma la pantalla —mismo criterio que Excel,
        que también corta el autoajuste en un máximo razonable-."""
        # Cuando se llama desde el botón de la toolbar, clicked() inyecta su
        # `checked` (False) como primer argumento posicional: se normaliza
        # para que un False/True no termine siendo un tope de 0/1 px.
        if maximo is True or maximo is False or not isinstance(maximo, int) or maximo < 40:
            maximo = 380
        from PySide6.QtGui import QFontMetrics
        tabla = self.tabla_editor
        # Caché de métricas por QFont: evita construir un QFontMetrics por
        # CADA celda en hojas grandes (miles de celdas se miden con las
        # mismas 2-4 fuentes típicas de un Excel).
        metricas = {}
        fm_base = QFontMetrics(tabla.font())
        total_celdas = tabla.rowCount() * tabla.columnCount()
        if total_celdas > _UMBRAL_CELDAS_AUTOAJUSTE_MUESTREO:
            # Incluye inicio y final del reporte, donde suelen estar tanto
            # encabezados como totales. El resto de la presentación y el
            # límite de ancho se mantienen sin cambios.
            paso = max(1, math.ceil(tabla.rowCount() / _FILAS_MUESTREO_AUTOAJUSTE))
            filas_a_medir = range(0, tabla.rowCount(), paso)
        else:
            filas_a_medir = range(tabla.rowCount())
        for col in range(tabla.columnCount()):
            encabezado = tabla.horizontalHeaderItem(col)
            ancho = fm_base.horizontalAdvance(encabezado.text()) + 36 if encabezado else 60
            for fila in filas_a_medir:
                item = tabla.item(fila, col)
                texto = item.text() if item else ""
                if not texto:
                    continue
                fuente = item.font()
                fm = metricas.get(fuente.toString())
                if fm is None:
                    fm = metricas[fuente.toString()] = QFontMetrics(fuente)
                ancho = max(ancho, fm.horizontalAdvance(texto) + 28)
                if ancho >= maximo:
                    ancho = maximo
                    break  # ya tocó el tope: nada más que medir en esta columna
            tabla.setColumnWidth(col, int(max(60, min(ancho, maximo))))

    def _zoom_hoja_cambiar(self, delta):
        """Acerca/aleja la hoja completa -tamaño de letra y alto de fila-,
        igual que el control de zoom de la esquina de Excel. El tamaño
        "real" (100%) de cada celda se guarda aparte (ROL_TAMANO_BASE) para
        poder escalarlo proporcionalmente sin perder negrita/cursiva."""
        nuevo = max(10, min(400, self._zoom_hoja + delta))
        if nuevo == self._zoom_hoja:
            return
        self._zoom_hoja = nuevo
        self.in_zoom_hoja.blockSignals(True)
        self.in_zoom_hoja.setText(f"{nuevo}%")
        self.in_zoom_hoja.blockSignals(False)
        self._sincronizando = True
        for r in range(self.tabla_editor.rowCount()):
            for c in range(self.tabla_editor.columnCount()):
                item = self.tabla_editor.item(r, c)
                if item is None:
                    continue
                base = item.data(ROL_TAMANO_BASE)
                if base is None:
                    base = item.font().pointSizeF()
                    if base <= 0:
                        base = 10.0
                    item.setData(ROL_TAMANO_BASE, base)
                f = item.font()
                f.setPointSizeF(max(6.0, base * nuevo / 100))
                item.setFont(f)
        alto_fila = max(18, int(22 * nuevo / 100))
        for r in range(self.tabla_editor.rowCount()):
            self.tabla_editor.setRowHeight(r, alto_fila)
        self._sincronizando = False
        self._autoajustar_columnas()

    def _zoom_hoja_set(self, texto):
        """Aplica el zoom de la hoja desde un texto escrito a mano (p. ej.
        '250' o '250%'). Valida el rango 10–400 y restaura el texto si el
        valor es inválido o no cambió."""
        texto = texto.strip().rstrip("%").strip()
        try:
            valor = int(float(texto))
        except (ValueError, TypeError):
            # Texto inválido: restaurar el valor actual sin disparar de nuevo
            self.in_zoom_hoja.blockSignals(True)
            self.in_zoom_hoja.setText(f"{self._zoom_hoja}%")
            self.in_zoom_hoja.blockSignals(False)
            return
        self._zoom_hoja_cambiar(valor - self._zoom_hoja)

    def _buscar_en_hoja(self):
        texto = self.in_buscar_celda.text().strip().lower()
        if not texto:
            return
        coincidencias = self.tabla_editor.findItems(texto, Qt.MatchFlag.MatchContains)
        self.tabla_editor.clearSelection()
        for item in coincidencias:
            item.setSelected(True)
        if coincidencias:
            self.tabla_editor.scrollToItem(coincidencias[0])
        mostrar_mensaje("info" if coincidencias else "advertencia", "Búsqueda",
                       f"{len(coincidencias)} coincidencia(s) encontrada(s)." if coincidencias
                       else "No se encontraron coincidencias.", self._padre_dialogo())

    def _reemplazar_en_hoja(self):
        buscar = self.in_buscar_celda.text()
        reemplazo = self.in_reemplazar_celda.text()
        if not buscar:
            return
        self._registrar_deshacer_hoja()
        contador = 0
        self._sincronizando = True
        for r in range(self.tabla_editor.rowCount()):
            for c in range(self.tabla_editor.columnCount()):
                item = self.tabla_editor.item(r, c)
                if item is None:
                    continue
                # El reemplazo busca/reemplaza sobre el contenido CRUDO (la
                # fórmula o el valor tal cual, no el resultado ya formateado)
                # para no corromper fórmulas ni perder el tipo de la celda.
                crudo = item.data(ROL_CRUDO)
                crudo_texto = crudo if isinstance(crudo, str) else (item.text() if crudo is None else str(crudo))
                if buscar in crudo_texto:
                    nuevo_crudo = crudo_texto.replace(buscar, reemplazo)
                    item.setData(ROL_CRUDO, nuevo_crudo)
                    item.setData(ROL_FORMATO_NUM, None)
                    contador += 1
        self._sincronizando = False
        if contador:
            self._recalcular_hoja()
        mostrar_mensaje("exito", "Reemplazo completado", f"Se reemplazaron {contador} celda(s).", self._padre_dialogo())

    # ------------------------------------------------------------
    # GUARDAR (CSV / XLSX)
    # ------------------------------------------------------------
    def _guardar(self):
        if not self.ruta_actual:
            return
        if self.tipo_actual == "pdf":
            try:
                self._guardar_pdf(self.ruta_actual)
            except Exception as e:
                import traceback
                traceback.print_exc()
                mostrar_mensaje("error", "No se pudo guardar", str(e), self._padre_dialogo())
            return
        try:
            if self.tipo_actual == "csv":
                self._guardar_csv(self.ruta_actual)
                registrar_auditoria("Reportes", f"Editó y guardó el archivo {os.path.basename(self.ruta_actual)}",
                                   getattr(self.main_window, "usuario_actual", None), self.ruta_actual)
                mostrar_mensaje("exito", "Guardado", f"Los cambios se guardaron en:\n{self.ruta_actual}", self._padre_dialogo())
            elif self.tipo_actual == "xlsx":
                # _sincronizar_grid_a_hoja toca widgets Qt → hilo principal.
                # wb.save() es I/O puro → hilo secundario.
                self._sincronizar_grid_a_hoja(self._hoja_actual)
                ruta = self.ruta_actual
                wb = self._wb
                if WorkerHilo is not None:
                    self._set_btn_guardando(True)
                    def _guardar_io():
                        wb.save(ruta)
                    self._hilo_guardado = WorkerHilo(_guardar_io)
                    self._hilo_guardado.terminado.connect(lambda _: (
                        self._set_btn_guardando(False),
                        registrar_auditoria("Reportes",
                            f"Editó y guardó el archivo {os.path.basename(ruta)}",
                            getattr(self.main_window, "usuario_actual", None), ruta),
                        mostrar_mensaje("exito", "Guardado",
                            f"Los cambios se guardaron en:\n{ruta}", self._padre_dialogo())))
                    self._hilo_guardado.error.connect(lambda msg: (
                        self._set_btn_guardando(False),
                        mostrar_mensaje("error", "No se pudo guardar",
                            msg.split("\n")[0], self._padre_dialogo())))
                    self._hilo_guardado.start()
                else:
                    wb.save(ruta)
                    registrar_auditoria("Reportes", f"Editó y guardó el archivo {os.path.basename(ruta)}",
                                       getattr(self.main_window, "usuario_actual", None), ruta)
                    mostrar_mensaje("exito", "Guardado", f"Los cambios se guardaron en:\n{ruta}", self._padre_dialogo())
            elif self.tipo_actual == "docx":
                self._guardar_docx(self.ruta_actual)
                registrar_auditoria("Reportes", f"Editó y guardó el archivo {os.path.basename(self.ruta_actual)}",
                                   getattr(self.main_window, "usuario_actual", None), self.ruta_actual)
                mostrar_mensaje("exito", "Guardado", f"Los cambios se guardaron en:\n{self.ruta_actual}", self._padre_dialogo())
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_btn_guardando(False)
            mostrar_mensaje("error", "No se pudo guardar", str(e), self._padre_dialogo())

    def _set_btn_guardando(self, guardando):
        """Cambia el texto/estado del botón Guardar para indicar progreso."""
        btn = getattr(self, "btn_guardar", None)
        if btn is None:
            return
        if guardando:
            btn.setText("Guardando…")
            btn.setEnabled(False)
        else:
            btn.setText("Guardar")
            btn.setEnabled(True)

    def _guardar_como(self):
        try:
            if self.tipo_actual == "csv":
                ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Guardar como", "reporte.csv", "CSV (*.csv)")
                if not ruta:
                    return
                self._guardar_csv(ruta)
            elif self.tipo_actual == "xlsx":
                ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Guardar como", "reporte.xlsx", "Excel (*.xlsx)")
                if not ruta:
                    return
                self._sincronizar_grid_a_hoja(self._hoja_actual)
                wb = self._wb
                if WorkerHilo is not None:
                    self._set_btn_guardando(True)
                    def _guardar_como_io():
                        wb.save(ruta)
                    self._hilo_guardado_como = WorkerHilo(_guardar_como_io)
                    def _on_ok(_):
                        self._set_btn_guardando(False)
                        self.ruta_actual = ruta
                        self.lbl_archivo_actual.setTextoCompleto(
                            f"{os.path.basename(ruta)}  —  {ruta}")
                        self.agregar_reciente(ruta)
                        registrar_auditoria("Reportes",
                            f"Guardó una copia editada como {os.path.basename(ruta)}",
                            getattr(self.main_window, "usuario_actual", None), ruta)
                        mostrar_mensaje("exito", "Guardado",
                            f"Copia guardada en:\n{ruta}", self._padre_dialogo())
                    self._hilo_guardado_como.terminado.connect(_on_ok)
                    self._hilo_guardado_como.error.connect(lambda msg: (
                        self._set_btn_guardando(False),
                        mostrar_mensaje("error", "No se pudo guardar",
                            msg.split("\n")[0], self._padre_dialogo())))
                    self._hilo_guardado_como.start()
                    return
                else:
                    wb.save(ruta)
            elif self.tipo_actual == "docx":
                ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Guardar como", "documento.docx", "Word (*.docx)")
                if not ruta:
                    return
                self._guardar_docx(ruta)
            elif self.tipo_actual == "pdf":
                ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Guardar como", "reporte.pdf", "PDF (*.pdf)")
                if not ruta:
                    return
                self._guardar_pdf(ruta, es_nuevo_archivo=True)
                return
            else:
                return
        except Exception as e:
            # ANTES esta función no tenía try/except (a diferencia de
            # _guardar()): cualquier error real durante el guardado -archivo
            # abierto y bloqueado por Excel, permisos, disco lleno, un dato
            # que openpyxl no supiera convertir, etc.- se propagaba SIN
            # capturar. Una excepción sin capturar dentro de un slot de Qt
            # puede terminar tumbando toda la aplicación en vez de solo
            # mostrar un mensaje de error, que es probablemente lo que
            # estaba causando el cierre inesperado de la app al "Guardar
            # como".
            import traceback
            traceback.print_exc()
            mostrar_mensaje("error", "No se pudo guardar", str(e), self._padre_dialogo())
            return
        self.ruta_actual = ruta
        self.lbl_archivo_actual.setTextoCompleto(f"{os.path.basename(ruta)}  —  {ruta}")
        self.agregar_reciente(ruta)
        registrar_auditoria("Reportes", f"Guardó una copia editada como {os.path.basename(ruta)}",
                           getattr(self.main_window, "usuario_actual", None), ruta)
        mostrar_mensaje("exito", "Guardado", f"Copia guardada en:\n{ruta}", self._padre_dialogo())

    # ------------------------------------------------------------
    # WORD (.docx)
    # ------------------------------------------------------------
    def _cargar_docx_lib(self):
        try:
            import docx
            return docx
        except ImportError:
            mostrar_mensaje("error", "Función no disponible",
                           "No se pudo abrir el editor de Word en este equipo. Contacta a soporte técnico.", self._padre_dialogo())
            return None

    def _abrir_docx(self, ruta):
        docx = self._cargar_docx_lib()
        if docx is None:
            raise RuntimeError("python-docx no disponible")
        documento = docx.Document(ruta)
        self.chk_congelar_encabezado.setVisible(False)
        self.chk_autofiltro.setVisible(False)
        self.chk_numeracion_paginas_word.setVisible(True)
        self.chk_justificar_auto_word.setVisible(True)
        self.editor_word.blockSignals(True)
        self.editor_word.setHtml(self._docx_a_html(documento, docx))
        self.editor_word.document().clearUndoRedoStacks()
        self.editor_word.blockSignals(False)
        self._word_ajustar_alto_pagina()
        self._vista_word.resetTransform()
        self._mostrar_pagina("word")
        self._word_sincronizar_barra()
        # El ajuste al ancho se hace un instante después (no en este mismo
        # tick), igual que con el PDF: justo ahora el panel puede no tener
        # todavía su tamaño final visible.
        QTimer.singleShot(0, self._word_ajustar_zoom_al_ancho)
        QTimer.singleShot(0, lambda: None if self._cerrando else (
            self._vista_word.horizontalScrollBar().setValue(0),
            self._vista_word.verticalScrollBar().setValue(0)))

    def _docx_a_html(self, documento, docx):
        """Convierte el contenido del .docx a un HTML sencillo que QTextEdit
        pueda mostrar y editar. No intenta replicar el formato exacto de Word
        -tablas o estilos personalizados quedan fuera de alcance-, pero sí
        conserva lo esencial para leer y corregir un reporte: texto,
        negrita/cursiva/subrayado, color, alineación, párrafos de título e
        IMÁGENES incrustadas (se insertan como datos embebidos en el propio
        HTML, así viajan con el documento sin depender de archivos externos)."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        alineaciones = {
            WD_ALIGN_PARAGRAPH.CENTER: "center",
            WD_ALIGN_PARAGRAPH.RIGHT: "right",
            WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
        }
        tamanos_titulo = {"Title": "24pt", "Heading 1": "20pt", "Heading 2": "16pt", "Heading 3": "13pt"}
        partes = ["<html><body>"]
        for parrafo in documento.paragraphs:
            estilo = (parrafo.style.name if parrafo.style else "Normal") or "Normal"
            alineacion = alineaciones.get(parrafo.alignment, "left")
            es_titulo = estilo in tamanos_titulo
            if not parrafo.runs and not parrafo.text:
                partes.append("<p>&nbsp;</p>")
                continue
            contenido = []
            for run in parrafo.runs:
                # Imagen incrustada en este run (si la hay). Un run con imagen
                # normalmente no trae texto, así que hay que revisarlo ANTES
                # de saltarnos los runs "vacíos" -si no, la imagen se perdía.
                for blip in run._element.findall(".//" + qn("a:blip")):
                    rid = blip.get(qn("r:embed")) or blip.get(qn("r:link"))
                    if not rid:
                        continue
                    try:
                        parte = documento.part.related_parts[rid]
                        b64 = base64.b64encode(parte.blob).decode("ascii")
                        mime = parte.content_type or "image/png"
                        contenido.append(f"<img src='data:{mime};base64,{b64}' style='max-width:640px;' />")
                    except Exception:
                        continue
                texto = (run.text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                if not texto:
                    continue
                texto = texto.replace("\n", "<br/>")
                estilos_run = []
                if run.bold or es_titulo:
                    estilos_run.append("font-weight:bold")
                if run.italic:
                    estilos_run.append("font-style:italic")
                if run.underline:
                    estilos_run.append("text-decoration:underline")
                try:
                    if run.font.size:
                        estilos_run.append(f"font-size:{run.font.size.pt}pt")
                    elif estilo in tamanos_titulo:
                        estilos_run.append(f"font-size:{tamanos_titulo[estilo]}")
                except Exception:
                    pass
                try:
                    if run.font.color and run.font.color.rgb:
                        estilos_run.append(f"color:#{run.font.color.rgb}")
                except Exception:
                    pass
                if estilos_run:
                    contenido.append(f"<span style='{';'.join(estilos_run)}'>{texto}</span>")
                else:
                    contenido.append(texto)
            texto_html = "".join(contenido) or "&nbsp;"
            estilo_parrafo = f"text-align:{alineacion};"
            if es_titulo:
                estilo_parrafo += f"font-weight:bold;font-size:{tamanos_titulo[estilo]};"
            partes.append(f"<p style='{estilo_parrafo}'>{texto_html}</p>")
        partes.append("</body></html>")
        return "".join(partes)

    def _guardar_docx(self, ruta):
        docx = self._cargar_docx_lib()
        if docx is None:
            raise RuntimeError("python-docx no disponible")
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor
        alineaciones = {
            int(Qt.AlignmentFlag.AlignHCenter): WD_ALIGN_PARAGRAPH.CENTER,
            int(Qt.AlignmentFlag.AlignRight): WD_ALIGN_PARAGRAPH.RIGHT,
            int(Qt.AlignmentFlag.AlignJustify): WD_ALIGN_PARAGRAPH.JUSTIFY,
        }
        documento = docx.Document()
        cuerpo = self.editor_word.document()
        bloque = cuerpo.begin()
        while bloque.isValid():
            parrafo = documento.add_paragraph()
            alineacion_bloque = int(bloque.blockFormat().alignment()) & 0xF
            parrafo.alignment = alineaciones.get(alineacion_bloque, WD_ALIGN_PARAGRAPH.LEFT)
            it = bloque.begin()
            hubo_texto = False
            while not it.atEnd():
                fragmento = it.fragment()
                if fragmento.isValid():
                    formato = fragmento.charFormat()
                    if formato.isImageFormat():
                        # Una imagen incrustada en el editor ocupa un fragmento
                        # aparte (con un carácter interno de "objeto" en vez de
                        # texto real); si no la distinguimos aquí, ese carácter
                        # se colaba como texto basura Y la imagen se perdía al
                        # guardar. La reinsertamos como una imagen de verdad.
                        hubo_texto = True
                        formato_img = formato.toImageFormat()
                        nombre = formato_img.name()
                        if nombre.startswith("data:") and ";base64," in nombre:
                            try:
                                _, b64data = nombre.split(";base64,", 1)
                                datos_imagen = base64.b64decode(b64data)
                                ancho = None
                                if formato_img.width() > 0:
                                    # px -> EMU aproximado a 96dpi, para que el
                                    # tamaño en Word se parezca al del editor.
                                    ancho = Pt(formato_img.width() * 0.75)
                                parrafo.add_run().add_picture(io.BytesIO(datos_imagen), width=ancho)
                            except Exception:
                                pass
                    elif fragmento.text():
                        hubo_texto = True
                        run = parrafo.add_run(fragmento.text())
                        run.bold = formato.fontWeight() > QFont.Weight.Normal
                        run.italic = formato.fontItalic()
                        run.underline = formato.fontUnderline()
                        try:
                            if formato.fontPointSize():
                                run.font.size = Pt(formato.fontPointSize())
                        except Exception:
                            pass
                        try:
                            color = formato.foreground().color()
                            if color.isValid() and color.name().lower() != "#000000":
                                run.font.color.rgb = RGBColor(color.red(), color.green(), color.blue())
                        except Exception:
                            pass
                it += 1
            if not hubo_texto:
                parrafo.text = ""
            # "Justificar párrafos sin alinear al guardar": la alineación
            # LEFT (izquierda) es tanto la que el usuario elige a propósito
            # como el valor por defecto de un párrafo al que nunca le tocó
            # el botón de alinear -no hay forma de distinguir ambos casos
            # desde QTextBlockFormat-, así que esta opción se ofrece
            # deshabilitada por defecto (ver chk_justificar_auto_word) para
            # no reescribir alineaciones que el usuario sí eligió a propósito.
            if (getattr(self, "chk_justificar_auto_word", None) is not None
                    and self.chk_justificar_auto_word.isChecked()
                    and parrafo.alignment == WD_ALIGN_PARAGRAPH.LEFT):
                parrafo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            bloque = bloque.next()

        # "Agregar numeración de páginas al guardar": inserta un campo PAGE
        # de Word en el pie de página -no un número fijo escrito a mano-,
        # así que Word lo recalcula solo si luego se añaden o quitan
        # páginas, exactamente como cuando se usa "Insertar número de
        # página" desde el propio Word.
        if getattr(self, "chk_numeracion_paginas_word", None) is not None \
                and self.chk_numeracion_paginas_word.isChecked():
            self._agregar_numeracion_paginas_docx(documento, docx)

        # "Marca de agua" (definida desde Herramientas → cinta de Word): se
        # estampa como texto diagonal gris claro detrás del contenido. El
        # editor de Qt no puede previsualizarla de forma fiel a Word, así que
        # solo se materializa en el .docx al guardar.
        texto_marca = getattr(self, "_marca_agua_word", None)
        if texto_marca:
            self._agregar_marca_agua_docx(documento, docx, texto_marca)

        documento.save(ruta)

    def _agregar_numeracion_paginas_docx(self, documento, docx):
        """Inserta el número de página (campo PAGE, no un valor fijo) centrado
        en el pie de página de la primera sección del documento."""
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        try:
            seccion = documento.sections[0]
            pie = seccion.footer
            pie.is_linked_to_previous = False
            parrafo = pie.paragraphs[0] if pie.paragraphs else pie.add_paragraph()
            parrafo.text = ""
            parrafo.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
            run = parrafo.add_run()
            campo_inicio = OxmlElement("w:fldChar")
            campo_inicio.set(qn("w:fldCharType"), "begin")
            instruccion = OxmlElement("w:instrText")
            instruccion.set(qn("xml:space"), "preserve")
            instruccion.text = "PAGE"
            campo_fin = OxmlElement("w:fldChar")
            campo_fin.set(qn("w:fldCharType"), "end")
            run._r.append(campo_inicio)
            run._r.append(instruccion)
            run._r.append(campo_fin)
        except Exception:
            # La numeración es un "extra": si algo en la estructura del
            # documento impide insertarla, no debe impedir guardar el resto.
            pass

    # ------------------------------------------------------------
    # HERRAMIENTAS DE DOCUMENTO (modo Word) — adaptación de las
    # "Herramientas de documento" del modo PDF:
    #   • Marca de agua                -> se estampa en el .docx al guardar
    #   • Combinar con otro PDF        -> insertar contenido de otro documento
    #   • Exportar página como imagen  -> exportar la hoja como imagen
    #   • Ver texto de la página       -> estadísticas del documento (el
    #     contenido ya ES texto editable, así que lo útil son las cifras)
    # ------------------------------------------------------------
    def _word_marca_de_agua(self):
        """Define (o quita) la marca de agua que se estampa al guardar .docx."""
        texto_actual = getattr(self, "_marca_agua_word", None) or ""
        texto, ok = QInputDialog.getText(
            self._padre_dialogo(), "Marca de agua",
            "Texto de la marca de agua (déjalo vacío para quitarla):",
            text=texto_actual)
        if not ok:
            return
        texto = texto.strip()
        self._marca_agua_word = texto or None
        self._refrescar_accion_marca_agua_word()
        if texto:
            mostrar_mensaje(
                "info", "Marca de agua",
                f"La marca de agua «{texto}» se aplicará en diagonal, detrás del texto, "
                "cuando guardes el documento (.docx).", self._padre_dialogo())

    def _refrescar_accion_marca_agua_word(self):
        """Refleja en el menú si hay una marca de agua pendiente por aplicar."""
        accion = getattr(self, "_accion_marca_agua_word", None)
        if accion is None:
            return
        texto = getattr(self, "_marca_agua_word", None)
        if texto:
            accion.setText(f"Quitar marca de agua («{texto}»)")
        else:
            accion.setText("Marca de agua…")

    def _word_insertar_documento_externo(self):
        """Versión Word de «Combinar con otro PDF»: agrega al final del
        documento el texto de otro archivo (.docx, .txt o .html)."""
        ruta, _ = QFileDialog.getOpenFileName(
            self._padre_dialogo(), "Insertar contenido de otro documento", "",
            "Documentos (*.docx *.txt *.html *.htm);;Word (*.docx);;"
            "Texto (*.txt);;HTML (*.html *.htm)")
        if not ruta:
            return
        ext = ruta.rsplit(".", 1)[-1].lower()
        texto = ""
        try:
            if ext == "docx":
                docx = self._cargar_docx_lib()
                if docx is None:
                    raise RuntimeError("python-docx no está disponible en este equipo")
                documento = docx.Document(ruta)
                texto = "\n".join(p.text for p in documento.paragraphs)
            elif ext in ("html", "htm"):
                from PySide6.QtGui import QTextDocument
                doc_tmp = QTextDocument()
                with open(ruta, "r", encoding="utf-8", errors="replace") as fh:
                    doc_tmp.setHtml(fh.read())
                texto = doc_tmp.toPlainText()
            else:
                with open(ruta, "r", encoding="utf-8", errors="replace") as fh:
                    texto = fh.read()
        except Exception as e:
            mostrar_mensaje("error", "No se pudo leer el documento", str(e), self._padre_dialogo())
            return
        if not texto.strip():
            mostrar_mensaje("advertencia", "Documento vacío",
                            "Ese documento no contiene texto que insertar.", self._padre_dialogo())
            return
        cursor = self.editor_word.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        contenido = self.editor_word.toPlainText()
        if contenido and not contenido.endswith("\n"):
            cursor.insertText("\n\n")
        elif contenido:
            cursor.insertText("\n")
        cursor.insertText(texto)
        self.editor_word.setTextCursor(cursor)
        self.editor_word.ensureCursorVisible()
        self._word_marcar_editado()
        mostrar_mensaje("info", "Documento insertado",
                        f"Se insertó el contenido de «{os.path.basename(ruta)}» al final del documento.",
                        self._padre_dialogo())

    def _word_exportar_imagen(self):
        """Versión Word de «Exportar página como imagen»: guarda la hoja
        del documento (con su formato) como imagen PNG."""
        ruta, _ = QFileDialog.getSaveFileName(
            self._padre_dialogo(), "Exportar hoja como imagen", "documento.png",
            "Imagen PNG (*.png)")
        if not ruta:
            return
        if not ruta.lower().endswith(".png"):
            ruta += ".png"
        pixmap = self.editor_word.grab()
        if pixmap.save(ruta, "PNG"):
            mostrar_mensaje("info", "Imagen exportada",
                            f"Se guardó la hoja del documento como «{os.path.basename(ruta)}».",
                            self._padre_dialogo())
        else:
            mostrar_mensaje("error", "No se pudo exportar",
                            "Ocurrió un problema al generar la imagen.", self._padre_dialogo())

    def _word_estadisticas(self):
        """Versión Word de «Ver texto de la página»: en vez de duplicar el
        texto (que aquí ya es editable), muestra las cifras del documento."""
        documento = self.editor_word.document()
        texto = self.editor_word.toPlainText()
        palabras = len([p for p in texto.split() if p.strip()])
        caracteres = len(texto.replace(" ", "").replace("\n", "").replace("\r", ""))
        imagenes = 0
        bloque = documento.begin()
        while bloque.isValid():
            it = bloque.begin()
            while not it.atEnd():
                if it.fragment().isValid() and it.fragment().charFormat().isImageFormat():
                    imagenes += 1
                it += 1
            bloque = bloque.next()
        mostrar_mensaje(
            "info", "Estadísticas del documento",
            f"Palabras: {palabras}\n"
            f"Caracteres (sin espacios): {caracteres}\n"
            f"Párrafos: {documento.blockCount()}\n"
            f"Imágenes: {imagenes}",
            self._padre_dialogo())

    def _agregar_marca_agua_docx(self, documento, docx, texto):
        """Estampa una marca de agua de texto (diagonal, gris claro, detrás
        del contenido) en la cabecera del .docx, igual que la que inserta
        Word desde Diseño → Marca de agua. Es un "extra": si la estructura
        del documento impide insertarla, no debe impedir guardar el resto."""
        try:
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
            from xml.sax.saxutils import escape
            seccion = documento.sections[0]
            cabecera = seccion.header
            cabecera.is_linked_to_previous = False
            parrafo = cabecera.paragraphs[0] if cabecera.paragraphs else cabecera.add_paragraph()
            parrafo.text = ""
            run = parrafo.add_run()
            pict = OxmlElement("w:pict")
            shape = OxmlElement("v:shape")
            shape.set("id", "PowerPlusWaterMarkObjectAcaDeXI")
            shape.set("o:spid", "_x0000_s2049")
            shape.set("type", "#_x0000_t136")
            shape.set("style",
                      "position:absolute;margin-left:0;margin-top:0;"
                      "width:468pt;height:140pt;rotation:315;z-index:-251654144;"
                      "mso-position-horizontal:center;mso-position-horizontal-relative:margin;"
                      "mso-position-vertical:center;mso-position-vertical-relative:margin")
            shape.set("o:allowincell", "f")
            shape.set("fillcolor", "#D9D9D9")
            shape.set("strokecolor", "#D9D9D9")
            fill = OxmlElement("v:fill")
            fill.set("opacity", ".5")
            textpath = OxmlElement("v:textpath")
            textpath.set("style", "font-size:1pt;font-family:Calibri;v-text-align:center")
            textpath.set("string", escape(texto))
            shape.append(fill)
            shape.append(textpath)
            pict.append(shape)
            run._r.append(pict)
        except Exception:
            pass

    def _word_marcar_editado(self):
        pass  # (reservado por si en el futuro se quiere marcar "cambios sin guardar")

    def _word_ajustar_zoom_al_ancho(self):
        """Igual que _pdf_ajustar_zoom_al_ancho: calcula el zoom para que la
        página de 816px quepa completa en el ancho disponible del panel, en
        vez de arrancar siempre a un 100% fijo que en una ventana angosta
        no cabría (apareciendo una barra horizontal en vez de verse
        completa y centrada, como pasaba con el 140% fijo del PDF)."""
        if self._cerrando:
            return
        ancho_disponible = self._vista_word.viewport().width() - 20
        if ancho_disponible <= 40:
            return
        self._zoom_word = round(max(10, min(400, (ancho_disponible / 816) * 100)))
        factor = self._zoom_word / 100
        self._vista_word.resetTransform()
        self._vista_word.scale(factor, factor)
        self.in_zoom_word.blockSignals(True)
        self.in_zoom_word.setText(f"{self._zoom_word}%")
        self.in_zoom_word.blockSignals(False)

    def _word_seguir_cursor(self):
        """Si el cursor de texto queda fuera del área visible, desplaza la
        vista para seguirlo. QTextEdit ya no puede hacer esto solo -se le
        apagó su scroll propio en __init__ porque ahora _vista_word es
        quien controla el desplazamiento, igual que scroll_pdf hace con
        las páginas del PDF."""
        rect_escena = self._proxy_word.mapRectToScene(QRectF(self.editor_word.cursorRect()))
        self._vista_word.ensureVisible(rect_escena, 20, 40)

    # ---------------- Imágenes dentro del documento (estilo Word) ----------------
    def _word_insertar_imagen(self):
        ruta, _ = QFileDialog.getOpenFileName(self._padre_dialogo(), "Insertar imagen", "",
                                              "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not ruta:
            return
        try:
            with open(ruta, "rb") as f:
                datos = f.read()
        except Exception as e:
            mostrar_mensaje("error", "No se pudo insertar", str(e), self._padre_dialogo())
            return
        imagen = QImage(ruta)
        if imagen.isNull():
            mostrar_mensaje("error", "No se pudo insertar", "El archivo seleccionado no es una imagen válida.", self._padre_dialogo())
            return
        ext = os.path.splitext(ruta)[1].lower().lstrip(".") or "png"
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "bmp": "image/bmp", "gif": "image/gif"}.get(ext, "image/png")
        # El "nombre" del recurso ES la propia imagen en base64: así, al
        # guardar como .docx, el mismo código que ya sabe leer imágenes desde
        # el HTML del documento original (ver _guardar_docx) funciona igual
        # de bien tanto para imágenes que venían del .docx como para estas
        # recién insertadas -sin necesitar dos caminos distintos.
        b64 = base64.b64encode(datos).decode("ascii")
        nombre_recurso = f"data:{mime};base64,{b64}"
        self.editor_word.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(nombre_recurso), imagen)
        ancho_disponible = max(120, self.editor_word.viewport().width() - 80)
        ancho = min(imagen.width(), ancho_disponible) or ancho_disponible
        alto = ancho * (imagen.height() / imagen.width()) if imagen.width() else imagen.height()
        formato = QTextImageFormat()
        formato.setName(nombre_recurso)
        formato.setWidth(ancho)
        formato.setHeight(alto)
        cursor = self.editor_word.textCursor()
        cursor.insertImage(formato)
        self.editor_word.setTextCursor(cursor)

    def _word_cursor_sobre_imagen(self, punto):
        """Si `punto` (coordenadas del viewport del editor) cae sobre una
        imagen, devuelve un cursor con esa imagen seleccionada; si no, None."""
        base = self.editor_word.cursorForPosition(punto)
        for offset in (0, -1):
            posicion = base.position() + offset
            if posicion < 0:
                continue
            candidato = QTextCursor(self.editor_word.document())
            candidato.setPosition(posicion)
            candidato.setPosition(posicion + 1, QTextCursor.MoveMode.KeepAnchor)
            if candidato.charFormat().isImageFormat():
                return candidato
        return None

    def _word_tamano_natural_imagen(self, nombre_recurso):
        try:
            recurso = self.editor_word.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(nombre_recurso))
        except Exception:
            recurso = None
        if recurso is None:
            return None
        if isinstance(recurso, QImage):
            imagen = recurso
        elif isinstance(recurso, QPixmap):
            imagen = recurso.toImage()
        else:
            imagen = QImage(recurso)
        return None if imagen.isNull() else imagen.size()

    def _word_redimensionar_imagen_en(self, cursor):
        formato = cursor.charFormat().toImageFormat()
        tam_natural = self._word_tamano_natural_imagen(formato.name())
        ancho_natural = tam_natural.width() if tam_natural else (formato.width() or 200)
        alto_natural = tam_natural.height() if tam_natural else (formato.height() or 200)
        dialogo = _DialogoRedimensionarImagen(formato.width() or ancho_natural, formato.height() or alto_natural,
                                              ancho_natural, alto_natural, self._padre_dialogo())
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        ancho, alto = dialogo.valores()
        nuevo = QTextImageFormat(formato)
        nuevo.setWidth(ancho)
        nuevo.setHeight(alto)
        cursor.setCharFormat(nuevo)

    def _word_escalar_imagen(self, cursor, factor):
        formato = cursor.charFormat().toImageFormat()
        tam_natural = self._word_tamano_natural_imagen(formato.name())
        ancho_base = tam_natural.width() if tam_natural else (formato.width() or 200)
        alto_base = tam_natural.height() if tam_natural else (formato.height() or 200)
        nuevo = QTextImageFormat(formato)
        nuevo.setWidth(ancho_base * factor)
        nuevo.setHeight(alto_base * factor)
        cursor.setCharFormat(nuevo)

    def _word_ajustar_imagen_a_pagina(self, cursor):
        formato = cursor.charFormat().toImageFormat()
        tam_natural = self._word_tamano_natural_imagen(formato.name())
        ancho_disponible = max(100, self.editor_word.viewport().width() - 80)
        if tam_natural and tam_natural.width():
            proporcion = tam_natural.height() / tam_natural.width()
        elif formato.width():
            proporcion = formato.height() / formato.width()
        else:
            proporcion = 1
        nuevo = QTextImageFormat(formato)
        nuevo.setWidth(ancho_disponible)
        nuevo.setHeight(ancho_disponible * proporcion)
        cursor.setCharFormat(nuevo)

    def _word_eliminar_imagen(self, cursor):
        cursor.removeSelectedText()

    def _word_transparencia_imagen(self, cursor):
        """Transparencia REAL (no simulada): a diferencia de la hoja de
        Excel -donde la "imagen" es un QWidget aparte y hay que fingir la
        opacidad con QGraphicsOpacityEffect-, aquí la imagen es un recurso
        QImage embebido en el documento; QTextEdit sí respeta su canal
        alfa al dibujarla. Se multiplica el canal alfa de cada píxel por el
        porcentaje elegido, se registra el resultado como un recurso NUEVO
        (nombre distinto, para no pisar el original por si se quiere
        volver a 100%), y se actualiza el formato en esa posición del
        cursor para que apunte al nuevo recurso."""
        formato = cursor.charFormat().toImageFormat()
        recurso = self.editor_word.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(formato.name()))
        imagen = recurso if isinstance(recurso, QImage) else (recurso.toImage() if isinstance(recurso, QPixmap) else QImage(recurso))
        if imagen is None or imagen.isNull():
            mostrar_mensaje("error", "No se pudo ajustar", "No se pudo leer la imagen para cambiarle la transparencia.",
                           self._padre_dialogo())
            return
        dialogo = QDialog(self._padre_dialogo())
        dialogo.setWindowTitle("Transparencia de la imagen")
        aplicar_icono_ventana(dialogo, ICONO_DOCUMENTO)
        layout = QVBoxLayout(dialogo)
        layout.addWidget(QLabel("Transparencia:"))
        fila = QHBoxLayout()
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 95)
        slider.setValue(0)
        lbl_valor = QLabel("0%")
        slider.valueChanged.connect(lambda v: lbl_valor.setText(f"{v}%"))
        fila.addWidget(slider, 1)
        fila.addWidget(lbl_valor)
        layout.addLayout(fila)
        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setIcon(icono_emoji("✖"))
        btn_cancelar.setIconSize(_QSize_emoji(16, 16))
        btn_aplicar = QPushButton("Aplicar")
        btn_aplicar.setIcon(icono_emoji("✅"))
        btn_aplicar.setIconSize(_QSize_emoji(16, 16))
        botones.addStretch(); botones.addWidget(btn_cancelar); botones.addWidget(btn_aplicar)
        layout.addLayout(botones)
        btn_cancelar.clicked.connect(dialogo.reject)
        btn_aplicar.clicked.connect(dialogo.accept)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        porcentaje_transparencia = slider.value()
        if porcentaje_transparencia == 0:
            return
        factor_opacidad = 1.0 - (porcentaje_transparencia / 100.0)
        # Se usa QPainter con setOpacity() -mucho más rápido que recorrer
        # los píxeles uno por uno en Python (que sería lentísimo con
        # imágenes grandes)- dibujando sobre un lienzo transparente: el
        # resultado es un canal alfa real, que QTextEdit sí respeta al
        # dibujar la imagen.
        imagen_transparente = QImage(imagen.size(), QImage.Format.Format_ARGB32_Premultiplied)
        imagen_transparente.fill(Qt.GlobalColor.transparent)
        pintor = QPainter(imagen_transparente)
        pintor.setOpacity(factor_opacidad)
        pintor.drawImage(0, 0, imagen)
        pintor.end()
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        imagen_transparente.save(buffer, "PNG")
        b64 = base64.b64encode(bytes(buffer.data())).decode("ascii")
        nombre_recurso = f"data:image/png;base64,{b64}"
        self.editor_word.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(nombre_recurso), imagen_transparente)
        nuevo = QTextImageFormat(formato)
        nuevo.setName(nombre_recurso)
        cursor.setCharFormat(nuevo)

    def _word_menu_contextual(self, punto):
        menu = self.editor_word.createStandardContextMenu()
        cursor_img = self._word_cursor_sobre_imagen(punto)
        if cursor_img is not None:
            menu.addSeparator()
            accion_100 = menu.addAction("Tamaño real (100%)")
            accion_50 = menu.addAction("Reducir a 50%")
            accion_ajustar = menu.addAction("Ajustar al ancho de página")
            accion_dialogo = menu.addAction("Cambiar tamaño…")
            accion_transparencia = menu.addAction("Transparencia…")
            accion_eliminar = menu.addAction("Eliminar imagen")
            accion_100.triggered.connect(lambda: self._word_escalar_imagen(cursor_img, 1.0))
            accion_50.triggered.connect(lambda: self._word_escalar_imagen(cursor_img, 0.5))
            accion_ajustar.triggered.connect(lambda: self._word_ajustar_imagen_a_pagina(cursor_img))
            accion_dialogo.triggered.connect(lambda: self._word_redimensionar_imagen_en(cursor_img))
            accion_transparencia.triggered.connect(lambda: self._word_transparencia_imagen(cursor_img))
            accion_eliminar.triggered.connect(lambda: self._word_eliminar_imagen(cursor_img))
        enlace = self.editor_word.anchorAt(punto)
        if enlace:
            menu.addSeparator()
            accion_abrir = menu.addAction("Abrir enlace")
            accion_editar = menu.addAction("Editar hipervínculo…")
            accion_quitar = menu.addAction("Quitar hipervínculo")
            accion_abrir.triggered.connect(lambda: abrir_enlace_externo(enlace, self))
            accion_editar.triggered.connect(lambda: self._word_insertar_enlace(punto))
            accion_quitar.triggered.connect(lambda: self._word_quitar_enlace(punto))
        menu.exec(self.editor_word.viewport().mapToGlobal(punto))

    def _word_cursor_sobre_enlace(self, punto=None):
        """Cursor posicionado sobre el hipervínculo bajo `punto` (o la
        posición actual del cursor de edición si no se da ninguno), con la
        selección expandida para cubrir el enlace completo. None si no hay
        ningún enlace ahí."""
        if punto is not None:
            cursor = self.editor_word.cursorForPosition(punto)
        else:
            cursor = self.editor_word.textCursor()
        if not cursor.charFormat().isAnchor():
            return None
        href = cursor.charFormat().anchorHref()
        # Qt no trae una forma directa de "seleccionar el ancla completa";
        # se expande carácter por carácter mientras el href siga siendo el
        # mismo -suficiente para enlaces normales de una sola línea-.
        inicio = cursor.position()
        while inicio > 0:
            c = QTextCursor(self.editor_word.document())
            c.setPosition(inicio - 1)
            c.setPosition(inicio, QTextCursor.MoveMode.KeepAnchor)
            if c.charFormat().anchorHref() != href:
                break
            inicio -= 1
        fin = cursor.position()
        limite = self.editor_word.document().characterCount() - 1
        while fin < limite:
            c = QTextCursor(self.editor_word.document())
            c.setPosition(fin)
            c.setPosition(fin + 1, QTextCursor.MoveMode.KeepAnchor)
            if c.charFormat().anchorHref() != href:
                break
            fin += 1
        resultado = QTextCursor(self.editor_word.document())
        resultado.setPosition(inicio)
        resultado.setPosition(fin, QTextCursor.MoveMode.KeepAnchor)
        return resultado

    def _word_quitar_enlace(self, punto=None):
        cursor = self._word_cursor_sobre_enlace(punto)
        if cursor is None:
            return
        formato_normal = QTextCharFormat()
        formato_normal.setAnchor(False)
        formato_normal.setAnchorHref("")
        formato_normal.setForeground(QColor("#0F172A"))
        formato_normal.setFontUnderline(False)
        cursor.mergeCharFormat(formato_normal)

    def _word_insertar_enlace(self, punto=None):
        """Inserta un hipervínculo nuevo en el texto seleccionado (o
        pregunta qué texto mostrar si no hay selección), o edita uno ya
        existente si el cursor está sobre un enlace -mismo flujo que
        Word/Office real (Ctrl+K)."""
        cursor_enlace = self._word_cursor_sobre_enlace(punto)
        if cursor_enlace is not None:
            cursor = cursor_enlace
        else:
            cursor = self.editor_word.textCursor()

        url_actual = cursor.charFormat().anchorHref() if cursor.charFormat().isAnchor() else ""
        texto_seleccionado = cursor.selectedText()

        if not texto_seleccionado:
            texto_nuevo, ok = QInputDialog.getText(
                self._padre_dialogo(), "Insertar hipervínculo", "Texto que se va a mostrar:")
            if not ok or not texto_nuevo.strip():
                return
            texto_seleccionado = texto_nuevo.strip()

        url, ok = QInputDialog.getText(
            self._padre_dialogo(), "Insertar hipervínculo",
            "Dirección del enlace (URL) -déjalo vacío para quitar el enlace-:", text=url_actual)
        if not ok:
            return
        url = url.strip()
        if url and "://" not in url and not url.lower().startswith("mailto:"):
            url = "https://" + url  # igual que Word: sin protocolo, se asume https
        if url and not enlace_es_seguro(url):
            mostrar_mensaje(
                "advertencia", "Tipo de enlace no permitido",
                "Solo se admiten direcciones http, https o mailto. No se guardó el hipervínculo:\n\n" + url,
                self._padre_dialogo())
            return

        formato_enlace = QTextCharFormat()
        if url:
            formato_enlace.setAnchor(True)
            formato_enlace.setAnchorHref(url)
            formato_enlace.setForeground(QColor("#2563EB"))
            formato_enlace.setFontUnderline(True)
        else:
            formato_enlace.setAnchor(False)
            formato_enlace.setAnchorHref("")
            formato_enlace.setForeground(QColor("#0F172A"))
            formato_enlace.setFontUnderline(False)

        cursor.insertText(texto_seleccionado, formato_enlace)
        # Al terminar de escribir el enlace, lo que se teclee A CONTINUACIÓN
        # no debe seguir "contagiado" del formato de enlace -si no, seguir
        # escribiendo después de un link lo seguiría subrayando/coloreando-.
        formato_normal = QTextCharFormat()
        formato_normal.setAnchor(False)
        formato_normal.setForeground(QColor("#0F172A"))
        formato_normal.setFontUnderline(False)
        cursor.setCharFormat(formato_normal)
        self.editor_word.setCurrentCharFormat(formato_normal)
        self.editor_word.setTextCursor(cursor)

    def _word_formato_actual(self):
        return self.editor_word.textCursor().charFormat()

    def _word_aplicar_formato(self, formato):
        cursor = self.editor_word.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(formato)
        self.editor_word.mergeCurrentCharFormat(formato)

    def _word_alternar_negrita(self, activo):
        formato = QTextCharFormat()
        formato.setFontWeight(QFont.Weight.Bold if activo else QFont.Weight.Normal)
        self._word_aplicar_formato(formato)

    def _word_alternar_cursiva(self, activo):
        formato = QTextCharFormat()
        formato.setFontItalic(activo)
        self._word_aplicar_formato(formato)

    def _word_alternar_subrayado(self, activo):
        formato = QTextCharFormat()
        formato.setFontUnderline(activo)
        self._word_aplicar_formato(formato)

    def _word_elegir_color_texto(self):
        color = _elegir_color_con_icono(QColor("#0F172A"), self._padre_dialogo(), "Color del texto")
        if color.isValid():
            formato = QTextCharFormat()
            formato.setForeground(color)
            self._word_aplicar_formato(formato)

    def _word_elegir_color_resaltado(self):
        color = _elegir_color_con_icono(QColor("#FEF08A"), self._padre_dialogo(), "Color de resaltado")
        if color.isValid():
            formato = QTextCharFormat()
            formato.setBackground(color)
            self._word_aplicar_formato(formato)

    def _word_alinear(self, alineacion):
        self.editor_word.setAlignment(alineacion)

    def _word_zoom(self, delta_porcentaje):
        """Acerca/aleja la PÁGINA como tal -no solo el texto-, exactamente
        igual que el zoom del PDF: la hoja completa (texto, márgenes, todo)
        se agranda o achica como una sola unidad visual, escalando la vista
        que envuelve la página (ver _vista_word/_escena_word), en vez de
        solo aumentar el tamaño de la fuente. Mismo rango y mismo paso que
        el PDF (10%-400%, de 20 en 20)."""
        nuevo = max(10, min(400, self._zoom_word + delta_porcentaje))
        if nuevo == self._zoom_word:
            return
        self._zoom_word = nuevo
        factor = nuevo / 100
        self._vista_word.resetTransform()
        self._vista_word.scale(factor, factor)
        self.in_zoom_word.blockSignals(True)
        self.in_zoom_word.setText(f"{nuevo}%")
        self.in_zoom_word.blockSignals(False)

    def _word_zoom_set(self, texto):
        """Aplica el zoom del editor Word desde un texto escrito a mano
        (p. ej. '150' o '150%'). Valida el rango y restaura si inválido."""
        texto = texto.strip().rstrip("%").strip()
        try:
            valor = int(float(texto))
        except (ValueError, TypeError):
            self.in_zoom_word.blockSignals(True)
            self.in_zoom_word.setText(f"{self._zoom_word}%")
            self.in_zoom_word.blockSignals(False)
            return
        self._word_zoom(valor - self._zoom_word)

    def _aplicar_estilo_editor_word(self):
        """Estilo de la página de Word. El escalado por zoom lo hace la
        vista que la envuelve (ver _word_zoom), así que aquí el margen de
        página es siempre el mismo -al igual que una página de PDF no
        redefine sus propios márgenes según el zoom, sino que toda la
        imagen se escala junta-."""
        c = getattr(self, "_c_tema_editor", None) or _colores_tema(self.main_window)
        self.editor_word.setStyleSheet(f"""
            QTextEdit {{
                background-color: #FFFFFF;
                color: #0F172A;
                border: none;
                padding: 24px 40px;
                selection-background-color: {c['accent']};
                selection-color: white;
            }}
        """)
        self._vista_word.setStyleSheet(_qss_scrollbar_editor(c, "QGraphicsView "))

    def _word_ajustar_alto_pagina(self):
        """La 'página' de Word crece de alto sola a medida que escribes -ni
        más ni menos, como una hoja real que va llenándose-, en vez de
        tener scroll propio (el scroll ahora lo maneja _vista_word, igual
        que scroll_pdf hace con las páginas del PDF)."""
        alto_contenido = max(1056, int(self.editor_word.document().size().height()) + 4)
        if self.editor_word.height() != alto_contenido:
            self.editor_word.setFixedHeight(alto_contenido)
        self._escena_word.setSceneRect(self._proxy_word.boundingRect())

    def _word_cambiar_tamano(self, _indice=None):
        try:
            tamano = float(self.combo_tamano_word.currentText())
        except ValueError:
            return
        formato = QTextCharFormat()
        formato.setFontPointSize(tamano)
        self._word_aplicar_formato(formato)

    def _word_cambiar_fuente(self, _indice=None):
        familia = self.combo_fuente_word.currentText()
        if not familia:
            return
        formato = QTextCharFormat()
        formato.setFontFamilies([familia])
        self._word_aplicar_formato(formato)

    def _word_aplicar_estilo(self, indice):
        tamanos = {0: 11, 1: 20, 2: 16, 3: 13}
        tamano = tamanos.get(indice, 11)
        formato = QTextCharFormat()
        formato.setFontPointSize(tamano)
        formato.setFontWeight(QFont.Weight.Bold if indice > 0 else QFont.Weight.Normal)
        cursor = self.editor_word.textCursor()
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.mergeCharFormat(formato)
        self.editor_word.setTextCursor(cursor)
        self.editor_word.mergeCurrentCharFormat(formato)
        self.combo_tamano_word.setCurrentText(str(tamano))

    def _word_lista_vinetas(self):
        cursor = self.editor_word.textCursor()
        cursor.createList(QTextListFormat.Style.ListDisc)

    def _word_lista_numerada(self):
        cursor = self.editor_word.textCursor()
        cursor.createList(QTextListFormat.Style.ListDecimal)

    def _word_sincronizar_barra(self):
        """Refleja en la barra de herramientas (negrita/cursiva/subrayado,
        alineación, tamaño) el formato del texto donde está el cursor ahora
        mismo, tal como se espera de cualquier editor de texto enriquecido."""
        formato = self._word_formato_actual()
        for boton in (self.btn_negrita_word, self.btn_cursiva_word, self.btn_subrayado_word,
                      self.btn_alinear_izq_word, self.btn_alinear_centro_word,
                      self.btn_alinear_der_word, self.btn_alinear_just_word):
            boton.blockSignals(True)
        self.btn_negrita_word.setChecked(formato.fontWeight() > QFont.Weight.Normal)
        self.btn_cursiva_word.setChecked(formato.fontItalic())
        self.btn_subrayado_word.setChecked(formato.fontUnderline())
        alineacion = self.editor_word.alignment()
        self.btn_alinear_izq_word.setChecked(bool(alineacion & Qt.AlignmentFlag.AlignLeft))
        self.btn_alinear_centro_word.setChecked(bool(alineacion & Qt.AlignmentFlag.AlignHCenter))
        self.btn_alinear_der_word.setChecked(bool(alineacion & Qt.AlignmentFlag.AlignRight))
        self.btn_alinear_just_word.setChecked(bool(alineacion & Qt.AlignmentFlag.AlignJustify))
        for boton in (self.btn_negrita_word, self.btn_cursiva_word, self.btn_subrayado_word,
                      self.btn_alinear_izq_word, self.btn_alinear_centro_word,
                      self.btn_alinear_der_word, self.btn_alinear_just_word):
            boton.blockSignals(False)
        if formato.fontPointSize():
            self.combo_tamano_word.blockSignals(True)
            self.combo_tamano_word.setCurrentText(str(int(formato.fontPointSize())))
            self.combo_tamano_word.blockSignals(False)
        familia_actual = formato.font().family()
        if familia_actual:
            self.combo_fuente_word.blockSignals(True)
            indice_familia = self.combo_fuente_word.findText(familia_actual, Qt.MatchFlag.MatchFixedString)
            if indice_familia >= 0:
                self.combo_fuente_word.setCurrentIndex(indice_familia)
            else:
                # La fuente del texto bajo el cursor no está en nuestra
                # lista reducida (p. ej. viene de un .docx externo con otra
                # tipografía): se agrega temporalmente al final para no
                # perder la referencia de cuál es, y queda seleccionada.
                self.combo_fuente_word.addItem(familia_actual)
                self.combo_fuente_word.setCurrentIndex(self.combo_fuente_word.count() - 1)
            self.combo_fuente_word.blockSignals(False)

    def _word_buscar_siguiente(self):
        texto = self.in_buscar_word.text()
        if not texto:
            return
        if not self.editor_word.find(texto):
            # No se encontró más adelante: volvemos al inicio y probamos de nuevo,
            # para que la búsqueda "dé la vuelta" como en cualquier editor.
            cursor = self.editor_word.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor_word.setTextCursor(cursor)
            if not self.editor_word.find(texto):
                mostrar_mensaje("info", "Sin resultados", f"No se encontró «{texto}» en el documento.", self._padre_dialogo())

    def _word_reemplazar_todo(self):
        buscar = self.in_buscar_word.text()
        reemplazo = self.in_reemplazar_word.text()
        if not buscar:
            return
        contenido = self.editor_word.toPlainText()
        contador = contenido.count(buscar)
        if contador == 0:
            mostrar_mensaje("info", "Sin resultados", f"No se encontró «{buscar}» en el documento.", self._padre_dialogo())
            return
        cursor = self.editor_word.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        buscador = self.editor_word.textCursor()
        buscador.movePosition(QTextCursor.MoveOperation.Start)
        self.editor_word.setTextCursor(buscador)
        while self.editor_word.find(buscar):
            c = self.editor_word.textCursor()
            c.insertText(reemplazo)
        cursor.endEditBlock()
        mostrar_mensaje("exito", "Reemplazo completado", f"Se reemplazaron {contador} coincidencia(s).", self._padre_dialogo())

    # ------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------
    def _cargar_fitz(self):
        try:
            import fitz
            return fitz
        except ImportError:
            mostrar_mensaje("error", "Función no disponible",
                           "No se pudo abrir el editor de PDF en este equipo. Contacta a soporte técnico.", self._padre_dialogo())
            return None

    def _abrir_pdf(self, ruta):
        fitz = self._cargar_fitz()
        if fitz is None:
            raise RuntimeError("PyMuPDF no disponible")
        if self._doc_pdf is not None:
            try:
                self._doc_pdf.close()
            except Exception:
                pass
        self._doc_pdf = fitz.open(ruta)
        self.chk_congelar_encabezado.setVisible(False)
        self.chk_autofiltro.setVisible(False)
        self.chk_numeracion_paginas_word.setVisible(False)
        self.chk_justificar_auto_word.setVisible(False)
        self._indice_pagina_pdf = 0
        self._zoom_pdf = 1.4
        self._paginas_pdf_editables = set()  # xrefs de páginas en blanco insertadas por el usuario
        self._pila_deshacer_pdf.clear()
        self._pila_rehacer_pdf.clear()
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setMaximum(max(1, len(self._doc_pdf)))
        self.spin_pagina_pdf.setValue(1)
        self.spin_pagina_pdf.blockSignals(False)
        self.lbl_total_paginas.setText(f"/ {len(self._doc_pdf)}")
        self.panel_texto_pdf.setVisible(False)
        self.btn_texto_pdf.setChecked(False)
        self._renderizar_todas_paginas()
        self._mostrar_pagina("pdf")
        # El ajuste al ancho se hace un instante después (no en este mismo
        # tick) porque justo ahora el panel puede no tener todavía su
        # tamaño final visible -por ejemplo, si el editor se está mostrando
        # por primera vez-, y mediríamos un ancho incorrecto.
        QTimer.singleShot(0, self._pdf_ajustar_zoom_al_ancho)

    def _renderizar_todas_paginas(self):
        """Renderiza (o vuelve a renderizar, tras un zoom/edición estructural)
        el documento completo como una columna de páginas dentro del scroll,
        y deja la vista en la página en la que estábamos.

        OPTIMIZACIÓN: para un PDF largo, rasterizar TODAS las páginas de
        golpe (una por una, de forma síncrona) podía congelar la app varios
        segundos con documentos de decenas de páginas. Ahora se crea de
        inmediato un marcador del TAMAÑO correcto para cada página -así el
        scroll y el salto a una página funcionan bien desde el primer
        instante-, y el contenido real (imagen + texto seleccionable) se
        rasteriza en tandas pequeñas con QTimer, cediendo el hilo principal
        entre tanda y tanda para que la interfaz no se congele. La página
        que se está viendo se prioriza para que aparezca primero."""
        self._render_en_progreso = True
        while self._layout_paginas_pdf.count():
            item = self._layout_paginas_pdf.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._labels_paginas_pdf = []
        if self._doc_pdf is None or len(self._doc_pdf) == 0:
            self._render_en_progreso = False
            return
        import fitz
        self._indice_pagina_pdf = max(0, min(self._indice_pagina_pdf, len(self._doc_pdf) - 1))
        sx = self._zoom_pdf
        for i in range(len(self._doc_pdf)):
            rect = self._doc_pdf[i].rect
            ancho = max(1, int(rect.width * sx))
            alto = max(1, int(rect.height * sx))
            lbl = _EtiquetaPaginaPDFSeleccionable(self, i, [])
            lbl.setFixedSize(ancho, alto)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background-color: white; border: 1px solid rgba(100, 116, 139, 90);")
            self._layout_paginas_pdf.addWidget(lbl, 0, Qt.AlignmentFlag.AlignHCenter)
            self._labels_paginas_pdf.append(lbl)
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setValue(self._indice_pagina_pdf + 1)
        self.spin_pagina_pdf.blockSignals(False)
        # Orden de rasterizado: primero la página actual y sus vecinas
        # cercanas (lo que la persona está viendo o va a ver al hacer
        # scroll), y el resto en orden -así el contenido "útil" aparece
        # casi al instante incluso en documentos largos.
        orden = sorted(range(len(self._doc_pdf)), key=lambda i: abs(i - self._indice_pagina_pdf))
        self._cola_render_pdf = deque(orden)
        self._token_render_pdf = getattr(self, "_token_render_pdf", 0) + 1
        self._continuar_render_pdf_por_tandas(self._token_render_pdf)
        if self.panel_texto_pdf.isVisible():
            self._actualizar_panel_texto_pdf()
        QTimer.singleShot(0, lambda: self._pdf_desplazar_a_pagina(self._indice_pagina_pdf))

    def _continuar_render_pdf_por_tandas(self, token, tamano_tanda=4):
        """Rasteriza hasta `tamano_tanda` páginas de la cola pendiente y se
        reprograma a sí misma con QTimer.singleShot(0, ...) hasta terminar
        -cediendo el control al bucle de eventos entre tanda y tanda para
        que la ventana siga respondiendo. `token` evita que una tanda vieja
        (de un render que ya se reemplazó, p.ej. cambiaste de página o de
        zoom de nuevo antes de terminar) siga escribiendo sobre labels que
        ya no corresponden."""
        if self._cerrando or token != getattr(self, "_token_render_pdf", None) or self._doc_pdf is None:
            return
        import fitz
        sx = self._zoom_pdf
        for _ in range(tamano_tanda):
            if not self._cola_render_pdf:
                self._render_en_progreso = False
                return
            i = self._cola_render_pdf.popleft()
            if i >= len(self._labels_paginas_pdf):
                continue
            lbl = self._labels_paginas_pdf[i]
            try:
                pagina = self._doc_pdf[i]
                pix = pagina.get_pixmap(matrix=fitz.Matrix(sx, sx), alpha=False)
                imagen = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                try:
                    palabras_crudas = pagina.get_text("words")
                except Exception:
                    palabras_crudas = []
                lbl.palabras = [(x0 * sx, y0 * sx, x1 * sx, y1 * sx, texto, bloque, linea, num)
                                for (x0, y0, x1, y1, texto, bloque, linea, num) in palabras_crudas]
                try:
                    enlaces_crudos = pagina.get_links()
                except Exception:
                    enlaces_crudos = []
                lbl.enlaces = []
                for enlace in enlaces_crudos:
                    uri = enlace.get("uri")
                    r = enlace.get("from")
                    if not uri or r is None:
                        continue  # enlaces internos (a otra página del mismo PDF) quedan fuera por ahora
                    # Estos enlaces vienen de un PDF que puede venir de fuera de
                    # la institución (adjunto, importado, etc.) -no los tipeó
                    # quien los está viendo-, así que se descartan aquí mismo
                    # los que no sean http/https/mailto en vez de confiar en el
                    # filtro de abrir_enlace_externo() como única defensa.
                    if not enlace_es_seguro(uri):
                        continue
                    lbl.enlaces.append((QRect(int(r.x0 * sx), int(r.y0 * sx),
                                               max(1, int((r.x1 - r.x0) * sx)),
                                               max(1, int((r.y1 - r.y0) * sx))), uri))
                lbl.setPixmap(QPixmap.fromImage(imagen))
            except Exception as e:
                print(f"[PDF] No se pudo renderizar la página {i + 1}: {e}")
        if self._cola_render_pdf:
            QTimer.singleShot(0, lambda: self._continuar_render_pdf_por_tandas(token, tamano_tanda))
        else:
            self._render_en_progreso = False

    def _pdf_copiar_seleccion(self):
        """Copia al portapapeles el texto seleccionado (arrastrando el mouse)
        en la página actualmente visible -equivalente en botón, para quien
        prefiera no usar el clic derecho, a lo que ya hace soltar el mouse
        sobre una selección."""
        if not self._labels_paginas_pdf or not (0 <= self._indice_pagina_pdf < len(self._labels_paginas_pdf)):
            return
        lbl = self._labels_paginas_pdf[self._indice_pagina_pdf]
        texto = lbl.texto_seleccionado() if hasattr(lbl, "texto_seleccionado") else ""
        if not texto:
            mostrar_mensaje("advertencia", "Sin selección",
                           "Primero arrastra el mouse sobre el texto de la página para seleccionarlo "
                           "(o haz doble clic sobre una palabra).", self._padre_dialogo())
            return
        QApplication.clipboard().setText(texto)
        mostrar_mensaje("exito", "Copiado", "El texto seleccionado se copió al portapapeles.", self._padre_dialogo())

    def _pdf_insertar_enlace(self):
        """Convierte el texto seleccionado (arrastrando el mouse sobre la
        página, igual que para copiar) en un hipervínculo real del PDF: el
        rectángulo de selección -en píxeles de la página YA renderizada al
        zoom actual- se convierte de vuelta a coordenadas de PDF (puntos,
        dividiendo por el mismo factor de zoom con el que se dibujó) y se
        inserta ahí un enlace con PyMuPDF."""
        if not self._pdf_listo():
            return
        if not self._labels_paginas_pdf or not (0 <= self._indice_pagina_pdf < len(self._labels_paginas_pdf)):
            return
        lbl = self._labels_paginas_pdf[self._indice_pagina_pdf]
        rect_pixeles = lbl._rect_seleccion() if hasattr(lbl, "_rect_seleccion") else None
        if rect_pixeles is None or (rect_pixeles.width() < 3 and rect_pixeles.height() < 3):
            mostrar_mensaje("advertencia", "Sin selección",
                           "Primero arrastra el mouse sobre el texto o la zona de la página que "
                           "quieres convertir en enlace.", self._padre_dialogo())
            return
        url, ok = QInputDialog.getText(self._padre_dialogo(), "Insertar hipervínculo",
                                       "Dirección del enlace (URL):")
        if not ok or not url.strip():
            return
        url = url.strip()
        if "://" not in url and not url.lower().startswith("mailto:"):
            url = "https://" + url
        import fitz
        sx = self._zoom_pdf
        rect_pdf = fitz.Rect(rect_pixeles.left() / sx, rect_pixeles.top() / sx,
                             rect_pixeles.right() / sx, rect_pixeles.bottom() / sx)
        self._registrar_deshacer_pdf()
        pagina = self._doc_pdf[self._indice_pagina_pdf]
        pagina.insert_link({"kind": fitz.LINK_URI, "from": rect_pdf, "uri": url})
        # PyMuPDF guarda los enlaces de una página en una lista interna que
        # NO se actualiza sola al llamar insert_link(): sin este reload,
        # get_links() -usado más abajo al re-renderizar para poder hacer
        # Ctrl+clic sobre el enlace recién creado- devolvía la lista vieja
        # (sin el enlace nuevo) hasta la siguiente vez que se abriera el
        # archivo.
        self._doc_pdf.reload_page(pagina)
        lbl._inicio = None
        lbl._fin = None
        self._renderizar_todas_paginas()
        mostrar_mensaje("exito", "Enlace insertado", "El hipervínculo se agregó a la página.", self._padre_dialogo())

    def _pdf_desplazar_a_pagina(self, indice):
        """Mueve la barra de scroll hasta el inicio de la página `indice`
        (esto es lo que hacen ⏮/◀/▶/⏭ y el spinbox: ya no hace falta un
        re-render, solo desplazar la vista continua)."""
        if self._cerrando or not self._labels_paginas_pdf or not (0 <= indice < len(self._labels_paginas_pdf)):
            return
        lbl = self._labels_paginas_pdf[indice]
        self.scroll_pdf.verticalScrollBar().setValue(lbl.geometry().y())

    def _pdf_pagina_por_scroll(self, valor):
        """Detecta, según la posición del scroll, qué página está centrada en
        la vista -esto es lo que permite «pasar de página» simplemente
        deslizando la barra o con la rueda del ratón, sin usar los botones."""
        if self._render_en_progreso or not self._labels_paginas_pdf:
            return
        centro = valor + self.scroll_pdf.viewport().height() / 2
        nueva = self._indice_pagina_pdf
        for i, lbl in enumerate(self._labels_paginas_pdf):
            geo = lbl.geometry()
            if geo.y() <= centro:
                nueva = i
            else:
                break
        if nueva != self._indice_pagina_pdf:
            self._indice_pagina_pdf = nueva
            self.spin_pagina_pdf.blockSignals(True)
            self.spin_pagina_pdf.setValue(nueva + 1)
            self.spin_pagina_pdf.blockSignals(False)
            if self.panel_texto_pdf.isVisible():
                pagina = self._doc_pdf[nueva]
                self.panel_texto_pdf.setPlainText(pagina.get_text() or "(Esta página no contiene texto extraíble.)")

    def _actualizar_panel_texto_pdf(self):
        """Actualiza el panel lateral de texto extraíble con el contenido
        de la página actual. Solo hace algo si el panel está visible y hay
        un documento PDF abierto."""
        if self._doc_pdf is None or not self.panel_texto_pdf.isVisible():
            return
        try:
            pagina = self._doc_pdf[self._indice_pagina_pdf]
            self.panel_texto_pdf.setPlainText(
                pagina.get_text() or "(Esta página no contiene texto extraíble.)"
            )
        except Exception:
            pass

    def _pdf_listo(self):
        if self._doc_pdf is None:
            mostrar_mensaje("advertencia", "Sin PDF abierto", "Abre primero un archivo PDF.", self._padre_dialogo())
            return False
        return True

    def _pdf_primera(self):
        if not self._pdf_listo():
            return
        self._indice_pagina_pdf = 0
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setValue(1)
        self.spin_pagina_pdf.blockSignals(False)
        self._pdf_desplazar_a_pagina(0)

    def _pdf_ultima(self):
        if not self._pdf_listo():
            return
        self._indice_pagina_pdf = len(self._doc_pdf) - 1
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setValue(self._indice_pagina_pdf + 1)
        self.spin_pagina_pdf.blockSignals(False)
        self._pdf_desplazar_a_pagina(self._indice_pagina_pdf)

    def _pdf_anterior(self):
        if not self._pdf_listo():
            return
        if self._indice_pagina_pdf > 0:
            self._indice_pagina_pdf -= 1
            self.spin_pagina_pdf.blockSignals(True)
            self.spin_pagina_pdf.setValue(self._indice_pagina_pdf + 1)
            self.spin_pagina_pdf.blockSignals(False)
            self._pdf_desplazar_a_pagina(self._indice_pagina_pdf)

    def _pdf_siguiente(self):
        if not self._pdf_listo():
            return
        if self._indice_pagina_pdf < len(self._doc_pdf) - 1:
            self._indice_pagina_pdf += 1
            self.spin_pagina_pdf.blockSignals(True)
            self.spin_pagina_pdf.setValue(self._indice_pagina_pdf + 1)
            self.spin_pagina_pdf.blockSignals(False)
            self._pdf_desplazar_a_pagina(self._indice_pagina_pdf)

    def _pdf_ir_a_pagina(self, numero):
        if self._doc_pdf is None:
            return
        objetivo = numero - 1
        if 0 <= objetivo < len(self._doc_pdf) and objetivo != self._indice_pagina_pdf:
            self._indice_pagina_pdf = objetivo
            self._pdf_desplazar_a_pagina(objetivo)

    def _pdf_zoom(self, delta):
        if not self._pdf_listo():
            return
        self._zoom_pdf = max(0.1, min(4.0, self._zoom_pdf + delta))
        self.in_zoom_pdf.blockSignals(True)
        self.in_zoom_pdf.setText(f"{int(round(self._zoom_pdf * 100))}%")
        self.in_zoom_pdf.blockSignals(False)
        self._renderizar_todas_paginas()

    def _pdf_zoom_set(self, texto):
        """Aplica el zoom del PDF desde un texto escrito a mano
        (p. ej. '200' o '200%'). Rango 10–400. Restaura si inválido."""
        texto = texto.strip().rstrip("%").strip()
        try:
            valor = int(float(texto))
        except (ValueError, TypeError):
            self.in_zoom_pdf.blockSignals(True)
            self.in_zoom_pdf.setText(f"{int(round(self._zoom_pdf * 100))}%")
            self.in_zoom_pdf.blockSignals(False)
            return
        nuevo_factor = max(0.1, min(4.0, valor / 100))
        if abs(nuevo_factor - self._zoom_pdf) < 0.005:
            # Mismo zoom: solo normalizar el texto
            self.in_zoom_pdf.blockSignals(True)
            self.in_zoom_pdf.setText(f"{int(round(self._zoom_pdf * 100))}%")
            self.in_zoom_pdf.blockSignals(False)
            return
        self._zoom_pdf = nuevo_factor
        self.in_zoom_pdf.blockSignals(True)
        self.in_zoom_pdf.setText(f"{int(round(self._zoom_pdf * 100))}%")
        self.in_zoom_pdf.blockSignals(False)
        if self._pdf_listo():
            self._renderizar_todas_paginas()

    def _pdf_ajustar_zoom_al_ancho(self):
        """Calcula el zoom para que la página quepa exactamente en el ancho
        disponible del panel -así el documento se ve completo y centrado de
        verdad al abrirlo, sin importar el tamaño de la ventana ni el de la
        página (antes, con el 140% fijo, una página tamaño carta en una
        ventana normal no cabía: aparecía una barra horizontal y la página
        quedaba pegada a la izquierda en vez de centrada)."""
        if self._cerrando or not self._pdf_listo():
            return
        ancho_disponible = self.scroll_pdf.viewport().width() - 20  # los 10px de margen de cada lado
        if ancho_disponible <= 40:
            return  # el panel todavía no tiene un tamaño real (p. ej. recién creado, aún oculto)
        ancho_pagina_pt = self._doc_pdf[self._indice_pagina_pdf].rect.width
        if ancho_pagina_pt <= 0:
            return
        self._zoom_pdf = max(0.1, min(4.0, ancho_disponible / ancho_pagina_pt))
        self.in_zoom_pdf.blockSignals(True)
        self.in_zoom_pdf.setText(f"{int(round(self._zoom_pdf * 100))}%")
        self.in_zoom_pdf.blockSignals(False)
        self._renderizar_todas_paginas()

    # ------------------------------------------------------------
    # DESHACER / REHACER (PDF)
    # ------------------------------------------------------------
    # PyMuPDF no trae undo propio, así que se aplica la misma estrategia de
    # "instantánea completa" que en la hoja de cálculo, pero del documento
    # entero (son PDFs de pocas páginas dentro de este editor, así que
    # guardar el documento completo en cada paso es liviano).
    LIMITE_DESHACER_PDF = 20

    def _registrar_deshacer_pdf(self):
        if self._doc_pdf is None:
            return
        self._pila_deshacer_pdf.append((self._doc_pdf.tobytes(), self._indice_pagina_pdf))
        if len(self._pila_deshacer_pdf) > self.LIMITE_DESHACER_PDF:
            self._pila_deshacer_pdf.pop(0)
        self._pila_rehacer_pdf.clear()
        self._actualizar_botones_deshacer()

    def _restaurar_snapshot_pdf(self, snap):
        import fitz
        datos, indice_pagina = snap
        self._doc_pdf.close()
        self._doc_pdf = fitz.open(stream=datos, filetype="pdf")
        self._indice_pagina_pdf = min(indice_pagina, len(self._doc_pdf) - 1)
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setMaximum(len(self._doc_pdf))
        self.spin_pagina_pdf.setValue(self._indice_pagina_pdf + 1)
        self.spin_pagina_pdf.blockSignals(False)
        self.lbl_total_paginas.setText(f"/ {len(self._doc_pdf)}")
        self._renderizar_todas_paginas()

    def _deshacer_pdf(self):
        if not self._pila_deshacer_pdf or self._doc_pdf is None:
            return
        self._pila_rehacer_pdf.append((self._doc_pdf.tobytes(), self._indice_pagina_pdf))
        self._restaurar_snapshot_pdf(self._pila_deshacer_pdf.pop())
        self._actualizar_botones_deshacer()

    def _rehacer_pdf(self):
        if not self._pila_rehacer_pdf or self._doc_pdf is None:
            return
        self._pila_deshacer_pdf.append((self._doc_pdf.tobytes(), self._indice_pagina_pdf))
        self._restaurar_snapshot_pdf(self._pila_rehacer_pdf.pop())
        self._actualizar_botones_deshacer()

    def _pdf_rotar(self):
        if not self._pdf_listo():
            return
        self._registrar_deshacer_pdf()
        pagina = self._doc_pdf[self._indice_pagina_pdf]
        pagina.set_rotation((pagina.rotation + 90) % 360)
        self._renderizar_todas_paginas()

    def _pdf_eliminar_pagina(self):
        if not self._pdf_listo():
            return
        if len(self._doc_pdf) <= 1:
            mostrar_mensaje("advertencia", "No se puede eliminar", "El documento debe tener al menos una página.", self._padre_dialogo())
            return
        respuesta = QMessageBox.question(self._padre_dialogo(), "Eliminar página",
                                        f"¿Eliminar la página {self._indice_pagina_pdf + 1}?")
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        self._registrar_deshacer_pdf()
        self._doc_pdf.delete_page(self._indice_pagina_pdf)
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setMaximum(max(1, len(self._doc_pdf)))
        self.spin_pagina_pdf.blockSignals(False)
        self.lbl_total_paginas.setText(f"/ {len(self._doc_pdf)}")
        self._renderizar_todas_paginas()

    def _pdf_insertar_pagina(self):
        if not self._pdf_listo():
            return
        self._registrar_deshacer_pdf()
        rect = self._doc_pdf[self._indice_pagina_pdf].rect
        nueva = self._doc_pdf.new_page(pno=self._indice_pagina_pdf + 1, width=rect.width, height=rect.height)
        # Se recuerda (por xref, que no cambia aunque se muevan/borren otras
        # páginas) que esta página fue creada en blanco por el usuario: solo
        # estas páginas se pueden "editar" después -ver _pdf_editar_pagina_
        # actual-, para no arriesgarse nunca a estropear el diseño de una
        # página que ya traía contenido del PDF original.
        self._paginas_pdf_editables.add(nueva.xref)
        self._indice_pagina_pdf += 1
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setMaximum(len(self._doc_pdf))
        self.spin_pagina_pdf.blockSignals(False)
        self.lbl_total_paginas.setText(f"/ {len(self._doc_pdf)}")
        self._renderizar_todas_paginas()

    def _pdf_mover_arriba(self):
        if not self._pdf_listo() or self._indice_pagina_pdf == 0:
            return
        self._registrar_deshacer_pdf()
        self._doc_pdf.move_page(self._indice_pagina_pdf, self._indice_pagina_pdf - 1)
        self._indice_pagina_pdf -= 1
        self._renderizar_todas_paginas()

    def _pdf_mover_abajo(self):
        if not self._pdf_listo() or self._indice_pagina_pdf >= len(self._doc_pdf) - 1:
            return
        self._registrar_deshacer_pdf()
        self._doc_pdf.move_page(self._indice_pagina_pdf, self._indice_pagina_pdf + 1)
        self._indice_pagina_pdf += 1
        self._renderizar_todas_paginas()

    def _pdf_alternar_panel_texto(self, visible):
        self.panel_texto_pdf.setVisible(visible)
        self.btn_copiar_texto_pdf.setVisible(visible)
        if visible and self._doc_pdf is not None:
            pagina = self._doc_pdf[self._indice_pagina_pdf]
            self.panel_texto_pdf.setPlainText(pagina.get_text() or "(Esta página no contiene texto extraíble.)")

    def _pdf_editar_pagina_actual(self):
        """Escribe texto con formato (negrita/cursiva/fuente/tamaño/color/
        alineación) en una página -SOLO si es una página en blanco que el
        propio usuario insertó con "➕ Insertar" (o cualquier página que ya
        esté vacía de por sí). No se permite "editar" una página que ya
        traía contenido del PDF original: no existe forma de reescribirla
        conservando el diseño exacto, y hacerlo igual -como pasaba antes-
        significaba borrar/estropear esa página. Para páginas con
        contenido, se puede usar en su lugar la selección/copia de texto
        (arrastrando el mouse) o insertar una marca de agua/anotación."""
        if not self._pdf_listo():
            return
        pagina = self._doc_pdf[self._indice_pagina_pdf]
        texto_existente = (pagina.get_text("text") or "").strip()
        es_editable = pagina.xref in self._paginas_pdf_editables or not texto_existente
        if not es_editable:
            mostrar_mensaje("advertencia", "Esta página no se puede editar",
                           "Para no arriesgarse a estropear el diseño original del PDF, solo se pueden "
                           "escribir/editar páginas en blanco -las que insertes con « Insertar»-. "
                           "Esta página ya trae contenido del archivo original.\n\n"
                           "Si necesitas el texto de esta página, puedes seleccionarlo arrastrando el "
                           "mouse sobre él (se copia al portapapeles), o usar « Insertar» para agregar "
                           "una página nueva en blanco.", self._padre_dialogo())
            return
        ya_editada_antes = pagina.xref in self._paginas_pdf_editables
        dialogo = _DialogoEditorPaginaPDF(self._padre_dialogo(), texto_inicial=texto_existente,
                                           css_editor=self._css_editor_actual or self._css_editor())
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        self._registrar_deshacer_pdf()
        import fitz
        html = dialogo.obtener_html()
        rect = pagina.rect
        margen = 36  # ~ media pulgada, para dejar márgenes en la hoja
        area = fitz.Rect(rect.x0 + margen, rect.y0 + margen, rect.x1 - margen, rect.y1 - margen)
        if ya_editada_antes:
            # La página ya se había editado antes: `insert_htmlbox` NO borra
            # lo que se escribió la vez anterior, solo agrega texto nuevo
            # encima -por eso el texto viejo y el nuevo quedaban superpuestos
            # al editar dos veces la misma página-. Se borra primero el
            # contenido previo (una redacción sin texto de reemplazo) antes
            # de escribir el texto actualizado.
            try:
                pagina.add_redact_annot(area)
                pagina.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            except Exception:
                pass
        try:
            pagina.insert_htmlbox(area, html, overlay=True)
        except Exception as e:
            mostrar_mensaje("error", "No se pudo aplicar", f"No se pudo escribir el contenido en la página: {e}",
                           self._padre_dialogo())
            return
        self._paginas_pdf_editables.add(pagina.xref)
        self._renderizar_todas_paginas()
        mostrar_mensaje("exito", "Página actualizada", "Se aplicó el contenido a la página.", self._padre_dialogo())

    def _pdf_marca_de_agua(self):
        if not self._pdf_listo():
            return
        dialogo = _DialogoMarcaDeAgua(self._padre_dialogo())
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        opciones = dialogo.valores()
        self._registrar_deshacer_pdf()
        paginas = range(len(self._doc_pdf)) if opciones["todas"] else [self._indice_pagina_pdf]
        for i in paginas:
            pagina = self._doc_pdf[i]
            rect = pagina.rect
            pagina.insert_textbox(rect, opciones["texto"], fontsize=opciones["tamano"],
                                  color=opciones["color"], fill_opacity=opciones["opacidad"],
                                  rotate=opciones["rotacion"], align=1, overlay=True)
        self._renderizar_todas_paginas()
        mostrar_mensaje("exito", "Marca de agua insertada",
                       "Recuerda usar «Guardar» o «Guardar como…» para conservar el cambio.", self._padre_dialogo())

    def _pdf_combinar(self):
        if not self._pdf_listo():
            return
        ruta, _ = QFileDialog.getOpenFileName(self._padre_dialogo(), "Combinar con otro PDF", "", "PDF (*.pdf)")
        if not ruta:
            return
        self._registrar_deshacer_pdf()
        import fitz
        try:
            otro = fitz.open(ruta)
            self._doc_pdf.insert_pdf(otro)
            otro.close()
        except Exception as e:
            mostrar_mensaje("error", "No se pudo combinar", str(e), self._padre_dialogo())
            return
        self.spin_pagina_pdf.blockSignals(True)
        self.spin_pagina_pdf.setMaximum(len(self._doc_pdf))
        self.spin_pagina_pdf.blockSignals(False)
        self.lbl_total_paginas.setText(f"/ {len(self._doc_pdf)}")
        mostrar_mensaje("exito", "PDF combinado",
                       f"Se agregaron las páginas de «{os.path.basename(ruta)}» al final. "
                       "Recuerda guardar para conservar el cambio.", self._padre_dialogo())

    def _pdf_exportar_imagen(self):
        if not self._pdf_listo():
            return
        ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar página como imagen",
                                              f"pagina_{self._indice_pagina_pdf + 1}.png", "PNG (*.png)")
        if not ruta:
            return
        import fitz
        pagina = self._doc_pdf[self._indice_pagina_pdf]
        pix = pagina.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), alpha=False)
        pix.save(ruta)
        mostrar_mensaje("exito", "Imagen exportada", f"Página exportada en:\n{ruta}", self._padre_dialogo())

    def _guardar_pdf(self, ruta, es_nuevo_archivo=False):
        if self._doc_pdf is None:
            return
        try:
            if es_nuevo_archivo:
                self._doc_pdf.save(ruta, garbage=4, deflate=True)
            else:
                # Se guarda primero en un archivo temporal y se reemplaza el
                # original al final: evita los problemas de guardado
                # incremental de PyMuPDF cuando el documento tiene páginas
                # insertadas, eliminadas o reordenadas.
                temporal = ruta + ".tmp_guardado"
                self._doc_pdf.save(temporal, garbage=4, deflate=True)
                self._doc_pdf.close()
                shutil.move(temporal, ruta)
                import fitz
                self._doc_pdf = fitz.open(ruta)
        except Exception as e:
            mostrar_mensaje("error", "No se pudo guardar el PDF", str(e), self._padre_dialogo())
            return
        self.ruta_actual = ruta
        self.lbl_archivo_actual.setTextoCompleto(f"{os.path.basename(ruta)}  —  {ruta}")
        if es_nuevo_archivo:
            self.agregar_reciente(ruta)
        registrar_auditoria("Reportes", f"Editó y guardó el PDF {os.path.basename(ruta)}",
                           getattr(self.main_window, "usuario_actual", None), ruta)
        mostrar_mensaje("exito", "Guardado", f"Los cambios se guardaron en:\n{ruta}", self._padre_dialogo())

    def _pdf_exportar_texto(self):
        if not self._pdf_listo():
            return
        ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar texto de la página",
                                              f"pagina_{self._indice_pagina_pdf + 1}.txt", "Texto (*.txt)")
        if not ruta:
            return
        pagina = self._doc_pdf[self._indice_pagina_pdf]
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(pagina.get_text())
        mostrar_mensaje("exito", "Texto exportado", f"Texto de la página exportado en:\n{ruta}", self._padre_dialogo())

    # ------------------------------------------------------------
    # IMPRESIÓN (directamente desde el editor, sin exportar antes)
    # ------------------------------------------------------------
    def _imprimir(self):
        if self.tipo_actual is None:
            return
        try:
            from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        except ImportError:
            mostrar_mensaje("error", "Impresión no disponible",
                           "La función de impresión no está disponible en este equipo.", self._padre_dialogo())
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogo = QPrintDialog(printer, self._padre_dialogo())
        dialogo.setWindowTitle("Imprimir")
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._renderizar_para_impresion(printer)
        except Exception as e:
            mostrar_mensaje("error", "No se pudo imprimir", str(e), self._padre_dialogo())

    def _renderizar_para_impresion(self, printer):
        if self.tipo_actual == "docx":
            self.editor_word.document().print_(printer)
        elif self.tipo_actual == "pdf":
            self._imprimir_pdf_en(printer)
        else:  # csv / xlsx
            self._imprimir_tabla_en(printer)

    def _tabla_a_html(self):
        filas = self.tabla_editor.rowCount()
        cols = self.tabla_editor.columnCount()
        partes = ["<html><body><table border='1' cellspacing='0' cellpadding='5' "
                  "style='border-collapse:collapse; font-family:Arial, sans-serif; font-size:9pt;'>"]
        for r in range(filas):
            partes.append("<tr>")
            for c in range(cols):
                item = self.tabla_editor.item(r, c)
                texto = (item.text() if item else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                negrita = bool(item and item.font().bold())
                celda = f"<b>{texto}</b>" if negrita else texto
                etiqueta = "th" if r == 0 else "td"
                partes.append(f"<{etiqueta}>{celda}</{etiqueta}>")
            partes.append("</tr>")
        partes.append("</table></body></html>")
        return "".join(partes)

    def _imprimir_tabla_en(self, printer):
        doc = QTextDocument()
        doc.setHtml(self._tabla_a_html())
        doc.print_(printer)

    def _imprimir_pdf_en(self, printer):
        if self._doc_pdf is None:
            return
        import fitz
        painter = QPainter(printer)
        rect_pagina = QRectF(printer.pageRect(printer.Unit.DevicePixel))
        for i in range(len(self._doc_pdf)):
            if i > 0:
                printer.newPage()
            pagina = self._doc_pdf[i]
            pix = pagina.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            imagen = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            escala = min(rect_pagina.width() / imagen.width(), rect_pagina.height() / imagen.height())
            ancho, alto = imagen.width() * escala, imagen.height() * escala
            x = rect_pagina.x() + (rect_pagina.width() - ancho) / 2
            y = rect_pagina.y() + (rect_pagina.height() - alto) / 2
            painter.drawImage(QRectF(x, y, ancho, alto), imagen)
        painter.end()

    # ------------------------------------------------------------
    # EXPORTAR A OTROS FORMATOS
    # ------------------------------------------------------------
    def _actualizar_menu_exportar(self):
        self.menu_exportar.clear()
        opciones = []
        if self.tipo_actual == "csv":
            opciones = [("Excel (.xlsx)", "xlsx"), ("PDF (.pdf)", "pdf"), ("Word (.docx)", "docx")]
        elif self.tipo_actual == "xlsx":
            opciones = [("CSV (.csv)", "csv"), ("PDF (.pdf)", "pdf"), ("Word (.docx)", "docx")]
        elif self.tipo_actual == "docx":
            opciones = [("PDF (.pdf)", "pdf"), ("XML (.xml)", "xml")]
        elif self.tipo_actual == "pdf":
            # Sin OCR no se puede convertir de forma fiable a texto/hoja editable:
            # se ofrecen solo las exportaciones que sí se pueden hacer bien.
            opciones = [("Imagen de la página actual (.png)", "imagen"),
                        ("Texto de la página actual (.txt)", "texto")]
        for etiqueta, formato in opciones:
            accion = self.menu_exportar.addAction(f"Exportar a {etiqueta}")
            accion.triggered.connect(lambda checked=False, f=formato: self._exportar(f))
        self.btn_exportar.setEnabled(bool(opciones))

    def _exportar(self, formato):
        try:
            if self.tipo_actual in ("csv", "xlsx"):
                self._exportar_desde_hoja(formato)
            elif self.tipo_actual == "docx":
                self._exportar_desde_docx(formato)
            elif self.tipo_actual == "pdf":
                if formato == "imagen":
                    self._pdf_exportar_imagen()
                elif formato == "texto":
                    self._pdf_exportar_texto()
        except Exception as e:
            mostrar_mensaje("error", "No se pudo exportar", str(e), self._padre_dialogo())

    def _exportar_desde_hoja(self, formato):
        nombre_base = os.path.splitext(os.path.basename(self.ruta_actual or "reporte"))[0]
        if formato == "csv":
            ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar a CSV", f"{nombre_base}.csv", "CSV (*.csv)")
            if not ruta:
                return
            self._guardar_csv(ruta)
            mostrar_mensaje("exito", "Exportado", "El archivo se exportó correctamente.", self._padre_dialogo())
        elif formato == "xlsx":
            openpyxl = self._cargar_openpyxl()
            if openpyxl is None:
                return
            ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar a Excel", f"{nombre_base}.xlsx", "Excel (*.xlsx)")
            if not ruta:
                return
            # Extraer datos de la grilla en el hilo principal (toca widgets Qt),
            # luego wb.save() en hilo secundario (I/O puro).
            wb = openpyxl.Workbook()
            hoja = wb.active
            for fila in self._extraer_filas_crudas_de_tabla():
                fila_valores = []
                for crudo in fila:
                    if isinstance(crudo, str) and crudo.strip().startswith("=") and len(crudo.strip()) > 1:
                        fila_valores.append(crudo.strip())
                    else:
                        valor, _formato = _analizar_crudo(crudo)
                        fila_valores.append(valor)
                hoja.append(fila_valores)
            if WorkerHilo is not None:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                def _xlsx_io():
                    wb.save(ruta)
                self._hilo_exportar_xlsx = WorkerHilo(_xlsx_io)
                self._hilo_exportar_xlsx.terminado.connect(lambda _: (
                    QApplication.restoreOverrideCursor(),
                    mostrar_mensaje("exito", "Exportado",
                        "El archivo se exportó correctamente.", self._padre_dialogo())))
                self._hilo_exportar_xlsx.error.connect(lambda msg: (
                    QApplication.restoreOverrideCursor(),
                    mostrar_mensaje("error", "Error al exportar",
                        msg.split("\n")[0], self._padre_dialogo())))
                self._hilo_exportar_xlsx.start()
            else:
                wb.save(ruta)
                mostrar_mensaje("exito", "Exportado", "El archivo se exportó correctamente.", self._padre_dialogo())
        elif formato == "pdf":
            ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar a PDF", f"{nombre_base}.pdf", "PDF (*.pdf)")
            if not ruta:
                return
            # _exportar_html_a_pdf ya es asíncrono (emite su propio toast al terminar)
            self._exportar_html_a_pdf(self._tabla_a_html(), ruta)
        elif formato == "docx":
            docx = self._cargar_docx_lib()
            if docx is None:
                return
            ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar a Word", f"{nombre_base}.docx", "Word (*.docx)")
            if not ruta:
                return
            # Construir documento en hilo principal (accede a datos de tabla),
            # documento.save() en hilo secundario.
            filas = self._extraer_filas_de_tabla()
            documento = docx.Document()
            if filas:
                tabla = documento.add_table(rows=len(filas), cols=len(filas[0]))
                tabla.style = "Light Grid Accent 1"
                for r, fila in enumerate(filas):
                    for c, valor in enumerate(fila):
                        celda = tabla.cell(r, c)
                        celda.text = str(valor) if valor is not None else ""
                        if r == 0:
                            for p in celda.paragraphs:
                                for run in p.runs:
                                    run.bold = True
            if WorkerHilo is not None:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                def _docx_io():
                    documento.save(ruta)
                self._hilo_exportar_docx = WorkerHilo(_docx_io)
                self._hilo_exportar_docx.terminado.connect(lambda _: (
                    QApplication.restoreOverrideCursor(),
                    mostrar_mensaje("exito", "Exportado",
                        "El archivo se exportó correctamente.", self._padre_dialogo())))
                self._hilo_exportar_docx.error.connect(lambda msg: (
                    QApplication.restoreOverrideCursor(),
                    mostrar_mensaje("error", "Error al exportar",
                        msg.split("\n")[0], self._padre_dialogo())))
                self._hilo_exportar_docx.start()
            else:
                documento.save(ruta)
                mostrar_mensaje("exito", "Exportado", "El archivo se exportó correctamente.", self._padre_dialogo())
        else:
            return

    def _exportar_desde_docx(self, formato):
        nombre_base = os.path.splitext(os.path.basename(self.ruta_actual or "documento"))[0]
        if formato == "pdf":
            ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar a PDF", f"{nombre_base}.pdf", "PDF (*.pdf)")
            if not ruta:
                return
            html = self.editor_word.toHtml()   # leer HTML en hilo principal
            self._exportar_html_a_pdf(html, ruta)
        elif formato == "xml":
            ruta, _ = QFileDialog.getSaveFileName(self._padre_dialogo(), "Exportar a XML", f"{nombre_base}.xml", "XML (*.xml)")
            if not ruta:
                return
            import tempfile, zipfile
            with tempfile.TemporaryDirectory() as tmp:
                temporal_docx = os.path.join(tmp, "temporal.docx")
                self._guardar_docx(temporal_docx)  # refleja lo que hay ahora mismo en el editor
                with zipfile.ZipFile(temporal_docx) as z:
                    contenido_xml = z.read("word/document.xml")
            with open(ruta, "wb") as f:
                f.write(contenido_xml)
        else:
            return
        mostrar_mensaje("exito", "Exportado", "El archivo se exportó correctamente.", self._padre_dialogo())

    def _exportar_html_a_pdf(self, html, ruta):
        """Genera un PDF a partir de HTML (usado tanto para exportar la hoja
        de cálculo como para exportar el documento Word) usando el propio
        motor de impresión de Qt.
        QPrinter + QTextDocument + doc.print_() son seguros en hilo
        secundario porque no hacen paint en pantalla: solo escriben al
        archivo de salida. Se ejecutan en un WorkerHilo para no bloquear
        la UI durante la impresión (puede tardar varios segundos en
        documentos grandes)."""
        if WorkerHilo is not None:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            def _tarea_pdf():
                from PySide6.QtPrintSupport import QPrinter
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(ruta)
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(printer)
            self._hilo_exportar_pdf = WorkerHilo(_tarea_pdf)
            self._hilo_exportar_pdf.terminado.connect(lambda _: (
                QApplication.restoreOverrideCursor(),
                mostrar_mensaje("exito", "Exportado",
                    "El archivo se exportó correctamente.", self._padre_dialogo())))
            self._hilo_exportar_pdf.error.connect(lambda msg: (
                QApplication.restoreOverrideCursor(),
                mostrar_mensaje("error", "Error al exportar",
                    msg.split("\n")[0], self._padre_dialogo())))
            self._hilo_exportar_pdf.start()
        else:
            from PySide6.QtPrintSupport import QPrinter
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(ruta)
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)

