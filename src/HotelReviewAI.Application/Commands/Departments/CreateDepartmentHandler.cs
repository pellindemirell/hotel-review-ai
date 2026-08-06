using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using MediatR;

namespace HotelReviewAI.Application.Commands.Departments;

public class CreateDepartmentHandler : IRequestHandler<CreateDepartmentCommand, Guid>
{
    private readonly IDepartmentRepository _departmentRepository;
    private readonly ICurrentUserService _currentUserService;

    public CreateDepartmentHandler(
        IDepartmentRepository departmentRepository,
        ICurrentUserService currentUserService)
    {
        _departmentRepository = departmentRepository;
        _currentUserService = currentUserService;
    }

    public async Task<Guid> Handle(CreateDepartmentCommand request, CancellationToken cancellationToken)
    {
        // HotelId atanmazsa departman hiçbir otelin listesinde görünmez.
        // HotelAdmin başka bir otele departman ekleyemez; kendi oteline sabitlenir.
        var hotelId = _currentUserService.Role == UserRole.HotelAdmin
            ? _currentUserService.HotelId
            : request.HotelId ?? _currentUserService.HotelId;
        if (hotelId is null)
        {
            throw new DomainException("Departman oluşturmak için bir otel seçilmelidir.");
        }

        var department = new Department
        {
            Key = request.Key,
            Name = request.Name,
            Description = request.Description,
            HotelId = hotelId
        };

        await _departmentRepository.AddAsync(department);
        await _departmentRepository.SaveChangesAsync();
        return department.Id;
    }
}
