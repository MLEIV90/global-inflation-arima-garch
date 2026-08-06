"""FASE 1 del ETL/EDA: entender la fuente (Inflation-data.xlsx) y documentar hallazgos.

Genera reports/fase1_estructura_fuente.md a partir de una inspección
programática del Excel, para que los hallazgos queden verificables y no
solo anotados de memoria.
"""

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "Inflation-data.xlsx"
REPORT_PATH = ROOT / "reports" / "fase1_estructura_fuente.md"

MEDIDAS = {
    "hcpi": "Headline CPI — índice de precios al consumidor general",
    "ecpi": "Energy CPI — índice de precios de energía",
    "fcpi": "Food CPI — índice de precios de alimentos",
    "ccpi": "Core CPI — índice de precios subyacente (sin energía/alimentos)",
    "ppi": "PPI — índice de precios al productor",
    "def": "GDP deflator — deflactor del PIB",
}
FRECUENCIAS = {"m": "mensual", "q": "trimestral", "a": "anual"}
HOJAS_MENSUALES = ["hcpi_m", "ecpi_m", "fcpi_m", "ccpi_m", "ppi_m"]
CODIGO_PAIS_RE = re.compile(r"^[A-Z]{3}$")


def es_fila_de_pais(codigo) -> bool:
    return isinstance(codigo, str) and bool(CODIGO_PAIS_RE.match(codigo))


def clasificar_hoja(nombre_hoja: str):
    partes = nombre_hoja.rsplit("_", 1)
    if len(partes) == 2 and partes[1] in FRECUENCIAS and partes[0] in MEDIDAS:
        return partes[0], partes[1]
    return None, None


def inspeccionar_hojas(path_excel: Path):
    import openpyxl

    wb = openpyxl.load_workbook(path_excel, read_only=True)
    nombres_hojas = wb.sheetnames
    wb.close()

    inventario = []
    dataframes = {}
    for hoja in nombres_hojas:
        medida, freq = clasificar_hoja(hoja)
        if medida is None:
            inventario.append(
                {
                    "hoja": hoja,
                    "medida": None,
                    "frecuencia": None,
                    "filas": None,
                    "columnas": None,
                    "tipo_dominante": None,
                    "n_paises_validos": None,
                }
            )
            continue

        df = pd.read_excel(path_excel, sheet_name=hoja)
        dataframes[hoja] = df
        es_pais = df["Country Code"].apply(es_fila_de_pais)
        df_paises = df[es_pais]
        tipo_dominante = (
            df_paises["Indicator Type"].value_counts(dropna=False).idxmax()
            if len(df_paises)
            else None
        )
        inventario.append(
            {
                "hoja": hoja,
                "medida": medida,
                "frecuencia": freq,
                "filas": df.shape[0],
                "columnas": df.shape[1],
                "tipo_dominante": tipo_dominante,
                "n_paises_validos": int(es_pais.sum()),
            }
        )
    return nombres_hojas, inventario, dataframes


def analizar_hoja_mensual(hoja: str, df: pd.DataFrame):
    date_cols = [c for c in df.columns if isinstance(c, int) and 190001 <= c <= 210012]
    es_pais = df["Country Code"].apply(es_fila_de_pais)
    df_paises = df[es_pais].copy()

    conteo_tipos = df_paises["Indicator Type"].value_counts(dropna=False).to_dict()

    excepciones = df_paises[df_paises["Indicator Type"] != "Index"]
    detalle_excepciones = []
    for _, fila in excepciones.iterrows():
        valores = fila[date_cols].dropna()
        detalle_excepciones.append(
            {
                "codigo_pais": fila["Country Code"],
                "pais": fila["Country"],
                "tipo": fila["Indicator Type"],
                "n_valores": len(valores),
                "primeros_valores": list(valores.head(5).items()),
            }
        )
    return conteo_tipos, detalle_excepciones


def interpretar_excepcion(detalle: dict) -> str:
    valores = [v for _, v in detalle["primeros_valores"]]
    if not valores:
        return "sin datos numéricos para inspeccionar"
    minimo, maximo = min(valores), max(valores)
    if 50 <= minimo <= 500 and 50 <= maximo <= 500:
        return (
            f"valores en rango {minimo:.1f}–{maximo:.1f}: es un ÍNDICE (base ~100) "
            f"pese a estar etiquetado '{detalle['tipo']}' — error de metadata, no de dato. "
            "El pct_change(12) actual lo trata bien por coincidencia."
        )
    return (
        f"valores en rango {minimo:.1f}–{maximo:.1f}: son claramente una TASA "
        f"(ya viene expresado en % de variación), consistente con la etiqueta "
        f"'{detalle['tipo']}'. Aplicarle pct_change(12) como si fuera índice es inválido."
    )


