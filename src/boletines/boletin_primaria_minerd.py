"""Informe de Aprendizaje — Nivel Primario, Formato Oficial República
Dominicana (MINERD).

Complemento de boletin_minerd.py para el Nivel Primario: la plantilla real
("Informe de Aprendizaje") es un documento distinto al "Boletín de
Calificaciones" de Secundaria, no una variación menor -por eso vive en su
propio módulo en vez de una rama más dentro del mismo dibujante:
  - 3 grupos de competencias (no 4) -ver GRUPOS_DISPLAY_PRIMARIA en
    boletin_minerd.py-, con columnas "Calificación final por competencia"
    (C1-C3) en vez de "Promedio Grupo de Competencias Específicas" (PC1-PC4).
  - Columnas de Recuperación Pedagógica (RP1-RP4) intercaladas entre cada
    período, cuando el área tiene esa recuperación registrada (algunos
    grados de Primaria las usan, otros no -se decide por los datos, no por
    el nombre del grado, para no depender de convenciones de texto en
    `grados.nombre`).
  - Escala DESCRIPTIVA (Destacado/Logrado/En Proceso/Insuficiente) como
    leyenda -las celdas siguen siendo numéricas (0-100), igual que el resto
    de AcaDeXI; la leyenda solo explica cómo leerlas, tal como en la
    plantilla real.
  - Situación en 3 estados (Promovido/a, Aplazado/a, Repitiente) en vez del
    A/R por asignatura de Secundaria -en Primaria la situación es del año
    completo, no por área-.
  - Caja de Observaciones por período (texto libre del docente).
"""
from datetime import datetime

from src.nucleo.bd import obtener_conexion
from src.boletines.boletin_minerd import (colores_boletin, _hex_a_rgb01, _fmt, _dibujar_texto_ajustado,
                             _dibujar_texto_multilinea, _encabezado_institucional, _firmas,
                             ESCALA_DESCRIPTIVA_PRIMARIA)

COL_LABEL= 130
COL_PERIODO= 20
COL_RP= 20
COL_C= 34
COL_FINAL= 38


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


def _dimensiones_pagina_primaria(boletin):
    mostrar_rp= any(a.get("tiene_rp") for a in boletin["areas"])
    n_periodos= max(len(boletin["periodos"]), 1)
    subcols= 2 if mostrar_rp else 1
    ancho= (2 * 24 + COL_LABEL + len(boletin["grupos_display"]) * n_periodos * subcols * COL_PERIODO
             + len(boletin["grupos_display"]) * COL_C + 2 * COL_FINAL)
    alto= 170 + max(len(boletin["areas"]), 1) * 13 + 230
    return ancho, alto


