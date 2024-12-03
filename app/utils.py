import re
from datetime import datetime as Datetime, date as Date, time as Time, timedelta

from .sql import Booking


def get_next_nth_date(span_days: int) -> list[Date]:
    today = Datetime.today().date()
    return [today + timedelta(days=i) for i in range(span_days)]


def get_room_id(booking: Booking) -> int:
    return booking.room.id


def strip_room_name(room_name: str) -> str:
    m = re.match(r"^\d+\.([\w\s]+)\s.*$", room_name)
    if m:
        return m.group(1)
    else:
        return room_name


def combine_datetime_midnight_aware(date: Date, time: Time) -> Datetime:
    return Datetime.combine(
        # if the end time is midnight, the date is next day
        date + timedelta(days=1) if time == Time(hour=0) else date,
        time,
    )
