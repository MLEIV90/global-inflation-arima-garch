# Bitácora de decisiones — Previsibilidad y volatilidad de la inflación global

Este documento consolida el razonamiento de alto nivel del proyecto: qué se
decidió, por qué, y con qué evidencia. Los detalles técnicos de cada
hallazgo están en los informes de fase (`reports/faseN_*.md`); acá va el
"por qué" que los conecta.

---

## Parte A — Bitácora del proceso

### 1. Objetivo del proyecto

Analizar previsibilidad (ARIMA) y volatilidad (GARCH) de la inflación en
~180 países usando datos **mensuales** del Banco Mundial (Global Database of
Inflation), en paralelo con `joblib`.

¿Por qué multi-país y no un solo país en profundidad? Porque el objeto de
estudio interesante acá no es "cuánta inflación tuvo el país X", sino **cómo
varía la previsibilidad y la volatilidad de la inflación según el régimen
del país** — economías con inflación baja y estable (ej. Alemania, Suiza)
deberían ser mucho más previsibles con ARIMA y mucho menos volátiles en
GARCH que economías con historial de crisis (Argentina, Venezuela, Turquía).
Un panel de ~680 series país×indicador es lo que permite esa comparación
sistemática en vez de anecdótica, y es a la vez chico como para correr en
una notebook y grande como para justificar un pipeline paralelizado prolijo.

### 2. Decisión de herramienta: `joblib`, no PySpark

Se evaluó explícitamente usar PySpark (como en el proyecto hermano
[global-inflation-arima-pyspark](https://github.com/MLEIV90/global-inflation-arima-pyspark),
que sí lo usa para datos **anuales**) y se descartó para este proyecto, de
forma deliberada y documentada acá para que quede como decisión de
ingeniería, no como omisión:

- **Volumen real**: ~676-684 series país×indicador, ~217.000 filas en el
  parquet mensual completo. Esto entra sin problema en la memoria de una
  notebook.
- **Costo de ajuste por serie**: validado en un script suelto previo a este
  repo, ARIMA+GARCH ajustan en ~2 segundos por serie. 680 series × 2s ≈ 22
  minutos en serie — trivialmente paralelizable en un solo proceso con
  varios cores.
- **Spark está pensado para volumen que no entra en una máquina, o para
  cómputo distribuido en un cluster.** Acá ninguna de las dos condiciones
  aplica: el overhead de gestión de cluster, serialización JVM y
  arranque de contexto de Spark sería un costo puro, sin ningún beneficio,
  para un problema que es "muchas tareas chicas e independientes en una
  sola máquina" — exactamente el caso de uso para el que `joblib` (con su
  backend `loky` de multiprocessing) es la herramienta correcta.
- Elegir la herramienta más simple que resuelve el problema, en vez de la
  que suena más impresionante, es la decisión de ingeniería correcta acá —
  y vale documentarlo así de explícito porque es una decisión que se
  revirtió respecto del proyecto hermano a propósito, no por default.

### 3. Por qué esta fuente y no la API anual del Banco Mundial

El Banco Mundial expone series de inflación anual estándar vía su API/WDI
(ej. el indicador `FP.CPI.TOTL.ZG`, que es lo que usa el proyecto hermano en
PySpark). Para este proyecto se usó en cambio el archivo
**Global Database of Inflation** (Ha, Kose & Ohnsorge), publicado como un
único Excel curado, porque:

- Trae **frecuencia mensual** (5 de 6 indicadores: `hcpi, ecpi, fcpi, ccpi,
  ppi`), algo que la API estándar de WDI no ofrece — y la frecuencia
  mensual es indispensable para este proyecto: con datos anuales, GARCH
  necesitaría décadas de historia por país para tener suficientes
  observaciones (se determinó en Fase 3 que GARCH necesita ≥100 puntos;
  con datos anuales eso son 100 años, inviable).
- Es un **archivo único versionado**, no una API que hay que golpear
  repetidamente — mejor para reproducibilidad (se descarga una vez, se
  cachea en `data/raw/`, y cualquiera puede re-ejecutar el pipeline sin
  depender de que la API siga respondiendo igual).
- Viene con **6 indicadores distintos** (CPI headline, energía, alimentos,
  núcleo, productor, deflactor) en vez de un solo índice agregado —
  permite comparar previsibilidad/volatilidad entre categorías de precios
  dentro del mismo país, no solo entre países.

### 4. Metodología: diagnóstico exhaustivo en 4 fases antes de corregir

