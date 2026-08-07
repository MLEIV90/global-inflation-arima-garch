# Análisis B — Estructura de la inflación (headline vs. componentes)

Informe generado por `src/09_analisis_estructura.py` sobre `data/processed/resultados_enriquecidos.parquet`. Las comparaciones entre indicadores del mismo país usan tests **pareados** (Wilcoxon signed-rank, Friedman) porque hcpi/ccpi/ecpi/fcpi/ppi del mismo país no son observaciones independientes entre sí.

## 1. Comparación de previsibilidad entre los 5 indicadores

RMSE walk-forward por indicador (todas las series aptas, no pareado):

| Indicador | N series | RMSE mediano | RMSE medio |
|---|---|---|---|
| Headline CPI (hcpi) | 175 | 0.697 | 1.201 |
| Energy CPI (ecpi) | 157 | 2.078 | 3.690 |
| Food CPI (fcpi) | 135 | 1.148 | 2.351 |
| Core CPI (ccpi) | 79 | 0.376 | 0.587 |
| PPI (ppi) | 94 | 1.878 | 2.890 |

Figura: `reports/figures/analisisB_boxplot_rmse_indicador.png` (eje y recortado en 0.05 para que sea legible — Malta/ecpi tiene RMSE≈0 porque su índice de energía estuvo literalmente congelado en el mismo valor 30+ meses seguidos, 2022-10 a 2025-03; probablemente precios regulados/subsidiados durante la crisis energética europea. No es un error: con una serie constante, tanto el naive como ARIMA "aciertan" siempre).

**Kruskal-Wallis entre los 5 indicadores** (no pareado, referencia general): H=198.97, p=6.26e-42.

**Hipótesis específica: core (ccpi) es más predecible que headline (hcpi)** — test pareado, mismos países en ambos indicadores:

Wilcoxon signed-rank (n=76 países): estadístico=320.0, p=3.26e-09. **Diferencia significativa**: Core CPI (mediana RMSE=0.370) es sistemáticamente más predecible que Headline CPI (mediana RMSE=0.560).

## 2. Volatilidad por componente

Ranking de indicadores por RMSE mediano (más volátil/impredecible primero):

1. Energy CPI (ecpi): 2.078
2. PPI (ppi): 1.878
3. Food CPI (fcpi): 1.148
4. Headline CPI (hcpi): 0.697
5. Core CPI (ccpi): 0.376

**Hipótesis: energía (ecpi) y alimentos (fcpi) son más volátiles/impredecibles que el core (ccpi)** — tests pareados:

- Energy CPI vs. Core CPI: Wilcoxon signed-rank (n=75 países): estadístico=185.0, p=5.84e-11. **Diferencia significativa**: Energy CPI (mediana RMSE=2.779) es sistemáticamente menos predecible que Core CPI (mediana RMSE=0.376).

- Food CPI vs. Core CPI: Wilcoxon signed-rank (n=72 países): estadístico=74.0, p=3.44e-12. **Diferencia significativa**: Food CPI (mediana RMSE=1.060) es sistemáticamente menos predecible que Core CPI (mediana RMSE=0.363).

## 3. Persistencia GARCH por indicador

Persistencia (alpha+beta) mediana por indicador (series con GARCH convergido):

| Indicador | N series | Persistencia mediana | Persistencia media |
|---|---|---|---|
| Headline CPI (hcpi) | 172 | 0.961 | 0.913 |
| Energy CPI (ecpi) | 151 | 0.976 | 0.893 |
| Food CPI (fcpi) | 131 | 0.964 | 0.900 |
| Core CPI (ccpi) | 79 | 0.952 | 0.892 |
| PPI (ppi) | 93 | 0.972 | 0.931 |

Figura: `reports/figures/analisisB_boxplot_persistencia_indicador.png`.

**Kruskal-Wallis entre los 5 indicadores**: H=7.26, p=1.23e-01.

**No hay diferencia significativa en persistencia entre indicadores** con este test — no se puede confirmar con estos datos que los shocks de energía/alimentos sean más (o menos) transitorios que los del índice general o el core.

## 4. Países con los 5 indicadores: ¿el orden de previsibilidad es consistente?

**57 países** tienen los 5 indicadores con RMSE walk-forward válido.

Rango promedio de previsibilidad dentro de cada país (1=más predecible, 5=menos):

- Core CPI (ccpi): 1.21
- Headline CPI (hcpi): 2.23
- Food CPI (fcpi): 3.42
- PPI (ppi): 3.91
- Energy CPI (ecpi): 4.23

Figura: `reports/figures/analisisB_rango_promedio.png`.

**Test de Friedman** (equivalente no paramétrico de ANOVA de medidas repetidas — H0: no hay un orden consistente entre indicadores dentro de cada país): estadístico=144.00, p=3.93e-30.

**El orden de previsibilidad SÍ es consistente entre países**: no es azar que algunos indicadores tiendan a ser más predecibles que otros dentro del mismo país — hay una jerarquía estructural entre componentes que se repite país a país, no solo un patrón agregado a nivel de medianas.

## Hallazgos principales

- **Confirmado**: el core (ccpi) es sistemáticamente más predecible que el headline (hcpi) (Wilcoxon p=3.3e-09, n=76) — consistente con la idea de que excluir alimentos/energía saca ruido, no señal.
- Volatilidad de energía/alimentos vs. core: Energy CPI SÍ es significativamente más volátil que el core; Food CPI SÍ es significativamente más volátil que el core.
- La persistencia de volatilidad NO difiere significativamente entre indicadores (p=0.12) en este panel.
- Con Friedman (p=3.9e-30, n=57 países), el orden de previsibilidad entre indicadores es una estructura real y repetible país a país, no solo un artefacto de promediar medianas.
