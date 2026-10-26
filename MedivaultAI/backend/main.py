import os
import io
import json
import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Google GenAI SDK imports
from google import genai
from google.genai import types

# Database imports
from backend.database import init_db, get_db, MedicalRecord, DoctorNote, User

app = FastAPI(title="MediVault AI API", version="2.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()

# --- PYDANTIC SCHEMAS ---

class UserAuthRequest(BaseModel):
    email: str
    password: str


class MedicineItem(BaseModel):
    medication_name: str = Field(description="Name of the medicine or therapeutic drug")
    dosage: str = Field(description="Clinical dosage e.g. 500mg, 10mg, 1 tablet")
    frequency: str = Field(description="Dosing frequency e.g. Twice daily after meals, Once daily at bedtime")
    instructions: str = Field(description="Detailed clinical administration & monitoring instructions e.g. Take with food to reduce GI distress, monitor liver enzymes")


class HealthMetricItem(BaseModel):
    metric_name: str = Field(description="Name of the test metric e.g. Fasting Glucose, HbA1c, Total Cholesterol, Hemoglobin, Blood Pressure")
    value: float = Field(description="Numerical value extracted from test result")
    unit: str = Field(description="Unit of measurement e.g. mg/dL, %, g/dL, mmHg")
    reference_range: str = Field(description="Normal reference range provided in report e.g. 70-99 mg/dL")
    status: str = Field(default="NORMAL", description="Status e.g. NORMAL, ELEVATED, LOW, CRITICAL_WARNING")
    warning_details: Optional[str] = Field(default=None, description="Explanation if marked CRITICAL_WARNING or abnormal")


class DocumentSummary(BaseModel):
    filename: str = Field(description="Original document name or identifier")
    document_type: str = Field(description="Type of medical doc e.g. Lab Report, Prescription, Discharge Summary")
    summary: str = Field(description="Brief summary of this specific document")


class MedicalAnalysisResult(BaseModel):
    patient_identity_match: bool = Field(default=True, description="True if all uploaded documents belong to the exact same patient. False if documents belong to different individuals.")
    identity_error_message: Optional[str] = Field(default=None, description="Message to display if patient identity match fails.")
    summaries: List[DocumentSummary] = Field(default_factory=list, description="Summary per document uploaded")
    medicines: List[MedicineItem] = Field(default_factory=list, description="Extracted active prescription medicines from report")
    recommended_medicines: List[MedicineItem] = Field(default_factory=list, description="MBBS-level clinical therapeutic recommendations (first-line disease-modifying drugs, specific target therapies, OTC, and dosage guidelines)")
    numerical_metrics: List[HealthMetricItem] = Field(default_factory=list, description="Extracted numerical lab metrics")
    consolidated_diagnosis: str = Field(description="Short, bullet-pointed clinical diagnosis highlighting main primary disease/condition names (e.g. • Type 2 Diabetes Mellitus - Uncontrolled, • Mixed Dyslipidemia) and key indicator values.")
    lifestyle_advice: List[str] = Field(default_factory=list, description="Actionable diet, exercise, and clinical monitoring recommendations based on report")
    medical_warnings: List[str] = Field(default_factory=list, description="Critical warnings or flags needing doctor attention")
    doctor_consultation_notice: str = Field(
        default="Medical Consultation Notice: These AI-assisted MBBS-level clinical recommendations and report summaries are provided for informational guidance only. Please consult your certified attending physician or clinical specialist for formal prescription validation and personalized treatment decisions.",
        description="Mandatory advisory notice to consult a certified doctor"
    )


class DoctorNoteCreate(BaseModel):
    user_id: int
    doctor_name: str
    note_date: str
    notes: str


class ChatRequest(BaseModel):
    user_id: int = 1
    messages: List[Dict[str, str]] = Field(default_factory=list, description="Chat history")
    user_message: str


# --- AUTOMATED HEALTH WARNING FLAGS & SAFETY RANGE CHECKER ---

def evaluate_health_metrics(metrics: List[HealthMetricItem]) -> List[HealthMetricItem]:
    evaluated = []
    for m in metrics:
        name_lower = m.metric_name.lower()
        val = m.value
        status = m.status
        warning = m.warning_details

        is_critical = False
        reason = ""

        if "fasting" in name_lower and ("glucose" in name_lower or "sugar" in name_lower):
            if val > 100:
                is_critical = True
                reason = f"Fasting Glucose ({val} {m.unit}) exceeds normal threshold (>100 mg/dL). High risk of prediabetes/diabetes."
        elif ("postprandial" in name_lower or "pp" in name_lower) and ("glucose" in name_lower or "sugar" in name_lower):
            if val > 140:
                is_critical = True
                reason = f"Postprandial Glucose ({val} {m.unit}) exceeds safe threshold (>140 mg/dL)."
        elif "glucose" in name_lower or "sugar" in name_lower:
            if val > 125:
                is_critical = True
                reason = f"Blood Glucose ({val} {m.unit}) is elevated (>125 mg/dL)."
        elif "hba1c" in name_lower or "a1c" in name_lower:
            if val > 5.7:
                is_critical = True
                reason = f"HbA1c ({val}%) is above optimal reference limit (>5.7%). Indicates elevated average blood sugar."
        elif "total cholesterol" in name_lower or ("cholesterol" in name_lower and "ldl" not in name_lower and "hdl" not in name_lower):
            if val > 200:
                is_critical = True
                reason = f"Total Cholesterol ({val} {m.unit}) exceeds healthy limit (>200 mg/dL)."
        elif "ldl" in name_lower:
            if val > 100:
                is_critical = True
                reason = f"LDL Cholesterol ({val} {m.unit}) is elevated (>100 mg/dL)."
        elif "triglyceride" in name_lower or "triglycerides" in name_lower:
            if val > 150:
                is_critical = True
                reason = f"Triglycerides ({val} {m.unit}) exceed normal reference (>150 mg/dL)."
        elif "hemoglobin" in name_lower or name_lower == "hb":
            if val < 12.0:
                is_critical = True
                reason = f"Hemoglobin ({val} {m.unit}) is below normal baseline (<12.0 g/dL). Potential anemia."
        elif "systolic" in name_lower:
            if val > 130:
                is_critical = True
                reason = f"Systolic Blood Pressure ({val} mmHg) is elevated (>130 mmHg)."
        elif "diastolic" in name_lower:
            if val > 80:
                is_critical = True
                reason = f"Diastolic Blood Pressure ({val} mmHg) is elevated (>80 mmHg)."
        elif "tsh" in name_lower or "thyroid" in name_lower:
            if val > 4.5 or val < 0.4:
                is_critical = True
                reason = f"TSH Level ({val} {m.unit}) is outside safe range (0.4 - 4.5 mIU/L)."

        if is_critical:
            status = "CRITICAL_WARNING"
            warning = reason if not warning else f"{warning} | {reason}"

        m.status = status
        m.warning_details = warning
        evaluated.append(m)
    return evaluated


# --- GEMINI CLIENT & RETRY MECHANISM ---

def get_genai_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY environment variable is missing. Please set GEMINI_API_KEY."
        )
    return genai.Client(api_key=api_key)


