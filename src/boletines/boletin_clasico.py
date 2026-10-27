"""Estilo Clásico de los boletines PDF.

Este módulo es la implementación ORIGINAL de los tres formatos oficiales
(Secundaria, Primaria y Técnico), preservada tal cual se veía antes del
sistema de diseño nuevo (`boletin_estilo.py`, usado por el estilo
"Moderno"). Vive aparte para que ambos estilos puedan mantenerse sin que
uno dependa del otro: quien quiera seguir viendo el boletín "de toda la
vida" lo tiene disponible exactamente como era, y quien prefiera el diseño
renovado lo activa desde "Exportar Boletín" -> "Estilo del boletín" (ver
`boletin_minerd.estilo_boletin` / `guardar_estilo_boletin`).

No se duplica NADA de la capa de datos (cálculo de notas, cascada,
asistencia, decisiones, ni los "mostrar_*_boletin" que leen la preferencia
guardada): todo eso se importa sin cambios desde boletin_minerd.py /
boletin_tecnico_minerd.py, que es donde vive de verdad. Lo único que hay
aquí es DIBUJO -las mismas funciones, con el mismo aspecto, que ya existían
antes del rediseño.
"""
from datetime import datetime

from src.nucleo.bd import obtener_conexion
from src.boletines.boletin_minerd import (colores_boletin, mostrar_resumen_asistencia_boletin,
                             mostrar_situacion_automatica_boletin, mostrar_leyenda_boletin,
                             mostrar_firma_padres_boletin, mostrar_situacion_final_boletin,
                             ESCALA_DESCRIPTIVA_PRIMARIA, periodos_del_anio,
                             _dibujar_logos_adicionales, _alto_extra_logos_adicionales,
                             _FUENTES_BOLETIN_VALIDAS, _fuente_pdf_utilizable)


