#Buscador Global de AcaDeXI.
#
#Permite buscar por nombre/matrícula/código en Estudiantes, Profesores, Personal
#Administrativo, Materias, Eventos del Calendario, Tareas del Banco de Tareas,
#Observaciones, Casos de Psicología, Materiales (inventario), Clases del
#Horario, Facultades/Carreras (Universidad) y Especialidades/Empresas/Pasantías
#(Politécnico) desde cualquier parte del sistema, y navegar directamente al
#módulo y registro correspondiente. Respeta el RBAC real por fila: un Profesor
#logueado solo ve resultados de sus propias secciones/materias/eventos;
#Psicología solo aparece para quien tiene acceso real al módulo (ver
#puede_ver_psicologia) y Materiales respeta el permiso granular por categoría.
#
#Además:
#- Encuentra un módulo por nombre (o sinónimo) y navega directo a él, sin
#registro asociado: escribir "calificaciones", "banco de tareas" u "horario"
#ya alcanza (ver _ALIAS_MODULOS y _buscar_modulos).
#- Un estudiante también aparece al buscar por su grado/curso, su sección, su
#área técnica o su carrera (según el tipo de institución), combinados o no
#con su nombre: "adrian informatica", "5to C", "5c", "5-C" y "Adrián 5-C"
#encuentran al mismo estudiante si le corresponde 5to grado, sección C y
#área técnica/carrera "Informática".
#- Escribir el nombre de una categoría (p. ej. "profesor") junto con un
#nombre propio, como en "profesor felix", prioriza resultados de esa
#categoría con ese nombre.
#- Modo Docente: cuando busca un Profesor (que solo ve "Mis Estudiantes"),
#se aplican sus retoques LOCALES (ver datos_locales_docente.py) por encima
#del dato institucional — igual que en la tabla del propio módulo — para
#que encuentre y muestre la versión que él mismo corrigió, aunque
#Dirección todavía no haya actualizado ese dato en el sistema.
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QShortcut, QKeySequence

from src.nucleo.bd import obtener_conexion
from src.nucleo.iconos import aplicar_icono_ventana, centrar_y_al_frente, ICONO_BUSQUEDA, icono_qicon_modulo
from src.nucleo.permisos import (es_profesor_restringido, obtener_secciones_permitidas,
    obtener_materias_permitidas, modulo_visible, puede_ver_psicologia,
    tiene_acceso_total_materiales, obtener_permisos_materiales_usuario)
from src.nucleo.datos_locales_docente import listar_overrides_estudiantes, aplicar_override
from src.nucleo.formato_hora import formatear_fecha
from src.nucleo.limite_campos import limitar_campo_texto


#Normaliza texto: convierte a minúsculas y elimina acentos.
def _normalizar_texto(texto):

    if not texto:
        return ""
    texto= texto.lower()
    return ''.join(
        c for c in unicodedata.normalize('NFKD', texto)
        if not unicodedata.combining(c)
    )


#Umbral de similitud por PALABRA (no por frase completa) para tolerar errores de tipeo. Con palabras cortas (3
#letras o menos) se relaja, porque un solo carácter de diferencia ya representa un porcentaje alto del texto.
_UMBRAL_PALABRA= 0.72
_UMBRAL_PALABRA_CORTA= 0.55


#True si `palabra_busqueda` (ya normalizada) aparece dentro del texto
#destino, ya sea como subcadena exacta, como prefijo de alguna palabra del
#destino (para búsquedas incompletas tipo "gonz" -> "gonzalez"), o con
#suficiente similitud aproximada Y la misma letra inicial frente a alguna
#palabra del destino (para tolerar errores de tipeo, ej. "gonzales" ->
#"gonzalez", sin confundir palabras distintas que solo comparten letras
#en el medio, ej. "maria" / "adrian").
#
#CASO ESPECIAL - palabra de una sola letra: no se busca como subcadena de
#TODO el texto destino, porque una sola letra aparece casi siempre en
#algún lugar de cualquier bloque de texto largo (nombre, especialidad,
#carrera...) y esa comprobación tan floja lo volvería inútil. Esto importa
#en especial ahora que la sección de un estudiante ("A", "B", "C"...) se
#puede buscar por separado (ej. "5to C"): una letra suelta debe exigir que
#alguna palabra COMPLETA del destino EMPIECE con ella (como cualquier otra
#palabra corta), no que la letra aparezca en cualquier posición de
#cualquier palabra. Así "c" encuentra la sección "C" (o un nombre que
#empiece por C, como "Carlos"), pero no cualquier palabra que solo
#contenga una 'c' en el medio (como "Informática").
def _palabra_coincide(palabra_busqueda, texto_destino_norm, palabras_destino):

    if len(palabra_busqueda) == 1:
        #p: cada palabra del destino; basta con que alguna empiece por la letra suelta buscada.
        return any(p.startswith(palabra_busqueda) for p in palabras_destino)
    if palabra_busqueda in texto_destino_norm:
        return True
    umbral= _UMBRAL_PALABRA_CORTA if len(palabra_busqueda) <= 3 else _UMBRAL_PALABRA
    for palabra_dest in palabras_destino:
        if palabra_dest.startswith(palabra_busqueda):
            return True
        #La tolerancia a tipeo (ratio de SequenceMatcher) exige ADEMÁS que ambas palabras empiecen con la misma letra.
        #Sin este requisito, nombres realmente distintos pero de longitud parecida y con letras en común pueden
        #"parecerse" lo suficiente por pura coincidencia: por ejemplo SequenceMatcher da 0.73 de similitud entre
        #"adrian" y "maria" (ambas comparten "aria"), lo que bastaba para que buscar "maria" encontrara por error a un
        #estudiante llamado "Adrian". Un error de tipeo real casi nunca cambia la primera letra (se escribe con cuidado
        #el inicio de la palabra), así que exigir la misma letra inicial elimina ese tipo de falso positivo sin perder
        #tolerancia
        #real a errores de tipeo (ej. "gonzales" -> "gonzalez" sigue
        #funcionando: ambas empiezan con "g").
        if palabra_dest[0] != palabra_busqueda[0]:
            continue
        if SequenceMatcher(None, palabra_busqueda, palabra_dest).ratio() >= umbral:
            return True
    return False


