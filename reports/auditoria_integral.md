# Auditoría Integral — Proyecto Global Inflation ARIMA-GARCH

## Estándar: revisión independiente tipo Big Four

**Fecha:** 2026-08-08
**Alcance:** integridad de datos, revisión de código, metodología, validez estadística, reproducibilidad, documentación, posicionamiento del proyecto.
**Naturaleza:** auditoría puramente diagnóstica. Ningún hallazgo de este documento fue remediado — la remediación queda para una fase correctiva posterior, explícitamente fuera de alcance acá.

**Nota de verificación:** cada hallazgo listado abajo fue re-verificado de forma independiente (releyendo el código citado, o recalculando la cifra desde `data/raw/Inflation-data.xlsx` / los parquets procesados) antes de incorporarlo a este documento. En los puntos donde la verificación encontró una cifra distinta a la reportada originalmente, se indica explícitamente **[cifra corregida en verificación]** con el valor original a continuación, para que quede trazable qué cambió y por qué. El resto de los hallazgos verificó exacto.

- **Ronda Fases A-B** (2026-08-08): 4 correcciones — reparto interno de A.3 (9+27, no 12+24), ejemplos de puntos válidos de A.3 (columna equivocada), ejemplo de Mozambique en A.6 (serie no duplicada), matiz de B.5 (el README sí menciona el piso, parcialmente).
- **Ronda Fase C-E, parte 1** (2026-08-08): 2 correcciones menores de precisión — ratio de D.3 (3.16× no 3.2×) y cantidad de paquetes de E.2 (121 no "130+"). El resto (incluyendo los números más cargados de C.2: 520/640, 519, medianas 289.5/166.5, p=4.36e-29) verificó exacto.
- **Ronda Fase E, parte 2 (E.1/E.4)** (2026-08-08): a diferencia de las rondas anteriores, E.1 y E.4 no fueron "hallazgos ya verificados" para formalizar — se ejecutaron de cero en esta sesión (clon real de GitHub a un directorio nuevo, venv nuevo, `data/raw` y `data/processed` borrados antes de correr para forzar una reproducción genuina, incluida la re-descarga por red). Los resultados de esa ejecución son la evidencia primaria de E.1 y E.4, no una re-verificación de un hallazgo preexistente.

## Clasificación de severidad

| Severidad | Definición |
|---|---|
| 🔴 **CRÍTICO** | Invalida hallazgos o resultados ya publicados |
| 🟠 **SIGNIFICATIVO** | Decisión material no documentada, o error que afecta el alcance de una conclusión |
| 🟡 **MENOR** | Imprecisión que no afecta las conclusiones |
| 🔵 **OBSERVACIÓN** | Nota de mejora, sin impacto en validez |

---

## FASE A — Integridad de Datos

### A.1 — Trazabilidad fuente → resultado
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se muestrearon 8 valores del parquet final (`inflacion_mensual_completa_v2.parquet`) y se rastrearon hasta la celda correspondiente en `data/raw/Inflation-data.xlsx`.

**Evidencia:** coincidencia exacta del índice crudo en los 8 casos muestreados (incluye casos con y sin ramificación por `Indicator Type`).

**Impacto en conclusiones:** ninguno — confirma que no hay corrupción de datos entre la fuente y el resultado final.

**Remediación sugerida:** N/A.

---

### A.2 — Fórmula log-diff
**Severidad:** — **SIN HALLAZGO**

**Descripción:** recálculo manual de `inflacion_yoy_log = 100·(ln(P_t) − ln(P_{t-12}))` sobre una muestra de filas del parquet final, comparado contra el valor almacenado.

**Evidencia:** diferencia 0.000000 en todos los casos verificados.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** N/A.

---

### A.3 — Completitud del panel
**Severidad:** 🟠 **SIGNIFICATIVO**

**Descripción:** de las 688 series país-indicador presentes en el Excel original (tras deduplicar), **640 llegan al resultado final como `apto_arima=True`** — 48 quedan excluidas. De esas 48, la exclusión no es igual de justificable en todos los casos.

**Evidencia (recalculada directamente sobre `data/raw/Inflation-data.xlsx` y confirmada contra las columnas `n_meses_validos`/`apto_arima` de `inflacion_mensual_completa_v2.parquet`):**

| Motivo de exclusión | N series |
|---|---|
| Sin ningún dato de índice (`n_meses_validos = 0`) | 12 |
| Bajo el piso de 60 meses, con 0 huecos internos | 9 **[cifra corregida en verificación; reportado originalmente: 12]** |
| **Cobertura ≥60 meses pero con algún hueco interno → excluidas igual** | **27 [cifra corregida en verificación; reportado originalmente: 24]** |
| **Total excluidas** | **48** |
| Aptas (`apto_arima=True`) | 640 |

El total (48 excluidas / 640 aptas de 688) coincide exactamente con lo reportado originalmente — la corrección es únicamente en el reparto interno entre "bajo el piso" y "con cobertura suficiente pero excluidas por huecos".

Las 27 series con cobertura sustancial excluidas por tener aunque sea un solo hueco interno (columna `n_meses_validos` real del pipeline, no una aproximación):

| Serie | `n_meses_validos` | `n_huecos_internos` |
|---|---|---|
| IRL / fcpi | 616 | ≥1 (clasificada `fragmentada`) |
| THA / ppi | 610 | 1 |
| ISL / fcpi | 557 | ≥1 (`fragmentada`) |
| CAF / ppi | 394 | ≥1 (`fragmentada`) |
| RUS / hcpi | 365 | 2 |
| BGR / hcpi | 362 | 1 |
| BGR / ecpi | 362 | 1 |
| BGR / fcpi | 362 | 1 |
| SDN / ecpi | 324 | 1 |
| ... (18 series adicionales, 61-251 meses) | | |

**Nota sobre los ejemplos citados originalmente:** los valores propuestos en el brief inicial (Rusia 351, Bulgaria 350, Tailandia 598, Irlanda 604) no coinciden con `n_meses_validos` — la columna que efectivamente determina `apto_arima` en el código (Hallazgo B.1). Están sistemáticamente ~12 unidades por debajo de la cifra real, consistente con haber usado una métrica de "meses de `inflacion_yoy_log` disponibles" (que pierde los primeros 12 meses por el lag interanual) en vez de `n_meses_validos` (meses de índice crudo, la base real del criterio de exclusión). Se corrigen acá a los valores reales de la columna que el propio pipeline usa para decidir la exclusión.

**Impacto en conclusiones:** ninguno de los análisis A/B/C/auditoría/robustez está invalidado — todos declaran explícitamente que trabajan sobre el universo `apto_arima`/`apto_garch`. El impacto es de **completitud no documentada**: un lector de `README.md` o del notebook no tiene forma de saber que 27 series con cientos de puntos válidos (algunas con más de 600 meses de historia) quedaron completamente afuera del panel modelado por tener un único hueco de un mes.

