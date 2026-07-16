using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Reviews;

public class GetReviewByIdHandler : IRequestHandler<GetReviewByIdQuery, ReviewDetailDto?>
{
    private readonly IReviewRepository _reviewRepository;

    public GetReviewByIdHandler(IReviewRepository reviewRepository)
    {
        _reviewRepository = reviewRepository;
    }

    public async Task<ReviewDetailDto?> Handle(GetReviewByIdQuery request, CancellationToken cancellationToken)
    {
        var review = await _reviewRepository.GetByIdWithDetailsAsync(request.Id);
        if (review is null)
        {
            return null;
        }

        return new ReviewDetailDto
        {
            Id = review.Id,
            GuestName = review.GuestName,
            Comment = review.Comment,
            Rating = review.Rating,
            ReviewDate = review.ReviewDate,
            Source = review.Source.ToString(),
            Language = review.Language,
            Analyses = review.Analyses.Select(a => new ReviewAnalysisDto
            {
                Id = a.Id,
                ClauseIndex = a.ClauseIndex,
                ClauseText = a.ClauseText,
                Sentiment = a.Sentiment.ToString(),
                SentimentScore = a.SentimentScore,
                Priority = a.Priority.ToString(),
                CategoryId = a.CategoryId,
                CategoryName = a.Category?.Name,
                Suggestion = a.Suggestion,
                Confidence = a.Confidence
            }).ToList(),
            Attachments = review.Attachments.Select(x => new ReviewAttachmentDto
            {
                Id = x.Id,
                FileUrl = x.FileUrl,
                FileType = x.FileType,
                OcrText = x.OcrText
            }).ToList(),
            ActionItems = review.ActionItems.Select(x => new ActionItemDto
            {
                Id = x.Id,
                Title = x.Title,
                Status = x.Status.ToString(),
                DueDate = x.DueDate,
                AssignedTo = x.AssignedTo
            }).ToList()
        };
    }
}
