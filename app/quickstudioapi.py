import asyncio
import logging
import os
from datetime import date, datetime
from typing import Optional

import httpx
from cachetools import TTLCache
from pydantic import BaseModel

BOOKING_URL = os.getenv(
    "BOOKING_URL", "https://www.quickstudio.com/en/studios/hf-music-studio-14/bookings"
)
CACHE_TTL = int(os.getenv("CACHE_TTL_MINUTES", "60")) * 60  # 1h

logger = logging.getLogger(__name__)

timeout = httpx.Timeout(30)  # quickstudio endpoints are slow
limits = httpx.Limits(max_connections=10)  # it is easy to strain the server
cache = TTLCache(maxsize=1000, ttl=CACHE_TTL)


class Band(BaseModel):
    id: int
    name: str


class Booking(BaseModel):
    type: int
    start: datetime
    end: datetime
    band: Optional[Band]


class RoomBooking(BaseModel):
    id: int
    name: str
    description: str
    size: int
    open: datetime
    close: datetime
    bookings: list[Booking]


async def _run_quickstudio_bookings_request(
    client: httpx.AsyncClient, date: date
) -> list[RoomBooking]:
    # Check if the bookings for the given date are already in the cache
    if date in cache:
        logger.debug(f"Hit quickstudio cache for date: {date}")
        return cache[date]

    response = await client.get(
        BOOKING_URL,
        params={"date": date.isoformat()},
        headers={"Accept": "application/json"},  # Force JSON response
    )
    response.raise_for_status()
    bookings = [RoomBooking.model_validate(room) for room in response.json()]

    cache[date] = bookings

    return bookings


async def get_quickstudio_bookings(date: date) -> list[RoomBooking]:
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        bookings = await _run_quickstudio_bookings_request(client, date)

    return bookings


async def get_batch_quickstudio_bookings(
    dates: list[date],
) -> dict[date, list[RoomBooking]]:
    # Group up the request with common client to enforce limits
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        tasks = {
            date: asyncio.create_task(_run_quickstudio_bookings_request(client, date))
            for date in dates
        }

        results = await asyncio.gather(*tasks.values())

    return dict(zip(tasks.keys(), results))
