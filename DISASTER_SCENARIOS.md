# Olası Felaket Senaryoları ve Çözüm Önerileri (Disaster Recovery & Mitigation Guide)

Bu doküman, **HotelReviewAI** (.NET Core Backend & Python AI Servisi) sistem mimarisinde yaşanabilecek olası sistem kesintilerini, performans kilitlenmelerini, veri bozulmalarını ve bunlara karşı alınan/alınması gereken önlemleri özetler.

---

## 1. Yapay Zeka Servisinin Yavaşlaması / İstek Kuyruğunun Şişmesi (Senkron Bloklama)

### 🔴 Senaryo
Yoğun dönemlerde (örn. sezon açılışı veya kampanya günleri) sisteme saniyede onlarca yorum girişi yapıldığını varsayalım. Python tarafındaki BERT / ABSA analizi CPU ve bellek yoğun bir işlemdir. İstek başına işlem süresi 5-10 saniyeye çıkabilir.

### ⚠️ Etkisi
- **Thread Pool Starvation:** C# Web API'si, Python'dan yanıt gelene kadar o HTTP thread'ini askıda (blocked) tutar. .NET thread havuzu tükenir ve tüm API (giriş yapma, sayfaları görüntüleme dahil) yanıt veremez hale gelir.
- **504 Gateway Timeout:** Mobil/Web kullanıcıları yorum gönderirken ekran donar ve sonunda zaman aşımı hatası alırlar.

### 💡 Çözüm: Asenkron Analiz İş Akışı (Event-Driven / Background Processing)
1. **202 Accepted Dönüşü:** Yorum eklendiğinde AI servisine senkron istek atılmamalıdır. Yorum veritabanına anında `Status = Pending` veya `IsAnalyzed = false` olarak kaydedilmeli ve kullanıcıya hemen `202 Accepted` (Yorum alındı) yanıtı dönülmelidir.
2. **Kuyruk Mekanizması:** Arka planda bir kuyruk mekanizması (**RabbitMQ**, **ActiveMQ** veya .NET tarafında **BackgroundService** / **Hangfire**) kullanılarak yorumlar sırayla Python servisine gönderilmelidir.
3. **Gerçek Zamanlı Bildirim:** Analiz bittiğinde veritabanı güncellenmeli ve **SignalR (WebSockets)** ile istemcilere bildirilmelidir.

```
[İstemci / Mobil] ──(POST /reviews)──> [.NET Core API] ──(Save DB)──> [202 Accepted (Anında)]
                                              │
                                       (Enqueue Task)
                                              ▼
                                      [RabbitMQ / Queue]
                                              │
                                      (Worker Fetch)
                                              ▼
                                    [Python AI Service]
                                              │
                                       (Update DB & SignalR)
                                              ▼
                                 [İstemciye Canlı Bildirim]
```

---

## 2. API Sözleşmesi Kayması (API Contract Drift)

### 🔴 Senaryo
Python servisini geliştiren ekip, `/analyze-review` çıktısındaki JSON alan adlarını veya tiplerini değiştirebilir (örn. `sentimentScore` alanını `sentiment_score` yapmak ya da `absaAspects` dizisini farklı bir şemaya taşımak).

### ⚠️ Etkisi
- C# backend tarafındaki `AiAnalysisService.cs` içerisindeki JSON deserialization işlemi bu alanları bulamaz.
- Kodumuzda `TryGetProperty` kullanarak savunmacı bir yaklaşım sergilendiği için uygulama çökmez; ancak analiz sonuçları veritabanına sürekli boş (`null` veya varsayılan değerlerle) kaydolmaya başlar. Yönetim paneli ve istatistikler bozulur.

### 💡 Çözüm
1. **OpenAPI / Swagger Zorunluluğu:** Python FastAPI tarafında OpenAPI şeması (`http://localhost:8000/docs`) canlı tutulmalı ve versiyonlanmalıdır (v1/v2).
2. **Otomatik Entegrasyon Testleri:** C# projesindeki entegrasyon testlerine, Python servisinin güncel API çıktısını şematik olarak doğrulayan otomatik test senaryoları eklenmelidir.

