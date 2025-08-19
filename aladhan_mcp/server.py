import asyncio
import datetime as dt
import httpx
import json, time

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, JsonContent

ALADHAN_BASE = "https://api.aladhan.com/v1"

server = Server("aladhan-mcp")


def text_json(obj) -> JsonContent:
    return JsonContent(content=obj)


def text_content(text: str) -> TextContent:
    return TextContent(text=text)


_CACHE: dict[str, tuple[float, dict]] = {}
def cache_get(key: str, ttl_s: int = 86400):
    item = _CACHE.get(key)
    if not item: return None
    ts, val = item
    return val if (time.time() - ts) < ttl_s else None
def cache_put(key: str, val: dict): _CACHE[key] = (time.time(), val)

async def get_json(url: str, params: dict | None = None, timeout=15):
    for i in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError:
            if i == 2: raise
            await asyncio.sleep(0.3 * (2 ** i))


@server.tool(
    name="list_calculation_methods",
    description="List Aladhan calculation methods (id -> name, params).",
    inputSchema={
        "type": "object",
        "properties": {},
        "additionalProperties": False
    }
)
async def list_calculation_methods(args: dict):
    cache_key = "methods"
    payload = cache_get(cache_key, ttl_s=86400)
    if not payload:
        payload = await get_json(f"{ALADHAN_BASE}/methods")
        cache_put(cache_key, payload)
    return text_json(payload.get("data", payload))


@server.tool(
    name="convert_gregorian_to_hijri",
    description="Convert Gregorian date to Hijri. Args: date (YYYY-MM-DD).",
    inputSchema={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Gregorian date in YYYY-MM-DD format",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
        },
        "required": ["date"],
        "additionalProperties": False
    }
)
async def convert_gregorian_to_hijri(args: dict):
    date = str(args.get("date") or "").strip()
    if not date:
        raise ValueError("Required: 'date' as YYYY-MM-DD")
    payload = await get_json(f"{ALADHAN_BASE}/gToH", params={"date": date})
    return text_json(payload.get("data", payload))


@server.tool(
    name="convert_hijri_to_gregorian",
    description="Convert Hijri date to Gregorian. Args: date (DD-MM-YYYY).",
    inputSchema={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Hijri date in DD-MM-YYYY format",
                "pattern": "^\\d{2}-\\d{2}-\\d{4}$"
            }
        },
        "required": ["date"],
        "additionalProperties": False
    }
)
async def convert_hijri_to_gregorian(args: dict):
    date = str(args.get("date") or "").strip()
    if not date:
        raise ValueError("Required: 'date' as DD-MM-YYYY")
    payload = await get_json(f"{ALADHAN_BASE}/hToG", params={"date": date})
    return text_json(payload.get("data", payload))