#Verifica coincidencia entre la búsqueda y el texto destino, ignorando
#acentos y mayúsculas/minúsculas.
#
#A diferencia de comparar las dos frases completas de un tirón (lo que
#diluye la similitud y falla apenas el destino es más largo que la
#búsqueda, como pasa con "nombre apellidos matrícula" concatenados), aquí
#la búsqueda se separa en palabras y CADA una debe encontrarse en algún
#lugar del destino (en cualquier orden). Esto permite encontrar, por
#ejemplo, "perez juan" o solo "gonz" (prefijo) o "gonzales" con una letra
#de más/menos (tolerancia a tipeo), sin exigir que el texto completo se
#parezca en su totalidad.
def _coincidencia_fuzzy(texto_busqueda, texto_destino):

    if not texto_busqueda or not texto_destino:
        return False
    busqueda_norm= _normalizar_texto(texto_busqueda)
    destino_norm= _normalizar_texto(texto_destino)
    #p: cada palabra de la búsqueda normalizada; se descartan las vacías.
    palabras_busqueda= [p for p in busqueda_norm.split() if p]
    if not palabras_busqueda:
        return False
    #p: cada palabra del destino normalizado; se descartan las vacías.
    palabras_destino= [p for p in destino_norm.split() if p]
    #p: cada palabra de la búsqueda; todas deben coincidir con el destino para aceptar el resultado.
    return all(_palabra_coincide(p, destino_norm, palabras_destino) for p in palabras_busqueda)


#Puntaje simple para ordenar resultados: las coincidencias más exactas
#(o que empiezan igual) se muestran primero que las aproximadas.
def _puntaje_relevancia(texto_busqueda, texto_destino):

    busqueda_norm= _normalizar_texto(texto_busqueda)
    destino_norm= _normalizar_texto(texto_destino)
    if destino_norm.startswith(busqueda_norm):
        return 3.0
    if busqueda_norm in destino_norm:
        return 2.0
    return 1.0 + SequenceMatcher(None, busqueda_norm, destino_norm).ratio()


def _modulo_visible_estudiantes(rol, restringido):

    nombre= "Mis Estudiantes" if restringido else "Estudiantes"
    return modulo_visible(rol, nombre)


def _modulo_visible_materias(rol, restringido):

    nombre= "Mis Materias" if restringido else "Materias"
    return modulo_visible(rol, nombre)


#Sinónimos comunes en español/RD para cada módulo, para que escribir "notas" encuentre "Calificaciones",
#"faltas" encuentre "Asistencia", etc., aunque el texto no coincida literalmente con el nombre que aparece en
#el menú lateral. No se muestran al usuario (la etiqueta siempre usa el nombre real del módulo): solo se usan
#puertas adentro para ampliar qué encuentra la búsqueda.
_ALIAS_MODULOS= {
    "Dashboard": "inicio resumen panel",
    "Calificaciones": "notas boletin boletines",
    "Calificaciones Técnicas": "notas boletin tecnicas",
    "Asistencia": "faltas inasistencia inasistencias",
    "Banco de Tareas": "tareas asignaciones actividades",
    "Horario": "clases",
    "Configuración": "ajustes preferencias config",
    "Copias de Seguridad": "backup backups respaldo respaldos",
    "Sincronización": "sync",
    "Reportes": "informes estadisticas",
    "Personal": "administrativo administrativa staff",
    "Observaciones": "disciplina disciplinarias incidencias anotaciones",
    "Materiales": "inventario biblioteca laboratorio equipos prestamos préstamos recursos",
    "Psicología": "psicologo psicologa psicólogo psicóloga casos terapia conductual",
    "Universidad": "facultades carreras pensum malla curricular",
    "Politécnico": "especialidades areas técnicas empresas pasantias pasantías talleres",
}


#Busca por nombre de módulo (o alguno de sus sinónimos en _ALIAS_MODULOS)
#para poder saltar directo a él escribiendo, por ejemplo, "calificaciones",
#"banco de tareas" u "horario", sin tener que ir a buscarlo en el menú
#lateral. Solo devuelve módulos visibles para el usuario actual: se
#consulta el estado real (oculto/visible) de cada fila del menú, que ya
#tiene en cuenta el rol Y cualquier ocultamiento dinámico adicional (p. ej.
#"Copias de Seguridad" solo para roles gerenciales).
#
#El ícono que se devuelve (en la posición del ícono, no concatenado al
#texto de la etiqueta) es el MISMO que ya se ve en esa fila de la
#sidebar -PNG de sidebar_icons/ o, si el módulo no tiene uno propio
#todavía, el icono vectorial coherente de iconos_auto.py-, solo que
#reducido a tamaño de emoji (ver icono_qicon_modulo en iconos.py). Antes
#se usaba el emoji suelto de respaldo de modulos_info (que ni siquiera
#es lo que la sidebar termina mostrando la mayoría de las veces, según
#su propio comentario en main.py), así que un resultado de "Módulos"
#podía verse con un ícono distinto al de esa misma fila en el menú.
def _buscar_modulos(main_window, texto):

    resultados= []
    modulos_info= getattr(main_window, "modulos_info", None) or []
    nav_list= getattr(main_window, "nav_list", None)
    coincidencias= []
    for idx, (_icono_respaldo, nombre) in enumerate(modulos_info):
        if nav_list is not None:
            item= nav_list.item(idx)
            if item is not None and item.isHidden():
                continue
        alias= _ALIAS_MODULOS.get(nombre, "")
        texto_destino= f"{nombre} {alias}".strip()
        if not _coincidencia_fuzzy(texto, texto_destino):
            continue
        #El puntaje prioriza la coincidencia contra el NOMBRE real del módulo; si solo coincidió por un sinónimo, se
        #penaliza un poco para que una coincidencia directa con el nombre siempre gane el empate.
        puntaje= max(_puntaje_relevancia(texto, nombre),
                      _puntaje_relevancia(texto, texto_destino) - 0.5)
        coincidencias.append((puntaje, ("Módulos", nombre, nombre, None, _icono_categoria(nombre))))
    #par es (puntaje, resultado): se ordena por puntaje de mayor a menor. r es el resultado de cada par;
    #solo se agregan los mejores de la categoría.
    coincidencias.sort(key=lambda par: par[0], reverse=True)
    resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])
    return resultados


