from __future__ import annotations

import httpx

from app.models.trip import PriceFact, TripCostBreakdown, TripRequest


BASELINE_EUR = {
    "lodging": 85,
    "meals": 30,
    "transport": 8,
    "activities": 22,
}


FX_RATES_FROM_EUR = {
    "EUR": 1.0,
    "USD": 1.08,
    "GBP": 0.85,
    "INR": 90.0,
    "JPY": 170.0,
    "CAD": 1.48,
    "AUD": 1.62,
    "CHF": 0.95,
    "SGD": 1.45,
    "AED": 3.95,
}


STYLE_MULTIPLIERS = {
    "budget": {"lodging": 0.65, "meals": 0.75, "transport": 0.9, "activities": 0.75},
    "mid": {"lodging": 1.0, "meals": 1.0, "transport": 1.0, "activities": 1.0},
    "comfortable": {"lodging": 1.15, "meals": 1.12, "transport": 1.05, "activities": 1.1},
    "luxury": {"lodging": 2.0, "meals": 1.8, "transport": 1.6, "activities": 1.8},
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _currency(trip: TripRequest) -> str:
    return (trip.budget_currency or "EUR").strip().upper() or "EUR"


def _style_key(trip: TripRequest) -> str:
    style = (trip.travel_style or "").lower()
    if "lux" in style:
        return "luxury"
    if "comfort" in style:
        return "comfortable"
    if "budget" in style or "cheap" in style or "low" in style:
        return "budget"
    return "mid"


def _destination_country_code(destination: str | None) -> tuple[str | None, str]:
    query = (destination or "").strip()
    if not query:
        return None, "destination was missing"

    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 1,
            },
            headers={"User-Agent": "agentic-travel-planner/1.0"},
            timeout=4.0,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            return None, "Nominatim returned no destination match"

        address = results[0].get("address", {})
        country_code = (address.get("country_code") or "").upper()
        country = address.get("country")
        if country_code:
            label = f"{country} ({country_code})" if country else country_code
            return country_code, f"Nominatim resolved destination country: {label}"
    except Exception as exc:
        return None, f"Nominatim lookup failed: {str(exc)[:180]}"

    return None, "Nominatim match did not include a country code"


