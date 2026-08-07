# Análisis A — Previsibilidad de la inflación

Informe generado por `src/08_analisis_previsibilidad.py` sobre `data/processed/resultados_enriquecidos.parquet`. Las secciones 1-3 y 5 usan solo `hcpi` (headline CPI, una fila por país) para evitar pseudo-replicación en los tests estadísticos — mezclar los 5 indicadores trataría a hcpi/ecpi/fcpi/ccpi/ppi del mismo país como observaciones independientes cuando no lo son. La sección 4 sí usa el panel completo (los 5 indicadores). N series hcpi analizadas: **174**.

## 1. Ranking de previsibilidad (hcpi)

**Top 15 países más predecibles** (menor RMSE walk-forward):

| País | Ingreso | Región | Inflación media (%) | ratio vs. naive | RMSE |
|---|---|---|---|---|---|
| Tanzania, United Rep. (TZA) | Lower middle income | Sub-Saharan Africa | 5.97 | 0.819 | 0.1326 |
| Malaysia (MYS) | Upper middle income | East Asia & Pacific | 2.11 | 0.775 | 0.1501 |
| Saudi Arabia (SAU) | High income | Middle East, North Africa, Afghanistan & Pakistan | 1.94 | 1.000 | 0.1713 |
| Switzerland (CHE) | High income | Europe & Central Asia | 2.18 | 0.910 | 0.2023 |
| Dominican Republic (DOM) | Upper middle income | Latin America & Caribbean | 7.79 | 0.734 | 0.2202 |
| Macao SAR, China (MAC) | High income | East Asia & Pacific | 2.27 | 0.951 | 0.2367 |
| Kuwait (KWT) | High income | Middle East, North Africa, Afghanistan & Pakistan | 2.86 | 1.000 | 0.2380 |
| Gambia, The (GMB) | Low income | Sub-Saharan Africa | 2.31 | 0.864 | 0.2691 |
| Zambia (ZMB) | Lower middle income | Sub-Saharan Africa | 10.96 | 0.824 | 0.3309 |
| Colombia (COL) | Upper middle income | Latin America & Caribbean | 14.43 | 0.905 | 0.3600 |
| Korea, Rep. (KOR) | High income | East Asia & Pacific | 6.29 | 0.952 | 0.3602 |
| Libya (LBY) | Upper middle income | Middle East, North Africa, Afghanistan & Pakistan | 8.16 | 1.350 | 0.3631 |
| Japan (JPN) | High income | East Asia & Pacific | 2.43 | 1.033 | 0.3639 |
| Malta (MLT) | High income | Middle East, North Africa, Afghanistan & Pakistan | 2.09 | 0.889 | 0.3688 |
| Mexico (MEX) | Upper middle income | Latin America & Caribbean | 21.52 | 0.972 | 0.3720 |

**Top 15 países menos predecibles** (mayor RMSE walk-forward):

| País | Ingreso | Región | Inflación media (%) | ratio vs. naive | RMSE |
|---|---|---|---|---|---|
| Zimbabwe (ZWE) | Lower middle income | Sub-Saharan Africa | 87.03 | 1.273 | 14.9152 |
| South Sudan (SSD) | Low income | Sub-Saharan Africa | 62.62 | 1.047 | 11.8038 |
| Lebanon (LBN) | Lower middle income | Middle East, North Africa, Afghanistan & Pakistan | 44.69 | 1.015 | 8.6887 |
| Sudan (SDN) | Low income | Sub-Saharan Africa | 46.30 | 1.054 | 7.6347 |
| Burkina Faso (BFA) | Low income | Sub-Saharan Africa | 2.13 | 1.000 | 5.3170 |
| Argentina (ARG) | Upper middle income | Latin America & Caribbean | 86.89 | 0.609 | 4.9793 |
| Kiribati (KIR) | Lower middle income | East Asia & Pacific | 2.58 | 1.023 | 4.0268 |
| Iraq (IRQ) | Upper middle income | Middle East, North Africa, Afghanistan & Pakistan | 0.88 | 1.006 | 4.0140 |
| Venezuela, RB (VEN) | Lower middle income | Latin America & Caribbean | 85.72 | 0.618 | 3.0688 |
| Sri Lanka (LKA) | Upper middle income | South Asia | 8.87 | 0.720 | 3.0550 |
| Burundi (BDI) | Low income | Sub-Saharan Africa | 10.55 | 1.033 | 2.5919 |
| Dominica (DMA) | Upper middle income | Latin America & Caribbean | 2.21 | 0.993 | 2.5846 |
| Pakistan (PAK) | Lower middle income | Middle East, North Africa, Afghanistan & Pakistan | 10.37 | 1.050 | 2.5656 |
| Turkey (TUR) | Upper middle income | Europe & Central Asia | 38.46 | 0.801 | 2.5456 |
| Central African Republic (CAF) | Low income | Sub-Saharan Africa | 4.19 | 0.967 | 2.4159 |

