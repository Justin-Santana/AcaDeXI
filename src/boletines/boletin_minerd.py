"""Boletín General — Formato Oficial República Dominicana (MINERD).

FASE 1 de 3 (general -> técnico -> boletín completo).

v2: reescrito contra la plantilla oficial en blanco del MINERD (Segundo
Ciclo Nivel Secundario / Informe de Aprendizaje Nivel Primario) en vez del
boletín ya diligenciado de una institución particular. Cambios de fondo
respecto a v1:

  - La grilla va TRANSPUESTA: filas = Áreas Curriculares, columnas =
    grupos de Competencias Fundamentales × Período (la plantilla real la
    dibuja así, no al revés).
  - Las 7 Competencias Fundamentales oficiales (ver
    configuracion.COMPETENCIAS_FUNDAMENTALES_RD) se AGRUPAN para mostrarse
    en columnas: 4 grupos en Secundaria, 3 grupos en Primaria -distinto
    agrupamiento por nivel, tal como en la plantilla real-. Ver
    GRUPOS_DISPLAY_SECUNDARIA / GRUPOS_DISPLAY_PRIMARIA.
  - Secundaria: se añade el desglose completo de la cascada de evaluación
    (50% C.F./50% C.E.C. -> C.C.F.; 30% C.F./70% C.E.EX -> C.EX.F.;
    Evaluación Especial; Situación Final A/R), Resumen de Asistencia y
    Leyenda, igual que la plantilla.
  - Primaria tiene su PROPIO documento ("Informe de Aprendizaje"): grupos
    de competencias distintos, columnas "Calificación final por
    competencia" (C1-C3) en vez de PC1-PC4, columnas de Recuperación
    Pedagógica (RP) por período cuando existan datos, escala descriptiva
    cualitativa (Destacado/Logrado/En Proceso/Insuficiente) en vez de A/R,
    y situación en 3 estados (Promovido/a, Aplazado/a, Repitiente).
  - Los colores del boletín ahora son DOS pares configurables (Primaria y
    Secundaria son documentos distintos con paletas distintas en la
    plantilla real), no uno solo para toda la institución.

Se sigue sin duplicar esquema para los datos (motor de Competencias
Específicas ya existente en bd.py); lo nuevo en `configuracion` son solo
columnas de preferencia (formato + 4 colores), y en `periodos` dos columnas
opcionales de fecha para poder repartir la asistencia por período -sin
ellas, esa caja del boletín queda en blanco, como en un boletín impreso sin
diligenciar.
"""
from datetime import datetime

from src.nucleo.bd import obtener_conexion, _agregar_columna_si_falta
from src.interfaz.configuracion import (COMPETENCIAS_FUNDAMENTALES_RD, es_sistema_dominicano,
                            resolver_nota_minima)

GRUPOS_DISPLAY_SECUNDARIA= [
    ("Comunicativa", ["Comunicativa"]),
    ("Pensamiento Lógico, Creativo y Crítico / Resolución de Problemas",
     ["Pensamiento Lógico, Creativo y Crítico", "Resolución de Problemas"]),
    ("Científica y Tecnológica / Ambiental y de la Salud",
     ["Científica y Tecnológica", "Ambiental y de la Salud"]),
    ("Ética y Ciudadana / Desarrollo Personal y Espiritual",
     ["Ética y Ciudadana", "Desarrollo Personal y Espiritual"]),
]

GRUPOS_DISPLAY_PRIMARIA= [
    ("Comunicativa", ["Comunicativa"]),
    ("Pensamiento Lógico, Creativo y Crítico; Resolución de Problemas; Científica y Tecnológica",
     ["Pensamiento Lógico, Creativo y Crítico", "Resolución de Problemas", "Científica y Tecnológica"]),
    ("Ética y Ciudadana; Desarrollo Personal y Espiritual; Ambiental y de la Salud",
     ["Ética y Ciudadana", "Desarrollo Personal y Espiritual", "Ambiental y de la Salud"]),
]

ESCALA_DESCRIPTIVA_PRIMARIA= [
    (89, 100, "Destacado", "Desempeño destacado con relación a los aspectos evaluados de las competencias de cada área."),
    (77, 88, "Logrado", "Ha logrado, en general, los aprendizajes esperados de las competencias de cada área."),
    (65, 76, "En Proceso", "Aún se encuentra en proceso, mostrando un logro muy básico."),
    (0, 64, "Insuficiente", "Desempeño insuficiente con relación a los aspectos evaluados."),
]

