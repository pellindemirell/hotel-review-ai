using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Exceptions;
using MediatR;

namespace HotelReviewAI.Application.Commands.Users;

public class CreateUserHandler : IRequestHandler<CreateUserCommand, Guid>
{
    private readonly IUserRepository _userRepository;
    private readonly IPasswordHasher _passwordHasher;

    public CreateUserHandler(IUserRepository userRepository, IPasswordHasher passwordHasher)
    {
        _userRepository = userRepository;
        _passwordHasher = passwordHasher;
    }

    public async Task<Guid> Handle(CreateUserCommand request, CancellationToken cancellationToken)
    {
        var existing = await _userRepository.GetByEmailAsync(request.Email);
        if (existing is not null)
        {
            throw new DomainException("Bu e-posta adresiyle zaten bir kullanıcı var.");
        }

        var user = new User
        {
            FullName = request.FullName,
            Email = request.Email,
            Role = request.Role,
            DepartmentId = request.DepartmentId
        };
        user.SetPasswordHash(_passwordHasher.HashPassword(request.Password));

        await _userRepository.AddAsync(user);
        return user.Id;
    }
}
