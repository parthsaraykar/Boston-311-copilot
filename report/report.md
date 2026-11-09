# Boston 311 Copilot: report

_IE 5374 Applied Generative AI · Module 7 Hackathon · Team 4 (Parth Sanjay Saraykar, Rutuja Kalidasrao Jadhav, Samruddhi Bansod)._
_**AI-generated section:** this report was drafted with Claude Code (an AI coding assistant) from the project's own outputs, following the team's analysis decisions; the team reviewed it. See README, "How we used AI"._

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
  next month, 25% of annual cost), Parks seasonals `s` (1.3× monthly cost, no training, no release cost,
  **April–October only**).
- **Flows:** served `q ≤ k·(x+s)`; backlog `B_t = B_{t-1} + D_t − q_t`, starting at zero as the brief allows;
  `L30_t ≥ B_{t-1} − q_t` (old work is served first, and anything left over a month counts as 30+ days late).
- **Objective:** crew cost (including trainees) + severance + seasonal cost + $20 × backlog + $100 × L30.
- **Target:** on-time share `Σ(D−B)/ΣD ≥ τ` **in each department**, with τ = 85% (our choice; the brief leaves it
  open). Without it, the cheapest plan lets Inspectional Services fall to 58% and Parks to 73% to save $71k.
- **Shadow prices:** re-solve with integers relaxed and read each capacity constraint's dual × `k`. That's the
  late cost one more crew would save in that month.

**Inputs: the brief's, as stated.**

| | Capacity | k = per crew-month | Annual cost | Crews, Jan 2025 |
|---|---|---|---|---|
| Public Works | 12 per day | 252 | $130,000 | 50 |
| Transportation | 15 per day | 315 | $110,000 | 18 |
| Parks | 6 per day | 126 | $120,000 | 10 |
| Inspectional Services | 4 per day | 84 | $140,000 | 16 |

**Results (2025 forecast demand):**

| Plan | Cost | On time | Transportation | Parks | ISD | PW |
|---|---|---|---|---|---|---|
| Flat (January crews all year) | $18.87M | 59.7% | 29.8% | 30.6% | 74.9% | 77.5% |
| Level (average demand ÷ k) | $14.47M | 82.5% | 89.8% | 37.0% | 74.9% | 84.9% |
| **Optimised (τ = 85%)** | **$13.57M** | **91.5%** | 97.8% | 86.7% | 85.9% | 89.4% |

- **Saving: $5.30M vs flat, $0.90M vs level.** Flat staffing is expensive because the backlog snowballs: work
  left over keeps costing $20 a month, and $100 once it's 30+ days old.
- **What the plan does (month-by-month table in notebook §3):**
  - Transportation hires 1 crew in January, 3 in February and 1 in March (18 → 23). It's the most short-staffed
    department.
  - Parks keeps its 10 permanent crews and adds seasonal crews in April, May, June, July and August (1, 6, 10,
    9, 5), with no training and no release cost.
  - Public Works hires 1 in March and 1 in April (50 → 52).
  - Inspectional Services hires 1 in June (16 → 17).
  - Nobody is released: with 25% severance, carrying a crew through a slow month is cheaper than releasing it.
- **Cost vs on-time frontier:** $13.50M up to a 55% target, $13.57M at 85%, $13.74M at 95%.
- **Shadow prices:**
  - One more Parks crew in April–August would save about $13.0k a month in late costs, against $10.0k for a
    crew-month.
  - One more Public Works crew in July would save $25.2k.
  - One more Inspectional Services crew in June would save $23.3k.

**Does "closed within the month = on time" fit history?** Only partly. We ran January crews flat through
2023–24 actual demand and compared the model's monthly on-time rate with the real one. Transportation correlates
at 0.75. The other departments don't: their real on-time rate barely moves between busy and quiet months, which
suggests staff absorb peaks in ways the model doesn't capture. Also, many Parks requests have 365-day SLA targets.
So the model is a **conservative proxy** for SLA on-time, not a replica of it.

## 5. Sensitivity and scenarios

We keep two questions apart. **Locked:** keep the saved plan and live with a new world. **Re-planned:** what we'd
pick if we knew.

| Case | Keep plan | Re-plan | Re-planning saves |
|---|---|---|---|
| Demand −20% | $13.11M · 100% | $11.51M · 92.2% | $1.61M |
| Demand −10% | $13.20M · 98.2% | $12.51M · 91.1% | $0.70M |
| Demand +10% | $17.39M · 47.1% | $14.89M · 90.3% | $2.50M |
| **Demand +20%** | **$29.35M · 25.0%** | $16.34M · 89.1% | **$13.01M** |
| Snowstorm (real data, Jan–Feb) | $14.43M · 75.9% | $13.97M · 90.1% | $0.46M |
| Heat wave (real data, Jul–Aug) | $14.00M · 83.8% | $13.94M · 89.6% | $0.05M |
| Crew output −10% | $17.83M · 43.4% | $14.98M · 89.1% | $2.85M |
| Training 2 months | $13.82M · 86.8% | $13.65M · 91.4% | $0.17M |
| Late cost $40 | $14.02M · 91.5% | $13.90M · 94.6% | $0.12M |

