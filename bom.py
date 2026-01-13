# app.py
import streamlit as st
from pathlib import Path
import json, uuid, time, os
from datetime import datetime
import pandas as pd
import plotly.express as px

# ---------- Config ----------
st.set_page_config(page_title="BOM Space ERP", layout="wide", initial_sidebar_state="collapsed")

BASE = Path(__file__).parent
DATA_FILE = BASE / "sample_data.json"
UPLOAD_DIR = BASE / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Data helpers ----------
def load_data():
    if not DATA_FILE.exists():
        # minimal structure if missing
        init = {"users": [], "projects": [], "uploads": [], "messages": [], "dashboards": []}
        DATA_FILE.write_text(json.dumps(init, indent=2))
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, default=str)

def find_user(name, role):
    """Finds a user by name and role from JSON"""
    d = load_data()
    for u in d["users"]:
        if u["name"].lower() == name.lower() and u["role"] == role:
            return u
    return None


def add_upload(project_id, project_name, team, uploaded_by, file_obj, final=False):
    d = load_data()
    ts = datetime.utcnow().isoformat()
    fname = f"{uuid.uuid4().hex}_{file_obj.name}"
    path = UPLOAD_DIR / fname
    with open(path, "wb") as f:
        f.write(file_obj.getbuffer())
    entry = {
        "id": (max([u["id"] for u in d.get("uploads", [])], default=0) + 1),
        "project_id": project_id,
        "project_name": project_name,
        "team": team,
        "uploaded_by": uploaded_by,
        "filename": fname,
        "original_name": file_obj.name,
        "ts": ts,
        "final": bool(final)
    }
    d.setdefault("uploads", []).append(entry)
    save_data(d)
    return entry

def replace_upload(upload_id, file_obj, uploaded_by):
    d = load_data()
    for u in d.get("uploads", []):
        if u["id"] == upload_id:
            # remove old file if exists
            old_path = UPLOAD_DIR / u["filename"]
            try:
                if old_path.exists():
                    old_path.unlink()
            except Exception:
                pass
            # write new file, keep same id and metadata updated
            fname = f"{uuid.uuid4().hex}_{file_obj.name}"
            with open(UPLOAD_DIR / fname, "wb") as f:
                f.write(file_obj.getbuffer())
            u["filename"] = fname
            u["original_name"] = file_obj.name
            u["uploaded_by"] = uploaded_by
            u["ts"] = datetime.utcnow().isoformat()
            save_data(d)
            return u
    return None

def remove_upload(upload_id):
    d = load_data()
    new_uploads = []
    for u in d.get("uploads", []):
        if u["id"] == upload_id:
            # delete file on disk if possible
            try:
                p = UPLOAD_DIR / u["filename"]
                if p.exists():
                    p.unlink()
            except Exception:
                pass
            continue
        new_uploads.append(u)
    d["uploads"] = new_uploads
    save_data(d)

def get_uploads_for_project(project_id):
    d = load_data()
    return [u for u in d.get("uploads", []) if u["project_id"] == project_id]

def save_message(frm, to, project, team, text):
    d = load_data()
    note = {"from": frm, "to": to, "project": project, "team": team, "text": text, "ts": datetime.utcnow().isoformat()}
    d.setdefault("messages", []).append(note)
    save_data(d)

def get_messages(project=None, team=None):
    d = load_data()
    msgs = d.get("messages", [])
    if project:
        msgs = [m for m in msgs if m.get("project") == project]
    if team:
        msgs = [m for m in msgs if m.get("team") == team]
    return msgs

def save_dashboard(cfg):
    d = load_data()
    d.setdefault("dashboards", []).append(cfg)
    save_data(d)

# ---------- UI theme ----------
st.markdown("""
<style>
body { background: radial-gradient(circle at top, #0f2027, #203a43, #2c5364); color: #e6f2ff; }
div.block-container { background-color: rgba(255,255,255,0.03); border-radius:12px; padding:18px; }
h1.center { text-align:center; color:#76e0ff; text-shadow: 0 0 8px rgba(118,224,255,0.3); }
.small-rocket { text-align:center; font-size:14px; color:#9ef3ff; }
</style>
""", unsafe_allow_html=True)

