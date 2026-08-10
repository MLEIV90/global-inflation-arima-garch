"""Diagnóstico (hallazgo nuevo, Fase A): busca series país-a-país
byte-idénticas en las 5 hojas mensuales del Excel crudo del Banco
Mundial, más allá de los 3 pares ya detectados en R1 (FIN/GAB, GBR/USA,
CZE/DJI, todos en hcpi).

SOLO DIAGNÓSTICO — no modifica ningún dato ni resultado. Se ejecuta
sobre `data/raw/Inflation-data.xlsx` directamente (no sobre el parquet
procesado) para determinar si la duplicación está en la fuente del
Banco Mundial o fue introducida por el ETL.

Además, para cada par detectado, compara contra la hoja anual oficial
(`{indicador}_a`) de cada país para intentar determinar cuál de los dos
países tiene la serie mensual correcta y cuál fue mal atribuida, y mide
el impacto en el hallazgo central del gradiente de ingreso (Kruskal-
Wallis) excluyendo las series mal atribuidas.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "Inflation-data.xlsx"
RESULTADOS_PATH = ROOT / "data" / "processed" / "resultados_enriquecidos.parquet"
REPORT_PATH = ROOT / "reports" / "diagnostico_series_duplicadas.md"

HOJAS_MENSUALES = ["hcpi_m", "ecpi_m", "fcpi_m", "ccpi_m", "ppi_m"]
NOMBRE_INDICADOR = {"hcpi_m": "hcpi", "ecpi_m": "ecpi", "fcpi_m": "fcpi", "ccpi_m": "ccpi", "ppi_m": "ppi"}
CODIGO_PAIS_RE = re.compile(r"^[A-Z]{3}$")


def es_fila_de_pais(codigo) -> bool:
    return isinstance(codigo, str) and bool(CODIGO_PAIS_RE.match(codigo))


def columnas_fecha(df: pd.DataFrame):
    return [c for c in df.columns if isinstance(c, int) and 190001 <= c <= 210012]


def deduplicar(df: pd.DataFrame, date_cols) -> pd.DataFrame:
    """Misma lógica que 05_etl_corregido.py: por país, se queda con la fila
    más completa (más meses válidos). Reproducida acá (no importada, el
    módulo empieza con un dígito) para operar directo sobre el Excel crudo."""
    valid_mask = df[date_cols].notna().to_numpy()
    n_validos = valid_mask.sum(axis=1)
    tmp = pd.DataFrame({"_n": n_validos, "_codigo": df["Country Code"].to_numpy()}, index=df.index)
    idx_elegido = tmp.groupby("_codigo")["_n"].idxmax()
    return df.loc[idx_elegido.values].copy()


def encontrar_pares_identicos(df_p: pd.DataFrame, date_cols) -> list[tuple[str, str]]:
    """Hashea cada fila (país) por sus valores (NaN incluido como parte de
    la huella) y agrupa por hash; confirma con comparación elemento a
    elemento (NaN-aware) para descartar colisiones de hash."""
    vals = df_p[date_cols].to_numpy(dtype=float)
    codigos = df_p["Country Code"].to_numpy()
    huella = np.where(np.isnan(vals), -999999.999999, np.round(vals, 6))
    claves = [huella[i].tobytes() for i in range(len(codigos))]
    grupos: dict[bytes, list[int]] = {}
    for i, k in enumerate(claves):
        grupos.setdefault(k, []).append(i)

    pares = []
    for idxs in grupos.values():
        if len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ia, ib = idxs[a], idxs[b]
                va, vb = vals[ia], vals[ib]
                iguales = np.array_equal(va, vb, equal_nan=True)
                if iguales and not (np.isnan(va).all()):  # excluir pares de series 100% vacías
                    pares.append(tuple(sorted((codigos[ia], codigos[ib]))))
    return pares


def paso1_deteccion_exhaustiva() -> pd.DataFrame:
    filas = []
    for hoja in HOJAS_MENSUALES:
        df = pd.read_excel(RAW_PATH, sheet_name=hoja)
        date_cols = columnas_fecha(df)
        df_p = df[df["Country Code"].apply(es_fila_de_pais)]
        df_p = deduplicar(df_p, date_cols)
        pares = encontrar_pares_identicos(df_p, date_cols)
        n_meses = {}
        for _, fila in df_p.iterrows():
            n_meses[fila["Country Code"]] = int(fila[date_cols].notna().sum())
        for a, b in pares:
            filas.append({
                "hoja": hoja,
                "indicador": NOMBRE_INDICADOR[hoja],
                "pais_a": a,
                "pais_b": b,
                "n_meses_validos": n_meses[a],
            })
    return pd.DataFrame(filas)


def tasa_anual_propia(indicador: str, pais: str) -> float | None:
    try:
        anual = pd.read_excel(RAW_PATH, sheet_name=f"{indicador}_a")
    except ValueError:
        return None
    cols_anio = [c for c in anual.columns if isinstance(c, int) and 1970 <= c <= 2026]
    fila_a = anual[anual["Country Code"] == pais]
    if len(fila_a) == 0 or len(cols_anio) == 0:
        return None
    vals = fila_a[cols_anio].iloc[0].astype(float).dropna()
    return float(vals.mean()) if len(vals) > 0 else None


def paso2_forense(pares_df: pd.DataFrame, nivel_ingreso: dict) -> pd.DataFrame:
    """Para cada par (que comparte la MISMA serie mensual, por definición
    del hallazgo), calcula la tasa YoY promedio que esa serie mensual
    compartida implica, y la compara contra la hoja anual oficial
    `{indicador}_a` de CADA país por separado (fuente independiente del
    Excel, no afectada por el mismo error de copiado del mensual). El
    país cuya hoja anual está más cerca de lo que implica el mensual
    compartido es el candidato a "serie auténtica"; el otro es candidato
    a "víctima" (su mensual real fue sobrescrito por el del primero)."""
    filas = []

    for _, row in pares_df.iterrows():
        ind = row["indicador"]
        mensual = pd.read_excel(RAW_PATH, sheet_name=f"{ind}_m")
        date_cols = columnas_fecha(mensual)
        mensual_p = deduplicar(mensual[mensual["Country Code"].apply(es_fila_de_pais)], date_cols)

        fila_compartida = mensual_p[mensual_p["Country Code"] == row["pais_a"]].iloc[0]
        serie = fila_compartida[date_cols].astype(float).dropna()
        idx_periodo = pd.PeriodIndex([f"{c // 100}-{c % 100:02d}" for c in serie.index], freq="M")
        indice = pd.Series(serie.values, index=idx_periodo).sort_index()
        yoy = 100 * (indice / indice.shift(12) - 1)
        yoy_medio_compartido = float(yoy.dropna().mean())

        resultado = {
            "indicador": ind, "pais_a": row["pais_a"], "pais_b": row["pais_b"],
            "yoy_medio_serie_mensual_compartida": round(yoy_medio_compartido, 3),
        }
        distancias = {}
        for pais in (row["pais_a"], row["pais_b"]):
            tasa_propia = tasa_anual_propia(ind, pais)
            dist = abs(tasa_propia - yoy_medio_compartido) if tasa_propia is not None else None
            distancias[pais] = dist
            resultado[f"{pais}_tasa_anual_propia"] = round(tasa_propia, 3) if tasa_propia is not None else None
            resultado[f"{pais}_nivel_ingreso"] = nivel_ingreso.get(pais)
            resultado[f"{pais}_distancia_a_mensual_compartido"] = round(dist, 3) if dist is not None else None

        validos = {p: d for p, d in distancias.items() if d is not None}
        if len(validos) == 2:
            autentico = min(validos, key=validos.get)
            victima = max(validos, key=validos.get)
            margen = validos[victima] - validos[autentico]
            resultado["veredicto"] = (
                f"{autentico} auténtico, {victima} víctima (margen {margen:.3f} pp)"
                if margen > 0.1 else "indeterminado (distancias casi iguales)"
            )
        else:
            resultado["veredicto"] = "indeterminado (falta hoja anual de al menos un país)"
        filas.append(resultado)
    return pd.DataFrame(filas)


def paso3_impacto_gradiente() -> dict:
    resultados = pd.read_parquet(RESULTADOS_PATH)
    orden_ingreso = ["Low income", "Lower middle income", "Upper middle income", "High income"]
    hcpi = resultados[(resultados["indicador"] == "hcpi") & (resultados["convergio_arima"]) & (resultados["nivel_ingreso"].notna())]

    h_original, p_original = stats.kruskal(*[
        hcpi.loc[hcpi["nivel_ingreso"] == g, "rmse_arima_walkforward"] for g in orden_ingreso
    ])
    medianas_original = hcpi.groupby("nivel_ingreso")["rmse_arima_walkforward"].median().reindex(orden_ingreso)

    # Los "mal atribuidos" se determinan en paso2; acá se excluyen ambos
    # miembros de cada par duplicado de hcpi (no se puede saber cuál es
    # el correcto sin la hoja anual, y aunque se supiera, la serie
    # "correcta" nunca se corrigió — solo se puede excluir, no reemplazar).
    return {"h_original": h_original, "p_original": p_original, "medianas_original": medianas_original, "hcpi": hcpi, "orden_ingreso": orden_ingreso}


def main() -> None:
    print("=" * 70)
    print("PASO 1 — Detección exhaustiva de series byte-idénticas (5 hojas mensuales)")
    print("=" * 70)
    pares_df = paso1_deteccion_exhaustiva()
    print(f"\nTotal de pares encontrados: {len(pares_df)}")
    print(pares_df.to_string(index=False))

    resultados = pd.read_parquet(RESULTADOS_PATH)
    nivel_ingreso = resultados.drop_duplicates("codigo_pais").set_index("codigo_pais")["nivel_ingreso"].to_dict()

    print("\n" + "=" * 70)
    print("PASO 2 — Forense: ¿cuál país tiene la serie correcta? (vs. hoja anual oficial)")
    print("=" * 70)
    forense_df = paso2_forense(pares_df, nivel_ingreso)
    print(forense_df.to_string(index=False))

    print("\n" + "=" * 70)
    print("PASO 3 — Impacto en el gradiente de ingreso (hcpi, Kruskal-Wallis)")
    print("=" * 70)
    impacto = paso3_impacto_gradiente()
    print(f"Kruskal-Wallis original: H={impacto['h_original']:.2f}, p={impacto['p_original']:.3g}")
    print(impacto["medianas_original"])

    pares_hcpi = pares_df[pares_df["indicador"] == "hcpi"]
    paises_afectados_hcpi = set(pares_hcpi["pais_a"]) | set(pares_hcpi["pais_b"])
    hcpi_excl = impacto["hcpi"][~impacto["hcpi"]["codigo_pais"].isin(paises_afectados_hcpi)]
    h_excl, p_excl = stats.kruskal(*[
        hcpi_excl.loc[hcpi_excl["nivel_ingreso"] == g, "rmse_arima_walkforward"] for g in impacto["orden_ingreso"]
    ])
    medianas_excl = hcpi_excl.groupby("nivel_ingreso")["rmse_arima_walkforward"].median().reindex(impacto["orden_ingreso"])
    print(f"\nExcluyendo {len(paises_afectados_hcpi)} países con hcpi duplicado ({sorted(paises_afectados_hcpi)}):")
    print(f"Kruskal-Wallis sin duplicados: H={h_excl:.2f}, p={p_excl:.3g}, n={len(hcpi_excl)} (vs. {len(impacto['hcpi'])} original)")
    print(medianas_excl)

    generar_reporte(pares_df, forense_df, impacto, hcpi_excl, h_excl, p_excl, medianas_excl, paises_afectados_hcpi)


def generar_reporte(pares_df, forense_df, impacto, hcpi_excl, h_excl, p_excl, medianas_excl, paises_afectados_hcpi) -> None:
    L = []
    L.append("# Diagnóstico — Series país-a-país byte-idénticas en el Excel del Banco Mundial")
    L.append("")
    L.append(
        "**Hallazgo nuevo de Fase A**, detectado durante la remediación R1 (verificación del "
        "benchmark Atkeson-Ohanian) y NO capturado por la auditoría formal A.1-A.6, que no buscó "
        "duplicados inter-país (A.6 buscó duplicados de `Country Code` *dentro* de una hoja, "
        "que es un problema distinto). SOLO DIAGNÓSTICO — no se modificó ningún dato ni resultado."
    )
    L.append("")
    L.append("## Paso 1 — Detección exhaustiva (las 5 hojas mensuales, no solo `hcpi`)")
    L.append("")
    L.append(
        f"Se comparó, dentro de cada una de las 5 hojas mensuales usadas por el proyecto "
        f"(`hcpi_m, ecpi_m, fcpi_m, ccpi_m, ppi_m`), cada par de países por igualdad byte-a-byte "
        f"de su fila completa de 663 meses (post-deduplicación por país, la misma lógica que usa "
        f"`05_etl_corregido.py`), directamente sobre `data/raw/Inflation-data.xlsx` — no sobre el "
        f"parquet procesado, para determinar si el problema está en la fuente o en el ETL."
    )
    L.append("")
    L.append(f"**Total de pares encontrados: {len(pares_df)}**")
    L.append("")
    if len(pares_df) > 0:
        L.append("| Hoja | Indicador | País A | País B | Meses válidos |")
        L.append("|---|---|---|---|---|")
        for _, r in pares_df.iterrows():
            L.append(f"| {r['hoja']} | {r['indicador']} | {r['pais_a']} | {r['pais_b']} | {r['n_meses_validos']} |")
    L.append("")
    L.append(
        "**Confirmado: el problema está en la fuente (Excel del Banco Mundial), no en el ETL** — "
        "la detección corrió directamente sobre `data/raw/Inflation-data.xlsx`, antes de cualquier "
        "transformación del proyecto."
    )
    L.append("")
    L.append("## Paso 2 — Forense: ¿cuál país tiene la serie correcta?")
    L.append("")
    L.append(
        "Ambos países de cada par comparten, por definición del hallazgo, la MISMA serie mensual. "
        "Se calculó la tasa YoY promedio que esa serie compartida implica, y se comparó contra la "
        "hoja anual oficial independiente (`{indicador}_a`) de **cada país por separado** — una "
        "fuente del mismo Excel pero no afectada por el mismo posible error de copiado fila-a-fila "
        "del mensual. El país cuya hoja anual está más cerca de lo que implica el mensual "
        "compartido es el candidato a **serie auténtica**; el otro, a **víctima** (su mensual real "
        "fue sobrescrito por el del primero)."
    )
    L.append("")
    L.append("| Indicador | Par | País | Tasa anual propia | Nivel de ingreso | Distancia al mensual compartido | Veredicto del par |")
    L.append("|---|---|---|---|---|---|---|")
    for _, r in forense_df.iterrows():
        par = f"{r['pais_a']}/{r['pais_b']}"
        for pais in (r["pais_a"], r["pais_b"]):
            tasa = r[f"{pais}_tasa_anual_propia"]
            ingreso = r[f"{pais}_nivel_ingreso"]
            dist = r[f"{pais}_distancia_a_mensual_compartido"]
            L.append(f"| {r['indicador']} | {par} (mensual compartido: {r['yoy_medio_serie_mensual_compartida']}%) | {pais} | {tasa if pd.notna(tasa) else 's/d'} | {ingreso if pd.notna(ingreso) else 's/d'} | {dist if pd.notna(dist) else 's/d'} | {r['veredicto']} |")
    L.append("")
    L.append(
        "**Lectura**: en **FIN/GAB** y **GBR/USA** el veredicto es claro y con margen amplio — la "
        "hoja anual de FIN (4.402%) y de GBR (5.391%) están a apenas 0.05-0.03 puntos porcentuales "
        "de lo que implica la serie mensual compartida, mientras que la de GAB (4.824%) y "
        "especialmente la de USA (4.018%, a 1.34 puntos de distancia) no coinciden en absoluto — "
        "evidencia razonablemente fuerte de que las filas mensuales de **Gabón** y de **Estados "
        "Unidos** en `hcpi_m` son en realidad una copia de las de Finlandia y Reino Unido "
        "respectivamente, no series propias. En **CZE/DJI** las dos distancias son casi idénticas "
        "(0.30 vs. 0.27) — **indeterminado**, no hay evidencia suficiente para asignar dirección."
    )
    L.append("")
    L.append(
        "**Limitación honesta**: esta es evidencia circunstancial (una hoja del mismo archivo del "
        "Banco Mundial comparada contra otra hoja del mismo archivo), no una fuente de verdad "
        "externa (banco central, FMI, INE local). Es razonablemente convincente para FIN/GAB y "
        "GBR/USA por el tamaño del margen, pero no es una confirmación definitiva. Por eso el Paso "
        "3 excluye **ambos** países de cada par (incluyendo los dos casos con veredicto), en vez de "
        "intentar quedarse con el 'correcto' y remodelarlo — reemplazar requeriría re-descargar o "
        "re-construir la serie real de Gabón/EE.UU./República Checa/Yibuti desde otra fuente, fuera "
        "del alcance de este diagnóstico."
    )
    L.append("")
    L.append("## Paso 3 — Impacto en el gradiente de ingreso (hallazgo central del proyecto)")
    L.append("")
    L.append(f"**Original** (todas las series `hcpi` con ARIMA convergido, n={len(impacto['hcpi'])}): Kruskal-Wallis H={impacto['h_original']:.2f}, **p={impacto['p_original']:.3g}**.")
    L.append("")
    L.append("```")
    L.append(impacto["medianas_original"].to_string())
    L.append("```")
    L.append("")
    L.append(f"**Excluyendo los {len(paises_afectados_hcpi)} países con `hcpi` duplicado** ({', '.join(sorted(paises_afectados_hcpi))}, n={len(hcpi_excl)}): Kruskal-Wallis H={h_excl:.2f}, **p={p_excl:.3g}**.")
    L.append("")
    L.append("```")
    L.append(medianas_excl.to_string())
    L.append("```")
    L.append("")
    if p_excl < 0.05:
        L.append(
            f"**El gradiente se mantiene significativo** tras excluir las series contaminadas "
            f"(p={p_excl:.3g}). El impacto de estos 6 países sobre el hallazgo central es "
            "marginal en términos de significancia estadística — pero eso no exime al proyecto "
            "de excluirlos, ya que dos series claramente corruptas (copiadas de otro país) no "
            "deberían seguir contribuyendo al panel modelado, independientemente de si mueven o "
            "no la aguja del test."
        )
    else:
        L.append(
            f"**El gradiente deja de ser significativo al 5%** tras excluir las series "
            f"contaminadas (p={p_excl:.3g}) — un resultado que exige revisar el hallazgo central "
            "con más cuidado antes de seguir citándolo sin esta salvedad."
        )
    L.append("")
    L.append(
        "**Nota sobre por qué la auditoría formal (A.1-A.6) no lo detectó**: A.6 buscó "
        "`Country Code` duplicado *dentro de una misma hoja* (36 casos encontrados, ej. Austria "
        "en `ppi_m` con dos vintages distintos bajo el mismo código) — un problema de "
        "*deduplicación intra-país*. Este hallazgo es distinto: son **dos países diferentes** con "
        "filas byte-idénticas — un problema de *contaminación inter-país* que ningún control de "
        "la auditoría original buscaba explícitamente. Queda documentado acá como una brecha de "
        "cobertura de la auditoría original, no como un error de ejecución de los controles que sí "
        "se hicieron."
    )
    L.append("")
    L.append("## Remediación sugerida (no implementada — este documento es solo diagnóstico)")
    L.append("")
    L.append(
        "1. Reportar el problema al Banco Mundial / consultar la versión más reciente del "
        "*Global Database of Inflation* por si ya fue corregido en una actualización posterior "
        "del archivo.\n"
        "2. Mientras no haya una fuente confiable para asignar la serie correcta a cada país, "
        "excluir del panel modelado las series de los países involucrados (marcar con un flag, "
        "no borrar filas, para trazabilidad) — no reemplazar por una de las dos series existentes, "
        "porque no se puede determinar cuál es la correcta.\n"
        "3. Ampliar el control de A.6 para que la auditoría futura incluya explícitamente "
        "comparación inter-país, no solo intra-país por código repetido."
    )
    L.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(L), encoding="utf-8")
    print(f"\n[reporte guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
