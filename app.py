import streamlit as st
import pandas as pd
import tempfile
import re
from datetime import datetime
from pathlib import Path

# ----------------------------
# Page setup
# ----------------------------
st.set_page_config(page_title="Shopify Promo Builder", layout="wide")
st.title("📦 Shopify Promotions Builder (Matrixify Compatible)")
st.markdown(
    "Upload an Excel file containing supplier promo data and download **3 ready-to-import** files:\n"
    "- **Marketplace_File.xlsx** (Summary + Marketplace_Data)\n"
    "- **Shopify x Matrixify file.xlsx**\n"
    "- **Shopify x Matrixify Blank Cleanup File.xlsx**"
)

uploaded_file = st.file_uploader("Choose a promo Excel file (.xlsx)", type=["xlsx"])


# ----------------------------
# Helpers
# ----------------------------
def parse_promo_dates(text):
    """
    Accepts formats like:
      - "From 01/01/2026 - 31/01/2026"
      - "01/01/2026 - 31/01/2026"
    Returns (start_date, end_date) as date objects or (None, None)
    """
    try:
        clean = str(text).replace("From ", "").strip()
        start_str, end_str = clean.split(" - ")
        start = datetime.strptime(start_str.strip(), "%d/%m/%Y").date()
        end = datetime.strptime(end_str.strip(), "%d/%m/%Y").date()
        return start, end
    except Exception:
        return None, None


def determine_values(raw):
    """
    Converts 'Consumer Promo' text into:
      - promo_type
      - $ value
      - % value
      - display text
      - raw text
    """
    text = str(raw).strip()

    if "443" in text or "Buy 3 Get 1" in text:
        return "443", 0, 0, "Buy 3 Get 1 Free", text

    if "Gift Card" in text or "Fuel Card" in text:
        m = re.search(r"(\d+)", text)
        display = f"${m.group(1)} eGift Card" if m else text
        return "Gift Card", 0, 0, display, text

    if "%" in text:
        m = re.search(r"(\d+)%", text)
        pct = int(m.group(1)) if m else 0
        display = text if "max" in text.lower() else f"{pct}% Off"
        return "Percentage", 0, pct, display, text

    m = re.search(r"(\d+)", text)
    if m:
        amt = int(m.group(1))
        display = f"${amt} Cash Back"
        return "Cash Back", amt, 0, display, text

    return "Unknown", 0, 0, text, text


def read_bytes(p: Path) -> bytes:
    return p.read_bytes()


# ----------------------------
# Guard: do nothing until file is uploaded
# ----------------------------
if uploaded_file is None:
    st.info("👆 Upload your supplier promo Excel file to begin.")
    st.stop()


