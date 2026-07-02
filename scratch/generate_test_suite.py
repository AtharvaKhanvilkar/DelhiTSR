import os
import sys

# Add scratch dir to path so we can import the doc text modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch

from doc_texts_part1 import DOC_01_TEXT, DOC_02_TEXT
from doc_texts_part2 import DOC_03_TEXT, DOC_04_TEXT
from doc_texts_part3 import DOC_05_TEXT, DOC_06_TEXT
from doc_texts_part4 import DOC_07_TEXT, DOC_08_TEXT

project_path = r"c:\Users\Heramb Khanvilkar\Desktop\tsr-engine\workspaces\TEST_37805aa3"
os.makedirs(project_path, exist_ok=True)

def generate_pdf(filename, text):
    """Generate a PDF with the given text content, using A4 pages."""
    filepath = os.path.join(project_path, filename)
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    margin = 60
    y = height - margin
    line_height = 14
    max_width = width - 2 * margin

    for line in text.split('\n'):
        # Wrap long lines
        if len(line) > 95:
            words = line.split(' ')
            current_line = ''
            for word in words:
                test = current_line + (' ' if current_line else '') + word
                if len(test) > 95:
                    c.drawString(margin, y, current_line)
                    y -= line_height
                    if y < margin:
                        c.showPage()
                        y = height - margin
                    current_line = word
                else:
                    current_line = test
            if current_line:
                c.drawString(margin, y, current_line)
                y -= line_height
                if y < margin:
                    c.showPage()
                    y = height - margin
        else:
            c.drawString(margin, y, line)
            y -= line_height
            if y < margin:
                c.showPage()
                y = height - margin

    c.save()
    print(f"  Generated: {filename}")

# Map filenames to document texts - chronological chain
documents = [
    ("01_DDA_Conveyance_Deed_1995.pdf",          DOC_01_TEXT),
    ("02_Sale_Deed_2005.pdf",                     DOC_02_TEXT),
    ("03_Mortgage_Deed_PNB_2008.pdf",             DOC_03_TEXT),
    ("04_Reconveyance_Deed_PNB_2012.pdf",         DOC_04_TEXT),
    ("05_Gift_Deed_2015.pdf",                     DOC_05_TEXT),
    ("06_Deposit_of_Title_Deeds_HDFC_2019.pdf",   DOC_06_TEXT),
    ("07_Leave_and_License_2022.pdf",             DOC_07_TEXT),
    ("08_Relinquishment_Deed_2024.pdf",           DOC_08_TEXT),
]

print(f"Generating {len(documents)} documents in: {project_path}\n")
for filename, text in documents:
    generate_pdf(filename, text)

print(f"\nDone! {len(documents)} PDFs generated.")
