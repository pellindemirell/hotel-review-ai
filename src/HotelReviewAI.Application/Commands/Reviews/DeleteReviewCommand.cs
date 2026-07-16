using MediatR;

namespace HotelReviewAI.Application.Commands.Reviews;

public record DeleteReviewCommand(Guid Id) : IRequest<bool>;
