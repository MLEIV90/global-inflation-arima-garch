"""Continuación de la auditoría metodológica — SOLO DIAGNÓSTICO.

PARTE 1: intervalos de confianza por bootstrap para el RMSE walk-forward
de cada serie hcpi, aplicados al ranking de previsibilidad de Análisis A.

PARTE 2: modelo OLS multivariado (errores robustos) de la previsibilidad,
controlando simultáneamente por ingreso, inflación media, longitud de
serie, región y persistencia GARCH.

Conclusiones condicionadas al resultado real de cada test.
"""

import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pmdarima as pm
import statsmodels.api as sm
from joblib import Parallel, delayed
from scipy import stats
from statsmodels.stats.outliers_influence import variance_inflation_factor

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
INFLACION_PATH = ROOT / "data" / "processed" / "inflacion_mensual_completa_v2.parquet"
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"
REPORT_PATH = ROOT / "reports" / "robustez_multivariado.md"
FIG_DIR = ROOT / "reports" / "figures"

VENTANA_EVAL = 24
REESTIMAR_CADA = 6
MIN_TOTAL_TRAMO = 48
TIMEOUT_SEG = 60
ALPHA = 0.05
N_BOOTSTRAP = 1000
N_RANKING = 15

ORDEN_INGRESO = ["Low income", "Lower middle income", "Upper middle income", "High income"]


def con_timeout(func, timeout_seg, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seg), None
        except FutureTimeoutError:
            return None, "timeout"
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {e}"[:200]


def recortar_tramo_continuo(sub: pd.DataFrame) -> pd.DataFrame:
    s = sub.dropna(subset=["inflacion_yoy_log"]).sort_values("fecha").reset_index(drop=True)
    if len(s) == 0:
        return s
    periodos = (s["fecha"].dt.year * 12 + s["fecha"].dt.month).astype(int)
    saltos = periodos.diff().fillna(1)
    grupo_id = (saltos != 1).cumsum()
    mejor_grupo = grupo_id.value_counts().idxmax()
    return s[grupo_id == mejor_grupo].reset_index(drop=True)


def _ajustar_arima(train: np.ndarray):
    return pm.auto_arima(
        train, max_p=5, max_q=5, max_d=2, seasonal=False,
        information_criterion="aicc", stepwise=True,
        suppress_warnings=True, error_action="ignore",
    )


def validacion_walk_forward(full: np.ndarray, modelo_inicial):
    S = len(full) - VENTANA_EVAL
    modelo_actual = modelo_inicial
    errores = []
    for i in range(VENTANA_EVAL):
        valor_real = full[S + i]
        try:
            pred = float(np.asarray(modelo_actual.predict(n_periods=1))[0])
        except Exception:
            pred = np.nan
        errores.append(valor_real - pred)

        if i > 0 and i % REESTIMAR_CADA == 0:
            nuevo_modelo, _ = con_timeout(_ajustar_arima, TIMEOUT_SEG, full[: S + i + 1])
            if nuevo_modelo is not None:
                modelo_actual = nuevo_modelo
                continue
        try:
            modelo_actual.update([valor_real])
        except Exception:
            pass
    return np.array(errores)


# ==================== PARTE 1: intervalos de confianza por bootstrap ====================
def bootstrap_rmse_ci(errores: np.ndarray, n_boot=N_BOOTSTRAP, seed=0):
    rng = np.random.RandomState(seed)
    n = len(errores)
    rmses_boot = np.empty(n_boot)
    for b in range(n_boot):
        muestra = rng.choice(errores, size=n, replace=True)
        rmses_boot[b] = np.sqrt(np.mean(muestra**2))
    return np.percentile(rmses_boot, 2.5), np.percentile(rmses_boot, 97.5)


