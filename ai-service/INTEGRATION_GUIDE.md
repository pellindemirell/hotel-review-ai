# 🚀 Otel Restoran Akıllı ABSA AI Servisi — Frontend & Backend Entegrasyon Rehberi

Bu belge, güncellenmiş **ABSA (Aspect-Based Sentiment Analysis) Yapılandırılmış AI Servisi**'nin mevcut veya yeni **Frontend (Web/Mobil UI)** ve **Backend (API Gateway / Ana Sunucu)** mimarinize entegre edilmesi için hazırlanmıştır.

---

## 🏗️ 1. Mimari Genel Bakış

```
[ FRONTEND ] (React / Next.js / Vue / Mobil App)
      │
      │ HTTP / REST (JSON)
      ▼
[ ANA BACKEND SUNUCUSU ] (Node.js / Python / Java / C# / PHP)
      │
      │ HTTP / REST (veya Doğrudan Mikroservis Çağrısı)
      ▼
[ ABSA AI SERVICE (FastAPI) ] (Port: 8000)
      ├── POST /analyze-absa                (Çoklu Cümlecik & Departman ABSA Analizi)
      ├── POST /analyze-review-legacy       (Genel Kategori, Duygu & Öneri Analizi)
      └── POST /review-intelligence/analyze (Derin 14 Aşamalı Operasyonel Analiz)
```

---

## 📡 2. Temel API Endpoint'leri ve Kullanımı

### 🔹 Endpoint 1: ABSA Analizi (`POST /analyze-absa`)
Yorumu cümleciklere bölerek her bir cümlenin departmanını (F&B, Kat Hizmetleri, Ön Büro vb.), duygusunu (%100 Negation Shield doğruluğu ile), öncelik puanını ve çözüm önerisini döner.

#### **İstek (Request Body)**
```json
{
  "comment": "Kahvaltı harikaydı ve lezzetlere duyarlıydılar ama odadaki klima çok gürültülüydü, hiç memnun kalmadık.",
  "rating": 3,
  "language": "tr"
}
```

#### **Yanıt (Response Body)**
```json
{
  "aspects": [
    {
      "clause": "Kahvaltı harikaydı ve lezzetlere duyarlıydılar",
      "aspect": "Yemek Lezzeti",
      "department": "Yiyecek & İçecek (F&B)",
      "sentiment": "Positive",
      "sentimentScore": 0.85,
      "confidence": 0.95,
      "priority": "low",
      "priorityScore": 10,
      "satisfactionLevel": "High",
      "keywords": ["kahvaltı", "lezzet"],
      "suggestion": "Kahvaltı kalitesini ve lezzet standardını korumaya devam edin."
    },
    {
      "clause": "ama odadaki klima çok gürültülüydü",
      "aspect": "İklimlendirme / Klima",
      "department": "Teknik Servis & IT",
      "sentiment": "Negative",
      "sentimentScore": -0.80,
      "confidence": 0.92,
      "priority": "high",
      "priorityScore": 85,
      "satisfactionLevel": "Low",
      "keywords": ["klima", "gürültü"],
      "suggestion": "Teknik servis ekibi klima motor sesini acilen kontrol etmelidir."
    },
    {
      "clause": "hiç memnun kalmadık",
      "aspect": "Genel Deneyim",
      "department": "Misafir İlişkileri",
      "sentiment": "Negative",
      "sentimentScore": -0.90,
      "confidence": 0.98,
      "priority": "critical",
      "priorityScore": 95,
      "satisfactionLevel": "Low",
      "keywords": ["memnun kalmadık"],
      "suggestion": "Misafir ile doğrudan iletişime geçilerek telafi teklif edilmelidir."
    }
  ],
  "overallSentiment": "Mixed",
  "overallScore": -0.28,
  "isMultiAspect": true,
  "aspectCount": 3,
  "departmentSummary": {
    "Yiyecek & İçecek (F&B)": {"count": 1, "sentiment": "Positive"},
    "Teknik Servis & IT": {"count": 1, "sentiment": "Negative"},
    "Misafir İlişkileri": {"count": 1, "sentiment": "Negative"}
  }
}
```

---

## 💻 3. Kod Örnekleri Entegrasyonu

### 🅰️ Node.js / Express (Backend Entegrasyonu)
```javascript
const axios = require('axios');

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8000';

async function analyzeHotelReview(reviewText, rating = null) {
  try {
    const response = await axios.post(`${AI_SERVICE_URL}/analyze-absa`, {
      comment: reviewText,
      rating: rating,
      language: 'tr'
    });
    
    return response.data;
  } catch (error) {
    console.error('AI Service Error:', error.message);
    throw error;
  }
}
```

### 🅱️ Python / FastAPI / Flask (Backend Entegrasyonu)
```python
import requests

AI_SERVICE_URL = "http://localhost:8000"

def analyze_review(comment: str, rating: int = None):
    payload = {
        "comment": comment,
        "rating": rating,
        "language": "tr"
    }
    response = requests.post(f"{AI_SERVICE_URL}/analyze-absa", json=payload)
    return response.json()
```

### 🅲 React / Next.js / Vue (Frontend Entegrasyonu)
```javascript
import React, { useState } from 'react';

export default function ReviewAnalyzer() {
  const [comment, setComment] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleAnalyze = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/analyze-absa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment })
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      alert('Analiz hatası!');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h2>Otel Akıllı Yorum Analizi</h2>
      <textarea 
        rows="4" 
        style={{ width: '100%' }}
        value={comment} 
        onChange={(e) => setComment(e.target.value)}
        placeholder="Yorumunuzu girin..."
      />
      <button onClick={handleAnalyze} disabled={loading} style={{ marginTop: '10px', padding: '10px 20px' }}>
        {loading ? 'Analiz Ediliyor...' : 'Analiz Et'}
      </button>

      {result && (
        <div style={{ marginTop: '20px' }}>
          <h3>Genel Duygu: {result.overallSentiment}</h3>
          <h4>Departman Aspect Detayları:</h4>
          <ul>
            {result.aspects.map((asp, idx) => (
              <li key={idx}>
                <strong>[{asp.department}]</strong> {asp.clause} — 
                <span style={{ color: asp.sentiment === 'Positive' ? 'green' : 'red' }}>
                  {asp.sentiment} ({asp.sentimentScore})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

---

## ⚡ 4. Dağıtım & Docker Kurulumu (Deployment)

Sunucunuzda veya bulutta (AWS, GCP, DigitalOcean, Hetzner, Docker Swarm, Kubernetes) çalıştırmak için:

```bash
# 1. Klasöre gidin
cd ai-service

# 2. Docker container'larını başlatın
docker-compose up --build -d
```
Servis arka planda `http://localhost:8000` adresinde hazır olur ve Swagger canlı dokümantasyonuna `http://localhost:8000/docs` adresinden erişebilirsiniz.
