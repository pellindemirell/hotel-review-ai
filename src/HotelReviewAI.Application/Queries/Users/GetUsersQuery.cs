using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Users;

// AllHotels yalnızca SuperAdmin için geçerlidir ve Personel Yönetimi ekranında kullanılır;
// diğer ekranlar (ör. görev atama) seçili otelle sınırlı liste alır.
public record GetUsersQuery(Guid? HotelId = null, Guid? DepartmentId = null, bool AllHotels = false)
    : IRequest<List<UserDto>>;