@server.tool(
    name="get_hijri_calendar_by_city",
    description=("Hijri month by city/country. Args: year (Hijri), month (1..12), "
                 "city, country. Optional: state, method, school, timezone, iso8601, "
                 "latitudeAdjustmentMethod (1..3), calendarMethod, midnightMode, adjustment."),
    inputSchema={
        "type": "object",
        "properties": {
            "year": {
                "type": "integer",
                "description": "Hijri year (e.g., 1446)",
                "minimum": 1
            },
            "month": {
                "type": "integer",
                "description": "Hijri month (1-12)",
                "minimum": 1,
                "maximum": 12
            },
            "city": {
                "type": "string",
                "description": "City name"
            },
            "country": {
                "type": "string",
                "description": "Country name or 2-letter ISO code"
            },
            "state": {
                "type": "string",
                "description": "State/province (optional)"
            },
            "method": {
                "type": "integer",
                "description": "Prayer calculation method (0-23 or 99)",
                "minimum": 0,
                "maximum": 99
            },
            "school": {
                "type": "integer",
                "description": "Islamic school: 0=Shafi, 1=Hanafi",
                "enum": [0, 1]
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (e.g., Asia/Singapore)"
            },
            "iso8601": {
                "type": "boolean",
                "description": "Return times in ISO-8601 format"
            },
            "latitudeAdjustmentMethod": {
                "type": "integer",
                "description": "Latitude adjustment method",
                "enum": [1, 2, 3]
            },
            "calendarMethod": {
                "type": "string",
                "description": "Calendar calculation method",
                "enum": ["HJCoSA", "UAQ", "DIYANET", "MATHEMATICAL"]
            },
            "midnightMode": {
                "type": "integer",
                "description": "Midnight calculation mode",
                "enum": [0, 1]
            },
            "adjustment": {
                "type": "integer",
                "description": "Time adjustment in minutes"
            }
        },
        "required": ["year", "month", "city", "country"],
        "additionalProperties": False
    }
)
async def get_hijri_calendar_by_city(args: dict):
    try:
        year = int(args["year"]); month = int(args["month"])
    except Exception:
        raise ValueError("Required: year (Hijri int), month (1..12)")
    city = str(args.get("city") or "").strip()
    country = str(args.get("country") or "").strip()
    if not city or not country:
        raise ValueError("Both 'city' and 'country' are required")

    params: dict[str, object] = {"city": city, "country": country}
    if args.get("state"): params["state"] = str(args["state"])
    if "method" in args and args["method"] is not None: params["method"] = int(args["method"])
    if "school" in args and args["school"] is not None:
        school = int(args["school"])
        if school not in (0, 1): raise ValueError("school must be 0 or 1")
        params["school"] = school
    if args.get("timezone"): params["timezonestring"] = str(args["timezone"])
    if "latitudeAdjustmentMethod" in args and args["latitudeAdjustmentMethod"] is not None:
        lam = int(args["latitudeAdjustmentMethod"])
        if lam not in (1,2,3): raise ValueError("latitudeAdjustmentMethod must be 1..3")
        params["latitudeAdjustmentMethod"] = lam
    if "calendarMethod" in args and args["calendarMethod"]:
        cm = str(args["calendarMethod"])
        if cm not in ("HJCoSA","UAQ","DIYANET","MATHEMATICAL"):
            raise ValueError("calendarMethod must be HJCoSA, UAQ, DIYANET, or MATHEMATICAL")
        params["calendarMethod"] = cm
    if "midnightMode" in args and args["midnightMode"] is not None:
        mm = int(args["midnightMode"])
        if mm not in (0,1): raise ValueError("midnightMode must be 0 or 1")
        params["midnightMode"] = mm
    if "iso8601" in args: params["iso8601"] = "true" if bool(args["iso8601"]) else "false"
    if "adjustment" in args and args["adjustment"] is not None:
        params["adjustment"] = int(args["adjustment"])

    url = f"{ALADHAN_BASE}/hijriCalendarByCity/{year}/{month}"
    payload = await get_json(url, params=params, timeout=20)
    return text_json(payload.get("data", payload))


