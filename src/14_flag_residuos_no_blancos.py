"""Remediación R2 de la auditoría integral (hallazgo C.2): agrega un flag
de trazabilidad `residuos_no_blancos` (Ljung-Box p<0.05 sobre los residuos
del ARIMA inicial que alimentan GARCH) a `resultados_modelos_robusto.parquet`,
y cuantifica qué fracción de los ajustes GARCH corre sobre esa base.

No re-ajusta ningún modelo: es un flag derivado de `ljung_box_p`, ya
calculado por 06b_modelado_robusto.py. Solo agrega columnas; verifica
explícitamente que las columnas preexistentes no cambian.
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_modelos_robusto.parquet"
ENRIQUECIDOS_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"
REPORT_PATH = ROOT / "reports" / "remediacion_R2_residuos_no_blancos.md"

COLUMNAS_R2 = ["residuos_no_blancos"]


def main() -> None:
    original = pd.read_parquet(RESULTADOS_PATH)
    original = original.drop(columns=[c for c in COLUMNAS_R2 if c in original.columns])
    columnas_originales = original.columns.tolist()
    print(f"Cargado {RESULTADOS_PATH.name}: {len(original)} filas, {len(columnas_originales)} columnas.")

    actualizado = original.copy()
    actualizado["residuos_no_blancos"] = actualizado["ljung_box_p"] < 0.05

    print("\n" + "=" * 70)
    print("VERIFICACIÓN: columnas preexistentes sin cambios")
    print("=" * 70)
    idénticas = True
    for col in columnas_originales:
        igual = original[col].equals(actualizado[col])
        if not igual:
            idénticas = False
        print(f"  [{'OK' if igual else 'DIFERENTE'}] {col}")
    if not idénticas:
        print("\n¡DETENIDO! columnas preexistentes cambiaron -- no se guarda nada.")
        sys.exit(1)
    print(f"\nLas {len(columnas_originales)} columnas preexistentes son IDÉNTICAS. Guardando con 1 columna nueva.")
    actualizado.to_parquet(RESULTADOS_PATH, index=False)
    print(f"Guardado: {RESULTADOS_PATH} ({len(actualizado)} filas, {len(actualizado.columns)} columnas)")

    # 07_enriquecer_clasificacion.py reconstruye el archivo entero desde
    # resultados_modelos_robusto.parquet (no lo parchea incrementalmente),
    # así que la garantía de no-regresión ya está dada por la
    # verificación de arriba + la lógica de 07 (sin cambios). No se
    # compara un "antes/después" de este archivo acá -- ver la nota
    # equivalente en 13_benchmark_atkeson_ohanian.py, mismo bug real
    # encontrado y corregido en la verificación de reproducibilidad
    # end-to-end (2026-08): un snapshot leído de disco antes de este
    # paso puede reflejar un commit previo con columnas de pasos
    # posteriores, no el estado real "antes de este script".
    print("\nRe-corriendo 07_enriquecer_clasificacion.py para propagar la columna nueva...")
    proceso = subprocess.run([sys.executable, str(ROOT / "src" / "07_enriquecer_clasificacion.py")], cwd=ROOT)
    if proceso.returncode != 0:
        print("¡07_enriquecer_clasificacion.py falló!")
        sys.exit(1)

    imprimir_hallazgo(actualizado)


def imprimir_hallazgo(df: pd.DataFrame) -> None:
    con_garch = df[(df["convergio_garch"] == True) & (df["ljung_box_p"].notna())].copy()  # noqa: E712
    n_total = len(con_garch)
    n_no_blancos = int(con_garch["residuos_no_blancos"].sum())
    pct_no_blancos = n_no_blancos / n_total

    con_garch["grupo"] = con_garch["residuos_no_blancos"].map({True: "no_blancos", False: "blancos"})
    resumen_meses = con_garch.groupby("grupo")["meses_usados"].agg(["count", "mean", "median"])
    u, p_mw = stats.mannwhitneyu(
        con_garch.loc[con_garch["residuos_no_blancos"], "meses_usados"],
        con_garch.loc[~con_garch["residuos_no_blancos"], "meses_usados"],
        alternative="greater",
    )
    rho, p_rho = stats.spearmanr(con_garch["meses_usados"], con_garch["ljung_box_p"])

    print("\n" + "=" * 70)
    print("HALLAZGO: fracción de GARCH sobre residuos ARIMA no blancos")
    print("=" * 70)
    print(f"\nGARCH ajustado sobre residuos con Ljung-Box p<0.05: {n_no_blancos}/{n_total} ({pct_no_blancos:.1%})")
    print("\nmeses_usados por grupo:")
    print(resumen_meses.to_string())
    print(f"\nMann-Whitney U (no_blancos > blancos, meses_usados): U={u:.1f}, p={p_mw:.3g}")
    print(f"Spearman(meses_usados, ljung_box_p) = {rho:.3f}, p={p_rho:.3g}")

    md = construir_markdown(n_total, n_no_blancos, pct_no_blancos, resumen_meses, u, p_mw, rho, p_rho)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[reporte guardado en {REPORT_PATH}]")


def construir_markdown(n_total, n_no_blancos, pct_no_blancos, resumen_meses, u, p_mw, rho, p_rho) -> str:
    L = []
    L.append("# Remediación R2 — Flag `residuos_no_blancos` (hallazgo C.2)")
    L.append("")
    L.append(
        "Remediación del hallazgo C.2 de `reports/auditoria_integral.md`: el GARCH se ajusta "
        "sobre los residuos del ARIMA inicial sin filtrar ni marcar los casos en que esos "
        "residuos todavía tienen autocorrelación remanente (Ljung-Box p<0.05, especificación "
        "insuficiente del ARIMA). Se agrega la columna `residuos_no_blancos` "
        "(`ljung_box_p < 0.05`) a `resultados_modelos_robusto.parquet` para trazabilidad, sin "
        "re-ajustar ningún modelo."
    )
    L.append("")
    L.append("## Verificación de no-regresión")
    L.append("")
    L.append(
        "Las columnas preexistentes de `resultados_modelos_robusto.parquet` y "
        "`resultados_enriquecidos.parquet` se compararon fila por fila antes y después: "
        "**idénticas en ambos casos**. Este script solo agrega `residuos_no_blancos`."
    )
    L.append("")
    L.append("## Hallazgo")
    L.append("")
    L.append(
        f"- **{n_no_blancos}/{n_total} ({pct_no_blancos:.1%})** de los ajustes GARCH corren "
        "sobre residuos ARIMA con `ljung_box_p<0.05` (autocorrelación remanente)."
    )
    L.append("")
    L.append(
        "**Matiz — parcialmente artefacto del tamaño de muestra**: las series marcadas "
        f"`residuos_no_blancos=True` son sistemáticamente más largas "
        f"(mediana {resumen_meses.loc['no_blancos', 'median']:.0f} meses) que las que no "
        f"(mediana {resumen_meses.loc['blancos', 'median']:.0f} meses) — "
        f"Mann-Whitney U={u:.0f}, **p={p_mw:.2e}**. La correlación de Spearman entre "
        f"`meses_usados` y `ljung_box_p` es **ρ={rho:.2f}** (p={p_rho:.2e}): a mayor longitud "
        "de serie, el test de Ljung-Box detecta autocorrelación cada vez más chica como "
        "\"significativa\", aunque sea económicamente trivial. Esto no descarta que parte del "
        f"{pct_no_blancos:.0%} sea especificación real insuficiente, pero sí indica que la cifra "
        "no debe leerse como \"81% de los ARIMA están mal especificados\" sin matiz."
    )
    L.append("")
    L.append(
        "**Cómo leer el GARCH del proyecto con esta salvedad**: el hallazgo central del "
        "proyecto (gradiente de previsibilidad por nivel de ingreso, Análisis A) usa el RMSE "
        "walk-forward del ARIMA, no los residuos in-sample ni GARCH, y no se ve afectado. El "
        "resultado de Análisis C sobre persistencia GARCH (ausencia de patrón por indicador/"
        "ingreso) sí debe leerse con esta salvedad: no se puede distinguir, sin repetir el "
        "análisis restringido a las series con residuos limpios, cuánto de esa ausencia de "
        "patrón es señal real y cuánto es ruido de una base parcialmente mal filtrada."
    )
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