# ----------------------------
# Main pipeline
# ----------------------------
try:
    with tempfile.TemporaryDirectory() as tmpdir:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(tmpdir) / f"Shopify_Promo_{ts}"
        out.mkdir(parents=True, exist_ok=True)

        expected_cols = {"BJC Code", "Consumer Promo", "Promotion Period"}

        # 1) Build Marketplace file (Summary + Marketplace_Data)
        rows = []
        source_summary = []

        xls = pd.ExcelFile(uploaded_file)

        for idx, sheet in enumerate(xls.sheet_names):
            df = xls.parse(sheet)

            # Skip sheets that don't have required columns
            if not expected_cols.issubset(set(df.columns)):
                continue

            df = df.dropna(subset=["BJC Code"])
            if df.empty:
                continue

            start, end = parse_promo_dates(df["Promotion Period"].iloc[0])

            source_summary.append(
                {
                    "Promo Name": sheet,
                    "Source Count": len(df),
                    "Source Start": start,
                    "Source End": end,
                }
            )

            slug = 2000 + idx

            for _, rec in df.iterrows():
                promo_type, dol, pct, display_txt, raw_txt = determine_values(rec["Consumer Promo"])

                rows.append(
                    {
                        "Status": 1,
                        "id": "",
                        "Bob Jane Material": rec["BJC Code"],
                        "Promo Name": sheet,
                        "Promo $ Value": dol,
                        "Promo % Value": pct,
                        "Valid From": start,
                        "Valid To": end,
                        "Slug": slug,
                        "Unit": 0,
                        "Type": promo_type,
                        "Price Match Skip": 1,
                        "Promo Retail Skip": 1,
                        "Notify Vendor": 0,
                        "Comments": "",
                        "Ad ID": "",
                        "_display_text": display_txt,
                        "_raw_text": raw_txt,
                    }
                )

        if not rows:
            st.error(
                "No valid promo data found.\n\n"
                "Make sure at least one sheet contains these columns:\n"
                "- **BJC Code**\n"
                "- **Consumer Promo**\n"
                "- **Promotion Period**"
            )
            st.stop()

        df_a = pd.DataFrame(rows)

        # Destination summary
        df_dest = df_a.groupby("Promo Name", as_index=False).agg(
            Dest_Count=("Bob Jane Material", "size"),
            Dest_Start=("Valid From", "first"),
            Dest_End=("Valid To", "first"),
        )

        df_summary = pd.merge(pd.DataFrame(source_summary), df_dest, on="Promo Name", how="left")

        # Excel formula check (kept as formula so it shows in Excel)
        df_summary["Check"] = [
            f'=IF(AND(B{r+2}=E{r+2},C{r+2}=F{r+2},D{r+2}=G{r+2}),"OK","Mismatch")'
            for r in range(len(df_summary))
        ]

        marketplace_path = out / "Marketplace_File.xlsx"
        with pd.ExcelWriter(marketplace_path, engine="openpyxl") as writer:
            df_summary.to_excel(writer, sheet_name="Summary", index=False)
            df_a.drop(columns=["_display_text", "_raw_text"]).to_excel(
                writer, sheet_name="Marketplace_Data", index=False
            )

        # 2) Promo file + 3) Cleanup file
        promo_rows = []
        cleanup_rows = []

        for _, rec in df_a.iterrows():
            display_txt = str(rec["_display_text"])
            raw_txt = str(rec["_raw_text"])
            promo_type = str(rec["Type"])

            bool_443 = "TRUE" if promo_type == "443" else ""

            promo_details = ""
            if promo_type == "Cash Back":
                m = re.search(r"\$(\d+)", display_txt)
                amt = m.group(1) if m else ""
                promo_details = f"${amt}_${amt} Cash Back" if amt else ""
            elif promo_type == "Percentage":
                promo_details = f"{raw_txt.replace(' ', '')}_{display_txt}"

            # Filter value detection
            if re.search(r"\d+%\s*Off", display_txt, flags=re.IGNORECASE):
                filter_val = "Percentage"
            elif "Cash Back" in display_txt:
                filter_val = "Cash Back"
            elif "Buy 3 Get 1 Free" in display_txt:
                filter_val = "Buy 3 Get 1 Free"
            elif "Gift Card" in display_txt or "Fuel Card" in display_txt:
                filter_val = "Gift Card"
            else:
                filter_val = ""

            entry = {
                "Variant SKU": rec["Bob Jane Material"],
                "Command": "MERGE",
                "Variant Metafield: display.promotion_secondary_text [single_line_text_field]": display_txt,
                "Variant Metafield: discounts.buy3get1 [boolean]": bool_443,
                "Variant Metafield: discount_promo.promo_details [single_line_text_field]": promo_details,
                "Variant Metafield: filter.promotion [single_line_text_field]": filter_val,
            }

            promo_rows.append(entry)
            cleanup_rows.append({k: (v if k in ["Variant SKU", "Command"] else "") for k, v in entry.items()})

        df_promo = pd.DataFrame(promo_rows)
        df_cleanup = pd.DataFrame(cleanup_rows)

        promo_path = out / "Shopify x Matrixify file.xlsx"
        cleanup_path = out / "Shopify x Matrixify Blank Cleanup File.xlsx"

        df_promo.to_excel(promo_path, index=False)
        df_cleanup.to_excel(cleanup_path, index=False)

        # IMPORTANT FIX:
        # Streamlit download_button data should be bytes (not an open file handle).
        st.success("✅ Files generated successfully. Download below:")

        c1, c2, c3 = st.columns(3)

        with c1:
            st.download_button(
                "⬇️ Download Marketplace File",
                data=read_bytes(marketplace_path),
                file_name=marketplace_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with c2:
            st.download_button(
                "⬇️ Download Promo File",
                data=read_bytes(promo_path),
                file_name=promo_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with c3:
            st.download_button(
                "⬇️ Download Cleanup File",
                data=read_bytes(cleanup_path),
                file_name=cleanup_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

except Exception as e:
    st.error("❌ The app crashed while processing the file.")
    st.exception(e)
