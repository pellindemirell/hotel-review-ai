using FluentValidation;
using HotelReviewAI.Application.Commands.Reviews;

namespace HotelReviewAI.Application.Validators.Reviews;

public class CreateReviewValidator : AbstractValidator<CreateReviewCommand>
{
    public CreateReviewValidator()
    {
        RuleFor(x => x.GuestName).NotEmpty().MaximumLength(150);
        RuleFor(x => x.Comment).NotEmpty().MinimumLength(10);
        RuleFor(x => x.Rating).InclusiveBetween(1, 5);
        RuleFor(x => x.Language).NotEmpty().MaximumLength(10);
    }
}
