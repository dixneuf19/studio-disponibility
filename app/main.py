# import uvicorn # debug
import asyncio
import re
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .quickstudioapi import (
    Availability,
    RoomAvailability,
    RoomBooking,
    get_quickstudio_bookings,
)

app = FastAPI()


@app.get("/health")
async def get_health() -> dict[str, str]:
    return {"message": "OK"}


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
    days_of_week: Annotated[list[int], Query()] = [1, 2, 3, 4, 5, 6, 7],
    min_room_size: int = 50,
    min_availability_duration: int = 60,
    start_time: time = time(hour=19),
    end_time: time = time(hour=00),
):
    tasks = []
    for day in range((end_date - start_date).days + 1):
        current_date = start_date + timedelta(days=day)
        if current_date.isoweekday() not in days_of_week:
            continue
        date = start_date + timedelta(days=day)
        task = asyncio.create_task(
            get_studio_availability(
                date=date,
                start_time=start_time,
                end_time=end_time,
                min_room_size=min_room_size,
                min_availability_duration=timedelta(minutes=min_availability_duration),
            )
        )
        tasks.append(task)

    room_availabilities = await asyncio.gather(*tasks)

    # remove date with no availabilities
    room_availabilities_per_date = {
        date: availabilities
        for date, availabilities in room_availabilities
        if len(availabilities) > 0
    }

    return templates.TemplateResponse(
        request=request,
        name="availabilities.html",
        context={
            "room_availabilities_per_date": room_availabilities_per_date,
            "datetime": datetime,
        },
    )


async def get_studio_availability(
    date: date,
    start_time: time,
    end_time: time,
    min_room_size,
    min_availability_duration: timedelta,
) -> tuple[date, list[RoomAvailability]]:
    room_bookings = await get_quickstudio_bookings(date)

    room_availabilities = [
        compute_room_availability(
            room_bookings,
            min_availability_duration,
            start_time,
            end_time,
        )
        for room_bookings in room_bookings
    ]
    filtered_room_availabilities = [
        room_availability
        for room_availability in room_availabilities
        if room_availability.size >= min_room_size
        and len(room_availability.availabilities) > 0
    ]

    return date, filtered_room_availabilities


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
        date=room_booking.open,
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
