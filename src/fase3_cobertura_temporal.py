"""FASE 3 del ETL/EDA: cobertura temporal y huecos a nivel de datos (SOLO DIAGNÓSTICO).

Trabaja directo sobre el índice crudo de las 5 hojas mensuales de
data/raw/Inflation-data.xlsx (no sobre el YoY del parquet, que todavía no
ramifica el tratamiento por Indicator Type — ver Fase 1). Excluye las series
ya identificadas como problemáticas para no contaminar el análisis de
cobertura, y lo documenta explícitamente. No corrige ningún dato.
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "Inflation-data.xlsx"
REPORT_PATH = ROOT / "reports" / "fase3_cobertura.md"
FIG_PATH = ROOT / "reports" / "figures" / "fase3_distribucion_longitud_por_indicador.png"

HOJAS_MENSUALES = ["hcpi_m", "ecpi_m", "fcpi_m", "ccpi_m", "ppi_m"]
CODIGO_PAIS_RE = re.compile(r"^[A-Z]{3}$")

# Series excluidas del análisis de cobertura (Fase 1 / Fase 2): no son un
# índice limpio, así que su "cobertura" no es comparable con el resto.
EXCLUSIONES = {
    ("ecpi_m", "IND"): "Fase 1: Indicator Type='Inflation', ya es tasa, no índice",
    ("ecpi_m", "IDN"): "Fase 1: Indicator Type='Inflation', ya es tasa, no índice",
    ("ecpi_m", "VEN"): "Fase 2: índice en 0.0 exacto ~60 meses, probable placeholder de dato faltante",
    ("fcpi_m", "VEN"): "Fase 2: índice en 0.0 exacto ~51 meses, probable placeholder de dato faltante",
}

PISO_ARIMA = 60   # 5 años
PISO_GARCH = 100  # ~8.3 años
CUTOFF_COMPLETA = 197501  # arranca en los primeros 5 años del panel (1970-1975)
UMBRAL_HUECO_GRAVE = 6    # meses; un tramo faltante >= esto se considera grave
MAX_LISTADO = 15


def es_fila_de_pais(codigo) -> bool:
    return isinstance(codigo, str) and bool(CODIGO_PAIS_RE.match(codigo))


def columnas_fecha(df: pd.DataFrame):
    return [c for c in df.columns if isinstance(c, int) and 190001 <= c <= 210012]


def deduplicar_por_completitud(df: pd.DataFrame, date_cols) -> pd.DataFrame:
    if df["Country Code"].duplicated().any():
        n_validos = df[date_cols].notna().sum(axis=1)
        idx_mas_completo = n_validos.groupby(df["Country Code"]).idxmax()
        df = df.loc[idx_mas_completo]
    return df


def analizar_serie(valores: pd.Series, date_cols):
    valid = valores.notna().to_numpy()
    idxv = valid.nonzero()[0]
    if len(idxv) == 0:
        return None  # sin ningún dato válido

    primer_idx, ultimo_idx = idxv[0], idxv[-1]
    primer_mes, ultimo_mes = date_cols[primer_idx], date_cols[ultimo_idx]
    span = ultimo_idx - primer_idx + 1
    meses_con_dato = len(idxv)
    densidad = meses_con_dato / span

    tramo = valid[primer_idx : ultimo_idx + 1]
    huecos = []
    en_hueco, inicio = False, None
    for i, v in enumerate(tramo):
        if not v and not en_hueco:
            en_hueco, inicio = True, i
        elif v and en_hueco:
            huecos.append((date_cols[primer_idx + inicio], date_cols[primer_idx + i - 1], i - inicio))
            en_hueco = False
    if en_hueco:
        huecos.append(
            (date_cols[primer_idx + inicio], date_cols[ultimo_idx], len(tramo) - inicio)
        )

    n_huecos = len(huecos)
    meses_faltantes_internos = sum(h[2] for h in huecos)
    patron_periodico = n_huecos >= 10 and max((h[2] for h in huecos), default=0) <= 2

    if n_huecos == 0:
        clasificacion = "completa" if primer_mes <= CUTOFF_COMPLETA else "arranque tardío"
    elif n_huecos <= 2:
        clasificacion = "con huecos internos"
    else:
        clasificacion = "fragmentada"

    return {
        "primer_mes": primer_mes,
        "ultimo_mes": ultimo_mes,
        "span": span,
        "meses_con_dato": meses_con_dato,
        "densidad": densidad,
        "n_huecos": n_huecos,
        "meses_faltantes_internos": meses_faltantes_internos,
        "huecos": huecos,
        "clasificacion": clasificacion,
        "patron_periodico": patron_periodico,
    }


def construir_dataset(path_excel: Path):
    filas = []
    n_excluidas = 0
    n_sin_dato = 0
    for hoja in HOJAS_MENSUALES:
        df = pd.read_excel(path_excel, sheet_name=hoja)
        date_cols = columnas_fecha(df)
        df_p = df[df["Country Code"].apply(es_fila_de_pais)]
        df_p = deduplicar_por_completitud(df_p, date_cols)

        for _, fila in df_p.iterrows():
            codigo = fila["Country Code"]
            if (hoja, codigo) in EXCLUSIONES:
                n_excluidas += 1
                continue
            info = analizar_serie(fila[date_cols], date_cols)
            if info is None:
                n_sin_dato += 1
                continue
            info.update({"hoja": hoja, "codigo_pais": codigo, "pais": fila["Country"]})
            filas.append(info)

    return pd.DataFrame(filas), n_excluidas, n_sin_dato


def graficar_distribucion(tabla: pd.DataFrame):
    hojas = HOJAS_MENSUALES
    fig, axes = plt.subplots(1, len(hojas), figsize=(20, 4), sharey=True)
    for ax, hoja in zip(axes, hojas):
        datos = tabla.loc[tabla["hoja"] == hoja, "meses_con_dato"]
        ax.hist(datos, bins=25, color="steelblue", edgecolor="white")
        ax.axvline(PISO_ARIMA, color="darkorange", linestyle="--", linewidth=1, label=f"ARIMA={PISO_ARIMA}")
        ax.axvline(PISO_GARCH, color="crimson", linestyle="--", linewidth=1, label=f"GARCH={PISO_GARCH}")
        ax.set_title(hoja)
        ax.set_xlabel("meses con dato")
    axes[0].set_ylabel("cantidad de series")
    axes[0].legend(fontsize=8)
    fig.suptitle("Distribución de longitud de serie (meses válidos) por indicador")
    fig.tight_layout()
    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_PATH, dpi=150)
    plt.close(fig)


def construir_markdown(tabla: pd.DataFrame, n_excluidas: int, n_sin_dato: int) -> str:
    L = []
    L.append("# Fase 3 — Cobertura temporal y huecos a nivel de datos")
    L.append("")
    L.append(
        "Informe generado por `src/fase3_cobertura_temporal.py`, trabajando directo sobre "
        "el índice crudo de las 5 hojas mensuales de `data/raw/Inflation-data.xlsx` (no sobre "
        "el YoY del parquet actual — ver Fase 1 sobre por qué ese cálculo todavía no es válido "
        "para todas las filas). **Solo diagnóstico: no se corrige ningún dato.**"
    )
    L.append("")
    L.append("## Exclusiones aplicadas antes del análisis")
    L.append("")
    L.append(
        f"Se excluyeron **{n_excluidas} series** ya identificadas como problemáticas en Fases "
        "1-2, para que no contaminen las métricas de cobertura (su 'cobertura' no sería "
        "comparable con la de un índice real):"
    )
    L.append("")
    for (hoja, codigo), motivo in EXCLUSIONES.items():
        L.append(f"- `{hoja}` / {codigo}: {motivo}")
    L.append("")
    L.append(
        f"Además, **{n_sin_dato} filas** de país no tienen NINGÚN valor de índice en toda la "
        "hoja (no es un hueco, es ausencia total de dato) — se excluyen del panel de cobertura "
        "por no tener span que medir, y quedan documentadas para la fase de corrección "
        "(candidatas a eliminarse directamente del ETL, no a rescatarse con imputación)."
    )
    L.append("")
    L.append(
        f"Los duplicados detectados en Fase 2 (36 país-hoja) se resolvieron acá igual que en "
        "`01_descarga_datos.py`: se conserva la fila con más puntos válidos por `Country Code`."
    )
    L.append("")

    n_total = len(tabla)
    L.append(f"## 1-2. Cobertura y clasificación por serie ({n_total} series analizadas)")
    L.append("")
    L.append(
        "Por cada serie se calculó: primer/último mes con dato, `span` (meses entre el primero "
        "y el último inclusive), `meses_con_dato` (conteo real de datos válidos en ese span), "
        "`densidad = meses_con_dato / span`, y los huecos internos (tramos de meses faltantes "
        "estrictamente dentro del span, sin contar el arranque tardío ni el final)."
    )
    L.append("")
    L.append("**Reglas de clasificación** (heurística documentada, no absoluta):")
    L.append("")
    L.append(f"- **completa**: 0 huecos internos y arranca en {CUTOFF_COMPLETA} o antes (primeros 5 años del panel).")
    L.append(f"- **arranque tardío**: 0 huecos internos pero arranca después de {CUTOFF_COMPLETA}.")
    L.append("- **con huecos internos**: 1 o 2 tramos faltantes dentro del span.")
    L.append("- **fragmentada**: 3 o más tramos faltantes dentro del span.")
    L.append("")

    resumen_clasif = (
        tabla.groupby(["hoja", "clasificacion"]).size().unstack(fill_value=0)
        .reindex(columns=["completa", "arranque tardío", "con huecos internos", "fragmentada"], fill_value=0)
    )
    L.append("| Hoja | completa | arranque tardío | con huecos internos | fragmentada | Total |")
    L.append("|---|---|---|---|---|---|")
    for hoja in HOJAS_MENSUALES:
        fila = resumen_clasif.loc[hoja]
        L.append(
            f"| {hoja} | {fila['completa']} | {fila['arranque tardío']} "
            f"| {fila['con huecos internos']} | {fila['fragmentada']} | {fila.sum()} |"
        )
    L.append("")

    L.append("## 3. Distribución de longitud de serie por indicador")
    L.append("")
    L.append(
        f"Histograma guardado en `{FIG_PATH.relative_to(ROOT).as_posix()}` — un panel por "
        "indicador (no agregado, para no mezclar la cobertura de hcpi con la de ccpi, que "
        "sistemáticamente tiene menos países reportando)."
    )
    L.append("")
    percentiles = tabla.groupby("hoja")["meses_con_dato"].describe(
        percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]
    )
    L.append("Percentiles de `meses_con_dato` por hoja:")
    L.append("")
    L.append("| Hoja | n | media | min | p10 | p25 | mediana | p75 | p90 | max |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for hoja in HOJAS_MENSUALES:
        r = percentiles.loc[hoja]
        L.append(
            f"| {hoja} | {r['count']:.0f} | {r['mean']:.0f} | {r['min']:.0f} | {r['10%']:.0f} "
            f"| {r['25%']:.0f} | {r['50%']:.0f} | {r['75%']:.0f} | {r['90%']:.0f} | {r['max']:.0f} |"
        )
    L.append("")

    L.append("## 4. Series aptas por piso mínimo")
    L.append("")
    L.append(
        f"Piso ARIMA sugerido: **{PISO_ARIMA} meses** (5 años). Piso GARCH sugerido: "
        f"**{PISO_GARCH} meses** (~8.3 años, GARCH necesita más historia para estimar la "
        "volatilidad de forma estable). Conteo de series con `meses_con_dato >=` cada piso, "
        "por hoja — es un conteo simple por cantidad de dato, todavía sin filtrar por huecos "
        "internos (eso se cruza en la sección 6)."
    )
    L.append("")
    L.append(f"| Hoja | Total series | ≥{PISO_ARIMA} (ARIMA) | ≥{PISO_GARCH} (GARCH) |")
    L.append("|---|---|---|---|")
    for hoja in HOJAS_MENSUALES:
        sub = tabla[tabla["hoja"] == hoja]
        n_arima = (sub["meses_con_dato"] >= PISO_ARIMA).sum()
        n_garch = (sub["meses_con_dato"] >= PISO_GARCH).sum()
        L.append(f"| {hoja} | {len(sub)} | {n_arima} | {n_garch} |")
    L.append("")

    L.append("## 5. Huecos internos: ¿cuántas series quedan comprometidas?")
    L.append("")
    con_huecos = tabla[tabla["n_huecos"] > 0].copy()
    n_graves = int((con_huecos["huecos"].apply(lambda hs: max(h[2] for h in hs)) >= UMBRAL_HUECO_GRAVE).sum())
    L.append(
        f"**{len(con_huecos)}** de {n_total} series tienen al menos un hueco interno. De esas, "
        f"**{n_graves}** tienen un tramo faltante de {UMBRAL_HUECO_GRAVE} meses o más (\"hueco "
        "grave\" — inviable para imputación simple, requeriría segmentar la serie o descartar "
        "el tramo previo al hueco)."
    )
    L.append("")
    if len(con_huecos):
        peores = con_huecos.assign(
            hueco_max=con_huecos["huecos"].apply(lambda hs: max(h[2] for h in hs))
        ).sort_values(["hueco_max", "meses_faltantes_internos"], ascending=False).head(MAX_LISTADO)
        L.append(f"Las {min(MAX_LISTADO, len(peores))} series con el hueco interno más largo:")
        L.append("")
        L.append("| Hoja | Código | País | N° huecos | Meses faltantes (total) | Hueco más largo | Detalle |")
        L.append("|---|---|---|---|---|---|---|")
        for _, r in peores.iterrows():
            detalle = "; ".join(f"{h[0]}–{h[1]} ({h[2]}m)" for h in r["huecos"][:4])
            if len(r["huecos"]) > 4:
                detalle += f" ... y {len(r['huecos']) - 4} más"
            L.append(
                f"| {r['hoja']} | {r['codigo_pais']} | {r['pais']} | {r['n_huecos']} "
                f"| {r['meses_faltantes_internos']} | {r['hueco_max']} | {detalle} |"
            )
    else:
        L.append("Ninguna serie tiene huecos internos. ✅")
    L.append("")

    periodicas = tabla[tabla["patron_periodico"]]
    if len(periodicas):
        L.append(
            "**Hallazgo específico — desfasaje de frecuencia, no huecos aleatorios:** algunas "
            "series marcadas como 'fragmentadas' no tienen datos faltantes al azar, sino un "
            "patrón perfectamente regular (10+ tramos faltantes, todos de 1-2 meses) — son "
            "series que en realidad se reportan trimestralmente pero están cargadas en la hoja "
            "mensual:"
        )
        L.append("")
        for _, r in periodicas.iterrows():
            L.append(f"- `{r['hoja']}` / {r['codigo_pais']} ({r['pais']}): {r['n_huecos']} tramos, todos ≤2 meses")
        L.append("")
        L.append(
            "Para estas series, \"imputar los huecos\" no es el tratamiento correcto — lo "
            "correcto es re-muestrear la serie a frecuencia trimestral real antes de modelar, "
            "no forzarla a mensual. Queda para la fase de corrección decidir si se excluyen del "
            "panel mensual o se tratan aparte."
        )
        L.append("")

    L.append("## 6. Tabla resumen: series efectivamente modelables por indicador")
    L.append("")
    L.append(
        "Una serie se considera **modelable sin tratamiento adicional** si no tiene ningún "
        f"hueco interno (clasificación 'completa' o 'arranque tardío') Y `meses_con_dato` "
        "alcanza el piso correspondiente. Series con huecos internos podrían rescatarse más "
        "adelante con interpolación/segmentación, pero eso es una decisión de la fase de "
        "corrección, no de este diagnóstico."
    )
    L.append("")
    L.append(
        "| Indicador | Series totales* | Modelables ARIMA (≥60m, sin huecos) | Modelables GARCH (≥100m, sin huecos) "
        "| Caen por span corto | Caen por huecos internos |"
    )
    L.append("|---|---|---|---|---|---|")
    for hoja in HOJAS_MENSUALES:
        sub = tabla[tabla["hoja"] == hoja]
        sin_huecos = sub["n_huecos"] == 0
        modelable_arima = sin_huecos & (sub["meses_con_dato"] >= PISO_ARIMA)
        modelable_garch = sin_huecos & (sub["meses_con_dato"] >= PISO_GARCH)
        cae_span = (sub["meses_con_dato"] < PISO_ARIMA) & sin_huecos
        cae_huecos = ~sin_huecos
        L.append(
            f"| {hoja} | {len(sub)} | {modelable_arima.sum()} | {modelable_garch.sum()} "
            f"| {cae_span.sum()} | {cae_huecos.sum()} |"
        )
    L.append("")
    L.append(
        f"\\* Series totales = después de excluir las {n_excluidas} ya conocidas como "
        f"problemáticas (Fases 1-2) y las {n_sin_dato} sin ningún dato de índice."
    )
    L.append("")

    total_arima = 0
    total_garch = 0
    for hoja in HOJAS_MENSUALES:
        sub = tabla[tabla["hoja"] == hoja]
        sin_huecos = sub["n_huecos"] == 0
        total_arima += int((sin_huecos & (sub["meses_con_dato"] >= PISO_ARIMA)).sum())
        total_garch += int((sin_huecos & (sub["meses_con_dato"] >= PISO_GARCH)).sum())

    L.append("## Conclusión: conteo realista de series modelables")
    L.append("")
    L.append(
        f"Sumando las 5 hojas mensuales: **{total_arima} series país×indicador son modelables "
        f"para ARIMA** (span ≥{PISO_ARIMA} meses, sin huecos internos) y **{total_garch} para "
        f"GARCH** (span ≥{PISO_GARCH} meses, sin huecos internos), de un universo de "
        f"{n_total} series con al menos algo de dato ({n_total + n_excluidas + n_sin_dato} "
        "filas de país en las 5 hojas originales). La brecha entre ARIMA y GARCH refleja que "
        "GARCH necesita bastante más historia para estimar volatilidad de forma estable — "
        "varios países con series cortas o con huecos van a quedar aptos para uno pero no "
        "para el otro. Esto es más estricto que el piso de 36 puntos usado en "
        "`02_calidad_series.py` (que medía puntos válidos de YoY, no meses de índice sin "
        "huecos) — la diferencia es esperable: acá se exige además la ausencia de huecos "
        "internos, que ese chequeo anterior no contemplaba."
    )
    L.append("")

    return "\n".join(L)


def main() -> None:
    tabla, n_excluidas, n_sin_dato = construir_dataset(RAW_PATH)

    graficar_distribucion(tabla)

    md = construir_markdown(tabla, n_excluidas, n_sin_dato)
    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")
    print(f"[figura guardada en {FIG_PATH}]")


if __name__ == "__main__":
    main()
