# Análisis C — Dinámica de volatilidad (GARCH)

Informe generado por `src/10_analisis_volatilidad.py` sobre `data/processed/resultados_enriquecidos.parquet`. Las secciones 1 y 5 usan el panel completo (los 5 indicadores, son descriptivas/de caracterización); las secciones 2 (test de asociación), 3 (correlación) y 4 (Kruskal-Wallis) se restringen a `hcpi` para que cada país aporte una sola observación a cada test, evitando pseudo-replicación (mismo criterio que Análisis A/B).

## 1. Distribución de la persistencia (alpha+beta)

Sobre las **626 series** con GARCH convergido (panel completo):

| Percentil | Persistencia |
|---|---|
| p10 | 0.716 |
| p25 | 0.892 |
| p50 | 0.968 |
| p75 | 0.992 |
| p90 | 1.000 |
| p95 | 1.000 |
| p99 | 1.000 |

- **58.5%** de las series tiene persistencia ≥ 0.95 (shocks muy duraderos).
- **12.5%** tiene persistencia ≥ 1 (IGARCH-like, borde de no-estacionariedad en varianza).

Figura: `reports/figures/analisisC_histograma_persistencia.png`.

## 2. El patrón IGARCH (persistencia ≥ 1)

**78 series** (panel completo) tienen persistencia ≥ 1.

Por región (panel completo, descriptivo):

- Europe & Central Asia: 29
- Sub-Saharan Africa: 16
- Middle East, North Africa, Afghanistan & Pakistan: 12
- East Asia & Pacific: 9
- Latin America & Caribbean: 6
- South Asia: 3
- North America: 2

Por nivel de ingreso (panel completo, descriptivo):

- Low income: 7
- Lower middle income: 21
- Upper middle income: 18
- High income: 31

**Test de asociación formal (hcpi, un país = una observación):**

Tabla de contingencia (nivel de ingreso × IGARCH-like):

igarch               False  True 
nivel_ingreso                    
Low income              18      1
Lower middle income     37      6
Upper middle income     47      4
High income             53      5

Chi-cuadrado: χ²=1.62, p=6.55e-01.
**Advertencia de validez**: 38% de las celdas tienen frecuencia esperada < 5 (regla de Cochran sugiere no superar el 20%) — hay muy pocos casos IGARCH en hcpi (16 en total) para que la aproximación chi-cuadrado sea del todo confiable. El resultado se reporta igual, pero con esta salvedad.

**Conclusión:** no se detecta asociación estadísticamente significativa entre nivel de ingreso y patrón IGARCH — con esta muestra, el patrón IGARCH parece repartido de forma más o menos pareja entre niveles de ingreso, no concentrado en un extremo.

## 3. Persistencia vs. previsibilidad de nivel

Figura: `reports/figures/analisisC_scatter_persistencia_rmse.png`.

Correlación de Spearman (hcpi, n=172): ρ=-0.007, p=9.30e-01.

**Conclusión:** no hay relación estadísticamente significativa entre persistencia de volatilidad y RMSE de nivel — son dos dimensiones de imprevisibilidad aparentemente **independientes** en este panel: que la volatilidad de un país sea persistente no implica que su nivel de inflación sea más difícil de pronosticar (ni viceversa).

## 4. Persistencia por nivel de ingreso y región

Persistencia mediana por nivel de ingreso (hcpi):

- Low income: 0.958
- Lower middle income: 0.938
- Upper middle income: 0.970
- High income: 0.970

Kruskal-Wallis: H=5.27, p=1.53e-01.
**Conclusión:** el gradiente de ingreso que se ve claramente en previsibilidad de nivel (Análisis A) **no se repite de forma significativa en persistencia de volatilidad** — son fenómenos relacionados pero no gobernados por el mismo gradiente.

Persistencia mediana por región (hcpi), de mayor a menor:

- North America: 0.983
- Latin America & Caribbean: 0.977
- Europe & Central Asia: 0.970
- Middle East, North Africa, Afghanistan & Pakistan: 0.961
- Sub-Saharan Africa: 0.956
- South Asia: 0.949
- East Asia & Pacific: 0.932

Kruskal-Wallis: H=5.30, p=3.80e-01.
**Conclusión:** no se puede descartar que las diferencias regionales en persistencia sean azar.

Figura: `reports/figures/analisisC_boxplot_persistencia_grupos.png`.

## 5. Casos que no convergieron en GARCH

De las 14 series sin `convergio_garch`, **0 son fallas reales de convergencia** (el optimizador corrió y no encontró una solución válida) y **14 son series que directamente no se intentaron** (`motivo_fallo_garch='serie_no_apto_garch'`, no cumplen el piso de 100 meses sin huecos internos de Fase 3 — nunca llegan a pedirle nada al optimizador).

**Hallazgo, corrigiendo la hipótesis de partida: no hubo ninguna falla real de convergencia de GARCH en todo el panel.** La expectativa de que Argentina o Venezuela fallarían "por volatilidad extrema" no se cumplió — `rescale=True` (Fase de modelado) hizo su trabajo. Lo que sí les pasó a Argentina y Venezuela es más aburrido pero más honesto: varias de sus series **ni siquiera llegaron a intentarse**, porque no cumplen el piso de 100 meses sin huecos que exige `apto_garch` — no por ser demasiado volátiles, sino por tener historia insuficiente (Argentina hcpi: 86 meses; Venezuela ecpi/fcpi/hcpi: 70-79 meses, recortadas además por la exclusión de sus ceros-placeholder en Fase 2).

Como evidencia de que sí converge en casos de volatilidad extrema: las series de Argentina, Venezuela, Zimbabwe y Turquía que **sí** cumplieron el piso de 100 meses convergieron todas, varias en el borde IGARCH (persistencia≈1):

| País | Indicador | Persistencia | Meses usados |
|---|---|---|---|
| ARG | ecpi | 0.990 | 88 |
| ARG | fcpi | 0.759 | 88 |
| ARG | ppi | 1.000 | 100 |
| TUR | ccpi | 1.000 | 363 |
| TUR | ecpi | 0.985 | 363 |
| TUR | fcpi | 0.972 | 651 |
| TUR | hcpi | 1.000 | 651 |
| TUR | ppi | 0.987 | 399 |
| VEN | ppi | 0.883 | 133 |
| ZWE | ecpi | 1.000 | 164 |
| ZWE | hcpi | 1.000 | 164 |

## Hallazgos principales

- **12.5%** del panel completo muestra comportamiento IGARCH-like (persistencia≥1); la asociación con nivel de ingreso NO alcanza significancia estadística con esta muestra (χ²=1.62, p=6.55e-01).
- Persistencia de volatilidad y previsibilidad de nivel (RMSE) son dimensiones estadísticamente INDEPENDIENTES en este panel (Spearman ρ=-0.01, p=9.30e-01).
- El gradiente de ingreso de Análisis A NO se repite en la persistencia de volatilidad (Kruskal-Wallis p=1.53e-01).
- No hubo ninguna falla real de convergencia de GARCH en todo el panel — los "casos problemáticos" esperados (Argentina, Venezuela) resultaron ser un problema de cobertura de datos (menos de 100 meses sin huecos), no de estabilidad numérica del modelo.
