using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using MediatR;
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Commands.Reviews;

public record ImportReviewsCommand(List<ImportReviewItemDto> Reviews) : IRequest<bool>;

public record ImportReviewItemDto(
    string GuestName,
    string Comment,
    int Rating,
    string Language,
    ReviewSource Source,
    DateTime? ReviewDate
);

public class ImportReviewsHandler : IRequestHandler<ImportReviewsCommand, bool>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IAnalysisJobRepository _analysisJobRepository;

    public ImportReviewsHandler(
        IReviewRepository reviewRepository,
        IAnalysisJobRepository analysisJobRepository)
    {
        _reviewRepository = reviewRepository;
        _analysisJobRepository = analysisJobRepository;
    }

    public async Task<bool> Handle(ImportReviewsCommand request, CancellationToken cancellationToken)
    {
        if (request.Reviews == null || request.Reviews.Count == 0)
        {
            return false;
        }

        foreach (var dto in request.Reviews)
        {
            var review = Review.Create(
                guestName: dto.GuestName,
                comment: dto.Comment,
                rating: dto.Rating,
                language: dto.Language,
                source: dto.Source,
                reviewDate: dto.ReviewDate ?? DateTime.UtcNow,
                createdBy: null
            );

            await _reviewRepository.AddAsync(review);
            
            var job = new AnalysisJob { ReviewId = review.Id };
            await _analysisJobRepository.AddAsync(job);
            
            await _reviewRepository.SaveChangesAsync();
        }

        return true;
    }
}