def process_documents_with_gemini(files_data: List[tuple]) -> MedicalAnalysisResult:
    client = get_genai_client()
    candidate_models = [
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
    ]

    parts = []
    for content, mime_type, fname in files_data:
        parts.append(types.Part.from_bytes(data=content, mime_type=mime_type))
        parts.append(f"Document File Name: {fname}")

    prompt_intro = (
        "You are a Senior MBBS / MD Clinical Pharmacotherapist and Internal Medicine Consultant.\n\n"
        "STRICT PATIENT IDENTITY GUARD:\n"
        "First, verify if ALL uploaded documents belong to the EXACT SAME patient by checking patient name, age, or identity markers across the files.\n"
        "If the uploaded documents belong to DIFFERENT individuals, set `patient_identity_match: false` and set `identity_error_message: \"Error: The uploaded records appear to belong to different individuals. MediVault AI strictly requires all batch-uploaded documents to belong to the same patient. Please upload records for one patient at a time.\"` and leave summaries and metrics empty.\n\n"
        "If all documents belong to the same patient (or single document uploaded):\n"
        "1. Set `patient_identity_match: true`.\n"
        "2. Provide individual document summaries.\n"
        "3. Extract active medicines from prescriptions.\n"
        "4. EXPERT MBBS DOCTOR MEDICINE RECOMMENDATIONS (`recommended_medicines`):\n"
        "   - Act as a trained MBBS/MD physician evaluating the patient's lab metrics, symptoms, and diagnosis.\n"
        "   - Do NOT give generic simple pain relievers like Paracetamol unless specifically indicated for fever/pain.\n"
        "   - Suggest targeted, evidence-based clinical therapeutics and first-line medical guidelines matching the diagnosed condition:\n"
        "     * Prediabetes / Diabetes -> First-line insulin sensitizer (e.g., Metformin 500mg - 1000mg with meal guidance).\n"
        "     * Dyslipidemia / High Cholesterol -> Lipid-lowering statin therapy (e.g., Atorvastatin 10mg - 20mg at bedtime).\n"
        "     * Hypertension -> First-line antihypertensives (e.g., Amlodipine 5mg or Telmisartan 40mg once daily with BP monitoring).\n"
        "     * Anemia / Low Hemoglobin -> Therapeutic oral iron (e.g., Ferrous Ascorbate 100mg + Folic Acid with Vitamin C for absorption).\n"
        "     * Thyroid dysfunction -> Levothyroxine or anti-thyroid therapy as indicated.\n"
        "   - For every recommended drug, provide exact clinical dosage, dosing frequency, and administration & safety instructions.\n"
        "5. Extract all numerical lab metrics with metric name, float value, unit, and reference range.\n"
        "6. Provide a SHORT, BULLET-POINTED consolidated diagnosis (`consolidated_diagnosis`). Do NOT write long paragraphs. List each main primary disease/condition name on its own distinct bullet point (e.g., '• Type 2 Diabetes Mellitus (Uncontrolled - HbA1c 8.1%)', '• Mixed Dyslipidemia (Hypercholesterolemia & High LDL)'), keeping it concise and focused on the main disease names.\n"
        "7. Provide actionable medical lifestyle, diet, and clinical monitoring recommendations.\n"
        "8. Highlight any critical medical warnings or abnormal findings requiring physician review.\n"
        "9. Include a clear doctor consultation notice."
        "10.If no explicit handwritten/printed prescriptions are present in the uploaded files, populate 'aggregated_prescriptions' with standard evidence-based medical treatment guidelines and common first-line medications according to the identified diagnosis (e.g., for Typhoid Fever / Salmonella positive test: list standard antibiotic options like Azithromycin or Ceftriaxone, along with antipyretics like Paracetamol for fever control, clearly labeled as 'Suggested Clinical Treatment Guidelines')."
    )

    last_error = None
    for model_name in candidate_models:
        for attempt in range(3):  # 1 initial + 2 retries
            try:
                if attempt > 0:
                    import time
                    time.sleep(2 * attempt)

                current_prompt = prompt_intro
                if attempt > 0 and last_error:
                    current_prompt += f"\n\n[RETRY ATTEMPT {attempt} NOTICE]: Previous attempt failed with error: {last_error}. Ensure exact matching Pydantic structure."

                response = client.models.generate_content(
                    model=model_name,
                    contents=[current_prompt] + parts,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=MedicalAnalysisResult.model_json_schema(),
                        temperature=0.1
                    )
                )

                raw_json = response.text
                if not raw_json:
                    raise ValueError("Empty response text returned from Gemini API.")

                parsed_dict = json.loads(raw_json)
                result = MedicalAnalysisResult.model_validate(parsed_dict)

                if result.patient_identity_match:
                    # Server-side safety range checker
                    result.numerical_metrics = evaluate_health_metrics(result.numerical_metrics)

                    # Sync critical warnings into medical_warnings list
                    for m in result.numerical_metrics:
                        if m.status == "CRITICAL_WARNING" and m.warning_details:
                            warn_str = f"CRITICAL FLAG: {m.metric_name} = {m.value} {m.unit} ({m.warning_details})"
                            if warn_str not in result.medical_warnings:
                                result.medical_warnings.append(warn_str)

                return result

            except Exception as e:
                last_error = str(e)
                print(f"[Gemini Model '{model_name}' Attempt {attempt + 1} Error]: {e}")
                # If model is exhausted (429) or not found (404), immediately try next candidate model
                if any(err_code in last_error for err_code in ["429", "404", "RESOURCE_EXHAUSTED", "NOT_FOUND"]):
                    break

    raise HTTPException(
        status_code=500,
        detail=f"Failed to parse medical records with Gemini after retry attempts. Error: {last_error}"
    )


