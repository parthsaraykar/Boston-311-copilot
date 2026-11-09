# Demo script (5 minutes)

Before: `make reset && make demo-cache`, start `make api`, open http://localhost:8000. Planner tab: Replay through Jun.

1. **0:00 — Problem (30 s).** 840 requests a day; Parks triples Jan → Jun; crews take a month to train and cost 25%
   to release. Two mistakes cost money: the wrong queue and the wrong number of crews.
2. **0:30 — Resident tab (75 s).**
   - "big hole near the Jackson Sq T stop, almost blew a tire" → Pothole, Public Works, District 02 Jamaica Plain,
     map pin.
   - The Spanish example → Pothole.
   - "downed wire sparking on Washington St" → red 911 banner, nothing filed.
   - Show the QR code (Planner tab, bottom): judges file live, and the counter on the Planner tab goes up.
3. **1:45 — Planner tab (90 s).**
   - KPIs: $17.34M vs $19.46M flat, saving $2.13M; on time 75% → 92.5%.
   - Drag the on-time target and watch the frontier point move. Set demand +10%: keeping the plan costs $19.86M
     at 55% on time.
   - Ask "Why hire Parks crews in April?": the agent answers that the plan uses seasonal crews from May (11), and
     that one more crew in April saves $9.2k against $10.8k a crew-month. It lists its sources.
4. **3:15 — Agents at work (60 s).**
   - Run stress test: worst case is demand +20% + storm + slower crews + slower hiring; it matches the
     brute-force grid in 13 of 24 probes.
   - Run monitor (through Jun): Public Works −16% YTD, Parks June under the band, so it drafts a re-plan.
   - Approve it, then open the trace.
5. **4:15 — Proof (45 s).** Evaluation tab: 94% type / 97% department, 100% of emergencies caught, accuracy by
   language (be honest: Haitian Creole is weak), and the honesty check at 90%. Toggle to the LLM column: the local
   3B model scored 82%, so we route with retrieval. We measured it instead of assuming the LLM is better. Close on the loop: routed requests
   feed the plan.

Fallbacks: with Ollama off, everything runs in fast / scripted mode. The video backup is in `report/`.
