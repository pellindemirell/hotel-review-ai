using HotelReviewAI.Application.DTOs;
using MediatR;

namespace HotelReviewAI.Application.Queries.Departments;

public record GetDepartmentsQuery(Guid? HotelId = null) : IRequest<List<DepartmentDto>>;
