"""Boletín Completo — Fase 3 de 3.

Esto NO es un cuarto sistema de cálculo: es el ensamblador que junta lo que
ya construyeron las Fases 1 y 2. La pieza que hacía posible esto ya
existía desde la Fase 1 sin que hubiera que tocarla:
`boletin_minerd.materias_de_estudiante` arma la grilla leyendo TODAS las
materias con horario en la sección del estudiante, sin filtrar por qué
docente dio esa materia -por eso un boletín ya sale completo (todas las
materias de todos los docentes) aunque quien lo exporte sea un solo
profesor. Lo único que faltaba era la exportación MASIVA (una sección
entera, un solo PDF) y la combinación automática con la página técnica
cuando el estudiante también cursa módulos de Politécnico.

Cada estudiante genera 1 página académica (Secundaria u Primaria, decidido
automáticamente por `construir_boletin_general`) + 1 página técnica SOLO SI
tiene módulos técnicos con horario o notas registradas ese año -si no
cursa Politécnico, no se le agrega una página técnica vacía.

Como cada estudiante puede tener columnas distintas (más o menos períodos,
más o menos áreas, con o sin RP), cada página del PDF final tiene su propio
tamaño exacto (reportlab permite tamaño de página por página) -no se
fuerza un tamaño único para toda la sección que recortaría a unos y
sobraría a otros.
"""
from src.nucleo.bd import get_connection
from src.boletines.boletin_minerd import (construir_boletin_general, dibujar_boletin_secundaria_oficial,
                             _dimensiones_pagina_secundaria)
from src.boletines.boletin_primaria_minerd import dibujar_informe_primaria_oficial, _dimensiones_pagina_primaria
from src.boletines.boletin_tecnico_minerd import (construir_boletin_tecnico, dibujar_boletin_tecnico_oficial,
                                     _dimensiones_pagina_tecnico)


def estudiantes_de_seccion(seccion_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT id FROM estudiantes WHERE seccion_id=? AND estado='Activo'
                 ORDER BY apellidos, nombre""", (seccion_id,))
    ids = [r["id"] for r in c.fetchall()]
    conn.close()
    return ids


def secciones_de_grado_o_todas(grado_id=None, anio_academico=None):
    """Lista de secciones a ofrecer en el selector de "Boletín completo":
    todas si no se filtra, o solo las de un grado (para Secretaría que
    quiere imprimir "todo 4to de Secundaria", por ejemplo)."""
    conn = get_connection()
    c = conn.cursor()
    condiciones, parametros = [], []
    if grado_id is not None:
        condiciones.append("grado_id=?")
        parametros.append(grado_id)
    if anio_academico is not None:
        condiciones.append("anio_academico=?")
        parametros.append(anio_academico)
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    c.execute(f"SELECT id, nombre, grado_id FROM secciones {where} ORDER BY grado_id, nombre", parametros)
    filas = [dict(f) for f in c.fetchall()]
    conn.close()
    return filas


def _agregar_pagina(cvs_ref, ancho, alto, dibujar_fn, *args):
    """`cvs_ref` es una lista de un elemento (truco para poder reasignar el
    canvas desde dentro de esta función: el primer estudiante determina con
    qué tamaño se ABRE el archivo; los siguientes solo cambian el tamaño de
    la página en curso con setPageSize, que reportlab sí permite variar
    página a página dentro del mismo documento)."""
    from reportlab.pdfgen import canvas as _canvas_mod
    if cvs_ref[0] is None:
        cvs_ref[0] = _canvas_mod.Canvas(cvs_ref[1], pagesize=(ancho, alto))
    else:
        cvs_ref[0].setPageSize((ancho, alto))
    dibujar_fn(cvs_ref[0], *args)
    cvs_ref[0].showPage()


def exportar_boletines_multiples_secciones_pdf(seccion_ids, ruta_pdf, institucion, incluir_tecnico=True,
                                                metodo="Promedio Ponderado", progreso_cb=None):
    """Igual que `exportar_boletin_seccion_pdf` pero para varias secciones
    en un solo archivo (p. ej. "todo 4to de Secundaria", que en AcaDeXI
    puede tener más de una sección A/B/C) -se usa la misma función interna
    de una sola sección, compartiendo el mismo canvas entre todas para que
    quede un solo PDF y no uno por sección."""
    cvs_ref = [None, ruta_pdf]
    generados, con_tecnico, omitidos = 0, 0, []
    total_estudiantes = sum(len(estudiantes_de_seccion(sid)) for sid in seccion_ids)
    indice_global = 0

    for seccion_id in seccion_ids:
        for estudiante_id in estudiantes_de_seccion(seccion_id):
            if progreso_cb:
                progreso_cb(indice_global, total_estudiantes, estudiante_id)
            indice_global += 1

            boletin = construir_boletin_general(estudiante_id, metodo=metodo)
            if boletin is None:
                omitidos.append(estudiante_id)
                continue

            if boletin["primaria"]:
                ancho, alto = _dimensiones_pagina_primaria(boletin)
                _agregar_pagina(cvs_ref, ancho, alto, dibujar_informe_primaria_oficial, institucion, boletin)
            else:
                ancho, alto = _dimensiones_pagina_secundaria(boletin)
                _agregar_pagina(cvs_ref, ancho, alto, dibujar_boletin_secundaria_oficial, institucion, boletin)
            generados += 1

            if incluir_tecnico:
                boletin_tec = construir_boletin_tecnico(estudiante_id)
                if boletin_tec and boletin_tec["modulos"]:
                    ancho_t, alto_t = _dimensiones_pagina_tecnico(boletin_tec)

                    def _dibujar_tecnico(cvs, institucion, boletin_tec, ancho_t=ancho_t, alto_t=alto_t):
                        dibujar_boletin_tecnico_oficial(cvs, ancho_t, alto_t, institucion, boletin_tec)

                    _agregar_pagina(cvs_ref, ancho_t, alto_t, _dibujar_tecnico, institucion, boletin_tec)
                    con_tecnico += 1

    if cvs_ref[0] is not None:
        cvs_ref[0].save()
    return {"generados": generados, "con_tecnico": con_tecnico, "omitidos": omitidos}


def exportar_boletin_seccion_pdf(seccion_id, ruta_pdf, institucion, incluir_tecnico=True,
                                  metodo="Promedio Ponderado", progreso_cb=None):
    """Genera UN solo PDF con el boletín completo de cada estudiante activo
    de la sección (orden alfabético, el mismo "número de orden" que ya usa
    cada boletín individual). Es un caso particular de
    `exportar_boletines_multiples_secciones_pdf` con una sola sección."""
    return exportar_boletines_multiples_secciones_pdf([seccion_id], ruta_pdf, institucion,
                                                        incluir_tecnico=incluir_tecnico, metodo=metodo,
                                                        progreso_cb=progreso_cb)
