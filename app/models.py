import os
from datetime import date as dt_date
from datetime import time, timedelta
from typing import Tuple

from pydantic import BaseModel

from .quickstudioapi import RoomBooking

DATA_STALE_MINUTES = int(os.getenv("DATA_STALE_MINUTES", 15))
SQL_DEBUG = os.getenv("SQL_DEBUG", "true").lower() == "true"


class Room(BaseModel):
    id: int
    name: str
    description: str
    size: int
    open: time
    close: time

    studio_name: str

    def __hash__(self):
        return hash(self.id)


class Band(BaseModel):
    id: int
    name: str

    def __hash__(self):
        return hash(self.id)


class Booking(BaseModel):
    type: int

    # with this representation, we assume that you cannot have a booking on several days
    date: dt_date
    start: time
    end: time  # special case for 0h00m, which is the start of next date

    band: Band

    room: Room


def convert_quickstudio_response(
    studio_name: str, room_bookings: list[RoomBooking]
) -> Tuple[list[Band], list[Booking], list[Room]]:
    rooms = set()
    bands = set()
    bookings = []
    for rb in room_bookings:
        room = Room(
            id=rb.id,
            name=rb.name,
            description=rb.description,
            size=rb.size,
            open=rb.open.time(),
            close=rb.close.time(),
            studio_name=studio_name,
        )
        rooms.add(room)
        for booking in rb.bookings:
            match booking.type:
                case 1:  # normal booking with a band
                    if booking.band is None:
                        raise Exception(
                            f"Booking for room '{rb.name}' has no band but has type {booking.type}"
                        )
                    band = Band(id=booking.band.id, name=booking.band.name)
                    bands.add(band)
                    if booking.start.date() != booking.end.date():
                        # we expect that a booking cannot cross over several days
                        # one exception: ends at midnight
                        if not (
                            booking.end.time() == time(hour=0)
                            and booking.end.date()
                            == booking.start.date() + timedelta(days=1)
                        ):
                            raise Exception(
                                f"booking {booking} spans several days which is not expected"
                            )

                    bookings.append(
                        Booking(
                            type=booking.type,
                            date=booking.start.date(),
                            start=booking.start.time(),
                            end=booking.end.time(),
                            band=band,
                            room=room,
                        )
                    )
                case 4:  # empty booking for non opening hours
                    pass
                case _:
                    raise Exception(
                        f"Unknow booking type '{booking.type}' for room '{rb.name}'"
                    )

    return list(bands), bookings, list(rooms)
