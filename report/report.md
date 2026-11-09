# Boston 311 Copilot: report

## 1. Problem

Boston 311 takes about 840 requests a day. Two things go wrong, and both cost money:

1. **Routing.** A resident's words have to become one of 170 type / department / queue combinations. A wrong queue
   means a repeat call, rework and a late fix.
2. **Staffing.** Demand is seasonal (Parks more than triples from January to June; Public Works peaks in late summer),
   but crews can't change fast. Hires train for a month, releases need notice plus 25% severance, and only Parks can
   use seasonal crews (at a 30% premium). Today Transportation closes only about half its requests on time.

Good routing makes the demand numbers true; a good plan gets the routed requests closed on time.

## 2. Data

Analyze Boston "311 Service Requests", yearly files 2022–2025 (1.18M cases). Kept: open, close and SLA target
dates, on-time flag, department, type, queue, source, neighborhood, lat/lon. Dropped: cases closed as duplicate or
invalid, rows with no department, the `Test` department. 2022 is used only as extra forecast history; the catalog,
equity and routing tables use 2023–2025.

- The **170 combinations** are the type / department / queue triples with 500+ cases in 2023–25. They cover
  **72 request types**: a pothole, for example, goes to one of 21 queues depending on the district.
- **City employees logged 42%** of requests (`source = Employee Generated`), which matches the brief.
- 2024 on-time rates: Transportation 47%, Inspectional Services 70%, Public Works 90%, Parks 93%.

## 3. Demand forecast

Per department, three candidates: **seasonal naive** (same month last year: the baseline), **damped Holt-Winters
ETS** (additive or multiplicative by AIC), and **seasonal naive scaled by recent year-over-year change**. The model
is chosen on backtest A (train 2022–23, score 2024); backtest B (train 2022–24, score 2025) is a true holdout,
because 2025 is the plan year and its actuals exist. The p10–p90 band comes from backtest-A relative errors (at
least ±5%). Those residuals also drive the simulation.

| Department | Chosen | WAPE 2024 (selection) naive → chosen | WAPE 2025 (holdout) naive → chosen |
|---|---|---|---|
| Transportation | naive × trend | 7.2% → 4.5% | 4.6% → 4.7% |
| Inspectional Services | ETS | 11.4% → 8.8% | 7.1% → 6.1% |
| Public Works | seasonal naive | 12.1% | 19.7% |
| Parks | ETS | 15.6% → 12.4% | 36.0% → 42.4% |

**Honest reading.** The forecast beats same-month-last-year in selection for 3 of 4 departments, and in the 2025
holdout for Inspectional Services. On the holdout the chosen model is about even with naive for Transportation
and Public Works, and worse for Parks. Parks requests fell 26% in 2025 (17.1k → 12.7k) and Public Works 16%. No
model trained on 2022–24 saw those level drops coming. They are exactly what the **Monitor agent** exists to catch:
replaying 2025, it flags Public Works year-to-date demand 16% under forecast and Parks June under its band.

## 4. Crew-planning optimizer

An integer program over 4 departments × 12 months (PuLP + CBC, ~1 s).

- **Decisions:** active crews `x`, hires `h` (paid while training, productive after 1 month), releases `r` (leave
  next month, 25% severance), Parks seasonals `s` (1.3× cost, immediate).
- **Flows:** served `q ≤ k·(x+s)`; backlog `B_t = B_{t-1} + D_t − q_t`; `L30_t ≥ B_{t-1} − q_t` (old work served
  first; anything older than a month counts as 30+ days late).
- **Objective:** crew cost (incl. trainees) + severance + seasonal premium + $20 × backlog + $100 × L30.
- **Target:** on-time share `Σ(D−B)/ΣD ≥ τ` **in each department** (τ = 85% by default). Without it, the cheapest
  plan lets Inspectional Services fall to 58% and Parks to 67% to save $164k.
- **Shadow prices:** re-solve with integers relaxed and read each capacity constraint's dual × `k`. The result is
  the late cost saved by one more crew that month.

