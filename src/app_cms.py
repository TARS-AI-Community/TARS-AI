#!/usr/bin/env python3
"""
TARS Configuration Manager / 2025-08-07
# atomikspace (discord)
# olivierdion1@hotmail.com
"""

import configparser
import os
import sys
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import time

class ActionType(Enum):
    ADD_SECTION = "ADD_SECTION"
    ADD_FIELD = "ADD_FIELD"
    REMOVE_SECTION = "REMOVE_SECTION"
    REMOVE_FIELD = "REMOVE_FIELD"
    PRESERVE_VALUE = "PRESERVE_VALUE"
    ADD_COMMENT = "ADD_COMMENT"
    PRESERVE_COMMENT = "PRESERVE_COMMENT"

@dataclass
class ConfigAction:
    action: ActionType
    section: str
    field: str = None
    value: str = None
    comment: str = None
    old_value: str = None

@dataclass
class ConfigField:
    name: str
    value: str
    inline_comment: str = ""
    description_comments: List[str] = None
    
    def __post_init__(self):
        if self.description_comments is None:
            self.description_comments = []

@dataclass  
class ConfigSection:
    name: str
    inline_comment: str = ""
    description_comments: List[str] = None
    fields: Dict[str, ConfigField] = None
    
    def __post_init__(self):
        if self.description_comments is None:
            self.description_comments = []
        if self.fields is None:
            self.fields = {}

