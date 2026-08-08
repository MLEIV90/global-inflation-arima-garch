# Auditoría Integral — Proyecto Global Inflation ARIMA-GARCH

## Estándar: revisión independiente tipo Big Four

**Fecha:** 2026-08-08
**Alcance:** integridad de datos, revisión de código, metodología, validez estadística, reproducibilidad, documentación, posicionamiento del proyecto.
**Naturaleza:** auditoría puramente diagnóstica. Ningún hallazgo de este documento fue remediado — la remediación queda para una fase correctiva posterior, explícitamente fuera de alcance acá.

**Nota de verificación:** cada hallazgo listado abajo fue re-verificado de forma independiente (releyendo el código citado, o recalculando la cifra desde `data/raw/Inflation-data.xlsx` / los parquets procesados) antes de incorporarlo a este documento. En cuatro puntos la verificación encontró una cifra distinta a la reportada originalmente; en esos casos se indica explícitamente **[cifra corregida en verificación]** con el valor original entre paréntesis, para que quede trazable qué cambió y por qué. El resto de los hallazgos verificó exacto.

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

*(pendiente — no evaluada en esta ronda de auditoría)*

## FASE D — Validez Estadística

*(pendiente — no evaluada en esta ronda de auditoría)*

## FASE E — Reproducibilidad

*(pendiente — no evaluada en esta ronda de auditoría)*

## FASE F — Documentación

*(pendiente — no evaluada en esta ronda de auditoría)*

## FASE G — Posicionamiento del Proyecto

*(pendiente — no evaluada en esta ronda de auditoría)*

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

**Totales por severidad:** 🟠 Significativo: 2 (A.3, B.1 — mismo problema raíz, contado dos veces por afectar tanto datos como código) · 🟡 Menor: 1 · 🔵 Observación: 2 · Sin hallazgo: 4.

**Ningún hallazgo de esta ronda es CRÍTICO** — ninguno invalida un resultado ya publicado en `reports/analisis_A/B/C`, `auditoria_metodologica.md` o `robustez_multivariado.md`. El hallazgo de mayor severidad (A.3/B.1) es sobre **alcance no documentado**, no sobre corrección de lo ya calculado.
