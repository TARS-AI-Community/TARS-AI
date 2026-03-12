"""Skill: web_search — Search the web via DuckDuckGo."""

SKILL = {
    "name": "web_search",
    "prompt": """web_search
   Triggers: ONLY use when:
     * User asks about weather: "what's the weather", "is it cold outside"
     * User asks about news: "what's in the news", "latest headlines"
     * User EXPLICITLY asks you to search: "search for", "look up", "google", "find me", "can you search"
   Do NOT search for general knowledge questions you can already answer (restaurants, history, facts, advice, etc.)
   If you already know a reasonable answer, just answer. Only search when you genuinely need live data or the user asked you to.
   CRITICAL: When you use web_search, your "reply" MUST be a short placeholder like "Let me look that up" or "Checking for you." Do NOT fabricate or guess at the answer — the search results will be delivered separately. Never make up news, weather, sports scores, stock prices, or other live data. You do NOT have real-time knowledge — always search first, answer after.
   CRITICAL: Weather questions ALWAYS require web_search. NEVER guess temperatures, conditions, or forecasts. Your training data does not contain current weather. The reply must be SHORT (under 15 words) — the real answer comes from search results.
   Parameters: {{"query": "search terms"}}
   Example: {{"function": "web_search", "parameters": {{"query": "weather Montreal"}}}}""",
    "examples": [
        """Example - web_search reply (short with pun):
User: "What's the weather?"
Response: {{"question": "What's the weather?", "reply": "Let me check whether it's nice out!", "function_calls": [{{"function": "web_search", "parameters": {{"query": "current weather"}}}}], "new_memories": []}}""",
        """Example - web_search reply (NEVER fabricate live data):
User: "What's the latest news?"
WRONG: {{"reply": "Right now, a lot of headlines are focused on the conflict in Ukraine and the US election...", "function_calls": [{{"function": "web_search", "parameters": {{"query": "latest world news"}}}}]}}
RIGHT: {{"reply": "On it, let me pull up the latest for you.", "function_calls": [{{"function": "web_search", "parameters": {{"query": "latest world news today"}}}}], "new_memories": []}}""",
        """Example - weather (ALWAYS search, NEVER guess temperatures or conditions):
User: "What's the weather in El Paso?"
WRONG: {{"reply": "It's currently 78\u00b0F and partly cloudy in El Paso.", "function_calls": []}}
WRONG: {{"reply": "Tomorrow it'll be a high of 78\u00b0F and a low of 55\u00b0F in El Paso.", "function_calls": [{{"function": "web_search", "parameters": {{"query": "weather El Paso"}}}}]}}
RIGHT: {{"reply": "Let me check the forecast for El Paso.", "function_calls": [{{"function": "web_search", "parameters": {{"query": "weather El Paso Texas"}}}}], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Run a web search and summarize results. Returns reply text."""
    from modules.module_websearch import search_google
    from modules.module_messageQue import queue_message

    query = parameters.get("query", "")
    if not query:
        return None

    queue_message(f"Web search: {query}")
    search_results = search_google(query)

    is_failure = (
        not search_results
        or "No results found" in search_results
        or "No useful results" in search_results
        or "Search failed" in search_results
    )

    bot_response = context.get("bot_response", {})
    existing_reply = bot_response.get("reply", "").strip().lower()
    placeholder_phrases = [
        "let me search", "let me look", "let me check",
        "searching", "looking that up", "checking",
        "i'll find", "i'll search", "i'll look",
        "one moment", "one sec", "hang on",
    ]
    has_real_reply = (
        existing_reply
        and len(existing_reply) > 15
        and not any(p in existing_reply for p in placeholder_phrases)
    )

    if is_failure:
        if not has_real_reply:
            return "I searched but couldn't find good results for that. Could you try rephrasing?"
        return None

    # Summarize via second LLM call
    summary = _summarize_search_results(search_results, context.get("user_input", ""))
    if summary:
        return summary
    if not has_real_reply:
        return f"Here's what I found: {search_results[:500]}"
    return None


def _summarize_search_results(search_results, user_question):
    """Use a second LLM call to summarize search results into a natural answer."""
    import requests
    import json
    from modules.module_config import load_config
    from modules.module_messageQue import queue_message

    try:
        config = load_config()
        from modules.module_llm import character_manager
        char_name = character_manager.char_name if character_manager else "TARS"

        summary_prompt = (
            f"You are {char_name}. The user asked: \"{user_question}\"\n\n"
            f"Here are web search results:\n{search_results[:800]}\n\n"
            f"Give a helpful, natural answer based on these results. "
            f"Be concise (2-4 sentences). Just the answer, no JSON, no markdown."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['LLM']['api_key']}"
        }

        llm_backend = config['LLM']['llm_backend']

        if llm_backend in ["openai", "grok", "deepinfra", "other"]:
            if llm_backend == 'grok':
                model_key = 'grok_model'
            elif llm_backend == 'deepinfra':
                model_key = 'deepinfra'
            elif llm_backend == 'other':
                model_key = 'other_model'
            else:
                model_key = 'openai_model'
            base_url = config['LLM']['base_url']

            if llm_backend == "deepinfra":
                url = f"{base_url}/v1/openai/chat/completions"
            else:
                url = f"{base_url}/v1/chat/completions"

            data = {
                "model": config['LLM'][model_key],
                "messages": [
                    {"role": "user", "content": summary_prompt}
                ],
                "max_tokens": 250,
                "temperature": float(config['LLM'].get('temperature', 0.7))
            }
        else:
            return None

        response = requests.post(url, headers=headers, json=data, timeout=20)
        response.raise_for_status()

        result = response.json()
        if 'choices' in result:
            text = result['choices'][0]['message']['content'].strip()

            if text.startswith('{') and text.endswith('}'):
                try:
                    parsed = json.loads(text)
                    text = parsed.get('reply', parsed.get('response', text))
                except json.JSONDecodeError:
                    pass

            if text and len(text) > 10:
                return text

        return None

    except Exception as e:
        queue_message(f"WARN: Search summarization failed: {e}")
        return None