def dibujar_informe_primaria_oficial(cvs, institucion, boletin, colores=None):
    colores= colores or colores_boletin(boletin["estudiante"]["nivel_educativo"])
    rgb_banda= _hex_a_rgb01(colores["banda"])
    rgb_texto_banda= _hex_a_rgb01(colores["texto_banda"])

    est= boletin["estudiante"]
    periodos= boletin["periodos"]
    n_periodos= max(len(periodos), 1)
    grupos_display= boletin["grupos_display"]
    areas= boletin["areas"]
    anio= boletin["anio_academico"]

    mostrar_rp= any(a.get("tiene_rp") for a in areas)
    subcols_por_periodo= 2 if mostrar_rp else 1

    margen= 24
    ancho_grupos= len(grupos_display) * n_periodos * subcols_por_periodo * COL_PERIODO
    ancho_c= len(grupos_display) * COL_C
    ancho= 2 * margen + COL_LABEL + ancho_grupos + ancho_c + 2 * COL_FINAL
    alto_fila= 13
    n_filas_cuerpo= max(len(areas), 1)
    alto= 170 + n_filas_cuerpo * alto_fila + 230

    recuperaciones= {a["materia_id"]: _recuperacion_final_area(est["id"], a["materia_id"], anio) for a in areas}
    observaciones= _observaciones_por_periodo(est["id"], periodos)

    y= alto - 34
    y= _encabezado_institucional(
        cvs, ancho, y, institucion, "INFORME DE APRENDIZAJE",
        f"{est['grado_nombre']} — {est['nivel_educativo'] or 'Primaria'} — DESEMPEÑO INDIVIDUAL DEL/LA ESTUDIANTE",
        rgb_banda, rgb_texto_banda, margen)

    cvs.setFont("Helvetica", 8.5)
    cvs.drawString(margen, y, f"Nombre(s) y apellido(s): {est['nombre']} {est['apellidos']}"
                              f"    Grado: {est['grado_nombre']}    Sección: {est['seccion_nombre']}")
    y -= 12
    cvs.drawString(margen, y, f"Año Escolar: {est['anio_academico']}    Docente: {est['docente'] or '—'}    "
                              f"Número de orden: {est['numero_orden'] or '—'}")
    y -= 16

    x0= margen
    fila1_y= y
    fila2_y= y - 26
    alto_doble= 40

    def rect_relleno(x, y_top, w, h):
        cvs.setFillColorRGB(*rgb_banda)
        cvs.rect(x, y_top - h, w, h, fill=1, stroke=1)
        cvs.setFillColorRGB(*rgb_texto_banda)

    x= x0
    rect_relleno(x, fila1_y, COL_LABEL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Áreas Curriculares", x + COL_LABEL / 2, fila1_y - alto_doble / 2 + 3,
                              COL_LABEL - 6, alto_doble - 6, tamano_inicial=8)
    cvs.setFillColorRGB(0, 0, 0)
    x += COL_LABEL

    columnas= []
    ancho_periodo_total= subcols_por_periodo * COL_PERIODO
    for etiqueta, _incluidos in grupos_display:
        ancho_grupo= n_periodos * ancho_periodo_total
        rect_relleno(x, fila1_y, ancho_grupo, alto_doble - 14)
        _dibujar_texto_multilinea(cvs, etiqueta, x + ancho_grupo / 2, fila1_y - (alto_doble - 14) / 2 + 3,
                                  ancho_grupo - 4, alto_doble - 18, tamano_inicial=5.5)
        cvs.setFillColorRGB(0, 0, 0)
        for i, periodo in enumerate(periodos):
            cx= x + i * ancho_periodo_total
            cvs.rect(cx, fila2_y - 14, COL_PERIODO, 14, stroke=1, fill=0)
            cvs.setFont("Helvetica-Bold", 6)
            cvs.drawCentredString(cx + COL_PERIODO / 2, fila2_y - 10, periodo["nombre"])
            et_local, idx_local = etiqueta, i
            columnas.append((cx, COL_PERIODO,
                              lambda a, et=et_local, ix=idx_local: _fmt(a["grilla"]["grupos"].get(et, [None] * n_periodos)[ix])))
            if mostrar_rp:
                cxr= cx + COL_PERIODO
                cvs.rect(cxr, fila2_y - 14, COL_RP, 14, stroke=1, fill=0)
                cvs.setFont("Helvetica-Bold", 5.5)
                cvs.drawCentredString(cxr + COL_RP / 2, fila2_y - 10, f"RP{i + 1}")
                columnas.append((cxr, COL_RP, lambda a, ix=idx_local: _fmt(a["rp"][ix] if ix < len(a["rp"]) else None)))
        x += ancho_grupo

    for i, (etiqueta, _incluidos) in enumerate(grupos_display):
        rect_relleno(x, fila1_y, COL_C, alto_doble)
        _dibujar_texto_multilinea(cvs, f"Calif. final C{i + 1}", x + COL_C / 2, fila1_y - alto_doble / 2 + 3,
                                  COL_C - 2, alto_doble - 6, tamano_inicial=6)
        cvs.setFillColorRGB(0, 0, 0)
        idx_local= i
        columnas.append((x, COL_C, lambda a, ix=idx_local: _fmt(a["grilla"]["finales_por_grupo"][ix]
                                                                 if ix < len(a["grilla"]["finales_por_grupo"]) else None)))
        x += COL_C

    rect_relleno(x, fila1_y, COL_FINAL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Calificación final del área", x + COL_FINAL / 2, fila1_y - alto_doble / 2 + 3,
                              COL_FINAL - 4, alto_doble - 6, tamano_inicial=5.5)
    cvs.setFillColorRGB(0, 0, 0)
    columnas.append((x, COL_FINAL, lambda a: _fmt(a["grilla"]["final"])))
    x += COL_FINAL

    rect_relleno(x, fila1_y, COL_FINAL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Calificación recuperación final/especial", x + COL_FINAL / 2,
                              fila1_y - alto_doble / 2 + 3, COL_FINAL - 4, alto_doble - 6, tamano_inicial=5)
    cvs.setFillColorRGB(0, 0, 0)

    def _texto_recuperacion(area):
        rec= recuperaciones.get(area["materia_id"], {})
        partes= []
        if rec.get("recuperacion_final") is not None:
            partes.append(_fmt(rec["recuperacion_final"]))
        if rec.get("recuperacion_especial") is not None:
            partes.append(_fmt(rec["recuperacion_especial"]))
        return " / ".join(partes)

    columnas.append((x, COL_FINAL, _texto_recuperacion))

    y= fila2_y - 14
    cvs.setFont("Helvetica", 6.5)
    for area in areas:
        cvs.rect(x0, y - alto_fila, COL_LABEL, alto_fila, stroke=1, fill=0)
        _dibujar_texto_ajustado(cvs, area["materia_nombre"], x0 + 3, y - alto_fila + 4, COL_LABEL - 6,
                                centrado=False, tamano_inicial=6.5, negrita=False)
        for cx, cw, getter in columnas:
            cvs.rect(cx, y - alto_fila, cw, alto_fila, stroke=1, fill=0)
            cvs.setFont("Helvetica", 6.3)
            cvs.drawCentredString(cx + cw / 2, y - alto_fila + 4, getter(area))
        y -= alto_fila

    if not areas:
        cvs.setFont("Helvetica", 9)
        cvs.drawString(x0, y - 12, "Este estudiante no tiene áreas curriculares asignadas todavía.")
        y -= 20

    #--- Observaciones por período ---
    y -= 16
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x0, y, "OBSERVACIONES")
    y -= 12
    for periodo in periodos:
        texto= observaciones.get(periodo["id"], "")
        cvs.rect(x0, y - 12, 40, 12, stroke=1, fill=0)
        cvs.setFont("Helvetica-Bold", 6.5)
        cvs.drawCentredString(x0 + 20, y - 9, periodo["nombre"])
        cvs.rect(x0 + 40, y - 12, ancho - 2 * margen - 40, 12, stroke=1, fill=0)
        cvs.setFont("Helvetica", 6.5)
        _dibujar_texto_ajustado(cvs, texto or "—", x0 + 44, y - 9, ancho - 2 * margen - 48,
                                centrado=False, tamano_inicial=6.5, negrita=False)
        y -= 12
    y -= 14

    #--- Escala descriptiva + Situación + Condición final ---
    y_top_cajas= y
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x0, y, "ESCALA DESCRIPTIVA")
    y -= 12
    for minimo, maximo, nivel, _desc in ESCALA_DESCRIPTIVA_PRIMARIA:
        rango= f"{minimo}-{maximo}" if maximo < 100 or minimo > 0 else f"{minimo}-{maximo}"
        cvs.setFont("Helvetica-Bold", 6.3)
        cvs.drawString(x0, y, f"{rango}:")
        cvs.setFont("Helvetica", 6.3)
        cvs.drawString(x0 + 48, y, nivel)
        y -= 9

    x_sit= x0 + 210
    y_s= y_top_cajas
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x_sit, y_s, "SITUACIÓN DEL/DE LA ESTUDIANTE")
    y_s -= 14
    sg= boletin["situacion_general"]
    cvs.setFont("Helvetica", 7.5)
    cvs.drawString(x_sit, y_s, ("[X]" if sg.get("promovido") else "[ ]") + " Promovido/a")
    y_s -= 12
    cvs.drawString(x_sit, y_s, ("[X]" if sg.get("aplazado") else "[ ]") + " Aplazado/a")
    y_s -= 12
    cvs.drawString(x_sit, y_s, ("[X]" if sg.get("repitiente") else "[ ]") + " Repitiente")
    y_s -= 16
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x_sit, y_s, "CONDICIÓN FINAL DEL/DE LA ESTUDIANTE:")
    y_s -= 12
    cvs.setFont("Helvetica", 7.5)
    cvs.drawString(x_sit, y_s, sg.get("decision", "Pendiente"))

    y_firmas= min(y, y_s) - 30
    _firmas(cvs, ancho, margen, y_firmas, institucion, "Maestro(a) Encargado(a) del Grado",
            "Director(a) del Centro Educativo")
    cvs.setFont("Helvetica", 6.5)
    cvs.drawString(margen, 12, f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d')}")
    return ancho, alto


def exportar_informe_primaria_pdf(estudiante_id, ruta_pdf, institucion, boletin=None):
    from reportlab.pdfgen import canvas as _canvas_mod
    from src.boletines.boletin_minerd import construir_boletin_general

    if boletin is None:
        boletin= construir_boletin_general(estudiante_id)
        if boletin is None:
            return None

    ancho, alto = _dimensiones_pagina_primaria(boletin)
    cvs= _canvas_mod.Canvas(ruta_pdf, pagesize=(ancho, alto))
    dibujar_informe_primaria_oficial(cvs, institucion, boletin)
    cvs.save()
    return boletin