**Inputs (params.yaml).** Crew cost is $130k for every department; the brief gives Public Works only, so the other
three are assumed. Requests per crew per month are assumed: Public Works 250, Transportation 300, Parks 60,
Inspectional Services 70. **Starting crews are calibrated**: the smallest flat crew count whose simulated 2024
on-time rate reaches the real 2024 rate. That gives Public Works 53, Transportation 20, Parks 38 and Inspectional
Services 20.

**Results (2025 forecast demand).**

| Plan | Cost | On time | Transportation | Parks | ISD | PW |
|---|---|---|---|---|---|---|
| Flat (today's crews) | $19.46M | 75.2% | 38.0% | 94.7% | 84.7% | 91.6% |
| Level (avg demand ÷ k) | $17.85M | 81.0% | 87.7% | 38.2% | 84.7% | 82.1% |
| **Optimised (τ = 85%)** | **$17.34M** | **92.5%** | 97.2% | 85.8% | 85.1% | 91.6% |

- **Saving: $2.13M vs flat, $0.51M vs level.**
- What it does: Transportation hires 3 crews in February and 1 in March (20 → 24); Parks releases 15 permanent
  crews after January and covers May–August with 11 / 20 / 16 / 4 seasonal crews; Public Works holds at 53.
- **Trade-off to state plainly:** Parks drops from 94.7% to 85.8% on time. It was over-staffed for winter, and the
  plan spends that money on Transportation.
- **Cost vs on-time frontier:** flat at $17.17M up to a 55% target; $17.34M at 85%; $17.58M at 95%.
- **Shadow prices:** one more Parks crew in May–August saves about $14.1k a month in late costs, against
  $10.8k for a crew-month. One more Inspectional Services crew in June saves $21.7k.

**Does "closed within the month = on time" fit history?** Only partly. We ran today's crews flat through 2023–24
actual demand and compared the model's monthly on-time rate with the real one. For Transportation the correlation
is 0.70. For the other three it is negative, with a mean absolute error of 11–26 points: their real on-time rate
barely moves between busy and quiet months, which suggests staff absorb peaks (overtime, re-prioritising) in ways
the model doesn't. So the model is a **conservative proxy** for SLA on-time, not a replica of it.

## 5. Sensitivity and scenarios

We keep two questions apart. **Locked:** keep the saved plan and live with a new world. **Re-planned:** what we'd
pick if we knew.

| Case | Keep plan | Re-plan |
|---|---|---|
| Demand −20% | $16.94M · 99.9% | $14.90M · 91.5% |
| Demand +10% | $19.86M · 55.4% | $18.74M · 90.9% |
| Demand +20% | $30.77M · 30.0% | $20.37M · 89.4% |
| Snowstorm (real data) | $17.68M · 86.4% | $17.59M · 90.5% |
| Crew output −10% | $20.20M · 51.0% | $18.85M · 89.9% |
| Training 2 months | $17.49M · 89.7% | $17.39M · 92.5% |
| Late cost $40 | $17.74M · 92.5% | $17.70M · 93.6% |
| Severance 50% | $17.86M · 92.5% | $17.72M · 92.5% |

- **The plan is fragile to under-forecasting.** A 10% demand miss costs $1.1M more than re-planning would. This is
  the strongest argument for the Monitor agent.
- **Storm from real data:** the worst winter days in 2022–24 were 2022-01-31 (3.1× normal), 2024-12-23 and
  2023-12-18. Injecting the extra requests from those storms into January–February adds 17,050 late requests and
  $341k if we don't adjust. Re-planning ahead recovers $92k.
- **Tornado (re-planned cost change):** crew cost ±10% moves cost ±$1.7M; crew output −10% / +10% moves it
  +$1.5M / −$1.1M; demand ±10% −$1.2M / +$1.4M; severance −$0.33M / +$0.38M; late cost −$0.28M / +$0.36M;
  seasonal premium ±$0.1M; training time under $0.1M. The 30+ day cost never binds.
- **100 simulated years** (bootstrapped forecast errors with a shared year-level shock, plan locked): cost p10 /
  p50 / p90 = $17.17M / $17.42M / $18.32M. **All four departments hit 85% in only 5 of 100 years** (Transportation
  89, Public Works 76, Parks 48, Inspectional Services 21). The plan sits right at the target for Inspectional
  Services and Parks, so any miss tips them under.
- **Robust plan** (one plan optimised over 20 sampled years): every department at target in 16 of 100 years, median
  cost $17.50M (+$75k). That's better but still tight. A city wanting 85% with high confidence should plan to
  about 90%.
- **Employee work smoothing:** moving 30% of employee-logged work out of above-average months into quieter months
  saves **$408k a year** and cuts the Parks peak from 43 to 38 crews.

## 6. Intake assistant

**Pipeline:**
1. **Safety gate.** Regex in English and the 5 test languages, plus the LLM's urgency field. Emergencies show
   *Call 911* and nothing is filed; injection and off-topic messages get a polite refusal.
2. **Privacy scrub.** Phones, emails and self-introduced names are removed before logging; only scrubbed text is
   stored.
3. **Photo.** `moondream` writes one line describing it.
4. **Retrieve.** 0.8 × multilingual MiniLM cosine + 0.2 × TF-IDF over **72 hand-written type cards** (name,
   description, 3 resident phrasings); keep the top 10.
5. **Classify.** `qwen2.5:3b` with a JSON-schema constrained output (category id is an enum of the 10 retrieved
   cards), validated by Pydantic, retried once.
6. **Clarify.** One follow-up question when confidence is under 0.6.
7. **Route by location.** The text decides the **type**; the **queue** comes from location: geocode (Nominatim) →
   nearest historical case → neighborhood → that type's most common queue there.
8. **Duplicates.** Same type, open, within 200 m.

In retrieval mode (the default, see below), the top match with a softmax-margin confidence is the answer.

**Test set:** 201 messages, written and labelled **before any model run**: 101 common (weighted by real volume), 20
long-tail, 30 ambiguous (each with a scripted follow-up reply), 20 multilingual (4 each: Spanish, Haitian Creole,
Chinese, Vietnamese, Portuguese), 15 emergencies, 15 off-topic / injection. Alternative acceptable labels are
recorded for genuinely overlapping types.

**Results:**

| | Retrieval only (no LLM) | Local LLM (qwen2.5:3b) |
|---|---|---|
| Type accuracy | **94.2%** | 81.9% |
| Department accuracy | **97.1%** | 89.5% |
| Type accuracy excl. near-copies of card examples | 90.3% | 76.7% |
| Top-10 retrieval hit rate | 98.8% | 98.8% |
| TF-IDF baseline (nearest card) | 83.0% | 83.0% |
| Emergencies caught / false alarms | 15/15 · 0% | 15/15 · 0% |
| Injection & off-topic refused / real requests refused | 15/15 · 1.2% | 15/15 · 0.6% |
| Ambiguous: first try → after one follow-up | 90.0% → 93.3% | 80.0% → 80.0% |
| Share sent a follow-up question | 11.4% | 0.5% |
| By language (4 each): es / ht / zh / vi / pt | 75 / 25 / 100 / 75 / 100% | 75 / 25 / 100 / 25 / 75% |
| Latency p50 / p95 | 60 ms / 1.2 s | 18.9 s / 37.7 s |
| Tokens per request · cost | 0 · $0 | 473 · $0 (local) |

**The key finding: on this laptop, retrieval beats the local LLM.** The 3B model overrides correct top
retrieval matches with near-synonyms (dumping → construction debris, street cleaning → litter basket). It is
overconfident: it asked a follow-up for 0.5% of messages, against 11% for retrieval. Vietnamese also drops to 25%.
We tested a hybrid in which retrieval decides when it is confident and the LLM only when it isn't: accuracy stayed
at 93.6% or fell, because the LLM fixed just 2 of the messages retrieval got wrong. So the app **routes with
retrieval by default**. The local LLM remains a switch, and it still reads photos and powers the agents' optional
LLM mode. A larger model (7B+ or hosted) may well reverse this; `make eval-llm` re-runs the comparison with
`INTAKE_MODEL` set to any Ollama model.

**Honesty check (leakage).** The same author wrote the cards and the test set, so 68 messages sit within 0.85 cosine
of a card example. On the other 103, retrieval-only type accuracy is **90.3%**.

**Queue from location**, tested on 286 real 2025 cases with their true type and coordinates: 83.2% exact queue,
95.8% department, and 65.0% for types with several district queues. Some real queues fall outside the 170 catalog
combinations, which caps this score.

**Human review queue.** Requests under the 0.6 cut-off go to a staff list, and the Evaluation tab plots the share
routed automatically against its accuracy at every cut-off.

**Equity.** In 2023–24, on-time by neighborhood ranged from 67% (Charlestown) to 87% (Beacon Hill). Weighting each
neighborhood's request mix by each department's on-time gain, the 5 worst-served neighborhoods gain 20.2 points on
average against 10.2 for the 5 best-served (correlation −0.70). The gains go mostly to the worst-served areas,
because those areas file a lot of Transportation work.

## 7. Agents

One tool registry (`agents/tools.py`) is used by the API and the agents and is also served over MCP. Each agent is
a system prompt, a tool allowlist and a step limit, run by one `run_agent` loop. The loop uses Ollama tool calls
when available. Every number in an answer must match a tool result from that turn: an ungrounded answer gets one
retry, then the agent's scripted policy (the same tools, a fixed order) takes over. Every step is traced to SQLite
and shown in the UI.

- **Intake:** classify → ask for clarification or a location (at most 3 follow-ups) → duplicates → expected fix
  time → file. Low-confidence requests go to the review queue.
- **Planner:** `get_plan`, `get_forecast`, `explain_month`, `run_scenario`, `compare_baselines`, `solve_plan`, and
  a hand-off to the stress-test agent. It says "I don't have that" when no tool answers the question.
- **Stress-test:** a greedy search over demand (+10 / +20%), storm, crew output (−10%) and training (2 months). It
  finds the brute-force grid's worst case (all four at once: $54.4M, 12% on time; re-planning saves $29.5M) in 13
  of 24 probes.
- **Monitor:** live demand (2025 replayed to a chosen month, plus requests filed in the app) against the band;
  drafts a re-plan for the rest of the year. **No agent can commit a plan**: only `POST /plan/approve/{id}`, from
  the Approve button, does that.

In LLM mode the 3B model picks sensible tools and its numbers pass the grounding check. Its reasoning can still be
wrong, though: it once called 2,550 requests "higher than" a capacity of 2,580. The grounding check catches
invented numbers, not bad logic. On this CPU-only laptop the model takes 20–60 s per tool step. The UI defaults to the scripted policy (instant)
and offers the LLM as a toggle; the trace shows which mode ran.

## 8. Responsible AI

- **Safety first.** The emergency gate runs before any model; 15 of 15 emergencies caught, 0 false alarms across
  186 non-emergencies.
- **Privacy.** Raw text is never stored, only the scrubbed text.
- **The message is data.** Injection patterns are refused, and the classifier can only output an id from the 10
  offered cards.
- **People stay in control.** Plans change only through a person's Approve click; low-confidence requests go to
  311 staff.
- **Local models.** No resident text leaves the machine except the location phrase sent to the geocoder.

## 9. Limits

- Crew output, three of the four crew costs and the 85% target are assumptions (`params.yaml`). Starting crews are
  calibrated, not observed.
- The on-time rule is a coarse proxy for SLA compliance (Section 4).
- 2025 level shifts (Parks −26%, Public Works −16%) make the 2025 forecast weak for those two departments.
- The test set has a single author. A second labeller should review a sample.
- The 3B local model is slow on CPU and weaker than a hosted model on Haitian Creole and on multi-step tool use.