**Remediación sugerida (no implementar en esta fase):** documentar explícitamente en `README.md` y en el notebook que el criterio de aptitud exige cero huecos internos absolutos, y cuantificar cuántas series con cobertura sustancial quedan afuera por esta razón. Evaluar en la fase correctiva si conviene una regla menos estricta (ver B.1).

---

### A.5 — Validación contra tasa oficial
**Severidad:** 🔵 **OBSERVACIÓN** — SIN HALLAZGO material

**Descripción:** inflación anual reconstruida desde el índice mensual, comparada contra la tasa oficial (`hcpi_a`) en 10 países.

**Evidencia:** error absoluto medio global 0.227 pp. El país con mayor error es EE.UU. (1.64 pp), consistente con una diferencia de redondeo/vintage en la fuente oficial, no con un error de cálculo propio (Fase 4 ya había reproducido `hcpi_a` a nivel observación-año, N=483, con mediana de error ~0.00001 pp — esta cifra de A.5 es una agregación a nivel país, distinta pero no contradictoria).

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ninguna acción requerida; opcionalmente anotar en la documentación que el caso EE.UU. es la excepción visible y por qué.

---

### A.6 — Heurística de deduplicación
**Severidad:** 🟡 **MENOR**

**Descripción:** la regla "quedarse con la fila más completa" (más puntos válidos) puede sacrificar actualidad frente a la fila alternativa descartada. Esto ya estaba parcialmente documentado (`reports/00_bitacora_decisiones.md`, con flag `dedup_conflicto_recencia` en el parquet final) pero la pérdida es real y vale la pena tenerla explícita en un documento de auditoría.

**Evidencia (confirmada contra `data/raw/Inflation-data.xlsx`):**

| Serie | Fila elegida | Fila alternativa descartada | Meses de actualidad perdidos |
|---|---|---|---|
| AUT / ppi | 453 pts, hasta 2024-09 | 302 pts, hasta 2025-02 | 5 |
| NLD / ppi | 657 pts, hasta 2024-09 | 530 pts, hasta 2025-02 | 5 |
| PRT / ppi | 297 pts, hasta 2024-09 | 243 pts, hasta 2025-03 | 6 |
| MOZ / ecpi | 211 pts, hasta 2024-08 | 111 pts, hasta 2025-03 | 7 |

**Nota de verificación:** el ejemplo de Mozambique citado originalmente ("MOZ ppi termina 2023-03, −2 años") es **incorrecto** — `MOZ` no tiene fila duplicada en `ppi_m` (una sola fila, 147 puntos, termina naturalmente en 2023-03 porque es toda la data disponible, no por una elección de deduplicación). El caso real de Mozambique con pérdida de actualidad por deduplicación está en `ecpi_m` (tabla arriba), ya documentado en `00_bitacora_decisiones.md`.

**Impacto en conclusiones:** ninguno — las 8 series con `dedup_conflicto_recencia=True` ya están marcadas y trazables en el parquet final; no hay ningún caso oculto o sin flag.

**Remediación sugerida:** ninguna acción de código requerida (la trazabilidad ya existe). Sugerido para la fase correctiva: evaluar si vale la pena, para los casos de mayor pérdida de actualidad, dar prioridad a la fila más reciente en vez de la más completa, o exponer ambas métricas al usuario final del parquet.

---

## FASE B — Revisión de Código

### B.1 — Criterio de aptitud exige cero huecos internos absolutos (causa raíz de A.3)
**Severidad:** 🟠 **SIGNIFICATIVO**

**Descripción:** en `src/05_etl_corregido.py`, líneas 189-190:

```python
apto_arima = (n_huecos == 0) and (n_validos >= PISO_ARIMA)
apto_garch = (n_huecos == 0) and (n_validos >= PISO_GARCH)
```

El criterio exige **cero huecos internos absolutos**, sin importar cuán largo sea el hueco ni cuán larga sea la serie. Una serie con 616 meses de historia y un solo mes faltante (ej. Irlanda/fcpi) queda **totalmente excluida**, exactamente igual que una serie con un hueco de 29 meses.

**Inconsistencia metodológica adicional:** el plan aprobado en `00_bitacora_decisiones.md` (Paso 9) especifica el criterio de aptitud en términos de huecos, pero por separado —tanto en Fase 3 (`fase3_cobertura_temporal.py`) como en la intención declarada del pipeline de modelado— se documentó la idea de trabajar sobre "el tramo continuo más largo" para series con huecos, no de descartar la serie entera. El código de `05_etl_corregido.py` implementa la versión más estricta (exclusión total) sin que quede documentado como una decisión explícita — no hay comentario, docstring ni entrada en la bitácora que explique por qué se abandonó la idea del tramo más largo en favor de la exclusión binaria.

**Evidencia:** líneas 189-190 de `src/05_etl_corregido.py` (citadas arriba, verificadas exactas). Consecuencia cuantificada en A.3: 27 series con cobertura sustancial (61-616 meses) excluidas del todo.

**Impacto en conclusiones:** no invalida ningún resultado ya reportado (todos los análisis trabajan correctamente sobre el universo `apto_arima` tal como está definido). El impacto es sobre el **alcance** del panel modelado: series como Rusia (`hcpi`, 365 meses) o Irlanda (`fcpi`, 616 meses) — economías con series largas y de interés genuino — no aparecen en ningún ranking, boxplot o regresión de Análisis A/B/C simplemente por un hueco puntual, no por falta real de datos.

**Remediación sugerida (no implementar en esta fase):** evaluar reemplazar el criterio binario por la lógica ya prevista en el plan original — recortar cada serie con huecos a su tramo continuo más largo (ya implementado como utilidad en `06b_modelado_robusto.py::recortar_tramo_continuo`, pero aplicado ahí sobre series que la ETL ya declaró aptas, no sobre las que quedaron excluidas antes de llegar al modelado) y re-evaluar la aptitud sobre ese tramo recortado, en vez de sobre la serie completa con huecos.

---

### B.2 — Data leakage en la validación walk-forward
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se verificó línea por línea `validacion_walk_forward()` en `src/06b_modelado_robusto.py` (y su réplica en `11_auditoria_metodologica.py`/`12_robustez_multivariado.py`).

**Evidencia:** en cada paso del loop, `modelo_actual.predict(n_periods=1)` se ejecuta **antes** de que el valor real (`valor_real = full[S + i]`) se use para calcular el error o para actualizar el modelo. La re-estimación periódica (`con_timeout(_ajustar_arima, ..., full[:S + i + 1])`) usa exactamente los datos revelados hasta ese punto, nunca datos futuros. El `.update()` en los pasos intermedios ocurre después de medir el error del paso actual. Implementación correcta — sin leakage.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** N/A. (Consistente con el hallazgo ya reportado en `reports/auditoria_metodologica.md`, que midió el impacto de un escenario de leakage contrafáctico y no encontró efecto significativo — acá se confirma además que el escenario contrafáctico ni siquiera está presente en el código real.)