#Orden curricular oficial (no alfabético) de las Áreas Curriculares, tal como aparecen en la plantilla real. Un
#área del boletín que NO esté en esta lista (una institución puede haber registrado una materia propia, p. ej.
#una electiva) se agrega al final, en orden alfabético -no desaparece, solo no tiene un lugar "oficial" fijo.
ORDEN_AREAS_SECUNDARIA= [
    "Lengua Española", "Lenguas Extranjeras (Inglés)", "Lenguas Extranjeras (Francés)",
    "Matemática", "Ciencias Sociales", "Ciencias de la Naturaleza",
    "Educación Artística", "Educación Física", "Formación Integral Humana y Religiosa",
]
ORDEN_AREAS_PRIMARIA= [
    "Lengua Española", "Matemática", "Ciencias Sociales", "Ciencias de la Naturaleza",
    "Educación Física", "Formación Integral, Humana y Religiosa", "Educación Artística",
]


def _ordenar_areas_curricular(materias, primaria):
    orden= ORDEN_AREAS_PRIMARIA if primaria else ORDEN_AREAS_SECUNDARIA
    indice= {nombre: i for i, nombre in enumerate(orden)}

    def clave(materia):
        return (indice.get(materia["nombre"], len(orden)), materia["nombre"])
    return sorted(materias, key=clave)


def es_nivel_primaria(nivel_educativo):
    return (nivel_educativo or "").strip().lower().startswith("primaria")


def migrar_configuracion_boletin(conn):
    _agregar_columna_si_falta(conn, "configuracion", "formato_boletin_general", "TEXT DEFAULT 'simple'")
    _agregar_columna_si_falta(conn, "configuracion", "boletin_color_banda_secundaria", "TEXT DEFAULT '#1F9E9E'")
    _agregar_columna_si_falta(conn, "configuracion", "boletin_color_texto_banda_secundaria", "TEXT DEFAULT '#FFFFFF'")
    _agregar_columna_si_falta(conn, "configuracion", "boletin_color_banda_primaria", "TEXT DEFAULT '#E8863C'")
    _agregar_columna_si_falta(conn, "configuracion", "boletin_color_texto_banda_primaria", "TEXT DEFAULT '#FFFFFF'")
    _agregar_columna_si_falta(conn, "periodos", "fecha_inicio", "TEXT")
    _agregar_columna_si_falta(conn, "periodos", "fecha_fin", "TEXT")
    conn.commit()


def formato_boletin_general():
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT formato_boletin_general FROM configuracion WHERE id=1")
    f= c.fetchone()
    conn.close()
    return (f["formato_boletin_general"] if f and f["formato_boletin_general"] else "simple")


def guardar_formato_boletin_general(formato):
    if formato not in ("simple", "oficial_rd"):
        raise ValueError("formato debe ser 'simple' u 'oficial_rd'")
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("UPDATE configuracion SET formato_boletin_general=? WHERE id=1", (formato,))
    conn.commit()
    conn.close()


def colores_boletin(nivel_educativo=None):
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT boletin_color_banda_secundaria, boletin_color_texto_banda_secundaria,
                        boletin_color_banda_primaria, boletin_color_texto_banda_primaria
                 FROM configuracion WHERE id=1""")
    f= c.fetchone()
    conn.close()
    if es_nivel_primaria(nivel_educativo):
        return {"banda": (f["boletin_color_banda_primaria"] if f else None) or "#E8863C",
                "texto_banda": (f["boletin_color_texto_banda_primaria"] if f else None) or "#FFFFFF"}
    return {"banda": (f["boletin_color_banda_secundaria"] if f else None) or "#1F9E9E",
            "texto_banda": (f["boletin_color_texto_banda_secundaria"] if f else None) or "#FFFFFF"}


def guardar_colores_boletin(nivel_educativo, color_banda, color_texto_banda):
    campo_banda= "boletin_color_banda_primaria" if es_nivel_primaria(nivel_educativo) else "boletin_color_banda_secundaria"
    campo_texto= ("boletin_color_texto_banda_primaria" if es_nivel_primaria(nivel_educativo)
                   else "boletin_color_texto_banda_secundaria")
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute(f"UPDATE configuracion SET {campo_banda}=?, {campo_texto}=? WHERE id=1",
              (color_banda, color_texto_banda))
    conn.commit()
    conn.close()


def datos_estudiante_boletin(estudiante_id):
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT estudiantes.id, estudiantes.nombre, estudiantes.apellidos,
                        estudiantes.seccion_id, secciones.nombre as seccion_nombre,
                        secciones.anio_academico, secciones.profesor_guia_id,
                        grados.id as grado_id, grados.nombre as grado_nombre,
                        grados.nivel_educativo, profesores.nombre as docente_nombre,
                        profesores.apellidos as docente_apellidos
                 FROM estudiantes
                 LEFT JOIN secciones ON estudiantes.seccion_id = secciones.id
                 LEFT JOIN grados ON secciones.grado_id = grados.id
                 LEFT JOIN profesores ON secciones.profesor_guia_id = profesores.id
                 WHERE estudiantes.id=?""", (estudiante_id,))
    f= c.fetchone()
    if not f:
        conn.close()
        return None
    c.execute("""SELECT id FROM estudiantes WHERE seccion_id=? AND estado='Activo'
                 ORDER BY apellidos, nombre""", (f["seccion_id"],))
    orden= [r["id"] for r in c.fetchall()]
    numero_orden= (orden.index(estudiante_id) + 1) if estudiante_id in orden else None
    conn.close()
    docente= ""
    if f["docente_nombre"]:
        docente= f"{f['docente_nombre']} {f['docente_apellidos'] or ''}".strip()
    return {
        "id": f["id"], "nombre": f["nombre"], "apellidos": f["apellidos"] or "",
        "seccion_id": f["seccion_id"], "seccion_nombre": f["seccion_nombre"] or "",
        "anio_academico": f["anio_academico"] or "", "grado_id": f["grado_id"],
        "grado_nombre": f["grado_nombre"] or "", "nivel_educativo": f["nivel_educativo"],
        "docente": docente, "numero_orden": numero_orden,
    }