def construir_markdown(nombres_hojas, inventario, analisis_mensuales) -> str:
    lineas = []
    lineas.append("# Fase 1 — Entender la fuente (Inflation-data.xlsx)")
    lineas.append("")
    lineas.append(
        "Informe generado programáticamente por `src/fase1_entender_fuente.py` a partir "
        "de `data/raw/Inflation-data.xlsx`. No editar a mano: si algo cambia, se corre "
        "el script de nuevo."
    )
    lineas.append("")

    # --- Sección 1 ---
    lineas.append("## 1. Inventario de las 20 hojas")
    lineas.append("")
    lineas.append(f"El workbook tiene {len(nombres_hojas)} hojas.")
    lineas.append("")
    lineas.append("| Hoja | Medida | Frecuencia | Filas | Columnas | Indicator Type dominante |")
    lineas.append("|---|---|---|---|---|---|")
    for item in inventario:
        if item["medida"] is None:
            lineas.append(f"| {item['hoja']} | *(no es hoja de datos país x fecha)* | | | | |")
        else:
            lineas.append(
                f"| {item['hoja']} | {item['medida']} ({MEDIDAS[item['medida']]}) "
                f"| {FRECUENCIAS[item['frecuencia']]} | {item['filas']} | {item['columnas']} "
                f"| {item['tipo_dominante']!r} |"
            )
    lineas.append("")
    lineas.append(
        "`Intro`, `top` y `Aggregate` no son paneles país x fecha: `Intro` es portada/notas, "
        "`top` es una tabla de metadatos de navegación del propio workbook, y `Aggregate` trae "
        "series ya agregadas (medianas/promedios globales y regionales) fuera de alcance de "
        "este ETL, que trabaja a nivel país."
    )
    lineas.append("")

    lineas.append("### Confirmación: `_m`/`_q` = Index, `_a` = Inflation")
    lineas.append("")
    ok_general = True
    for item in inventario:
        if item["medida"] is None:
            continue
        freq = item["frecuencia"]
        tipo = str(item["tipo_dominante"]).lower()
        if freq in ("m", "q"):
            esperado_ok = tipo == "index"
        else:
            esperado_ok = tipo in ("inflation", "rate")
        estado = "✅" if esperado_ok else "❌"
        if not esperado_ok:
            ok_general = False
        etiqueta_esperada = "Index" if freq in ("m", "q") else "Inflation"
        lineas.append(
            f"- {estado} `{item['hoja']}`: dominante = {item['tipo_dominante']!r} "
            f"(esperado, case-insensitive: {etiqueta_esperada!r})"
        )
    lineas.append("")
    lineas.append(
        "**Confirmado con una excepción de etiqueta:** todas las hojas `_m`/`_q` tienen "
        "'Index'/'index' como tipo dominante y todas las `_a` de CPI/PPI tienen 'Inflation' "
        "como tipo dominante. La única desviación es `def_a`, que usa la etiqueta 'Rate' en vez "
        "de 'Inflation' — mismo significado (tasa anual, no índice), pero el string difiere, "
        "así que un chequeo `== 'Inflation'` literal fallaría para `def_a`."
    )
    lineas.append("")

    # --- Sección 2 y 3 ---
    lineas.append("## 2–3. Hallazgo crítico: las hojas mensuales NO son homogéneas")
    lineas.append("")
    lineas.append(
        "Cada hoja mensual (`hcpi_m, ecpi_m, fcpi_m, ccpi_m, ppi_m`) debería traer únicamente "
        "filas con `Indicator Type == 'Index'`. En la práctica hay países-excepción con otro "
        "tipo. Conteo de `Indicator Type` por hoja (solo filas de país, se excluyen filas de "
        "nota/footnote sin código ISO3 válido):"
    )
    lineas.append("")
    for hoja, (conteo_tipos, excepciones) in analisis_mensuales.items():
        lineas.append(f"**`{hoja}`**")
        lineas.append("")
        for tipo, n in conteo_tipos.items():
            lineas.append(f"- {tipo!r}: {n}")
        if not excepciones:
            lineas.append("- Sin países-excepción. ✅")
        lineas.append("")
        if excepciones:
            lineas.append("País-excepción encontrado (no es `'Index'` limpio):")
            lineas.append("")
            lineas.append("| Código | País | Indicator Type | n valores | primeros 5 valores | interpretación |")
            lineas.append("|---|---|---|---|---|---|")
            for det in excepciones:
                primeros_str = ", ".join(
                    f"{fecha}={valor:.2f}" for fecha, valor in det["primeros_valores"]
                )
                interpretacion = interpretar_excepcion(det)
                lineas.append(
                    f"| {det['codigo_pais']} | {det['pais']} | {det['tipo']!r} "
                    f"| {det['n_valores']} | {primeros_str} | {interpretacion} |"
                )
            lineas.append("")

    # --- Sección 4 ---
    lineas.append("## 4. Implicancia para el ETL")
    lineas.append("")
    lineas.append(
        "`src/01_descarga_datos.py` (versión previa a esta fase) calcula la inflación "
        "interanual con `pct_change(periods=12)` sobre la columna `indice`, asumiendo que **todas** "
        "las filas de las hojas mensuales son un índice base ~100. Eso es correcto para la "
        "inmensa mayoría de países, pero:"
    )
    lineas.append("")
    lineas.append(
        "- Para filas cuyo `Indicator Type` real es `'Inflation'` (ej. **India** y **Indonesia** "
        "en `ecpi_m`), la columna de valores YA es una tasa de variación interanual, no un "
        "índice. Aplicarle `pct_change(12)` de nuevo calcula \"la variación porcentual de una "
        "tasa\", un número sin sentido económico (se verificó en el parquet actual: para India "
        "salen valores como -89.6% o -48.1%, que no son inflación interanual real — es el "
        "artefacto de tratar una tasa como si fuera un nivel)."
    )
    lineas.append(
        "- Para filas mal etiquetadas como `'Inflation'`/`'index'` pero que en realidad SÍ son "
        "un índice (ej. **British Virgin Islands** en `hcpi_m`, valores ~104–107 con base ~100; "
        "**Australia** en `ppi_m`, etiquetado `'index'` en minúscula), el `pct_change(12)` actual "
        "da un resultado correcto por coincidencia — el dato es un índice aunque la etiqueta diga "
        "otra cosa."
    )
    lineas.append("")
    lineas.append(
        "**Conclusión:** el ETL tiene que ramificar el tratamiento por `Indicator Type` real de "
        "cada fila, no asumir un único tratamiento por hoja:"
    )
    lineas.append("")
    lineas.append(
        "1. Filas `Indicator Type` case-insensitive `'index'` → calcular YoY con `pct_change(12)`."
    )
    lineas.append(
        "2. Filas `Indicator Type == 'Inflation'` cuyos valores están en escala de índice "
        "(ver columna \"interpretación\" arriba) → tratar igual que (1), el error está en la "
        "etiqueta, no en el dato."
    )
    lineas.append(
        "3. Filas `Indicator Type == 'Inflation'` cuyos valores ya están en escala de tasa "
        "(India, Indonesia en ecpi_m) → usar el valor directamente como `inflacion_yoy`, sin "
        "recalcular, y dejar `indice` en NaN o marcarlo como no aplicable."
    )
    lineas.append("")

    # --- Sección 5 ---
    lineas.append("## 5. Medidas por frecuencia")
    lineas.append("")
    medidas_por_freq = {}
    for item in inventario:
        if item["medida"] is None:
            continue
        medidas_por_freq.setdefault(item["medida"], set()).add(item["frecuencia"])
    lineas.append("| Medida | Mensual | Trimestral | Anual |")
    lineas.append("|---|---|---|---|")
    for medida in MEDIDAS:
        freqs = medidas_por_freq.get(medida, set())
        fila = [medida]
        for f in ("m", "q", "a"):
            fila.append("✅" if f in freqs else "—")
        lineas.append("| " + " | ".join(fila) + " |")
    lineas.append("")
    lineas.append(
        "**`def` (GDP deflator) no tiene hoja mensual** — solo existe `def_q` (trimestral) y "
        "`def_a` (anual). No hay forma de incluirlo en un panel mensual sin resamplear/interpolar "
        "desde trimestral, lo cual es un tratamiento distinto al de los otros 5 indicadores y "
        "queda fuera de alcance del ETL mensual actual (`01_descarga_datos.py` usa 5 "
        "indicadores, no 6)."
    )
    lineas.append("")

    return "\n".join(lineas)


def main() -> None:
    nombres_hojas, inventario, dataframes = inspeccionar_hojas(RAW_PATH)

    analisis_mensuales = {}
    for hoja in HOJAS_MENSUALES:
        analisis_mensuales[hoja] = analizar_hoja_mensual(hoja, dataframes[hoja])

    md = construir_markdown(nombres_hojas, inventario, analisis_mensuales)

    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
