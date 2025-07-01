from dataclasses import dataclass
from datetime import date
from typing import Dict
from typing import Optional
import urllib.parse

import sqlalchemy as sa
import streamlit as st
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table
from streamlit.connections import SQLConnection

st.set_page_config(
    page_title="Task Tracker",
    page_icon="📃",
    initial_sidebar_state="collapsed",
)

# Inject custom CSS
# def local_css(file_name):
#     with open(file_name) as f:
#         st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# local_css("style.css")

def inject_css():
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

inject_css()


##################################################
### MODELS
##################################################

TABLE_NAME = "todo"
SESSION_STATE_KEY_TODOS = "todos_data"


@dataclass
class Todo:
    id: Optional[int] = None
    title: str = ""
    description: Optional[str] = None
    label: Optional[str] = None 
    requester: Optional[str] = None
    priority: Optional[str] = "medium"
    status: Optional[str] = "to-do"
    created_at: Optional[date] = None
    due_at: Optional[date] = None
    done: bool = False

    # Class method to easily create a Todo object from a database row
    @classmethod
    def from_row(cls, row):
        if row:
            return cls(**row._mapping)
        return None
    
##################################################
@dataclass
class Subtask:
    id: Optional[int] = None
    todo_id: int = None
    title: str = ""
    done: bool = False

    @classmethod
    def from_row(cls, row):
        if row:
            return cls(**row._mapping)
        return None



# Use st.cache_resource to define the database table structure only once
# and share it across all user sessions connected to this Streamlit server process.
# This avoids redefining the table structure on every script rerun or for every user.
@st.cache_resource
def connect_table():
    metadata_obj = MetaData()
    todo_table = Table(
        TABLE_NAME,
        metadata_obj,
        Column("id", Integer, primary_key=True),
        Column("title", String(30)),
        Column("description", String, nullable=True),
        Column("label", String(20), nullable=True),
        Column("priority", String(10), nullable=True, default="medium"),
        Column("status", String(20), nullable=True, default="to-do"),
        Column("requester", String(50), nullable=True),
        Column("created_at", Date),
        Column("due_at", Date, nullable=True),
        Column("done", Boolean, nullable=True),
    )
    subtask_table = Table(
        "subtasks",
        metadata_obj,
        Column("id", Integer, primary_key=True),
        Column("todo_id", Integer),  # Foreign key to todo
        Column("title", String(100)),
        Column("done", Boolean, default=False),
    )
    return metadata_obj, todo_table, subtask_table


##################################################
### DATA INTERACTION
##################################################


def check_table_exists(connection: SQLConnection, table_name: str) -> bool:
    inspector = sa.inspect(connection.engine)
    return inspector.has_table(table_name)


def load_all_todos(connection: SQLConnection, table: Table) -> Dict[int, Todo]:
    """Fetches all todos from the DB and returns as a dict keyed by id."""
    stmt = sa.select(table).order_by(table.c.id)
    with connection.session as session:
        result = session.execute(stmt)
        todos = [Todo.from_row(row) for row in result.all()]
        return {todo.id: todo for todo in todos if todo}


def load_todo(connection: SQLConnection, table: Table, todo_id: int) -> Optional[Todo]:
    """Fetches a single todo by id from the DB."""
    stmt = sa.select(table).where(table.c.id == todo_id)
    with connection.session as session:
        result = session.execute(stmt)
        row = result.first()
        return Todo.from_row(row)


##################################################
### STREAMLIT CALLBACKS
##################################################

# These functions handle the logic when a user interacts with a widget (button, form).
# The usual workflow for those callbacks is:
# 1. Get form input data through st.session_state form widget keys,
# 2. Perform database operations,
# 3. Refresh session state by reading from database.


