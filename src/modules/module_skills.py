"""
Module: Skills
Auto-discovers and manages skill plugins from src/skills/.

Each skill is a Python file (skill_*.py) with:
  - SKILL dict: {"name": str, "prompt": str}
  - execute(parameters: dict, context: dict) -> str | None

Usage:
    from modules.module_skills import SkillManager
    skills = SkillManager()
    skills.discover()
    # Get prompt text for LLM:
    prompt_text = skills.get_prompt_text()
    # Dispatch a function call:
    result = skills.execute("web_search", {"query": "weather"}, context)
"""

import os
import sys
import importlib
import glob
from modules.module_messageQue import queue_message


class SkillManager:
    """Discovers, loads, and dispatches skill plugins."""

    def __init__(self):
        self._skills = {}       # name -> module
        self._skill_meta = {}   # name -> SKILL dict

    def discover(self, skills_dir=None):
        """Scan skills directory and load all skill_*.py files."""
        if skills_dir is None:
            skills_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")

        if not os.path.isdir(skills_dir):
            queue_message(f"SKILLS: Directory not found: {skills_dir}")
            return

        # Ensure skills dir is importable
        parent_dir = os.path.dirname(skills_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        pattern = os.path.join(skills_dir, "skill_*.py")
        skill_files = sorted(glob.glob(pattern))

        for filepath in skill_files:
            filename = os.path.basename(filepath)
            module_name = filename[:-3]  # strip .py

            try:
                mod = importlib.import_module(f"skills.{module_name}")

                if not hasattr(mod, 'SKILL') or not hasattr(mod, 'execute'):
                    queue_message(f"SKILLS: Skipping {filename} — missing SKILL dict or execute()")
                    continue

                skill_def = mod.SKILL
                name = skill_def.get("name", "")
                if not name:
                    queue_message(f"SKILLS: Skipping {filename} — no name in SKILL dict")
                    continue

                if name in self._skills:
                    queue_message(f"SKILLS: WARNING — duplicate skill name '{name}' in {filename}, overwriting previous")
                self._skills[name] = mod
                self._skill_meta[name] = skill_def
            except Exception as e:
                queue_message(f"SKILLS: Failed to load {filename}: {e}")

        queue_message(f"SKILLS: Loaded {len(self._skills)} skills: {', '.join(sorted(self._skills.keys()))}")

    def has_skill(self, name):
        """Check if a skill is loaded."""
        return name in self._skills

    def execute(self, name, parameters, context):
        """Execute a skill by name. Returns reply text or None.

        Args:
            name: Skill function name (e.g. "web_search")
            parameters: Dict of parameters from the LLM function call
            context: Dict with execution context:
                - bot_response: The full parsed LLM response dict
                - user_input: The original user text
                - source: "voice" or "webui"
                - has_image: True if user provided an image
                - config: The loaded config dict

        Returns:
            str: New reply text to replace bot_response["reply"], or
            None: Don't modify the reply
        """
        mod = self._skills.get(name)
        if mod is None:
            queue_message(f"SKILLS: Unknown skill: {name}")
            return None

        try:
            result = mod.execute(parameters, context)
            return result
        except Exception as e:
            queue_message(f"SKILLS: Execution failed for {name}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_prompt_text(self):
        """Generate the function calling prompt text from all loaded skills.

        Returns the numbered list of tool descriptions that gets injected
        into the system prompt for the LLM.
        """
        lines = []
        for name in sorted(self._skill_meta.keys(), key=lambda n: self._get_sort_key(n)):
            meta = self._skill_meta[name]
            prompt = meta.get("prompt", "")
            if prompt:
                lines.append(prompt)
                lines.append("")  # blank line between skills
        return "\n".join(lines)

    def get_examples_text(self):
        """Generate the examples prompt text from all loaded skills.

        Returns combined examples from skills that have an 'examples' list
        in their SKILL dict. These get injected into the system prompt.
        """
        examples = []
        for name in sorted(self._skill_meta.keys(), key=lambda n: self._get_sort_key(n)):
            meta = self._skill_meta[name]
            skill_examples = meta.get("examples", [])
            for ex in skill_examples:
                if ex:
                    examples.append(ex)
        return "\n\n".join(examples)

    def get_skill_names(self):
        """Return list of loaded skill names."""
        return list(self._skills.keys())

    def get_skill_count(self):
        """Return number of loaded skills."""
        return len(self._skills)

    def _get_sort_key(self, name):
        """Return sort key for a skill. Uses 'order' from SKILL dict if set, else alphabetical by name."""
        meta = self._skill_meta.get(name, {})
        return (meta.get("order", 999), name)


# Module-level singleton
_manager = None


def get_skill_manager():
    """Get the global SkillManager instance."""
    return _manager


def initialize_skills(skills_dir=None):
    """Initialize and discover skills. Called from app.py at startup."""
    global _manager
    _manager = SkillManager()
    _manager.discover(skills_dir)
    return _manager
