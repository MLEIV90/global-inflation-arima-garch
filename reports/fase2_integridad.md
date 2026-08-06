# Fase 2 — Auditoría de integridad estructural

Informe generado programáticamente por `src/fase2_integridad_estructural.py` leyendo directamente `data/raw/Inflation-data.xlsx` (las 5 hojas mensuales), sin pasar por el ETL. **Es solo diagnóstico: nada de lo encontrado acá se corrige en esta fase.**

## 1. Duplicados (Country Code repetido dentro de una hoja)

Total de países con filas duplicadas, sumando las 5 hojas: **36**.

**`hcpi_m`** — 0 país(es) con fila duplicada ✅

**`ecpi_m`** — 30 país(es) con fila duplicada

| Código | País | N° filas | Puntos válidos por fila |
|---|---|---|---|
| BHR | Bahrain | 2 | [99, 182] |
| BOL | Bolivia | 2 | [243, 118] |
| BRA | Brazil | 2 | [309, 309] |
| BWA | Botswana | 2 | [114, 183] |
| CMR | Cameroon | 2 | [153, 151] |
| DOM | Dominican Republic | 2 | [171, 314] |
| ECU | Ecuador | 2 | [242, 243] |
| EGY | Egypt, Arab Rep. | 2 | [67, 177] |
| GAB | Gabon | 2 | [180, 61] |
| IRQ | Iraq | 2 | [117, 119] |
| JOR | Jordan | 2 | [227, 327] |
| KWT | Kuwait | 2 | [182, 156] |
| LBN | Lebanon | 2 | [121, 207] |
| LSO | Lesotho | 2 | [242, 99] |
| MOZ | Mozambique | 2 | [211, 111] |
| MUS | Mauritius | 2 | [0, 154] |
| MYS | Malaysia | 2 | [302, 242] |
| NAM | Namibia | 2 | [243, 279] |
| OMN | Oman | 2 | [287, 119] |
| PHL | Philippines | 2 | [375, 86] |
| PRY | Paraguay | 2 | [242, 364] |
| QAT | Qatar | 2 | [181, 57] |
| SEN | Senegal | 2 | [339, 72] |
| SGP | Singapore | 2 | [240, 242] |
| TCD | Chad | 2 | [180, 71] |
| TGO | Togo | 2 | [339, 75] |
| THA | Thailand | 2 | [165, 484] |
| TUN | Tunisia | 2 | [242, 243] |
| UGA | Uganda | 2 | [333, 123] |
| URY | Uruguay | 2 | [214, 143] |

**`fcpi_m`** — 2 país(es) con fila duplicada

| Código | País | N° filas | Puntos válidos por fila |
|---|---|---|---|
| SGP | Singapore | 2 | [662, 240] |
| THA | Thailand | 2 | [591, 165] |

**`ccpi_m`** — 0 país(es) con fila duplicada ✅

**`ppi_m`** — 4 país(es) con fila duplicada

| Código | País | N° filas | Puntos válidos por fila |
|---|---|---|---|
| AUT | Austria | 2 | [453, 302] |
| NLD | Netherlands | 2 | [657, 530] |
| PRT | Portugal | 2 | [297, 243] |
| ZAF | South Africa | 2 | [491, 662] |

Interpretación: cuando los conteos de puntos válidos por fila son parecidos y del mismo orden (como en `ppi_m`), suelen ser dos vintages/bases de la misma serie real (confirmado en Fase 1 para AUT/NLD/PRT/ZAF). El volumen encontrado acá en `ecpi_m` (30 países) es mucho mayor a lo detectado en Fase 1 — que solo miró `ppi_m` — así que el criterio de deduplicación de `01_descarga_datos.py` (quedarse con la fila más completa) aplica de forma genérica a las 5 hojas, no solo a `ppi_m`, y ya cubre estos casos. Queda documentado acá para que la decisión de deduplicación esté trazada, no solo aplicada en código.

## 2. Filas no-país (notas / footnotes)

