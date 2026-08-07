# Robustez: intervalos de confianza y modelo multivariado

Informe generado por `src/12_robustez_multivariado.py`. **Solo diagnóstico.** Continuación de `auditoria_metodologica.md` — acá se cuantifica la incertidumbre del ranking de previsibilidad y se pone todo lo encontrado en Análisis A/B/C dentro de un único modelo multivariado.

## Parte 1 — Intervalos de confianza en la previsibilidad

Para cada una de las 174 series hcpi se recalcularon los errores de forecast walk-forward (mismo procedimiento que Análisis A/`06b_modelado_robusto.py`) y se calculó un intervalo de confianza del RMSE por bootstrap (1000 iteraciones, resampleo con reemplazo de los ~24 errores por serie, percentiles 2.5/97.5).

Figura: `reports/figures/robustez_ranking_ci.png`.

**Dentro del top 15 más predecible:** el país #1 tiene IC [0.102, 0.163]. **5 de los otros 14** países del top 15 tienen un intervalo que se solapa con el del #1 — es decir, no se puede afirmar con confianza que sean menos predecibles que el país "más predecible" del panel.

**Dentro del bottom 15 menos predecible:** de forma simétrica, **7 de los otros 14** países del bottom 15 son estadísticamente indistinguibles del país menos predecible del panel.

**Sobre el ranking completo (174 series):** de los 173 pares de países consecutivos (ordenados por RMSE puntual), solo **0 (0.0%)** tienen intervalos de confianza que NO se solapan — el resto de los pares consecutivos son estadísticamente indistinguibles entre sí con esta cantidad de observaciones walk-forward.

Top 15 con intervalos:

| # | País | RMSE | IC 95% | ¿Distinguible del #1? |
|---|---|---|---|---|
| 1 | Tanzania, United Rep. (TZA) | 0.133 | [0.102, 0.163] | No |
| 2 | Malaysia (MYS) | 0.150 | [0.118, 0.181] | No |
| 3 | Saudi Arabia (SAU) | 0.171 | [0.113, 0.228] | No |
| 4 | Switzerland (CHE) | 0.202 | [0.149, 0.253] | No |
| 5 | Dominican Republic (DOM) | 0.220 | [0.166, 0.270] | Sí |
| 6 | Macao SAR, China (MAC) | 0.237 | [0.155, 0.326] | No |
| 7 | Kuwait (KWT) | 0.238 | [0.141, 0.327] | No |
| 8 | Gambia, The (GMB) | 0.269 | [0.214, 0.321] | Sí |
| 9 | Zambia (ZMB) | 0.331 | [0.230, 0.428] | Sí |
| 10 | Colombia (COL) | 0.360 | [0.237, 0.465] | Sí |
| 11 | Korea, Rep. (KOR) | 0.360 | [0.227, 0.493] | Sí |
| 12 | Libya (LBY) | 0.363 | [0.244, 0.470] | Sí |
| 13 | Japan (JPN) | 0.364 | [0.276, 0.448] | Sí |
| 14 | Malta (MLT) | 0.369 | [0.246, 0.485] | Sí |
| 15 | Mexico (MEX) | 0.372 | [0.268, 0.482] | Sí |

Bottom 15 con intervalos:

| # | País | RMSE | IC 95% | ¿Distinguible del último? |
|---|---|---|---|---|
| 1 | Central African Republic (CAF) | 2.416 | [1.143, 3.536] | Sí |
| 2 | Turkey (TUR) | 2.546 | [1.582, 3.443] | Sí |
| 3 | Pakistan (PAK) | 2.566 | [1.614, 3.450] | Sí |
| 4 | Dominica (DMA) | 2.585 | [1.625, 3.439] | Sí |
| 5 | Burundi (BDI) | 2.592 | [1.850, 3.322] | Sí |
| 6 | Sri Lanka (LKA) | 3.055 | [1.779, 4.199] | Sí |
| 7 | Venezuela, RB (VEN) | 3.069 | [1.932, 4.330] | Sí |
| 8 | Iraq (IRQ) | 4.014 | [0.673, 6.851] | No |
| 9 | Kiribati (KIR) | 4.027 | [2.601, 5.239] | No |
| 10 | Argentina (ARG) | 4.979 | [3.365, 6.413] | No |
| 11 | Burkina Faso (BFA) | 5.317 | [1.210, 8.980] | No |
| 12 | Sudan (SDN) | 7.635 | [5.280, 9.594] | No |
| 13 | Lebanon (LBN) | 8.689 | [5.004, 12.263] | No |
| 14 | South Sudan (SSD) | 11.804 | [7.565, 15.262] | No |
| 15 | Zimbabwe (ZWE) | 14.915 | [4.604, 22.932] | No |

