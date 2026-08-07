"""Auditoría metodológica — SOLO DIAGNÓSTICO, no modifica el pipeline.

PARTE 1: mide el impacto de un posible data leakage en la selección de
orden (p,d,q) de auto_arima (¿AICc calculado viendo el período de
evaluación?).

PARTE 2: mide si el gradiente ingreso→previsibilidad reportado en
Análisis A es economía real o un artefacto de que los países ricos
tienen series más largas.

Conclusiones condicionadas al resultado real de cada test (lección de los
Análisis A/B/C).
"""

import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

import numpy as np
import pandas as pd
import pmdarima as pm
from joblib import Parallel, delayed
from scipy import stats

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
INFLACION_PATH = ROOT / "data" / "processed" / "inflacion_mensual_completa_v2.parquet"
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"
REPORT_PATH = ROOT / "reports" / "auditoria_metodologica.md"

# Mismos parámetros que src/06b_modelado_robusto.py, reutilizados acá para
# poder reproducir/perturbar el mismo procedimiento.
VENTANA_EVAL = 24
REESTIMAR_CADA = 6
MIN_TOTAL_TRAMO = 48
TIMEOUT_SEG = 60
ALPHA = 0.05

ORDEN_INGRESO = ["Low income", "Lower middle income", "Upper middle income", "High income"]
ORDINAL_INGRESO = {n: i for i, n in enumerate(ORDEN_INGRESO)}

N_MUESTRA_POR_INGRESO = 12  # Parte 1: ~12 x 4 = hasta 48 series
N_TRUNC = 48  # Parte 2: longitud común para el chequeo de robustez por truncamiento


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


def _ajustar_arima_orden_fijo(train: np.ndarray, orden):
    modelo = pm.ARIMA(order=orden, suppress_warnings=True)
    modelo.fit(train)
    return modelo


def validacion_walk_forward(full: np.ndarray, modelo_inicial):
    """Idéntica a la de 06b_modelado_robusto.py: cada paso revela un dato
    real y solo usa lo revelado hasta ese momento (nunca datos futuros) —
    tanto para (a) como para (b) de la Parte 1, así el único factor que
    cambia entre ambas es cómo se obtuvo el modelo INICIAL."""
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


# ==================== PARTE 1: leakage en selección de orden ====================
def auditar_leakage_serie(codigo: str, indicador: str, sub: pd.DataFrame) -> dict:
    resultado = {
        "codigo_pais": codigo, "indicador": indicador,
        "orden_correcto": None, "orden_leak": None, "orden_distinto": None,
        "rmse_correcto": np.nan, "rmse_leak": np.nan,
    }
    tramo = recortar_tramo_continuo(sub)
    if len(tramo) < MIN_TOTAL_TRAMO:
        return resultado

    full = tramo["inflacion_yoy_log"].to_numpy()
    train_inicial = full[:-VENTANA_EVAL]

    # (b) correcto: orden elegido SOLO con datos de entrenamiento (lo que ya hace el pipeline)
    modelo_correcto, _ = con_timeout(_ajustar_arima, TIMEOUT_SEG, train_inicial)
    if modelo_correcto is None:
        return resultado
    resultado["orden_correcto"] = modelo_correcto.order

    # (a) con leakage: orden elegido viendo TODA la serie (incluye el período de evaluación),
    # pero los PARÁMETROS para arrancar el walk-forward se ajustan solo con train_inicial --
    # así se aísla el efecto de "qué orden se habría elegido" del efecto de "con qué datos se
    # calibran los parámetros", que ya sabemos que no debe incluir el futuro.
    modelo_full, _ = con_timeout(_ajustar_arima, TIMEOUT_SEG, full)
    if modelo_full is None:
        return resultado
    orden_leak = modelo_full.order
    resultado["orden_leak"] = orden_leak
    resultado["orden_distinto"] = orden_leak != modelo_correcto.order

    modelo_leak_train, _ = con_timeout(_ajustar_arima_orden_fijo, TIMEOUT_SEG, train_inicial, orden_leak)
    if modelo_leak_train is None:
        return resultado

    err_correcto = validacion_walk_forward(full, modelo_correcto)
    err_leak = validacion_walk_forward(full, modelo_leak_train)

    valido = np.isfinite(err_correcto) & np.isfinite(err_leak)
    if valido.sum() == 0:
        return resultado

    resultado["rmse_correcto"] = float(np.sqrt(np.mean(err_correcto[valido] ** 2)))
    resultado["rmse_leak"] = float(np.sqrt(np.mean(err_leak[valido] ** 2)))
    return resultado


