# AI Service API Contract — C# Backend Entegrasyonu

## 1. Servis Bilgileri

| Parametre | Değer |
|-----------|-------|
| Base URL (Dev) | `http://localhost:8001` |
| Base URL (Prod) | `http://ai-service:8001` |
| Content-Type | `application/json` |
| Encoding | UTF-8 |

## 2. Endpoint: `POST /analyze-review`

Müşteri yorumunu analiz eder: duygu, kategori, ABSA aspect'leri, öneri.

### 2.1 Request

```json
{
  "comment": "Oda temizdi ama kahvaltı kötüydü",
  "rating": 3,
  "language": "tr"
}
```

| Alan | Tip | Zorunlu | Açıklama |
|------|-----|---------|----------|
| `comment` | string | evet | Müşteri yorum metni |
| `rating` | int (1-5) | hayır | Kullanıcı puanı |
| `language` | string | hayır | Dil kodu (`tr`, `en`, `de`, `ru`) |

### 2.2 Response

```json
{
  "sentiment": "Positive",
  "sentimentScore": 0.35,
  "category": "Kat Hizmetleri & Temizlik",
  "keywords": ["oda temizliği", "kahvaltı"],
  "summary": "2 alan değerlendirildi: oda temizdi..., kahvaltı kötüydü.",
  "suggestion": "Kahvaltı saatlerinde personel takviyesi yapın.",
  "confidence": 0.92,
  "isMixedReview": true,
  "secondaryCategory": "Yiyecek & İçecek (F&B)",
  "absaAspects": [
    {
      "clause": "kahvaltı kötüydü",
      "domain": "turizm",
      "domainLabel": "Turizm",
      "department": "food_beverage",
      "departmentLabel": "Yiyecek & İçecek (F&B)",
      "aspect": "breakfast",
      "aspectLabel": "Kahvaltı",
      "sentiment": "Negative",
      "sentimentScore": -0.35,
      "confidence": 0.91,
      "priority": "high",
      "priorityScore": 4,
      "satisfactionLevel": "Az Memnun",
      "actionRequired": true,
      "keywords": ["kahvaltı", "kötü"],
      "suggestion": "Kahvaltı çeşitliliği artırılmalı."
    }
  ],
  "absaDepartmentSummary": {
    "turizm:food_beverage": {
      "domain": "turizm",
      "department": "food_beverage",
      "departmentLabel": "Yiyecek & İçecek (F&B)",
      "total": 1,
      "negative": 1,
      "positive": 0,
      "neutral": 0
    },
    "turizm:housekeeping": {
      "domain": "turizm",
      "department": "housekeeping",
      "departmentLabel": "Kat Hizmetleri & Temizlik",
      "total": 1,
      "negative": 0,
      "positive": 1,
      "neutral": 0
    }
  }
}
```

### 2.3 Response Alanları

| Alan | Tip | Açıklama |
|------|-----|----------|
| `sentiment` | string | `"Positive"` / `"Negative"` / `"Neutral"` |
| `sentimentScore` | float | -1.0 ile 1.0 arası |
| `category` | string | Birincil departman label'ı (kanonik 8'li) |
| `absaAspects[]` | array | Her cümlecik için aspect detayı (aşağıya bak) |
| `absaDepartmentSummary` | object | Departman bazında duygu özeti |

#### absaAspect Alanları

| Alan | Tip | Örnek | Açıklama |
|------|-----|-------|----------|
| `clause` | string | `"kahvaltı kötüydü"` | Cümlecik metni |
| `department` | string | `"food_beverage"` | Departman anahtarı (İngilizce) |
| `departmentLabel` | string | `"Yiyecek & İçecek (F&B)"` | Departman etiketi (Türkçe, kanonik) |
| `aspect` | string | `"breakfast"` | Aspect anahtarı |
| `aspectLabel` | string | `"Kahvaltı"` | Aspect etiketi |
| `sentiment` | string | `"Negative"` | Duygu (İngilizce) |
| `sentimentScore` | float | -0.35 | Duygu skoru (-1.0 .. 1.0) |
| `confidence` | float | 0.91 | Güven skoru (0.0 .. 1.0) |
| `priority` | string | `"high"` | Öncelik: `"critical"` / `"high"` / `"medium"` / `"low"` / `"info"` |
| `priorityScore` | int | 4 | Öncelik puanı (1-5) |
| `satisfactionLevel` | string | `"Az Memnun"` | Memnuniyet seviyesi |
| `actionRequired` | bool | true | Aksiyon gerekli mi |
| `keywords` | string[] | `["kahvaltı","kötü"]` | Anahtar kelimeler |
| `suggestion` | string | `"Kahvaltı çeşitliliği..."` | İyileştirme önerisi |

## 3. Kanonik Departman Seti (8 Departman)

Tüm aspect'ler aşağıdaki 8 departmandan birine atanır:

