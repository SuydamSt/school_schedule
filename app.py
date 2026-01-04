import calendar
import datetime as dt
import streamlit as st

from storage.repo import save_data, load_data
from scheduler.engine import generate_free_slots, build_week_plan
from scheduler.models import (
    Day,
    DAYS_IN_ORDER,
    Lecture,
    Preferences,
    InputData,
    minutes_to_hhmm,
    hhmm_to_minutes,
    compute_course_targets,
)

st.set_page_config(page_title="study scheduler", layout="wide")
st.title("study scheduler")

if "lectures" not in st.session_state:
    st.session_state.lectures = []
if "prefs" not in st.session_state:
    st.session_state.prefs = Preferences()

st.markdown(
    """
<style>
.daycard {
  border: 1px solid rgba(0,0,0,0.15);
  border-radius: 14px;
  padding: 10px 10px 6px 10px;
  min-height: 190px;
  background: rgba(0,0,0,0.01);
}
.daycard.out {
  opacity: 0.45;
}
.daynum {
  font-weight: 700;
  font-size: 0.95rem;
  margin-bottom: 6px;
}
.blockchip {
  border-left-width: 6px;
  border-left-style: solid;
  padding: 6px 8px;
  margin: 6px 0;
  background: rgba(0,0,0,0.03);
  border-radius: 12px;
}
.blockchip .t {
  font-size: 0.82rem;
  line-height: 1.1;
  word-break: break-word;
}
</style>
""",
    unsafe_allow_html=True,
)

def course_from_label(label: str) -> str:
    if label.startswith("Study:"):
        return label[len("Study:") :].strip()
    if label.startswith("Lecture:"):
        return label[len("Lecture:") :].strip()
    return ""

def build_course_colors(lectures: list[Lecture]) -> dict[str, str]:
    out: dict[str, str] = {}
    for lec in lectures:
        name = str(lec.course_name).strip() or "untitled course"
        c = str(getattr(lec, "color_hex", "")).strip() or "#4e79a7"
        out[name] = c
    return out

def day_enum_from_date(date_obj: dt.date) -> Day:
    return DAYS_IN_ORDER[date_obj.weekday()]

def block_html(label: str, start: int, end: int, color: str) -> str:
    text = f"{minutes_to_hhmm(start)}–{minutes_to_hhmm(end)} {label}"
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"<div class='blockchip' style='border-left-color:{color};'><div class='t'>{safe}</div></div>"

