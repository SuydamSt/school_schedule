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


def _lecture_busy_abs(data: InputData) -> List[Tuple[int, int]]:
    buf = data.prefs.buffer_minutes
    out: List[Tuple[int, int]] = []
    for lec in data.lectures:
        if lec.online:
            continue
        day_i = DAYS_IN_ORDER.index(lec.day)
        base = day_i * 24 * 60
        s, e = _expand_interval(lec.start, lec.end, buf)
        out.append((base + s, base + e))
    out.sort()
    return out


def _sleep_duration(prefs) -> int:
    if prefs.sleep_start == prefs.sleep_end:
        return 0
    if prefs.sleep_start < prefs.sleep_end:
        return prefs.sleep_end - prefs.sleep_start
    return (24 * 60 - prefs.sleep_start) + prefs.sleep_end


def _shift_interval_forward_until_free(
    start_abs: int,
    duration: int,
    step: int,
    busy_abs: List[Tuple[int, int]],
    search_limit_abs: int,
) -> Tuple[int, int] | None:
    if duration <= 0:
        return None
    t0 = start_abs
    t1 = start_abs + duration
    while t1 <= search_limit_abs:
        if _is_free(t0, t1, busy_abs):
            return t0, t1
        t0 += step
        t1 += step
    return None


def reserve_sleep_week_abs(data: InputData) -> List[Tuple[int, int]]:
    prefs = data.prefs
    dur = _sleep_duration(prefs)
    if dur <= 0:
        return []

    step = max(1, int(prefs.slot_minutes))
    lecture_busy = _lecture_busy_abs(data)
    busy_abs = list(lecture_busy)

    sleep_abs: List[Tuple[int, int]] = []

    for day_i in range(len(DAYS_IN_ORDER)):
        desired_start_abs = day_i * 24 * 60 + prefs.sleep_start
        search_limit = desired_start_abs + 48 * 60
        placed = _shift_interval_forward_until_free(desired_start_abs, dur, step, busy_abs, search_limit)
        if placed is None:
            placed = (desired_start_abs, desired_start_abs + dur)
        s, e = placed
        sleep_abs.append((s, e))
        busy_abs.append((s, e))
        busy_abs.sort()

    return sleep_abs