# ---------- Auth ----------
if 'user' not in st.session_state:
    st.markdown("<h1 class='center'>🚀 Welcome to BOM Space ERP</h1>", unsafe_allow_html=True)
    st.markdown("<p class='small-rocket'>Preparing your launchpad...</p>", unsafe_allow_html=True)
    # login controls in sidebar (only when not logged in)
    with st.sidebar:
        st.header("Login")
        role_choice = st.selectbox("Login role", ["member","team_lead","project_lead","admin","superadmin"])
        username = st.text_input("Username (name)")
        pin = st.text_input("PIN (4-digit)", type="password")
        if st.button("Login"):
            user = find_user(username.strip(), role_choice)  # now uses role
            if not user:
                st.error("User not found for this role. Check name and role in JSON.")
            else:
                if pin.strip() == user.get("pin"):
                    with st.spinner("🛰 Initializing Space Console..."):
                        time.sleep(1.0)
                    st.session_state['user'] = user
                    st.rerun()
                else:
                    st.error("Invalid PIN")

    st.stop()

user = st.session_state['user']

st.markdown(f"<h2 class='center'>🚀 Hello, {user['name']} ({user['role']})</h2>", unsafe_allow_html=True)

# ---------- Project label swap: show "Project 1" style names ----------
d = load_data()
# create mapping project_id -> "Project N"
project_display_map = {}
for idx, p in enumerate(d.get("projects", []), start=1):
    project_display_map[p["id"]] = f"Project {idx}"
# inverse map to lookup project by display name
display_to_project = {v: p for p_id, v in project_display_map.items() for p in d.get("projects", []) if p["id"]==p_id}

# fallback if mapping empty, build from list order
if not project_display_map and d.get("projects"):
    for idx, p in enumerate(d["projects"], start=1):
        project_display_map[p["id"]] = f"Project {idx}"
        display_to_project[f"Project {idx}"] = p

# ---------- Navigation tabs ----------
tabs = ["Personal", "Central", "Analysis", "Messenger"]
if user['role'] in ("project_lead", "admin", "superadmin"):
    tabs.insert(2, "Final BOM")
if user['role'] in ("admin", "superadmin"):
    tabs.append("Assigning")
    tabs.append("Admin")

tab = st.selectbox("Portal", tabs)

