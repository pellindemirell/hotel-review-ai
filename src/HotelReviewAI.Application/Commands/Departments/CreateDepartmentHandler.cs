using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using MediatR;

namespace HotelReviewAI.Application.Commands.Departments;

public class CreateDepartmentHandler : IRequestHandler<CreateDepartmentCommand, Guid>
{
    private readonly IDepartmentRepository _departmentRepository;

    public CreateDepartmentHandler(IDepartmentRepository departmentRepository)
    {
        _departmentRepository = departmentRepository;
    }

    public async Task<Guid> Handle(CreateDepartmentCommand request, CancellationToken cancellationToken)
    {
        var department = new Department
        {
            Key = request.Key,
            Name = request.Name,
            Description = request.Description
        };

        await _departmentRepository.AddAsync(department);
        return department.Id;
    }
}
