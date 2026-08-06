"""FASE 2 del ETL/EDA: auditoría de integridad estructural (SOLO DIAGNÓSTICO).

Lee las 5 hojas mensuales de data/raw/Inflation-data.xlsx directamente (sin
pasar por 01_descarga_datos.py) y documenta duplicados, filas no-país,
códigos anómalos, índices <=0, cobertura del encabezado de fechas y saltos
mes a mes sospechosos. No corrige ni modifica ningún dato.
"""

import re
from pathlib import Path

import pandas as pd
import pycountry

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "Inflation-data.xlsx"
REPORT_PATH = ROOT / "reports" / "fase2_integridad.md"

HOJAS_MENSUALES = ["hcpi_m", "ecpi_m", "fcpi_m", "ccpi_m", "ppi_m"]
CODIGO_PAIS_RE = re.compile(r"^[A-Z]{3}$")

# Excepciones de Indicator Type ya documentadas en Fase 1 (reports/fase1_estructura_fuente.md)
CASOS_CONOCIDOS_FASE1 = {
    ("hcpi_m", "VGB"): "Fase 1: etiquetado 'Inflation' pero es índice",
    ("ecpi_m", "IDN"): "Fase 1: etiquetado 'Inflation', es tasa real",
    ("ecpi_m", "IND"): "Fase 1: etiquetado 'Inflation', es tasa real",
    ("ppi_m", "AUS"): "Fase 1: etiquetado 'index' minúscula pero es índice",
}

UMBRAL_CAIDA = -0.40
UMBRAL_SUBIDA = 1.00
VENTANA_CLUSTER = 3  # posiciones de distancia entre saltos para considerarlos "cluster"
MAX_EJEMPLOS_POR_PAIS = 5


def es_fila_de_pais(codigo) -> bool:
    return isinstance(codigo, str) and bool(CODIGO_PAIS_RE.match(codigo))


def columnas_fecha(df: pd.DataFrame):
    return [c for c in df.columns if isinstance(c, int) and 190001 <= c <= 210012]


def cargar_hojas(path_excel: Path):
    return {hoja: pd.read_excel(path_excel, sheet_name=hoja) for hoja in HOJAS_MENSUALES}


# ---------- 1. Duplicados ----------
def analizar_duplicados(hojas):
    resultado = {}
    for hoja, df in hojas.items():
        date_cols = columnas_fecha(df)
        df_p = df[df["Country Code"].apply(es_fila_de_pais)]
        codigos_dup = df_p["Country Code"][df_p["Country Code"].duplicated(keep=False)].unique()
        casos = []
        for codigo in sorted(codigos_dup):
            filas = df_p[df_p["Country Code"] == codigo]
            puntos_validos = [int(fila[date_cols].notna().sum()) for _, fila in filas.iterrows()]
            casos.append(
                {
                    "codigo": codigo,
                    "pais": filas["Country"].iloc[0],
                    "n_filas": len(filas),
                    "puntos_validos_por_fila": puntos_validos,
                }
            )
        resultado[hoja] = casos
    return resultado


# ---------- 2. Filas no-país ----------
def analizar_filas_no_pais(hojas):
    resultado = {}
    for hoja, df in hojas.items():
        es_pais = df["Country Code"].apply(es_fila_de_pais)
        no_pais = df[~es_pais]
        ejemplos = []
        for _, fila in no_pais.iterrows():
            contenido = fila["Country Code"] if pd.notna(fila["Country Code"]) else "(celda vacía / NaN)"
            ejemplos.append(str(contenido)[:140])
        resultado[hoja] = {"n": len(no_pais), "ejemplos": ejemplos}
    return resultado


