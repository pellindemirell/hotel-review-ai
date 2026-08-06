using FluentValidation;
using HotelReviewAI.Application.Commands.Users;
using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Application.Validators.Users;

public class CreateUserValidator : AbstractValidator<CreateUserCommand>
{
    public CreateUserValidator()
    {
        RuleFor(x => x.FullName).NotEmpty().MaximumLength(150);
        RuleFor(x => x.Email).NotEmpty().EmailAddress();
        RuleFor(x => x.Password).NotEmpty().MinimumLength(6);
        RuleFor(x => x.Role).IsInEnum().WithMessage("Geçersiz rol belirtildi.");
    }
}
