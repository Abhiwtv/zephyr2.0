# NetCoop AI · Zephyr 2.0

A neuro-symbolic multi-agent engine for diagnosing network faults. Deterministic Python handles scoring, masking and the final verdict. Stateless LLM agents (**Qwen2.5-14B-Instruct-AWQ**) handle only the semantic reasoning.

**Compute:** inference runs on a modular **Bring-Your-Own-Compute (BYOC)** layer. The always-on Oracle VM control plane starts an **ephemeral Google Cloud T4 GPU** only when a diagnosis needs it, so idle GPU cost is zero and the inference layer stays decoupled from the control plane.

![Architecture](docs/NetCoop_Zephyr2_Architecture.png)

---

## 1. Agent Responsibilities

The system has two kinds of participants. **Symbolic components** are deterministic Python: they decide what each agent sees and how much its vote weighs. **LLM agents** reason over what they are given. They never set their own authority and never issue the final verdict.

### Symbolic components

| Component | Responsibility | Output |
|---|---|---|
| `InfrastructureSensor` | Fuzzy-scores device health: status, CPU, memory, interface errors | `anomaly_score`, severity tier |
| `TrafficSensor` | Fuzzy-scores performance: latency, jitter, loss, utilization, queue drops | `anomaly_score`, severity tier |
| `L4L7Sensor` | Fuzzy-scores services: DNS, DHCP, application health | `anomaly_score`, severity tier |
| `AsyncConsensusIterator` | The orchestrator. Masks telemetry per domain, injects scores into prompts, runs the voters concurrently, computes consensus and runs the epoch loop | Consensus ratio, final verdict |
| Report formatter | Maps the agreed result into the `DiagnosticReport` schema | Benchmark JSON report |

Severity tiers run `HEALTHY → MINOR → MAJOR → CRITICAL → FATAL` (score 0.0 to 3.0+). If all three scores are 0.0, no LLM is called.

### LLM agents

| Agent | Sees | Does | Never |
|---|---|---|---|
| **The Brain** (`ReasoningEngine`) | Fuzzy alerts from all sensors | Proposes one root-cause hypothesis with recommended actions, and revises it when votes come back against it | Votes on its own hypothesis |
| `traffic_agent` | Traffic telemetry only (interface errors masked) | Votes `APPROVE` / `REJECT` / `ABSTAIN` on the hypothesis, backed by evidence | Sees data outside its domain |
| `infrastructure_agent` | Infrastructure telemetry only | Same as above | Sees data outside its domain |
| `l4_l7_agent` | Service telemetry only (CPU masked) | Same as above | Sees data outside its domain |

### Cognitive split: asymmetric chain-of-thought

The Brain and the voters run on the same model in deliberately different modes. This optimises token generation and VRAM use.

| | The Brain | The Voters |
|---|---|---|
| **Mode** | Native chain-of-thought (thinking **enabled**) | Strict zero-shot (thinking **disabled**) |
| **Token budget** | High, giving it a reasoning scratchpad | Minimal: a single vote and short evidence |
| **Job** | Analyses alerts and debate memory in depth, then proposes the root cause | Pattern-matches the hypothesis against its own metrics |
| **Speed** | Slower, deliberate | Milliseconds, fully asynchronous |

Deep reasoning happens **once**, in the Brain. The three voters stay fast and cheap, so the debate scales without exhausting the T4's VRAM.

### How the vote works

1. The **Brain** proposes one hypothesis, e.g. *"congestion on the MHR uplink"*, along with recommended actions (`hypothesis_broadcast`).
2. All three voters (`traffic_agent`, `infrastructure_agent`, `l4_l7_agent`) review it **asynchronously**. Each one sees only its own masked telemetry.
3. Each voter casts exactly one of three votes and backs it with facts from its own domain:


| Vote | Meaning |
|---|---|
| `APPROVE` | My domain's telemetry supports this hypothesis |
| `REJECT` | My domain's telemetry argues against it (a `suggested_alternative` can be given) |
| `ABSTAIN` | My domain has nothing relevant, or the vote was forced by the middleware |

```json
{
  "agent_id": "traffic_agent",
  "vote": "APPROVE",
  "reason": "Uplink saturated with egress drops",
  "supporting_evidence": ["utilization_out_pct = 97%", "out_discards = 1840"]
}
```

4. The orchestrator **weights** each vote by its domain's `anomaly_score`, so an agent whose domain is abnormal carries more authority.
5. The weighted result is the **confidence**:
   - **≥ 0.70:** the hypothesis is accepted and the debate ends early.
   - **Only one `APPROVE`, all others `ABSTAIN`:** confidence is **capped at 0.60**, so a single agent can never push a hypothesis through on its own.
   - **< 0.70:** the rejections and reasons go back to the Brain for a new hypothesis, for up to 3 rounds. If there is still no consensus, the best hypothesis is reported with status **`investigating`**.