---

### B.3 — Determinismo y semillas
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se revisó cada punto de aleatoriedad en el código de modelado y auditoría.

**Evidencia:** bootstrap de RMSE (`src/12_robustez_multivariado.py::bootstrap_rmse_ci`) usa `seed=0` como default, sin override en las llamadas reales — determinístico. Muestreo estratificado de países en la auditoría de leakage (`src/11_auditoria_metodologica.py`) usa `np.random.RandomState(42)`. No se encontró ningún uso de aleatoriedad sin semilla fija en el código de pipeline o de análisis.

**Impacto en conclusiones:** ninguno — consistente con la verificación de reproducibilidad end-to-end ya documentada (`run_pipeline.py` reprodujo cada `.md`/`.parquet` byte a byte).

**Remediación sugerida:** N/A.

---

### B.5 — Consistencia de parámetros entre código y documentación
**Severidad:** 🔵 **OBSERVACIÓN**

**Descripción:** se verificaron los parámetros clave citados en `README.md` contra las constantes reales del código.

**Evidencia:** `VENTANA_EVAL = 24`, `REESTIMAR_CADA = 6` (`src/06b_modelado_robusto.py`, líneas 39-40) y `PISO_GARCH = 100` (`src/05_etl_corregido.py`, línea 31) coinciden exactamente con lo descrito en `README.md`.

**Matiz sobre el criterio de huecos:** `README.md` (sección "Limitaciones honestas") **sí menciona** "el piso de 100 meses sin huecos internos que exige `apto_garch`" — no es cierto que esté completamente ausente de la documentación. Lo que no está documentado es el **alcance real** del criterio: (a) que la misma regla de cero-huecos aplica también a `apto_arima`, no solo a `apto_garch`, y (b) la magnitud del efecto — 27 series con cobertura sustancial excluidas (A.3), no solo los 2-3 casos de Argentina/Venezuela mencionados como ejemplo en esa sección.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ampliar la sección de limitaciones para cuantificar el efecto sobre `apto_arima` también, no solo sobre `apto_garch`, una vez resuelto B.1.

---

## FASE C — Metodología

### C.1 — Elección de la transformación log-diff
**Severidad:** 🔵 **OBSERVACIÓN**

**Descripción:** la elección de `log-diff` sobre `pct_change` para alimentar el modelado está justificada por estabilidad numérica ante hiperinflación (Fase 4) y validada externamente contra la tasa oficial del Banco Mundial (A.5). No se probó sensibilidad del resultado ante transformaciones alternativas (ej. Box-Cox, diferencias de segundo orden en log).

**Evidencia:** `reports/fase4_univariada.md` (comparación cuantitativa `pct_change` vs. `log-diff`); A.5 (validación externa, error medio 0.227 pp).

**Impacto en conclusiones:** ninguno — la elección está defendida con evidencia, no es una decisión arbitraria.

**Remediación sugerida:** ninguna acción requerida. Opcionalmente, en una fase de robustez futura, re-correr el modelado con una transformación alternativa sobre una muestra chica para confirmar que el ranking de previsibilidad no depende de la elección de transformación.

---

### C.2 — ARIMA mal especificado se propaga a GARCH sin filtrar
**Severidad:** 🟠 **SIGNIFICATIVO**

**Descripción:** el test de Ljung-Box sobre los residuos del ARIMA inicial (el mismo modelo cuyos residuos alimentan GARCH) da p<0.05 —residuos con autocorrelación remanente, señal de especificación insuficiente— en una fracción mayoritaria de las series, y esas series no se filtran ni se marcan antes de pasarlas a GARCH.

**Evidencia (recalculada sobre `resultados_enriquecidos.parquet`):**
- **520 de 640 series (81.2%)** con ARIMA convergido tienen `ljung_box_p < 0.05`.
- De esas 520, **519 tienen GARCH ajustado** sobre esos residuos autocorrelacionados.
- **421 de las 640 (65.8% del total, 81.0% de las 520 que fallan)** tienen `ljung_box_p < 0.001` — muy por debajo del umbral convencional, lo que sugiere que en una porción sustancial de los casos no es solo sensibilidad del test a n grande.
- **Matiz confirmado**: las series que fallan Ljung-Box son sistemáticamente más largas (mediana 289.5 meses) que las que no fallan (mediana 166.5 meses) — Mann-Whitney U, **p=4.36×10⁻²⁹**. Es consistente con que, a mayor n, el test de Ljung-Box detecta autocorrelación cada vez más chica como "estadísticamente significativa" aunque sea económicamente trivial — parte del 81% probablemente es esto, no necesariamente mala especificación real.

**Impacto en conclusiones:** el hallazgo central del proyecto (gradiente de previsibilidad por ingreso, Análisis A) se basa en el **RMSE walk-forward del ARIMA**, no en los residuos in-sample ni en GARCH — no se ve afectado directamente. El hallazgo de Análisis C sobre persistencia GARCH (que no distingue por indicador ni por ingreso) es un hallazgo **negativo** (ausencia de diferencia) — que la volatilidad ajustada sobre residuos parcialmente mal especificados no muestre patrón es, si acaso, un motivo adicional de cautela sobre ese resultado negativo, no una invalidación de un resultado positivo. El daño real es que el proyecto no reportó en ningún lado qué fracción de los ajustes GARCH parte de una base con autocorrelación residual, y por lo tanto no se puede distinguir, sin este análisis, cuánto de la falta de patrón en persistencia GARCH (Análisis C) es señal real y cuánto es ruido de una base mal filtrada.

**Remediación sugerida (no implementar en esta fase):** filtrar (o al menos marcar con un flag `arima_bien_especificado`) las series con Ljung-Box significativo antes de interpretarlas en el contexto de GARCH; reportar la fracción afectada en `reports/analisis_C_volatilidad.md`; considerar repetir el análisis de persistencia GARCH restringido a las ~120 series (19%) con residuos limpios, como chequeo de robustez.

---

### C.3 — GARCH(1,1) simétrico, sin variantes asimétricas
**Severidad:** 🔵 **OBSERVACIÓN**

**Descripción:** el proyecto usa exclusivamente GARCH(1,1) simétrico. No distingue si un shock de inflación viene de una sorpresa al alza o a la baja (para eso harían falta EGARCH o GJR-GARCH).

**Evidencia:** `src/06b_modelado_robusto.py`, `_ajustar_garch()` — `arch_model(resid, vol="Garch", p=1, q=1, rescale=True)`, sin alternativa. Ya documentado como decisión consciente en `README.md`, sección "Trabajo futuro".

**Impacto en conclusiones:** ninguno — el alcance está declarado explícitamente, no es una omisión oculta. `rescale=True` afecta la escala de `omega` pero no la de la persistencia (`alpha+beta`), que es la métrica efectivamente usada en Análisis C — no hay confusión de unidades en el hallazgo reportado.

