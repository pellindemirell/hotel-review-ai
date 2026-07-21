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
        // AI servisine analiz isteği gönder (graceful degradation: null dönerse atla)
        var aiResult = await _aiAnalysisService.AnalyzeReviewAsync(
            review.Comment, review.Rating, review.Language, cancellationToken);

        if (aiResult is null)
        {
            _logger.LogWarning("AI analizi alınamadı, yorum ID: {ReviewId}. Analiz atlanıyor.", review.Id);
            return;
        }

        var prefix = isReanalysis ? "[Yeniden Analiz]" : "[Otomatik]";
        var absaPrefix = isReanalysis ? "[ABSA Yeniden Analiz]" : "[ABSA Otomatik]";

        // Eşleşen ABSA aspect'leri varsa her biri için ayrı analiz ve aksiyon kaydı oluştur
        if (aiResult.AbsaAspects != null && aiResult.AbsaAspects.Any())
        {
            int idx = 0;
            foreach (var aspect in aiResult.AbsaAspects)
            {
                var (deptId, catId) = await ResolveDepartmentAndCategoryAsync(aspect.Department, aspect.Clause);

                var aspectSentiment = aspect.Sentiment switch
                {
                    "Positive" => Sentiment.Positive,
                    "Negative" => Sentiment.Negative,
                    _ => Sentiment.Neutral
                };

                var aspectPriority = aspect.Priority switch
                {
                    "Kritik" => Priority.Kritik,
                    "Yuksek" => Priority.Yuksek,
                    "Orta" => Priority.Orta,
                    _ => Priority.Bilgi
                };

                var analysis = new ReviewAnalysis
                {
                    ReviewId = review.Id,
                    ClauseIndex = idx++,
                    ClauseText = aspect.Clause,
                    Sentiment = aspectSentiment,
                    SentimentScore = aspect.SentimentScore,
                    Priority = aspectPriority,
                    CategoryId = catId,
                    Suggestion = aspect.Suggestion,
                    Confidence = aiResult.Confidence,
                    Keywords = aiResult.Keywords,
                    Summary = aiResult.Summary
                };

                await _reviewAnalysisRepository.AddAsync(analysis);

                // Negatif aspect'ler için ilgili departmana otomatik ActionItem oluştur
                if (aspectSentiment == Sentiment.Negative && deptId.HasValue)
                {
                    var actionItem = new ActionItem
                    {
                        ReviewId = review.Id,
                        DepartmentId = deptId.Value,
                        Title = $"{absaPrefix} {aspect.Clause}",
                        Status = ActionItemStatus.Open,
                        DueDate = DateTime.UtcNow.AddDays(3)
                    };

                    await _actionItemRepository.AddAsync(actionItem);

                    _logger.LogInformation(
                        "Negatif aspect için otomatik aksiyon oluşturuldu. ReviewId: {ReviewId}, Dept: {DeptKey}",
                        review.Id, aspect.Department);
                }
            }
        }
        else
        {
            // Düz analiz yapısı (Legacy fallback)
            ReviewCategory? category = null;
            if (!string.IsNullOrEmpty(aiResult.Category))
            {
                category = await _categoryRepository.GetByNameAsync(aiResult.Category);
            }

            var sentimentEnum = aiResult.Sentiment switch
            {
                "Positive" => Sentiment.Positive,
                "Negative" => Sentiment.Negative,
                _ => Sentiment.Neutral
            };

            var priorityEnum = sentimentEnum == Sentiment.Negative ? Priority.Yuksek : Priority.Bilgi;

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

            if (sentimentEnum == Sentiment.Negative && category is not null)
            {
                var actionItem = new ActionItem
                {
                    ReviewId = review.Id,
                    DepartmentId = category.DepartmentId,
                    Title = $"{prefix} {category.Name}: {(review.Comment.Length > 80 ? review.Comment[..80] + "..." : review.Comment)}",
                    Status = ActionItemStatus.Open,
                    DueDate = DateTime.UtcNow.AddDays(3)
                };

                await _actionItemRepository.AddAsync(actionItem);
            }
        }
    }

    private async Task<(Guid? DepartmentId, Guid? CategoryId)> ResolveDepartmentAndCategoryAsync(
        string departmentKey, string clause)
    {
        var departments = await _departmentRepository.GetAllAsync();
        var department = departments.FirstOrDefault(d => d.Key.Equals(departmentKey, StringComparison.OrdinalIgnoreCase));
        if (department is null)
            return (null, null);

        var categories = await _categoryRepository.GetAllAsync();
        var deptCategories = categories.Where(c => c.DepartmentId == department.Id).ToList();

        var lowerClause = clause.ToLowerInvariant();
        var matchedCategory = deptCategories.FirstOrDefault(c => 
            c.Keywords.Any(k => lowerClause.Contains(k.ToLowerInvariant())));

        var categoryId = matchedCategory?.Id ?? deptCategories.FirstOrDefault()?.Id;

        return (department.Id, categoryId);
    }
}
