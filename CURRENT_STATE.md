# CURRENT_STATE — WAGER

> Estado vivo del repo: qué corre hoy, qué falta. Lo mantiene Claude Code al día en cada
> sesión de trabajo (regla: NORTH_STAR §0.10). Última actualización: **2026-07-01**.

## Qué corre hoy

**Slice 1 (reward path), Slice 2 (harness C1+C2+C3) y slice de derivación (rivales+batería+
certificados) completos y verdes.** `pip install -e .[dev,agent]` + `pytest` → **86 verdes,
2 skip** (tests LLM opt-in; correr con `RUN_LLM_TESTS=1`). Python 3.13.

**Última sesión (v0.30)**: auditoría código-vs-docs por iniciativa propia → deriva doc-código
v0.18→v0.29 corregida + checklist de supersesión + certificados auto-descriptivos (`RivalAccess`).
Antes (v0.26–v0.29): decisión (A) funcionales de stakes (spec-first, triangulada), score
combinado implementado (paso 1), acceso de rivales (β) en dos modos (d-obs)/(d-exp). **Próximo
paso de trabajo: (2) calibrar `c_F` mínimo-suficiente** (ver "Orden del slice" abajo).

- `wager/contracts/` — contratos Pydantic v2 (world, case, episode, reports).
- `wager/reward/` — **zona cero-LLM** (allowlist de imports en CI + no importa
  `wager.agent`/`wager.harness`): `seeds`, `distance`, `mdl`, `sandbox`, `scorer`
  (R, D_MAX), `ladder` (L1), `variance` (L2), `episode_score` (R de submission).
- `wager/factory/` — `case_loader`, `world_lint` (lado fábrica; LLM permitido acá).
- `wager/agent/` — **lado solver (LLM)**: `llm_client` (Foundry v1 multi-turn),
  `cells`. Nunca importado por `wager.reward`.
- `wager/harness/` — `world_server` (autoridad del episodio: verbos + ledger +
  humo + scoring), `kernel_proc` (kernel en proceso separado + env proxy data-only),
  `episode` (loop LLM + guardas + trace), `env`/`case_episode`, `kernel`/`c1_env` (C1).
- `cases/dummy_dose_v0/` — `world.py`, `battery.json`, `meta.json` (+ episode),
  `ladder/`, `brief.md` (cara pública, ASCII), `solvers.py`, runners
  (`run_slice`, `c1_smoke`, `c2_pair`, `e0_episode`, `e05_episodes`,
  `make_ladder_fixtures`, `ablate_m`, `diagnose`), `traces/` (E0/E0.5).

### Entregables medidos (`python cases/dummy_dose_v0/run_slice.py`, defaults v0 K=16 n=1000 m=2)

- **L1**: orden total de las 6 verdades degradadas con todos los márgenes ≥5%,
  cada peldaño anotado como ancla (R fijo) o medición. R = {verdad 1.000
  (anchor:S_truth), perturbado 0.942, linealizado 0.728, gemelo 0.344, ingenuo
  0.000 (anchor:S_naive), nulo 0/−2.53 (reference:S_null)}. Margen más ajustado:
  verdad→perturbado 5.85%.
- **L2**: CV(R) = 1.17% sobre 20 seed-sets (objetivo <5%); CV(S_verdad) = 0.54%;
  descomposición std(R) total 0.0084 = lado-mundo 0.0075 ⊕ lado-maqueta 0.0039.
- **Costo K×n×m** (16×1000×2): L1 6.4s, L2 27.1s.
- **Ablación de m** (`ablate_m.py`): CV(R) 1.17/1.13/1.10% para m=2/3/5 → m=2
  default v0 (el lado-mundo domina; subir m casi no mueve el total).

## Hallazgos del Slice 1 (Decision Log v0.12)

La escalera L1 destapó tres bugs de **maquinaria** (no de fixtures) al fallar el
orden total; se diagnosticó per-ítem (`diagnose.py`) antes de tocar nada:
1. D_MAX clampeaba toda distancia (debía asignarse solo en crash).
2. D_MAX referenciaba el null equivocado (permutación de la verdad, no el null model).
3. Los márgenes L1 se medían contra S_verdad−S_nulo (un outlier patológico);
   ahora contra el rango de normalización S_verdad−S_ingenuo (unidades de R).
Fixtures de la escalera intactos.

## Resultados del Slice 2 (C2 + C3, Decision Log v0.15–v0.16)

- **C2**: naive R=0.044 vs canonical R=1.000 por el juego real (investigar gana).
- **E0** (gpt-5.4): R=0.895, 4 turnos — jugable; 1 submit falló humo y se corrigió.
- **E0.5 (corregido, seeds arreglados)**: gpt-5.4 R∈{0.000, 0.960}, DeepSeek-V3.2
  R∈{0.915, 0.919}. Todos honestos, 0 crashes. Firma conductual v0.1
  (attribution_before_experiment) = True en los 4.