def create_todo_callback(connection: SQLConnection, table: Table):
    # 1. Get form input data
    if not st.session_state.new_todo_form__title:
        st.toast("Title empty, not adding todo")
        return

    new_todo_data = {
        "title": st.session_state.new_todo_form__title,
        "description": st.session_state.new_todo_form__description,
        "requester": st.session_state.new_todo_form__requester,
        "label": st.session_state.new_todo_form__label,
        "priority": st.session_state.new_todo_form__priority,
        "status": st.session_state.new_todo_form__status,
        "created_at": date.today(),
        "due_at": st.session_state.new_todo_form__due_date,
        "done": False,
    }

    # 2. Perform database operations
    stmt = table.insert().values(**new_todo_data)
    with connection.session as session:
        # probably needs a try...except but eh
        session.execute(stmt)
        session.commit()

    # 3. Refresh session state from database
    st.session_state[SESSION_STATE_KEY_TODOS] = load_all_todos(conn, todo_table)


def open_update_callback(todo_id: int):
    st.session_state[f"currently_editing__{todo_id}"] = True


def cancel_update_callback(todo_id: int):
    st.session_state[f"currently_editing__{todo_id}"] = False


def update_todo_callback(connection: SQLConnection, table: Table, todo_id: int):
    # 1. Get form input data
    updated_values = {
        "title": st.session_state[f"edit_todo_form_{todo_id}__title"],
        "description": st.session_state[f"edit_todo_form_{todo_id}__description"],
        "status": st.session_state[f"edit_todo_form_{todo_id}__status"],
        "requester": st.session_state[f"edit_todo_form_{todo_id}__requester"],
        "due_at": st.session_state[f"edit_todo_form_{todo_id}__due_date"],
    }

    if not updated_values["title"]:
        st.toast("Title cannot be empty.", icon="⚠️")
        st.session_state[f"currently_editing__{todo_id}"] = True
        return

    # 2. Perform database operations
    stmt = table.update().where(table.c.id == todo_id).values(**updated_values)
    with connection.session as session:
        session.execute(stmt)
        session.commit()

    # 3. Refresh session state from database
    st.session_state[SESSION_STATE_KEY_TODOS][todo_id] = load_todo(
        connection, table, todo_id
    )
    st.session_state[f"currently_editing__{todo_id}"] = False


def delete_todo_callback(connection: SQLConnection, table: Table, todo_id: int):
    # 1. Get form input data

    # 2. Perform database operations
    stmt = table.delete().where(table.c.id == todo_id)
    with connection.session as session:
        session.execute(stmt)
        session.commit()

    # 3. Refresh session state from database
    st.session_state[SESSION_STATE_KEY_TODOS] = load_all_todos(conn, todo_table)
    st.session_state[f"currently_editing__{todo_id}"] = False


def mark_done_callback(connection: SQLConnection, table: Table, todo_id: int):
    # 1. Get form input data
    current_done_status = st.session_state[SESSION_STATE_KEY_TODOS][todo_id].done

    # 2. Perform database operations
    stmt = (
        table.update().where(table.c.id == todo_id).values(done=not current_done_status)
    )
    with connection.session as session:
        session.execute(stmt)
        session.commit()

    # 3. Refresh session state from database
    st.session_state[SESSION_STATE_KEY_TODOS][todo_id] = load_todo(
        connection, table, todo_id
    )

# --- Subtask Callbacks ---#
def load_subtasks(connection, subtask_table, todo_id):
    stmt = sa.select(subtask_table).where(subtask_table.c.todo_id == todo_id)
    with connection.session as session:
        result = session.execute(stmt)
        return [Subtask.from_row(row) for row in result.fetchall()]

def create_subtask(connection, subtask_table, todo_id, title):
    stmt = subtask_table.insert().values(todo_id=todo_id, title=title, done=False)
    with connection.session as session:
        session.execute(stmt)
        session.commit()

def toggle_subtask_done(connection, subtask_table, subtask_id, new_done):
    stmt = subtask_table.update().where(subtask_table.c.id == subtask_id).values(done=new_done)
    with connection.session as session:
        session.execute(stmt)
        session.commit()