### Voter rules

Each voter's prompt includes its domain's `anomaly_score`, and that score sets its behaviour:

- **Score > 0 (bleeding):** cite abnormal metrics as `supporting_evidence`. Do not use normal metrics (e.g. normal CPU) to `REJECT` a valid fault in another domain.
- **Score = 0 (healthy):** may only falsify, never support. `supporting_evidence` must stay empty, and the voter should `ABSTAIN` if the hypothesis is vague ("Unknown network anomaly") or blames another domain.
- **Cascading failures:** downstream agents (e.g. `L4_L7`) must vote `APPROVE` when the Brain proposes a catastrophic physical failure, such as a dead core switch, that explains their downstream service timeouts. This stops domain silos from rejecting a valid root cause just because the fault is outside their layer. The rule fixes the `EVAL-10` total-meltdown case.
- **Always:** the LLM chooses the vote; Python sets its weight.

### Analogy: a hospital diagnosis board

| Hospital | Zephyr |
|---|---|
| **Triage monitors** check every patient's vitals. If all vitals are normal, the patient goes home without seeing a doctor. | Fuzzy sensors and the fast-path exit |
| **The chief physician** reads the triage alerts and proposes one diagnosis. | The Brain |
| **Specialists** (cardiologist, neurologist, pathologist) each see only their own test results and vote for it, against it, or abstain. | `traffic_agent`, `infrastructure_agent`, `l4_l7_agent` |
| The specialist whose tests look most abnormal **carries the most weight**. A diagnosis backed by only one specialist is recorded as **tentative**, never certain. | Score-based weights and the 0.60 single-agent cap |
| **The board secretary** keeps the minutes, tallies the votes and sends the chief back to rethink, for up to 3 rounds. | `AsyncConsensusIterator` |
| **The records clerk** writes the final report in the hospital's standard format. | Report formatter |

The chief physician never grades their own diagnosis, and no specialist can comment on tests they haven't seen. That is why the system avoids echo chambers.

---

## 2. Communication Interfaces

Agents exchange **structured Python dictionaries / JSON**, never free text. There are two lines of defence for data quality:

- **On the way in**, Pydantic validates the input shape and the fuzzy logic engine absorbs noise in the values.
- **On the way out**, the `CoordinationMiddleware` checks every LLM response before it reaches the consensus math.

```
POST ─► TelemetryInput (Pydantic) ─► Sensors (FuzzyLogicEngine) ─► Orchestrator ─► Brain ─► Voters
                                                                        ▲                    │
                                                                        └─ CoordinationMiddleware ◄─┘
```

### 2.1 External interfaces

| Endpoint | Direction | Payload |
|---|---|---|
| `POST /api/v1/diagnose` | Client → engine | `TelemetryInput` in, `DiagnosticReport` out |
| `WS /api/v1/debate-stream` | Engine → dashboard | Live pipeline events and consensus math traces |

### 2.2 Inbound: Pydantic and fuzzy logic

- **`TelemetryInput` (Pydantic)** rejects structurally invalid requests at the API Gateway, before any agent runs.
- **`FuzzyLogicEngine`** (inside each sensor) is the main defence against noisy telemetry. It scores the *degree* of drift instead of applying hard binary thresholds, so a single noisy sample only nudges the `anomaly_score` and does not trigger a false alarm.

### 2.3 Outbound: `CoordinationMiddleware` (semantic firewall)

The middleware sits **between the domain voters and the orchestrator**. It intercepts the raw JSON produced by Qwen and validates it against the Pydantic `AgentVoteSchema`. This stops hallucinated keys or invalid vote types from ever reaching the consensus math.

**Circuit breaker.** The system does not retry. A vote is replaced with a safe fallback in two cases:
- the LLM call exceeds the **45-second `aiohttp` timeout**
- the response breaks `AgentVoteSchema`

The fallback is:

```json
{ "vote": "ABSTAIN", "reason": "Middleware intercept" }
```

This means a single bad or slow LLM response can never hang or crash the pipeline.

### 2.4 Message contracts

| Message | From → To | Fields |
|---|---|---|
| Sensor output | Sensor → Orchestrator | `device_id`, `domain`, `alert_category`, `evidence[]` |
| `hypothesis_broadcast` | Brain → Voters | `incident_id`, `proposed_root_cause`, `confidence_estimate`, `recommended_actions[]`, `target_devices[]` |
| `hypothesis_vote` | Voter → Orchestrator (via middleware) | `incident_id`, `agent_id`, `vote` (`APPROVE` / `REJECT` / `ABSTAIN`), `reason`, `suggested_alternative`, `supporting_evidence[]` |

