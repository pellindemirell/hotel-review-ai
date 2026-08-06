using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Commands.Users;

// HotelId body'de gönderilmez; controller X-Hotel-Id header'ından doldurur (SuperAdmin otel seçer),
// boş kalırsa handler giriş yapan kullanıcının otelini kullanır.
public record CreateUserCommand(
    string FullName,
    string Email,
    string Password,
    UserRole Role,
    Guid? DepartmentId,
    Guid? HotelId = null) : IRequest<Guid>;
