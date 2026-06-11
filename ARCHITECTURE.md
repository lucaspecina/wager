# WAGER — ARCHITECTURE.md
## Diseño técnico (companion de NORTH_STAR.md)

> **Qué es este documento.** El "cómo" a nivel de contratos, librerías y algoritmos. El "por qué" y el "qué" viven en `NORTH_STAR.md` — ante conflicto conceptual, manda NORTH_STAR. Se mantiene con la misma disciplina (NORTH_STAR §0): nada se borra, decisiones al Decision Log, secciones `[ESTABLE]` / `[EN DEBATE]`.
>
> **Estado**: v0.2 (2026-06-11). v0.1: spec inicial. v0.2: pirámide de validación (§13), normalización del reward por anclas (§9.1), experimentos con canal sucio (§8), certificado de recuperabilidad + proxies declarados (§7), columnas señuelo (§4), triangulación (§10). Todo lo marcado `[EN DEBATE]` se espera que cambie al contacto con el código.

---

## 1. Anatomía de un caso `[ESTABLE]`

Un caso es una carpeta autocontenida:

```
cases/<case_id>/
  world.py        # mecanismo + superficie de control + sample()  — la verdad
  sources.yaml    # fuentes observacionales: costo, n disponible, operadores aplicados
  brief.md        # narrativa + stakes + ficha técnica — lo ÚNICO que ve el agente
  battery.json    # [(peso, regime, seed), ...] — OCULTO al agente
  rivals/         # programas rivales (misma firma que world.sample) — OCULTOS
  meta.json       # operadores instalados + perillas, brechas computadas, suite,
                  # semilla de origen (si hubo), perilla de prior, certificados
```

Regla de visibilidad: el agente ve `brief.md` y el handle `env`. Todo lo demás es lado fábrica.

---

## 2. El mundo `[ESTABLE en interfaz, EN DEBATE en detalles]`

### 2.1 Interfaz

```python
class World:
    schema: list[ColumnSpec]            # observables: nombre, tipo, unidad, rango plausible
    control_surface: ControlSurface     # perillas externas declaradas + rangos + costos
    sources: dict[str, SourceSpec]      # fuentes observacionales (ver §3)

    def sample(self, regime: Regime, n: int, seed: int) -> Table
        # corre el MECANISMO LIMPIO bajo el régimen; devuelve tabla con schema exacto

# Regime = {"config": {...},      # punto de la superficie de control (do() es el caso mínimo;
#                                 #  también señales temporales, políticas condicionales)
#           "context": {...},     # condiciones no intervenibles
#           "horizon": int|None}  # para mundos dinámicos
```

### 2.2 Las tres capas

| Capa | Implementación | Trampas |
|---|---|---|
| Mecanismo | `world.py` (ecuaciones/dinámica) | Raras (heterogeneidad latente, umbrales, contaminación) |
| Canal de observación | operadores aplicados en `sources.yaml` | Frecuentes (error de medición, proxies, batch effects) |
| Proceso de muestreo | operadores aplicados en `sources.yaml` | Frecuentes (selección, survivorship, censura) |

**Invariante**: las trampas viven en las fuentes; `world.sample()` (lo que usa el scorer) es siempre el mecanismo limpio. El agente recibe vistas corrompidas vía `observe`; la corrección corre la verdad.

### 2.3 Familias de mecanismos v0 (el catálogo de motores)

| Familia | Ejemplos de instancia | Formalismo |
|---|---|---|
| SCM estático | dosis-respuesta, riesgo operativo, scoring | ecuaciones estructurales |
| Compartimental | SIR/SEIR, farmacocinética PK/PD, tanques | ODE |
| Crecimiento/saturación | logístico, Gompertz, adopción | ODE |
| Colas/servicio | M/M/k, triage hospitalario, soporte | simulación de eventos discretos |
| Feedback/regulación | termostato, mercado con ajuste de precios | ODE |

Fuente: libros de texto de modelado aplicado (epidemiología matemática, PK/PD, teoría de colas, dinámica de sistemas). **No se inventan motores: se instancian del catálogo con parámetros sampleados.** Post-v1: circuitos génicos, agent-based.

