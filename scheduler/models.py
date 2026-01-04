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
    online: bool = False
    color_hex: str = "#4e79a7"

    @property
    def duration_minutes(self) -> int:
        return max(0, self.end - self.start)

    @property
    def target_study_minutes(self) -> int:
        return int(round(self.duration_minutes * self.multiplier))


class Preferences(BaseModel):
    earliest_start: Minute = 8 * 60
    latest_end: Minute = 22 * 60

    sleep_start: Minute = 9 * 60
    sleep_end: Minute = 17 * 60

    slot_minutes: int = 30
    min_block: int = 30
    max_block: int = 90
    prefer_blocks_per_day_max: int = 4
    buffer_minutes: int = 30

    candidate_count: int = 30

    weight_spread: float = 1.0
    weight_late: float = 1.0
    weight_day_overload: float = 1.0
    weight_gap_bonus: float = 1.0


class InputData(BaseModel):
    lectures: List[Lecture]
    prefs: Preferences


class TimeBlock(BaseModel):
    day: Day
    start: Minute
    end: Minute
    label: str


def compute_course_targets(lectures: List[Lecture]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for lec in lectures:
        name = str(lec.course_name).strip() or "untitled course"
        totals[name] = totals.get(name, 0) + lec.target_study_minutes
    return totals


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end
