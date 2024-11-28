from datetime import datetime, date, time

from sqlmodel import SQLModel, Field, Relationship, create_engine, Session
from sqlalchemy import delete, Engine
from sqlalchemy.exc import IntegrityError
from .quickstudioapi import RoomBooking, get_quickstudio_bookings

from typing import Tuple

import asyncio


class Room(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    description: str
    size: int
    open: datetime
    close: datetime

    studio_name: str = Field(foreign_key="studio.name")

    def __hash__(self):
        return hash(self.id)


class Studio(SQLModel, table=True):
    name: str = Field(primary_key=True)
    # rooms: list[Room] | None = Relationship(back_populates="studio")


class Band(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)

    def __hash__(self):
        return hash(self.id)


class Booking(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: int
    start: datetime
    end: datetime

    band_id: int = Field(foreign_key="band.id")
    band: Band = Relationship()

    room_id: int = Field(foreign_key="room.id")
    room: Room = Relationship()


def convert_quickstudio_response(
    studio: Studio, room_bookings: list[RoomBooking]
) -> Tuple[list[Room], list[Band], list[Booking]]:
    rooms = set()
    bands = set()
    bookings = []
    for rb in room_bookings:
        room = Room(
            id=rb.id,
            name=rb.name,
            description=rb.description,
            size=rb.size,
            open=rb.open,
            close=rb.close,
            studio_name=studio.name,
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
                    bookings.append(
                        Booking(
                            type=booking.type,
                            start=booking.start,
                            end=booking.end,
                            band_id=band.id,
                            room_id=room.id,
                        )
                    )
                case 4:  # empty booking for non opening hours
                    pass
                case _:
                    raise Exception(
                        f"Unknow booking type '{booking.type}' for room '{rb.name}'"
                    )

    return (list(rooms), list(bands), bookings)


async def refresh_bookings(engine: Engine, studio: Studio, date: date):
    room_bookings = await get_quickstudio_bookings(date)
    rooms, bands, bookings = convert_quickstudio_response(studio, room_bookings)
    start_of_day = datetime.combine(date, time(hour=0, minute=0, second=0))
    end_of_day = datetime.combine(date, time(hour=23, minute=59, second=59))

    with Session(engine) as session:
        for room in rooms:
            session.merge(room)
        for band in bands:
            session.merge(band)

        statement = (
            delete(Booking)
            .where(Booking.start >= start_of_day)  # type: ignore[arg-type]
            .where(Booking.start <= end_of_day)  # type: ignore[arg-type]
        )
        session.exec(statement)  # type: ignore[arg-type]
        session.add_all(bookings)

        session.commit()


def init_db(sqlite_url: str, debug: bool = False) -> Engine:
    engine = create_engine(sqlite_url, echo=debug)
    SQLModel.metadata.create_all(engine)

    return engine


async def main():
    sqlite_file_name = "database.db"
    sqlite_url = f"sqlite:///{sqlite_file_name}"

    engine = init_db(sqlite_url, debug=True)

    hf14 = Studio(name="hf-music-studio-14")

    try:
        with Session(engine) as session:
            session.add(hf14)

            session.commit()
            session.refresh(hf14)  # necessary to use the object later
    except IntegrityError:
        print("Studio already created")

    current_date = datetime.today().date()

    await refresh_bookings(engine, hf14, current_date)


if __name__ == "__main__":
    asyncio.run(main())
