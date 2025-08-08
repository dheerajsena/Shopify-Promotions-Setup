# Shopify Promotions Builder (Matrixify Compatible)

A simple and scalable Streamlit app to generate Shopify Matrixify files for uploading promotional metafields.

## 🔧 Features
- Upload `Supplier Promo File.xlsx`
- Generates two files:
  - `Shopify x Matrixify file.xlsx`
  - `Shopify x Matrixify Blank Cleanup File.xlsx`

## 🚀 How to Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 📁 Expected Columns in Supplier File:
- `BJC Code`
- `Consumer Promo`
- `Promotion Period`

Built for Bob Jane T-Marts | Developed with ❤️ using Streamlit