import json 
import urllib.request  # Used to send requests to the local Ollama server

MODEL_NAME = "qwen2.5-coder:3b"  # This is the local Ollama model we are using

def ask_ollama(prompt):
    url = "http://localhost:11434/api/generate"

    data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 250
        }
    }

    json_data = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=json_data,
        headers={"Content-Type": "application/json"}
    )

    response = urllib.request.urlopen(request, timeout=120)

    response_text = response.read().decode("utf-8")

    response_data = json.loads(response_text)

    return response_data["response"]

def clean_sql_response(response):
    response = response.strip()

    response = response.replace("```sql", "")
    response = response.replace("```", "")

    response = response.strip()

    return response