Example `hypothesis_vote`:

```json
{
  "incident_id": "INC-8832",
  "agent_id": "traffic_agent",
  "vote": "APPROVE",
  "reason": "Uplink utilization and egress drops match congestion",
  "suggested_alternative": null,
  "supporting_evidence": ["utilization_out_pct = 97%", "out_discards = 1840"]
}
```

---

## 3. Orchestration & Data Flow

The orchestrator controls the whole diagnostic debate. It decides which incident runs, which agents are consulted, how their votes are combined and when the debate ends. It is built for three things: **stability under load**, **non-blocking execution** and **zero state bleed between incidents**.

### 3.1 Sequential Event Router: `route_and_resolve_batch`

A campus-wide outage produces a flood of alerts at once. The router does not fire them all at the LLM in parallel. Instead it:

1. **Takes in** the full, unordered batch of campus telemetry.
2. **Clusters** alerts by `device_id` (temporal topology clustering), so related symptoms on the same device become one incident instead of many duplicates.
3. **Queues** the incidents and resolves them **one at a time**.

This sequencing works as a **circuit breaker for the inference layer**. It protects local GPU VRAM from out-of-memory (OOM) crashes and keeps token generation fast, even during a live demo or a real outage storm.

### 3.2 The Debate Loop: `execute_voting_loop`

Each incident goes through the same lifecycle:

1. **Hypothesis.** The `ReasoningEngine` (Qwen 2.5 14B AWQ, chain-of-thought enabled) produces a JSON hypothesis with the proposed root cause and recommended actions.
2. **Broadcast.** The orchestrator sends it as a `hypothesis_broadcast` to the three domain voters: `Infrastructure`, `Traffic` and `L4_L7`.
3. **Asynchronous collection.** Votes are gathered with non-blocking async calls, so the Python event loop stays free while the LLM is generating. Each response passes through the `CoordinationMiddleware` (section 2.3) before it is counted.
4. **Consensus check.** The votes are scored (section 3.3). If consensus is reached, the debate ends. If not, the result is written to memory and the Brain starts the next round.

### 3.3 Consensus Math & Single-Agent Protection

| Condition | Outcome |
|---|---|
| Domain voters agree, **confidence ≥ 0.70** | Debate **ends early** and the hypothesis is accepted |
| Only **one** voter returns `APPROVE` and the rest `ABSTAIN` | Confidence is **capped at 0.60** |
| Disagreement | Next round, up to **3 rounds** |
| **Healthy bypass:** all fuzzy sensors return `0.0` | The consensus loop is **skipped entirely** (fast path) |
| **Zero-weight guard:** a baseline reaches the loop and every agent votes `APPROVE` with `0.0` weight | The middleware forces confidence to **`1.0`** and exits cleanly, avoiding a divide-by-zero |

**Why the 0.60 cap matters.** Without it, one confident but hallucinating agent could approve a hypothesis while the others abstain, and immediately override the system. The cap means a single-agent finding is reported with **moderate confidence**, never high. Isolated faults such as **DHCP pool exhaustion** still get diagnosed, but the uncertainty is stated honestly.

### 3.4 Thread-Safe Memory Management: `IncidentMemory`

- **Debate history.** `IncidentMemory` records every hypothesis, vote and confidence score for the incident, across a maximum of **3 rounds**. Each new round of the Brain builds on this history.
- **Concurrency safety.** All reads and writes are protected by `threading.Lock()` mutexes, so asynchronous vote collection cannot cause race conditions.
- **Guaranteed cleanup.** Each incident runs inside a strict `try...finally` block. Memory is wiped after every incident, **even if the LLM crashes or times out**, so no state from one incident can leak into the next.

---

## 4. Evidence Correlation & Error Handling

Zephyr correlates evidence **mathematically before the LLM is involved**, and is built to survive both corrupted telemetry and LLM failures at runtime.

### 4.1 Deterministic Evidence Correlation (Symbolic Layer)

All raw metrics pass through the **Fuzzy Logic Engine** before any LLM sees them.

**Triangular Membership Functions (TRIMF).** Each metric is mapped from a raw number to a linguistic degree of membership:

```
μ(x) = max( min( (x − a)/(b − a), (c − x)/(c − b) ), 0 )
```

```
cpu: 78%  ──► TRIMF ──►  "Warning CPU load detected (Fuzzy Confidence: 0.80)"
```

**Three-way classification.** Every signal ends up in exactly one class:

