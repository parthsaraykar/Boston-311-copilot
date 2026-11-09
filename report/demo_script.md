# Demo script (5 minutes)

Before: `make reset && make demo-cache`, start `make api`, then `make share` for the public link. Open http://localhost:8000. Agents page: replay through Jun.

1. **0:00 — Problem (30 s).** 840 requests a day; Parks triples Jan → Jun; crews take a month to train and cost 25%
   to release. Two mistakes cost money: the wrong queue and the wrong number of crews.
2. **0:30 — Resident tab (75 s).**
   - "big hole near the Jackson Sq T stop, almost blew a tire" → Pothole, Public Works, District 02 Jamaica Plain,
     map pin.
   - The Spanish example → Pothole.
   - "downed wire sparking on Washington St" → red 911 banner, nothing filed.
   - Show the QR code (Review page): judges file live from their phones over the public link, and their pins
     appear on City pulse.
3. **1:45 — Planner tab (90 s).**
   - KPIs: $13.57M vs $18.87M flat, saving $5.30M; on time 60% → 91.5%.
   - Drag the on-time target and watch the frontier point move. Set demand +10%: keeping the plan drops on-time
     to 47%.
   - Ask "Why hire Parks crews in April?": the agent answers that the plan uses seasonal crews from May (11), and
     that one more crew in April saves $9.2k against $10.8k a crew-month. It lists its sources.
4. **3:15 — Agents at work (60 s).**
   - Run stress test: worst case is demand +20% + storm + slower crews + slower hiring; it matches the
     brute-force grid in 13 of 24 probes.
   - Run monitor (through Jun): Public Works −16% YTD, Parks June under the band, so it drafts a re-plan.
   - Approve it, then open the trace.
5. **4:00 — 2025 replay (20 s).** On real 2025 demand, plan + monitor keeps all 4 departments at target
   ($14.19M vs $15.11M for January crews; on time 70% → 90%). Be upfront about the churn.
6. **4:20 — Proof (40 s).** Evaluation tab: 94% type / 97% department, 100% of emergencies caught, accuracy by
   language (be honest: Haitian Creole is weak), and the honesty check at 90%. Toggle to the LLM column: the local
   3B model scored 82%, so we route with retrieval. We measured it instead of assuming the LLM is better. Close on the loop: routed requests
   feed the plan.

Fallbacks: with Ollama off, everything runs in fast / scripted mode. The video backup is in `report/`.