| Department Key | Department Label (Türkçe) | Kapsam |
|---------------|---------------------------|--------|
| `housekeeping` | Kat Hizmetleri & Temizlik | Oda temizliği, nevresim, banyo, genel hijyen |
| `food_beverage` | Yiyecek & İçecek (F&B) | Restoran, bar, kahvaltı, yemek kalitesi, içecek |
| `front_office` | Ön Büro & Misafir İlişkileri | Resepsiyon, check-in/out, misafir ilişkileri |
| `engineering` | Teknik Servis & IT | Klima, WiFi, TV, su tesisatı, elektrik |
| `leisure` | Rekreasyon & Eğlence | Havuz, aquapark, animasyon, plaj, spor alanları |
| `grounds` | Çevre, Güvenlik & Ulaşım | Otopark, bahçe, güvenlik, ulaşım, konum |
| `atmosphere` | Otel Atmosferi & Misafir Profili | Manzara, genel atmosfer, kalabalık, müşteri profili |
| `staff` | Personel Davranışı | Personel tutumu, güleryüz, ilgi, profesyonellik |

## 4. C# DTO'lar (.NET 8 / C# 12)

```csharp
using System.Text.Json.Serialization;

public class ReviewRequest
{
    [JsonPropertyName("comment")]
    public string Comment { get; set; } = string.Empty;

    [JsonPropertyName("rating")]
    public int? Rating { get; set; }

    [JsonPropertyName("language")]
    public string? Language { get; set; }
}

public class ReviewResponse
{
    [JsonPropertyName("sentiment")]
    public string Sentiment { get; set; } = string.Empty;

    [JsonPropertyName("sentimentScore")]
    public double SentimentScore { get; set; }

    [JsonPropertyName("category")]
    public string Category { get; set; } = string.Empty;

    [JsonPropertyName("keywords")]
    public List<string> Keywords { get; set; } = new();

    [JsonPropertyName("summary")]
    public string Summary { get; set; } = string.Empty;

    [JsonPropertyName("suggestion")]
    public string Suggestion { get; set; } = string.Empty;

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("isMixedReview")]
    public bool IsMixedReview { get; set; }

    [JsonPropertyName("secondaryCategory")]
    public string? SecondaryCategory { get; set; }

    [JsonPropertyName("absaAspects")]
    public List<AbsaAspect>? AbsaAspects { get; set; }

    [JsonPropertyName("absaDepartmentSummary")]
    public Dictionary<string, DepartmentSummary>? AbsaDepartmentSummary { get; set; }
}

public class AbsaAspect
{
    [JsonPropertyName("clause")]
    public string Clause { get; set; } = string.Empty;

    [JsonPropertyName("department")]
    public string Department { get; set; } = string.Empty;

    [JsonPropertyName("departmentLabel")]
    public string DepartmentLabel { get; set; } = string.Empty;

    [JsonPropertyName("aspect")]
    public string Aspect { get; set; } = string.Empty;

    [JsonPropertyName("aspectLabel")]
    public string AspectLabel { get; set; } = string.Empty;

    [JsonPropertyName("sentiment")]
    public string Sentiment { get; set; } = string.Empty;

    [JsonPropertyName("sentimentScore")]
    public double SentimentScore { get; set; }

    [JsonPropertyName("confidence")]
    public double Confidence { get; set; }

    [JsonPropertyName("priority")]
    public string Priority { get; set; } = string.Empty;

    [JsonPropertyName("priorityScore")]
    public int PriorityScore { get; set; }

    [JsonPropertyName("satisfactionLevel")]
    public string SatisfactionLevel { get; set; } = string.Empty;

    [JsonPropertyName("actionRequired")]
    public bool ActionRequired { get; set; }

    [JsonPropertyName("keywords")]
    public List<string> Keywords { get; set; } = new();

    [JsonPropertyName("suggestion")]
    public string Suggestion { get; set; } = string.Empty;
}

public class DepartmentSummary
{
    [JsonPropertyName("domain")]
    public string Domain { get; set; } = string.Empty;

    [JsonPropertyName("department")]
    public string Department { get; set; } = string.Empty;

    [JsonPropertyName("departmentLabel")]
    public string DepartmentLabel { get; set; } = string.Empty;

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("positive")]
    public int Positive { get; set; }

    [JsonPropertyName("negative")]
    public int Negative { get; set; }

    [JsonPropertyName("neutral")]
    public int Neutral { get; set; }
}
```

## 5. C# HttpClient Kullanımı

```csharp
public class AiServiceClient
{
    private readonly HttpClient _httpClient;

    public AiServiceClient(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.BaseAddress = new Uri("http://localhost:8001");
    }

    public async Task<ReviewResponse?> AnalyzeReviewAsync(
        string comment, int? rating = null, string? language = null)
    {
        var request = new ReviewRequest
        {
            Comment = comment,
            Rating = rating,
            Language = language
        };

        var response = await _httpClient.PostAsJsonAsync("/analyze-review", request);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<ReviewResponse>();
    }
}
```

## 6. Değişiklik Geçmişi

| Tarih | Versiyon | Açıklama |
|-------|----------|----------|
| 2026-07-21 | 2.0 | Kanonik 8 departman setine geçiş. `departmentLabel` Türkçe etiket olarak eklendi. Tüm non-canonical label'lar temizlendi (Restaurant, Havuz, Animasyon, Odalar, vs.) |
