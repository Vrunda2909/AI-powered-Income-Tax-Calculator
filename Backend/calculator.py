# -*- coding: utf-8 -*-
"""
Tax Calculator with Form 16 Processing
Integrates Streamlit UI with Watson AI tax calculations
"""

import os
import re
import json
import tempfile
import subprocess
from dotenv import load_dotenv
import streamlit as st

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models.utils.enums import ModelTypes
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
from ibm_watsonx_ai.foundation_models import ModelInference

# Load environment variables from .env file
load_dotenv("key.env")

def setup_watson_ai():
    # Get API key from environment variable
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("API_KEY not found in environment variables")
    
    # Setup credentials
    credentials = Credentials(
        url="https://us-south.ml.cloud.ibm.com",
        api_key=api_key,
    )
    
    # Get project ID from environment variable
    project_id = os.getenv("PROJECT_ID")
    if not project_id:
        raise ValueError("PROJECT_ID not found in environment variables")
    
    # Model parameters for deterministic output
    model_id = "ibm/granite-20b-code-instruct"
    parameters = {
        GenParams.DECODING_METHOD: "greedy",  # Greedy decoding for more deterministic results
        GenParams.MAX_NEW_TOKENS: 400,
        GenParams.STOP_SEQUENCES: ["<end·of·code>"],
        GenParams.TEMPERATURE: 0.2,  # Lower temperature to reduce randomness
        GenParams.TOP_P: 1.0,  # Use the full distribution for token sampling
    }
    
    # Initialize model
    model = ModelInference(
        model_id=model_id,
        params=parameters,
        credentials=credentials,
        project_id=project_id
    )
    
    return model


# Module for tax regime definitions
def get_tax_regime_info():
    old_regime = """
                REBATE = 500000

                Tax Slabs :

  `               Taxable Income (Rs.)      Tax Rate (%)
                  0 - 250000                    NIL
                  250001 - 500000               5%
                  500001 - 1000000              20%
                  Above 1000000                 30%

              """

    new_regime = """
                REBATE = 1200000

                Tax Slabs :

  `               Taxable Income (Rs.)      Tax Rate (%)
                  0 - 4,00,000                NIL
                  4,00,001 - 8,00,000         5%
                  8,00,001 - 12,00,000        10%
                  12,00,001 - 16,00,000       15%
                  16,00,001 - 20,00,000       20%
                  20,00,001 - 24,00,000       25%
                  Above 24,00,000             30%
              """
              
    return {'old': old_regime, 'new': new_regime}

# Module for generating prompt for tax calculation
def create_prompt(context):
    instruction = """
    Using the directions below, generate Python code for the given task. Make sure to only use nested IF blocks, no else or else if blocks as shown

    Input:
    Write a Python function to calculate the total income tax give the taxable income based on the inuted tax slabs

    Output:

    def cal_tax(taxable_income):
        tax = 0
        REBATE = 1200000
        if taxable_income > REBATE:
            if taxable_income > 2400000:
                tax += (taxable_income - 2400000) * 0.30
                taxable_income = 2400000
            if taxable_income > 2000000:
                tax += (taxable_income - 2000000) * 0.25
                taxable_income = 2000000
            if taxable_income > 1600000:
                tax += (taxable_income - 1600000) * 0.20
                taxable_income = 1600000
            if taxable_income > 1200000:
                tax += (taxable_income - 1200000) * 0.15
                taxable_income = 1200000
            if taxable_income > 800000:
                tax += (taxable_income - 800000) * 0.10
                taxable_income = 800000
            if taxable_income > 400000:
                tax += (taxable_income - 400000) * 0.05
                taxable_income = 400000
            return tax
    <end of code>
    """
    
    question = f"""Input:
        Write a Python function, to calculate the tax based on REBATE and the given tax slab information : {context}.
        The function 'cal_tax' will take the argument 'taxable_income', an int. It will return an int which would be the tax paid on that income based on tax slabs inputed using nested IF conditions like in example output."""
    
    return instruction, question

# Module for generating tax calculation function
def generate_tax_function(model, regime_info):
    instruction, question = create_prompt(regime_info)
    result = model.generate_text(" ".join([instruction, question]))
    
    return result

# Module for extracting code from model output
def extract_code(result):
    code_as_text = result.split('Output:')[1].split('<end of code>')[0]
    return code_as_text.strip()

# Module for net income calculation
def cal_net(input_data, regime='new'):
    if regime == 'new':
        net = input_data['gross_salary'] - 75000 + input_data.get("total_other_income", 0)
    else:
        total_deductions = (
            input_data.get('exemptions_section_10', 0) + 
            input_data.get('deductions_chapter_via', 0) + 
            input_data.get('allowances', 0) + 
            input_data.get('relief_section_89', 0)
        )
        additions = input_data.get("total_other_income", 0)
        net = input_data.get('gross_salary', 0) - total_deductions + additions
    return net

