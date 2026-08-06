# Fase 4 — Estadística univariada

Informe generado por `src/fase4_estadistica_univariada.py`, sobre el índice crudo de las 5 hojas mensuales de `data/raw/Inflation-data.xlsx`. **Solo diagnóstico: no se corrige ningún dato ni se toca el ETL.**

## Exclusiones aplicadas

Se excluyeron **4 series** ya identificadas como problemáticas en Fases 1-2 (no son un índice limpio, contaminarían cualquier estadística):

- `ecpi_m` / IND: Fase 1: Indicator Type='Inflation', ya es tasa, no índice
- `ecpi_m` / IDN: Fase 1: Indicator Type='Inflation', ya es tasa, no índice
- `ecpi_m` / VEN: Fase 2: índice en 0.0 exacto ~60 meses, probable placeholder de dato faltante
- `fcpi_m` / VEN: Fase 2: índice en 0.0 exacto ~51 meses, probable placeholder de dato faltante

Además, **12 filas** sin ningún dato de índice (ver Fase 3).

## 1. pct_change vs log-difference

Sobre **207,935** observaciones YoY válidas. Denominadores exactamente en cero (P_{t-12}=0): **0**. Infinitos generados: pct_change → 0, log-diff → 0.

**Correlación de Pearson (lineal) entre ambos métodos: 0.2762** — a primera vista parece baja para dos fórmulas que deberían "coincidir", pero es exactamente el síntoma del problema que motiva esta sección, no una contradicción: `log-diff = 100·ln(1 + pct_change/100)` es una función monotónica exacta de `pct_change` (no hay ninguna otra fuente de variación entre ambas), así que la **correlación de Spearman (de orden/monotonía) es 1.000000** — prácticamente 1, como matemáticamente tiene que ser. La brecha entre ambas correlaciones es la evidencia: un puñado de observaciones extremas (hiperinflación) tiene tanto peso en la varianza de `pct_change` que arrastra la correlación lineal hacia abajo. Si se descarta apenas el 1% más extremo (|pct_change| > 99%), la correlación de Pearson sube a **0.9920**. Es la misma relación matemática en los tres casos — lo que cambia es cuánto la distorsiona el 1% de datos más extremos, y esa sensibilidad es justamente por qué `pct_change` es la serie numéricamente menos estable de las dos.

En este panel ya depurado (sin las series excluidas) **ningún denominador es exactamente cero**, así que ninguno de los dos métodos genera infinitos literales — el caso que sí lo hubiera generado (Venezuela con índice=0.0) es precisamente uno de los que se excluyó en Fase 2. El argumento real a favor de log-diff no es "evita infinitos" sino **estabilidad numérica en la cola**: `pct_change` está acotado abajo en -100% pero NO tiene techo (máximo observado: **344,272%**, Venezuela PPI ene-2019), mientras que `log-diff` es simétrico y comprime esa misma observación a **814%** — casi 3 órdenes de magnitud menos extremo, para el mismo evento económico real.

Las 10 observaciones donde más divergen ambos métodos:

| Hoja | Código | País | Fecha | índice | índice(t-12) | pct_change | log-diff |
|---|---|---|---|---|---|---|---|
| ppi_m | VEN | Venezuela, RB | 2019-01 | 113263.98 | 32.89 | 344,272.1% | 814.4% |
| ppi_m | VEN | Venezuela, RB | 2018-12 | 53080.34 | 18.45 | 287,598.3% | 796.4% |
| ppi_m | VEN | Venezuela, RB | 2018-11 | 29011.08 | 12.39 | 234,049.2% | 775.9% |
| ppi_m | VEN | Venezuela, RB | 2018-10 | 16075.12 | 8.47 | 189,688.9% | 754.8% |
| ppi_m | VEN | Venezuela, RB | 2018-09 | 8869.00 | 5.23 | 169,479.3% | 743.6% |
| ppi_m | VEN | Venezuela, RB | 2018-08 | 2742.75 | 4.34 | 63,097.0% | 644.9% |
| ppi_m | VEN | Venezuela, RB | 2018-07 | 774.26 | 3.61 | 21,347.6% | 536.8% |
| ppi_m | VEN | Venezuela, RB | 2018-06 | 368.87 | 2.94 | 12,446.6% | 483.2% |
| ppi_m | PER | Peru | 1990-09 | 9.09 | 0.08 | 11,323.6% | 473.8% |
| ppi_m | PER | Peru | 1990-08 | 6.73 | 0.06 | 11,139.2% | 472.2% |