def correr_parte1(df_inflacion: pd.DataFrame, df_resultados: pd.DataFrame):
    hcpi = df_resultados[
        (df_resultados["indicador"] == "hcpi")
        & (df_resultados["convergio_arima"])
        & (df_resultados["nivel_ingreso"].notna())
    ]
    muestra_codigos = []
    rng = np.random.RandomState(42)
    for nivel in ORDEN_INGRESO:
        codigos_nivel = hcpi.loc[hcpi["nivel_ingreso"] == nivel, "codigo_pais"].unique()
        n = min(N_MUESTRA_POR_INGRESO, len(codigos_nivel))
        elegidos = rng.choice(codigos_nivel, size=n, replace=False)
        muestra_codigos.extend(elegidos.tolist())

    print(f"Parte 1 -- muestra de {len(muestra_codigos)} países (hcpi).")

    grupos = []
    for codigo in muestra_codigos:
        sub = df_inflacion[(df_inflacion["codigo_pais"] == codigo) & (df_inflacion["indicador"] == "hcpi")]
        if not sub.empty:
            grupos.append((codigo, sub))

    t0 = time.time()
    resultados = Parallel(n_jobs=-1, verbose=0)(
        delayed(auditar_leakage_serie)(codigo, "hcpi", sub) for codigo, sub in grupos
    )
    tiempo = time.time() - t0
    print(f"Parte 1 -- tiempo: {tiempo:.1f}s")

    tabla = pd.DataFrame(resultados)
    tabla = tabla.dropna(subset=["rmse_correcto", "rmse_leak"])
    return tabla


def analizar_parte1(tabla: pd.DataFrame):
    n = len(tabla)
    n_orden_distinto = int(tabla["orden_distinto"].sum())
    tabla["diff_rmse"] = tabla["rmse_leak"] - tabla["rmse_correcto"]
    tabla["diff_rmse_pct"] = tabla["diff_rmse"] / tabla["rmse_correcto"]

    if n >= 5:
        stat, p_wilcoxon = stats.wilcoxon(tabla["rmse_leak"], tabla["rmse_correcto"])
    else:
        stat, p_wilcoxon = np.nan, np.nan

    r_ranking, p_ranking = stats.spearmanr(tabla["rmse_correcto"], tabla["rmse_leak"])

    return {
        "n": n,
        "n_orden_distinto": n_orden_distinto,
        "pct_orden_distinto": n_orden_distinto / n if n else np.nan,
        "diff_rmse_mediana": tabla["diff_rmse"].median(),
        "diff_rmse_pct_mediana": tabla["diff_rmse_pct"].median(),
        "stat_wilcoxon": stat,
        "p_wilcoxon": p_wilcoxon,
        "r_ranking": r_ranking,
        "p_ranking": p_ranking,
        "tabla": tabla,
    }


# ==================== PARTE 2: longitud como confusor ====================
def correr_parte2_correlaciones(df_resultados: pd.DataFrame):
    hcpi = df_resultados[
        (df_resultados["indicador"] == "hcpi")
        & (df_resultados["convergio_arima"])
        & (df_resultados["rmse_arima_walkforward"].notna())
        & (df_resultados["nivel_ingreso"].notna())
    ].copy()
    hcpi["ingreso_ordinal"] = hcpi["nivel_ingreso"].map(ORDINAL_INGRESO)

    x = hcpi["ingreso_ordinal"]
    y = hcpi["rmse_arima_walkforward"]
    z = hcpi["meses_usados"]

    r_xz, p_xz = stats.spearmanr(x, z)  # ingreso vs longitud
    r_zy, p_zy = stats.spearmanr(z, y)  # longitud vs RMSE
    r_xy, p_xy = stats.spearmanr(x, y)  # ingreso vs RMSE (ya visto en Análisis A)

    denom = np.sqrt((1 - r_xz**2) * (1 - r_zy**2))
    r_parcial = (r_xy - r_xz * r_zy) / denom if denom > 0 else np.nan
    n = len(hcpi)
    df_t = n - 3
    if pd.notna(r_parcial) and abs(r_parcial) < 1:
        t_stat = r_parcial * np.sqrt(df_t / (1 - r_parcial**2))
        p_parcial = 2 * stats.t.sf(abs(t_stat), df_t)
    else:
        p_parcial = np.nan

    return {
        "n": n, "r_xz": r_xz, "p_xz": p_xz, "r_zy": r_zy, "p_zy": p_zy,
        "r_xy": r_xy, "p_xy": p_xy, "r_parcial": r_parcial, "p_parcial": p_parcial,
        "hcpi": hcpi,
    }


