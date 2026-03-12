"""Skill: play_youtube — Search and play a YouTube video."""

SKILL = {
    "name": "play_youtube",
    "prompt": """play_youtube
   Triggers: "play [video topic]", "show me [video]", "watch [video]"
   Parameters: {{"query": "search terms"}}
   Example: {{"function": "play_youtube", "parameters": {{"query": "funny cats"}}}}""",
}


def _close_ui_and_pause_stt():
    from modules.module_messageQue import queue_message
    try:
        from modules.module_stt import get_stt_manager
        stt = get_stt_manager()
        if stt:
            stt.pause()
            queue_message("STT paused during video playback")
    except Exception as e:
        queue_message(f"Could not pause STT: {e}")
    try:
        from modules.module_main import ui_manager
        if ui_manager and ui_manager.running:
            queue_message("Closing UI for browser playback...")
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
    """Search and play a YouTube video. Returns reply text."""
    query = parameters.get("query", "")
    if not query:
        return "Please specify what video you'd like to watch."

    from modules.module_browser import search_and_play
    result = search_and_play(query, on_start=_close_ui_and_pause_stt, on_end=_reopen_ui_and_resume_stt)
    if result['success']:
        video_info = result.get('video', {})
        return f"{result['message']} by {video_info.get('channel', 'Unknown')}."
    return result['message']
