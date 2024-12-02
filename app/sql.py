import asyncio
from datetime import date as dt_date
from datetime import datetime, time, timedelta
from typing import Tuple

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import (
    Field,
    Relationship,
    Session,
    SQLModel,
    create_engine,
    select,
)

from .quickstudioapi import RoomBooking, get_quickstudio_bookings


class Room(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)
    description: str
    size: int
    open: time
    close: time

    studio_name: str = Field(foreign_key="studio.name", index=True)
    studio: "Studio" = Relationship(back_populates="rooms")

    def __hash__(self):
        return hash(self.id)


class Studio(SQLModel, table=True):
    name: str = Field(primary_key=True)
    rooms: list[Room] | None = Relationship(back_populates="studio")


class Band(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str = Field(index=True)

    def __hash__(self):
        return hash(self.id)


class Booking(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: int

    # with this representation, we assume that you cannot have a booking on several days
    date: dt_date = Field(index=True)
    start: time
    end: time  # special case for 0h00m, which is the start of next date

    band_id: int = Field(foreign_key="band.id")
    band: Band = Relationship()

    room_id: int = Field(foreign_key="room.id")
    room: Room = Relationship()


class StudioDataCache(SQLModel, table=True):
    studio_name: str = Field(primary_key=True, index=True)
    date: dt_date = Field(primary_key=True, index=True)
    last_refresh: datetime


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
            open=rb.open.time(),
            close=rb.close.time(),
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


async def refresh_bookings(session: Session, studio: Studio, date: dt_date):
    room_bookings = await get_quickstudio_bookings(date)
    rooms, bands, bookings = convert_quickstudio_response(studio, room_bookings)

    for room in rooms:
        session.merge(room)
    for band in bands:
        session.merge(band)

    # TODO: this could be somewhat improved with a DELETE query using sqlite
    # However, sqlite + sqlalchemy does not seem to easily support DELETE + JOIN query
    stale_bookings = get_bookings(session, studio, date)
    for sb in stale_bookings:
        session.delete(sb)

    session.add_all(bookings)

    session.commit()


# TODO: fetch data from remote before sending the response
def get_bookings(session: Session, studio: Studio, date: dt_date) -> list[Booking]:
    statement = (
        select(Booking)
        .where(Booking.date == date)
        .join(Room)
        .where(Room.studio_name == studio.name)
    )
    results = session.exec(statement)

    # TODO: is this the good way to convert from sequence to list
    bookings = results.all()
    return list(bookings)


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
    with Session(engine) as session:
        await refresh_bookings(session, hf14, current_date)


if __name__ == "__main__":
    asyncio.run(main())