**Remediación sugerida:** ya recogida en "Trabajo futuro" del README — sin acción adicional en esta auditoría.

---

### C.4 — Sesgo por re-estimar el orden cada 6 pasos (no cada mes)
**Severidad:** 🔵 **OBSERVACIÓN** — **mitigado, ya verificado**

**Descripción:** el walk-forward re-busca `(p,d,q)` cada `REESTIMAR_CADA=6` pasos en vez de en cada uno de los 24, por eficiencia. Esto podría introducir un sesgo si el orden "óptimo" cambia rápido mes a mes.

**Evidencia:** `reports/auditoria_metodologica.md`, Parte 1 — el escenario de leakage (que es un caso más extremo de "el orden no se re-optimiza con cada dato nuevo") se midió directamente: el ranking de países con y sin ese efecto correlaciona en ρ=0.996 (Spearman). El efecto de la cadencia de re-estimación en sí no se aisló por separado, pero la cota superior de su impacto ya está acotada por esa medición.

**Impacto en conclusiones:** ninguno, dado lo ya verificado.

**Remediación sugerida:** ninguna acción requerida.

---

### C.5 — Baseline de comparación potencialmente sub-óptimo
**Severidad:** 🟠 **SIGNIFICATIVO**

**Descripción:** el único benchmark contra el que se mide el aporte de ARIMA es el random walk ("el próximo valor es el último observado"). La literatura de pronóstico de inflación (Atkeson & Ohanian, 2001, *"Are Phillips Curves Useful for Forecasting Inflation?"*) documenta que un promedio móvil de los últimos 12 meses suele ser un benchmark más difícil de superar que el random walk puro, para series de inflación específicamente.

**Evidencia:** `src/06b_modelado_robusto.py`, `validacion_walk_forward()` — `valor_anterior = full[S + i - 1]` es la única definición de baseline en todo el pipeline. No hay una segunda columna de referencia calculada.

**Impacto en conclusiones:** no invalida el 63% de series que le ganan al random walk (ese número es correcto para el benchmark que efectivamente se usó). Sí significa que esa cifra probablemente **sobreestima** el valor agregado real de ARIMA — contra un benchmark más exigente (media móvil 12m), la fracción de series donde ARIMA aporta algo probablemente sea menor a 63%. El hallazgo del gradiente de ingreso (Análisis A) es una comparación *relativa entre países*, no depende del benchmark absoluto, así que no se ve afectado en la misma medida.

**Remediación sugerida (no implementar en esta fase):** agregar el benchmark Atkeson-Ohanian (media móvil de 12 meses) al pipeline de modelado, calcular `ratio_vs_ao12` en paralelo a `ratio_vs_naive`, y reportar ambos en Análisis A.

---

### C.6 — Tratamiento de huecos internos
Ver **B.1** (Fase B) — inconsistencia ya registrada entre el criterio documentado ("usar el tramo continuo más largo") y el implementado (exclusión total de la serie ante cualquier hueco).

---

## FASE D — Validez Estadística

### D.1 — Supuestos de los tests utilizados
**Severidad:** 🔵 **OBSERVACIÓN**

**Descripción:** los tests no paramétricos (Kruskal-Wallis, Wilcoxon signed-rank, Friedman) usados en Análisis A/B son apropiados dado que el RMSE no es normal (asimetría alta, confirmada y reportada explícitamente por el propio proyecto en `reports/analisis_A_previsibilidad.md`). El único test paramétrico con supuestos cuestionables (chi-cuadrado, Análisis C, sección 2) ya fue auto-reportado con su propia advertencia de validez (38% de celdas con frecuencia esperada <5) en el momento en que se corrió, no en esta auditoría.

**Evidencia:** `reports/analisis_C_volatilidad.md`, sección 2 — advertencia de validez ya presente en el documento original.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ninguna acción requerida — es un ejemplo de buena práctica ya aplicada, no un hallazgo a remediar.

---

### D.2 — Multiplicidad de tests (riesgo de falsos positivos)
**Severidad:** — **SIN HALLAZGO** (fortaleza)

**Descripción:** se evaluó si los ~7 tests de significancia independientes que sostienen los hallazgos principales (no las docenas de comparaciones descriptivas incluidas en cada informe) sobreviven una corrección de Bonferroni conjunta.

**Evidencia:** los 7 tests principales — gradiente de ingreso (Kruskal-Wallis, p=5.6×10⁻⁷), núcleo vs. headline (Wilcoxon, p=3.3×10⁻⁹), energía vs. núcleo (Wilcoxon, p=5.8×10⁻¹¹), alimentos vs. núcleo (Wilcoxon, p=3.4×10⁻¹²), orden de previsibilidad entre indicadores (Friedman, p=3.9×10⁻³⁰), correlación parcial ingreso↔RMSE controlando longitud (p=7.9×10⁻⁶), gradiente sobre muestra truncada (Kruskal-Wallis, p=2.3×10⁻⁶) — tienen p-valores entre 1×10⁻⁶ y 1×10⁻³⁰. Con umbral de Bonferroni para 7 tests (0.05/7≈0.0071) o incluso para 10 (0.005), los 7 sobreviven con enorme margen.

**Matiz importante:** esto aplica a los tests de hipótesis independientes. **No** aplica de la misma manera a los coeficientes individuales del modelo OLS multivariado (`reports/robustez_multivariado.md`) — son estimaciones de un único modelo conjunto, no tests independientes, y no se corrigieron por multiplicidad entre sí. El más débil de esos coeficientes (`ingreso_Lower middle income`, p=0.017) **no sobreviviría** un umbral de Bonferroni de 0.005 si se lo tratara como parte de la misma familia de comparaciones — vale la pena tenerlo presente al citar ese coeficiente específico (a diferencia de los otros dos coeficientes de ingreso, p=0.001, que sí sobrevivirían holgadamente).

**Impacto en conclusiones:** ninguno sobre los 7 tests principales. Matiz agregado sobre un coeficiente específico del modelo multivariado.

**Remediación sugerida:** ninguna acción de código requerida. Sugerido documentar la distinción entre "tests independientes" y "coeficientes de un mismo modelo" la próxima vez que se cite el coeficiente de `ingreso_Lower middle income` específicamente.

---

### D.3 — Tamaño de efecto del hallazgo central
**Severidad:** — **SIN HALLAZGO** (fortaleza)

**Descripción:** se calculó el tamaño de efecto (no solo la significancia) del gradiente de previsibilidad por ingreso.

**Evidencia (recalculada):** épsilon-cuadrado = (H − k + 1)/(n − k) = (31.85 − 4 + 1)/(174 − 4) = **0.170** — efecto grande según las convenciones habituales (>0.14). Ratio de RMSE mediano entre el grupo menos predecible (Low income, 1.70) y el más predecible (High income, 0.54): **3.16×** **[precisión ajustada en verificación; reportado originalmente: 3.2×, diferencia menor de redondeo]**.

