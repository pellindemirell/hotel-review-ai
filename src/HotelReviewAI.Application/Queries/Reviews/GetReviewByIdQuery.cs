using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Reviews;

public record GetReviewByIdQuery(Guid Id) : IRequest<ReviewDetailDto?>;
