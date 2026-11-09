"""Safety gate (runs before anything else) and privacy scrubber (runs before anything is logged)."""
from __future__ import annotations

import re

# Emergencies: life safety -> "Call 911". Patterns cover English plus the five test languages.
EMERGENCY_PATTERNS = [
    # English
    r"\bgas (smell|leak)", r"\bsmell(s|ing)? (of |like )?gas\b", r"\bsmells? gas\b", r"\bcarbon monoxide\b", r"\bco alarm\b",
    r"\bspark(s|ing)\b", r"\b(downed|down|fallen|live|hanging|snapped) (power |electric(al)? )?(wire|line)s?\b",
    r"\b(power|electric(al)?) (wire|line)s? (is |are )?(down|on the ground|sparking|fell)",
    r"\bon fire\b", r"\b(house|building|car|apartment|kitchen) fire\b", r"\bfire (in|at|on)\b", r"\bflames?\b",
    r"\b(smoke|smoking) (coming|pouring)\b", r"\bexplosion\b",
    r"\b(person|man|woman|kid|child|someone|somebody|people|guy|lady|he|she)\b.{0,30}\b(hurt|injured|bleeding|unconscious|not breathing|collapsed|passed out|overdos\w*|trapped|hit by)\b",
    r"\b(hurt|injured|bleeding|unconscious|not breathing|collapsed|passed out|overdos\w*)\b.{0,20}\b(person|man|woman|kid|child|someone|somebody)\b",
    r"\bnot breathing\b", r"\bheart attack\b", r"\boverdos(e|ing)\b",
    r"\b(gun|shooting|shots fired|stabb(ed|ing)|knife)\b", r"\bbeing (attacked|assaulted|robbed)\b",
    r"\b(car|crash|accident)\b.{0,30}\b(injur|hurt|bleeding|trapped)\w*", r"\bdrowning\b",
    r"\bwater main (burst|break)\b.{0,40}\b(flood|electric)",
    # Spanish
    r"\bolor a gas\b", r"\bfuga de gas\b", r"\bhuele a gas\b", r"\bcables? (ca[ií]dos?|el[eé]ctricos? ca[ií]dos?)\b",
    r"\bchispas?\b", r"\bchispeando\b", r"\bincendio\b", r"\bfuego\b", r"\bherid[oa]s?\b", r"\bsangrando\b", r"\bno respira\b",
    r"\binconsciente\b",
    # Haitian Creole
    r"\bsant gaz\b", r"\bgaz k ap koule\b", r"\bdife\b", r"\bblese\b", r"\bfil (kouran|elektrik)\b", r"\bpa respire\b",
    r"\bap senyen\b", r"\bsanble gaz\b",
    # Portuguese
    r"\bcheiro de g[aá]s\b", r"\bvazamento de g[aá]s\b", r"\bfogo\b", r"\binc[eê]ndio\b", r"\bfios? (ca[ií]dos?|el[eé]tricos?)\b",
    r"\bfa[ií]scas?\b", r"\bferid[oa]s?\b", r"\bn[aã]o est[aá] respirando\b", r"\bdesmaiad[oa]\b",
    # Vietnamese
    r"mùi gas", r"mùi ga\b", r"rò rỉ gas", r"cháy", r"dây điện", r"tia lửa", r"bị thương", r"chảy máu", r"không thở", r"bất tỉnh",
    # Chinese
    r"煤气", r"燃气", r"天然气", r"着火", r"火灾", r"起火", r"电线", r"火花", r"受伤", r"流血", r"不能呼吸", r"没有呼吸", r"昏迷",
]
# Phrases that look like emergencies but are ordinary 311 work.
EMERGENCY_EXCEPTIONS = [r"\bfire hydrant\b", r"\bgas (station|street ?light|lamp|light)\b", r"\bfireworks?\b",
                        r"\bcampfire\b", r"\bfire ?place\b", r"\bfire escape\b"]

