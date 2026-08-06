using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using Microsoft.Extensions.Logging;
using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Services;

/// <summary>
/// Yorumların AI analizi ve otomatik aksiyon süreçlerini yöneten servis implementasyonu.
/// </summary>
public class ReviewAnalysisProcessingService : IReviewAnalysisProcessingService
{
    // ActionItemConfiguration: Title -> HasMaxLength(300). Başlık cümle metninden
    // kurulduğu için uzun bir cümle kaydı patlatıyordu ("22001: value too long for
    // type character varying(300)") ve iş sonsuza dek Processing'de kalıyordu.
    private const int ActionItemTitleMaxLength = 300;

    /// <summary>
    /// Başlığı kolon sınırına sığdırır; kesme gerekiyorsa sonuna "..." koyar.
    /// </summary>
    private static string TruncateTitle(string title)
    {
        if (string.IsNullOrEmpty(title) || title.Length <= ActionItemTitleMaxLength)
        {
            return title;
        }

        return string.Concat(title.AsSpan(0, ActionItemTitleMaxLength - 3), "...");
    }

    private readonly IReviewAnalysisRepository _reviewAnalysisRepository;
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IReviewCategoryRepository _categoryRepository;
    private readonly IAiAnalysisService _aiAnalysisService;
    private readonly IDepartmentRepository _departmentRepository;
    private readonly ILogger<ReviewAnalysisProcessingService> _logger;

    public ReviewAnalysisProcessingService(
        IReviewAnalysisRepository reviewAnalysisRepository,
        IActionItemRepository actionItemRepository,
        IReviewCategoryRepository categoryRepository,
        IAiAnalysisService aiAnalysisService,
        IDepartmentRepository departmentRepository,
        ILogger<ReviewAnalysisProcessingService> logger)
    {
        _reviewAnalysisRepository = reviewAnalysisRepository;
        _actionItemRepository = actionItemRepository;
        _categoryRepository = categoryRepository;
        _aiAnalysisService = aiAnalysisService;
        _departmentRepository = departmentRepository;
        _logger = logger;
    }