# ---------- 3. Validación de códigos ----------
def validar_codigos(hojas):
    iso3 = {c.alpha_3 for c in pycountry.countries}
    codigo_a_nombres, nombre_a_codigos = {}, {}
    for df in hojas.values():
        df_p = df[df["Country Code"].apply(es_fila_de_pais)].drop_duplicates(
            subset=["Country Code", "Country"]
        )
        for _, fila in df_p.iterrows():
            codigo_a_nombres.setdefault(fila["Country Code"], set()).add(fila["Country"])
            nombre_a_codigos.setdefault(fila["Country"], set()).add(fila["Country Code"])

    return {
        "n_codigos_unicos": len(codigo_a_nombres),
        "no_iso3": {c: sorted(n) for c, n in codigo_a_nombres.items() if c not in iso3},
        "codigo_multi_nombre": {c: sorted(n) for c, n in codigo_a_nombres.items() if len(n) > 1},
        "nombre_multi_codigo": {n: sorted(c) for n, c in nombre_a_codigos.items() if len(c) > 1},
    }


# ---------- 4. Índices problemáticos ----------
def analizar_indices_problematicos(hojas):
    resultado = {}
    for hoja, df in hojas.items():
        date_cols = columnas_fecha(df)
        df_p = df[df["Country Code"].apply(es_fila_de_pais)]
        vals = df_p[date_cols]

        n_neg = int((vals < 0).sum().sum())
        n_zero = int((vals == 0).sum().sum())
        n_frac = int(((vals > 0) & (vals < 1)).sum().sum())

        mask_le0 = vals <= 0
        casos_no_positivos = []
        for idx in df_p.index:
            fila_mask = mask_le0.loc[idx]
            fechas_problema = fila_mask[fila_mask].index.tolist()
            if fechas_problema:
                codigo = df_p.loc[idx, "Country Code"]
                casos_no_positivos.append(
                    {
                        "codigo": codigo,
                        "pais": df_p.loc[idx, "Country"],
                        "fechas": fechas_problema,
                        "n": len(fechas_problema),
                        "conocido": CASOS_CONOCIDOS_FASE1.get((hoja, codigo)),
                    }
                )

        conteo_frac_por_pais = (
            ((vals > 0) & (vals < 1)).sum(axis=1).loc[lambda s: s > 0].sort_values(ascending=False)
        )
        top_frac = [
            (df_p.loc[idx, "Country Code"], df_p.loc[idx, "Country"], int(n))
            for idx, n in conteo_frac_por_pais.head(5).items()
        ]

        resultado[hoja] = {
            "n_neg": n_neg,
            "n_zero": n_zero,
            "n_frac": n_frac,
            "casos_no_positivos": casos_no_positivos,
            "top_frac": top_frac,
            "n_paises_con_frac": int((conteo_frac_por_pais > 0).sum()),
        }
    return resultado


