"""Pipeline maestro: reproduce de punta a punta todos los resultados
finales del proyecto, en orden.

No incluye los scripts de diagnóstico (src/fase1_*.py .. fase5_*.py,
src/02_calidad_series.py, src/06_modelado_arima_garch.py): esos ya
cumplieron su función exploratoria durante el desarrollo y sus hallazgos
quedaron documentados en reports/faseN_*.md — no hace falta
re-ejecutarlos para reproducir los resultados finales. Ver README.md,
sección "Estructura del repo", para el detalle de qué es pipeline y qué
es diagnóstico.

Uso: python run_pipeline.py
Tiempo estimado: ~20-25 minutos (el paso de modelado es el más lento).
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

PASOS = [
    ("01_descarga_datos.py", "Descarga el Excel del Banco Mundial a data/raw/ (si no existe ya)"),
    ("05_etl_corregido.py", "ETL corregido: índice/tasa por Indicator Type, ceros de Venezuela, doble transformación, flags"),
    ("06b_modelado_robusto.py", "Modelado ARIMA+GARCH con walk-forward + baseline naive (el más lento, ~10-15 min)"),
    ("13_benchmark_atkeson_ohanian.py", "Remediación C.5: agrega benchmark Atkeson-Ohanian (media móvil 12m) y re-propaga a enriquecidos"),
    ("14_flag_residuos_no_blancos.py", "Remediación C.2: agrega flag residuos_no_blancos (Ljung-Box p<0.05) y re-propaga a enriquecidos"),
    ("07_enriquecer_clasificacion.py", "Enriquecimiento con región/nivel de ingreso del Banco Mundial"),
    ("08_analisis_previsibilidad.py", "Análisis A: previsibilidad (ranking, gradiente de ingreso, hiperinflación)"),
    ("09_analisis_estructura.py", "Análisis B: estructura (headline vs. componentes)"),
    ("10_analisis_volatilidad.py", "Análisis C: dinámica de volatilidad (GARCH)"),
    ("11_auditoria_metodologica.py", "Auditoría: leakage de orden ARIMA + longitud como confusor"),
    ("12_robustez_multivariado.py", "Robustez: intervalos de confianza bootstrap + modelo multivariado"),
]


def main() -> None:
    t0_total = time.time()
    resultados = []

    for script, descripcion in PASOS:
        ruta = ROOT / "src" / script
        print(f"\n{'=' * 70}\n[{script}] {descripcion}\n{'=' * 70}")
        t0 = time.time()
        proceso = subprocess.run([PYTHON, str(ruta)], cwd=ROOT)
        dt = time.time() - t0
        ok = proceso.returncode == 0
        resultados.append((script, ok, dt))
        print(f"\n[{script}] {'OK' if ok else 'FALLÓ'} en {dt:.1f}s")
        if not ok:
            print(f"\nEl pipeline se detiene: {script} terminó con código {proceso.returncode}.")
            break

    dt_total = time.time() - t0_total
    print(f"\n{'=' * 70}\nRESUMEN DEL PIPELINE\n{'=' * 70}")
    for script, ok, dt in resultados:
        marca = "OK  " if ok else "FALLO"
        print(f"  [{marca}] {script} ({dt:.1f}s)")
    print(f"\nTiempo total: {dt_total:.1f}s ({dt_total / 60:.1f} min)")

    completo = len(resultados) == len(PASOS) and all(ok for _, ok, _ in resultados)
    if completo:
        print("\nPipeline completo: todos los pasos terminaron OK.")
    else:
        print("\nPipeline incompleto — revisar el paso que falló arriba.")
        sys.exit(1)


if __name__ == "__main__":
    main()
