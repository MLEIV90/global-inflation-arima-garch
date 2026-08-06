# Fase 3 — Cobertura temporal y huecos a nivel de datos

Informe generado por `src/fase3_cobertura_temporal.py`, trabajando directo sobre el índice crudo de las 5 hojas mensuales de `data/raw/Inflation-data.xlsx` (no sobre el YoY del parquet actual — ver Fase 1 sobre por qué ese cálculo todavía no es válido para todas las filas). **Solo diagnóstico: no se corrige ningún dato.**

## Exclusiones aplicadas antes del análisis

Se excluyeron **4 series** ya identificadas como problemáticas en Fases 1-2, para que no contaminen las métricas de cobertura (su 'cobertura' no sería comparable con la de un índice real):

- `ecpi_m` / IND: Fase 1: Indicator Type='Inflation', ya es tasa, no índice
- `ecpi_m` / IDN: Fase 1: Indicator Type='Inflation', ya es tasa, no índice
- `ecpi_m` / VEN: Fase 2: índice en 0.0 exacto ~60 meses, probable placeholder de dato faltante
- `fcpi_m` / VEN: Fase 2: índice en 0.0 exacto ~51 meses, probable placeholder de dato faltante

Además, **12 filas** de país no tienen NINGÚN valor de índice en toda la hoja (no es un hueco, es ausencia total de dato) — se excluyen del panel de cobertura por no tener span que medir, y quedan documentadas para la fase de corrección (candidatas a eliminarse directamente del ETL, no a rescatarse con imputación).

Los duplicados detectados en Fase 2 (36 país-hoja) se resolvieron acá igual que en `01_descarga_datos.py`: se conserva la fila con más puntos válidos por `Country Code`.

## 1-2. Cobertura y clasificación por serie (672 series analizadas)

Por cada serie se calculó: primer/último mes con dato, `span` (meses entre el primero y el último inclusive), `meses_con_dato` (conteo real de datos válidos en ese span), `densidad = meses_con_dato / span`, y los huecos internos (tramos de meses faltantes estrictamente dentro del span, sin contar el arranque tardío ni el final).

**Reglas de clasificación** (heurística documentada, no absoluta):

- **completa**: 0 huecos internos y arranca en 197501 o antes (primeros 5 años del panel).
- **arranque tardío**: 0 huecos internos pero arranca después de 197501.
- **con huecos internos**: 1 o 2 tramos faltantes dentro del span.
- **fragmentada**: 3 o más tramos faltantes dentro del span.

| Hoja | completa | arranque tardío | con huecos internos | fragmentada | Total |
|---|---|---|---|---|---|
| hcpi_m | 32 | 145 | 6 | 1 | 184 |
| ecpi_m | 16 | 140 | 7 | 2 | 165 |
| fcpi_m | 22 | 112 | 5 | 3 | 142 |
| ccpi_m | 17 | 63 | 0 | 0 | 80 |
| ppi_m | 18 | 78 | 2 | 3 | 101 |

## 3. Distribución de longitud de serie por indicador

Histograma guardado en `reports/figures/fase3_distribucion_longitud_por_indicador.png` — un panel por indicador (no agregado, para no mezclar la cobertura de hcpi con la de ccpi, que sistemáticamente tiene menos países reportando).

Percentiles de `meses_con_dato` por hoja:

| Hoja | n | media | min | p10 | p25 | mediana | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|---|
| hcpi_m | 184 | 319 | 29 | 177 | 183 | 242 | 364 | 663 | 663 |
| ecpi_m | 165 | 290 | 44 | 131 | 182 | 243 | 339 | 596 | 663 |
| fcpi_m | 142 | 317 | 44 | 136 | 193 | 243 | 372 | 663 | 663 |
| ccpi_m | 80 | 376 | 31 | 165 | 230 | 351 | 563 | 663 | 663 |
| ppi_m | 101 | 341 | 31 | 132 | 194 | 302 | 471 | 642 | 662 |

## 4. Series aptas por piso mínimo

Piso ARIMA sugerido: **60 meses** (5 años). Piso GARCH sugerido: **100 meses** (~8.3 años, GARCH necesita más historia para estimar la volatilidad de forma estable). Conteo de series con `meses_con_dato >=` cada piso, por hoja — es un conteo simple por cantidad de dato, todavía sin filtrar por huecos internos (eso se cruza en la sección 6).

| Hoja | Total series | ≥60 (ARIMA) | ≥100 (GARCH) |
|---|---|---|---|
| hcpi_m | 184 | 182 | 178 |
| ecpi_m | 165 | 162 | 157 |
| fcpi_m | 142 | 141 | 138 |
| ccpi_m | 80 | 79 | 79 |
| ppi_m | 101 | 99 | 98 |

## 5. Huecos internos: ¿cuántas series quedan comprometidas?

**29** de 672 series tienen al menos un hueco interno. De esas, **6** tienen un tramo faltante de 6 meses o más ("hueco grave" — inviable para imputación simple, requeriría segmentar la serie o descartar el tramo previo al hueco).

Las 15 series con el hueco interno más largo:

| Hoja | Código | País | N° huecos | Meses faltantes (total) | Hueco más largo | Detalle |
|---|---|---|---|---|---|---|
| ppi_m | CAF | Central African Republic | 3 | 40 | 29 | 198804–198812 (9m); 199211–199212 (2m); 199408–199612 (29m) |
| ecpi_m | PER | Peru | 1 | 22 | 22 | 202003–202112 (22m) |
| hcpi_m | RUS | Russian Federation | 2 | 30 | 16 | 202204–202307 (16m); 202309–202410 (14m) |
| ecpi_m | BHS | Bahamas | 3 | 16 | 12 | 201401–201401 (1m); 201601–201612 (12m); 201710–201712 (3m) |
| hcpi_m | YEM | Yemen, Rep. | 1 | 11 | 11 | 201501–201511 (11m) |
| ppi_m | THA | Thailand | 1 | 7 | 7 | 202007–202101 (7m) |
| ppi_m | COG | Congo, Rep. | 3 | 8 | 5 | 197705–197709 (5m); 198704–198705 (2m); 198707–198707 (1m) |
| ppi_m | MNE | Montenegro | 3 | 12 | 4 | 201801–201804 (4m); 201901–201904 (4m); 202001–202004 (4m) |
| ecpi_m | COG | Congo, Rep. | 1 | 4 | 4 | 201809–201812 (4m) |
| fcpi_m | COG | Congo, Rep. | 1 | 4 | 4 | 201809–201812 (4m) |
| hcpi_m | GNB | Guinea-Bissau | 1 | 3 | 3 | 202305–202307 (3m) |
| ecpi_m | GNB | Guinea-Bissau | 1 | 3 | 3 | 202305–202307 (3m) |
| fcpi_m | GNB | Guinea-Bissau | 1 | 3 | 3 | 202305–202307 (3m) |
| ppi_m | ALB | Albania | 1 | 3 | 3 | 201207–201209 (3m) |
| ecpi_m | BLZ | Belize | 81 | 162 | 2 | 199012–199101 (2m); 199103–199104 (2m); 199106–199107 (2m); 199109–199110 (2m) ... y 77 más |

**Hallazgo específico — desfasaje de frecuencia, no huecos aleatorios:** algunas series marcadas como 'fragmentadas' no tienen datos faltantes al azar, sino un patrón perfectamente regular (10+ tramos faltantes, todos de 1-2 meses) — son series que en realidad se reportan trimestralmente pero están cargadas en la hoja mensual:

- `hcpi_m` / BLZ (Belize): 81 tramos, todos ≤2 meses
- `ecpi_m` / BLZ (Belize): 81 tramos, todos ≤2 meses
- `fcpi_m` / BLZ (Belize): 81 tramos, todos ≤2 meses
- `fcpi_m` / IRL (Ireland): 23 tramos, todos ≤2 meses
- `fcpi_m` / ISL (Iceland): 54 tramos, todos ≤2 meses

Para estas series, "imputar los huecos" no es el tratamiento correcto — lo correcto es re-muestrear la serie a frecuencia trimestral real antes de modelar, no forzarla a mensual. Queda para la fase de corrección decidir si se excluyen del panel mensual o se tratan aparte.

## 6. Tabla resumen: series efectivamente modelables por indicador

Una serie se considera **modelable sin tratamiento adicional** si no tiene ningún hueco interno (clasificación 'completa' o 'arranque tardío') Y `meses_con_dato` alcanza el piso correspondiente. Series con huecos internos podrían rescatarse más adelante con interpolación/segmentación, pero eso es una decisión de la fase de corrección, no de este diagnóstico.

| Indicador | Series totales* | Modelables ARIMA (≥60m, sin huecos) | Modelables GARCH (≥100m, sin huecos) | Caen por span corto | Caen por huecos internos |
|---|---|---|---|---|---|
| hcpi_m | 184 | 175 | 172 | 2 | 7 |
| ecpi_m | 165 | 154 | 149 | 2 | 9 |
| fcpi_m | 142 | 134 | 131 | 0 | 8 |
| ccpi_m | 80 | 79 | 79 | 1 | 0 |
| ppi_m | 101 | 94 | 93 | 2 | 5 |

\* Series totales = después de excluir las 4 ya conocidas como problemáticas (Fases 1-2) y las 12 sin ningún dato de índice.

## Conclusión: conteo realista de series modelables

Sumando las 5 hojas mensuales: **636 series país×indicador son modelables para ARIMA** (span ≥60 meses, sin huecos internos) y **624 para GARCH** (span ≥100 meses, sin huecos internos), de un universo de 672 series con al menos algo de dato (688 filas de país en las 5 hojas originales). La brecha entre ARIMA y GARCH refleja que GARCH necesita bastante más historia para estimar volatilidad de forma estable — varios países con series cortas o con huecos van a quedar aptos para uno pero no para el otro. Esto es más estricto que el piso de 36 puntos usado en `02_calidad_series.py` (que medía puntos válidos de YoY, no meses de índice sin huecos) — la diferencia es esperable: acá se exige además la ausencia de huecos internos, que ese chequeo anterior no contemplaba.