Se decidió, desde el arranque del EDA riguroso, **separar estrictamente
diagnóstico de corrección**: cuatro fases, cada una un script + informe
reproducible que **no modifica ningún dato**, antes de tocar una sola línea
del ETL de corrección. La razón es simple — este dataset resultó tener
suficientes problemas estructurales entrelazados (duplicados, filas mal
etiquetadas, ceros-placeholder, desfasajes de frecuencia, hiperinflación)
que corregir sobre la marcha, fase a fase, hubiera significado tomar
decisiones de corrección con información parcial y posiblemente tener que
deshacerlas más tarde. Diagnosticar todo primero, con el panorama completo,
permite que el ETL corregido (Parte B de este documento) sea un solo
rediseño coherente en vez de una serie de parches.

### 5. Resumen ejecutivo por fase

**[Fase 1 — Entender la fuente](fase1_estructura_fuente.md).** Inventario
programático de las 20 hojas del Excel, confirmando que las hojas `_m`/`_q`
son índice y las `_a` son tasa (con una excepción de etiqueta: `def_a` usa
`'Rate'` en vez de `'Inflation'`). Hallazgo crítico: las 5 hojas mensuales
**no son homogéneas** en `Indicator Type` — India e Indonesia en `ecpi_m`
ya vienen como tasa (no índice), y British Virgin Islands en `hcpi_m` y
Australia en `ppi_m` están mal etiquetados pero sí son índice. Confirmado también que el deflactor del PIB (`def`) no tiene
hoja mensual, solo trimestral/anual.

**[Fase 2 — Integridad estructural](fase2_integridad.md).** Auditoría
sobre el Excel crudo: **36 país-hoja con `Country Code` duplicado** (30 de
ellos solo en `ecpi_m`, mucho más de lo que Fase 1 había visto mirando
únicamente `ppi_m`), filas de nota/footnote sin código ISO3 válido,
validación de códigos contra `pycountry` (único no-estándar: `XKX`/Kosovo,
esperado), y un hallazgo nuevo no explicado por Fase 1: **Venezuela con
índice exactamente 0.0** durante ~51-60 meses en `ecpi_m`/`fcpi_m`,
económicamente inconsistente con un índice de precios real. También se
documentaron 24 país-hoja con discontinuidades/saltos mes a mes fuera de
rango, clasificados tentativamente entre rebase aislado y posible
hiperinflación real.

**[Fase 3 — Cobertura temporal](fase3_cobertura.md).** Trabajando sobre el
índice crudo (excluyendo ya las series confirmadas problemáticas), se
clasificó cada serie por patrón de cobertura y se aplicaron pisos de 60
meses (ARIMA) y 100 meses (GARCH): **636 series modelables para ARIMA, 624
para GARCH**, de 672 series con datos utilizables. Se detectó además que el
desfasaje de frecuencia (datos que en realidad son trimestrales cargados en
la hoja mensual) es un fenómeno **por serie individual, no por país** — una
corrección que se hizo al informe después de que una verificación
independiente mostrara que el hallazgo original generalizaba mal (Irlanda e
Islandia son 100% mensuales en `hcpi_m`, y solo mezclan tramos trimestrales
en `fcpi_m`).

**[Fase 4 — Estadística univariada](fase4_univariada.md).** El objetivo
central era decidir con evidencia `pct_change` vs `log-diff`. Resultado:
son equivalentes en magnitud para inflación baja/moderada pero divergen
fuerte en hiperinflación (Venezuela PPI ene-2019: 344.272% en `pct_change`
vs 814% en `log-diff`, mismo evento real). Se validó además el índice y la
fórmula contra la tasa anual oficial (`hcpi_a`) — el promedio anual del
índice la reproduce casi exactamente (error mediano ≈ 0), confirmando que
el cálculo de base es correcto. Se caracterizaron 77 series con algún mes
>100% de inflación (20 con >1000%) y 553 series con algún mes de deflación,
con los casos más extremos (Japón, Suiza) confirmados como economía real,
no artefacto de datos.

### 6. Decisiones metodológicas clave

