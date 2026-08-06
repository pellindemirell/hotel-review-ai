import requests

data = {
    "comment": "iyi",
    "rating": 1
}

try:
    response = requests.post("http://localhost:8000/analyze-review", json=data)
    print(response.status_code)
    print(response.json())
except Exception as e:
    print("Error:", e)
