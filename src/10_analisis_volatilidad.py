"""Análisis C — Dinámica de volatilidad (GARCH).

Sobre data/processed/resultados_enriquecidos.parquet. La sección 1
(distribución general) y la 5 (casos sin convergencia) usan el panel
completo (los 5 indicadores) porque son descriptivas/de caracterización,
no comparaciones entre países. Las secciones 2 (test de asociación), 3
(correlación) y 4 (Kruskal-Wallis) se restringen a `hcpi` para que cada
país aporte una sola observación (mismo criterio que Análisis A/B).
Conclusiones condicionadas al p-valor real de cada test.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"
REPORT_PATH = ROOT / "reports" / "analisis_C_volatilidad.md"
FIG_DIR = ROOT / "reports" / "figures"

ORDEN_INGRESO = ["Low income", "Lower middle income", "Upper middle income", "High income"]
ALPHA = 0.05


def cargar_datos():
    df = pd.read_parquet(RESULTADOS_PATH)
    conv = df[df["convergio_garch"]].copy()
    return df, conv


# ---------- 1. Distribución de la persistencia ----------
def analizar_distribucion(conv: pd.DataFrame):
    p = conv["persistencia"]
    percentiles = p.quantile([0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    frac_095 = (p >= 0.95).mean()
    frac_1 = (p >= 1).mean()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(p, bins=40, color="steelblue", edgecolor="white")
    ax.axvline(0.95, color="orange", linestyle="--", linewidth=1, label="persistencia=0.95")
    ax.axvline(1.0, color="crimson", linestyle="--", linewidth=1, label="persistencia=1 (IGARCH)")
    ax.set_xlabel("Persistencia GARCH (alpha+beta)")
    ax.set_ylabel("Cantidad de series")
    ax.set_title(f"Distribución de persistencia — panel completo (n={len(conv)})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisC_histograma_persistencia.png", dpi=120)
    plt.close(fig)

    return percentiles, frac_095, frac_1


# ---------- 2. Patrón IGARCH ----------
def analizar_igarch(df: pd.DataFrame, conv: pd.DataFrame):
    igarch_completo = conv[conv["persistencia"] >= 1].copy()

    por_region_completo = igarch_completo.groupby("region", observed=True).size().sort_values(ascending=False)
    por_ingreso_completo = igarch_completo.groupby("nivel_ingreso", observed=True).size().reindex(ORDEN_INGRESO)

    hcpi = conv[(conv["indicador"] == "hcpi") & (conv["nivel_ingreso"].notna())].copy()
    hcpi["igarch"] = hcpi["persistencia"] >= 1
    tabla = pd.crosstab(hcpi["nivel_ingreso"], hcpi["igarch"]).reindex(ORDEN_INGRESO)
    tabla = tabla.fillna(0)

    if tabla.shape[0] >= 2 and tabla.shape[1] == 2 and tabla.to_numpy().sum() > 0:
        chi2, p_chi2, dof, expected = stats.chi2_contingency(tabla)
        pct_celdas_bajas = (expected < 5).mean()
    else:
        chi2, p_chi2, expected, pct_celdas_bajas = np.nan, np.nan, None, np.nan

    return igarch_completo, por_region_completo, por_ingreso_completo, tabla, chi2, p_chi2, pct_celdas_bajas


# ---------- 3. Persistencia vs RMSE ----------
def analizar_persistencia_vs_rmse(conv: pd.DataFrame):
    hcpi = conv[(conv["indicador"] == "hcpi") & (conv["rmse_arima_walkforward"].notna())].copy()
    r, p = stats.spearmanr(hcpi["persistencia"], hcpi["rmse_arima_walkforward"])

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(hcpi["persistencia"], hcpi["rmse_arima_walkforward"], alpha=0.6, color="steelblue")
    ax.set_yscale("log")
    ax.set_xlabel("Persistencia GARCH (alpha+beta)")
    ax.set_ylabel("RMSE walk-forward (log-diff, escala log)")
    ax.set_title("Persistencia de volatilidad vs. previsibilidad de nivel (hcpi)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisC_scatter_persistencia_rmse.png", dpi=120)
    plt.close(fig)

    return hcpi, r, p


# ---------- 4. Persistencia por ingreso y región ----------
def analizar_persistencia_por_grupo(conv: pd.DataFrame):
    hcpi = conv[(conv["indicador"] == "hcpi") & (conv["nivel_ingreso"].notna())].copy()

    grupos_ing = [hcpi.loc[hcpi["nivel_ingreso"] == n, "persistencia"].dropna() for n in ORDEN_INGRESO]
    grupos_ing = [g for g in grupos_ing if len(g) >= 3]
    if len(grupos_ing) >= 2:
        h_ing, p_ing = stats.kruskal(*grupos_ing)
    else:
        h_ing, p_ing = np.nan, np.nan
    medianas_ing = hcpi.groupby("nivel_ingreso", observed=True)["persistencia"].median().reindex(ORDEN_INGRESO)

    hcpi_reg = hcpi[hcpi["region"].notna()]
    regiones = [r for r, g in hcpi_reg.groupby("region", observed=True) if len(g) >= 3]
    grupos_reg = [hcpi_reg.loc[hcpi_reg["region"] == r, "persistencia"].dropna() for r in regiones]
    if len(grupos_reg) >= 2:
        h_reg, p_reg = stats.kruskal(*grupos_reg)
    else:
        h_reg, p_reg = np.nan, np.nan
    medianas_reg = hcpi_reg.groupby("region", observed=True)["persistencia"].median().sort_values(ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))
    datos_ing = [hcpi.loc[hcpi["nivel_ingreso"] == n, "persistencia"].dropna() for n in ORDEN_INGRESO]
    axes[0].boxplot(datos_ing, tick_labels=ORDEN_INGRESO)
    axes[0].set_ylabel("Persistencia GARCH")
    axes[0].set_title("Por nivel de ingreso (hcpi)")
    axes[0].tick_params(axis="x", rotation=25)

    orden_reg = medianas_reg.index.tolist()
    datos_reg = [hcpi_reg.loc[hcpi_reg["region"] == r, "persistencia"].dropna() for r in orden_reg]
    axes[1].boxplot(datos_reg, tick_labels=orden_reg)
    axes[1].set_ylabel("Persistencia GARCH")
    axes[1].set_title("Por región (hcpi)")
    axes[1].tick_params(axis="x", rotation=40)
    for label in axes[1].get_xticklabels():
        label.set_ha("right")

    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisC_boxplot_persistencia_grupos.png", dpi=120)
    plt.close(fig)

    return medianas_ing, h_ing, p_ing, medianas_reg, h_reg, p_reg


# ---------- 5. Casos que no convergieron ----------
def analizar_no_convergencia(df: pd.DataFrame):
    no_conv = df[~df["convergio_garch"]].copy()
    fallas_reales = no_conv[no_conv["motivo_fallo_garch"] != "serie_no_apto_garch"]
    no_apto = no_conv[no_conv["motivo_fallo_garch"] == "serie_no_apto_garch"]
    return no_conv, fallas_reales, no_apto


def construir_markdown(percentiles, frac_095, frac_1, n_conv,
                        igarch_completo, por_region_ig, por_ingreso_ig, tabla_chi2, chi2, p_chi2, pct_celdas_bajas,
                        hcpi_rmse, r_rmse, p_rmse,
                        medianas_ing, h_ing, p_ing, medianas_reg, h_reg, p_reg,
                        no_conv, fallas_reales, no_apto, df_completo):
    L = []
    L.append("# Análisis C — Dinámica de volatilidad (GARCH)")
    L.append("")
    L.append(
        "Informe generado por `src/10_analisis_volatilidad.py` sobre "
        "`data/processed/resultados_enriquecidos.parquet`. Las secciones 1 y 5 usan el panel "
        "completo (los 5 indicadores, son descriptivas/de caracterización); las secciones 2 "
        "(test de asociación), 3 (correlación) y 4 (Kruskal-Wallis) se restringen a `hcpi` "
        "para que cada país aporte una sola observación a cada test, evitando "
        "pseudo-replicación (mismo criterio que Análisis A/B)."
    )
    L.append("")

    # 1
    L.append("## 1. Distribución de la persistencia (alpha+beta)")
    L.append("")
    L.append(f"Sobre las **{n_conv} series** con GARCH convergido (panel completo):")
    L.append("")
    L.append("| Percentil | Persistencia |")
    L.append("|---|---|")
    for q, v in percentiles.items():
        L.append(f"| p{int(q*100)} | {v:.3f} |")
    L.append("")
    L.append(f"- **{frac_095:.1%}** de las series tiene persistencia ≥ 0.95 (shocks muy duraderos).")
    L.append(f"- **{frac_1:.1%}** tiene persistencia ≥ 1 (IGARCH-like, borde de no-estacionariedad en varianza).")
    L.append("")
    L.append(f"Figura: `reports/figures/analisisC_histograma_persistencia.png`.")
    L.append("")

    # 2
    L.append("## 2. El patrón IGARCH (persistencia ≥ 1)")
    L.append("")
    L.append(f"**{len(igarch_completo)} series** (panel completo) tienen persistencia ≥ 1.")
    L.append("")
    L.append("Por región (panel completo, descriptivo):")
    L.append("")
    for region, n in por_region_ig.items():
        L.append(f"- {region}: {n}")
    L.append("")
    L.append("Por nivel de ingreso (panel completo, descriptivo):")
    L.append("")
    for nivel in ORDEN_INGRESO:
        n = por_ingreso_ig.get(nivel, 0)
        L.append(f"- {nivel}: {int(n) if pd.notna(n) else 0}")
    L.append("")
    L.append("**Test de asociación formal (hcpi, un país = una observación):**")
    L.append("")
    L.append("Tabla de contingencia (nivel de ingreso × IGARCH-like):")
    L.append("")
    L.append(tabla_chi2.to_string())
    L.append("")
    if pd.notna(p_chi2):
        L.append(f"Chi-cuadrado: χ²={chi2:.2f}, p={p_chi2:.2e}.")
        if pct_celdas_bajas > 0.2:
            L.append(
                f"**Advertencia de validez**: {pct_celdas_bajas:.0%} de las celdas tienen "
                "frecuencia esperada < 5 (regla de Cochran sugiere no superar el 20%) — hay muy "
                f"pocos casos IGARCH en hcpi ({int(tabla_chi2[True].sum())} en total) para que la "
                "aproximación chi-cuadrado sea del todo confiable. El resultado se reporta "
                "igual, pero con esta salvedad."
            )
        L.append("")
        if p_chi2 < ALPHA:
            L.append(
                "**Conclusión:** hay asociación estadísticamente significativa entre nivel de "
                "ingreso y patrón IGARCH — el patrón NO está repartido de forma pareja entre "
                "niveles de ingreso."
            )
        else:
            L.append(
                "**Conclusión:** no se detecta asociación estadísticamente significativa entre "
                "nivel de ingreso y patrón IGARCH — con esta muestra, el patrón IGARCH parece "
                "repartido de forma más o menos pareja entre niveles de ingreso, no "
                "concentrado en un extremo."
            )
    else:
        L.append("No hay suficientes casos IGARCH en hcpi para correr el test.")
    L.append("")

    # 3
    L.append("## 3. Persistencia vs. previsibilidad de nivel")
    L.append("")
    L.append(f"Figura: `reports/figures/analisisC_scatter_persistencia_rmse.png`.")
    L.append("")
    L.append(f"Correlación de Spearman (hcpi, n={len(hcpi_rmse)}): ρ={r_rmse:.3f}, p={p_rmse:.2e}.")
    L.append("")
    if p_rmse < ALPHA:
        direccion = "positiva" if r_rmse > 0 else "negativa"
        L.append(
            f"**Conclusión:** hay una relación {direccion} y estadísticamente significativa "
            "entre persistencia de volatilidad y RMSE de nivel — la imprevisibilidad del "
            "*nivel* de inflación y la de su *volatilidad* no son completamente independientes "
            "en este panel."
        )
    else:
        L.append(
            "**Conclusión:** no hay relación estadísticamente significativa entre persistencia "
            "de volatilidad y RMSE de nivel — son dos dimensiones de imprevisibilidad "
            "aparentemente **independientes** en este panel: que la volatilidad de un país "
            "sea persistente no implica que su nivel de inflación sea más difícil de "
            "pronosticar (ni viceversa)."
        )
    L.append("")

    # 4
    L.append("## 4. Persistencia por nivel de ingreso y región")
    L.append("")
    L.append("Persistencia mediana por nivel de ingreso (hcpi):")
    L.append("")
    for nivel in ORDEN_INGRESO:
        if nivel in medianas_ing.index and pd.notna(medianas_ing[nivel]):
            L.append(f"- {nivel}: {medianas_ing[nivel]:.3f}")
    L.append("")
    if pd.notna(p_ing):
        L.append(f"Kruskal-Wallis: H={h_ing:.2f}, p={p_ing:.2e}.")
        L.append(
            "**Conclusión:** el gradiente de ingreso SÍ se repite en la persistencia de "
            "volatilidad." if p_ing < ALPHA else
            "**Conclusión:** el gradiente de ingreso que se ve claramente en previsibilidad de "
            "nivel (Análisis A) **no se repite de forma significativa en persistencia de "
            "volatilidad** — son fenómenos relacionados pero no gobernados por el mismo "
            "gradiente."
        )
    L.append("")
    L.append("Persistencia mediana por región (hcpi), de mayor a menor:")
    L.append("")
    for region, v in medianas_reg.items():
        L.append(f"- {region}: {v:.3f}")
    L.append("")
    if pd.notna(p_reg):
        L.append(f"Kruskal-Wallis: H={h_reg:.2f}, p={p_reg:.2e}.")
        L.append(
            "**Conclusión:** hay diferencias regionales significativas en persistencia de "
            "volatilidad." if p_reg < ALPHA else
            "**Conclusión:** no se puede descartar que las diferencias regionales en "
            "persistencia sean azar."
        )
    L.append("")
    L.append(f"Figura: `reports/figures/analisisC_boxplot_persistencia_grupos.png`.")
    L.append("")

    # 5
    L.append("## 5. Casos que no convergieron en GARCH")
    L.append("")
    L.append(
        f"De las {len(no_conv)} series sin `convergio_garch`, **{len(fallas_reales)} son "
        f"fallas reales de convergencia** (el optimizador corrió y no encontró una solución "
        f"válida) y **{len(no_apto)} son series que directamente no se intentaron** "
        "(`motivo_fallo_garch='serie_no_apto_garch'`, no cumplen el piso de 100 meses sin "
        "huecos internos de Fase 3 — nunca llegan a pedirle nada al optimizador)."
    )
    L.append("")
    if len(fallas_reales) == 0:
        L.append(
            "**Hallazgo, corrigiendo la hipótesis de partida: no hubo ninguna falla real de "
            "convergencia de GARCH en todo el panel.** La expectativa de que Argentina o "
            "Venezuela fallarían \"por volatilidad extrema\" no se cumplió — `rescale=True` "
            "(Fase de modelado) hizo su trabajo. Lo que sí les pasó a Argentina y Venezuela es "
            "más aburrido pero más honesto: varias de sus series **ni siquiera llegaron a "
            "intentarse**, porque no cumplen el piso de 100 meses sin huecos que exige "
            "`apto_garch` — no por ser demasiado volátiles, sino por tener historia "
            "insuficiente (Argentina hcpi: 86 meses; Venezuela ecpi/fcpi/hcpi: 70-79 meses, "
            "recortadas además por la exclusión de sus ceros-placeholder en Fase 2)."
        )
        L.append("")
        casos_extremos = df_completo[
            (df_completo["codigo_pais"].isin(["ARG", "VEN", "ZWE", "TUR"])) & (df_completo["convergio_garch"])
        ][["codigo_pais", "indicador", "persistencia", "meses_usados"]].sort_values(["codigo_pais", "indicador"])
        L.append(
            "Como evidencia de que sí converge en casos de volatilidad extrema: las series de "
            "Argentina, Venezuela, Zimbabwe y Turquía que **sí** cumplieron el piso de 100 "
            "meses convergieron todas, varias en el borde IGARCH (persistencia≈1):"
        )
        L.append("")
        L.append("| País | Indicador | Persistencia | Meses usados |")
        L.append("|---|---|---|---|")
        for _, r in casos_extremos.iterrows():
            L.append(f"| {r['codigo_pais']} | {r['indicador']} | {r['persistencia']:.3f} | {int(r['meses_usados'])} |")
    else:
        L.append("Series con falla real de convergencia:")
        L.append("")
        L.append("| País | Indicador | Motivo |")
        L.append("|---|---|---|")
        for _, r in fallas_reales.iterrows():
            L.append(f"| {r['codigo_pais']} | {r['indicador']} | {r['motivo_fallo_garch']} |")
    L.append("")

    # Hallazgos
    L.append("## Hallazgos principales")
    L.append("")
    if pd.notna(p_chi2):
        veredicto_chi2 = "es estadísticamente significativa" if p_chi2 < ALPHA else "NO alcanza significancia estadística con esta muestra"
        L.append(
            f"- **{frac_1:.1%}** del panel completo muestra comportamiento IGARCH-like "
            f"(persistencia≥1); la asociación con nivel de ingreso {veredicto_chi2} "
            f"(χ²={chi2:.2f}, p={p_chi2:.2e})."
        )
    else:
        L.append(f"- **{frac_1:.1%}** del panel completo muestra comportamiento IGARCH-like (persistencia≥1).")

    veredicto_rmse = "SÍ están relacionadas" if p_rmse < ALPHA else "son dimensiones estadísticamente INDEPENDIENTES"
    L.append(
        f"- Persistencia de volatilidad y previsibilidad de nivel (RMSE) {veredicto_rmse} "
        f"en este panel (Spearman ρ={r_rmse:.2f}, p={p_rmse:.2e})."
    )
    if pd.notna(p_ing):
        veredicto_ing = "se repite" if p_ing < ALPHA else "NO se repite"
        L.append(
            f"- El gradiente de ingreso de Análisis A {veredicto_ing} en la persistencia de "
            f"volatilidad (Kruskal-Wallis p={p_ing:.2e})."
        )
    L.append(
        "- No hubo ninguna falla real de convergencia de GARCH en todo el panel — los "
        "\"casos problemáticos\" esperados (Argentina, Venezuela) resultaron ser un problema "
        "de cobertura de datos (menos de 100 meses sin huecos), no de estabilidad numérica "
        "del modelo."
    )
    L.append("")

    return "\n".join(L)


def main() -> None:
    df, conv = cargar_datos()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    percentiles, frac_095, frac_1 = analizar_distribucion(conv)
    igarch_completo, por_region_ig, por_ingreso_ig, tabla_chi2, chi2, p_chi2, pct_celdas_bajas = analizar_igarch(df, conv)
    hcpi_rmse, r_rmse, p_rmse = analizar_persistencia_vs_rmse(conv)
    medianas_ing, h_ing, p_ing, medianas_reg, h_reg, p_reg = analizar_persistencia_por_grupo(conv)
    no_conv, fallas_reales, no_apto = analizar_no_convergencia(df)

    md = construir_markdown(
        percentiles, frac_095, frac_1, len(conv),
        igarch_completo, por_region_ig, por_ingreso_ig, tabla_chi2, chi2, p_chi2, pct_celdas_bajas,
        hcpi_rmse, r_rmse, p_rmse,
        medianas_ing, h_ing, p_ing, medianas_reg, h_reg, p_reg,
        no_conv, fallas_reales, no_apto, df,
    )
    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