#Tope de resultados a MOSTRAR por categoría, aplicado DESPUÉS de filtrar (ya no antes, como el viejo LIMIT 25
#en SQL que descartaba registros sin siquiera revisarlos). Esto solo evita que la lista crezca sin límite; no
#afecta qué tan a fondo se busca.
MAX_RESULTADOS_POR_CATEGORIA= 30

MODULO_ROLE= Qt.ItemDataRole.UserRole
TEXTO_BUSCAR_ROLE= Qt.ItemDataRole.UserRole + 1


#Icono por defecto para cada categoría de resultado, usado cuando el propio resultado no trae uno más
#específico (como sí hace cada fila de "Módulos", con el icono real de ESE módulo). Es el mismo QIcon "reducido
#a emoji" que ya usa la sidebar para el módulo correspondiente a esa categoría (ver icono_qicon_modulo en
#iconos.py): PNG propio si existe, si no el icono vectorial coherente de iconos_auto.py -nunca un emoji crudo
#elegido a mano aparte, que antes hacía que, por ejemplo, "Profesores" y "Personal" (dos módulos con icono
#propio bien distinto en la sidebar) se vieran aquí con el mismo glyph genérico de "dos personas".
##Con @lru_cache en vez de un diccionario armado de una sola vez a nivel de módulo: icono_qicon_modulo()
#construye QPixmap/QIcon, que en Qt necesitan una QApplication ya viva -y buscador_global.py se importa en
#main.py ANTES de crear la QApplication (import de módulos arriba, QApplication() recién
#dentro de `if __name__ == "__main__"`)-. Resolviendo perezosamente, en el
#primer uso real (ya con la app corriendo), se evita ese problema y de paso se cachea para no repetir la
#resolución en cada resultado de una búsqueda.
@lru_cache(maxsize=None)
def _icono_categoria(nombre_modulo):

    return icono_qicon_modulo(nombre_modulo)


