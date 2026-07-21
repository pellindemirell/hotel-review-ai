using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using MediatR;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Application.Commands.Reviews;

public record ReanalyzeReviewCommand(Guid ReviewId) : IRequest<bool>;

public class ReanalyzeReviewHandler : IRequestHandler<ReanalyzeReviewCommand, bool>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IReviewAnalysisRepository _reviewAnalysisRepository;
    private readonly IReviewAnalysisProcessingService _analysisProcessingService;

    public ReanalyzeReviewHandler(
        IReviewRepository reviewRepository,
        IReviewAnalysisRepository reviewAnalysisRepository,
        IReviewAnalysisProcessingService analysisProcessingService)
    {
        _reviewRepository = reviewRepository;
        _reviewAnalysisRepository = reviewAnalysisRepository;
        _analysisProcessingService = analysisProcessingService;
    }

    public async Task<bool> Handle(ReanalyzeReviewCommand request, CancellationToken cancellationToken)
    {
        var review = await _reviewRepository.GetByIdAsync(request.ReviewId);
        if (review == null)
        {
            throw new DomainException("Yorum bulunamadı.");
        }

        // 1. Eski analizleri temizle
        var existingAnalyses = await _reviewAnalysisRepository.GetByReviewIdAsync(request.ReviewId);
        foreach (var oldAnalysis in existingAnalyses)
        {
            await _reviewAnalysisRepository.DeleteAsync(oldAnalysis);
        }

        // 2. AI analizi ve otomatik aksiyon işlemlerini ortak servise devret (isReanalysis: true)
        await _analysisProcessingService.ProcessAnalysisAsync(review, isReanalysis: true, cancellationToken);

        return true;
    }
}