@server.tool(
    name="get_prayer_times",
    description="Get daily prayer times by coordinates. date format: DD-MM-YYYY (defaults to today).",
    inputSchema={
        "type": "object",
        "properties": {
            "lat": {
                "type": "number",
                "description": "Latitude coordinate"
            },
            "lon": {
                "type": "number",
                "description": "Longitude coordinate"
            },
            "date": {
                "type": "string",
                "description": "Date in DD-MM-YYYY format (defaults to today)",
                "pattern": "^\\d{2}-\\d{2}-\\d{4}$"
            },
            "method": {
                "type": "integer",
                "description": "Prayer calculation method (0-23 or 99)",
                "minimum": 0,
                "maximum": 99
            },
            "school": {
                "type": "integer",
                "description": "Islamic school: 0=Shafi, 1=Hanafi",
                "enum": [0, 1]
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (e.g., Asia/Singapore)"
            },
            "iso8601": {
                "type": "boolean",
                "description": "Return times in ISO-8601 format"
            }
        },
        "required": ["lat", "lon"],
        "additionalProperties": False
    }
)
async def get_prayer_times(args: dict):
    """
    args:
      lat (float)     - required
      lon (float)     - required
      date (str)      - optional, DD-MM-YYYY; defaults to today
      method (int)    - optional, 0..23 or 99
      school (int)    - optional, 0=Shafi, 1=Hanafi
      timezone (str)  - optional, IANA tz name (e.g., Asia/Singapore)
      iso8601 (bool)  - optional, return ISO-8601 times
    """
    try:
        lat = float(args["lat"])
        lon = float(args["lon"])
    except Exception:
        raise ValueError("Missing or invalid 'lat'/'lon' (float required)")

    date = args.get("date")
    if not date:
        today = dt.date.today()
        date = today.strftime("%d-%m-%Y")

    params = {
        "latitude": lat,
        "longitude": lon,
    }

    if "school" in args:
        school = int(args["school"])
        if school not in (0, 1):
            raise ValueError("school must be 0 (Shafi) or 1 (Hanafi)")
        params["school"] = school

    if "method" in args:
        params["method"] = int(args["method"])

    if "timezone" in args:
        params["timezonestring"] = str(args["timezone"])

    if "iso8601" in args:
        params["iso8601"] = "true" if bool(args["iso8601"]) else "false"

    url = f"{ALADHAN_BASE}/timings/{date}"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()

    timings = payload.get("data", {}).get("timings", {})
    return text_json(timings)


@server.tool(
    name="get_prayer_times_by_city",
    description=(
        "Get daily prayer times by city/country (date format: DD-MM-YYYY; defaults to today). "
        "Optional: state, method (0..23 or 99), school (0=Shafi,1=Hanafi), timezone, iso8601."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name"
            },
            "country": {
                "type": "string",
                "description": "Country name or 2-letter ISO code"
            },
            "state": {
                "type": "string",
                "description": "State/province (optional)"
            },
            "date": {
                "type": "string",
                "description": "Date in DD-MM-YYYY format (defaults to today)",
                "pattern": "^\\d{2}-\\d{2}-\\d{4}$"
            },
            "method": {
                "type": "integer",
                "description": "Prayer calculation method (0-23 or 99)",
                "minimum": 0,
                "maximum": 99
            },
            "school": {
                "type": "integer",
                "description": "Islamic school: 0=Shafi, 1=Hanafi",
                "enum": [0, 1]
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (e.g., Asia/Singapore)"
            },
            "iso8601": {
                "type": "boolean",
                "description": "Return times in ISO-8601 format"
            }
        },
        "required": ["city", "country"],
        "additionalProperties": False
    }
)
async def get_prayer_times_by_city(args: dict):
    """
    args:
      city (str)       - required
      country (str)    - required (name or 2-letter ISO code)
      state (str)      - optional
      date (str)       - optional, DD-MM-YYYY; defaults to today
      method (int)     - optional, 0..23 or 99
      school (int)     - optional, 0=Shafi, 1=Hanafi
      timezone (str)   - optional, IANA tz (e.g., Asia/Singapore)
      iso8601 (bool)   - optional, return ISO-8601 times
    """
    import datetime as dt
    import httpx

    city = str(args.get("city") or "").strip()
    country = str(args.get("country") or "").strip()
    if not city or not country:
        raise ValueError("Both 'city' and 'country' are required")

    date = args.get("date")
    if not date:
        date = dt.date.today().strftime("%d-%m-%Y")

    params: dict[str, object] = {
        "city": city,
        "country": country,
    }
    if args.get("state"):
        params["state"] = str(args["state"])

    if "method" in args and args["method"] is not None:
        params["method"] = int(args["method"])

    if "school" in args and args["school"] is not None:
        school = int(args["school"])
        if school not in (0, 1):
            raise ValueError("school must be 0 (Shafi) or 1 (Hanafi)")
        params["school"] = school

    if "timezone" in args and args["timezone"]:
        params["timezonestring"] = str(args["timezone"])

    if "iso8601" in args:
        params["iso8601"] = "true" if bool(args["iso8601"]) else "false"

    url = f"{ALADHAN_BASE}/timingsByCity/{date}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()

    timings = payload.get("data", {}).get("timings", {})
    return text_json(timings)


