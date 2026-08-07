"""Análisis B — Estructura de la inflación (headline vs. componentes).

Compara previsibilidad (RMSE walk-forward) y persistencia de volatilidad
(GARCH alpha+beta) entre los 5 indicadores (hcpi, ecpi, fcpi, ccpi, ppi).
Las comparaciones entre indicadores del MISMO país se hacen con tests
pareados (Wilcoxon signed-rank, Friedman) porque no son observaciones
independientes entre sí. Todas las conclusiones se generan condicionadas
al p-valor real de cada test, nunca como texto fijo (lección del Análisis
A).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"
REPORT_PATH = ROOT / "reports" / "analisis_B_estructura.md"
FIG_DIR = ROOT / "reports" / "figures"

INDICADORES = ["hcpi", "ecpi", "fcpi", "ccpi", "ppi"]
NOMBRES = {
    "hcpi": "Headline CPI",
    "ecpi": "Energy CPI",
    "fcpi": "Food CPI",
    "ccpi": "Core CPI",
    "ppi": "PPI",
}
ALPHA = 0.05


def cargar_datos():
    df = pd.read_parquet(RESULTADOS_PATH)
    validos = df[(df["convergio_arima"]) & (df["rmse_arima_walkforward"].notna())].copy()
    return df, validos


def test_pareado(pivote: pd.DataFrame, ind_a: str, ind_b: str):
    sub = pivote[[ind_a, ind_b]].dropna()
    if len(sub) < 5:
        return {"n": len(sub), "suficiente": False}
    stat, p = stats.wilcoxon(sub[ind_a], sub[ind_b])
    return {
        "n": len(sub),
        "suficiente": True,
        "mediana_a": sub[ind_a].median(),
        "mediana_b": sub[ind_b].median(),
        "stat": stat,
        "p": p,
        "gana_a": sub[ind_a].median() < sub[ind_b].median(),
    }


def texto_test_pareado(nombre_a, nombre_b, resultado, contexto=""):
    if not resultado["suficiente"]:
        return f"No hay suficientes países con ambos indicadores (n={resultado['n']}) para un test pareado confiable."
    direccion = "más predecible" if resultado["gana_a"] else "menos predecible"
    if resultado["p"] < ALPHA:
        return (
            f"Wilcoxon signed-rank (n={resultado['n']} países): estadístico={resultado['stat']:.1f}, "
            f"p={resultado['p']:.2e}. **Diferencia significativa**: {nombre_a} (mediana RMSE="
            f"{resultado['mediana_a']:.3f}) es sistemáticamente {direccion} que {nombre_b} "
            f"(mediana RMSE={resultado['mediana_b']:.3f}).{contexto}"
        )
    return (
        f"Wilcoxon signed-rank (n={resultado['n']} países): estadístico={resultado['stat']:.1f}, "
        f"p={resultado['p']:.2e}. **No hay diferencia significativa** entre {nombre_a} "
        f"(mediana RMSE={resultado['mediana_a']:.3f}) y {nombre_b} (mediana RMSE="
        f"{resultado['mediana_b']:.3f}) — con este n, no se puede confirmar que uno sea "
        f"sistemáticamente más predecible que el otro.{contexto}"
    )


# ---------- 1-2. RMSE por indicador ----------
def analizar_rmse_por_indicador(validos: pd.DataFrame):
    resumen = validos.groupby("indicador")["rmse_arima_walkforward"].agg(["size", "median", "mean"]).reindex(INDICADORES)

    grupos = [validos.loc[validos["indicador"] == i, "rmse_arima_walkforward"].dropna() for i in INDICADORES]
    h_stat, p_kw = stats.kruskal(*grupos)

    fig, ax = plt.subplots(figsize=(8, 5))
    datos = [validos.loc[validos["indicador"] == i, "rmse_arima_walkforward"].dropna() for i in INDICADORES]
    ax.boxplot(datos, tick_labels=[NOMBRES[i] for i in INDICADORES])
    ax.set_yscale("log")
    ax.set_ylim(bottom=0.05)  # Malta ecpi tiene RMSE~0 (índice congelado, ver nota en el texto)
    ax.set_ylabel("RMSE walk-forward (log-diff)")
    ax.set_title("RMSE por indicador (los 5)")
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisB_boxplot_rmse_indicador.png", dpi=120)
    plt.close(fig)

    return resumen, h_stat, p_kw


# ---------- 3. Persistencia GARCH por indicador ----------
def analizar_persistencia_por_indicador(df: pd.DataFrame):
    conv = df[df["convergio_garch"]].copy()
    resumen = conv.groupby("indicador")["persistencia"].agg(["size", "median", "mean"]).reindex(INDICADORES)

    grupos = [conv.loc[conv["indicador"] == i, "persistencia"].dropna() for i in INDICADORES]
    grupos_validos = [g for g in grupos if len(g) >= 3]
    if len(grupos_validos) >= 2:
        h_stat, p_kw = stats.kruskal(*grupos_validos)
    else:
        h_stat, p_kw = np.nan, np.nan

    fig, ax = plt.subplots(figsize=(8, 5))
    datos = [conv.loc[conv["indicador"] == i, "persistencia"].dropna() for i in INDICADORES]
    ax.boxplot(datos, tick_labels=[NOMBRES[i] for i in INDICADORES])
    ax.axhline(1.0, color="crimson", linestyle="--", linewidth=1, label="persistencia=1 (IGARCH)")
    ax.set_ylabel("Persistencia GARCH (alpha+beta)")
    ax.set_title("Persistencia de volatilidad por indicador")
    ax.legend(fontsize=8)
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisB_boxplot_persistencia_indicador.png", dpi=120)
    plt.close(fig)

    return resumen, h_stat, p_kw


# ---------- 4. Países con los 5 indicadores ----------
def analizar_paises_completos(validos: pd.DataFrame):
    pivote = validos.pivot_table(index="codigo_pais", columns="indicador", values="rmse_arima_walkforward")
    completos = pivote.dropna(subset=INDICADORES)

    if len(completos) < 5:
        return completos, None, np.nan, np.nan

    rangos = completos[INDICADORES].rank(axis=1, method="average")
    rango_promedio = rangos.mean().reindex(INDICADORES)

    stat, p = stats.friedmanchisquare(*[completos[i] for i in INDICADORES])

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([NOMBRES[i] for i in INDICADORES], rango_promedio.values, color="steelblue")
    ax.set_ylabel("Rango promedio de previsibilidad\n(1=más predecible, 5=menos, dentro de cada país)")
    ax.set_title(f"Orden de previsibilidad por país (n={len(completos)} países con los 5 indicadores)")
    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisB_rango_promedio.png", dpi=120)
    plt.close(fig)

    return completos, rango_promedio, stat, p


def construir_markdown(resumen_rmse, h_kw_rmse, p_kw_rmse, test_ccpi_hcpi, resumen_pers, h_kw_pers, p_kw_pers,
                        test_ccpi_ecpi, test_ccpi_fcpi, completos, rango_promedio, friedman_stat, friedman_p):
    L = []
    L.append("# Análisis B — Estructura de la inflación (headline vs. componentes)")
    L.append("")
    L.append(
        "Informe generado por `src/09_analisis_estructura.py` sobre "
        "`data/processed/resultados_enriquecidos.parquet`. Las comparaciones entre "
        "indicadores del mismo país usan tests **pareados** (Wilcoxon signed-rank, "
        "Friedman) porque hcpi/ccpi/ecpi/fcpi/ppi del mismo país no son observaciones "
        "independientes entre sí."
    )
    L.append("")

    # 1
    L.append("## 1. Comparación de previsibilidad entre los 5 indicadores")
    L.append("")
    L.append("RMSE walk-forward por indicador (todas las series aptas, no pareado):")
    L.append("")
    L.append("| Indicador | N series | RMSE mediano | RMSE medio |")
    L.append("|---|---|---|---|")
    for ind in INDICADORES:
        r = resumen_rmse.loc[ind]
        L.append(f"| {NOMBRES[ind]} ({ind}) | {int(r['size'])} | {r['median']:.3f} | {r['mean']:.3f} |")
    L.append("")
    L.append(
        f"Figura: `reports/figures/analisisB_boxplot_rmse_indicador.png` (eje y recortado en "
        "0.05 para que sea legible — Malta/ecpi tiene RMSE≈0 porque su índice de energía "
        "estuvo literalmente congelado en el mismo valor 30+ meses seguidos, 2022-10 a "
        "2025-03; probablemente precios regulados/subsidiados durante la crisis energética "
        "europea. No es un error: con una serie constante, tanto el naive como ARIMA "
        "\"aciertan\" siempre)."
    )
    L.append("")
    L.append(
        f"**Kruskal-Wallis entre los 5 indicadores** (no pareado, referencia general): "
        f"H={h_kw_rmse:.2f}, p={p_kw_rmse:.2e}."
    )
    L.append("")
    L.append(
        "**Hipótesis específica: core (ccpi) es más predecible que headline (hcpi)** — "
        "test pareado, mismos países en ambos indicadores:"
    )
    L.append("")
    L.append(texto_test_pareado("Core CPI", "Headline CPI", test_ccpi_hcpi))
    L.append("")

    # 2
    L.append("## 2. Volatilidad por componente")
    L.append("")
    L.append("Ranking de indicadores por RMSE mediano (más volátil/impredecible primero):")
    L.append("")
    orden_rmse = resumen_rmse["median"].sort_values(ascending=False)
    for i, (ind, val) in enumerate(orden_rmse.items(), 1):
        L.append(f"{i}. {NOMBRES[ind]} ({ind}): {val:.3f}")
    L.append("")
    L.append(
        "**Hipótesis: energía (ecpi) y alimentos (fcpi) son más volátiles/impredecibles que "
        "el core (ccpi)** — tests pareados:"
    )
    L.append("")
    L.append(f"- Energy CPI vs. Core CPI: {texto_test_pareado('Energy CPI', 'Core CPI', test_ccpi_ecpi)}")
    L.append("")
    L.append(f"- Food CPI vs. Core CPI: {texto_test_pareado('Food CPI', 'Core CPI', test_ccpi_fcpi)}")
    L.append("")

    # 3
    L.append("## 3. Persistencia GARCH por indicador")
    L.append("")
    L.append("Persistencia (alpha+beta) mediana por indicador (series con GARCH convergido):")
    L.append("")
    L.append("| Indicador | N series | Persistencia mediana | Persistencia media |")
    L.append("|---|---|---|---|")
    for ind in INDICADORES:
        r = resumen_pers.loc[ind]
        L.append(f"| {NOMBRES[ind]} ({ind}) | {int(r['size'])} | {r['median']:.3f} | {r['mean']:.3f} |")
    L.append("")
    L.append(f"Figura: `reports/figures/analisisB_boxplot_persistencia_indicador.png`.")
    L.append("")
    if pd.notna(p_kw_pers):
        L.append(
            f"**Kruskal-Wallis entre los 5 indicadores**: H={h_kw_pers:.2f}, p={p_kw_pers:.2e}."
        )
        L.append("")
        if p_kw_pers < ALPHA:
            ind_mas_persistente = resumen_pers["median"].idxmax()
            ind_menos_persistente = resumen_pers["median"].idxmin()
            L.append(
                f"**Diferencia significativa entre indicadores.** {NOMBRES[ind_mas_persistente]} "
                f"tiene la persistencia más alta (mediana {resumen_pers.loc[ind_mas_persistente, 'median']:.3f}) "
                f"y {NOMBRES[ind_menos_persistente]} la más baja (mediana "
                f"{resumen_pers.loc[ind_menos_persistente, 'median']:.3f}). "
                "**Implicancia de política monetaria:** si los shocks de energía/alimentos "
                "resultan con menor persistencia que el core, son más 'transitorios' en el "
                "sentido de Blinder/Bernanke y un banco central tendría más justificación "
                "para no reaccionar ante ellos; si su persistencia es similar o mayor al "
                "core, la idea de 'mirar a través' de esos shocks pierde sustento empírico "
                "en este panel."
            )
        else:
            L.append(
                "**No hay diferencia significativa en persistencia entre indicadores** con "
                "este test — no se puede confirmar con estos datos que los shocks de "
                "energía/alimentos sean más (o menos) transitorios que los del índice "
                "general o el core."
            )
    else:
        L.append("No hay suficientes series con GARCH convergido en algún indicador para correr el test.")
    L.append("")

    # 4
    L.append("## 4. Países con los 5 indicadores: ¿el orden de previsibilidad es consistente?")
    L.append("")
    L.append(f"**{len(completos)} países** tienen los 5 indicadores con RMSE walk-forward válido.")
    L.append("")
    if rango_promedio is not None:
        L.append("Rango promedio de previsibilidad dentro de cada país (1=más predecible, 5=menos):")
        L.append("")
        for ind in rango_promedio.sort_values().index:
            L.append(f"- {NOMBRES[ind]} ({ind}): {rango_promedio[ind]:.2f}")
        L.append("")
        L.append(f"Figura: `reports/figures/analisisB_rango_promedio.png`.")
        L.append("")
        L.append(
            f"**Test de Friedman** (equivalente no paramétrico de ANOVA de medidas repetidas — "
            f"H0: no hay un orden consistente entre indicadores dentro de cada país): "
            f"estadístico={friedman_stat:.2f}, p={friedman_p:.2e}."
        )
        L.append("")
        if friedman_p < ALPHA:
            L.append(
                "**El orden de previsibilidad SÍ es consistente entre países**: no es azar que "
                "algunos indicadores tiendan a ser más predecibles que otros dentro del mismo "
                "país — hay una jerarquía estructural entre componentes que se repite país a "
                "país, no solo un patrón agregado a nivel de medianas."
            )
        else:
            L.append(
                "**El orden de previsibilidad NO resulta consistente entre países** con este "
                "test — aunque las medianas agregadas (secciones 1-2) puedan sugerir una "
                "jerarquía, no hay evidencia de que esa jerarquía se repita sistemáticamente "
                "país por país."
            )
    else:
        L.append("Muestra insuficiente para el test de Friedman.")
    L.append("")

    # Hallazgos
    L.append("## Hallazgos principales")
    L.append("")
    hallazgos = []

    if test_ccpi_hcpi["suficiente"]:
        if test_ccpi_hcpi["p"] < ALPHA and test_ccpi_hcpi["gana_a"]:
            hallazgos.append(
                f"**Confirmado**: el core (ccpi) es sistemáticamente más predecible que el "
                f"headline (hcpi) (Wilcoxon p={test_ccpi_hcpi['p']:.1e}, n={test_ccpi_hcpi['n']}) "
                "— consistente con la idea de que excluir alimentos/energía saca ruido, no señal."
            )
        elif test_ccpi_hcpi["p"] < ALPHA:
            hallazgos.append(
                f"**Resultado inesperado**: el core (ccpi) salió sistemáticamente MENOS "
                f"predecible que el headline (hcpi) (Wilcoxon p={test_ccpi_hcpi['p']:.1e}), "
                "lo opuesto a la hipótesis de que excluir componentes volátiles mejora la "
                "previsibilidad — vale la pena investigar por qué en una fase posterior."
            )
        else:
            hallazgos.append(
                f"**No confirmado**: la diferencia entre core y headline no es significativa "
                f"(Wilcoxon p={test_ccpi_hcpi['p']:.2f}) — con este panel no se puede sostener "
                "que excluir alimentos/energía haga la inflación más predecible."
            )

    veredictos_volatilidad = []
    for nombre, test in [("Energy CPI", test_ccpi_ecpi), ("Food CPI", test_ccpi_fcpi)]:
        if test["suficiente"] and test["p"] < ALPHA and not test["gana_a"]:
            veredictos_volatilidad.append(f"{nombre} SÍ es significativamente más volátil que el core")
        elif test["suficiente"] and test["p"] < ALPHA:
            veredictos_volatilidad.append(f"{nombre} salió más predecible que el core (lo opuesto a la hipótesis)")
        elif test["suficiente"]:
            veredictos_volatilidad.append(f"{nombre} no mostró diferencia significativa con el core")
        else:
            veredictos_volatilidad.append(f"{nombre}: muestra insuficiente")
    hallazgos.append("Volatilidad de energía/alimentos vs. core: " + "; ".join(veredictos_volatilidad) + ".")

    if pd.notna(p_kw_pers):
        if p_kw_pers < ALPHA:
            hallazgos.append(
                f"La persistencia de volatilidad SÍ difiere entre indicadores (p={p_kw_pers:.1e}) "
                f"— {NOMBRES[resumen_pers['median'].idxmax()]} es la más persistente, "
                f"{NOMBRES[resumen_pers['median'].idxmin()]} la menos."
            )
        else:
            hallazgos.append(
                f"La persistencia de volatilidad NO difiere significativamente entre "
                f"indicadores (p={p_kw_pers:.2f}) en este panel."
            )

    if rango_promedio is not None:
        if friedman_p < ALPHA:
            hallazgos.append(
                f"Con Friedman (p={friedman_p:.1e}, n={len(completos)} países), el orden de "
                "previsibilidad entre indicadores es una estructura real y repetible país a "
                "país, no solo un artefacto de promediar medianas."
            )
        else:
            hallazgos.append(
                f"Con Friedman (p={friedman_p:.2f}, n={len(completos)} países), no se puede "
                "confirmar que el orden de previsibilidad se repita de forma consistente entre "
                "países — las medianas agregadas podrían estar promediando patrones "
                "heterogéneos país por país."
            )

    for h in hallazgos:
        L.append(f"- {h}")
    L.append("")

    return "\n".join(L)


def main() -> None:
    df, validos = cargar_datos()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    pivote_rmse = validos.pivot_table(index="codigo_pais", columns="indicador", values="rmse_arima_walkforward")

    resumen_rmse, h_kw_rmse, p_kw_rmse = analizar_rmse_por_indicador(validos)
    test_ccpi_hcpi = test_pareado(pivote_rmse, "ccpi", "hcpi")
    test_ccpi_ecpi = test_pareado(pivote_rmse, "ecpi", "ccpi")
    test_ccpi_fcpi = test_pareado(pivote_rmse, "fcpi", "ccpi")

    resumen_pers, h_kw_pers, p_kw_pers = analizar_persistencia_por_indicador(df)

    completos, rango_promedio, friedman_stat, friedman_p = analizar_paises_completos(validos)

    md = construir_markdown(
        resumen_rmse, h_kw_rmse, p_kw_rmse, test_ccpi_hcpi,
        resumen_pers, h_kw_pers, p_kw_pers,
        test_ccpi_ecpi, test_ccpi_fcpi,
        completos, rango_promedio, friedman_stat, friedman_p,
    )
    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