def materias_de_estudiante(estudiante_id, seccion_id=None):
    conn= obtener_conexion()
    c= conn.cursor()
    if seccion_id is None:
        c.execute("SELECT seccion_id FROM estudiantes WHERE id=?", (estudiante_id,))
        f= c.fetchone()
        seccion_id= f["seccion_id"] if f else None
    if seccion_id is None:
        conn.close()
        return []
    c.execute("""SELECT DISTINCT materias.id, materias.nombre FROM horarios
                 LEFT JOIN materias ON horarios.materia_id = materias.id
                 WHERE horarios.seccion_id=? AND materias.id IS NOT NULL
                 AND materias.estado='Activa'
                 AND (materias.modelo_evaluacion IS NULL OR materias.modelo_evaluacion != 'Técnica (RA)')
                 ORDER BY materias.nombre""", (seccion_id,))
    filas= [dict(f) for f in c.fetchall()]
    conn.close()
    return filas


def periodos_del_anio(anio_academico):
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT id, nombre, fecha_inicio, fecha_fin FROM periodos WHERE anio_academico=? ORDER BY orden",
              (anio_academico,))
    filas= [dict(f) for f in c.fetchall()]
    conn.close()
    return filas


def _promedio(valores):
    limpios= [v for v in valores if v is not None]
    return (sum(limpios) / len(limpios)) if limpios else None


def grilla_area(estudiante_id, materia_id, grado_id, periodos, grupos_display):
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("""SELECT id, competencia_fundamental FROM competencias_especificas
                 WHERE materia_id=? AND grado_id=? AND estado='Activa'""", (materia_id, grado_id))
    ces= c.fetchall()
    if not ces:
        conn.close()
        return {"grupos": {}, "finales_por_grupo": [None] * len(grupos_display),
                "pc": [None] * len(periodos), "final": None, "con_curriculo": False}

    ces_por_fundamental= {}
    for ce in ces:
        clave= ce["competencia_fundamental"] or "Sin clasificar"
        ces_por_fundamental.setdefault(clave, []).append(ce["id"])

    grupos= {}
    for etiqueta, fundamentales_incluidos in grupos_display:
        ids_ce= []
        for nf in fundamentales_incluidos:
            ids_ce.extend(ces_por_fundamental.get(nf, []))
        valores_por_periodo= []
        for periodo in periodos:
            if not ids_ce:
                valores_por_periodo.append(None)
                continue
            marcadores= ",".join("?" * len(ids_ce))
            c.execute(f"""SELECT nota FROM competencia_periodo
                         WHERE estudiante_id=? AND periodo_id=? AND competencia_id IN ({marcadores})""",
                      [estudiante_id, periodo["id"]] + ids_ce)
            notas= [r["nota"] for r in c.fetchall() if r["nota"] is not None]
            valores_por_periodo.append(_promedio(notas))
        grupos[etiqueta]= valores_por_periodo
    conn.close()

    etiquetas= [g[0] for g in grupos_display]
    pc= []
    for i in range(len(periodos)):
        pc.append(_promedio([grupos[et][i] for et in etiquetas]))
    finales_por_grupo= [_promedio(grupos[et]) for et in etiquetas]
    final= _promedio(pc)
    return {"grupos": grupos, "finales_por_grupo": finales_por_grupo, "pc": pc, "final": final, "con_curriculo": True}


