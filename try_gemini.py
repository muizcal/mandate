import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()  # reads GEMINI_API_KEY

def get_price(item: str) -> str:
    """Look up the price of an item."""
    return "12.50 USD"

resp = client.models.generate_content(
    model=os.environ["GEMINI_MODEL"],
    contents="How much does a stapler cost? Use the tool.",
    config=types.GenerateContentConfig(tools=[get_price]),
)
print(resp.text)