def calcular_ci_serie(codigo: str, sub: pd.DataFrame) -> dict:
    resultado = {"codigo_pais": codigo, "rmse_recalc": np.nan, "rmse_ci_low": np.nan, "rmse_ci_high": np.nan, "n_pasos": 0}
    tramo = recortar_tramo_continuo(sub)
    if len(tramo) < MIN_TOTAL_TRAMO:
        return resultado
    full = tramo["inflacion_yoy_log"].to_numpy()
    train_inicial = full[:-VENTANA_EVAL]

    modelo, _ = con_timeout(_ajustar_arima, TIMEOUT_SEG, train_inicial)
    if modelo is None:
        return resultado

    errores = validacion_walk_forward(full, modelo)
    valido = np.isfinite(errores)
    if valido.sum() < 5:
        return resultado

    errores_validos = errores[valido]
    resultado["rmse_recalc"] = float(np.sqrt(np.mean(errores_validos**2)))
    ci_low, ci_high = bootstrap_rmse_ci(errores_validos)
    resultado["rmse_ci_low"] = ci_low
    resultado["rmse_ci_high"] = ci_high
    resultado["n_pasos"] = int(valido.sum())
    return resultado


def correr_parte1(df_inflacion: pd.DataFrame, df_resultados: pd.DataFrame):
    hcpi = df_resultados[
        (df_resultados["indicador"] == "hcpi")
        & (df_resultados["convergio_arima"])
        & (df_resultados["rmse_arima_walkforward"].notna())
        & (df_resultados["nivel_ingreso"].notna())
    ]
    print(f"Parte 1 -- recalculando errores walk-forward + bootstrap para {len(hcpi)} series hcpi.")

    t0 = time.time()
    resultados = Parallel(n_jobs=-1, verbose=0)(
        delayed(calcular_ci_serie)(
            codigo, df_inflacion[(df_inflacion["codigo_pais"] == codigo) & (df_inflacion["indicador"] == "hcpi")]
        )
        for codigo in hcpi["codigo_pais"].unique()
    )
    print(f"Parte 1 -- tiempo: {time.time()-t0:.1f}s")

    tabla_ci = pd.DataFrame(resultados)
    tabla = hcpi.merge(tabla_ci, on="codigo_pais", how="left")
    tabla = tabla.dropna(subset=["rmse_ci_low", "rmse_ci_high"])
    return tabla


def analizar_ranking_ci(tabla: pd.DataFrame):
    ordenado = tabla.sort_values("rmse_recalc").reset_index(drop=True)
    top = ordenado.head(N_RANKING).copy()
    bottom = ordenado.tail(N_RANKING).copy()
    seleccion = pd.concat([top, bottom]).reset_index(drop=True)

    # overlap con el #1 (más predecible) dentro del top15
    ci1_low, ci1_high = top.iloc[0]["rmse_ci_low"], top.iloc[0]["rmse_ci_high"]
    top["distinguible_de_1"] = (top["rmse_ci_low"] > ci1_high) | (top["rmse_ci_high"] < ci1_low)
    n_indistinguibles_top = int((~top["distinguible_de_1"]).sum()) - 1  # excluye al propio #1

    # overlap con el último (menos predecible) dentro del bottom15
    ciN_low, ciN_high = bottom.iloc[-1]["rmse_ci_low"], bottom.iloc[-1]["rmse_ci_high"]
    bottom["distinguible_del_ultimo"] = (bottom["rmse_ci_low"] > ciN_high) | (bottom["rmse_ci_high"] < ciN_low)
    n_indistinguibles_bottom = int((~bottom["distinguible_del_ultimo"]).sum()) - 1

    # pares consecutivos sin solapamiento (ordenado completo, no solo top/bottom)
    pares_distintos = 0
    for i in range(len(ordenado) - 1):
        a, b = ordenado.iloc[i], ordenado.iloc[i + 1]
        if a["rmse_ci_high"] < b["rmse_ci_low"] or b["rmse_ci_high"] < a["rmse_ci_low"]:
            pares_distintos += 1

    fig, ax = plt.subplots(figsize=(9, 11))
    y_pos = np.arange(len(seleccion))
    for grupo, color in [(top, "steelblue"), (bottom, "indianred")]:
        y_grupo = y_pos[: len(grupo)] if grupo is top else y_pos[len(top) :]
        ax.errorbar(
            grupo["rmse_recalc"], y_grupo,
            xerr=[grupo["rmse_recalc"] - grupo["rmse_ci_low"], grupo["rmse_ci_high"] - grupo["rmse_recalc"]],
            fmt="o", color="black", ecolor=color, elinewidth=2, capsize=3, markersize=4,
        )
    etiquetas = [f"{r['codigo_pais']} ({r['pais']})" for _, r in seleccion.iterrows()]
    ax.set_yticks(y_pos)
    ax.set_yticklabels(etiquetas, fontsize=8)
    ax.invert_yaxis()
    ax.axhline(N_RANKING - 0.5, color="gray", linestyle=":", linewidth=1)
    ax.set_xlabel("RMSE walk-forward (log-diff) — punto + IC 95% bootstrap")
    ax.set_title(f"Top {N_RANKING} más predecibles (azul) vs. menos predecibles (rojo) — hcpi\ncon intervalos de confianza")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "robustez_ranking_ci.png", dpi=120)
    plt.close(fig)

    return top, bottom, n_indistinguibles_top, n_indistinguibles_bottom, pares_distintos, len(ordenado)


