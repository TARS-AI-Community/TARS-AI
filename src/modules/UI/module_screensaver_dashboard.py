"""
Module: Dashboard Screensaver (Magic Mirror Style)
Author: Charles-Olivier Dion (Atomikspace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026

This module was originally created by Charles-Olivier Dion (Atomikspace).

Permission is granted to use, copy, modify, and redistribute this module,
in whole or in part, provided that:

- This notice is retained in the source file(s)
- The original author (Charles-Olivier Dion / Atomikspace) is clearly credited
- Any modifications are clearly identified as such

This notice applies only to this module and does not extend to the
entire project or repository in which it may be included.

APIs Used (No API Key Required):
- Open-Meteo (https://open-meteo.com) - Weather and forecast
- Google News RSS - News feeds
- JokeAPI (https://jokeapi.dev) - Jokes (multilingual)

Configuration:
- Edit dashboard.ini in the /src folder
- Set location, language, display options, and custom quotes
"""

import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import math
import random
import threading
import time
import json
import io
import os
import configparser
import urllib.request
import urllib.error
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from html import unescape
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
import re

from modules.module_config import load_config

CONFIG = load_config()

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(os.path.dirname(MODULE_DIR))
INI_PATH = os.path.join(SRC_DIR, "dashboard.ini")

def load_ini_config():
    config = configparser.ConfigParser()
    
    defaults = {
        'latitude': 45.5017,
        'longitude': -73.5673,
        'timezone': 'America/Montreal',
        'location_name': 'Montreal',
        'language': 'en',
        'country': 'CA',
        'temp_unit': 'celsius',
        'weather_update_interval': 600,
        'news_update_interval': 300,
        'max_news_items': 30,
        'scroll_speed': 18,
        'show_weather': True,
        'show_forecast': True,
        'show_sun_moon': True,
        'show_news': True,
        'show_clock': True,
        'show_date': True,
        'show_quotes': True,
        'background_animation': True,
        'quote_mode': 'alternate',
        'calendar_ics_urls': [],
        'calendar_days_ahead': 7,
        'calendar_max_events': 10,
        'calendar_update_interval': 300,
        'feed_mode': 'news',
    }
    
    if os.path.exists(INI_PATH):
        try:
            config.read(INI_PATH, encoding='utf-8')
            
            if config.has_section('Location'):
                defaults['latitude'] = config.getfloat('Location', 'latitude', fallback=defaults['latitude'])
                defaults['longitude'] = config.getfloat('Location', 'longitude', fallback=defaults['longitude'])
                defaults['timezone'] = config.get('Location', 'timezone', fallback=defaults['timezone'])
                defaults['location_name'] = config.get('Location', 'location_name', fallback=defaults['location_name'])
            
            if config.has_section('Language'):
                defaults['language'] = config.get('Language', 'language', fallback=defaults['language'])
                defaults['country'] = config.get('Language', 'country', fallback=defaults['country'])
            
            if config.has_section('Weather'):
                defaults['temp_unit'] = config.get('Weather', 'temp_unit', fallback=defaults['temp_unit'])
                defaults['weather_update_interval'] = config.getint('Weather', 'update_interval', fallback=defaults['weather_update_interval'])
            
            if config.has_section('News'):
                defaults['news_update_interval'] = config.getint('News', 'update_interval', fallback=defaults['news_update_interval'])
                defaults['max_news_items'] = config.getint('News', 'max_items', fallback=defaults['max_news_items'])
            
            if config.has_section('Display'):
                defaults['show_weather'] = config.getboolean('Display', 'show_weather', fallback=defaults['show_weather'])
                defaults['show_forecast'] = config.getboolean('Display', 'show_forecast', fallback=defaults['show_forecast'])
                defaults['show_sun_moon'] = config.getboolean('Display', 'show_sun_moon', fallback=defaults['show_sun_moon'])
                defaults['show_news'] = config.getboolean('Display', 'show_news', fallback=defaults['show_news'])
                defaults['show_clock'] = config.getboolean('Display', 'show_clock', fallback=defaults['show_clock'])
                defaults['show_date'] = config.getboolean('Display', 'show_date', fallback=defaults['show_date'])
                defaults['show_quotes'] = config.getboolean('Display', 'show_quotes', fallback=defaults['show_quotes'])
                defaults['background_animation'] = config.getboolean('Display', 'background_animation', fallback=defaults['background_animation'])
                defaults['scroll_speed'] = config.getint('Display', 'scroll_speed', fallback=defaults['scroll_speed'])
            
            if config.has_section('QuoteMode'):
                defaults['quote_mode'] = config.get('QuoteMode', 'mode', fallback=defaults['quote_mode'])
            
            if config.has_section('Calendar'):
                ics_urls_str = config.get('Calendar', 'ics_urls', fallback='')
                if not ics_urls_str:
                    ics_urls_str = config.get('Calendar', 'ics_url', fallback='')
                if ics_urls_str:
                    defaults['calendar_ics_urls'] = [url.strip() for url in ics_urls_str.split(',') if url.strip()]
                defaults['calendar_days_ahead'] = config.getint('Calendar', 'days_ahead', fallback=defaults['calendar_days_ahead'])
                defaults['calendar_max_events'] = config.getint('Calendar', 'max_events', fallback=defaults['calendar_max_events'])
                defaults['calendar_update_interval'] = config.getint('Calendar', 'update_interval', fallback=defaults['calendar_update_interval'])
            
            if config.has_section('Feed'):
                defaults['feed_mode'] = config.get('Feed', 'mode', fallback=defaults['feed_mode'])
            
            pass
        except Exception as e:
            pass
    else:
        pass
    
    return defaults, config

def load_quotes_from_ini(config, language):
    quotes = []
    
    section_name = f"Quotes_{language}"
    if not config.has_section(section_name):
        section_name = "Quotes_en"
    
    if config.has_section(section_name):
        quote_items = []
        for key, value in config.items(section_name):
            if key.startswith('quote_'):
                try:
                    num = int(key.split('_')[1])
                    quote_items.append((num, value))
                except (ValueError, IndexError):
                    continue
        
        quote_items.sort(key=lambda x: x[0])
        for _, value in quote_items:
            if '|' in value:
                parts = value.rsplit('|', 1)
                quote_text = parts[0].strip()
                author = parts[1].strip()
                quotes.append((quote_text, author))
    
    return quotes if quotes else None

class DashboardConfig:
    
    def __init__(self):
        ini_values, self._ini_config = load_ini_config()
        
        self.LATITUDE = ini_values['latitude']
        self.LONGITUDE = ini_values['longitude']
        self.TIMEZONE = ini_values['timezone']
        self.LOCATION_NAME = ini_values['location_name']
        
        self.LANGUAGE = ini_values['language']
        self.COUNTRY = ini_values['country']
        
        self.TEMP_UNIT = ini_values['temp_unit']
        
        self.WEATHER_UPDATE_INTERVAL = ini_values['weather_update_interval']
        self.NEWS_UPDATE_INTERVAL = ini_values['news_update_interval']
        
        self.SHOW_WEATHER = ini_values['show_weather']
        self.SHOW_FORECAST = ini_values['show_forecast']
        self.SHOW_SUN_MOON = ini_values['show_sun_moon']
        self.SHOW_NEWS = ini_values['show_news']
        self.SHOW_CLOCK = ini_values['show_clock']
        self.SHOW_DATE = ini_values['show_date']
        self.SHOW_QUOTES = ini_values['show_quotes']
        self.BACKGROUND_ANIMATION = ini_values['background_animation']
        
        self.QUOTE_MODE = ini_values['quote_mode']
        
        self.MAX_NEWS_ITEMS = ini_values['max_news_items']
        self.SCROLL_SPEED = ini_values['scroll_speed']
        
        self.CALENDAR_ICS_URLS = ini_values['calendar_ics_urls']
        self.CALENDAR_DAYS_AHEAD = ini_values['calendar_days_ahead']
        self.CALENDAR_MAX_EVENTS = ini_values['calendar_max_events']
        self.CALENDAR_UPDATE_INTERVAL = ini_values['calendar_update_interval']
        self.FEED_MODE = ini_values['feed_mode']
        
        self.FORECAST_DAYS = 5
    
    def get_quotes(self, language):
        quotes = load_quotes_from_ini(self._ini_config, language)
        return quotes

DATE_FORMATS = {
    "en": "{day}, {month} {d}, {year}",
    "fr": "{day} {d} {month} {year}",
    "es": "{day}, {d} de {month} de {year}",
    "de": "{day}, {d}. {month} {year}",
}

def format_date_localized(dt, lang, labels):
    day_name = labels["days_full"][dt.weekday()]
    month_name = labels["months"][dt.month - 1]
    
    fmt = DATE_FORMATS.get(lang, "{day}, {month} {d}, {year}")
    return fmt.format(day=day_name, month=month_name, d=dt.day, year=dt.year)

def calculate_moon_phase(dt=None):
    if dt is None:
        dt = datetime.now()
    
    known_new_moon = datetime(2000, 1, 6, 18, 14, 0)
    
    synodic_month = 29.530588853
    
    diff = dt - known_new_moon
    days_since = diff.total_seconds() / 86400
    
    cycle_position = (days_since % synodic_month) / synodic_month
    
    phase_angle = cycle_position * 360
    
    illumination = (1 - math.cos(cycle_position * 2 * math.pi)) / 2
    
    phase_index = int(cycle_position * 8) % 8
    
    return phase_index, illumination, phase_angle

NEWS_FEEDS = []

def build_news_feeds(config):
    location = config.LOCATION_NAME
    lang = config.LANGUAGE
    country = config.COUNTRY
    
    geo = location.replace(" ", "%20")
    
    feeds = [
        ("Local", f"https://news.google.com/rss/headlines/section/geo/{geo}?hl={lang}-{country}&gl={country}&ceid={country}:{lang}"),
        ("Top Stories", f"https://news.google.com/rss?hl={lang}-{country}&gl={country}&ceid={country}:{lang}"),
        ("Technology", f"https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl={lang}-{country}&gl={country}&ceid={country}:{lang}"),
        ("Science", f"https://news.google.com/rss/headlines/section/topic/SCIENCE?hl={lang}-{country}&gl={country}&ceid={country}:{lang}"),
        ("Business", f"https://news.google.com/rss/headlines/section/topic/BUSINESS?hl={lang}-{country}&gl={country}&ceid={country}:{lang}"),
        ("World", f"https://news.google.com/rss/headlines/section/topic/WORLD?hl={lang}-{country}&gl={country}&ceid={country}:{lang}"),
    ]
    
    return feeds

