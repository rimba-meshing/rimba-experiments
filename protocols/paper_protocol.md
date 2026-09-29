### 1. Tabla principal

Una fila por dataset y secuencia, procesando el intervalo completo definido para cada experimento. No se usarán prefijos como filas. Modo de máximo rendimiento: pre-scan + polyline

Datasets previstos:

- MaiCity, secuencia 01;
- KITTI, secuencia 07;

Usaremos una única configuración de referencia, elegida después de la ablación.

Para cada fila:

- número de frames evaluados;
- tiempo total;
- tiempo medio por frame;
- distribución del tiempo por frame;
- memoria máxima de GPU;
- memoria máxima de CPU;
- número final de vértices;
- número final de caras;
- tamaño del resultado exportado.

La frontera temporal debe mantenerse fija: excluir carga del dataset y escritura final del PLY, pero incluir transferencias, ejecución GPU, sincronización, descarga final y construcción host-side.

### 2. Calidad geométrica y topológica

En MaiCity medir:

- precision;
- recall;
- F-score;

Usar el protocolo modificado de TanksAndTemples empleado por SLAMesh/CAD-Mesher
y mantenido en el fork `RuanJY/TanksAndTemples`.

La entrada de la evaluación es MaiCity secuencia 01. La referencia
independiente se construye acumulando MaiCity secuencia 02 (320 haces) con sus
poses del dataset. No se hace alineamiento de trayectoria ni registro ICP:
ambas nubes ya se consideran expresadas en el marco global del dataset.

El evaluador fija `tau = 0.10 m`, muestrea uniformemente `6,553,600` puntos de
la malla, aplica voxelización de `0.05 m` (`tau / 2`) en ambas nubes y calcula
precision reconstrucción→referencia, recall referencia→reconstrucción y su
media armónica F1. También conserva las nubes coloreadas de precisión/recall y
la curva PR para las figuras de error.

- generar mapas espaciales de calor separados para precision y recall sobre las
  nubes correspondientes. El F1 se reporta como métrica global; no se generará
  un mapa local de F1, porque requeriría definir una agregación espacial y unas
  correspondencias adicionales que no forman parte del protocolo.

### 3. Figuras cualitativas

La figura cualitativa es importante y debería mostrar:

- la reconstrucción completa;
- el mismo punto de vista para todos los métodos;
- la misma escala;
- varias ampliaciones;
- bordes y zonas de stitching;
- oclusiones;
- estructuras finas;
- zonas donde el polyline proxy modifique la geometría.

La figura de errores debe estar separada o claramente diferenciada de esta figura visual.

### 4. Tiempos por etapa

Para MaiCity 01 y KITTI 07, conviene medir las etapas siguientes:

- preparación del scan;
- proyección a range image;
- procesamiento de la profundidad acumulada;
- construcción de vértices;
- generación del mesh denso;
- stitching de fronteras;
- construcción del polyline proxy;
- transferencias CPU-GPU;
- sincronizaciones;
- esperas del scheduler;
- materialización final en CPU.

Estas medidas sirven para explicar el resultado, pero no deben sustituir al tiempo end-to-end. Las mediciones instrumentadas pueden introducir sincronizaciones adicionales.

### 5. Escalabilidad temporal y de memoria

Aquí sí interesa sacar gráficas donde cada tick del eje X es un frame (un índice) del frame.

Para cada frame se mide:

- tiempo del frame;
- memoria GPU máxima;
- memoria CPU máxima;
- memoria persistente del mesh;
- tiempos de cada etapa
- etapa que se convierte en dominante;

Estas gráficas deben mostrar si la ventaja del solapamiento se mantiene o desaparece cuando crecen la profundidad acumulada, la frontera topológica o la memoria utilizada.


### 7. Ablación del scheduler

Las tres configuraciones serán:

1. `none`, sin solapamiento;
2. `pre-scan`;
3. `pre-scan + polyline`.

Para cada dataset y secuencia hay que medir:

- tiempo total y tiempo por frame;
- tiempo de espera del consumidor;
- tiempo de preparación;
- tiempo de sincronización;
- tiempo de construcción del proxy;
- memoria GPU y CPU;
- número de vértices y caras;
- caras válidas;
- cambios respecto a `none`;
- métricas geométricas de MaiCity.

### 8. Comparación con otros métodos

Hay que intentar comparar con métodos externos

Para cada método comparable:

- mismo hardware;
- misma secuencia;
- mismas poses, si es posible;
- tiempo total y por frame;
- memoria;
- tamaño del mesh;
- vértices y caras;
- métricas geométricas;
- mapas de precision y recall en MaiCity.

En conjunto, los resultados deben permitir responder a cuatro preguntas:

1. ¿Reduce el scheduler el tiempo end-to-end?
2. ¿Qué coste tiene en memoria y escalabilidad?
3. ¿Cambia la geometría o la topología?
4. ¿Dónde acierta y dónde falla respecto a otros métodos?

La estructura de resultados prevista corresponde a estas preguntas y métricas.

### Automatización reproducible

El lanzador principal es `tools/run_paper_protocol.py`. Configura y compila
tres variantes CUDA directamente desde el submódulo `rimba`, detecta de forma
automática el intervalo completo disponible en cada secuencia, ejecuta la
tabla principal y la ablación del scheduler, toma pasadas separadas de memoria,
guarda tiempos por frame y por etapa, y deja plantillas para calidad, figuras
cualitativas y métodos externos.

Antes de una ejecución real se puede inspeccionar todo con:

```bash
python3 tools/run_paper_protocol.py --dry-run \
  --output results/paper_protocol/dry-run
```

La ejecución completa se lanza con:

```bash
python3 tools/run_paper_protocol.py \
  --output results/paper_protocol/$(date +%Y%m%d_%H%M%S)
```