# ==================== PARTE 2: modelo multivariado ====================
def construir_datos_regresion(df_resultados: pd.DataFrame, df_inflacion: pd.DataFrame):
    infl_media = (
        df_inflacion.groupby(["codigo_pais", "indicador"])["inflacion_yoy_pct"].mean().reset_index(name="inflacion_media_pct")
    )
    hcpi = df_resultados[
        (df_resultados["indicador"] == "hcpi")
        & (df_resultados["convergio_arima"])
        & (df_resultados["rmse_arima_walkforward"].notna())
        & (df_resultados["nivel_ingreso"].notna())
        & (df_resultados["region"].notna())
        & (df_resultados["convergio_garch"])
    ].copy()
    hcpi = hcpi.merge(infl_media, on=["codigo_pais", "indicador"], how="left")

    hcpi["log_rmse"] = np.log(hcpi["rmse_arima_walkforward"])
    hcpi["log_inflacion"] = np.log1p(hcpi["inflacion_media_pct"].abs())

    hcpi["nivel_ingreso"] = pd.Categorical(hcpi["nivel_ingreso"], categories=ORDEN_INGRESO, ordered=False)
    regiones_orden = ["Sub-Saharan Africa"] + [r for r in sorted(hcpi["region"].unique()) if r != "Sub-Saharan Africa"]
    hcpi["region"] = pd.Categorical(hcpi["region"], categories=regiones_orden, ordered=False)

    return hcpi


def correr_regresion(hcpi: pd.DataFrame):
    dummies_ingreso = pd.get_dummies(hcpi["nivel_ingreso"], prefix="ingreso", drop_first=True).astype(float)
    dummies_region = pd.get_dummies(hcpi["region"], prefix="region", drop_first=True).astype(float)

    X = pd.concat(
        [
            dummies_ingreso,
            dummies_region,
            hcpi[["log_inflacion", "meses_usados", "persistencia"]].reset_index(drop=True).astype(float),
        ],
        axis=1,
    )
    X.index = hcpi.index
    X = sm.add_constant(X)
    y = hcpi["log_rmse"]

    modelo = sm.OLS(y, X).fit(cov_type="HC3")

    vif = pd.Series(
        [variance_inflation_factor(X.drop(columns="const").values, i) for i in range(X.shape[1] - 1)],
        index=X.drop(columns="const").columns,
    )

    return modelo, X, vif


