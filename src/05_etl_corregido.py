"""ETL corregido — implementa los 10 pasos del plan aprobado en
reports/00_bitacora_decisiones.md, incorporando los hallazgos de las 4
fases de diagnóstico. Genera
data/processed/inflacion_mensual_completa_v2.parquet y, al final, corre una
validación sobre el resultado guardado.
"""

import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "Inflation-data.xlsx"
OUT_PATH = ROOT / "data" / "processed" / "inflacion_mensual_completa_v2.parquet"

HOJAS_MENSUALES = ["hcpi_m", "ecpi_m", "fcpi_m", "ccpi_m", "ppi_m"]
NOMBRE_INDICADOR = {"hcpi_m": "hcpi", "ecpi_m": "ecpi", "fcpi_m": "fcpi", "ccpi_m": "ccpi", "ppi_m": "ppi"}
CODIGO_PAIS_RE = re.compile(r"^[A-Z]{3}$")

# Paso 4 — ramificación por Indicator Type real (Fase 1)
TRATAMIENTO_TASA_DIRECTA = {("ecpi_m", "IND"), ("ecpi_m", "IDN")}
TRATAMIENTO_ETIQUETA_CORREGIDA = {("hcpi_m", "VGB"), ("ppi_m", "AUS")}

# Paso 5 — ceros de Venezuela tratados como dato faltante (Fase 2)
TRATAMIENTO_CEROS_A_NAN = {("ecpi_m", "VEN"), ("fcpi_m", "VEN")}

PISO_ARIMA = 60
PISO_GARCH = 100
CUTOFF_COMPLETA = 197501
UMBRAL_HIPER = 100
PAISES_VALIDACION = ["USA", "DEU", "JPN", "GBR", "BRA", "ZAF", "MEX", "TUR", "ARG", "IND"]


# ---------- Paso 1-2: carga y filtro de filas no-país ----------
def es_fila_de_pais(codigo) -> bool:
    return isinstance(codigo, str) and bool(CODIGO_PAIS_RE.match(codigo))


def columnas_fecha(df: pd.DataFrame):
    return [c for c in df.columns if isinstance(c, int) and 190001 <= c <= 210012]


# ---------- Paso 3: deduplicar + marcar conflicto de recencia ----------
def deduplicar_y_marcar_conflicto(df: pd.DataFrame, date_cols) -> pd.DataFrame:
    valid_mask = df[date_cols].notna().to_numpy()
    n_cols = len(date_cols)
    tiene_dato = valid_mask.any(axis=1)
    pos_ultima = np.where(
        tiene_dato, n_cols - 1 - np.argmax(valid_mask[:, ::-1], axis=1), -1
    )
    fechas_arr = np.array(date_cols)
    ultima_fecha = np.where(pos_ultima >= 0, fechas_arr[pos_ultima.clip(min=0)], -1)
    n_validos = valid_mask.sum(axis=1)

    tmp = pd.DataFrame(
        {"_n": n_validos, "_ultima": ultima_fecha, "_codigo": df["Country Code"].to_numpy()},
        index=df.index,
    )
    idx_elegido = tmp.groupby("_codigo")["_n"].idxmax()
    ultima_maxima_por_codigo = tmp.groupby("_codigo")["_ultima"].max()

    elegido = df.loc[idx_elegido.values].copy()
    ultima_del_elegido = tmp.loc[idx_elegido.values, "_ultima"].to_numpy()
    ultima_disponible = elegido["Country Code"].map(ultima_maxima_por_codigo).to_numpy()
    # Conflicto real: la fila elegida (más completa) no llega a la fecha más
    # reciente que sí alcanza alguna de sus duplicadas — un empate en fecha
    # no cuenta como conflicto.
    elegido["dedup_conflicto_recencia"] = ultima_del_elegido < ultima_disponible
    return elegido


