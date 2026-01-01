from __future__ import annotations

from enum import Enum
from typing import List
from pydantic import BaseModel, Field

Minute = int

class Day(str, Enum):
    mon = "Mon"
    tue = "Tue"
    wed = "Wed"
    thu = "Thu"
    fri = "Fri"
    sat = "Sat"
    sun = "Sun"


DAYS_IN_ORDER: List[Day] = [Day.mon, Day.tue, Day.wed, Day.thu, Day.fri, Day.sat, Day.sun]

class Course(BaseModel):
    name: str
    weekly_target_minutes: int = Field(ge=0, default=180)

def minutes_to_hhmm(m: int) -> str:
    h = (m//60)%24
    mm = m%60
    return f"{h:02d}:{mm:02d}"

def hhmm_to_minutes(hhmm: str) -> int:
    hh, mm = hhmm.strip().split(":")
    return int(hh)*60*int(mm)