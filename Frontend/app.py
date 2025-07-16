import streamlit as st
import subprocess
import json
import os
import re
import tempfile
from dotenv import load_dotenv
from backend.calculator import setup_watson_ai, get_tax_regime_info, generate_tax_function, cal_net, extract_code
import math
load_dotenv()
st.title("📄 Income Tax Calculator")

# File uploader for Form 16 PDF
uploaded_file = st.file_uploader("Upload your Form 16 (PDF)", type=["pdf"])

# Radio button for selecting the tax regime
regime = st.radio("Select Tax Regime", ["Old Regime", "New Regime"])

# Display button for calculation
calculate_button = st.button("Calculate Tax")

if uploaded_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        temp_pdf.write(uploaded_file.read())
        temp_pdf_path = temp_pdf.name

    extract_proc = subprocess.run(["python", "backend/docling_llamavision.py", temp_pdf_path], capture_output=True, text=True)
    os.remove(temp_pdf_path)

    if extract_proc.returncode != 0:
        st.error("Extraction failed.")
        st.text(extract_proc.stderr)
        st.stop()

    try:
        with open("form16.json", "r") as f:
            form16_data = json.load(f)
    except Exception as e:
        st.error(f"Failed to read extracted data: {e}")
        st.stop()

# Run computation only when file is uploaded, regime is selected, and calculate button is clicked
if regime and calculate_button:
    # with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
    #     temp_pdf.write(uploaded_file.read())
    #     temp_pdf_path = temp_pdf.name

    # extract_proc = subprocess.run(["python", "docling_llamavision.py",temp_pdf_path], capture_output=True, text=True)
    # if extract_proc.returncode != 0:
    #     st.error("Extraction failed.")
    #     os.remove(temp_pdf_path)
    #     st.text(extract_proc.stderr)
    #     st.stop() 
    # try:
    #     with open("form16.json", "r") as f:
    #         form16_data = json.load(f)
    # except Exception as e:
    #     st.error(f"Failed to read form16.json: {e}")
    #     os.remove(temp_pdf_path)
    #     st.stop()
    # os.remove(temp_pdf_path)   

    # Initialize the model
    model = setup_watson_ai()

    # Get tax regime info based on the selected regime
    regime_info = get_tax_regime_info().get('new' if regime == "New Regime" else 'old')

    # Generate the tax calculation function using the Watson model
    tax_function_code = generate_tax_function(model, regime_info)

    # Extract the tax calculation logic from generated code
    tax_function = extract_code(tax_function_code)

    # Execute the generated tax calculation function as Python code
    try:
        exec(tax_function)  # Execute the function in the current context
    except Exception as e:
        st.error(f"Failed to execute generated code: {e}")
        st.stop()

    # Now that we have the tax calculation logic, we can calculate the net income
    st.info("Calculating net income...")

    net_income = cal_net(form16_data, regime='new' if regime == "New Regime" else 'old')

    st.subheader(f"Net Income based on selected regime ({regime}):")
    st.write(f"₹ {net_income}")
    
    # st.write(extract_proc)
    print(tax_function)

    # Now we can call the generated tax function with the extracted net income
    try:
        tax_paid = cal_tax(net_income)
        out = tax_paid + 0.04 * tax_paid  # Adding surcharge or any additional tax
        st.subheader("Calculated Tax Paid:")
        st.write(f"₹ {math.floor(out)}")

    except Exception as e:
        st.error(f"Failed to calculate tax: {e}")
        st.stop()