UI_LABELS = {
    "en": {
        "current_weather": "CURRENT WEATHER",
        "forecast": "FORECAST",
        "news": "NEWS",
        "loading": "Loading...",
        "loading_weather": "Loading weather...",
        "loading_news": "Loading news...",
        "feels": "Feels",
        "humidity": "Humidity",
        "wind": "Wind",
        "today": "Today",
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "days_full": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "months": ["January", "February", "March", "April", "May", "June", 
                   "July", "August", "September", "October", "November", "December"],
        "sunrise": "Sunrise",
        "sunset": "Sunset",
        "moon_phases": ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", 
                        "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"],
        "calendar": "CALENDAR",
        "loading_calendar": "Loading calendar...",
        "no_events": "No events in the next {days} days",
        "all_day": "All day",
        "tomorrow": "Tomorrow",
        "ongoing": "Ongoing",
    },
    "fr": {
        "current_weather": "MÉTÉO ACTUELLE",
        "forecast": "PRÉVISIONS",
        "news": "ACTUALITÉS",
        "loading": "Chargement...",
        "loading_weather": "Chargement météo...",
        "loading_news": "Chargement actualités...",
        "feels": "Ressenti",
        "humidity": "Humidité",
        "wind": "Vent",
        "today": "Auj.",
        "days": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
        "days_full": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
        "months": ["janvier", "février", "mars", "avril", "mai", "juin",
                   "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
        "sunrise": "Lever",
        "sunset": "Coucher",
        "moon_phases": ["Nouvelle Lune", "Premier Croissant", "Premier Quartier", "Gibbeuse Croissante",
                        "Pleine Lune", "Gibbeuse Décroissante", "Dernier Quartier", "Dernier Croissant"],
        "calendar": "CALENDRIER",
        "loading_calendar": "Chargement calendrier...",
        "no_events": "Aucun événement dans les {days} prochains jours",
        "all_day": "Toute la journée",
        "tomorrow": "Demain",
        "ongoing": "En cours",
    },
    "es": {
        "current_weather": "CLIMA ACTUAL",
        "forecast": "PRONÓSTICO",
        "news": "NOTICIAS",
        "loading": "Cargando...",
        "loading_weather": "Cargando clima...",
        "loading_news": "Cargando noticias...",
        "feels": "Sensación",
        "humidity": "Humedad",
        "wind": "Viento",
        "today": "Hoy",
        "days": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
        "days_full": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "months": ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                   "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
        "sunrise": "Amanecer",
        "sunset": "Atardecer",
        "moon_phases": ["Luna Nueva", "Creciente", "Cuarto Creciente", "Gibosa Creciente",
                        "Luna Llena", "Gibosa Menguante", "Cuarto Menguante", "Menguante"],
        "calendar": "CALENDARIO",
        "loading_calendar": "Cargando calendario...",
        "no_events": "Sin eventos en los próximos {days} días",
        "all_day": "Todo el día",
        "tomorrow": "Mañana",
        "ongoing": "En curso",
    },
    "de": {
        "current_weather": "AKTUELLES WETTER",
        "forecast": "VORHERSAGE",
        "news": "NACHRICHTEN",
        "loading": "Laden...",
        "loading_weather": "Wetter laden...",
        "loading_news": "Nachrichten laden...",
        "feels": "Gefühlt",
        "humidity": "Feuchtigkeit",
        "wind": "Wind",
        "today": "Heute",
        "days": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "days_full": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "months": ["Januar", "Februar", "März", "April", "Mai", "Juni",
                   "Juli", "August", "September", "Oktober", "November", "Dezember"],
        "sunrise": "Sonnenaufgang",
        "sunset": "Sonnenuntergang",
        "moon_phases": ["Neumond", "Zunehmende Sichel", "Erstes Viertel", "Zunehmender Mond",
                        "Vollmond", "Abnehmender Mond", "Letztes Viertel", "Abnehmende Sichel"],
        "calendar": "KALENDER",
        "loading_calendar": "Kalender laden...",
        "no_events": "Keine Termine in den nächsten {days} Tagen",
        "all_day": "Ganztägig",
        "tomorrow": "Morgen",
        "ongoing": "Laufend",
    },
}

WEATHER_DESCRIPTIONS = {
    "en": {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
        56: "Freezing drizzle", 57: "Dense freezing drizzle",
        61: "Slight rain", 63: "Rain", 65: "Heavy rain",
        66: "Freezing rain", 67: "Heavy freezing rain",
        71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
        80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
        85: "Snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm", 99: "Severe storm",
    },
    "fr": {
        0: "Ciel dégagé", 1: "Peu nuageux", 2: "Partiellement nuageux", 3: "Couvert",
        45: "Brouillard", 48: "Brouillard givrant", 51: "Bruine légère", 53: "Bruine", 55: "Forte bruine",
        56: "Bruine verglaçante", 57: "Forte bruine verglaçante",
        61: "Pluie légère", 63: "Pluie", 65: "Forte pluie",
        66: "Pluie verglaçante", 67: "Forte pluie verglaçante",
        71: "Neige légère", 73: "Neige", 75: "Forte neige", 77: "Grains de neige",
        80: "Averses", 81: "Averses", 82: "Fortes averses",
        85: "Averses de neige", 86: "Fortes averses de neige",
        95: "Orage", 96: "Orage", 99: "Violent orage",
    },
    "es": {
        0: "Cielo despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado",
        45: "Niebla", 48: "Niebla helada", 51: "Llovizna ligera", 53: "Llovizna", 55: "Llovizna densa",
        56: "Llovizna helada", 57: "Llovizna helada densa",
        61: "Lluvia ligera", 63: "Lluvia", 65: "Lluvia fuerte",
        66: "Lluvia helada", 67: "Lluvia helada fuerte",
        71: "Nieve ligera", 73: "Nieve", 75: "Nevada fuerte", 77: "Granos de nieve",
        80: "Chubascos", 81: "Chubascos", 82: "Chubascos fuertes",
        85: "Chubascos de nieve", 86: "Fuertes chubascos de nieve",
        95: "Tormenta", 96: "Tormenta", 99: "Tormenta severa",
    },
    "de": {
        0: "Klarer Himmel", 1: "Überwiegend klar", 2: "Teilweise bewölkt", 3: "Bedeckt",
        45: "Nebel", 48: "Raureifnebel", 51: "Leichter Niesel", 53: "Niesel", 55: "Starker Niesel",
        56: "Gefrierender Niesel", 57: "Starker gefrierender Niesel",
        61: "Leichter Regen", 63: "Regen", 65: "Starker Regen",
        66: "Gefrierender Regen", 67: "Starker gefrierender Regen",
        71: "Leichter Schnee", 73: "Schnee", 75: "Starker Schnee", 77: "Schneekörner",
        80: "Regenschauer", 81: "Regenschauer", 82: "Starke Schauer",
        85: "Schneeschauer", 86: "Starke Schneeschauer",
        95: "Gewitter", 96: "Gewitter", 99: "Schweres Gewitter",
    },
}

QUOTES = {
    "en": [
        ("Love is the one thing we're capable of perceiving that transcends dimensions of time and space.", "Interstellar"),
        ("We used to look up at the sky and wonder at our place in the stars. Now we just look down and worry about our place in the dirt.", "Interstellar"),
        ("Mankind was born on Earth. It was never meant to die here.", "Interstellar"),
        ("Do not go gentle into that good night. Rage, rage against the dying of the light.", "Interstellar"),
        ("Time is relative. It can stretch and it can squeeze, but it can't run backwards.", "Interstellar"),
        ("Once you're a parent, you're the ghost of your children's future.", "Interstellar"),
        ("We're explorers, not caretakers.", "Interstellar"),
        ("The universe is vast, but human will is vaster.", "Science Fiction"),
        ("Somewhere, something incredible is waiting to be known.", "Carl Sagan"),
        ("The stars don't look bigger, but they do look brighter.", "Interstellar"),
    ],
    "fr": [
        ("L'amour est la seule chose capable de transcender le temps et l'espace.", "Interstellar"),
        ("Nous levions les yeux vers le ciel pour nous émerveiller des étoiles. Maintenant, nous regardons le sol et nous inquiétons.", "Interstellar"),
        ("L'humanité est née sur Terre. Elle n'était pas destinée à y mourir.", "Interstellar"),
        ("N'entre pas docilement dans cette nuit éternelle. Résiste à l'extinction de la lumière.", "Interstellar"),
        ("Le temps est relatif. Il peut s'étirer et se contracter, mais jamais reculer.", "Interstellar"),
        ("Être parent, c'est devenir le fantôme du futur de ses enfants.", "Interstellar"),
        ("Nous sommes des explorateurs, pas des gardiens.", "Interstellar"),
        ("L'univers est immense, mais la volonté humaine l'est davantage.", "Science-fiction"),
        ("Quelque part, quelque chose d'incroyable attend d'être découvert.", "Carl Sagan"),
        ("Les étoiles ne sont pas plus grandes, mais elles brillent davantage.", "Interstellar"),
    ],
    "es": [
        ("El amor es lo único capaz de trascender el tiempo y el espacio.", "Interstellar"),
        ("Antes mirábamos al cielo y soñábamos con las estrellas. Ahora miramos al suelo y nos preocupamos.", "Interstellar"),
        ("La humanidad nació en la Tierra. No estaba destinada a morir aquí.", "Interstellar"),
        ("No entres dócil en esa noche eterna. Lucha contra la muerte de la luz.", "Interstellar"),
        ("El tiempo es relativo. Puede estirarse, pero no retroceder.", "Interstellar"),
        ("Ser padre es convertirse en el fantasma del futuro de tus hijos.", "Interstellar"),
        ("Somos exploradores, no cuidadores.", "Interstellar"),
        ("El universo es inmenso, pero la voluntad humana lo es aún más.", "Ciencia ficción"),
        ("En algún lugar, algo increíble espera ser descubierto.", "Carl Sagan"),
        ("Las estrellas no son más grandes, pero brillan más.", "Interstellar"),
    ],
    "de": [
        ("Liebe ist das Einzige, was Zeit und Raum überwinden kann.", "Interstellar"),
        ("Früher blickten wir zu den Sternen. Heute schauen wir nach unten und sorgen uns.", "Interstellar"),
        ("Die Menschheit wurde auf der Erde geboren, nicht um hier zu sterben.", "Interstellar"),
        ("Geh nicht sanft in diese gute Nacht. Kämpfe gegen das Erlöschen des Lichts.", "Interstellar"),
        ("Zeit ist relativ. Sie kann sich dehnen, aber nicht zurücklaufen.", "Interstellar"),
        ("Eltern werden heißt, zum Geist der Zukunft der eigenen Kinder zu werden.", "Interstellar"),
        ("Wir sind Entdecker, keine Verwalter.", "Interstellar"),
        ("Das Universum ist groß, aber der menschliche Wille ist größer.", "Science-Fiction"),
        ("Irgendwo wartet etwas Unglaubliches darauf, entdeckt zu werden.", "Carl Sagan"),
        ("Die Sterne wirken nicht größer, aber heller.", "Interstellar"),
    ],
}

