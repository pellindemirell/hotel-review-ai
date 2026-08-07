using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Commands.Reviews;

public record CreateReviewCommand(
    string GuestName,
    string Comment,
    int Rating,
    string Language,
    ReviewSource Source,
    DateTime? ReviewDate,
    Guid? HotelId = null,
    /// <summary>Yüklenmiş görselin adresi; yoksa null. Ek kaydı bundan üretilir.</summary>
    string? PhotoUrl = null) : IRequest<Guid>;
