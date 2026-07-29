using HotelReviewAI.Application.DTOs;

namespace HotelReviewAI.Application.Interfaces;

/// <summary>
/// Python FastAPI AI servisine erişimi soyutlayan arayüz.
/// </summary>
public interface IAiAnalysisService
{
    /// <summary>
    /// Tek bir yorumu analiz eder; sentiment, kategori, anahtar kelimeler ve öneri döner.
    /// AI servisi erişilemez olduğunda null döner (graceful degradation).
    /// </summary>
    Task<AiAnalysisResult?> AnalyzeReviewAsync(string comment, int rating, string language, CancellationToken ct = default);

    /// <summary>
    /// Yorum görselindeki metni OCR ile okur.
    /// </summary>
    Task<string?> PerformOcrAsync(Stream imageStream, string fileName, string contentType, CancellationToken ct = default);
}
