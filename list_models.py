from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()  # reads GEMINI_API_KEY

for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(m.name.replace("models/", ""))