**Conclusión Parte 1:** el ranking país-por-país de Análisis A es matemáticamente correcto pero engañoso si se lee como una lista estrictamente ordenada. La lectura honesta es en **grupos de previsibilidad estadísticamente indistinguibles**, no un orden exacto: la diferencia entre el país #1 y buena parte del resto del top 15 (o entre el último y buena parte del bottom 15) no es distinguible del azar con 15 vs. 15 observaciones walk-forward por serie. Las diferencias SÍ son claras entre los extremos del panel completo (un país del top 15 vs. uno del bottom 15), pero no entre vecinos cercanos del ranking.

## Parte 2 — Modelo multivariado de la previsibilidad

Variable dependiente: `log(rmse_arima_walkforward)`. Se usó el logaritmo porque la asimetría del RMSE en nivel es muy alta (asimetría=5.37) y baja sustancialmente al tomar logaritmo (asimetría=1.02), más apropiado para los supuestos de OLS.

Predictores: nivel de ingreso (dummies, referencia = Low income), inflación media del país (`log1p(|inflación media|)`, misma razón de asimetría), longitud de la serie (`meses_usados`), región (dummies, referencia = Sub-Saharan Africa) y persistencia GARCH. OLS con errores robustos a heterocedasticidad (HC3).

**N = 171** países. **R² = 0.315** (R² ajustado = 0.263).

### Coeficientes

Figura: `reports/figures/robustez_coeficientes_ols.png`.

| Variable | Coeficiente | Error estándar (robusto) | p-valor | Significativo (p<0.05) |
|---|---|---|---|---|
| const | +0.2750 | 0.4890 | 0.574 | No |
| ingreso_Lower middle income | -0.6202 | 0.2594 | 0.017 | Sí |
| ingreso_Upper middle income | -0.8476 | 0.2553 | 0.001 | Sí |
| ingreso_High income | -0.9889 | 0.2852 | 0.001 | Sí |
| region_East Asia & Pacific | +0.1852 | 0.2005 | 0.356 | No |
| region_Europe & Central Asia | +0.3223 | 0.1769 | 0.068 | No |
| region_Latin America & Caribbean | +0.0368 | 0.1946 | 0.850 | No |
| region_Middle East, North Africa, Afghanistan & Pakistan | +0.3058 | 0.2205 | 0.165 | No |
| region_North America | +0.2162 | 0.2052 | 0.292 | No |
| region_South Asia | +0.2483 | 0.3806 | 0.514 | No |
| log_inflacion | +0.2482 | 0.1029 | 0.016 | Sí |
| meses_usados | -0.0009 | 0.0003 | 0.004 | Sí |
| persistencia | -0.1178 | 0.4753 | 0.804 | No |

### Multicolinealidad (VIF)

| Variable | VIF |
|---|---|
| ingreso_Lower middle income | 3.31 |
| ingreso_Upper middle income | 5.26 |
| ingreso_High income | 7.48 |
| region_East Asia & Pacific | 2.02 |
| region_Europe & Central Asia | 3.91 |
| region_Latin America & Caribbean | 2.52 |
| region_Middle East, North Africa, Afghanistan & Pakistan | 1.87 |
| region_North America | 1.19 |
| region_South Asia | 1.23 |
| log_inflacion | 7.32 |
| meses_usados | 7.50 |
| persistencia | 15.46 |

**Advertencia:** ['ingreso_Upper middle income', 'ingreso_High income', 'log_inflacion', 'meses_usados', 'persistencia'] tienen VIF > 5 — hay multicolinealidad relevante entre estos predictores, sus coeficientes individuales hay que interpretarlos con cautela (el modelo en conjunto sigue siendo válido, pero separar el efecto de cada uno de estos predictores específicos es menos preciso).

### Interpretación de las variables clave

**El ingreso sobrevive, al menos parcialmente, el control simultáneo por todas las demás variables**: ingreso_Lower middle income es significativo (coef=-0.620, p=0.017); ingreso_Upper middle income es significativo (coef=-0.848, p=0.001); ingreso_High income es significativo (coef=-0.989, p=0.001). Esto es consistente con Análisis A y con la Parte 2 de la auditoría anterior: el ingreso tiene un efecto propio sobre la previsibilidad, no reducible a los otros factores del modelo.

**La inflación media aporta información propia más allá del ingreso** (coef=+0.248, p=0.016): a igual nivel de ingreso, región, longitud de serie y persistencia, países con mayor inflación media siguen siendo menos predecibles.

**La longitud de la serie SIGUE importando incluso controlando por ingreso** (coef=-0.00094, p=0.004) — series más largas tienden a ser más predecibles incluso después de controlar por todo lo demás.

**Persistencia GARCH**: coef=-0.118, p=0.804 — NO significativa, consistente con el hallazgo de Análisis C de que previsibilidad de nivel y persistencia de volatilidad son dimensiones mayormente independientes.

**Conclusión Parte 2:** el modelo explica **31.5%** de la variación en previsibilidad (R²) entre los países de la muestra. Es una fracción sustancial — sugiere que las variables incluidas capturan buena parte de lo que determina la previsibilidad de la inflación.