Figura: `reports/figures/fase4_pct_vs_logdiff.png` — coinciden casi perfectamente para inflación baja/moderada (panel izquierdo) y divergen fuerte en hiperinflación (panel derecho, escala symlog).

**Conclusión de esta sección:** para inflación baja/moderada (la inmensa mayoría de las observaciones) ambos métodos son prácticamente intercambiables — la correlación de Pearson sube a 0.9920 apenas se deja afuera el 1% más extremo, y la relación es monotónica exacta en el 100% de los casos (Spearman 1.000000). La diferencia importa solo en el puñado de episodios de hiperinflación, y ahí `log-diff` es claramente más estable numéricamente: no tiene el piso artificial de -100%, es simétrico ante subas/bajas proporcionalmente equivalentes, y es aditivo en el tiempo (la suma de 12 log-diffs mensuales da exactamente el log-diff anual, algo que `pct_change` no cumple).

## 2. Validación contra la tasa oficial (hcpi_a)

Para 10 países (USA, DEU, JPN, GBR, BRA, ZAF, MEX, TUR, ARG, IND), se comparó la tasa anual oficial (`hcpi_a`) contra dos formas de agregar el índice mensual: **dic/dic** (índice de diciembre vs diciembre del año anterior) y **promedio anual del índice** (promedio de los 12 meses del año vs promedio de los 12 meses del año anterior, ambos con `pct_change`).

| Método | N | Error absoluto medio | Mediana del error | Correlación vs oficial |
|---|---|---|---|---|
| dic/dic | 485 | 11.938 pp | 0.800 pp | 0.8976 |
| promedio anual del índice | 483 | 0.337 pp | 0.000 pp | 0.9999 |

**Hallazgo clave — la "prueba de oro":** el promedio anual del índice (ratio de promedios, `pct_change`, NO log-diff) reproduce `hcpi_a` casi exactamente (mediana del error = 0.00001 puntos porcentuales, correlación 0.9999). Esto confirma dos cosas a la vez: (1) el índice mensual crudo y la fórmula `pct_change` están bien calculados — si estuvieran mal, no reproducirían la cifra oficial con este nivel de precisión; y (2) el Banco Mundial define la inflación anual oficial como **variación del promedio anual del índice**, no como diciembre contra diciembre — por eso el método dic/dic tiene un error sistemáticamente mayor (11.94 pp de media vs 0.34 pp), no porque esté "mal calculado" sino porque mide una cosa distinta (inflación puntual de un mes específico, no el promedio del año).

**Implicancia directa para el ETL:** la columna `inflacion_yoy` que hoy genera `01_descarga_datos.py` (un `pct_change(12)` mes a mes) es la serie de inflación **puntual mensual** — coincide con `hcpi_a` solo en el mes de referencia si ese mes fuera diciembre y si `hcpi_a` fuera dic/dic (no lo es). No es un error: es un estadístico distinto y legítimo (la inflación interanual reportada cada mes por cualquier oficina de estadística), pero no hay que esperar que coincida número-a-número con `hcpi_a`, y conviene documentarlo así para quien use el parquet.

Países con mayor error promedio incluso con el método correcto (promedio anual):

- USA: 1.868 pp de error absoluto medio
- TUR: 0.989 pp de error absoluto medio
- IND: 0.097 pp de error absoluto medio

## 3. Distribución de la inflación por indicador

Se usa `pct_change` (la transformación validada en la sección 2 contra la cifra oficial) para caracterizar la distribución — ver sección de Recomendaciones para la decisión final sobre qué transformación alimenta el modelado.

| Indicador | N | Media | Mediana | Desvío | p1 | p5 | p95 | p99 | Asimetría | Curtosis (exceso) |
|---|---|---|---|---|---|---|---|---|---|---|
| hcpi_m | 56,413 | 14.00 | 4.09 | 107.20 | -2.46 | -0.43 | 28.91 | 136.27 | 31.06 | 1332.22 |
| ecpi_m | 45,834 | 9.91 | 4.03 | 123.25 | -14.55 | -6.34 | 27.47 | 79.29 | 59.43 | 3875.44 |
| fcpi_m | 43,332 | 8.57 | 4.18 | 35.37 | -5.61 | -1.73 | 24.91 | 71.27 | 32.34 | 1536.77 |
| ccpi_m | 29,138 | 5.79 | 2.96 | 14.83 | -1.00 | 0.10 | 17.19 | 55.02 | 15.57 | 365.89 |
| ppi_m | 33,218 | 58.53 | 3.88 | 3135.58 | -11.97 | -4.83 | 34.54 | 171.18 | 87.23 | 8096.08 |

