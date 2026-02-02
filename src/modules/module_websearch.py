"""
Module: Web Search
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import requests
import re
import xml.etree.ElementTree as ET
from ddgs import DDGS
from modules.module_messageQue import queue_message
from modules.module_config import load_config

_WIND_DIRECTIONS = {
    'N': 'north', 'S': 'south', 'E': 'east', 'W': 'west',
    'NE': 'northeast', 'NW': 'northwest', 'SE': 'southeast', 'SW': 'southwest',
    'NNE': 'north northeast', 'ENE': 'east northeast',
    'NNW': 'north northwest', 'WNW': 'west northwest',
    'SSE': 'south southeast', 'ESE': 'east southeast',
    'SSW': 'south southwest', 'WSW': 'west southwest',
}

_WEATHER_STRIP_WORDS = [
    'weather', 'forecast', 'temperature', 'temp',
    'current', 'currently',
    "what's", 'whats', 'what', 'how',
    'will', 'is', 'it', 'be', 'like',
    'can', 'you', 'tell', 'me', 'check', 'get',
    'in', 'at', 'for', 'the', 'of',
    'today', 'tonight', 'this evening',
    'tomorrow', 'day after tomorrow',
    'this week', 'next few days', 'week ahead',
]


def _get_default_location():
    try:
        cfg = load_config()
        name = cfg.get('CHAR', {}).get('location_name', '')
        if name:
            return name
        lat = cfg.get('CHAR', {}).get('latitude', '')
        lon = cfg.get('CHAR', {}).get('longitude', '')
        if lat and lon:
            return f"{lat},{lon}"
    except Exception:
        pass
    return 'Quebec City'


def _expand_wind_direction(abbr):
    return _WIND_DIRECTIONS.get(abbr.upper(), abbr.lower())


def _extract_location(query):
    location = query.lower()
    for word in _WEATHER_STRIP_WORDS:
        location = re.sub(r'\b' + re.escape(word) + r'\b', '', location)
    location = ' '.join(location.split()).strip()
    return location if location else _get_default_location()


def _detect_time_reference(query):
    lower_q = query.lower()
    if 'day after tomorrow' in lower_q:
        return 2, "the day after tomorrow"
    if 'tomorrow' in lower_q:
        return 1, "tomorrow"
    if any(w in lower_q for w in ['tonight', 'this evening']):
        return 0, "tonight"
    if any(w in lower_q for w in ['this week', 'next few days', 'week ahead']):
        return -1, "this week"
    return 0, "right now"


def _format_current_weather(current, today_forecast, location):
    condition = current['weatherDesc'][0]['value']
    temp = current['temp_C']
    feels_like = current['FeelsLikeC']
    humidity = current['humidity']
    wind_speed = current['windspeedKmph']
    wind_dir = _expand_wind_direction(current['winddir16Point'])

    parts = [f"Right now in {location} it's {condition.lower()}, {temp} degrees"]

    try:
        if abs(int(temp) - int(feels_like)) >= 3:
            parts.append(f"but it feels like {feels_like}")
    except ValueError:
        pass

    try:
        if int(wind_speed) > 5:
            parts.append(f"Wind is coming from the {wind_dir} at {wind_speed} kilometers per hour")
    except ValueError:
        pass

    try:
        if int(humidity) >= 70:
            parts.append(f"Humidity is at {humidity} percent")
    except ValueError:
        pass

    if today_forecast:
        parts.append(f"The high today is {today_forecast['maxtempC']} and the low is {today_forecast['mintempC']}")

    return ". ".join(parts) + "."


def _format_day_forecast(day_data, location, time_label):
    high = day_data['maxtempC']
    low = day_data['mintempC']
    hourly = day_data.get('hourly', [])

    condition = "mixed conditions"
    if hourly:
        mid_idx = min(4, len(hourly) - 1)
        desc = hourly[mid_idx].get('weatherDesc', [{}])
        if desc and desc[0].get('value'):
            condition = desc[0]['value'].lower()

    parts = [f"{time_label.capitalize()} in {location} expect {condition} with a high of {high} and a low of {low}"]

    if hourly:
        rain_vals = [int(h.get('chanceofrain', 0)) for h in hourly]
        snow_vals = [int(h.get('chanceofsnow', 0)) for h in hourly]
        max_snow = max(snow_vals) if snow_vals else 0
        max_rain = max(rain_vals) if rain_vals else 0
        if max_snow >= 40:
            parts.append(f"There's about a {max_snow} percent chance of snow")
        elif max_rain >= 40:
            parts.append(f"There's about a {max_rain} percent chance of rain")

    return ". ".join(parts) + "."


def _format_multiday_forecast(forecasts, location):
    day_names = ["Today", "Tomorrow", "The day after"]
    parts = [f"Here's the forecast for {location}"]

    for i, day in enumerate(forecasts[:3]):
        high = day['maxtempC']
        low = day['mintempC']
        hourly = day.get('hourly', [])
        condition = "mixed"
        if hourly:
            mid_idx = min(4, len(hourly) - 1)
            desc = hourly[mid_idx].get('weatherDesc', [{}])
            if desc and desc[0].get('value'):
                condition = desc[0]['value'].lower()
        name = day_names[i] if i < len(day_names) else f"Day {i+1}"
        parts.append(f"{name}, {condition}, high of {high} and low of {low}")

    return ". ".join(parts) + "."


def search_google(query):
    lower = query.lower()

    if 'weather' in lower:
        return get_weather(query)

    if any(word in lower for word in ['news', 'latest', 'happening', 'today', 'recent']):
        result = get_news(query)
        if result and "No recent news" not in result and "Couldn't get" not in result:
            return result

    return web_search(query)


def web_search(query):
    try:
        queue_message(f"Searching web: {query}")
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=5))

        if not results:
            return f"No results found for '{query}'."

        formatted = []
        for r in results[:3]:
            title = r.get('title', '').strip()
            body = r.get('body', '').strip()
            if body:
                if len(body) > 200:
                    body = body[:197] + "..."
                formatted.append(f"• {title}: {body}")
            elif title:
                formatted.append(f"• {title}")

        if formatted:
            queue_message(f"Found {len(formatted)} results")
            return "\n".join(formatted)

        return f"No results found for '{query}'."

    except Exception as e:
        queue_message(f"Search error: {e}")
        return f"Search failed: {str(e)}"


def get_news(query):
    try:
        topic = query.lower()
        for word in ['news', 'latest', 'about', 'happening', 'recent', 'today', 'whats', "what's"]:
            topic = topic.replace(word, '')
        topic = topic.strip()
        if not topic:
            topic = 'world'

        queue_message(f"Getting news for: {topic}")
        url = f"https://news.google.com/rss/search?q={topic}&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        headlines = []
        for item in root.findall('.//item')[:5]:
            title = item.find('title')
            if title is not None and title.text:
                clean_title = title.text.rsplit(' - ', 1)[0]
                if len(clean_title) > 120:
                    clean_title = clean_title[:117] + "..."
                headlines.append(clean_title)

        if headlines:
            queue_message(f"Found {len(headlines)} headlines")
            return "Latest headlines:\n" + "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines[:3])])

        return f"No recent news found about {topic}."

    except Exception as e:
        queue_message(f"News error: {e}")
        return f"Couldn't get news: {str(e)}"


def get_weather(query):
    location = _extract_location(query)
    location_display = location.title()

    try:
        forecast_day, time_label = _detect_time_reference(query)
        queue_message(f"Getting weather for: {location} ({time_label})")

        response = requests.get(f"https://wttr.in/{location}?format=j1", timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data['current_condition'][0]
        forecasts = data.get('weather', [])

        if forecast_day == 0 and time_label == "right now":
            return _format_current_weather(current, forecasts[0] if forecasts else None, location_display)

        if 0 <= forecast_day <= 2 and forecast_day < len(forecasts):
            return _format_day_forecast(forecasts[forecast_day], location_display, time_label)

        if forecast_day == -1 and forecasts:
            return _format_multiday_forecast(forecasts, location_display)

        return f"Couldn't get the forecast for {time_label} in {location_display}."

    except Exception as e:
        queue_message(f"Weather error: {e}")
        return f"Couldn't get the weather for {location_display} right now."


def search_google_news(query):
    return get_news(query)


def search_duckduckgo(query):
    return search_google(query)