**Impacto en conclusiones:** ninguno — refuerza el hallazgo. No es un caso de significancia estadística con efecto trivial.

**Remediación sugerida:** ninguna acción requerida. Sugerido incorporar el épsilon-cuadrado como métrica reportada de forma explícita en `reports/analisis_A_previsibilidad.md`, no solo en esta auditoría.

---

### D.4 — Robustez del modelo OLS (multicolinealidad)
**Severidad:** 🔵 **OBSERVACIÓN**

**Descripción:** el VIF (factor de inflación de varianza) del modelo multivariado ya fue calculado, reportado y marcado con advertencia explícita por el propio proyecto, no por esta auditoría.

**Evidencia:** `reports/robustez_multivariado.md`, sección "Multicolinealidad (VIF)" — 5 de 12 predictores con VIF>5, con advertencia textual sobre interpretar esos coeficientes con cautela.

**Impacto en conclusiones:** ninguno adicional al ya reconocido por el propio proyecto.

**Remediación sugerida:** ninguna acción requerida — buena práctica ya aplicada.

---

### D.5 — Poder estadístico de los hallazgos negativos (ausencia de diferencia)
**Severidad:** — **SIN HALLAZGO** (observación menor)

**Descripción:** varios hallazgos del proyecto son de **ausencia** de diferencia (persistencia GARCH no difiere por indicador ni por ingreso, Análisis B/C) — vale la pena confirmar que no es simplemente falta de poder estadístico por muestras chicas.

**Evidencia (recalculada sobre `resultados_enriquecidos.parquet`, series con GARCH convergido):** hcpi n=172, ecpi n=151, fcpi n=131, ppi n=93, ccpi n=79. La mayoría de los grupos supera ampliamente n=100; `ccpi` (79) y `ppi` (93) son los más chicos, algo por debajo de 100 pero no drásticamente.

**Impacto en conclusiones:** ninguno — el tamaño muestral es razonable en la mayoría de los grupos comparados; la ausencia de diferencia reportada es creíble como hallazgo genuino, no como artefacto de poder insuficiente, aunque `ccpi` es el grupo donde más cautela amerita.

**Remediación sugerida:** ninguna acción requerida. Opcionalmente, reportar el poder estadístico ex-post (no solo el n) la próxima vez que se destaque un hallazgo de ausencia de diferencia sobre el grupo `ccpi` específicamente.

---

## FASE E — Reproducibilidad

### E.1 — Reproducibilidad end-to-end en limpio
**Severidad:** — **SIN HALLAZGO** (fortaleza, verificada con evidencia más fuerte que la ya publicada)

**Descripción:** `README.md` ya afirmaba reproducibilidad byte a byte, pero esa verificación previa corrió `run_pipeline.py` **en el mismo checkout y el mismo entorno** que generó los resultados originales — no probaba que un tercero, clonando el repositorio de cero, pudiera reproducirlo. Para esta auditoría se ejecutó la prueba más exigente: clon real desde GitHub a un directorio nuevo, entorno virtual nuevo instalado desde `requirements.txt`, y borrado explícito de `data/raw/Inflation-data.xlsx` y de todos los `data/processed/*.parquet` **antes** de correr — forzando que incluso la descarga por red se ejecute de nuevo, no solo el cómputo.

**Evidencia:**
- Clon: `git clone https://github.com/MLEIV90/global-inflation-arima-garch.git` — exitoso, HEAD en `4535462` (último commit de la auditoría al momento de la prueba).
- Entorno: `python -m venv` nuevo + `pip install -r requirements.txt` — **3m 27s**, sin errores; las 12 dependencias directas (`pandas, numpy, statsmodels, pmdarima, arch, joblib, scipy, openpyxl, matplotlib, seaborn, requests, pycountry`) importan correctamente.
- Ejecución: `python run_pipeline.py` sobre el repo con `data/raw/` y `data/processed/` vacíos — **9/9 pasos OK, 17.0 minutos** (1019.5s), incluida la re-descarga real del Excel del Banco Mundial por red, sin ninguna intervención manual.
- Comparación (`git status --short` dentro del clon limpio, después de la corrida): de **todos** los archivos que `run_pipeline.py` regenera — 5 parquets, 8 informes `.md`, todas las figuras `.png` de esos 8 informes — **cero diferencias**. Coincidencia byte a byte total.

**Impacto en conclusiones:** ninguno — refuerza, con evidencia más rigurosa, la afirmación de reproducibilidad ya publicada en `README.md`.

**Remediación sugerida:** ninguna acción requerida sobre el pipeline en sí. Sugerido: actualizar la nota de reproducibilidad de `README.md` para aclarar que la verificación original fue in-place y que esta (E.1) es la primera verificación desde un clon externo genuino, con el tiempo real (17.0 min, no 15.0 — la diferencia es esperable por variación de carga de red/CPU entre corridas, no una inconsistencia).

---

### E.4 — Pasos manuales ocultos / cobertura real de `run_pipeline.py`
**Severidad:** 🟡 **MENOR**

**Descripción:** se evaluó si `run_pipeline.py` cubre todo el flujo reproducible del proyecto con un solo comando, o si hay pasos que un tercero necesitaría conocer sin que estén documentados.

**Evidencia:**

1. **Los 5 scripts de diagnóstico (`fase1_*.py`…`fase5_*.py`) no son una dependencia oculta** — se confirmó por lectura de código que `src/05_etl_corregido.py` (el primer paso real del pipeline) no lee ningún archivo producido por esos 5 scripts; trabaja directo desde `data/raw/Inflation-data.xlsx`. Excluirlos de `run_pipeline.py` no rompe nada — es una exclusión segura, ya documentada en el propio `run_pipeline.py` y en `README.md`.

2. **Dos artefactos versionados quedan huérfanos y `run_pipeline.py` no los regenera** — confirmado empíricamente (no solo por lectura de código) en la corrida de E.1: tras borrar todo `data/processed/` y correr el pipeline completo, `git status` mostró **`data/processed/calidad_series.parquet`** y **`data/processed/resultados_modelos.parquet`** como *eliminados*, no *modificados* — es decir, ningún paso de `run_pipeline.py` los vuelve a crear. Son producidos por `src/02_calidad_series.py` y `src/06_modelado_arima_garch.py` (la versión original de modelado, pre-walk-forward) respectivamente — ambos scripts deliberadamente fuera del pipeline por estar superados (documentado en `README.md`), pero sus **outputs siguen versionados en git** como si fueran vigentes. No se usan en ningún paso posterior, así que el impacto es bajo, pero un tercero que abra `calidad_series.parquet` esperando que refleje la lógica de calidad actual del proyecto encontraría un artefacto congelado en una versión temprana del ETL.

