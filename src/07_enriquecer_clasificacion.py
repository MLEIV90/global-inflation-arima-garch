"""Enriquece los resultados de modelado con la clasificación oficial del
Banco Mundial (región + nivel de ingreso) por país. Solo preparación de
datos -- ningún análisis todavía.
"""

from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_modelos_robusto.parquet"
CLASIFICACION_PATH = ROOT / "data" / "processed" / "clasificacion_paises.parquet"
OUT_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"

URL_API = "https://api.worldbank.org/v2/country?format=json&per_page=400"


def descargar_clasificacion() -> pd.DataFrame:
    resp = requests.get(URL_API, timeout=30)
    resp.raise_for_status()
    _, paises = resp.json()

    filas = []
    for p in paises:
        region = p["region"]["value"].strip()
        nivel_ingreso = p["incomeLevel"]["value"].strip()
        if region == "Aggregates" or nivel_ingreso == "Aggregates":
            continue  # agregados regionales/de ingreso, no son países
        filas.append({"codigo_pais": p["id"], "region": region, "nivel_ingreso": nivel_ingreso})

    return pd.DataFrame(filas)


def main() -> None:
    clasificacion = descargar_clasificacion()
    CLASIFICACION_PATH.parent.mkdir(parents=True, exist_ok=True)
    clasificacion.to_parquet(CLASIFICACION_PATH, index=False)
    print(f"Clasificación de {len(clasificacion)} países guardada en {CLASIFICACION_PATH}")

    resultados = pd.read_parquet(RESULTADOS_PATH)
    enriquecidos = resultados.merge(clasificacion, on="codigo_pais", how="left")
    enriquecidos.to_parquet(OUT_PATH, index=False)
    print(f"Resultados enriquecidos guardados en {OUT_PATH}")

    # --- Validación ---
    n_total = len(enriquecidos)
    matcheados = enriquecidos["region"].notna()
    n_match = int(matcheados.sum())
    n_sin_match = n_total - n_match

    print("\n" + "=" * 70)
    print("VALIDACIÓN")
    print("=" * 70)
    print(f"\nSeries totales: {n_total}")
    print(f"Matchearon con clasificación: {n_match} ({n_match/n_total:.1%})")
    print(f"Sin región/ingreso: {n_sin_match} ({n_sin_match/n_total:.1%})")

    if n_sin_match:
        no_match = enriquecidos.loc[~matcheados, ["codigo_pais", "pais", "indicador"]].drop_duplicates(
            subset=["codigo_pais"]
        )
        print("\nCódigos sin match (revisar si son agregados/territorios):")
        print(no_match.sort_values("codigo_pais").to_string(index=False))

    print("\n" + "=" * 70)
    print("DISTRIBUCIÓN")
    print("=" * 70)

    print("\nSeries y países únicos por región:")
    por_region = enriquecidos.dropna(subset=["region"]).groupby("region").agg(
        n_series=("codigo_pais", "size"), n_paises=("codigo_pais", "nunique")
    ).sort_values("n_series", ascending=False)
    print(por_region.to_string())

    print("\nSeries y países únicos por nivel de ingreso:")
    por_ingreso = enriquecidos.dropna(subset=["nivel_ingreso"]).groupby("nivel_ingreso").agg(
        n_series=("codigo_pais", "size"), n_paises=("codigo_pais", "nunique")
    ).sort_values("n_series", ascending=False)
    print(por_ingreso.to_string())


if __name__ == "__main__":
    main()
