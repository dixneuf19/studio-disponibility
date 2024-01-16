from datetime import date, datetime, timedelta
from typing import Optional

from pydantic import BaseModel


class Band(BaseModel):
    id: int
    name: str


class Booking(BaseModel):
    type: int
    start: datetime
    end: datetime
    band: Optional[Band]


class RoomBooking(BaseModel):
    name: str
    description: str
    size: int
    open: datetime
    close: datetime
    bookings: list[Booking]


class Availability(BaseModel):
    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


class RoomAvailability(BaseModel):
    name: str
    size: int
    availabilities: list[Availability]
