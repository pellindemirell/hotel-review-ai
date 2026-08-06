using MediatR;

namespace HotelReviewAI.Application.Commands.Categories;

public record UpdateCategoryCommand(
    Guid Id,
    string Name,
    List<string> Keywords,
    Guid DepartmentId) : IRequest<bool>;
