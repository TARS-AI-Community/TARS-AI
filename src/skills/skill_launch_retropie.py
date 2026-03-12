"""Skill: launch_retropie — Launch the RetroPie gaming system."""

import os
import threading

SKILL = {
    "name": "launch_retropie",
    "prompt": """launch_retropie
   Triggers: Use when user wants to play retro games or launch RetroPie/EmulationStation
     * "start retropie", "launch retropie", "open retropie"
     * "I want to play a retro game", "play retro games", "play some retro games"
     * "start emulation station", "launch emulation station"
     * "play NES/SNES/Genesis/N64" (any classic console reference with intent to play)
   Parameters: {{}}
   Example: {{"function": "launch_retropie", "parameters": {{}}}}""",
    "examples": [
        """Example - Launch RetroPie:
User: "I want to play a retro game"
Response: {{"question": "I want to play a retro game", "reply": "Firing up RetroPie for you. Have fun!", "function_calls": [{{"function": "launch_retropie", "parameters": {{}}}}], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Launch RetroPie gaming system. Returns reply text."""
    import subprocess
    from modules.module_messageQue import queue_message

    retropie_script = os.path.expanduser("~/TARS-AI/launch_retropie.sh")

    if not os.path.isfile(retropie_script) or not os.access(retropie_script, os.X_OK):
        return "RetroPie doesn't seem to be installed. You can install it by running the installer again."

    def launch_after_tts():
        import time
        time.sleep(5)
        queue_message("Launching RetroPie script...")
        if os.path.isfile("/usr/bin/lxterminal"):
            os.system(f"setsid lxterminal --title='RetroPie' -e {retropie_script} &")
        elif os.path.isfile("/usr/bin/xfce4-terminal"):
            os.system(f"setsid xfce4-terminal --title='RetroPie' -e {retropie_script} &")
        else:
            os.system(f"setsid x-terminal-emulator -e {retropie_script} &")
        try:
            from modules.module_main import shutdown_event, stop_event
            if stop_event:
                stop_event.set()
            if shutdown_event:
                queue_message("Setting shutdown event for clean exit...")
                shutdown_event.set()
        except Exception as e:
            queue_message(f"Could not set shutdown event: {e}")

    threading.Thread(target=launch_after_tts, daemon=False).start()
    return "Launching RetroPie. Have fun gaming!"
