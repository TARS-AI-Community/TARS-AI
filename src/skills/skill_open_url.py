"""Skill: open_url — Open a website URL in the browser."""

SKILL = {
    "name": "open_url",
    "prompt": """open_url
   Triggers: "open [website]", "go to [site]", "visit [url]"
   Parameters: {{"url": "https://...", "description": "optional"}}
   Example: {{"function": "open_url", "parameters": {{"url": "https://google.com", "description": "Google"}}}}""",
}


def _close_ui_and_pause_stt():
    from modules.module_messageQue import queue_message
    try:
        from modules.module_stt import get_stt_manager
        stt = get_stt_manager()
        if stt:
            stt.pause()
            queue_message("STT paused during browser session")
    except Exception as e:
        queue_message(f"Could not pause STT: {e}")
    try:
        from modules.module_main import ui_manager
        if ui_manager and ui_manager.running:
            queue_message("Closing UI for browser...")
            ui_manager.running = False
            ui_manager.join(timeout=5)
            queue_message("UI closed")
    except Exception as e:
        queue_message(f"Could not close UI: {e}")


def _reopen_ui_and_resume_stt():
    from modules.module_messageQue import queue_message
    try:
        from modules.module_main import ui_manager, shutdown_event, battery_module, stt_manager
        import modules.module_main as main_module
        from modules.module_main import UIManager

        if ui_manager and not ui_manager.running:
            queue_message("Reopening UI...")
            if shutdown_event is None:
                queue_message("ERROR: Missing shutdown_event - cannot reopen UI")
                return
            new_ui_manager = UIManager(shutdown_event=shutdown_event, battery_module=battery_module)
            new_ui_manager.start()
            main_module.ui_manager = new_ui_manager
            if stt_manager:
                stt_manager.ui_manager = new_ui_manager
            from modules.module_main import memory_manager
            if memory_manager:
                memory_manager.ui_manager = new_ui_manager
            queue_message("UI reopened")
    except Exception as e:
        queue_message(f"Could not reopen UI: {e}")
        import traceback
        traceback.print_exc()
    try:
        from modules.module_stt import get_stt_manager
        stt = get_stt_manager()
        if stt:
            stt.resume()
            queue_message("STT resumed")
    except Exception as e:
        queue_message(f"Could not resume STT: {e}")


def execute(parameters, context):
    """Open a URL in the browser. Returns reply text."""
    from modules.module_messageQue import queue_message

    url = parameters.get("url", "")
    description = parameters.get("description", "")
    if not url:
        return "No URL provided."

    from modules.module_browser import get_browser_player
    player = get_browser_player()
    player.set_callbacks(on_start=_close_ui_and_pause_stt, on_end=_reopen_ui_and_resume_stt)

    queue_message(f"Opening URL: {url}")
    success = player.play_video(url)

    if success:
        return f"Opening {description if description else url}"
    return "Failed to open the website"
