# Fase 5 — Análisis de series de tiempo

Informe generado por `src/fase5_series_tiempo.py` sobre `data/processed/inflacion_mensual_completa_v2.parquet`, usando `inflacion_yoy_log` (Fase 4) y solo series `apto_arima`/`apto_garch`. **Solo diagnóstico: no se ajusta ningún modelo final, no se corrige ningún dato.** Los huecos internos no se interpolan — todas las series usadas ya tienen 0 huecos internos por definición de `apto_arima`/`apto_garch` (Fase 3/ETL); solo se recortan los primeros ~12 meses sin dato por el lag de `inflacion_yoy_log`.

Universo: **640 series apto_arima**, **626 series apto_garch** (subconjunto de las anteriores).

## 1. Estacionariedad (ADF + KPSS)

Para cada serie se corre ADF (H0: raíz unitaria / no estacionaria) y KPSS (H0: estacionaria) en nivel; si ambos tests coinciden en 'no estacionaria', se diferencia una vez (d=1) y se repite; si hace falta, una segunda vez (d=2, tope de este análisis). Si los dos tests no coinciden entre sí en algún d, se marca 'ambigua' en vez de forzar una conclusión.

**Distribución del orden de integración recomendado (todas las series apto_arima):**

| d recomendado | N series | % |
|---|---|---|
| d=0 | 436 | 68.1% |
| d=1 | 202 | 31.6% |
| d=2 | 2 | 0.3% |

De las 640 series: **304 quedaron 'ambiguas'** (ADF y KPSS no coinciden incluso tras diferenciar) y **0 sin datos suficientes** para completar el procedimiento — ninguna de las dos se fuerza a una conclusión, quedan marcadas para revisión manual si hace falta.

**Por indicador:**

| Indicador | d=0 | d=1 | d=2 | Total |
|---|---|---|---|---|
| ccpi | 37 | 42 | 0 | 79 |
| ecpi | 118 | 39 | 0 | 157 |
| fcpi | 99 | 36 | 0 | 135 |
| hcpi | 106 | 68 | 1 | 175 |
| ppi | 76 | 17 | 1 | 94 |

**Implicancia para auto_arima:** el rango de `d` a explorar debería ser `{0, 1, 2}` — la inmensa mayoría de las series cae en d=0 o d=1 (inflación YoY en log-diff ya es razonablemente estacionaria en la mayoría de los países, algo esperable porque es una tasa de variación, no un nivel), pero hay una cola de series que necesita d=2, así que no conviene fijar `d` a un valor único para todo el panel.

## 2. Autocorrelación (muestra representativa)

Muestra de 8 países en `hcpi` con perfiles distintos: estables/bajos (USA, DEU, GBR), historial deflacionario (JPN), históricamente altos/volátiles (BRA, ZAF, TUR, ARG). Figura: `reports/figures/fase5_acf_pacf_muestra.png`.

| País | N obs. | ACF lag 1 | ACF lag 12 | Último lag 1-12 con ACF significativa |
|---|---|---|---|---|
| USA | 651 | 0.994 | 0.799 | 12 |
| DEU | 651 | 0.984 | 0.690 | 12 |
| JPN | 650 | 0.989 | 0.748 | 12 |
| GBR | 651 | 0.994 | 0.799 | 12 |
| BRA | 532 | 0.997 | 0.793 | 12 |
| ZAF | 649 | 0.982 | 0.731 | 12 |
| TUR | 651 | 0.993 | 0.798 | 12 |
| ARG | 86 | 0.982 | 0.366 | 12 |

**Observación adicional en la figura:** en 6 de las 8 series (USA, DEU, JPN, GBR, ZAF, TUR) la PACF cae dentro de la banda de no-significancia para casi todos los lags 2-12, pero muestra un pico aislado y consistente en el **lag 13** (no en el 12, que es donde se buscaría un efecto estacional clásico). Es un patrón demasiado sistemático entre países distintos como para ser casualidad — probablemente una firma estructural de cómo se construye `inflacion_yoy_log` (una suma móvil de 12 log-retornos mensuales), no un ciclo de calendario. Queda anotado como algo a tener presente al definir el rango de `p`/`q` por serie, sin profundizar más acá porque excede el alcance de este diagnóstico.

Las 8 series muestran autocorrelación significativa en el lag 1 y, en la mayoría, persistencia hasta varios lags más (típico de inflación YoY: el propio cálculo de variación interanual introduce dependencia serial por construcción). Esto confirma que **hay algo que ARIMA puede capturar** — si el ACF hubiera caído a cero inmediatamente en el lag 1 en todas las series, ARIMA no tendría ninguna estructura que modelar más allá de ruido blanco. La forma de decaimiento (lento y gradual en las series de mayor persistencia, ej. las de inflación alta, vs. corte más rápido en las más estables) sugiere que los órdenes `p` y `q` razonables para explorar en `auto_arima` están en el rango **0-3**, no hace falta ir más alto — decaimientos lentos ya quedan cubiertos por el término de diferenciación `d`, no por `p`/`q` grandes.

## 3. Test ARCH (Engle) — validación clave para GARCH

Sobre cada serie `apto_garch`, se diferencia con el `d` recomendado en la sección 1 (o d=1 si no hay conclusión), se ajusta un AR(1) simple sobre la serie diferenciada, y se corre el test ARCH-LM de Engle (`statsmodels.stats.diagnostic.het_arch`, 12 rezagos) sobre los residuos. p<0.05 → se rechaza "no hay efecto ARCH" → hay agrupamiento de volatilidad (volatility clustering) → GARCH está justificado para esa serie.

