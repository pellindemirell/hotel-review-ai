using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using Mapster;
using MediatR;
using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Application.Queries.Users;

public class GetUsersHandler : IRequestHandler<GetUsersQuery, List<UserDto>>
{
    private readonly IUserRepository _userRepository;
    private readonly IDepartmentRepository _departmentRepository;
    private readonly IHotelRepository _hotelRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetUsersHandler(
        IUserRepository userRepository,
        IDepartmentRepository departmentRepository,
        IHotelRepository hotelRepository,
        ICurrentUserService currentUserService)
    {
        _userRepository = userRepository;
        _departmentRepository = departmentRepository;
        _hotelRepository = hotelRepository;
        _currentUserService = currentUserService;
    }

    // Listede önce yönetici hesapları, sonra departman yöneticileri gelsin diye rol sırası.
    private static int RoleRank(UserRole role) => role switch
    {
        UserRole.SuperAdmin => 0,
        UserRole.HotelAdmin => 1,
        _ => 2
    };

    public async Task<List<UserDto>> Handle(GetUsersQuery request, CancellationToken cancellationToken)
    {
        // SuperAdmin yalnızca AllHotels istendiğinde (Personel Yönetimi) tüm otelleri görür;
        // aksi hâlde seçili otelle sınırlıdır. Görev atama ekranı bu sayede başka otelin
        // personelini listelemiyor.
        Guid? finalHotelId = _currentUserService.Role switch
        {
            UserRole.SuperAdmin => request.AllHotels ? null : request.HotelId,
            UserRole.HotelAdmin => _currentUserService.HotelId,
            UserRole.DepartmentManager => _currentUserService.HotelId,
            _ => null
        };

        Guid? finalDeptId = _currentUserService.Role switch
        {
            UserRole.SuperAdmin => request.DepartmentId,
            UserRole.HotelAdmin => request.DepartmentId,
            UserRole.DepartmentManager => _currentUserService.DepartmentId,
            _ => null
        };

        // Departman yöneticisi yetkisiz gelirse veya HotelAdmin'in oteli yoksa boş dönsün.
        if (_currentUserService.Role is UserRole.HotelAdmin or UserRole.DepartmentManager && finalHotelId == null)
            return new List<UserDto>();

        var users = await _userRepository.GetUsersAsync(finalHotelId, finalDeptId);
        var departments = (await _departmentRepository.GetAllAsync()).ToDictionary(d => d.Id);
        var hotels = (await _hotelRepository.GetAllAsync()).ToDictionary(h => h.Id);

        var dtos = users.Select(u =>
        {
            var dto = u.Adapt<UserDto>();
            dto.DepartmentName = u.DepartmentId is not null && departments.TryGetValue(u.DepartmentId.Value, out var dept)
                ? dept.Name
                : null;
            dto.HotelName = u.HotelId is not null && hotels.TryGetValue(u.HotelId.Value, out var hotel)
                ? hotel.Name
                : u.HotelName;
            return dto;
        });

        // Sıralama: önce yönetici hesapları, sonra otel adı, departman ve ad.
        // Sorguda ORDER BY olmadığı için liste her istekte farklı sırada geliyordu.
        return dtos
            .OrderBy(d => RoleRank(Enum.TryParse<UserRole>(d.Role, out var role) ? role : UserRole.DepartmentManager))
            .ThenBy(d => d.HotelName ?? string.Empty, StringComparer.CurrentCulture)
            .ThenBy(d => d.DepartmentName ?? string.Empty, StringComparer.CurrentCulture)
            .ThenBy(d => d.FullName, StringComparer.CurrentCulture)
            .ToList();
    }
}