def mark_all_subtasks_done(connection, subtask_table, todo_id):
    stmt = subtask_table.update().where(subtask_table.c.todo_id == todo_id).values(done=True)
    with connection.session as session:
        session.execute(stmt)
        session.commit()



##################################################
### UI WIDGETS
##################################################

# These functions render parts of the UI.
# They take data like a Todo object and display it using Streamlit widgets.


def generate_gcal_link(title: str, description: str, due_date: date) -> str:
    base = "https://calendar.google.com/calendar/render"
    start = due_date.strftime("%Y%m%dT090000Z")
    end = due_date.strftime("%Y%m%dT100000Z")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "details": description or "No description provided.",
        "dates": f"{start}/{end}",
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


# Function to display a single todo item as a card


def todo_card(connection: SQLConnection, todo_table: Table, subtask_table: Table, todo_item: Todo):
    todo_id = todo_item.id

    with st.container(border=True):
        # Top row: Title and Meta Info
        title_col, meta_col = st.columns([3, 2])
        with title_col:
            display_title = todo_item.title
            if todo_item.done:
                display_title = f"~~{display_title}~~"
            st.subheader(display_title)

        with meta_col:
            meta_items = []

            if todo_item.label:
                meta_items.append(f"🏷️ <strong>{todo_item.label.title()}</strong>")
            if todo_item.priority:
                meta_items.append(f"🔵 <strong>{todo_item.priority.title()}</strong>")
            if todo_item.status:
                meta_items.append(f"📌 <strong>{todo_item.status.title()}</strong>")

            # Join all with vertical bars
            meta_text = " &nbsp;|&nbsp; ".join(meta_items)

            st.markdown(f"<div style='text-align: right; font-size: 14px;'>{meta_text}</div>", unsafe_allow_html=True)


        # Description
        display_description = todo_item.description or ":grey[*No description*]"
        if todo_item.done:
            display_description = f"~~{display_description}~~"
        st.markdown(display_description)

        # Requester and Due Date
        display_requester = todo_item.requester or ":grey[*No requester*]"
        display_due_date = f"Due {todo_item.due_at.strftime('%Y-%m-%d')}"
        if todo_item.done:
            display_due_date = f"~~{display_due_date}~~"
        st.markdown(f"**Requester:** {display_requester}")
        st.caption(display_due_date)

        calendar_link = generate_gcal_link(todo_item.title, todo_item.description, todo_item.due_at)

        st.markdown(
            f'<a href="{calendar_link}" target="_blank"><button style="background-color:#e0e0e0; color:#333; font-size:12px; padding:4px 8px; border:none; border-radius:4px;">📅 Add to Google Calendar</button></a>',
            unsafe_allow_html=True,
        )


        # === Main Actions ===
        done_col, edit_col, delete_col = st.columns(3)
        done_col.button(
            "Done" if not todo_item.done else "Redo",
            icon=":material/check_circle:",
            key=f"display_todo_{todo_id}__done",
            on_click=mark_done_callback,
            args=(connection, todo_table, todo_id),
            type="secondary" if todo_item.done else "primary",
            use_container_width=True,
        )
        edit_col.button(
            "Edit",
            icon=":material/edit:",
            key=f"display_todo_{todo_id}__edit",
            on_click=open_update_callback,
            args=(todo_id,),
            disabled=todo_item.done,
            use_container_width=True,
        )
        if delete_col.button(
            "Delete",
            icon=":material/delete:",
            key=f"display_todo_{todo_id}__delete",
            use_container_width=True,
        ):
            delete_todo_callback(connection, todo_table, todo_id)
            st.rerun(scope="app")

        st.divider()

        # === Subtasks ===
        # === Subtasks ===
        subtasks = load_subtasks(connection, subtask_table, todo_id)
        with st.expander("Subtasks", expanded=True):
            if subtasks:
                st.markdown("**Subtasks:**")

                completed_count = sum(sub.done for sub in subtasks)
                total_count = len(subtasks)
                st.progress(completed_count / total_count, text=f"{completed_count}/{total_count} completed")

                for sub in subtasks:
                    label_text = f"~~{sub.title}~~" if sub.done else sub.title
                    checkbox_key = f"subtask_{sub.id}"

                    if checkbox_key not in st.session_state:
                        st.session_state[checkbox_key] = sub.done

                    new_done = st.checkbox(
                        label=label_text,
                        value=sub.done,
                        key=checkbox_key,
                    )

                    # Only trigger if value actually changed
                    if new_done != sub.done:
                        toggle_subtask_done(connection, subtask_table, sub.id, new_done)
                        st.rerun()


                # Mark all done
                if completed_count < total_count:
                    if st.button("✅ Mark All Done", key=f"mark_all_done_{todo_id}"):
                        mark_all_subtasks_done(connection, subtask_table, todo_id)
                        st.rerun()
            else:
                st.caption("No subtasks yet.")

            # Subtask Form
            with st.form(f"new_subtask_form_{todo_id}", clear_on_submit=True):
                new_subtask = st.text_input("Add subtask", key=f"new_subtask_{todo_id}")
                if st.form_submit_button("Add"):
                    if new_subtask.strip():
                        create_subtask(connection, subtask_table, todo_id, new_subtask.strip())
                        st.rerun()




