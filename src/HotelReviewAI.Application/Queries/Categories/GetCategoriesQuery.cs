using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Categories;

public record GetCategoriesQuery : IRequest<List<CategoryDto>>;
