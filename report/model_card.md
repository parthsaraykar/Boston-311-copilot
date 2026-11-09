# Model card: Boston 311 intake assistant

**What it does.** Reads a resident's message (any language; optional photo) and returns one of the 72 request
types in Boston 311's 170 type / department / queue combinations. The queue comes from the location. It also
returns a confidence score, a one-line reason, and the location and neighborhood. It says *Call 911* for
emergencies and refuses off-topic or manipulative messages.

**Models.**
- `qwen2.5:3b` (local, via Ollama; optional, off by default): picks one of 10 retrieved categories under a JSON schema.
- `paraphrase-multilingual-MiniLM-L12-v2` + TF-IDF: retrieval.
- `moondream` (local): one-line photo description.
- Default: the top retrieval match is used.

**Intended use.** A first-pass router for 311 staff and residents. Low-confidence requests (< 0.6) go to a human
review queue. Not for emergencies: those are detected and sent to 911.

**Test results.** 201 hand-labelled messages; see `eval/eval.json` and the Evaluation tab.
- Retrieval only: type accuracy 94.2% (90.3% excluding near-copies of card examples), department 97.1%, top-10
  hit rate 98.8%, TF-IDF baseline 83.0%.
- Emergencies caught: 15 / 15, with 0 false alarms. Injection / off-topic refused: 15 / 15.
- By language (retrieval only, 4 messages each): Spanish 75%, Portuguese 100%, Chinese 100%, Vietnamese 75%,
  **Haitian Creole 25%**.
- Local LLM (`qwen2.5:3b`): type 81.9%, department 89.5%, same safety results, p50 19 s. It is worse than
  retrieval, so retrieval is the default; the LLM is optional.

**Known failure cases.**
- Haitian Creole is weak: the multilingual embedding model has little Creole training data, and so does the 3B
  LLM.
- Near-synonym types get confused: bulk item vs mattress pickup, illegal dumping vs trash barrels, street cleaning
  vs unshoveled sidewalk.
- Queue choice depends on geocoding. Vague places ("near my house") fall back to the type's busiest queue, and the
  assistant asks for a location.
- A message that mixes a real request with an injection attempt is refused as a whole.

**Privacy.** Phone numbers, emails and self-introduced names ("my name is…", "me llamo…") are removed before
anything is logged; raw text is never stored. Everything runs locally except the location phrase, which is sent to
OpenStreetMap Nominatim for geocoding.

**Limits.** The cards and the test set were written by the same author; a second labeller should review them. The
test set is small for minority languages (4 each), so per-language numbers have wide error bars.
