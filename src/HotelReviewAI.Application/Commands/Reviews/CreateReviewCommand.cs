using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Commands.Reviews;

public record CreateReviewCommand(
    string GuestName,
    string Comment,
    int Rating,
    string Language,
    ReviewSource Source,
    DateTime? ReviewDate) : IRequest<Guid>;
