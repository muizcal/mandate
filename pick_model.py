import os, time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(http_options=types.HttpOptions(timeout=30_000))

SKIP = ("tts", "image", "live", "embedding", "robotics", "omni", "transcribe",
        "computer-use", "antigravity", "deep-research", "lyria", "gemma",
        "nano-banana", "customtools", "aqa", "veo", "imagen")

names = []
for m in client.models.list():
    n = m.name.replace("models/", "")
    if ("generateContent" in (m.supported_actions or []) and "flash" in n
            and not any(s in n for s in SKIP)):
        names.append(n)
names = sorted(names, reverse=True)[:10]
print("Testing:", ", ".join(names), "\n")

decl = types.FunctionDeclaration(
    name="get_price", description="Look up an item's price.",
    parameters=types.Schema(type="OBJECT",
                            properties={"item": types.Schema(type="STRING")},
                            required=["item"]))
cfg = types.GenerateContentConfig(
    tools=[types.Tool(function_declarations=[decl])],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))

good = []
for n in names:
    t = time.time()
    try:
        r = client.models.generate_content(
            model=n, contents="How much does a stapler cost? Use the tool.", config=cfg)
        secs = time.time() - t
        if r.function_calls:
            print(f"PASS  {n:36s} {secs:5.1f}s  tool call ok")
            good.append((secs, n))
        else:
            print(f"WEAK  {n:36s} {secs:5.1f}s  answered without calling the tool")
    except Exception as e:
        msg = str(e).replace("\n", " ")[:95]
        print(f"FAIL  {n:36s} {time.time() - t:5.1f}s  {msg}")
    time.sleep(2)

print()
if good:
    good.sort()
    print("Put these in .env:")
    print("GEMINI_MODEL=" + good[0][1])
    if len(good) > 1:
        print("GEMINI_FALLBACK_MODEL=" + good[1][1])
else:
    print("No model passed. Paste the output above and I'll work out why.")