## 2. Gradiente por nivel de ingreso

RMSE mediano por nivel de ingreso:

- Low income: 1.7014
- Lower middle income: 0.8490
- Upper middle income: 0.7029
- High income: 0.5376

Figura: `reports/figures/analisisA_boxplot_ingreso.png`.

**Test de Kruskal-Wallis** (no paramétrico, apropiado porque el RMSE no es normal — tiene cola derecha pesada): H = 31.85, p-valor = 5.62e-07.
**Conclusión:** con p < 0.05, se confirma que la diferencia entre grupos de ingreso NO es azar.

## 3. Previsibilidad vs. nivel de inflación

Figura: `reports/figures/analisisA_scatter_inflacion_rmse.png`.

- Correlación de Spearman inflación media vs. RMSE: **ρ = 0.185** (p = 1.45e-02).
- Correlación de Spearman inflación media vs. nivel de ingreso (ordinal): ρ = -0.221 (p = 3.36e-03).
- Correlación de Spearman RMSE vs. nivel de ingreso (ordinal): ρ = -0.420 (p = 7.90e-09).

**Correlación parcial** de inflación vs. RMSE, controlando por nivel de ingreso: **ρ parcial = 0.104** (p = 1.73e-01, n=174).

La correlación parcial cae sustancialmente respecto a la correlación simple: **gran parte de la relación aparente entre inflación y RMSE está mediada por el nivel de ingreso** — ambas variables están correlacionadas entre sí, y el ingreso es al menos parte de lo que explica la imprevisibilidad, no solo el nivel de inflación en sí.

## 4. El hallazgo del baseline (panel completo, 5 indicadores)

Sobre las 639 series con walk-forward válido: **403 (63.1%)** tienen `ratio_vs_naive < 1` (ARIMA le gana al naive) y 236 (36.9%) no.

Inflación media (valor absoluto) — mediana donde ARIMA **gana**: 4.90%. Mediana donde **no gana**: 5.19%.

Figura: `reports/figures/analisisA_boxplot_baseline.png`.

**Test de Mann-Whitney U** (H1: la inflación absoluta es mayor donde ARIMA gana): U = 47333.0, p-valor = 5.39e-01.
**Chequeo de robustez** (en vez de partir la muestra en dos grupos, correlación continua entre |inflación media| y `ratio_vs_naive` sobre las 639 series): Spearman ρ = -0.053, p = 1.78e-01.

**Conclusión:** **ninguno de los dos tests alcanza significancia estadística** (p=0.54 y p=0.18) — con esta muestra, el nivel de inflación por sí solo NO predice de forma confiable si una serie va a ganarle al naive o no. La narrativa "el random walk es imbatible en inflación estable" es intuitiva y se ve con claridad en un puñado de países ilustrativos (EE.UU./Alemania pierden, Argentina/Venezuela ganan — ver el sanity check de la fase de modelado), pero **no se sostiene como patrón general y estadísticamente significativo en todo el panel.**