**Resultado global: 571 de 626 series (91.2%) muestran efecto ARCH significativo (p<0.05).**

**Por indicador:**

| Indicador | N series | Con ARCH significativo | % |
|---|---|---|---|
| ccpi | 79 | 76 | 96.2% |
| ecpi | 151 | 133 | 88.1% |
| fcpi | 131 | 122 | 93.1% |
| hcpi | 172 | 153 | 89.0% |
| ppi | 93 | 87 | 93.5% |

De las series **con** efecto ARCH significativo, **11.2%** también tienen el flag `alta_inflacion=True` (algún mes >100% YoY). De las series **sin** efecto ARCH, **9.1%** lo tienen.

**Conclusión explícita:** el efecto ARCH aparece en el 91% de las series aptas — no es un fenómeno aislado a un puñado de países, es la situación **mayoritaria** en este panel, y **no está limitado al subconjunto de series de alta inflación**: 11.2% vs. 9.1% es una diferencia chica (la tasa base de `alta_inflacion` en todo el universo `apto_garch` ya es ~11%), no la brecha grande que se vería si el efecto ARCH viniera casi exclusivamente de los episodios hiperinflacionarios. En criollo: **GARCH tiene sustento empírico amplio en prácticamente todo el panel** — economías estables incluidas — no es un fenómeno exclusivo de países con historial de hiperinflación como Argentina, Venezuela o Turquía.

## 4. Estacionalidad mensual

Sobre la misma muestra de 8 países: descomposición STL (período 12) para medir qué porción de la varianza total explica el componente estacional, más ACF y PACF en el lag 12 como chequeo cruzado. Figura: `reports/figures/fase5_estacionalidad_muestra.png`.

**Aviso metodológico importante, encontrado al correr este análisis:** `inflacion_yoy_log` es, por construcción, una diferencia a 12 meses del log-índice — eso le da a la serie una autocorrelación alta y de decaimiento lento en casi todos los lags cortos (lag 1: ACF≈0.98-0.99 en la muestra), simplemente por la superposición de ventanas de 12 meses, no por un patrón de calendario. Eso significa que la **ACF en el lag 12 no es un buen indicador de estacionalidad acá** — va a dar 'significativa' en la mayoría de las series solo por arrastre de esa persistencia general, sin que eso implique un ciclo estacional real. La **PACF en el lag 12** es la métrica correcta para esto, porque aísla el aporte propio del lag 12 controlando por los lags 1-11.

| País | % varianza explicada por estacional (STL) | ACF lag 12 sig. | PACF lag 12 sig. |
|---|---|---|---|
| USA | 1.13% | sí | no |
| DEU | 1.20% | sí | sí |
| JPN | 0.92% | sí | no |
| GBR | 1.13% | sí | no |
| BRA | 0.29% | sí | sí |
| ZAF | 0.87% | sí | no |
| TUR | 0.89% | sí | sí |
| ARG | 1.44% | sí | no |

Chequeo extendido a las 640 series `apto_arima` completas (no solo la muestra): **ACF lag 12 significativa en 440 (68.8%)** vs. **PACF lag 12 significativa en solo 165 (25.8%)** — la brecha entre ambos porcentajes es exactamente la confirmación del aviso metodológico: la mayor parte de lo que la ACF marca como "lag 12 significativo" es persistencia general arrastrada desde lags anteriores, no un efecto estacional propio del lag 12.

**Lectura:** tomando la PACF (la métrica correcta) como referencia, solo ~26% de las series tiene una señal propia en el lag 12, y en la muestra de 8 países el componente estacional STL explica una fracción chica de la varianza total. Esto es coherente con trabajar sobre **inflación interanual** (`inflacion_yoy_log`) en vez de sobre el índice o la variación mensual: el cálculo interanual ya absorbe gran parte de la estacionalidad de calendario (aguinaldos, vacaciones, cosechas estacionales, etc.). No hay evidencia para justificar SARIMA como default para todo el panel; sí conviene activarlo puntualmente en el ~26% de series donde la PACF en lag 12 da significativa.

## Recomendaciones para el modelado

1. **Rango de `(p,d,q)` para `auto_arima`:** `d ∈ {0,1,2}` (la mayoría cae en 0-1, dejar 2 disponible para la cola de series más persistentes); `p,q ∈ {0,...,3}` — los ACF/PACF de la muestra no muestran estructura que requiera órdenes más altos una vez que `d` está bien elegido.
2. **SARIMA vs. ARIMA simple:** no usar SARIMA como default para todo el panel — la estacionalidad de calendario ya queda mayormente absorbida al trabajar en inflación interanual. Sí vale la pena que el pipeline chequee la **PACF en lag 12** (no la ACF, que queda confundida con la persistencia general de la serie — ver sección 4) por serie y active un término estacional solo en el ~26% de series donde da significativa, en vez de pagar el costo de estimarlo en todo el panel.
3. **GARCH está empíricamente justificado en la mayoría del panel** (91% de las 626 series `apto_garch` con efecto ARCH significativo) — y no es un patrón exclusivo de países de alta inflación, la tasa de efecto ARCH es prácticamente la misma con o sin episodios de hiperinflación en la serie (sección 3). El pipeline puede intentar GARCH en todo el universo `apto_garch`, pero conviene guardar el p-valor del test ARCH-LM como metadato: si el ajuste GARCH falla o no converge en una serie sin efecto ARCH significativo, es la explicación esperada, no un bug.
