# Diagnóstico — Series país-a-país byte-idénticas en el Excel del Banco Mundial

**Hallazgo nuevo de Fase A**, detectado durante la remediación R1 (verificación del benchmark Atkeson-Ohanian) y NO capturado por la auditoría formal A.1-A.6, que no buscó duplicados inter-país (A.6 buscó duplicados de `Country Code` *dentro* de una hoja, que es un problema distinto). SOLO DIAGNÓSTICO — no se modificó ningún dato ni resultado.

## Paso 1 — Detección exhaustiva (las 5 hojas mensuales, no solo `hcpi`)

Se comparó, dentro de cada una de las 5 hojas mensuales usadas por el proyecto (`hcpi_m, ecpi_m, fcpi_m, ccpi_m, ppi_m`), cada par de países por igualdad byte-a-byte de su fila completa de 663 meses (post-deduplicación por país, la misma lógica que usa `05_etl_corregido.py`), directamente sobre `data/raw/Inflation-data.xlsx` — no sobre el parquet procesado, para determinar si el problema está en la fuente o en el ETL.

**Total de pares encontrados: 3**

| Hoja | Indicador | País A | País B | Meses válidos |
|---|---|---|---|---|
| hcpi_m | hcpi | CZE | DJI | 411 |
| hcpi_m | hcpi | FIN | GAB | 663 |
| hcpi_m | hcpi | GBR | USA | 663 |

**Confirmado: el problema está en la fuente (Excel del Banco Mundial), no en el ETL** — la detección corrió directamente sobre `data/raw/Inflation-data.xlsx`, antes de cualquier transformación del proyecto.

## Paso 2 — Forense: ¿cuál país tiene la serie correcta?

Ambos países de cada par comparten, por definición del hallazgo, la MISMA serie mensual. Se calculó la tasa YoY promedio que esa serie compartida implica, y se comparó contra la hoja anual oficial independiente (`{indicador}_a`) de **cada país por separado** — una fuente del mismo Excel pero no afectada por el mismo posible error de copiado fila-a-fila del mensual. El país cuya hoja anual está más cerca de lo que implica el mensual compartido es el candidato a **serie auténtica**; el otro, a **víctima** (su mensual real fue sobrescrito por el del primero).

| Indicador | Par | País | Tasa anual propia | Nivel de ingreso | Distancia al mensual compartido | Veredicto del par |
|---|---|---|---|---|---|---|
| hcpi | CZE/DJI (mensual compartido: 4.876%) | CZE | 4.58 | High income | 0.296 | indeterminado (distancias casi iguales) |
| hcpi | CZE/DJI (mensual compartido: 4.876%) | DJI | 5.142 | Lower middle income | 0.266 | indeterminado (distancias casi iguales) |
| hcpi | FIN/GAB (mensual compartido: 4.45%) | FIN | 4.402 | High income | 0.048 | FIN auténtico, GAB víctima (margen 0.326 pp) |
| hcpi | FIN/GAB (mensual compartido: 4.45%) | GAB | 4.824 | Upper middle income | 0.374 | FIN auténtico, GAB víctima (margen 0.326 pp) |
| hcpi | GBR/USA (mensual compartido: 5.357%) | GBR | 5.391 | High income | 0.034 | GBR auténtico, USA víctima (margen 1.305 pp) |
| hcpi | GBR/USA (mensual compartido: 5.357%) | USA | 4.018 | High income | 1.339 | GBR auténtico, USA víctima (margen 1.305 pp) |

**Lectura**: en **FIN/GAB** y **GBR/USA** el veredicto es claro y con margen amplio — la hoja anual de FIN (4.402%) y de GBR (5.391%) están a apenas 0.05-0.03 puntos porcentuales de lo que implica la serie mensual compartida, mientras que la de GAB (4.824%) y especialmente la de USA (4.018%, a 1.34 puntos de distancia) no coinciden en absoluto — evidencia razonablemente fuerte de que las filas mensuales de **Gabón** y de **Estados Unidos** en `hcpi_m` son en realidad una copia de las de Finlandia y Reino Unido respectivamente, no series propias. En **CZE/DJI** las dos distancias son casi idénticas (0.30 vs. 0.27) — **indeterminado**, no hay evidencia suficiente para asignar dirección.