| Class | Meaning | Treatment |
|---|---|---|
| **Benign noise** | Normal variation or a one-off spike | Dropped and never reaches the LLM |
| **Warning** | Borderline degradation | Passed on with its fuzzy confidence |
| **Critical** | Severe fault | Passed on with its fuzzy confidence |

**Why it matters.** The engine is a mathematically grounded filter, and it directly addresses the hackathon's requirement for **robustness to noisy, inconsistent telemetry**. The LLM correlates *pre-scored evidence* rather than raw numbers, so it never has to guess whether a value like `78%` is dangerous.

### 4.2 Error Handling & System Resilience

**Pydantic semantic firewall (`CoordinationMiddleware`)**

Every LLM response is intercepted and validated against `AgentVoteSchema`:

| LLM failure | Middleware response |
|---|---|
| Hallucinated or invalid JSON key | Catches the validation error and forces `ABSTAIN` |
| Invented vote type (e.g. `vote: MAYBE`) | Catches the validation error and forces `ABSTAIN` |
| Conversational markdown wrapper (```` ```json … ``` ````) | Strips the markdown, then validates |

A malformed agent response therefore **degrades to a safe abstention** and never crashes the pipeline.

**Non-blocking I/O and timeouts**

- All inference calls use asynchronous `aiohttp` with a hard **45-second timeout**.
- If the GPU inference node freezes or VRAM locks up, the agent times out, the error is logged and orchestration continues.
- The master event loop is never blocked.

**Graceful degradation**

If consensus is still not reached after **3 rounds**, the system does not fail. Instead it:

1. Outputs the **highest-confidence hypothesis** found during the debate.
2. Sets `status` to **`investigating`** instead of `diagnosed`.
3. Records the gap in `limitations` (e.g. *"Failed to reach strong consensus"*).

The operator always gets a usable, honestly labelled report, even under the worst-case runtime conditions.

---

## 5. Workflow

Every request takes the same path, from raw telemetry to the final JSON report.

```
POST /api/v1/diagnose
   │
   ▼
① Validate & isolate ─► ② Fuzzy scoring ─► all 0.0? ──YES──► Healthy report (no LLM)
                                              │ NO
                                              ▼
                        ③ Route & queue incidents (by device_id, one at a time)
                                              │
                        ┌─────────────────────▼─────────────────────┐
                        │ ④ Mask telemetry + inject scored prompts  │
                        │ ⑤ Brain → new hypothesis_broadcast        │◄──┐ rejections + reasons
                        │ ⑥ Voters → hypothesis_vote (async)        │   │ (max 3 rounds)
                        │   └─ CoordinationMiddleware               │   │
                        │ ⑦ Confidence ≥ 0.70 ? ── NO ──────────────┼───┘
                        └─────────────────────┬─────────────────────┘
                                              │ YES  (or 3 rounds → "investigating")
                                              ▼
                        ⑧ DiagnosticReport JSON ─► ⑨ Wipe IncidentMemory ─► next incident
```

| Step | Stage | What happens |
|---|---|---|
| ① | Validate & isolate | `TelemetryInput` (Pydantic) validates the request and `global_state` is cleared. |
| ② | Fuzzy scoring | The three sensors apply TRIMF: noise is dropped, and warnings and critical faults get a fuzzy confidence and an `anomaly_score`. |
| — | Fast path | If every score is 0.0, a healthy report is returned immediately and no LLM is called. |
| ③ | Route | `route_and_resolve_batch` clusters alerts by `device_id` and queues the incidents to run one at a time. |
| ④ | Mask & prompt | Each voter receives only its own domain's telemetry plus a bleeding or healthy directive. |
| ⑤ | Hypothesise | The `ReasoningEngine` (Qwen 2.5 14B AWQ, chain-of-thought enabled) proposes a root cause and recommended actions. |
| ⑥ | Vote | `Infrastructure`, `Traffic` and `L4_L7` vote `APPROVE` / `REJECT` / `ABSTAIN` asynchronously. `CoordinationMiddleware` validates each vote and forces `ABSTAIN` on bad JSON or a 45 s timeout. |
| ⑦ | Decide | Confidence ≥ 0.70 ends the debate. A single-agent approval is capped at 0.60. Below 0.70, the Brain revises, for up to 3 rounds. |
| ⑧ | Report | The result is mapped into `DiagnosticReport`. If there is no consensus after 3 rounds, the best hypothesis is reported with status `investigating` and the gap is listed in `limitations`. |
| ⑨ | Clean up | `IncidentMemory` is wiped in a `try...finally` block, and the next queued incident starts. |

Throughout the run, `RealTimeNOCLogger` streams each step and its confidence maths over `WS /api/v1/debate-stream` to the live dashboard.