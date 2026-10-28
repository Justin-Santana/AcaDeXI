#Regla: ninguna tabla de la app (salvo el editor de reportes) puede tener un tope
#de altura fijo, y toda tabla que se añade a un layout debe poder estirarse.
import re
from pathlib import Path

RAIZ= Path(__file__).resolve().parents[1]
ARCHIVOS= [p for p in (RAIZ / "src").rglob("*.py")
            if p.name not in ("reportes_editor.py", "paginacion.py")]

def test_sin_topes_de_altura_en_tablas():

    malos= []
    for p in ARCHIVOS:
        for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(tabla\w*|tbl\w*)\.setMaximumHeight\(|\b(tabla\w*|tbl\w*)\.setFixedHeight\(", linea):
                malos.append(f"{p.relative_to(RAIZ)}:{i}")
    assert not malos, "topes de altura en tablas: " + ", ".join(malos)

def test_tablas_se_añaden_con_estiramiento():

    malos= []
    for p in ARCHIVOS:
        for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"addWidget\((self\.)?(tabla|tbl)\w*\)", linea):
                malos.append(f"{p.relative_to(RAIZ)}:{i}")
    assert not malos, "tablas sin factor de estiramiento: " + ", ".join(malos)