def _world_bank_gdp_ppp(country_code: str) -> tuple[float | None, str]:
    try:
        response = httpx.get(
            f"https://api.worldbank.org/v2/country/{country_code}/indicator/NY.GDP.PCAP.PP.CD",
            params={"format": "json", "per_page": 8},
            timeout=4.0,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or len(data) < 2:
            return None, "World Bank returned an unexpected response"

        for row in data[1]:
            value = row.get("value")
            year = row.get("date")
            if value:
                return float(value), f"World Bank GDP per capita PPP ({country_code}, {year})"
    except Exception as exc:
        return None, f"World Bank PPP lookup failed: {str(exc)[:180]}"

    return None, "World Bank had no recent GDP per capita PPP value"


def _cost_index_for_destination(destination: str | None) -> tuple[float, str, str, float]:
    country_code, country_note = _destination_country_code(destination)
    if not country_code:
        return 1.0, "generic baseline; destination country unavailable", "generic_baseline", 0.42

    gdp_ppp, gdp_note = _world_bank_gdp_ppp(country_code)
    if not gdp_ppp:
        return (
            1.0,
            f"generic baseline; {country_note}; {gdp_note}",
            "generic_baseline",
            0.45,
        )

    # PPP-adjusted GDP is not a price quote, but it gives a transparent,
    # no-account cost signal that avoids hardcoding city/country price tables.
    multiplier = _clamp((gdp_ppp / 45000.0) ** 0.45, 0.45, 1.85)
    return (
        multiplier,
        f"dynamic cost index from {country_note}; {gdp_note}; multiplier={round(multiplier, 2)}",
        "dynamic_cost_index",
        0.62,
    )


def _live_fx_rate(target_currency: str) -> tuple[float, str] | None:
    if target_currency == "EUR":
        return 1.0, "EUR base currency"

    try:
        response = httpx.get(
            "https://api.frankfurter.app/latest",
            params={"from": "EUR", "to": target_currency},
            timeout=4.0,
        )
        response.raise_for_status()
        data = response.json()
        rate = float(data.get("rates", {}).get(target_currency))
        if rate > 0:
            return rate, "Frankfurter live ECB exchange rate"
    except Exception:
        return None

    return None


def _fx_rate(target_currency: str) -> tuple[float, str, str]:
    live_rate = _live_fx_rate(target_currency)
    if live_rate:
        return live_rate[0], live_rate[1], "live_fx"

    if target_currency in FX_RATES_FROM_EUR:
        return (
            FX_RATES_FROM_EUR[target_currency],
            "bundled fallback exchange rate",
            "static_fx",
        )

    return 1.0, "unknown currency; left EUR-denominated baseline unchanged", "no_fx"


def _convert(amount: float, rate: float) -> float:
    return round(amount * rate, 2)


def _fact(
    category: str,
    mid: float,
    currency: str,
    unit: str,
    source_name: str,
    source_url: str | None,
    confidence: float,
) -> PriceFact:
    return PriceFact(
        category=category,
        amount_low=round(mid * 0.75, 2),
        amount_mid=round(mid, 2),
        amount_high=round(mid * 1.35, 2),
        currency=currency,
        unit=unit,
        source_name=source_name,
        source_url=source_url,
        confidence=confidence,
    )


def estimate_trip_cost_breakdown(trip: TripRequest) -> TripCostBreakdown:
    travelers = max(1, trip.travelers or 1)
    days = max(1, trip.num_days or 3)
    nights = max(1, days - 1)
    currency = _currency(trip)
    style = _style_key(trip)

    cost_index, cost_source, baseline_mode, confidence = _cost_index_for_destination(
        trip.destination
    )
    multipliers = STYLE_MULTIPLIERS[style]
    fx_rate, fx_source, fx_mode = _fx_rate(currency)

    lodging_mid = _convert(BASELINE_EUR["lodging"] * cost_index * multipliers["lodging"], fx_rate)
    meals_mid = _convert(BASELINE_EUR["meals"] * cost_index * multipliers["meals"], fx_rate)
    transport_mid = _convert(BASELINE_EUR["transport"] * cost_index * multipliers["transport"], fx_rate)
    activities_mid = _convert(BASELINE_EUR["activities"] * cost_index * multipliers["activities"], fx_rate)

    lodging = round(lodging_mid * nights, 2)
    meals = round(meals_mid * days * travelers, 2)
    local_transport = round(transport_mid * days * travelers, 2)
    activities = round(activities_mid * days * travelers, 2)
    total = round(lodging + meals + local_transport + activities, 2)

    source_url = "https://api.worldbank.org/v2/"
    price_facts = [
        _fact(
            "lodging",
            lodging_mid,
            currency,
            "per_room_night",
            cost_source,
            source_url,
            confidence,
        ),
        _fact(
            "meals",
            meals_mid,
            currency,
            "per_person_day",
            cost_source,
            source_url,
            confidence,
        ),
        _fact(
            "local_transport",
            transport_mid,
            currency,
            "per_person_day",
            cost_source,
            source_url,
            confidence,
        ),
        _fact(
            "activities",
            activities_mid,
            currency,
            "per_person_day",
            cost_source,
            source_url,
            confidence,
        ),
    ]

    notes = [
        f"Cost model used {style} travel style, {days} day(s), {nights} lodging night(s), and {travelers} traveler(s).",
        f"Pricing source: {cost_source}.",
        f"Currency source: {fx_source}.",
        "Inbound/outbound flights are excluded unless a later flight-pricing tool is added.",
    ]

    return TripCostBreakdown(
        lodging=lodging,
        meals=meals,
        local_transport=local_transport,
        activities=activities,
        total=total,
        currency=currency,
        pricing_mode=f"{baseline_mode}+{fx_mode}",
        notes=notes,
        price_facts=price_facts,
    )


def estimate_base_trip_cost(trip: TripRequest) -> float:
    return estimate_trip_cost_breakdown(trip).total
