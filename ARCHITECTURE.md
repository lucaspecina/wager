# WAGER — ARCHITECTURE.md
## Diseño técnico (companion de NORTH_STAR.md)

> **Qué es este documento.** El "cómo" a nivel de contratos, librerías y algoritmos. El "por qué" y el "qué" viven en `NORTH_STAR.md` — ante conflicto conceptual, manda NORTH_STAR. Se mantiene con la misma disciplina (NORTH_STAR §0): nada se borra, decisiones al Decision Log, secciones `[ESTABLE]` / `[EN DEBATE]`.
>
> **Estado**: v0.5 (2026-06-11). v0.1: spec inicial. v0.2: pirámide de validación (§13), normalización del reward por anclas (§9.1), experimentos con canal sucio (§8), certificado de recuperabilidad + proxies declarados (§7), columnas señuelo (§4), triangulación (§10). v0.3: decisiones pre-Slice 1 (Decision Log de NORTH_STAR v0.10) — semántica de seeds y pseudocódigo del scorer corregido (§9), anclas con función completa + serialización canónica del rival (a) (§9.1), MDL AST-min→zlib + ensembles por concat canónico (§9.2), D_MAX_item (§8), acceso a datos de rivales (a)/(d) (§5), stakes en `meta.json` (§6), L1 monotonía-por-eje + valores iniciales L1/L2 (§13), lint de imports en humo y en `world.py` (§8), fuentes con plantillas neutrales (§4). v0.4: regla de capa de operadores (asignación = mecanismo, §3). v0.5: hallazgos del Slice 1 — D_MAX solo en crash + referenciado al null model (§8), márgenes L1 en unidades de R / rango S_verdad−S_ingenuo (§9.1, §13). Todo lo marcado `[EN DEBATE]` se espera que cambie al contacto con el código.

---

## 1. Anatomía de un caso `[ESTABLE]`

Un caso es una carpeta autocontenida:

```
cases/<case_id>/
  world.py        # mecanismo + superficie de control + sample()  — la verdad
  sources.yaml    # fuentes observacionales: costo, n disponible, operadores aplicados
  brief.md        # narrativa + stakes + ficha técnica — lo ÚNICO que ve el agente
  battery.json    # [(peso, regime, seed_mundo), ...] — OCULTO al agente
                  #   (los seeds lado-maqueta se derivan: derive_seed(seed_mundo, j), §9)
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
| 1 | `confounding_por_indicacion` | mecanismo (asignación) / muestreo (selección) | fuerza de asignación | "el tratamiento daña/cura" (espurio) | HRT/WHI; catálogos de sesgo |
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

**Regla de capa (v0.4)**: la capa de un operador la define el **proceso que lo encarna**, no su nombre. `confounding_por_indicacion` es de **mecanismo** cuando la asignación del tratamiento es un proceso del mundo — el tratamiento lleva ecuación estructural propia (`D := g(S) + ruido`) que `do()` reemplaza, semántica SCM estándar — y de **muestreo** solo cuando el confounding lo induce la selección del dataset (tipo collider). Consecuencia: `world.sample()` bajo régimen observacional genera la asignación natural confundida; el "mecanismo limpio" de §2.2 significa limpio de corrupciones de canal/muestreo, no sin estructura de asignación.

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

**Columnas señuelo (anti-leak de esquema).** El esquema lo elige quien conoce la trampa → es un canal de leak no auditado: una columna `fecha_de_entrada_a_cohorte` susurra immortal time. Reglas: los esquemas se samplean de plantillas por dominio con independencia de las trampas instaladas, y todo mundo lleva columnas plausibles e irrelevantes. El probe del generador (§14) se extiende al nivel esquema. **Mismo tratamiento para las fuentes (v0.3)**: los nombres y descripciones de fuentes (lo que muestra `env.describe()`) se generan desde plantillas neutrales por el mismo proceso ciego — una fuente llamada `registro_de_sobrevivientes` susurra la trampa igual que una columna delatora — y el probe del generador se extiende también a nombres y descripciones de fuentes.

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

**Acceso a datos de los rivales por ajuste (v0.3).** Los rivales (a) y (d) ajustan sobre el pool observacional COMPLETO de todas las fuentes (n máximo declarado en `sources.yaml`, cero experimentos) — ancla fuerte y reproducible; el certificado de brecha mecanística ya rechaza los mundos donde ese acceso alcanza. El fit es seeded, y el rival (a) se persiste con **serialización canónica declarada**: su MDL entra en el ancla S_ingenuo (§9.1) y debe ser estable, o el ancla baila con decisiones de serialización.

Cobertura imperfecta de rivales = ataque #13: se amortigua con la cola de auditoría de la batería y (futuro, OQ#11) generación adversarial de rivales.

---

## 6. Batería — algoritmo `[ESTABLE en estructura, EN DEBATE en números]`

```
1. CANDIDATOS: sampler por familia de superficie de control
   (~10^3 regímenes; ~20% off-support / combinaciones fuera del rango histórico)
