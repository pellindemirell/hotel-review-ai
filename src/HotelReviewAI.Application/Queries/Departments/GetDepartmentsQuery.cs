using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Departments;

public record GetDepartmentsQuery : IRequest<List<DepartmentDto>>;
