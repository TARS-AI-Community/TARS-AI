"""Skill: system_control — Exit program or shut down the device."""

import threading

SKILL = {
    "name": "system_control",
    "required_params": ["action"],
    "description": "Shut down, restart, or exit the program",
    "prompt": """system_control
   Triggers: Use ONLY when the user explicitly asks to exit/quit the program OR shut down/power off the device.
     * Exit: "exit the program", "quit the program", "close the program", "stop the program", "exit TARS", "quit TARS"
     * Shutdown: "shut down", "shutdown", "power off", "turn off the pi", "turn off the raspberry pi"
   Do NOT trigger on vague phrases like "stop", "turn off" (could mean volume/lights), "go to sleep", or "goodbye"
   The user must clearly refer to exiting the application or shutting down the device.
   Parameters: {{"action": "exit|shutdown"}}
   Example (exit): {{"function": "system_control", "parameters": {{"action": "exit"}}}}
   Example (shutdown): {{"function": "system_control", "parameters": {{"action": "shutdown"}}}}""",
    "examples": [
        """Example - Exit program:
User: "Exit the program"
Response: {{"reply": "Shutting down the program. See you later!", "function_calls": [{{"function": "system_control", "parameters": {{"action": "exit"}}}}], "new_memories": []}}""",
        """Example - Shutdown device:
User: "Shut down the raspberry pi"
Response: {{"reply": "Powering off now. Goodbye!", "function_calls": [{{"function": "system_control", "parameters": {{"action": "shutdown"}}}}], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Exit program or shutdown device. Returns reply text."""
    from modules.module_messageQue import queue_message

    action = parameters.get("action", "")
    bot_response = context.get("bot_response", {})

    if action == "exit":
        queue_message("[SYSTEM] Exit requested via voice command")

        def exit_after_tts():
            import time
            time.sleep(5)
            try:
                from modules.module_main import ui_manager
                if ui_manager and hasattr(ui_manager, 'exit_program'):
                    ui_manager.exit_program()
                else:
                    from modules.module_main import shutdown_event
                    if shutdown_event:
                        shutdown_event.set()
                    import sys
                    sys.exit(0)
            except Exception as e:
                queue_message(f"Exit failed: {e}")
                import sys
                sys.exit(0)

        threading.Thread(target=exit_after_tts, daemon=False).start()
        return bot_response.get("reply", "Shutting down the program. See you later!")

    elif action == "shutdown":
        queue_message("[SYSTEM] Shutdown requested via voice command")

        def shutdown_after_tts():
            import time
            time.sleep(5)
            try:
                from modules.module_main import ui_manager
                if ui_manager and hasattr(ui_manager, 'initiate_shutdown'):
                    ui_manager.initiate_shutdown()
                else:
                    import subprocess
                    subprocess.Popen(['sudo', 'shutdown', 'now'])
                    import sys
                    sys.exit(0)
            except Exception as e:
                queue_message(f"Shutdown failed: {e}")
                import subprocess
                subprocess.Popen(['sudo', 'shutdown', 'now'])
                import sys
                sys.exit(0)

        threading.Thread(target=shutdown_after_tts, daemon=False).start()
        return bot_response.get("reply", "Powering off now. Goodbye!")

    return "I didn't understand that system command."
