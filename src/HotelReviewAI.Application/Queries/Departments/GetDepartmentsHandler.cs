using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Queries.Departments;

public class GetDepartmentsHandler : IRequestHandler<GetDepartmentsQuery, List<DepartmentDto>>
{
    private readonly IDepartmentRepository _departmentRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetDepartmentsHandler(
        IDepartmentRepository departmentRepository,
        ICurrentUserService currentUserService)
    {
        _departmentRepository = departmentRepository;
        _currentUserService = currentUserService;
    }

    public async Task<List<DepartmentDto>> Handle(GetDepartmentsQuery request, CancellationToken cancellationToken)
    {
        // SuperAdmin dışındaki roller otel seçmediği için istemci X-Hotel-Id göndermiyor
        // (shell.ts, HotelAdmin/DepartmentManager için seçimi temizliyor). Otel kısıtı
        // burada JWT'deki hotelId claim'inden zorunlu kılınmazsa 5 otelin TÜM departmanları
        // dönüyor ve yan menüde her departman birden çok kez görünüyordu.
        var effectiveHotelId = _currentUserService.Role is UserRole.HotelAdmin or UserRole.DepartmentManager
            ? _currentUserService.HotelId
            : request.HotelId;

        var departments = await _departmentRepository.GetDepartmentsAsync(effectiveHotelId);
        return departments.Select(d => new DepartmentDto
        {
            Id = d.Id,
            Key = d.Key,
            Name = d.Name,
            Description = d.Description
        }).ToList();
    }
}