def _nota_simple_area(estudiante_id, materia_id, periodos, metodo):
    from src.modulos.calificaciones import calcular_nota_final
    conn= obtener_conexion()
    c= conn.cursor()
    valores_por_periodo= []
    todas= []
    for periodo in periodos:
        c.execute("SELECT valor, peso FROM calificaciones WHERE estudiante_id=? AND materia_id=? AND periodo_id=?",
                  (estudiante_id, materia_id, periodo["id"]))
        filas= [dict(f) for f in c.fetchall()]
        nota= calcular_nota_final(filas, metodo) if filas else None
        valores_por_periodo.append(nota)
        todas.extend(filas)
    conn.close()
    final= calcular_nota_final(todas, metodo) if todas else None
    return valores_por_periodo, final


def _recuperacion_pedagogica_area(estudiante_id, materia_id, periodos):
    conn= obtener_conexion()
    c= conn.cursor()
    valores= []
    for periodo in periodos:
        c.execute("""SELECT nota_rp FROM recuperacion_pedagogica
                     WHERE estudiante_id=? AND materia_id=? AND periodo_id=?""",
                  (estudiante_id, materia_id, periodo["id"]))
        f= c.fetchone()
        valores.append(f["nota_rp"] if f and f["nota_rp"] is not None else None)
    conn.close()
    return valores


def _cascada_evaluacion(estudiante_id, materia_id, anio_academico):
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT nota_completiva FROM evaluacion_completiva WHERE estudiante_id=? AND materia_id=? AND anio_academico=?",
              (estudiante_id, materia_id, anio_academico))
    completiva= c.fetchone()
    c.execute("SELECT nota_extraordinaria FROM evaluacion_extraordinaria WHERE estudiante_id=? AND materia_id=? AND anio_academico=?",
              (estudiante_id, materia_id, anio_academico))
    extraordinaria= c.fetchone()
    c.execute("SELECT nota_especial FROM evaluacion_especial WHERE estudiante_id=? AND materia_id=? AND anio_academico=?",
              (estudiante_id, materia_id, anio_academico))
    especial= c.fetchone()
    conn.close()
    return {
        "completiva": completiva["nota_completiva"] if completiva else None,
        "extraordinaria": extraordinaria["nota_extraordinaria"] if extraordinaria else None,
        "especial": especial["nota_especial"] if especial else None,
    }


def _desglose_cascada_secundaria(cf, cascada):
    d= {"cf_50": None, "cec": cascada.get("completiva"), "cec_50": None, "ccf": None,
         "cf_30": None, "ce_ex": cascada.get("extraordinaria"), "ce_ex_70": None, "cexf": None,
         "especial_cf": cf, "especial_ce": cascada.get("especial")}
    if cf is not None:
        d["cf_50"]= cf * 0.5
        d["cf_30"]= cf * 0.3
    if cascada.get("completiva") is not None:
        d["cec_50"]= cascada["completiva"] * 0.5
    if cascada.get("extraordinaria") is not None:
        d["ce_ex_70"]= cascada["extraordinaria"] * 0.7
    if d["cf_50"] is not None and d["cec_50"] is not None:
        d["ccf"]= d["cf_50"] + d["cec_50"]
    if d["cf_30"] is not None and d["ce_ex_70"] is not None:
        d["cexf"]= d["cf_30"] + d["ce_ex_70"]
    return d


def _situacion_general_estudiante(estudiante_id, anio_academico):
    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT decision FROM decision_promocion WHERE estudiante_id=? AND anio_academico=?",
              (estudiante_id, anio_academico))
    f= c.fetchone()
    conn.close()
    decision= (f["decision"] if f else None) or "Pendiente"
    return {"decision": decision,
            "promovido": decision == "Promovido",
            "aplazado": decision == "Evaluación Especial Autorizada",
            "repitiente": decision == "Repite el Grado"}


def resumen_asistencia(estudiante_id, seccion_id, periodos):
    conn= obtener_conexion()
    c= conn.cursor()
    resultado= {}
    for periodo in periodos:
        if not periodo.get("fecha_inicio") or not periodo.get("fecha_fin"):
            resultado[periodo["id"]]= {"asistencia": None, "ausencia": None}
            continue
        c.execute("""SELECT estado, COUNT(*) as n FROM asistencia
                     WHERE estudiante_id=? AND seccion_id=? AND fecha BETWEEN ? AND ?
                     GROUP BY estado""",
                  (estudiante_id, seccion_id, periodo["fecha_inicio"], periodo["fecha_fin"]))
        conteos= {r["estado"]: r["n"] for r in c.fetchall()}
        resultado[periodo["id"]]= {
            "asistencia": conteos.get("Presente", 0),
            "ausencia": sum(v for k, v in conteos.items() if k != "Presente"),
        }
    conn.close()
    return resultado


