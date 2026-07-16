using MediatR;

namespace HotelReviewAI.Application.Commands.Users;

public record CreateUserCommand(
    string FullName,
    string Email,
    string Password,
    string Role,
    Guid? DepartmentId) : IRequest<Guid>;