    public async Task ProcessAnalysisAsync(Review review, bool isReanalysis, CancellationToken cancellationToken)
    {
        // Idempotency: yeniden denemede (RetryCount>0) veya kısmi yazma sonrası aynı yorum
        // için ikinci bir analiz seti üretilmesin. Önceden her deneme yeni ReviewAnalysis
        // ve yeni ActionItem ekliyor, çift kayıt oluşuyordu.
        if (!isReanalysis)
        {
            var existing = await _reviewAnalysisRepository.GetByReviewIdAsync(review.Id);
            if (existing.Any())
            {
                _logger.LogInformation(
                    "Yorum {ReviewId} için zaten {Count} analiz kaydı var; tekrar analiz edilmiyor.",
                    review.Id, existing.Count());
                return;
            }
        }

        // AI servisine analiz isteği gönder (graceful degradation: null dönerse atla)
        var aiResult = await _aiAnalysisService.AnalyzeReviewAsync(
            review.Comment, review.Rating, review.Language, cancellationToken);

        if (aiResult is null)
        {
            _logger.LogWarning("AI servisi yanıt vermedi, yorum ID: {ReviewId}. Analiz erteleniyor.", review.Id);
            throw new InvalidOperationException($"AI Analysis failed for ReviewId: {review.Id}");
        }

        var prefix = isReanalysis ? "[Yeniden Analiz]" : "[Otomatik]";
        var absaPrefix = isReanalysis ? "[ABSA Yeniden Analiz]" : "[ABSA Otomatik]";

        // Eşleşen ABSA aspect'leri varsa her biri için ayrı analiz ve aksiyon kaydı oluştur
        if (aiResult.AbsaAspects != null && aiResult.AbsaAspects.Any())
        {
            int idx = 0;
            foreach (var aspect in aiResult.AbsaAspects)
            {
                var (deptId, matchedCategory) = await ResolveDepartmentAndCategoryAsync(
                    aspect.Department, aspect.Clause, review.HotelId, aspect.Aspect);

                var aspectSentiment = aspect.Sentiment switch
                {
                    "Positive" => Sentiment.Positive,
                    "Negative" => Sentiment.Negative,
                    _ => Sentiment.Neutral
                };

                var aspectPriority = aspect.Priority?.ToLowerInvariant() switch
                {
                    "critical" or "kritik" => Priority.Critical,
                    "high" or "yuksek" or "yüksek" => Priority.High,
                    "medium" or "orta" => Priority.Medium,
                    _ => Priority.Info
                };

                var analysis = new ReviewAnalysis
                {
                    ReviewId = review.Id,
                    ClauseIndex = idx++,
                    ClauseText = aspect.Clause,
                    Sentiment = aspectSentiment,
                    SentimentScore = aspect.SentimentScore,
                    Priority = aspectPriority,
                    CategoryId = matchedCategory?.Id,
                    Suggestion = aspect.Suggestion,
                    // Aspect'in kendi güven skoru; yoksa yorumun genel skoruna düşülür.
                    // Önceden her aspect'e genel ortalama yazılıyordu.
                    Confidence = aspect.Confidence > 0 ? aspect.Confidence : aiResult.Confidence,
                    Keywords = aspect.Keywords != null && aspect.Keywords.Any() ? aspect.Keywords : (idx == 1 ? aiResult.Keywords : []),
                    Summary = idx == 1 ? aiResult.Summary : null,
                    AspectLabel = aspect.AspectLabel,
                    DepartmentLabel = aspect.DepartmentLabel
                };

                await _reviewAnalysisRepository.AddAsync(analysis);

                // Negatif aspect'ler için ilgili departmana otomatik ActionItem oluştur
                if (aspectSentiment == Sentiment.Negative && deptId.HasValue)
                {
                    var catTitle = matchedCategory?.Name;
                    if (string.IsNullOrEmpty(catTitle))
                    {
                        catTitle = !string.IsNullOrEmpty(aspect.AspectLabel) ? aspect.AspectLabel : aspect.Department;
                    }

                    var actionItem = new ActionItem
                    {
                        ReviewId = review.Id,
                        HotelId = review.HotelId,
                        DepartmentId = deptId.Value,
                        CategoryId = matchedCategory?.Id,
                        Title = TruncateTitle($"{absaPrefix} [{catTitle}] {aspect.Clause}"),
                        Status = ActionItemStatus.Open,
                        DueDate = DateTime.UtcNow.AddDays(3)
                    };

                    await _actionItemRepository.AddAsync(actionItem);

                    _logger.LogInformation(
                        "Negatif aspect için otomatik aksiyon oluşturuldu. ReviewId: {ReviewId}, Dept: {DeptKey}, Category: {CatTitle}",
                        review.Id, aspect.Department, catTitle);
                }
            }
        }
        else
        {
            // Düz analiz yapısı (Legacy fallback)
            ReviewCategory? category = null;
            if (!string.IsNullOrEmpty(aiResult.Category))
            {
                var allCategories = await _categoryRepository.GetAllAsync();
                var departments = await _departmentRepository.GetAllAsync();
                var hotelDepartmentIds = departments.Where(d => d.HotelId == review.HotelId).Select(d => d.Id).ToList();
                category = allCategories.FirstOrDefault(c => c.Name == aiResult.Category && hotelDepartmentIds.Contains(c.DepartmentId)) 
                           ?? allCategories.FirstOrDefault(c => c.Name == aiResult.Category);
            }

            var sentimentEnum = aiResult.Sentiment switch
            {
                "Positive" => Sentiment.Positive,
                "Negative" => Sentiment.Negative,
                _ => Sentiment.Neutral
            };

            var priorityEnum = sentimentEnum == Sentiment.Negative ? Priority.High : Priority.Info;

            var analysis = new ReviewAnalysis
            {
                ReviewId = review.Id,
                ClauseIndex = 0,
                ClauseText = review.Comment,
                Sentiment = sentimentEnum,
                SentimentScore = aiResult.SentimentScore,
                Priority = priorityEnum,
                CategoryId = category?.Id,
                Suggestion = aiResult.Suggestion,
                Confidence = aiResult.Confidence,
                Keywords = aiResult.Keywords,
                Summary = aiResult.Summary
            };

            await _reviewAnalysisRepository.AddAsync(analysis);

            if (sentimentEnum == Sentiment.Negative)
            {
                Guid? deptId = category?.DepartmentId;
                if (!deptId.HasValue)
                {
                    var departments = await _departmentRepository.GetAllAsync();
                    var hotelDepts = departments.Where(d => !review.HotelId.HasValue || d.HotelId == review.HotelId).ToList();
                    deptId = hotelDepts.FirstOrDefault(d => d.Key == "grounds" || d.Key == "front_office")?.Id
                             ?? hotelDepts.FirstOrDefault()?.Id;
                }

                if (deptId.HasValue)
                {
                    var catTitle = category?.Name ?? "Genel Şikayet";
                    var actionItem = new ActionItem
                    {
                        ReviewId = review.Id,
                        HotelId = review.HotelId,
                        DepartmentId = deptId.Value,
                        CategoryId = category?.Id,
                        Title = TruncateTitle($"{prefix} {catTitle}: {(review.Comment.Length > 80 ? review.Comment[..80] + "..." : review.Comment)}"),
                        Status = ActionItemStatus.Open,
                        DueDate = DateTime.UtcNow.AddDays(3)
                    };

                    await _actionItemRepository.AddAsync(actionItem);
                }
            }
        }

        await _reviewAnalysisRepository.SaveChangesAsync();
        await _actionItemRepository.SaveChangesAsync();
    }