WEATHER_ABBREV = {
    "en": {
        0: "Clear", 1: "Clear", 2: "Cloudy", 3: "Cloudy",
        45: "Fog", 48: "Fog", 51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
        56: "Ice", 57: "Ice", 61: "Rain", 63: "Rain", 65: "Rain",
        66: "Ice", 67: "Ice", 71: "Snow", 73: "Snow", 75: "Snow", 77: "Snow",
        80: "Showers", 81: "Showers", 82: "Showers",
        85: "Snow", 86: "Snow", 95: "Storm", 96: "Storm", 99: "Storm",
    },
    "fr": {
        0: "Clair", 1: "Clair", 2: "Nuageux", 3: "Couvert",
        45: "Brouill.", 48: "Brouill.", 51: "Bruine", 53: "Bruine", 55: "Bruine",
        56: "Verglas", 57: "Verglas", 61: "Pluie", 63: "Pluie", 65: "Pluie",
        66: "Verglas", 67: "Verglas", 71: "Neige", 73: "Neige", 75: "Neige", 77: "Neige",
        80: "Averses", 81: "Averses", 82: "Averses",
        85: "Neige", 86: "Neige", 95: "Orage", 96: "Orage", 99: "Orage",
    },
    "es": {
        0: "Despej.", 1: "Despej.", 2: "Nublado", 3: "Cubierto",
        45: "Niebla", 48: "Niebla", 51: "Llovizna", 53: "Llovizna", 55: "Llovizna",
        56: "Helada", 57: "Helada", 61: "Lluvia", 63: "Lluvia", 65: "Lluvia",
        66: "Helada", 67: "Helada", 71: "Nieve", 73: "Nieve", 75: "Nieve", 77: "Nieve",
        80: "Chubas.", 81: "Chubas.", 82: "Chubas.",
        85: "Nieve", 86: "Nieve", 95: "Tormenta", 96: "Tormenta", 99: "Tormenta",
    },
    "de": {
        0: "Klar", 1: "Klar", 2: "Wolkig", 3: "Bedeckt",
        45: "Nebel", 48: "Nebel", 51: "Niesel", 53: "Niesel", 55: "Niesel",
        56: "Eis", 57: "Eis", 61: "Regen", 63: "Regen", 65: "Regen",
        66: "Eis", 67: "Eis", 71: "Schnee", 73: "Schnee", 75: "Schnee", 77: "Schnee",
        80: "Schauer", 81: "Schauer", 82: "Schauer",
        85: "Schnee", 86: "Schnee", 95: "Gewitter", 96: "Gewitter", 99: "Gewitter",
    },
}

class DataFetcher:
    
    def __init__(self, config):
        self.config = config
        self.weather_data = None
        self.forecast_data = None
        self.news_data = []
        self.jokes_data = []
        self.calendar_data = []
        self.calendar_loaded = False
        self.image_cache = {}
        self.last_weather_update = 0
        self.last_news_update = 0
        self.last_jokes_update = 0
        self.last_calendar_update = 0
        self.lock = threading.Lock()
        self.running = True
        
        self.news_feeds = build_news_feeds(config)
        
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
    
    def _update_loop(self):
        while self.running:
            current_time = time.time()
            
            if current_time - self.last_weather_update > self.config.WEATHER_UPDATE_INTERVAL:
                self._fetch_weather()
                self.last_weather_update = current_time
            
            if self.config.FEED_MODE in ("news", "alternate") and current_time - self.last_news_update > self.config.NEWS_UPDATE_INTERVAL:
                self._fetch_news()
                self.last_news_update = current_time
            
            if self.config.FEED_MODE in ("calendar", "alternate") and self.config.CALENDAR_ICS_URLS and current_time - self.last_calendar_update > self.config.CALENDAR_UPDATE_INTERVAL:
                self._fetch_calendar()
                self.last_calendar_update = current_time
            
            if self.config.QUOTE_MODE in ("jokes", "alternate") and current_time - self.last_jokes_update > 600:
                self._fetch_jokes()
                self.last_jokes_update = current_time
            
            time.sleep(30)
    
    def _fetch_weather(self):
        try:
            base_url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": self.config.LATITUDE,
                "longitude": self.config.LONGITUDE,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
                "timezone": self.config.TIMEZONE,
                "forecast_days": self.config.FORECAST_DAYS
            }
            
            if self.config.TEMP_UNIT == "fahrenheit":
                params["temperature_unit"] = "fahrenheit"
            
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{base_url}?{query_string}"
            
            req = urllib.request.Request(url, headers={"User-Agent": "DashboardScreensaver/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            with self.lock:
                self.weather_data = data.get("current", {})
                self.forecast_data = data.get("daily", {})
                
        except Exception as e:
            pass
    
    def _fetch_news(self):
        all_news = []
        
        for source_name, feed_url in self.news_feeds:
            try:
                req = urllib.request.Request(feed_url, headers={
                    "User-Agent": "DashboardScreensaver/1.0"
                })
                with urllib.request.urlopen(req, timeout=10) as response:
                    xml_data = response.read().decode('utf-8', errors='ignore')
                
                root = ET.fromstring(xml_data)
                
                namespaces = {
                    'media': 'http://search.yahoo.com/mrss/',
                    'atom': 'http://www.w3.org/2005/Atom',
                    'content': 'http://purl.org/rss/1.0/modules/content/'
                }
                
                items = root.findall(".//item")
                if not items:
                    items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
                
                for item in items[:10]:
                    title = item.find("title")
                    if title is None:
                        title = item.find("{http://www.w3.org/2005/Atom}title")
                    
                    if title is None or not title.text:
                        continue
                    
                    clean_title = unescape(title.text.strip())
                    clean_title = re.sub(r'<[^>]+>', '', clean_title)
                    
                    desc = item.find("description")
                    if desc is None:
                        desc = item.find("{http://www.w3.org/2005/Atom}summary")
                    if desc is None:
                        desc = item.find("{http://www.w3.org/2005/Atom}content")
                    if desc is None:
                        desc = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
                    
                    clean_desc = ""
                    if desc is not None and desc.text:
                        clean_desc = unescape(desc.text.strip())
                        clean_desc = re.sub(r'<[^>]+>', '', clean_desc)
                        clean_desc = re.sub(r'\s+', ' ', clean_desc)
                        clean_desc = clean_desc[:400]
                    
                    image_url = None
                    
                    thumb = item.find("{http://search.yahoo.com/mrss/}thumbnail")
                    if thumb is not None:
                        image_url = thumb.get('url')
                    
                    if not image_url:
                        media = item.find("{http://search.yahoo.com/mrss/}content")
                        if media is not None:
                            media_type = media.get('type', '')
                            if 'image' in media_type or media.get('url', '').endswith(('.jpg', '.png', '.jpeg', '.webp')):
                                image_url = media.get('url')
                    
                    if not image_url:
                        media_group = item.find("{http://search.yahoo.com/mrss/}group")
                        if media_group is not None:
                            media_content = media_group.find("{http://search.yahoo.com/mrss/}content")
                            if media_content is not None:
                                image_url = media_content.get('url')
                    
                    if not image_url:
                        enclosure = item.find("enclosure")
                        if enclosure is not None:
                            enc_type = enclosure.get('type', '')
                            if 'image' in enc_type or enclosure.get('url', '').endswith(('.jpg', '.png', '.jpeg', '.webp')):
                                image_url = enclosure.get('url')
                    
                    if not image_url:
                        html_content = ""
                        if desc is not None and desc.text:
                            html_content = desc.text
                        content_encoded = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
                        if content_encoded is not None and content_encoded.text:
                            html_content = content_encoded.text
                        
                        if html_content:
                            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
                            if img_match:
                                image_url = img_match.group(1)
                    
                    pub_date = item.find("pubDate")
                    if pub_date is None:
                        pub_date = item.find("{http://www.w3.org/2005/Atom}published")
                    
                    all_news.append({
                        "title": clean_title,
                        "description": clean_desc,
                        "source": source_name,
                        "image_url": image_url,
                        "date": pub_date.text if pub_date is not None else None
                    })
                        
            except Exception as e:
                pass
        
        random.shuffle(all_news)
        
        with self.lock:
            self.news_data = all_news[:self.config.MAX_NEWS_ITEMS * 2]
        
        self._fetch_images()
    
    def _fetch_images(self):
        with self.lock:
            news_copy = list(self.news_data)
        
        for item in news_copy[:self.config.MAX_NEWS_ITEMS]:
            url = item.get('image_url')
            if not url or url in self.image_cache:
                continue
            
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "DashboardScreensaver/1.0"
                })
                with urllib.request.urlopen(req, timeout=5) as response:
                    image_data = response.read()
                
                image_file = io.BytesIO(image_data)
                surface = pygame.image.load(image_file)
                
                thumb_size = (120, 80)
                surface = pygame.transform.smoothscale(surface, thumb_size)
                
                with self.lock:
                    self.image_cache[url] = surface
                    
            except Exception as e:
                with self.lock:
                    self.image_cache[url] = None
    
    def get_image(self, url):
        if not url:
            return None
        with self.lock:
            return self.image_cache.get(url)
    
    def get_weather(self):
        with self.lock:
            return self.weather_data
    
    def get_forecast(self):
        with self.lock:
            return self.forecast_data
    
    def get_news(self, count=30):
        with self.lock:
            return self.news_data[:count]
    
    def get_jokes(self):
        with self.lock:
            return list(self.jokes_data)
    
    def get_calendar(self):
        with self.lock:
            return list(self.calendar_data)
    
    def is_calendar_loaded(self):
        with self.lock:
            return self.calendar_loaded
    
    def _fetch_jokes(self):
        try:
            lang_map = {
                "en": "en",
                "fr": "fr",
                "de": "de",
                "es": "es",
                "pt": "pt",
                "cs": "cs",
            }
            lang = lang_map.get(self.config.LANGUAGE, "en")
            
            url = f"https://v2.jokeapi.dev/joke/Miscellaneous,Pun?type=single&amount=10&lang={lang}&safe-mode"
            
            req = urllib.request.Request(url, headers={"User-Agent": "DashboardScreensaver/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            jokes = []
            if data.get('error') is False:
                joke_list = data.get('jokes', [])
                for joke_data in joke_list:
                    if joke_data.get('type') == 'single':
                        joke_text = joke_data.get('joke', '')
                        if joke_text:
                            jokes.append(joke_text)
            
            if jokes:
                with self.lock:
                    self.jokes_data = jokes
                    
        except Exception as e:
            pass
    
    def _fetch_calendar(self):
        try:
            urls = self.config.CALENDAR_ICS_URLS
            if not urls:
                return
            
            all_events = []
            
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "DashboardScreensaver/1.0"})
                    with urllib.request.urlopen(req, timeout=15) as response:
                        ics_data = response.read().decode('utf-8', errors='ignore')
                    
                    events = self._parse_ics(ics_data)
                    all_events.extend(events)
                except Exception as e:
                    pass
            
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            future_limit = now + timedelta(days=self.config.CALENDAR_DAYS_AHEAD)
            
            upcoming = []
            for event in all_events:
                start = event.get('start')
                end = event.get('end')
                if start:
                    if start >= today_start and start <= future_limit:
                        upcoming.append(event)
                    elif end and end >= now and start < now:
                        upcoming.append(event)
            
            upcoming.sort(key=lambda x: x['start'])
            upcoming = upcoming[:self.config.CALENDAR_MAX_EVENTS]
            
            with self.lock:
                self.calendar_data = upcoming
                self.calendar_loaded = True
                
        except Exception as e:
            with self.lock:
                self.calendar_loaded = True
    
    def _parse_ics(self, ics_data):
        events = []
        lines = ics_data.replace('\r\n ', '').replace('\r\n\t', '').split('\n')
        
        in_event = False
        event = {}
        
        for line in lines:
            line = line.strip()
            
            if line == 'BEGIN:VEVENT':
                in_event = True
                event = {'attendees': []}
            elif line == 'END:VEVENT':
                if event.get('start') and event.get('summary'):
                    if event.get('start') and event.get('end'):
                        delta = event['end'] - event['start']
                        total_minutes = int(delta.total_seconds() / 60)
                        hours, minutes = divmod(total_minutes, 60)
                        if hours > 0 and minutes > 0:
                            event['duration'] = f"{hours}h{minutes}m"
                        elif hours > 0:
                            event['duration'] = f"{hours}h"
                        else:
                            event['duration'] = f"{minutes}m"
                    events.append(event)
                in_event = False
                event = {}
            elif in_event:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key_parts = key.split(';')
                    key_name = key_parts[0]
                    
                    if key_name == 'SUMMARY':
                        event['summary'] = value.replace('\\,', ',').replace('\\n', ' ').replace('\\;', ';')
                    elif key_name == 'DESCRIPTION':
                        desc = value.replace('\\,', ',').replace('\\n', ' ').replace('\\;', ';').replace('\\N', ' ')
                        desc = ' '.join(desc.split())
                        event['description'] = desc
                    elif key_name == 'LOCATION':
                        event['location'] = value.replace('\\,', ',').replace('\\n', ' ')
                    elif key_name == 'ATTENDEE':
                        name = None
                        for part in key_parts[1:]:
                            if part.startswith('CN='):
                                name = part[3:].strip('"')
                                break
                        if not name and value.startswith('mailto:'):
                            name = value[7:].split('@')[0]
                        if name and name not in event['attendees']:
                            event['attendees'].append(name)
                    elif key_name == 'ORGANIZER':
                        name = None
                        for part in key_parts[1:]:
                            if part.startswith('CN='):
                                name = part[3:].strip('"')
                                break
                        if name:
                            event['organizer'] = name
                    elif key_name in ('DTSTART', 'DTEND'):
                        dt = self._parse_ics_datetime(value, key_parts)
                        if dt:
                            if key_name == 'DTSTART':
                                event['start'] = dt
                                event['all_day'] = len(value) == 8
                            else:
                                event['end'] = dt
        
        return events
    
    def _parse_ics_datetime(self, value, key_parts):
        try:
            value = value.replace('Z', '')
            
            if len(value) == 8:
                return datetime.strptime(value, '%Y%m%d')
            elif len(value) >= 15:
                return datetime.strptime(value[:15], '%Y%m%dT%H%M%S')
            else:
                return None
        except:
            return None
    
    def stop(self):
        self.running = False

