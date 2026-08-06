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

    private readonly ICurrentUserService _currentUserService;

    public ReanalyzeReviewHandler(
        IReviewRepository reviewRepository,
        IReviewAnalysisRepository reviewAnalysisRepository,
        IReviewAnalysisProcessingService analysisProcessingService,
        ICurrentUserService currentUserService)
    {
        _reviewRepository = reviewRepository;
        _reviewAnalysisRepository = reviewAnalysisRepository;
        _analysisProcessingService = analysisProcessingService;
        _currentUserService = currentUserService;
    }

    public async Task<bool> Handle(ReanalyzeReviewCommand request, CancellationToken cancellationToken)
    {
        var review = await _reviewRepository.GetByIdAsync(request.ReviewId);
        if (review == null)
        {
            throw new DomainException("Yorum bulunamadı.");
        }

        if (_currentUserService.Role == UserRole.DepartmentManager || _currentUserService.Role == UserRole.HotelAdmin)
        {
            if (review.HotelId != _currentUserService.HotelId)
            {
                throw new UnauthorizedAccessException("Bu otelin yorumlarını yeniden analiz etme yetkiniz yok.");
            }
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