---

## 3. Mobil OCR ve Yüksek Çözünürlüklü Dosya Yüklemeleri (Bant Genişliği Felaketi)

### 🔴 Senaryo
Mobil kullanıcılar yorum eklerken fatura veya oda görselini doğrudan kameradan çıktığı gibi (sıkıştırılmamış, 8MB - 15MB arası) sisteme yüklemeye çalışabilir.

### ⚠️ Etkisi
- Ağ yavaşsa yükleme dakikalar sürer, mobil uygulamanın bataryasını tüketir ve yarıda kalma olasılığını artırır.
- Sunucu tarafında IIS/Kestrel üzerinde büyük dosya yükleme sınırları (`MaxRequestBodySize`) aşılırsa istekler doğrudan reddedilir.
- OCR servisi (Tesseract / OpenCV) resmi işlerken yüksek bellek tüketiminden dolayı kilitlenebilir.

### 💡 Çözüm
1. **İstemci Tarafında Sıkıştırma:** Mobil uygulama (React Native / Flutter / Native) resim yüklemeden önce resmi cihaz içinde yeniden boyutlandırmalı ve JPEG kalitesini düşürerek boyutu en fazla 500KB - 1MB arasına indirmelidir.
2. **Bant Dışı İşleme (Off-load):** OCR işlemi senkron web isteği yerine, resim bir nesne depolama alanına (AWS S3, Azure Blob veya yerel sunucu diskine) yüklendikten sonra arka planda kuyruktan tetiklenerek yapılmalıdır.

---

## 4. Türkçe Karakter Encoding Uyuşmazlığı

### 🔴 Senaryo
Türkçe yorumlardaki karakterlerin (`ç, ğ, ı, ö, ş, ü, İ`) veri transferi sırasında doğru kodlanmaması (`UTF-8` yerine `ASCII` veya `ISO-8859-9` kullanımı).

### ⚠️ Etkisi
- Python servisi `"trke"` veya bozuk simgeler içeren karakterler alır.
- Doğal Dil İşleme (NLP) modelleri karakter bozukluğundan dolayı kelimeleri tanıyamaz ve duygu durumunu/kategoriyi yanlış tespit eder.

### 💡 Çözüm
- `AiAnalysisService.cs` içindeki `StringContent` tanımında kodlamanın her zaman `Encoding.UTF8` olduğu doğrulanmalıdır:
  ```csharp
  var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");
  ```
- Python FastAPI uygulamasında gelen isteklerin `UTF-8` olarak okunduğu middleware katmanında garanti edilmelidir.

---

## 📈 Risk Analizi ve Özet Önlemler

| Risk Alanı | Kritiklik Derecesi | Alınan Önlem (Mevcut) | Yapılması Gereken (Gelecek) |
|---|---|---|---|
| **AI Servis Kesintisi / Yavaşlama** | 🔴 Yüksek | Polly Retry & Try-Catch (Graceful Degradation) | Kuyruk tabanlı (Asenkron RabbitMQ / Hangfire) analiz mimarisine geçiş. |
| **DB Kilitlenmeleri** | 🟡 Orta | Python DB yazma yetkisi kaldırıldı (Tek sahip C#) | Veritabanında kritik indekslerin (`ReviewId`, `DepartmentId`) takibi. |
| **API Şema Değişimi (Contract Drift)** | 🟡 Orta | `TryGetProperty` ile güvenli JSON okuma | Entegrasyon testleri ve API sözleşmesi (Swagger/OpenAPI) takibi. |
| **Büyük Dosya / OCR Felaketi** | 🔴 Yüksek | Görsel netlik skoru filtresi & Stream okuma | Mobil cihazda görsel sıkıştırma ve yükleme boyutu limitleri. |
| **Karakter Encoding Uyuşmazlığı** | 🟢 Düşük | C# `Encoding.UTF8` açıkça belirtildi | Python FastAPI UTF-8 Middleware doğrulaması. |
