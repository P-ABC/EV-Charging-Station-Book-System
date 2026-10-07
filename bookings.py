"""bookings.py — Binary booking/reservation storage for EV Charging Station."""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import models

BOOKING_STRUCT = struct.Struct(models.BOOKING_FORMAT)
RECORD_SIZE = BOOKING_STRUCT.size

STATUS_CONFIRMED = 1
STATUS_COMPLETED = 2
STATUS_CANCELLED = 3
STATUS_NAMES = {
    STATUS_CONFIRMED: "Confirmed",
    STATUS_COMPLETED: "Completed",
    STATUS_CANCELLED: "Cancelled",
}


def _encode(value: str, size: int) -> bytes:
    raw = (value or "").encode("utf-8")[:size]
    raw = raw.decode("utf-8", errors="ignore").encode("utf-8")
    return raw.ljust(size, b"\x00")


def _decode(value: bytes) -> str:
    return value.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()


@dataclass
class Booking:
    booking_id: int
    point_id: int
    customer_name: str
    booking_date: str
    start_time: str
    end_time: str
    status: int
    created_at: int

    @property
    def status_text(self) -> str:
        return STATUS_NAMES.get(self.status, f"Unknown({self.status})")

    def to_bytes(self) -> bytes:
        return BOOKING_STRUCT.pack(
            int(self.booking_id),
            int(self.point_id),
            _encode(self.customer_name, 30),
            _encode(self.booking_date, 10),
            _encode(self.start_time, 5),
            _encode(self.end_time, 5),
            int(self.status),
            int(self.created_at),
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "Booking":
        values = BOOKING_STRUCT.unpack(data)
        return cls(
            booking_id=values[0], point_id=values[1],
            customer_name=_decode(values[2]),
            booking_date=_decode(values[3]),
            start_time=_decode(values[4]), end_time=_decode(values[5]),
            status=values[6], created_at=values[7],
        )


class BookingStore:
    """Fixed-length binary CRUD storage for bookings.dat."""

    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(path):
            open(path, "ab").close()

    def integrity_check(self):
        size = os.path.getsize(self.path)
        return size % RECORD_SIZE == 0, size % RECORD_SIZE

    def truncate_incomplete(self) -> None:
        valid = os.path.getsize(self.path) // RECORD_SIZE * RECORD_SIZE
        with open(self.path, "r+b") as fh:
            fh.truncate(valid)

    def read_all(self) -> List[Booking]:
        result: List[Booking] = []
        with open(self.path, "rb") as fh:
            while True:
                data = fh.read(RECORD_SIZE)
                if not data:
                    break
                if len(data) != RECORD_SIZE:
                    break
                result.append(Booking.from_bytes(data))
        return result

    def find(self, booking_id: int) -> Optional[Booking]:
        for booking in self.read_all():
            if booking.booking_id == booking_id:
                return booking
        return None

    def active_for_point(self, point_id: int) -> List[Booking]:
        return [b for b in self.read_all()
                if b.point_id == point_id and b.status == STATUS_CONFIRMED]

    def next_id(self) -> int:
        records = self.read_all()
        return max((b.booking_id for b in records), default=0) + 1

    def append(self, booking: Booking) -> None:
        with open(self.path, "ab") as fh:
            fh.write(booking.to_bytes())
            fh.flush()
            os.fsync(fh.fileno())

    def update(self, booking: Booking) -> None:
        with open(self.path, "r+b") as fh:
            while True:
                pos = fh.tell()
                data = fh.read(RECORD_SIZE)
                if not data:
                    break
                if Booking.from_bytes(data).booking_id == booking.booking_id:
                    fh.seek(pos)
                    fh.write(booking.to_bytes())
                    fh.flush()
                    os.fsync(fh.fileno())
                    return
        raise KeyError(f"booking_id {booking.booking_id} not found")

    def count(self) -> int:
        return len(self.read_all())


def validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def validate_time(value: str) -> str:
    datetime.strptime(value, "%H:%M")
    return value
