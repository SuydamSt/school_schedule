import streamlit as st

from scheduler.models import (
    Day,
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

with st.sidebar:
    st.header("preferences")
    prefs: Preferences = st.session_state.prefs

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

    try:
        prefs.earliest_start = hhmm_to_minutes(earliest)
        prefs.latest_end = hhmm_to_minutes(latest)
        prefs.sleep_start = hhmm_to_minutes(sleep_start)
        prefs.sleep_end = hhmm_to_minutes(sleep_end)
        prefs.slot_minutes = int(slot_minutes)
        prefs.min_block = int(min_block)
        prefs.max_block = int(max_block)
        prefs.prefer_blocks_per_day_max = int(per_day)
        st.session_state.prefs = prefs
    except Exception:
        st.warning("time format should be hh:mm (example: 08:30)")

tab1, tab2 = st.tabs(["lectures", "debug"])

with tab1:
    st.subheader("lectures (this drives study targets)")

    for idx, lec in enumerate(list(st.session_state.lectures)):
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
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
            )
        except Exception:
            st.warning("lecture times must be hh:mm")

    if st.button("add lecture"):
        st.session_state.lectures.append(
            Lecture(course_name="course 1", day=Day.mon, start=9 * 60, end=10 * 60, multiplier=2.0)
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
    st.subheader("debug data")
    data = InputData(lectures=st.session_state.lectures, prefs=st.session_state.prefs)
    st.json(data.model_dump())
