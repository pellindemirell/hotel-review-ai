using MediatR;

namespace HotelReviewAI.Application.Commands.Categories;

public record CreateCategoryCommand(
    string Key,
    string Name,
    List<string> Keywords,
    Guid DepartmentId) : IRequest<Guid>;
