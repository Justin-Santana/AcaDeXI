#Boletín Técnico — Formato Oficial República Dominicana (MINERD, Politécnico).
#
#FASE 2 de 3. Reutiliza el motor de Resultados de Aprendizaje (RA) que ya
#vive en bd.py (`resultados_aprendizaje` + `calificacion_ra`) y la MISMA
#fórmula de Calificación Final que ya calcula
#`calificaciones_tecnicas.py::_construir_tarjeta_modulo_boletin`:
#
#C.F. = sum(nota_RA * peso_RA) / suma_pesos      (solo si TODOS los RA
#del módulo tienen nota)
#
#La grilla oficial (ver boletín técnico real) no muestra el peso ni la nota
#de cada RA por separado: muestra la CONTRIBUCIÓN de cada RA a la nota final
#(nota_RA * peso_RA / 100). Se comprobó contra la plantilla real: sumando las
#columnas RA1%...RA9% de una fila se obtiene exactamente su C.F. -por eso la
#celda de este módulo es esa contribución, no el peso ni la nota crudos.
#
#Este módulo espera materias con `modelo_evaluacion = MODELO_EVALUACION_TECNICA`
#(constante que ya vive en materias.py) — mismas materias que ya administra
#calificaciones_tecnicas.py, no crea materias ni RA nuevos.
from datetime import datetime

from src.nucleo.bd import obtener_conexion

try:

    from src.modulos.materias import MODELO_EVALUACION_TECNICA
except Exception:
    #Mismo valor por defecto que usa la columna `materias.modelo_evaluacion` en bd.py si el módulo materias.py no
    #está disponible en este contexto.
    MODELO_EVALUACION_TECNICA= "Técnica (RA)"

DECISIONES_PROMOCION_SITUACION= {
    "Promovido": "Promovido/a",
    "Repite el Grado": "Repitiente",
}


#Mismo criterio (y mismo fallback) que ya usa
#calificaciones_tecnicas.py::_generar_boletin: primero por horario de la
#sección; si no hay nada ahí (sección aún sin horario técnico cargado),
#cae a cualquier módulo técnico donde el estudiante ya tenga notas
#registradas ese año, para no dejar el boletín vacío.
def modulos_tecnicos_de_estudiante(estudiante_id, seccion_id, anio_academico):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT DISTINCT materias.id, materias.nombre, materias.codigo
                 FROM horarios JOIN materias ON horarios.materia_id = materias.id
                 WHERE horarios.seccion_id=? AND materias.modelo_evaluacion=?
                 ORDER BY materias.nombre""", (seccion_id, MODELO_EVALUACION_TECNICA))
    modulos= [dict(f) for f in c.fetchall()]
    if not modulos:
        c.execute("""SELECT DISTINCT materias.id, materias.nombre, materias.codigo FROM calificacion_ra
                     JOIN resultados_aprendizaje ra ON calificacion_ra.resultado_aprendizaje_id = ra.id
                     JOIN materias ON ra.materia_id = materias.id
                     WHERE calificacion_ra.estudiante_id=? AND calificacion_ra.anio_academico=?
                     AND materias.modelo_evaluacion=?
                     ORDER BY materias.nombre""", (estudiante_id, anio_academico, MODELO_EVALUACION_TECNICA))
        modulos= [dict(f) for f in c.fetchall()]
    conn.close()
    return modulos


#Devuelve {"contribuciones": [c_ra1, c_ra2, ...], "cf": valor_o_None,
#"n_ra": int}. `contribuciones[i]` es None si ese RA todavía no tiene
#nota (celda en blanco en el PDF, igual que la plantilla real cuando un
#módulo usa menos RA que el máximo de la tabla).
def grilla_modulo_tecnico(estudiante_id, materia_id, anio_academico):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT * FROM resultados_aprendizaje WHERE materia_id=? AND estado='Activo'
                 ORDER BY orden, codigo""", (materia_id,))
    ra_lista= [dict(f) for f in c.fetchall()]
    contribuciones= []
    notas_validas, pesos_validos= [], []
    for ra in ra_lista:
        c.execute("""SELECT nota FROM calificacion_ra WHERE estudiante_id=? AND resultado_aprendizaje_id=?
                     AND anio_academico=?""", (estudiante_id, ra["id"], anio_academico))
        f= c.fetchone()
        nota= f["nota"] if f and f["nota"] is not None else None
        peso= ra["peso"] or 0
        if nota is not None:
            contribuciones.append(nota * peso / 100)
            notas_validas.append(nota)
            pesos_validos.append(peso)
        else:
            contribuciones.append(None)
    conn.close()
    suma_pesos= sum(pesos_validos)
    cf= None
    if ra_lista and len(notas_validas) == len(ra_lista) and suma_pesos > 0:
        cf= sum(n * p for n, p in zip(notas_validas, pesos_validos)) / suma_pesos
    return {"contribuciones": contribuciones, "cf": cf, "n_ra": len(ra_lista),
            "codigos_ra": [ra["codigo"] for ra in ra_lista]}


