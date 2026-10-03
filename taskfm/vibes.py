"""Map a coding-task prompt to a listening vibe.

Pure text in, vibe out. No network, no model, no config needed - so the answer is
instant and identical every run. Spotify playlist *searches* live here too, so one
table is the whole product: words -> mood -> radio station.

Scoring rules
-------------
* Concrete nouns and phrases (`css`, `readme`, `stack trace`) are STRONG = 2:
  they say what the work *is*.
* Generic action verbs (`fix`, `write`, `build`) are SOFT = 1: they say what you're
  doing, not what about. So "fix the readme" reads as docs, not as a bug hunt.
* A vibe must reach `min_score` (default 1) or taskfm leaves your music alone.
* Ties go to the vibe listed earlier; `focus` sits last as the catch-all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STRONG = 2.0
SOFT = 1.0


@dataclass(frozen=True)
class Vibe:
    name: str
    blurb: str
    queries: tuple[str, ...]
    keywords: dict[str, float]


@dataclass
class Match:
    vibe: Vibe | None
    score: float
    matches: list[tuple[str, float]] = field(default_factory=list)
    reason: str = ""


VIBES: tuple[Vibe, ...] = (
    Vibe(
        name="debug",
        blurb="fixing what's broken",
        queries=("deep techno focus", "minimal techno", "techno focus", "electronic focus"),
        keywords={
            "root cause": STRONG,
            "stack trace": STRONG,
            "stacktrace": STRONG,
            "flaky test": STRONG,
            "failing test": STRONG,
            "not working": STRONG,
            "error message": STRONG,
            "race condition": STRONG,
            "memory leak": STRONG,
            "step through": STRONG,
            "debugger": STRONG,
            "debugging": STRONG,
            "debug": STRONG,
            "traceback": STRONG,
            "exception": STRONG,
            "regression": STRONG,
            "reproduce": STRONG,
            "bisect": STRONG,
            "segfault": STRONG,
            "deadlock": STRONG,
            "investigate": STRONG,
            "diagnose": STRONG,
            "flaky": STRONG,
            "crash": STRONG,
            "broken": STRONG,
            "failing": STRONG,
            "failure": STRONG,
            "panic": STRONG,
            "hang": STRONG,
            "hanging": STRONG,
            "glitch": STRONG,
            "bug": STRONG,
            "error": STRONG,
            "issue": STRONG,
            "leak": STRONG,
            "wrong": STRONG,
            "fix": SOFT,
            "fixing": SOFT,
        },
    ),
    Vibe(
        name="ship",
        blurb="shipping and infrastructure",
        queries=("synthwave", "retrowave", "outrun synthwave", "cyberpunk"),
        keywords={
            "ci/cd": STRONG,
            "continuous integration": STRONG,
            "github actions": STRONG,
            "rolling deploy": STRONG,
            "load balancer": STRONG,
            "docker compose": STRONG,
            "deploy": STRONG,
            "deployment": STRONG,
            "docker": STRONG,
            "kubernetes": STRONG,
            "k8s": STRONG,
            "terraform": STRONG,
            "pipeline": STRONG,
            "rollback": STRONG,
            "release": STRONG,
            "shipping": STRONG,
            "infra": STRONG,
            "server": STRONG,
            "nginx": STRONG,
            "aws": STRONG,
            "gcp": STRONG,
            "azure": STRONG,
            "infrastructure": STRONG,
            "monitoring": STRONG,
            "grafana": STRONG,
            "prometheus": STRONG,
            "uptime": STRONG,
            "scaling": STRONG,
            "dns": STRONG,
            "ssl": STRONG,
            "tls": STRONG,
            "cron": STRONG,
            "certificate": STRONG,
            "provision": SOFT,
        },
    ),
    Vibe(
        name="data",
        blurb="queries, numbers and models",
        queries=("lofi jazz", "jazz study", "chillhop", "lofi beats"),
        keywords={
            "machine learning": STRONG,
            "dataframe": STRONG,
            "analytics": STRONG,
            "visualize": STRONG,
            "visualization": STRONG,
            "statistics": STRONG,
            "correlation": STRONG,
            "spreadsheet": STRONG,
            "embeddings": STRONG,
            "embedding": STRONG,
            "warehouse": STRONG,
            "bigquery": STRONG,
            "snowflake": STRONG,
            "postgres": STRONG,
            "postgresql": STRONG,
            "mysql": STRONG,
            "sqlite": STRONG,
            "database": STRONG,
            "dataset": STRONG,
            "notebook": STRONG,
            "jupyter": STRONG,
            "pytorch": STRONG,
            "training": STRONG,
            "aggregate": STRONG,
            "chart": STRONG,
            "pandas": STRONG,
            "query": STRONG,
            "sql": STRONG,
            "csv": STRONG,
            "etl": STRONG,
            "plot": STRONG,
        },
    ),
    Vibe(
        name="design",
        blurb="interface and visual work",
        queries=("upbeat indie", "feel good indie", "indie focus", "creative flow"),
        keywords={
            "landing page": STRONG,
            "dark mode": STRONG,
            "design system": STRONG,
            "color palette": STRONG,
            "visual design": STRONG,
            "typography": STRONG,
            "responsive": STRONG,
            "animations": STRONG,
            "animation": STRONG,
            "tailwind": STRONG,
            "gradient": STRONG,
            "wireframe": STRONG,
            "mockup": STRONG,
            "branding": STRONG,
            "homepage": STRONG,
            "dashboard": STRONG,
            "landing": STRONG,
            "spacing": STRONG,
            "styling": STRONG,
            "styles": STRONG,
            "palette": STRONG,
            "colors": STRONG,
            "colours": STRONG,
            "color": STRONG,
            "layout": STRONG,
            "figma": STRONG,
            "brand": STRONG,
            "theme": STRONG,
            "visual": STRONG,
            "button": STRONG,
            "modal": STRONG,
            "footer": STRONG,
            "header": STRONG,
            "navbar": STRONG,
            "css": STRONG,
            "sass": STRONG,
            "ui": STRONG,
            "ux": STRONG,
            "animating": SOFT,
        },
    ),
    Vibe(
        name="docs",
        blurb="writing prose and docs",
        queries=("calm classical", "classical study", "acoustic concentration", "ambient piano"),
        keywords={
            "api reference": STRONG,
            "documentation": STRONG,
            "docstring": STRONG,
            "changelog": STRONG,
            "readme": STRONG,
            "read me": STRONG,
            "proofread": STRONG,
            "copyedit": STRONG,
            "tutorial": STRONG,
            "grammar": STRONG,
            "prose": STRONG,
            "docs": STRONG,
            "article": STRONG,
            "blog": STRONG,
            "outline": SOFT,
            "translate": SOFT,
            "rewrite": SOFT,
            "draft": SOFT,
        },
    ),
    Vibe(
        name="review",
        blurb="reading and auditing code",
        queries=("soft ambient", "ambient study", "piano focus", "calm focus"),
        keywords={
            "code review": STRONG,
            "read through": STRONG,
            "check over": STRONG,
            "walkthrough": STRONG,
            "security audit": STRONG,
            "review": STRONG,
            "audit": STRONG,
            "diff": STRONG,
            "triage": STRONG,
            "analysis": SOFT,
            "analyze": SOFT,
            "analyse": SOFT,
            "inspect": SOFT,
            "security": SOFT,
            "explore": SOFT,
            "understand the": SOFT,
            "pr": SOFT,
        },
    ),
    Vibe(
        name="focus",
        blurb="deep work, no words",
        queries=("deep focus", "instrumental study", "focus flow", "lofi beats to code to"),
        keywords={
            "from scratch": STRONG,
            "deep dive": STRONG,
            "state machine": STRONG,
            "build out": STRONG,
            "algorithm": STRONG,
            "compiler": STRONG,
            "parser": STRONG,
            "concurrency": STRONG,
            "concurrent": STRONG,
            "endpoint": STRONG,
            "schema": STRONG,
            "refactor": SOFT,
            "implementation": SOFT,
            "implementing": SOFT,
            "implement": SOFT,
            "migrate": SOFT,
            "migration": SOFT,
            "benchmark": SOFT,
            "performance": SOFT,
            "optimize": SOFT,
            "optimise": SOFT,
            "scaffold": SOFT,
            "backend": SOFT,
            "frontend": SOFT,
            "feature": SOFT,
            "develop": SOFT,
            "developing": SOFT,
            "building": SOFT,
            "module": SOFT,
            "index": SOFT,
            "cache": SOFT,
            "thread": SOFT,
            "async": SOFT,
            "mutex": SOFT,
            "build": SOFT,
            "write": SOFT,
            "code": SOFT,
            "coding": SOFT,
        },
    ),
)

BY_NAME: dict[str, Vibe] = {v.name: v for v in VIBES}

_PATTERNS: dict[str, re.Pattern[str]] = {}
WORD_RE = re.compile(r"[a-z0-9]+")
QUOTE_WRAP = "\"'“”‘’`"
SUFFIX = r"(?:s|es|ing|ed)?"


def _pattern(keyword: str) -> re.Pattern[str]:
    pat = _PATTERNS.get(keyword)
    if pat is None:
        # Standalone word (so "css" never matches "scss") plus the usual tail,
        # so "bug" also catches "bugs" and "fix" also catches "fixed".
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(keyword) + SUFFIX + r"(?![a-z0-9])")
        _PATTERNS[keyword] = pat
    return pat


def normalize(prompt: str) -> str:
    text = prompt.strip().strip(QUOTE_WRAP)
    return re.sub(r"\s+", " ", text.lower()).strip()


def word_count(prompt: str) -> int:
    return len(WORD_RE.findall(prompt))


def classify(
    prompt: str,
    *,
    min_score: float = 1.0,
    extra_keywords: dict[str, str] | None = None,
    fallback: str = "none",
) -> Match:
    """Score every vibe against `prompt` and return the best one.

    `extra_keywords` maps a keyword to a vibe name (user config overrides).
    `fallback` is the vibe name to use when nothing scores, or "none" to
    leave music untouched.
    """
    text = normalize(prompt)
    if not text:
        return Match(vibe=None, score=0.0, reason="empty prompt")

    scores: dict[str, float] = {v.name: 0.0 for v in VIBES}
    hits: dict[str, list[tuple[str, float]]] = {v.name: [] for v in VIBES}

    for vibe in VIBES:
        for keyword, weight in vibe.keywords.items():
            if _pattern(keyword).search(text):
                scores[vibe.name] += weight
                hits[vibe.name].append((keyword, weight))

    for keyword, target in (extra_keywords or {}).items():
        if target in scores and _pattern(str(keyword).lower()).search(text):
            scores[target] += SOFT
            hits[target].append((str(keyword), SOFT))

    best: Vibe | None = None
    best_score = 0.0
    for vibe in VIBES:
        if scores[vibe.name] > best_score:
            best, best_score = vibe, scores[vibe.name]

    if best is None or best_score < min_score:
        if fallback in BY_NAME and word_count(text) >= 3:
            return Match(
                vibe=BY_NAME[fallback],
                score=best_score,
                matches=hits[fallback],
                reason="fallback",
            )
        return Match(vibe=None, score=best_score, reason="no signal")

    return Match(vibe=best, score=best_score, matches=hits[best.name], reason="scored")