Filas sin un `Country Code` ISO3 válido (3 letras mayúsculas) — típicamente texto de nota al pie que Excel dejó en la misma columna que los códigos de país.

| Hoja | N° filas no-país | Contenido |
|---|---|---|
| hcpi_m | 1 | - Note: "IFS" indicates IMF's International Financial Statistics database. "National sources" incldues the data from central banks, statitisca |
| ecpi_m | 2 | - (celda vacía / NaN)<br>- Note:  "CPI" indicates IMF Consumer Price Index database.  "National sources" incldues the data from central banks, statitiscal offices, or  |
| fcpi_m | 2 | - (celda vacía / NaN)<br>- Note: "CPI" indicates IMF Consumer Price Index database.  "National sources" incldues the data from central banks, statitiscal offices, or o |
| ccpi_m | 2 | - (celda vacía / NaN)<br>- Note: "National sources" incldues the data from central banks, statitiscal offices, or other country-specific institutions. |
| ppi_m | 1 | - Note: "IFS" indicates IMF's International Financial Statistics database. "National sources" incldues the data from central banks, statitisca |

Estas filas no tienen valores numéricos en las columnas de fecha (se verificó en Fase 1), así que `01_descarga_datos.py` ya las descarta indirectamente vía `dropna(subset=['indice'])`. No requieren tratamiento explícito adicional, pero conviene filtrarlas por `Country Code` antes del melt para que quede explícito por qué se excluyen, no como efecto secundario del dropna.

## 3. Validación de Country Code

Códigos de país únicos (unión de las 5 hojas mensuales): **189**.

**Códigos que no son ISO 3166-1 alpha-3 estándar (vs. librería `pycountry`):**

- `XKX` → Kosovo

`XKX` (Kosovo) es el único caso: no tiene código ISO 3166 oficial porque su estatus como país no es reconocido de forma universal, pero `XKX` es el código que usa consistentemente el Banco Mundial para Kosovo en todas sus bases — es un código anómalo respecto al estándar ISO, pero esperado y estable dentro de esta fuente. No requiere corrección.

**Mismo código con más de un nombre de país entre hojas:**

- `CIV`: ["Cote d'Ivoire", "CÃ´te d'Ivoire"]
- `STP`: ['Sao Tome and Principe', 'SÃ£o TomÃ© and Principe']

Son variantes de escritura del mismo nombre (con/sin tilde), no países distintos — inconsistencia cosmética, no estructural.

**Mismo nombre de país con más de un código entre hojas:**

Ninguno. ✅ (el `codigo_pais` es una clave estable para hacer join entre indicadores)

## 4. Índices problemáticos (valores <=0 y fraccionarios)

| Hoja | indice<0 | indice==0 | 0<indice<1 | Países con algún valor <=0 |
|---|---|---|---|---|
| hcpi_m | 0 | 0 | 1713 | 0 |
| ecpi_m | 15 | 63 | 287 | 2 |
| fcpi_m | 0 | 51 | 564 | 1 |
| ccpi_m | 0 | 0 | 239 | 0 |
| ppi_m | 0 | 0 | 715 | 0 |

### Casos con indice <= 0 (país, fechas exactas)

**`ecpi_m`**

| Código | País | N° meses <=0 | Fechas | ¿Caso ya conocido de Fase 1? |
|---|---|---|---|---|
| IND | India | 18 | 197508, 197509, 197510, 197511, 197512, 197601, 197602, 197603, 197604, 197605, 197606, 197607 ... | Fase 1: etiquetado 'Inflation', es tasa real |
| VEN | Venezuela, RB | 60 | 201301, 201302, 201303, 201304, 201305, 201306, 201307, 201308, 201309, 201310, 201311, 201312 ... | **NUEVO — no estaba en Fase 1** |

**`fcpi_m`**

| Código | País | N° meses <=0 | Fechas | ¿Caso ya conocido de Fase 1? |
|---|---|---|---|---|
| VEN | Venezuela, RB | 51 | 201301, 201302, 201303, 201304, 201305, 201306, 201307, 201308, 201309, 201310, 201311, 201312 ... | **NUEVO — no estaba en Fase 1** |

