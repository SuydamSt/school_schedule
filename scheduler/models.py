from __future__ import annotations

from enum import Enum
from typing import Dict, List
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


def minutes_to_hhmm(m: int) -> str:
    h = (m // 60) % 24
    mm = m % 60
    return f"{h:02d}:{mm:02d}"


def hhmm_to_minutes(hhmm: str) -> int:
    hh, mm = hhmm.strip().split(":")
    return int(hh) * 60 + int(mm)


class Lecture(BaseModel):
    course_name: str
    day: Day
    start: Minute
    end: Minute
    multiplier: float = Field(ge=0.0, default=2.0)

    @property
    def duration_minutes(self) -> int:
        return max(0, self.end - self.start)

    @property
    def target_study_minutes(self) -> int:
        return int(round(self.duration_minutes * self.multiplier))


class Preferences(BaseModel):
    earliest_start: Minute = 8 * 60
    latest_end: Minute = 22 * 60
    sleep_start: Minute = 23 * 60
    sleep_end: Minute = 7 * 60

    slot_minutes: int = 30
    min_block: int = 30
    max_block: int = 90
    prefer_blocks_per_day_max: int = 4


class InputData(BaseModel):
    lectures: List[Lecture]
    prefs: Preferences


def compute_course_targets(lectures: List[Lecture]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for lec in lectures:
        name = (lec.course_name or "").strip() or "untitled course"
        totals[name] = totals.get(name, 0) + lec.target_study_minutes
    return totals
