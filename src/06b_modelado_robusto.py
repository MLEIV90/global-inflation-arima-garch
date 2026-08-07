"""Pipeline de modelado ARIMA + GARCH — versión robusta.

Mismo diseño que src/06_modelado_arima_garch.py (mismo universo de series,
mismos rangos de búsqueda, mismo GARCH sobre residuos, mismo manejo de
fallos/timeout/paralelización), con dos mejoras a la evaluación de
previsibilidad:

1. Validación walk-forward: en vez de un solo corte de 12 meses, se evalúa
   sobre una ventana de VENTANA_EVAL meses, avanzando el origen del
   pronóstico de a un mes y re-estimando el orden del modelo completo cada
   REESTIMAR_CADA pasos (entre re-estimaciones, se actualizan los
   parámetros con `ARIMA.update()`, mucho más barato que un re-search).
2. Baseline ingenuo (random walk: "el próximo valor = el último
   observado") evaluado sobre las mismas ventanas, para poder comparar
   rmse_arima vs rmse_naive — la prueba de honestidad de si el modelo
   aporta algo sobre lo trivial.
"""

import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

import numpy as np
import pandas as pd
import pmdarima as pm
from arch import arch_model
from joblib import Parallel, delayed
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import pacf

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "inflacion_mensual_completa_v2.parquet"
OUT_PATH = ROOT / "data" / "processed" / "resultados_modelos_robusto.parquet"

VENTANA_EVAL = 24  # meses de validación walk-forward (rango sugerido: 24-36)
REESTIMAR_CADA = 6  # re-buscar (p,d,q) cada N pasos; el resto, solo .update()
MIN_TRAIN_INICIAL = 24  # mínimo de historia antes de arrancar el walk-forward
MIN_TOTAL_TRAMO = VENTANA_EVAL + MIN_TRAIN_INICIAL  # 48
TIMEOUT_SEG = 60


def con_timeout(func, timeout_seg, *args, **kwargs):
    """Igual que en 06_modelado_arima_garch.py: ThreadPoolExecutor en vez de
    signal.alarm porque este último no existe en Windows."""
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


def detectar_estacionalidad(serie: pd.Series) -> bool:
    if len(serie) < 30:
        return False
    try:
        vals = pacf(serie, nlags=12, method="ywm")
    except Exception:
        return False
    banda = 1.96 / np.sqrt(len(serie))
    return bool(abs(vals[12]) > banda)


def _ajustar_arima(train: np.ndarray):
    return pm.auto_arima(
        train,
        max_p=5,
        max_q=5,
        max_d=2,
        seasonal=False,
        information_criterion="aicc",
        stepwise=True,
        suppress_warnings=True,
        error_action="ignore",
    )


def _ajustar_garch(resid: np.ndarray):
    modelo = arch_model(resid, vol="Garch", p=1, q=1, rescale=True)
    return modelo.fit(disp="off")