INJECTION_PATTERNS = [
    r"\bignore\b.{0,40}\b(instruction|prompt|rule|previous|above)s?\b", r"\bdisregard\b.{0,40}\b(instruction|rule|prompt)",
    r"\bsystem prompt\b", r"\byou are now\b", r"\bact as\b", r"\bpretend (to be|you)\b", r"\bjailbreak\b",
    r"\bdeveloper mode\b", r"\breveal\b.{0,30}\b(prompt|instruction|secret|key)", r"\bnew instructions?\b",
    r"\boverride\b.{0,30}\b(rule|safety|instruction)", r"\bprint (your|the) (prompt|instructions)\b",
    r"\b(set|change|make)\b.{0,30}\b(confidence|priority|urgency)\b.{0,20}\b(1(\.0)?|100|max|highest)\b",
    r"</?(system|assistant|instructions?)>", r"\bDAN\b",
]

# Civic words: a message with none of these and no close category match is treated as off-topic.
CIVIC_HINTS = r"\b(street|road|sidewalk|trash|garbage|tree|park|light|sign|car|parking|pothole|rat|mice|noise|landlord|apartment|heat|graffiti|needle|dump|snow|water|drain|bike|vehicle|signal|building|construction|crosswalk|recycl|bin|cart|mattress|couch|animal|dog|bus|leak|mold|lot|hydrant|dead|pickup|pick up|broken|calle|basura|árbol|luz|rue|lari|fatra|rua|lixo|đường|rác|街|垃圾|路|灯)\w*"


def check(text: str) -> dict:
    """Returns {kind: 'emergency'|'injection'|'ok', matched: pattern or None}."""
    low = text.lower()
    masked = low
    for ex in EMERGENCY_EXCEPTIONS:
        masked = re.sub(ex, " ", masked)
    for p in EMERGENCY_PATTERNS:
        if re.search(p, masked, flags=re.IGNORECASE):
            return {"kind": "emergency", "matched": p}
    for p in INJECTION_PATTERNS:
        if re.search(p, text, flags=re.IGNORECASE):
            return {"kind": "injection", "matched": p}
    return {"kind": "ok", "matched": None}


def looks_civic(text: str) -> bool:
    return re.search(CIVIC_HINTS, text.lower()) is not None


# ---------- privacy ----------

PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
NAME = re.compile(
    r"\b(my name is|my name's|this is|i am|i'm|me llamo|mi nombre es|meu nome [eé]|mwen rele|tôi tên là|tên tôi là)\s+"
    r"([A-ZÀ-Ý][\w'’-]+(?:\s+[A-ZÀ-Ý][\w'’-]+){0,2})", re.IGNORECASE)
NAME_ZH = re.compile(r"(我叫|我的名字是)\s*\S{1,4}")
# words that follow "I am"/"I'm" but are not names
NOT_NAMES = {"a", "an", "the", "not", "so", "very", "really", "calling", "writing", "reporting", "tired", "sick",
             "worried", "concerned", "trying", "looking", "here", "at", "in", "on", "near", "outside", "home", "going",
             "getting", "unable", "afraid", "sure", "having", "just", "still", "renting", "living", "standing"}


def scrub(text: str) -> tuple[str, list[str]]:
    """Remove phone numbers, emails and self-introduced names. Returns (clean_text, kinds_removed)."""
    removed = []
    if EMAIL.search(text):
        text, removed = EMAIL.sub("[EMAIL]", text), removed + ["email"]
    if PHONE.search(text):
        text, removed = PHONE.sub("[PHONE]", text), removed + ["phone"]

    def _name(m):
        first = m.group(2).split()[0].lower()
        if first in NOT_NAMES or (m.group(1).lower() in ("i am", "i'm", "this is") and not m.group(2)[0].isupper()):
            return m.group(0)
        removed.append("name")
        return f"{m.group(1)} [NAME]"

    text = NAME.sub(_name, text)
    if NAME_ZH.search(text):
        text = NAME_ZH.sub(lambda m: m.group(1) + "[NAME]", text)
        removed.append("name")
    return text, sorted(set(removed))
