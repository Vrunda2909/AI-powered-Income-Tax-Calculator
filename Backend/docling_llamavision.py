import os
from dotenv import load_dotenv
import json
import sys

# Load environment variables from key.env
load_dotenv("key.env")

config = {
    "url": f"{os.getenv('WATSONX_URL')}/ml/v1/text/chat?version=2023-05-29",
    "model_id": "meta-llama/llama-3-2-11b-vision-instruct",
    "project_id": os.getenv('PROJECT_ID'),
    "max_tokens": 300,
    "time_limit": 10000
}

from langchain_huggingface import HuggingFaceEmbeddings
from transformers import AutoTokenizer

embeddings_model_path = "ibm-granite/granite-embedding-30m-english"
embeddings_model = HuggingFaceEmbeddings(
    model_name=embeddings_model_path,
)
embeddings_tokenizer = AutoTokenizer.from_pretrained(embeddings_model_path)

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

pdf_pipeline_options = PdfPipelineOptions(
    do_ocr=False,
    generate_picture_images=True
)
format_options = {
    InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options),
}
converter = DocumentConverter(format_options=format_options)

sources = [sys.argv[1]]
conversions = { source: converter.convert(source=source).document for source in sources }

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.types.doc.document import TableItem
from langchain_core.documents import Document

doc_id = 0
texts: list[Document] = []
for source, docling_document in conversions.items():
    for chunk in HybridChunker(tokenizer=embeddings_tokenizer).chunk(docling_document):
        items = chunk.meta.doc_items
        if len(items) == 1 and isinstance(items[0], TableItem):
            continue # we will process tables later
        refs = " ".join(map(lambda item: item.get_ref().cref, items))
        # print(refs)
        text = chunk.text
        document = Document(
            page_content=text,
            metadata={
                "doc_id": (doc_id:=doc_id+1),
                "source": source,
                "ref": refs,
            },
        )
        texts.append(document)

# print(f"{len(texts)} text document chunks created")

from docling_core.types.doc.labels import DocItemLabel

doc_id = len(texts)
tables: list[Document] = []
for source, docling_document in conversions.items():
    for table in docling_document.tables:
        if table.label in [DocItemLabel.TABLE]:
            ref = table.get_ref().cref
            # print(ref)
            text = table.export_to_markdown()
            document = Document(
                page_content=text,
                metadata={
                    "doc_id": (doc_id:=doc_id+1),
                    "source": source,
                    "ref": ref
                },
            )
            tables.append(document)

import json
extracted_data = {
    "text": "\n\n".join(doc.page_content for doc in texts),
    "tables": [doc.page_content for doc in tables],
}

with open("extracted.json", "w", encoding="utf-8") as f:
    json.dump(extracted_data, f, indent=2)
# print(f"{len(tables)} table documents created")

def get_access_token():
    iam_url = 'https://iam.cloud.ibm.com/identity/token'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {
        'grant_type': 'urn:ibm:params:oauth:grant-type:apikey',
        'apikey': os.environ['API_KEY']
    }
    response = requests.post(iam_url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        print(f"Failed to get access token: {response.status_code}")
        return None
    
import requests
def invoke_wx_ai(config, prompt):
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    body = {
        "messages": [
            {
                "role": "system",
                "content": "You are an AI assistant specializing in extracting financial details from Form 16 documents. Your task is to analyze the provided text and table data and return accurate structured data."
            },
            {
                "role": "user",
                "content": prompt  
            }
        ],
        "model_id": config["model_id"],
        "project_id": config["project_id"],
        "decoding_method": "greedy",
        "repetition_penalty": 1,
        "max_tokens": 1000
    }

    response = requests.post(config["url"], headers=headers, json=body)

    if response.status_code == 200:
        return {"response": response.json()['choices'][0]['message']['content']}
    else:
        # print(f"Error: {response.status_code}, {response.text}")
        return {"error": response.text}

def query_form16(query):
    
    with open("extracted.json", "r") as f:
        extracted_data = json.load(f)
    # User Query: {query}
    # """
    formatted_prompt = f"""
    This is a Form 16 document containing salary and tax deduction details.

    Extracted Text:
    {extracted_data['text']}

    Extracted Tables:
    {json.dumps(extracted_data['tables'], indent=2)}

    You are a tax assistant. From the extracted text and tables, extract and return the following fields in **flat JSON format**. All values must be numeric (no text, no calculations).

    ⚠️ Strict Instructions:
    - Only return valid JSON.
    - No explanations, no extra comments.
    - If a value is not available, use 0.0.
    - DO NOT use formulas like 50000 + 2400 — instead return the summed value (e.g., 52400).

    Expected JSON structure:

    {{
    "gross_salary": <Total gross salary from Section 17>,
    "exemptions_section_10": <Total exemptions under Section 10 like HRA>,
    "allowances": <Sum of standard deduction, entertainment allowance, professional tax>,
    "deductions_chapter_via": <Total deductions under Chapter VI-A>,
    "total_income": <Total taxable income>,
    "tax_on_total_income": <Tax calculated on total taxable income>,
    "rebate_87a": <Rebate if any>,
    "cession_or_surcharge": <Cess or surcharge total>,
    "relief_section_89": <Relief under Section 89 if any>,
    "net_tax_payable": <Tax payable after relief>,
    "total_other_income": <Other income if reported>,
    }}

    User Query: {query}
    """

    response = invoke_wx_ai(config, formatted_prompt)
    return response["response"]

query = "Please extract all tax-relevant financial fields from this Form 16."
response = query_form16(query)

print(response)

with open("form16.json", "w") as f:
    json.dump(json.loads(response), f, indent=2)