@server.tool(
    name="get_qibla",
    description="Get Qibla direction (bearing, degrees) from latitude/longitude.",
    inputSchema={
        "type": "object",
        "properties": {
            "lat": {
                "type": "number",
                "description": "Latitude coordinate"
            },
            "lon": {
                "type": "number",
                "description": "Longitude coordinate"
            }
        },
        "required": ["lat", "lon"],
        "additionalProperties": False
    }
)
async def get_qibla(args: dict):
    """
    args:
      lat (float)  - required
      lon (float)  - required
    """
    import httpx

    try:
        lat = float(args["lat"])
        lon = float(args["lon"])
    except Exception:
        raise ValueError("Missing or invalid 'lat'/'lon' (float required)")

    url = f"{ALADHAN_BASE}/qibla/{lat}/{lon}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        payload = r.json()

    data = payload.get("data", {})
    direction = data.get("direction")
    if direction is not None:
        return text_json({"direction": direction})
    return text_json(payload)


@server.tool(
    name="get_next_prayer",
    description=(
        "Get the next prayer (name and time) for a given date and coordinates. "
        "Date format: DD-MM-YYYY (defaults to today). Optional: method (0..23 or 99), "
        "school (0=Shafi,1=Hanafi), timezone (IANA), iso8601 (bool)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "lat": {
                "type": "number",
                "description": "Latitude coordinate"
            },
            "lon": {
                "type": "number",
                "description": "Longitude coordinate"
            },
            "date": {
                "type": "string",
                "description": "Date in DD-MM-YYYY format (defaults to today)",
                "pattern": "^\\d{2}-\\d{2}-\\d{4}$"
            },
            "method": {
                "type": "integer",
                "description": "Prayer calculation method (0-23 or 99)",
                "minimum": 0,
                "maximum": 99
            },
            "school": {
                "type": "integer",
                "description": "Islamic school: 0=Shafi, 1=Hanafi",
                "enum": [0, 1]
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (e.g., Asia/Singapore)"
            },
            "iso8601": {
                "type": "boolean",
                "description": "Return times in ISO-8601 format"
            }
        },
        "required": ["lat", "lon"],
        "additionalProperties": False
    }
)
async def get_next_prayer(args: dict):
    """
    args:
      lat (float)      - required
      lon (float)      - required
      date (str)       - optional, DD-MM-YYYY; defaults to today
      method (int)     - optional, 0..23 or 99
      school (int)     - optional, 0=Shafi, 1=Hanafi
      timezone (str)   - optional, IANA tz (e.g., Asia/Singapore)
      iso8601 (bool)   - optional, return ISO-8601 times
    """
    import datetime as dt
    import httpx

    try:
        lat = float(args["lat"])
        lon = float(args["lon"])
    except Exception:
        raise ValueError("Missing or invalid 'lat'/'lon' (float required)")

    date = args.get("date")
    if not date:
        date = dt.date.today().strftime("%d-%m-%Y")

    params: dict[str, object] = {
        "latitude": lat,
        "longitude": lon,
    }

    if "method" in args and args["method"] is not None:
        params["method"] = int(args["method"])

    if "school" in args and args["school"] is not None:
        school = int(args["school"])
        if school not in (0, 1):
            raise ValueError("school must be 0 (Shafi) or 1 (Hanafi)")
        params["school"] = school

    if "timezone" in args and args["timezone"]:
        params["timezonestring"] = str(args["timezone"])

    if "iso8601" in args:
        params["iso8601"] = "true" if bool(args["iso8601"]) else "false"

    url = f"{ALADHAN_BASE}/nextPrayer/{date}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()

    data = payload.get("data", {})

    if data:
        return text_json(data)

    return text_json(payload)


