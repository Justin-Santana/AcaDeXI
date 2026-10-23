# Cambios de esta mejora

## 1. Botones «Aceptar» sin icono
`iconos_auto.py`: la entrada `('aceptar', '✔')` sigue en la matriz (y `icono_para_texto("Aceptar")` la devuelve),
pero el rellenado automático de botones se salta los textos de `_TEXTOS_BOTON_SIN_ICONO`. Para exentar otro
botón (p. ej. «Confirmar», «Entendido») basta agregar su texto a esa tupla.

## 2. Deshacer y Rehacer genéricos (nuevo: `deshacer_rehacer.py`, `deshacer_rehacer_ui.py`)
Toda la lógica vive en esos dos archivos (datos y capa visual); no hay más archivos para esto.
- Botones «Deshacer» y «Rehacer» (un solo widget por tabla, se ocultan solos), Ctrl+Z para deshacer y
  Ctrl+Y / Ctrl+Shift+Z para rehacer, hasta 10 niveles por pantalla. Hacer una acción nueva vacía lo rehacible.
- Los avisos flotantes traen la acción contraria: tras eliminar -> «Deshacer»; tras deshacer -> «Rehacer».
- Captura las filas antes de un DELETE/UPDATE **incluyendo lo que se borra en cascada**; deshacer y rehacer
  son atómicos (si algo choca, no cambia nada). Al rehacer se vuelve a capturar el estado actual, así que un
  dato hijo añadido entre medias no se pierde al deshacer de nuevo.
- Pantallas: Estudiantes, Profesores y Psicología (migradas desde su deshacer de un solo nivel) y, nuevas,
  Materias (5 tablas), Materiales (+categorías), Personal, Observaciones, Banco de Tareas, Calendario,
  Calificaciones (calificaciones, competencias, indicadores), Calificaciones Técnicas (RA), Horario (clases
  locales), Politécnico (5), Universidad (3), Alarmas (recordatorios).
- **Corrección de un fallo previo:** el «Deshacer» de Estudiantes y Profesores solo reinsertaba la fila
  principal; asistencia, calificaciones, observaciones, etc. (borradas por `ON DELETE CASCADE`) se perdían.
- Los cuadros modales «Eliminado correctamente» de estas pantallas se sustituyeron por un aviso no bloqueante.
  Los tutoriales siguen recibiendo su evento de éxito.
- El editor de reportes conserva su propio deshacer/rehacer (es otro sistema, de edición de documentos).

## 3. Feedback (nuevo: `feedback.py`)
`mostrar_toast(widget, texto, tipo, accion=None)`: avisos apilables, con ✕, se pausan al pasar el cursor.
Añadido a: interruptores de Psicología/Materiales (Configuración), activar/desactivar usuario, foto de perfil.

## 4. Temas
- Paletas: acento, hover y texto secundario con contraste suficiente en Emerald, Sunset, Amber y Turquesa
  (claro) y retoques menores en Omega, Rose y los modos oscuros de Sunset/Amber.
- `main.py`: fuera de Colorful, «Eliminar» ahora es rojo y los botones neutros gris pizarra (antes todos
  usaban el acento y eran idénticos a «Guardar»).
- `contraste.py` + títulos de tarjeta (Estudiantes, Profesores, Personal) ajustados para leerse en oscuro.

## 5. Depuración (segunda pasada)
- Motor de deshacer/rehacer: un UPDATE que cambiaba la clave primaria "deshacía" sin restaurar nada y
  decía que había funcionado. Ahora esas ediciones se marcan como no deshacibles, y deshacer/rehacer una
  edición cuya fila ya no existe falla con aviso y sin cambiar nada (antes era un éxito silencioso).
- `BEGIN` ya no falla si la conexión traía una transacción abierta.
- Avisos flotantes: corregido el recorrido de la lista al descartar avisos duplicados.
- Auditoría: «Deshizo/Rehizo» se registra con el mismo nombre de módulo que el resto (p. ej. «Materias»).
- Etiquetas de Personal unificadas con las demás pantallas.
- Verificado con datos reales cada manejador de eliminación modificado (eliminar → deshacer → rehacer →
  deshacer), los avisos de Configuración y de la foto de perfil, y la carga de los 21 módulos con todas sus
  pestañas en varios temas (0 excepciones).

## 6. Revisión visual de Configuración y Reportes (temas)
Revisadas a ojo todas las pestañas de ambos módulos (y la ventana completa con su barra lateral) en
Colorful, Rose, Amber, Turquesa, Emerald, Slate, Omega, Sunset y Midnight, en claro y oscuro. Dos defectos
reales, ambos globales (afectaban a TODAS las pantallas, no solo a estas dos):
- **Barras de desplazamiento invisibles** en los 10 temas distintos de Colorful (contraste 1.1–1.8:1): el asa
  usaba colores de la barra lateral que solo Colorful define. Ahora 4.5–9.5:1. Colorful no cambia.
- **Botones deshabilitados ilegibles** (p. ej. «Anterior/Siguiente» de la paginación): texto de color de tema
  sobre fondo de color de tema (1.0–2.2:1). Ahora fondo neutro del tema y texto con >= 3:1. Colorful no cambia.
Sin cambios, a propósito: el editor de reportes tiene un tema propio (modo claro + acento azul por defecto,
con 16 acentos elegibles) y su hoja es blanca también en modo oscuro; es diseño del editor, no un defecto.