with st.sidebar:
    st.header("preferences")
    prefs: Preferences = st.session_state.prefs

    st.subheader("data")
    c_save, c_load, c_reset = st.columns(3)

    if c_save.button("save"):
        data = InputData(lectures=st.session_state.lectures, prefs=st.session_state.prefs)
        save_data(data)
        st.success("saved to data.json")

    if c_load.button("load"):
        loaded = load_data()
        if loaded:
            st.session_state.lectures = loaded.lectures
            st.session_state.prefs = loaded.prefs
            st.rerun()
        else:
            st.warning("no data.json found")

    if c_reset.button("reset"):
        st.session_state.lectures = []
        st.session_state.prefs = Preferences()
        st.rerun()

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        earliest = st.text_input("earliest start (hh:mm)", value=minutes_to_hhmm(prefs.earliest_start))
        latest = st.text_input("latest end (hh:mm)", value=minutes_to_hhmm(prefs.latest_end))
    with c2:
        sleep_start = st.text_input("sleep start (hh:mm)", value=minutes_to_hhmm(prefs.sleep_start))
        sleep_end = st.text_input("sleep end (hh:mm)", value=minutes_to_hhmm(prefs.sleep_end))

    slot_minutes = st.selectbox("slot size (minutes)", [15, 30, 45, 60], index=[15, 30, 45, 60].index(prefs.slot_minutes))
    min_block = st.selectbox("min block (minutes)", [15, 30, 45, 60], index=[15, 30, 45, 60].index(prefs.min_block))
    max_block = st.selectbox("max block (minutes)", [60, 90, 120, 150, 180], index=[60, 90, 120, 150, 180].index(prefs.max_block))
    per_day = st.selectbox("max blocks per day", [2, 3, 4, 5, 6], index=[2, 3, 4, 5, 6].index(prefs.prefer_blocks_per_day_max))
    buffer_minutes = st.selectbox("buffer between things (minutes)", [0, 15, 30, 45, 60], index=[0, 15, 30, 45, 60].index(prefs.buffer_minutes))

    st.divider()
    st.subheader("planner quality")
    candidate_count = st.selectbox("candidate schedules", [5, 10, 20, 30, 50, 75, 100], index=[5, 10, 20, 30, 50, 75, 100].index(prefs.candidate_count if prefs.candidate_count in [5, 10, 20, 30, 50, 75, 100] else 30))
    weight_spread = st.slider("spread across week", 0.0, 3.0, float(prefs.weight_spread), 0.1)
    weight_late = st.slider("avoid late study", 0.0, 3.0, float(prefs.weight_late), 0.1)
    weight_day_overload = st.slider("avoid overloaded days", 0.0, 3.0, float(prefs.weight_day_overload), 0.1)
    weight_gap_bonus = st.slider("prefer gaps near lectures", 0.0, 3.0, float(prefs.weight_gap_bonus), 0.1)

    st.divider()
    st.subheader("calendar")
    today = dt.date.today()
    view_year = st.selectbox("year", [today.year - 1, today.year, today.year + 1], index=1)
    view_month = st.selectbox("month", list(range(1, 13)), index=today.month - 1)
    week_variation = st.selectbox("week variation", ["on", "off"], index=0)

    try:
        prefs.earliest_start = hhmm_to_minutes(earliest)
        prefs.latest_end = hhmm_to_minutes(latest)
        prefs.sleep_start = hhmm_to_minutes(sleep_start)
        prefs.sleep_end = hhmm_to_minutes(sleep_end)
        prefs.slot_minutes = int(slot_minutes)
        prefs.min_block = int(min_block)
        prefs.max_block = int(max_block)
        prefs.prefer_blocks_per_day_max = int(per_day)
        prefs.buffer_minutes = int(buffer_minutes)
        prefs.candidate_count = int(candidate_count)
        prefs.weight_spread = float(weight_spread)
        prefs.weight_late = float(weight_late)
        prefs.weight_day_overload = float(weight_day_overload)
        prefs.weight_gap_bonus = float(weight_gap_bonus)
        st.session_state.prefs = prefs
    except Exception:
        st.warning("time format should be hh:mm (example: 08:30)")

tab1, tab2, tab3, tab4 = st.tabs(["lectures", "availability", "plan (month)", "debug"])

with tab1:
    st.subheader("lectures (this drives study targets)")

    for idx, lec in enumerate(list(st.session_state.lectures)):
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 1, 1, 1, 1, 1, 1])
        with col1:
            cname = st.text_input(f"course #{idx+1}", value=lec.course_name, key=f"lec_course_{idx}")
        with col2:
            day = st.selectbox(
                f"day #{idx+1}",
                options=[d.value for d in Day],
                index=[d.value for d in Day].index(lec.day.value),
                key=f"lec_day_{idx}",
            )
        with col3:
            start = st.text_input(f"start #{idx+1}", value=minutes_to_hhmm(lec.start), key=f"lec_start_{idx}")
        with col4:
            end = st.text_input(f"end #{idx+1}", value=minutes_to_hhmm(lec.end), key=f"lec_end_{idx}")
        with col5:
            online = st.checkbox("online", value=bool(getattr(lec, "online", False)), key=f"lec_online_{idx}")
        with col6:
            color_hex = st.color_picker("color", value=str(getattr(lec, "color_hex", "#4e79a7")), key=f"lec_color_{idx}")
        with col7:
            if st.button("remove", key=f"lec_remove_{idx}"):
                st.session_state.lectures.pop(idx)
                st.rerun()

        mcol1, mcol2 = st.columns([1, 3])
        with mcol1:
            multiplier = st.number_input(
                f"multiplier #{idx+1}",
                min_value=0.0,
                value=float(getattr(lec, "multiplier", 2.0)),
                step=0.5,
                key=f"lec_mult_{idx}",
            )
        with mcol2:
            try:
                dur = hhmm_to_minutes(end) - hhmm_to_minutes(start)
                dur = max(0, dur)
                target = int(round(dur * float(multiplier)))
                st.caption(f"duration: {dur} min • target study: {target} min ({target/60:.1f}h)")
            except Exception:
                st.caption("enter valid start/end times to preview target study time")

        try:
            st.session_state.lectures[idx] = Lecture(
                course_name=(str(cname).strip() or "untitled course"),
                day=Day([d for d in Day if d.value == day][0]),
                start=hhmm_to_minutes(start),
                end=hhmm_to_minutes(end),
                multiplier=float(multiplier),
                online=bool(online),
                color_hex=str(color_hex).strip() or "#4e79a7",
            )
        except Exception:
            st.warning("lecture times must be hh:mm")

    if st.button("add lecture"):
        st.session_state.lectures.append(
            Lecture(course_name="course 1", day=Day.mon, start=9 * 60, end=10 * 60, multiplier=2.0, online=False, color_hex="#4e79a7")
        )
        st.rerun()

    st.divider()
    st.subheader("weekly study targets (computed)")
    targets = compute_course_targets(st.session_state.lectures)
    if not targets:
        st.caption("add at least one lecture to compute targets")
    else:
        rows = [{"course": k, "target_minutes": v, "target_hours": round(v / 60, 2)} for k, v in sorted(targets.items())]
        st.dataframe(rows, use_container_width=True)