def construir_boletin_general(estudiante_id, metodo="Promedio Ponderado", anio_academico=None):
    datos= datos_estudiante_boletin(estudiante_id)
    if not datos:
        return None
    anio= anio_academico or datos["anio_academico"]
    periodos= periodos_del_anio(anio)
    primaria= es_nivel_primaria(datos["nivel_educativo"])
    grupos_display= GRUPOS_DISPLAY_PRIMARIA if primaria else GRUPOS_DISPLAY_SECUNDARIA
    materias= _ordenar_areas_curricular(materias_de_estudiante(estudiante_id, datos["seccion_id"]), primaria)

    conn= obtener_conexion()
    c= conn.cursor()
    c.execute("SELECT nota_minima, nota_minima_primaria, nota_minima_secundaria, sistema_calificacion "
              "FROM configuracion WHERE id=1")
    cfg= c.fetchone()
    conn.close()
    nota_minima= resolver_nota_minima(cfg, nivel_educativo=datos["nivel_educativo"]) if cfg else 70
    dominicano= es_sistema_dominicano(cfg["sistema_calificacion"]) if cfg else False

    areas= []
    for materia in materias:
        grilla= grilla_area(estudiante_id, materia["id"], datos["grado_id"], periodos, grupos_display)
        if not grilla["con_curriculo"]:
            valores_simples, final = _nota_simple_area(estudiante_id, materia["id"], periodos, metodo)
            grilla= {"grupos": {}, "finales_por_grupo": [None] * len(grupos_display),
                      "pc": valores_simples, "final": final, "con_curriculo": False}
        area= {"materia_id": materia["id"], "materia_nombre": materia["nombre"], "grilla": grilla}

        if primaria:
            area["rp"]= _recuperacion_pedagogica_area(estudiante_id, materia["id"], periodos)
            area["tiene_rp"]= any(v is not None for v in area["rp"])
        else:
            cascada= _cascada_evaluacion(estudiante_id, materia["id"], anio) if dominicano else {}
            area["cascada"]= cascada
            area["desglose"]= _desglose_cascada_secundaria(grilla["final"], cascada) if dominicano else {}
            nota_para_situacion= grilla["final"]
            if area["desglose"].get("ccf") is not None:
                nota_para_situacion= area["desglose"]["ccf"]
            if area["desglose"].get("cexf") is not None:
                nota_para_situacion= area["desglose"]["cexf"]
            if cascada.get("especial") is not None:
                nota_para_situacion= cascada["especial"]
            area["situacion"]= ("" if nota_para_situacion is None
                                  else ("A" if nota_para_situacion >= nota_minima else "R"))
        areas.append(area)

    asistencia= resumen_asistencia(estudiante_id, datos["seccion_id"], periodos) if dominicano else {}
    situacion_general= _situacion_general_estudiante(estudiante_id, anio) if dominicano else {}

    return {
        "estudiante": datos, "periodos": periodos, "areas": areas,
        "nota_minima": nota_minima, "dominicano": dominicano, "primaria": primaria,
        "grupos_display": grupos_display, "asistencia": asistencia,
        "situacion_general": situacion_general, "anio_academico": anio,
    }


