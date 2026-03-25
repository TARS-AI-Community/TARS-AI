"""
Module: Skill Engine
Routes user messages to relevant skills before prompt construction,
reducing prompt size sent to the main LLM.

Supports two modes:
  - llm:       All enabled skills included in every prompt (legacy behavior)
  - keyword:   Python keyword matching + recently-used tracking (instant, no model)
"""

import re
import collections
import time as _time
from modules.module_messageQue import queue_message

# ── Keyword trigger definitions ──────────────────────────────────────
# Each skill maps to a list of keyword/phrase patterns.
# These are checked against the lowercased user message.
# Skills not listed here will never match via keywords (only via recent-use).

SKILL_TRIGGERS = {
    "adjust_persona": [
        # "set X to N" but NOT "set volume to N" or "set the thermostat"
        r"\bset\s+(?!volume|the\s+thermostat|the\s+volume)\w+\s+to\s+\d+",
        r"\bchange\s+\w+\s+to\b", r"\bupdate\s+\w+\s+to\b",
        r"\bmake\s+(?!a\s+|me\s+|some\s+)\w+\s+\d+",
        r"\bverbosity\b", r"\bsarcasm\b", r"\bhumor\b",
        r"\bhonesty\b", r"\bempathy\b", r"\bcuriosity\b", r"\bconfidence\b",
        r"\bformality\b", r"\badaptability\b", r"\bdiscipline\b", r"\bimagination\b",
        r"\boptimism\b", r"\bcheerfulness\b", r"\bengagement\b", r"\brespectfulness\b",
        r"\bemotional.stability\b", r"\bpragmatism\b", r"\bresourcefulness\b",
        r"\blove\b.*\d+", r"\bdesire\b.*\d+", r"\bromanticism\b", r"\bdevotion\b",
        r"\bsentimentality\b", r"\bintimacy\b",
        r"\badjust\s+(your\s+)?(persona|personality)\b",
    ],
    "browser": [
        r"\bopen\s+(the\s+)?(website|site|page)\b", r"\bgo\s+to\s+\w+\.(com|org|net|io)\b",
        r"\bvisit\s+\w+\b", r"\bplay\s+.+\s+on\s+youtube\b", r"\bwatch\s+.+\s+on\s+youtube\b",
        r"\bopen\s+\w+\.(com|org|net|io)\b", r"\bopen\s+(youtube|reddit|google|twitter|twitch)\b",
        r"\bgo\s+to\s+(youtube|reddit|google|twitter|twitch)\b",
    ],
    "capture_camera_view": [
        r"\bwhat\s+(do\s+you|can\s+you)\s+see\b", r"\blook\s+(at|around)\b",
        r"\bwhat'?s?\s+(visible|in\s+front|around|that)\b", r"\bdescribe\s+(surroundings|view|what)\b",
        r"\bcheck\s+visually\b", r"\bcan\s+you\s+see\b",
        r"\btake\s+a\s+look\b",
    ],
    "execute_movement": [
        r"\bwalk\s+(forward|backward)\b", r"\bturn\s+(left|right)\b",
        r"\bstep\s+(back|forward)\b", r"\bmove\s+(forward|backward|left|right)\b",
        r"\bgo\s+forward\b",
    ],
    "identify_speaker_name": [
        r"\bmy\s+name\s+is\s+\w+",
        r"\bcall\s+me\s+\w+",
    ],
    "reminder": [
        r"\bremind\s+me\b", r"\bset\s+(a\s+)?(reminder|timer|alarm)\b",
        r"\bcancel\b.*\b(reminder|timer|alarm)s?\b", r"\bwhat\s+reminders?\b",
        r"\blist\s+(my\s+)?(reminder|timer)s?\b", r"\bin\s+\d+\s+(minute|hour|second)s?\b",
    ],
    "sandbox_exec": [
        r"\bcalculate\b", r"\bcompute\b", r"\bsolve\b", r"\bmath\b",
        r"\bfactorial\b", r"\bprime\s+number", r"\bsort\s+(these|this|the)\b",
        r"\brun\s+(this\s+)?(code|script|python)\b", r"\bexecute\s+(code|python)\b",
        r"\bwrite\s+(a\s+)?(script|code|program|function)\b",
    ],
    "system_control": [
        r"\bexit\s+(the\s+)?program\b", r"\bquit\s+(the\s+)?program\b",
        r"\bclose\s+(the\s+)?program\b", r"\bstop\s+(the\s+)?program\b",
        r"\bexit\s+tars\b", r"\bquit\s+tars\b",
        r"\bshut\s*down\b", r"\bpower\s+off\b", r"\bturn\s+off\s+the\s+(pi|raspberry)\b",
    ],
    "take_photo": [
        r"\btake\s+(a\s+)?(photo|picture|pic|snapshot)\b", r"\btake\s+my\s+(photo|picture|pic)\b",
        r"\bsnap\s+(a\s+)?(photo|picture|pic)\b",
        r"\bphoto(graph)?\s+(of\s+me|this)\b",
        r"\bcapture\s+(a\s+)?photo\b",
    ],
    "tars_radio": [
        r"\bplay\s+(some\s+)?music\b", r"\bplay\s+(my\s+)?songs?\b",
        r"\bstart\s+(the\s+)?radio\b", r"\bstop\s+(the\s+)?music\b",
        r"\bstop\s+(the\s+)?radio\b", r"\bturn\s+off\s+(the\s+)?music\b",
        r"\bnext\s+song\b", r"\bskip\s+(this|song|track)\b",
        r"\bpause\s+(the\s+)?music\b", r"\bresume\b", r"\bunpause\b",
        r"\bdownload\s+(this\s+)?song\b", r"\badd\s+(this\s+)?to\s+my\s+library\b",
        r"\bwhat\s+songs?\s+(do\s+)?i\s+have\b", r"\blist\s+(my\s+)?music\b",
        r"\bwhat'?s?\s+playing\b", r"\bwhat\s+song\s+is\s+this\b",
        r"\brename\s+(that\s+)?song\b", r"\bdelete\s+(that\s+)?song\b",
        # "play [song name]" — but NOT "play on youtube", "play retro games", "play NES"
        r"\bplay\s+(?!.*\bon\s+youtube\b)(?!retro\b|nes\b|snes\b|genesis\b|n64\b)\w+\b",
    ],
    "volume": [
        r"\b(raise|lower|increase|decrease)\s+(the\s+)?volume\b",
        r"\bset\s+(the\s+)?volume\s+to\b", r"\bvolume\s+(up|down)\b",
        r"\bmute\b", r"\bunmute\b",
        r"\bwhat'?s?\s+(the\s+)?volume\b", r"\bcheck\s+(the\s+)?volume\b",
        r"\bturn\s+(it\s+)?(up|down)\b", r"\b(louder|quieter)\b",
    ],
    "web_search": [
        r"\bweather\b", r"\bforecast\b",
        r"\bnews\b", r"\bheadlines\b",
        r"\bsearch\s+for\b", r"\blook\s+up\b",
        # "google X" but NOT "open google.com" / "go to google"
        r"\bgoogle\s+(?!\.com\b)(?!chrome\b)\w+",
        r"\bfind\s+me\b", r"\bcan\s+you\s+search\b",
    ],
    "generate_image": [
        r"\bgenerate\s+(a\s+)?(photo|image|picture|artwork|portrait)\b",
        r"\bdraw\s+(me\s+)?(a\s+)?\w+", r"\bcreate\s+(an?\s+)?(image|picture|artwork)\b",
        r"\bmake\s+(a\s+)?(photo|picture|image)\s+of\b", r"\bpaint\s+(me\s+)?\w+",
    ],
    "generate_music": [
        r"\bmake\s+(me\s+)?a\s+song\b", r"\bgenerate\s+music\b",
        r"\bcompose\s+(a\s+)?track\b", r"\bcreate\s+(a\s+)?beat\b",
        r"\bwrite\s+(a\s+)?song\b", r"\bproduce\s+(a\s+)?track\b",
    ],
    "home_assistant": [
        r"\bturn\s+(on|off)\s+(the\s+)?(lights?|lamp|fan|switch)\b",
        r"\bopen\s+(the\s+)?(garage|door|gate|blind)\b",
        r"\bclose\s+(the\s+)?(garage|door|gate|blind)\b",
        r"\block\s+(the\s+)?(door|front)\b", r"\bunlock\b",
        r"\bset\s+(the\s+)?thermostat\b", r"\btemperature\s+to\s+\d+\b",
        r"\bis\s+the\s+(garage|door|front)\b",
    ],
    "network_camera": [
        r"\bshow\s+(me\s+)?(the\s+)?\w+\s+camera\b", r"\bcheck\s+(the\s+)?(\w+\s+)*cam(era)?\b",
        r"\bpull\s+up\s+(the\s+)?\w+\s+(feed|camera)\b",
        r"\bsecurity\s+camera\b", r"\bsnapshot\b",
    ],
    "launch_retropie": [
        r"\bstart\s+retropie\b", r"\blaunch\s+retropie\b", r"\bopen\s+retropie\b",
        r"\bplay\s+(retro|nes|snes|genesis|n64)\s+game", r"\bemulation\s+station\b",
    ],
    "example": [
        r"\bskill\s+example\b", r"\brun\s+skill\s+example\b",
    ],
}