| Decisión | Justificación | Evidencia |
|---|---|---|
| Calcular **doble transformación** (`inflacion_yoy_pct` + `inflacion_yoy_log`), no elegir una sola | `pct_change` es la unidad estándar/interpretable y la que reproduce la cifra oficial; `log-diff` es numéricamente más estable para alimentar GARCH (no tiene piso en -100%, comprime la cola de hiperinflación) | Fase 4, secciones 1 y 2 |
| **No winsorizar hiperinflación por defecto** — marcar con flag y decidir en el momento de ajustar cada modelo | Winsorizar preventivamente destruye información real sobre régimen de alta inflación, que es justo lo que un análisis de volatilidad quiere capturar | Fase 4, sección 4 |
| **Panel no balanceado por diseño** — no excluir países por historia corta, usar flags de cobertura/confianza en vez de recortar a un subconjunto común | Recortar el panel a los países con historia completa sesgaría la muestra hacia economías estables (las que más años llevan con series limpias) | Fase 3; mismo criterio ya aplicado en el proyecto hermano PySpark |
| **Tratamiento por serie individual (país×indicador), nunca por país en bloque** | Un país puede tener un indicador limpio y otro problemático (ej. Irlanda: `hcpi_m` 100% mensual, `fcpi_m` con tramos trimestrales); generalizar a nivel país produce hallazgos falsos | Fase 3 — corrección aplicada tras verificación independiente |
| **Ramificar por `Indicator Type` real, no por hoja** | Asumir que toda una hoja mensual es índice rompe el cálculo para las filas que ya vienen como tasa (India/Indonesia) | Fase 1, sección 4 |

---

## Parte B — Plan del ETL corregido (propuesta, sin ejecutar)

Checklist ordenado como pipeline. Cada paso referencia el hallazgo de fase
que lo motiva. **No se ha escrito ni ejecutado código de corrección
todavía** — esto es la propuesta a aprobar antes de codear
`02_descarga_datos_v2.py` (o el nombre que se decida).

### Paso 1 — Cargar las 5 hojas mensuales crudas
`hcpi_m, ecpi_m, fcpi_m, ccpi_m, ppi_m` desde `data/raw/Inflation-data.xlsx`.
(`def` queda fuera del panel mensual — Fase 1.)

### Paso 2 — Filtrar filas no-país explícitamente
Quedarse solo con filas cuyo `Country Code` matchea `^[A-Z]{3}$`, **antes**
del melt — no depender de que el `dropna` posterior las descarte como
efecto secundario. (Fase 2, sección 2.)

### Paso 3 — Deduplicar `Country Code` repetido — con revisión de los 36 casos

Regla por defecto: quedarse con la fila de más puntos válidos (ya
implementada y validada para AUT/NLD/PRT/ZAF desde el primer commit).

**Revisión pedida, hecha ahora:** de los 36 país-hoja duplicados, **8 casos
(22%)** tienen un conflicto real entre "más completa" (más puntos) y "más
reciente" (llega más cerca de 2025):

| Hoja | Código | Elegida (n / hasta) | Alternativa (n / hasta) | Meses de recencia que se pierden | Cuánto más larga es la elegida |
|---|---|---|---|---|---|
| ppi_m | AUT | 453 / 2024-09 | 302 / 2025-02 | 5 | 1.50× |
| ppi_m | NLD | 657 / 2024-09 | 530 / 2025-02 | 5 | 1.24× |
| ppi_m | PRT | 297 / 2024-09 | 243 / 2025-03 | 6 | 1.22× |
| ecpi_m | EGY | 177 / 2024-09 | 67 / 2025-03 | 6 | 2.64× |
| ecpi_m | MOZ | 211 / 2024-08 | 111 / 2025-03 | 7 | 1.90× |
| ecpi_m | CMR | 153 / 2024-09 | 151 / 2025-01 | 4 | 1.01× |
| ecpi_m | DOM | 314 / 2025-02 | 171 / 2025-03 | 1 | 1.84× |
| ecpi_m | KWT | 182 / 2025-02 | 156 / 2025-03 | 1 | 1.17× |

Lectura: en la mayoría de estos casos (EGY, MOZ, DOM, KWT) la fila elegida
tiene sustancialmente más historia (1.2×-2.6×) a costa de perder solo 1-7
meses de actualidad — un trade-off razonable para ARIMA/GARCH, donde más
historia generalmente pesa más que unos pocos meses recientes. El caso
**CMR es casi un empate** (153 vs 151 puntos, 4 meses de diferencia) y
**AUT/NLD/PRT** son los más marginales (1.2×-1.5× más historia por 5-6
meses de recencia perdida) — valen una mirada puntual.

**No se propone fusionar/empalmar las dos filas** (usar una para el tramo
viejo y otra para el tramo nuevo): Fase 1 confirmó que en estos casos las
dos filas son series numéricamente distintas (bases/vintages diferentes,
no la misma serie repetida), así que empalmarlas sin reescalar
introduciría un salto de nivel no documentado — el mismo tipo de problema
que Fase 2 marcó como "discontinuidad/rebase" a evaluar aparte, no una
solución gratis. Se deja para un refinamiento futuro si hace falta.

