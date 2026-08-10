# Remediación R2 — Flag `residuos_no_blancos` (hallazgo C.2)

Remediación del hallazgo C.2 de `reports/auditoria_integral.md`: el GARCH se ajusta sobre los residuos del ARIMA inicial sin filtrar ni marcar los casos en que esos residuos todavía tienen autocorrelación remanente (Ljung-Box p<0.05, especificación insuficiente del ARIMA). Se agrega la columna `residuos_no_blancos` (`ljung_box_p < 0.05`) a `resultados_modelos_robusto.parquet` para trazabilidad, sin re-ajustar ningún modelo.

## Verificación de no-regresión

Las columnas preexistentes de `resultados_modelos_robusto.parquet` y `resultados_enriquecidos.parquet` se compararon fila por fila antes y después: **idénticas en ambos casos**. Este script solo agrega `residuos_no_blancos`.

## Hallazgo

- **519/626 (82.9%)** de los ajustes GARCH corren sobre residuos ARIMA con `ljung_box_p<0.05` (autocorrelación remanente).

**Matiz — parcialmente artefacto del tamaño de muestra**: las series marcadas `residuos_no_blancos=True` son sistemáticamente más largas (mediana 290 meses) que las que no (mediana 170 meses) — Mann-Whitney U=44864, **p=4.74e-24**. La correlación de Spearman entre `meses_usados` y `ljung_box_p` es **ρ=-0.70** (p=4.86e-93): a mayor longitud de serie, el test de Ljung-Box detecta autocorrelación cada vez más chica como "significativa", aunque sea económicamente trivial. Esto no descarta que parte del 83% sea especificación real insuficiente, pero sí indica que la cifra no debe leerse como "81% de los ARIMA están mal especificados" sin matiz.

**Cómo leer el GARCH del proyecto con esta salvedad**: el hallazgo central del proyecto (gradiente de previsibilidad por nivel de ingreso, Análisis A) usa el RMSE walk-forward del ARIMA, no los residuos in-sample ni GARCH, y no se ve afectado. El resultado de Análisis C sobre persistencia GARCH (ausencia de patrón por indicador/ingreso) sí debe leerse con esta salvedad: no se puede distinguir, sin repetir el análisis restringido a las series con residuos limpios, cuánto de esa ausencia de patrón es señal real y cuánto es ruido de una base parcialmente mal filtrada.