@server.tool(
    name="get_hijri_calendar",
    description=(
        "Get prayer times for a Hijri month by coordinates. "
        "Args: year (Hijri), month (Hijri), lat, lon. "
        "Optional: method (0..23 or 99), school (0=Shafi,1=Hanafi), midnightMode (0/1), "
        "timezone (IANA), latitudeAdjustmentMethod (1..3), calendarMethod "
        "(HJCoSA|UAQ|DIYANET|MATHEMATICAL), iso8601 (bool), adjustment (int)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "year": {
                "type": "integer",
                "description": "Hijri year (e.g., 1446)",
                "minimum": 1
            },
            "month": {
                "type": "integer",
                "description": "Hijri month (1-12)",
                "minimum": 1,
                "maximum": 12
            },
            "lat": {
                "type": "number",
                "description": "Latitude coordinate"
            },
            "lon": {
                "type": "number",
                "description": "Longitude coordinate"
            },
            "method": {
                "type": "integer",
                "description": "Prayer calculation method (0-23 or 99)",
                "minimum": 0,
                "maximum": 99
            },
            "school": {
                "type": "integer",
                "description": "Islamic school: 0=Shafi, 1=Hanafi",
                "enum": [0, 1]
            },
            "midnightMode": {
                "type": "integer",
                "description": "Midnight calculation mode",
                "enum": [0, 1]
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (e.g., Asia/Singapore)"
            },
            "latitudeAdjustmentMethod": {
                "type": "integer",
                "description": "Latitude adjustment method",
                "enum": [1, 2, 3]
            },
            "calendarMethod": {
                "type": "string",
                "description": "Calendar calculation method",
                "enum": ["HJCoSA", "UAQ", "DIYANET", "MATHEMATICAL"]
            },
            "iso8601": {
                "type": "boolean",
                "description": "Return times in ISO-8601 format"
            },
            "adjustment": {
                "type": "integer",
                "description": "Time adjustment in minutes"
            }
        },
        "required": ["year", "month", "lat", "lon"],
        "additionalProperties": False
    }
)
async def get_hijri_calendar(args: dict):
    """
    args:
      year (int)     - required, Hijri year (e.g., 1446)
      month (int)    - required, Hijri month 1..12
      lat (float)    - required
      lon (float)    - required
      method (int)   - optional, 0..23 or 99
      school (int)   - optional, 0=Shafi, 1=Hanafi
      midnightMode (int) - optional, 0 or 1
      timezone (str) - optional, IANA tz (e.g., Asia/Singapore)
      latitudeAdjustmentMethod (int) - optional, 1..3
      calendarMethod (str) - optional, HJCoSA|UAQ|DIYANET|MATHEMATICAL
      iso8601 (bool) - optional
      adjustment (int) - optional (applies if calendarMethod=MATHEMATICAL)
    """
    import httpx

    try:
        year = int(args["year"])
        month = int(args["month"])
        lat = float(args["lat"])
        lon = float(args["lon"])
    except Exception:
        raise ValueError("Required: year (int), month (int), lat (float), lon (float)")

    params: dict[str, object] = {
        "latitude": lat,
        "longitude": lon,
    }

    if "method" in args and args["method"] is not None:
        params["method"] = int(args["method"])

    if "school" in args and args["school"] is not None:
        school = int(args["school"])
        if school not in (0, 1):
            raise ValueError("school must be 0 (Shafi) or 1 (Hanafi)")
        params["school"] = school

    if "midnightMode" in args and args["midnightMode"] is not None:
        mm = int(args["midnightMode"])
        if mm not in (0, 1):
            raise ValueError("midnightMode must be 0 or 1")
        params["midnightMode"] = mm

    if "timezone" in args and args["timezone"]:
        params["timezonestring"] = str(args["timezone"])

    if "latitudeAdjustmentMethod" in args and args["latitudeAdjustmentMethod"] is not None:
        lam = int(args["latitudeAdjustmentMethod"])
        if lam not in (1, 2, 3):
            raise ValueError("latitudeAdjustmentMethod must be 1, 2, or 3")
        params["latitudeAdjustmentMethod"] = lam

    if "calendarMethod" in args and args["calendarMethod"]:
        cm = str(args["calendarMethod"])
        if cm not in ("HJCoSA", "UAQ", "DIYANET", "MATHEMATICAL"):
            raise ValueError("calendarMethod must be HJCoSA, UAQ, DIYANET, or MATHEMATICAL")
        params["calendarMethod"] = cm

    if "iso8601" in args:
        params["iso8601"] = "true" if bool(args["iso8601"]) else "false"

    if "adjustment" in args and args["adjustment"] is not None:
        params["adjustment"] = int(args["adjustment"])

    url = f"{ALADHAN_BASE}/hijriCalendar/{year}/{month}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()

    data = payload.get("data", [])
    return text_json(data if data else payload)


