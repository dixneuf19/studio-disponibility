import os
import logging
from contextlib import asynccontextmanager
from datetime import date as Date
from datetime import datetime as Datetime
from datetime import time as Time
from datetime import timedelta
from itertools import groupby
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.quickstudioapi import get_batch_quickstudio_bookings

from .models import Booking, Room, convert_quickstudio_response
from .utils import (
    combine_datetime_midnight_aware,
    get_dates_from_range,
    get_room_id,
    strip_room_name,
)

AUTO_CACHE_SPAN_DAYS = int(os.getenv("AUTO_CACHE_SPAN_DAYS", 15))

STUDIO_NAMES = ["hf-14"]

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())


class RoomAvailability(BaseModel):
    room_name: str
    date: Date
    start: Datetime
    end: Datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load up cache

    for studio in STUDIO_NAMES:
        _ = studio  # TODO: parametrize for several studios
        _ = await get_batch_quickstudio_bookings(
            get_dates_from_range(
                Date.today(), Date.today() + timedelta(days=AUTO_CACHE_SPAN_DAYS)
            )
        )  # do nothing of the result, we only want to load up the cache

    yield
    # Add shutdown tasks if necessary


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def get_health() -> dict[str, str]:
    return {"message": "OK"}


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"Datetime": Datetime}
    )


@app.get("/availabilities", response_class=HTMLResponse)
async def get_availabilities(
    request: Request,
    studio_name: str,
    start_date: Date,
    end_date: Date,
    from_time: Time,
    to_time: Time,
    days_of_week: Annotated[list[int], Query()] = [1, 2, 3, 4, 5, 6, 7],
    min_room_size: int = 50,
    min_availability_duration: int = 60,
):
    dates = [
        date
        for date in get_dates_from_range(start_date, end_date)
        if date.isoweekday() in days_of_week
    ]

    quickstudio_bookings_per_date = await get_batch_quickstudio_bookings(dates)

    room_availabilities_per_date: dict[Date, list[RoomAvailability]] = {}

    for date, quickstudio_bookings in quickstudio_bookings_per_date.items():
        _, bookings, rooms = convert_quickstudio_response(
            studio_name, quickstudio_bookings
        )

        room_availabilities_per_date[date] = _compute_room_availabilities(
            bookings,
            rooms,
            date,
            from_time,
            to_time,
            timedelta(minutes=min_availability_duration),
            min_room_size,
        )

    return templates.TemplateResponse(
        request=request,
        name="availabilities.html",
        context={
            "room_availabilities_per_date": room_availabilities_per_date,
            "Datetime": Datetime,
        },
    )


def _compute_room_availabilities(
    bookings: list[Booking],
    studio_rooms: list[Room],
    date: Date,
    from_time: Time,
    to_time: Time,
    min_availability_duration: timedelta,
    min_room_size: int,
) -> list[RoomAvailability]:
    availabilities = []

    bookings_per_room = {
        room_id: list(bookings_iter)
        for room_id, bookings_iter in groupby(
            sorted(bookings, key=get_room_id), key=get_room_id
        )
    }

    # only consider big enough rooms
    for room in (room for room in studio_rooms if room.size >= min_room_size):
        start_pointer = Datetime.combine(date, max(room.open, from_time))
        end_pointer = min(
            combine_datetime_midnight_aware(date, to_time),
            combine_datetime_midnight_aware(date, room.close),
        )

        # Sort bookings by chronological order
        sorted_bookings_for_room = (
            sorted(bookings_per_room[room.id], key=lambda x: x.start)
            if room.id in bookings_per_room
            else []
        )

        # opening_time is a moving pointer to find rooms without bookings
        # this work because
        for booking in sorted_bookings_for_room:
            if Datetime.combine(booking.date, booking.start) > start_pointer:
                availabilities.append(
                    RoomAvailability(
                        room_name=strip_room_name(room.name),
                        date=date,
                        start=start_pointer,
                        end=combine_datetime_midnight_aware(
                            booking.date, booking.start
                        ),
                    )
                )
            start_pointer = max(
                combine_datetime_midnight_aware(date, booking.end), start_pointer
            )

        # All bookings have been considered, the rest is available
        if end_pointer > start_pointer:
            availabilities.append(
                RoomAvailability(
                    room_name=strip_room_name(room.name),
                    date=date,
                    start=start_pointer,
                    end=end_pointer,
                )
            )
    # remove availabilities too shorts
    filtered_availabilities = [
        availability
        for availability in availabilities
        if (availability.end - availability.start) >= min_availability_duration
    ]

    # sort per start
    return sorted(filtered_availabilities, key=lambda a: a.start)


# debug
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
