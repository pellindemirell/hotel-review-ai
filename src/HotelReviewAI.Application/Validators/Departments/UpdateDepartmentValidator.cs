using FluentValidation;
using HotelReviewAI.Application.Commands.Departments;

namespace HotelReviewAI.Application.Validators.Departments;

public class UpdateDepartmentValidator : AbstractValidator<UpdateDepartmentCommand>
{
    public UpdateDepartmentValidator()
    {
        RuleFor(x => x.Id).NotEmpty();
        RuleFor(x => x.Name).NotEmpty().MaximumLength(100);
    }
}
