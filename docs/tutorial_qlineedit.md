# QLineEdit explicado simple

Un QLineEdit es la cajita de una sola línea donde el usuario escribe: el nombre, el correo, la
contraseña, el monto. Nada más que eso, un renglón. Si necesitas varias líneas (observaciones,
descripciones) eso ya es QTextEdit.

Acá va cada parte y cada cosa que se le puede hacer, en corto.

---

## crearlo y ponerlo en la pantalla

```python
campo= QLineEdit()
campo.setPlaceholderText("Nombre del estudiante")
layout.addWidget(campo)
```

El widget no aparece solo: hay que meterlo en un layout (`QVBoxLayout`, `QFormLayout`...), si no
queda creado pero invisible.

---

## el texto gris de ayuda

`setPlaceholderText("...")` pone ese texto gris que se ve mientras el campo está vacío y
desaparece cuando el usuario escribe. No es un valor, no se guarda, no se lee con `text()`.

```python
self.input_usuario.setPlaceholderText("Nombre de usuario")
```

Ojo: no sirve como etiqueta. Si el dato importa, ponle un `QLabel` al lado; el placeholder se
borra apenas escriben y el usuario se queda sin saber qué campo es.

---

## leer lo que escribió y poner texto

```python
nombre= campo.text().strip()      # leer (strip para no guardar espacios de más)
campo.setText("Justin")           # poner un valor
campo.clear()                     # dejarlo vacío
```

`text()` devuelve siempre un `str`, aunque el campo esté vacío devuelve `""`, nunca `None`. Por
eso alcanza con `if not campo.text():` para saber si está vacío.

---

## que no se vea lo que escribe

`setEchoMode()` decide cómo se muestra el texto:

| modo | qué hace |
|---|---|
| `QLineEdit.EchoMode.Normal` | se ve todo (lo normal) |
| `QLineEdit.EchoMode.Password` | muestra puntos, para contraseñas |
| `QLineEdit.EchoMode.NoEcho` | no muestra nada, ni la cantidad de letras |
| `QLineEdit.EchoMode.PasswordEchoOnEdit` | muestra la letra mientras escribe y la tapa al salir |

```python
self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
```

El botón del ojito no cambia nada por dentro: solo alterna entre `Normal` y `Password`.

---

## tope de caracteres

`setMaxLength(300)` corta lo que se pueda escribir o pegar. En AcaDeXI no se llama directo, se
usa `limitar_campo_texto(campo, 300)` de `src/nucleo/limite_campos.py`, que además protege los
QTextEdit.

```python
limitar_campo_texto(self.input_usuario, 300)
```

---

## solo lectura

```python
campo.setReadOnly(True)     # se ve, se puede seleccionar y copiar, pero no editar
campo.setEnabled(False)     # se ve gris y ni siquiera se puede seleccionar
```

No es lo mismo: `readOnly` deja copiar el dato, `setEnabled(False)` no. Para un código que el
usuario no debe cambiar pero sí leer, va `setReadOnly`.

---

## avisar cuando el usuario hace algo

Son señales, se conectan con `.connect()`:

```python
campo.textChanged.connect(self.filtrar_tabla)      # cada tecla, también si cambia por código
campo.textEdited.connect(self.marcar_cambiado)     # solo si escribió el usuario
campo.editingFinished.connect(self.guardar)        # al salir del campo o apretar Enter
campo.returnPressed.connect(self.buscar)           # solo al apretar Enter
```

La diferencia que importa: `textChanged` también salta cuando TÚ cambias el texto con
`setText()`; `textEdited` no. Si al cargar un formulario se dispara la búsqueda sola, es por esto.

---

## que solo acepte números

```python
from PySide6.QtGui import QIntValidator, QDoubleValidator
campo.setValidator(QIntValidator(0, 999))              # entero entre 0 y 999
campo.setValidator(QDoubleValidator(0.0, 100.0, 2))    # decimal, 2 decimales
```

El validador no deja escribir la letra: si el usuario teclea "a" en un campo de nota, no pasa
nada. Ojo: con `QDoubleValidator` hay que tener en cuenta la coma y el punto según el idioma, así
que para notas conviene además revisar el valor al guardar.

---

## formato fijo con guiones

`setInputMask()` obliga a un formato mientras se escribe, por ejemplo una cédula o un teléfono:

```python
campo.setInputMask("000-0000000-0;_")     # el "_" es lo que se ve en los huecos
```

Es cómodo pero rígido: si la institución cambia el formato, hay que tocar el código. Para datos
que ya vienen con guiones de la base, mejor no poner máscara.

---

## alinear el texto

```python
campo.setAlignment(Qt.AlignmentFlag.AlignCenter)     # centrado
campo.setAlignment(Qt.AlignmentFlag.AlignRight)      # a la derecha, típico en montos
```

Sirve para columnas de dinero o números de lista, donde leer a la derecha cansa menos.

---

## la X para borrar

```python
campo.setClearButtonEnabled(True)
```

Pone una X al final del campo cuando hay texto. Es gratis y en campos de búsqueda se agradece.

---

## un icono adentro del campo

`addAction()` mete un icono o un botón dentro del mismo campo, a la izquierda o a la derecha:

```python
campo.addAction(icono_lupa, QLineEdit.ActionPosition.LeadingPosition)     # lupa a la izquierda
campo.addAction(accion_ojo, QLineEdit.ActionPosition.TrailingPosition)    # ojo a la derecha
```

Es lo que usa el login para el ojo de la contraseña: el botón vive dentro del QLineEdit, no al
lado.

---

## sugerencias mientras escribe

```python
from PySide6.QtWidgets import QCompleter
completer= QCompleter(lista_de_nombres, campo)
completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
campo.setCompleter(completer)
```

Va mostrando la lista de coincidencias abajo. Si la lista cambia con la base, hay que volver a
crear el completer, no alcanza con cambiar la lista original.

---

## cómo se ve

El QLineEdit se pinta con QSS, igual que un div en CSS:

```python
campo.setStyleSheet("""
    QLineEdit { border: 1px solid #CBD5E1; border-radius: 8px; padding: 8px 12px; }
    QLineEdit:focus { border: 2px solid #2563EB; }
""")
```

`:focus` es el estado cuando el usuario está escribiendo ahí. En AcaDeXI los estilos se aplican
por tema en `_apply_theme()`, no campo por campo, para que el modo claro y el oscuro cambien
juntos.

---

## que el cursor ya esté ahí al abrir

```python
campo.setFocus()
campo.selectAll()      # si ya trae un valor, lo deja seleccionado para sobrescribir
```

Un formulario que abre con el cursor puesto en el primer campo se siente mucho mejor que uno
donde hay que hacer clic primero.

---

## globito de ayuda

```python
campo.setToolTip("Solo letras, sin números")
```

Es el cartelito que sale al dejar el mouse encima. Para reglas que el usuario va a olvidar (mínimo
de caracteres, formato), es lo más barato que hay.

---

## lo que más se usa en AcaDeXI

- Login: `src/inicio/login.py` (usuario, contraseña, ojo para verla).
- Búsquedas y filtros: `src/interfaz/buscador_global.py`.
- Campos con tope: cualquier módulo que llame a `limitar_campo_texto(...)`.
- Formularios de alta y edición: `src/modulos/estudiantes.py`, `materias.py`, `profesores.py`.
