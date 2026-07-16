using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Commands.Categories;

public class UpdateCategoryHandler : IRequestHandler<UpdateCategoryCommand, bool>
{
    private readonly IReviewCategoryRepository _categoryRepository;

    public UpdateCategoryHandler(IReviewCategoryRepository categoryRepository)
    {
        _categoryRepository = categoryRepository;
    }

    public async Task<bool> Handle(UpdateCategoryCommand request, CancellationToken cancellationToken)
    {
        var category = await _categoryRepository.GetByIdAsync(request.Id);
        if (category is null)
        {
            return false;
        }

        category.Name = request.Name;
        category.Keywords = request.Keywords;
        category.DepartmentId = request.DepartmentId;

        await _categoryRepository.UpdateAsync(category);
        return true;
    }
}
