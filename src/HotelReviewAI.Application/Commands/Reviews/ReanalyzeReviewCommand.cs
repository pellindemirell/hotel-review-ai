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

        var existingAnalyses = await _reviewAnalysisRepository.GetByReviewIdAsync(request.ReviewId);
        if (existingAnalyses.Any())
        {
            await _reviewAnalysisRepository.SoftDeleteRangeAsync(existingAnalyses);
            await _reviewAnalysisRepository.SaveChangesAsync();
        }

        // 2. AI analizi ve otomatik aksiyon işlemlerini ortak servise devret (isReanalysis: true)
        await _analysisProcessingService.ProcessAnalysisAsync(review, isReanalysis: true, cancellationToken);

        return true;
    }
}
