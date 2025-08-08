import streamlit as st
import pandas as pd
import os
import tempfile
import shutil
import re
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Shopify Promo Builder", layout="wide")
st.title("📦 Shopify Promotions Builder (Matrixify Compatible)")
st.markdown("Upload your **Supplier Promo File (.xlsx)** and download 3 ready-to-import Matrixify files.")

uploaded_file = st.file_uploader("Upload Supplier Promo Excel file", type=["xlsx"])

def parse_promo_dates(text: str):
    try:
        clean = text.replace("From ", "").strip()
        start_str, end_str = clean.split(" - ")
        start = datetime.strptime(start_str, "%d/%m/%Y").date()
        end = datetime.strptime(end_str, "%d/%m/%Y").date()
        return start, end
    except:
        return None, None

def determine_values(raw: str):
    text = str(raw).strip()
    if "443" in text or "Buy 3 Get 1" in text:
        return "443", 0, 0, "Buy 3 Get 1 Free", text
    if "Gift Card" in text or "Fuel Card" in text:
        m = re.search(r"(\d+)", text)
        display = f"${{m.group(1)}} eGift Card" if m else text
        return "Gift Card", 0, 0, display, text
    if "%" in text:
        m = re.search(r"(\d+)%", text)
        pct = int(m.group(1)) if m else 0
        display = text if "max" in text.lower() else f"{pct}% Off"
        return "Percentage", 0, pct, display, text
    m = re.search(r"(\d+)", text)
    if m:
        amt = int(m.group(1))
        display = f"${{amt}} Cash Back"
        return "Cash Back", amt, 0, display, text
    return "Unknown", 0, 0, text, text

if uploaded_file:
    with tempfile.TemporaryDirectory() as tmpdir:
        base_name = datetime.now().strftime("Shopify_Promo_%Y%m%d_%H%M%S")
        output_dir = Path(tmpdir) / base_name
        output_dir.mkdir(parents=True, exist_ok=True)

        xls = pd.ExcelFile(uploaded_file)

        # Build Marketplace File
        rows = []
        source_summary = []
        for idx, sheet in enumerate(xls.sheet_names):
            df = xls.parse(sheet)
            if {"BJC Code","Consumer Promo","Promotion Period"}.issubset(df.columns):
                df = df.dropna(subset=["BJC Code"])
                if not df.empty:
                    count = len(df)
                    start, end = parse_promo_dates(df["Promotion Period"].iloc[0])
                    source_summary.append({"Promo Name": sheet, "Source Count": count, "Source Start": start, "Source End": end})
                    slug = 2000 + idx
                    for _, rec in df.iterrows():
                        promo_type, dol, pct, display_txt, raw_txt = determine_values(rec["Consumer Promo"])
                        rows.append({
                            "Status": 1, "id": "", "Bob Jane Material": rec["BJC Code"],
                            "Promo Name": sheet, "Promo $ Value": dol, "Promo % Value": pct,
                            "Valid From": start, "Valid To": end, "Slug": slug, "Unit": 0,
                            "Type": promo_type, "Price Match Skip": 1, "Promo Retail Skip": 1,
                            "Notify Vendor": 0, "Comments": "", "Ad ID": "",
                            "_display_text": display_txt, "_raw_text": raw_txt
                        })
        df_a = pd.DataFrame(rows)
        df_dest = df_a.groupby("Promo Name", as_index=False).agg(
            Dest_Count=("Bob Jane Material", "size"),
            Dest_Start=("Valid From", "first"),
            Dest_End=("Valid To", "first")
        )
        df_summary = pd.merge(pd.DataFrame(source_summary), df_dest, on="Promo Name", how="left")
        df_summary["Check"] = [
            f'=IF(AND(B{r+2}=E{r+2},C{r+2}=F{r+2},D{r+2}=G{r+2}),"OK","Mismatch")'
            for r in range(len(df_summary))
        ]

        marketplace_file = output_dir / "Marketplace_File.xlsx"
        with pd.ExcelWriter(marketplace_file, engine="openpyxl") as w:
            df_summary.to_excel(w, sheet_name="Summary", index=False)
            df_a.drop(columns=["_display_text", "_raw_text"]).to_excel(w, sheet_name="Marketplace_Data", index=False)

        # Build Promo and Cleanup Files
        promo_rows = []
        cleanup_rows = []
        for _, rec in df_a.iterrows():
            sku = rec["Bob Jane Material"]
            promo_type = rec["Type"]
            display_txt = rec["_display_text"]
            raw_txt = rec["_raw_text"]

            bool_443 = "TRUE" if promo_type == "443" else ""
            promo_details = ""
            if promo_type == "Cash Back":
                m = re.search(r"\$(\d+)", display_txt)
                amt = m.group(1) if m else ""
                promo_details = f"${{amt}}_${{amt}} Cash Back"
            elif promo_type == "Percentage":
                raw_ns = raw_txt.replace(" ", "")
                promo_details = f"{raw_ns}_{display_txt}"

            filter_promo = ""
            if re.search(r"\d+% Off", display_txt):
                filter_promo = "Percentage"
            elif "Cash Back" in display_txt:
                filter_promo = "Cash Back"
            elif "Buy 3 Get 1 Free" in display_txt:
                filter_promo = "Buy 3 Get 1 Free"
            elif "Gift Card" in display_txt:
                filter_promo = "Gift Card"

            promo_rows.append({
                "Variant SKU": sku,
                "Command": "MERGE",
                "Variant Metafield: display.promotion_secondary_text [single_line_text_field]": display_txt,
                "Variant Metafield: discounts.buy3get1 [boolean]": bool_443,
                "Variant Metafield: discount_promo.promo_details [single_line_text_field]": promo_details,
                "Variant Metafield: filter.promotion [single_line_text_field]": filter_promo
            })
            cleanup_rows.append({
                "Variant SKU": sku,
                "Command": "MERGE",
                "Variant Metafield: display.promotion_secondary_text [single_line_text_field]": "",
                "Variant Metafield: discounts.buy3get1 [boolean]": "",
                "Variant Metafield: discount_promo.promo_details [single_line_text_field]": "",
                "Variant Metafield: filter.promotion [single_line_text_field]": ""
            })

        df_full = pd.DataFrame(promo_rows)
        df_cleanup = pd.DataFrame(cleanup_rows)

        promo_file = output_dir / "Shopify x Matrixify file.xlsx"
        cleanup_file = output_dir / "Shopify x Matrixify Blank Cleanup File.xlsx"
        df_full.to_excel(promo_file, index=False)
        df_cleanup.to_excel(cleanup_file, index=False)

        st.success("✅ Files generated successfully. Download below:")
        with open(marketplace_file, "rb") as f:
            st.download_button("⬇️ Download Marketplace File", data=f, file_name=marketplace_file.name)
        with open(promo_file, "rb") as f:
            st.download_button("⬇️ Download Promo File", data=f, file_name=promo_file.name)
        with open(cleanup_file, "rb") as f:
            st.download_button("⬇️ Download Cleanup File", data=f, file_name=cleanup_file.name)