Por defecto usa MaiCity `01` y KITTI `07`, desde el primer hasta el último
`.bin` contiguo, `3` warm-up runs y `10` runs medidos para throughput. La
configuración de referencia es `coarsened`, macroceldas de hasta `16x16`,
error máximo `0.08 m`, soporte acumulado, `pre-scan + polyline`, área máxima
de hole filling de `50 pixel^2` y radio de culling de `70 m`. La variante
`none` desactiva también el proxy; `pre-scan` lo deja desactivado; y la
tercera variante activa el proxy polyline fijado por el código actual.

La memoria se mide en dos pasadas separadas. La pasada detallada
usa una compilación separada con instrumentación de memoria y una configuración
secuencial, porque sus snapshots inspeccionan metadatos de vectores que podrían
ser modificados por el worker asíncrono. El binario emite `memory.stage` en los
límites de las fases principales, con RSS, memoria lógica, capacidades de
buffers host/device, acumulación y `cudaMemGetInfo`. Cada snapshot incluye
`pass_kind` (`warmup` o `measured`) y `run_index`, por lo que las pasadas no se
mezclan durante el análisis.

La pasada coarse usa el binario benchmark normal y repite las tres variantes
reales (`none`, `pre-scan` y `pre-scan + polyline`). Se ejecuta fuera de la
medición de throughput y recoge el máximo RSS mediante `/usr/bin/time -v` y
muestras de NVML cada `0.05 s`, filtradas por el árbol de procesos del PID
lanzador. Esto cubre el hijo real `ri_meshing` cuando la ejecución está
envuelta por `/usr/bin/time`. Es una medición de pico aproximada y puede
perder asignaciones muy breves, pero no cuenta la memoria de otros procesos de
la GPU y sí refleja el scheduler real.
`--no-sample-gpu-memory` permite desactivar esas muestras explícitamente.

Los timings por etapa se ejecutan como diagnóstico en una compilación Release:
`instrumented` con solape y `detailed` secuencial; no deben sustituir al tiempo
end-to-end de la tabla principal.
Para evitar carreras al inspeccionar capacidades de `thrust::device_vector`,
el binario de memoria fuerza deliberadamente el scheduling secuencial; por
tanto esta pasada mide el crecimiento de las estructuras del algoritmo, no el
pico adicional de dos prefijos concurrentes.

Los resultados quedan en `results.csv`, `frame_metrics.csv`,
`run_timings.csv`, `throughput_stats.csv`, `throughput_comparisons.csv`,
`stage_timings.csv`, `stage_summary.csv`, `scheduler_timeline.csv`,
`memory_stages.csv`, los logs y los comandos exactos. Las tablas compactas se
derivan posteriormente durante el análisis y no las genera el protocolo. La
evaluación Tanks and Temples se ejecuta si se proporciona
`--quality-ground-truth` (o la variable `RI_MAICITY_GROUND_TRUTH`) y existe un
PLY retenido de MaiCity. El script general llama a
`tools/evaluate_maicity_tnt.py`, que carga directamente el `run_evaluation()`
del fork y evita el argumento histórico `--traj-path`, ya que la variante RuanJY
no usa trayectoria ni registro. Si no se proporciona la referencia,
`quality.csv` registra explícitamente que la pasada está pendiente.

### Estadística de las repeticiones

El ejecutable conserva una muestra por cada repetición interna, después de los
warm-ups, mediante las líneas `Measured run N call time`. Esas muestras miden
la llamada multi-frame completa sin I/O del dataset ni escritura del PLY. El
protocolo las guarda sin promediar en `run_timings.csv` y calcula en
`throughput_stats.csv`:

- media y desviación estándar muestral entre ejecuciones;
- desviación estándar expresada en ms/frame;
- IC bilateral del 95 % de la media usando Student-t (`n-1` grados de libertad).

Los frames no se consideran muestras independientes: sólo hay diez observaciones
por configuración en el protocolo de throughput. `throughput_comparisons.csv`
compara cada variante contra `scheduler_none` usando Welch para la diferencia
de medias. La reducción porcentual y su intervalo se derivan de ese intervalo
de diferencia manteniendo fija la media observada del baseline; el campo está
marcado como derivado para no confundirlo con un diseño emparejado.

El protocolo conserva un JSON y un CSV de muestras por configuración, además
de las tablas agregadas descritas arriba.

Para reparar una ejecución existente sin repetir el mallado, se puede usar
`--resume --skip-build --refresh-coarse-memory` sobre la misma carpeta de
artefactos. Esto conserva throughput, memoria detallada y timings ya
registrados, reemplaza únicamente las filas de memoria coarse —incluyendo sus
muestras NVML— y vuelve a ejecutar la calidad geométrica sobre los PLY
retenidos. Es útil si una versión anterior del sampler o del wrapper produjo
datos inválidos.

Ejemplo standalone:

```bash
python3 tools/evaluate_maicity_tnt.py \
  --ground-truth /path/to/maicity_sequence02_global.ply \
  --mesh results/paper_protocol/.../meshes/maicity_reference_pre_scan_polyline_throughput.ply \
  --output results/paper_protocol/.../quality/maicity_tnt/reference_pre_scan_polyline
```

Ejemplo integrado en el protocolo general:

```bash
RI_MAICITY_GROUND_TRUTH=/path/to/maicity_sequence02_global.ply \
python3 tools/run_paper_protocol.py \
  --keep-ablation-meshes \
  --output results/paper_protocol/$(date +%Y%m%d_%H%M%S)
```

Las figuras cualitativas y la comparación con métodos externos requieren
selección manual de cámara o reproducción controlada, por lo que el script
deja sus entradas y una plantilla sin rellenar automáticamente.
