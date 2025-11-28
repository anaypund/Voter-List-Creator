from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract
import numpy as np
import io
import re
import csv

def preprocess_and_crop_columns(page_image):
    w, h = page_image.size

    # Set custom margins
    top_margin = 320
    bottom_margin = 150
    left_margin = 50
    right_margin = 80

    # Apply cropping using the margins
    cropped = page_image.crop((
        left_margin,
        top_margin,
        w - right_margin,
        h - bottom_margin
    ))

    col_width = cropped.width // 3
    columns = []
    LEFT_CUT = 0
    for i in range(3):
        full_col = cropped.crop((i * col_width, 0, (i + 1) * col_width, cropped.height))
        valuable_width = int(0.7 * full_col.width)
        cleaned_col = full_col.crop((LEFT_CUT, 0, valuable_width, full_col.height))
        columns.append(cleaned_col)

    return columns

def extract_header(page):
    w, h = page.size

    # Set custom margins
    top_margin = 130
    bottom_margin =290
    left_margin = 50
    right_margin = 50

    # Apply cropping using the margins
    cropped = page.crop((
        left_margin,
        top_margin,
        w//2,
        bottom_margin
    ))

    return cropped


def artificially_expand_line_spacing(image, spacing=12, line_padding=10, min_gap=10):
    import numpy as np
    from itertools import groupby
    from operator import itemgetter

    gray = image.convert("L")
    np_img = np.array(gray)

    # Invert: text becomes >0
    projection = np.sum(255 - np_img, axis=1)
    threshold = np.max(projection) * 0.1
    is_text_row = projection > threshold

    # Detect line blocks (start, end) where text is present
    line_blocks = []
    current_start = None
    for i, has_text in enumerate(is_text_row):
        if has_text:
            if current_start is None:
                current_start = i
        else:
            if current_start is not None:
                line_blocks.append((current_start, i - 1))
                current_start = None
    if current_start is not None:
        line_blocks.append((current_start, len(is_text_row) - 1))

    # Merge nearby lines if gap is too small (e.g. between 'वय' and 'लिंग')
    merged_blocks = []
    prev_start, prev_end = line_blocks[0]
    for start, end in line_blocks[1:]:
        if start - prev_end < min_gap:
            prev_end = end
        else:
            merged_blocks.append((prev_start, prev_end))
            prev_start, prev_end = start, end
    merged_blocks.append((prev_start, prev_end))

    # Calculate new height
    new_height = sum((end - start + 1 + spacing + 2 * line_padding) for start, end in merged_blocks)
    new_img = Image.new("L", (gray.width, new_height), color=255)

    # Stitch cleanly spaced lines
    y_cursor = 0
    for start, end in merged_blocks:
        line_img = gray.crop((0, max(0, start - line_padding), gray.width, min(gray.height, end + line_padding + 1)))
        new_img.paste(line_img, (0, y_cursor))
        y_cursor += line_img.height + spacing

    return new_img



def extract_entries(text, nagar_parishad, prabhag_kr, yaadi_bhaag_kr, booth_address):
    entries = re.split(r"(?:^|\n)\s*मतदाराचे पूर्ण\s*[:：]?\s*", text)[1:]

    parsed = []
    for entry in entries:
        name = entry.splitlines()[0].strip(" :") if entry.strip() else ""

        def extract_field(pattern):
            match = re.search(pattern, entry)
            return match.group(1).strip(" :") if match else ""

        father = extract_field(r"वडिलांचे नाव\s*[:：]?\s*(.*)")
        husband = extract_field(r"पतीचे नाव\s*[:：]?\s*(.*)")

        # Fixed house no: capture only the same line, even if blank
        house_line = re.search(r"घर क्रमांक\s*[:：]?(.*)", entry)
        house_val = house_line.group(1).strip(" :") if house_line else ""

        # Age and gender extraction
        age = extract_field(r"वय\s*[:：]?\s*(\d{1,3})")
        gender = extract_field(r"लिंग\s*[:：]?\s*([^\n\d]+)")

        parsed.append({
            "Name": name,
            "Father Name": father,
            "Husband Name": husband,
            "House Number": house_val,
            "Age": age,
            "Gender": gender,
            "Nagar_Parishad": nagar_parishad,
            "Prabhag_kr": prabhag_kr,
            "Yaadi_bhaag_kr": yaadi_bhaag_kr,
            "Booth_address": booth_address,
        })

    return parsed