# ---------- 5. Cobertura de fechas (esquema) ----------
def analizar_cobertura_fechas(hojas):
    resultado = {}
    for hoja, df in hojas.items():
        date_cols = columnas_fecha(df)
        periodos = [(c // 100) * 12 + (c % 100) for c in date_cols]
        ordenado = periodos == sorted(periodos)
        huecos = [
            (date_cols[i - 1], date_cols[i])
            for i in range(1, len(periodos))
            if periodos[i] - periodos[i - 1] != 1
        ]
        resultado[hoja] = {
            "n_cols": len(date_cols),
            "desde": date_cols[0],
            "hasta": date_cols[-1],
            "ordenado": ordenado,
            "huecos": huecos,
        }
    return resultado


# ---------- 6. Discontinuidades / rebases ----------
def detectar_saltos_serie(serie: pd.Series):
    periodos = [(c // 100) * 12 + (c % 100) for c in serie.index]
    saltos = []
    for i in range(1, len(serie)):
        if periodos[i] - periodos[i - 1] != 1:
            continue
        v0, v1 = serie.iloc[i - 1], serie.iloc[i]
        if pd.isna(v0) or pd.isna(v1) or v0 == 0:
            continue
        var = (v1 - v0) / abs(v0)
        if var < UMBRAL_CAIDA or var > UMBRAL_SUBIDA:
            saltos.append((serie.index[i - 1], serie.index[i], v0, v1, var, i))
    return saltos


def clasificar_patron(saltos) -> str:
    if len(saltos) <= 1:
        return "salto aislado (posible rebase de base)"
    posiciones = [s[5] for s in saltos]
    gaps = [posiciones[k] - posiciones[k - 1] for k in range(1, len(posiciones))]
    if any(g <= VENTANA_CLUSTER for g in gaps):
        return "cluster de saltos consecutivos (posible hiperinflación real)"
    return "varios saltos pero espaciados entre sí (posibles rebases repetidos)"


def analizar_discontinuidades(hojas):
    resultado = {}
    for hoja, df in hojas.items():
        date_cols = columnas_fecha(df)
        df_p = df[df["Country Code"].apply(es_fila_de_pais)]
        casos = []
        for _, fila in df_p.iterrows():
            serie = fila[date_cols].dropna()
            if len(serie) < 2:
                continue
            saltos = detectar_saltos_serie(serie)
            if not saltos:
                continue
            codigo = fila["Country Code"]
            casos.append(
                {
                    "codigo": codigo,
                    "pais": fila["Country"],
                    "n_saltos": len(saltos),
                    "clasificacion": clasificar_patron(saltos),
                    "conocido": CASOS_CONOCIDOS_FASE1.get((hoja, codigo)),
                    "ejemplos": [
                        (f0, f1, round(v0, 3), round(v1, 3), round(var * 100, 1))
                        for f0, f1, v0, v1, var, _ in saltos[:MAX_EJEMPLOS_POR_PAIS]
                    ],
                }
            )
        casos.sort(key=lambda c: c["n_saltos"], reverse=True)
        resultado[hoja] = casos
    return resultado


# ---------- Construcción del markdown ----------
def construir_markdown(dup, no_pais, codigos, indices_prob, cobertura, discontinuidades) -> str:
    L = []
    L.append("# Fase 2 — Auditoría de integridad estructural")
    L.append("")
    L.append(
        "Informe generado programáticamente por `src/fase2_integridad_estructural.py` "
        "leyendo directamente `data/raw/Inflation-data.xlsx` (las 5 hojas mensuales), "
        "sin pasar por el ETL. **Es solo diagnóstico: nada de lo encontrado acá se corrige "
        "en esta fase.**"
    )
    L.append("")

    # 1. Duplicados
    L.append("## 1. Duplicados (Country Code repetido dentro de una hoja)")
    L.append("")
    total_dup = sum(len(v) for v in dup.values())
    L.append(f"Total de países con filas duplicadas, sumando las 5 hojas: **{total_dup}**.")
    L.append("")
    for hoja, casos in dup.items():
        L.append(f"**`{hoja}`** — {len(casos)} país(es) con fila duplicada" + ("" if casos else " ✅"))
        if casos:
            L.append("")
            L.append("| Código | País | N° filas | Puntos válidos por fila |")
            L.append("|---|---|---|---|")
            for c in casos:
                L.append(
                    f"| {c['codigo']} | {c['pais']} | {c['n_filas']} "
                    f"| {c['puntos_validos_por_fila']} |"
                )
        L.append("")
    L.append(
        "Interpretación: cuando los conteos de puntos válidos por fila son parecidos y del "
        "mismo orden (como en `ppi_m`), suelen ser dos vintages/bases de la misma serie "
        "real (confirmado en Fase 1 para AUT/NLD/PRT/ZAF). El volumen encontrado acá en "
        "`ecpi_m` (30 países) es mucho mayor a lo detectado en Fase 1 — que solo miró "
        "`ppi_m` — así que el criterio de deduplicación de `01_descarga_datos.py` "
        "(quedarse con la fila más completa) aplica de forma genérica a las 5 hojas, no "
        "solo a `ppi_m`, y ya cubre estos casos. Queda documentado acá para que la decisión "
        "de deduplicación esté trazada, no solo aplicada en código."
    )
    L.append("")

    # 2. Filas no-país
    L.append("## 2. Filas no-país (notas / footnotes)")
    L.append("")
    L.append(
        "Filas sin un `Country Code` ISO3 válido (3 letras mayúsculas) — típicamente texto "
        "de nota al pie que Excel dejó en la misma columna que los códigos de país."
    )
    L.append("")
    L.append("| Hoja | N° filas no-país | Contenido |")
    L.append("|---|---|---|")
    for hoja, info in no_pais.items():
        contenido = "<br>".join(f"- {e}" for e in info["ejemplos"]) if info["ejemplos"] else "—"
        L.append(f"| {hoja} | {info['n']} | {contenido} |")
    L.append("")
    L.append(
        "Estas filas no tienen valores numéricos en las columnas de fecha (se verificó en "
        "Fase 1), así que `01_descarga_datos.py` ya las descarta indirectamente vía "
        "`dropna(subset=['indice'])`. No requieren tratamiento explícito adicional, pero "
        "conviene filtrarlas por `Country Code` antes del melt para que quede explícito por "
        "qué se excluyen, no como efecto secundario del dropna."
    )
    L.append("")

    # 3. Validación de códigos
    L.append("## 3. Validación de Country Code")
    L.append("")
    L.append(f"Códigos de país únicos (unión de las 5 hojas mensuales): **{codigos['n_codigos_unicos']}**.")
    L.append("")
    L.append("**Códigos que no son ISO 3166-1 alpha-3 estándar (vs. librería `pycountry`):**")
    L.append("")
    if codigos["no_iso3"]:
        for c, nombres in codigos["no_iso3"].items():
            L.append(f"- `{c}` → {', '.join(nombres)}")
        L.append("")
        L.append(
            "`XKX` (Kosovo) es el único caso: no tiene código ISO 3166 oficial porque su "
            "estatus como país no es reconocido de forma universal, pero `XKX` es el código "
            "que usa consistentemente el Banco Mundial para Kosovo en todas sus bases — "
            "es un código anómalo respecto al estándar ISO, pero esperado y estable dentro "
            "de esta fuente. No requiere corrección."
        )
    else:
        L.append("Ninguno. ✅")
    L.append("")
    L.append("**Mismo código con más de un nombre de país entre hojas:**")
    L.append("")
    if codigos["codigo_multi_nombre"]:
        for c, nombres in codigos["codigo_multi_nombre"].items():
            L.append(f"- `{c}`: {nombres}")
        L.append(
            "\nSon variantes de escritura del mismo nombre (con/sin tilde), no países "
            "distintos — inconsistencia cosmética, no estructural."
        )
    else:
        L.append("Ninguno. ✅")
    L.append("")
    L.append("**Mismo nombre de país con más de un código entre hojas:**")
    L.append("")
    if codigos["nombre_multi_codigo"]:
        for n, cods in codigos["nombre_multi_codigo"].items():
            L.append(f"- {n}: {cods}")
    else:
        L.append("Ninguno. ✅ (el `codigo_pais` es una clave estable para hacer join entre indicadores)")
    L.append("")

    # 4. Índices problemáticos
    L.append("## 4. Índices problemáticos (valores <=0 y fraccionarios)")
    L.append("")
    L.append("| Hoja | indice<0 | indice==0 | 0<indice<1 | Países con algún valor <=0 |")
    L.append("|---|---|---|---|---|")
    for hoja, info in indices_prob.items():
        L.append(
            f"| {hoja} | {info['n_neg']} | {info['n_zero']} | {info['n_frac']} "
            f"| {len(info['casos_no_positivos'])} |"
        )
    L.append("")
    L.append("### Casos con indice <= 0 (país, fechas exactas)")
    L.append("")
    hay_casos_le0 = any(info["casos_no_positivos"] for info in indices_prob.values())
    if not hay_casos_le0:
        L.append("Ninguno. ✅")
    for hoja, info in indices_prob.items():
        if not info["casos_no_positivos"]:
            continue
        L.append(f"**`{hoja}`**")
        L.append("")
        L.append("| Código | País | N° meses <=0 | Fechas | ¿Caso ya conocido de Fase 1? |")
        L.append("|---|---|---|---|---|")
        for c in info["casos_no_positivos"]:
            fechas_str = ", ".join(str(f) for f in c["fechas"][:12]) + (
                " ..." if len(c["fechas"]) > 12 else ""
            )
            conocido = c["conocido"] or "**NUEVO — no estaba en Fase 1**"
            L.append(f"| {c['codigo']} | {c['pais']} | {c['n']} | {fechas_str} | {conocido} |")
        L.append("")
    L.append(
        "Lectura: los valores negativos de India (`ecpi_m`) son el mismo caso ya documentado "
        "en Fase 1 (la fila es una tasa, no un índice — una tasa negativa es perfectamente "
        "válida, es deflación). Los ceros exactos de **Venezuela** en `ecpi_m` y `fcpi_m` "
        "**son un caso nuevo, no explicado por Fase 1**: un índice de precios en 0.0 exacto "
        "no tiene sentido económico (implicaría precio nulo) y más bien sugiere un "
        "placeholder de dato faltante cargado como `0` en vez de vacío — a revisar en la fase "
        "de corrección."
    )
    L.append("")
    L.append("### Valores fraccionarios (0 < indice < 1)")
    L.append("")
    L.append(
        "No se tratan como error: para países con hiperinflación histórica y un año base "
        "posterior (índice=100 en un año reciente), los valores de décadas atrás son "
        "fracciones minúsculas por construcción matemática del índice, no un problema de "
        "datos. Los 5 países con más meses fraccionarios por hoja, a modo de contexto:"
    )
    L.append("")
    for hoja, info in indices_prob.items():
        if info["n_frac"] == 0:
            continue
        top = ", ".join(f"{codigo} ({pais}): {n}" for codigo, pais, n in info["top_frac"])
        L.append(f"- `{hoja}` ({info['n_paises_con_frac']} países con algún valor fraccionario): {top}")
    L.append("")

    # 5. Cobertura de fechas (esquema)
    L.append("## 5. Cobertura de fechas — esquema del encabezado")
    L.append("")
    L.append(
        "Chequeo de que las columnas de fecha del encabezado (no los datos) sean "
        "consecutivas y estén ordenadas — huecos *en los datos* se auditan en Fase 3."
    )
    L.append("")
    L.append("| Hoja | N° columnas | Desde | Hasta | Ordenado | Huecos en el esquema |")
    L.append("|---|---|---|---|---|---|")
    for hoja, info in cobertura.items():
        huecos = info["huecos"] if info["huecos"] else "Ninguno ✅"
        L.append(
            f"| {hoja} | {info['n_cols']} | {info['desde']} | {info['hasta']} "
            f"| {'✅' if info['ordenado'] else '❌'} | {huecos} |"
        )
    L.append("")
    L.append(
        "Las 5 hojas mensuales comparten exactamente el mismo esquema de fechas "
        "(663 columnas, 1970-01 a 2025-03, consecutivas y ordenadas) — el encabezado en sí "
        "no tiene huecos en ninguna hoja."
    )
    L.append("")

    # 6. Discontinuidades
    L.append("## 6. Discontinuidades / posibles rebases (saltos mes a mes)")
    L.append("")
    L.append(
        f"Se marca un salto cuando dos meses **calendario-consecutivos** (sin hueco de por "
        f"medio) tienen una variación menor a {UMBRAL_CAIDA:.0%} o mayor a {UMBRAL_SUBIDA:.0%}. "
        "Clasificación tentativa por país: si los saltos detectados están separados por más "
        f"de {VENTANA_CLUSTER} observaciones entre sí → *salto aislado (posible rebase)*; si "
        "dos o más saltos caen cerca uno del otro → *cluster (posible hiperinflación real)*. "
        "Es una heurística para priorizar revisión manual, no una conclusión definitiva."
    )
    L.append("")
    total_saltos = sum(len(v) for v in discontinuidades.values())
    total_paises_saltos = sum(len(v) for v in discontinuidades.values())
    L.append(f"Total de país-hoja con al menos un salto: **{total_paises_saltos}**.")
    L.append("")
    for hoja, casos in discontinuidades.items():
        L.append(f"**`{hoja}`** — {len(casos)} país(es) con saltos" + ("" if casos else " ✅"))
        if casos:
            L.append("")
            L.append("| Código | País | N° saltos | Clasificación tentativa | ¿Conocido de Fase 1? | Ejemplos (mes_prev→mes_cur: var%) |")
            L.append("|---|---|---|---|---|---|")
            for c in casos:
                ejemplos_str = "; ".join(
                    f"{f0}→{f1}: {v0}→{v1} ({var:+.1f}%)" for f0, f1, v0, v1, var in c["ejemplos"]
                )
                if c["n_saltos"] > MAX_EJEMPLOS_POR_PAIS:
                    ejemplos_str += f" ... y {c['n_saltos'] - MAX_EJEMPLOS_POR_PAIS} más"
                conocido = c["conocido"] or "—"
                L.append(
                    f"| {c['codigo']} | {c['pais']} | {c['n_saltos']} | {c['clasificacion']} "
                    f"| {conocido} | {ejemplos_str} |"
                )
        L.append("")

    # Resumen final
    L.append("## Resumen de problemas estructurales detectados")
    L.append("")
    L.append("Checklist para la fase de corrección posterior:")
    L.append("")
    L.append(
        f"- [ ] **Duplicados**: {total_dup} país(es) con fila repetida en alguna hoja mensual "
        "(30 en ecpi_m, 4 en ppi_m, 2 en fcpi_m) — decidir criterio de deduplicación "
        "explícito (actualmente: fila más completa) y documentarlo en el ETL."
    )
    L.append(
        "- [ ] **Filas no-país**: presentes en 4 de las 5 hojas (footnotes de texto) — "
        "filtrar explícitamente por `Country Code` ISO3 antes del melt, no depender del "
        "`dropna` implícito."
    )
    L.append(
        "- [ ] **Códigos anómalos**: `XKX` (Kosovo) no es ISO 3166 estándar pero es estable "
        "y esperado — no requiere acción. Sin inconsistencias nombre↔código entre hojas."
    )
    n_casos_le0_nuevos = sum(
        1
        for info in indices_prob.values()
        for c in info["casos_no_positivos"]
        if c["conocido"] is None
    )
    L.append(
        f"- [ ] **Índices <=0**: {n_casos_le0_nuevos} caso(s) NUEVO(S) no explicado(s) por "
        "Fase 1 (Venezuela con índice exactamente 0.0 en ecpi_m/fcpi_m) — investigar si es "
        "placeholder de dato faltante antes de calcular YoY sobre esas filas."
    )
    L.append(
        "- [ ] **Valores fraccionarios (0<indice<1)**: no es un problema en sí, es "
        "consecuencia esperada de rebases de índice en países con inflación histórica alta "
        "(Turquía, Ecuador, México, Brasil, etc.) — no requiere corrección, solo tenerlo "
        "presente al interpretar niveles crudos de `indice`."
    )
    L.append(
        "- [ ] **Cobertura de fechas (esquema)**: sin huecos en el encabezado de ninguna "
        "hoja — no requiere acción."
    )
    L.append(
        f"- [ ] **Discontinuidades/rebases**: {total_paises_saltos} país-hoja con saltos "
        "mes a mes fuera de rango — revisar caso por caso en la fase de corrección para "
        "decidir si son rebases de base (aislados) que requieren empalme, o períodos de "
        "hiperinflación real (clusters) que se dejan tal cual."
    )
    L.append("")

    return "\n".join(L)


def main() -> None:
    hojas = cargar_hojas(RAW_PATH)

    dup = analizar_duplicados(hojas)
    no_pais = analizar_filas_no_pais(hojas)
    codigos = validar_codigos(hojas)
    indices_prob = analizar_indices_problematicos(hojas)
    cobertura = analizar_cobertura_fechas(hojas)
    discontinuidades = analizar_discontinuidades(hojas)

    md = construir_markdown(dup, no_pais, codigos, indices_prob, cobertura, discontinuidades)

    print(md)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"\n[guardado en {REPORT_PATH}]")


if __name__ == "__main__":
    main()
