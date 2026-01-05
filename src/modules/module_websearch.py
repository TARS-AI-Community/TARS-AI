"""
module_websearch.py

Web Search Module for TARS-AI using free APIs.
"""

import requests
import xml.etree.ElementTree as ET
from modules.module_messageQue import queue_message

def search_google(query):
    """
    Search using DuckDuckGo instant answer API (free, no auth).
    
    Parameters:
    - query (str): The search query.
    
    Returns:
    - str: Extracted search results.
    """
    
    # Check if it's a weather query
    if 'weather' in query.lower():
        return get_weather(query)
    
    # Check if it's a news query
    if any(word in query.lower() for word in ['news', 'latest', 'happening', 'today']):
        return get_news(query)
    
    try:
        queue_message(f"Searching DuckDuckGo: {query}")
        
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        results = []
        
        # Abstract (summary from Wikipedia, etc.)
        if data.get('AbstractText'):
            results.append(data['AbstractText'])
        
        # Instant answer
        if data.get('Answer'):
            results.append(data['Answer'])
        
        # Definition
        if data.get('Definition'):
            results.append(data['Definition'])
        
        # Related topics
        if data.get('RelatedTopics') and not results:
            for topic in data['RelatedTopics'][:3]:
                if isinstance(topic, dict) and topic.get('Text'):
                    results.append(topic['Text'])
        
        if results:
            combined = " ".join(results[:2])
            queue_message(f"Found: {combined[:150]}...")
            return combined
        else:
            return f"No instant answer found for '{query}'. Try being more specific."
            
    except Exception as e:
        queue_message(f"Search error: {e}")
        return f"Search failed: {str(e)}"

def get_news(query):
    """
    Get news using Google News RSS feed.
    
    Parameters:
    - query (str): Query containing topic.
    
    Returns:
    - str: News headlines.
    """
    try:
        # Clean query - remove news-related words
        topic = query.lower()
        for word in ['news', 'latest', 'today', 'happening', 'what', 'the', 'in', 'about']:
            topic = topic.replace(word, '')
        topic = topic.strip()
        
        if not topic:
            topic = 'world'
        
        queue_message(f"Getting news for: {topic}")
        
        # Google News RSS feed
        url = f"https://news.google.com/rss/search?q={topic}&hl=en-US&gl=US&ceid=US:en"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Parse RSS XML
        root = ET.fromstring(response.content)
        
        headlines = []
        for item in root.findall('.//item')[:5]:
            title = item.find('title')
            if title is not None and title.text:
                # Remove source name (everything after last " - ")
                clean_title = title.text.rsplit(' - ', 1)[0]
                # Limit length
                if len(clean_title) > 120:
                    clean_title = clean_title[:117] + "..."
                headlines.append(clean_title)
        
        if headlines:
            # Format as numbered list
            news_text = "Latest headlines:\n" + "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines[:3])])
            queue_message(f"Found {len(headlines)} headlines")
            return news_text
        else:
            return f"No recent news found about {topic}."
        
    except Exception as e:
        queue_message(f"News error: {e}")
        return f"Couldn't get news: {str(e)}"

def get_weather(query):
    """
    Get weather using wttr.in free weather service.
    
    Parameters:
    - query (str): Query containing location.
    
    Returns:
    - str: Weather information.
    """
    try:
        # Extract location from query
        location = query.lower().replace('weather', '').replace('in', '').replace('at', '').strip()
        if not location:
            location = 'Quebec City'  # Default
        
        queue_message(f"Getting weather for: {location}")
        
        # Get JSON format for detailed info
        url = f"https://wttr.in/{location}?format=j1"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract current conditions
        current = data['current_condition'][0]
        
        # Get today's forecast
        today = data['weather'][0]
        
        weather_text = (
            f"{location.title()}: {current['weatherDesc'][0]['value']}, "
            f"{current['temp_C']}°C (feels like {current['FeelsLikeC']}°C). "
            f"Humidity {current['humidity']}%, "
            f"Wind {current['windspeedKmph']}km/h {current['winddir16Point']}. "
            f"High: {today['maxtempC']}°C, Low: {today['mintempC']}°C."
        )
        
        queue_message(f"Weather: {weather_text}")
        return weather_text
        
    except Exception as e:
        queue_message(f"Weather error: {e}")
        return f"Couldn't get weather data: {str(e)}"

def search_google_news(query):
    """
    Search news (alias for get_news).
    
    Parameters:
    - query (str): The search query.
    
    Returns:
    - str: News results.
    """
    return get_news(query)

def search_duckduckgo(query):
    """
    Direct DuckDuckGo search (alias for search_google).
    
    Parameters:
    - query (str): The search query.
    
    Returns:
    - str: Search results.
    """
    return search_google(query)