def _hex_a_rgb01(hexcolor):
    hexcolor= (hexcolor or "#1F9E9E").lstrip("#")
    if len(hexcolor) != 6:
        hexcolor= "1F9E9E"
    return tuple(int(hexcolor[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _aclarar(rgb, factor=0.75):
    """Tono más claro del color de banda -se usa para resaltar la columna
    'Calificación Final del Área' en el cuerpo de la grilla, igual que la
    plantilla real la resalta en celeste sobre un encabezado turquesa. No
    es un color nuevo que haya que configurar aparte: se deriva del mismo
    color de banda que la institución ya eligió, así que cambiar un color
    sigue moviendo el boletín completo de forma consistente."""
    return tuple(c + (1 - c) * factor for c in rgb)


def _fmt(valor, decimales=0):
    return f"{valor:.{decimales}f}" if valor is not None else ""


def _dibujar_texto_ajustado(cvs, texto, x, y, ancho_max, centrado=True, tamano_inicial=6.5, negrita=True):
    fuente_base= "Helvetica-Bold" if negrita else "Helvetica"
    tam= tamano_inicial
    while tam > 4 and cvs.stringWidth(texto, fuente_base, tam) > ancho_max:
        tam -= 0.5
    cvs.setFont(fuente_base, tam)
    if centrado:
        cvs.drawCentredString(x, y, texto)
    else:
        cvs.drawString(x, y, texto)


def _dibujar_texto_multilinea(cvs, texto, cx, y_centro, ancho_max, alto_max, tamano_inicial=6.5, negrita=True):
    """Reparte `texto` en varias líneas (ajuste de palabras, no solo por
    '/') hasta que quepa en ancho_max de ancho y alto_max de alto,
    reduciendo el tamaño de fuente si hace falta. Los encabezados oficiales
    (nombres de competencias fundamentales, "PROMEDIO GRUPO DE COMPETENCIAS
    ESPECÍFICAS", etc.) son demasiado largos para una sola línea en una
    columna angosta -por eso todo encabezado de la grilla pasa por aquí en
    vez de por el ajuste de una sola línea que sí sirve para celdas de
    datos.

    El ajuste deja un margen de seguridad del 10% en ancho y alto: los
    anchos de letra que reportlab usa para decidir el tamaño de fuente son
    las métricas estándar de Adobe para las fuentes base14, pero algunos
    lectores de PDF (ej. el visor de Microsoft Edge) renderizan letras
    mayúsculas acentuadas/negritas un poco más anchas que esas métricas -sin
    este margen, un texto que "en el papel" (según el cálculo) cabe justo,
    puede verse desbordado en esos visores."""
    fuente= "Helvetica-Bold" if negrita else "Helvetica"
    tam= tamano_inicial
    palabras= texto.replace(" / ", " /").split(" ")
    ancho_seguro= ancho_max * 0.9
    alto_seguro= alto_max * 0.9
    while tam >= 4:
        interlineado= tam + 1.5
        lineas, actual = [], ""
        for palabra in palabras:
            candidato= (actual + " " + palabra).strip()
            if cvs.stringWidth(candidato, fuente, tam) <= ancho_seguro or not actual:
                actual= candidato
            else:
                lineas.append(actual)
                actual= palabra
        if actual:
            lineas.append(actual)
        if len(lineas) * interlineado <= alto_seguro and all(
                cvs.stringWidth(l, fuente, tam) <= ancho_seguro for l in lineas):
            break
        tam -= 0.5
    else:
        tam= 4
        interlineado= tam + 1.5
    cvs.setFont(fuente, tam)
    y_inicio= y_centro + (len(lineas) - 1) * interlineado / 2
    for i, linea in enumerate(lineas):
        cvs.drawCentredString(cx, y_inicio - i * interlineado, linea.strip())


def _dibujar_texto_multilinea_lista(cvs, items, cx, y_centro, ancho_max, alto_max, tamano_inicial=6.5,
                                    negrita=True, vineta="\u2022 ", espacio_entre_items=0.55):
    """Como `_dibujar_texto_multilinea`, pero para una LISTA de nombres (las
    competencias fundamentales que integran un mismo grupo de columnas):
    cada una va en su propia línea con una viñeta "•" delante, en vez de
    concatenarlas con " / " en un solo párrafo -así se ve la plantilla
    oficial del MINERD en un boletín real.

    `espacio_entre_items` (en unidades de interlineado) abre un huequito
    ENTRE una competencia y la siguiente -no entre las líneas en que se
    partió una misma competencia larga- tal como en la foto del boletín
    oficial: cada viñeta se lee como una entrada separada de la lista, no
    todas pegadas unas a otras."""
    items= [str(i) for i in (items or []) if i]
    if not items:
        return
    fuente= "Helvetica-Bold" if negrita else "Helvetica"
    tam= tamano_inicial
    ancho_seguro= ancho_max * 0.9
    alto_seguro= alto_max * 0.9
    lineas= [(i, True) for i in items]
    while tam >= 4:
        interlineado= tam + 1.5
        ancho_vineta= cvs.stringWidth(vineta, fuente, tam)
        lineas= []
        for item in items:
            palabras= item.split(" ")
            actual, primera = "", True
            for palabra in palabras:
                candidato= (actual + " " + palabra).strip()
                limite= (ancho_seguro - ancho_vineta) if primera else ancho_seguro
                if cvs.stringWidth(candidato, fuente, tam) <= limite or not actual:
                    actual= candidato
                else:
                    lineas.append(((vineta + actual) if primera else actual, primera))
                    primera= False
                    actual= palabra
            if actual:
                lineas.append(((vineta + actual) if primera else actual, primera))
        n_items= sum(1 for _, inicio in lineas if inicio)
        alto_necesario= len(lineas) * interlineado + (n_items - 1) * espacio_entre_items * interlineado
        if alto_necesario <= alto_seguro and all(
                cvs.stringWidth(l, fuente, tam) <= ancho_seguro for l, _ in lineas):
            break
        tam -= 0.5
    else:
        tam= 4
        interlineado= tam + 1.5
        n_items= sum(1 for _, inicio in lineas if inicio)
    extra= espacio_entre_items * interlineado
    alto_total= len(lineas) * interlineado + (n_items - 1) * extra
    cvs.setFont(fuente, tam)
    y= y_centro + (alto_total - interlineado) / 2
    for indice, (linea, inicio_item) in enumerate(lineas):
        if indice > 0 and inicio_item:
            y -= extra
        cvs.drawCentredString(cx, y, linea.strip())
        y -= interlineado


def _alto_extra_datos_institucion(institucion):
    """Alto extra que hay que sumarle a la página cuando el encabezado va a
    imprimir Distrito Educativo y/o Dirección debajo del nombre de la
    institución (ver `_dibujar_datos_institucion` más abajo): 13pt por cada
    renglón que en verdad se vaya a dibujar -si Configuración > Institución
    no tiene cargado ese dato, ese boletín en particular no reserva espacio
    para un renglón vacío, igual que ya hace el resto del boletín con
    cualquier otro bloque opcional."""
    institucion= institucion or {}
    extra= 0
    if institucion.get("distrito"):
        extra += 13
    if institucion.get("direccion"):
        extra += 13
    return extra


def _dibujar_datos_institucion(cvs, ancho, y, institucion, tamano_nombre=9, tamano_extra=8):
    """Dibuja, centrados, el nombre de la institución y -si están
    cargados- el Distrito Educativo y la Dirección, cada uno con la
    tipografía y el color que se hayan elegido en "Exportar Boletín" ->
    "Encabezado institucional" (ver `estilo_encabezado_institucion`).
    `y` es la posición del renglón del NOMBRE (el llamador ya dejó el
    espacio para esa primera línea); Distrito/Dirección, cuando aplican,
    corren `y` 13pt más abajo cada uno. Devuelve el `y` final, en la misma
    posición que devolvía esta función antes de existir Distrito/Dirección
    cuando ninguno de los dos está cargado -así ningún boletín existente
    cambia de aspecto por el simple hecho de tener esta preferencia."""
    estilo= institucion.get("estilo_encabezado") or {}

    def _renglon(texto, clave, tamano):
        cfg= estilo.get(clave) or {}
        fuente= cfg.get("fuente") or "Helvetica"
        if fuente not in _FUENTES_BOLETIN_VALIDAS:
            fuente= "Helvetica"
        cvs.setFont(_fuente_pdf_utilizable(fuente), tamano)
        cvs.setFillColorRGB(*_hex_a_rgb01(cfg.get("color") or "#000000"))
        cvs.drawCentredString(ancho / 2, y, texto)
        cvs.setFillColorRGB(0, 0, 0)

    _renglon(institucion.get("nombre") or "AcaDeXI", "nombre", tamano_nombre)
    if institucion.get("distrito"):
        y -= 13
        _renglon(f"Distrito Educativo {institucion['distrito']}", "distrito", tamano_extra)
    if institucion.get("direccion"):
        y -= 13
        _renglon(institucion["direccion"], "direccion", tamano_extra)
    return y


def _encabezado_institucional(cvs, ancho, y, institucion, titulo, subtitulo, rgb_banda, rgb_texto_banda, margen):
    from reportlab.lib.utils import ImageReader
    if institucion.get("logo"):
        try:
            img= ImageReader(institucion["logo"])
            iw, ih = img.getSize()
            alto_img= 36
            cvs.drawImage(img, margen, y - 28, width=alto_img * (iw / ih), height=alto_img,
                          preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    y -= _dibujar_logos_adicionales(cvs, ancho, y, institucion, margen)
    cvs.setFont("Helvetica-Bold", 13)
    cvs.drawCentredString(ancho / 2, y, titulo)
    y -= 18
    y= _dibujar_datos_institucion(cvs, ancho, y, institucion)
    #32 (antes 22): la banda de color necesita quedar lo bastante más abajo
    #del logo institucional/adicionales como para que el rectángulo sólido de la banda -que se pinta DESPUÉS,
    #encima de lo ya dibujado- no le tape la base a un logo alto (p. ej. un sello/escudo circular): con 22 quedaban
    #a 1pt de distancia, tan pegados que la banda literalmente pintaba por encima del borde inferior del logo ("se
    #entrecorta con la barra"). Con 32 el logo institucional (alto 36, ver más arriba) queda a 9pt de la banda y el
    #más alto de los adicionales (36, ver `_dibujar_logos_adicionales`) también -ver `_alto_extra_area_tecnica` y
    #los `_dimensiones_pagina_*`, que ya suman este mismo extra al alto total de la página para que nada se corra
    #fuera de la hoja.
    y -= 32
    cvs.setFillColorRGB(*rgb_banda)
    cvs.rect(margen, y - 5, ancho - 2 * margen, 18, fill=1, stroke=0)
    cvs.setFillColorRGB(*rgb_texto_banda)
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawCentredString(ancho / 2, y, subtitulo)
    cvs.setFillColorRGB(0, 0, 0)
    return y - 28


def _caja_datos_estudiante(cvs, x0, y, ancho, est, alto_fila=23):
    """Grilla de 2 filas x 3 columnas con los datos del estudiante (borde
    por celda, etiqueta pequeña arriba y valor debajo), en vez de una sola
    línea de texto corrido separando cada dato con espacios fijos -eso se
    desalinea apenas un nombre o un año escolar es más largo que otro (ver
    boletín ya diligenciado: "Nombre(s)...Grado:...Sección:" corrido sin
    columnas reales). Comparten esta misma caja Secundaria, Primaria y
    Técnico -son los mismos 6 datos en los tres formatos-.

    Si `est["area_tecnica"]` viene con valor (institución Politécnico o
    Personalizado+Politécnico, y el estudiante tiene un Área Técnica/
    especialidad asignada -ver datos_estudiante_boletin), se agrega una
    tercera fila de ancho completo con ese dato. En cualquier otro caso
    (Escuela normal, o Politécnico pero el estudiante aún sin especialidad
    asignada) la caja se ve exactamente igual que antes."""
    filas= [
        [("Nombre(s) y apellido(s)", f"{est['nombre']} {est['apellidos']}".strip()),
         ("Grado", est['grado_nombre'] or "—"),
         ("Sección", est['seccion_nombre'] or "—")],
        [("Año Escolar", est['anio_academico'] or "—"),
         ("Docente", est['docente'] or "—"),
         ("Número de orden", str(est['numero_orden']) if est['numero_orden'] else "—")],
    ]
    col_ancho= ancho / 3
    for fila in filas:
        for i, (etiqueta, valor) in enumerate(fila):
            cx= x0 + i * col_ancho
            cvs.rect(cx, y - alto_fila, col_ancho, alto_fila, stroke=1, fill=0)
            cvs.setFont("Helvetica-Bold", 5.8)
            cvs.setFillColorRGB(0.35, 0.35, 0.35)
            cvs.drawString(cx + 5, y - 9, etiqueta.upper())
            cvs.setFillColorRGB(0, 0, 0)
            _dibujar_texto_ajustado(cvs, valor, cx + 5, y - alto_fila + 6, col_ancho - 10,
                                    centrado=False, tamano_inicial=7.8, negrita=False)
        y -= alto_fila

    if est.get("area_tecnica"):
        cvs.rect(x0, y - alto_fila, ancho, alto_fila, stroke=1, fill=0)
        cvs.setFont("Helvetica-Bold", 5.8)
        cvs.setFillColorRGB(0.35, 0.35, 0.35)
        cvs.drawString(x0 + 5, y - 9, "ÁREA TÉCNICA")
        cvs.setFillColorRGB(0, 0, 0)
        _dibujar_texto_ajustado(cvs, est["area_tecnica"], x0 + 5, y - alto_fila + 6, ancho - 10,
                                centrado=False, tamano_inicial=7.8, negrita=False)
        y -= alto_fila

    return y - 8


def _alto_extra_area_tecnica(est, alto_fila=20):
    """Cuánto más alta debe ser la página cuando `_caja_datos_estudiante`
    va a dibujar la fila extra de Área Técnica -para que las funciones de
    dimensiones (_dimensiones_pagina_secundaria/primaria) reserven el
    mismo espacio exacto que va a usar el dibujante real, sin recortar ni
    dejar sobrante."""
    return alto_fila if est.get("area_tecnica") else 0


def _firmas(cvs, ancho, margen, y_base, institucion, etiqueta_izq, etiqueta_der, centrar_izq=False,
            con_sello=False):
    """`centrar_izq=True` centra la firma de la izquierda (en vez de
    pegarla al margen) -se usa cuando arriba, en la misma columna
    izquierda, ya se dibujó el "Sello" de la sección de Firma de Padres
    (ver `_dibujar_seccion_firma_padres`): dos elementos distintos pegados
    al mismo margen izquierdo, uno encima del otro, se ven amontonados: al
    separar la firma hacia el centro de la página queda un reparto más
    equilibrado (Sello a la izquierda, esta firma al centro, la otra
    firma a la derecha) en vez de dos columnas vacías a la derecha.

    `con_sello=True` dibuja el Sello en ESTA misma fila, en la columna
    izquierda, con la misma línea y el mismo ancho que las dos firmas.

    Antes el Sello se dibujaba en su propia franja, 50pt por ENCIMA de esta
    fila, así que quedaba desalineado: tres elementos pensados como una fila
    (Sello · Maestro(a) · Director(a)) con uno de ellos flotando más arriba y
    con una línea de menos de la mitad de largo. Con `con_sello=True` el ancho
    útil se reparte en TRES columnas iguales en vez de anclar las firmas a los
    márgenes: así los tres bloques quedan alineados y con el mismo ancho sin
    depender de que sobre sitio a la izquierda. Es el mismo criterio que ya usa
    `boletin_estilo.dibujar_firmas` para repartir N bloques.

    La franja que el Sello ocupaba antes NO se pierde: `_dibujar_seccion_firma_padres`
    la sigue reservando, porque es un timbre físico y necesita su espacio."""
    from reportlab.lib.utils import ImageReader
    ancho_firma= 170
    x_sello= None
    if con_sello:
        ancho_col= (ancho - 2 * margen) / 3
        ancho_firma= min(ancho_firma, ancho_col - 14)
        x_sello= margen + (ancho_col - ancho_firma) / 2
        x_izq= margen + ancho_col + (ancho_col - ancho_firma) / 2
        x_der= margen + 2 * ancho_col + (ancho_col - ancho_firma) / 2
    else:
        x_der= ancho - margen - 20 - ancho_firma
        x_izq= margen + 20
        if centrar_izq:
            x_centrada= (ancho - ancho_firma) / 2
            #Si la página es angosta (pocos períodos/grupos) centrar podría solapar con la firma de la derecha -en ese caso
            #no vale la pena forzarlo, se deja como estaba (mejor amontonado que encimado).
            if x_centrada + ancho_firma + 20 <= x_der:
                x_izq= x_centrada
    if institucion.get("firma"):
        try:
            img= ImageReader(institucion["firma"])
            iw, ih = img.getSize()
            alto_img= 26
            cvs.drawImage(img, x_der + ancho_firma / 2 - (alto_img * (iw / ih)) / 2, y_base + 4,
                          width=alto_img * (iw / ih), height=alto_img, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    cvs.setFont("Helvetica", 7.5)
    if x_sello is not None:
        cvs.line(x_sello, y_base, x_sello + ancho_firma, y_base)
        cvs.drawCentredString(x_sello + ancho_firma / 2, y_base - 10, "Sello")
    cvs.line(x_izq, y_base, x_izq + ancho_firma, y_base)
    cvs.line(x_der, y_base, x_der + ancho_firma, y_base)
    cvs.drawCentredString(x_izq + ancho_firma / 2, y_base - 10, etiqueta_izq)
    cvs.drawCentredString(x_der + ancho_firma / 2, y_base - 10, etiqueta_der)






def _alto_extra_firma_padres(periodos, mostrar_firma_padres=None, mostrar_situacion_final=None):
    """Alto adicional que hay que reservar en la página para el/los
    bloque(s) opcionales de Firma de Padres y/o Situación Final +
    Observaciones -son dos preferencias independientes (ver
    `mostrar_firma_padres_boletin`/`mostrar_situacion_final_boletin`) que
    pueden estar activas por separado o juntas; el alto necesario es el
    mismo en los tres casos con al menos una activa (una fila por período +
    una fila fija de "Fin de Año Escolar" + el espacio del Sello/caja de
    Observaciones), igual que ya hace `_alto_extra_area_tecnica`/
    `_alto_extra_logos_adicionales` con sus propios bloques opcionales."""
    if mostrar_firma_padres is None:
        mostrar_firma_padres= mostrar_firma_padres_boletin()
    if mostrar_situacion_final is None:
        mostrar_situacion_final= mostrar_situacion_final_boletin()
    if not mostrar_firma_padres and not mostrar_situacion_final:
        return 0
    n_filas= (len(periodos) if periodos else 4) + 1
    return 16 + n_filas * 15 + 68  #encabezado + filas + espacio del Sello/caja de Observaciones


def _dibujar_seccion_firma_padres(cvs, margen, ancho, y_inicio, periodos, rgb_banda, rgb_texto_banda,
                                   mostrar_firma_padres=True, mostrar_situacion_final=True):
    """Dibuja el/los bloque(s) opcional(es) -ver `mostrar_firma_padres_boletin`
    y `mostrar_situacion_final_boletin`, ahora preferencias INDEPENDIENTES
    entre sí: tabla de firma de padres/madres por período + franja del Sello (columna
    izquierda) y Situación Final del Estudiante (círculos Promovido/
    Reprobado) + Observaciones (columna derecha) -mismo formato en papel de
    la plantilla de referencia. Cada columna solo se dibuja si su flag
    correspondiente es True; si solo una de las dos está activa, esa única
    columna se estira al ancho completo disponible en vez de dejar la mitad
    de la página en blanco. Usa la MISMA banda de color del boletín
    (`rgb_banda`/`rgb_texto_banda`) en los encabezados, para que se vea
    integrado y no como un bloque aparte con estilo propio. Devuelve la "y"
    final (la más baja de las columnas dibujadas) para que el llamador
    coloque las firmas de Maestro(a)/Director(a) debajo sin solaparse."""
    alto_header= 16
    alto_fila= 15
    ancho_disponible= ancho - 2 * margen

    def rect_banda(x, y_top, w, h, rgb=rgb_banda):
        cvs.setFillColorRGB(*rgb)
        cvs.rect(x, y_top - h, w, h, fill=1, stroke=1)
        cvs.setFillColorRGB(*rgb_texto_banda)

    if mostrar_firma_padres and mostrar_situacion_final:
        ancho_izq= ancho_disponible * 0.52
        ancho_der= ancho_disponible - ancho_izq - 20
    elif mostrar_firma_padres:
        ancho_izq= ancho_disponible
        ancho_der= 0
    else:
        ancho_izq= 0
        ancho_der= ancho_disponible
    x_izq= margen
    x_der= margen + ancho_izq + (20 if (mostrar_firma_padres and mostrar_situacion_final) else 0)

    y_izq_final= None
    y_der_final= None

    if mostrar_firma_padres:
        col_periodo= 95
        col_firma= ancho_izq - col_periodo

        filas= [p["nombre"] for p in periodos] if periodos else []
        filas= filas + ["Fin de Año Escolar"]

        #--- Columna izquierda: PERIODO | FIRMA DEL PADRE, MADRE O TUTOR ---
        y= y_inicio
        rect_banda(x_izq, y, col_periodo, alto_header)
        cvs.setFont("Helvetica-Bold", 7)
        cvs.drawCentredString(x_izq + col_periodo / 2, y - alto_header + 5, "PERIODO")
        rect_banda(x_izq + col_periodo, y, col_firma, alto_header)
        cvs.drawCentredString(x_izq + col_periodo + col_firma / 2, y - alto_header + 5,
                              "FIRMA DEL PADRE, MADRE O TUTOR")
        cvs.setFillColorRGB(0, 0, 0)
        y -= alto_header

        cvs.setFont("Helvetica", 7)
        for etiqueta in filas:
            cvs.rect(x_izq, y - alto_fila, col_periodo, alto_fila, stroke=1, fill=0)
            _dibujar_texto_ajustado(cvs, etiqueta, x_izq + 4, y - alto_fila + 4, col_periodo - 6, centrado=False,
                                    tamano_inicial=7)
            #Alineada con la etiqueta del período (misma altura que su texto, "y - alto_fila + 4"): antes estaba en "y -
            #4", casi pegada al borde SUPERIOR de la fila -a solo 4pt del borde que separa esta fila de la anterior-, así
            #que se veía como si le perteneciera a la fila de arriba en vez de a su propia
            #etiqueta ("doble línea" reportada).
            cvs.line(x_izq + col_periodo + 8, y - alto_fila + 4, x_izq + col_periodo + col_firma - 8,
                     y - alto_fila + 4)
            y -= alto_fila
        y_tabla_final= y

        #La franja del Sello se SIGUE reservando -es un timbre físico y
        #necesita su espacio de sobra-, pero el Sello ya no se dibuja aquí:
        #ahora comparte la fila de las firmas de Maestro(a)/Director(a), para quedar alineado con ellas (ver `_firmas`,
        #parámetro `con_sello`). El alto reservado es exactamente el mismo de antes (la línea del Sello estaba en `y` y
        #su etiqueta en `y - 10`, que es lo que se devuelve), así que la fila de firmas no se mueve de donde estaba.
        y -= 50  #antes 34 (y 22 originalmente): el Sello es un timbre físico, necesita espacio de sobra
        y_izq_final= y - 10
    else:
        #Sin tabla de firmas, la caja de Observaciones (si se dibuja) usa una altura de referencia fija en vez de
        #calzar con una tabla que no existe en esta página.
        n_filas= (len(periodos) if periodos else 4) + 1
        y_tabla_final= y_inicio - alto_header - n_filas * alto_fila

    if mostrar_situacion_final:
        #--- Columna derecha: SITUACIÓN FINAL DEL ESTUDIANTE + OBSERVACIONES ---
        y= y_inicio
        rect_banda(x_der, y, ancho_der, alto_header)
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x_der + 6, y - alto_header + 5, "SITUACIÓN FINAL DEL ESTUDIANTE")
        cy= y - alto_header / 2
        cx1= x_der + ancho_der - 148
        cvs.circle(cx1, cy, 3.5, stroke=1, fill=0)
        cvs.setFont("Helvetica", 7)
        cvs.drawString(cx1 + 7, cy - 2.5, "Promovido")
        cx2= x_der + ancho_der - 68
        cvs.circle(cx2, cy, 3.5, stroke=1, fill=0)
        cvs.drawString(cx2 + 7, cy - 2.5, "Reprobado")
        cvs.setFillColorRGB(0, 0, 0)
        y -= alto_header

        rgb_obs= _aclarar(rgb_banda, 0.65)
        rect_banda(x_der, y, ancho_der, alto_header, rgb=rgb_obs)
        cvs.setFillColorRGB(0, 0, 0)
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawCentredString(x_der + ancho_der / 2, y - alto_header + 5, "OBSERVACIONES:")
        y -= alto_header

        alto_caja_obs= max(y_tabla_final - y, 40)  #misma altura que la tabla de firmas (si la hay)
        cvs.rect(x_der, y - alto_caja_obs, ancho_der, alto_caja_obs, stroke=1, fill=0)
        y -= alto_caja_obs
        y_der_final= y

    candidatos= [v for v in (y_izq_final, y_der_final) if v is not None]
    return min(candidatos) if candidatos else y_inicio


#PDF — SECUNDARIA (grilla transpuesta + cascada + asistencia + leyenda)

#SECUNDARIA (clásico)
SEC_COL_LABEL= 130
SEC_COL_PERIODO= 22
SEC_COL_CF= 34
SEC_COL_CASCADA= 26
SEC_COL_AR= 20


def _ancho_pagina_secundaria(n_grupos, n_periodos, mostrar_situacion_automatica=True):
    margen= 32
    ancho_grupos= n_grupos * n_periodos * SEC_COL_PERIODO
    ancho_pc= n_periodos * SEC_COL_PERIODO
    ancho_datos= (ancho_grupos + ancho_pc + SEC_COL_CF + 4 * SEC_COL_CASCADA + 4 * SEC_COL_CASCADA
                   + 2 * SEC_COL_CASCADA + (2 * SEC_COL_AR if mostrar_situacion_automatica else 0))
    return 2 * margen + SEC_COL_LABEL + ancho_datos, margen


def dibujar_boletin_secundaria_oficial(cvs, institucion, boletin, colores=None, mostrar_resumen_asistencia=None,
                                        mostrar_situacion_automatica=None, mostrar_leyenda=None,
                                        mostrar_firma_padres=None, mostrar_situacion_final=None):
    """`mostrar_resumen_asistencia`/`mostrar_situacion_automatica`/
    `mostrar_leyenda`/`mostrar_firma_padres`/`mostrar_situacion_final`:
    None usa la preferencia guardada en Configuración
    (`mostrar_resumen_asistencia_boletin`/`mostrar_situacion_automatica_boletin`/
    `mostrar_leyenda_boletin`/`mostrar_firma_padres_boletin`/
    `mostrar_situacion_final_boletin`); True/False la fuerza explícitamente
    (usado por el diálogo "Exportar Boletín" para que la exportación
    puntual respete lo elegido ahí mismo sin tener que guardarlo antes en
    Configuración). `mostrar_firma_padres` y `mostrar_situacion_final` son
    preferencias INDEPENDIENTES entre sí -ver `_dibujar_seccion_firma_padres`."""
    colores= colores or colores_boletin(boletin["estudiante"]["nivel_educativo"])
    rgb_banda= _hex_a_rgb01(colores["banda"])
    rgb_texto_banda= _hex_a_rgb01(colores["texto_banda"])

    est= boletin["estudiante"]
    periodos= boletin["periodos"]
    n_periodos= max(len(periodos), 1)
    grupos_display= boletin["grupos_display"]
    areas= boletin["areas"]
    mostrar_ar_automatico= (mostrar_situacion_automatica if mostrar_situacion_automatica is not None
                             else mostrar_situacion_automatica_boletin())
    mostrar_firma_padres_final= (mostrar_firma_padres if mostrar_firma_padres is not None
                                  else mostrar_firma_padres_boletin())
    mostrar_situacion_final_final= (mostrar_situacion_final if mostrar_situacion_final is not None
                                     else mostrar_situacion_final_boletin())

    ancho, margen = _ancho_pagina_secundaria(len(grupos_display), n_periodos, mostrar_ar_automatico)
    alto_fila= 16
    n_filas_cuerpo= max(len(areas), 1)
    alto= (226 + n_filas_cuerpo * alto_fila + 248 + _alto_extra_area_tecnica(est)
            + _alto_extra_logos_adicionales(institucion)
            + _alto_extra_datos_institucion(institucion)
            + _alto_extra_firma_padres(periodos, mostrar_firma_padres_final,
                                        mostrar_situacion_final_final))  #cabecera (+10: espacio logo/banda, ver _encabezado_institucional) + grilla + cajas inferiores


    y= alto - 38
    y= _encabezado_institucional(
        cvs, ancho, y, institucion, "BOLETÍN DE CALIFICACIONES",
        f"{est['grado_nombre']} — {est['nivel_educativo'] or 'Secundaria'} — CALIFICACIONES DE RENDIMIENTO",
        rgb_banda, rgb_texto_banda, margen)

    y= _caja_datos_estudiante(cvs, margen, y, ancho - 2 * margen, est)

    x0= margen
    fila1_y= y - 6
    fila2_y= fila1_y - 30
    alto_doble= 46

    def rect_relleno(x, y_top, w, h):
        cvs.setFillColorRGB(*rgb_banda)
        cvs.rect(x, y_top - h, w, h, fill=1, stroke=1)
        cvs.setFillColorRGB(*rgb_texto_banda)

    x= x0
    #Columna "Áreas Curriculares" (ocupa las 2 filas de encabezado)
    rect_relleno(x, fila1_y, SEC_COL_LABEL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Áreas Curriculares", x + SEC_COL_LABEL / 2, fila1_y - alto_doble / 2 + 3,
                              SEC_COL_LABEL - 6, alto_doble - 6, tamano_inicial=8)
    cvs.setFillColorRGB(0, 0, 0)
    x += SEC_COL_LABEL

    columnas= []  #(x, ancho, getter(area) -> str, es_final)
    for etiqueta, incluidos in grupos_display:
        ancho_grupo= n_periodos * SEC_COL_PERIODO
        rect_relleno(x, fila1_y, ancho_grupo, alto_doble - 14)
        _dibujar_texto_multilinea_lista(cvs, incluidos, x + ancho_grupo / 2, fila1_y - (alto_doble - 14) / 2 + 3,
                                        ancho_grupo - 4, alto_doble - 20, tamano_inicial=6)
        cvs.setFillColorRGB(0, 0, 0)
        for i, periodo in enumerate(periodos):
            cx= x + i * SEC_COL_PERIODO
            cvs.rect(cx, fila2_y - 14, SEC_COL_PERIODO, 14, stroke=1, fill=0)
            _dibujar_texto_ajustado(cvs, periodo["nombre"], cx + SEC_COL_PERIODO / 2, fila2_y - 10,
                                    SEC_COL_PERIODO - 2, tamano_inicial=6)
            et_local= etiqueta
            idx_local= i
            columnas.append((cx, SEC_COL_PERIODO,
                              lambda a, et=et_local, ix=idx_local: _fmt(a["grilla"]["grupos"].get(et, [None] * n_periodos)[ix]),
                              False))
        x += ancho_grupo

    ancho_pc= n_periodos * SEC_COL_PERIODO
    rect_relleno(x, fila1_y, ancho_pc, alto_doble - 14)
    _dibujar_texto_multilinea(cvs, "PROMEDIO GRUPO DE COMPETENCIAS ESPECÍFICAS", x + ancho_pc / 2,
                              fila1_y - (alto_doble - 14) / 2 + 3, ancho_pc - 4, alto_doble - 20, tamano_inicial=5.5)
    cvs.setFillColorRGB(0, 0, 0)
    for i in range(n_periodos):
        cx= x + i * SEC_COL_PERIODO
        cvs.rect(cx, fila2_y - 14, SEC_COL_PERIODO, 14, stroke=1, fill=0)
        cvs.setFont("Helvetica-Bold", 6)
        cvs.drawCentredString(cx + SEC_COL_PERIODO / 2, fila2_y - 10, f"PC{i + 1}")
        ix= i
        columnas.append((cx, SEC_COL_PERIODO, lambda a, ix=ix: _fmt(a["grilla"]["pc"][ix] if ix < len(a["grilla"]["pc"]) else None), False))
    x += ancho_pc

    rgb_resaltado_hdr= _aclarar(rgb_banda, 0.55)
    cvs.setFillColorRGB(*rgb_resaltado_hdr)
    cvs.rect(x, fila1_y - alto_doble, SEC_COL_CF, alto_doble, fill=1, stroke=1)
    cvs.setFillColorRGB(0, 0, 0)
    _dibujar_texto_multilinea(cvs, "CALIFICACIÓN FINAL DEL ÁREA", x + SEC_COL_CF / 2, fila1_y - alto_doble / 2 + 3,
                              SEC_COL_CF - 4, alto_doble - 6, tamano_inicial=6)
    columnas.append((x, SEC_COL_CF, lambda a: _fmt(a["grilla"]["final"]), True))
    x += SEC_COL_CF

    def bloque_cascada(titulo, subcols):
        nonlocal x
        ancho_bloque= len(subcols) * SEC_COL_CASCADA
        rect_relleno(x, fila1_y, ancho_bloque, alto_doble - 14)
        _dibujar_texto_multilinea(cvs, titulo, x + ancho_bloque / 2, fila1_y - (alto_doble - 14) / 2 + 3,
                                  ancho_bloque - 4, alto_doble - 20, tamano_inicial=5.5)
        cvs.setFillColorRGB(0, 0, 0)
        for etiqueta_sub, clave in subcols:
            cvs.rect(x, fila2_y - 14, SEC_COL_CASCADA, 14, stroke=1, fill=0)
            _dibujar_texto_ajustado(cvs, etiqueta_sub, x + SEC_COL_CASCADA / 2, fila2_y - 10, SEC_COL_CASCADA - 2,
                                    tamano_inicial=5.5)
            clave_local= clave
            columnas.append((x, SEC_COL_CASCADA, lambda a, k=clave_local: _fmt(a["desglose"].get(k)), False))
            x += SEC_COL_CASCADA

    bloque_cascada("CALIFICACIÓN COMPLETIVA", [("50% C.F.", "cf_50"), ("C.E.C.", "cec"),
                                                ("50% C.E.C.", "cec_50"), ("C.C.F.", "ccf")])
    bloque_cascada("CALIFICACIÓN EXTRAORDINARIA", [("30% C.F.", "cf_30"), ("C.E. EX", "ce_ex"),
                                                    ("70% C.E. EX", "ce_ex_70"), ("C.EX.F.", "cexf")])
    bloque_cascada("EVALUACIÓN ESPECIAL", [("C.F.", "especial_cf"), ("C.E.", "especial_ce")])

    if mostrar_ar_automatico:
        ancho_sit= 2 * SEC_COL_AR
        rect_relleno(x, fila1_y, ancho_sit, alto_doble - 14)
        _dibujar_texto_multilinea(cvs, "SITUACIÓN FINAL", x + ancho_sit / 2,
                                  fila1_y - (alto_doble - 14) / 2 + 3, ancho_sit - 2, alto_doble - 14, tamano_inicial=5)
        cvs.setFillColorRGB(0, 0, 0)
        for j, letra in enumerate(("A", "R")):
            cx= x + j * SEC_COL_AR
            cvs.rect(cx, fila2_y - 14, SEC_COL_AR, 14, stroke=1, fill=0)
            cvs.setFont("Helvetica-Bold", 6.5)
            cvs.drawCentredString(cx + SEC_COL_AR / 2, fila2_y - 10, letra)
            letra_local= letra
            columnas.append((cx, SEC_COL_AR, lambda a, L=letra_local: ("X" if a["situacion"] == L else ""), False))

    y= fila2_y - 14
    cvs.rect(x0, fila1_y - alto_doble, ancho - 2 * margen, 0)  #no-op, mantiene referencia visual

    rgb_resaltado= _aclarar(rgb_banda, 0.8)
    cvs.setFont("Helvetica", 6.5)
    for area in areas:
        cvs.rect(x0, y - alto_fila, SEC_COL_LABEL, alto_fila, stroke=1, fill=0)
        _dibujar_texto_ajustado(cvs, area["materia_nombre"], x0 + 3, y - alto_fila + 4, SEC_COL_LABEL - 6,
                                centrado=False, tamano_inicial=6.5, negrita=False)
        for cx, cw, getter, resaltada in columnas:
            if resaltada:
                cvs.setFillColorRGB(*rgb_resaltado)
                cvs.rect(cx, y - alto_fila, cw, alto_fila, stroke=1, fill=1)
                cvs.setFillColorRGB(0, 0, 0)
            else:
                cvs.rect(cx, y - alto_fila, cw, alto_fila, stroke=1, fill=0)
            cvs.setFont("Helvetica-Bold" if resaltada else "Helvetica", 6.3)
            cvs.drawCentredString(cx + cw / 2, y - alto_fila + 4, getter(area))
        y -= alto_fila

    if not areas:
        cvs.setFont("Helvetica", 9)
        cvs.drawString(x0, y - 12, "Este estudiante no tiene áreas curriculares asignadas todavía.")
        y -= 24

    #--- Resumen de Asistencia (opcional) + Leyenda + Situación general + Condición final ---
    y -= 22
    y_cajas_top= y
    ancho_asistencia= 190
    mostrar_asistencia= (mostrar_resumen_asistencia if mostrar_resumen_asistencia is not None
                          else mostrar_resumen_asistencia_boletin())
    if mostrar_asistencia:
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x0, y, "RESUMEN DE ASISTENCIA DEL/LA ESTUDIANTE")
        y -= 12
        encabezados_asis= ["Período", "Asist.", "Ausen.", "% Asist.", "% Ausen."]
        anchos_asis= [40, 34, 34, 40, 42]
        cx= x0
        cvs.setFont("Helvetica-Bold", 6)
        for h, w in zip(encabezados_asis, anchos_asis):
            cvs.rect(cx, y - 12, w, 12, stroke=1, fill=0)
            cvs.drawCentredString(cx + w / 2, y - 9, h)
            cx += w
        y -= 12
        total_asist, total_ausen = 0, 0
        hay_datos_asistencia= any(v.get("asistencia") is not None for v in boletin["asistencia"].values())
        for periodo in periodos:
            datos_p= boletin["asistencia"].get(periodo["id"], {})
            asis= datos_p.get("asistencia")
            ausen= datos_p.get("ausencia")
            if asis is not None:
                total_asist += asis
            if ausen is not None:
                total_ausen += ausen
            cx= x0
            valores_fila= [periodo["nombre"], _fmt(asis), _fmt(ausen), "", ""]
            cvs.setFont("Helvetica", 6)
            for val, w in zip(valores_fila, anchos_asis):
                cvs.rect(cx, y - 12, w, 12, stroke=1, fill=0)
                cvs.drawCentredString(cx + w / 2, y - 9, val)
                cx += w
            y -= 12
        if hay_datos_asistencia and (total_asist + total_ausen) > 0:
            pct_asis= 100 * total_asist / (total_asist + total_ausen)
            pct_ausen= 100 - pct_asis
        else:
            pct_asis= pct_ausen= None
        cx= x0
        valores_fila= ["Total", _fmt(total_asist) if hay_datos_asistencia else "", _fmt(total_ausen) if hay_datos_asistencia else "",
                        (_fmt(pct_asis, 1) + "%") if pct_asis is not None else "",
                        (_fmt(pct_ausen, 1) + "%") if pct_ausen is not None else ""]
        cvs.setFont("Helvetica-Bold", 6)
        for val, w in zip(valores_fila, anchos_asis):
            cvs.rect(cx, y - 12, w, 12, stroke=1, fill=0)
            cvs.drawCentredString(cx + w / 2, y - 9, val)
            cx += w
        y -= 12

    #Leyenda: si el resumen de asistencia no se muestra, la leyenda ocupa su lugar (arranca en x0) en vez de dejar
    #un hueco en blanco a la izquierda. Si la leyenda misma está desactivada (`mostrar_leyenda`), la Situación
    #del/de la Estudiante pasa a ocupar su lugar en vez de dejar todo el bloque derecho en blanco.
    mostrar_ley= mostrar_leyenda if mostrar_leyenda is not None else mostrar_leyenda_boletin()
    x_leyenda= (x0 + ancho_asistencia + 24) if mostrar_asistencia else x0
    y_l= y_cajas_top
    if mostrar_ley:
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x_leyenda, y_l, "LEYENDA")
        y_l -= 12
        leyenda= [("P1-P4", "Período 1 a 4"), ("PC", "Promedio Grupo de Competencias Específicas"),
                   ("C.F.", "Calificación Final"), ("C.E.C.", "Calificación Evaluación Completiva"),
                   ("C.C.F.", "Calificación Completiva Final"), ("C.E. EX", "Calificación Evaluación Extraordinaria"),
                   ("C.EX.F.", "Calificación Extraordinaria Final"), ("C.E.", "Calificación Especial")]
        if mostrar_ar_automatico:
            #Solo tiene sentido explicar A/R si esas columnas de verdad están en la grilla -con "Aprobación automática"
            #desactivada (ver `mostrar_situacion_automatica_boletin`) no existen.
            leyenda.append(("A / R", "Aprobado / Reprobado"))
        cvs.setFont("Helvetica", 6.3)
        for abrev, significado in leyenda:
            cvs.drawString(x_leyenda, y_l, f"{abrev}: {significado}")
            y_l -= 8.5

    #Situación general + condición final (a la derecha de la leyenda, o en su lugar si está desactivada). Este
    #bloque queda OCULTO por completo cuando "Situación Final" (`mostrar_situacion_final_final`, el bloque de
    #Promovido/Reprobado + Observaciones que se dibuja más abajo junto a Firma de Padres) está activo: los dos
    #dicen exactamente lo mismo (si el/la estudiante fue promovido/a o no), así que mostrar ambos a la vez es
    #redundante y confuso -con Situación Final activa, este es el que sobra. Si Situación Final está apagada, este
    #bloque se sigue dibujando como siempre (SIEMPRE se dibuja en ese caso -lo que cambia con "Aprobación
    #automática", `mostrar_ar_automatico`, es solo el contenido de sus casillas: con la opción activa se marcan
    #solas según `situacion_general`; con ella desactivada, Dirección quiere decidir a mano, así que las casillas
    #quedan en blanco ([ ] sin marcar) y "Condición Final" se deja como una línea vacía para escribir con lapicero,
    #en vez de imprimir un "Pendiente" que no aporta nada a un formulario que se va a llenar a mano).
    x_sit= (x_leyenda + 238) if mostrar_ley else x_leyenda
    y_s= y_cajas_top
    if not mostrar_situacion_final_final:
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x_sit, y_s, "SITUACIÓN DEL/DE LA ESTUDIANTE")
        y_s -= 14
        sg= boletin["situacion_general"] if mostrar_ar_automatico else {}
        cvs.setFont("Helvetica", 7.5)
        cvs.drawString(x_sit, y_s, ("[X]" if sg.get("promovido") else "[ ]") + " Promovido/a")
        cvs.drawString(x_sit + 90, y_s, ("[X]" if sg.get("repitiente") else "[ ]") + " Repitiente")
        y_s -= 22  #antes 16: quedaba casi pegado a "CONDICIÓN FINAL" (ver reporte de layout)
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x_sit, y_s, "CONDICIÓN FINAL DEL/DE LA ESTUDIANTE:")
        y_s -= 18  #antes 12: la línea/el texto quedaba casi tocando la etiqueta
        cvs.setFont("Helvetica", 7.5)
        if mostrar_ar_automatico:
            cvs.drawString(x_sit, y_s, sg.get("decision", "Pendiente"))
        else:
            cvs.line(x_sit, y_s - 2, x_sit + 200, y_s - 2)

    y_base_inferior= min(y, y_l, y_s)
    if mostrar_firma_padres_final or mostrar_situacion_final_final:
        y_base_inferior= _dibujar_seccion_firma_padres(cvs, margen, ancho, y_base_inferior - 10, periodos,
                                                         rgb_banda, rgb_texto_banda,
                                                         mostrar_firma_padres=mostrar_firma_padres_final,
                                                         mostrar_situacion_final=mostrar_situacion_final_final)
    y_firmas= y_base_inferior - 38
    _firmas(cvs, ancho, margen, y_firmas, institucion, "Maestro(a) Encargado(a) del Grado",
            "Director(a) del Centro Educativo", centrar_izq=mostrar_firma_padres_final,
            con_sello=mostrar_firma_padres_final)
    cvs.setFont("Helvetica", 6.5)
    cvs.drawString(margen, 16, f"Nota mínima aprobatoria: {boletin['nota_minima']:.0f}   |   "
                               f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d')}")
    return ancho, alto


def _dimensiones_pagina_secundaria(boletin, institucion=None, mostrar_situacion_automatica=None,
                                    mostrar_firma_padres=None, mostrar_situacion_final=None):
    """`institucion` es opcional (por compatibilidad con quien todavía
    llame a esta función sin ese argumento): sin ella no se reserva espacio
    extra para logos adicionales envueltos en más de una fila, exactamente
    el mismo comportamiento que tenía esta función antes de que existiera
    esa característica. Pasarla es lo que le permite a la página crecer por
    adelantado si los logos configurados necesitan más de una fila -ver
    `_alto_extra_logos_adicionales`. `mostrar_situacion_automatica` sigue el
    mismo patrón None=preferencia guardada que ya usan las demás opciones
    de boletín -afecta el ANCHO (2 columnas A/R menos si está apagada, ver
    `_ancho_pagina_secundaria`). `mostrar_firma_padres`/`mostrar_situacion_final`
    (independientes entre sí) afectan el ALTO -ver `_alto_extra_firma_padres`."""
    mostrar_ar_automatico= (mostrar_situacion_automatica if mostrar_situacion_automatica is not None
                             else mostrar_situacion_automatica_boletin())
    n_grupos= len(boletin["grupos_display"])
    n_periodos= max(len(boletin["periodos"]), 1)
    ancho, _ = _ancho_pagina_secundaria(n_grupos, n_periodos, mostrar_ar_automatico)
    alto= (226 + max(len(boletin["areas"]), 1) * 16 + 248 + _alto_extra_area_tecnica(boletin["estudiante"])
            + _alto_extra_logos_adicionales(institucion)
            + _alto_extra_datos_institucion(institucion)
            + _alto_extra_firma_padres(boletin["periodos"], mostrar_firma_padres,
                                        mostrar_situacion_final))  #226 (antes 216): +10 del espacio logo/banda, ver _encabezado_institucional
    return ancho, alto




#PRIMARIA (clásico)
PRI_COL_LABEL= 130
PRI_COL_PERIODO= 20
PRI_COL_RP= 20
PRI_COL_C= 34
PRI_COL_FINAL= 38


def _observaciones_por_periodo(estudiante_id, periodos):
    conn= obtener_conexion()
    c= conn.cursor()
    resultado= {}
    for periodo in periodos:
        if not periodo.get("fecha_inicio") or not periodo.get("fecha_fin"):
            resultado[periodo["id"]]= ""
            continue
        c.execute("""SELECT texto FROM observaciones WHERE estudiante_id=? AND fecha BETWEEN ? AND ?
                     ORDER BY fecha""", (estudiante_id, periodo["fecha_inicio"], periodo["fecha_fin"]))
        textos= [r["texto"] for r in c.fetchall()]
        resultado[periodo["id"]]= " / ".join(textos)
    conn.close()
    return resultado


def _recuperacion_final_area(estudiante_id, materia_id, anio_academico):
    """Reutiliza las mismas tablas de la cascada de Secundaria
    (`evaluacion_completiva` / `evaluacion_especial`): no son específicas de
    nivel, solo registran "una nota de recuperación de fin de año" para una
    materia -el nombre de columna que se les da en el PDF es lo que cambia
    según el documento (Secundaria las llama C.E.C./C.E.; Primaria las
    llama "Calificación recuperación final/especial")."""
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT nota_completiva FROM evaluacion_completiva WHERE estudiante_id=? AND materia_id=? AND anio_academico=?",
              (estudiante_id, materia_id, anio_academico))
    final= c.fetchone()
    c.execute("SELECT nota_especial FROM evaluacion_especial WHERE estudiante_id=? AND materia_id=? AND anio_academico=?",
              (estudiante_id, materia_id, anio_academico))
    especial= c.fetchone()
    conn.close()
    return {"recuperacion_final": final["nota_completiva"] if final else None,
            "recuperacion_especial": especial["nota_especial"] if especial else None}


