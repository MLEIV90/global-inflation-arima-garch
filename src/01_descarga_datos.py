"""Descarga el dataset de inflación del Banco Mundial y lo deja en formato largo."""

from pathlib import Path

import pandas as pd
import requests

URL = (
    "https://thedocs.worldbank.org/en/doc/1ad246272dbbc437c74323719506aa0c-0350012021/"
    "original/Inflation-data.xlsx"
)

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "Inflation-data.xlsx"
OUT_PATH = ROOT / "data" / "processed" / "inflacion_mensual_completa.parquet"

# Hojas mensuales disponibles en el workbook. El deflactor del PIB (def_*) solo
# existe a frecuencia trimestral/anual en esta fuente, por eso no aparece acá.
HOJAS_MENSUALES = {
    "hcpi_m": "hcpi",
    "ecpi_m": "ecpi",
    "fcpi_m": "fcpi",
    "ccpi_m": "ccpi",
    "ppi_m": "ppi",
}


def descargar_excel() -> Path:
    if RAW_PATH.exists():
        return RAW_PATH
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    RAW_PATH.write_bytes(resp.content)
    return RAW_PATH


def hoja_a_largo(path_excel: Path, hoja: str, indicador: str) -> pd.DataFrame:
    df = pd.read_excel(path_excel, sheet_name=hoja)
    columnas_fecha = [c for c in df.columns if isinstance(c, int) and 190001 <= c <= 210012]

    # Algunas hojas traen dos filas para el mismo país (mismo label, series
    # numéricamente distintas, ej. AUT/NLD/PRT/ZAF en ppi_m). Nos quedamos con
    # la fila más completa para no mezclar dos series distintas por país.
    if df["Country Code"].duplicated().any():
        n_validos = df[columnas_fecha].notna().sum(axis=1)
        idx_mas_completo = n_validos.groupby(df["Country Code"]).idxmax()
        df = df.loc[idx_mas_completo]

    largo = df.melt(
        id_vars=["Country Code", "Country"],
        value_vars=columnas_fecha,
        var_name="fecha_yyyymm",
        value_name="indice",
    )
    largo["fecha"] = pd.to_datetime(largo["fecha_yyyymm"], format="%Y%m")
    largo["indicador"] = indicador
    largo = largo.rename(columns={"Country Code": "codigo_pais", "Country": "pais"})
    return largo[["pais", "codigo_pais", "indicador", "fecha", "indice"]]


def calcular_inflacion_yoy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["codigo_pais", "indicador", "fecha"])
    df["inflacion_yoy"] = df.groupby(["codigo_pais", "indicador"])["indice"].pct_change(
        periods=12
    ) * 100
    return df


def main() -> None:
    path_excel = descargar_excel()

    frames = [hoja_a_largo(path_excel, hoja, indicador) for hoja, indicador in HOJAS_MENSUALES.items()]
    datos = pd.concat(frames, ignore_index=True)
    datos = datos.dropna(subset=["indice"])

    datos = calcular_inflacion_yoy(datos)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    datos.to_parquet(OUT_PATH, index=False)

    n_paises = datos["codigo_pais"].nunique()
    n_indicadores = datos["indicador"].nunique()
    n_series = datos.groupby(["codigo_pais", "indicador"]).ngroups
    fecha_min, fecha_max = datos["fecha"].min(), datos["fecha"].max()

    print(f"Países: {n_paises}")
    print(f"Indicadores: {n_indicadores} -> {sorted(datos['indicador'].unique())}")
    print(f"Series (país x indicador): {n_series}")
    print(f"Rango de fechas: {fecha_min.date()} a {fecha_max.date()}")
    print(f"Filas totales: {len(datos)}")
    print(f"Filas con inflación YoY calculable: {datos['inflacion_yoy'].notna().sum()}")
    print(f"Guardado en: {OUT_PATH}")


if __name__ == "__main__":
    main()
