using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using MediatR;

namespace HotelReviewAI.Application.Commands.Categories;

public class CreateCategoryHandler : IRequestHandler<CreateCategoryCommand, Guid>
{
    private readonly IReviewCategoryRepository _categoryRepository;

    public CreateCategoryHandler(IReviewCategoryRepository categoryRepository)
    {
        _categoryRepository = categoryRepository;
    }

    public async Task<Guid> Handle(CreateCategoryCommand request, CancellationToken cancellationToken)
    {
        var category = new ReviewCategory
        {
            Key = request.Key,
            Name = request.Name,
            Keywords = request.Keywords,
            DepartmentId = request.DepartmentId
        };

        await _categoryRepository.AddAsync(category);
        return category.Id;
    }
}