### 2.4 Piel semántica y perilla de prior

Cada mundo lleva naming + dominio + narrativa. `meta.json` registra `prior_reliability ∈ [0,1]`: correlación entre lo que un panel de LLMs frescos espera del mundo dado solo el naming, y la verdad del programa. El curriculum controla la *base rate* de sorpresa con esta perilla (NORTH_STAR §4.6, anti-contrarian).

---

## 3. Librería de operadores v0 `[EN DEBATE — lista inicial, set abierto]`

**Principio: la librería es el alfabeto, no el contenido.** Los operadores son el vocabulario interno de la fábrica para expresar estructuras epistémicas — no un temario. El solver jamás ve la taxonomía (evaluación ciega a motivos, NORTH_STAR §2.4): desde su lado solo existe un mundo cuyos datos no cierran. La diversidad fenomenológica sale del producto motor × composición × perillas × piel — el mismo operador sobre motores distintos produce superficies de datos irreconocibles entre sí; lo único compartido es la *movida* que lo detecta, y esa movida es lo que debe generalizar (E3 es la alarma si no).

**Operador** = transformación parametrizada que se aplica sobre fuentes (capas 2–3) o, raramente, sobre el mecanismo (capa 1). Firma conceptual: `apply(target, **knobs)`. Cada operador declara: capa, perillas con rangos, el malentendido canónico que induce, y su fuente histórica.

| # | Operador | Capa | Perillas principales | Malentendido que induce | Fuente minada |
|---|---|---|---|---|---|
| 1 | `confounding_por_indicacion` | muestreo | fuerza de asignación | "el tratamiento daña/cura" (espurio) | HRT/WHI; catálogos de sesgo |
| 2 | `survivorship` | muestreo | tasa + criterio de filtrado | "los sobrevivientes representan a todos" | aviones WWII; finanzas |
| 3 | `collider_seleccion` | muestreo | regla de entrada al dataset | correlaciones espurias intra-muestra | sesgo de admisión |
| 4 | `error_de_medicion` | canal | varianza, sesgo, proxy | atenuación / efectos fantasma | psicometría |
| 5 | `batch_effect` | canal | drift por lote/fecha/sitio | "señal" que es instrumento | genómica |
| 6 | `censura_informativa` | muestreo | mecanismo de dropout ligado al outcome | efectos inflados | ensayos clínicos |
| 7 | `immortal_time` | muestreo | desfase de inclusión | tratamientos "milagrosos" | farmacoepidemiología |
| 8 | `heterogeneidad_latente` | mecanismo | k subpoblaciones, proporciones, signos | efecto promedio engañoso (Simpson) | suite Mendel |
| 9 | `regime_shift` | mecanismo/canal | punto de quiebre, magnitud | extrapolar el pasado | econometría |
| 10 | `umbral_no_lineal` | mecanismo | posición y filo del threshold | linealizar lo no lineal | toxicología |
| 11 | `missingness_informativo` | canal | MNAR dependiente del valor | imputación ingenua | encuestas |
| 12 | `contaminacion_anomala` | mecanismo+muestreo | proceso espurio inyectado, tasa | alisar la anomalía como ruido | fraude, sensores — suite Snow |
| 13 | `revelacion_secuencial` | meta | qué se observa tras qué hallazgo | el plan batch pierde | brecha de adaptividad |

**Composición**: un caso instala 2–4 operadores con perillas sampleadas; las **interacciones** entre operadores (p.ej. survivorship encima de asignación confundida) producen patrones que ningún operador genera solo — es donde muere lo "de manual". **Apertura del set**: el designer puede proponer operadores nuevos como código; entran si (a) ejecutan contra ≥2 motores, (b) inducen brechas > umbral en al menos uno, (c) no duplican el archivo (similitud de firma conductual). El canal de crecimiento principal es **a demanda de semillas**: cuando la moraleja de un caso real no puede expresarse con el vocabulario actual, eso — no la imaginación — dispara la propuesta de un operador nuevo. Así la librería converge hacia "el vocabulario necesario para expresar cómo la realidad engaña a los científicos" (el Catalogue of Bias sugiere que son decenas de entradas, no miles — pero tampoco trece). Si el flujo de semillas se corta y la librería se congela, se materializa el ataque #15.