# ---------- PERSONAL: upload, view, edit, remove (all roles allowed depending on permission) ----------
if tab == "Personal":
    st.header("Personal Portal")
    # available projects: if user has team, only projects that include team; else all
    projects = [p for p in d.get("projects", []) if not user.get("team") or user.get("team") in p.get("teams", [])]
    if not projects:
        st.info("No projects assigned. Contact admin.")
    else:
        # show projects as "Project N"
        proj_display_names = [project_display_map.get(p["id"], p["name"]) for p in projects]
        sel_proj_display = st.selectbox("Select Project", proj_display_names)
        # find real project object
        proj = None
        for p in projects:
            if project_display_map.get(p["id"], p["name"]) == sel_proj_display:
                proj = p
                break
        sel_team = st.selectbox("Select Team", proj["teams"])
        uploaded_file = st.file_uploader("Upload BOM (CSV/XLSX)", type=["csv","xls","xlsx"], key="personal_uploader")
        if st.button("Save Upload", key="personal_save"):
            if not uploaded_file:
                st.error("Select a file.")
            else:
                entry = add_upload(proj["id"], sel_proj_display, sel_team, user["name"], uploaded_file)
                st.success("Upload saved.")
                st.write("Uploaded at:", entry["ts"])
        st.markdown("### Your uploads")
        ups = [u for u in d.get("uploads", []) if u["uploaded_by"] == user["name"]]
        ups = sorted(ups, key=lambda x: x["ts"], reverse=True)
        if ups:
            df = pd.DataFrame([{"id":u["id"], "project":u["project_name"], "team":u["team"], "file":u["original_name"], "ts":u["ts"], "final":u.get("final", False)} for u in ups])
            st.dataframe(df)
            for u in ups:
                cols = st.columns([3,1,1,1,1])
                cols[0].write(f"{u['original_name']} — {u['project_name']} / {u['team']} (uploaded: {u['ts']})")
                # view (open in new tab) — HTML anchor link to file path
                import base64
                file_path = UPLOAD_DIR / u["filename"]
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        data = f.read()
                    b64 = base64.b64encode(data).decode()
                    mime = "application/octet-stream"
                    view_html = f'<a href="data:{mime};base64,{b64}" download="{u["original_name"]}" target="_blank">Open in new tab</a>'
                    cols[1].markdown(view_html, unsafe_allow_html=True)
                else:
                    cols[1].write("File missing")

                # download
                try:
                    data_bytes = (UPLOAD_DIR / u["filename"]).read_bytes()
                    cols[2].download_button(label="Download", data=data_bytes, file_name=u["original_name"], key=f"personal_dl_{u['id']}")
                except Exception:
                    cols[2].write("File missing")
                # edit (replace) — allowed for uploader, team lead, project lead, admin, superadmin
                can_edit = False
                if user["role"] in ("project_lead", "admin", "superadmin"):
                    can_edit = True
                if user["role"] == "team_lead" and user.get("team") == u["team"]:
                    can_edit = True
                if user["name"] == u["uploaded_by"]:
                    can_edit = True
                if can_edit:
                    if cols[3].button("Edit (replace)", key=f"personal_edit_{u['id']}"):
                        st.session_state[f"editing_{u['id']}"] = True
                    if st.session_state.get(f"editing_{u['id']}", False):
                        new_file = cols[4].file_uploader("Choose replacement", type=["csv","xls","xlsx"], key=f"replace_{u['id']}")
                        if new_file and cols[4].button("Apply Replacement", key=f"apply_replace_{u['id']}"):
                            replace_upload(u["id"], new_file, user["name"])
                            st.success("Replaced upload.")
                            st.session_state.pop(f"editing_{u['id']}", None)
                            st.rerun()

                # remove (similar permissions)
                if can_edit:
                    if cols[4].button("Remove", key=f"personal_rm_{u['id']}"):
                        remove_upload(u["id"])
                        st.success("Upload removed.")
                        st.rerun()

        else:
            st.info("No uploads found.")

