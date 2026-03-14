"""
Module: Skills
Auto-discovers and manages skill plugins from src/skills/.

Each skill is a Python file (skill_*.py) with:
  - SKILL dict: {"name": str, "prompt": str, "config": {...} (optional)}
  - execute(parameters: dict, context: dict) -> str | None

All discovered skills default to enabled. Users toggle them on/off via the web UI.
Per-skill state and config are stored in [SKILL:<name>] sections in config.ini:

  [SKILL:discord]
  disabled = true
  channel_id = 811470553139249186

Skills can define their own config schema via a "config" key in the SKILL dict:
  "config": {
      "url": {"type": "text", "default": "http://...", "description": "Server URL"},
      "token": {"type": "password", "default": "", "description": "API token"},
      "steps": {"type": "number", "default": 20, "min": 1, "max": 100, "description": "..."},
      "service": {"type": "select", "default": "openai", "options": ["openai","local"], "description": "..."},
  }

Skills access their config via context["skill_config"] in execute().

Usage:
    from modules.module_skills import SkillManager
    skills = SkillManager()
    skills.discover()
    prompt_text = skills.get_prompt_text()
    result = skills.execute("web_search", {"query": "weather"}, context)
"""

import os
import sys
import importlib
import glob
import configparser
from modules.module_messageQue import queue_message


def _get_config_path():
    """Return path to src/config.ini."""
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config.ini"
    )


