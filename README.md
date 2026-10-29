# AcaDeXI

**Sistema de Gestión Escolar Integral**

AcaDeXI es una aplicación de escritorio diseñada para optimizar la administración académica y administrativa de instituciones educativas. Ofrece una solución completa y modular, adaptable a diferentes tipos de centros (escuelas, politécnicos, universidades), con un enfoque en la facilidad de uso, la seguridad de los datos y la eficiencia en los procesos.

## Características Principales

- **Gestión Académica**: Estudiantes, profesores, personal, materias, secciones, grados.
- **Asistencia**: Registro diario, resúmenes por sección y alertas de inasistencia.
- **Calificaciones**: Notas por competencias, boletines oficiales (formato MINERD), evaluación técnica con RA.
- **Horarios**: Vista semanal interactiva, gestión de aulas y asignación de clases.
- **Banco de Tareas**: Creación de tareas, seguimiento de entregas, calificación por competencias.
- **Secuencias Didácticas**: Planificación de unidades de aprendizaje con el esquema del MINERD (situación de aprendizaje, competencias, indicadores de logro, contenidos y sesiones con evidencias e instrumentos), ligada a las competencias y tareas de la app y exportable a Word.
- **Calendario**: Eventos institucionales, recordatorios y alarmas con notificaciones.
- **Observaciones**: Registro de incidencias, seguimiento conductual y académico.
- **Psicología**: Módulo confidencial para el área de psicología (acceso restringido).
- **Materiales**: Inventario, préstamos y control de recursos (libros, equipos, herramientas).
- **Reportes**: Generación de informes estadísticos y listados exportables a PDF/CSV.
- **Sincronización**: Con Google Drive, Dropbox, OneDrive o servidor institucional propio.
- **Copias de Seguridad**: Automáticas y manuales, con historial de respaldos.
- **Roles y Permisos**: Control de acceso basado en roles (RBAC) con flexibilidad para personalizaciones.
- **Temas**: Modo claro/oscuro, personalización de colores y accesibilidad visual.
- **Multidioma**: Soporte para español, inglés y portugués en la interfaz de usuario.

## Requisitos del Sistema

- **Sistema Operativo**: Windows 7 o superior, macOS, Linux (distribuciones compatibles con PySide6).
- **Procesador**: 1 GHz o superior.
- **Memoria RAM**: 4 GB recomendados.
- **Espacio en disco**: 500 MB disponibles (más espacio para la base de datos SQLite).
- **Conexión a Internet**: Opcional (requerida para sincronización en la nube y actualizaciones).

## Instalación

### Usuarios Finales (Ejecutable)

1. Descargue el instalador o el archivo comprimido de la última versión estable.
2. Ejecute el instalador (Windows) o descomprima los archivos en la carpeta de su elección.
3. Siga las instrucciones en pantalla. La primera ejecución creará la base de datos y abrirá el asistente de configuración.
4. Si ya dispone de una base de datos (`src.db`), colóquela en la carpeta de datos de la aplicación (en Windows: `%APPDATA%\AcaDeXI`; en Linux: `~/.local/share/AcaDeXI`; en macOS: `~/Library/Application Support/AcaDeXI`).

### Desarrollo

1. Clonar el repositorio: `git clone https://github.com/tu-usuario/acadexi.git`
2. Crear un entorno virtual: `python -m venv venv`
3. Activar el entorno:
   - Windows: `venv\Scripts\activate`
   - Linux/macOS: `source venv/bin/activate`
4. Instalar dependencias: `pip install -r requirements.txt`
5. Ejecutar: `python main.py`

## Estructura del proyecto

```
AcaDeXI/
├── main.py                 Lanzador (llama a src.interfaz.ventana_principal.main)
├── src/
│   ├── nucleo/             BD, permisos, iconos, rutas, edición, utilidades (no depende de nadie)
│   ├── sincronizacion/     Backends y asistente de sincronización
│   ├── boletines/          Boletines PDF (MINERD, clásico, técnico, primaria)
│   ├── servicios/          Alarmas y generación de instaladores
│   ├── interfaz/           Ventana principal, configuración, dashboard, widgets compartidos
│   ├── inicio/             Login, bienvenida, asistente inicial, tutoriales
│   ├── modulos/            Pantallas funcionales (estudiantes, calificaciones, horario...)
│   └── assets/             iconos/, términos y licencias de iconos
├── servidor/               Servidor institucional (script independiente + sus requisitos)
├── empaquetado/            instaladores Inno Setup (*.iss)
├── version_info.txt        datos de versión del .exe (lo lee PyInstaller)
├── docs/                   Arquitectura, cambios, guías y cartas (PDF)
├── tools/                  Scripts auxiliares de desarrollo
└── tests/                  pytest (`python -m pytest tests`)
```

Más detalle en `docs/ARQUITECTURA.md`.

## Dependencias

Las dependencias se listan en `requirements.txt`. Las principales son:

- **PySide6** (LGPL v3): Interfaz gráfica, multimedia y red.
- **ReportLab** (BSD): Generación de documentos PDF.
- **OpenPyXL** (MIT): Manipulación de archivos Excel.
- **argon2-cffi** (MIT): Hashing de contraseñas.
- **Pillow** (HPND): Procesamiento de imágenes.
- **google-auth-oauthlib**, **google-api-python-client** (Apache 2.0): Integración con Google Drive.
- **dropbox** (Apache 2.0/MIT): Integración con Dropbox.
- **msal** (MIT): Autenticación Microsoft.
- **FastAPI**, **Uvicorn** (MIT): Servidor embebido para sincronización directa.
- **cryptography** (Apache 2.0/BSD): Cifrado y seguridad.

## Documentación

El manual de usuario detallado se encuentra en el archivo `MANUAL_USUARIO.pdf` incluido en la distribución.

## Licencia

AcaDeXI es propiedad de **AcaDeXI – Software Educativo**. Su uso está sujeto a los términos del **Contrato de Licencia de Usuario Final (EULA)** que se incluye con la distribución. El código fuente se proporciona únicamente con fines de estudio y bajo autorización expresa.

Este producto incluye bibliotecas de código abierto con sus propias licencias. Los detalles se encuentran en el archivo `LICENSE.txt` y en la documentación del software.

## Agradecimientos

Agradecemos a la comunidad de Python y a los desarrolladores de las bibliotecas de código abierto que hacen posible este proyecto.

## Contacto

Para soporte técnico, consultas o sugerencias, contáctenos en: `soporte@acadexi.com`

---

© AcaDeXI – Software Educativo. Todos los derechos reservados.