3. **`notebooks/informe_completo.ipynb` no está en `run_pipeline.py` ni el comando para regenerarlo está documentado.** El notebook lee los parquets/figuras que sí genera el pipeline, así que su *contenido de código* nunca queda desactualizado — pero sus **outputs ejecutados** (las celdas ya corridas, las figuras embebidas) sólo se actualizan corriendo manualmente `jupyter nbconvert --to notebook --execute --inplace notebooks/informe_completo.ipynb`. Ese comando no aparece en `README.md` (que solo linkea al notebook, sección "Resumen ejecutivo") ni en la sección "Cómo reproducir". Un tercero que corra `run_pipeline.py` y luego mire el notebook está viendo outputs de una ejecución anterior, sin ninguna indicación de que hace falta un paso extra si quiere refrescarlos.

4. **`reports/auditoria_integral.md` (este documento) no es reproducible por script** — es narrativa auditada manualmente, con recálculos puntuales ad-hoc para cada hallazgo. Esto es una decisión de diseño razonable (no todo documento de un proyecto tiene que ser un script), pero significa que la respuesta a "¿se reproduce todo con un comando?" es distinta según qué carpeta de `reports/` se mire.

**Respuesta directa a la pregunta de la auditoría:** un tercero que clona el repo y corre `python run_pipeline.py` reproduce **correctamente y por completo** el pipeline cuantitativo (los 5 parquets vigentes + los 8 informes de análisis/auditoría/robustez con sus figuras — confirmado en E.1). **No** reproduce, sin un paso adicional no documentado, los outputs del notebook narrativo. Los 2 artefactos huérfanos (`calidad_series.parquet`, `resultados_modelos.parquet`) quedan tal como estén en el checkout de git, sin indicación de que están congelados.

**Impacto en conclusiones:** ninguno sobre los resultados analíticos ya publicados. El impacto es sobre la experiencia de un tercero tratando de entender qué está vigente y qué no en `data/processed/` y en `reports/`.

**Remediación sugerida (no implementar en esta fase):**
- Agregar a `README.md` el comando de regeneración del notebook, o incorporarlo como paso opcional final de `run_pipeline.py`.
- Eliminar del control de versiones (o mover a una carpeta `legacy/` explícita) `calidad_series.parquet` y `resultados_modelos.parquet`, ya que ningún script los regenera y no se usan en ningún paso posterior — mantenerlos en `data/processed/` junto a los artefactos vigentes invita a confundirlos con datos actuales.

---

### E.2 — Cobertura de dependencias
**Severidad:** — **SIN HALLAZGO** (observación menor)

**Descripción:** se verificó que `requirements.txt` cubra todos los imports usados en `src/*.py` y `run_pipeline.py`.

**Evidencia:** **121 paquetes** con versión fijada **[precisión ajustada en verificación; reportado originalmente: "130+"]**, incluyendo todas las dependencias directas (`pandas`, `numpy`, `statsmodels`, `pmdarima`, `arch`, `joblib`, `scipy`, `openpyxl`, `matplotlib`, `seaborn`, `requests`, `pycountry`) y el árbol completo de Jupyter (agregado para `notebooks/informe_completo.ipynb`). Es un `pip freeze` completo del entorno, no un listado mínimo de dependencias directas — funciona para reproducibilidad exacta pero es más pesado de lo estrictamente necesario para correr solo el pipeline (sin el notebook).

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** opcionalmente, separar `requirements.txt` (mínimo, pipeline) de un `requirements-notebook.txt` o `requirements-dev.txt` (Jupyter y afines), si en algún momento importa minimizar el entorno de producción.

---

### E.3 — Rutas hardcodeadas
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se buscaron rutas absolutas hardcodeadas (Windows o Unix) en todo `src/*.py` y `run_pipeline.py`.

**Evidencia:** cero coincidencias fuera del patrón dinámico `Path(__file__).resolve().parents[1]`, usado consistentemente en los 15 scripts para derivar la raíz del proyecto en tiempo de ejecución. El pipeline es portable entre máquinas/sistemas operativos sin edición manual de rutas.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ninguna acción requerida.

---

## FASE F — Documentación

### F.1 — Consistencia numérica README ↔ resultados: cifra de Venezuela
**Severidad:** — **SIN HALLAZGO** *(no confirmado en verificación — ver nota)*

**Descripción:** se verificó puntualmente la cifra de Venezuela PPI citada como ejemplo del contraste `pct_change` vs. `log-diff`.

**Evidencia:** `README.md` línea 65 dice textualmente *"el mismo evento real en Venezuela midió **344.272%** en `pct_change` contra **814%** en `log-diff`"* — el número completo, no truncado. `notebooks/informe_completo.ipynb` (celda de Fase 4) dice lo mismo: **344.272%**. Búsqueda de la cadena `"272%"` en ambos archivos: una sola coincidencia en cada uno, en los dos casos como parte de `344.272%`, no como un valor `272%` aislado.

**Nota de verificación:** el hallazgo tal como fue reportado originalmente ("el README menciona 272%, truncamiento accidental de 344") **no se confirma** — no existe esa cadena de texto en el repo actual. Es posible que se haya corregido entre el momento en que se detectó y esta verificación, o que la observación original haya sido un error de lectura. Se documenta como "sin hallazgo" en vez de omitirlo silenciosamente, para que quede trazable que sí se buscó y no se encontró.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ninguna acción requerida.

---

### F.2 — Afirmaciones del README contra evidencia recalculada
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se extrajeron programáticamente todas las cifras estadísticas citadas en `README.md` (p-valores, ρ, R², n) y se contrastaron contra los valores ya verificados de forma independiente en las Fases A-E de esta misma auditoría y en los informes de Análisis A/B/C.

**Evidencia:** `R²=0.315`, `n=171/76/57`, y los 7 p-valores citados (5.6×10⁻⁷, 3.3×10⁻⁹, 5.8×10⁻¹¹, 3.4×10⁻¹², 3.9×10⁻³⁰, 7.9×10⁻⁶, 2.3×10⁻⁶) coinciden exactos con los valores ya confirmados en Fases A-D de esta auditoría.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ninguna acción requerida.

---

### F.3 — Completitud de la sección de limitaciones
**Severidad:** 🟡 **MENOR**

**Descripción:** la sección "Limitaciones honestas" de `README.md` es sustancialmente más completa que lo habitual en un proyecto de este tipo (declara panel no balanceado, series sin GARCH, un solo tipo de modelo, estacionalidad no explotada, incertidumbre del ranking) — pero fue escrita antes de que existiera esta auditoría integral, así que no incluye los hallazgos SIGNIFICATIVO que la propia auditoría encontró después.

