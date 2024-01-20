# import uvicorn # debug
import re
from datetime import date, datetime, time, timedelta

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import Availability, RoomAvailability, RoomBooking

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"datetime": datetime}
    )


@app.get("/availability", response_class=HTMLResponse)
async def availability(
    request: Request,
    start_date: date,
    end_date: date,
    min_room_size: int = 50,
    min_availability_duration: int = 60,
    start_time: time = time(hour=19),
    end_time: time = time(hour=00),
):
    room_bookings_per_date = {}
    for day in range((end_date - start_date).days + 1):
        date = start_date + timedelta(days=day)
        room_bookings_per_date[date] = await get_quickstudio_bookings(date)

    room_availabilities_per_date = {}
    for date, room_bookings in room_bookings_per_date.items():
        room_availabilities = [
            compute_room_availability(
                room_bookings,
                timedelta(minutes=min_availability_duration),
                start_time,
                end_time,
            )
            for room_bookings in room_bookings
        ]
        room_availabilities_per_date[date] = [
            room_availability
            for room_availability in room_availabilities
            if room_availability.size >= min_room_size
            and len(room_availability.availabilities) > 0
        ]

    return templates.TemplateResponse(
        request=request,
        name="availabilities.html",
        context={
            "room_availabilities_per_date": room_availabilities_per_date,
            "datetime": datetime,
        },
    )


async def get_quickstudio_bookings(date: date) -> list[RoomBooking]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            "https://www.quickstudio.com/en/studios/hf-music-studio-14/bookings",
            params={"date": date.isoformat()},
            headers={"Accept": "application/json"},  # Force JSON response
        )

    response.raise_for_status()
    return [RoomBooking(**room) for room in response.json()]


def compute_room_availability(
    room_booking: RoomBooking,
    min_availability_duration: timedelta,
    start_time: time,
    end_time: time,
) -> RoomAvailability:
    availabilities = []
    opening_time = max(
        room_booking.open,
        datetime.combine(
            room_booking.open, start_time, tzinfo=room_booking.open.tzinfo
        ),
    )
    if end_time == time(hour=0):
        closing_time = min(
            room_booking.close,
            datetime.combine(
                room_booking.open + timedelta(days=1),
                end_time,
                tzinfo=room_booking.open.tzinfo,
            ),
        )
    else:
        closing_time = min(
            room_booking.close,
            datetime.combine(
                room_booking.open, end_time, tzinfo=room_booking.open.tzinfo
            ),
        )

    # Sort bookings by chronological order
    room_booking.bookings.sort(key=lambda x: x.start)

    for booking in room_booking.bookings:
        if booking.start > opening_time:
            availabilities.append(Availability(start=opening_time, end=booking.start))
        opening_time = max(booking.end, opening_time)

    if closing_time > opening_time:
        availabilities.append(Availability(start=opening_time, end=closing_time))

    # Filter availabilities based on start_time and end_time
    filtered_availabilities = [
        availability
        for availability in availabilities
        if (availability.end - availability.start) >= min_availability_duration
    ]

    return RoomAvailability(
        name=_strip_room_name(room_booking.name),
        size=room_booking.size,
        availabilities=filtered_availabilities,
    )


def _strip_room_name(room_name: str) -> str:
    m = re.match(r"^\d+\.([\w\s]+)\s.*$", room_name)
    if m:
        return m.group(1)
    else:
        return room_name


# debug
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)
