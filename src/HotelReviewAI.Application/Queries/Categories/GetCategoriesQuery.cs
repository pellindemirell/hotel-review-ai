using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Categories;

// Kategoriler departman üzerinden otele bağlıdır; HotelId verilmezse tüm otellerin
// kategorileri dönerdi (aynı isimler tekrar tekrar listeleniyordu).
public record GetCategoriesQuery(Guid? HotelId = null) : IRequest<List<CategoryDto>>;