---

## 4. Generación de un caso — los dos modos `[ESTABLE]`

```
MODO CON SEMILLA (paper / informe NTSB / case study EIS / par obs→RCT / post-mortem):
  semilla → [digestion] → moraleja epistémica
          → [architect] → motor del catálogo + operadores TRASPLANTADOS de la moraleja
          → perillas + piel (anti-leak: el writer del brief NO ve batería ni rivales)

MODO SIN SEMILLA (sampleo):
  prior de la librería → motor ~ catálogo, operadores ~ composiciones plausibles,
  perillas ~ rangos, piel ~ generador de dominios
```

En ambos modos los operadores instalados quedan **declarados en `meta.json`** (jamás en el brief): rivales, batería y certificados se computan desde esa declaración — es la hoja de respuestas del examinador.

**Declarado = certificado, no = único.** La declaración no acota lo que el agente puede o debe descubrir: el agente debe modelar el mundo ENTERO, y la batería sondea todas las regiones donde los rivales discrepan — típicamente varias por caso (2–4 operadores en interacción + estructura del mecanismo: heterogeneidad, umbrales, dinámica). El crédito es graduado: entender parte de la estructura paga parte del score. Lo que la declaración habilita es la *garantía*: solo sobre lo declarado podemos derivar rivales y certificar que el caso lo testea discriminativamente. Estructura no declarada igual queda sondeada (cola de auditoría; los rivales (a)/(d) fallan donde fallan), pero sin certificado.

**Tres fuentes de generación, con roles distintos — ninguna reemplaza a las otras.**

1. **Semillas reales** (papers, NTSB, EIS, obs→RCT, post-mortems): la *autoridad sobre la estructura* — anclan el soporte de la distribución a cómo la realidad engaña de verdad. No son la fuente de volumen.
2. **Composición + perillas** (librería sobre el catálogo de motores): el *volumen* — convierten cada estructura en una familia paramétrica de mundos re-sampleables.
3. **Búsqueda del designer** (oráculo de fallas, regret sobre perillas, operadores nuevos): la *frontera* — regiones que ningún corpus documentó, en el borde de la policy actual. Mitigación activa del ataque #14 y motor de la coevolución; el modo con semilla no la veta.

**Test de contaminación (obligatorio para casos con semilla investigativa).** Las semillas famosas viven en el pretraining del solver: el riesgo es que recupere la moraleja de memoria sin investigar (viola la invariante "forzar investigación"). El instrumento ya existe: si el rival (c) *prior evocado* — compilado por un panel fresco desde brief+schema, sin datos — ya contiene la estructura de la trampa (brecha de prior ≈ 0), el caso NO certifica como investigativo: se re-skinea, se re-estructura, o se clasifica en el bucket confirmatorio del curriculum. **Práctica por defecto para semillas conocidas: trasplante cruzado de dominio** — la moraleja "el tratamiento se daba a los más graves" (medicina) expresada en un mundo de colas ("los upgrades se daban a los servidores más cargados"): conserva la estructura del engaño, destruye la recuperabilidad por memoria, y testea exactamente la abstracción que queremos entrenar.

**Sesgo del propio corpus de semillas (declarado).** El archivo del error documentado tiene survivorship: solo contiene los engaños que alguien detectó, en campos que se auto-auditan (medicina, aviación). Las trampas que engañan para siempre, o las de campos sin cultura de auditoría, no están — por eso la fuente 3 es irreemplazable. **Métrica de salud del pipeline de semillas: tasa de novedad estructural** — fracción de semillas nuevas que exigen un operador o una composición no vista. Si colapsa, el stream está agotado y el peso de generación migra a búsqueda.

El principio de SREG sobrevive en todas las fuentes: *el caso real inspira la estructura del engaño; el mundo es nuevo*.