# ---------- CENTRAL-PORTAL: ----------
elif tab == "Central":
    st.header("Central Portal - Team uploads (all members listed)")
    proj_options = d.get("projects", []) if user["role"] in ("admin","superadmin") else [p for p in d.get("projects", []) if not user.get("team") or user.get("team") in p.get("teams", [])]
    if not proj_options:
        st.info("No projects available.")
    else:
        # show as Project N
        proj_display_list = [project_display_map.get(p["id"], p["name"]) for p in proj_options]
        sel_proj_display = st.selectbox("Select Project", proj_display_list, key="central_proj_select")
        proj = None
        for p in proj_options:
            if project_display_map.get(p["id"], p["name"]) == sel_proj_display:
                proj = p
                break
        # show all uploads grouped by team and person
        uploads = [u for u in d.get("uploads", []) if u["project_id"] == proj["id"]]
        if not uploads:
            st.info("No uploads for this project.")
        else:
            # group by team -> uploader
            teams = proj.get("teams", [])
            for team in teams:
                st.markdown(f"### Team: {team}")
                team_uploads = [u for u in uploads if u["team"] == team]
                if not team_uploads:
                    st.write("No uploads for this team.")
                    continue
                # show a table of all uploads in this team
                df = pd.DataFrame([{"id":u["id"], "file":u["original_name"], "by":u["uploaded_by"], "ts":u["ts"], "final":u.get("final", False)} for u in team_uploads])
                st.dataframe(df)
                for u in team_uploads:
                    cols = st.columns([3,1,1,1,1])
                    cols[0].write(f"{u['original_name']} — by {u['uploaded_by']} at {u['ts']}")
                    # view upload
                    import base64
                    file_path = UPLOAD_DIR / u["filename"]
                    if file_path.exists():
                        with open(file_path, "rb") as f:
                            data = f.read()
                        b64 = base64.b64encode(data).decode()
                        mime = "application/octet-stream"
                        view_html = f'<a href="data:{mime};base64,{b64}" download="{u["original_name"]}" target="_blank">Open in new tab</a>'
                        cols[1].markdown(view_html, unsafe_allow_html=True)
                    else:
                        cols[1].write("File missing")

                    # download with unique key
                    try:
                        data_bytes = (UPLOAD_DIR / u["filename"]).read_bytes()
                        cols[2].download_button("Download", data_bytes, file_name=u["original_name"], key=f"central_dl_{u['id']}")
                    except Exception:
                        cols[2].write("File missing")
                    # edit / replace permission: team lead for that team, project lead, admin, superadmin
                    can_edit = False
                    if user["role"] in ("project_lead","admin","superadmin"):
                        can_edit = True
                    if user["role"] == "team_lead" and user.get("team") == team:
                        can_edit = True
                    if can_edit:
                        # Edit
                        if cols[3].button("Edit (replace)", key=f"central_edit_{u['id']}"):
                            st.session_state[f"central_edit_{u['id']}"] = True
                        if st.session_state.get(f"central_edit_{u['id']}", False):
                            new_file = cols[4].file_uploader("Replace file", type=["csv","xls","xlsx"], key=f"central_replace_{u['id']}")
                            if new_file and cols[4].button("Apply", key=f"central_apply_{u['id']}"):
                                replace_upload(u["id"], new_file, user["name"])
                                st.success("Replaced.")
                                st.session_state.pop(f"central_edit_{u['id']}", None)
                                st.rerun()

                        # Remove
                        if cols[4].button("Remove", key=f"central_rm_{u['id']}"):
                            remove_upload(u["id"])
                            st.success("Removed.")
                            st.rerun()

