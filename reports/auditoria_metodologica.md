# Auditoría metodológica

Informe generado por `src/11_auditoria_metodologica.py`. **Solo diagnóstico: no se modificó ningún script del pipeline de modelado ni de análisis existente.** Objetivo: medir el impacto de dos debilidades metodológicas identificadas, no asumirlas ni descartarlas de antemano.

## Parte 1 — Leakage en selección de orden ARIMA

**Diseño del experimento:** para cada serie de la muestra se comparan dos formas de elegir el orden (p,d,q) inicial: **(a) con leakage** — `auto_arima` corre viendo la serie completa, incluyendo los 24 meses que después se usan para evaluar — vs. **(b) correcto** — `auto_arima` corre solo con los datos anteriores a esos 24 meses (lo que ya hace `06b_modelado_robusto.py`). En ambos casos, los **parámetros** del modelo inicial se calibran solo con datos de entrenamiento (nunca con el futuro), y el walk-forward posterior es idéntico en los dos casos (mismas re-estimaciones cada 6 pasos, usando en cada paso solo lo revelado hasta ese momento) — así se aísla específicamente el efecto de qué orden se elige, no otra cosa.

Muestra: **48 países** (hcpi, estratificado por nivel de ingreso).

- Orden (p,d,q) distinto entre (a) y (b): **29 de 48 series (60.4%)**.
- Diferencia de RMSE walk-forward (leak − correcto), mediana: **+0.0000** (+0.0% relativo).

**Test de Wilcoxon signed-rank** (H0: no hay diferencia sistemática entre RMSE con leakage y sin leakage): estadístico=462.0, p=7.00e-01.

**El leakage NO tiene un efecto sistemático y estadísticamente significativo** sobre el RMSE en esta muestra — aunque el orden elegido cambia en algunos casos, el impacto en la métrica de previsibilidad walk-forward no es distinguible de cero. Esto es consistente con que, en el pipeline real (`06b_modelado_robusto.py`), la selección de orden **ya excluye** la ventana de evaluación desde el arranque (`train_inicial = full[:-VENTANA_EVAL]`) — el leakage que se está midiendo acá es un escenario contrafáctico ("qué pasaría si no lo hubiéramos excluido"), no algo presente en los resultados ya reportados.

**Impacto en el ranking entre países:** correlación de Spearman entre el RMSE correcto y el RMSE con leakage: ρ=0.996 (p=2.44e-49).

El ranking de países por previsibilidad es prácticamente idéntico con o sin leakage — aunque el leakage moviera el RMSE puntual de algunas series, no reordena de forma relevante qué países son más o menos predecibles entre sí.

Las 10 series donde más cambia el RMSE (valor absoluto relativo):

| País | Orden correcto | Orden leak | RMSE correcto | RMSE leak | Diff % |
|---|---|---|---|---|---|
| SYC | (1, 1, 3) | (1, 1, 1) | 0.5410 | 0.6737 | +24.5% |
| LBY | (1, 0, 2) | (1, 1, 0) | 0.3631 | 0.3010 | -17.1% |
| AZE | (2, 0, 2) | (2, 0, 2) | 0.6077 | 0.6864 | +13.0% |
| PER | (2, 1, 2) | (2, 0, 1) | 0.4237 | 0.3742 | -11.7% |
| SLV | (0, 1, 1) | (2, 0, 0) | 0.4192 | 0.3793 | -9.5% |
| TCD | (2, 0, 0) | (2, 1, 2) | 1.7587 | 1.6245 | -7.6% |
| BLR | (1, 1, 0) | (2, 1, 3) | 1.3089 | 1.2298 | -6.0% |
| MNE | (3, 1, 3) | (1, 1, 0) | 1.1385 | 1.0883 | -4.4% |
| KIR | (1, 0, 2) | (3, 0, 4) | 4.0268 | 3.8578 | -4.2% |
| BDI | (1, 0, 0) | (2, 0, 5) | 2.5919 | 2.6893 | +3.8% |

**Conclusión Parte 1:** **el leakage descrito no está presente en el pipeline que efectivamente generó los resultados usados en Análisis A/B/C** (`06b_modelado_robusto.py` ya excluye la ventana de evaluación de la selección de orden) — el experimento contrafáctico de esta auditoría no encuentra evidencia de que hacerlo mal (a propósito, como comparación) cambiaría las conclusiones de forma sistemática. No hace falta rehacer el modelado por este motivo.

## Parte 2 — Longitud de serie como confusor del gradiente de ingreso

Sobre las 174 series hcpi con clasificación válida:

- Correlación **nivel de ingreso ↔ meses_usados**: ρ=0.492, p=5.19e-12.
- Correlación **meses_usados ↔ RMSE**: ρ=-0.291, p=9.71e-05.
- Correlación **nivel de ingreso ↔ RMSE** (ya visto en Análisis A): ρ=-0.420, p=7.90e-09.

**La prueba clave — correlación parcial ingreso↔RMSE controlando por meses_usados:** ρ parcial=-0.332, p=7.93e-06.

**El gradiente de ingreso SOBREVIVE al controlar por longitud de serie** — sigue siendo significativo incluso descontando el efecto de que los países ricos tienen series más largas. Es evidencia a favor de que el hallazgo de Análisis A es economía real, no un artefacto de cantidad de datos.

**Chequeo de robustez — mismo largo para todos:** se truncó cada serie hcpi a los últimos 48 meses (el piso mínimo real de la muestra) y se re-corrió `auto_arima` + walk-forward desde cero sobre esa versión truncada, así todos los países entran al test de Kruskal-Wallis con exactamente la misma cantidad de datos.

N series con 48 meses o más: **174**.

RMSE mediano por nivel de ingreso, serie completa vs. truncada a longitud común:

| Nivel de ingreso | RMSE mediano (serie completa) | RMSE mediano (truncada) |
|---|---|---|
| Low income | 1.7014 | 1.6099 |
| Lower middle income | 0.8490 | 0.9692 |
| Upper middle income | 0.7029 | 0.7263 |
| High income | 0.5376 | 0.6227 |

**Kruskal-Wallis sobre la muestra truncada**: H=28.93, p=2.31e-06.

**El gradiente de ingreso persiste incluso con longitud de serie idéntica para todos los países** — confirmación adicional, independiente de la correlación parcial, de que el hallazgo de Análisis A es real.

**Conclusión Parte 2:** **ambos chequeos (correlación parcial y truncamiento) coinciden en que el gradiente de ingreso es real, no un artefacto de longitud de serie.** El hallazgo central de Análisis A se sostiene.