**Evidencia (`README.md`, sección "Limitaciones honestas", verificada línea por línea):**
- **No menciona C.2** (81% de series con residuos ARIMA autocorrelacionados, GARCH ajustado encima sin filtrar).
- **No menciona C.5** (el único benchmark de comparación es random walk, sin media móvil de 12 meses).
- **Menciona el criterio de huecos, pero solo para GARCH** ("el piso de 100 meses sin huecos internos que exige `apto_garch`") — no aclara que la misma regla aplica a `apto_arima`, ni cuantifica que 27 series con cobertura sustancial (61-616 meses) quedan excluidas por esta razón (A.3/B.1).

**Impacto en conclusiones:** ninguno — es una brecha de completitud documental, no de validez de lo ya calculado.

**Remediación sugerida:** ampliar la sección de limitaciones con estos tres puntos, idealmente en conjunto con (no necesariamente después de) la remediación de C.2/C.5/B.1, para que la documentación quede sincronizada con el estado real del proyecto.

---

### F.4 — Claridad para la audiencia
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se evaluó si la documentación sirve tanto a un lector técnico (recruiter/ingeniero) como a uno con formación económica pero no necesariamente técnica.

**Evidencia:** `README.md` funciona como resumen ejecutivo denso pero legible; `notebooks/informe_completo.ipynb` provee el recorrido narrativo completo con explicaciones accesibles de ARIMA/GARCH y ejemplos visuales antes de cada hallazgo cuantitativo. La combinación de ambos documentos, con roles explícitamente diferenciados (el propio README lo aclara: *"Este README es el resumen de vitrina... el recorrido narrativo completo... está en el notebook"*), cubre razonablemente ambas audiencias sin que ninguna quede desatendida.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ninguna acción requerida.

---

## FASE G — Posicionamiento del Proyecto

### G.1 — Consistencia con la literatura profesional
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se evaluó si el hallazgo central del proyecto (previsibilidad de la inflación ligada a estabilidad/nivel de ingreso) es consistente con, contradice, o reclama indebidamente novedad frente a la literatura de pronóstico de inflación ya establecida.

**Evidencia:** el hallazgo es consistente con Pincheira & Medel, *"The Elusive Predictive Ability of Global Inflation"*, y con Atkeson & Ohanian (2001) — ya citado explícitamente en `README.md` (sección "Trabajo futuro") y usado como referencia en el hallazgo C.5 de esta misma auditoría. El proyecto replica un patrón ya documentado en la literatura, sobre un panel más amplio (188 países) y con un proceso más transparente (código y datos públicos, auto-auditoría), sin contradecir el estado del arte ni reclamar un hallazgo original que no lo sea.

**Impacto en conclusiones:** ninguno — refuerza la credibilidad del hallazgo central al situarlo dentro de un cuerpo de evidencia previo, no en aislamiento.

**Remediación sugerida:** ninguna acción requerida sobre el hallazgo en sí (ver G.2 para una mejora de presentación relacionada).

---

### G.2 — Originalidad reclamada vs. aporte real
**Severidad:** 🔵 **OBSERVACIÓN**

**Descripción:** el proyecto no reclama originalidad metodológica (ARIMA/GARCH son técnicas estándar, declaradas como tales) — su aporte real es la combinación de escala multi-país, transparencia de proceso de punta a punta, y auto-auditoría metodológica, que sí está bien delimitada y no se sobre-vende en ningún documento del repo.

**Evidencia:** `README.md` no usa lenguaje de "primero en" o "novedoso"; encuadra el proyecto explícitamente como una pregunta aplicada sobre un método conocido. No existe, sin embargo, una sección que compare explícitamente el proyecto contra la literatura citada (Pincheira/Medel, Atkeson-Ohanian) — la conexión existe (ver G.1) pero está repartida entre "Trabajo futuro" y esta auditoría, no consolidada en un solo lugar visible para un lector académico.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** agregar una sección breve "Trabajos relacionados" en `README.md` o el notebook, situando explícitamente el proyecto frente a Pincheira/Medel y Atkeson-Ohanian — mejora de percepción de rigor académico, no una corrección de fondo.

---

### G.3 — Riesgo de sobre-afirmación
**Severidad:** — **SIN HALLAZGO**

**Descripción:** se evaluó si el tono del `README.md` reclama más de lo que la evidencia del proyecto sostiene.

**Evidencia:** el documento encuadra la pregunta de investigación con humildad explícita (*"el objetivo no es predecir la inflación"*), califica el hallazgo central con precisión (*"sobrevive a cuatro intentos independientes de tirarlo abajo"*, no "está probado" sin matices), declara abiertamente la incertidumbre del ranking país-a-país como una limitación central del propio hallazgo insignia (hallazgo 5), y presenta la decisión de ingeniería `joblib` vs. PySpark con su justificación cuantitativa, sin lenguaje promocional. No se encontró ninguna afirmación en `README.md` o el notebook que no esté respaldada por un informe o recálculo verificable.

**Impacto en conclusiones:** ninguno.

**Remediación sugerida:** ninguna acción requerida — mantener este estándar de tono en futuras actualizaciones de la documentación.

---

## Matriz resumen de hallazgos