# Pre-compile all patterns for performance
_COMPILED_TRIGGERS = {
    skill: [re.compile(p, re.IGNORECASE) for p in patterns]
    for skill, patterns in SKILL_TRIGGERS.items()
}

class SkillEngine:
    """Routes user messages to relevant skills via keyword matching."""

    def __init__(self):
        self._engine_type = "llm"
        self._recent_skills = collections.deque(maxlen=5)
        self._skill_descriptions = {}
        self._loaded = False
        self._cached_message = None
        self._cached_result = None

    def initialize(self, engine_type, skill_manager=None):
        """Load the selected engine. Called once at startup."""
        self._engine_type = engine_type.lower().strip()

        if skill_manager:
            self._build_skill_descriptions(skill_manager)

        if self._engine_type == "llm":
            queue_message("INFO: Skill Engine: LLM mode (all skills in prompt)")
            self._loaded = True
            return

        if self._engine_type == "keyword":
            queue_message("INFO: Skill Engine: Keyword mode (instant routing, no model)")
            self._loaded = True
            return

        queue_message(f"WARNING: Unknown skill engine '{self._engine_type}', falling back to LLM mode")
        self._engine_type = "llm"
        self._loaded = True

    def _build_skill_descriptions(self, skill_manager):
        """Build a compact name->description map from the skill manager."""
        self._skill_descriptions = {}
        for name in skill_manager.get_skill_names():
            meta = skill_manager._skill_meta.get(name, {})
            desc = meta.get("description", name)
            self._skill_descriptions[name] = desc

    def update_skill_descriptions(self, skill_manager):
        """Refresh skill descriptions (call after skills are toggled)."""
        self._build_skill_descriptions(skill_manager)

    def is_active(self):
        """Return True if using a routing engine (not LLM passthrough)."""
        return self._loaded and self._engine_type != "llm"

    def record_skill_use(self, skill_name):
        """Track a skill that was just invoked (for context continuity)."""
        if skill_name not in self._recent_skills:
            self._recent_skills.append(skill_name)

    def classify(self, user_message, available_skills=None):
        """Classify which skills are relevant for a user message.

        Returns a set of skill names, or None to use all skills (fallback).
        """
        if not self.is_active():
            return None

        if available_skills is None:
            available_skills = list(self._skill_descriptions.keys())

        # Return cached result if same message
        if self._cached_message == user_message and self._cached_result is not None:
            return self._cached_result

        try:
            t0 = _time.perf_counter()

            if self._engine_type == "keyword":
                matched = self._keyword_classify(user_message, available_skills)
            else:
                return None

            # Always include recently used skills for context continuity
            matched.update(s for s in self._recent_skills if s in available_skills)

            dur = _time.perf_counter() - t0
            queue_message(f"INFO: Skill Engine [{self._engine_type}] classified in {dur*1000:.1f}ms -> {matched or 'chat only'}")

            self._cached_message = user_message
            self._cached_result = matched
            return matched

        except Exception as e:
            queue_message(f"WARNING: Skill Engine classification failed: {e}")
            return None

    def _keyword_classify(self, user_message, available_skills):
        """Fast keyword/regex matching against known trigger patterns.

        Skills WITH keyword entries: only included if a pattern matches.
        Skills WITHOUT keyword entries (community/new): always included
        so they never break — they just don't get the filtering optimization.
        """
        matched = set()
        msg_lower = user_message.lower()

        for skill_name in available_skills:
            if skill_name in _COMPILED_TRIGGERS:
                # Known skill — check patterns
                for pattern in _COMPILED_TRIGGERS[skill_name]:
                    if pattern.search(msg_lower):
                        matched.add(skill_name)
                        break
            else:
                # Community/new skill with no keyword entry — always include
                matched.add(skill_name)

        return matched

    def get_filtered_prompt_text(self, skill_manager, user_message):
        """Get prompt text with only the relevant skills included."""
        matched = self.classify(user_message, skill_manager.get_skill_names())

        if matched is None:
            return skill_manager.get_prompt_text()

        if not matched:
            return "(No function calls needed for this message — respond conversationally)"

        return skill_manager.get_prompt_text_for(matched)

    def get_filtered_examples_text(self, skill_manager, user_message):
        """Get examples text with only the relevant skills included."""
        matched = self.classify(user_message, skill_manager.get_skill_names())

        if matched is None:
            return skill_manager.get_examples_text()

        if not matched:
            return ""

        return skill_manager.get_examples_text_for(matched)

    def get_status(self):
        """Return current engine status for the dashboard API."""
        return {
            "engine_type": self._engine_type,
            "loaded": self._loaded,
            "recent_skills": list(self._recent_skills),
        }


# ── Module-level singleton ────────────────────────────────────────────

_engine = None


def get_skill_engine():
    """Get the global SkillEngine instance."""
    return _engine


def initialize_skill_engine(engine_type, skill_manager=None):
    """Initialize the skill engine. Called from app.py at startup."""
    global _engine
    _engine = SkillEngine()
    _engine.initialize(engine_type, skill_manager)
    return _engine
