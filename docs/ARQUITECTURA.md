# Arquitectura

## Capas
| Paquete | Contenido | Puede importar de |
|---|---|---|
| `nucleo` | bd, permisos, iconos, atajos, rutas, edición, utilidades | nada (solo `nucleo`) |
| `sincronizacion` | sincronización y backends | `nucleo` |
| `boletines`, `servicios`, `inicio`, `interfaz`, `modulos` | UI y lógica de negocio | capas anteriores y entre sí, **sin ciclos a nivel de módulo** |

`tests/test_arquitectura.py` hace cumplir esto. Los imports perezosos (dentro de funciones) son la
forma aceptada de romper ciclos puntuales (p. ej. `bd` → `boletin_minerd`, `paginacion` → `configuracion`).

## Rutas y recursos (`src/nucleo/rutas.py`)
- `get_app_root_dir()`: carpeta del `.exe` (empaquetado) o raíz del repo. Aquí se busca `AcaDeXI_Docentes_Setup.exe`.
- `get_iconos_dir()` / `buscar_dato(nombre)`: recursos empaquetados (`_internal/`) o `src/assets/`, `docs/` y `servidor/` en desarrollo.
- Nunca uses `__file__` para localizar recursos: empaquetado apunta a un sitio distinto.

## Ediciones
`src/nucleo/edicion.py` decide la edición (`full`, `docentes`, `single_teacher`, `side_stepper`).
Las fábricas de módulos de `ventana_principal.py` usan nombres cualificados (`src.modulos.X`).

## Empaquetado
Se compila con auto-py-to-exe usando `configacadexi.json` (raíz; ignorado por git porque lleva rutas absolutas).
El bundle conserva su diseño (`_internal/iconos`, documentos sueltos en `_internal/`), por lo que los `.iss` no cambian.
Los `.iss` consumen el **resultado compilado** (`AcaDeXI.exe` + `_internal\`): cópialos junto al exe como antes.

## Problemas conocidos de las fuentes (no de la estructura)
Marcados `xfail` en los tests:
- `boletines/boletin_clasico.py` importa `mostrar_resumen_asistencia_boletin` (no existe en `boletin_minerd.py`).
- `inicio/wizard_visual.py` importa `PanelAparienciaWizard` (no existe en `configuracion.py`).
- `interfaz/deshacer_rehacer_ui.py` necesita `nucleo/deshacer_rehacer.py` y `nucleo/feedback.py` (faltan sus `.py`).

## Materias y módulos técnicos por curso (opcional)
- `materias.grado_id` es un curso/grado **opcional**. `NULL` = sin curso específico: el módulo o materia
  está disponible para cualquier curso de su área.
- Los módulos técnicos solo se vinculan a cursos de Secundaria - Segundo Ciclo
  (`curso_admite_componente_tecnico`, basado en `puede_tener_componente_tecnico`).
- Filtrado compartido: `modulos_tecnicos_por_area_y_curso(area_id, grado_id)` en
  `src/interfaz/filtros_curso_seccion.py`. Toda ventana que filtre módulos por área y curso debe usarlo,
  no repetir la consulta.
- Asignación técnica: un módulo vinculado a un curso no puede asignarse a una sección de otro curso.

## Altura de tablas
- Ninguna tabla lleva tope fijo de altura (`setMaximumHeight`/`setFixedHeight`). Solo se fija un
  `setMinimumHeight` de usabilidad. Toda tabla se añade a su layout con factor de estirado (`addWidget(tabla, 1)`).
- Lo fuerzan `tests/test_tablas_altura.py`. El editor de reportes queda fuera, por diseño.

## Secuencias didácticas
- Datos y exportación Word sin Qt en `src/nucleo/secuencias.py`; pantalla en `src/modulos/secuencias.py`
  (`ModuloSecuenciasDidacticas`, sección DOCENCIA; roles Administrador, Director, Coordinador y Profesor).
- Tablas: `secuencias_didacticas`, `secuencia_sesiones`, `secuencia_competencia`, `secuencia_indicador`,
  `secuencia_tarea`. Reutiliza `competencias_especificas` / `indicadores_logro` y vincula `tareas`.
- Borrar una materia, grado o profesor no borra la secuencia (`SET NULL`); borrar la secuencia no toca tareas ni competencias.
- Pendiente: edición Single Teacher (usa `bd_single_teacher.py`, no `bd.py`).