# ---------- Paso 7: patrón de frecuencia real por serie ----------
def detectar_patron_frecuencia(fechas_validas):
    if len(fechas_validas) < 2:
        return "insuficiente para determinar"
    periodos = [(c // 100) * 12 + (c % 100) for c in fechas_validas]
    pasos = [periodos[i] - periodos[i - 1] for i in range(1, len(periodos))]
    valores_unicos = set(pasos)
    if valores_unicos == {1}:
        return "mensual"
    if valores_unicos == {3}:
        return "trimestral"
    return "mixto/cambia en el tiempo"


# ---------- Pasos 1-6: construir el panel largo con las correcciones ----------
def construir_panel_corregido(path_excel: Path) -> pd.DataFrame:
    filas = []
    for hoja in HOJAS_MENSUALES:
        df = pd.read_excel(path_excel, sheet_name=hoja)
        date_cols = columnas_fecha(df)
        df_p = df[df["Country Code"].apply(es_fila_de_pais)]
        df_p = deduplicar_y_marcar_conflicto(df_p, date_cols)

        for _, fila in df_p.iterrows():
            codigo = fila["Country Code"]
            valores = fila[date_cols].astype(float)
            conflicto = bool(fila["dedup_conflicto_recencia"])
            for fecha_yyyymm, valor in zip(date_cols, valores):
                filas.append((hoja, codigo, fila["Country"], fecha_yyyymm, valor, conflicto))

    panel = pd.DataFrame(
        filas,
        columns=["hoja", "codigo_pais", "pais", "fecha_yyyymm", "valor_original", "dedup_conflicto_recencia"],
    )
    panel["fecha"] = pd.to_datetime(panel["fecha_yyyymm"], format="%Y%m")

    # Paso 4 — tratamiento por Indicator Type real
    etiquetas = pd.DataFrame(
        [(h, c, "tasa_directa") for h, c in TRATAMIENTO_TASA_DIRECTA]
        + [(h, c, "index_etiqueta_corregida") for h, c in TRATAMIENTO_ETIQUETA_CORREGIDA],
        columns=["hoja", "codigo_pais", "tratamiento_indicator_type"],
    )
    panel = panel.merge(etiquetas, on=["hoja", "codigo_pais"], how="left")
    panel["tratamiento_indicator_type"] = panel["tratamiento_indicator_type"].fillna("index")

    # Paso 5 — ceros de Venezuela -> NaN (antes de derivar índice/tasa)
    clave = pd.Series(list(zip(panel["hoja"], panel["codigo_pais"])), index=panel.index)
    mask_ven = clave.isin(TRATAMIENTO_CEROS_A_NAN) & (panel["valor_original"] == 0)
    panel.loc[mask_ven, "valor_original"] = np.nan

    panel = panel.sort_values(["hoja", "codigo_pais", "fecha"]).reset_index(drop=True)

    # `indice`: NaN para las filas que ya son tasa directa (no hay índice real).
    # `es_tasa` se calcula DESPUÉS del sort/reset_index: np.where alinea por
    # posición, no por índice de pandas, así que si se calculara antes del
    # reordenamiento quedaría desalineado con el resto de las columnas.
    es_tasa = panel["tratamiento_indicator_type"] == "tasa_directa"
    panel["indice"] = np.where(es_tasa, np.nan, panel["valor_original"])

    # Paso 6 — doble transformación
    indice_lag12 = panel.groupby(["hoja", "codigo_pais"])["indice"].shift(12)
    pct_index = 100 * (panel["indice"] / indice_lag12 - 1)
    log_index = 100 * (np.log(panel["indice"]) - np.log(indice_lag12))

    panel["inflacion_yoy_pct"] = np.where(es_tasa, panel["valor_original"], pct_index)
    panel["inflacion_yoy_log"] = np.where(
        es_tasa, 100 * np.log(1 + panel["valor_original"] / 100), log_index
    )

    return panel


# ---------- Pasos 7-9: flags por serie ----------
def resumir_serie(grupo: pd.DataFrame) -> pd.Series:
    grupo = grupo.sort_values("fecha")
    valido = grupo["valor_original"].notna().to_numpy()
    idxv = valido.nonzero()[0]

    if len(idxv) == 0:
        return pd.Series(
            {
                "n_meses_validos": 0,
                "n_huecos_internos": 0,
                "clasificacion_cobertura": "sin_datos",
                "patron_frecuencia": "insuficiente para determinar",
                "apto_arima": False,
                "apto_garch": False,
                "alta_inflacion": False,
            }
        )

    primer, ultimo = idxv[0], idxv[-1]
    tramo = valido[primer : ultimo + 1]
    n_huecos = 0
    en_hueco = False
    for v in tramo:
        if not v and not en_hueco:
            n_huecos += 1
            en_hueco = True
        elif v:
            en_hueco = False

    n_validos = len(idxv)
    primer_fecha = int(grupo["fecha_yyyymm"].iloc[primer])
    if n_huecos == 0:
        clasificacion = "completa" if primer_fecha <= CUTOFF_COMPLETA else "arranque tardío"
    elif n_huecos <= 2:
        clasificacion = "con huecos internos"
    else:
        clasificacion = "fragmentada"

    fechas_validas = grupo["fecha_yyyymm"].to_numpy()[idxv].tolist()
    patron = detectar_patron_frecuencia(fechas_validas)

    apto_arima = (n_huecos == 0) and (n_validos >= PISO_ARIMA)
    apto_garch = (n_huecos == 0) and (n_validos >= PISO_GARCH)
    alta_inflacion = bool((grupo["inflacion_yoy_pct"] > UMBRAL_HIPER).any())

    return pd.Series(
        {
            "n_meses_validos": n_validos,
            "n_huecos_internos": n_huecos,
            "clasificacion_cobertura": clasificacion,
            "patron_frecuencia": patron,
            "apto_arima": apto_arima,
            "apto_garch": apto_garch,
            "alta_inflacion": alta_inflacion,
        }
    )


def agregar_flags_por_serie(panel: pd.DataFrame) -> pd.DataFrame:
    resumen = panel.groupby(["hoja", "codigo_pais"], group_keys=True).apply(
        resumir_serie, include_groups=False
    )
    resumen = resumen.reset_index()
    panel = panel.merge(resumen, on=["hoja", "codigo_pais"], how="left")
    return panel


# ---------- Paso 10: recorte final y guardado ----------
def finalizar_y_guardar(panel: pd.DataFrame) -> pd.DataFrame:
    final = panel[panel["valor_original"].notna()].copy()
    final["indicador"] = final["hoja"].map(NOMBRE_INDICADOR)
    columnas = [
        "pais",
        "codigo_pais",
        "indicador",
        "fecha",
        "indice",
        "inflacion_yoy_pct",
        "inflacion_yoy_log",
        "tratamiento_indicator_type",
        "patron_frecuencia",
        "alta_inflacion",
        "n_meses_validos",
        "clasificacion_cobertura",
        "apto_arima",
        "apto_garch",
        "dedup_conflicto_recencia",
    ]
    final = final[columnas].sort_values(["indicador", "codigo_pais", "fecha"]).reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final.to_parquet(OUT_PATH, index=False)
    return final


# ---------- Validación post-ETL ----------
def validar_sin_infinitos(final: pd.DataFrame):
    n_inf_pct = int(np.isinf(final["inflacion_yoy_pct"]).sum())
    n_inf_log = int(np.isinf(final["inflacion_yoy_log"]).sum())
    return n_inf_pct, n_inf_log


def validar_prueba_de_oro(final: pd.DataFrame, path_excel: Path):
    df_a = pd.read_excel(path_excel, sheet_name="hcpi_a")
    year_cols = [c for c in df_a.columns if isinstance(c, int) and 1970 <= c <= 2025]

    hcpi = final[final["indicador"] == "hcpi"].copy()
    hcpi["year"] = hcpi["fecha"].dt.year
    hcpi["month"] = hcpi["fecha"].dt.month

    filas = []
    for codigo in PAISES_VALIDACION:
        serie = hcpi[hcpi["codigo_pais"] == codigo]
        fila_a = df_a[df_a["Country Code"] == codigo]
        if serie.empty or fila_a.empty:
            continue
        oficial = fila_a.iloc[0][year_cols]
        idx = serie.set_index(["year", "month"])["indice"]
        for year in range(1971, 2025):
            ofic = oficial.get(year)
            if pd.isna(ofic):
                continue
            vals_y = [idx.get((year, m)) for m in range(1, 13)]
            vals_p = [idx.get((year - 1, m)) for m in range(1, 13)]
            if all(pd.notna(v) for v in vals_y) and all(pd.notna(v) for v in vals_p):
                avg_pct = 100 * (np.mean(vals_y) / np.mean(vals_p) - 1)
            else:
                avg_pct = np.nan
            filas.append((codigo, year, ofic, avg_pct))

    tabla = pd.DataFrame(filas, columns=["codigo_pais", "year", "oficial", "avg_pct"])
    tabla["error"] = (tabla["avg_pct"] - tabla["oficial"]).abs()
    return tabla


def imprimir_validacion(final: pd.DataFrame, path_excel: Path):
    print("=" * 70)
    print("VALIDACIÓN DEL ETL CORREGIDO")
    print("=" * 70)

    # 1
    n_series = final.groupby(["codigo_pais", "indicador"]).ngroups
    print(f"\n1. Filas totales: {len(final):,} | Series (país x indicador): {n_series}")

    # 2
    n_inf_pct, n_inf_log = validar_sin_infinitos(final)
    n_nan_pct = int(final["inflacion_yoy_pct"].isna().sum())
    print(f"\n2. Infinitos: pct={n_inf_pct}, log={n_inf_log} (deben ser 0)")
    print(f"   NaN en inflacion_yoy_pct: {n_nan_pct:,} (esperable en los primeros 12 meses de cada serie)")

    # 3
    print("\n3. Conteo de flags:")
    resumen_series = final.drop_duplicates(subset=["codigo_pais", "indicador"])
    print(f"   apto_arima=True: {resumen_series['apto_arima'].sum()} / {n_series}")
    print(f"   apto_garch=True: {resumen_series['apto_garch'].sum()} / {n_series}")
    print(f"   alta_inflacion=True: {resumen_series['alta_inflacion'].sum()} / {n_series}")
    print(f"   dedup_conflicto_recencia=True: {resumen_series['dedup_conflicto_recencia'].sum()} / {n_series}")
    print("   patron_frecuencia:")
    for patron, n in resumen_series["patron_frecuencia"].value_counts().items():
        print(f"     - {patron}: {n}")
    print("   tratamiento_indicator_type:")
    for trat, n in resumen_series["tratamiento_indicator_type"].value_counts().items():
        print(f"     - {trat}: {n}")

    # 4
    print("\n4. India/Indonesia ecpi (tratamiento_indicator_type='tasa_directa'):")
    for codigo in ["IND", "IDN"]:
        sub = final[(final["codigo_pais"] == codigo) & (final["indicador"] == "ecpi")].sort_values("fecha")
        if sub.empty:
            print(f"   {codigo}: sin filas")
            continue
        muestra = sub[["fecha", "indice", "inflacion_yoy_pct", "inflacion_yoy_log"]].head(5)
        print(f"   {codigo} — primeras filas:")
        print(muestra.to_string(index=False))
        rango = sub["inflacion_yoy_pct"].agg(["min", "max"])
        print(f"   {codigo} — rango inflacion_yoy_pct: [{rango['min']:.2f}, {rango['max']:.2f}] (antes: hasta -89%/-48% de basura)")

    # 5
    print("\n5. Venezuela — ceros deberían ser NaN, no filas presentes:")
    for codigo, ind in [("VEN", "ecpi"), ("VEN", "fcpi")]:
        sub = final[(final["codigo_pais"] == codigo) & (final["indicador"] == ind)]
        n_ceros = int((sub["indice"] == 0).sum())
        print(f"   {ind}/{codigo}: filas presentes={len(sub)}, filas con indice==0: {n_ceros} (debe ser 0)")

    # 6
    print("\n6. Prueba de oro — validación contra hcpi_a oficial (recalculada sobre el parquet v2):")
    tabla = validar_prueba_de_oro(final, path_excel)
    err = tabla["error"].dropna()
    corr = tabla[["avg_pct", "oficial"]].corr().iloc[0, 1]
    print(f"   N={len(err)}, error absoluto medio={err.mean():.3f} pp, mediana={err.median():.5f} pp, correlación={corr:.4f}")
    print("   (comparar con Fase 4: media 0.337 pp, mediana ~0.000, correlación 0.9999 — debe ser prácticamente igual)")


def main() -> None:
    panel = construir_panel_corregido(RAW_PATH)
    panel = agregar_flags_por_serie(panel)
    final = finalizar_y_guardar(panel)

    print(f"Guardado: {OUT_PATH} ({len(final):,} filas)")
    imprimir_validacion(final, RAW_PATH)


if __name__ == "__main__":
    main()