Lectura: los valores negativos de India (`ecpi_m`) son el mismo caso ya documentado en Fase 1 (la fila es una tasa, no un índice — una tasa negativa es perfectamente válida, es deflación). Los ceros exactos de **Venezuela** en `ecpi_m` y `fcpi_m` **son un caso nuevo, no explicado por Fase 1**: un índice de precios en 0.0 exacto no tiene sentido económico (implicaría precio nulo) y más bien sugiere un placeholder de dato faltante cargado como `0` en vez de vacío — a revisar en la fase de corrección.

### Valores fraccionarios (0 < indice < 1)

No se tratan como error: para países con hiperinflación histórica y un año base posterior (índice=100 en un año reciente), los valores de décadas atrás son fracciones minúsculas por construcción matemática del índice, no un problema de datos. Los 5 países con más meses fraccionarios por hoja, a modo de contexto:

- `hcpi_m` (16 países con algún valor fraccionario): TUR (Turkey): 309, ECU (Ecuador): 242, MEX (Mexico): 196, ISR (Israel): 168, BRA (Brazil): 166
- `ecpi_m` (5 países con algún valor fraccionario): ISR (Israel): 168, MEX (Mexico): 80, TUR (Turkey): 25, VEN (Venezuela, RB): 11, IND (India): 3
- `fcpi_m` (6 países con algún valor fraccionario): TUR (Turkey): 308, ISR (Israel): 168, ISL (Iceland): 33, ROU (Romania): 31, ZAF (South Africa): 13
- `ccpi_m` (3 países con algún valor fraccionario): ISR (Israel): 168, MEX (Mexico): 51, TUR (Turkey): 20
- `ppi_m` (12 países con algún valor fraccionario): VEN (Venezuela, RB): 120, TUR (Turkey): 106, COL (Colombia): 105, ISR (Israel): 82, MEX (Mexico): 56

## 5. Cobertura de fechas — esquema del encabezado

Chequeo de que las columnas de fecha del encabezado (no los datos) sean consecutivas y estén ordenadas — huecos *en los datos* se auditan en Fase 3.

| Hoja | N° columnas | Desde | Hasta | Ordenado | Huecos en el esquema |
|---|---|---|---|---|---|
| hcpi_m | 663 | 197001 | 202503 | ✅ | Ninguno ✅ |
| ecpi_m | 663 | 197001 | 202503 | ✅ | Ninguno ✅ |
| fcpi_m | 663 | 197001 | 202503 | ✅ | Ninguno ✅ |
| ccpi_m | 663 | 197001 | 202503 | ✅ | Ninguno ✅ |
| ppi_m | 663 | 197001 | 202503 | ✅ | Ninguno ✅ |

Las 5 hojas mensuales comparten exactamente el mismo esquema de fechas (663 columnas, 1970-01 a 2025-03, consecutivas y ordenadas) — el encabezado en sí no tiene huecos en ninguna hoja.

## 6. Discontinuidades / posibles rebases (saltos mes a mes)

Se marca un salto cuando dos meses **calendario-consecutivos** (sin hueco de por medio) tienen una variación menor a -40% o mayor a 100%. Clasificación tentativa por país: si los saltos detectados están separados por más de 3 observaciones entre sí → *salto aislado (posible rebase)*; si dos o más saltos caen cerca uno del otro → *cluster (posible hiperinflación real)*. Es una heurística para priorizar revisión manual, no una conclusión definitiva.

Total de país-hoja con al menos un salto: **24**.

**`hcpi_m`** — 3 país(es) con saltos