**Limitación honesta**: esta es evidencia circunstancial (una hoja del mismo archivo del Banco Mundial comparada contra otra hoja del mismo archivo), no una fuente de verdad externa (banco central, FMI, INE local). Es razonablemente convincente para FIN/GAB y GBR/USA por el tamaño del margen, pero no es una confirmación definitiva. Por eso el Paso 3 excluye **ambos** países de cada par (incluyendo los dos casos con veredicto), en vez de intentar quedarse con el 'correcto' y remodelarlo — reemplazar requeriría re-descargar o re-construir la serie real de Gabón/EE.UU./República Checa/Yibuti desde otra fuente, fuera del alcance de este diagnóstico.

## Paso 3 — Impacto en el gradiente de ingreso (hallazgo central del proyecto)

**Original** (todas las series `hcpi` con ARIMA convergido, n=174): Kruskal-Wallis H=31.85, **p=5.62e-07**.

```
nivel_ingreso
Low income             1.701389
Lower middle income    0.849010
Upper middle income    0.702898
High income            0.537629
```

**Excluyendo los 6 países con `hcpi` duplicado** (CZE, DJI, FIN, GAB, GBR, USA, n=168): Kruskal-Wallis H=30.39, **p=1.14e-06**.

```
nivel_ingreso
Low income             1.701389
Lower middle income    0.812650
Upper middle income    0.713257
High income            0.543777
```

**El gradiente se mantiene significativo** tras excluir las series contaminadas (p=1.14e-06), incluso levemente más fuerte que el original (p=5.6e-07 con las 6 series incluidas). El impacto de estos 6 países sobre el hallazgo central es, medido directamente, nulo.

**Nota sobre por qué la auditoría formal (A.1-A.6) no lo detectó**: A.6 buscó `Country Code` duplicado *dentro de una misma hoja* (36 casos encontrados, ej. Austria en `ppi_m` con dos vintages distintos bajo el mismo código) — un problema de *deduplicación intra-país*. Este hallazgo es distinto: son **dos países diferentes** con filas byte-idénticas — un problema de *contaminación inter-país* que ningún control de la auditoría original buscaba explícitamente. Queda documentado acá como una brecha de cobertura de la auditoría original, no como un error de ejecución de los controles que sí se hicieron.

## Decisión de cierre (2026-08)

Se evaluó explícitamente excluir del panel modelado las 6 series afectadas y re-correr Análisis A, contra documentar el hallazgo sin tocar el panel modelado. Se optó por **documentar, no remediar con exclusión**: el impacto ya está medido (no es una suposición) y es nulo sobre la conclusión central — el gradiente de ingreso se sostiene prácticamente igual con o sin estas series. El costo de una remediación de código (re-modelado, actualización de reportes derivados) no se justifica frente a un beneficio ya confirmado como cero. Documentado de forma prominente en `README.md` ("Limitaciones honestas") y en `notebooks/informe_completo.ipynb`, e incorporado a `reports/auditoria_integral.md` como hallazgo A.7, cerrado con esta misma decisión.

**Trabajo futuro** (no remediación de código, sino investigación externa):

1. Reportar el problema al Banco Mundial / consultar la versión más reciente del *Global Database of Inflation* por si ya fue corregido en una actualización posterior del archivo.
2. Investigar el par indeterminado (CZE/DJI) contra una fuente externa independiente (FRED, FMI/IFS) para determinar cuál de los dos países tiene la serie real — solo entonces tendría sentido corregir o excluir con confianza.
3. Ampliar el control de A.6 para que la auditoría futura incluya explícitamente comparación inter-país, no solo intra-país por código repetido.
