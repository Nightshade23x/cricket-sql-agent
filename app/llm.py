import json 
import urllib.request  # Used to send requests to the local Ollama server

MODEL_NAME = "qwen2.5-coder:3b"  # This is the local Ollama model we are using

def ask_ollama(prompt):  # This function sends a prompt to Ollama and returns the model response
    url = "http://localhost:11434/api/generate"  # This is the local Ollama API endpoint

    data = {  # This dictionary contains the request data for Ollama
        "model": MODEL_NAME,  # This tells Ollama which model to use
        "prompt": prompt,  # This is the prompt we want to send to the model
        "stream": False  # This tells Ollama to return the full response at once
    }
    json_data = json.dumps(data).encode("utf-8")  # Converts the dictionary into JSON bytes
    request = urllib.request.Request(  # Creates the HTTP request
        url,  # The Ollama API URL
        data=json_data,  # The JSON data being sent
        headers={"Content-Type": "application/json"}  # Tells Ollama we are sending JSON
    )
    response = urllib.request.urlopen(request)  # Sends the request to Ollama
    response_text = response.read().decode("utf-8")  # Reads the response and converts it to text
    response_data = json.loads(response_text)  # Converts the JSON response into a Python dictionary
    return response_data["response"]  # Returns only the model's generated text

def clean_sql_response(response):
    response = response.strip()

    response = response.replace("```sql", "")
    response = response.replace("```", "")

    response = response.strip()

    return response