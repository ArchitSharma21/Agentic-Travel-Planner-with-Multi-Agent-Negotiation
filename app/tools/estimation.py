from app.models.trip import TripRequest


def estimate_base_trip_cost(trip: TripRequest) -> float:
    travelers = trip.travelers or 1
    days = trip.num_days or 3

    style = (trip.travel_style or "").lower()

    hotel_per_night = 70
    food_per_day = 30
    local_transport_per_day = 10
    activities_per_day = 25

    if "luxury" in style:
        hotel_per_night = 180
        food_per_day = 70
        activities_per_day = 60
    elif "mid" in style or "comfortable" in style:
        hotel_per_night = 110
        food_per_day = 45
        activities_per_day = 40
    elif "budget" in style:
        hotel_per_night = 50
        food_per_day = 20
        activities_per_day = 15

    total = (
        hotel_per_night * days
        + food_per_day * days * travelers
        + local_transport_per_day * days * travelers
        + activities_per_day * days * travelers
    )

    return round(total, 2)