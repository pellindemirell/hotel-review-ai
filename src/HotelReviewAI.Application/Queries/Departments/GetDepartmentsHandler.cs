using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Departments;

public class GetDepartmentsHandler : IRequestHandler<GetDepartmentsQuery, List<DepartmentDto>>
{
    private readonly IDepartmentRepository _departmentRepository;

    public GetDepartmentsHandler(IDepartmentRepository departmentRepository)
    {
        _departmentRepository = departmentRepository;
    }

    public async Task<List<DepartmentDto>> Handle(GetDepartmentsQuery request, CancellationToken cancellationToken)
    {
        var departments = await _departmentRepository.GetDepartmentsAsync(request.HotelId);
        return departments.Select(d => new DepartmentDto
        {
            Id = d.Id,
            Key = d.Key,
            Name = d.Name,
            Description = d.Description
        }).ToList();
    }
}
