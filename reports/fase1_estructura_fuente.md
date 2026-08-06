# Fase 1 — Entender la fuente (Inflation-data.xlsx)

Informe generado programáticamente por `src/fase1_entender_fuente.py` a partir de `data/raw/Inflation-data.xlsx`. No editar a mano: si algo cambia, se corre el script de nuevo.

## 1. Inventario de las 20 hojas

El workbook tiene 20 hojas.

| Hoja | Medida | Frecuencia | Filas | Columnas | Indicator Type dominante |
|---|---|---|---|---|---|
| Intro | *(no es hoja de datos país x fecha)* | | | | |
| top | *(no es hoja de datos país x fecha)* | | | | |
| hcpi_m | hcpi (Headline CPI — índice de precios al consumidor general) | mensual | 186 | 670 | 'Index' |
| hcpi_q | hcpi (Headline CPI — índice de precios al consumidor general) | trimestral | 204 | 227 | 'index' |
| hcpi_a | hcpi (Headline CPI — índice de precios al consumidor general) | anual | 205 | 61 | 'Inflation' |
| ecpi_m | ecpi (Energy CPI — índice de precios de energía) | mensual | 202 | 1240 | 'Index' |
| ecpi_q | ecpi (Energy CPI — índice de precios de energía) | trimestral | 136 | 228 | 'index' |
| ecpi_a | ecpi (Energy CPI — índice de precios de energía) | anual | 174 | 61 | 'Inflation' |
| fcpi_m | fcpi (Food CPI — índice de precios de alimentos) | mensual | 155 | 671 | 'Index' |
| fcpi_q | fcpi (Food CPI — índice de precios de alimentos) | trimestral | 169 | 229 | 'index' |
| fcpi_a | fcpi (Food CPI — índice de precios de alimentos) | anual | 184 | 61 | 'Inflation' |
| ccpi_m | ccpi (Core CPI — índice de precios subyacente (sin energía/alimentos)) | mensual | 83 | 670 | 'Index' |
| ccpi_q | ccpi (Core CPI — índice de precios subyacente (sin energía/alimentos)) | trimestral | 80 | 228 | 'index' |
| ccpi_a | ccpi (Core CPI — índice de precios subyacente (sin energía/alimentos)) | anual | 113 | 61 | 'Inflation' |
| ppi_m | ppi (PPI — índice de precios al productor) | mensual | 106 | 671 | 'Index' |
| ppi_q | ppi (PPI — índice de precios al productor) | trimestral | 108 | 642 | 'index' |
| ppi_a | ppi (PPI — índice de precios al productor) | anual | 114 | 61 | 'Inflation' |
| def_q | def (GDP deflator — deflactor del PIB) | trimestral | 98 | 228 | 'index' |
| def_a | def (GDP deflator — deflactor del PIB) | anual | 198 | 60 | 'Rate' |
| Aggregate | *(no es hoja de datos país x fecha)* | | | | |

`Intro`, `top` y `Aggregate` no son paneles país x fecha: `Intro` es portada/notas, `top` es una tabla de metadatos de navegación del propio workbook, y `Aggregate` trae series ya agregadas (medianas/promedios globales y regionales) fuera de alcance de este ETL, que trabaja a nivel país.

### Confirmación: `_m`/`_q` = Index, `_a` = Inflation

- ✅ `hcpi_m`: dominante = 'Index' (esperado, case-insensitive: 'Index')
- ✅ `hcpi_q`: dominante = 'index' (esperado, case-insensitive: 'Index')
- ✅ `hcpi_a`: dominante = 'Inflation' (esperado, case-insensitive: 'Inflation')
- ✅ `ecpi_m`: dominante = 'Index' (esperado, case-insensitive: 'Index')
- ✅ `ecpi_q`: dominante = 'index' (esperado, case-insensitive: 'Index')
- ✅ `ecpi_a`: dominante = 'Inflation' (esperado, case-insensitive: 'Inflation')
- ✅ `fcpi_m`: dominante = 'Index' (esperado, case-insensitive: 'Index')
- ✅ `fcpi_q`: dominante = 'index' (esperado, case-insensitive: 'Index')
- ✅ `fcpi_a`: dominante = 'Inflation' (esperado, case-insensitive: 'Inflation')
- ✅ `ccpi_m`: dominante = 'Index' (esperado, case-insensitive: 'Index')
- ✅ `ccpi_q`: dominante = 'index' (esperado, case-insensitive: 'Index')
- ✅ `ccpi_a`: dominante = 'Inflation' (esperado, case-insensitive: 'Inflation')
- ✅ `ppi_m`: dominante = 'Index' (esperado, case-insensitive: 'Index')
- ✅ `ppi_q`: dominante = 'index' (esperado, case-insensitive: 'Index')
- ✅ `ppi_a`: dominante = 'Inflation' (esperado, case-insensitive: 'Inflation')
- ✅ `def_q`: dominante = 'index' (esperado, case-insensitive: 'Index')
- ✅ `def_a`: dominante = 'Rate' (esperado, case-insensitive: 'Inflation')

**Confirmado con una excepción de etiqueta:** todas las hojas `_m`/`_q` tienen 'Index'/'index' como tipo dominante y todas las `_a` de CPI/PPI tienen 'Inflation' como tipo dominante. La única desviación es `def_a`, que usa la etiqueta 'Rate' en vez de 'Inflation' — mismo significado (tasa anual, no índice), pero el string difiere, así que un chequeo `== 'Inflation'` literal fallaría para `def_a`.

