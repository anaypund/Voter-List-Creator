import pandas as pd
import os
import base64
from pathlib import Path

os.environ["WEASYPRINT_DLL_DIRECTORIES"] = r"C:\msys64\mingw64\bin"
from weasyprint import HTML

def image_to_base64(image_path):
    """Convert image to base64 string"""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

# Load CSV
df = pd.read_csv("short.csv")

# Convert image to base64 (do this once before the loop)
try:
    photo_base64 = image_to_base64("raw pdfs\mahure 01.jpg")
    photo_src = f"data:image/png;base64,{photo_base64}"
except FileNotFoundError:
    print("Warning: Image not found, using placeholder")
    photo_src = ""  # Or use a placeholder

# Convert rows to blocks
blocks_html = ""
count = 0

for _, row in df.iterrows():
    father_or_husband = (
        f"वडिलांचे नाव: {row['Father Name']}" 
        if pd.notna(row['Father Name']) and row['Father Name'] != "" 
        else f"पतीचे नाव: {row['Husband Name']}"
    )
    
    house_no = "" if pd.isna(row['House Number']) else row['House Number']

    block = f"""
    <div class="block">
        <div class="block-photo-wrapper">
            <img src="{photo_src}" class="block-photo" alt="Photo" />
        </div>
        <div class="block-text">
            <div class="line1">{row['Nagar_Parishad']}  &nbsp;&nbsp;  प्रभाग क्र : {row['Prabhag_kr']}</div>
            <div class="line1">यादी भाग क्र. {row['Yaadi_bhaag_kr']} &nbsp;&nbsp; {row['Booth_address']}</div>
            <div class="spacer"></div>
            <div>मतदाराचे नाव: {row['Name']}</div>
            <div>{father_or_husband}</div>
            <div>घर क्रमांक: {house_no}</div>
            <div>वय : {row['Age']} &nbsp;&nbsp; लिंग : {row['Gender']}</div>
        </div>
    </div>
    """

    blocks_html += block
    count += 1

    if count % 8 == 0:
        blocks_html += '<div class="page-break"></div>'

# Final HTML (rest of your code remains the same)
html_text = f"""
<!DOCTYPE html>
<html lang="mr">
<head>
<meta charset="UTF-8">
<style>
@page {{
    size: A4;
    margin: 0;
}}
@font-face {{
    font-family: "NotoDeva";
    src: url("NotoSerifDevanagari-VariableFont_wdth,wght.ttf");
}}
body {{
    font-family: "NotoDeva";
    margin: 0;
    padding: 0;
    font-size: 12pt;
}}
.page-break {{
    page-break-after: always;
}}
.block {{
    width: 46%;
    height: 15.3rem;
    float: left;
    box-sizing: border-box;
    font-size: 9pt;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    margin: 12px;
    margin-left: 18px;
    margin-bottom: 28px;
    border: 1px solid #333;
    background: #fff;
}}
.block-photo-wrapper {{
    width: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
}}
.block-photo {{
    width: 100%;
    height: auto;
    object-fit: cover;
}}
.block-text {{
    padding: 10px;
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}}
.line1 {{
    font-weight: bold;
    font-size: 9pt;
    text-align: center;
    width: 100%;   
}}
.spacer {{
    height: 11px;
}}
</style>
</head>
<body>
{blocks_html}
</body>
</html>
"""

HTML(string=html_text).write_pdf("ward 2.pdf")
print("PDF Created Successfully!")