def _dimensiones_pagina_primaria(boletin, institucion=None, mostrar_firma_padres=None,
                                  mostrar_situacion_final=None):
    """`institucion` es opcional (compatibilidad con llamadores previos a
    esta característica): sin ella no se reserva espacio extra para logos
    adicionales envueltos en más de una fila -ver
    `_alto_extra_logos_adicionales` en boletin_minerd.py. `mostrar_firma_
    padres`/`mostrar_situacion_final` son preferencias independientes -ver
    `_alto_extra_firma_padres`."""
    mostrar_rp= any(a.get("tiene_rp") for a in boletin["areas"])
    n_periodos= max(len(boletin["periodos"]), 1)
    subcols= 2 if mostrar_rp else 1
    ancho= (2 * 32 + PRI_COL_LABEL + len(boletin["grupos_display"]) * n_periodos * subcols * PRI_COL_PERIODO
             + len(boletin["grupos_display"]) * PRI_COL_C + 2 * PRI_COL_FINAL)
    alto= (226 + max(len(boletin["areas"]), 1) * 16 + 268 + _alto_extra_area_tecnica(boletin["estudiante"])
            + _alto_extra_logos_adicionales(institucion)
            + _alto_extra_datos_institucion(institucion)
            + _alto_extra_firma_padres(boletin["periodos"], mostrar_firma_padres,
                                        mostrar_situacion_final))  #226 (antes 216): +10 del espacio logo/banda, ver _encabezado_institucional
    return ancho, alto


