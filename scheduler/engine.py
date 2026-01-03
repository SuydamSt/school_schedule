from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

from scheduler.models import (
    Day,
    DAYS_IN_ORDER,
    InputData,
    TimeBlock,
    compute_course_targets,
    overlaps,
    in_sleep_window,
)
from scheduler.scoring import score_plan


@dataclass(frozen=True)
class Slot:
    day: Day
    start: int
    end: int


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _expand_interval(start: int, end: int, buffer_minutes: int) -> Tuple[int, int]:
    s = _clamp(start - buffer_minutes, 0, 24 * 60)
    e = _clamp(end + buffer_minutes, 0, 24 * 60)
    return s, e


def _is_free(start: int, end: int, busy: List[Tuple[int, int]]) -> bool:
    return all(not overlaps(start, end, b0, b1) for (b0, b1) in busy)


def _add_busy(busy: List[Tuple[int, int]], start: int, end: int) -> None:
    busy.append((start, end))
    busy.sort()


def _non_online_lecture_busy_for_day(data: InputData, day: Day) -> List[Tuple[int, int]]:
    buf = data.prefs.buffer_minutes
    intervals: List[Tuple[int, int]] = []
    for lec in data.lectures:
        if lec.day == day and not lec.online:
            intervals.append(_expand_interval(lec.start, lec.end, buf))
    intervals.sort()
    return intervals


def _sleep_blocks_raw_for_day(day: Day, sleep_start: int, sleep_end: int) -> List[TimeBlock]:
    blocks: List[TimeBlock] = []
    if sleep_start == sleep_end:
        return blocks
    if sleep_start < sleep_end:
        blocks.append(TimeBlock(day=day, start=sleep_start, end=sleep_end, label="Sleep"))
        return blocks
    blocks.append(TimeBlock(day=day, start=sleep_start, end=24 * 60, label="Sleep"))
    blocks.append(TimeBlock(day=day, start=0, end=sleep_end, label="Sleep"))
    return blocks


def _shift_block_forward_until_free(
    start: int,
    end: int,
    slot: int,
    busy: List[Tuple[int, int]],
) -> Tuple[int, int] | None:
    duration = max(0, end - start)
    if duration <= 0:
        return None

    t0 = _clamp(start, 0, 24 * 60)
    t1 = _clamp(end, 0, 24 * 60)

    if t1 - t0 != duration:
        t1 = t0 + duration
        if t1 > 24 * 60:
            return None

    while t1 <= 24 * 60:
        if _is_free(t0, t1, busy):
            return t0, t1
        t0 += slot
        t1 += slot

    return None


def _adjusted_sleep_blocks_for_day(data: InputData, day: Day) -> List[TimeBlock]:
    prefs = data.prefs
    slot = max(1, int(prefs.slot_minutes))
    raw = _sleep_blocks_raw_for_day(day, prefs.sleep_start, prefs.sleep_end)
    lecture_busy = _non_online_lecture_busy_for_day(data, day)

    out: List[TimeBlock] = []
    for b in raw:
        shifted = _shift_block_forward_until_free(b.start, b.end, slot, lecture_busy)
        if shifted is None:
            continue
        s, e = shifted
        out.append(TimeBlock(day=day, start=s, end=e, label="Sleep"))
        lecture_busy.append(_expand_interval(s, e, prefs.buffer_minutes))
        lecture_busy.sort()

    return out


def _sleep_busy_for_day(data: InputData, day: Day) -> List[Tuple[int, int]]:
    buf = data.prefs.buffer_minutes
    intervals: List[Tuple[int, int]] = []
    for b in _adjusted_sleep_blocks_for_day(data, day):
        intervals.append(_expand_interval(b.start, b.end, buf))
    intervals.sort()
    return intervals


def generate_free_slots(data: InputData) -> Dict[Day, List[Slot]]:
    prefs = data.prefs
    free: Dict[Day, List[Slot]] = {}

    for day in DAYS_IN_ORDER:
        busy: List[Tuple[int, int]] = []
        busy.extend(_non_online_lecture_busy_for_day(data, day))
        busy.extend(_sleep_busy_for_day(data, day))
        busy.sort()

        slots: List[Slot] = []
        t = prefs.earliest_start
        while t + prefs.slot_minutes <= prefs.latest_end:
            if in_sleep_window(t, prefs.sleep_start, prefs.sleep_end):
                t += prefs.slot_minutes
                continue
            end = t + prefs.slot_minutes
            if _is_free(t, end, busy):
                slots.append(Slot(day=day, start=t, end=end))
            t += prefs.slot_minutes

        free[day] = slots

    return free