class SkillManager:
    """Discovers, loads, and dispatches skill plugins."""

    def __init__(self):
        self._skills = {}        # name -> module
        self._skill_meta = {}    # name -> SKILL dict
        self._disabled = set()   # skill names disabled via config
        self._skill_config = {}  # name -> {field: value} persisted config values

    # ── Discovery ─────────────────────────────────────────────

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

        # Load persisted config and disabled state from config.ini
        self._load_config()

        enabled = [n for n in sorted(self._skills.keys()) if n not in self._disabled]
        disabled = [n for n in sorted(self._skills.keys()) if n in self._disabled]
        queue_message(f"INFO: Loaded {len(enabled)} skills: {', '.join(enabled)}")
        if disabled:
            queue_message(f"INFO: Disabled {len(disabled)} skills: {', '.join(disabled)}")

    # ── Config persistence (config.ini) ────────────────────────

    def _load_config(self):
        """Load per-skill config and disabled state from [SKILL:*] sections in config.ini.

        Each [SKILL:<name>] section may contain:
          disabled = true   (if the skill is turned off)
          <field> = <value> (skill-specific config values)
        """
        self._skill_config = {}
        self._disabled = set()
        config_path = _get_config_path()

        if not os.path.exists(config_path):
            return

        config = configparser.ConfigParser()
        config.read(config_path)

        # Migrate any leftover [SKILLS] disabled= list from old format
        if config.has_section('SKILLS'):
            old_disabled = config.get('SKILLS', 'disabled', fallback='').strip()
            if old_disabled:
                for name in old_disabled.split(','):
                    name = name.strip()
                    if name:
                        self._disabled.add(name)
            self._remove_section_from_file('SKILLS')

        for section in config.sections():
            if not section.startswith('SKILL:'):
                continue
            skill_name = section[6:]  # strip "SKILL:" prefix
            items = dict(config.items(section))
            # disabled flag lives in the section, not in skill_config values
            if items.pop('disabled', '').strip().lower() == 'true':
                self._disabled.add(skill_name)
            self._skill_config[skill_name] = items

        # One-time migration: copy values from old legacy sections into [SKILL:*]
        self._migrate_legacy_sections(config)

    def _remove_section_from_file(self, section_name):
        """Remove a section and its fields from config.ini using line-level editing."""
        config_path = _get_config_path()
        if not os.path.exists(config_path):
            return
        header = f'[{section_name}]'
        lines = open(config_path, 'r').readlines()
        new_lines = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            if stripped == header:
                in_section = True
                continue
            elif in_section and stripped.startswith('[') and stripped.endswith(']'):
                in_section = False
            if not in_section:
                new_lines.append(line)
        with open(config_path, 'w') as f:
            f.writelines(new_lines)
        queue_message(f"SKILLS: Removed legacy [{section_name}] section from config.ini")

    def _migrate_legacy_sections(self, config):
        """One-time migration: copy old config.ini sections into [SKILL:*] format.

        Maps:
          [DISCORD]       channel_id  -> [SKILL:discord]    channel_id
          [HOME_ASSISTANT] url        -> [SKILL:home_assistant] url
          [STABLE_DIFFUSION] *        -> [SKILL:generate_image] *
        Only migrates a skill if it has no [SKILL:*] section yet.
        Saves immediately so migration only runs once.
        """
        LEGACY_MAP = {
            'discord':          ('DISCORD',          ['channel_id']),
            'home_assistant':   ('HOME_ASSISTANT',   ['url']),  # token stays in .env only
            'generate_image':   ('STABLE_DIFFUSION', [
                'service', 'url', 'prompt_prefix', 'prompt_postfix',
                'negative_prompt', 'seed', 'steps', 'cfg_scale', 'sampler_name',
                'denoising_strength', 'width', 'height', 'restore_faces',
                'comfyui_workflow', 'comfyui_img2img_workflow',
            ]),
        }
        migrated = False
        for skill_name, (old_section, fields) in LEGACY_MAP.items():
            if skill_name in self._skill_config:
                continue  # already has [SKILL:*] data, skip
            if not config.has_section(old_section):
                continue
            values = {}
            for field in fields:
                if config.has_option(old_section, field):
                    values[field] = config.get(old_section, field)
            if values:
                self._skill_config[skill_name] = values
                self._save_skill_section(skill_name)
                queue_message(f"SKILLS: Migrated [{old_section}] -> [SKILL:{skill_name}]")
                migrated = True
        return migrated

    def _save_skill_section(self, name):
        """Write a single [SKILL:<name>] section to config.ini.

        Writes disabled = true if the skill is disabled, plus all config values.
        Omits the disabled key entirely when enabled (enabled is the default).
        Uses line-level editing to preserve comments in the rest of the file.
        """
        config_path = _get_config_path()
        if not os.path.exists(config_path):
            return

        section_header = f'[SKILL:{name}]'
        values = self._skill_config.get(name, {})
        lines = open(config_path, 'r').readlines()

        # Remove existing section
        new_lines = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            if stripped == section_header:
                in_section = True
                continue
            elif in_section and stripped.startswith('[') and stripped.endswith(']'):
                in_section = False
            if not in_section:
                new_lines.append(line)

        # Only write the section if it has something to store
        is_disabled = name in self._disabled
        if not is_disabled and not values:
            with open(config_path, 'w') as f:
                f.writelines(new_lines)
            return

        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines.append('\n')
        new_lines.append(f'{section_header}\n')
        if is_disabled:
            new_lines.append('disabled = true\n')
        for field, value in sorted(values.items()):
            new_lines.append(f'{field} = {value}\n')
        new_lines.append('\n')

        with open(config_path, 'w') as f:
            f.writelines(new_lines)

    def get_skill_config(self, name):
        """Get the resolved config dict for a skill (saved values merged over defaults).

        Returns a flat dict like {"url": "http://...", "token": "abc123", ...}
        """
        meta = self._skill_meta.get(name, {})
        schema = meta.get("config", {})
        saved = self._skill_config.get(name, {})

        resolved = {}
        for field, field_def in schema.items():
            if field in saved:
                resolved[field] = saved[field]
            else:
                resolved[field] = field_def.get("default", "")
        return resolved

    def set_skill_config_bulk(self, name, values):
        """Set multiple config fields for a skill and persist to config.ini."""
        if name not in self._skill_config:
            self._skill_config[name] = {}
        self._skill_config[name].update(values)
        self._save_skill_section(name)

    # ── Enable / disable ──────────────────────────────────────

    def is_enabled(self, name):
        """Check if a skill is enabled (loaded and not disabled)."""
        return name in self._skills and name not in self._disabled

    def set_enabled(self, name, enabled):
        """Enable or disable a skill and persist to config.ini."""
        if enabled:
            self._disabled.discard(name)
        else:
            self._disabled.add(name)
        self._save_skill_section(name)

    def has_skill(self, name):
        """Check if a skill is loaded (regardless of enabled state)."""
        return name in self._skills

    # ── Execution ─────────────────────────────────────────────

    def execute(self, name, parameters, context):
        """Execute a skill by name. Returns reply text or None.

        The skill's resolved config is injected into context["skill_config"].
        """
        if name in self._disabled:
            queue_message(f"SKILLS: Skill '{name}' is disabled")
            return None

        mod = self._skills.get(name)
        if mod is None:
            queue_message(f"SKILLS: Unknown skill: {name}")
            return None

        # Inject skill-specific config into context
        context["skill_config"] = self.get_skill_config(name)

        try:
            result = mod.execute(parameters, context)
            return result
        except Exception as e:
            queue_message(f"SKILLS: Execution failed for {name}: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ── Prompt building ───────────────────────────────────────

    def get_prompt_text(self):
        """Generate the function calling prompt text from all enabled skills."""
        lines = []
        for name in sorted(self._skill_meta.keys(), key=lambda n: self._get_sort_key(n)):
            if name in self._disabled:
                continue
            meta = self._skill_meta[name]
            prompt = meta.get("prompt", "")
            if prompt:
                lines.append(prompt)
                lines.append("")
        return "\n".join(lines)

    def get_examples_text(self):
        """Generate the examples prompt text from all enabled skills."""
        examples = []
        for name in sorted(self._skill_meta.keys(), key=lambda n: self._get_sort_key(n)):
            if name in self._disabled:
                continue
            meta = self._skill_meta[name]
            for ex in meta.get("examples", []):
                if ex:
                    examples.append(ex)
        return "\n\n".join(examples)

    # ── Accessors ─────────────────────────────────────────────

    def get_skill_names(self):
        """Return list of enabled skill names."""
        return [n for n in self._skills.keys() if n not in self._disabled]

    def get_all_skill_names(self):
        """Return list of all skill names (including disabled)."""
        return list(self._skills.keys())

    def get_skill_count(self):
        """Return number of enabled skills."""
        return len([n for n in self._skills if n not in self._disabled])

    def get_skills_info(self):
        """Return full info for all skills (for the web UI API).

        Returns list of dicts with: name, description, enabled, config_schema, config_values
        """
        result = []
        for name in sorted(self._skills.keys()):
            meta = self._skill_meta.get(name, {})
            result.append({
                "name": name,
                "description": meta.get("description", ""),
                "enabled": name not in self._disabled,
                "config_schema": meta.get("config", {}),
                "config_values": self.get_skill_config(name),
            })
        return result

    def reload_config(self):
        """Reload config from disk. Call after external changes."""
        self._load_config()
        enabled = [n for n in sorted(self._skills.keys()) if n not in self._disabled]
        disabled = [n for n in sorted(self._skills.keys()) if n in self._disabled]
        queue_message(f"SKILLS: Reloaded — {len(enabled)} enabled, {len(disabled)} disabled")

    def _get_sort_key(self, name):
        """Return sort key for a skill."""
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
