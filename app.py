import streamlit as st

from scheduler.models import Course

st.set_page_config(page_title="v0.1.1", layout="wide")
st.title("school schedule v0.1.1")

if "courses" not in st.session_state:
    st.session_state.courses = [Course(name="course 1", weekly_target_minutes=180)]

st.subheader("courses")

for idx, c in enumerate(list(st.session_state.courses)):
    col1, col2, col3 = st.columns([2,2,1])
    with col1:
        name = st.text_input(f"name #{idx+1}", value=c.name, key=f"course_name_{idx}")
    with col2:
        mins = st.number_input(
            f"weekly target minutes #{idx+1}",
            min_value=0,
            step=30,
            value=int(c.weekly_target_minutes),
            key=f"course_mins_{idx}",
        )
    with col3:
        if st.button("remove", key=f"course_remove_{idx}"):
            st.session_state.courses.pop(idx)
            st.rerun()

    st.session_state.courses[idx] = Course(name=name.strip() or f"course {idx}+1", weekly_target_minutes=int(mins))

if st.button("add course"):
    st.session_state.courses.append(Course(name=f"course {len(st.session_state.courses)+1}", weekly_target_minutes=180))
    st.rerun()

st.divider()
st.write("current_data:")
st.json([c.model_dump() for c in st.session_state.courses])