| Código | País | N° saltos | Clasificación tentativa | ¿Conocido de Fase 1? | Ejemplos (mes_prev→mes_cur: var%) |
|---|---|---|---|---|---|
| BGR | Bulgaria | 1 | salto aislado (posible rebase de base) | — | 199701→199702: 691.129→2366.1 (+242.4%) |
| GIN | Guinea | 1 | salto aislado (posible rebase de base) | — | 200612→200701: 25.151→13.632 (-45.8%) |
| MDA | Moldova, Rep. | 1 | salto aislado (posible rebase de base) | — | 199112→199201: 0.005→0.016 (+240.1%) |

**`ecpi_m`** — 8 país(es) con saltos

| Código | País | N° saltos | Clasificación tentativa | ¿Conocido de Fase 1? | Ejemplos (mes_prev→mes_cur: var%) |
|---|---|---|---|---|---|
| IND | India | 12 | cluster de saltos consecutivos (posible hiperinflación real) | Fase 1: etiquetado 'Inflation', es tasa real | 197104→197105: 1.7→0.6 (-64.7%); 197506→197507: 9.0→4.2 (-53.3%); 197507→197508: 4.2→0.0 (-100.0%); 197701→197702: 3.0→6.9 (+130.0%); 197801→197802: 5.9→3.2 (-45.8%) ... y 7 más |
| SSD | South Sudan | 9 | cluster de saltos consecutivos (posible hiperinflación real) | — | 201802→201803: 3470.157→17123.925 (+393.5%); 201803→201804: 17123.925→4818.617 (-71.9%); 201910→201911: 20300.651→5817.828 (-71.3%); 201911→201912: 5817.828→13447.012 (+131.1%); 202005→202006: 24394.852→8519.065 (-65.1%) ... y 4 más |
| VEN | Venezuela, RB | 7 | cluster de saltos consecutivos (posible hiperinflación real) | — | 201805→201806: 0.01→0.06 (+500.0%); 201806→201807: 0.06→0.14 (+133.3%); 201810→201811: 0.18→0.43 (+138.9%); 201811→201812: 0.43→11.51 (+2576.7%); 201812→201901: 11.51→66.35 (+476.5%) ... y 2 más |
| ISR | Israel | 2 | cluster de saltos consecutivos (posible hiperinflación real) | — | 197511→197512: 0.004→0.001 (-69.9%); 197512→197601: 0.001→0.004 (+234.6%) |
| SDN | Sudan | 2 | varios saltos pero espaciados entre sí (posibles rebases repetidos) | — | 202108→202109: 5459.123→17571.833 (+221.9%); 202208→202209: 21821.337→58255.971 (+167.0%) |
| ECU | Ecuador | 1 | salto aislado (posible rebase de base) | — | 202411→202412: 111.673→57.278 (-48.7%) |
| SUR | Suriname | 1 | salto aislado (posible rebase de base) | — | 201510→201511: 59.837→122.671 (+105.0%) |
| UKR | Ukraine | 1 | salto aislado (posible rebase de base) | — | 201503→201504: 155.5→326.1 (+109.7%) |

**`fcpi_m`** — 5 país(es) con saltos

| Código | País | N° saltos | Clasificación tentativa | ¿Conocido de Fase 1? | Ejemplos (mes_prev→mes_cur: var%) |
|---|---|---|---|---|---|
| VEN | Venezuela, RB | 5 | cluster de saltos consecutivos (posible hiperinflación real) | — | 201804→201805: 1.8→4.1 (+127.8%); 201808→201809: 24.2→50.1 (+107.0%); 201810→201811: 94.4→223.1 (+136.3%); 201812→201901: 442.2→1344.2 (+204.0%); 201901→201902: 1344.2→2910.1 (+116.5%) |
| ZMB | Zambia | 2 | cluster de saltos consecutivos (posible hiperinflación real) | — | 202401→202402: 464.47→4755.04 (+923.8%); 202402→202403: 4755.04→486.52 (-89.8%) |
| LVA | Latvia | 1 | salto aislado (posible rebase de base) | — | 199111→199112: 1.554→3.731 (+140.1%) |
| BGR | Bulgaria | 1 | salto aislado (posible rebase de base) | — | 199701→199702: 727.995→2729.755 (+275.0%) |
| GIN | Guinea | 1 | salto aislado (posible rebase de base) | — | 201001→201002: 49.623→28.477 (-42.6%) |