class DashboardAnimation:
    
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.is_portrait = height > width  # Detect portrait mode
        self.time = 0.0
        self.initialized = False
        self.clock = pygame.time.Clock()
        self.clock.tick()
        
        self.show_time = show_time
        self.config = DashboardConfig()
        self.ampm_format = CONFIG['UI']['ampm_format']
        
        self.lang = self.config.LANGUAGE
        self.labels = UI_LABELS.get(self.lang, UI_LABELS["en"])
        self.weather_desc = WEATHER_DESCRIPTIONS.get(self.lang, WEATHER_DESCRIPTIONS["en"])
        self.weather_abbrev = WEATHER_ABBREV.get(self.lang, WEATHER_ABBREV["en"])
        
        ini_quotes = self.config.get_quotes(self.lang)
        if ini_quotes:
            self.quotes_list = ini_quotes
        else:
            self.quotes_list = QUOTES.get(self.lang, QUOTES["en"])
        
        self.data_fetcher = DataFetcher(self.config)
        
        self.fonts = {}
        self.text_textures = {}
        
        self.news_offset = 0
        self.news_scroll_timer = 0
        self.quote_index = random.randint(0, max(1, len(self.quotes_list)) - 1)
        self.quote_timer = 0
        
        self.bg_color = (0.05, 0.05, 0.08)
        self.text_color = (0.9, 0.9, 0.95)
        self.accent_color = (0.3, 0.6, 0.9)
        self.dim_color = (0.5, 0.5, 0.6)
        
        self.panels = {}
        
        self.feed_fbo = None
        self.feed_texture = None
        self.feed_surface = None
        
        self.feed_active = "news"
        self.feed_switch_time = None
        self.news_last_cycle = 0
        self.news_cycle_complete = False
        self.calendar_cycles = 0
        self.calendar_last_cycle = 0
        self.news_start_time = None
        self.calendar_start_time = None
        self.feed_startup_grace = True
        self.news_first_render = True
        self.calendar_first_render = True
    
    def initialize(self):
        if self.initialized:
            return
        
        # For portrait mode, use dimensions directly; for landscape, swap for rotation
        if self.is_portrait:
            self.layout_width = self.width
            self.layout_height = self.height
        else:
            self.layout_width = self.height
            self.layout_height = self.width
        
        glClearColor(*self.bg_color, 1.0)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        pygame.font.init()
        
        import os
        module_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(module_dir, "AlteHaasGroteskBold.ttf")
        
        try:
            self.fonts['large'] = pygame.font.Font(font_path, 72)
            self.fonts['medium'] = pygame.font.Font(font_path, 36)
            self.fonts['small'] = pygame.font.Font(font_path, 24)
            self.fonts['tiny'] = pygame.font.Font(font_path, 18)
            self.fonts['icon'] = pygame.font.Font(font_path, 48)
        except:
            self.fonts['large'] = pygame.font.Font(None, 72)
            self.fonts['medium'] = pygame.font.Font(None, 36)
            self.fonts['small'] = pygame.font.Font(None, 24)
            self.fonts['tiny'] = pygame.font.Font(None, 18)
            self.fonts['icon'] = pygame.font.Font(None, 48)
        
        margin = 25
        panel_width = self.layout_width - margin * 2
        
        y_pos = margin
        
        self.panels = {
            'clock': {'x': margin, 'y': y_pos, 'w': panel_width, 'h': 80},
        }
        y_pos += 90
        
        self.panels['weather'] = {'x': margin, 'y': y_pos, 'w': panel_width, 'h': 150}
        y_pos += 160
        
        self.panels['forecast'] = {'x': margin, 'y': y_pos, 'w': panel_width, 'h': 130}
        y_pos += 140
        
        self.panels['sun_moon'] = {'x': margin, 'y': y_pos, 'w': panel_width, 'h': 80}
        y_pos += 90
        
        quote_height = 70
        self.panels['quote'] = {'x': margin, 'y': self.layout_height - margin - quote_height, 'w': panel_width, 'h': quote_height}
        
        news_top = y_pos
        news_bottom = self.layout_height - margin - quote_height - 15
        news_height = max(1, news_bottom - news_top)  # Ensure at least 1 pixel
        self.panels['news'] = {'x': margin, 'y': news_top, 'w': panel_width, 'h': news_height}
        
        self.feed_surface_width = max(1, int(panel_width))
        self.feed_surface_height = max(1, int(news_height))
        
        self.initialized = True
    
    def _create_text_texture(self, text, font_name, color):
        font = self.fonts.get(font_name, self.fonts['small'])
        
        try:
            text_surface = font.render(text, True, 
                                       (int(color[0]*255), int(color[1]*255), int(color[2]*255)))
        except:
            text_surface = self.fonts['small'].render("?", True,
                                                      (int(color[0]*255), int(color[1]*255), int(color[2]*255)))
        
        text_data = pygame.image.tostring(text_surface, "RGBA", True)
        width, height = text_surface.get_size()
        
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        
        return texture_id, width, height
    
    def _draw_text(self, text, x, y, font_name='small', color=None, center=False, alpha=1.0):
        if color is None:
            color = self.text_color
        
        if alpha <= 0:
            return 0, 0
        
        tex_id, width, height = self._create_text_texture(text, font_name, color)
        
        if center:
            x = x - width // 2
        
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glColor4f(1.0, 1.0, 1.0, alpha)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y + height)
        glTexCoord2f(1, 0); glVertex2f(x + width, y + height)
        glTexCoord2f(1, 1); glVertex2f(x + width, y)
        glTexCoord2f(0, 1); glVertex2f(x, y)
        glEnd()
        
        glDeleteTextures([tex_id])
        
        return width, height
    
    def _draw_rect(self, x, y, w, h, color, alpha=0.3):
        glDisable(GL_TEXTURE_2D)
        glColor4f(color[0], color[1], color[2], alpha)
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()
    
    def _draw_line(self, x1, y1, x2, y2, color, alpha=0.5):
        glDisable(GL_TEXTURE_2D)
        glColor4f(color[0], color[1], color[2], alpha)
        glBegin(GL_LINES)
        glVertex2f(x1, y1)
        glVertex2f(x2, y2)
        glEnd()
    
    def _init_background_animation(self):
        self.ribbons = []
        ribbon_configs = [
            {'y_pct': 0.12, 'alpha': 0.08, 'thick': 40, 'amp_mult': 0.9},
            {'y_pct': 0.22, 'alpha': 0.10, 'thick': 55, 'amp_mult': 1.3},
            {'y_pct': 0.32, 'alpha': 0.06, 'thick': 35, 'amp_mult': 0.7},
            {'y_pct': 0.42, 'alpha': 0.12, 'thick': 60, 'amp_mult': 1.5},
            {'y_pct': 0.52, 'alpha': 0.07, 'thick': 45, 'amp_mult': 1.1},
            {'y_pct': 0.62, 'alpha': 0.09, 'thick': 50, 'amp_mult': 1.4},
            {'y_pct': 0.72, 'alpha': 0.08, 'thick': 55, 'amp_mult': 0.85},
            {'y_pct': 0.82, 'alpha': 0.11, 'thick': 48, 'amp_mult': 1.2},
            {'y_pct': 0.90, 'alpha': 0.06, 'thick': 38, 'amp_mult': 0.8},
        ]
        
        for i, cfg in enumerate(ribbon_configs):
            self.ribbons.append({
                'y_base': self.layout_height * cfg['y_pct'],
                'amplitude1': 70 * cfg['amp_mult'],
                'amplitude2': 45 * cfg['amp_mult'],
                'amplitude3': 25 * cfg['amp_mult'],
                'amp_vary_speed': 0.012 + random.random() * 0.015,
                'amp_vary_phase': random.random() * 6.28,
                'amp_vary_range': 0.3 + random.random() * 0.4,
                'freq1': 0.007 + (i % 4) * 0.001,
                'freq2': 0.0035 + (i % 3) * 0.0005,
                'freq3': 0.002,
                'osc_speed1': 0.035 + (i % 5) * 0.006,
                'osc_speed2': 0.025 + (i % 4) * 0.005,
                'osc_speed3': 0.02 + (i % 3) * 0.004,
                'phase': i * 0.7,
                'alpha_base': cfg['alpha'],
                'alpha_speed': 0.015 + random.random() * 0.025,
                'alpha_phase': random.random() * 6.28,
                'alpha_range': 0.4 + random.random() * 0.3,
                'thickness_base': cfg['thick'],
                'thickness_speed1': 0.025 + random.random() * 0.02,
                'thickness_speed2': 0.018 + random.random() * 0.015,
                'thickness_phase': random.random() * 6.28,
                'color_speed': 0.02 + random.random() * 0.015,
                'color_freq': 0.004 + random.random() * 0.002,
                'color_phase': random.random() * 6.28
            })
    
    def _render_background_animation(self):
        if not hasattr(self, 'ribbons'):
            self._init_background_animation()
        
        glDisable(GL_TEXTURE_2D)
        glShadeModel(GL_SMOOTH)
        
        for ribbon in self.ribbons:
            points = []
            num_points = int(self.layout_width / 2) + 1
            
            osc1 = math.sin(self.time * ribbon['osc_speed1'])
            osc2 = math.sin(self.time * ribbon['osc_speed2'] + 0.5)
            osc3 = math.sin(self.time * ribbon['osc_speed3'] + 1.0)
            
            amp_pulse = 0.5 + 0.5 * math.sin(self.time * ribbon['amp_vary_speed'] + ribbon['amp_vary_phase'])
            amp_mult = (1 - ribbon['amp_vary_range']) + ribbon['amp_vary_range'] * amp_pulse
            
            alpha_pulse = 0.5 + 0.5 * math.sin(self.time * ribbon['alpha_speed'] + ribbon['alpha_phase'])
            ribbon_alpha = ribbon['alpha_base'] * ((1 - ribbon['alpha_range']) + ribbon['alpha_range'] * alpha_pulse)
            
            color_time = self.time * ribbon['color_speed'] * 100
            
            for i in range(num_points):
                x = i * 2
                
                wave1 = math.sin(x * ribbon['freq1'] + ribbon['phase']) * ribbon['amplitude1'] * osc1 * amp_mult
                wave2 = math.sin(x * ribbon['freq2'] + ribbon['phase'] * 1.3) * ribbon['amplitude2'] * osc2 * amp_mult
                wave3 = math.sin(x * ribbon['freq3'] + ribbon['phase'] * 0.7) * ribbon['amplitude3'] * osc3 * amp_mult
                
                y = ribbon['y_base'] + wave1 + wave2 + wave3
                
                thick_t1 = self.time * ribbon['thickness_speed1'] * 100
                thick_t2 = self.time * ribbon['thickness_speed2'] * 100
                thickness_wave = 0.6 + 0.6 * math.sin((x - thick_t1) * 0.008 + ribbon['thickness_phase'])
                thickness_wave2 = 0.7 + 0.5 * math.sin((x - thick_t2) * 0.004 + ribbon['thickness_phase'] * 1.5)
                
                thickness = ribbon['thickness_base'] * thickness_wave * thickness_wave2
                thickness = max(thickness, ribbon['thickness_base'] * 0.4)
                
                blue_amount = 0.5 + 0.5 * math.sin((x - color_time) * ribbon['color_freq'] + ribbon['color_phase'])
                blue_amount *= 0.5 + 0.5 * math.sin((x - color_time * 0.7) * ribbon['color_freq'] * 0.5 + ribbon['color_phase'] * 1.3)
                
                points.append((x, y, thickness, blue_amount))
            
            glBegin(GL_QUAD_STRIP)
            for x, y, thick, blue_amt in points:
                r = 0.70 - blue_amt * 0.25
                g = 0.75 + blue_amt * 0.10
                b = 0.80 + blue_amt * 0.20
                glColor4f(r, g, b, 0)
                glVertex2f(x, y - thick * 1.3)
                glColor4f(r + 0.05, g + 0.04, b + 0.03, ribbon_alpha * 0.4)
                glVertex2f(x, y - thick * 0.5)
            glEnd()
            
            glBegin(GL_QUAD_STRIP)
            for x, y, thick, blue_amt in points:
                r = 0.70 - blue_amt * 0.25
                g = 0.75 + blue_amt * 0.10
                b = 0.80 + blue_amt * 0.20
                alpha = ribbon_alpha
                glColor4f(r + 0.05, g + 0.04, b + 0.03, alpha * 0.4)
                glVertex2f(x, y - thick * 0.5)
                glColor4f(r + 0.25, g + 0.20, b + 0.15, alpha)
                glVertex2f(x, y - thick * 0.05)
            glEnd()
            
            glBegin(GL_QUAD_STRIP)
            for x, y, thick, blue_amt in points:
                r = 0.70 - blue_amt * 0.25
                g = 0.75 + blue_amt * 0.10
                b = 0.80 + blue_amt * 0.20
                alpha = ribbon_alpha
                glColor4f(r + 0.25, g + 0.20, b + 0.15, alpha)
                glVertex2f(x, y - thick * 0.05)
                glColor4f(r + 0.18, g + 0.14, b + 0.10, alpha * 0.55)
                glVertex2f(x, y + thick * 0.35)
            glEnd()
            
            glBegin(GL_QUAD_STRIP)
            for x, y, thick, blue_amt in points:
                r = 0.70 - blue_amt * 0.25
                g = 0.75 + blue_amt * 0.10
                b = 0.80 + blue_amt * 0.20
                alpha = ribbon_alpha
                glColor4f(r + 0.18, g + 0.14, b + 0.10, alpha * 0.55)
                glVertex2f(x, y + thick * 0.35)
                glColor4f(r, g, b, 0)
                glVertex2f(x, y + thick * 0.7)
            glEnd()
    
    def _create_feed_surface(self, width, height):
        # Ensure minimum dimensions for pygame Surface
        width = max(1, int(width))
        height = max(1, int(height))
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))
        return surface
    
    def _draw_text_to_surface(self, surface, text, x, y, font_name, color):
        if y < -50 or y > surface.get_height() + 50:
            return
        font = self.fonts.get(font_name, self.fonts['small'])
        try:
            text_surf = font.render(text, True, (int(color[0]*255), int(color[1]*255), int(color[2]*255)))
            surface.blit(text_surf, (int(x), int(y)))
        except:
            pass
    
    def _draw_line_to_surface(self, surface, x1, y1, x2, y2, color, alpha=0.5):
        if y1 < -10 or y1 > surface.get_height() + 10:
            return
        pygame.draw.line(surface, (int(color[0]*255), int(color[1]*255), int(color[2]*255), int(alpha*255)), (int(x1), int(y1)), (int(x2), int(y2)), 1)
    
    def _draw_surface_with_fade(self, surface, x, y, fade_top=40, fade_bottom=50, scroll_offset=0):
        width, height = surface.get_size()
        
        if HAS_NUMPY:
            arr = pygame.surfarray.pixels_alpha(surface)
            
            effective_fade_top = min(fade_top, scroll_offset) if scroll_offset > 0 else 0
            for row in range(min(int(effective_fade_top), height)):
                if effective_fade_top > 0:
                    alpha_mult = row / effective_fade_top
                    arr[:, row] = (arr[:, row] * alpha_mult).astype('uint8')
            
            for row in range(min(int(fade_bottom), height)):
                alpha_mult = row / fade_bottom
                screen_row = height - 1 - row
                if screen_row >= 0 and screen_row < height:
                    arr[:, screen_row] = (arr[:, screen_row] * alpha_mult).astype('uint8')
            
            del arr
        
        try:
            texture_data = pygame.image.tostring(surface, "RGBA", True)
            
            tex_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
            
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, tex_id)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            
            glBegin(GL_QUADS)
            glTexCoord2f(0, 1); glVertex2f(x, y)
            glTexCoord2f(1, 1); glVertex2f(x + width, y)
            glTexCoord2f(1, 0); glVertex2f(x + width, y + height)
            glTexCoord2f(0, 0); glVertex2f(x, y + height)
            glEnd()
            
            glDeleteTextures([tex_id])
        except:
            pass
    
    def _render_clock(self):
        panel = self.panels['clock']
        now = datetime.now()
        
        if self.ampm_format:
            time_str = now.strftime("%I:%M")
            ampm_str = now.strftime("%p")
        else:
            time_str = now.strftime("%H:%M")
            ampm_str = None
        
        self._draw_text(time_str, panel['x'], panel['y'], 'large', self.text_color)
        
        sec_str = now.strftime(":%S")
        self._draw_text(sec_str, panel['x'] + 190, panel['y'] + 45, 'small', self.dim_color)
        
        if ampm_str:
            self._draw_text(ampm_str, panel['x'] + 190, panel['y'] + 10, 'small', self.dim_color)
        
        date_str = format_date_localized(now, self.lang, self.labels)
        
        self._draw_text(date_str, panel['x'] + 270, panel['y'] + 10, 'small', self.dim_color)
        self._draw_text(self.config.LOCATION_NAME, panel['x'] + 270, panel['y'] + 45, 'small', self.dim_color)
    
    def _render_weather(self):
        panel = self.panels['weather']
        weather = self.data_fetcher.get_weather()
        
        self._draw_text(self.labels["current_weather"], panel['x'], panel['y'], 'tiny', self.accent_color)
        self._draw_line(panel['x'], panel['y'] + 25, panel['x'] + panel['w'], panel['y'] + 25, self.accent_color, 0.3)
        
        if weather:
            temp = weather.get('temperature_2m', '--')
            unit = "F" if self.config.TEMP_UNIT == "fahrenheit" else "C"
            temp_str = f"{temp:.1f}" if isinstance(temp, (int, float)) else f"{temp}"
            self._draw_text(temp_str, panel['x'], panel['y'] + 35, 'large', self.text_color)
            self._draw_text(f"°{unit}", panel['x'] + 165, panel['y'] + 45, 'small', self.dim_color)
            
            weather_code = weather.get('weather_code', 0)
            condition = self.weather_desc.get(weather_code, "?")
            
            right_x = panel['x'] + 270
            self._draw_text(condition, right_x, panel['y'] + 40, 'small', self.text_color)
            
            feels_like = weather.get('apparent_temperature', '--')
            humidity = weather.get('relative_humidity_2m', '--')
            wind = weather.get('wind_speed_10m', '--')
            
            if isinstance(feels_like, (int, float)):
                self._draw_text(f"{self.labels['feels']}: {feels_like:.1f}°{unit}", right_x, panel['y'] + 70, 'tiny', self.dim_color)
            self._draw_text(f"{self.labels['humidity']}: {humidity}%", right_x, panel['y'] + 95, 'tiny', self.dim_color)
            self._draw_text(f"{self.labels['wind']}: {wind} km/h", right_x, panel['y'] + 120, 'tiny', self.dim_color)
        else:
            self._draw_text(self.labels["loading_weather"], panel['x'], panel['y'] + 60, 'small', self.dim_color)
    
    def _render_forecast(self):
        panel = self.panels['forecast']
        forecast = self.data_fetcher.get_forecast()
        
        self._draw_text(self.labels["forecast"], panel['x'], panel['y'], 'tiny', self.accent_color)
        self._draw_line(panel['x'], panel['y'] + 25, panel['x'] + panel['w'], panel['y'] + 25, self.accent_color, 0.3)
        
        if forecast and 'time' in forecast:
            times = forecast.get('time', [])
            maxs = forecast.get('temperature_2m_max', [])
            mins = forecast.get('temperature_2m_min', [])
            codes = forecast.get('weather_code', [])
            precip = forecast.get('precipitation_probability_max', [])
            
            unit = "F" if self.config.TEMP_UNIT == "fahrenheit" else "C"
            num_days = min(len(times), 5)
            day_width = panel['w'] // num_days
            
            for i in range(num_days):
                t, hi, lo, code = times[i], maxs[i], mins[i], codes[i]
                rain = precip[i] if i < len(precip) else 0
                
                x = panel['x'] + i * day_width
                y = panel['y'] + 35
                
                if i == 0:
                    day_name = self.labels["today"]
                else:
                    try:
                        day = datetime.strptime(t, "%Y-%m-%d")
                        day_name = self.labels["days"][day.weekday()]
                    except:
                        day_name = t[:3]
                
                self._draw_text(day_name, x + 5, y, 'tiny', self.text_color)
                
                short_cond = self.weather_abbrev.get(code, "?")
                self._draw_text(short_cond, x + 5, y + 22, 'tiny', self.dim_color)
                
                hi_str = f"{hi:.0f}" if isinstance(hi, (int, float)) else str(hi)
                lo_str = f"{lo:.0f}" if isinstance(lo, (int, float)) else str(lo)
                self._draw_text(f"{hi_str}/{lo_str}", x + 5, y + 44, 'tiny', self.text_color)
                
                if rain and rain > 0:
                    self._draw_text(f"{rain}%", x + 5, y + 66, 'tiny', self.accent_color)
        else:
            self._draw_text(self.labels["loading"], panel['x'], panel['y'] + 50, 'small', self.dim_color)
    
    def _draw_sun_icon(self, cx, cy, radius, rising=True):
        if rising:
            sun_color = (1.0, 0.7, 0.2)
        else:
            sun_color = (0.9, 0.4, 0.2)
        
        horizon_y = cy + 5
        
        glColor4f(sun_color[0], sun_color[1], sun_color[2], 1.0)
        ray_length = 8
        ray_start = radius + 3
        for i in range(5):
            angle = math.pi * (0.2 + i * 0.15)
            x1 = cx + ray_start * math.cos(angle)
            y1 = cy - ray_start * math.sin(angle)
            x2 = cx + (ray_start + ray_length) * math.cos(angle)
            y2 = cy - (ray_start + ray_length) * math.sin(angle)
            glLineWidth(2.0)
            glBegin(GL_LINES)
            glVertex2f(x1, y1)
            glVertex2f(x2, y2)
            glEnd()
        
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(cx, horizon_y)
        segments = 20
        for i in range(segments + 1):
            angle = math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = horizon_y - radius * math.sin(angle)
            glVertex2f(x, y)
        glEnd()
        
        glColor4f(sun_color[0], sun_color[1], sun_color[2], 0.8)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glVertex2f(cx - radius - 10, horizon_y)
        glVertex2f(cx + radius + 10, horizon_y)
        glEnd()
        
        arrow_y = horizon_y + 12
        arrow_size = 6
        
        if rising:
            glBegin(GL_TRIANGLES)
            glVertex2f(cx, horizon_y + 5)
            glVertex2f(cx - arrow_size, arrow_y)
            glVertex2f(cx + arrow_size, arrow_y)
            glEnd()
        else:
            glBegin(GL_TRIANGLES)
            glVertex2f(cx, arrow_y + 5)
            glVertex2f(cx - arrow_size, horizon_y + 5)
            glVertex2f(cx + arrow_size, horizon_y + 5)
            glEnd()
        
        glLineWidth(1.0)
    
    def _draw_moon_icon(self, cx, cy, radius, phase_index, illumination):
        
        glColor4f(0.2, 0.2, 0.25, 1.0)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(cx, cy)
        for i in range(33):
            angle = 2 * math.pi * i / 32
            glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        glEnd()
        
        glColor4f(0.95, 0.95, 0.85, 1.0)
        
        if phase_index == 0:
            glColor4f(0.4, 0.4, 0.45, 1.0)
            glBegin(GL_LINE_LOOP)
            for i in range(32):
                angle = 2 * math.pi * i / 32
                glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            glEnd()
            
        elif phase_index == 4:
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(cx, cy)
            for i in range(33):
                angle = 2 * math.pi * i / 32
                glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            glEnd()
            
        elif phase_index in [1, 2, 3]:
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(cx, cy)
            for i in range(17):
                angle = -math.pi/2 + math.pi * i / 16
                glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            if phase_index == 1:
                curve = 0.6
            elif phase_index == 2:
                curve = 0.0
            else:
                curve = -0.6
            for i in range(16, -1, -1):
                angle = -math.pi/2 + math.pi * i / 16
                glVertex2f(cx + radius * curve * math.cos(angle), cy + radius * math.sin(angle))
            glEnd()
            
        elif phase_index in [5, 6, 7]:
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(cx, cy)
            for i in range(17):
                angle = math.pi/2 + math.pi * i / 16
                glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            if phase_index == 7:
                curve = 0.6
            elif phase_index == 6:
                curve = 0.0
            else:
                curve = -0.6
            for i in range(16, -1, -1):
                angle = math.pi/2 + math.pi * i / 16
                glVertex2f(cx + radius * curve * math.cos(angle), cy + radius * math.sin(angle))
            glEnd()
    
    def _render_sun_moon(self):
        panel = self.panels['sun_moon']
        forecast = self.data_fetcher.get_forecast()
        
        sunrise_str = "--:--"
        sunset_str = "--:--"
        
        if forecast and 'sunrise' in forecast and 'sunset' in forecast:
            try:
                sunrise_list = forecast.get('sunrise', [])
                sunset_list = forecast.get('sunset', [])
                if sunrise_list and sunset_list:
                    sunrise_dt = datetime.strptime(sunrise_list[0], "%Y-%m-%dT%H:%M")
                    sunset_dt = datetime.strptime(sunset_list[0], "%Y-%m-%dT%H:%M")
                    
                    if self.ampm_format:
                        sunrise_str = sunrise_dt.strftime("%I:%M %p")
                        sunset_str = sunset_dt.strftime("%I:%M %p")
                    else:
                        sunrise_str = sunrise_dt.strftime("%H:%M")
                        sunset_str = sunset_dt.strftime("%H:%M")
            except Exception as e:
                pass
        
        phase_index, illumination, phase_angle = calculate_moon_phase()
        phase_name = self.labels["moon_phases"][phase_index]
        
        section_width = panel['w'] // 3
        
        sec1_x = panel['x']
        icon_x = sec1_x + 25
        text_x = sec1_x + 55
        self._draw_sun_icon(icon_x, panel['y'] + 40, 12, rising=True)
        self._draw_text(self.labels["sunrise"], text_x, panel['y'] + 20, 'tiny', self.dim_color)
        self._draw_text(sunrise_str, text_x, panel['y'] + 42, 'small', self.text_color)
        
        sec2_x = panel['x'] + section_width
        icon_x = sec2_x + 25
        text_x = sec2_x + 55
        self._draw_sun_icon(icon_x, panel['y'] + 40, 12, rising=False)
        self._draw_text(self.labels["sunset"], text_x, panel['y'] + 20, 'tiny', self.dim_color)
        self._draw_text(sunset_str, text_x, panel['y'] + 42, 'small', self.text_color)
        
        sec3_x = panel['x'] + section_width * 2
        icon_x = sec3_x + 25
        text_x = sec3_x + 55
        self._draw_moon_icon(icon_x, panel['y'] + 40, 16, phase_index, illumination)
        self._draw_text(phase_name, text_x, panel['y'] + 25, 'tiny', self.text_color)
        illum_str = f"{int(illumination * 100)}%"
        self._draw_text(illum_str, text_x, panel['y'] + 48, 'tiny', self.dim_color)

    def _render_news(self):
        panel = self.panels['news']
        news = self.data_fetcher.get_news(self.config.MAX_NEWS_ITEMS)
        
        self._draw_text(self.labels["news"], panel['x'], panel['y'], 'tiny', self.accent_color)
        self._draw_line(panel['x'], panel['y'] + 25, panel['x'] + panel['w'], panel['y'] + 25, self.accent_color, 0.3)
        
        if not news:
            self._draw_text(self.labels["loading_news"], panel['x'], panel['y'] + 60, 'small', self.dim_color)
            return
        
        content_height = max(1, int(panel['h'] - 40))
        surface_width = max(1, int(panel['w']))
        
        fade_top = 35
        fade_bottom = 45
        
        text_width = 45
        items_layout = []
        
        for item in news:
            title_lines = self._wrap_text(item['title'], text_width)[:2]
            desc = item.get('description', '')
            desc_lines = self._wrap_text(desc, text_width)[:8] if desc else []
            
            item_height = 22 + (28 * len(title_lines)) + 5 + (20 * len(desc_lines)) + 20
            items_layout.append({
                'item': item,
                'title_lines': title_lines,
                'desc_lines': desc_lines,
                'height': item_height
            })
        
        total_content_height = sum(it['height'] for it in items_layout)
        
        if self.news_first_render:
            self.news_start_time = self.time
            self.news_last_cycle = 0
            self.news_first_render = False
        
        news_elapsed = self.time - self.news_start_time
        
        if total_content_height > content_height:
            scroll_range = total_content_height - content_height + 50
            scroll_speed = self.config.SCROLL_SPEED
            scroll_time = scroll_range / scroll_speed
            pause_before = 15
            pause_after = 15
            total_cycle = pause_before + scroll_time + pause_after
            
            current_cycle = int(news_elapsed / total_cycle)
            if current_cycle > self.news_last_cycle:
                self.news_cycle_complete = True
            self.news_last_cycle = current_cycle
            
            cycle_position = (news_elapsed % total_cycle)
            if cycle_position < pause_before:
                scroll_offset = 0
            elif cycle_position < pause_before + scroll_time:
                scroll_offset = (cycle_position - pause_before) * scroll_speed
            else:
                scroll_offset = scroll_range
            
            scroll_offset = min(scroll_offset, scroll_range)
        else:
            total_cycle = 30
            current_cycle = int(news_elapsed / total_cycle)
            if current_cycle > self.news_last_cycle:
                self.news_cycle_complete = True
            self.news_last_cycle = current_cycle
            scroll_offset = 0
        
        feed_surface = self._create_feed_surface(surface_width, content_height)
        
        y_pos = -scroll_offset
        
        for layout in items_layout:
            item = layout['item']
            item_height = layout['height']
            
            if y_pos + item_height < -20:
                y_pos += item_height
                continue
            if y_pos > content_height + 20:
                break
            
            cur_y = y_pos
            
            self._draw_text_to_surface(feed_surface, item['source'], 0, cur_y, 'tiny', self.accent_color)
            cur_y += 22
            
            for line in layout['title_lines']:
                self._draw_text_to_surface(feed_surface, line, 0, cur_y, 'small', self.text_color)
                cur_y += 28
            
            if layout['desc_lines']:
                cur_y += 5
                for line in layout['desc_lines']:
                    self._draw_text_to_surface(feed_surface, line, 0, cur_y, 'tiny', self.dim_color)
                    cur_y += 20
            
            cur_y += 5
            self._draw_line_to_surface(feed_surface, 0, cur_y, surface_width - 20, cur_y, self.dim_color, 0.2)
            
            y_pos += item_height
        
        self._draw_surface_with_fade(feed_surface, panel['x'], panel['y'] + 35, fade_top, fade_bottom, scroll_offset)
    
    def _render_calendar(self):
        panel = self.panels['news']
        events = self.data_fetcher.get_calendar()
        
        self._draw_text(self.labels["calendar"], panel['x'], panel['y'], 'tiny', self.accent_color)
        self._draw_line(panel['x'], panel['y'] + 25, panel['x'] + panel['w'], panel['y'] + 25, self.accent_color, 0.3)
        
        if not events:
            if not self.config.CALENDAR_ICS_URLS:
                self._draw_text("No calendar URL configured", panel['x'], panel['y'] + 60, 'small', self.dim_color)
                if self.feed_switch_time is None and self.config.FEED_MODE == "alternate":
                    self.feed_switch_time = self.time + 10
            elif self.data_fetcher.is_calendar_loaded():
                no_events_msg = self.labels["no_events"].format(days=self.config.CALENDAR_DAYS_AHEAD)
                self._draw_text(no_events_msg, panel['x'], panel['y'] + 60, 'small', self.dim_color)
                if self.feed_switch_time is None and self.config.FEED_MODE == "alternate":
                    self.feed_switch_time = self.time + 10
            else:
                self._draw_text(self.labels["loading_calendar"], panel['x'], panel['y'] + 60, 'small', self.dim_color)
            return
        
        content_height = max(1, int(panel['h'] - 40))
        surface_width = max(1, int(panel['w']))
        
        fade_top = 35
        fade_bottom = 45
        
        text_width = 45
        items_layout = []
        now = datetime.now()
        
        for event in events:
            start = event.get('start')
            end = event.get('end')
            summary = event.get('summary', 'No title')
            location = event.get('location', '')
            description = event.get('description', '')
            duration = event.get('duration', '')
            attendees = event.get('attendees', [])
            organizer = event.get('organizer', '')
            all_day = event.get('all_day', False)
            
            is_ongoing = False
            if start and end and not all_day:
                if start <= now <= end:
                    is_ongoing = True
            
            if start.date() == now.date():
                date_str = self.labels.get("today", "Today")
            elif start.date() == (now + timedelta(days=1)).date():
                date_str = self.labels.get("tomorrow", "Tomorrow")
            else:
                day_names = self.labels.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
                months = self.labels.get("months", ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
                date_str = f"{day_names[start.weekday()]} {start.day} {months[start.month - 1][:3]}"
            
            if all_day:
                time_str = self.labels.get("all_day", "All day")
            elif is_ongoing:
                if self.ampm_format:
                    time_str = f"{start.strftime('%I:%M %p')} - {self.labels.get('ongoing', 'Ongoing')}"
                else:
                    time_str = f"{start.strftime('%H:%M')} - {self.labels.get('ongoing', 'Ongoing')}"
            else:
                if self.ampm_format:
                    time_str = start.strftime("%I:%M %p")
                else:
                    time_str = start.strftime("%H:%M")
                if duration:
                    time_str = f"{time_str} ({duration})"
            
            all_title_lines = self._wrap_text(summary, text_width)
            title_lines = all_title_lines[:2]
            if len(all_title_lines) > 2 and title_lines:
                title_lines[-1] = title_lines[-1].rstrip() + " (...)"
            all_desc_lines = self._wrap_text(description, text_width) if description else []
            desc_lines = all_desc_lines[:3]
            if len(all_desc_lines) > 3 and desc_lines:
                desc_lines[-1] = desc_lines[-1].rstrip() + " (...)"
            all_loc_lines = self._wrap_text(location, text_width) if location else []
            loc_lines = all_loc_lines[:1]
            if len(all_loc_lines) > 1 and loc_lines:
                loc_lines[-1] = loc_lines[-1].rstrip() + " (...)"
            
            people = []
            if organizer:
                people.append(organizer)
            for att in attendees[:5]:
                if att not in people:
                    people.append(att)
            people_str = ", ".join(people[:4])
            if len(people) > 4:
                people_str += f" +{len(people) - 4}"
            all_people_lines = self._wrap_text(people_str, text_width) if people_str else []
            people_lines = all_people_lines[:1]
            if len(all_people_lines) > 1 and people_lines:
                people_lines[-1] = people_lines[-1].rstrip() + " (...)"
            
            item_height = 22 + (28 * len(title_lines)) + (20 * len(desc_lines)) + (20 * len(loc_lines)) + (20 * len(people_lines)) + 20
            items_layout.append({
                'date_str': date_str,
                'time_str': time_str,
                'title_lines': title_lines,
                'desc_lines': desc_lines,
                'loc_lines': loc_lines,
                'people_lines': people_lines,
                'height': item_height,
                'all_day': all_day
            })
        
        total_content_height = sum(it['height'] for it in items_layout)
        
        if self.calendar_first_render:
            self.calendar_start_time = self.time
            self.calendar_last_cycle = 0
            self.calendar_first_render = False
            scroll_offset = 0
            calendar_elapsed = 0
        else:
            calendar_elapsed = self.time - self.calendar_start_time
            
            if total_content_height > content_height:
                scroll_range = total_content_height - content_height + 50
                scroll_speed = self.config.SCROLL_SPEED
                scroll_time = scroll_range / scroll_speed
                pause_before = 15
                pause_after = 3
                total_cycle = pause_before + scroll_time + pause_after
                
                current_cycle = int(calendar_elapsed / total_cycle)
                if current_cycle > self.calendar_last_cycle:
                    self.calendar_cycles += 1
                self.calendar_last_cycle = current_cycle
                
                cycle_position = (calendar_elapsed % total_cycle)
                if cycle_position < pause_before:
                    scroll_offset = 0
                elif cycle_position < pause_before + scroll_time:
                    scroll_offset = (cycle_position - pause_before) * scroll_speed
                else:
                    scroll_offset = scroll_range
                
                scroll_offset = min(scroll_offset, scroll_range)
            else:
                total_cycle = 20
                current_cycle = int(calendar_elapsed / total_cycle)
                if current_cycle > self.calendar_last_cycle:
                    self.calendar_cycles += 1
                self.calendar_last_cycle = current_cycle
                scroll_offset = 0
        
        feed_surface = self._create_feed_surface(surface_width, content_height)
        
        y_pos = -scroll_offset
        
        for layout in items_layout:
            item_height = layout['height']
            
            if y_pos + item_height < -20:
                y_pos += item_height
                continue
            if y_pos > content_height + 20:
                y_pos += item_height
                continue
            
            cur_y = y_pos
            
            header = f"{layout['date_str']} • {layout['time_str']}"
            self._draw_text_to_surface(feed_surface, header, 0, cur_y, 'tiny', self.accent_color)
            cur_y += 22
            
            for line in layout['title_lines']:
                self._draw_text_to_surface(feed_surface, line, 0, cur_y, 'small', self.text_color)
                cur_y += 28
            
            if layout['desc_lines']:
                for line in layout['desc_lines']:
                    self._draw_text_to_surface(feed_surface, line, 0, cur_y, 'tiny', self.dim_color)
                    cur_y += 20
            
            if layout['people_lines']:
                for line in layout['people_lines']:
                    self._draw_text_to_surface(feed_surface, f"👥 {line}", 0, cur_y, 'tiny', self.dim_color)
                    cur_y += 20
            
            if layout['loc_lines']:
                for line in layout['loc_lines']:
                    self._draw_text_to_surface(feed_surface, f"📍 {line}", 0, cur_y, 'tiny', self.dim_color)
                    cur_y += 20
            
            cur_y += 5
            self._draw_line_to_surface(feed_surface, 0, cur_y, surface_width - 20, cur_y, self.dim_color, 0.2)
            
            y_pos += item_height
        
        self._draw_surface_with_fade(feed_surface, panel['x'], panel['y'] + 35, fade_top, fade_bottom, scroll_offset)
    
    def _render_feed(self):
        mode = self.config.FEED_MODE
        
        if mode == "news":
            self._render_news()
        elif mode == "calendar":
            self._render_calendar()
        elif mode == "alternate":
            if self.feed_startup_grace and self.time > 10:
                self.feed_startup_grace = False
            
            if self.feed_switch_time is not None and self.time >= self.feed_switch_time:
                if self.feed_active == "news":
                    self.feed_active = "calendar"
                    self.calendar_cycles = 0
                    self.calendar_last_cycle = 0
                    self.calendar_start_time = None
                    self.calendar_first_render = True
                else:
                    self.feed_active = "news"
                    self.news_cycle_complete = False
                    self.news_last_cycle = 0
                    self.news_start_time = None
                    self.news_first_render = True
                self.feed_switch_time = None
            
            if self.feed_active == "news":
                self._render_news()
                if self.news_cycle_complete and self.feed_switch_time is None and not self.feed_startup_grace:
                    self.feed_switch_time = self.time + 15
            else:
                self._render_calendar()
                if self.calendar_cycles >= 3 and self.feed_switch_time is None:
                    self.feed_switch_time = self.time + 15
        else:
            self._render_news()
    
    def _draw_surface(self, surface, x, y):
        if surface is None:
            return
        
        try:
            texture_data = pygame.image.tostring(surface, "RGBA", True)
            width, height = surface.get_size()
            
            tex_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
            
            glEnable(GL_TEXTURE_2D)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(x, y + height)
            glTexCoord2f(1, 0); glVertex2f(x + width, y + height)
            glTexCoord2f(1, 1); glVertex2f(x + width, y)
            glTexCoord2f(0, 1); glVertex2f(x, y)
            glEnd()
            
            glDeleteTextures([tex_id])
        except Exception as e:
            pass
    
    def _wrap_text(self, text, max_chars):
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = (current_line + " " + word).strip() if current_line else word
            if len(test_line) <= max_chars:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def _render_quote(self):
        panel = self.panels['quote']
        
        self._draw_rect(panel['x'], panel['y'], panel['w'], panel['h'], self.accent_color, 0.1)
        
        show_joke = False
        if self.config.QUOTE_MODE == "jokes":
            show_joke = True
        elif self.config.QUOTE_MODE == "alternate":
            show_joke = (self.quote_index % 2 == 1)
        
        if show_joke:
            jokes = self.data_fetcher.get_jokes()
            if jokes:
                joke_idx = (self.quote_index // 2) if self.config.QUOTE_MODE == "alternate" else self.quote_index
                joke_text = jokes[joke_idx % len(jokes)]
                
                lines = self._wrap_text(joke_text, 55)
                
                y_offset = panel['y'] + 10
                for line in lines[:3]:
                    self._draw_text(line, panel['x'] + 15, y_offset, 'tiny', self.text_color)
                    y_offset += 20
            else:
                self._render_quote_text(panel)
        else:
            self._render_quote_text(panel)
    
    def _render_quote_text(self, panel):
        quote_idx = (self.quote_index // 2) if self.config.QUOTE_MODE == "alternate" else self.quote_index
        quote_text, quote_author = self.quotes_list[quote_idx % len(self.quotes_list)]
        
        lines = self._wrap_text(quote_text, 55)
        
        y_offset = panel['y'] + 12
        for i, line in enumerate(lines[:2]):
            prefix = '"' if i == 0 else ''
            suffix = '"' if i == len(lines[:2]) - 1 else ''
            self._draw_text(f'{prefix}{line}{suffix}', panel['x'] + 15, y_offset, 'tiny', self.text_color)
            y_offset += 20
        
        self._draw_text(f"- {quote_author}", panel['x'] + panel['w'] - 150, panel['y'] + 50, 'tiny', self.dim_color)
    
    def update(self, delta_time=None):
        if delta_time is None:
            try:
                delta_time = self.clock.get_time() / 1000.0
            except:
                delta_time = 0.033
        
        delta_time = min(delta_time, 0.1)
        
        self.time += delta_time
        
        self.news_scroll_timer += delta_time
        if self.news_scroll_timer > 30:
            self.news_offset = (self.news_offset + 1) % max(1, len(self.data_fetcher.get_news()))
            self.news_scroll_timer = 0
        
        self.quote_timer += delta_time
        rotate_interval = 30 if self.config.QUOTE_MODE == "alternate" else 60
        if self.quote_timer > rotate_interval:
            if self.config.QUOTE_MODE == "alternate":
                max_items = max(len(self.quotes_list), len(self.data_fetcher.get_jokes()) or 1) * 2
                self.quote_index = (self.quote_index + 1) % max(max_items, 20)
            else:
                self.quote_index = (self.quote_index + 1) % len(self.quotes_list)
            self.quote_timer = 0
    
    def render(self):
        if not self.initialized:
            self.initialize()
        
        glClear(GL_COLOR_BUFFER_BIT)
        glLoadIdentity()
        
        # Only apply rotation when in landscape mode (OS doesn't handle rotation)
        if not self.is_portrait:
            glTranslatef(self.width, 0, 0)
            glRotatef(90, 0, 0, 1)
        
        if self.config.BACKGROUND_ANIMATION:
            self._render_background_animation()
        
        if self.config.SHOW_CLOCK:
            self._render_clock()
        
        if self.config.SHOW_WEATHER:
            self._render_weather()
        
        if self.config.SHOW_FORECAST:
            self._render_forecast()
        
        if self.config.SHOW_SUN_MOON:
            self._render_sun_moon()
        
        if self.config.SHOW_NEWS:
            self._render_feed()
        
        if self.config.SHOW_QUOTES:
            self._render_quote()
        
        pygame.display.flip()
        
        try:
            self.clock.tick(30)
        except:
            pass
    
    def reset(self):
        self.time = 0.0
        self.news_offset = 0
        self.news_scroll_timer = 0
        self.quote_timer = 0
        self.news_start_time = None
        self.calendar_start_time = None
        self.feed_switch_time = None
        self.news_cycle_complete = False
        self.news_last_cycle = 0
        self.calendar_cycles = 0
        self.calendar_last_cycle = 0
        self.feed_startup_grace = True
        self.news_first_render = True
        self.calendar_first_render = True
    
    def cleanup(self):
        self.initialized = False
        self.data_fetcher.stop()
        
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glColor4f(1.0, 1.0, 1.0, 1.0)

if __name__ == "__main__":
    pygame.init()
    
    width, height = 800, 480
    pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
    pygame.display.set_caption("Dashboard Screensaver Test")
    
    dashboard = DashboardAnimation(None, width, height)
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
        
        dashboard.update()
        dashboard.render()
    
    dashboard.cleanup()
    pygame.quit()