def situacion_estudiante_politecnico(estudiante_id, anio_academico):

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT decision, accion_no_promocion, motivo_conducta FROM decision_promocion
                 WHERE estudiante_id=? AND anio_academico=?""", (estudiante_id, anio_academico))
    f= c.fetchone()
    conn.close()
    if not f:
        return {"decision": "Pendiente", "situacion": "", "condicion_final": ""}
    situacion= DECISIONES_PROMOCION_SITUACION.get(f["decision"], "")
    condicion= f["decision"] or "Pendiente"
    if f["accion_no_promocion"]:
        condicion += f" — {f['accion_no_promocion']}"
    return {"decision": f["decision"] or "Pendiente", "situacion": situacion, "condicion_final": condicion}


#Ensambla los datos del boletín técnico: módulos técnicos del
#estudiante, su grilla RA (contribuciones + C.F.), y su situación final
#de Politécnico. Reutiliza `datos_estudiante_boletin` de
#boletin_minerd.py para no duplicar la resolución de sección/grado/año.
def construir_boletin_tecnico(estudiante_id, anio_academico=None):

    from src.boletines.boletin_minerd import datos_estudiante_boletin
    datos= datos_estudiante_boletin(estudiante_id)
    if not datos:
        return None
    anio= anio_academico or datos["anio_academico"]
    modulos= modulos_tecnicos_de_estudiante(estudiante_id, datos["seccion_id"], anio)
    max_ra= 0
    filas= []
    for modulo in modulos:
        grilla= grilla_modulo_tecnico(estudiante_id, modulo["id"], anio)
        max_ra= max(max_ra, grilla["n_ra"])
        filas.append({"materia_id": modulo["id"], "materia_nombre": modulo["nombre"],
                       "codigo": modulo.get("codigo") or "", "grilla": grilla})
    situacion= situacion_estudiante_politecnico(estudiante_id, anio)
    return {"estudiante": datos, "anio_academico": anio, "modulos": filas,
            "max_ra": max_ra, "situacion": situacion}


#PDF — grilla oficial técnica (apaisado): filas = módulos, columnas = RA1%...RAn% (contribución) + C.F., más el
#bloque de Situación/Condición Final del/de la estudiante.
def _fmt(valor, decimales=0):

    return f"{valor:.{decimales}f}" if valor is not None else ""


def dibujar_boletin_tecnico_oficial(cvs, ancho, alto, institucion, boletin, colores=None):

    from reportlab.lib.utils import ImageReader
    from src.boletines.boletin_minerd import _hex_a_rgb01, _dibujar_texto_ajustado

    colores= colores or {"banda": "#1F9E9E", "texto_banda": "#FFFFFF"}
    rgb_banda= _hex_a_rgb01(colores["banda"])
    rgb_texto_banda= _hex_a_rgb01(colores["texto_banda"])

    est= boletin["estudiante"]
    modulos= boletin["modulos"]
    max_ra= max(boletin["max_ra"], 1)

    margen= 30
    y= alto - 34
    if institucion.get("logo"):
        try:

            img= ImageReader(institucion["logo"])
            iw, ih= img.getSize()
            alto_img= 40
            cvs.drawImage(img, margen, y - 30, width=alto_img * (iw / ih), height=alto_img,
                          preserveAspectRatio= True, mask='auto')
        except Exception:
            pass
    cvs.setFont("Helvetica-Bold", 13)
    cvs.drawCentredString(ancho / 2, y, "BOLETÍN DE CALIFICACIONES Y MÓDULOS TÉCNICOS")
    y -= 15
    cvs.setFont("Helvetica", 9)
    cvs.drawCentredString(ancho / 2, y, institucion.get("nombre", "AcaDeXI"))
    y -= 18

    cvs.setFillColorRGB(*rgb_banda)
    cvs.rect(margen, y - 4, ancho - 2 * margen, 16, fill=1, stroke=0)
    cvs.setFillColorRGB(*rgb_texto_banda)
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawCentredString(ancho / 2, y, f"{est['grado_nombre']} — CALIFICACIONES DE RENDIMIENTO TÉCNICO")
    cvs.setFillColorRGB(0, 0, 0)
    y -= 22

    cvs.setFont("Helvetica", 8.5)
    cvs.drawString(margen, y, f"Año Escolar: {est['anio_academico']}    Grado: {est['grado_nombre']}   "
                              f"Sección: {est['seccion_nombre']}")
    y -= 12
    cvs.drawString(margen, y, f"Número de orden: {est['numero_orden'] or '—'}    "
                              f"Nombre(s): {est['nombre']} {est['apellidos']}")
    y -= 16

    col_izq_ancho= 170  #nombre del módulo técnico
    col_cf_ancho= 40
    ancho_ra= ancho - 2 * margen - col_izq_ancho - col_cf_ancho
    col_ra_ancho= ancho_ra / max_ra
    alto_fila= 16
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
                                centrado= False, tamano_inicial=7)
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
        y -= 24

    #--- Situación del/de la Estudiante ---
    y -= 20
    situacion= boletin["situacion"]
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawString(x0, y, "Situación del/de la Estudiante:")
    cvs.setFont("Helvetica", 9)
    marca_prom= "☒" if situacion["situacion"] == "Promovido/a" else "☐"
    marca_rep= "☒" if situacion["situacion"] == "Repitiente" else "☐"
    cvs.drawString(x0 + 175, y, f"{marca_prom} Promovido/a")
    cvs.drawString(x0 + 280, y, f"{marca_rep} Repitiente")
    y -= 16
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawString(x0, y, "Condición Final del/de la Estudiante:")
    cvs.setFont("Helvetica", 9)
    cvs.drawString(x0 + 190, y, situacion["condicion_final"] or "Pendiente")
    y -= 24

    if institucion.get("firma"):
        try:

            img= ImageReader(institucion["firma"])
            iw, ih= img.getSize()
            alto_img= 30
            x_firma= ancho - margen - 150
            cvs.drawImage(img, x_firma, y, width=alto_img * (iw / ih), height=alto_img,
                          preserveAspectRatio= True, mask='auto')
            cvs.line(x_firma, y - 3, x_firma + 150, y - 3)
            cvs.setFont("Helvetica", 7)
            cvs.drawCentredString(x_firma + 75, y - 13, "Directora/Director del Centro Educativo")
        except Exception:
            pass
    cvs.setFont("Helvetica", 7)
    cvs.drawString(margen, 20, f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d')}")


def _dimensiones_pagina_tecnico(boletin):

    from reportlab.lib.pagesizes import letter, landscape
    return landscape(letter)


def exportar_boletin_tecnico_oficial_pdf(estudiante_id, ruta_pdf, institucion, anio_academico=None):

    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.pdfgen import canvas
    from src.boletines.boletin_minerd import colores_boletin

    boletin= construir_boletin_tecnico(estudiante_id, anio_academico=anio_academico)
    if boletin is None:
        return None
    colores= colores_boletin(None)  #Politécnico/Técnico siempre es Secundaria -> paleta "secundaria"
    ancho, alto= _dimensiones_pagina_tecnico(boletin)
    cvs= canvas.Canvas(ruta_pdf, pagesize=(ancho, alto))
    dibujar_boletin_tecnico_oficial(cvs, ancho, alto, institucion, boletin, colores)
    cvs.save()
    return boletin