**`ccpi_m`** — 1 país(es) con saltos

| Código | País | N° saltos | Clasificación tentativa | ¿Conocido de Fase 1? | Ejemplos (mes_prev→mes_cur: var%) |
|---|---|---|---|---|---|
| BGR | Bulgaria | 1 | salto aislado (posible rebase de base) | — | 199701→199702: 11.42→39.96 (+249.9%) |

**`ppi_m`** — 7 país(es) con saltos

| Código | País | N° saltos | Clasificación tentativa | ¿Conocido de Fase 1? | Ejemplos (mes_prev→mes_cur: var%) |
|---|---|---|---|---|---|
| VEN | Venezuela, RB | 5 | cluster de saltos consecutivos (posible hiperinflación real) | — | 201805→201806: 182.18→368.87 (+102.5%); 201806→201807: 368.87→774.26 (+109.9%); 201807→201808: 774.26→2742.75 (+254.2%); 201808→201809: 2742.75→8869.0 (+223.4%); 201812→201901: 53080.34→113263.98 (+113.4%) |
| PER | Peru | 2 | varios saltos pero espaciados entre sí (posibles rebases repetidos) | — | 198808→198809: 0.001→0.004 (+176.9%); 199007→199008: 1.552→6.732 (+333.8%) |
| UKR | Ukraine | 2 | varios saltos pero espaciados entre sí (posibles rebases repetidos) | — | 199212→199301: 0.005→0.011 (+118.2%); 199410→199411: 1.562→3.27 (+109.3%) |
| BGR | Bulgaria | 1 | salto aislado (posible rebase de base) | — | 199701→199702: 12.714→34.397 (+170.5%) |
| KWT | Kuwait | 1 | salto aislado (posible rebase de base) | — | 202003→202004: 52.7→31.1 (-41.0%) |
| POL | Poland | 1 | salto aislado (posible rebase de base) | — | 198912→199001: 5.035→10.299 (+104.6%) |
| ROU | Romania | 1 | salto aislado (posible rebase de base) | — | 199010→199011: 0.024→0.055 (+126.4%) |

## Resumen de problemas estructurales detectados

Checklist para la fase de corrección posterior:

- [ ] **Duplicados**: 36 país(es) con fila repetida en alguna hoja mensual (30 en ecpi_m, 4 en ppi_m, 2 en fcpi_m) — decidir criterio de deduplicación explícito (actualmente: fila más completa) y documentarlo en el ETL.
- [ ] **Filas no-país**: presentes en 4 de las 5 hojas (footnotes de texto) — filtrar explícitamente por `Country Code` ISO3 antes del melt, no depender del `dropna` implícito.
- [ ] **Códigos anómalos**: `XKX` (Kosovo) no es ISO 3166 estándar pero es estable y esperado — no requiere acción. Sin inconsistencias nombre↔código entre hojas.
- [ ] **Índices <=0**: 2 caso(s) NUEVO(S) no explicado(s) por Fase 1 (Venezuela con índice exactamente 0.0 en ecpi_m/fcpi_m) — investigar si es placeholder de dato faltante antes de calcular YoY sobre esas filas.
- [ ] **Valores fraccionarios (0<indice<1)**: no es un problema en sí, es consecuencia esperada de rebases de índice en países con inflación histórica alta (Turquía, Ecuador, México, Brasil, etc.) — no requiere corrección, solo tenerlo presente al interpretar niveles crudos de `indice`.
- [ ] **Cobertura de fechas (esquema)**: sin huecos en el encabezado de ninguna hoja — no requiere acción.
- [ ] **Discontinuidades/rebases**: 24 país-hoja con saltos mes a mes fuera de rango — revisar caso por caso en la fase de corrección para decidir si son rebases de base (aislados) que requieren empalme, o períodos de hiperinflación real (clusters) que se dejan tal cual.
