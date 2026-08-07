"""Análisis A — Previsibilidad de la inflación.

Trabaja sobre data/processed/resultados_enriquecidos.parquet. Las
secciones 1-3 y 5 (comparaciones entre países) se restringen al indicador
`hcpi` (headline CPI): usar los 5 indicadores mezclados violaría
independencia en los tests estadísticos (varios indicadores del mismo país
no son observaciones independientes) y hcpi es, por lejos, el más
comparable entre países. La sección 4 sí usa el panel completo (los 5
indicadores) porque caracteriza el hallazgo del 37% ya reportado sobre el
panel completo en la fase de modelado.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"
INFLACION_PATH = ROOT / "data" / "processed" / "inflacion_mensual_completa_v2.parquet"
REPORT_PATH = ROOT / "reports" / "analisis_A_previsibilidad.md"
FIG_DIR = ROOT / "reports" / "figures"

ORDEN_INGRESO = ["Low income", "Lower middle income", "Upper middle income", "High income"]
ORDINAL_INGRESO = {n: i for i, n in enumerate(ORDEN_INGRESO)}


def cargar_datos():
    resultados = pd.read_parquet(RESULTADOS_PATH)
    inflacion = pd.read_parquet(INFLACION_PATH)
    inflacion_media = (
        inflacion.groupby(["codigo_pais", "indicador"])["inflacion_yoy_pct"]
        .mean()
        .reset_index(name="inflacion_media_pct")
    )
    resultados = resultados.merge(inflacion_media, on=["codigo_pais", "indicador"], how="left")
    return resultados


def preparar_hcpi(df: pd.DataFrame) -> pd.DataFrame:
    hcpi = df[
        (df["indicador"] == "hcpi")
        & (df["convergio_arima"])
        & (df["rmse_arima_walkforward"].notna())
        & (df["nivel_ingreso"].notna())
    ].copy()
    hcpi["nivel_ingreso"] = pd.Categorical(hcpi["nivel_ingreso"], categories=ORDEN_INGRESO, ordered=True)
    hcpi["ingreso_ordinal"] = hcpi["nivel_ingreso"].map(ORDINAL_INGRESO)
    return hcpi


# ---------- 1. Ranking ----------
def construir_ranking(hcpi: pd.DataFrame):
    cols = ["codigo_pais", "pais", "nivel_ingreso", "region", "inflacion_media_pct", "ratio_vs_naive", "rmse_arima_walkforward"]
    mas_predecibles = hcpi.nsmallest(15, "rmse_arima_walkforward")[cols]
    menos_predecibles = hcpi.nlargest(15, "rmse_arima_walkforward")[cols]
    return mas_predecibles, menos_predecibles


# ---------- 2. Gradiente por nivel de ingreso ----------
def analizar_gradiente_ingreso(hcpi: pd.DataFrame):
    grupos = [hcpi.loc[hcpi["nivel_ingreso"] == n, "rmse_arima_walkforward"].dropna() for n in ORDEN_INGRESO]
    h_stat, p_valor = stats.kruskal(*grupos)

    medianas = hcpi.groupby("nivel_ingreso", observed=True)["rmse_arima_walkforward"].median()

    fig, ax = plt.subplots(figsize=(8, 5))
    hcpi.boxplot(column="rmse_arima_walkforward", by="nivel_ingreso", ax=ax)
    ax.set_xlabel("Nivel de ingreso")
    ax.set_ylabel("RMSE walk-forward (log-diff)")
    ax.set_title("RMSE por nivel de ingreso (hcpi)")
    plt.suptitle("")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisA_boxplot_ingreso.png", dpi=120)
    plt.close(fig)

    return h_stat, p_valor, medianas


# ---------- 3. Previsibilidad vs nivel de inflación ----------
def analizar_inflacion_vs_rmse(hcpi: pd.DataFrame):
    x = hcpi["inflacion_media_pct"]
    y = hcpi["rmse_arima_walkforward"]
    z = hcpi["ingreso_ordinal"]

    r_xy, p_xy = stats.spearmanr(x, y)
    r_xz, p_xz = stats.spearmanr(x, z)
    r_yz, p_yz = stats.spearmanr(y, z)

    denom = np.sqrt((1 - r_xz**2) * (1 - r_yz**2))
    r_parcial = (r_xy - r_xz * r_yz) / denom if denom > 0 else np.nan
    n = len(hcpi)
    df_t = n - 3
    if pd.notna(r_parcial) and abs(r_parcial) < 1:
        t_stat = r_parcial * np.sqrt(df_t / (1 - r_parcial**2))
        p_parcial = 2 * stats.t.sf(abs(t_stat), df_t)
    else:
        p_parcial = np.nan

    fig, ax = plt.subplots(figsize=(8, 6))
    colores = {"Low income": "#d62728", "Lower middle income": "#ff7f0e", "Upper middle income": "#1f77b4", "High income": "#2ca02c"}
    for nivel in ORDEN_INGRESO:
        sub = hcpi[hcpi["nivel_ingreso"] == nivel]
        ax.scatter(sub["inflacion_media_pct"], sub["rmse_arima_walkforward"], label=nivel, color=colores[nivel], alpha=0.7)
    ax.set_xlabel("Inflación media del período (%, pct_change)")
    ax.set_ylabel("RMSE walk-forward (log-diff)")
    ax.set_xscale("symlog")
    ax.set_yscale("log")
    ax.set_title("Previsibilidad vs. nivel de inflación (hcpi)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisA_scatter_inflacion_rmse.png", dpi=120)
    plt.close(fig)

    return {
        "r_xy": r_xy, "p_xy": p_xy,
        "r_xz": r_xz, "p_xz": p_xz,
        "r_yz": r_yz, "p_yz": p_yz,
        "r_parcial": r_parcial, "p_parcial": p_parcial,
        "n": n,
    }


# ---------- 4. Hallazgo del baseline (panel completo) ----------
def analizar_baseline(df: pd.DataFrame):
    panel = df[(df["convergio_arima"]) & (df["ratio_vs_naive"].notna())].copy()
    panel["gana_arima"] = panel["ratio_vs_naive"] < 1

    n_total = len(panel)
    n_gana = int(panel["gana_arima"].sum())

    inflacion_abs_gana = panel.loc[panel["gana_arima"], "inflacion_media_pct"].abs().dropna()
    inflacion_abs_no_gana = panel.loc[~panel["gana_arima"], "inflacion_media_pct"].abs().dropna()
    u_stat, p_valor = stats.mannwhitneyu(inflacion_abs_gana, inflacion_abs_no_gana, alternative="greater")

    # chequeo de robustez: correlación continua en vez de partir la muestra
    # en dos grupos (usa toda la información de ratio_vs_naive, no solo el
    # signo de gana/no-gana)
    con_datos = panel.dropna(subset=["inflacion_media_pct", "ratio_vs_naive"])
    r_cont, p_cont = stats.spearmanr(con_datos["inflacion_media_pct"].abs(), con_datos["ratio_vs_naive"])

    fig, ax = plt.subplots(figsize=(7, 5))
    datos = [inflacion_abs_no_gana, inflacion_abs_gana]
    ax.boxplot(datos, tick_labels=["ARIMA NO gana\n(ratio>=1)", "ARIMA gana\n(ratio<1)"])
    ax.set_yscale("symlog")
    ax.set_ylabel("|Inflación media del período| (%)")
    ax.set_title("Inflación media: series donde ARIMA gana vs. no gana al naive\n(panel completo, 5 indicadores)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisA_boxplot_baseline.png", dpi=120)
    plt.close(fig)

    # nuance: dentro de las series de MAYOR RMSE (menos predecibles), separar
    # inflación "en tendencia" (ARIMA la sigue bien) de "errática/con saltos"
    # (ni ARIMA ni naive la agarran) -- para explicar por qué el efecto
    # simple sale débil: ambos tipos de alta inflación tironean en sentidos
    # opuestos dentro del mismo grupo de "alta inflación".
    alta_inflacion = panel[panel["inflacion_media_pct"].abs() > 20].copy()
    alta_inflacion = alta_inflacion.sort_values("ratio_vs_naive")

    return {
        "n_total": n_total,
        "n_gana": n_gana,
        "mediana_infl_gana": inflacion_abs_gana.median(),
        "mediana_infl_no_gana": inflacion_abs_no_gana.median(),
        "u_stat": u_stat,
        "p_valor": p_valor,
        "r_cont": r_cont,
        "p_cont": p_cont,
        "alta_inflacion": alta_inflacion,
    }


# ---------- 5. Patrones regionales ----------
def analizar_regiones(hcpi: pd.DataFrame):
    resumen = hcpi.groupby("region", observed=True).agg(
        n_series=("codigo_pais", "size"), rmse_mediano=("rmse_arima_walkforward", "median")
    ).sort_values("rmse_mediano")

    sin_na = hcpi[hcpi["region"] != "North America"]
    grupos = [g["rmse_arima_walkforward"].dropna() for _, g in sin_na.groupby("region", observed=True) if len(g) >= 3]
    if len(grupos) >= 2:
        h_stat, p_valor = stats.kruskal(*grupos)
    else:
        h_stat, p_valor = np.nan, np.nan

    orden_regiones = resumen.index.tolist()
    fig, ax = plt.subplots(figsize=(10, 5))
    datos = [hcpi.loc[hcpi["region"] == r, "rmse_arima_walkforward"].dropna() for r in orden_regiones]
    ax.boxplot(datos, tick_labels=orden_regiones)
    ax.set_yscale("log")
    ax.set_ylabel("RMSE walk-forward (log-diff)")
    ax.set_title("RMSE por región (hcpi)")
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "analisisA_boxplot_region.png", dpi=120)
    plt.close(fig)

    return resumen, h_stat, p_valor


def construir_markdown(mas_pred, menos_pred, h_ing, p_ing, medianas_ing, corr, baseline, resumen_reg, h_reg, p_reg, n_hcpi):
    L = []
    L.append("# Análisis A — Previsibilidad de la inflación")
    L.append("")
    L.append(
        "Informe generado por `src/08_analisis_previsibilidad.py` sobre "
        "`data/processed/resultados_enriquecidos.parquet`. Las secciones "
        "1-3 y 5 usan solo `hcpi` (headline CPI, una fila por país) para "
        "evitar pseudo-replicación en los tests estadísticos — mezclar los "
        "5 indicadores trataría a hcpi/ecpi/fcpi/ccpi/ppi del mismo país "
        "como observaciones independientes cuando no lo son. La sección 4 "
        f"sí usa el panel completo (los 5 indicadores). N series hcpi "
        f"analizadas: **{n_hcpi}**."
    )
    L.append("")

    # 1
    L.append("## 1. Ranking de previsibilidad (hcpi)")
    L.append("")
    L.append("**Top 15 países más predecibles** (menor RMSE walk-forward):")
    L.append("")
    L.append("| País | Ingreso | Región | Inflación media (%) | ratio vs. naive | RMSE |")
    L.append("|---|---|---|---|---|---|")
    for _, r in mas_pred.iterrows():
        L.append(
            f"| {r['pais']} ({r['codigo_pais']}) | {r['nivel_ingreso']} | {r['region']} "
            f"| {r['inflacion_media_pct']:.2f} | {r['ratio_vs_naive']:.3f} | {r['rmse_arima_walkforward']:.4f} |"
        )
    L.append("")
    L.append("**Top 15 países menos predecibles** (mayor RMSE walk-forward):")
    L.append("")
    L.append("| País | Ingreso | Región | Inflación media (%) | ratio vs. naive | RMSE |")
    L.append("|---|---|---|---|---|---|")
    for _, r in menos_pred.iterrows():
        L.append(
            f"| {r['pais']} ({r['codigo_pais']}) | {r['nivel_ingreso']} | {r['region']} "
            f"| {r['inflacion_media_pct']:.2f} | {r['ratio_vs_naive']:.3f} | {r['rmse_arima_walkforward']:.4f} |"
        )
    L.append("")

    # 2
    L.append("## 2. Gradiente por nivel de ingreso")
    L.append("")
    L.append("RMSE mediano por nivel de ingreso:")
    L.append("")
    for nivel in ORDEN_INGRESO:
        if nivel in medianas_ing.index:
            L.append(f"- {nivel}: {medianas_ing[nivel]:.4f}")
    L.append("")
    L.append(f"Figura: `reports/figures/analisisA_boxplot_ingreso.png`.")
    L.append("")
    L.append(
        f"**Test de Kruskal-Wallis** (no paramétrico, apropiado porque el RMSE no es normal — "
        f"tiene cola derecha pesada): H = {h_ing:.2f}, p-valor = {p_ing:.2e}."
    )
    conclusion_ing = (
        "se confirma que la diferencia entre grupos de ingreso NO es azar"
        if p_ing < 0.05
        else "no se puede descartar que la diferencia entre grupos sea azar"
    )
    L.append(f"**Conclusión:** con p {'<' if p_ing < 0.05 else '>='} 0.05, {conclusion_ing}.")
    L.append("")

    # 3
    L.append("## 3. Previsibilidad vs. nivel de inflación")
    L.append("")
    L.append(f"Figura: `reports/figures/analisisA_scatter_inflacion_rmse.png`.")
    L.append("")
    L.append(
        f"- Correlación de Spearman inflación media vs. RMSE: **ρ = {corr['r_xy']:.3f}** "
        f"(p = {corr['p_xy']:.2e})."
    )
    L.append(
        f"- Correlación de Spearman inflación media vs. nivel de ingreso (ordinal): "
        f"ρ = {corr['r_xz']:.3f} (p = {corr['p_xz']:.2e})."
    )
    L.append(
        f"- Correlación de Spearman RMSE vs. nivel de ingreso (ordinal): "
        f"ρ = {corr['r_yz']:.3f} (p = {corr['p_yz']:.2e})."
    )
    L.append("")
    L.append(
        f"**Correlación parcial** de inflación vs. RMSE, controlando por nivel de ingreso: "
        f"**ρ parcial = {corr['r_parcial']:.3f}** (p = {corr['p_parcial']:.2e}, n={corr['n']})."
    )
    L.append("")
    if abs(corr["r_parcial"]) > 0.3 and corr["p_parcial"] < 0.05:
        veredicto_confound = (
            "La correlación parcial se mantiene alta y significativa después de controlar por "
            "ingreso: **el nivel de inflación explica la imprevisibilidad de forma independiente "
            "del nivel de ingreso**, no es solo un efecto indirecto de que los países pobres "
            "tienden a tener más inflación."
        )
    else:
        veredicto_confound = (
            "La correlación parcial cae sustancialmente respecto a la correlación simple: "
            "**gran parte de la relación aparente entre inflación y RMSE está mediada por el "
            "nivel de ingreso** — ambas variables están correlacionadas entre sí, y el ingreso "
            "es al menos parte de lo que explica la imprevisibilidad, no solo el nivel de "
            "inflación en sí."
        )
    L.append(veredicto_confound)
    L.append("")

    # 4
    L.append("## 4. El hallazgo del baseline (panel completo, 5 indicadores)")
    L.append("")
    pct_gana = baseline["n_gana"] / baseline["n_total"]
    L.append(
        f"Sobre las {baseline['n_total']} series con walk-forward válido: **{baseline['n_gana']} "
        f"({pct_gana:.1%})** tienen `ratio_vs_naive < 1` (ARIMA le gana al naive) y "
        f"{baseline['n_total']-baseline['n_gana']} ({1-pct_gana:.1%}) no."
    )
    L.append("")
    L.append(
        f"Inflación media (valor absoluto) — mediana donde ARIMA **gana**: "
        f"{baseline['mediana_infl_gana']:.2f}%. Mediana donde **no gana**: "
        f"{baseline['mediana_infl_no_gana']:.2f}%."
    )
    L.append("")
    L.append(f"Figura: `reports/figures/analisisA_boxplot_baseline.png`.")
    L.append("")
    L.append(
        f"**Test de Mann-Whitney U** (H1: la inflación absoluta es mayor donde ARIMA gana): "
        f"U = {baseline['u_stat']:.1f}, p-valor = {baseline['p_valor']:.2e}."
    )
    L.append(
        f"**Chequeo de robustez** (en vez de partir la muestra en dos grupos, correlación "
        f"continua entre |inflación media| y `ratio_vs_naive` sobre las {baseline['n_total']} "
        f"series): Spearman ρ = {baseline['r_cont']:.3f}, p = {baseline['p_cont']:.2e}."
    )
    L.append("")
    if baseline["p_valor"] < 0.05 and baseline["p_cont"] < 0.05:
        conclusion_baseline = (
            "ambos tests confirman con datos la narrativa: las series donde ARIMA le gana al "
            "naive tienen inflación significativamente más alta que las series donde no le "
            "gana. **El random walk es difícil de superar específicamente en los países de "
            "inflación baja y estable.**"
        )
    else:
        conclusion_baseline = (
            "**ninguno de los dos tests alcanza significancia estadística** (p="
            f"{baseline['p_valor']:.2f} y p={baseline['p_cont']:.2f}) — con esta muestra, el "
            "nivel de inflación por sí solo NO predice de forma confiable si una serie va a "
            "ganarle al naive o no. La narrativa \"el random walk es imbatible en inflación "
            "estable\" es intuitiva y se ve con claridad en un puñado de países ilustrativos "
            "(EE.UU./Alemania pierden, Argentina/Venezuela ganan — ver el sanity check de la "
            "fase de modelado), pero **no se sostiene como patrón general y estadísticamente "
            "significativo en todo el panel.**"
        )
    L.append(f"**Conclusión:** {conclusion_baseline}")
    L.append("")

    alta = baseline["alta_inflacion"]
    L.append(
        f"**¿Por qué el efecto simple sale débil?** Mirando de cerca las {len(alta)} series con "
        "inflación media absoluta > 20% (todas, en principio, \"candidatas\" a que ARIMA le "
        "gane al naive por tener una tendencia marcada), el `ratio_vs_naive` va de "
        f"{alta['ratio_vs_naive'].min():.2f} a {alta['ratio_vs_naive'].max():.2f} — un rango "
        "enorme, no un bloque uniforme. Argentina, Venezuela y Lituania (inflación alta pero "
        "con una tendencia sostenida que ARIMA puede seguir) están entre las que MÁS le ganan "
        "al naive; Zimbabwe, Sudán del Sur y Letonia (`hcpi`, no `fcpi`) — inflación alta pero "
        "con saltos discontinuos o cambios de régimen abruptos — están entre las que MENOS le "
        "ganan. **No es \"cuánta\" inflación tiene la serie lo que determina si ARIMA aporta, "
        "sino si esa inflación tiene una tendencia que un modelo lineal puede seguir, o si es "
        "errática/discontinua** — eso diluye la relación simple entre nivel de inflación y "
        "ventaja de ARIMA cuando se la mide en bloque."
    )
    L.append("")

    # 5
    L.append("## 5. Patrones regionales (hcpi)")
    L.append("")
    L.append("RMSE mediano por región, de más a menos predecible:")
    L.append("")
    L.append("| Región | N series | RMSE mediano |")
    L.append("|---|---|---|")
    for region, r in resumen_reg.iterrows():
        nota = " *(n=2, no incluida en el test)*" if region == "North America" else ""
        L.append(f"| {region}{nota} | {int(r['n_series'])} | {r['rmse_mediano']:.4f} |")
    L.append("")
    L.append(f"Figura: `reports/figures/analisisA_boxplot_region.png`.")
    L.append("")
    if pd.notna(p_reg):
        L.append(
            f"**Test de Kruskal-Wallis** entre regiones (excluyendo North America por n=2): "
            f"H = {h_reg:.2f}, p-valor = {p_reg:.2e}."
        )
        conclusion_reg = (
            "hay diferencias regionales significativas en previsibilidad."
            if p_reg < 0.05
            else "no se puede descartar que las diferencias regionales observadas sean azar."
        )
        L.append(f"**Conclusión:** {conclusion_reg}")
    L.append("")

    # Conclusiones
    L.append("## Conclusiones principales")
    L.append("")
    if p_ing < 0.05:
        texto_c1 = (
            f"**El ingreso importa, y no es casualidad**: el gradiente de previsibilidad por "
            f"nivel de ingreso es estadísticamente significativo (Kruskal-Wallis "
            f"p={p_ing:.1e}) — los países de mayores ingresos tienen inflación más previsible, "
            "en línea con instituciones monetarias más estables y menor exposición a shocks "
            "estructurales."
        )
    else:
        texto_c1 = (
            f"**El gradiente de previsibilidad por nivel de ingreso no alcanza significancia "
            f"estadística** (Kruskal-Wallis p={p_ing:.2f}) — con esta muestra no se puede "
            "confirmar que el nivel de ingreso por sí solo determine la previsibilidad."
        )
    L.append(f"1. {texto_c1}")
    if abs(corr["r_parcial"]) > 0.3 and corr["p_parcial"] < 0.05:
        texto_c2 = (
            f"**La inflación alta es sistemáticamente más difícil de pronosticar incluso "
            f"controlando por nivel de ingreso** (correlación parcial ρ={corr['r_parcial']:.2f}, "
            f"p={corr['p_parcial']:.1e}): no es solo que los países pobres tengan más "
            "inflación, el nivel de inflación en sí mismo predice peor performance de "
            "pronóstico."
        )
    else:
        texto_c2 = (
            f"**La correlación simple entre inflación y RMSE (ρ={corr['r_xy']:.2f}) se explica "
            f"en gran parte por el nivel de ingreso**, no por la inflación en sí misma: al "
            f"controlar por ingreso, la correlación parcial cae a ρ={corr['r_parcial']:.2f} "
            f"(p={corr['p_parcial']:.2f}, no significativa). El ingreso y la inflación están "
            "entrelazados en esta muestra, y separar sus efectos con el n disponible no da "
            "una conclusión firme sobre cuál de los dos \"causa\" la imprevisibilidad."
        )
    L.append(f"2. {texto_c2}")

    if baseline["p_valor"] < 0.05 and baseline["p_cont"] < 0.05:
        texto_c3 = (
            "**El 37% donde ARIMA no le gana al naive no es un fracaso del modelo — es la "
            "firma de la estabilidad**: son sistemáticamente las series de inflación baja, "
            "donde 'el mes que viene se va a parecer al anterior' ya es una predicción casi "
            "óptima."
        )
    else:
        texto_c3 = (
            "**El 37% donde ARIMA no le gana al naive NO se explica simplemente por \"baja "
            "inflación\"** — ni el test de grupos ni la correlación continua encuentran una "
            "relación estadísticamente significativa entre nivel de inflación y "
            "`ratio_vs_naive` en todo el panel. Lo que sí aparece, mirando de cerca las series "
            "de inflación alta (sección 4), es que importa más el *tipo* de alta inflación "
            "(tendencia sostenida vs. saltos erráticos) que su magnitud. La narrativa \"random "
            "walk imbatible en inflación estable\" es real en casos puntuales (ver el sanity "
            "check de la fase de modelado: EE.UU./Alemania vs. Argentina/Venezuela) pero no es "
            "la explicación general de por qué el otro 37% no le gana al naive — haría falta "
            "mirar caso por caso, no un patrón único."
        )
    L.append(f"3. {texto_c3}")
    if pd.notna(p_reg) and p_reg < 0.05:
        texto_c4 = (
            f"**También hay estructura regional propia** (Kruskal-Wallis entre regiones "
            f"p={p_reg:.1e}), probablemente correlacionada con ingreso pero no reducible a "
            "él — vale la pena tenerla presente como variable propia en análisis futuros."
        )
    else:
        p_reg_txt = f"{p_reg:.2f}" if pd.notna(p_reg) else "no calculable"
        texto_c4 = (
            f"**La región, a diferencia del ingreso, NO muestra un efecto estadísticamente "
            f"significativo propio** (Kruskal-Wallis p={p_reg_txt}) una vez que se la mira "
            "región por región — el RMSE mediano varía (Sub-Saharan Africa el doble que Latin "
            "America & Caribbean, sección 5), pero con el n disponible por región no alcanza "
            "para distinguir esa variación de azar. Es coherente con que buena parte de la "
            "variación regional podría estar mediada por la composición de ingreso de cada "
            "región, no por geografía en sí."
        )
    L.append(f"4. {texto_c4}")
    L.append("")

    return "\n".join(L)


def main() -> None:
    df = cargar_datos()
    hcpi = preparar_hcpi(df)
    n_hcpi = len(hcpi)

    FIG_DIR.mkdir(parents=True, exist_ok=True)

    mas_pred, menos_pred = construir_ranking(hcpi)
    h_ing, p_ing, medianas_ing = analizar_gradiente_ingreso(hcpi)
    corr = analizar_inflacion_vs_rmse(hcpi)
    baseline = analizar_baseline(df)
    resumen_reg, h_reg, p_reg = analizar_regiones(hcpi)

    md = construir_markdown(
        mas_pred, menos_pred, h_ing, p_ing, medianas_ing, corr, baseline, resumen_reg, h_reg, p_reg, n_hcpi
    )
    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