with tab2:
    st.subheader("availability (free study slots)")
    data = InputData(lectures=st.session_state.lectures, prefs=st.session_state.prefs)
    free = generate_free_slots(data)
    total_slots = sum(len(v) for v in free.values())
    st.caption(f"slot size: {data.prefs.slot_minutes} min • buffer: {data.prefs.buffer_minutes} min • total free slots: {total_slots}")

    for day in DAYS_IN_ORDER:
        slots = free.get(day, [])
        st.markdown(f"### {day.value}")
        if not slots:
            st.caption("no free slots")
        else:
            rows = [{"start": minutes_to_hhmm(s.start), "end": minutes_to_hhmm(s.end)} for s in slots]
            st.dataframe(rows, use_container_width=True)

with tab3:
    st.subheader("plan (month view)")
    data = InputData(lectures=st.session_state.lectures, prefs=st.session_state.prefs)
    colors = build_course_colors(st.session_state.lectures)

    cal = calendar.Calendar(firstweekday=0)
    month_weeks = list(cal.monthdatescalendar(int(view_year), int(view_month)))

    week_plans: list[tuple[list[dt.date], dict[dt.date, list]]] = []
    for week in month_weeks:
        anchor = next((d for d in week if d.month == int(view_month)), week[0])
        iso = anchor.isocalendar()
        seed = int(view_year) * 10000 + int(view_month) * 100 + int(iso.week)
        if week_variation == "off":
            seed = int(view_year) * 10000 + int(view_month) * 100 + 1

        plan = build_week_plan(data, seed=seed)
        by_weekday: dict[int, list] = {i: [] for i in range(7)}
        for b in plan:
            by_weekday[DAYS_IN_ORDER.index(b.day)].append(b)
        for i in by_weekday:
            by_weekday[i].sort(key=lambda x: x.start)

        date_map: dict[dt.date, list] = {}
        for d in week:
            wd = d.weekday()
            date_map[d] = by_weekday.get(wd, [])
        week_plans.append((week, date_map))

    headers = st.columns(7)
    for i, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        headers[i].markdown(f"**{name}**")

    for week, date_map in week_plans:
        cols = st.columns(7)
        for i, date_obj in enumerate(week):
            in_month = (date_obj.month == int(view_month))
            cls = "daycard" if in_month else "daycard out"
            blocks = date_map.get(date_obj, [])

            parts = [f"<div class='{cls}'><div class='daynum'>{date_obj.day}</div>"]
            limit = 6
            shown = 0
            for b in blocks:
                c = course_from_label(b.label)
                color = colors.get(c, "#888888")
                parts.append(block_html(b.label, b.start, b.end, color))
                shown += 1
                if shown >= limit:
                    break
            if len(blocks) > limit:
                parts.append(f"<div style='opacity:0.7; font-size:0.8rem; padding:2px 2px;'>+{len(blocks)-limit} more</div>")
            parts.append("</div>")
            html = "".join(parts)

            with cols[i]:
                st.markdown(html, unsafe_allow_html=True)

with tab4:
    st.subheader("debug data")
    data = InputData(lectures=st.session_state.lectures, prefs=st.session_state.prefs)
    st.json(data.model_dump())
