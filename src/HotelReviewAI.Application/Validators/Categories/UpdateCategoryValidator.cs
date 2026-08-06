using FluentValidation;
using HotelReviewAI.Application.Commands.Categories;

namespace HotelReviewAI.Application.Validators.Categories;

public class UpdateCategoryValidator : AbstractValidator<UpdateCategoryCommand>
{
    public UpdateCategoryValidator()
    {
        RuleFor(x => x.Id).NotEmpty();
        RuleFor(x => x.Name).NotEmpty().MaximumLength(100);
        RuleFor(x => x.DepartmentId).NotEmpty();
    }
}