**Columnas señuelo (anti-leak de esquema).** El esquema lo elige quien conoce la trampa → es un canal de leak no auditado: una columna `fecha_de_entrada_a_cohorte` susurra immortal time. Reglas: los esquemas se samplean de plantillas por dominio con independencia de las trampas instaladas, y todo mundo lleva columnas plausibles e irrelevantes. El probe del generador (§14) se extiende al nivel esquema.

Pipeline completo: semilla? → digestion → architect (motor+operadores+perillas) → piel → compilación (`world.py` + `sources.yaml`) → **rivales (§5)** → **batería (§6)** → brechas/certificados (§7) → validación → brief (writer ciego).

---

## 5. Rivales — semántica precisa `[ESTABLE en concepto]`

Rival = programa con la **misma firma** `sample(regime, n, seed)` que encarna una creencia equivocada-pero-tentadora. Principio: **el rival se deriva, no se escribe** — cero autoría por caso.

| Receta | Construcción (automática) | Creencia que encarna |
|---|---|---|
| (a) `ajuste_ingenuo` | fit generativo flexible (p.ej. condicionales por columna con GBM/mixturas) sobre los datos corrompidos agregados de las fuentes | "los datos dicen lo que parecen decir" — hereda TODAS las trampas juntas |
| (b) `gemelo_inocente` (uno por operador instalado) | esqueleto mecanístico de la verdad, operador T removido de las fuentes, parámetros libres re-ajustados para reproducir los datos corrompidos observados | "no vi la trampa T: ese patrón es mecanismo real" |
| (c) `prior_evocado` | panel de k LLMs frescos ve SOLO brief+schema (sin datos) → describe el mecanismo esperado → se compila a programa; se usa el consenso | "el libro de texto tiene razón" — necesario para mundos move 37 |
| (d) `escalera_de_capacidad` | {lineal → GAM → boosting → red} fit a los datos accesibles bajo presupuesto estándar | fuerza bruta sin mecanismo, en niveles crecientes — malentendidos descubiertos por búsqueda (mitiga el techo de lo comprensible, ataque #14) |

Cobertura imperfecta de rivales = ataque #13: se amortigua con la cola de auditoría de la batería y (futuro, OQ#11) generación adversarial de rivales.

---

## 6. Batería — algoritmo `[ESTABLE en estructura, EN DEBATE en números]`

```
1. CANDIDATOS: sampler por familia de superficie de control
   (~10^3 regímenes; ~20% off-support / combinaciones fuera del rango histórico)
2. DESACUERDO: para cada r: disagreement(r) = media de D entre pares de
   {verdad, rivales} con n_mc muestras
3. RELEVANCIA: stakes_relevance(r) declarada desde el brief
   (variables de decisión y rangos de interés, en meta.json)
4. PESO: w(r) ∝ stakes_relevance(r) × disagreement(r); normalizar
5. SELECCIÓN: top-K (~160) + cola de auditoría (~40 uniformes, peso bajo)
6. PERSISTIR: battery.json = [(w, r, seed)]
```

Forma de la batería como dial de tipo de caso: concentrada en decisiones (casos con cliente) ↔ plana y ancha (system mapping). Las dos muertes (NORTH_STAR §4.4): angosta → examen cerrado; uniforme → la trivia diluye.

---

## 7. Certificados por caso (computados en design time) `[ESTABLE]`

| Certificado | Cómputo | Umbral go/no-go |
|---|---|---|
| Brecha mecanística | score(estrategia mecanística de referencia) − score(rival (a)/(d) mejor) | > umbral |
| Brecha de prior | D(rival (c), verdad) sobre la batería, condicionada a recuperable con presupuesto | según suite |
| Brecha de adaptividad | score(política secuencial greedy-EIG) − score(mejor diseño batch) | > 0 si el caso pretende entrenar el loop |
| Brecha de teoría | score(sin restricción) − score(mejor modelo sin estado latente) | > 0 en suite Mendel |
| Carga diferencial | ≥2 de: verificador ruidoso / objetivo oculto / canal sesgado / sondas caras | obligatorio |
| Validez | el mundo corre; los fenómenos declarados se materializan (validators) | obligatorio |
| Recuperabilidad | fracción de la estructura identificable con el acceso/presupuesto dado (estimada vía oráculo/ensembles) | declarada por caso; la batería la refleja — anti-degeneración "solo abstención" |

**Proxies computables (declarados).** "Mejor estrategia mecanística" se aproxima en v0 por **S_verdad** (score de entregar `world.py` mismo — el techo de ruido de muestreo; sobreestima el headroom alcanzable, y eso se declara) o por re-fit del esqueleto verdadero con datos limitados al presupuesto. "Mejor política secuencial" (adaptividad) requiere un diseñador greedy-EIG por formalismo — maquinaria v0 de alcance acotado. Cada brecha publica su proxy y su sesgo.

---

## 8. Episodio — harness `[ESTABLE en protocolo]`

- **Runtime**: kernel Jupyter persistente (patrón ya probado en SREG); objeto `env` inyectado; Python libre entre llamadas.
- **Opacidad**: el mundo corre server-side (proceso/contenedor separado); `env` es un cliente RPC. El agente no puede leer `world.py` ni la batería. Requisito duro (ataque #7).
- **Verbos** (protocolo universal; argumentos declarados por mundo):
  - `env.describe()` — gratis: brief, schema, fuentes+costos, superficie de control, presupuesto restante.
  - `env.observe(source, n)` — debita según `sources.yaml`; devuelve vista corrompida por los operadores de esa fuente.
  - `env.experiment(design)` — caro; `design` = {población, regla de asignación (incl. condicional/estratificada), configuración de superficie, horizonte, qué medir}. **El experimento esquiva el proceso de muestreo de las fuentes históricas (eso es lo que compra la aleatorización) pero NUNCA el canal de medición** — el termómetro sigue siendo el mismo termómetro. Operadores opcionales de imperfección experimental (non-compliance, attrition, error del instrumento) con perilla habilitan el trade-off **barato-y-sucio vs caro-y-limpio**: auditar el propio experimento es parte del juicio; el experimento perfecto entrenaría el anti-skill "el RCT es palabra santa".
  - `env.submit(code)` — terminal tras validación de humo.
- **Criterio de admisibilidad de verbos nuevos**: ejecutable determinísticamente desde la declaración del mundo. Extensiones candidatas: `buy_instrument` (revela columnas ocultas), `consult` (NL generado DESDE el programa — dirección formal→NL, segura).
- **Mundos observacionales** (suite Kepler): `experiment` ausente del menú; la superficie es elección de población/época/instrumento.
- **Ledger**: episodio termina por submit o quiebra. Ratio presupuesto/complejidad: dial central del curriculum.

### Validación de humo en submit (no es scoring)
3 regímenes públicos triviales: columnas exactas, tipos, n, timeout, sin red. Falla → error devuelto, episodio sigue abierto.

### Semántica de bordes
Key de régimen ignorada = claim implícito de no-efecto (la batería lo cotiza). Crash/NaN en un ítem → D_MAX capeado en ese ítem. Seeds apareados + m repeticiones por ítem (varianza del reward).

---

## 9. Scoring — implementación `[EN DEBATE en elección de D y λ]`

```python
def score(submission, world, battery, lam):
    fid = 0.0
    for w, regime, seed in battery:
        real = world.sample(regime, n=1000, seed=seed)
        pred = run_sandboxed(submission, regime, n=1000, seed=seed)   # crash → D_MAX
        fid -= w * energy_distance(standardize(real), standardize(pred))
    return fid - lam * mdl(submission)        # mdl v0 = len(zlib.compress(code))
```

- `D` default: **energy distance** (basada en muestras, propia). Alternativas en evaluación: MMD, CRPS por marginales. Estandarización por columna con estadísticas de la verdad.
- Ensemble: `[(peso, code)]` → D sobre la mezcla muestreada según pesos.
- `λ` calibrado empíricamente sobre la suite E1 para que MDL pese 5–10% del rango de score.
- **Differential testing**: búsqueda (random restarts / CEM) de `r* = argmax D(submission, world)` — auditoría y engrosamiento de batería.
- **PROHIBIDO**: cualquier salida de LLM en este cómputo (NORTH_STAR §2.2).

### 9.1 Normalización del reward entre mundos (obligatoria para RL)

La distancia cruda depende de dimensionalidad, escala de ruido y composición de la batería — scores de mundos distintos NO son comparables, y RL sobre escala caótica rompe la advantage estimation. Anclar con los rivales, que ya se computan para los certificados:

```
R = clip( (S_agente − S_ingenuo) / (S_verdad − S_ingenuo), 0, 1 )
```

`S_verdad` = score de entregar `world.py` mismo (techo: solo ruido de muestreo); `S_ingenuo` = score del rival (a). Beneficios: rewards comparables entre mundos, brechas adimensionales, dificultad interpretable. Caso borde: `S_verdad − S_ingenuo ≈ 0` → el mundo no discrimina → se rechaza (equivale a brecha mecanística ≈ 0).

### 9.2 Detalles de contrato que importan

- **Piso de varianza**: el apareamiento de seeds alinea el lado del mundo pero NO la aleatoriedad interna de la maqueta del agente → varianza irreducible que solo bajan las m repeticiones (costo total de scoring: K × n × m por episodio; medir CV en el primer slice).
- **Techo de tiempo por llamada** de `model()`: una maqueta lenta multiplica el costo de scoring ×K.
- **MDL sobre AST minificado**, no zlib crudo (anti code-golf).
- Energy distance con columnas mixtas (categóricas + continuas): codificación declarada y fija.

---

## 10. Tipos de caso = regiones del espacio producto `[ESTABLE]`

Un caso = elección en 5 ejes: **motor × operadores × superficie × forma de batería × stakes**. Sin maquinaria por tipo — apodos de esquinas:

| Apodo (suite) | Motor | Operadores típicos | Superficie | Batería | Stakes |
|---|---|---|---|---|---|
| Causal con cliente | SCM | 1,2,6,7 | intervenible | concentrada en decisiones | cliente decide |
| Anomalías (**Snow**) | cualquiera | 12 (+5) | mixta | consecuencias de la contaminación | "algo anda mal, ¿qué?" |
| Constructos latentes (**Mendel**) | SCM/ODE | 8 | intervenible | regiones donde el promedio engaña | subtipos |
| Prior vs evidencia (**Semmelweis**) | cualquiera | cualquiera + prior_reliability baja | mixta | donde intuición y verdad chocan | move 37 |
| Observacional/forecast (**Kepler**) | ODE | 4,5,9 | solo elección de qué mirar | horizontes y contextos held-out | predecir lo no visto |
| System mapping | cualquiera | 2–3 variados | amplia | plana y ancha | sin cliente |
| Diagnóstico/causa raíz | compartimental/colas | 12 variantes | reparaciones | contrafactuales de reparación | "¿cuál proceso está activo?" |
| Identificabilidad | SCM | acceso restringido | mínima | queries no-identificables | gana el ensemble ancho honesto |

**Triangulación como patrón de primera clase** (enriquece la suite Kepler): mundos con 2–3 fuentes cuyos sesgos difieren de modo que solo cruzándolas se identifica la verdad sin experimentos — exactamente cómo identifica la ciencia observacional real. Junto con el certificado de recuperabilidad (§7), evita que Kepler degenere en entrenar pura abstención.

---

## 11. Las tres bibliotecas minables (fuentes, no imaginación) `[ESTABLE]`

1. **Zoológico de motores**: textos de modelado aplicado — epidemiología matemática, PK/PD, teoría de colas, dinámica de sistemas, ecología cuantitativa.
2. **Biblioteca del error científico** (→ operadores): Catalogue of Bias (Oxford, ~60 entradas documentadas), el catálogo clásico de Sackett (1979), taxonomías de sesgo de epidemiología, literatura de discrepancias observacional-vs-RCT, Retraction Watch, post-mortems de replicación.
3. **Archivo de investigaciones resueltas** (→ semillas para digestion): informes NTSB (mecanismo adjudicado por investigación formal), case studies de brotes EIS/CDC (investigaciones didácticas con respuesta conocida), post-mortems de incidentes SRE, pares obs→RCT (también eval E4).

El designer LLM solo *propone* (operadores nuevos, composiciones); ejecución + brechas + archivo *deciden*.

---

## 12. Lo mínimo para E1 `[ESTABLE]`

Contenedor de casos (§1) + harness (§8) + scorer (§9) + constructor de batería (§6, puede ser semiautomático al principio) + **~20 mundos hechos a mano** en 2 familias (SCM + un ODE), cubriendo ≥5 suites, con certificados computados. Sin designer automático, sin RL, sin operadores abiertos. Modelos frontier vía API + las 3 manipulaciones de constructo de NORTH_STAR §6-E1.

---

## 13. Validación de la maquinaria — la pirámide `[ESTABLE]`

La escalera E1→E4 (NORTH_STAR §6) valida constructo e hipótesis; estos niveles validan que la maquinaria mide algo *antes*:

- **L0 — Tests de contrato**: unidades/semántica de regímenes entre mundo y maqueta (un error de escala que no crashea es un corruptor mudo); **sandbox red-team** (tests que intentan activamente leer `world.py`/`battery.json` desde el episodio y desde la submission, y deben fallar); **test de CI cero-LLM en el reward path** (el build falla si se viola).
- **L1 — Escalera de verdades degradadas** (aceptación obligatoria por mundo, automática): se scorea una secuencia de submissions de calidad conocida decreciente — `world.py` exacto → verdad con parámetros perturbados → verdad con un mecanismo ablado → gemelo inocente → ajuste ingenuo → modelo nulo — y el score DEBE ordenarlas con márgenes declarados. Si no las ordena, la batería de ese mundo está rota. Es el certificado de monotonía y el detector automático de rivales débiles (ataque #13).
- **L2 — Protocolo de varianza del reward**: la misma submission scoreada R veces → CV objetivo declarado; medir en el primer slice y ajustar K, n, m hasta cumplirlo. Sin esto, RL aprende ruido.
- **L3 — E1** (instrumento): NORTH_STAR §6 — incluye mundos de control, baseline humano, auditoría humana de baterías, validez convergente/discriminante externa.
- **L4 — E2/E3** (entrenamiento y abstracción). **L5 — E4** (transfer real).

## 14. Open items técnicos

1. Sampler de regímenes candidatos por familia de superficie (hereda OQ#1 de NORTH_STAR — punto de presión #1).
2. Arquitectura RPC del handle opaco sin matar latencia del REPL.
3. Gramática de `design` en `experiment` por familia (describe el experimento, no creencias).
4. n_mc, K, m y n de scoring para varianza de reward objetivo (<x% del rango).
5. Fit generativo del rival (a): elección de la familia condicional.
6. Re-ajuste de parámetros del gemelo inocente (b): procedimiento estándar.
7. Compilación del prior evocado (c): prompt del panel + agregación.
8. MDL: alternativas a zlib (AST, parámetros); sensibilidad de λ.
9. Prompts de manipulación de constructo para E1 (descuidado / prolijo / base) — necesarios para la predicción 2 de E1.
10. Oráculo de valor v0 (EIG greedy por Monte Carlo sobre los 20 mundos a mano) — necesario para la predicción 3 de E1; las predicciones 1–2 pueden correr antes.
11. Probe "aprendió al generador": clasificador que intente predecir el operador instalado desde el brief/datos superficiales — alarma complementaria a E3 contra tells del generador.
12. Pipeline de minado de semillas: formato de la cola (NTSB/EIS/obs→RCT), criterios de priorización, y el trigger "moraleja inexpresable → operador nuevo".
13. Diseñador greedy-EIG por formalismo: maquinaria compartida entre proxy de adaptividad (§7) y oráculo de valor v0 — definir alcance mínimo.
14. Márgenes de la escalera de verdades degradadas (L1) y CV objetivo (L2): valores iniciales y procedimiento de ajuste.