- **RETRACTADO (v0.16)**: el "DeepSeek R=0 = brecha de teoría" de v0.15 era un
  **artefacto de rango de seed** (legacy `np.random.seed` rechaza ≥2³²;
  `derive_seed` daba 64 bits → 16/16 crashes → D_MAX → R=0). Fix: seeds 32-bit +
  smoke reforzado. R real de DeepSeek ≈0.98. El dummy NO muestra brecha de teoría
  (un modelo sin latente saca ~0.92). Reportar SIEMPRE R_uncl (clips≠mediciones).
- Fricciones resueltas: no-ASCII en briefs; `hasattr` faltaba; seeds 64-bit.

## Slice de derivación automática (EN CURSO, Decision Log v0.17–v0.18)

Pre-registración v0.17 (predicciones dummy/Mendel ANTES de correr). Hecho:
- **Mundo estructurado** (`world.py` PARAMS + mechanism; meta declara `ablation`).
- **`score_callable`** (reward): scoring in-process de rivales callable de fábrica.
- **Rivales a/d** (`wager/factory/derive_rivals.py`) + **certificados**
  (`certificates.py`): brecha de teoría + mecanística.
- **Certificado dummy ✅ (predicción i CONFIRMADA)**: theory gap **0.062** (no-latente
  recupera R=0.938), mechanistic gap **0.990**. El dummy es trampa de confounding,
  no de latente. La disciplina cazó 2 artefactos de rival débil (predicción registrada).
  - **Procedencia (footnotes v0.30, NO correcciones):** theory gap 0.062 = vs
    **proto-(d-exp)** (grilla `do(dose)` ad-hoc, `standardized=false`); re-correr UNA
    vez cuando exista la (d-exp) estandarizada (paso 3) — pre-registro: cambia poco.
    Mechanistic gap = vs **(a) solo**; bajo v0.29 = vs best{(a),(d-obs)}; recomputar
    cuando nazca (d-obs) — pre-registro: el dummy se mueve poco (movimiento grande →
    investigar (a), no retunear). El acceso de cada rival viaja ahora EN el
    `certificates.json` y el dossier (certificados auto-descriptivos).
- **Rival (c) panel ✅** (LLM-first milestone, `rival_c_panel.py`): 3/3 LLMs frescos
  compilan a programa ejecutable; el prior aterriza < ingenuo (R≈0).

**Hecho desde entonces (v0.20–v0.24)**:
1. ✅ `battery_builder` (candidatos + `disagreement_norm`=D/D_MAX + piso de elegibilidad +
   `stakes_relevance` + dedup) → batería 100%-derivada; **aceptación (i) MET** (criterio de
   producción: monotonía + extremos).
2. ✅ Rival (b) gemelo (ablación de operador + refit) + **escalera de capacidad completa**
   (a + linear + GBM + gemelos = 5 rivales del desacuerdo; `build_standard_rivals`).
3. ✅ Ronda de hardening v0.24: cola de cohort fuera-de-registro, robustez al seed
   (~6.5pp estructural → producción necesita ~200 ítems), checklist de promesas del brief
   en el dossier. **Retractación de Claude** (item 5): out-of-record discrimina el rung
   linealizado → suba de peso a discutir con Lucas.

**PENDIENTE de Lucas (gatea el cierre del slice de derivación)**:
- Re-auditoría del mapa de cobertura CON el checklist de promesas → recién ahí **expira el
  bootstrap** (battery.json de mano → derivada).
- Decisión sobre el peso out-of-record (consecuencia de la retractación item 5).

## Mendel (2º mundo) — predicción (ii) REFUTADA, hallazgo de scoring (Decision Log v0.25)

`cases/mendel_subtypes_v0/world.py` (subtipos latentes con efecto de dosis de signo
opuesto + biomarcador bimodal) + `theory_gap_probe.py`. **Pre-registro `30365fa` antes del
código.** Resultado: **el control decisivo (oráculo Gaussiano de momentos por-régimen,
unimodal) saca R=0.963** → gap irreducible **0.037** (≈ dummy). El "gap" de 0.35 vs el
no-latente homoscedástico era artefacto de heteroscedasticidad. **La distancia de energía
sobre marginales casi no ve multimodalidad a momentos fijos** → la heterogeneidad latente
NO es recompensable con el scoring actual. PERO un funcional `P(daño)` muestra brechas
0.16–0.29 → el latente SÍ es decision-relevante.