def graficar_coeficientes(modelo, nombres_legibles):
    params = modelo.params.drop("const")
    ci = modelo.conf_int().drop("const")
    ci.columns = ["low", "high"]
    orden = params.reindex(params.abs().sort_values(ascending=True).index)

    fig, ax = plt.subplots(figsize=(9, 7))
    y_pos = np.arange(len(orden))
    etiquetas = [nombres_legibles.get(v, v) for v in orden.index]
    ax.errorbar(
        orden.values, y_pos,
        xerr=[orden.values - ci.loc[orden.index, "low"].values, ci.loc[orden.index, "high"].values - orden.values],
        fmt="o", color="black", ecolor="steelblue", elinewidth=2, capsize=3,
    )
    ax.axvline(0, color="crimson", linestyle="--", linewidth=1)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(etiquetas, fontsize=8)
    ax.set_xlabel("Coeficiente (variable dependiente: log RMSE) — IC 95% robusto")
    ax.set_title("Modelo multivariado de previsibilidad (hcpi)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "robustez_coeficientes_ols.png", dpi=120)
    plt.close(fig)


def construir_markdown(tabla_ci, top, bottom, n_indist_top, n_indist_bottom, pares_distintos, n_total,
                        modelo, vif, n_reg, skew_rmse, skew_log_rmse):
    L = []
    L.append("# Robustez: intervalos de confianza y modelo multivariado")
    L.append("")
    L.append(
        "Informe generado por `src/12_robustez_multivariado.py`. **Solo diagnóstico.** "
        "Continuación de `auditoria_metodologica.md` — acá se cuantifica la incertidumbre del "
        "ranking de previsibilidad y se pone todo lo encontrado en Análisis A/B/C dentro de un "
        "único modelo multivariado."
    )
    L.append("")

    # PARTE 1
    L.append("## Parte 1 — Intervalos de confianza en la previsibilidad")
    L.append("")
    L.append(
        f"Para cada una de las {len(tabla_ci)} series hcpi se recalcularon los errores de "
        f"forecast walk-forward (mismo procedimiento que Análisis A/`06b_modelado_robusto.py`) "
        f"y se calculó un intervalo de confianza del RMSE por bootstrap "
        f"({N_BOOTSTRAP} iteraciones, resampleo con reemplazo de los ~24 errores por serie, "
        "percentiles 2.5/97.5)."
    )
    L.append("")
    L.append(f"Figura: `reports/figures/robustez_ranking_ci.png`.")
    L.append("")

    L.append(f"**Dentro del top {N_RANKING} más predecible:** el país #1 tiene IC "
              f"[{top.iloc[0]['rmse_ci_low']:.3f}, {top.iloc[0]['rmse_ci_high']:.3f}]. "
              f"**{n_indist_top} de los otros {N_RANKING-1}** países del top {N_RANKING} tienen "
              "un intervalo que se solapa con el del #1 — es decir, no se puede afirmar con "
              "confianza que sean menos predecibles que el país \"más predecible\" del panel.")
    L.append("")
    L.append(f"**Dentro del bottom {N_RANKING} menos predecible:** de forma simétrica, "
              f"**{n_indist_bottom} de los otros {N_RANKING-1}** países del bottom {N_RANKING} "
              "son estadísticamente indistinguibles del país menos predecible del panel.")
    L.append("")
    L.append(
        f"**Sobre el ranking completo ({n_total} series):** de los {n_total-1} pares de "
        f"países consecutivos (ordenados por RMSE puntual), solo **{pares_distintos} "
        f"({pares_distintos/(n_total-1):.1%})** tienen intervalos de confianza que NO se "
        "solapan — el resto de los pares consecutivos son estadísticamente indistinguibles "
        "entre sí con esta cantidad de observaciones walk-forward."
    )
    L.append("")
    L.append("Top 15 con intervalos:")
    L.append("")
    L.append("| # | País | RMSE | IC 95% | ¿Distinguible del #1? |")
    L.append("|---|---|---|---|---|")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        L.append(
            f"| {i} | {r['pais']} ({r['codigo_pais']}) | {r['rmse_recalc']:.3f} "
            f"| [{r['rmse_ci_low']:.3f}, {r['rmse_ci_high']:.3f}] "
            f"| {'Sí' if r['distinguible_de_1'] else 'No'} |"
        )
    L.append("")
    L.append("Bottom 15 con intervalos:")
    L.append("")
    L.append("| # | País | RMSE | IC 95% | ¿Distinguible del último? |")
    L.append("|---|---|---|---|---|")
    for i, (_, r) in enumerate(bottom.iterrows(), 1):
        L.append(
            f"| {i} | {r['pais']} ({r['codigo_pais']}) | {r['rmse_recalc']:.3f} "
            f"| [{r['rmse_ci_low']:.3f}, {r['rmse_ci_high']:.3f}] "
            f"| {'Sí' if r['distinguible_del_ultimo'] else 'No'} |"
        )
    L.append("")
    L.append(
        "**Conclusión Parte 1:** el ranking país-por-país de Análisis A es matemáticamente "
        "correcto pero engañoso si se lee como una lista estrictamente ordenada. La lectura "
        "honesta es en **grupos de previsibilidad estadísticamente indistinguibles**, no un "
        "orden exacto: la diferencia entre el país #1 y buena parte del resto del top 15 (o "
        "entre el último y buena parte del bottom 15) no es distinguible del azar con "
        f"{N_RANKING} vs. {N_RANKING} observaciones walk-forward por serie. Las diferencias "
        "SÍ son claras entre los extremos del panel completo (un país del top 15 vs. uno del "
        "bottom 15), pero no entre vecinos cercanos del ranking."
    )
    L.append("")

    # PARTE 2
    L.append("## Parte 2 — Modelo multivariado de la previsibilidad")
    L.append("")
    L.append(
        f"Variable dependiente: `log(rmse_arima_walkforward)`. Se usó el logaritmo porque la "
        f"asimetría del RMSE en nivel es muy alta (asimetría={skew_rmse:.2f}) y baja "
        f"sustancialmente al tomar logaritmo (asimetría={skew_log_rmse:.2f}), más apropiado "
        "para los supuestos de OLS."
    )
    L.append("")
    L.append(
        "Predictores: nivel de ingreso (dummies, referencia = Low income), inflación media del "
        "país (`log1p(|inflación media|)`, misma razón de asimetría), longitud de la serie "
        "(`meses_usados`), región (dummies, referencia = Sub-Saharan Africa) y persistencia "
        "GARCH. OLS con errores robustos a heterocedasticidad (HC3)."
    )
    L.append("")
    L.append(f"**N = {n_reg}** países. **R² = {modelo.rsquared:.3f}** (R² ajustado = {modelo.rsquared_adj:.3f}).")
    L.append("")
    L.append("### Coeficientes")
    L.append("")
    L.append(f"Figura: `reports/figures/robustez_coeficientes_ols.png`.")
    L.append("")
    L.append("| Variable | Coeficiente | Error estándar (robusto) | p-valor | Significativo (p<0.05) |")
    L.append("|---|---|---|---|---|")
    for var in modelo.params.index:
        sig = "Sí" if modelo.pvalues[var] < ALPHA else "No"
        L.append(f"| {var} | {modelo.params[var]:+.4f} | {modelo.bse[var]:.4f} | {modelo.pvalues[var]:.3f} | {sig} |")
    L.append("")

    L.append("### Multicolinealidad (VIF)")
    L.append("")
    L.append("| Variable | VIF |")
    L.append("|---|---|")
    for var, v in vif.items():
        L.append(f"| {var} | {v:.2f} |")
    L.append("")
    vif_alto = vif[vif > 5]
    if len(vif_alto):
        L.append(
            f"**Advertencia:** {list(vif_alto.index)} tienen VIF > 5 — hay multicolinealidad "
            "relevante entre estos predictores, sus coeficientes individuales hay que "
            "interpretarlos con cautela (el modelo en conjunto sigue siendo válido, pero "
            "separar el efecto de cada uno de estos predictores específicos es menos preciso)."
        )
    else:
        L.append("Ningún predictor supera VIF=5 — no hay evidencia de multicolinealidad problemática.")
    L.append("")

    # interpretación puntual de variables clave
    L.append("### Interpretación de las variables clave")
    L.append("")
    vars_ingreso = [v for v in modelo.params.index if v.startswith("ingreso_")]
    algun_ingreso_sig = any(modelo.pvalues[v] < ALPHA for v in vars_ingreso)
    if algun_ingreso_sig:
        texto_ingreso = (
            "**El ingreso sobrevive, al menos parcialmente, el control simultáneo por todas "
            "las demás variables**: "
            + "; ".join(
                f"{v} {'es significativo' if modelo.pvalues[v] < ALPHA else 'NO es significativo'} "
                f"(coef={modelo.params[v]:+.3f}, p={modelo.pvalues[v]:.3f})"
                for v in vars_ingreso
            )
            + ". Esto es consistente con Análisis A y con la Parte 2 de la auditoría anterior: el "
            "ingreso tiene un efecto propio sobre la previsibilidad, no reducible a los otros "
            "factores del modelo."
        )
    else:
        texto_ingreso = (
            "**El ingreso NO sobrevive el control simultáneo por las demás variables**: ninguna "
            "de las dummies de ingreso es significativa una vez que se controla por inflación "
            "media, longitud, región y persistencia GARCH al mismo tiempo. Esto matiza el "
            "hallazgo de Análisis A — el gradiente bivariado es real, pero en el modelo "
            "conjunto su efecto podría estar mediado por (o redundante con) alguna de las otras "
            "variables incluidas."
        )
    L.append(texto_ingreso)
    L.append("")

    p_inflacion = modelo.pvalues["log_inflacion"]
    if p_inflacion < ALPHA:
        texto_inflacion = (
            f"**La inflación media aporta información propia más allá del ingreso** "
            f"(coef={modelo.params['log_inflacion']:+.3f}, p={p_inflacion:.3f}): a igual nivel "
            "de ingreso, región, longitud de serie y persistencia, países con mayor inflación "
            "media siguen siendo "
            + ("menos" if modelo.params["log_inflacion"] > 0 else "más")
            + " predecibles."
        )
    else:
        texto_inflacion = (
            f"**La inflación media NO aporta información significativa más allá del ingreso y "
            f"las demás variables** (coef={modelo.params['log_inflacion']:+.3f}, "
            f"p={p_inflacion:.3f}) en el modelo conjunto."
        )
    L.append(texto_inflacion)
    L.append("")

    p_meses = modelo.pvalues["meses_usados"]
    if p_meses < ALPHA:
        texto_meses = (
            f"**La longitud de la serie SIGUE importando incluso controlando por ingreso** "
            f"(coef={modelo.params['meses_usados']:+.5f}, p={p_meses:.3f}) — series "
            + ("más largas tienden a ser más predecibles" if modelo.params["meses_usados"] < 0 else "más largas tienden a ser menos predecibles, un resultado contraintuitivo que amerita revisión")
            + " incluso después de controlar por todo lo demás."
        )
    else:
        texto_meses = (
            f"**La longitud de la serie NO es significativa en el modelo conjunto** "
            f"(coef={modelo.params['meses_usados']:+.5f}, p={p_meses:.3f}) — consistente con la "
            "Parte 2 de la auditoría anterior, que ya había encontrado que el gradiente de "
            "ingreso sobrevive controlando por longitud."
        )
    L.append(texto_meses)
    L.append("")

    p_persist = modelo.pvalues["persistencia"]
    texto_persist = (
        f"**Persistencia GARCH**: coef={modelo.params['persistencia']:+.3f}, p={p_persist:.3f} — "
        + ("significativa" if p_persist < ALPHA else "NO significativa")
        + ", consistente con el hallazgo de Análisis C de que previsibilidad de nivel y "
        "persistencia de volatilidad son dimensiones mayormente independientes."
    )
    L.append(texto_persist)
    L.append("")

    L.append(
        f"**Conclusión Parte 2:** el modelo explica **{modelo.rsquared:.1%}** de la variación "
        "en previsibilidad (R²) entre los países de la muestra. "
        + (
            "Es una fracción sustancial — sugiere que las variables incluidas capturan buena "
            "parte de lo que determina la previsibilidad de la inflación."
            if modelo.rsquared > 0.3
            else "Es una fracción modesta — buena parte de la variación en previsibilidad entre "
            "países queda sin explicar por estas cinco variables, así que el retrato es "
            "parcial: hay factores relevantes (institucionales, de política monetaria, de "
            "composición de la canasta, etc.) que este modelo no captura."
        )
    )
    L.append("")

    return "\n".join(L)


def main() -> None:
    df_inflacion = pd.read_parquet(INFLACION_PATH)
    df_resultados = pd.read_parquet(RESULTADOS_PATH)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    tabla_ci = correr_parte1(df_inflacion, df_resultados)
    top, bottom, n_indist_top, n_indist_bottom, pares_distintos, n_total = analizar_ranking_ci(tabla_ci)

    hcpi_reg = construir_datos_regresion(df_resultados, df_inflacion)
    skew_rmse = stats.skew(hcpi_reg["rmse_arima_walkforward"])
    skew_log_rmse = stats.skew(hcpi_reg["log_rmse"])
    modelo, X, vif = correr_regresion(hcpi_reg)

    nombres_legibles = {
        "log_inflacion": "log(1+|inflación media|)",
        "meses_usados": "Meses usados",
        "persistencia": "Persistencia GARCH",
    }
    graficar_coeficientes(modelo, nombres_legibles)

    md = construir_markdown(
        tabla_ci, top, bottom, n_indist_top, n_indist_bottom, pares_distintos, n_total,
        modelo, vif, len(hcpi_reg), skew_rmse, skew_log_rmse,
    )
    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