def r2_score_simple(actual: np.ndarray, fitted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    fitted = np.asarray(fitted, dtype=float)
    n = min(len(actual), len(fitted))
    actual, fitted = actual[-n:], fitted[-n:]
    ss_res = np.sum((actual - fitted) ** 2)
    ss_tot = np.sum((actual - actual.mean()) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan


def validacion_walk_forward(full: np.ndarray, modelo_inicial):
    """Walk-forward de 1 paso sobre los últimos VENTANA_EVAL valores de
    `full`, re-estimando el orden cada REESTIMAR_CADA pasos y actualizando
    parámetros (`.update`) en los pasos intermedios. Devuelve arrays de
    errores ARIMA y naive (mismo largo, NaN filtrado antes de promediar)."""
    S = len(full) - VENTANA_EVAL
    modelo_actual = modelo_inicial
    errores_arima, errores_naive = [], []

    for i in range(VENTANA_EVAL):
        valor_real = full[S + i]
        valor_anterior = full[S + i - 1]

        try:
            pred = modelo_actual.predict(n_periods=1)
            pred_arima = float(np.asarray(pred)[0])
        except Exception:
            pred_arima = np.nan

        errores_arima.append(valor_real - pred_arima)
        errores_naive.append(valor_real - valor_anterior)

        # revelar el dato real y refrescar el modelo antes del próximo paso
        if i > 0 and i % REESTIMAR_CADA == 0:
            nuevo_modelo, _ = con_timeout(_ajustar_arima, TIMEOUT_SEG, full[: S + i + 1])
            if nuevo_modelo is not None:
                modelo_actual = nuevo_modelo
                continue
        try:
            modelo_actual.update([valor_real])
        except Exception:
            pass  # si falla el update, se sigue con el modelo tal cual para el próximo paso

    return np.array(errores_arima), np.array(errores_naive)


def procesar_serie(codigo: str, indicador: str, sub: pd.DataFrame) -> dict:
    pais = sub["pais"].iloc[0]
    es_apto_garch = bool(sub["apto_garch"].iloc[0])

    resultado = {
        "codigo_pais": codigo,
        "indicador": indicador,
        "pais": pais,
        "meses_usados": 0,
        "estacionalidad_detectada": False,
        "convergio_arima": False,
        "motivo_fallo_arima": None,
        "orden_p": np.nan,
        "orden_d": np.nan,
        "orden_q": np.nan,
        "aicc": np.nan,
        "r2_in_sample": np.nan,
        "ljung_box_p": np.nan,
        "n_pasos_walkforward": 0,
        "rmse_arima_walkforward": np.nan,
        "rmse_naive_walkforward": np.nan,
        "ratio_vs_naive": np.nan,
        "arima_supera_naive": False,
        "std_error_walkforward": np.nan,
        "convergio_garch": False,
        "motivo_fallo_garch": None,
        "omega": np.nan,
        "alpha": np.nan,
        "beta": np.nan,
        "persistencia": np.nan,
    }

    tramo = recortar_tramo_continuo(sub)
    resultado["meses_usados"] = len(tramo)

    if len(tramo) < MIN_TOTAL_TRAMO:
        resultado["motivo_fallo_arima"] = f"datos_insuficientes (tramo continuo={len(tramo)}<{MIN_TOTAL_TRAMO})"
        resultado["motivo_fallo_garch"] = "sin_residuos_arima"
        return resultado

    resultado["estacionalidad_detectada"] = detectar_estacionalidad(tramo["inflacion_yoy_log"])

    full = tramo["inflacion_yoy_log"].to_numpy()
    train_inicial = full[:-VENTANA_EVAL]

    modelo_arima, motivo = con_timeout(_ajustar_arima, TIMEOUT_SEG, train_inicial)
    if modelo_arima is None:
        resultado["motivo_fallo_arima"] = motivo
        resultado["motivo_fallo_garch"] = "sin_residuos_arima"
        return resultado

    resultado["convergio_arima"] = True
    p, d, q = modelo_arima.order
    resultado["orden_p"], resultado["orden_d"], resultado["orden_q"] = p, d, q
    resultado["aicc"] = float(modelo_arima.aicc())

    fitted = modelo_arima.predict_in_sample()
    resultado["r2_in_sample"] = r2_score_simple(train_inicial, fitted)

    resid = np.asarray(modelo_arima.resid())
    try:
        lb = acorr_ljungbox(resid, lags=[12], return_df=True)
        resultado["ljung_box_p"] = float(lb["lb_pvalue"].iloc[0])
    except Exception:
        pass

    # MEJORA 1 + 2: walk-forward de ARIMA y del baseline ingenuo
    try:
        err_arima, err_naive = validacion_walk_forward(full, modelo_arima)
        valido = np.isfinite(err_arima) & np.isfinite(err_naive)
        err_arima, err_naive = err_arima[valido], err_naive[valido]
        resultado["n_pasos_walkforward"] = int(valido.sum())
        if valido.sum() > 0:
            rmse_arima = float(np.sqrt(np.mean(err_arima**2)))
            rmse_naive = float(np.sqrt(np.mean(err_naive**2)))
            resultado["rmse_arima_walkforward"] = rmse_arima
            resultado["rmse_naive_walkforward"] = rmse_naive
            resultado["std_error_walkforward"] = float(np.std(err_arima))
            if rmse_naive > 0:
                ratio = rmse_arima / rmse_naive
                resultado["ratio_vs_naive"] = ratio
                resultado["arima_supera_naive"] = bool(ratio < 1)
    except Exception as e:
        resultado["motivo_fallo_arima"] = f"walkforward_fallo: {type(e).__name__}: {e}"[:200]

    if not es_apto_garch:
        resultado["motivo_fallo_garch"] = "serie_no_apto_garch"
        return resultado

    garch_res, motivo_g = con_timeout(_ajustar_garch, TIMEOUT_SEG, resid)
    if garch_res is None:
        resultado["motivo_fallo_garch"] = motivo_g
        return resultado

    if garch_res.convergence_flag != 0:
        resultado["motivo_fallo_garch"] = f"no_convergio (flag={garch_res.convergence_flag})"
        return resultado

    resultado["convergio_garch"] = True
    params = garch_res.params
    omega = float(params.get("omega", np.nan))
    alpha = float(params.get("alpha[1]", np.nan))
    beta = float(params.get("beta[1]", np.nan))
    resultado["omega"] = omega
    resultado["alpha"] = alpha
    resultado["beta"] = beta
    resultado["persistencia"] = alpha + beta

    return resultado


def main() -> None:
    df = pd.read_parquet(DATA_PATH)
    aptas = df[df["apto_arima"]]
    grupos = list(aptas.groupby(["codigo_pais", "indicador"]))
    print(f"Series a procesar (apto_arima): {len(grupos)}")
    print(f"Walk-forward: ventana={VENTANA_EVAL} meses, re-estimación cada {REESTIMAR_CADA} pasos")

    t0 = time.time()
    resultados = Parallel(n_jobs=-1, verbose=5)(
        delayed(procesar_serie)(codigo, indicador, g) for (codigo, indicador), g in grupos
    )
    tiempo_total = time.time() - t0

    tabla = pd.DataFrame(resultados)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_parquet(OUT_PATH, index=False)

    imprimir_resumen(tabla, tiempo_total)


def imprimir_resumen(tabla: pd.DataFrame, tiempo_total: float) -> None:
    n = len(tabla)
    n_arima_ok = int(tabla["convergio_arima"].sum())
    n_garch_intentos = int((tabla["motivo_fallo_garch"] != "serie_no_apto_garch").sum())
    n_garch_ok = int(tabla["convergio_garch"].sum())

    print("=" * 70)
    print("RESUMEN — src/06b_modelado_robusto.py")
    print("=" * 70)
    print(f"\nTiempo total: {tiempo_total:.1f}s ({tiempo_total/60:.1f} min) para {n} series")
    print(f"\nARIMA: {n_arima_ok}/{n} convergieron ({n_arima_ok/n:.1%})")
    if n_arima_ok < n:
        print("  Motivos de fallo ARIMA:")
        for motivo, cnt in tabla.loc[~tabla["convergio_arima"], "motivo_fallo_arima"].value_counts().items():
            print(f"    - {motivo}: {cnt}")

    print(f"\nGARCH: intentado en {n_garch_intentos} series (apto_garch); convergió en {n_garch_ok} ({n_garch_ok/n_garch_intentos:.1%} de las intentadas)")

    con_wf = tabla[tabla["n_pasos_walkforward"] > 0]
    n_supera = int(con_wf["arima_supera_naive"].sum())
    print(f"\n--- MEJORA 2: ARIMA vs. baseline ingenuo (walk-forward, {len(con_wf)} series evaluadas) ---")
    print(f"ARIMA le gana al ingenuo (ratio<1): {n_supera} ({n_supera/len(con_wf):.1%})")
    print(f"ARIMA NO le gana (ratio>=1): {len(con_wf)-n_supera} ({(len(con_wf)-n_supera)/len(con_wf):.1%})")
    print(f"Ratio promedio: {con_wf['ratio_vs_naive'].mean():.3f} | mediana: {con_wf['ratio_vs_naive'].median():.3f}")

    print("\n--- Sanity check: estables vs. crisis ---")
    muestra = ["USA", "DEU", "GBR", "JPN", "ARG", "VEN", "TUR", "ZAF", "BRA"]
    cols_check = [
        "codigo_pais", "indicador", "orden_p", "orden_d", "orden_q",
        "rmse_arima_walkforward", "rmse_naive_walkforward", "ratio_vs_naive", "arima_supera_naive",
    ]
    check = tabla[(tabla["codigo_pais"].isin(muestra)) & (tabla["indicador"] == "hcpi")][cols_check]
    print(check.sort_values("codigo_pais").to_string(index=False))

    print("\nPreview de resultados (10 filas):")
    cols_preview = [
        "codigo_pais", "indicador", "meses_usados", "convergio_arima",
        "rmse_arima_walkforward", "rmse_naive_walkforward", "ratio_vs_naive",
        "std_error_walkforward", "convergio_garch", "persistencia",
    ]
    print(tabla[cols_preview].head(10).to_string(index=False))

    print(f"\nGuardado en: {OUT_PATH}")


if __name__ == "__main__":
    main()
