import pandas as pd
import os
os.environ["WEASYPRINT_DLL_DIRECTORIES"] = r"C:\msys64\mingw64\bin"

from weasyprint import HTML, CSS

from weasyprint import HTML, CSS

# Load CSV
df = pd.read_csv("voter_data.csv")

# Convert rows to blocks (8 per page)
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
        <div class="line1">{row['Nagar_Parishad']}  &nbsp;&nbsp;  प्रभाग क्र : {row['Prabhag_kr']}</div>
        <div class="line1">यादी भाग क्र. {row['Yaadi_bhaag_kr']} &nbsp;&nbsp; {row['Booth_address']}</div>

        <div class="spacer"></div>

        <div>मतदाराचे नाव: {row['Name']}</div>
        <div>{father_or_husband}</div>
        <div>घर क्रमांक: {house_no}</div>
        <div>वय : {row['Age']} &nbsp;&nbsp; लिंग : {row['Gender']}</div>
    </div>
    """

    blocks_html += block
    count += 1

    # Insert a page break after every 8 blocks
    if count % 8 == 0:
        blocks_html += '<div class="page-break"></div>'

# Final HTML
html_text = f"""
<!DOCTYPE html>
<html lang="mr">
<head>
<meta charset="UTF-8">

<style>

@page {{
    size: A4;
    margin: 0;      /* <<< REMOVE DEFAULT BROWSER MARGINS */
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
    align-text: center;
}}

.page-break {{
    page-break-after: always;
}}

.block {{
    width: 42%;
    height: 14.1rem;
    float: left;
    box-sizing: border-box;
    font-size: 8pt;
    
    display: flex;
    flex-direction: column;
    justify-content: flex-end;


    /* <<< YOU CAN TWEAK THESE >>> */
    padding: 10px;
    
    margin: 20px;
    margin-left: 35px;
    margin-bottom: 37px;
    /* border: 1px dashed #ccc; */ /* Enable only for debugging */
}}

.line1 {{
    font-weight: bold;
    font-size: 8pt;
    text-align: center;
    width: 100%;   
}}

.spacer {{
    height: 10px; /* space before personal details */
}}

</style>
</head>

<body>
{blocks_html}
</body>
</html>
"""

# Export to PDF
HTML(string=html_text).write_pdf("Voter_List_8_Block.pdf")

print("PDF Created Successfully!")