# Function to display the inline form for editing an existing todo item
def todo_edit_widget(connection: SQLConnection, table: Table, todo_item: Todo):
    todo_id = todo_item.id

    with st.form(f"edit_todo_form_{todo_id}"):
        st.text_input(
            "Title", value=todo_item.title, key=f"edit_todo_form_{todo_id}__title"
        )
        st.text_area(
            "Description",
            value=todo_item.description,
            key=f"edit_todo_form_{todo_id}__description",
        )

        st.date_input(
            "Due date",
            value=todo_item.due_at,
            key=f"edit_todo_form_{todo_id}__due_date",
        )

        submit_col, cancel_col = st.columns(2)
        submit_col.form_submit_button(
            "Save",
            icon=":material/save:",
            type="primary",
            on_click=update_todo_callback,
            args=(connection, table, todo_id),
            use_container_width=True,
        )

        cancel_col.form_submit_button(
            "Cancel",
            on_click=cancel_update_callback,
            args=(todo_id,),
            use_container_width=True,
        )


# If a script rerun by widget interaction is triggered from a @st.fragment function
# Instead of a script rerun, Streamlit only reruns the fragment function

# Any widget interaction and callback that occurs within this function
# only affects the database state and session state of the input todo item
# so the fragment reruns to reload and display the state of the todo item


# This function is used to display a todo item, either as a card or an edit widget
# It checks if the user is currently editing the todo item and displays the appropriate UI.
@st.fragment
def todo_component(connection: SQLConnection, todo_table: Table, subtask_table: Table, todo_id: int):
    todo_item = st.session_state[SESSION_STATE_KEY_TODOS][todo_id]
    currently_editing = st.session_state.get(f"currently_editing__{todo_id}", False)

    if not currently_editing:
        todo_card(connection, todo_table, subtask_table, todo_item)
    else:
        todo_edit_widget(connection, todo_table, todo_item)



##################################################
### USER INTERFACE
##################################################

st.title("Task Tracker")

#conn = st.connection("todo_db", ttl=5 * 60)
conn = st.connection("supabase_db", ttl=5 * 60)
metadata_obj, todo_table, subtask_table = connect_table()