| ID | Fase | Descripción breve | Severidad | Verificación |
|---|---|---|---|---|
| A.1 | Datos | Trazabilidad fuente→resultado | Sin hallazgo | Confirmado exacto |
| A.2 | Datos | Fórmula log-diff | Sin hallazgo | Confirmado exacto |
| A.3 | Datos | 27 series con cobertura sustancial excluidas por 1+ hueco | 🟠 Significativo | Cifras corregidas en verificación |
| A.5 | Datos | Validación externa vs. tasa oficial | 🔵 Observación | Confirmado, consistente con Fase 4 |
| A.6 | Datos | Heurística de deduplicación sacrifica actualidad | 🟡 Menor | Ejemplo MOZ corregido en verificación |
| B.1 | Código | Criterio de aptitud exige cero huecos absolutos (causa raíz de A.3) | 🟠 Significativo | Líneas de código confirmadas exactas |
| B.2 | Código | Data leakage en walk-forward | Sin hallazgo | Confirmado exacto |
| B.3 | Código | Determinismo y semillas | Sin hallazgo | Confirmado exacto |
| B.5 | Código | Consistencia de parámetros código↔documentación | 🔵 Observación | Matiz agregado en verificación |
| C.1 | Metodología | Transformación log-diff sin test de sensibilidad | 🔵 Observación | Confirmado, ya defendido con evidencia |
| C.2 | Metodología | ARIMA con residuos autocorrelacionados propagado a GARCH sin filtrar | 🟠 Significativo | Confirmado exacto (520/640, 519, p=4.36e-29) |
| C.3 | Metodología | GARCH(1,1) sin variantes asimétricas | 🔵 Observación | Confirmado, ya declarado en README |
| C.4 | Metodología | Re-estimación cada 6 pasos, no cada mes | 🔵 Observación | Confirmado, ya acotado por auditoría previa |
| C.5 | Metodología | Baseline random walk, no media móvil 12m (Atkeson-Ohanian) | 🟠 Significativo | Confirmado — único benchmark en el código |
| C.6 | Metodología | Tratamiento de huecos — ver B.1 | — | Referencia cruzada |
| D.1 | Estadística | Supuestos de tests no-paramétricos | 🔵 Observación | Confirmado, buena práctica ya aplicada |
| D.2 | Estadística | Multiplicidad de tests (Bonferroni) | Sin hallazgo (fortaleza) | Confirmado, con matiz sobre coeficiente OLS p=0.017 |
| D.3 | Estadística | Tamaño de efecto del gradiente de ingreso | Sin hallazgo (fortaleza) | ε²=0.17 confirmado; ratio corregido a 3.16× |
| D.4 | Estadística | Robustez OLS (VIF) | 🔵 Observación | Confirmado, ya reportado por el proyecto |
| D.5 | Estadística | Poder estadístico de hallazgos negativos | Sin hallazgo (menor) | Confirmado (n=79-172 según indicador) |
| E.1 | Reproducibilidad | Reproducibilidad end-to-end desde clon limpio | Sin hallazgo (fortaleza) | Ejecutado de cero: 9/9 pasos OK, 17.0 min, 0 diferencias |
| E.2 | Reproducibilidad | Cobertura de dependencias | Sin hallazgo (menor) | Confirmado, cantidad corregida a 121 |
| E.3 | Reproducibilidad | Rutas hardcodeadas | Sin hallazgo | Confirmado, cero coincidencias |
| E.4 | Reproducibilidad | Notebook y 2 artefactos legacy no cubiertos por `run_pipeline.py` | 🟡 Menor | Confirmado empíricamente (git status tras corrida limpia) |
| F.1 | Documentación | Cifra de Venezuela ("272%" truncado) | Sin hallazgo | No se confirmó — el README ya dice 344.272% |
| F.2 | Documentación | Afirmaciones del README vs. evidencia recalculada | Sin hallazgo | Los 7 p-valores + R² + n citados, exactos |
| F.3 | Documentación | Limitaciones no incluyen hallazgos de esta auditoría | 🟡 Menor | Confirmado — C.2, C.5 y alcance de B.1 ausentes |
| F.4 | Documentación | Claridad para audiencia técnica y económica | Sin hallazgo | Confirmado — README + notebook con roles diferenciados |
| G.1 | Posicionamiento | Consistencia con literatura (Pincheira/Medel, Atkeson-Ohanian) | Sin hallazgo | Confirmado, ya citado en README y en C.5 |
| G.2 | Posicionamiento | Originalidad reclamada vs. aporte real | 🔵 Observación | Bien delimitado; falta sección "Trabajos relacionados" |
| G.3 | Posicionamiento | Riesgo de sobre-afirmación en el tono | Sin hallazgo | Confirmado — tono medido, sin lenguaje promocional |

**Totales por severidad (Fases A-G, auditoría completa):** 🟠 Significativo: 4 (A.3, B.1 —mismo problema raíz—, C.2, C.5) · 🟡 Menor: 3 (A.6, E.4, F.3) · 🔵 Observación: 8 (A.5, B.5, C.1, C.3, C.4, D.1, D.4, G.2) · Sin hallazgo (fortaleza/confirmado/no-confirmado): 15 (A.1, A.2, B.2, B.3, D.2, D.3, D.5, E.1, E.2, E.3, F.1, F.2, F.4, G.1, G.3).

**Total de puntos de control evaluados: 30** (4+3+8+15; no incluye C.6, referencia cruzada a B.1 sin severidad propia).

---

## Dictamen final

**Opinión: favorable, con observaciones.**

Sobre las 7 fases evaluadas (A-G) y los 30 puntos de control examinados: **cero hallazgos críticos**. Ningún hallazgo de esta auditoría invalida, revierte o pone en duda la validez de un resultado ya publicado en `reports/analisis_A_previsibilidad.md`, `analisis_B_estructura.md`, `analisis_C_volatilidad.md`, `auditoria_metodologica.md` o `robustez_multivariado.md`. El hallazgo insignia del proyecto —el gradiente de previsibilidad por nivel de ingreso— fue puesto a prueba de forma independiente en esta auditoría (D.2, D.3) y se sostiene: efecto grande (ε²=0.17), estadísticamente robusto ante corrección por multiplicidad, y no explicado por longitud de serie.

Se identificaron **4 hallazgos SIGNIFICATIVO**, todos remediables y ninguno retroactivo:

1. **A.3 / B.1** (mismo problema raíz) — el criterio de aptitud exige cero huecos internos absolutos, excluyendo 27 series con cobertura sustancial (61-616 meses) del panel modelado, sin que el alcance real de esta exclusión esté documentado.
2. **C.2** — el 81% de los ARIMA convergidos tienen residuos con autocorrelación remanente, y GARCH se ajusta sobre ellos sin filtrar ni marcar la fracción afectada.
3. **C.5** — el único benchmark de comparación es random walk puro; la literatura sugiere que un benchmark de media móvil sería más exigente y más apropiado para inflación específicamente.

Ninguno de los tres remedia con un cambio trivial de una línea — los tres requieren una decisión de diseño (qué hacer con las series excluidas, si filtrar o no antes de GARCH, si agregar un segundo benchmark) que corresponde a una fase correctiva posterior, explícitamente fuera de alcance de esta auditoría.

El resto de los hallazgos —3 MENOR (A.6, E.4, F.3) y 8 OBSERVACIÓN— son imprecisiones de documentación o mejoras de presentación sin impacto en la validez de las conclusiones. Un hecho notable de esta auditoría, sobre su propio proceso: a lo largo de las 7 fases, 6 puntos de control requirieron corrección de precisión respecto al brief original en el que se basaron (el reparto interno y los ejemplos de A.3, el ejemplo de Mozambique en A.6, el matiz de B.5, el ratio de D.3, la cantidad de paquetes de E.2) y uno (F.1) **no se confirmó en absoluto** al re-verificar contra el estado actual del repositorio. Ninguna de estas correcciones cambió la conclusión de ningún hallazgo. Esto es consistente con el estándar aplicado durante toda la auditoría: cada cifra citada en este documento fue recalculada o releída de la fuente antes de publicarse, no transcrita de un brief sin control cruzado.

**Reproducibilidad (E.1)** se verificó con el estándar más exigente disponible — clon externo desde GitHub, entorno virtual nuevo, re-descarga de datos por red — y resultó perfecta: 9/9 pasos, reproducción byte a byte de cada resultado cuantitativo publicado.

**Recomendación:** el proyecto puede presentarse como está, citando esta auditoría como evidencia de rigor y auto-crítica documentada. Se recomienda una fase correctiva que aborde los 4 hallazgos SIGNIFICATIVO antes de cualquier extensión del alcance del proyecto (más países, más indicadores, nuevos modelos), para no propagar el mismo criterio de exclusión de huecos o la misma falta de filtro pre-GARCH a un panel más grande.