# ---------- FINAL BOM ----------
elif tab == "Final BOM":
    st.header("🚀 Final BOM Portal")

    # Everyone can view Final BOMs
    d = load_data()
    proj_options = d.get("projects", [])
    proj_display_list = [project_display_map.get(p["id"], f"Project {p['id']}") for p in proj_options]
    sel_proj_display = st.selectbox("Select Project", proj_display_list, key="final_proj")

    proj = None
    for p in proj_options:
        if project_display_map.get(p["id"], f"Project {p['id']}") == sel_proj_display:
            proj = p
            break

    # Final uploads for this project
    final_uploads = [u for u in d.get("uploads", []) if u["project_id"] == proj["id"] and u.get("final")]
    st.markdown("### 🛰️ Final BOMs")

    if final_uploads:
        for u in final_uploads:
            cols = st.columns([3, 1, 1, 1])
            cols[0].write(f"📄 {u['original_name']} — uploaded by {u['uploaded_by']} at {u['ts']}")

            # --- VIEW (Open in New Tab) ---
            file_path = (UPLOAD_DIR / u["filename"])
           

            # --- DOWNLOAD ---
            try:
                data_bytes = file_path.read_bytes()
                cols[1].download_button(
                    "⬇️ Download",
                    data_bytes,
                    file_name=u["original_name"],
                    key=f"final_dl_{u['id']}"
                )
            except Exception:
                cols[1].write("File missing")

            # --- ROLE-BASED EDIT & REMOVE ---
            if user["role"] in ("project_lead", "admin", "superadmin"):
                if cols[2].button("✏️ Edit / Replace", key=f"final_edit_{u['id']}"):
                    st.session_state[f"final_edit_{u['id']}"] = True

                if st.session_state.get(f"final_edit_{u['id']}", False):
                    new_file = st.file_uploader(
                        "Replace Final BOM",
                        type=["csv", "xls", "xlsx"],
                        key=f"final_replace_{u['id']}"
                    )
                    if new_file and st.button("Apply Final Replace", key=f"final_apply_{u['id']}"):
                        replace_upload(u["id"], new_file, user["name"])
                        d2 = load_data()
                        for uu in d2.get("uploads", []):
                            if uu["id"] == u["id"]:
                                uu["final"] = True
                        save_data(d2)
                        st.success("✅ Final BOM replaced successfully!")
                        st.session_state.pop(f"final_edit_{u['id']}", None)
                        st.rerun()

                # Optional: Add Remove
                if cols[3].button("🗑️ Remove", key=f"final_rm_{u['id']}"):
                    try:
                        os.remove(file_path)
                        d["uploads"] = [x for x in d["uploads"] if x["id"] != u["id"]]
                        save_data(d)
                        st.success("Removed Final BOM successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error removing: {e}")
            else:
                cols[3].write("—")

    else:
        st.info("No Final BOMs yet for this project.")

    # --- PROJECT LEAD CAN UPLOAD NEW FINAL BOM ---
    if user["role"] == "project_lead":
        new_final = st.file_uploader(
            "📤 Upload Final BOM (Project Lead Only)",
            type=["csv", "xls", "xlsx"],
            key="pl_final"
        )
        if new_final and st.button("Upload Final BOM", key="pl_final_upload"):
            entry = add_upload(
                proj["id"],
                project_display_map.get(proj["id"], proj["name"]),
                user.get("team") or "",
                user["name"],
                new_final,
                final=True
            )
            st.success("🚀 Final BOM uploaded successfully!")


# ---------- ANALYSIS (Plotly + dashboard save) ----------
elif tab == "Analysis":
    st.header("Analysis Portal (Plotly)")
    proj_options = d.get("projects", []) if user["role"] in ("admin","superadmin") else [p for p in d.get("projects", []) if not user.get("team") or user.get("team") in p.get("teams", [])]
    if not proj_options:
        st.info("No projects available.")
    else:
        proj_display_list = [project_display_map.get(p["id"], p["name"]) for p in proj_options]
        sel_proj_display = st.selectbox("Project", proj_display_list, key="analysis_proj")
        proj = None
        for p in proj_options:
            if project_display_map.get(p["id"], p["name"]) == sel_proj_display:
                proj = p
                break
        sel_team = st.selectbox("Team", proj["teams"], key="analysis_team")
        uploads = [u for u in d.get("uploads", []) if u["project_id"] == proj["id"] and u["team"] == sel_team]
        choice = st.selectbox("Choose upload to analyze", ["<Upload new>"] + [u["original_name"] for u in uploads], key="analysis_choice")
        file_to_analyze = None
        if choice != "<Upload new>":
            u = next(x for x in uploads if x["original_name"] == choice)
            file_to_analyze = UPLOAD_DIR / u["filename"]
        new_file = st.file_uploader("Or upload a file now", type=["csv","xls","xlsx"], key="analysis_new")
        if new_file:
            # save as persistent upload first
            entry = add_upload(proj["id"], sel_proj_display, sel_team, user["name"], new_file)
            file_to_analyze = UPLOAD_DIR / entry["filename"]
        if file_to_analyze:
            try:
                if str(file_to_analyze).lower().endswith(".csv"):
                    df = pd.read_csv(file_to_analyze)
                else:
                    df = pd.read_excel(file_to_analyze)
                st.markdown("**Preview**")
                st.dataframe(df.head())
                st.markdown("**Summary**")
                st.dataframe(df.describe(include='all').fillna(''))
                # chart builder
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                all_cols = df.columns.tolist()
                st.markdown("### Build a chart")
                chart_type = st.selectbox("Chart type", ["Histogram", "Line", "Bar", "Scatter", "Pie"], key="chart_type")
                x_col = None; y_col = None; agg_func = None
                if chart_type in ("Histogram", "Pie"):
                    x_col = st.selectbox("Column", numeric_cols + all_cols, key="chart_x")
                else:
                    x_col = st.selectbox("X-axis", all_cols, key="chart_x2")
                    y_col = st.selectbox("Y-axis (numeric)", numeric_cols, key="chart_y2")
                if chart_type in ("Bar","Line","Scatter"):
                    fig = px.line(df, x=x_col, y=y_col) if chart_type=="Line" else (px.bar(df, x=x_col, y=y_col) if chart_type=="Bar" else px.scatter(df, x=x_col, y=y_col))
                elif chart_type=="Histogram":
                    fig = px.histogram(df, x=x_col)
                else:  # Pie
                    # for pie, use value counts
                    vc = df[x_col].value_counts().reset_index()
                    vc.columns = ["category", "count"]
                    fig = px.pie(vc, names="category", values="count")
                st.plotly_chart(fig, use_container_width=True)
                # save dashboard config
                st.markdown("### Save dashboard configuration")
                dash_name = st.text_input("Dashboard name")
                if st.button("Save dashboard"):
                    cfg = {"name": dash_name or f"{proj['name']}-{sel_team}-{datetime.utcnow().isoformat()}", "project_id": proj["id"], "team": sel_team, "file": str(file_to_analyze.name), "chart": {"type": chart_type, "x": x_col, "y": y_col}}
                    save_dashboard(cfg)
                    st.success("Dashboard saved.")
                # list saved dashboards for this project/team
                st.markdown("#### Saved dashboards")
                saved = [s for s in d.get("dashboards", []) if s.get("project_id") == proj["id"] and s.get("team")==sel_team]
                for s in saved:
                    st.write(f"- {s.get('name')} — {s.get('chart')}")
            except Exception as e:
                st.error("Failed to parse file: " + str(e))