def clean_ocr_text(text):
    replacements = {
        r"[;:!]"            : ":",           # Normalize ; and ! to colon
        r"\bबय\b"           : "वय",          # Misread बय → वय
        r"\bचय\b"           : "वय",          # Misread चय → वय
        r"\bमाव\b"          : "नाव",         # Misread माव → नाव
        r"\bमाब\b"          : "नाव",         # Misread माब → नाव
        r"\bनाब\b"          : "नाव",         # Misread नाब → नाव
        r"\bनाय\b"          : "नाव",         # Misread नाय → नाव
        r"\bनाव\s*!"        : "नाव :",        # Handle नाव ! → नाव :
        r"\bलिगं\b"         : "लिंग",        # Missing anusvara
        r"\bलिग\b"          : "लिंग",        # Another common variant
        r"छायाचत्र"         : "छायाचित्र",    # Incomplete word
        r":"                : " : ",          # Ensure spacing around colons
        r"ख्री"              : "स्री",
        r"स्त्री"              : "स्री",
        r"घरक्रमांक"          : "घर क्रमांक"
    }

    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text)
    
    return text

def process_header(header_text):
    lines = header_text.strip().split("\n")

    # --- 1) Nagar Parishad (first line) ---
    nagar_parishad = lines[0].strip()

    # --- 2) Prabhag number from second line ---
    # Looks for first number (Devanagari digits also handled)
    prabhag_match = re.search(r'(\d+|[०-९]+)', lines[1])
    prabhag_kr = prabhag_match.group(1) if prabhag_match else None

    # --- 3) Yaadi Bhaag number before ":" ---
    line3 = lines[2]
    yaadi_match = re.search(r'क्र\.?\s*([०-९\d]+)', line3)
    yaadi_bhaag_kr = yaadi_match.group(1) if yaadi_match else None

    # --- 4) Booth address (everything after ":") ---
    if ":" in line3:
        booth_address = line3.split(":", 1)[1].strip()
    else:
        booth_address = None

    return nagar_parishad, prabhag_kr, yaadi_bhaag_kr, booth_address


def preprocess_image(image):
    # Convert to grayscale
    gray = image.convert("L")

    # Enhance contrast
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(1.5)
    return enhanced

#     # Remove small noise
#     filtered = enhanced.filter(ImageFilter.MedianFilter())

#     # Binarize: turn into black & white
#     # thresholded = filtered.point(lambda x: 0 if x < 140 else 255, mode='1')

#     return filtered
#     # return image


if __name__ == '__main__':

    # Load all pages from the PDF
    pdf_path_list = ["raw pdfs/FinalList_Ward_2.pdf", "raw pdfs/FinalList_Ward_3.pdf", "raw pdfs/FinalList_Ward_4.pdf"]
    for pdf_idx, pdf_path in enumerate(pdf_path_list):
        print(f"Loading pdf {pdf_path}")
        pages = convert_from_path(pdf_path, dpi=300)[2:-1]
        print("loaded pdf")

        final_data = []

        index =1
        for idx, page in enumerate(pages, start=1):
            print(idx)
            # Check Header
            header = extract_header(page)
            # header.save(f"imgs/Header_{idx}.png")
            header_text = pytesseract.image_to_string(header, lang='Devanagari+mar')
            nagar_parishad, prabhag_kr, yaadi_bhaag_kr, booth_address = process_header(header_text)
            
            columns = preprocess_and_crop_columns(page)
            for col_img in columns:
                # col_img = preprocess_image(col_img)
                # col_img = artificially_expand_line_spacing(col_img)
                text = pytesseract.image_to_string(col_img, lang='Devanagari')

                # col_img.save(f"imgs/debug_column_{index}.png")

                text = clean_ocr_text(text)
                parsed = extract_entries(text, nagar_parishad, prabhag_kr, yaadi_bhaag_kr, booth_address)
                final_data.extend(parsed)
                # with open(f'txts/column_{index}.txt', 'w', encoding='utf-8') as f:
                #     f.write(text)
                index += 1

        # Save only final CSV
        with open(f"voter_ward_{pdf_idx}.csv", "w", newline="", encoding="utf-8") as f:
            # writer = csv.DictWriter(f, fieldnames=["नाव", "वडिलांचे नाव", "पतीचे नाव", "घर क्रमांक", "वय", "लिंग"])
            writer = csv.DictWriter(f, fieldnames=["Name", "Father Name", "Husband Name", "House Number", "Age", "Gender", "Nagar_Parishad", "Prabhag_kr", "Yaadi_bhaag_kr", "Booth_address"])
            writer.writeheader()
            writer.writerows(final_data)

        print(f"✅ Done! Extracted {len(final_data)} records from memory, no files saved.")