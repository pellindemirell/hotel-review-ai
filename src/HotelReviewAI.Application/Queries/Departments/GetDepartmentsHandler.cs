using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using Mapster;
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
        var departments = await _departmentRepository.GetAllAsync();
        return departments.Adapt<List<DepartmentDto>>();
    }
}
