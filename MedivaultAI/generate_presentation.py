import sys

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
except ImportError:
    print("python-pptx library is not installed. Run 'pip install python-pptx' to generate the PPTX file.")
    sys.exit(1)


def create_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]

    # Colors
    NAVY = RGBColor(30, 58, 138)
    BLUE = RGBColor(37, 99, 235)
    DARK_GRAY = RGBColor(30, 41, 59)
    LIGHT_BG = RGBColor(248, 250, 252)
    WHITE = RGBColor(255, 255, 255)
    RED = RGBColor(185, 28, 28)
    GREEN = RGBColor(6, 95, 70)

    def add_header(slide, title_text, category_text="MEDIVAULT AI PLATFORM"):
        # Top banner
        banner = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.1))
        banner.fill.solid()
        banner.fill.fore_color.rgb = NAVY
        banner.line.color.rgb = NAVY

        tf = banner.text_frame
        tf.margin_left = Inches(0.8)
        tf.margin_top = Inches(0.15)
        
        p0 = tf.paragraphs[0]
        p0.text = category_text.upper()
        p0.font.size = Pt(10)
        p0.font.bold = True
        p0.font.color.rgb = RGBColor(147, 197, 253)

        p1 = tf.add_paragraph()
        p1.text = title_text
        p1.font.size = Pt(22)
        p1.font.bold = True
        p1.font.color.rgb = WHITE

    # --- SLIDE 1: Title Slide ---
    slide1 = prs.slides.add_slide(blank_layout)
    bg1 = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = NAVY
    bg1.line.color.rgb = NAVY

    tf1 = bg1.text_frame
    tf1.margin_left = Inches(1.0)
    tf1.margin_top = Inches(2.2)

    p = tf1.paragraphs[0]
    p.text = "🏥 MediVault AI"
    p.font.size = Pt(48)
    p.font.bold = True
    p.font.color.rgb = WHITE

    p_sub = tf1.add_paragraph()
    p_sub.text = "Production-Ready Personal Health Knowledge Engine & Multi-Report Vision AI"
    p_sub.font.size = Pt(22)
    p_sub.font.color.rgb = RGBColor(191, 219, 254)

    p_meta = tf1.add_paragraph()
    p_meta.text = "\nFastAPI • Streamlit • SQLAlchemy • Google GenAI SDK (Gemini 3.8 Flash) • ReportLab"
    p_meta.font.size = Pt(14)
    p_meta.font.color.rgb = RGBColor(147, 197, 253)

    # --- SLIDE 2: Executive Summary & Problem/Solution ---
    slide2 = prs.slides.add_slide(blank_layout)
    add_header(slide2, "Executive Summary: Problem & Solution Overview")

    # Problem Box
    box_prob = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.2))
    box_prob.fill.solid()
    box_prob.fill.fore_color.rgb = RGBColor(254, 242, 242)
    box_prob.line.color.rgb = RED
    tf_p = box_prob.text_frame
    tf_p.margin_left = Inches(0.4)
    tf_p.margin_top = Inches(0.3)
    p = tf_p.paragraphs[0]
    p.text = "❌ Key Healthcare Challenges"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = RED

    bullets_p = [
        "Fragmented & Unorganized Medical Records: Patients struggle to track lab reports across multiple visits.",
        "Complex Clinical Jargon: Critical lab flags (glucose, lipids, HbA1c) are hard for patients to interpret.",
        "Prescription Confusion: Lack of structured active medicine schedules and dosage tracking.",
        "Patient Identity Mismatches: High risk of mixing family medical documents in digital uploads."
    ]
    for b in bullets_p:
        p_b = tf_p.add_paragraph()
        p_b.text = f"• {b}"
        p_b.font.size = Pt(13)
        p_b.font.color.rgb = DARK_GRAY

    # Solution Box
    box_sol = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.2))
    box_sol.fill.solid()
    box_sol.fill.fore_color.rgb = RGBColor(236, 253, 245)
    box_sol.line.color.rgb = GREEN
    tf_s = box_sol.text_frame
    tf_s.margin_left = Inches(0.4)
    tf_s.margin_top = Inches(0.3)
    p = tf_s.paragraphs[0]
    p.text = "✅ MediVault AI Solution"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = GREEN

    bullets_s = [
        "Multi-Report Vision OCR: Parses PDFs, JPEGs, and PNGs in a single request using Gemini 3.8 Flash.",
        "Same-Patient Identity Guard: Verifies document consistency across batch uploads.",
        "Automated Safety Range Checker: Highlights out-of-range metrics with CRITICAL_WARNING status.",
        "MBBS Doctor Persona: Generates condition-specific clinical therapeutic recommendations (e.g., Metformin for Prediabetes).",
        "Context-Aware Patient Vault Chatbot: Answers queries using stored patient history."
    ]
    for b in bullets_s:
        p_b = tf_s.add_paragraph()
        p_b.text = f"• {b}"
        p_b.font.size = Pt(13)
        p_b.font.color.rgb = DARK_GRAY

    # --- SLIDE 3: Key Features & Architectural Capabilities ---
    slide3 = prs.slides.add_slide(blank_layout)
    add_header(slide3, "Core System Capabilities & Key Features")

    features = [
        ("🔐 Patient Auth Portal", "Secure login/registration system providing isolated database vaults per user."),
        ("👁️ Vision OCR & Retries", "Extracts diagnosis, lab metrics, and medicines with automated Pydantic retries."),
        ("🛡️ Patient Identity Guard", "Ensures batch-uploaded records belong to the exact same patient before saving."),
        ("⚠️ Range Checker Engine", "Evaluates Fasting Glucose, HbA1c, Cholesterol, and BP against clinical reference limits."),
        ("🩺 MBBS Therapeutics", "Acts as a trained physician suggesting first-line evidence-based clinical drugs."),
        ("📄 ReportLab PDF Export", "Generates clinical PDFs with document borders, tables, and mandatory advisory footers.")
    ]

    for i, (title, desc) in enumerate(features):
        col = i % 3
        row = i // 3
        x = Inches(0.8 + col * 3.9)
        y = Inches(1.6 + row * 2.6)
        card = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, Inches(3.6), Inches(2.3))
        card.fill.solid()
        card.fill.fore_color.rgb = LIGHT_BG
        card.line.color.rgb = BLUE
        tf_c = card.text_frame
        tf_c.margin_left = Inches(0.2)
        tf_c.margin_top = Inches(0.2)
        
        p = tf_c.paragraphs[0]
        p.text = title
        p.font.size = Pt(15)
        p.font.bold = True
        p.font.color.rgb = NAVY
        
        p_d = tf_c.add_paragraph()
        p_d.text = desc
        p_d.font.size = Pt(12)
        p_d.font.color.rgb = DARK_GRAY

    # Save Presentation
    output_filename = "MediVault_AI_Presentation.pptx"
    prs.save(output_filename)
    print(f"Presentation generated successfully: {output_filename}")


if __name__ == "__main__":
    create_presentation()