class TarsConfigManager:
    def __init__(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_file = os.path.join(script_dir, "config.ini.template")
        self.config_file = os.path.join(script_dir, "config.ini")
        self.backup_file = os.path.join(script_dir, "config_backup.ini")
        self.actions: List[ConfigAction] = []
        
    def display_tars_header(self):
        tars_cms_art = """
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║    ████████  █████  ██████  ███████      ██████ ███    ███ ███████    ║
║       ██    ██   ██ ██   ██ ██          ██      ████  ████ ██         ║
║       ██    ███████ ██████  ███████     ██      ██ ████ ██ ███████    ║
║       ██    ██   ██ ██   ██      ██     ██      ██  ██  ██      ██    ║
║       ██    ██   ██ ██   ██ ███████      ██████ ██      ██ ███████    ║
║                                                                       ║
║                   Configuration Management System                     ║
║                                                                       ║
║      "Cooper, this is no time for caution... but for configs!"        ║
║                                                                       ║
╚══════════════════════════════════════════════════════════════⠞⠁⠗⠎═════╝
        """
        print(tars_cms_art)
        print("🤖 TARS: Initiating configuration synchronization protocol...")
        time.sleep(0.5)

    def display_loading(self, message: str):
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        for i in range(20):
            print(f"\r🤖 TARS: {message} {chars[i % len(chars)]}", end="", flush=True)
            time.sleep(0.1)
        print(f"\r🤖 TARS: {message} ✓")

    def parse_config_structure(self, filename: str) -> Dict[str, ConfigSection]:
        """Parse config file manually to preserve ALL comments and structure"""
        sections = {}
        
        if not os.path.exists(filename):
            return sections
        
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                lines = file.readlines()
        except Exception as e:
            print(f"🤖 TARS: Error reading file {filename}: {e}")
            return sections
        
        current_section = None
        pending_comments = []
        
        try:
            for line_num, line in enumerate(lines, 1):
                original_line = line.rstrip('\n\r')
                stripped_line = line.strip()
                
                if stripped_line.startswith('#'):
                    pending_comments.append(stripped_line[1:].strip())
                    
                elif stripped_line.startswith('[') and ']' in stripped_line:
                    bracket_end = stripped_line.find(']')
                    section_name = stripped_line[1:bracket_end]
                    remaining = stripped_line[bracket_end + 1:].strip()
                    inline_comment = ""
                    if remaining.startswith('#'):
                        inline_comment = remaining[1:].strip()
                    
                    current_section = ConfigSection(
                        name=section_name,
                        inline_comment=inline_comment,
                        description_comments=pending_comments.copy() if pending_comments else []
                    )
                    sections[section_name] = current_section
                    pending_comments = []
                    
                elif '=' in stripped_line and not stripped_line.startswith('#'):
                    if current_section is None:
                        continue
                        
                    parts = stripped_line.split('=', 1)
                    field_name = parts[0].strip()
                    value_part = parts[1].strip() if len(parts) > 1 else ""
                    
                    inline_comment = ""
                    if '#' in value_part:
                        value_comment_split = value_part.split('#', 1)
                        value_part = value_comment_split[0].strip()
                        inline_comment = value_comment_split[1].strip()
                    
                    field = ConfigField(
                        name=field_name,
                        value=value_part,
                        inline_comment=inline_comment,
                        description_comments=pending_comments.copy() if pending_comments else []
                    )
                    
                    current_section.fields[field_name] = field
                    pending_comments = []
                
                elif stripped_line == "":
                    pending_comments = []
        
        except Exception as e:
            print(f"🤖 TARS: Error parsing line {line_num} in {filename}: {e}")
            print(f"🤖 TARS: Line content: '{original_line}'")
            raise

        return sections

    def analyze_differences(self) -> List[ConfigAction]:
        self.display_loading("Analyzing configuration differences")
        
        template_sections = self.parse_config_structure(self.template_file)
        existing_sections = self.parse_config_structure(self.config_file)
        
        actions = []
        
        for section_name, template_section in template_sections.items():
            if section_name not in existing_sections:
                actions.append(ConfigAction(
                    ActionType.ADD_SECTION, 
                    section_name, 
                    comment=template_section.inline_comment
                ))
                
                if template_section.description_comments:
                    actions.append(ConfigAction(
                        ActionType.ADD_COMMENT,
                        section_name,
                        field="__section_desc__",
                        value='\n'.join(template_section.description_comments)
                    ))
                
                for field_name, template_field in template_section.fields.items():
                    actions.append(ConfigAction(
                        ActionType.ADD_FIELD,
                        section_name,
                        field_name,
                        template_field.value,
                        template_field.inline_comment
                    ))
                    
                    if template_field.description_comments:
                        actions.append(ConfigAction(
                            ActionType.ADD_COMMENT,
                            section_name,
                            field=f"__{field_name}_desc__",
                            value='\n'.join(template_field.description_comments)
                        ))
            else:
                existing_section = existing_sections[section_name]
                
                template_desc = '\n'.join(template_section.description_comments) if template_section.description_comments else ""
                existing_desc = '\n'.join(existing_section.description_comments) if existing_section.description_comments else ""
                if template_desc != existing_desc and template_desc:
                    actions.append(ConfigAction(
                        ActionType.ADD_COMMENT,
                        section_name,
                        field="__section_desc__",
                        value=template_desc
                    ))
                
                if template_section.inline_comment != existing_section.inline_comment and template_section.inline_comment:
                    actions.append(ConfigAction(
                        ActionType.ADD_COMMENT,
                        section_name,
                        field="__section__",
                        value=template_section.inline_comment
                    ))
                
                for field_name, template_field in template_section.fields.items():
                    if field_name not in existing_section.fields:
                        actions.append(ConfigAction(
                            ActionType.ADD_FIELD,
                            section_name,
                            field_name,
                            template_field.value,
                            template_field.inline_comment
                        ))
                        
                        if template_field.description_comments:
                            actions.append(ConfigAction(
                                ActionType.ADD_COMMENT,
                                section_name,
                                field=f"__{field_name}_desc__",
                                value='\n'.join(template_field.description_comments)
                            ))
                    else:
                        existing_field = existing_section.fields[field_name]
                        field_has_changes = False
                        
                        template_field_desc = '\n'.join(template_field.description_comments) if template_field.description_comments else ""
                        existing_field_desc = '\n'.join(existing_field.description_comments) if existing_field.description_comments else ""
                        if template_field_desc != existing_field_desc and template_field_desc:
                            actions.append(ConfigAction(
                                ActionType.ADD_COMMENT,
                                section_name,
                                field=f"__{field_name}_desc__",
                                value=template_field_desc
                            ))
                            field_has_changes = True
                        
                        if template_field.inline_comment != existing_field.inline_comment and template_field.inline_comment:
                            actions.append(ConfigAction(
                                ActionType.ADD_COMMENT,
                                section_name,
                                field=field_name,
                                value=template_field.inline_comment
                            ))
                            field_has_changes = True
               
                        if field_has_changes:
                            actions.append(ConfigAction(
                                ActionType.PRESERVE_VALUE,
                                section_name,
                                field_name,
                                existing_field.value,
                                old_value=existing_field.value
                            ))

        for section_name, existing_section in existing_sections.items():
            if section_name not in template_sections:
                actions.append(ConfigAction(
                    ActionType.REMOVE_SECTION,
                    section_name
                ))
            else:
                for field_name in existing_section.fields:
                    if field_name not in template_sections[section_name].fields:
                        actions.append(ConfigAction(
                            ActionType.REMOVE_FIELD,
                            section_name,
                            field_name,
                            existing_section.fields[field_name].value
                        ))
        
        return actions
        
    def create_backup(self):
        """Create a backup of the existing config.ini file"""
        if os.path.exists(self.config_file):
            try:
                import shutil
                shutil.copy2(self.config_file, self.backup_file)
                print(f"🤖 TARS: Configuration backup created at config_backup.ini")
                print(f"🤖 TARS: Your original configuration is safe in the tesseract, Cooper.")
                return True
            except Exception as e:
                print(f"🤖 TARS: Warning - Could not create backup: {e}")
                print("🤖 TARS: Proceeding without backup. Humor setting: 25%")
                return False
        return True

    def confirm_removals(self, actions: List[ConfigAction]) -> List[ConfigAction]:
        """Ask user for confirmation before removing sections/fields"""
        if actions is None:
            print("🤖 TARS: Debug - Actions is None, returning empty list")
            return []
        
        remove_actions = [a for a in actions if a.action in [ActionType.REMOVE_SECTION, ActionType.REMOVE_FIELD]]
        
        if not remove_actions:
            return actions
        
        print(f"\n⚠️  TARS: Cooper, I've detected {len(remove_actions)} items that would be removed:")
        print("=" * 50)
        
        sections_to_remove = [a for a in remove_actions if a.action == ActionType.REMOVE_SECTION]
        fields_to_remove = [a for a in remove_actions if a.action == ActionType.REMOVE_FIELD]
        
        if sections_to_remove:
            print("\n🗑️  SECTIONS TO REMOVE:")
            for action in sections_to_remove:
                print(f"   └─ [{action.section}] (entire section)")
        
        if fields_to_remove:
            print("\n🗑️  FIELDS TO REMOVE:")
            for action in fields_to_remove:
                print(f"   └─ [{action.section}] {action.field} = {action.value}")
        
        print(f"\n🤖 TARS: These items exist in your config but not in the template.")
        print("🤖 TARS: They might be obsolete... or they might be important.")
        
        while True:
            print(f"\nOptions:")
            print("  [y] Yes, remove all obsolete items")
            print("  [n] No, keep everything (skip removals)")
            print("  [i] Interactive - ask me about each item")
            
            choice = input("🤖 TARS: What's your preference, Cooper? [y/n/i]: ").strip().lower()
            
            if choice == 'y':
                print("🤖 TARS: Roger that. Preparing for removal sequence.")
                return actions
            
            elif choice == 'n':
                print("🤖 TARS: Understood. Keeping all existing items.")
                return [a for a in actions if a.action not in [ActionType.REMOVE_SECTION, ActionType.REMOVE_FIELD]]
            
            elif choice == 'i':
                print("🤖 TARS: Initiating interactive removal protocol...")
                return self.interactive_removal_selection(actions, remove_actions)
            
            else:
                print("🤖 TARS: Invalid input detected. Please choose y, n, or i.")

    def interactive_removal_selection(self, all_actions: List[ConfigAction], remove_actions: List[ConfigAction]) -> List[ConfigAction]:
        """Let user decide on each removal individually"""
        actions_to_keep = [a for a in all_actions if a not in remove_actions]
        
        print(f"\n🤖 TARS: Entering interactive mode. Processing {len(remove_actions)} items...")
        
        for i, action in enumerate(remove_actions, 1):
            print(f"\n── Item {i}/{len(remove_actions)} ──")
            
            if action.action == ActionType.REMOVE_SECTION:
                print(f"📁 Section: [{action.section}]")
                print(f"🤖 TARS: This entire section would be removed.")
            else:
                print(f"📄 Field: [{action.section}] {action.field} = {action.value}")
                print(f"🤖 TARS: This field would be removed from section [{action.section}].")
            
            while True:
                keep_choice = input(f"   Keep this item? [y/n]: ").strip().lower()
                if keep_choice in ['y', 'yes']:
                    print(f"   ✓ Keeping item")
                    break
                elif keep_choice in ['n', 'no']:
                    print(f"   ✗ Will remove item")
                    actions_to_keep.append(action)
                    break
                else:
                    print("   Please enter 'y' or 'n'")
        
        print(f"\n🤖 TARS: Interactive selection complete!")
        return actions_to_keep

    def display_action_summary(self, actions: List[ConfigAction]):
        print("\n" + "="*70)
        print("🤖 TARS: Configuration Analysis Complete")
        print("="*70)
        
        if not actions:
            print("\n✨ Cooper, the configuration is already synchronized!")
            print("🤖 TARS: No actions required. Humor setting: 75%")
            return False
        
        add_sections = [a for a in actions if a.action == ActionType.ADD_SECTION]
        add_fields = [a for a in actions if a.action == ActionType.ADD_FIELD]
        add_comments = [a for a in actions if a.action == ActionType.ADD_COMMENT]
        remove_sections = [a for a in actions if a.action == ActionType.REMOVE_SECTION]
        remove_fields = [a for a in actions if a.action == ActionType.REMOVE_FIELD]
        preserve_fields = [a for a in actions if a.action == ActionType.PRESERVE_VALUE]
        preserve_comments = [a for a in actions if a.action == ActionType.PRESERVE_COMMENT]
        
        print(f"\n📊 MISSION SUMMARY:")
        print(f"   🆕 Sections to add: {len(add_sections)}")
        print(f"   ➕ Fields to add: {len(add_fields)}")
        print(f"   💬 Comments to add: {len(add_comments)}")
        print(f"   🗑️  Sections to remove: {len(remove_sections)}")
        print(f"   ➖ Fields to remove: {len(remove_fields)}")
        print(f"   🔒 Values to preserve: {len(preserve_fields)}")
        print(f"   📝 Comments to preserve: {len(preserve_comments)}")
        
        if add_sections:
            print(f"\n🆕 NEW SECTIONS:")
            for action in add_sections:
                comment_info = f" # {action.comment}" if action.comment else ""
                print(f"   └─ [{action.section}]{comment_info}")
        
        if add_fields:
            print(f"\n➕ NEW FIELDS:")
            for action in add_fields:
                comment_info = f" # {action.comment}" if action.comment else ""
                print(f"   └─ [{action.section}] {action.field} = {action.value}{comment_info}")
        
        if add_comments:
            print(f"\n💬 NEW COMMENTS:")
            for action in add_comments:
                comment_type = "section" if action.field == "__section_desc__" else "field"
                field_name = action.field.replace("__", "").replace("_desc", "") if action.field != "__section_desc__" else ""
                target = f"[{action.section}]" if comment_type == "section" else f"[{action.section}] {field_name}"
                print(f"   └─ {target}: {action.value[:50]}...")
        
        if remove_sections:
            print(f"\n🗑️  SECTIONS TO REMOVE:")
            for action in remove_sections:
                print(f"   └─ [{action.section}]")
        
        if remove_fields:
            print(f"\n➖ FIELDS TO REMOVE:")
            for action in remove_fields:
                print(f"   └─ [{action.section}] {action.field} = {action.value}")
        
        if preserve_fields:
            print(f"\n🔒 VALUES TO PRESERVE:")
            for action in preserve_fields[:5]:
                print(f"   └─ [{action.section}] {action.field} = {action.value}")
            if len(preserve_fields) > 5:
                print(f"   └─ ... and {len(preserve_fields) - 5} more")
        
        if preserve_comments:
            print(f"\n📝 COMMENTS TO PRESERVE:")
            for action in preserve_comments[:5]:
                comment_type = "section" if action.field == "__section_desc__" else "field"
                field_name = action.field.replace("__", "").replace("_desc", "") if action.field != "__section_desc__" else ""
                target = f"[{action.section}]" if comment_type == "section" else f"[{action.section}] {field_name}"
                print(f"   └─ {target}: {action.value[:50]}...")
            if len(preserve_comments) > 5:
                print(f"   └─ ... and {len(preserve_comments) - 5} more")
        
        return True

    def apply_changes(self, actions: List[ConfigAction]):
        print(f"\n🚀 TARS: Initiating configuration update sequence...")
        
        backup_created = self.create_backup()
        if not backup_created:
            proceed = input("🤖 TARS: Continue without backup? [y/N]: ").strip().lower()
            if proceed not in ['y', 'yes']:
                print("🤖 TARS: Mission aborted for safety reasons.")
                return
            
        template_sections = self.parse_config_structure(self.template_file)
        existing_sections = self.parse_config_structure(self.config_file)
        
        final_sections = {}

        for section_name, template_section in template_sections.items():
            final_section = ConfigSection(
                name=section_name,
                inline_comment=template_section.inline_comment,
                description_comments=template_section.description_comments.copy() if template_section.description_comments else []
            )
            
            for field_name, template_field in template_section.fields.items():
                if section_name in existing_sections and field_name in existing_sections[section_name].fields:
                    existing_field = existing_sections[section_name].fields[field_name]
                    final_field = ConfigField(
                        name=field_name,
                        value=existing_field.value,
                        inline_comment=template_field.inline_comment,
                        description_comments=template_field.description_comments.copy() if template_field.description_comments else []  # Always use template description
                    )
                else:
                    final_field = ConfigField(
                        name=field_name,
                        value=template_field.value,
                        inline_comment=template_field.inline_comment,
                        description_comments=template_field.description_comments.copy() if template_field.description_comments else []
                    )
                
                final_section.fields[field_name] = final_field
            
            final_sections[section_name] = final_section
        
        self.write_config_file(final_sections)
        
        print(f"\n✅ TARS: Configuration synchronization complete!")
        print(f"🤖 TARS: The cosmic dance of data alignment is finished, Cooper.")

    def write_config_file(self, sections: Dict[str, ConfigSection]):
        """Write config file with complete comment preservation"""
        with open(self.config_file, 'w', encoding='utf-8') as file:
            for section_name, section in sections.items():
                if section.description_comments:
                    for comment in section.description_comments:
                        file.write(f"# {comment}\n")
                
                if section.inline_comment:
                    file.write(f"[{section_name}] # {section.inline_comment}\n")
                else:
                    file.write(f"[{section_name}]\n")
                
                for field_name, field in section.fields.items():
                    if field.description_comments:
                        for comment in field.description_comments:
                            file.write(f"# {comment}\n")
                    
                    if field.inline_comment:
                        file.write(f"{field.name} = {field.value} # {field.inline_comment}\n")
                    else:
                        file.write(f"{field.name} = {field.value}\n")
                
                file.write("\n")

    def run(self):
        try:
            self.display_tars_header()
            
            if not os.path.exists(self.template_file):
                print(f"🤖 TARS: Houston, we have a problem. Template file '{self.template_file}' not found.")
                print("🤖 TARS: Humor setting reduced to 0%. This is serious, Cooper.")
                sys.exit(1)
            
            print("🤖 TARS: Debug - About to analyze differences...")
            actions = self.analyze_differences()
            print(f"🤖 TARS: Debug - Got {len(actions) if actions else 0} actions")
            
            print("🤖 TARS: Debug - About to confirm removals...")
            actions = self.confirm_removals(actions)
            print(f"🤖 TARS: Debug - After removal confirmation: {len(actions) if actions else 0} actions")
            
            print("🤖 TARS: Debug - About to display summary...")
            has_changes = self.display_action_summary(actions)
            
            if not has_changes:
                return
            
            print(f"\n{'─'*70}")
            print("🤖 TARS: Cooper, shall I proceed with the synchronization?")
            response = input("   Continue? [Y/n]: ").strip().lower()
            
            if response in ['', 'y', 'yes']:
                self.apply_changes(actions)
            else:
                print("🤖 TARS: Mission aborted. Configuration remains unchanged.")
                print("🤖 TARS: Sometimes discretion is the better part of valor.")
                
        except Exception as e:
            print(f"\n🤖 TARS: Debug - Error occurred at: {e}")
            import traceback
            traceback.print_exc()
            raise

    def update_config_programmatically(self, config_data: Dict, create_backup: bool = True) -> Tuple[bool, str, List[str]]:
        """
        Update configuration programmatically without user interaction
        
        Args:
            config_data: Dictionary of configuration sections and fields
            create_backup: Whether to create a backup before updating
            
        Returns:
            Tuple of (success, message, actions_taken)
        """
        try:
            # Create backup if requested
            if create_backup:
                if not self.create_backup():
                    return False, "Failed to create backup", []
            
            # Load configurations
            template_sections = self.parse_config_structure(self.template_file)
            existing_sections = self.parse_config_structure(self.config_file)
            
            # Create updated configuration structure
            final_sections = {}
            actions_taken = []
            
            for section_name, template_section in template_sections.items():
                final_section = ConfigSection(
                    name=section_name,
                    inline_comment=template_section.inline_comment,
                    description_comments=template_section.description_comments.copy() if template_section.description_comments else []
                )
                
                for field_name, template_field in template_section.fields.items():
                    # Determine value to use
                    if section_name in config_data and field_name in config_data[section_name]:
                        new_value = str(config_data[section_name][field_name])
                        actions_taken.append(f"Updated [{section_name}] {field_name}")
                    elif section_name in existing_sections and field_name in existing_sections[section_name].fields:
                        existing_value = existing_sections[section_name].fields[field_name].value
                        new_value = existing_value
                        actions_taken.append(f"Preserved [{section_name}] {field_name}")
                    else:
                        new_value = template_field.value
                        actions_taken.append(f"Used template [{section_name}] {field_name}")
                    
                    final_field = ConfigField(
                        name=field_name,
                        value=new_value,
                        inline_comment=template_field.inline_comment,
                        description_comments=template_field.description_comments.copy() if template_field.description_comments else []
                    )
                    
                    final_section.fields[field_name] = final_field
                
                final_sections[section_name] = final_section
            
            # Write configuration
            self.write_config_file(final_sections)
            
            return True, f"Configuration updated successfully ({len(actions_taken)} changes)", actions_taken
            
        except Exception as e:
            return False, f"Configuration update failed: {str(e)}", []
    
    def validate_config_data(self, config_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate configuration data against template structure
        
        Args:
            config_data: Dictionary of configuration sections and fields
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            template_sections = self.parse_config_structure(self.template_file)
            
            for section_name, section_data in config_data.items():
                if section_name not in template_sections:
                    errors.append(f"Unknown section: [{section_name}]")
                    continue
                    
                template_section = template_sections[section_name]
                
                for field_name, field_value in section_data.items():
                    if field_name not in template_section.fields:
                        errors.append(f"Unknown field: [{section_name}] {field_name}")
                        continue
                        
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            
        return len(errors) == 0, errors
    
    def get_config_sync_status(self) -> Dict:
        """
        Get configuration synchronization status for programmatic access
        
        Returns:
            Dictionary with sync status information
        """
        try:
            actions = self.analyze_differences()
            
            return {
                "is_synchronized": len(actions) == 0,
                "total_actions": len(actions),
                "add_sections": len([a for a in actions if a.action == ActionType.ADD_SECTION]),
                "add_fields": len([a for a in actions if a.action == ActionType.ADD_FIELD]),
                "add_comments": len([a for a in actions if a.action == ActionType.ADD_COMMENT]),
                "remove_sections": len([a for a in actions if a.action == ActionType.REMOVE_SECTION]),
                "remove_fields": len([a for a in actions if a.action == ActionType.REMOVE_FIELD]),
                "preserve_values": len([a for a in actions if a.action == ActionType.PRESERVE_VALUE]),
                "actions": [
                    {
                        "action": action.action.value,
                        "section": action.section,
                        "field": action.field,
                        "value": action.value,
                        "comment": action.comment
                    } for action in actions
                ]
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "is_synchronized": False
            }

    def show_interstellar_goodbye(self):
        goodbye_art = """
        
    ⭐ TARS: "Cooper, the bulk beings are closing the tesseract..." ⭐
    
         🌌 Configuration mission accomplished! 🌌
        """
        print(goodbye_art)

if __name__ == "__main__":
    try:
        manager = TarsConfigManager()
        manager.run()
        manager.show_interstellar_goodbye()
    except KeyboardInterrupt:
        print("\n\n🤖 TARS: Mission interrupted by user.")
        print("🤖 TARS: Remember Cooper, love is the one thing we're capable of perceiving that transcends dimensions of time and space... and config files.")
    except Exception as e:
        print(f"\n🤖 TARS: Critical system error: {e}")
        print("🤖 TARS: Humor setting: 100%. At least we tried, Cooper!")