    private async Task<(Guid? DepartmentId, ReviewCategory? MatchedCategory)> ResolveDepartmentAndCategoryAsync(
        string departmentKey, string clause, Guid? hotelId = null, string? aspectKey = null)
    {
        var departments = await _departmentRepository.GetAllAsync();
        var department = departments.FirstOrDefault(d =>
            (d.Key.Equals(departmentKey, StringComparison.OrdinalIgnoreCase) ||
             d.Name.Equals(departmentKey, StringComparison.OrdinalIgnoreCase) ||
             d.Name.Contains(departmentKey, StringComparison.OrdinalIgnoreCase) ||
             departmentKey.Contains(d.Key, StringComparison.OrdinalIgnoreCase)) &&
            (!hotelId.HasValue || d.HotelId == hotelId.Value))
            ?? departments.FirstOrDefault(d =>
                d.Key.Equals(departmentKey, StringComparison.OrdinalIgnoreCase) ||
                d.Name.Equals(departmentKey, StringComparison.OrdinalIgnoreCase) ||
                d.Name.Contains(departmentKey, StringComparison.OrdinalIgnoreCase));

        if (department == null)
        {
            var lowerDeptKey = (departmentKey ?? "").ToLowerInvariant();
            department = departments.FirstOrDefault(d =>
                (!hotelId.HasValue || d.HotelId == hotelId.Value) &&
                (
                    (lowerDeptKey.Contains("personel") && (d.Key == "staff" || d.Name.Contains("Kaynakları"))) ||
                    ((lowerDeptKey.Contains("ulaşım") || lowerDeptKey.Contains("transfer") || lowerDeptKey.Contains("güvenlik")) && (d.Key == "grounds" || d.Name.Contains("Ulaşım") || d.Name.Contains("Güvenlik"))) ||
                    ((lowerDeptKey.Contains("yiyecek") || lowerDeptKey.Contains("içecek") || lowerDeptKey.Contains("restoran") || lowerDeptKey.Contains("mutfak")) && (d.Key == "food_beverage" || d.Name.Contains("İçecek"))) ||
                    ((lowerDeptKey.Contains("temizlik") || lowerDeptKey.Contains("oda") || lowerDeptKey.Contains("banyo") || lowerDeptKey.Contains("housekeeping")) && (d.Key == "housekeeping" || d.Name.Contains("Temizlik") || d.Name.Contains("Hizmetleri"))) ||
                    ((lowerDeptKey.Contains("teknik") || lowerDeptKey.Contains("klima") || lowerDeptKey.Contains("wifi")) && (d.Key == "engineering" || d.Name.Contains("Teknik"))) ||
                    ((lowerDeptKey.Contains("eğlence") || lowerDeptKey.Contains("spa") || lowerDeptKey.Contains("havuz") || lowerDeptKey.Contains("animasyon")) && (d.Key == "leisure" || d.Name.Contains("Eğlence"))) ||
                    ((lowerDeptKey.Contains("resepsiyon") || lowerDeptKey.Contains("ön büro") || lowerDeptKey.Contains("giris")) && (d.Key == "front_office" || d.Name.Contains("Ön Büro")))
                )
            );
        }

        // Eşleşme yoksa departman BOŞ bırakılır. Önceden "listenin ilk departmanı"na
        // düşülüyordu; bu, tamamen alakasız bir departmana otomatik görev açılmasına
        // yol açıyordu (ör. wifi şikayeti İnsan Kaynakları'na).
        if (department == null)
        {
            _logger.LogWarning(
                "AI'dan gelen departman eşleştirilemedi: '{DepartmentKey}' (otel: {HotelId}). " +
                "Analiz departmansız kaydedilecek, otomatik görev açılmayacak.",
                departmentKey, hotelId);
        }

        var categories = await _categoryRepository.GetAllAsync();
        var lowerClause = clause.ToLowerInvariant();

        ReviewCategory? matchedCategory = null;
        int maxLen = 0;

        var availableCategories = department != null
            ? categories.Where(c => c.DepartmentId == department.Id).ToList()
            : categories.ToList();

        // 1) Önce AI'ın aspect anahtarıyla doğrudan eşle. Python'un aspect key'leri
        // ("room_cleanliness", "breakfast"…) ReviewCategory.Key ile aynı sözlükten geliyor;
        // bu hazır eşleşme önceden hiç kullanılmıyor, kategori clause içinde keyword
        // aranarak yeniden tahmin ediliyordu.
        if (!string.IsNullOrWhiteSpace(aspectKey))
        {
            var byKey = availableCategories.FirstOrDefault(c =>
                c.Key.Equals(aspectKey, StringComparison.OrdinalIgnoreCase));

            if (byKey != null)
            {
                return (byKey.DepartmentId, byKey);
            }
        }

        // 2) Aspect anahtarı tutmazsa clause içinde anahtar kelime ara (yedek yol).
        foreach (var cat in availableCategories)
        {
            foreach (var kw in cat.Keywords)
            {
                var lowerKw = kw.ToLowerInvariant();
                if (lowerClause.Contains(lowerKw) && lowerKw.Length > maxLen)
                {
                    maxLen = lowerKw.Length;
                    matchedCategory = cat;
                }
            }
        }

        if (matchedCategory != null)
        {
            return (matchedCategory.DepartmentId, matchedCategory);
        }

        // Kategori de eşleşmezse BOŞ bırakılır. Önceden "listenin ilk kategorisi"
        // atanıyordu; bu, panelde ve dashboard grafiklerinde tamamen yanlış kategori
        // dağılımı üretiyordu.
        _logger.LogWarning(
            "Aspect için kategori eşleştirilemedi (aspect: '{AspectKey}', departman: '{DepartmentKey}'). " +
            "Analiz kategorisiz kaydedilecek.",
            aspectKey, departmentKey);

        return (department?.Id, null);
    }