def truncar_y_modelar(codigo: str, sub: pd.DataFrame) -> dict:
    resultado = {"codigo_pais": codigo, "rmse_trunc": np.nan, "convergio": False}
    tramo = recortar_tramo_continuo(sub)
    if len(tramo) < N_TRUNC:
        return resultado
    tramo_trunc = tramo.tail(N_TRUNC).reset_index(drop=True)
    full = tramo_trunc["inflacion_yoy_log"].to_numpy()
    train_inicial = full[:-VENTANA_EVAL]

    modelo, _ = con_timeout(_ajustar_arima, TIMEOUT_SEG, train_inicial)
    if modelo is None:
        return resultado

    errores = validacion_walk_forward(full, modelo)
    valido = np.isfinite(errores)
    if valido.sum() == 0:
        return resultado

    resultado["rmse_trunc"] = float(np.sqrt(np.mean(errores[valido] ** 2)))
    resultado["convergio"] = True
    return resultado


def correr_parte2_truncamiento(df_inflacion: pd.DataFrame, df_resultados: pd.DataFrame):
    hcpi = df_resultados[
        (df_resultados["indicador"] == "hcpi")
        & (df_resultados["convergio_arima"])
        & (df_resultados["nivel_ingreso"].notna())
        & (df_resultados["meses_usados"] >= N_TRUNC)
    ]
    print(f"Parte 2 (truncamiento a {N_TRUNC} meses) -- {len(hcpi)} países.")

    grupos = []
    for codigo in hcpi["codigo_pais"].unique():
        sub = df_inflacion[(df_inflacion["codigo_pais"] == codigo) & (df_inflacion["indicador"] == "hcpi")]
        if not sub.empty:
            grupos.append(codigo)

    t0 = time.time()
    resultados = Parallel(n_jobs=-1, verbose=0)(
        delayed(truncar_y_modelar)(
            codigo, df_inflacion[(df_inflacion["codigo_pais"] == codigo) & (df_inflacion["indicador"] == "hcpi")]
        )
        for codigo in grupos
    )
    tiempo = time.time() - t0
    print(f"Parte 2 (truncamiento) -- tiempo: {tiempo:.1f}s")

    tabla = pd.DataFrame(resultados)
    tabla = tabla[tabla["convergio"]].merge(
        hcpi[["codigo_pais", "nivel_ingreso"]], on="codigo_pais", how="left"
    )
    return tabla


def analizar_parte2_truncamiento(tabla: pd.DataFrame):
    grupos = [tabla.loc[tabla["nivel_ingreso"] == n, "rmse_trunc"].dropna() for n in ORDEN_INGRESO]
    grupos = [g for g in grupos if len(g) >= 3]
    if len(grupos) >= 2:
        h_stat, p_valor = stats.kruskal(*grupos)
    else:
        h_stat, p_valor = np.nan, np.nan
    medianas = tabla.groupby("nivel_ingreso", observed=True)["rmse_trunc"].median().reindex(ORDEN_INGRESO)
    return h_stat, p_valor, medianas