**Propuesta:** mantener la regla de "más puntos" para las 36, y agregar una
columna `dedup_conflicto_recencia` (booleana) marcando estos 8 casos para
que quede trazable en el parquet final cuál fila se descartó y por qué,
sin bloquear el resto del pipeline.

### Paso 4 — Ramificar por `Indicator Type` real (no por hoja)
- `ecpi_m` / IND, IDN: `Indicator Type='Inflation'`, el valor ya es una
  tasa → usar directamente como `inflacion_yoy_pct` (sin recalcular con
  `pct_change`), dejar `indice` en `NaN` (no hay índice real disponible
  para estas dos filas), y derivar `inflacion_yoy_log` como
  `100·ln(1 + valor/100)` a partir de esa tasa.
- `hcpi_m` / VGB y `ppi_m` / AUS: etiqueta incorrecta pero el valor SÍ es
  índice (confirmado por escala en Fase 1) → tratar como cualquier fila
  `Index` normal, sin excepción.

### Paso 5 — Tratar los ceros de Venezuela como dato faltante
`ecpi_m` y `fcpi_m` / VEN: los ~51-60 meses con índice exactamente `0.0`
pasan a `NaN` (no son un valor real, Fase 2). Esto los convierte
automáticamente en huecos internos de la serie, no en observaciones válidas
de "colapso total de precios".

### Paso 6 — Calcular ambas transformaciones
`inflacion_yoy_pct = 100·(P_t/P_{t-12} - 1)` y
`inflacion_yoy_log = 100·(ln(P_t) - ln(P_{t-12}))`, aplicadas después de
los pasos 4-5 (para que ya operen sobre el índice/tasa corregidos, no sobre
el dato crudo con problemas conocidos).

### Paso 7 — Detectar y marcar patrón de frecuencia por serie
Reutilizar la lógica de Fase 3 (moda de pasos entre observaciones
consecutivas) y agregar columna `patron_frecuencia`
(`mensual`/`trimestral`/`mixto`) por serie. Las series `mixto` (29 en Fase
3: Belice en las 3 hojas, Irlanda/Islandia en `fcpi_m`, y ~24 más con
huecos puntuales) **no se excluyen ni se remuestrean automáticamente** —
quedan marcadas para que la fase de modelado decida tratamiento caso por
caso (remuestreo a trimestral vs. imputación de hueco puntual, según la
distribución de pasos de cada una).

### Paso 8 — Flag de hiperinflación, sin winsorizar
Columna `alta_inflacion` (booleana) = `True` si `inflacion_yoy_pct > 100`
en algún punto de la serie. No se recorta ni transforma el valor — el
tratamiento (log-diff ya atenúa, winsorizar como último recurso) se decide
en la etapa de ajuste de modelo, no acá (Fase 4, recomendación).

### Paso 9 — Calcular métricas de cobertura y flags de aptitud, sin excluir filas
Por serie: `n_meses_validos`, `n_huecos_internos`, `clasificacion_cobertura`
(completa/arranque tardío/con huecos/fragmentada — Fase 3), y dos flags
booleanos `apto_arima` (≥60 meses, sin huecos internos) y `apto_garch`
(≥100 meses, sin huecos internos). **No se borran filas del parquet por
esto** — se deja que el script de modelado filtre por el flag que
corresponda, para no perder trazabilidad de por qué una serie quedó afuera.

### Paso 10 — Guardar el resultado
`data/processed/inflacion_mensual_completa_v2.parquet` con columnas:
`pais, codigo_pais, indicador, fecha, indice, inflacion_yoy_pct,
inflacion_yoy_log, tratamiento_indicator_type, patron_frecuencia,
alta_inflacion, n_meses_validos, clasificacion_cobertura, apto_arima,
apto_garch, dedup_conflicto_recencia`. Se versiona con sufijo `_v2` en vez
de sobreescribir el actual, para poder comparar antes/después.

---

**Pendiente de aprobación antes de codear:** confirmar que este orden de
pasos y las columnas de salida son las que se quieren, y decidir si los 8
casos de `dedup_conflicto_recencia` (en especial CMR, casi empatado)
merecen una revisión manual puntual antes de fijar la regla, o si se
acepta la regla automática con el flag como suficiente trazabilidad.
