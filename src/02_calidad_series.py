"""Análisis de calidad de las series país x indicador antes de modelar ARIMA/GARCH."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "processed" / "inflacion_mensual_completa.parquet"
OUT_PATH = ROOT / "data" / "processed" / "calidad_series.parquet"
FIG_PATH = ROOT / "reports" / "figures" / "distribucion_puntos_validos.png"

PISO_MINIMO = 36  # 3 años de datos mensuales


def main() -> None:
    datos = pd.read_parquet(IN_PATH)

    calidad = (
        datos.groupby(["codigo_pais", "indicador"])["inflacion_yoy"]
        .apply(lambda s: s.notna().sum())
        .reset_index(name="n_puntos_validos")
    )
    calidad["apto_modelado"] = calidad["n_puntos_validos"] >= PISO_MINIMO

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    calidad.to_parquet(OUT_PATH, index=False)

    n_series = len(calidad)
    n_bajo_piso = (~calidad["apto_modelado"]).sum()
    percentiles = calidad["n_puntos_validos"].describe(
        percentiles=[0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
    )

    print(f"Series totales: {n_series}")
    print(f"Piso mínimo: {PISO_MINIMO} puntos válidos (3 años)")
    print(f"Series por debajo del piso: {n_bajo_piso} ({n_bajo_piso / n_series:.1%})")
    print(f"Series aptas para modelado: {n_series - n_bajo_piso}")
    print()
    print("Distribución de puntos válidos por serie:")
    print(percentiles.to_string())

    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(calidad["n_puntos_validos"], bins=40, color="steelblue", edgecolor="white")
    ax.axvline(PISO_MINIMO, color="crimson", linestyle="--", label=f"Piso = {PISO_MINIMO}")
    ax.set_xlabel("Puntos válidos (inflación YoY no nula)")
    ax.set_ylabel("Cantidad de series (país x indicador)")
    ax.set_title("Distribución de puntos válidos por serie")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_PATH, dpi=150)

    print(f"\nGuardado: {OUT_PATH}")
    print(f"Guardado: {FIG_PATH}")


if __name__ == "__main__":
    main()
