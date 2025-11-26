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
    top_margin = 120
    bottom_margin = 100
    left_margin = 45
    right_margin = 30

    # Apply cropping using the margins
    cropped = page_image.crop((
        left_margin,
        top_margin,
        w - right_margin,
        h - bottom_margin
    ))

    col_width = cropped.width // 3
    columns = []

    for i in range(3):
        full_col = cropped.crop((i * col_width, 0, (i + 1) * col_width, cropped.height))
        valuable_width = int((2 / 3) * full_col.width)
        cleaned_col = full_col.crop((15, 0, valuable_width, full_col.height))
        columns.append(cleaned_col)

    return columns

def preprocess_and_crop_cards(page_image):
    w, h = page_image.size

    # Custom margins for full page crop
    top_margin = 120
    bottom_margin = 75
    left_margin = 45
    right_margin = 30

    # Crop page to remove page-level margins
    cropped = page_image.crop((
        left_margin,
        top_margin,
        w - right_margin,
        h - bottom_margin
    ))

    col_width = cropped.width // 3
    num_cards_per_col = 10
    card_images = []

    for i in range(3):  # 3 vertical columns
        full_col = cropped.crop((
            i * col_width,
            0,
            (i + 1) * col_width,
            cropped.height
        ))

        # Crop out right 1/3 part to avoid "छायाचित्र" and number
        valuable_width = int((2 / 3) * full_col.width)
        cleaned_col = full_col.crop((15, 0, valuable_width, full_col.height))

        card_height = cleaned_col.height // num_cards_per_col

        for j in range(num_cards_per_col):
            card = cleaned_col.crop((
                0,
                j * card_height,
                cleaned_col.width,
                (j + 1) * card_height
            ))
            top_trim = 60  # or 20 depending on font size
            card = card.crop((0, top_trim, card.width, card.height))
            card_images.append(card)

    return card_images

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



def extract_entries(text):
    entries = re.split(r"(?:^|\n)\s*नाव\s*[:：]?\s*", text)[1:]

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
            "नाव": name,
            "वडिलांचे नाव": father,
            "पतीचे नाव": husband,
            "घर क्रमांक": house_val,
            "वय": age,
            "लिंग": gender,
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
    }

    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text)
    
    return text


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



# Load all pages from the PDF
pdf_path = "raw pdfs\shortened.pdf"
pages = convert_from_path(pdf_path, dpi=300)[2:4]

final_data = []

index =1
for page in pages:
    columns = preprocess_and_crop_columns(page)
    # for i, img in enumerate(columns):
    #     img.save(f"imgs/debug_column_{i+1}.png")
    for col_img in columns:
        # col_img = preprocess_image(col_img)
        col_img = artificially_expand_line_spacing(col_img)
        text = pytesseract.image_to_string(col_img, lang='mar')

        col_img.save(f"imgs/debug_column_{index}.png")

        text = clean_ocr_text(text)
        final_data.extend(extract_entries(text))
        with open(f'txts/column_{index}.txt', 'w', encoding='utf-8') as f:
            f.write(text)
        index += 1

# Save only final CSV
with open("voter_data.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["नाव", "वडिलांचे नाव", "पतीचे नाव", "घर क्रमांक", "वय", "लिंग"])
    writer.writeheader()
    writer.writerows(final_data)

print(f"✅ Done! Extracted {len(final_data)} records from memory, no files saved.")



# from pdf2image import convert_from_path
# from PIL import Image
# import pytesseract
# import io
# import re
# import csv

# def preprocess_and_crop_columns(page_image):
#     w, h = page_image.size
#     margin = 30  # crop 30px from all sides
#     cropped = page_image.crop((margin, margin, w - margin, h - margin))
#     col_width = cropped.width // 3
#     return [
#         cropped.crop((i * col_width, 0, (i + 1) * col_width, cropped.height))
#         for i in range(3)
#     ]

# def extract_entries(text):
#     entries = re.split(r"(?:^|\n)\s*नाव\s*[:：]?\s*", text)[1:]
#     parsed = []
#     for entry in entries:
#         name = entry.splitlines()[0].strip()
#         father = re.search(r"वडिलांचे नाव[:：]?\s*([^\n]+)", entry)
#         husband = re.search(r"पतीचे नाव[:：]?\s*([^\n]+)", entry)
#         house = re.search(r"घर क्रमांक[:：]?\s*([^\n]+)", entry)
#         age = re.search(r"वय[:：]?\s*(\d{1,3})", entry)
#         gender = re.search(r"लिंग[:：]?\s*([^\n]+)", entry)

#         parsed.append({
#             "नाव": name,
#             "वडिलांचे नाव": father.group(1).strip() if father else "",
#             "पतीचे नाव": husband.group(1).strip() if husband else "",
#             "घर क्रमांक": house.group(1).strip() if house else "",
#             "वय": age.group(1) if age else "",
#             "लिंग": gender.group(1).strip() if gender else "",
#         })
#     return parsed

# # Load all pages from the PDF
# pdf_path = "raw pdfs\shortened.pdf"
# pages = convert_from_path(pdf_path, dpi=300)[2:3]

# final_data = []

# for page in pages:
#     columns = preprocess_and_crop_columns(page)
#     for col_img in columns:
#         text = pytesseract.image_to_string(col_img, lang='mar')
#         final_data.extend(extract_entries(text))

# # Save only final CSV
# with open("test.csv", "w", newline="", encoding="utf-8") as f:
#     writer = csv.DictWriter(f, fieldnames=["नाव", "वडिलांचे नाव", "पतीचे नाव", "घर क्रमांक", "वय", "लिंग"])
#     writer.writeheader()
#     writer.writerows(final_data)

# print(f"✅ Done! Extracted {len(final_data)} records from memory, no files saved.")
