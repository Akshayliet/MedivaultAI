import os
import base64
import requests
import streamlit as st

st.set_page_config(
    page_title="MediVault AI - Personal Health & Medical Vault",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_BASE_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8001")

# --- DARK & LIGHT MODE ADAPTIVE STYLING ---
st.markdown("""
    <style>
    /* Cap sidebar width at 250px */
    [data-testid="stSidebar"] {
        min-width: 250px !important;
        max-width: 250px !important;
        padding-top: 1rem;
    }
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    /* Adaptive Card Container */
    .vault-card {
        border: 1px solid var(--secondary-background-color, #e2e8f0);
        background-color: var(--secondary-background-color, #f8fafc);
        color: var(--text-color, #0f172a);
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 12px;
    }
    /* High contrast Dark & Light mode compatible banner */
    .notice-box-banner {
        border: 2px solid #2563eb;
        border-left: 8px solid #1d4ed8;
        background-color: rgba(37, 99, 235, 0.15);
        color: var(--text-color, #1e293b);
        padding: 14px 18px;
        border-radius: 8px;
        font-size: 14px;
        line-height: 1.5;
        font-weight: 500;
        margin-top: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# Initialize Session State
if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None
if "selected_record_id" not in st.session_state:
    st.session_state.selected_record_id = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "assistant", "content": "Hello! I am MediVault's Senior MBBS Clinical Assistant. I have authorized access to your uploaded medical vault documents. How can I assist you with your health reports today?"}
    ]

# --- HELPER FUNCTIONS FOR AUTH & API CALLS ---

def register_api(email, password):
    try:
        res = requests.post(f"{API_BASE_URL}/api/v1/register", json={"email": email, "password": password}, timeout=5)
        if res.status_code == 200:
            return True, res.json()
        else:
            detail = res.json().get("detail", "Registration failed.")
            return False, detail
    except Exception as e:
        return False, f"Connection error: {e}"

def login_api(email, password):
    try:
        res = requests.post(f"{API_BASE_URL}/api/v1/login", json={"email": email, "password": password}, timeout=5)
        if res.status_code == 200:
            return True, res.json()
        else:
            detail = res.json().get("detail", "Invalid email or password.")
            return False, detail
    except Exception as e:
        return False, f"Connection error: {e}"

def fetch_records(user_id):
    try:
        res = requests.get(f"{API_BASE_URL}/api/v1/records?user_id={user_id}", timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []
def format_diagnosis_bullets(diag_str: str) -> str:
    if not diag_str or diag_str == "N/A":
        return "N/A"
    
    # If already formatted with bullet points, return as is
    if "•" in diag_str or "- " in diag_str or "\n*" in diag_str:
        return diag_str
        
    # Auto-format long paragraph into bullet points for main disease names
    normalized = diag_str.replace(" and concurrent ", ". ").replace(" with concurrent ", ". ").replace(" with ", " — ")
    sentences = [s.strip() for s in normalized.split(". ") if s.strip()]
    
    lines = []
    for s in sentences:
        s_clean = s.strip(".")
        if s_clean:
            lines.append(f"• **{s_clean}**")
            
    return "\n\n".join(lines) if lines else diag_str

def delete_record_api(record_id):
    try:
        res = requests.delete(f"{API_BASE_URL}/api/v1/records/{record_id}", timeout=5)
        return res.status_code == 200
    except Exception:
        return False

def fetch_doctor_notes(user_id):
    try:
        res = requests.get(f"{API_BASE_URL}/api/v1/doctor-notes?user_id={user_id}", timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def save_doctor_note_api(user_id, doctor_name, note_date, notes):
    try:
        payload = {"user_id": user_id, "doctor_name": doctor_name, "note_date": str(note_date), "notes": notes}
        res = requests.post(f"{API_BASE_URL}/api/v1/doctor-notes", json=payload, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

def delete_doctor_note_api(note_id):
    try:
        res = requests.delete(f"{API_BASE_URL}/api/v1/doctor-notes/{note_id}", timeout=5)
        return res.status_code == 200
    except Exception:
        return False

def fetch_health_trends(user_id):
    try:
        res = requests.get(f"{API_BASE_URL}/api/v1/health-trends?user_id={user_id}", timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {}


# --- AUTHENTICATION PORTAL VIEW ---

if not st.session_state.authenticated_user:
    st.title("🛡️ MediVault AI Portal")
    st.caption("Secure Personal Health Knowledge Engine & Vision Analytics")
    
    col_auth_center, _ = st.columns([1.2, 0.8])
    with col_auth_center:
        auth_tab1, auth_tab2 = st.tabs(["🔐 Patient Login", "📝 Register New Account"])
        
        with auth_tab1:
            st.subheader("Login to your MediVault")
            with st.form("login_form"):
                login_email = st.text_input("Gmail / Email Address", placeholder="name@gmail.com")
                login_password = st.text_input("Password", type="password")
                btn_login = st.form_submit_button("🔓 Log In", use_container_width=True, type="primary")
                
                if btn_login:
                    if not login_email or not login_password:
                        st.error("Please provide both email and password.")
                    else:
                        success, data_or_err = login_api(login_email, login_password)
                        if success:
                            st.session_state.authenticated_user = data_or_err
                            st.success(f"Welcome back, {data_or_err['email']}!")
                            st.rerun()
                        else:
                            st.error(data_or_err)
                            
        with auth_tab2:
            st.subheader("Create New Patient Vault Account")
            with st.form("register_form"):
                reg_email = st.text_input("Gmail / Email Address", placeholder="patient@gmail.com")
                reg_password = st.text_input("Create Password", type="password")
                btn_reg = st.form_submit_button("✨ Register Account", use_container_width=True, type="primary")
                
                if btn_reg:
                    if not reg_email or not reg_password:
                        st.error("Please provide both email and password.")
                    else:
                        success, data_or_err = register_api(reg_email, reg_password)
                        if success:
                            st.session_state.authenticated_user = data_or_err
                            st.success("Account created successfully! Logging in...")
                            st.rerun()
                        else:
                            st.error(data_or_err)
                            
    st.stop()


# --- AUTHENTICATED DASHBOARD VIEW ---

user_info = st.session_state.authenticated_user
current_user_id = user_info["id"]

# Sidebar Header & User Profile
st.sidebar.title("🏥 MediVault AI")
st.sidebar.caption(f"👤 Patient: **{user_info['email']}**")

if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state.authenticated_user = None
    st.session_state.selected_record_id = None
    st.session_state.chat_messages = []
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📤 Upload Reports")
uploaded_files = st.sidebar.file_uploader(
    "Choose medical PDF or images",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key="file_uploader"
)

if st.sidebar.button("⚡ Analyze Documents", use_container_width=True, type="primary"):
    if not uploaded_files:
        st.sidebar.warning("Please select at least one document.")
    else:
        with st.sidebar.spinner("Processing Vision AI & Identity Guard..."):
            try:
                files_payload = [
                    ("files", (uf.name, uf.getvalue(), uf.type or "application/octet-stream"))
                    for uf in uploaded_files
                ]
                res = requests.post(
                    f"{API_BASE_URL}/api/v1/analyze-records",
                    files=files_payload,
                    data={"user_id": current_user_id},
                    timeout=120
                )
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.selected_record_id = data["id"]
                    st.sidebar.success("Records analyzed & saved!")
                    st.rerun()
                elif res.status_code == 400:
                    st.sidebar.error(res.json().get("detail", "Upload error."))
                else:
                    st.sidebar.error(f"Analysis failed: {res.text}")
            except Exception as e:
                st.sidebar.error(f"Connection error: {e}")

st.sidebar.markdown("---")
st.sidebar.subheader("🗄️ Vault Records")

search_query = st.sidebar.text_input("🔍 Search", "", placeholder="Filename or ID...")
filter_option = st.sidebar.selectbox("Filter", ["All", "Lab Reports", "Prescriptions"])

all_records = fetch_records(current_user_id) or []

filtered_records = []
for r in all_records:
    analysis = r.get("analysis", {})
    doc_summaries = analysis.get("summaries", [])
    doc_types = " ".join([ds.get("document_type", "").lower() for ds in doc_summaries])
    
    if filter_option == "Lab Reports" and "lab" not in doc_types and "report" not in doc_types:
        if not any("glucose" in str(m).lower() or "cholesterol" in str(m).lower() for m in analysis.get("numerical_metrics", [])):
            continue
    elif filter_option == "Prescriptions" and "prescription" not in doc_types:
        if not analysis.get("medicines"):
            continue

    if search_query:
        q = search_query.lower()
        if q not in r.get("filename", "").lower() and q not in str(r.get("id")):
            continue

    filtered_records.append(r)

if not filtered_records:
    st.sidebar.info("No records saved yet.")
else:
    for rec in filtered_records:
        rec_id = rec["id"]
        created_at = rec.get("created_at", "")
        col_btn, col_del = st.sidebar.columns([0.8, 0.2])
        is_active = (st.session_state.selected_record_id == rec_id)
        btn_label = f"{'🟢 ' if is_active else ''}#{rec_id} | {created_at[:10]}"
        
        if col_btn.button(btn_label, key=f"rec_btn_{rec_id}", use_container_width=True):
            st.session_state.selected_record_id = rec_id
            st.rerun()
            
        if col_del.button("🗑️", key=f"del_btn_{rec_id}"):
            if delete_record_api(rec_id):
                if st.session_state.selected_record_id == rec_id:
                    st.session_state.selected_record_id = None
                st.rerun()

# Main Dashboard
st.title("🛡️ MediVault AI Dashboard")

tab_vault, tab_trends, tab_notes, tab_chat = st.tabs([
    "📂 Medical Vault & Detailed Analysis",
    "📈 Health Metric Trends",
    "📝 Doctor Consultation Logger",
    "💬 AI Clinical Assistant"
])

# Tab 1: Detailed Dual-Panel View
with tab_vault:
    selected_id = st.session_state.selected_record_id
    if not selected_id and all_records:
        selected_id = all_records[0]["id"]
        st.session_state.selected_record_id = selected_id

    if not selected_id:
        st.info("👈 Upload your medical records or select a historical record from the sidebar vault to view detailed insights.")
    else:
        current_rec = next((r for r in all_records if r["id"] == selected_id), None)
        if current_rec:
            analysis = current_rec.get("analysis", {})
            st.subheader(f"📋 Record Summary #{current_rec['id']} - {current_rec.get('filename', '')}")
            st.caption(f"Uploaded on: {current_rec.get('created_at', '')}")
            st.markdown("---")
            
            col_left, col_right = st.columns([1.15, 0.85])
            
            with col_left:
                sub_tab1, sub_tab2, sub_tab3, sub_tab4, sub_tab5 = st.tabs([
                    "🔬 Diagnosis", "💊 Medicines & Clinical Advice", "🩺 Care Guidelines", "⚠️ Warnings & Flags", "📝 Doctor Notes"
                ])
                
                with sub_tab1:
                    st.markdown("### 🔬 MBBS-Level Consolidated Diagnosis")
                    raw_diag = analysis.get("consolidated_diagnosis", "N/A")
                    formatted_diag = format_diagnosis_bullets(raw_diag)
                    st.markdown(formatted_diag)
                    st.markdown("#### Document Summaries")
                    for s in analysis.get("summaries", []):
                        with st.expander(f"📄 {s.get('filename')} ({s.get('document_type')})", expanded=True):
                            st.write(s.get("summary", ""))

                with sub_tab2:
                    st.markdown("### 💊 Active Prescription Medicines")
                    medicines = analysis.get("medicines", [])
                    if medicines:
                        formatted_meds = [
                            {
                                "Medication Name": m.get("medication_name", ""),
                                "Dosage": m.get("dosage", ""),
                                "Frequency": m.get("frequency", ""),
                                "Instructions": m.get("instructions", "")
                            }
                            for m in medicines
                        ]
                        st.dataframe(formatted_meds, use_container_width=True, hide_index=True)
                    else:
                        st.info("No active prescription medications extracted.")
                        
                    st.markdown("### 💡 MBBS Doctor Recommended Therapeutics & Clinical Guidance")
                    rec_meds = analysis.get("recommended_medicines", [])
                    if rec_meds:
                        formatted_rec_meds = [
                            {
                                "Recommended Medicine": m.get("medication_name", ""),
                                "Dosage": m.get("dosage", ""),
                                "Frequency": m.get("frequency", ""),
                                "Clinical Instructions & Rationale": m.get("instructions", "")
                            }
                            for m in rec_meds
                        ]
                        st.dataframe(formatted_rec_meds, use_container_width=True, hide_index=True)
                    else:
                        st.info("No additional clinical therapeutics recommended.")

                with sub_tab3:
                    st.markdown("### 🩺 Actionable Care & Lifestyle Guidelines")
                    for item in analysis.get("lifestyle_advice", []):
                        st.markdown(f"• **{item}**")

                with sub_tab4:
                    st.markdown("### ⚠️ Health Warnings & Critical Flags")
                    for w in analysis.get("medical_warnings", []):
                        st.error(f"**CRITICAL WARNING:** {w}")
                    
                    st.markdown("#### 🧪 Extracted Numerical Lab Metrics & Range Checker")
                    for m in analysis.get("numerical_metrics", []):
                        if m.get("status") == "CRITICAL_WARNING":
                            st.markdown(
                                f"🔴 :red[**CRITICAL WARNING**] &nbsp;|&nbsp; **{m.get('metric_name')}**: :red[**{m.get('value')} {m.get('unit')}**] "
                                f"(Ref Range: `{m.get('reference_range')}`)\n\n"
                                f"> :red[**{m.get('warning_details')}**]"
                            )
                            st.markdown("---")
                        else:
                            st.markdown(f"🟢 **{m.get('metric_name')}**: `{m.get('value')} {m.get('unit')}` (Ref Range: `{m.get('reference_range')}`)")

                with sub_tab5:
                    st.markdown("### 📝 Doctor Consultation Notes")
                    notes_list = fetch_doctor_notes(current_user_id)
                    for dn in notes_list:
                        with st.expander(f"Dr. {dn['doctor_name']} ({dn['note_date']})"):
                            st.write(dn['notes'])

            with col_right:
                st.markdown("### 📄 Formal PDF Report Preview")
                pdf_url = f"{API_BASE_URL}/api/v1/download-pdf/{selected_id}"
                try:
                    pdf_res = requests.get(pdf_url, timeout=10)
                    if pdf_res.status_code == 200:
                        pdf_bytes = pdf_res.content
                        st.download_button(
                            label="📥 Download Clinical PDF Summary",
                            data=pdf_bytes,
                            file_name=f"medivault_report_{selected_id}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            type="primary"
                        )
                        st.markdown("<br>", unsafe_allow_html=True)
                        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                        pdf_display = (
                            f'<iframe src="data:application/pdf;base64,{base64_pdf}" '
                            f'width="100%" height="600" type="application/pdf" style="border: 1px solid #cbd5e1; border-radius: 8px;"></iframe>'
                        )
                        st.markdown(pdf_display, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Failed to fetch PDF: {e}")
                    
            # Highly Visible Doctor Consultation Advisory Banner (Dark & Light Mode Compatible)
            notice_text = analysis.get(
                "doctor_consultation_notice",
                "Medical Consultation Notice: These AI-assisted MBBS-level clinical recommendations and report summaries are provided for informational guidance only. Please consult your certified attending physician or clinical specialist for formal prescription validation and personalized treatment decisions."
            )
            st.info(f"👨‍⚕️ **DOCTOR CONSULTATION NOTICE:** {notice_text}")

# Tab 2: Health Metric Trends
with tab_trends:
    st.header("📈 Aggregated Health Metric Trends Over Time")
    trends_data = fetch_health_trends(current_user_id)
    if trends_data:
        selected_metric = st.selectbox("Select Health Metric to Plot", list(trends_data.keys()))
        if selected_metric:
            data_points = trends_data[selected_metric]
            formatted_points = [
                {
                    "Date": dp.get("date", ""),
                    "Value": dp.get("value", 0),
                    "Unit": dp.get("unit", "")
                }
                for dp in data_points
            ]
            st.dataframe(formatted_points, hide_index=True, use_container_width=True)
            
            chart_data = {dp.get("date", f"Point {i}"): dp.get("value", 0) for i, dp in enumerate(data_points)}
            st.line_chart(chart_data, use_container_width=True)
    else:
        st.info("No trend data available yet for your account.")

# Tab 3: Doctor Consultation Logger
with tab_notes:
    st.header("📝 Doctor Consultation Logger")
    col_form, col_list = st.columns([1, 1])
    with col_form:
        with st.form("doc_form", clear_on_submit=True):
            d_name = st.text_input("Doctor Name")
            d_date = st.date_input("Visit Date")
            d_notes = st.text_area("Prescription Notes & Consultation Summary")
            if st.form_submit_button("💾 Save Note", type="primary", use_container_width=True):
                if save_doctor_note_api(current_user_id, d_name, d_date, d_notes):
                    st.success("Doctor consultation note saved!")
                    st.rerun()
    with col_list:
        for n in fetch_doctor_notes(current_user_id):
            with st.expander(f"Dr. {n['doctor_name']} ({n['note_date']})"):
                st.write(n["notes"])
                if st.button("🗑️ Delete", key=f"dn_{n['id']}"):
                    delete_doctor_note_api(n['id'])
                    st.rerun()

# Tab 4: AI Clinical Assistant (Context-Aware to User Vault)
with tab_chat:
    st.header("💬 AI Clinical Assistant (MBBS Specialist Persona)")
    st.info("🔒 Connected to your personal MediVault database. Asking clinical questions will automatically reference your uploaded lab reports and medical history.")
    
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
    if user_input := st.chat_input("Ask a question about your lab reports, medicines, or health..."):
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)
            
        with st.chat_message("assistant"):
            with st.spinner("Analyzing your clinical records & query..."):
                try:
                    payload = {
                        "user_id": current_user_id,
                        "messages": st.session_state.chat_messages[:-1],
                        "user_message": user_input
                    }
                    res = requests.post(f"{API_BASE_URL}/api/v1/chat/medical", json=payload, timeout=30)
                    bot_reply = res.json().get("response", "")
                except Exception as e:
                    bot_reply = f"Error: {e}"
                st.write(bot_reply)
                st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