#PDF — utilidades compartidas
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
    datos."""
    fuente= "Helvetica-Bold" if negrita else "Helvetica"
    tam= tamano_inicial
    palabras= texto.replace(" / ", " /").split(" ")
    while tam >= 4:
        interlineado= tam + 1.5
        lineas, actual = [], ""
        for palabra in palabras:
            candidato= (actual + " " + palabra).strip()
            if cvs.stringWidth(candidato, fuente, tam) <= ancho_max or not actual:
                actual= candidato
            else:
                lineas.append(actual)
                actual= palabra
        if actual:
            lineas.append(actual)
        if len(lineas) * interlineado <= alto_max and all(
                cvs.stringWidth(l, fuente, tam) <= ancho_max + 2 for l in lineas):
            break
        tam -= 0.5
    else:
        tam= 4
        interlineado= tam + 1.5
    cvs.setFont(fuente, tam)
    y_inicio= y_centro + (len(lineas) - 1) * interlineado / 2
    for i, linea in enumerate(lineas):
        cvs.drawCentredString(cx, y_inicio - i * interlineado, linea.strip())


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
    cvs.setFont("Helvetica-Bold", 13)
    cvs.drawCentredString(ancho / 2, y, titulo)
    y -= 15
    cvs.setFont("Helvetica", 9)
    cvs.drawCentredString(ancho / 2, y, institucion.get("nombre", "AcaDeXI"))
    y -= 18
    cvs.setFillColorRGB(*rgb_banda)
    cvs.rect(margen, y - 4, ancho - 2 * margen, 16, fill=1, stroke=0)
    cvs.setFillColorRGB(*rgb_texto_banda)
    cvs.setFont("Helvetica-Bold", 9)
    cvs.drawCentredString(ancho / 2, y, subtitulo)
    cvs.setFillColorRGB(0, 0, 0)
    return y - 22


def _firmas(cvs, ancho, margen, y_base, institucion, etiqueta_izq, etiqueta_der):
    from reportlab.lib.utils import ImageReader
    ancho_firma= 170
    x_izq= margen + 20
    x_der= ancho - margen - 20 - ancho_firma
    if institucion.get("firma"):
        try:
            img= ImageReader(institucion["firma"])
            iw, ih = img.getSize()
            alto_img= 26
            cvs.drawImage(img, x_der + ancho_firma / 2 - (alto_img * (iw / ih)) / 2, y_base + 4,
                          width=alto_img * (iw / ih), height=alto_img, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    cvs.line(x_izq, y_base, x_izq + ancho_firma, y_base)
    cvs.line(x_der, y_base, x_der + ancho_firma, y_base)
    cvs.setFont("Helvetica", 7.5)
    cvs.drawCentredString(x_izq + ancho_firma / 2, y_base - 10, etiqueta_izq)
    cvs.drawCentredString(x_der + ancho_firma / 2, y_base - 10, etiqueta_der)


#PDF — SECUNDARIA (grilla transpuesta + cascada + asistencia + leyenda)
COL_LABEL= 130
COL_PERIODO= 22
COL_CF= 34
COL_CASCADA= 26
COL_AR= 20


def _ancho_pagina_secundaria(n_grupos, n_periodos):
    margen= 24
    ancho_grupos= n_grupos * n_periodos * COL_PERIODO
    ancho_pc= n_periodos * COL_PERIODO
    ancho_datos= (ancho_grupos + ancho_pc + COL_CF + 4 * COL_CASCADA + 4 * COL_CASCADA
                   + 2 * COL_CASCADA + 2 * COL_AR)
    return 2 * margen + COL_LABEL + ancho_datos, margen


def dibujar_boletin_secundaria_oficial(cvs, institucion, boletin, colores=None):
    colores= colores or colores_boletin(boletin["estudiante"]["nivel_educativo"])
    rgb_banda= _hex_a_rgb01(colores["banda"])
    rgb_texto_banda= _hex_a_rgb01(colores["texto_banda"])

    est= boletin["estudiante"]
    periodos= boletin["periodos"]
    n_periodos= max(len(periodos), 1)
    grupos_display= boletin["grupos_display"]
    areas= boletin["areas"]

    ancho, margen = _ancho_pagina_secundaria(len(grupos_display), n_periodos)
    alto_fila= 13
    n_filas_cuerpo= max(len(areas), 1)
    alto= (170 + n_filas_cuerpo * alto_fila + 210)  #cabecera + grilla + cajas inferiores

    y= alto - 34
    y= _encabezado_institucional(
        cvs, ancho, y, institucion, "BOLETÍN DE CALIFICACIONES",
        f"{est['grado_nombre']} — {est['nivel_educativo'] or 'Secundaria'} — CALIFICACIONES DE RENDIMIENTO",
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
    #Columna "Áreas Curriculares" (ocupa las 2 filas de encabezado)
    rect_relleno(x, fila1_y, COL_LABEL, alto_doble)
    _dibujar_texto_multilinea(cvs, "Áreas Curriculares", x + COL_LABEL / 2, fila1_y - alto_doble / 2 + 3,
                              COL_LABEL - 6, alto_doble - 6, tamano_inicial=8)
    cvs.setFillColorRGB(0, 0, 0)
    x += COL_LABEL

    columnas= []  #(x, ancho, getter(area) -> str, es_final)
    for etiqueta, _incluidos in grupos_display:
        ancho_grupo= n_periodos * COL_PERIODO
        rect_relleno(x, fila1_y, ancho_grupo, alto_doble - 14)
        _dibujar_texto_multilinea(cvs, etiqueta, x + ancho_grupo / 2, fila1_y - (alto_doble - 14) / 2 + 3,
                                  ancho_grupo - 4, alto_doble - 20, tamano_inicial=6)
        cvs.setFillColorRGB(0, 0, 0)
        for i, periodo in enumerate(periodos):
            cx= x + i * COL_PERIODO
            cvs.rect(cx, fila2_y - 14, COL_PERIODO, 14, stroke=1, fill=0)
            cvs.setFont("Helvetica-Bold", 6)
            cvs.drawCentredString(cx + COL_PERIODO / 2, fila2_y - 10, periodo["nombre"])
            et_local= etiqueta
            idx_local= i
            columnas.append((cx, COL_PERIODO,
                              lambda a, et=et_local, ix=idx_local: _fmt(a["grilla"]["grupos"].get(et, [None] * n_periodos)[ix]),
                              False))
        x += ancho_grupo

    ancho_pc= n_periodos * COL_PERIODO
    rect_relleno(x, fila1_y, ancho_pc, alto_doble - 14)
    _dibujar_texto_multilinea(cvs, "PROMEDIO GRUPO DE COMPETENCIAS ESPECÍFICAS", x + ancho_pc / 2,
                              fila1_y - (alto_doble - 14) / 2 + 3, ancho_pc - 4, alto_doble - 20, tamano_inicial=5.5)
    cvs.setFillColorRGB(0, 0, 0)
    for i in range(n_periodos):
        cx= x + i * COL_PERIODO
        cvs.rect(cx, fila2_y - 14, COL_PERIODO, 14, stroke=1, fill=0)
        cvs.setFont("Helvetica-Bold", 6)
        cvs.drawCentredString(cx + COL_PERIODO / 2, fila2_y - 10, f"PC{i + 1}")
        ix= i
        columnas.append((cx, COL_PERIODO, lambda a, ix=ix: _fmt(a["grilla"]["pc"][ix] if ix < len(a["grilla"]["pc"]) else None), False))
    x += ancho_pc

    rgb_resaltado_hdr= _aclarar(rgb_banda, 0.55)
    cvs.setFillColorRGB(*rgb_resaltado_hdr)
    cvs.rect(x, fila1_y - alto_doble, COL_CF, alto_doble, fill=1, stroke=1)
    cvs.setFillColorRGB(0, 0, 0)
    _dibujar_texto_multilinea(cvs, "CALIFICACIÓN FINAL DEL ÁREA", x + COL_CF / 2, fila1_y - alto_doble / 2 + 3,
                              COL_CF - 4, alto_doble - 6, tamano_inicial=6)
    columnas.append((x, COL_CF, lambda a: _fmt(a["grilla"]["final"]), True))
    x += COL_CF

    def bloque_cascada(titulo, subcols):
        nonlocal x
        ancho_bloque= len(subcols) * COL_CASCADA
        rect_relleno(x, fila1_y, ancho_bloque, alto_doble - 14)
        _dibujar_texto_multilinea(cvs, titulo, x + ancho_bloque / 2, fila1_y - (alto_doble - 14) / 2 + 3,
                                  ancho_bloque - 4, alto_doble - 20, tamano_inicial=5.5)
        cvs.setFillColorRGB(0, 0, 0)
        for etiqueta_sub, clave in subcols:
            cvs.rect(x, fila2_y - 14, COL_CASCADA, 14, stroke=1, fill=0)
            _dibujar_texto_ajustado(cvs, etiqueta_sub, x + COL_CASCADA / 2, fila2_y - 10, COL_CASCADA - 2,
                                    tamano_inicial=5.5)
            clave_local= clave
            columnas.append((x, COL_CASCADA, lambda a, k=clave_local: _fmt(a["desglose"].get(k)), False))
            x += COL_CASCADA

    bloque_cascada("CALIFICACIÓN COMPLETIVA", [("50% C.F.", "cf_50"), ("C.E.C.", "cec"),
                                                ("50% C.E.C.", "cec_50"), ("C.C.F.", "ccf")])
    bloque_cascada("CALIFICACIÓN EXTRAORDINARIA", [("30% C.F.", "cf_30"), ("C.E. EX", "ce_ex"),
                                                    ("70% C.E. EX", "ce_ex_70"), ("C.EX.F.", "cexf")])
    bloque_cascada("EVALUACIÓN ESPECIAL", [("C.F.", "especial_cf"), ("C.E.", "especial_ce")])

    ancho_sit= 2 * COL_AR
    rect_relleno(x, fila1_y, ancho_sit, alto_doble - 14)
    _dibujar_texto_multilinea(cvs, "SITUACIÓN FINAL EN LA ASIGNATURA", x + ancho_sit / 2,
                              fila1_y - (alto_doble - 14) / 2 + 3, ancho_sit - 2, alto_doble - 20, tamano_inicial=5)
    cvs.setFillColorRGB(0, 0, 0)
    for j, letra in enumerate(("A", "R")):
        cx= x + j * COL_AR
        cvs.rect(cx, fila2_y - 14, COL_AR, 14, stroke=1, fill=0)
        cvs.setFont("Helvetica-Bold", 6.5)
        cvs.drawCentredString(cx + COL_AR / 2, fila2_y - 10, letra)
        letra_local= letra
        columnas.append((cx, COL_AR, lambda a, L=letra_local: ("X" if a["situacion"] == L else ""), False))

    y= fila2_y - 14
    cvs.rect(x0, fila1_y - alto_doble, ancho - 2 * margen, 0)  #no-op, mantiene referencia visual

    rgb_resaltado= _aclarar(rgb_banda, 0.8)
    cvs.setFont("Helvetica", 6.5)
    for area in areas:
        cvs.rect(x0, y - alto_fila, COL_LABEL, alto_fila, stroke=1, fill=0)
        _dibujar_texto_ajustado(cvs, area["materia_nombre"], x0 + 3, y - alto_fila + 4, COL_LABEL - 6,
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
        y -= 20

    #--- Resumen de Asistencia + Leyenda + Situación general + Condición final ---
    y -= 16
    y_cajas_top= y
    ancho_asistencia= 190
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

    #Leyenda (a la par del resumen de asistencia)
    x_leyenda= x0 + ancho_asistencia + 16
    y_l= y_cajas_top
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x_leyenda, y_l, "LEYENDA")
    y_l -= 12
    leyenda= [("P1-P4", "Período 1 a 4"), ("PC", "Promedio Grupo de Competencias Específicas"),
               ("C.F.", "Calificación Final"), ("C.E.C.", "Calificación Evaluación Completiva"),
               ("C.C.F.", "Calificación Completiva Final"), ("C.E. EX", "Calificación Evaluación Extraordinaria"),
               ("C.EX.F.", "Calificación Extraordinaria Final"), ("C.E.", "Calificación Especial"),
               ("A / R", "Aprobado / Reprobado")]
    cvs.setFont("Helvetica", 6.3)
    for abrev, significado in leyenda:
        cvs.drawString(x_leyenda, y_l, f"{abrev}: {significado}")
        y_l -= 8.5

    #Situación general + condición final (a la derecha)
    x_sit= x_leyenda + 230
    y_s= y_cajas_top
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x_sit, y_s, "SITUACIÓN DEL/DE LA ESTUDIANTE")
    y_s -= 14
    sg= boletin["situacion_general"]
    cvs.setFont("Helvetica", 7.5)
    cvs.drawString(x_sit, y_s, ("[X]" if sg.get("promovido") else "[ ]") + " Promovido/a")
    cvs.drawString(x_sit + 90, y_s, ("[X]" if sg.get("repitiente") else "[ ]") + " Repitiente")
    y_s -= 16
    cvs.setFont("Helvetica-Bold", 7.5)
    cvs.drawString(x_sit, y_s, "CONDICIÓN FINAL DEL/DE LA ESTUDIANTE:")
    y_s -= 12
    cvs.setFont("Helvetica", 7.5)
    cvs.drawString(x_sit, y_s, sg.get("decision", "Pendiente"))

    y_firmas= min(y, y_l, y_s) - 30
    _firmas(cvs, ancho, margen, y_firmas, institucion, "Maestro(a) Encargado(a) del Grado",
            "Director(a) del Centro Educativo")
    cvs.setFont("Helvetica", 6.5)
    cvs.drawString(margen, 12, f"Nota mínima aprobatoria: {boletin['nota_minima']:.0f}   |   "
                               f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d')}")
    return ancho, alto


def _dimensiones_pagina_secundaria(boletin):
    n_grupos= len(boletin["grupos_display"])
    n_periodos= max(len(boletin["periodos"]), 1)
    ancho, _ = _ancho_pagina_secundaria(n_grupos, n_periodos)
    alto= 170 + max(len(boletin["areas"]), 1) * 13 + 210
    return ancho, alto


def exportar_boletin_general_oficial_pdf(estudiante_id, ruta_pdf, institucion, metodo="Promedio Ponderado"):
    from reportlab.pdfgen import canvas as _canvas_mod

    boletin= construir_boletin_general(estudiante_id, metodo=metodo)
    if boletin is None:
        return None
    if boletin["primaria"]:
        from src.boletines.boletin_primaria_minerd import exportar_informe_primaria_pdf
        return exportar_informe_primaria_pdf(estudiante_id, ruta_pdf, institucion, boletin=boletin)

    #Se dibuja en dos pasadas: la primera calcula el tamaño exacto de página que necesita esta cantidad de
    #áreas/grupos/columnas (para no cortar ni sobrar espacio), la segunda dibuja de verdad sobre un canvas ya del
    #tamaño correcto.
    ancho, alto_estimado = _dimensiones_pagina_secundaria(boletin)
    cvs= _canvas_mod.Canvas(ruta_pdf, pagesize=(ancho, alto_estimado))
    dibujar_boletin_secundaria_oficial(cvs, institucion, boletin)
    cvs.save()
    return boletin
