using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using MediatR;

namespace HotelReviewAI.Application.Commands.Users;

public class CreateUserHandler : IRequestHandler<CreateUserCommand, Guid>
{
    private readonly IUserRepository _userRepository;
    private readonly IPasswordHasher _passwordHasher;
    private readonly ICurrentUserService _currentUserService;

    public CreateUserHandler(
        IUserRepository userRepository,
        IPasswordHasher passwordHasher,
        ICurrentUserService currentUserService)
    {
        _userRepository = userRepository;
        _passwordHasher = passwordHasher;
        _currentUserService = currentUserService;
    }

    public async Task<Guid> Handle(CreateUserCommand request, CancellationToken cancellationToken)
    {
        // E-posta normalize edilerek saklanır; aksi hâlde "A@x.com" ve "a@x.com" iki ayrı
        // hesap olarak oluşturulabiliyordu (benzersizlik indeksi harfe duyarlı).
        var email = request.Email.Trim().ToLowerInvariant();

        var existing = await _userRepository.GetByEmailAsync(email);
        if (existing is not null)
        {
            throw new DomainException("Bu e-posta adresiyle zaten bir kullanıcı var.");
        }

        // HotelId atanmazsa kullanıcı hiçbir otelin personel listesinde görünmez ve
        // token'ında hotelId claim'i olmadığı için otel bazlı filtreler devre dışı kalır.
        var hotelId = request.HotelId ?? _currentUserService.HotelId;
        if (hotelId is null && request.Role != UserRole.SuperAdmin)
        {
            throw new DomainException("Kullanıcı oluşturmak için bir otel seçilmelidir.");
        }

        var user = new User
        {
            FullName = request.FullName.Trim(),
            Email = email,
            Role = request.Role,
            DepartmentId = request.DepartmentId,
            HotelId = hotelId
        };
        user.SetPasswordHash(_passwordHasher.HashPassword(request.Password));

        await _userRepository.AddAsync(user);
        await _userRepository.SaveChangesAsync();
        return user.Id;
    }
}