def _sleep_busy_by_day(data: InputData, sleep_abs: List[Tuple[int, int]]) -> Dict[Day, List[Tuple[int, int]]]:
    buf = data.prefs.buffer_minutes
    out: Dict[Day, List[Tuple[int, int]]] = {d: [] for d in DAYS_IN_ORDER}
    for s_abs, e_abs in sleep_abs:
        t = s_abs
        while t < e_abs:
            day_i = (t // (24 * 60)) % len(DAYS_IN_ORDER)
            day = DAYS_IN_ORDER[day_i]
            within = t % (24 * 60)
            cap = (t // (24 * 60) + 1) * (24 * 60)
            end = min(e_abs, cap)
            s = within
            e = within + (end - t)
            out[day].append(_expand_interval(s, e, buf))
            t = end
    for d in out:
        out[d].sort()
    return out


def _lecture_busy_by_day(data: InputData) -> Dict[Day, List[Tuple[int, int]]]:
    buf = data.prefs.buffer_minutes
    out: Dict[Day, List[Tuple[int, int]]] = {d: [] for d in DAYS_IN_ORDER}
    for lec in data.lectures:
        if lec.online:
            continue
        out[lec.day].append(_expand_interval(lec.start, lec.end, buf))
    for d in out:
        out[d].sort()
    return out


def generate_free_slots(data: InputData) -> Dict[Day, List[Slot]]:
    prefs = data.prefs
    sleep_abs = reserve_sleep_week_abs(data)
    lecture_busy = _lecture_busy_by_day(data)
    sleep_busy = _sleep_busy_by_day(data, sleep_abs)

    free: Dict[Day, List[Slot]] = {}
    for day in DAYS_IN_ORDER:
        busy = sorted(lecture_busy[day] + sleep_busy[day])
        slots: List[Slot] = []
        t = prefs.earliest_start
        while t + prefs.slot_minutes <= prefs.latest_end:
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
    blocks: List[TimeBlock] = []
    for lec in data.lectures:
        if lec.online:
            continue
        name = str(lec.course_name).strip() or "untitled course"
        blocks.append(TimeBlock(day=lec.day, start=lec.start, end=lec.end, label=f"Lecture: {name}"))
    blocks.sort(key=lambda b: (DAYS_IN_ORDER.index(b.day), b.start))
    return blocks


def _candidate_study_blocks(
    data: InputData,
    rng: random.Random,
    sleep_abs: List[Tuple[int, int]],
) -> List[TimeBlock]:
    prefs = data.prefs
    targets = compute_course_targets(data.lectures)
    remaining = {k: int(v) for k, v in targets.items() if int(v) > 0}

    lecture_busy = _lecture_busy_by_day(data)
    sleep_busy = _sleep_busy_by_day(data, sleep_abs)

    busy_by_day: Dict[Day, List[Tuple[int, int]]] = {}
    for day in DAYS_IN_ORDER:
        busy_by_day[day] = sorted(lecture_busy[day] + sleep_busy[day])

    blocks_per_day: Dict[Day, int] = {day: 0 for day in DAYS_IN_ORDER}
    last_course_day: Dict[Day, str] = {day: "" for day in DAYS_IN_ORDER}
    study: List[TimeBlock] = []

    slot = prefs.slot_minutes
    min_block = _round_up_to_slot(prefs.min_block, slot)
    max_block = _round_down_to_slot(prefs.max_block, slot)
    if max_block < min_block:
        max_block = min_block

    day_indices = list(range(len(DAYS_IN_ORDER)))
    rng.shuffle(day_indices)

    def weighted_pick_course(day: Day) -> str | None:
        items = [(c, remaining[c]) for c in remaining if remaining[c] > 0]
        if not items:
            return None
        avoid = last_course_day[day]
        items2 = [(c, w) for (c, w) in items if c != avoid]
        pool = items2 if items2 else items
        total = sum(w for _, w in pool)
        r = rng.uniform(0, float(total))
        acc = 0.0
        for c, w in pool:
            acc += float(w)
            if r <= acc:
                return c
        return pool[-1][0]

    guard = 0
    while any(v > 0 for v in remaining.values()) and guard < 50000:
        guard += 1
        progressed = False

        for di in day_indices:
            day = DAYS_IN_ORDER[di]
            if blocks_per_day[day] >= prefs.prefer_blocks_per_day_max:
                continue

            cname = weighted_pick_course(day)
            if cname is None:
                continue

            desired = min(max_block, remaining[cname])
            desired = _round_down_to_slot(desired, slot)
            if desired < min_block:
                desired = min_block

            starts = list(range(prefs.earliest_start, prefs.latest_end - desired + 1, slot))
            rng.shuffle(starts)

            for t in starts:
                end = t + desired
                if _is_free(t, end, busy_by_day[day]):
                    study.append(TimeBlock(day=day, start=t, end=end, label=f"Study: {cname}"))
                    blocks_per_day[day] += 1
                    remaining[cname] = max(0, remaining[cname] - desired)
                    last_course_day[day] = cname

                    bs, be = _expand_interval(t, end, prefs.buffer_minutes)
                    _add_busy(busy_by_day[day], bs, be)

                    progressed = True
                    break

        if not progressed:
            break

    return study


def build_week_plan(data: InputData) -> List[TimeBlock]:
    prefs = data.prefs
    sleep_abs = reserve_sleep_week_abs(data)
    base = _base_plan_blocks(data)

    best_blocks = None
    best_score = None

    n = max(1, int(prefs.candidate_count))
    for i in range(n):
        rng = random.Random(i + 1)
        study = _candidate_study_blocks(data, rng, sleep_abs)
        blocks = base + study
        blocks.sort(key=lambda b: (DAYS_IN_ORDER.index(b.day), b.start))
        s = score_plan(blocks, prefs)
        if best_score is None or s > best_score:
            best_score = s
            best_blocks = blocks

    return best_blocks if best_blocks is not None else base
