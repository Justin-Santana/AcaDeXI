"""Módulos técnicos vinculados (opcional) a un curso, y filtrado área + curso.
Corre en un subproceso con una base temporal para no tocar datos reales."""
import subprocess, sys, textwrap
from pathlib import Path

RAIZ= Path(__file__).resolve().parents[1]

SCRIPT= textwrap.dedent("""
    import sys
    from PySide6.QtWidgets import QApplication, QComboBox
    app= QApplication(sys.argv)
    from src.nucleo.bd import inicializar_bd, obtener_conexion
    inicializar_bd()
    conn= obtener_conexion(); c = conn.cursor()
    c.execute("INSERT INTO especialidades (nombre, codigo) VALUES ('Informática','IFC')"); a = c.lastrowid
    c.execute("INSERT INTO especialidades (nombre, codigo) VALUES ('Mecatrónica','MEC')"); m = c.lastrowid
    c.execute("INSERT INTO grados (nombre, nivel_educativo, ciclo_secundaria, orden) VALUES ('4to','Secundaria','Segundo Ciclo',4)"); g4 = c.lastrowid
    c.execute("INSERT INTO grados (nombre, nivel_educativo, ciclo_secundaria, orden) VALUES ('1ro','Secundaria','Primer Ciclo',1)"); g1 = c.lastrowid
    c.execute("INSERT INTO grados (nombre, nivel_educativo, ciclo_secundaria, orden) VALUES ('5to','Secundaria','Segundo Ciclo',5)"); g5 = c.lastrowid
    for nom, esp, g in [("P4", a, g4), ("Redes", a, None), ("R5", a, g5), ("Torno", m, None)]:
        c.execute("INSERT INTO materias (codigo,nombre,creditos,especialidad_id,estado,modelo_evaluacion,grado_id) "
                  "VALUES (?,?,?,?,?,?,?)", (nom, nom, 3, esp, 'Activa', 'Técnica (RA)', g))
    conn.commit(); conn.close()
    from src.interfaz.filtros_curso_seccion import (modulos_tecnicos_por_area_y_curso as mt,
        curso_admite_componente_tecnico, poblar_combo_curso_opcional)
    n= lambda L: sorted(x for _, x in L)
    assert n(mt(a, g4)) == ["P4", "Redes"], n(mt(a, g4))
    assert n(mt(a, g5)) == ["R5", "Redes"], n(mt(a, g5))
    assert n(mt(a, None)) == ["P4", "R5", "Redes"], n(mt(a, None))
    assert n(mt(m, g4)) == ["Torno"], n(mt(m, g4))
    assert curso_admite_componente_tecnico(g4) and not curso_admite_componente_tecnico(g1)
    cb= QComboBox(); poblar_combo_curso_opcional(cb, solo_con_componente_tecnico=True)
    assert [cb.itemText(i) for i in range(cb.count())] == ["— Sin curso específico —", "4to", "5to"]
    print("OK")
""")

def test_filtrado_modulos_por_area_y_curso(tmp_path):
    env= {"HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"}
    r= subprocess.run([sys.executable, "-c", SCRIPT], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr[-1500:]