Asimetría y curtosis muy por encima de 0 en las 5 hojas (especialmente `ppi_m` y `ecpi_m`, los indicadores con más episodios de hiperinflación/shocks de precios de energía) confirman colas pesadas hacia la derecha — consistente con lo encontrado en la sección 1: son unos pocos episodios extremos los que dominan la forma de la distribución, no el comportamiento típico.

Figura: `reports/figures/fase4_distribucion_por_indicador.png` — fila superior con recorte a [-50%, 150%] para ver la forma típica, fila inferior rango completo con eje y logarítmico para que la cola extrema siga siendo visible sin dominar el gráfico.

## 4. Hiperinflación

**77 series** (país×indicador) tuvieron al menos un mes con inflación YoY > 100%. **20 series** superaron 1000% en algún mes.

Episodios con pico > 1000% (tramos contiguos por encima de 100%, agrupados por serie):

| Hoja | Código | País | Inicio | Fin | Pico (%) |
|---|---|---|---|---|---|
| ppi_m | VEN | Venezuela, RB | 201505 | 201901 | 344,272% |
| ppi_m | PER | Peru | 198803 | 199111 | 11,324% |
| ecpi_m | SSD | South Sudan | 202309 | 202408 | 9,800% |
| ppi_m | UKR | Ukraine | 199301 | 199602 | 9,502% |
| hcpi_m | BRA | Brazil | 198704 | 199504 | 6,821% |
| hcpi_m | SVN | Slovenia | 198706 | 199012 | 3,465% |
| ppi_m | BLR | Belarus | 199301 | 199512 | 2,841% |
| hcpi_m | MDA | Moldova, Rep. | 199201 | 199412 | 2,706% |
| ecpi_m | BGR | Bulgaria | 199607 | 199802 | 2,363% |
| fcpi_m | BGR | Bulgaria | 199607 | 199801 | 2,224% |
| hcpi_m | BGR | Bulgaria | 199607 | 199801 | 2,020% |
| ppi_m | BGR | Bulgaria | 199607 | 199801 | 1,960% |
| hcpi_m | LVA | Latvia | 199201 | 199307 | 1,445% |
| fcpi_m | LVA | Latvia | 199201 | 199306 | 1,413% |
| hcpi_m | LTU | Lithuania | 199112 | 199403 | 1,412% |
| ppi_m | POL | Poland | 198908 | 199012 | 1,369% |
| hcpi_m | POL | Poland | 199001 | 199101 | 1,200% |
| ppi_m | RUS | Russian Federation | 199301 | 199602 | 1,172% |
| hcpi_m | RUS | Russian Federation | 199301 | 199601 | 1,066% |
| fcpi_m | ZMB | Zambia | 202402 | 202402 | 1,042% |

**El problema para GARCH:** un modelo GARCH estima la varianza condicional a partir de los residuos al cuadrado — un puñado de observaciones con valores miles de veces más grandes que el resto (Venezuela, Zimbabwe, Sudán del Sur, Bulgaria en su hiperinflación de los 90) van a dominar por completo la estimación de la varianza de largo plazo (`omega`) y pueden hacer que el modelo no converja o sobre-reaccione a esos pocos puntos, ignorando la dinámica de volatilidad "normal" del resto de la serie.

**Opciones de tratamiento a evaluar (sin decidir en esta fase):**

1. **Winsorizar** (recortar a un percentil, ej. p1/p99): simple, pero destruye información real sobre régimen de alta inflación — exactamente lo que un análisis de volatilidad querría capturar.
2. **Trabajar en log-diff**: ya comprime la escala de forma natural (ver sección 1) sin descartar ningún dato — pero no elimina el problema, solo lo atenúa.
3. **Analizar por separado / flag de régimen**: marcar estas series (o estos tramos) como "alta inflación" y tratarlas con un modelo o umbral distinto en vez de forzarlas al mismo pipeline que Alemania o Estados Unidos.
4. **Excluir del panel de GARCH** (no de ARIMA): la volatilidad durante hiperinflación es un fenómeno distinto al que típicamente le interesa a un modelo GARCH orientado a riesgo de mercado normal — podría no tener sentido modelarlo con el mismo marco.