# ---------- MESSENGER ----------
elif tab == "Messenger":
    st.header("Messenger")
    proj_options = d.get("projects", []) if user["role"] in ("admin","superadmin") else [p for p in d.get("projects", []) if not user.get("team") or user.get("team") in p.get("teams", [])]
    if not proj_options:
        st.info("No projects available")
    else:
        proj_display_list = [project_display_map.get(p["id"], p["name"]) for p in proj_options]
        sel_proj_display = st.selectbox("Project", proj_display_list, key="msg_proj")
        proj = None
        for p in proj_options:
            if project_display_map.get(p["id"], p["name"]) == sel_proj_display:
                proj = p
                break
        teams = proj.get("teams", [])
        if user["role"] == "team_lead":
            teams = [user.get("team")]
        sel_team = st.selectbox("Team", teams, key="msg_team")
        members = [u for u in d.get("users", []) if u.get("team") == sel_team]
        recipient_list = [m["name"] for m in members] + ["All"]
        recipient = st.selectbox("Message to", recipient_list, key="msg_to")
        msg_text = st.text_area("Message", key="msg_text")
        if st.button("Send Message", key="msg_send"):
            if msg_text.strip():
                to_user = recipient if recipient != "All" else None
                save_message(user["name"], to_user, sel_proj_display, sel_team, msg_text.strip())
                st.success("Message sent")
                st.rerun()

            else:
                st.error("Enter a message")
        st.markdown("#### Recent messages")
        msgs = get_messages(project=sel_proj_display, team=sel_team)
        relevant = [m for m in msgs if m.get("to") in (None, user["name"])]
        if relevant:
            for m in relevant[-50:]:
                st.write(f"**{m['ts']}** — *{m['from']}* → *{m.get('to') or 'All'}*: {m['text']}")
        else:
            st.info("No messages yet.")

# ---------- ASSIGNING ----------

