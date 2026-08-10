# Remediación R1 — Benchmark Atkeson-Ohanian (hallazgo C.5)

Remediación del hallazgo C.5 de `reports/auditoria_integral.md`: el único benchmark usado hasta ahora era random walk puro. Se agregó el benchmark de Atkeson & Ohanian (2001) — promedio móvil de los últimos 12 meses observados — como segundo baseline, sobre la misma ventana walk-forward (24 meses) ya usada por ARIMA y el random walk. No se re-ajustó ningún modelo ARIMA/GARCH; se reutilizó `rmse_arima_walkforward` ya calculado.

## Verificación de no-regresión

Las 25 columnas preexistentes de `resultados_modelos_robusto.parquet` y las de `resultados_enriquecidos.parquet` se compararon fila por fila (`Series.equals`, sensible a NaN) antes y después de este cambio: **idénticas en ambos casos**. Este script solo agrega 3 columnas nuevas: `rmse_atkeson_ohanian`, `ratio_vs_ao`, `arima_supera_ao` (más `n_pasos_ao`, informativa).

## Hallazgo

- **ARIMA le gana al benchmark Atkeson-Ohanian**: 634/640 series (**99.1%**).
- **ARIMA le gana al random walk**: 403/639 series (**63.1%**, cifra ya reportada en Análisis A).
- Diferencia: **+36.0% puntos porcentuales**.

**No se confirma la hipótesis del hallazgo C.5, y el resultado es el opuesto al esperado**: ARIMA le gana a Atkeson-Ohanian en 99.1% de las series, muchísimo más que el 63.1% contra el random walk — el benchmark AO resultó mucho *más fácil* de superar en este panel, no más difícil.

**Explicación**: la ventana de evaluación walk-forward usa, para cada serie, los últimos 24 meses de datos disponibles (hasta 2025-03 para la mayoría de los países desarrollados). Ese tramo cubre el pico y la posterior desinflación rápida post-pandemia (ej. EE.UU.: de ~8% interanual a mediados de 2022 a ~3% en 2025). Un promedio móvil de 12 meses **reacciona con rezago severo** ante un cambio de tendencia de esa magnitud (sigue prediciendo ~8% cuando la inflación real ya bajó a 3%), mientras que el random walk (usa el último valor observado) se ajusta de inmediato en cada paso. El benchmark de Atkeson-Ohanian (2001) es conocido en la literatura por ser difícil de superar en regímenes de inflación **estables y sin tendencia marcada** — no es el caso de esta ventana de evaluación, que coincide con uno de los períodos de mayor volatilidad de tendencia en inflación de las últimas décadas. La conclusión no es que AO sea un benchmark débil en general, sino que esta ventana temporal específica lo penaliza estructuralmente.

Ratio promedio/mediana vs. AO (excluyendo 1 caso(s) con `rmse_ao=0`): 0.366 / 0.320. Vs. random walk: 0.953 / 0.966.

## Sanity check: ¿se mantiene el patrón estables-vs-crisis?

| País | ratio_vs_naive | ratio_vs_ao |
|---|---|---|
| ARG | 0.609 | 0.176 |
| BRA | 1.267 | 0.370 |
| DEU | 1.000 | 0.273 |
| GBR | 0.988 | 0.274 |
| JPN | 1.033 | 0.689 |
| TUR | 0.801 | 0.248 |
| USA | 0.988 | 0.274 |
| VEN | 0.618 | 0.129 |
| ZAF | 1.000 | 0.360 |

El patrón se mantiene en términos *relativos*: Argentina y Venezuela (crisis, tendencia sostenida) siguen teniendo ratios más bajos (ARIMA más dominante) que los países estables. Pero la distinción se **diluye** en términos *absolutos*: contra AO, hasta los países estables (USA, DEU, GBR) tienen ratio_vs_ao muy por debajo de 1 (~0.27), algo que no pasaba contra el random walk (ratio_vs_naive ≈0.99, prácticamente empatados). El benchmark AO es tan débil en esta ventana que deja de discriminar entre regímenes — todos le ganan cómodamente.

## Observaciones adicionales (detectadas al implementar este benchmark, no introducidas por él)

- **3 par(es) de países con series `inflacion_yoy_log` byte-idénticas** en `inflacion_mensual_completa_v2.parquet` (mismo indicador, mismos valores en todas las fechas): FIN, GAB; GBR, USA; CZE, DJI. Preexistente a este cambio — se verificó que `rmse_arima_walkforward` ya era idéntico para estos pares antes de esta remediación, así que no fue introducido por el benchmark AO. Amerita revisión de la fuente (posible mapeo erróneo código-país↔serie en el Excel del Banco Mundial); no se corrige acá por estar fuera del alcance de esta remediación.
- **1 serie (MLT/ecpi)** tiene `inflacion_yoy_log`=0 en las 39 observaciones más recientes (índice plano/congelado en la fuente), lo que produce `rmse_atkeson_ohanian`=0 y `ratio_vs_ao`=inf para esa fila. Se cuenta correctamente como 'no le gana a AO' (`arima_supera_ao=False`) pero se excluyó del promedio/mediana de `ratio_vs_ao` reportado arriba para no distorsionarlo.

## Conclusión sobre el hallazgo C.5

El hallazgo C.5 queda **remediado en el sentido técnico** (el benchmark AO fue implementado y reportado), pero la evidencia contradice la hipótesis que motivó la recomendación: en esta ventana de evaluación, Atkeson-Ohanian NO es un benchmark más exigente que el random walk, sino notablemente más débil, por la razón temporal explicada arriba. La cifra de referencia para evaluar el aporte real de ARIMA sigue siendo el 63.1% contra random walk (Análisis A) — la comparación contra AO no la invalida ni la reduce; si acaso, refuerza que ARIMA aporta valor incluso frente a benchmarks alternativos, aunque en este panel el random walk resultó ser, de los dos, el más difícil de superar.