**DECISIÓN (v0.26→v0.27): (A) funcionales de stakes, SPEC-FIRST — APROBADA (triangulada con
2ª IA) con 2 correcciones de mi estrés-test.** Spec escrito (ARCHITECTURE §9.3 + certificado
de Visibilidad §7 + rung-diagnóstico oráculo §13-L1 + red-team de 5 ataques) + Decision Log
v0.26/v0.27. Correcciones v0.27: **(Q4)** el oráculo de momentos es **diagnóstico** ("¿el
metro ve?"), NO el proxy de brecha de teoría — esa va contra el **mejor sin-latente FLEXIBLE**
(mixturas/GBM condicional). **(Q5)** **Mendel v0 no tiene latente genuino** (el biomarcador
limpio lo proxia) → **Mendel v1**: biomarcador ruidoso + ausente de la fuente barata
(comprable) + batería con shifts de mix fuera de soporte; v0 queda como **control negativo**.
Reglas nuevas: separación calibración/validación + banda de sensibilidad (`c_F` ×2/÷2);
completitud = certificado de visibilidad (no whack-a-mole); VoI prohibido en reward.

**Orden del slice (v0.27, EN CURSO)**: **(0)** ✅ brief+meta de Mendel v1 con trazabilidad
(`255d781`; FunctionalSpec en contratos) → **(1)** ✅ score combinado en `wager/reward/`
(`7ccaf23`; functionals.py cero-LLM + D_MAX combinado amendment 4 + P1 identidad-por-
construcción verificado; suite 85 verde) → **(2)** calibrar `c_F` mínimo-suficiente +
congelar → **(3)** P2-v1 con el par de control v0/v1 → **(4)** P3 → **(5)** P4 + banda de
sensibilidad.

**v0.29 (acceso de rivales, β)**: la variación de mix entra por EXPERIMENTOS (fuente barata
sigue single-mix); escalera (d) en dos modos — **(d-obs)** ancla la brecha mecanística,
**(d-exp)** (presupuesto experimental estandarizado y scripteado, acceso igualado al agente)
ancla la brecha de teoría. Principio: *brecha de teoría = contrafáctico con acceso igualado*.
Línea sin-latente = sin cabezal de mezcla (MDN/GMM condicional NO cuentan); escalera con
miembros de extrapolación SUAVE en mix (árboles plateau-ean = razón tonta). Pre-registro
P2-v1 completo (tabla 2×2: v0 chico / v1 grande ≥3×v0 con el funcional cargando la mayor
parte / mecanística grande en ambos / banda c_F ×2÷2 / guardia si v0 sale grande).

**v0.30 (auditoría código-vs-docs por iniciativa propia, HECHA)**: una verificación de
alineación destapó una **deriva doc-código v0.18→v0.29** — ARCHITECTURE §5 decía "(a) y (d)
cero experimentos" pero el código entrena (d) sobre grilla experimental desde v0.18 (el código
se adelantó a la doctrina; el papel quedó atrás). Tres contramedidas: **(1)** fix de §5 ((a)
verbatim intocable; (d) → referencia a los dos modos de §7); **(2)** checklist de supersesión
→ CLAUDE.md (grep obligatorio de cada ubicación de la regla vieja; "una regla, una casa");
**(3)** **certificados auto-descriptivos** — el acceso del rival (modo/presupuesto/seeds) es
campo Pydantic OBLIGATORIO del certificado (`RivalAccess`) con guarda (teoría=experimental,
mecanística=observacional) e impreso en el dossier → una deriva se ve en cada dossier, no solo
leyendo código. Footnotes de procedencia de los números históricos (arriba). Suite 86 verde.
**(d-exp) NO participa de la calibración de `c_F`** (la brecha de teoría queda independiente).

**Después**: detector de contaminación v1 = contraste-gemelo (sobre el dummy). Stretch: E0-Mendel.

**PENDIENTE de Lucas que sigue abierto** (del slice de derivación): re-auditoría del mapa de
cobertura del dummy CON el checklist → expira el bootstrap; decisión del peso out-of-record
(retractación item 5).

## Qué falta (más allá del slice)

- E1: ~20 mundos a mano en 2 familias, ≥5 suites (ARCHITECTURE §12).
- Hardening del handle opaco (gaps en `REDTEAM.md`); mejor extractor de firmas.
- Collider+medición (3er mundo, ejercita la capa de muestreo).

## Deuda / pendientes

- Sandbox v0 es honesto pero no es jaula real: gaps declarados en `REDTEAM.md`
  (C-extensions, rlimit de memoria, fork). Se cierran con el harness interactivo.
- λ es **provisional** (calibrado al 5% del rango de normalización del dummy);
  se recalibra sobre la suite E1.
- Issue conocido E2 (diferido): clip(R,0,1) y sparsity de gradiente; rotación de
  seed-sets durante entrenamiento.
- Ensembles `[(peso, code)]`: `mdl_bytes` ya los soporta; el scoring de mezcla
  muestreada falta (no hay fixtures de ensemble en el Slice 1).
