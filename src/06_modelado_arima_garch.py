"""Pipeline de modelado ARIMA + GARCH sobre el panel de inflación mensual.

Ajusta auto_arima (pmdarima) por serie país×indicador y, sobre sus residuos,
un GARCH(1,1) (arch) para las series aptas. Paralelizado con joblib.
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
OUT_PATH = ROOT / "data" / "processed" / "resultados_modelos.parquet"

N_TEST = 12
MIN_TOTAL_TRAMO = 24  # al menos 12 de train + 12 de test
TIMEOUT_SEG = 60


def con_timeout(func, timeout_seg, *args, **kwargs):
    """Corre func en un thread aparte y aborta si tarda más de timeout_seg.

    ThreadPoolExecutor (no multiprocessing) porque cada llamada ya corre
    dentro de un worker de joblib -- funciona igual en Windows/Linux, a
    diferencia de signal.alarm que no existe en Windows.
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seg), None
        except FutureTimeoutError:
            return None, "timeout"
        except Exception as e:  # noqa: BLE001 - queremos capturar cualquier falla de ajuste
            return None, f"{type(e).__name__}: {e}"[:200]


def recortar_tramo_continuo(sub: pd.DataFrame) -> pd.DataFrame:
    """Devuelve el tramo contiguo (sin huecos de calendario) más largo de
    `inflacion_yoy_log`. No imputa: si hay un hueco, corta ahí."""
    s = sub.dropna(subset=["inflacion_yoy_log"]).sort_values("fecha").reset_index(drop=True)
    if len(s) == 0:
        return s
    periodos = (s["fecha"].dt.year * 12 + s["fecha"].dt.month).astype(int)
    saltos = periodos.diff().fillna(1)
    grupo_id = (saltos != 1).cumsum()
    mejor_grupo = grupo_id.value_counts().idxmax()
    return s[grupo_id == mejor_grupo].reset_index(drop=True)


def detectar_estacionalidad(serie: pd.Series) -> bool:
    """PACF en lag 12 (no ACF, ver Fase 5) como flag informativo -- no se
    ajusta SARIMA, solo se guarda para uso futuro."""
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
        "rmse_oos": np.nan,
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

    train = tramo["inflacion_yoy_log"].iloc[:-N_TEST].to_numpy()
    test = tramo["inflacion_yoy_log"].iloc[-N_TEST:].to_numpy()

    modelo_arima, motivo = con_timeout(_ajustar_arima, TIMEOUT_SEG, train)
    if modelo_arima is None:
        resultado["motivo_fallo_arima"] = motivo
        resultado["motivo_fallo_garch"] = "sin_residuos_arima"
        return resultado

    resultado["convergio_arima"] = True
    p, d, q = modelo_arima.order
    resultado["orden_p"], resultado["orden_d"], resultado["orden_q"] = p, d, q
    resultado["aicc"] = float(modelo_arima.aicc())

    fitted = modelo_arima.predict_in_sample()
    resultado["r2_in_sample"] = r2_score_simple(train, fitted)

    resid = np.asarray(modelo_arima.resid())
    try:
        lb = acorr_ljungbox(resid, lags=[12], return_df=True)
        resultado["ljung_box_p"] = float(lb["lb_pvalue"].iloc[0])
    except Exception:
        pass

    try:
        forecast = modelo_arima.predict(n_periods=N_TEST)
        forecast = np.asarray(forecast)
        resultado["rmse_oos"] = float(np.sqrt(np.mean((test - forecast) ** 2)))
    except Exception as e:
        resultado["motivo_fallo_arima"] = f"forecast_fallo: {type(e).__name__}: {e}"[:200]

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
    print("RESUMEN — src/06_modelado_arima_garch.py")
    print("=" * 70)
    print(f"\nTiempo total: {tiempo_total:.1f}s ({tiempo_total/60:.1f} min) para {n} series")
    print(f"\nARIMA: {n_arima_ok}/{n} convergieron ({n_arima_ok/n:.1%})")
    if n_arima_ok < n:
        print("  Motivos de fallo ARIMA:")
        for motivo, cnt in tabla.loc[~tabla["convergio_arima"], "motivo_fallo_arima"].value_counts().items():
            print(f"    - {motivo}: {cnt}")

    print(f"\nGARCH: intentado en {n_garch_intentos} series (apto_garch); convergió en {n_garch_ok} ({n_garch_ok/n_garch_intentos:.1%} de las intentadas)")
    fallos_garch = tabla.loc[
        (~tabla["convergio_garch"]) & (tabla["motivo_fallo_garch"] != "serie_no_apto_garch"),
        "motivo_fallo_garch",
    ]
    if len(fallos_garch):
        print("  Motivos de fallo GARCH (excluyendo 'no apto_garch'):")
        for motivo, cnt in fallos_garch.value_counts().items():
            print(f"    - {motivo}: {cnt}")

    print("\nPreview de resultados (10 filas):")
    cols_preview = [
        "codigo_pais", "indicador", "meses_usados", "convergio_arima",
        "orden_p", "orden_d", "orden_q", "aicc", "rmse_oos",
        "convergio_garch", "alpha", "beta", "persistencia",
    ]
    print(tabla[cols_preview].head(10).to_string(index=False))

    print(f"\nGuardado en: {OUT_PATH}")


if __name__ == "__main__":
    main()
