using MediatR;

namespace HotelReviewAI.Application.Commands.Departments;

// HotelId body'de gönderilmez; controller X-Hotel-Id header'ından doldurur (SuperAdmin otel seçer),
// boş kalırsa handler giriş yapan kullanıcının otelini kullanır.
public record CreateDepartmentCommand(string Key, string Name, string? Description, Guid? HotelId = null) : IRequest<Guid>;
