"""Weather from Open-Meteo (free, no account or key). Sends only a city name, then coordinates."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search?name={name}&count=1"
FORECAST = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max&timezone=auto&forecast_days=2")

# Narrow on purpose: a general question ("what temperature does water boil at?") must not reach this tool.
WANTS_WEATHER = re.compile(r"\b(weather|forecast)\b|\bhava\s+(durumu|nasıl|kaç)", re.I)
NOT_A_CITY = {"bugün", "yarın", "şimdi", "bu", "bugünkü", "yarınki", "today", "tomorrow", "now", "the"}
CITY_EN = re.compile(r"\b(?:in|for|at)\s+([a-zçğıöşü][a-zçğıöşü' .-]*?)(?:\s+(?:today|tomorrow|now|tonight|please))?\s*[?.!]*$", re.I)
CITY_TR = re.compile(r"^([a-zçğıöşü][a-zçğıöşü ]*?)(?:'?(?:da|de|ta|te))?\s+(?:için\s+)?hava\b", re.I)
TOMORROW = re.compile(r"\b(tomorrow|yarın)\b", re.I)
TURKISH = re.compile(r"\bhava\b|\byarın\b|\bbugün\b", re.I)

EN = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
      51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
      71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers",
      82: "heavy showers", 95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail"}
TR = {0: "açık", 1: "çoğunlukla açık", 2: "parçalı bulutlu", 3: "kapalı", 45: "sisli", 48: "sisli",
      51: "hafif çisenti", 53: "çisenti", 55: "yoğun çisenti", 61: "hafif yağmur", 63: "yağmur", 65: "kuvvetli yağmur",
      71: "hafif kar", 73: "kar", 75: "yoğun kar", 80: "sağanak", 81: "sağanak", 82: "şiddetli sağanak",
      95: "gök gürültülü fırtına", 96: "dolulu fırtına", 99: "dolulu fırtına"}


def _http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis-weather"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def find_city(text: str, default: str | None) -> str | None:
    t = text.strip()
    m = CITY_EN.search(t) or CITY_TR.search(t)
    city = m.group(1).strip() if m else None
    return city if city and city.lower() not in NOT_A_CITY else default


def answer(text: str, locate: Callable[[], tuple[float, float] | None] | None = None,
           fetch: Callable[[str], dict] | None = None) -> str | None:
    """The weather for the request, or None if the request is not about weather.

    A city named in the sentence wins; otherwise `locate()` supplies where you are right now.
    """
    if not WANTS_WEATHER.search(text):
        return None
    fetch = fetch or _http_json
    tr = bool(TURKISH.search(text))
    city = find_city(text, None)
    day = 1 if TOMORROW.search(text) else 0
    try:
        if city:
            found = fetch(GEOCODE.format(name=urllib.parse.quote(city))).get("results") or []
            if not found:
                return f"'{city}' şehrini bulamadım." if tr else f"I could not find a city called {city}."
            place = found[0]
        else:
            if locate is None:
                from .location import here as locate
            spot = locate()
            if spot is None:
                return ("Konumunu bulamadım. 'Ankara hava durumu' gibi bir şehir söyleyebilirsin." if tr else
                        "I could not work out where you are. Say 'weather in Ankara' instead.")
            place = {"latitude": spot[0], "longitude": spot[1], "name": None}
        data = fetch(FORECAST.format(lat=place["latitude"], lon=place["longitude"]))
        daily, now = data["daily"], data["current"]
        lo, hi = daily["temperature_2m_min"][day], daily["temperature_2m_max"][day]
        rain = daily["precipitation_probability_max"][day]
        code = now["weather_code"]
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, ValueError):
        return "Hava durumu servisine ulaşamadım." if tr else "I could not reach the weather service."
    name = place.get("name")
    prefix = f"{name}: " if name else ""
    if tr:
        when = "Yarın" if day else "Bugün"
        now_part = "" if day else f"Şu an {now['temperature_2m']:.0f} derece, {TR.get(code, 'değişken')}. "
        return f"{prefix}{now_part}{when} en düşük {lo:.0f}, en yüksek {hi:.0f} derece, yağış ihtimali yüzde {rain}."
    when = "Tomorrow" if day else "Today"
    now_part = "" if day else f"It is {now['temperature_2m']:.0f} degrees, {EN.get(code, 'changing weather')}. "
    return f"{prefix}{now_part}{when} {lo:.0f} to {hi:.0f} degrees, {rain} percent chance of rain."