PROJECTS = [f"Project {i}" for i in range(1, 6)]
TEAMS = [
    "Design",
    "Separation",
    "Mechanism",
    "Manufacturing/Methods",
    "Tooling",
    "PPC",
    "Program",
    "Quality",
    "Purchases & Stores",
    "Finance",
    "Configuration"
]
if tab == "Assigning":
    st.header("Assigning (Admin)")
    if user["role"] not in ("admin", "superadmin"):
        st.error("Access denied")
    else:
        users = d.get("users", [])
        if not users:
            st.info("No users available.")
        else:
            # --- Select user ---
            sel_name = st.selectbox("Select User", [u["name"] for u in users], key="assign_user")
            sel_user = next(u for u in users if u["name"] == sel_name)

            # --- Select role ---
            roles = ["member", "team_lead", "project_lead", "admin", "superadmin"]
            new_role = st.selectbox(
                "Select Role",
                roles,
                index=roles.index(sel_user.get("role", "member")) if sel_user.get("role") in roles else 0,
                key="assign_role"
            )

            # --- Select team ---
            new_team = st.selectbox("Select Team", TEAMS, key="assign_team")

            # --- Select project ---
            new_project = st.selectbox("Select Project", PROJECTS, key="assign_project")

            # --- Custom PIN for login ---
            new_pin = st.text_input("Set / Reset PIN (optional)", type="password", key="assign_pin")

            # --- Assign / Update user ---
            if st.button("Assign / Update", key="assign_apply"):
                for u in d.get("users", []):
                    if u["name"] == sel_name:
                        if "roles" not in u:
                            u["roles"] = []

                        # Add new role entry (user can have multiple)
                        new_entry = {
                            "role": new_role,
                            "team": new_team,
                            "project": new_project,
                            "pin": new_pin.strip() if new_pin else u.get("pin")
                        }

                        # Avoid duplicate roles
                        if not any(r["role"] == new_role and r["team"] == new_team and r["project"] == new_project for r in u["roles"]):
                            u["roles"].append(new_entry)

                        # Also update main fields (for backward compatibility)
                        u["role"] = new_role
                        u["team"] = new_team
                        u["project"] = new_project
                        if new_pin:
                            u["pin"] = new_pin.strip()

                save_data(d)
                st.success(f"Updated assignments for {sel_name}")



            # --- Display user’s assigned roles ---
            if sel_user.get("roles"):
                st.markdown("### Assigned Roles")
                for idx, r in enumerate(sel_user["roles"], start=1):
                    st.write(f"{idx}. **Role:** {r['role']} | **Team:** {r['team']} | **Project:** {r['project']} | **PIN:** {r.get('pin', 'N/A')}")


# ---------- ADMIN ----------
elif tab == "Admin":
    st.header("Admin Portal")
    if user["role"] not in ("admin", "superadmin"):
        st.error("Access denied")
    else:
        for u in d.get("users", []):
            cols = st.columns([3,1,1,1])
            cols[0].write(f"{u['name']} — {u['role']} — team: {u.get('team')}")
            if cols[1].button("Remove", key=f"admin_rm_{u['id']}"):
                if user["role"] != "superadmin":
                    st.error("Only superadmin can remove users.")
                else:
                    d["users"] = [x for x in d["users"] if x["id"] != u["id"]]
                    save_data(d)
                    st.rerun()

            if cols[2].button("Reset PIN", key=f"admin_rst_{u['id']}"):
                for x in d.get("users", []):
                    if x["id"] == u["id"]:
                        x["pin"] = "0000"
                save_data(d)
                st.success("PIN reset to 0000")
            # add more admin controls as needed

# ---------- LOGOUT ----------
st.markdown("<div style='position:fixed; right:20px; bottom:20px;'>", unsafe_allow_html=True)
if st.button("Logout", key="logout_btn"):
    if 'user' in st.session_state:
        del st.session_state['user']
    st.rerun()

st.markdown("</div>", unsafe_allow_html=True)