2. DESACUERDO: para cada r: disagreement(r) = media de D entre pares de
   {verdad, rivales} con n_mc muestras
   (D = el MISMO score combinado del §9.3 — energía + funcionales — "un solo
    método": la batería pesa donde los rivales discrepan también en el funcional)
3. RELEVANCIA: stakes_relevance(r) declarada en meta.json por el architect
   (variables de decisión y rangos de interés; el brief la NARRA después —
    la batería se construye antes del brief y el writer sigue ciego a batería
    y rivales; v0.3 corrige la circularidad de la redacción anterior)
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
| Brecha de teoría | score(sin restricción) − score(**mejor sin-latente FLEXIBLE** de la escalera (d): mixturas / GBM condicional, no solo lineal) | > 0 en suite Mendel, **bajo score combinado** |
| **Visibilidad** (v0.26) | toda estructura instalada debe **separarse en el reward del caso**: el rung de ablación de cada operador pierde ≥ 3×CV(R) bajo el score COMBINADO | obligatorio; si tras declarar funcionales sigue invisible → rediseño o rechazo del mundo, registrado |
| Carga diferencial | ≥2 de: verificador ruidoso / objetivo oculto / canal sesgado / sondas caras | obligatorio |
| Validez | el mundo corre; los fenómenos declarados se materializan (validators) | obligatorio |
| Recuperabilidad | fracción de la estructura identificable con el acceso/presupuesto dado (estimada vía oráculo/ensembles) | declarada por caso; la batería la refleja — anti-degeneración "solo abstención" |

**Proxies computables (declarados).** "Mejor estrategia mecanística" se aproxima en v0 por **S_verdad** (score de entregar `world.py` mismo — el techo de ruido de muestreo; sobreestima el headroom alcanzable, y eso se declara) o por re-fit del esqueleto verdadero con datos limitados al presupuesto. "Mejor política secuencial" (adaptividad) requiere un diseñador greedy-EIG por formalismo — maquinaria v0 de alcance acotado. **"Mejor modelo sin estado latente" (brecha de teoría) se certifica contra el mejor sin-latente FLEXIBLE de la escalera (d)** — incluyendo aprendedores de distribución condicional flexibles (mixturas, GBM condicional), no solo el lineal/homoscedástico: un rival débil INFLA la brecha vía heteroscedasticidad (la trampa v0.18; Decision Log v0.25). Cada brecha publica su proxy y su sesgo.

**El oráculo de momentos NO es el proxy de brecha de teoría (corrección v0.27, Q4).** Responde otra pregunta — **"¿el metro VE la estructura instalada?"** — y se canoniza como **rung de DIAGNÓSTICO** que operacionaliza el certificado de Visibilidad (§13-L1): una Gaussiana con media+covarianza exactas por-régimen (unimodal) debe quedar **estrictamente por debajo de `world.py` bajo el score combinado**; si lo iguala (como bajo energía-sola: R=0.96), el funcional no captura la estructura y el mundo no es recompensable. Es control de instrumento, no rival de teoría.

**Diagnóstico permanente de fábrica — `theory_gap_probe` generalizado (v0.26/v0.27).** El probe de Mendel se canoniza como check de fábrica para todo mundo con estructura latente declarada: computa la brecha **bajo energía-sola** vs **bajo el score combinado**, con el oráculo de momentos como control de "¿el metro ve?". Divergencia grande = **bandera de punto ciego del reward**. Es también donde vive la opción (B) reclasificada (§9.3): toda `D` más sensible se prueba acá como diagnóstico, nunca en el reward. Corre en design time, antes de certificar; cazó el ataque #5 en Mendel.

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
3 regímenes públicos triviales: columnas exactas, tipos, n, timeout, sin red, **lint de imports de la submission** (allowlist: stdlib seguro + numpy/pandas/scipy/sklearn; sin red/subprocess/filesystem). Falla → error devuelto, episodio sigue abierto. El mismo lint, aplicado por el validator de fábrica, rige para `world.py` (allowlist: numpy/scipy/stdlib; sin subprocess/os/red).

### Semántica de bordes
Key de régimen ignorada = claim implícito de no-efecto (la batería lo cotiza). **Crash/NaN en un ítem → se asigna `D_MAX_item = 1.5 × D(verdad, null_model)` en ese ítem** (NO un clamp universal sobre distancias legítimas — v0.12): crashear paga estrictamente peor que no saber nada, para que el crash deliberado no sea una abstención trucha. Una distancia legítima > D_MAX solo se clampea como **cota de robustez** (el modelo es peor que 1.5× el nulo). **El null de referencia es el null MODEL** (marginales del pool, el mismo que ancla S_null), no una permutación de columnas de la verdad: la permutación conserva las marginales correctas y subestima cuán malo es "no saber nada" off-support, dejando que el propio nulo supere su cap (v0.12). Seeds apareados + m repeticiones por ítem (semántica precisa en §9).

---

## 9. Scoring — implementación `[EN DEBATE en elección de D y λ]`

```python
def score(submission, world, battery, lam, m):
    fid = 0.0
    for w, regime, seed_w in battery:
        real = world.sample(regime, n=1000, seed=seed_w)   # lado mundo: seed fijo por ítem,
                                                           # compartido entre submissions (CRN)
        d = 0.0
        for j in range(m):                                 # m repeticiones lado maqueta
            seed_m = derive_seed(seed_w, j)                # ≠ seed_w, determinístico
            pred = run_sandboxed(submission, regime, n=1000, seed=seed_m)  # crash → D_MAX_item
            d += energy_distance(standardize(real), standardize(pred)) / m
        fid -= w * min(d, d_max_item(regime, seed_w))      # D_MAX_item = 1.5 × D(verdad, nulo)
    return fid - lam * mdl(submission)   # mdl v0 = len(zlib(AST minificado)); ensembles: §9.2
```

**Semántica de seeds (v0.3).** Lado mundo: un seed por ítem, persistido en `battery.json`, compartido entre todas las submissions — common random numbers: las comparaciones entre submissions y contra las anclas son de baja varianza. Lado maqueta: `derive_seed(seed_item, j)` por repetición, **nunca** el seed del mundo — si coincidieran, entregar `world.py` literal daría D=0 exacto y el techo S_verdad perdería su semántica de "solo ruido de muestreo" (bug del pseudocódigo v0.2). Producción scorea con seeds fijos (reproducible); L2 (§13) estima el ruido re-scoreando con B sets re-sampleados. **Nota para E2 (diferida)**: los seed-sets de batería rotan periódicamente durante el entrenamiento — con realizaciones eternamente fijas, la policy puede sobreajustarlas (leakage lento).

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

`S_verdad` = score de entregar `world.py` mismo (techo: solo ruido de muestreo, garantizado por la separación de seeds de §9); `S_ingenuo` = score del rival (a) en su serialización canónica (§5). **Las tres cantidades — S_verdad, S_ingenuo, S_agente — se computan con la MISMA función completa (fidelidad − λ·MDL)**: R(`world.py`) = 1 por construcción y la normalización es autoconsistente; una submission igual de fiel pero más corta que `world.py` puede superar el techo (clip en 1). Beneficios: rewards comparables entre mundos, brechas adimensionales, dificultad interpretable. **El rango de normalización `S_verdad − S_ingenuo` es también el rango contra el que se miden los márgenes de L1** (§13, v0.12) — NO `S_verdad − S_nulo`: el nulo es un outlier patológico off-support (ignora la variable controlada) que infla el rango, y R clipea la región sub-ingenuo de todos modos. Caso borde: `S_verdad − S_ingenuo ≈ 0` → el mundo no discrimina → se rechaza (equivale a brecha mecanística ≈ 0). Issue conocido de E2 (decisión diferida, Decision Log v0.10): el clip en 0 aplana el gradiente debajo del rival ingenuo — candidatos: ancla nula para curriculum temprano / variante sin clip para RL.

### 9.2 Detalles de contrato que importan

- **Piso de varianza**: el apareamiento de seeds alinea el lado del mundo pero NO el lado maqueta (`derive_seed`, §9) → varianza irreducible que solo bajan las m repeticiones (costo total de scoring: K × n × m por episodio; medir CV en el primer slice y reportar la descomposición lado-mundo / solo-lado-maqueta).
- **Techo de tiempo por llamada** de `model()`: una maqueta lenta multiplica el costo de scoring ×K.
- **MDL v0 = `len(zlib.compress(ast_minify(code)))`** (anti code-golf; resuelve la contradicción zlib-crudo vs AST de v0.2). **Ensembles: `mdl = len(zlib.compress(concat(miembros minificados, orden canónico)))`** — la estructura compartida comprime una sola vez: un ensemble de variantes (incertidumbre honesta sobre parámetros/mecanismos) paga ~un miembro; uno de programas no relacionados paga completo. Resuelve la tensión MDL-vs-ensemble sin maquinaria extra (Decision Log v0.10).
- Energy distance con columnas mixtas (categóricas + continuas): codificación declarada y fija.

### 9.3 Score combinado — funcionales de stakes `[EN DEBATE — spec nuevo, Decision Log v0.26]`

**Por qué.** El probe de Mendel (Decision Log v0.25) mostró que la energy distance sobre marginales casi no penaliza multimodalidad a momentos fijos: un oráculo Gaussiano (media+covarianza exactas por-régimen, **unimodal**) saca R=0.96 contra una verdad máximamente bimodal (clusters en ±12, ruido 0.5). La estructura latente, cuya firma observable es de orden superior (modos/colas), queda **invisible** al reward → la suite Mendel (constructos latentes) no es recompensable con energía-sola. Es el **ataque #5 (Goodhart del proxy) realizado** y cazado por el certificado **antes de entrenar**. Fix: el score por ítem suma, a la energía, términos de **funcional de decisión declarado en stakes**.

**Encuadre (Decision Log v0.27, teoría de scoring rules).** No existe métrica libre-de-decisión: **toda `D` fija es un prior congelado sobre qué diferencias importan**, y la relevancia es dependiente del mundo. El score correcto se *deriva de los stakes* (un scoring rule propio se define respecto de la decisión/pérdida, no en abstracto). Por eso (A) no es un parche: es **base universal débil (energía) + amplificación declarada mínima-suficiente** donde los stakes dicen que importa. La energía sola era el caso degenerado "todas las diferencias pesan igual", que el hallazgo de Mendel refutó. **La opción (B)** (una `D` más sensible, p.ej. MMD bandwidth fino) **queda reclasificada: vive como diagnóstico permanente de fábrica (el `theory_gap_probe`), JAMÁS como reward** — meter más sensibilidad cruda al reward premia estructura que la decisión no usa (el espejo del blind-spot).

**Score combinado por ítem.** Para cada ítem `(w, régimen, seed)`:
```
d_item = energy_distance(std(real), std(pred))            # identidad conductual (término base, como §9)
       + Σ_F  c_F · | F(pred) − F(real) |                  # términos de funcional declarados, escala natural de F
d_item = min(d_item, D_MAX_item)                           # cap per-ítem sobre la SUMA (como §9; crash → D_MAX)
fid   -= w · d_item
```
- `F`: funcional de la biblioteca tipada (abajo), evaluado sobre **las muestras** (no sobre parámetros). `F(real)` se computa de la verdad con los mismos seeds apareados (CRN).
- Escala natural de F: probabilidades en su `[0,1]` nativo; cuantiles estandarizados por la verdad (las stats de columna de §9). Sin transformación extra (declarada).
- `c_F`: peso relativo del término, **calibrado UNA vez por suite** con criterio **mínimo-suficiente** (el menor `c_F` que hace visible la estructura instalada), luego **congelado y registrado** — **NO por caso** (calibrar por caso sería autoría). Provisional hasta E1.
- **Separación calibración/validación (regla dura, Decision Log v0.27 — cierra la circularidad).** Los rungs/mundos usados para calibrar `c_F` quedan **INHABILITADOS como evidencia de validez**. La validez se gana en: L1 de los OTROS mundos (no calibrantes) + E1 + la predicción (iii) (la batería pesa donde los rivales discrepan en el funcional) + held-out. Y **toda conclusión sustantiva se reporta con BANDA DE SENSIBILIDAD** (re-scorear con `c_F` ×2 y ÷2): si la conclusión se da vuelta en esa banda, es filo de cuchillo y se declara. *Sin esto, "tuneo `c_F` hasta que la escalera separe" es tuning-to-pass disfrazado — exactamente lo que L1 debe detectar.*
- La energía **sigue siendo el término base**: ningún funcional la reemplaza. Es la identidad conductual completa; el funcional solo agrega sensibilidad al rasgo decision-relevante que la energía no ve. **Identidad por construcción**: un caso que no declara funcionales tiene score combinado ≡ score de §9 (la suite del dummy no cambia).

**Biblioteca tipada de funcionales** (hermana de la de operadores §3: minable, **crece a demanda de stakes reales, nunca por imaginación suelta**; el solver jamás la ve):

| Funcional | `F(muestras)` | Escala |
|---|---|---|
| Exceedance de umbral | `P(outcome ≷ θ)` | `[0,1]` nativo |
| Cuantil | `q_τ(outcome)` | estandarizada por la verdad |
| Media condicional por subgrupo declarado | `E[outcome \| subgrupo]` | estandarizada |
| Pérdida esperada bajo regla declarada | `E[loss(decisión(régimen), outcome)]` | declarada por caso |

**Preferencia de la librería (Decision Log v0.27).** Si el brief define una **decisión nítida** (una regla de acción única), se usa **UN solo funcional de pérdida esperada** `E[loss(decisión, outcome)]` — menos perillas, menos superficie de calibración. La suma de varios funcionales queda solo para mundos **sin regla de acción única** (stakes difusos). Y el **valor de información** de descubrir el latente (VoI) NO entra acá: es un **oráculo de valor** que vive en firmas/análisis, **PROHIBIDO en el reward** — recompensar VoI sería premiar una conducta (investigar), y las conductas se observan, jamás se premian (NORTH_STAR §2.1).

**Criterio de completitud (cierra "¿cuántos funcionales?", Decision Log v0.27).** No es whack-a-mole abierto: es un **invariante de fábrica POR-MUNDO y chequeable**. (1) Toda estructura que **instalamos** (operadores declarados) debe pasar el **certificado de visibilidad** (§7) bajo el score combinado — y nosotros instalamos todo lo del mundo. (2) El residuo emergente (estructura no instalada a mano, surgida de la composición) lo cubre el `theory_gap_probe` como diagnóstico permanente. (3) Lo que ni el probe ve es el **ataque #14** (techo de lo comprensible), ya declarado como límite abierto. Suficiencia = visibilidad de lo instalado, no enumeración infinita de funcionales.

**REGLA DE TRAZABILIDAD (anti-Goodhart del diseñador).** Cada funcional instanciado en un caso **DEBE citar la cláusula verbatim del brief que lo promete** — es el checklist de promesas (Decision Log v0.24) en reversa: el brief promete → el funcional lo codifica. Si el brief no enuncia el rasgo (p.ej. "daño" en Mendel), se **corrige el CASO** (brief + `meta.json`) con registro y re-certificación; **no se inventa el funcional para que el gap aparezca**. El writer del brief sigue ciego a batería y rivales; la cláusula vive en `meta.json` y el writer la narra.

**Contrato del agente: INTACTO.** `model(regime, n, seed) → tabla`. Los funcionales se computan de SUS muestras, server-side, post-hoc; el agente nunca ve cuáles se scorean (como la batería). **Cero LLM** en el cómputo (los funcionales son numpy puro; CI §13-L0 sin cambios).

**Batería: UN solo método.** El desacuerdo entre rivales (§6 paso 2) se computa en el **mismo** score combinado, no en energía-sola → la batería concentra peso donde los rivales discrepan en el **funcional** (colas, shifts de subtipo), dándole a la predicción (iii) su test real.

**Normalización (§9.1): forma sin cambios.** S_verdad, S_ingenuo, S_agente con la MISMA función completa (ahora energía + funcionales − λ·MDL). `R(world.py)=1` se preserva (F(world.py)=F(verdad) salvo ruido de muestreo).

**Mini red-team — "cómo Goodharteo el funcional" (5 ataques + defensa):**
1. **Matchear el funcional, romper el resto** (ajustar P(daño) exacto con basura en lo demás) → lo paga la **energía base** (término aditivo dominante, no reemplazado).
2. **Funcional no promovido por el brief** (el diseñador lo declara para fabricar el gap) → **regla de trazabilidad**: cita verbatim o se corrige el caso.
3. **Colapsar el funcional a constante** (predecir siempre la media) → `|F(pred)−F(real)|` lo penaliza donde F es sensible al modo (P(daño) de un unimodal ≠ bimodal: la evidencia del probe, brecha 0.16–0.29).
4. **Gaming del cap** (inflar un término para saturar D_MAX y ocultar otro) → cap per-ítem sobre la **suma**; la suite de sanidad de escala (§13) verifica ninguna distancia > D_MAX y el orden sin clipear.
5. **Overfit a los seeds del funcional** (P̂ con n finito tiene ruido binomial) → seeds apareados (CRN) + m reps; **L2 verifica CV(R)<5% incluyendo los términos funcionales** (ruido binomial de P̂ con n=1000, m=2 ≈ 1.6 pts — dentro de presupuesto; verificar en el slice).

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
- **L1 — Escalera de verdades degradadas** (aceptación obligatoria por mundo, automática): se scorea una secuencia de submissions de calidad conocida — `world.py` exacto, verdad con parámetros perturbados, verdad con un mecanismo ablado, gemelo inocente, ajuste ingenuo, modelo nulo. **Forma del certificado en producción (v0.3): monotonía-por-eje + extremos** — `world.py` > cada rival > nulo, y dentro de cada eje de degradación, perturbación creciente ⇒ score no-creciente. NO se exige orden total entre peldaños heterogéneos: no está garantizado teóricamente, y tunear las degradaciones hasta que el orden pase sería autoría silenciosa — exactamente lo que L1 debe detectar. El **orden total** se usa solo como test de aceptación del scorer sobre el dummy canónico del Slice 1 (perillas elegidas para que valga). Margen inicial: cada separación exigida ≥5% del **rango de normalización (S_verdad − S_ingenuo), en unidades de R** (v0.12 — NO S_verdad − S_nulo: el nulo es un outlier patológico off-support que infla el rango, y R clipea la región sub-ingenuo; ver §9.1); modelo nulo v0 = marginales independientes del pool, usado como referencia de D_MAX y diagnóstico. Valores empíricos, ajustables. Si el certificado falla, la batería de ese mundo está rota. Es el detector automático de rivales débiles (ataque #13) — y en el Slice 1 destapó tres bugs de maquinaria del scorer (Decision Log v0.12), cumpliendo exactamente su función. **Rung de DIAGNÓSTICO extra para mundos latentes (suite Mendel, v0.26/v0.27): el oráculo de momentos matcheados** (Gaussiana media+cov exactas por-régimen, unimodal) — responde "¿el metro ve?", NO es el rival de teoría (ese es el mejor sin-latente FLEXIBLE de la escalera (d), §7-Q4). Debe quedar **estrictamente por debajo** de `world.py` bajo el score COMBINADO; si lo iguala (como bajo energía-sola: R=0.96, Decision Log v0.25), el funcional no captura la estructura y el mundo no es recompensable. Operacionaliza el certificado de Visibilidad (§7).
- **L2 — Protocolo de varianza del reward**: con seeds de producción fijos el score es determinístico; el ruido relevante es la dependencia del azar de los seeds elegidos. Protocolo (v0.3): re-scorear con B sets de seeds re-sampleados (lado mundo y lado maqueta) la submission del **peldaño medio** de la escalera (donde el ruido más confunde) → **CV objetivo < 5% sobre R normalizado** (la escala cruda varía por mundo), reportando además el **CV de S_verdad** (denominador de R) y la **descomposición lado-mundo / solo-lado-maqueta** (mundo fijo, variando j). Medir en el primer slice junto con el costo K×n×m; ajustar K, n, m hasta cumplir. Sin esto, RL aprende ruido.
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
14. Márgenes de la escalera (L1) y CV objetivo (L2): valores iniciales fijados (5% del rango; CV < 5% sobre R — Decision Log v0.10); queda abierto el procedimiento de ajuste empírico.