#Devuelve una lista de tuplas (categoria, etiqueta, modulo_destino,
#texto_filtro, icono) con los resultados que coinciden con `texto` en las
#distintas entidades del sistema, respetando las restricciones de RBAC
#por fila para el rol Profesor. `icono` ya es un QIcon real y reducido a
#tamaño de emoji -el mismo que usa la sidebar para el módulo de esa
#categoría (ver icono_qicon_modulo en iconos.py)-, listo para pasarse
#directo a QListWidgetItem.setIcon(), nunca un emoji crudo dentro de la
#etiqueta de texto.
#Utiliza fuzzy matching (por palabra, no por frase completa) para mayor
#flexibilidad, y revisa TODOS los registros activos de cada categoría, no
#solo los primeros de la lista, ordenando después por relevancia.
def buscar_global(main_window, texto):

    texto= (texto or "").strip()
    if len(texto) < 1:
        return []
    resultados= []
    rol= getattr(main_window, "rol_actual", None)

    #--- Módulos (navegación directa, sin registro asociado) --- Va primero: si alguien escribe el nombre de un
    #módulo ("horario", "banco de tareas"...) lo más útil es verlo de inmediato arriba, sin tener que bajar entre
    #resultados de estudiantes/profesores/etc.
    resultados.extend(_buscar_modulos(main_window, texto))

    conn= obtener_conexion()
    c= conn.cursor()

    #--- Estudiantes ---
    restringir_secciones= es_profesor_restringido(main_window)
    #Secciones permitidas del docente, calculadas UNA sola vez: la usan la sección de Estudiantes y también las
    #categorías nuevas (Observaciones, Psicología, Pasantías...) que filtran por la sección del estudiante.
    secciones_permitidas_glob= (obtener_secciones_permitidas(main_window)
                                  if restringir_secciones else None)
    destino_estudiantes= "Mis Estudiantes" if restringir_secciones else "Estudiantes"
    if _modulo_visible_estudiantes(rol, restringir_secciones):
        secciones_permitidas= obtener_secciones_permitidas(main_window) if restringir_secciones else None
        #MODO DOCENTE: un Profesor busca sobre "Mis Estudiantes", que muestra sus retoques LOCALES (ver
        #datos_locales_docente.py) por encima del dato institucional — el mismo criterio que ya usa _cargar_tabla() en
        #estudiantes.py. Si el docente corrigió localmente un nombre o una sección que Dirección aún no actualizó, el
        #buscador debe encontrar (y mostrar) esa versión corregida, no la institucional desactualizada.
        overrides= listar_overrides_estudiantes(main_window) if restringir_secciones else {}
        #Si algún override cambia la sección de un estudiante, esa sección puede no ser ninguna de las "permitidas" de
        #este docente (es solo texto local, no un cambio real de acceso) ni la que ya trae el JOIN de abajo (que se
        #arma con la sección INSTITUCIONAL). Por eso se arma aparte un mapa completo grado+sección para poder
        #resolverla.
        mapa_grado_seccion= {}
        if restringir_secciones and overrides:
            c.execute("""SELECT s.id, s.nombre AS seccion_nombre, g.nombre AS grado_nombre
                         FROM secciones s LEFT JOIN grados g ON g.id = s.grado_id""")
            mapa_grado_seccion= {fs["id"]: (fs["grado_nombre"] or "", fs["seccion_nombre"] or "")
                                   for fs in c.fetchall()}
        #Sin LIMIT aquí: se revisan TODOS los estudiantes activos y se filtra en memoria. Antes se limitaba a los
        #primeros 25 (alfabéticamente) ANTES de aplicar la búsqueda, así que con más de 25 estudiantes, cualquiera
        #fuera de ese primer bloque alfabético era invisible para el buscador sin importar qué tan bien coincidiera. Se
        #hace JOIN con secciones/grados/especialidades/carreras para que el estudiante también se encuentre buscando
        #por su curso ("5to"), su
        #sección ("C"), su área técnica o su carrera — no solo por nombre o
        #matrícula como antes.
        c.execute("""SELECT e.id, e.matricula, e.nombre, e.apellidos, e.seccion_id, e.carrera_id,
                            s.nombre AS seccion_nombre, g.nombre AS grado_nombre,
                            g.nivel_educativo AS nivel_educativo,
                            esp.nombre AS especialidad_nombre, car.nombre AS carrera_nombre
                     FROM estudiantes e
                     LEFT JOIN secciones s ON s.id = e.seccion_id
                     LEFT JOIN grados g ON g.id = s.grado_id
                     LEFT JOIN especialidades esp ON esp.id = e.especialidad_id
                     LEFT JOIN carreras car ON car.id = e.carrera_id
                     WHERE e.estado='Activo'""")
        coincidencias= []
        for fila in c.fetchall():
            #El RBAC por fila se decide SIEMPRE con la sección institucional
            #real (f), nunca con la del override: un retoque local es solo
            #una personalización de texto, no un cambio real de acceso.
            if secciones_permitidas is not None and fila["seccion_id"] not in secciones_permitidas:
                continue
            datos= aplicar_override(fila, overrides.get(fila["id"])) if restringir_secciones else fila

            nombre_completo= f"{datos['nombre']} {datos['apellidos'] or ''}"
            seccion_id_efectiva= datos["seccion_id"]
            if restringir_secciones and seccion_id_efectiva != fila["seccion_id"]:
                #El docente reasignó localmente a este estudiante a otra sección: se resuelve su nombre en el mapa completo
                #(arriba) en vez del que trae el JOIN (que sigue la sección institucional).
                grado_nombre, seccion_nombre= mapa_grado_seccion.get(
                    seccion_id_efectiva, (fila["grado_nombre"] or "", fila["seccion_nombre"] or ""))
            else:
                grado_nombre= fila["grado_nombre"] or ""
                seccion_nombre= fila["seccion_nombre"] or ""
            #El área técnica y la carrera SÍ se muestran en la tabla de "Mis Estudiantes" siempre con el dato institucional
            #(nunca el override), así que aquí se respeta el mismo criterio.
            especialidad_nombre= fila["especialidad_nombre"] or ""
            carrera_nombre= fila["carrera_nombre"] or ""
            #Nivel educativo como criterio de búsqueda más ("Juan Pérez secundaria", "3ro C informática secundaria"): mismo
            #dato que ya usa el filtro de Nivel Educativo en Estudiantes - Universidad se reconoce por tener Carrera (dato
            #existente), el resto por grados.nivel_educativo (ver resolver_nivel_academico_* en bd.py, la misma fuente de
            #verdad en todos lados).
            nivel_nombre= "Universidad" if fila["carrera_id"] is not None else (fila["nivel_educativo"] or "")

            partes_busqueda= [nombre_completo, fila["matricula"] or "", "estudiante alumno alumna"]
            if grado_nombre:
                partes_busqueda.append(grado_nombre)
            if seccion_nombre:
                partes_busqueda.append(seccion_nombre)
            if grado_nombre and seccion_nombre:
                #Formas abreviadas típicas de nombrar "curso + sección" de un
                #tirón ("5c", "5-C"), además de la forma ya cubierta arriba
                #como dos palabras sueltas ("5to" + "C", ej. "5to C").
                numero_grado= re.match(r"\s*(\d+)", grado_nombre)
                if numero_grado:
                    partes_busqueda.append(f"{numero_grado.group(1)}{seccion_nombre}")
                    partes_busqueda.append(f"{numero_grado.group(1)}-{seccion_nombre}")
            if especialidad_nombre:
                partes_busqueda.append(especialidad_nombre)
            if carrera_nombre:
                partes_busqueda.append(carrera_nombre)
            if nivel_nombre:
                partes_busqueda.append(nivel_nombre)
            #p: cada parte de texto no vacía; se unen en un solo texto para comparar con la búsqueda.
            texto_concatenado= " ".join(p for p in partes_busqueda if p)

            if _coincidencia_fuzzy(texto, texto_concatenado):
                #p: cada trozo de detalle no vacío; se unen con ' · ' para mostrar en el resultado.
                detalle= " · ".join(p for p in (
                    f"{grado_nombre} {seccion_nombre}".strip(),
                    especialidad_nombre, carrera_nombre) if p)
                etiqueta= f"{nombre_completo} — Matrícula {datos['matricula'] or 's/n'}"
                if detalle:
                    etiqueta += f" ({detalle})"
                if restringir_secciones and fila["id"] in overrides:
                    #Antes esto agregaba un emoji de lapicito suelto al final de la etiqueta; con los emojis fuera del texto, se
                    #dice con palabras que ese dato tiene un retoque local propio del docente que Dirección aún no actualizó en el
                    #sistema.
                    etiqueta += " (editado localmente)"
                #texto_filtro va con el dato INSTITUCIONAL (no el override):
                #es lo que se escribe en el buscador rápido de "Mis Estudiantes" al llegar, y ese buscador rápido compara
                #contra el nombre/matrícula institucional, no contra el override.
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Estudiantes", etiqueta, destino_estudiantes,
                                        fila["matricula"] or fila["nombre"], _icono_categoria(destino_estudiantes))))
        #Aquí y en cada bloque de categoría siguiente: par=(puntaje, resultado) para ordenar por relevancia
        #y r=resultado que se agrega a la lista final (solo los mejores de la categoría).
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Profesores ---
    if modulo_visible(rol, "Profesores"):
        c.execute("""SELECT id, nombre, apellidos, especialidad FROM profesores
                     WHERE estado='Activo'""")
        coincidencias= []
        for fila in c.fetchall():
            nombre_completo= f"{fila['nombre']} {fila['apellidos'] or ''}"
            #Alias "profesor/profesora/docente" para que una búsqueda tipo "profesor felix" encuentre al profesor Félix
            #aunque la palabra "profesor" no forme parte de su nombre ni especialidad.
            texto_concatenado= f"{nombre_completo} {fila['especialidad'] or ''} profesor profesora docente"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                etiqueta= nombre_completo + (f" — {fila['especialidad']}" if fila["especialidad"] else "")
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Profesores", etiqueta, "Profesores", fila["nombre"],
                                        _icono_categoria("Profesores"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Personal Administrativo ---
    if modulo_visible(rol, "Personal"):
        c.execute("""SELECT id, nombre, apellidos, cargo FROM personal_administrativo
                     WHERE estado='Activo'""")
        coincidencias= []
        for fila in c.fetchall():
            nombre_completo= f"{fila['nombre']} {fila['apellidos'] or ''}"
            texto_concatenado= f"{nombre_completo} {fila['cargo'] or ''} personal administrativo"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                etiqueta= nombre_completo + (f" — {fila['cargo']}" if fila["cargo"] else "")
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Personal", etiqueta, "Personal", fila["nombre"],
                                        _icono_categoria("Personal"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Materias ---
    destino_materias= "Mis Materias" if restringir_secciones else "Materias"
    if _modulo_visible_materias(rol, restringir_secciones):
        materias_permitidas= obtener_materias_permitidas(main_window) if restringir_secciones else None
        #Los módulos técnicos (modelo_evaluacion='Técnica (RA)') viven en su
        #propio módulo dentro de Politécnico, no en "Materias" -el propio listado de Materias ya los excluye (ver
        #materias.py), así que el buscador global debe hacer lo mismo para no ofrecer un resultado que en realidad no
        #está ahí.
        c.execute("""SELECT id, codigo, nombre FROM materias
                     WHERE estado='Activa'
                     AND (modelo_evaluacion IS NULL OR modelo_evaluacion != 'Técnica (RA)')""")
        coincidencias= []
        for fila in c.fetchall():
            if materias_permitidas is not None and fila["id"] not in materias_permitidas:
                continue
            texto_concatenado= f"{fila['nombre']} {fila['codigo'] or ''} materia asignatura"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                etiqueta= f"{fila['nombre']}" + (f" ({fila['codigo']})" if fila["codigo"] else "")
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Materias", etiqueta, destino_materias, fila["nombre"],
                                        _icono_categoria(destino_materias))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Eventos del Calendario --- Antes el buscador global ignoraba por completo esta tabla: escribir el título
    #de un evento (p. ej. "reunión") no encontraba nada, aunque el evento sí existiera y se viera perfectamente en
    #el propio módulo Calendario. Mismo criterio de visibilidad que usa ModuloCalendario._
    #cargar_datos(): un evento "Personal" solo lo ve quien lo creó; el resto
    #(Institucional, Examen, Entrega, Reunión) lo ve cualquier usuario que tenga acceso al módulo Calendario.
    if modulo_visible(rol, "Calendario"):
        usuario_id= getattr(main_window, "id_usuario_actual", None)
        c.execute("SELECT id, titulo, descripcion, tipo, fecha, visibilidad, usuario_id FROM eventos")
        coincidencias= []
        for fila in c.fetchall():
            if fila["visibilidad"] == "Personal" and fila["usuario_id"] != usuario_id:
                continue
            texto_concatenado= (f"{fila['titulo']} {fila['descripcion'] or ''} {fila['tipo'] or ''} "
                                  f"evento cita calendario")
            if _coincidencia_fuzzy(texto, texto_concatenado):
                fecha_fmt= formatear_fecha(fila["fecha"], main_window)
                etiqueta= fila["titulo"] + (f" — {fecha_fmt}" if fecha_fmt else "")
                if fila["tipo"]:
                    etiqueta += f" ({fila['tipo']})"
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Calendario", etiqueta, "Calendario", fila["titulo"],
                                        _icono_categoria("Calendario"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Tareas (Banco de Tareas) --- Igual que Calendario: el buscador global tampoco tocaba esta tabla. Un
    #Profesor restringido solo encuentra tareas de sus propias materias (mismo criterio que usa el propio módulo,
    #ver obtener_materias_permitidas).
    if modulo_visible(rol, "Banco de Tareas"):
        materias_permitidas= obtener_materias_permitidas(main_window) if restringir_secciones else None
        c.execute("""SELECT t.id, t.titulo, t.categoria, t.materia_id, t.estado, t.fecha_entrega,
                            m.nombre AS materia_nombre
                     FROM tareas t LEFT JOIN materias m ON m.id = t.materia_id
                     WHERE t.estado='Activa'""")
        coincidencias= []
        for fila in c.fetchall():
            if materias_permitidas is not None and fila["materia_id"] not in materias_permitidas:
                continue
            texto_concatenado= (f"{fila['titulo']} {fila['categoria'] or ''} {fila['materia_nombre'] or ''} "
                                  f"tarea actividad")
            if _coincidencia_fuzzy(texto, texto_concatenado):
                fecha_fmt= formatear_fecha(fila["fecha_entrega"], main_window)
                etiqueta= fila["titulo"]
                #p: cada dato de detalle no vacío (materia, categoría); se unen con ' · '.
                detalle= " · ".join(p for p in (fila["materia_nombre"], fila["categoria"]) if p)
                if detalle:
                    etiqueta += f" — {detalle}"
                if fecha_fmt:
                    etiqueta += f" (entrega {fecha_fmt})"
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Banco de Tareas", etiqueta, "Banco de Tareas", fila["titulo"],
                                        _icono_categoria("Banco de Tareas"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Observaciones ---
    #El buscador global ignoraba por completo esta tabla. RBAC por fila:
    #un Profesor restringido solo encuentra observaciones de estudiantes de sus propias secciones (mismo criterio
    #que el módulo). El texto que se pre-carga al llegar al módulo es el nombre del estudiante, que es como el
    #buscador del módulo acota mejor sus registros.
    if modulo_visible(rol, "Observaciones"):
        c.execute("""SELECT o.texto, o.naturaleza, o.categorias, o.destacada, o.fecha,
                            e.nombre AS est_nombre, e.apellidos AS est_apellidos,
                            e.seccion_id AS seccion_id
                     FROM observaciones o
                     LEFT JOIN estudiantes e ON e.id = o.estudiante_id""")
        coincidencias= []
        for fila in c.fetchall():
            if restringir_secciones and (secciones_permitidas_glob is None
                                          or fila["seccion_id"] not in secciones_permitidas_glob):
                continue
            nombre_est= f"{fila['est_nombre'] or ''} {fila['est_apellidos'] or ''}".strip()
            texto_concatenado= (f"{nombre_est} {fila['texto'] or ''} {fila['naturaleza'] or ''} "
                                  f"{fila['categorias'] or ''} observación anotación")
            if _coincidencia_fuzzy(texto, texto_concatenado):
                fecha_fmt= formatear_fecha(fila["fecha"][:10], main_window) if fila["fecha"] else None
                etiqueta= f"{fila['naturaleza'] or 'Informativa'} — {nombre_est or 'Sin estudiante'}"
                if fila["destacada"]:
                    etiqueta += " (destacada)"
                if fecha_fmt:
                    etiqueta += f" — {fecha_fmt}"
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Observaciones", etiqueta, "Observaciones",
                                        nombre_est or None, _icono_categoria("Observaciones"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Psicología (casos) --- Visibilidad especial: solo el/la psicólogo/a con el módulo otorgado (o el
    #Administrador con la función habilitada) ve estos registros — ver puede_ver_psicologia en permisos.py. Son
    #registros sensibles: si el usuario no tiene acceso al módulo, ni siquiera aparecen en resultados.
    if puede_ver_psicologia(main_window):
        c.execute("""SELECT p.texto, p.naturaleza, p.estado_caso, p.fecha,
                            e.nombre AS est_nombre, e.apellidos AS est_apellidos
                     FROM psicologia p
                     LEFT JOIN estudiantes e ON e.id = p.estudiante_id""")
        coincidencias= []
        for fila in c.fetchall():
            nombre_est= f"{fila['est_nombre'] or ''} {fila['est_apellidos'] or ''}".strip()
            texto_concatenado= (f"{nombre_est} {fila['texto'] or ''} {fila['naturaleza'] or ''} "
                                  f"{fila['estado_caso'] or ''} caso psicología psicológico")
            if _coincidencia_fuzzy(texto, texto_concatenado):
                fecha_fmt= formatear_fecha(fila["fecha"][:10], main_window) if fila["fecha"] else None
                etiqueta= f"{fila['estado_caso'] or 'Caso'} — {nombre_est or 'Sin estudiante'}"
                if fecha_fmt:
                    etiqueta += f" — {fecha_fmt}"
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Psicología", etiqueta, "Psicología",
                                        nombre_est or None, _icono_categoria("Psicología"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Materiales (inventario) --- RBAC granular por CATEGORÍA de material (ver permisos.py): quien tiene acceso
    #total ve todo el inventario; quien tiene permisos por usuario solo encuentra materiales de sus categorías
    #asignadas.
    if modulo_visible(rol, "Materiales"):
        categorias_permitidas= None
        if not tiene_acceso_total_materiales(main_window):
            id_usuario= getattr(main_window, "id_usuario_actual", None)
            categorias_permitidas= {cid for cid, _p in obtener_permisos_materiales_usuario(id_usuario)}
        c.execute("""SELECT m.nombre, m.codigo, m.descripcion, m.ubicacion, m.estado,
                            m.categoria_id, cm.nombre AS categoria_nombre
                     FROM materiales m
                     LEFT JOIN categorias_material cm ON cm.id = m.categoria_id""")
        coincidencias= []
        for fila in c.fetchall():
            if categorias_permitidas is not None and fila["categoria_id"] not in categorias_permitidas:
                continue
            texto_concatenado= (f"{fila['nombre']} {fila['codigo'] or ''} {fila['descripcion'] or ''} "
                                  f"{fila['ubicacion'] or ''} {fila['categoria_nombre'] or ''} "
                                  f"{fila['estado'] or ''} material inventario equipo")
            if _coincidencia_fuzzy(texto, texto_concatenado):
                #p: cada dato de detalle no vacío (categoría, ubicación); se unen con ' · '.
                detalle= " · ".join(p for p in (fila["categoria_nombre"], fila["ubicacion"]) if p)
                etiqueta= fila["nombre"] + (f" ({fila['codigo']})" if fila["codigo"] else "")
                if detalle:
                    etiqueta += f" — {detalle}"
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Materiales", etiqueta, "Materiales",
                                        fila["nombre"], _icono_categoria("Materiales"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Horario (clases) --- RBAC: un Profesor restringido solo encuentra clases de sus materias y
    #secciones (mismos criterios de obtener_materias/secciones_permitidas).
    if modulo_visible(rol, "Horario"):
        materias_permitidas= obtener_materias_permitidas(main_window) if restringir_secciones else None
        c.execute("""SELECT h.dia, h.hora_inicio, h.hora_fin,
                            m.nombre AS materia_nombre, m.id AS materia_id,
                            s.nombre AS seccion_nombre, s.id AS seccion_id,
                            g.nombre AS grado_nombre, a.nombre AS aula_nombre
                     FROM horarios h
                     LEFT JOIN materias m ON m.id = h.materia_id
                     LEFT JOIN secciones s ON s.id = h.seccion_id
                     LEFT JOIN grados g ON g.id = s.grado_id
                     LEFT JOIN aulas a ON a.id = h.aula_id""")
        coincidencias= []
        for fila in c.fetchall():
            if materias_permitidas is not None and fila["materia_id"] not in materias_permitidas:
                continue
            if restringir_secciones and secciones_permitidas_glob is not None \
                    and fila["seccion_id"] not in secciones_permitidas_glob:
                continue
            grupo= f"{fila['grado_nombre'] or ''} {fila['seccion_nombre'] or ''}".strip()
            texto_concatenado= (f"{fila['materia_nombre'] or ''} {grupo} {fila['dia'] or ''} "
                                  f"{fila['aula_nombre'] or ''} clase horario")
            if _coincidencia_fuzzy(texto, texto_concatenado):
                #p: cada dato de la franja no vacío (día, hora inicio, hora fin); se unen con ' · '.
                franja= " · ".join(p for p in (fila["dia"], fila["hora_inicio"], fila["hora_fin"]) if p)
                etiqueta= f"{fila['materia_nombre'] or 'Sin materia'}"
                if grupo:
                    etiqueta += f" — {grupo}"
                if franja:
                    etiqueta += f" ({franja})"
                if fila["aula_nombre"]:
                    etiqueta += f" — Aula {fila['aula_nombre']}"
                coincidencias.append((_puntaje_relevancia(texto, texto_concatenado),
                                       ("Horario", etiqueta, "Horario",
                                        fila["materia_nombre"], _icono_categoria("Horario"))))
        #par: (puntaje, resultado); los de mayor puntaje van primero
        coincidencias.sort(key=lambda par: par[0], reverse=True)
        resultados.extend(r for _, r in coincidencias[:MAX_RESULTADOS_POR_CATEGORIA])

    #--- Universidad: facultades y carreras --- Entidades sin buscador propio que precargue texto (la pestaña no se
    #puede preseleccionar desde el resultado), así que texto_filtro va None:
    #el clic navega al módulo y ya.
    if modulo_visible(rol, "Universidad"):
        c.execute("""SELECT f.nombre AS facultad_nombre,
                            (SELECT GROUP_CONCAT(cr.nombre, ', ') FROM carreras cr
                              WHERE cr.facultad_id = f.id) AS carreras_txt
                     FROM facultades f""")
        for fila in c.fetchall():
            texto_concatenado= f"{fila['facultad_nombre']} {fila['carreras_txt'] or ''} facultad universidad"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                resultados.append(("Universidad", f"Facultad: {fila['facultad_nombre']}", "Universidad",
                                    None, _icono_categoria("Universidad")))
        c.execute("""SELECT cr.nombre AS carrera_nombre, fa.nombre AS facultad_nombre
                     FROM carreras cr LEFT JOIN facultades fa ON fa.id = cr.facultad_id""")
        for fila in c.fetchall():
            texto_concatenado= f"{fila['carrera_nombre']} {fila['facultad_nombre'] or ''} carrera universidad"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                etiqueta= f"Carrera: {fila['carrera_nombre']}"
                if fila["facultad_nombre"]:
                    etiqueta += f" — {fila['facultad_nombre']}"
                resultados.append(("Universidad", etiqueta, "Universidad", None,
                                    _icono_categoria("Universidad")))

    #--- Politécnico: especialidades, empresas y pasantías ---
    if modulo_visible(rol, "Politécnico"):
        c.execute("SELECT nombre, codigo FROM especialidades")
        for fila in c.fetchall():
            texto_concatenado= f"{fila['nombre']} {fila['codigo'] or ''} especialidad área técnica politécnico"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                resultados.append(("Politécnico", f"Especialidad: {fila['nombre']}", "Politécnico",
                                    None, _icono_categoria("Politécnico")))
        c.execute("SELECT nombre, rubro, ubicacion FROM empresas_pasantia")
        for fila in c.fetchall():
            texto_concatenado= f"{fila['nombre']} {fila['rubro'] or ''} {fila['ubicacion'] or ''} empresa pasantía"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                etiqueta= f"Empresa: {fila['nombre']}"
                if fila["rubro"]:
                    etiqueta += f" ({fila['rubro']})"
                resultados.append(("Politécnico", etiqueta, "Politécnico",
                                    None, _icono_categoria("Politécnico")))
        #Pasantías: el resultado es el ESTUDIANTE en pasantía; un Profesor restringido solo ve las de sus secciones
        #(mismo RBAC del módulo).
        c.execute("""SELECT p.estado,
                            e.nombre AS est_nombre, e.apellidos AS est_apellidos,
                            e.seccion_id AS seccion_id, ep.nombre AS empresa_nombre
                     FROM pasantias p
                     LEFT JOIN estudiantes e ON e.id = p.estudiante_id
                     LEFT JOIN empresas_pasantia ep ON ep.id = p.empresa_id""")
        for fila in c.fetchall():
            if restringir_secciones and (secciones_permitidas_glob is None
                                          or fila["seccion_id"] not in secciones_permitidas_glob):
                continue
            nombre_est= f"{fila['est_nombre'] or ''} {fila['est_apellidos'] or ''}".strip()
            texto_concatenado= f"{nombre_est} {fila['empresa_nombre'] or ''} {fila['estado'] or ''} pasantía"
            if _coincidencia_fuzzy(texto, texto_concatenado):
                etiqueta= f"Pasantía: {nombre_est or '—'}"
                if fila["empresa_nombre"]:
                    etiqueta += f" — {fila['empresa_nombre']}"
                if fila["estado"]:
                    etiqueta += f" ({fila['estado']})"
                resultados.append(("Politécnico", etiqueta, "Politécnico",
                                    nombre_est or None, _icono_categoria("Politécnico")))

    conn.close()
    return resultados


#Ventana emergente de búsqueda global: escribe y pulsa Enter (o el botón)
#para ver resultados agrupados; doble clic navega al módulo correspondiente.
class DialogoBusquedaGlobal(QDialog):

    def __init__(self, main_window, texto_inicial=""):

        super().__init__(main_window)
        self.main_window= main_window
        self.setWindowTitle("Buscador Global")
        aplicar_icono_ventana(self, ICONO_BUSQUEDA)
        #Ancho por defecto más generoso que el mínimo: con 480px de ancho (el viejo tamaño por defecto) las etiquetas
        #largas de resultado (nombre + matrícula + grado/sección + área técnica/carrera, o un "profesor — especialidad"
        #largo) quedaban cortadas o cubrían todo el ancho aunque hubiera espacio de sobra en pantalla. El mínimo se
        #deja más bajo por si la ventana se redimensiona, pero el tamaño con el que ABRE es más ancho.
        self.setMinimumSize(480, 420)
        self.resize(760, 560)

        disposicion= QVBoxLayout(self)
        disposicion.setContentsMargins(18, 18, 18, 18)
        disposicion.setSpacing(10)

        fila= QHBoxLayout()
        self.in_texto= QLineEdit()
        limitar_campo_texto(self.in_texto, 300)
        self.in_texto.setPlaceholderText(
            "Buscar estudiante, profesor, personal, materia o un módulo (ej. \"5to C\", \"horario\")...")
        self.in_texto.setText(texto_inicial)
        self.in_texto.returnPressed.connect(self._buscar)
        fila.addWidget(self.in_texto)
        btn_buscar= QPushButton("Buscar")
        btn_buscar.setObjectName("BtnAccionAgregar")
        btn_buscar.clicked.connect(self._buscar)
        fila.addWidget(btn_buscar)
        disposicion.addLayout(fila)

        self.lbl_info= QLabel("Escribe al menos 1 carácter y presiona Enter.")
        self.lbl_info.setObjectName("DescModulo")
        disposicion.addWidget(self.lbl_info)

        self.lista= QListWidget()
        self.lista.itemDoubleClicked.connect(self._ir_a_resultado)
        disposicion.addWidget(self.lista, 1)

        lbl_ayuda= QLabel("Doble clic sobre un resultado para ir directamente a ese módulo.")
        lbl_ayuda.setObjectName("DescModulo")
        disposicion.addWidget(lbl_ayuda)

        if texto_inicial:
            self._buscar()

        #Ctrl+F como interruptor "cerrar": el atajo global de main.py (registrado en la ventana principal con
        #ApplicationShortcut) en la práctica NO llega hasta acá — mientras este diálogo está con
        #exec() corriendo, es SU propio QLineEdit el que tiene el foco, y
        #es a él a quien Qt le entrega primero el evento de teclado; el atajo de la ventana principal, de fondo y
        #bloqueada por la modalidad, se queda sin recibir el segundo Ctrl+F. Por eso el atajo para cerrar se registra
        #ACÁ, directamente sobre el propio
        #diálogo (WidgetWithChildrenShortcut, el valor por defecto de
        #QShortcut): así no depende de que el evento viaje hacia afuera, sino que se resuelve con el diálogo mismo, que
        #es quien realmente tiene el foco en ese momento.
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.close)

        centrar_y_al_frente(self, main_window)

    def _buscar(self):

        texto= self.in_texto.text().strip()
        self.lista.clear()
        if len(texto) < 1:
            self.lbl_info.setText("Escribe al menos 1 carácter y presiona Enter.")
            return
        resultados= buscar_global(self.main_window, texto)
        if not resultados:
            self.lbl_info.setText(f"Sin resultados para '{texto}'.")
            return
        self.lbl_info.setText(f"{len(resultados)} resultado(s) para '{texto}':")
        categoria_actual= None
        for categoria, etiqueta, modulo, texto_filtro, icono in resultados:
            if categoria != categoria_actual:
                encabezado= QListWidgetItem(categoria)
                encabezado.setFlags(Qt.ItemFlag.NoItemFlags)
                font= encabezado.font()
                font.setBold(True)
                encabezado.setFont(font)
                self.lista.addItem(encabezado)
                categoria_actual= categoria
            #El ícono ya llega como QIcon real -el mismo que usa la fila de ese módulo en la sidebar (PNG propio o, si no
            #tiene, el vectorial coherente de iconos_auto.py), solo que reducido a tamaño de emoji, ver icono_qicon_modulo
            #en iconos.py- nunca un emoji crudo metido dentro del texto ni un dibujo QPainter aparte que pudiera no
            #coincidir con lo que ya se ve en el menú lateral para ese mismo módulo.
            item= QListWidgetItem(etiqueta)
            if icono is not None and not icono.isNull():
                item.setIcon(icono)
            self.lista.setIconSize(QSize(18, 18))
            item.setData(MODULO_ROLE, modulo)
            item.setData(TEXTO_BUSCAR_ROLE, texto_filtro)
            self.lista.addItem(item)

    def _ir_a_resultado(self, item):

        modulo= item.data(MODULO_ROLE)
        texto_filtro= item.data(TEXTO_BUSCAR_ROLE)
        if not modulo:
            return
        if modulo not in self.main_window.modulos:
            return
        indice= self.main_window.modulos.index(modulo)
        self.main_window.nav_list.setCurrentRow(indice)
        pagina= self.main_window.stacked_widget.widget(indice)
        if pagina is not None and texto_filtro:
            #Cada módulo nombra su propia caja de búsqueda distinto (in_buscar en Estudiantes/Profesores/Personal,
            #in_busqueda en Calendario, in_buscar_tareas en el Catálogo de Banco de Tareas): se prueban los nombres
            #conocidos en vez de asumir uno solo, para que el resultado quede realmente filtrado al llegar, no solo
            #navegado al módulo correcto.
            for nombre_campo in ("in_buscar", "in_busqueda", "in_buscar_tareas", "buscador"):
                campo= getattr(pagina, nombre_campo, None)
                if campo is not None:
                    campo.setText(texto_filtro)
                    break
            #Banco de Tareas tiene dos pestañas (Catálogo/Entregas); la búsqueda global solo indexa el Catálogo, así que
            #hay que asegurarse de aterrizar ahí y no dejar al usuario viendo Entregas con el filtro aplicado en una
            #pestaña que no ve.
            if modulo == "Banco de Tareas" and hasattr(pagina, "tabs"):
                pagina.tabs.setCurrentIndex(0)
        self.accept()