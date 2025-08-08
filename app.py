import streamlit as st
import pandas as pd
import os
import tempfile
import shutil
from datetime import datetime
import re

st.set_page_config(page_title="Shopify Promo Builder", layout="wide")
st.title("📦 Shopify Promotions Builder (Matrixify Compatible)")
st.markdown("Upload your **Supplier Promo File (.xlsx)** and download 3 ready-to-import Matrixify files.")

uploaded_file = st.file_uploader("Upload Supplier Promo Excel file", type=["xlsx"])

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
        all_rows = []

        for sheet in xls.sheet_names:
            df = xls.parse(sheet)
            if {"BJC Code", "Consumer Promo", "Promotion Period"}.issubset(df.columns):
                df = df.dropna(subset=["BJC Code"])
                for _, rec in df.iterrows():
                    promo_type, dol, pct, display_txt, raw_txt = determine_values(rec["Consumer Promo"])
                    all_rows.append({
                        "Variant SKU": rec["BJC Code"],
                        "Command": "MERGE",
                        "Variant Metafield: display.promotion_secondary_text [single_line_text_field]": display_txt,
                        "Variant Metafield: discounts.buy3get1 [boolean]": "TRUE" if promo_type == "443" else "",
                        "Variant Metafield: discount_promo.promo_details [single_line_text_field]": (
                            f"${{dol}}_${{display_txt}}" if promo_type == "Cash Back" else
                            raw_txt.replace(" ", "") + "_" + display_txt if promo_type == "Percentage" else ""
                        ),
                        "Variant Metafield: filter.promotion [single_line_text_field]": (
                            "Percentage" if re.search(r"\d+% Off", display_txt) else
                            "Cash Back" if "Cash Back" in display_txt else
                            "Buy 3 Get 1 Free" if "Buy 3 Get 1 Free" in display_txt else
                            "Gift Card" if "Gift Card" in display_txt else ""
                        )
                    })

        df_full = pd.DataFrame(all_rows)
        df_cleanup = df_full.copy()
        for col in df_cleanup.columns[2:]:
            df_cleanup[col] = ""

        # Save outputs
        promo_file = output_dir / "Shopify x Matrixify file.xlsx"
        cleanup_file = output_dir / "Shopify x Matrixify Blank Cleanup File.xlsx"

        df_full.to_excel(promo_file, index=False)
        df_cleanup.to_excel(cleanup_file, index=False)

        st.success("✅ Files generated successfully. Download below:")
        with open(promo_file, "rb") as f:
            st.download_button("⬇️ Download Promo File", data=f, file_name=promo_file.name)

        with open(cleanup_file, "rb") as f:
            st.download_button("⬇️ Download Cleanup File", data=f, file_name=cleanup_file.name)