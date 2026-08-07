using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using MediatR;
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Commands.Reviews;

public record CreateMobileReviewCommand(
    string GuestName,
    string Comment,
    int Rating,
    string Language,
    string? PhotoUrl,
    string? OcrText,
    Guid? HotelId = null
) : IRequest<Guid>;

public class CreateMobileReviewHandler : IRequestHandler<CreateMobileReviewCommand, Guid>
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IReviewAttachmentRepository _reviewAttachmentRepository;
    private readonly ICurrentUserService _currentUserService;
    private readonly IMediator _mediator;

    public CreateMobileReviewHandler(
        IReviewRepository reviewRepository,
        IReviewAttachmentRepository reviewAttachmentRepository,
        ICurrentUserService currentUserService,
        IMediator mediator)
    {
        _reviewRepository = reviewRepository;
        _reviewAttachmentRepository = reviewAttachmentRepository;
        _currentUserService = currentUserService;
        _mediator = mediator;
    }

    public async Task<Guid> Handle(CreateMobileReviewCommand request, CancellationToken cancellationToken)
    {
        // HotelId hiç geçilmediği için mobil yorumlar NULL otelle kaydediliyordu.
        // GetReviewsHandler, HotelAdmin/DepartmentManager için filtreyi
        // HotelId = <kullanıcının oteli> olarak zorluyor; NULL hiçbir zaman
        // eşleşmediğinden bu yorumlar panelde hiç görünmüyordu.
        // Öncelik istekten gelen değerde (X-Hotel-Id header'ı), yoksa oturumdaki
        // kullanıcının oteli kullanılır.
        var effectiveHotelId = request.HotelId ?? _currentUserService.HotelId;

        var review = Review.Create(
            guestName: request.GuestName,
            comment: request.Comment,
            rating: request.Rating,
            language: request.Language,
            source: ReviewSource.Mobile,
            reviewDate: DateTime.UtcNow,
            createdBy: null,
            hotelId: effectiveHotelId
        );

        await _reviewRepository.AddAsync(review);

        if (!string.IsNullOrEmpty(request.PhotoUrl))
        {
            var attachment = new ReviewAttachment
            {
                ReviewId = review.Id,
                FileUrl = request.PhotoUrl,
                FileType = Path.GetExtension(request.PhotoUrl) ?? ".jpg",
                OcrText = request.OcrText
            };

            await _reviewAttachmentRepository.AddAsync(attachment);
        }

        // Veritabanı değişikliklerini kaydet (ReanalyzeReviewCommand veriyi veritabanından okuyabilsin)
        await _reviewRepository.SaveChangesAsync();

        // Mobil yorum kaydedildikten sonra AI analizi ve otomatik aksiyon sürecini tetikler.
        await _mediator.Send(new ReanalyzeReviewCommand(review.Id), cancellationToken);

        return review.Id;
    }
}
