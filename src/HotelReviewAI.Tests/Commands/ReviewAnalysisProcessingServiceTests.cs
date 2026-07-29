using FluentAssertions;
using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Application.Services;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using Microsoft.Extensions.Logging;
using NSubstitute;
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace HotelReviewAI.Tests.Commands;

public class ReviewAnalysisProcessingServiceTests
{
    private readonly IReviewAnalysisRepository _reviewAnalysisRepository;
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IReviewCategoryRepository _categoryRepository;
    private readonly IAiAnalysisService _aiAnalysisService;
    private readonly IDepartmentRepository _departmentRepository;
    private readonly ILogger<ReviewAnalysisProcessingService> _logger;
    private readonly ReviewAnalysisProcessingService _service;

    public ReviewAnalysisProcessingServiceTests()
    {
        _reviewAnalysisRepository = Substitute.For<IReviewAnalysisRepository>();
        _actionItemRepository = Substitute.For<IActionItemRepository>();
        _categoryRepository = Substitute.For<IReviewCategoryRepository>();
        _aiAnalysisService = Substitute.For<IAiAnalysisService>();
        _departmentRepository = Substitute.For<IDepartmentRepository>();
        _logger = Substitute.For<ILogger<ReviewAnalysisProcessingService>>();

        _service = new ReviewAnalysisProcessingService(
            _reviewAnalysisRepository,
            _actionItemRepository,
            _categoryRepository,
            _aiAnalysisService,
            _departmentRepository,
            _logger
        );
    }

    [Fact]
    public async Task ProcessAnalysisAsync_WithAbsaAspects_ShouldSaveEachAspectAndCreateActionItems()
    {
        // Arrange
        var review = Review.Create(
            "Ahmet Yılmaz",
            "Odada sıcak su akmıyordu, temizlik çok kötüydü.",
            1,
            "tr",
            ReviewSource.Manual,
            DateTime.UtcNow,
            null
        );

        var mockDept = new Department { Key = "housekeeping", Name = "Oda Hizmetleri" };
        var deptId = mockDept.Id;
        var mockDepts = new List<Department> { mockDept };

        var mockCategories = new List<ReviewCategory>
        {
            new ReviewCategory { Key = "room_cleanliness", Name = "Oda Temizliği", Keywords = new List<string>{"temizlik", "su"}, DepartmentId = deptId }
        };

        _departmentRepository.GetAllAsync().Returns(mockDepts);
        _categoryRepository.GetAllAsync().Returns(mockCategories);

        var aiResult = new AiAnalysisResult
        {
            Sentiment = "Negative",
            SentimentScore = -0.95,
            Category = "Temizlik",
            Keywords = new List<string> { "su", "temizlik" },
            Summary = "Sıcak su ve temizlik şikayeti",
            Suggestion = "Temizlik kontrol listeleri güncellenmelidir.",
            Confidence = 0.98,
            AbsaAspects = new List<AiAbsaAspect>
            {
                new AiAbsaAspect
                {
                    Clause = "temizlik çok kötüydü",
                    Department = "housekeeping",
                    Sentiment = "Negative",
                    SentimentScore = -0.9,
                    Priority = "Yuksek",
                    Suggestion = "Kontrol listelerini güncelleyin"
                }
            }
        };

        _aiAnalysisService.AnalyzeReviewAsync(
            Arg.Any<string>(), Arg.Any<int>(), Arg.Any<string>(), Arg.Any<CancellationToken>()
        ).Returns(aiResult);

        // Act
        await _service.ProcessAnalysisAsync(review, isReanalysis: false, CancellationToken.None);

        // Assert
        // AI analiz sonucunun veritabanına kaydedildiğini doğrula
        await _reviewAnalysisRepository.Received(1).AddAsync(Arg.Any<ReviewAnalysis>());

        // Negatif yorum olduğu için otomatik ActionItem oluşturulduğunu doğrula
        await _actionItemRepository.Received(1).AddAsync(Arg.Any<ActionItem>());
    }

    [Fact]
    public async Task ProcessAnalysisAsync_WithAiServiceOffline_ShouldLogWarningAndUseFallback()
    {
        // Arrange
        var review = Review.Create(
            "Ahmet Yılmaz",
            "Odada sıcak su akmıyordu, temizlik çok kötüydü.",
            1,
            "tr",
            ReviewSource.Manual,
            DateTime.UtcNow,
            null
        );

        _aiAnalysisService.AnalyzeReviewAsync(
            Arg.Any<string>(), Arg.Any<int>(), Arg.Any<string>(), Arg.Any<CancellationToken>()
        ).Returns((AiAnalysisResult?)null);

        _departmentRepository.GetAllAsync().Returns(new List<Department>());
        _categoryRepository.GetAllAsync().Returns(new List<ReviewCategory>());

        // Act
        await _service.ProcessAnalysisAsync(review, isReanalysis: false, CancellationToken.None);

        // Assert
        // Yerel simülasyon (fallback) çalışmalı ve analiz kaydedilmeli
        await _reviewAnalysisRepository.Received(1).AddAsync(Arg.Any<ReviewAnalysis>());
    }
}