@server.tool(
    name="get_monthly_calendar",
    description=(
        "Get prayer times for a Gregorian month by coordinates. "
        "Args: year (Gregorian), month (1..12), lat, lon. "
        "Optional: method (0..23 or 99), school (0=Shafi,1=Hanafi), midnightMode (0/1), "
        "timezone (IANA), latitudeAdjustmentMethod (1..3), shafaq (general|ahmer|abyad), "
        "tune (comma-separated offsets), iso8601 (bool), adjustment (int)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "year": {
                "type": "integer",
                "description": "Gregorian year (e.g., 2025)",
                "minimum": 1
            },
            "month": {
                "type": "integer",
                "description": "Gregorian month (1-12)",
                "minimum": 1,
                "maximum": 12
            },
            "lat": {
                "type": "number",
                "description": "Latitude coordinate"
            },
            "lon": {
                "type": "number",
                "description": "Longitude coordinate"
            },
            "method": {
                "type": "integer",
                "description": "Prayer calculation method (0-23 or 99)",
                "minimum": 0,
                "maximum": 99
            },
            "school": {
                "type": "integer",
                "description": "Islamic school: 0=Shafi, 1=Hanafi",
                "enum": [0, 1]
            },
            "midnightMode": {
                "type": "integer",
                "description": "Midnight calculation mode",
                "enum": [0, 1]
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (e.g., Asia/Singapore)"
            },
            "latitudeAdjustmentMethod": {
                "type": "integer",
                "description": "Latitude adjustment method",
                "enum": [1, 2, 3]
            },
            "shafaq": {
                "type": "string",
                "description": "Shafaq type for some calculation methods",
                "enum": ["general", "ahmer", "abyad"]
            },
            "tune": {
                "type": "string",
                "description": "Comma-separated minute offsets for timings"
            },
            "iso8601": {
                "type": "boolean",
                "description": "Return times in ISO-8601 format"
            },
            "adjustment": {
                "type": "integer",
                "description": "Time adjustment in minutes"
            }
        },
        "required": ["year", "month", "lat", "lon"],
        "additionalProperties": False
    }
)
async def get_monthly_calendar(args: dict):
    """
    args:
      year (int)    - required, Gregorian year (e.g., 2025)
      month (int)   - required, Gregorian month 1..12
      lat (float)   - required
      lon (float)   - required
      method (int)  - optional, 0..23 or 99
      school (int)  - optional, 0=Shafi, 1=Hanafi
      midnightMode (int) - optional, 0 or 1
      timezone (str) - optional, IANA tz (e.g., Asia/Singapore)
      latitudeAdjustmentMethod (int) - optional, 1..3
      shafaq (str)  - optional, general|ahmer|abyad (used with some methods)
      tune (str)    - optional, CSV minute offsets for timings
      iso8601 (bool) - optional
      adjustment (int) - optional (MATHEMATICAL calendar adjustments)
    """
    import httpx

    try:
        year = int(args["year"])
        month = int(args["month"])
        lat = float(args["lat"])
        lon = float(args["lon"])
    except Exception:
        raise ValueError("Required: year (int), month (int), lat (float), lon (float)")

    params: dict[str, object] = {
        "latitude": lat,
        "longitude": lon,
    }

    if "method" in args and args["method"] is not None:
        params["method"] = int(args["method"])

    if "school" in args and args["school"] is not None:
        school = int(args["school"])
        if school not in (0, 1):
            raise ValueError("school must be 0 (Shafi) or 1 (Hanafi)")
        params["school"] = school

    if "midnightMode" in args and args["midnightMode"] is not None:
        mm = int(args["midnightMode"])
        if mm not in (0, 1):
            raise ValueError("midnightMode must be 0 or 1")
        params["midnightMode"] = mm

    if "timezone" in args and args["timezone"]:
        params["timezonestring"] = str(args["timezone"])

    if "latitudeAdjustmentMethod" in args and args["latitudeAdjustmentMethod"] is not None:
        lam = int(args["latitudeAdjustmentMethod"])
        if lam not in (1, 2, 3):
            raise ValueError("latitudeAdjustmentMethod must be 1, 2, or 3")
        params["latitudeAdjustmentMethod"] = lam

    if "shafaq" in args and args["shafaq"]:
        sh = str(args["shafaq"])
        if sh not in ("general", "ahmer", "abyad"):
            raise ValueError("shafaq must be general, ahmer, or abyad")
        params["shafaq"] = sh

    if "tune" in args and args["tune"]:
        params["tune"] = str(args["tune"])

    if "iso8601" in args:
        params["iso8601"] = "true" if bool(args["iso8601"]) else "false"

    if "adjustment" in args and args["adjustment"] is not None:
        params["adjustment"] = int(args["adjustment"])

    url = f"{ALADHAN_BASE}/calendar/{year}/{month}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()

    data = payload.get("data", [])
    return text_json(data if data else payload)


