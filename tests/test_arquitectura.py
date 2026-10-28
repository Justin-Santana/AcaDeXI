#Reglas de la estructura: capas, ciclos y que todo módulo importe.
import ast, importlib, subprocess, sys
from pathlib import Path
import pytest

RAIZ= Path(__file__).resolve().parents[1]
PAQ= RAIZ / "src"
MODULOS= sorted(p for p in PAQ.rglob("*.py") if p.name != "__init__.py")
#Fallos conocidos de las fuentes (no de la estructura): ver docs/ARQUITECTURA.md
CONOCIDOS= {
    "src.interfaz.deshacer_rehacer_ui": "faltan los .py de nucleo.deshacer_rehacer / nucleo.feedback",
}
def nombre(p):

    return ".".join(p.relative_to(RAIZ).with_suffix("").parts)

def _imports_toplevel(p):

    out= set()
    for n in ast.parse(p.read_text(encoding="utf-8")).body:
        if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("src."):
            out.add(n.module if n.module.count(".") >= 2 else f"{n.module}.{n.names[0].name}")
    return {".".join(x.split(".")[:3]) for x in out}

def test_nucleo_no_depende_de_nadie():

    for p in (PAQ / "nucleo").glob("*.py"):
        malos= {m for m in _imports_toplevel(p) if not m.startswith("src.nucleo")}
        assert not malos, f"{p.name} importa fuera de nucleo: {malos}"

def test_sincronizacion_solo_depende_de_nucleo():

    for p in (PAQ / "sincronizacion").glob("*.py"):
        malos= {m for m in _imports_toplevel(p) if not m.startswith(("src.nucleo", "src.sincronizacion"))}
        assert not malos, f"{p.name}: {malos}"

def test_sin_ciclos_a_nivel_de_modulo():

    g= {nombre(p): _imports_toplevel(p) for p in MODULOS}
    estado= {}
    def dfs(u, pila):

        estado[u]= 1
        for w in g.get(u, ()):
            assert estado.get(w) != 1, f"ciclo: {' -> '.join(pila + [u, w])}"
            if w not in estado:
                dfs(w, pila + [u])
        estado[u]= 2
    for u in g:
        if u not in estado:
            dfs(u, [])

@pytest.mark.parametrize("p", MODULOS, ids=nombre)
def test_importa(p):

    m= nombre(p)
    if m in CONOCIDOS:
        pytest.xfail(CONOCIDOS[m])
    r= subprocess.run([sys.executable, "-c", f"import {m}"], cwd=RAIZ, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]

def test_fabricas_de_modulos_resuelven():

    v= importlib.import_module("src.interfaz.ventana_principal")
    for d in (v._FABRICAS_MODULOS, v._FABRICAS_MODULOS_SINGLE_TEACHER):
        for k, (mod, cls) in d.items():
            assert hasattr(importlib.import_module(mod), cls), f"{k}: {mod}.{cls}"