## 2–3. Hallazgo crítico: las hojas mensuales NO son homogéneas

Cada hoja mensual (`hcpi_m, ecpi_m, fcpi_m, ccpi_m, ppi_m`) debería traer únicamente filas con `Indicator Type == 'Index'`. En la práctica hay países-excepción con otro tipo. Conteo de `Indicator Type` por hoja (solo filas de país, se excluyen filas de nota/footnote sin código ISO3 válido):

**`hcpi_m`**

- 'Index': 184
- 'Inflation': 1

País-excepción encontrado (no es `'Index'` limpio):

| Código | País | Indicator Type | n valores | primeros 5 valores | interpretación |
|---|---|---|---|---|---|
| VGB | British Virgin Islands | 'Inflation' | 29 | 201501=104.59, 201502=104.32, 201503=104.71, 201504=104.77, 201505=104.82 | valores en rango 104.3–104.8: es un ÍNDICE (base ~100) pese a estar etiquetado 'Inflation' — error de metadata, no de dato. El pct_change(12) actual lo trata bien por coincidencia. |

**`ecpi_m`**

- 'Index': 198
- 'Inflation': 2

País-excepción encontrado (no es `'Index'` limpio):

| Código | País | Indicator Type | n valores | primeros 5 valores | interpretación |
|---|---|---|---|---|---|
| IDN | Indonesia | 'Inflation' | 338 | 199601=16.44, 199602=16.49, 199603=16.52, 199604=16.60, 199605=16.62 | valores en rango 16.4–16.6: son claramente una TASA (ya viene expresado en % de variación), consistente con la etiqueta 'Inflation'. Aplicarle pct_change(12) como si fuera índice es inválido. |
| IND | India | 'Inflation' | 635 | 197001=4.20, 197002=4.70, 197003=5.40, 197004=5.80, 197005=5.80 | valores en rango 4.2–5.8: son claramente una TASA (ya viene expresado en % de variación), consistente con la etiqueta 'Inflation'. Aplicarle pct_change(12) como si fuera índice es inválido. |

**`fcpi_m`**

- 'Index': 153
- Sin países-excepción. ✅

**`ccpi_m`**

- 'Index': 81
- Sin países-excepción. ✅

**`ppi_m`**

- 'Index': 104
- 'index': 1

País-excepción encontrado (no es `'Index'` limpio):

| Código | País | Indicator Type | n valores | primeros 5 valores | interpretación |
|---|---|---|---|---|---|
| AUS | Australia | 'index' | 242 | 200101=75.17, 200102=75.17, 200103=75.27, 200104=75.48, 200105=75.68 | valores en rango 75.2–75.7: es un ÍNDICE (base ~100) pese a estar etiquetado 'index' — error de metadata, no de dato. El pct_change(12) actual lo trata bien por coincidencia. |

## 4. Implicancia para el ETL

`src/01_descarga_datos.py` (versión previa a esta fase) calcula la inflación interanual con `pct_change(periods=12)` sobre la columna `indice`, asumiendo que **todas** las filas de las hojas mensuales son un índice base ~100. Eso es correcto para la inmensa mayoría de países, pero:

- Para filas cuyo `Indicator Type` real es `'Inflation'` (ej. **India** y **Indonesia** en `ecpi_m`), la columna de valores YA es una tasa de variación interanual, no un índice. Aplicarle `pct_change(12)` de nuevo calcula "la variación porcentual de una tasa", un número sin sentido económico (se verificó en el parquet actual: para India salen valores como -89.6% o -48.1%, que no son inflación interanual real — es el artefacto de tratar una tasa como si fuera un nivel).
- Para filas mal etiquetadas como `'Inflation'`/`'index'` pero que en realidad SÍ son un índice (ej. **British Virgin Islands** en `hcpi_m`, valores ~104–107 con base ~100; **Australia** en `ppi_m`, etiquetado `'index'` en minúscula), el `pct_change(12)` actual da un resultado correcto por coincidencia — el dato es un índice aunque la etiqueta diga otra cosa.

**Conclusión:** el ETL tiene que ramificar el tratamiento por `Indicator Type` real de cada fila, no asumir un único tratamiento por hoja:

1. Filas `Indicator Type` case-insensitive `'index'` → calcular YoY con `pct_change(12)`.
2. Filas `Indicator Type == 'Inflation'` cuyos valores están en escala de índice (ver columna "interpretación" arriba) → tratar igual que (1), el error está en la etiqueta, no en el dato.
3. Filas `Indicator Type == 'Inflation'` cuyos valores ya están en escala de tasa (India, Indonesia en ecpi_m) → usar el valor directamente como `inflacion_yoy`, sin recalcular, y dejar `indice` en NaN o marcarlo como no aplicable.

## 5. Medidas por frecuencia

| Medida | Mensual | Trimestral | Anual |
|---|---|---|---|
| hcpi | ✅ | ✅ | ✅ |
| ecpi | ✅ | ✅ | ✅ |
| fcpi | ✅ | ✅ | ✅ |
| ccpi | ✅ | ✅ | ✅ |
| ppi | ✅ | ✅ | ✅ |
| def | — | ✅ | ✅ |

**`def` (GDP deflator) no tiene hoja mensual** — solo existe `def_q` (trimestral) y `def_a` (anual). No hay forma de incluirlo en un panel mensual sin resamplear/interpolar desde trimestral, lo cual es un tratamiento distinto al de los otros 5 indicadores y queda fuera de alcance del ETL mensual actual (`01_descarga_datos.py` usa 5 indicadores, no 6).
