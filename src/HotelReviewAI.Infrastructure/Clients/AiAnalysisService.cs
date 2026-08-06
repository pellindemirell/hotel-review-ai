using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Infrastructure.Clients;

/// <summary>
/// Python FastAPI AI servisine HTTP istekleri gönderir.
/// Polly retry politikası DependencyInjection.cs içinde yapılandırılır.
/// AI servisi erişilemez olduğunda null döner (graceful degradation).
/// </summary>
public class AiAnalysisService : IAiAnalysisService
{
    private readonly HttpClient _httpClient;
    private readonly ILogger<AiAnalysisService> _logger;

    public AiAnalysisService(HttpClient httpClient, ILogger<AiAnalysisService> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
    }

    public async Task<AiTranslationResult?> TranslateToTurkishAsync(
        string text, string? sourceLanguage, CancellationToken ct = default)
    {
        try
        {
            var payload = new { text, sourceLang = sourceLanguage };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync("/translate", content, ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("AI çeviri servisi başarısız yanıt döndü: {StatusCode}", response.StatusCode);
                return null;
            }

            var raw = await response.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(raw);
            var root = doc.RootElement;

            return new AiTranslationResult
            {
                TranslatedText = root.TryGetProperty("translatedText", out var t) ? t.GetString() ?? "" : "",
                DetectedLanguage = root.TryGetProperty("detectedLang", out var d) ? d.GetString() ?? "" : "",
                AlreadyTurkish = root.TryGetProperty("alreadyTurkish", out var a) && a.GetBoolean()
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AI çeviri servisine erişilemedi.");
            return null;
        }
    }

    public async Task<AiAnalysisResult?> AnalyzeReviewAsync(
        string comment, int rating, string language, CancellationToken ct = default)
    {
        try
        {
            var payload = new
            {
                comment,
                rating,
                language
            };

            var json = JsonSerializer.Serialize(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            var response = await _httpClient.PostAsync("/analyze-review", content, ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning(
                    "AI servisi başarısız yanıt döndü: {StatusCode}", response.StatusCode);
                return null;
            }

            // FastAPI'den gelen snake_case JSON'ı C# DTO'ya map et
            var options = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            };

            var raw = await response.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(raw);
            var root = doc.RootElement;

            return new AiAnalysisResult
            {
                Sentiment = root.TryGetProperty("sentiment", out var s) ? s.GetString() ?? "Neutral" : "Neutral",
                SentimentScore = root.TryGetProperty("sentimentScore", out var ss) ? ss.GetDouble() : 0.0,
                Category = root.TryGetProperty("category", out var c) && c.ValueKind != JsonValueKind.Null ? c.GetString() : null,
                Keywords = root.TryGetProperty("keywords", out var kw)
                    ? kw.EnumerateArray().Select(x => x.GetString() ?? "").Where(x => !string.IsNullOrEmpty(x)).ToList()
                    : [],
                Summary = root.TryGetProperty("summary", out var sum) ? sum.GetString() ?? "" : "",
                Suggestion = root.TryGetProperty("suggestion", out var sug) ? sug.GetString() ?? "" : "",
                Confidence = root.TryGetProperty("confidence", out var conf) ? conf.GetDouble() : 0.0,
                AbsaAspects = root.TryGetProperty("absaAspects", out var absa) && absa.ValueKind == JsonValueKind.Array
                    ? absa.EnumerateArray().Select(x => new AiAbsaAspect
                    {
                        Clause = x.TryGetProperty("clause", out var cl) ? cl.GetString() ?? "" : "",
                        Aspect = x.TryGetProperty("aspect", out var asp) ? asp.GetString() ?? "" : "",
                        Department = x.TryGetProperty("department", out var dept) ? dept.GetString() ?? "" : "",
                        DepartmentLabel = x.TryGetProperty("departmentLabel", out var dl) ? dl.GetString() ?? "" : "",
                        AspectLabel = x.TryGetProperty("aspectLabel", out var al) ? al.GetString() ?? "" : (x.TryGetProperty("aspect", out var a) ? a.GetString() ?? "" : ""),
                        Sentiment = x.TryGetProperty("sentiment", out var sent) ? sent.GetString() ?? "" : "",
                        SentimentScore = x.TryGetProperty("sentimentScore", out var score) ? score.GetDouble() : 0.0,
                        Priority = x.TryGetProperty("priority", out var prio) ? prio.GetString() ?? "" : "",
                        Suggestion = x.TryGetProperty("suggestion", out var sugg) ? sugg.GetString() ?? "" : "",
                        Confidence = x.TryGetProperty("confidence", out var aconf) ? aconf.GetDouble() : 0.0,
                        Keywords = x.TryGetProperty("keywords", out var kw) && kw.ValueKind == JsonValueKind.Array
                            ? kw.EnumerateArray().Select(k => k.GetString() ?? "").Where(k => !string.IsNullOrEmpty(k)).ToList()
                            : []
                    }).ToList()
                    : []
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AI servisi çağrısı sırasında hata oluştu. Analiz atlanıyor.");
            return null;
        }
    }

    public async Task<string?> PerformOcrAsync(
        Stream imageStream, string fileName, string contentType, CancellationToken ct = default)
    {
        try
        {
            using var content = new MultipartFormDataContent();
            var streamContent = new StreamContent(imageStream);
            streamContent.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(contentType);
            content.Add(streamContent, "file", fileName);

            var response = await _httpClient.PostAsync("/ocr-image", content, ct);
            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("AI OCR servisi başarısız yanıt döndü: {StatusCode}", response.StatusCode);
                return null;
            }

            var responseJson = await response.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(responseJson);
            if (doc.RootElement.TryGetProperty("ocr_text", out var ocrProp))
            {
                return ocrProp.GetString();
            }

            return null;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AI OCR servisi çağrısı sırasında hata oluştu.");
            return null;
        }
    }

    public async Task<bool> IsHealthyAsync(CancellationToken ct = default)
    {
        try
        {
            var response = await _httpClient.GetAsync("/health", ct);
            if (!response.IsSuccessStatusCode)
                return false;

            var body = await response.Content.ReadFromJsonAsync<HealthCheckResponse>(cancellationToken: ct);
            return body?.Ready ?? false;
        }
        catch
        {
            return false;
        }
    }

    private class HealthCheckResponse
    {
        public bool Ready { get; set; }
        public string? Status { get; set; }
    }
}