# --- REPORTLAB PDF GENERATION ---

def build_pdf_report(record_id: int, filename: str, created_at: str, analysis: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1E3A8A'), spaceAfter=4
    )
    meta_style = ParagraphStyle(
        'DocMeta', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#475569'), spaceAfter=12
    )
    section_heading = ParagraphStyle(
        'SectionHeading', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor('#1E40AF'), spaceBefore=10, spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyTextDark', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#1E293B')
    )
    warning_style = ParagraphStyle(
        'WarningTextDark', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#B91C1C')
    )

    story = []

    # Title & Metadata Header
    story.append(Paragraph("<b>MediVault AI - Consolidated Clinical Summary Report</b>", title_style))
    story.append(Paragraph(f"<b>Record ID:</b> #{record_id} &nbsp;|&nbsp; <b>Source Files:</b> {filename} &nbsp;|&nbsp; <b>Generated Date:</b> {created_at}", meta_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563EB'), spaceAfter=12))

    # Consolidated Diagnosis
    diag = analysis.get("consolidated_diagnosis", "No consolidated diagnosis provided.")
    story.append(Paragraph("<b>🔬 Consolidated Clinical Overview & MBBS Diagnosis</b>", section_heading))
    story.append(Paragraph(diag, body_style))
    story.append(Spacer(1, 10))

    # Medical Warnings
    warnings = analysis.get("medical_warnings", [])
    if warnings:
        story.append(Paragraph("<b>⚠️ Health Warnings & Flagged Metrics</b>", section_heading))
        for w in warnings:
            story.append(Paragraph(f"• <b>CRITICAL WARNING:</b> {w}", warning_style))
        story.append(Spacer(1, 10))

    # Lab Test Metrics Table
    metrics = analysis.get("numerical_metrics", [])
    if metrics:
        story.append(Paragraph("<b>📊 Extracted Lab Test Metrics</b>", section_heading))
        table_data = [["Metric Name", "Value", "Unit", "Ref Range", "Status"]]
        for m in metrics:
            st_val = m.get("status", "NORMAL")
            status_p = Paragraph(f"<b>{st_val}</b>", warning_style if st_val == "CRITICAL_WARNING" else body_style)
            table_data.append([
                Paragraph(m.get("metric_name", ""), body_style),
                Paragraph(str(m.get("value", "")), body_style),
                Paragraph(m.get("unit", ""), body_style),
                Paragraph(m.get("reference_range", "N/A"), body_style),
                status_p
            ])
        t = Table(table_data, colWidths=[140, 60, 60, 140, 140])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#DBEAFE')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 5),
            ('TOPPADDING', (0,0), (-1,0), 5),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Medicines Table
    medicines = analysis.get("medicines", [])
    if medicines:
        story.append(Paragraph("<b>💊 Active Prescription Medicines</b>", section_heading))
        med_data = [["Medication Name", "Dosage", "Frequency", "Instructions"]]
        for med in medicines:
            med_data.append([
                Paragraph(med.get("medication_name", ""), body_style),
                Paragraph(med.get("dosage", ""), body_style),
                Paragraph(med.get("frequency", ""), body_style),
                Paragraph(med.get("instructions", ""), body_style)
            ])
        med_table = Table(med_data, colWidths=[130, 80, 110, 220])
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#D1FAE5')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#065F46')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 5),
            ('TOPPADDING', (0,0), (-1,0), 5),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ]))
        story.append(med_table)
        story.append(Spacer(1, 10))

    # AI Recommended Medicines
    rec_medicines = analysis.get("recommended_medicines", [])
    if rec_medicines:
        story.append(Paragraph("<b>💡 MBBS-Level Recommended Clinical Therapeutics & OTC Guidance</b>", section_heading))
        rec_data = [["Recommended Medicine", "Dosage", "Frequency", "Clinical Instructions & Rationale"]]
        for med in rec_medicines:
            rec_data.append([
                Paragraph(med.get("medication_name", ""), body_style),
                Paragraph(med.get("dosage", ""), body_style),
                Paragraph(med.get("frequency", ""), body_style),
                Paragraph(med.get("instructions", ""), body_style)
            ])
        rec_table = Table(rec_data, colWidths=[130, 80, 110, 220])
        rec_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#FEF3C7')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#92400E')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 5),
            ('TOPPADDING', (0,0), (-1,0), 5),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ]))
        story.append(rec_table)
        story.append(Spacer(1, 10))

    # Lifestyle Guidelines
    lifestyle = analysis.get("lifestyle_advice", [])
    if lifestyle:
        story.append(Paragraph("<b>🩺 Care Guidelines & Lifestyle Recommendations</b>", section_heading))
        for item in lifestyle:
            story.append(Paragraph(f"• {item}", body_style))
        story.append(Spacer(1, 12))

    # Doctor Consultation Advisory Notice
    consultation_notice = analysis.get(
        "doctor_consultation_notice",
        "Medical Consultation Notice: These AI-assisted MBBS clinical recommendations are provided for informational guidance only. Please review this summary with your attending physician or specialist for formal prescription validation."
    )
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#94A3B8'), spaceBefore=8, spaceAfter=8))
    notice_style = ParagraphStyle(
        'DoctorNotice', parent=styles['Normal'], fontSize=8, leading=11, textColor=colors.HexColor('#475569'), alignment=1
    )
    story.append(Paragraph(f"<b>{consultation_notice}</b>", notice_style))

    def draw_decorations(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#2563EB'))
        canvas.setLineWidth(1.5)
        canvas.rect(18, 18, doc.pagesize[0] - 36, doc.pagesize[1] - 36)

        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748B'))
        canvas.drawString(36, 24, "MediVault AI - Confidential Patient Record")
        canvas.drawRightString(doc.pagesize[0] - 36, 24, f"Page {canvas._pageNumber}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_decorations, onLaterPages=draw_decorations)
    buffer.seek(0)
    return buffer.getvalue()


# --- AUTH ENDPOINTS ---

@app.post("/api/v1/register", response_model=Dict[str, Any])
def register_user(req: UserAuthRequest, db: Session = Depends(get_db)):
    email_clean = req.email.strip().lower()
    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    
    new_user = User(
        email=email_clean,
        password=req.password,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": new_user.id, "email": new_user.email}


@app.post("/api/v1/login", response_model=Dict[str, Any])
def login_user(req: UserAuthRequest, db: Session = Depends(get_db)):
    email_clean = req.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean, User.password == req.password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"id": user.id, "email": user.email}


# --- API ENDPOINTS ---

@app.post("/api/v1/analyze-records", response_model=Dict[str, Any])
async def analyze_records(
    files: List[UploadFile] = File(...),
    user_id: int = Form(1),
    db: Session = Depends(get_db)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    files_data = []
    filenames_list = []

    for file in files:
        content = await file.read()
        mime_type = file.content_type or "application/octet-stream"

        if file.filename.lower().endswith(".pdf"):
            mime_type = "application/pdf"
        elif file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            mime_type = "image/png" if file.filename.lower().endswith(".png") else "image/jpeg"

        files_data.append((content, mime_type, file.filename))
        filenames_list.append(file.filename)

    analysis_result = process_documents_with_gemini(files_data)

    if not analysis_result.patient_identity_match:
        error_msg = analysis_result.identity_error_message or "Error: Uploaded records belong to different individuals. Please upload files for the same patient."
        raise HTTPException(status_code=400, detail=error_msg)

    analysis_json_str = analysis_result.model_dump_json()

    combined_filename = ", ".join(filenames_list)
    new_record = MedicalRecord(
        user_id=user_id,
        filename=combined_filename,
        analysis=analysis_json_str,
        created_at=datetime.datetime.utcnow()
    )

    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return {
        "id": new_record.id,
        "filename": new_record.filename,
        "analysis": analysis_result.model_dump(),
        "created_at": new_record.created_at.isoformat()
    }


@app.get("/api/v1/records", response_model=List[Dict[str, Any]])
def get_records(user_id: int = 1, db: Session = Depends(get_db)):
    records = db.query(MedicalRecord).filter(MedicalRecord.user_id == user_id).order_by(MedicalRecord.created_at.desc()).all()
    results = []
    for r in records:
        analysis_dict = {}
        try:
            analysis_dict = json.loads(r.analysis)
        except Exception:
            pass
        results.append({
            "id": r.id,
            "filename": r.filename,
            "analysis": analysis_dict,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""
        })
    return results


@app.get("/api/v1/records/{record_id}", response_model=Dict[str, Any])
def get_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found.")

    analysis_dict = json.loads(record.analysis)
    return {
        "id": record.id,
        "filename": record.filename,
        "analysis": analysis_dict,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else ""
    }


@app.delete("/api/v1/records/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found.")
    db.delete(record)
    db.commit()
    return {"message": f"Record #{record_id} successfully deleted."}


@app.get("/api/v1/download-pdf/{record_id}")
def download_pdf(record_id: int, db: Session = Depends(get_db)):
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found.")

    analysis_dict = json.loads(record.analysis)
    created_at_str = record.created_at.strftime("%Y-%m-%d %H:%M UTC") if record.created_at else "N/A"

    pdf_bytes = build_pdf_report(
        record_id=record.id,
        filename=record.filename,
        created_at=created_at_str,
        analysis=analysis_dict
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=medivault_report_{record_id}.pdf"
        }
    )


@app.post("/api/v1/doctor-notes", response_model=Dict[str, Any])
def create_doctor_note(note: DoctorNoteCreate, db: Session = Depends(get_db)):
    new_note = DoctorNote(
        user_id=note.user_id,
        doctor_name=note.doctor_name,
        note_date=note.note_date,
        notes=note.notes,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return {
        "id": new_note.id,
        "doctor_name": new_note.doctor_name,
        "note_date": new_note.note_date,
        "notes": new_note.notes,
        "created_at": new_note.created_at.strftime("%Y-%m-%d %H:%M")
    }


@app.get("/api/v1/doctor-notes", response_model=List[Dict[str, Any]])
def get_doctor_notes(user_id: int = 1, db: Session = Depends(get_db)):
    notes = db.query(DoctorNote).filter(DoctorNote.user_id == user_id).order_by(DoctorNote.created_at.desc()).all()
    return [
        {
            "id": n.id,
            "doctor_name": n.doctor_name,
            "note_date": n.note_date,
            "notes": n.notes,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else ""
        }
        for n in notes
    ]


@app.delete("/api/v1/doctor-notes/{note_id}")
def delete_doctor_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(DoctorNote).filter(DoctorNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Doctor note not found.")
    db.delete(note)
    db.commit()
    return {"message": f"Doctor note #{note_id} deleted."}


@app.get("/api/v1/health-trends", response_model=Dict[str, List[Dict[str, Any]]])
def get_health_trends(user_id: int = 1, db: Session = Depends(get_db)):
    records = db.query(MedicalRecord).filter(MedicalRecord.user_id == user_id).order_by(MedicalRecord.created_at.asc()).all()
    trends: Dict[str, List[Dict[str, Any]]] = {}

    for r in records:
        date_str = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "Unknown"
        try:
            data = json.loads(r.analysis)
            metrics = data.get("numerical_metrics", [])
            for m in metrics:
                name = m.get("metric_name", "").strip()
                val = m.get("value")
                unit = m.get("unit", "")
                if name and val is not None:
                    if name not in trends:
                        trends[name] = []
                    trends[name].append({
                        "date": date_str,
                        "value": float(val),
                        "unit": unit
                    })
        except Exception:
            continue

    return trends


@app.post("/api/v1/chat/medical")
def medical_chatbot(request: ChatRequest, db: Session = Depends(get_db)):
    client = get_genai_client()

    user_records = db.query(MedicalRecord).filter(MedicalRecord.user_id == request.user_id).order_by(MedicalRecord.created_at.desc()).all()

    patient_context_str = "No medical records uploaded yet."
    if user_records:
        context_items = []
        for r in user_records:
            try:
                data = json.loads(r.analysis)
                diag = data.get("consolidated_diagnosis", "")
                meds = [f"{m.get('medication_name')} ({m.get('dosage')})" for m in data.get("medicines", [])]
                rec_meds = [f"{m.get('medication_name')} ({m.get('dosage')})" for m in data.get("recommended_medicines", [])]
                metrics = [f"{m.get('metric_name')}: {m.get('value')} {m.get('unit')} ({m.get('status')})" for m in data.get("numerical_metrics", [])]
                context_items.append(
                    f"Record #{r.id} ({r.created_at.strftime('%Y-%m-%d')}):\n"
                    f"  - Diagnosis: {diag}\n"
                    f"  - Prescribed Medicines: {', '.join(meds) if meds else 'None'}\n"
                    f"  - Recommended Therapeutics: {', '.join(rec_meds) if rec_meds else 'None'}\n"
                    f"  - Key Metrics: {', '.join(metrics) if metrics else 'None'}"
                )
            except Exception:
                continue
        patient_context_str = "\n".join(context_items)

    system_instruction = (
        "You are MediVault AI's Senior MBBS / MD Clinical Assistant.\n"
        "You have direct authorized access to the logged-in patient's medical records and lab reports stored in their MediVault database.\n\n"
        f"--- LOGGED-IN PATIENT MEDICAL VAULT HISTORY ---\n"
        f"{patient_context_str}\n"
        f"-----------------------------------------------\n\n"
        "Use the patient's medical vault context above to accurately answer questions regarding their specific lab reports, medicines, diagnosis, symptoms, and health guidelines as a trained MBBS physician.\n"
        "Provide expert clinical guidance with precise therapeutic rationale, dosage notes, and clinical monitoring recommendations.\n\n"
        "CRITICAL GUARDRAIL RULE: If the user asks about ANY non-medical or non-health topic (such as programming, software engineering, sports, finance, stocks, entertainment, general math, history, coding, etc.), "
        "you MUST NOT answer the question. Instead, respond EXACTLY with the following sentence and nothing else:\n"
        "\"I am MediVault's clinical assistant, strictly configured to answer health and medical queries. Please ask a health-related question.\"\n\n"
        "MANDATORY DOCTOR CONSULTATION ADVISORY: Always conclude your response with a brief message advising the patient to review these findings with their attending doctor for formal clinical management."
    )

    candidate_models = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]

    user_msg_lower = request.user_message.lower()
    offtopic_keywords = [
        "python", "javascript", "c++", "java", "code", "programming", "sql",
        "crypto", "bitcoin", "stock market", "nba", "nfl", "cricket", "football",
        "movie", "finance", "weather"
    ]
    if any(k in user_msg_lower for k in offtopic_keywords) and not any(h in user_msg_lower for h in ["health", "doctor", "medical", "blood", "sugar", "diet", "disease", "report", "lab", "medicine"]):
        return {"response": "I am MediVault's clinical assistant, strictly configured to answer health and medical queries. Please ask a health-related question."}

    formatted_prompt = ""
    for msg in request.messages:
        role_label = "User" if msg.get("role") == "user" else "Assistant"
        formatted_prompt += f"{role_label}: {msg.get('content', '')}\n"

    formatted_prompt += f"User: {request.user_message}"

    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=formatted_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2
                )
            )
            if response.text:
                return {"response": response.text.strip()}
        except Exception as e:
            print(f"[Chat Model '{model_name}' Error]: {e}")
            continue

    return {"response": "I am MediVault's clinical assistant, strictly configured to answer health and medical queries. Please ask a health-related question."}
