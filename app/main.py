# import uvicorn  # debug
import re
from contextlib import asynccontextmanager
from datetime import datetime as Datetime, date as Date, time as Time, timedelta
from itertools import groupby
from typing import Annotated

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, Session

from .sql import (
    Booking,
    Studio,
    StudioDataCache,
    get_bookings,
    init_db,
    refresh_bookings,
)

STUDIO_NAMES = ["hf-14"]


class RoomAvailability(SQLModel):
    room_name: str
    date: Date
    start: Datetime
    end: Datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the ML model
    sqlite_file_name = "database.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    app.state.engine = init_db(sqlite_url)

    # TODO: Refresh data for a bigger range
    current_date = Datetime.today().date()

    for studio_name in STUDIO_NAMES:
        with Session(app.state.engine) as session:
            studio = Studio(name=studio_name)
            session.merge(studio)
            session.commit()
            await refresh_bookings(session, studio, current_date)

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


@app.get("/availability", response_class=HTMLResponse)
async def availability(
    request: Request,
    studio_name: str,
    start_date: Date,
    end_date: Date,
    days_of_week: Annotated[list[int], Query()] = [1, 2, 3, 4, 5, 6, 7],
    min_room_size: int = 50,
    min_availability_duration: int = 60,
    from_time: Time = Time(hour=19),
    to_time: Time = Time(hour=00),
):
    # tasks = []
    # TODO: use FastAPI dependency injection
    with Session(request.app.state.engine) as session:
        studio = session.get(Studio, studio_name)
        if not studio:
            raise HTTPException(
                status_code=404, detail=f"Studio {studio_name} is not supported"
            )

        room_availabilities_per_date: dict[Date, list[RoomAvailability]] = {}
        for day in range((end_date - start_date).days + 1):
            current_date = start_date + timedelta(days=day)
            if current_date.isoweekday() not in days_of_week:
                continue

            date = start_date + timedelta(days=day)

            last_data_pull = session.get(
                StudioDataCache, {"studio_name": studio.name, "date": date}
            )
            if (
                not last_data_pull
                or last_data_pull.last_refresh < Datetime.now() - timedelta(minutes=5)
            ):
                await refresh_bookings(session, studio, date)
                session.merge(
                    StudioDataCache(
                        studio_name=studio.name, date=date, last_refresh=Datetime.now()
                    )
                )

            bookings = get_bookings(session, studio, date)

            room_availabilities_per_date[date] = _compute_room_availabilities(
                studio,
                bookings,
                date,
                from_time,
                to_time,
                timedelta(minutes=min_availability_duration),
                min_room_size,
            )
            # TODO: if relevant, reimplement concurrent API calls
        #     task = asyncio.create_task(
        #         get_studio_availability(
        #             date=date,
        #             start_time=start_time,
        #             end_time=end_time,
        #             min_room_size=min_room_size,
        #             min_availability_duration=timedelta(minutes=min_availability_duration),
        #         )
        #     )
        #     tasks.append(task)

        # room_availabilities = await asyncio.gather(*tasks)

        # remove date with no availabilities

        return templates.TemplateResponse(
            request=request,
            name="availabilities.html",
            context={
                "room_availabilities_per_date": room_availabilities_per_date,
                "Datetime": Datetime,
            },
        )


def _get_room_id(booking: Booking) -> int:
    return booking.room.id


def _compute_room_availabilities(
    studio: Studio,
    bookings: list[Booking],
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
            sorted(bookings, key=_get_room_id), key=_get_room_id
        )
    }

    if studio.rooms is None:
        return availabilities

    # only consider big enough rooms
    for room in (room for room in studio.rooms if room.size >= min_room_size):
        start_pointer = Datetime.combine(date, max(room.open, from_time))
        min_close = min(room.close, to_time)
        end_pointer = Datetime.combine(
            # if the end time is midnight, the date is next day
            date + timedelta(days=1) if min_close == Time(hour=0) else date,
            min_close,
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
                        room_name=_strip_room_name(room.name),
                        date=date,
                        start=start_pointer,
                        end=Datetime.combine(booking.date, booking.start),
                    )
                )
            start_pointer = max(Datetime.combine(date, booking.end), start_pointer)

        # All bookings have been considered, the rest is available
        if end_pointer > start_pointer:
            availabilities.append(
                RoomAvailability(
                    room_name=_strip_room_name(room.name),
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


def _strip_room_name(room_name: str) -> str:
    m = re.match(r"^\d+\.([\w\s]+)\s.*$", room_name)
    if m:
        return m.group(1)
    else:
        return room_name


# debug
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)
