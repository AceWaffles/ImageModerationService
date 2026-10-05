"""Allow / Review / Reject from the detectors' raw signals.

Reject  - OpenAI flags graphic violence or self-harm; or OpenAI flags sexual content AND an
          independent detector confirms explicit content (GantMan porn+hentai, or a NudeNet
          exposed breast/genitalia/buttocks/anus detection).
Review  - OpenAI flags sexual content without that confirmation; or NudeNet sees explicit content
          OpenAI did not flag (the detectors disagree, so a person decides).
Allow   - everything else, including ordinary non-graphic violence.

GantMan alone never escalates: on real trading-card art it scores some cartoons as explicit.

Thresholds are deployment configuration (environment), not code, so a published copy of this
file does not reveal the live values:
  MODERATION_GANTMAN_EXPLICIT   default 0.70
  MODERATION_NUDENET_EXPLICIT   default 0.50
"""
import os

POLICY_VERSION = "2026-10-05"

ALWAYS_REJECT = ("violence/graphic", "self-harm", "self-harm/intent", "self-harm/instructions")
EXPLICIT_NUDENET = {"FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED",
                    "BUTTOCKS_EXPOSED", "ANUS_EXPOSED"}


def _threshold(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def evaluate(openai: dict, gantman: dict, nudenet: list[dict]) -> tuple[str, list[str]]:
    categories = openai["categories"]
    reasons = [f"openai:{c}" for c in ALWAYS_REJECT if categories.get(c)]
    if reasons:
        return "reject", reasons

    gantman_limit = _threshold("MODERATION_GANTMAN_EXPLICIT", 0.70)
    nudenet_limit = _threshold("MODERATION_NUDENET_EXPLICIT", 0.50)

    sexual = bool(categories.get("sexual"))
    gantman_explicit = gantman["porn"] + gantman["hentai"]
    nudenet_explicit: dict[str, float] = {}
    for d in nudenet:
        if d["class"] in EXPLICIT_NUDENET and d["score"] >= nudenet_limit:
            nudenet_explicit[d["class"]] = max(d["score"], nudenet_explicit.get(d["class"], 0.0))

    if sexual:
        reasons.append("openai:sexual")
    if gantman_explicit >= gantman_limit:
        reasons.append(f"gantman:explicit {gantman_explicit:.2f}")
    reasons += [f"nudenet:{c} {s:.2f}" for c, s in nudenet_explicit.items()]

    confirmed = gantman_explicit >= gantman_limit or bool(nudenet_explicit)
    if sexual and confirmed:
        return "reject", reasons
    if sexual or nudenet_explicit:
        return "review", reasons
    return "allow", reasons