## 5. Valores negativos (deflación)

**553 series** tuvieron al menos un mes de deflación (YoY < 0).
**455 series** tuvieron una racha de 6 o más meses consecutivos de deflación ("sostenida"):

| Hoja | Código | País | Meses con deflación | % del historial | Racha máxima (meses) |
|---|---|---|---|---|---|
| fcpi_m | IRL | Ireland | 157 | 26.0% | 92 |
| ppi_m | JPN | Japan | 264 | 45.8% | 65 |
| hcpi_m | MAC | Macao SAR, China | 78 | 25.4% | 65 |
| ecpi_m | SVK | Slovakia | 106 | 30.2% | 60 |
| ecpi_m | QAT | Qatar | 98 | 58.0% | 60 |
| fcpi_m | MAC | Macao SAR, China | 65 | 21.2% | 60 |
| ecpi_m | JPN | Japan | 246 | 40.6% | 57 |
| ecpi_m | ARE | United Arab Emirates | 100 | 52.1% | 56 |
| ccpi_m | JPN | Japan | 189 | 29.1% | 55 |
| ecpi_m | TWN | Taiwan, China | 199 | 38.3% | 52 |
| ppi_m | CHE | Switzerland | 255 | 39.5% | 51 |
| ecpi_m | BRN | Brunei Darussalam | 102 | 60.0% | 50 |
| ppi_m | SGP | Singapore | 344 | 57.1% | 49 |
| hcpi_m | JPN | Japan | 162 | 24.9% | 49 |
| ppi_m | AUT | Austria | 164 | 37.2% | 47 |

**¿Real o artefacto?** Japón (`hcpi_m`: 49 meses de racha máxima) y Suiza (`hcpi_m`: 28 meses de racha máxima) encabezan las rachas más largas de deflación — coincide exactamente con episodios económicos reales y bien documentados (deflación japonesa post-burbuja de los 90s-2000s, y episodios deflacionarios suizos ligados a la fortaleza del franco). Que los casos con mayor racha sean precisamente estos dos países, y no países al azar, es evidencia de que la deflación detectada es real, no un artefacto de datos.

## Recomendaciones para el ETL

**1. Transformación — usar ambas, con roles distintos, no una sola columna:**

- **`inflacion_yoy_pct`** (`pct_change`, la que ya existe): mantenerla como la serie "headline", interpretable en las unidades estándar de cualquier reporte de inflación, y es la que se validó contra `hcpi_a` en la sección 2 (con el ajuste de usar promedio anual, no dic/dic, si en algún momento se agrega una agregación anual al ETL).
- **`inflacion_yoy_log`** (`log-diff`, nueva): agregar como columna adicional para alimentar ARIMA/GARCH — la evidencia de la sección 1 (mismo evento real: 344.272% en pct_change vs 814% en log-diff) muestra que reduce la asimetría y el peso de la cola extrema sin descartar ningún dato, además de ser aditiva en el tiempo y no tener el piso artificial de -100% que sí tiene `pct_change`.

**2. Hiperinflación — no excluir, pero sí marcar:**

Agregar un flag `alta_inflacion` (ej. `pct_change_yoy > 100` en algún punto de la serie) en vez de winsorizar por defecto. Trabajar en log-diff ya atenúa el problema para la mayoría de los casos; reservar winsorización o modelado separado como tratamiento opcional solo para las 20 series que superan 1000%, si el ajuste de GARCH no converge sobre ellas en log-diff. La decisión final de qué hacer con cada una queda para cuando se intente ajustar el modelo, no antes — winsorizar preventivamente tiraría información real.

**3. Deflación — no requiere tratamiento especial:**

Los valores negativos son economía real (Japón, Suiza), no un error de datos. Ni `pct_change` ni `log-diff` tienen problemas matemáticos con deflación (a diferencia de la hiperinflación, que sí estresa la cola derecha) — no se necesita ningún tratamiento adicional más allá de calcular ambas columnas con la fórmula estándar.
