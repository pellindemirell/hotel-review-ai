using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Infrastructure.Services;

/// <summary>
/// AI model eğitimi bitene kadar veya yerel testlerde FastAPI'ye bağımlı olmadan 
/// sahte analiz sonuçları dönen geçici servis implementasyonu (Feature Toggle).
/// </summary>
public class FakeAiAnalysisService : IAiAnalysisService
{
    public Task<AiAnalysisResult?> AnalyzeReviewAsync(
        string comment, int rating, string language, CancellationToken ct = default)
    {
        var (sentiment, score) = rating switch
        {
            <= 2 => ("Negative", rating == 1 ? -0.9 : -0.6),
            3 => ("Neutral", 0.0),
            _ => ("Positive", rating == 5 ? 0.9 : 0.6)
        };

        var category = rating switch
        {
            <= 2 when comment.Contains("temiz", StringComparison.OrdinalIgnoreCase) || comment.Contains("kirli", StringComparison.OrdinalIgnoreCase) => "Temizlik",
            <= 2 when comment.Contains("yemek", StringComparison.OrdinalIgnoreCase) || comment.Contains("soğuk", StringComparison.OrdinalIgnoreCase) => "Yemek",
            _ => "Personel"
        };

        var suggestion = sentiment switch
        {
            "Negative" => "Müşteri memnuniyetsizliği acilen giderilmeli, ilgili alan denetlenmelidir.",
            "Positive" => "Hizmet standartları korunmalı ve misafire teşekkür edilmelidir.",
            _ => "Geri bildirim hizmet kalitesini artırmak üzere takip listesine eklenmelidir."
        };

        var words = comment.Split(' ');
        var summary = words.Length > 8 ? string.Join(" ", words.Take(8)) + "..." : comment;

        var absaAspects = new List<AiAbsaAspect>();
        if (comment.Contains("ama", StringComparison.OrdinalIgnoreCase) || comment.Contains("ve", StringComparison.OrdinalIgnoreCase))
        {
            absaAspects.Add(new AiAbsaAspect
            {
                Clause = "Oda temizliği çok iyiydi",
                Department = "housekeeping",
                Sentiment = "Positive",
                SentimentScore = 0.9,
                Priority = "Bilgi",
                Suggestion = "Temizlik standartları korunmalıdır."
            });

            absaAspects.Add(new AiAbsaAspect
            {
                Clause = "kahvaltı biraz soğuktu",
                Department = "food_beverage",
                Sentiment = "Negative",
                SentimentScore = -0.7,
                Priority = "Yuksek",
                Suggestion = "F&B kahvaltı sıcaklık kontrolleri artırılmalıdır."
            });
        }
        else
        {
            absaAspects.Add(new AiAbsaAspect
            {
                Clause = comment,
                Department = rating <= 2 ? "housekeeping" : "staff",
                Sentiment = sentiment,
                SentimentScore = score,
                Priority = sentiment == "Negative" ? "Yuksek" : "Bilgi",
                Suggestion = suggestion
            });
        }

        var result = new AiAnalysisResult
        {
            Sentiment = sentiment,
            SentimentScore = score,
            Category = category,
            Keywords = new List<string> { "oda", "hizmet", "personel" },
            Summary = summary,
            Suggestion = suggestion,
            Confidence = 0.95,
            AbsaAspects = absaAspects
        };

        return Task.FromResult<AiAnalysisResult?>(result);
    }

    public Task<string?> PerformOcrAsync(
        Stream imageStream, string fileName, string contentType, CancellationToken ct = default)
    {
        var fakeOcr = "[Fake OCR: Yorum görselindeki metin başarıyla okundu. Oda temizliği çok kötüydü ama personel ilgiliydi.]";
        return Task.FromResult<string?>(fakeOcr);
    }
}