@server.tool(
    name="get_monthly_calendar_by_city",
    description=(
        "Get prayer times for a Gregorian month by city/country. "
        "Args: year, month, city, country. Optional: state, method (0..23 or 99), "
        "school (0=Shafi,1=Hanafi), midnightMode (0/1), timezone (IANA), "
        "latitudeAdjustmentMethod (1..3), shafaq (general|ahmer|abyad), "
        "tune (CSV minute offsets), iso8601 (bool), adjustment (int), x7xapikey (str)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "year": {
                "type": "integer",
                "description": "Gregorian year (e.g., 2025)",
                "minimum": 1
            },
            "month": {
                "type": "integer",
                "description": "Gregorian month (1-12)",
                "minimum": 1,
                "maximum": 12
            },
            "city": {
                "type": "string",
                "description": "City name"
            },
            "country": {
                "type": "string",
                "description": "Country name or 2-letter ISO code"
            },
            "state": {
                "type": "string",
                "description": "State/province (optional)"
            },
            "method": {
                "type": "integer",
                "description": "Prayer calculation method (0-23 or 99)",
                "minimum": 0,
                "maximum": 99
            },
            "school": {
                "type": "integer",
                "description": "Islamic school: 0=Shafi, 1=Hanafi",
                "enum": [0, 1]
            },
            "midnightMode": {
                "type": "integer",
                "description": "Midnight calculation mode",
                "enum": [0, 1]
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (e.g., Asia/Singapore)"
            },
            "latitudeAdjustmentMethod": {
                "type": "integer",
                "description": "Latitude adjustment method",
                "enum": [1, 2, 3]
            },
            "shafaq": {
                "type": "string",
                "description": "Shafaq type for some calculation methods",
                "enum": ["general", "ahmer", "abyad"]
            },
            "tune": {
                "type": "string",
                "description": "Comma-separated minute offsets for timings"
            },
            "iso8601": {
                "type": "boolean",
                "description": "Return times in ISO-8601 format"
            },
            "adjustment": {
                "type": "integer",
                "description": "Time adjustment in minutes"
            },
            "x7xapikey": {
                "type": "string",
                "description": "API key for premium features (see Aladhan docs)"
            }
        },
        "required": ["year", "month", "city", "country"],
        "additionalProperties": False
    }
)
async def get_monthly_calendar_by_city(args: dict):
    """
    args:
      year (int)    - required, Gregorian year (e.g., 2025)
      month (int)   - required, 1..12
      city (str)    - required
      country (str) - required (name or 2-letter ISO code)
      state (str)   - optional
      method (int)  - optional, 0..23 or 99
      school (int)  - optional, 0=Shafi, 1=Hanafi
      midnightMode (int) - optional, 0 or 1
      timezone (str) - optional, IANA tz (e.g., Asia/Singapore)
      latitudeAdjustmentMethod (int) - optional, 1..3
      shafaq (str)  - optional, general|ahmer|abyad
      tune (str)    - optional, CSV minute offsets (Imsak,Fajr,Sunrise,...) 
      iso8601 (bool) - optional
      adjustment (int) - optional (MATHEMATICAL method only)
      x7xapikey (str) - optional (see Aladhan docs)
    """
    import httpx

    try:
        year = int(args["year"])
        month = int(args["month"])
    except Exception:
        raise ValueError("Required: year (int) and month (int 1..12)")

    city = str(args.get("city") or "").strip()
    country = str(args.get("country") or "").strip()
    if not city or not country:
        raise ValueError("Both 'city' and 'country' are required")

    params: dict[str, object] = {
        "city": city,
        "country": country,
    }

    if args.get("state"):
        params["state"] = str(args["state"])

    if "method" in args and args["method"] is not None:
        params["method"] = int(args["method"])

    if "school" in args and args["school"] is not None:
        school = int(args["school"])
        if school not in (0, 1):
            raise ValueError("school must be 0 (Shafi) or 1 (Hanafi)")
        params["school"] = school

    if "midnightMode" in args and args["midnightMode"] is not None:
        mm = int(args["midnightMode"])
        if mm not in (0, 1):
            raise ValueError("midnightMode must be 0 or 1")
        params["midnightMode"] = mm

    if "timezone" in args and args["timezone"]:
        params["timezonestring"] = str(args["timezone"])

    if "latitudeAdjustmentMethod" in args and args["latitudeAdjustmentMethod"] is not None:
        lam = int(args["latitudeAdjustmentMethod"])
        if lam not in (1, 2, 3):
            raise ValueError("latitudeAdjustmentMethod must be 1, 2, or 3")
        params["latitudeAdjustmentMethod"] = lam

    if "shafaq" in args and args["shafaq"]:
        sh = str(args["shafaq"])
        if sh not in ("general", "ahmer", "abyad"):
            raise ValueError("shafaq must be general, ahmer, or abyad")
        params["shafaq"] = sh

    if "tune" in args and args["tune"]:
        params["tune"] = str(args["tune"])

    if "iso8601" in args:
        params["iso8601"] = "true" if bool(args["iso8601"]) else "false"

    if "adjustment" in args and args["adjustment"] is not None:
        params["adjustment"] = int(args["adjustment"])

    if "x7xapikey" in args and args["x7xapikey"]:
        params["x7xapikey"] = str(args["x7xapikey"])

    url = f"{ALADHAN_BASE}/calendarByCity/{year}/{month}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        payload = r.json()

    data = payload.get("data", [])
    return TextContent(text=str(data if data else payload))


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write)


if __name__ == "__main__":
    asyncio.run(main())
