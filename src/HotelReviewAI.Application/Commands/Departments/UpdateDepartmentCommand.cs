using MediatR;

namespace HotelReviewAI.Application.Commands.Departments;

public record UpdateDepartmentCommand(Guid Id, string Name, string? Description) : IRequest<bool>;