def _round_down_to_slot(n: int, slot: int) -> int:
    if slot <= 0:
        return n
    return (n // slot) * slot


def _round_up_to_slot(n: int, slot: int) -> int:
    if slot <= 0:
        return n
    return ((n + slot - 1) // slot) * slot


def _base_plan_blocks(data: InputData) -> List[TimeBlock]:
    prefs = data.prefs
    blocks: List[TimeBlock] = []

    for day in DAYS_IN_ORDER:
        blocks.extend(_adjusted_sleep_blocks_for_day(data, day))

    for lec in data.lectures:
        if lec.online:
            continue
        name = str(lec.course_name).strip() or "untitled course"
        blocks.append(TimeBlock(day=lec.day, start=lec.start, end=lec.end, label=f"Lecture: {name}"))

    return blocks


def _candidate_study_blocks(data: InputData, rng: random.Random) -> List[TimeBlock]:
    prefs = data.prefs
    targets = compute_course_targets(data.lectures)
    remaining = dict(targets)

    busy_by_day: Dict[Day, List[Tuple[int, int]]] = {}
    for day in DAYS_IN_ORDER:
        busy: List[Tuple[int, int]] = []
        busy.extend(_non_online_lecture_busy_for_day(data, day))
        busy.extend(_sleep_busy_for_day(data, day))
        busy.sort()
        busy_by_day[day] = busy

    blocks_per_day: Dict[Day, int] = {day: 0 for day in DAYS_IN_ORDER}
    study: List[TimeBlock] = []

    slot = prefs.slot_minutes
    min_block = _round_up_to_slot(prefs.min_block, slot)
    max_block = _round_down_to_slot(prefs.max_block, slot)
    if max_block < min_block:
        max_block = min_block

    courses = list(remaining.keys())
    rng.shuffle(courses)

    day_indices = list(range(len(DAYS_IN_ORDER)))
    rng.shuffle(day_indices)

    def can_place(day: Day, start: int, end: int) -> bool:
        if start < prefs.earliest_start or end > prefs.latest_end:
            return False
        if in_sleep_window(start, prefs.sleep_start, prefs.sleep_end):
            return False
        return _is_free(start, end, busy_by_day[day])

    for cname in courses:
        guard = 0
        while remaining.get(cname, 0) > 0 and guard < 10000:
            guard += 1

            desired = min(max_block, remaining[cname])
            desired = _round_down_to_slot(desired, slot)
            if desired < min_block:
                desired = min_block
            if desired <= 0:
                break

            placed = False
            for di in day_indices:
                day = DAYS_IN_ORDER[di]
                if blocks_per_day[day] >= prefs.prefer_blocks_per_day_max:
                    continue

                starts = list(range(prefs.earliest_start, prefs.latest_end - desired + 1, slot))
                rng.shuffle(starts)

                for t in starts:
                    end = t + desired
                    if can_place(day, t, end):
                        study.append(TimeBlock(day=day, start=t, end=end, label=f"Study: {cname}"))
                        blocks_per_day[day] += 1
                        remaining[cname] -= desired

                        bs, be = _expand_interval(t, end, prefs.buffer_minutes)
                        _add_busy(busy_by_day[day], bs, be)

                        placed = True
                        break

                if placed:
                    break

            if not placed:
                break

    return study


def build_week_plan(data: InputData) -> List[TimeBlock]:
    prefs = data.prefs
    base = _base_plan_blocks(data)

    best_blocks = None
    best_score = None

    n = max(1, int(prefs.candidate_count))
    for i in range(n):
        rng = random.Random(i + 1)
        study = _candidate_study_blocks(data, rng)
        blocks = base + study
        blocks.sort(key=lambda b: (DAYS_IN_ORDER.index(b.day), b.start))
        s = score_plan(blocks, prefs)
        if best_score is None or s > best_score:
            best_score = s
            best_blocks = blocks

    return best_blocks if best_blocks is not None else base
