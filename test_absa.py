import requests
import json

data = {
    "comment": "oda çok pis klima bozuk havlular ıslak kahvaltı çok kötü personel ilgisiz",
    "rating": 1
}

response = requests.post("http://localhost:8000/analyze-review", json=data)
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