    private async Task<HotelReviewAI.Application.DTOs.AiAnalysisResult> SimulateAnalysisAsync(Review review)
    {
        var sentiment = review.Rating switch
        {
            <= 2 => "Negative",
            3 => "Neutral",
            _ => "Positive"
        };
        var score = review.Rating switch
        {
            1 => -0.9, 2 => -0.6, 3 => 0.0, 4 => 0.6, 5 => 0.9, _ => 0.0
        };

        var lowerComment = review.Comment.ToLowerInvariant();
        var allCategories = await _categoryRepository.GetAllAsync();
        var departments = await _departmentRepository.GetAllAsync();
        var hotelDepartmentIds = departments.Where(d => d.HotelId == review.HotelId).Select(d => d.Id).ToList();
        var hotelCategories = allCategories.Where(c => hotelDepartmentIds.Contains(c.DepartmentId)).ToList();
        if (hotelCategories.Count == 0)
            hotelCategories = allCategories.ToList();

        ReviewCategory? bestCategory = null;
        int maxKeywordLength = 0;

        foreach (var category in hotelCategories)
        {
            foreach (var kw in category.Keywords)
            {
                var lowerKw = kw.ToLowerInvariant();
                if (lowerComment.Contains(lowerKw) && lowerKw.Length > maxKeywordLength)
                {
                    maxKeywordLength = lowerKw.Length;
                    bestCategory = category;
                }
            }
        }

        return new HotelReviewAI.Application.DTOs.AiAnalysisResult
        {
            Sentiment = sentiment,
            SentimentScore = score,
            Category = bestCategory?.Name,
            Keywords = bestCategory?.Keywords ?? [],
            Summary = "Şikayet konusu analiz edildi ve ilgili birime aksiyon oluşturuldu.",
            Suggestion = "Misafir şikayeti doğrultusunda ilgili departman tarafından aksiyon alınmalıdır.",
            Confidence = 0.85
        };
    }
}
