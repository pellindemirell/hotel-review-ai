using MediatR;

namespace HotelReviewAI.Application.Commands.Departments;

public record CreateDepartmentCommand(string Key, string Name, string? Description) : IRequest<Guid>;