def dibujar_informe_primaria_oficial(cvs, institucion, boletin, colores=None, mostrar_leyenda=None,
                                      mostrar_situacion_automatica=None, mostrar_firma_padres=None,
                                      mostrar_situacion_final=None):
    """`mostrar_leyenda`: None usa la preferencia guardada en Configuración
    (`mostrar_leyenda_boletin`); True/False la fuerza explícitamente (mismo
    patrón que `mostrar_resumen_asistencia`/`mostrar_situacion_automatica`
    en el Boletín de Secundaria). Aquí la "leyenda" es la caja "ESCALA
    DESCRIPTIVA" (rangos Destacado/Logrado/En Proceso/Insuficiente).

    `mostrar_situacion_automatica`: mismo patrón -None usa la preferencia
    guardada (`mostrar_situacion_automatica_boletin`); el bloque "SITUACIÓN
    DEL/DE LA ESTUDIANTE" + "CONDICIÓN FINAL" siempre se dibuja (Dirección
    necesita el espacio en el PDF para firmarlo a mano), pero con la opción
    desactivada las casillas quedan sin marcar y la condición final se deja
    como una línea en blanco para llenar con lapicero, en vez de imprimir
    marcas automáticas que no reflejan una decisión manual todavía.

    `mostrar_firma_padres`/`mostrar_situacion_final`: mismo patrón -None
    usa la preferencia guardada (`mostrar_firma_padres_boletin`/
    `mostrar_situacion_final_boletin`); son preferencias INDEPENDIENTES
    entre sí. La primera activa la tabla de Firma del Padre/Madre/Tutor por
    período + Sello; la segunda activa el bloque "SITUACIÓN FINAL DEL
    ESTUDIANTE" (Promovido/Reprobado) + Observaciones -ver
    `_dibujar_seccion_firma_padres` en boletin_minerd.py."""
    colores= colores or colores_boletin(boletin["estudiante"]["nivel_educativo"])
    rgb_banda= _hex_a_rgb01(colores["banda"])
    rgb_texto_banda= _hex_a_rgb01(colores["texto_banda"])

    est= boletin["estudiante"]
    periodos= boletin["periodos"]
    n_periodos= max(len(periodos), 1)
    grupos_display= boletin["grupos_display"]
    areas= boletin["areas"]
    anio= boletin["anio_academico"]

    mostrar_ar_automatico= (mostrar_situacion_automatica if mostrar_situacion_automatica is not None
                             else mostrar_situacion_automatica_boletin())
    mostrar_firma_padres_final= (mostrar_firma_padres if mostrar_firma_padres is not None
                                  else mostrar_firma_padres_boletin())
    mostrar_situacion_final_final= (mostrar_situacion_final if mostrar_situacion_final is not None
                                     else mostrar_situacion_final_boletin())

    mostrar_rp= any(a.get("tiene_rp") for a in areas)
    subcols_por_periodo= 2 if mostrar_rp else 1

    margen= 32
    ancho_grupos= len(grupos_display) * n_periodos * subcols_por_periodo * PRI_COL_PERIODO
    ancho_c= len(grupos_display) * PRI_COL_C
    ancho= 2 * margen + PRI_COL_LABEL + ancho_grupos + ancho_c + 2 * PRI_COL_FINAL
    alto_fila= 16
    n_filas_cuerpo= max(len(areas), 1)
    alto= (226 + n_filas_cuerpo * alto_fila + 268 + _alto_extra_area_tecnica(est)
            + _alto_extra_logos_adicionales(institucion)
            + _alto_extra_datos_institucion(institucion)
            + _alto_extra_firma_padres(periodos, mostrar_firma_padres_final,
                                        mostrar_situacion_final_final))  #226 (antes 216): +10 del espacio logo/banda, ver _encabezado_institucional

    recuperaciones= {a["materia_id"]: _recuperacion_final_area(est["id"], a["materia_id"], anio) for a in areas}
    observaciones= _observaciones_por_periodo(est["id"], periodos)

    y= alto - 38
    y= _encabezado_institucional(
        cvs, ancho, y, institucion, "INFORME DE APRENDIZAJE",
        f"{est['grado_nombre']} — {est['nivel_educativo'] or 'Primaria'} — DESEMPEÑO INDIVIDUAL DEL/LA ESTUDIANTE",
        rgb_banda, rgb_texto_banda, margen)

    y= _caja_datos_estudiante(cvs, margen, y, ancho - 2 * margen, est)

    x0= margen
    fila1_y= y - 6
    fila2_y= fila1_y - 30
    alto_doble= 46

    def rect_relleno(x, y_top, w, h):
        cvs.setFillColorRGB(*rgb_banda)
        cvs.rect(x, y_top - h, w, h, fill=1, stroke=1)
        cvs.setFillColorRGB(*rgb_texto_banda)

    x= x0
    rect_relleno(x, fila1_y, PRI_COL_LABEL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Áreas Curriculares", x + PRI_COL_LABEL / 2, fila1_y - alto_doble / 2 + 3,
                              PRI_COL_LABEL - 6, alto_doble - 6, tamano_inicial=8)
    cvs.setFillColorRGB(0, 0, 0)
    x += PRI_COL_LABEL

    columnas= []
    ancho_periodo_total= subcols_por_periodo * PRI_COL_PERIODO
    for etiqueta, _incluidos in grupos_display:
        ancho_grupo= n_periodos * ancho_periodo_total
        rect_relleno(x, fila1_y, ancho_grupo, alto_doble - 14)
        _dibujar_texto_multilinea(cvs, etiqueta, x + ancho_grupo / 2, fila1_y - (alto_doble - 14) / 2 + 3,
                                  ancho_grupo - 4, alto_doble - 18, tamano_inicial=5.5)
        cvs.setFillColorRGB(0, 0, 0)
        for i, periodo in enumerate(periodos):
            cx= x + i * ancho_periodo_total
            cvs.rect(cx, fila2_y - 14, PRI_COL_PERIODO, 14, stroke=1, fill=0)
            _dibujar_texto_ajustado(cvs, periodo["nombre"], cx + PRI_COL_PERIODO / 2, fila2_y - 10,
                                    PRI_COL_PERIODO - 2, tamano_inicial=6)
            et_local, idx_local = etiqueta, i
            columnas.append((cx, PRI_COL_PERIODO,
                              lambda a, et=et_local, ix=idx_local: _fmt(a["grilla"]["grupos"].get(et, [None] * n_periodos)[ix])))
            if mostrar_rp:
                cxr= cx + PRI_COL_PERIODO
                cvs.rect(cxr, fila2_y - 14, PRI_COL_RP, 14, stroke=1, fill=0)
                cvs.setFont("Helvetica-Bold", 5.5)
                cvs.drawCentredString(cxr + PRI_COL_RP / 2, fila2_y - 10, f"RP{i + 1}")
                columnas.append((cxr, PRI_COL_RP, lambda a, ix=idx_local: _fmt(a["rp"][ix] if ix < len(a["rp"]) else None)))
        x += ancho_grupo

    for i, (etiqueta, _incluidos) in enumerate(grupos_display):
        rect_relleno(x, fila1_y, PRI_COL_C, alto_doble)
        _dibujar_texto_multilinea(cvs, f"Calif. final C{i + 1}", x + PRI_COL_C / 2, fila1_y - alto_doble / 2 + 3,
                                  PRI_COL_C - 2, alto_doble - 6, tamano_inicial=6)
        cvs.setFillColorRGB(0, 0, 0)
        idx_local= i
        columnas.append((x, PRI_COL_C, lambda a, ix=idx_local: _fmt(a["grilla"]["finales_por_grupo"][ix]
                                                                 if ix < len(a["grilla"]["finales_por_grupo"]) else None)))
        x += PRI_COL_C

    rect_relleno(x, fila1_y, PRI_COL_FINAL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Calificación final del área", x + PRI_COL_FINAL / 2, fila1_y - alto_doble / 2 + 3,
                              PRI_COL_FINAL - 4, alto_doble - 6, tamano_inicial=5.5)
    cvs.setFillColorRGB(0, 0, 0)
    columnas.append((x, PRI_COL_FINAL, lambda a: _fmt(a["grilla"]["final"])))
    x += PRI_COL_FINAL

    rect_relleno(x, fila1_y, PRI_COL_FINAL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Calificación recuperación final/especial", x + PRI_COL_FINAL / 2,
                              fila1_y - alto_doble / 2 + 3, PRI_COL_FINAL - 4, alto_doble - 6, tamano_inicial=5)
    cvs.setFillColorRGB(0, 0, 0)

    def _texto_recuperacion(area):
        rec= recuperaciones.get(area["materia_id"], {})
        partes= []
        if rec.get("recuperacion_final") is not None:
            partes.append(_fmt(rec["recuperacion_final"]))
        if rec.get("recuperacion_especial") is not None:
            partes.append(_fmt(rec["recuperacion_especial"]))
        return " / ".join(partes)

    columnas.append((x, PRI_COL_FINAL, _texto_recuperacion))

    y= fila2_y - 14
    cvs.setFont("Helvetica", 6.5)
    for area in areas:
        cvs.rect(x0, y - alto_fila, PRI_COL_LABEL, alto_fila, stroke=1, fill=0)
        _dibujar_texto_ajustado(cvs, area["materia_nombre"], x0 + 3, y - alto_fila + 4, PRI_COL_LABEL - 6,
                                centrado=False, tamano_inicial=6.5, negrita=False)
        for cx, cw, getter in columnas:
            cvs.rect(cx, y - alto_fila, cw, alto_fila, stroke=1, fill=0)
            cvs.setFont("Helvetica", 6.3)
            cvs.drawCentredString(cx + cw / 2, y - alto_fila + 4, getter(area))
        y -= alto_fila

    if not areas:
        cvs.setFont("Helvetica", 9)
        cvs.drawString(x0, y - 12, "Este estudiante no tiene áreas curriculares asignadas todavía.")
        y -= 24

    #--- Observaciones por período ---
    y -= 22
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x0, y, "OBSERVACIONES")
    y -= 14
    for periodo in periodos:
        texto= observaciones.get(periodo["id"], "")
        cvs.rect(x0, y - 14, 40, 14, stroke=1, fill=0)
        _dibujar_texto_ajustado(cvs, periodo["nombre"], x0 + 20, y - 10, 38, tamano_inicial=6.5)
        cvs.rect(x0 + 40, y - 14, ancho - 2 * margen - 40, 14, stroke=1, fill=0)
        cvs.setFont("Helvetica", 6.5)
        _dibujar_texto_ajustado(cvs, texto or "—", x0 + 44, y - 10, ancho - 2 * margen - 48,
                                centrado=False, tamano_inicial=6.5, negrita=False)
        y -= 14
    y -= 20

    #--- Escala descriptiva (opcional) + Situación + Condición final ---
    mostrar_ley= mostrar_leyenda if mostrar_leyenda is not None else mostrar_leyenda_boletin()
    y_top_cajas= y
    if mostrar_ley:
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x0, y, "ESCALA DESCRIPTIVA")
        y -= 14
        for minimo, maximo, nivel, _desc in ESCALA_DESCRIPTIVA_PRIMARIA:
            rango= f"{minimo}-{maximo}" if maximo < 100 or minimo > 0 else f"{minimo}-{maximo}"
            cvs.setFont("Helvetica-Bold", 6.3)
            cvs.drawString(x0, y, f"{rango}:")
            cvs.setFont("Helvetica", 6.3)
            cvs.drawString(x0 + 48, y, nivel)
            y -= 10.5

    #Situación general: a la derecha de la escala, o en su lugar si está
    #desactivada (mismo criterio que Secundaria con Leyenda/Situación).
    #Este bloque queda OCULTO por completo cuando "Situación Final" (`mostrar_situacion_final_final`) está activo
    #-mismo criterio y misma razón que en Secundaria, ver el comentario largo en
    #`dibujar_boletin_secundaria_oficial`: los dos dicen exactamente lo mismo y mostrar ambos a la vez es
    #redundante. Si está apagada, este bloque se sigue dibujando como siempre; lo que cambia con
    #"Aprobación automática" es el contenido: activa -> casillas
    #marcadas solas según `situacion_general` y la decisión ya
    #registrada; desactivada -> las tres casillas quedan sin marcar y
    #"Condición Final" se deja como una línea en blanco para que Dirección la llene a mano con lapicero.
    x_sit= (x0 + 220) if mostrar_ley else x0
    y_s= y_top_cajas
    if not mostrar_situacion_final_final:
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x_sit, y_s, "SITUACIÓN DEL/DE LA ESTUDIANTE")
        y_s -= 16
        sg= boletin["situacion_general"] if mostrar_ar_automatico else {}
        cvs.setFont("Helvetica", 7.5)
        cvs.drawString(x_sit, y_s, ("[X]" if sg.get("promovido") else "[ ]") + " Promovido/a")
        y_s -= 14
        cvs.drawString(x_sit, y_s, ("[X]" if sg.get("aplazado") else "[ ]") + " Aplazado/a")
        y_s -= 14
        cvs.drawString(x_sit, y_s, ("[X]" if sg.get("repitiente") else "[ ]") + " Repitiente")
        y_s -= 24  #antes 18: quedaba casi pegado a "CONDICIÓN FINAL" (ver reporte de layout)
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawString(x_sit, y_s, "CONDICIÓN FINAL DEL/DE LA ESTUDIANTE:")
        y_s -= 20  #antes 14: la línea/el texto quedaba casi tocando la etiqueta
        cvs.setFont("Helvetica", 7.5)
        if mostrar_ar_automatico:
            cvs.drawString(x_sit, y_s, sg.get("decision", "Pendiente"))
        else:
            cvs.line(x_sit, y_s - 2, x_sit + 200, y_s - 2)

    y_base_inferior= min(y, y_s)
    if mostrar_firma_padres_final or mostrar_situacion_final_final:
        y_base_inferior= _dibujar_seccion_firma_padres(cvs, margen, ancho, y_base_inferior - 10, periodos,
                                                         rgb_banda, rgb_texto_banda,
                                                         mostrar_firma_padres=mostrar_firma_padres_final,
                                                         mostrar_situacion_final=mostrar_situacion_final_final)
    y_firmas= y_base_inferior - 38
    _firmas(cvs, ancho, margen, y_firmas, institucion, "Maestro(a) Encargado(a) del Grado",
            "Director(a) del Centro Educativo", centrar_izq=mostrar_firma_padres_final,
            con_sello=mostrar_firma_padres_final)
    cvs.setFont("Helvetica", 6.5)
    cvs.drawString(margen, 16, f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d')}")
    return ancho, alto




#PDF — grilla oficial técnica (apaisado): filas = módulos, columnas = RA1%...RAn% (contribución) + C.F., más el
#bloque de Situación/Condición Final del/de la estudiante.
def dibujar_boletin_tecnico_oficial(cvs, ancho, alto, institucion, boletin, colores=None,
                                     mostrar_situacion_automatica=None, mostrar_firma_padres=None):
    """`mostrar_situacion_automatica`: mismo patrón que en boletin_minerd.py
    / boletin_primaria_minerd.py -None usa la preferencia guardada
    (`mostrar_situacion_automatica_boletin`). El bloque "Situación del/de
    la Estudiante" + "Condición Final" siempre se dibuja; con la opción
    desactivada las casillas quedan sin marcar y "Condición Final" se deja
    como una línea en blanco para llenar a mano, en vez de imprimir marcas
    automáticas basadas en una decisión que Dirección todavía no tomó.

    `mostrar_firma_padres`: mismo patrón -None usa la preferencia guardada
    (`mostrar_firma_padres_boletin`); activa el mismo bloque opcional de
    Firma del Padre/Madre/Tutor por período + Sello, y Situación Final del
    Estudiante con Observaciones que ya tienen Secundaria y Primaria (ver
    `_dibujar_seccion_firma_padres` en boletin_minerd.py). El Politécnico
    no maneja "períodos" propios en su boletín RA -se reutilizan los
    períodos del año académico del boletín general (`periodos_del_anio`)
    para que las filas de la tabla coincidan con las del boletín de
    Competencias del mismo estudiante."""
    from reportlab.lib.utils import ImageReader
    #OJO: estas son las funciones CLÁSICAS definidas más arriba en este mismo módulo (_hex_a_rgb01,
    #_dibujar_texto_ajustado, _dibujar_datos_ institucion, _dibujar_seccion_firma_padres) -NO las del estilo
    #Moderno de boletin_minerd.py, que tienen un aspecto distinto. Solo `_dibujar_logos_adicionales` y
    #`periodos_del_anio` son realmente compartidas entre estilos (no cambiaron con el rediseño), así que esas sí se
    #importan desde boletin_minerd (ver cabecera del módulo).

    mostrar_situacion_final= (mostrar_situacion_automatica if mostrar_situacion_automatica is not None
                               else mostrar_situacion_automatica_boletin())
    mostrar_firma_padres_final= (mostrar_firma_padres if mostrar_firma_padres is not None
                                  else mostrar_firma_padres_boletin())

    colores= colores or {"banda": "#1F9E9E", "texto_banda": "#FFFFFF"}
    rgb_banda= _hex_a_rgb01(colores["banda"])
    rgb_texto_banda= _hex_a_rgb01(colores["texto_banda"])

    est= boletin["estudiante"]
    modulos= boletin["modulos"]
    max_ra= max(boletin["max_ra"], 1)

    margen= 36
    y= alto - 38
    if institucion.get("logo"):
        try:
            img= ImageReader(institucion["logo"])
            iw, ih = img.getSize()
            alto_img= 40
            cvs.drawImage(img, margen, y - 30, width=alto_img * (iw / ih), height=alto_img,
                          preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    y -= _dibujar_logos_adicionales(cvs, ancho, y, institucion, margen)
    cvs.setFont("Helvetica-Bold", 13)
    cvs.drawCentredString(ancho / 2, y, "BOLETÍN DE CALIFICACIONES Y MÓDULOS TÉCNICOS")
    y -= 18
    y= _dibujar_datos_institucion(cvs, ancho, y, institucion)
    #32 (antes 22): misma corrección que en boletin_minerd._encabezado_
    #institucional -con 22 el logo institucional (alto 40 aquí) quedaba a solo -3pt de la banda, es decir la banda
    #literalmente se pintaba ENCIMA de la base del logo. El boletín técnico ya usa carta apaisada con margen de
    #sobra, así que sumar estos 10pt no requiere agrandar la página.
    y -= 32

    cvs.setFillColorRGB(*rgb_banda)
    cvs.rect(margen, y - 5, ancho - 2 * margen, 18, fill=1, stroke=0)
    cvs.setFillColorRGB(*rgb_texto_banda)
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawCentredString(ancho / 2, y, f"{est['grado_nombre']} — CALIFICACIONES DE RENDIMIENTO TÉCNICO")
    cvs.setFillColorRGB(0, 0, 0)
    y -= 28

    #`_caja_datos_estudiante` clásica (definida arriba en este módulo), NO la del estilo Moderno.
    y= _caja_datos_estudiante(cvs, margen, y, ancho - 2 * margen, est)

    col_izq_ancho= 170  #nombre del módulo técnico
    col_cf_ancho= 40
    ancho_ra= ancho - 2 * margen - col_izq_ancho - col_cf_ancho
    col_ra_ancho= ancho_ra / max_ra
    alto_fila= 19
    x0= margen

    #Encabezado
    cvs.setFillColorRGB(*rgb_banda)
    cvs.rect(x0, y - alto_fila, col_izq_ancho, alto_fila, fill=1, stroke=0)
    for i in range(max_ra):
        cvs.rect(x0 + col_izq_ancho + i * col_ra_ancho, y - alto_fila, col_ra_ancho, alto_fila, fill=1, stroke=0)
    cvs.rect(x0 + col_izq_ancho + ancho_ra, y - alto_fila, col_cf_ancho, alto_fila, fill=1, stroke=0)
    cvs.setFillColorRGB(*rgb_texto_banda)
    cvs.setFont("Helvetica-Bold", 7)
    cvs.drawString(x0 + 4, y - alto_fila + 5, "Módulo Técnico")
    for i in range(max_ra):
        cx= x0 + col_izq_ancho + i * col_ra_ancho + col_ra_ancho / 2
        cvs.drawCentredString(cx, y - alto_fila + 5, f"RA{i + 1}%")
    cvs.drawCentredString(x0 + col_izq_ancho + ancho_ra + col_cf_ancho / 2, y - alto_fila + 5, "C.F.")
    cvs.setFillColorRGB(0, 0, 0)
    y -= alto_fila

    cvs.setFont("Helvetica", 7)
    for modulo in modulos:
        grilla= modulo["grilla"]
        cvs.rect(x0, y - alto_fila, col_izq_ancho, alto_fila, stroke=1, fill=0)
        etiqueta= modulo["materia_nombre"] + (f" ({modulo['codigo']})" if modulo["codigo"] else "")
        _dibujar_texto_ajustado(cvs, etiqueta, x0 + 3, y - alto_fila + 5, col_izq_ancho - 6,
                                centrado=False, tamano_inicial=7)
        for i in range(max_ra):
            cx= x0 + col_izq_ancho + i * col_ra_ancho
            cvs.rect(cx, y - alto_fila, col_ra_ancho, alto_fila, stroke=1, fill=0)
            if i < len(grilla["contribuciones"]):
                cvs.setFont("Helvetica", 7)
                cvs.drawCentredString(cx + col_ra_ancho / 2, y - alto_fila + 5, _fmt(grilla["contribuciones"][i]))
        cx_cf= x0 + col_izq_ancho + ancho_ra
        cvs.rect(cx_cf, y - alto_fila, col_cf_ancho, alto_fila, stroke=1, fill=0)
        cvs.setFont("Helvetica-Bold", 7.5)
        cvs.drawCentredString(cx_cf + col_cf_ancho / 2, y - alto_fila + 5,
                              _fmt(grilla["cf"]) if grilla["cf"] is not None else "Pend.")
        y -= alto_fila

    if not modulos:
        cvs.setFont("Helvetica", 9)
        cvs.drawString(x0, y - 14, "Este estudiante no tiene módulos técnicos asignados todavía.")
        y -= 28

    #--- Situación del/de la Estudiante: el bloque siempre se dibuja; con "Aprobación automática" desactivada las
    #casillas quedan sin marcar y "Condición Final" se deja como una línea en blanco para llenar a mano (ver
    #docstring de la función) ---
    y -= 26
    situacion= boletin["situacion"] if mostrar_situacion_final else {"situacion": "", "condicion_final": ""}
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawString(x0, y, "Situación del/de la Estudiante:")
    cvs.setFont("Helvetica", 9)
    marca_prom= "[X]" if situacion["situacion"] == "Promovido/a" else "[ ]"
    marca_rep= "[X]" if situacion["situacion"] == "Repitiente" else "[ ]"
    cvs.drawString(x0 + 180, y, f"{marca_prom} Promovido/a")
    cvs.drawString(x0 + 285, y, f"{marca_rep} Repitiente")
    y -= 20
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawString(x0, y, "Condición Final del/de la Estudiante:")
    cvs.setFont("Helvetica", 9)
    if mostrar_situacion_final:
        cvs.drawString(x0 + 195, y, situacion["condicion_final"] or "Pendiente")
    else:
        cvs.line(x0 + 195, y - 2, x0 + 395, y - 2)
    y -= 30

    if mostrar_firma_padres_final:
        periodos_tec= periodos_del_anio(boletin["anio_academico"])
        y= _dibujar_seccion_firma_padres(cvs, margen, ancho, y + 4, periodos_tec, rgb_banda, rgb_texto_banda)
        y -= 26

    #El Sello comparte ESTA línea con la firma de la Directora/Director (ver `_firmas` y
    #`_dibujar_seccion_firma_padres`): antes se dibujaba 50pt más arriba, en su propia franja, y quedaba
    #desalineado con la firma. El boletín técnico cierra solo con la Dirección (no lleva Maestro(a)), así que son
    #dos bloques -Sello a la izquierda y la firma a la derecha-, los dos con la misma línea y en la misma línea
    #base.
    ancho_bloque= 150
    y_linea= y - 3
    if mostrar_firma_padres_final:
        x_sello= margen + 20
        cvs.line(x_sello, y_linea, x_sello + ancho_bloque, y_linea)
        cvs.setFont("Helvetica", 7)
        cvs.drawCentredString(x_sello + ancho_bloque / 2, y_linea - 10, "Sello")
    if institucion.get("firma"):
        try:
            img= ImageReader(institucion["firma"])
            iw, ih = img.getSize()
            alto_img= 30
            x_firma= ancho - margen - 150
            cvs.drawImage(img, x_firma, y, width=alto_img * (iw / ih), height=alto_img,
                          preserveAspectRatio=True, mask='auto')
            cvs.line(x_firma, y_linea, x_firma + ancho_bloque, y_linea)
            cvs.setFont("Helvetica", 7)
            cvs.drawCentredString(x_firma + ancho_bloque / 2, y_linea - 10,
                                  "Directora/Director del Centro Educativo")
        except Exception:
            pass
    cvs.setFont("Helvetica", 7)
    cvs.drawString(margen, 20, f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d')}")


def _dimensiones_pagina_tecnico(boletin, institucion=None, mostrar_firma_padres=None):
    """`institucion` es opcional (compatibilidad con llamadores previos):
    el boletín técnico ya usa carta apaisada, con margen de sobra para una
    fila de logos adicionales -pero si alguno de los dos lados necesita más
    de una fila (varios logos cargados), se agrega esa altura extra en vez
    de dejar que se superponga con la grilla de abajo. Igual con
    `mostrar_firma_padres` -ver `_alto_extra_firma_padres` en
    boletin_minerd.py."""
    #`_alto_extra_logos_adicionales`, `_alto_extra_firma_padres` y `_alto_extra_datos_institucion` son las mismas
    #fórmulas en ambos
    #estilos (no cambiaron con el rediseño) -las de logos y período ya
    #están importadas en la cabecera del módulo; `_alto_extra_datos_ institucion` es la clásica definida arriba en
    #este mismo módulo.
    from reportlab.lib.pagesizes import letter, landscape
    ancho, alto = landscape(letter)
    periodos_tec= periodos_del_anio(boletin["anio_academico"]) if boletin else None
    return ancho, (alto + _alto_extra_logos_adicionales(institucion)
                   + _alto_extra_datos_institucion(institucion)
                   + _alto_extra_firma_padres(periodos_tec, mostrar_firma_padres))


