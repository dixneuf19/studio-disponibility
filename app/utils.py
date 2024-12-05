import re
from datetime import date as Date
from datetime import datetime as Datetime
from datetime import time as Time
from datetime import timedelta

from .models import Booking


def get_dates_from_range(from_date: Date, to_date: Date) -> list[Date]:
    return [
        from_date + timedelta(days=day) for day in range((to_date - from_date).days + 1)
    ]


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