# --- Sidebar for Admin Actions ---
with st.sidebar:
    st.header("Admin")
    #--- Admin Actions ---
    if st.button(
        "Create table",
        type="secondary",
        help="Creates the 'todo' table if it doesn't exist.",
    ):
        metadata_obj.create_all(conn.engine)
        st.toast("Todo table created successfully!", icon="✅")
    
    st.subheader("Filter Tasks")


    filter_priority = st.multiselect(
        "Priority", options=["low", "medium", "high"], default=["low", "medium", "high"]
    )

    filter_status = st.multiselect(
        "Status",
        options=["to-do", "in progress", "completed", "blocked"],
        default=["to-do", "in progress", "completed", "blocked"]
    )

    hide_done = st.checkbox("Hide completed tasks", value=False)

    st.subheader("Sort Tasks By")
    sort_by = st.selectbox("Sort by", ["due_at", "created_at"], index=0)
    sort_ascending = st.radio("Order", ["Ascending", "Descending"], index=0)

    st.subheader("Filter by Label")

    filter_label = st.multiselect(
        "Label",
        options=["work", "school", "personal", "others"],
        default=["work", "school", "personal", "others"]
    )


# --- Admin Actions ---
    

    st.divider()
    st.subheader("Session State Debug", help="Is not updated by fragment rerun!")
    st.json(st.session_state)


# --- Display list of Todo items ---

# 1. Check if database table exists. Else redirect to admin sidebar for creation
if not check_table_exists(conn, TABLE_NAME):
    st.warning("Create table from admin sidebar", icon="⚠")
    st.stop()

# 2. Load database items into session state.
#    This happens on the first run or if the state was cleared.
if SESSION_STATE_KEY_TODOS not in st.session_state:
    with st.spinner("Loading Todos..."):
        st.session_state[SESSION_STATE_KEY_TODOS] = load_all_todos(conn, todo_table)


# 3. Display Todos from Session State
current_todos: Dict[int, Todo] = st.session_state.get(SESSION_STATE_KEY_TODOS, {})

# Convert to list for filtering
filtered_todos = list(current_todos.values())

# Apply filters
filtered_todos = [
    todo for todo in filtered_todos
    if todo.label in filter_label and
       todo.priority in filter_priority and
       todo.status in filter_status and
       (not hide_done or not todo.done)
]
# If no todos match the filters, show a message
if not filtered_todos and current_todos:
    st.warning("No todos match the selected filters.", icon="⚠️")
elif not current_todos:
    st.info("No tasks in the database yet. Add one below 👇", icon="ℹ️")


# Apply sorting
reverse_sort = sort_ascending == "Descending"
filtered_todos.sort(key=lambda x: getattr(x, sort_by) or date.max, reverse=reverse_sort)

# Render filtered todos
for todo in filtered_todos:
    todo_id = todo.id
    if f"currently_editing__{todo_id}" not in st.session_state:
        st.session_state[f"currently_editing__{todo_id}"] = False
    todo_component(conn, todo_table, subtask_table, todo_id)


# --- Display create Todo form ---

with st.form("new_todo_form", clear_on_submit=True):
    st.subheader(":material/add_circle: New todo")
    st.text_input("Title", key="new_todo_form__title", placeholder="Add your task")
    st.text_area(
        "Description",
        key="new_todo_form__description",
        placeholder="Add more details...",
    )
    st.text_input("Requester", key="new_todo_form__requester", placeholder="Requested by")

    # 🔄 Make dropdowns side-by-side
    col1, col2, col3 = st.columns(3)
    with col1:
        st.selectbox("Priority", ["low", "medium", "high"], key="new_todo_form__priority", index=1)
    with col2:
        st.selectbox("Status", ["to-do", "in progress", "blocked", "done"], key="new_todo_form__status", index=0)
    with col3:
        st.selectbox("Label", ["work", "school", "personal", "others"], key="new_todo_form__label")


    date_col, submit_col = st.columns((1, 2), vertical_alignment="bottom")
    date_col.date_input("Due date", key="new_todo_form__due_date")
    submit_col.form_submit_button(
        "Add todo",
        on_click=create_todo_callback,
        args=(conn, todo_table),
        type="primary",
        use_container_width=True,
    )