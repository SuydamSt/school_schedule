from __future__ import annotations

from typing import Dict, List, Tuple

from scheduler.models import DAYS_IN_ORDER, Day, Preferences, TimeBlock


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _busy_intervals_from_blocks(blocks: List[TimeBlock]) -> Dict[Day, List[Tuple[int, int]]]:
    out: Dict[Day, List[Tuple[int, int]]] = {d: [] for d in DAYS_IN_ORDER}
    for b in blocks:
        if b.label.startswith("Lecture:") or b.label.startswith("Sleep"):
            out[b.day].append((b.start, b.end))
    for d in out:
        out[d].sort()
    return out


def _study_blocks(blocks: List[TimeBlock]) -> List[TimeBlock]:
    return [b for b in blocks if b.label.startswith("Study:")]


def _course_from_label(label: str) -> str:
    if label.startswith("Study:"):
        return label[len("Study:") :].strip()
    return ""


def score_plan(blocks: List[TimeBlock], prefs: Preferences) -> float:
    studies = _study_blocks(blocks)
    if not studies:
        return -1e9

    study_minutes_by_day: Dict[Day, int] = {d: 0 for d in DAYS_IN_ORDER}
    study_blocks_by_day: Dict[Day, int] = {d: 0 for d in DAYS_IN_ORDER}

    late_pen = 0.0
    for b in studies:
        mins = max(0, b.end - b.start)
        study_minutes_by_day[b.day] += mins
        study_blocks_by_day[b.day] += 1
        if prefs.latest_end > prefs.earliest_start:
            x = (b.start - prefs.earliest_start) / float(prefs.latest_end - prefs.earliest_start)
            late_pen += _clamp(x, 0.0, 1.0) ** 2 * mins

    daily_vals = [float(study_minutes_by_day[d]) for d in DAYS_IN_ORDER]
    mean = sum(daily_vals) / float(len(daily_vals))
    spread_pen = sum((v - mean) ** 2 for v in daily_vals) / float(len(daily_vals))

    overload_pen = 0.0
    for d in DAYS_IN_ORDER:
        over = max(0, study_blocks_by_day[d] - prefs.prefer_blocks_per_day_max)
        overload_pen += float(over * over)

    busy = _busy_intervals_from_blocks(blocks)
    gap_bonus = 0.0
    for b in studies:
        intervals = busy.get(b.day, [])
        if not intervals:
            continue
        best_dist = None
        for s, e in intervals:
            dist = min(abs(b.start - e), abs(s - b.end))
            if best_dist is None or dist < best_dist:
                best_dist = dist
        if best_dist is None:
            continue
        if best_dist <= 60:
            gap_bonus += (60.0 - float(best_dist)) * 0.25

    variety_pen = 0.0
    for d in DAYS_IN_ORDER:
        day_studies = [b for b in studies if b.day == d]
        day_studies.sort(key=lambda x: x.start)
        for i in range(1, len(day_studies)):
            if _course_from_label(day_studies[i].label) == _course_from_label(day_studies[i - 1].label):
                variety_pen += 1.0

    score = 0.0
    score -= prefs.weight_spread * spread_pen
    score -= prefs.weight_late * late_pen
    score -= prefs.weight_day_overload * overload_pen
    score += prefs.weight_gap_bonus * gap_bonus
    score -= 0.75 * variety_pen
    return score
