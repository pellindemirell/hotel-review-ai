using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Commands.Departments;

public class UpdateDepartmentHandler : IRequestHandler<UpdateDepartmentCommand, bool>
{
    private readonly IDepartmentRepository _departmentRepository;

    public UpdateDepartmentHandler(IDepartmentRepository departmentRepository)
    {
        _departmentRepository = departmentRepository;
    }

    public async Task<bool> Handle(UpdateDepartmentCommand request, CancellationToken cancellationToken)
    {
        var department = await _departmentRepository.GetByIdAsync(request.Id);
        if (department is null)
        {
            return false;
        }

        department.Name = request.Name;
        department.Description = request.Description;

        await _departmentRepository.UpdateAsync(department);
        await _departmentRepository.SaveChangesAsync();
        return true;
    }
}