# ==================== reporte ====================
def construir_markdown(res1, res2_corr, tabla_trunc, h_trunc, p_trunc, medianas_trunc, medianas_originales):
    L = []
    L.append("# Auditoría metodológica")
    L.append("")
    L.append(
        "Informe generado por `src/11_auditoria_metodologica.py`. **Solo diagnóstico: no se "
        "modificó ningún script del pipeline de modelado ni de análisis existente.** Objetivo: "
        "medir el impacto de dos debilidades metodológicas identificadas, no asumirlas ni "
        "descartarlas de antemano."
    )
    L.append("")

    # PARTE 1
    L.append("## Parte 1 — Leakage en selección de orden ARIMA")
    L.append("")
    L.append(
        "**Diseño del experimento:** para cada serie de la muestra se comparan dos formas de "
        "elegir el orden (p,d,q) inicial: **(a) con leakage** — `auto_arima` corre viendo la "
        "serie completa, incluyendo los 24 meses que después se usan para evaluar — vs. "
        "**(b) correcto** — `auto_arima` corre solo con los datos anteriores a esos 24 meses "
        "(lo que ya hace `06b_modelado_robusto.py`). En ambos casos, los **parámetros** del "
        "modelo inicial se calibran solo con datos de entrenamiento (nunca con el futuro), y "
        "el walk-forward posterior es idéntico en los dos casos (mismas re-estimaciones cada "
        f"{REESTIMAR_CADA} pasos, usando en cada paso solo lo revelado hasta ese momento) — "
        "así se aísla específicamente el efecto de qué orden se elige, no otra cosa."
    )
    L.append("")
    L.append(f"Muestra: **{res1['n']} países** (hcpi, estratificado por nivel de ingreso).")
    L.append("")
    L.append(
        f"- Orden (p,d,q) distinto entre (a) y (b): **{res1['n_orden_distinto']} de {res1['n']} "
        f"series ({res1['pct_orden_distinto']:.1%})**."
    )
    L.append(
        f"- Diferencia de RMSE walk-forward (leak − correcto), mediana: "
        f"**{res1['diff_rmse_mediana']:+.4f}** ({res1['diff_rmse_pct_mediana']:+.1%} relativo)."
    )
    L.append("")
    if pd.notna(res1["p_wilcoxon"]):
        L.append(
            f"**Test de Wilcoxon signed-rank** (H0: no hay diferencia sistemática entre RMSE "
            f"con leakage y sin leakage): estadístico={res1['stat_wilcoxon']:.1f}, "
            f"p={res1['p_wilcoxon']:.2e}."
        )
        L.append("")
        if res1["p_wilcoxon"] < ALPHA:
            direccion = "más bajo (mejor)" if res1["diff_rmse_mediana"] < 0 else "más alto (peor)"
            L.append(
                f"**El leakage tiene un efecto sistemático y estadísticamente significativo**: "
                f"con leakage el RMSE walk-forward sale {direccion} de forma consistente. Esto "
                "significa que las cifras de RMSE reportadas en Análisis A/B/C podrían estar "
                "sesgadas por este efecto, y ameritaría re-correr el modelado completo con la "
                "selección de orden corregida antes de confiar en comparaciones finas entre "
                "países."
            )
        else:
            L.append(
                "**El leakage NO tiene un efecto sistemático y estadísticamente significativo** "
                "sobre el RMSE en esta muestra — aunque el orden elegido cambia en algunos "
                "casos, el impacto en la métrica de previsibilidad walk-forward no es "
                "distinguible de cero. Esto es consistente con que, en el pipeline real "
                "(`06b_modelado_robusto.py`), la selección de orden **ya excluye** la ventana "
                "de evaluación desde el arranque (`train_inicial = full[:-VENTANA_EVAL]`) — el "
                "leakage que se está midiendo acá es un escenario contrafáctico (\"qué pasaría "
                "si no lo hubiéramos excluido\"), no algo presente en los resultados ya "
                "reportados."
            )
    L.append("")
    L.append(
        f"**Impacto en el ranking entre países:** correlación de Spearman entre el RMSE "
        f"correcto y el RMSE con leakage: ρ={res1['r_ranking']:.3f} (p={res1['p_ranking']:.2e})."
    )
    L.append("")
    if res1["r_ranking"] > 0.9:
        L.append(
            "El ranking de países por previsibilidad es prácticamente idéntico con o sin "
            "leakage — aunque el leakage moviera el RMSE puntual de algunas series, no "
            "reordena de forma relevante qué países son más o menos predecibles entre sí."
        )
    else:
        L.append(
            "El ranking de países cambia de forma no trivial entre ambos escenarios — el "
            "leakage no es solo un desplazamiento uniforme del RMSE, también afecta el orden "
            "relativo entre países, lo cual es más preocupante para conclusiones tipo "
            "\"ranking de previsibilidad\" (Análisis A, sección 1)."
        )
    L.append("")

    peores = res1["tabla"].reindex(res1["tabla"]["diff_rmse_pct"].abs().sort_values(ascending=False).index).head(10)
    L.append("Las 10 series donde más cambia el RMSE (valor absoluto relativo):")
    L.append("")
    L.append("| País | Orden correcto | Orden leak | RMSE correcto | RMSE leak | Diff % |")
    L.append("|---|---|---|---|---|---|")
    for _, r in peores.iterrows():
        L.append(
            f"| {r['codigo_pais']} | {r['orden_correcto']} | {r['orden_leak']} "
            f"| {r['rmse_correcto']:.4f} | {r['rmse_leak']:.4f} | {r['diff_rmse_pct']:+.1%} |"
        )
    L.append("")

    conclusion_p1 = (
        "**el leakage es una preocupación real y hay que rehacer el modelado** con la "
        "selección de orden corregida antes de confiar en los análisis A/B/C tal como están."
        if pd.notna(res1["p_wilcoxon"]) and res1["p_wilcoxon"] < ALPHA
        else "**el leakage descrito no está presente en el pipeline que efectivamente generó "
        "los resultados usados en Análisis A/B/C** (`06b_modelado_robusto.py` ya excluye la "
        "ventana de evaluación de la selección de orden) — el experimento contrafáctico de "
        "esta auditoría no encuentra evidencia de que hacerlo mal (a propósito, como "
        "comparación) cambiaría las conclusiones de forma sistemática. No hace falta rehacer "
        "el modelado por este motivo."
    )
    L.append(f"**Conclusión Parte 1:** {conclusion_p1}")
    L.append("")

    # PARTE 2
    L.append("## Parte 2 — Longitud de serie como confusor del gradiente de ingreso")
    L.append("")
    L.append(f"Sobre las {res2_corr['n']} series hcpi con clasificación válida:")
    L.append("")
    L.append(
        f"- Correlación **nivel de ingreso ↔ meses_usados**: ρ={res2_corr['r_xz']:.3f}, "
        f"p={res2_corr['p_xz']:.2e}."
    )
    L.append(
        f"- Correlación **meses_usados ↔ RMSE**: ρ={res2_corr['r_zy']:.3f}, "
        f"p={res2_corr['p_zy']:.2e}."
    )
    L.append(
        f"- Correlación **nivel de ingreso ↔ RMSE** (ya visto en Análisis A): "
        f"ρ={res2_corr['r_xy']:.3f}, p={res2_corr['p_xy']:.2e}."
    )
    L.append("")
    L.append(
        f"**La prueba clave — correlación parcial ingreso↔RMSE controlando por meses_usados:** "
        f"ρ parcial={res2_corr['r_parcial']:.3f}, p={res2_corr['p_parcial']:.2e}."
    )
    L.append("")
    if res2_corr["p_parcial"] < ALPHA:
        veredicto_parcial = (
            "**El gradiente de ingreso SOBREVIVE al controlar por longitud de serie** — "
            "sigue siendo significativo incluso descontando el efecto de que los países ricos "
            "tienen series más largas. Es evidencia a favor de que el hallazgo de Análisis A "
            "es economía real, no un artefacto de cantidad de datos."
        )
    else:
        veredicto_parcial = (
            "**El gradiente de ingreso NO sobrevive al controlar por longitud de serie** — "
            "la correlación parcial pierde significancia estadística. Esto es evidencia de que "
            "el hallazgo de Análisis A podría estar, al menos en parte, confundido por la "
            "longitud de las series disponibles, no ser puramente economía real."
        )
    L.append(veredicto_parcial)
    L.append("")

    L.append(
        f"**Chequeo de robustez — mismo largo para todos:** se truncó cada serie hcpi a los "
        f"últimos {N_TRUNC} meses (el piso mínimo real de la muestra) y se re-corrió "
        "`auto_arima` + walk-forward desde cero sobre esa versión truncada, así todos los "
        "países entran al test de Kruskal-Wallis con exactamente la misma cantidad de datos."
    )
    L.append("")
    L.append(f"N series con {N_TRUNC} meses o más: **{len(tabla_trunc)}**.")
    L.append("")
    L.append("RMSE mediano por nivel de ingreso, serie completa vs. truncada a longitud común:")
    L.append("")
    L.append("| Nivel de ingreso | RMSE mediano (serie completa) | RMSE mediano (truncada) |")
    L.append("|---|---|---|")
    for nivel in ORDEN_INGRESO:
        v_orig = medianas_originales.get(nivel, np.nan)
        v_trunc = medianas_trunc.get(nivel, np.nan)
        L.append(f"| {nivel} | {v_orig:.4f} | {v_trunc:.4f} |" if pd.notna(v_orig) and pd.notna(v_trunc) else f"| {nivel} | - | - |")
    L.append("")
    if pd.notna(p_trunc):
        L.append(f"**Kruskal-Wallis sobre la muestra truncada**: H={h_trunc:.2f}, p={p_trunc:.2e}.")
        L.append("")
        if p_trunc < ALPHA:
            L.append(
                "**El gradiente de ingreso persiste incluso con longitud de serie idéntica "
                "para todos los países** — confirmación adicional, independiente de la "
                "correlación parcial, de que el hallazgo de Análisis A es real."
            )
        else:
            L.append(
                "**El gradiente de ingreso desaparece cuando se controla la longitud por "
                "truncamiento** — con la misma cantidad de datos para todos, no se puede "
                "confirmar que el nivel de ingreso siga explicando diferencias de "
                "previsibilidad. Esto refuerza la posibilidad de que el hallazgo de Análisis A "
                "estuviera parcialmente confundido por longitud de serie."
            )
    L.append("")

    veredicto_final_real = (
        pd.notna(res2_corr["p_parcial"]) and res2_corr["p_parcial"] < ALPHA
    ) and (pd.notna(p_trunc) and p_trunc < ALPHA)
    veredicto_final_artefacto = (
        pd.notna(res2_corr["p_parcial"]) and res2_corr["p_parcial"] >= ALPHA
    ) and (pd.notna(p_trunc) and p_trunc >= ALPHA)

    if veredicto_final_real:
        conclusion_p2 = (
            "**ambos chequeos (correlación parcial y truncamiento) coinciden en que el "
            "gradiente de ingreso es real, no un artefacto de longitud de serie.** El hallazgo "
            "central de Análisis A se sostiene."
        )
    elif veredicto_final_artefacto:
        conclusion_p2 = (
            "**ambos chequeos coinciden en que el gradiente de ingreso NO sobrevive al "
            "controlar por longitud de serie.** El hallazgo central de Análisis A está, con "
            "esta evidencia, mejor explicado como un artefacto de que los países ricos tienen "
            "series más largas que como una diferencia real de previsibilidad económica — "
            "ameritaría revisar la sección 2 de Análisis A."
        )
    else:
        conclusion_p2 = (
            "**los dos chequeos no coinciden entre sí** (uno sugiere que el gradiente es real, "
            "el otro que no) — la evidencia es mixta y no permite una conclusión firme y única "
            "sobre si el gradiente de ingreso es economía real o un artefacto de longitud de "
            "serie. Ameritaría un chequeo adicional (ej. con otro método de control como una "
            "regresión múltiple explícita) antes de tomar una postura."
        )
    L.append(f"**Conclusión Parte 2:** {conclusion_p2}")
    L.append("")

    return "\n".join(L)


def main() -> None:
    df_inflacion = pd.read_parquet(INFLACION_PATH)
    df_resultados = pd.read_parquet(RESULTADOS_PATH)

    tabla1 = correr_parte1(df_inflacion, df_resultados)
    res1 = analizar_parte1(tabla1)

    res2_corr = correr_parte2_correlaciones(df_resultados)
    medianas_originales = res2_corr["hcpi"].groupby("nivel_ingreso", observed=True)["rmse_arima_walkforward"].median().reindex(ORDEN_INGRESO)

    tabla_trunc = correr_parte2_truncamiento(df_inflacion, df_resultados)
    h_trunc, p_trunc, medianas_trunc = analizar_parte2_truncamiento(tabla_trunc)

    md = construir_markdown(res1, res2_corr, tabla_trunc, h_trunc, p_trunc, medianas_trunc, medianas_originales)
    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