- **Under-forecasting is the dangerous direction.** At +20% the backlog snowballs and a locked plan costs more
  than double. Over-forecasting just means idle crews.
- **Storms and heat waves come from real data.** We found the days in 2022–24 with the highest citywide counts
  against a 28-day rolling median, and added each spike's extra requests per department to the 2025 demand.
  - Snowstorms: 2022-01-31 (3.1× a normal day), 2024-12-23 and 2023-12-18, added to Jan–Feb. If the plan doesn't
    change, that's 43,162 more late requests and $0.86M.
  - Heat waves: 2022-08-31 (1.8×), 2023-08-31 and 2022-08-03, added to Jul–Aug. If the plan doesn't change,
    that's $0.43M.
- **Tornado (change in re-planned cost):** crew cost ±10% moves it ±$1.3M; crew output −10% / +10%, +$1.4M /
  −$0.9M; demand ±10%, −$1.1M / +$1.3M; late cost $10 / $40, −$0.26M / +$0.34M. Training time, the seasonal
  premium and severance each move it by under $0.1M.
- **100 simulated years** (bootstrapped forecast errors with a shared year-level shock, plan locked):
  - Cost p10 / p50 / p90: $13.35M / $13.65M / $14.89M.
  - All four departments hit 85% in only 6 of 100 years: Transportation 89, Public Works 68, Parks 53, Inspectional
    Services 24. The plan sits right at the target for Inspectional Services and Parks.
- **Robust plan** (one plan optimised over 20 sampled years): all four at target in 9 of 100 years, at a median cost
  of $13.64M. Planning to about 90% gives real headroom.
- **Employee-logged work:** 42% of requests are logged by city employees, and that work can be scheduled. Moving
  30% of it out of above-average months saves **$281k a year** and trims the Parks peak from 20 crews to 18.

## 5b. Proof on real data: the 2025 replay

What if Boston had run this in 2025? We replay the **real 2025 demand** month by month and score four strategies
on it. The plan starts from the January forecast (trained on 2022–24). With the monitor, the shipped Monitor rule
runs at the end of each month: when a department's demand leaves the forecast band, or is more than 8% off year to
date, it re-plans the remaining months. Past months stay fixed, and hires still need a month of training.

| Strategy, real 2025 demand | Cost | On time | Depts ≥ 85% | Worst dept |
|---|---|---|---|---|
| January crews all year | $15.11M | 70.2% | 1/4 | Transportation 32.8% |
| Optimised plan, never changed | $13.30M | 96.1% | 3/4 | Inspectional Services 71.4% |
| **Optimised plan + monitor** | **$14.19M** | **89.8%** | **4/4** | Public Works 85.5% |
| Perfect hindsight (lower bound) | $12.61M | 90.5% | 4/4 | Inspectional Services 85.3% |

- **The monitored plan is the only real strategy that keeps every department at target.** It costs $0.92M less
  than January crews and lifts on-time from 70% to 90%.
- **The plan that never changes is cheaper, but it fails a department.** 2025 demand fell well under forecast for
  Public Works (−16%) and Parks (−26%), so that plan was overstaffed there, and it still left Inspectional
  Services at 71%.
- **The monitor's cost is churn:** 11 re-plans and $1.06M of severance. The $1.58M gap to perfect hindsight is
  the value of a better forecast.
- **Rule variants, for transparency.** YTD-only, persistent-drift, target-margin and HR-capacity-cap variants were
  run on a 2024 replay (forecast trained through 2023) and on 2025. The 2024 selection picks the shipped rule.
  Every variant that's cheaper in 2025 lets a department fall to 61–75%.

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
  finds the brute-force grid's worst case (all four at once: $54.5M, 11% on time; re-planning saves $33.5M) in 13
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

- Crew capacity, costs and January crews are planning assumptions given by the brief. The 85% target and the
  $20 / $100 overdue costs drive the trade-off; the tornado shows how much they matter.
- The on-time rule is a coarse proxy for SLA compliance (Section 4).
- 2025 level shifts (Parks −26%, Public Works −16%) make the 2025 forecast weak for those two departments.
- The test set has a single author. A second labeller should review a sample.
- The 3B local model is slow on CPU and weaker than a hosted model on Haitian Creole and on multi-step tool use.