**¿Por qué el efecto simple sale débil?** Mirando de cerca las 59 series con inflación media absoluta > 20% (todas, en principio, "candidatas" a que ARIMA le gane al naive por tener una tendencia marcada), el `ratio_vs_naive` va de 0.42 a 1.72 — un rango enorme, no un bloque uniforme. Argentina, Venezuela y Lituania (inflación alta pero con una tendencia sostenida que ARIMA puede seguir) están entre las que MÁS le ganan al naive; Zimbabwe, Sudán del Sur y Letonia (`hcpi`, no `fcpi`) — inflación alta pero con saltos discontinuos o cambios de régimen abruptos — están entre las que MENOS le ganan. **No es "cuánta" inflación tiene la serie lo que determina si ARIMA aporta, sino si esa inflación tiene una tendencia que un modelo lineal puede seguir, o si es errática/discontinua** — eso diluye la relación simple entre nivel de inflación y ventaja de ARIMA cuando se la mide en bloque.

## 5. Patrones regionales (hcpi)

RMSE mediano por región, de más a menos predecible:

| Región | N series | RMSE mediano |
|---|---|---|
| North America *(n=2, no incluida en el test)* | 2 | 0.4524 |
| Latin America & Caribbean | 31 | 0.5864 |
| East Asia & Pacific | 22 | 0.6145 |
| Europe & Central Asia | 47 | 0.6925 |
| South Asia | 6 | 0.7135 |
| Middle East, North Africa, Afghanistan & Pakistan | 22 | 0.8046 |
| Sub-Saharan Africa | 44 | 0.9841 |

Figura: `reports/figures/analisisA_boxplot_region.png`.

**Test de Kruskal-Wallis** entre regiones (excluyendo North America por n=2): H = 8.70, p-valor = 1.22e-01.
**Conclusión:** no se puede descartar que las diferencias regionales observadas sean azar.

## Conclusiones principales

1. **El ingreso importa, y no es casualidad**: el gradiente de previsibilidad por nivel de ingreso es estadísticamente significativo (Kruskal-Wallis p=5.6e-07) — los países de mayores ingresos tienen inflación más previsible, en línea con instituciones monetarias más estables y menor exposición a shocks estructurales.
2. **La correlación simple entre inflación y RMSE (ρ=0.19) se explica en gran parte por el nivel de ingreso**, no por la inflación en sí misma: al controlar por ingreso, la correlación parcial cae a ρ=0.10 (p=0.17, no significativa). El ingreso y la inflación están entrelazados en esta muestra, y separar sus efectos con el n disponible no da una conclusión firme sobre cuál de los dos "causa" la imprevisibilidad.
3. **El 37% donde ARIMA no le gana al naive NO se explica simplemente por "baja inflación"** — ni el test de grupos ni la correlación continua encuentran una relación estadísticamente significativa entre nivel de inflación y `ratio_vs_naive` en todo el panel. Lo que sí aparece, mirando de cerca las series de inflación alta (sección 4), es que importa más el *tipo* de alta inflación (tendencia sostenida vs. saltos erráticos) que su magnitud. La narrativa "random walk imbatible en inflación estable" es real en casos puntuales (ver el sanity check de la fase de modelado: EE.UU./Alemania vs. Argentina/Venezuela) pero no es la explicación general de por qué el otro 37% no le gana al naive — haría falta mirar caso por caso, no un patrón único.
4. **La región, a diferencia del ingreso, NO muestra un efecto estadísticamente significativo propio** (Kruskal-Wallis p=0.12) una vez que se la mira región por región — el RMSE mediano varía (Sub-Saharan Africa el doble que Latin America & Caribbean, sección 5), pero con el n disponible por región no alcanza para distinguir esa variación de azar. Es coherente con que buena parte de la variación regional podría estar mediada por la composición de ingreso de cada región, no por geografía en sí.
