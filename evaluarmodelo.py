"""
evaluar_modelo.py
=================
Calcula métricas de desempeño del sistema BioEntry
a partir de la base de datos de accesos (usuarios.db).

Cómo usarlo
-----------
1. Corre el sistema un rato con personas conocidas y desconocidas.
2. Luego ejecuta:  python evaluar_modelo.py

Métricas que genera
-------------------
- Accuracy, Precision, Recall, F1-score
- Matriz de confusión
- Distribución de confianza (aprobados vs denegados)
- Reporte completo por persona
"""

import sqlite3
import numpy as np
from datetime import datetime

# ============================================
# CONEXIÓN
# ============================================

conn   = sqlite3.connect("usuarios.db")
cursor = conn.cursor()

# ============================================
# OBTENER ACCESOS
# ============================================

cursor.execute("""
    SELECT nombre, resultado, confianza, timestamp
    FROM accesos
    ORDER BY timestamp ASC
""")

rows = cursor.fetchall()

if not rows:
    print("⚠️  No hay registros en la tabla 'accesos'.")
    print("   Corre el sistema primero para generar datos.")
    conn.close()
    exit()

print(f"\n{'═'*55}")
print(f"  BioEntry — Evaluación del Modelo")
print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
print(f"{'═'*55}\n")

# ============================================
# SEPARAR DATOS
# ============================================

nombres    = [r[0] for r in rows]
resultados = [r[1] for r in rows]   # 'aprobado' | 'denegado'
confianzas = [r[2] for r in rows]

# Para métricas: 1 = aprobado, 0 = denegado
y_pred = [1 if r == 'aprobado' else 0 for r in resultados]

# ============================================
# ESTADÍSTICAS BÁSICAS
# ============================================

total       = len(rows)
n_aprobados = y_pred.count(1)
n_denegados = y_pred.count(0)

print(f"  Total de accesos registrados : {total}")
print(f"  Aprobados                    : {n_aprobados}")
print(f"  Denegados                    : {n_denegados}\n")

# ============================================
# CONFIANZA PROMEDIO
# ============================================

conf_arr = np.array(confianzas)
conf_ok  = conf_arr[[i for i,r in enumerate(resultados) if r == 'aprobado']]
conf_no  = conf_arr[[i for i,r in enumerate(resultados) if r == 'denegado']]

print(f"  Confianza promedio — Aprobados : {conf_ok.mean():.1f}%  (σ={conf_ok.std():.1f})")
if len(conf_no):
    print(f"  Confianza promedio — Denegados : {conf_no.mean():.1f}%  (σ={conf_no.std():.1f})")

# ============================================
# MÉTRICAS POR PERSONA
# ============================================

print(f"\n  {'─'*50}")
print(f"  Detalle por persona\n")

personas = sorted(set(nombres))

for persona in personas:

    idx        = [i for i,n in enumerate(nombres) if n == persona]
    aprobaciones = sum(y_pred[i] for i in idx)
    denegaciones = len(idx) - aprobaciones
    conf_p       = np.mean([confianzas[i] for i in idx])

    print(f"  {persona}")
    print(f"    Apariciones : {len(idx)}")
    print(f"    Aprobados   : {aprobaciones}")
    print(f"    Denegados   : {denegaciones}")
    print(f"    Confianza μ : {conf_p:.1f}%")
    print()

# ============================================
# ESTIMACIÓN DE ACCURACY
# (asumiendo que 'Desconocido' = denegado correcto
#  y personas registradas = aprobado correcto)
# ============================================

cursor.execute("SELECT COUNT(*) FROM usuarios")
n_registrados = cursor.fetchone()[0]

# Verdaderos positivos: persona registrada aprobada
# Verdaderos negativos: 'Desconocido' denegado
# Falsos positivos: 'Desconocido' aprobado (raro pero posible)
# Falsos negativos: persona registrada denegada

vp = sum(1 for n,r in zip(nombres,resultados) if n != 'Desconocido' and r == 'aprobado')
vn = sum(1 for n,r in zip(nombres,resultados) if n == 'Desconocido' and r == 'denegado')
fp = sum(1 for n,r in zip(nombres,resultados) if n == 'Desconocido' and r == 'aprobado')
fn = sum(1 for n,r in zip(nombres,resultados) if n != 'Desconocido' and r == 'denegado')

accuracy  = (vp + vn) / total if total else 0
precision = vp / (vp + fp)    if (vp + fp) else 0
recall    = vp / (vp + fn)    if (vp + fn) else 0
f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0

print(f"  {'─'*50}")
print(f"  Métricas del modelo\n")
print(f"  Accuracy   : {accuracy*100:.1f}%")
print(f"  Precision  : {precision*100:.1f}%")
print(f"  Recall     : {recall*100:.1f}%")
print(f"  F1-Score   : {f1*100:.1f}%")

print(f"\n  Matriz de confusión (estimada)")
print(f"  ┌─────────────────┬────────┬────────┐")
print(f"  │                 │  Pred+ │  Pred- │")
print(f"  ├─────────────────┼────────┼────────┤")
print(f"  │  Real+ (conocido)│  {vp:5d} │  {fn:5d} │")
print(f"  │  Real- (descon.) │  {fp:5d} │  {vn:5d} │")
print(f"  └─────────────────┴────────┴────────┘")

print(f"\n{'═'*55}\n")

conn.close()