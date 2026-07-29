using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using Mapster;
using MediatR;

namespace HotelReviewAI.Application.Queries.Users;

public class GetUsersHandler : IRequestHandler<GetUsersQuery, List<UserDto>>
{
    private readonly IUserRepository _userRepository;
    private readonly IDepartmentRepository _departmentRepository;

    public GetUsersHandler(IUserRepository userRepository, IDepartmentRepository departmentRepository)
    {
        _userRepository = userRepository;
        _departmentRepository = departmentRepository;
    }

    public async Task<List<UserDto>> Handle(GetUsersQuery request, CancellationToken cancellationToken)
    {
        var users = await _userRepository.GetUsersAsync(request.HotelId);
        var departments = (await _departmentRepository.GetAllAsync()).ToDictionary(d => d.Id);

        // Mapster ile map et, sonra DepartmentName'i departman sözlüğünden doldur
        return users.Select(u =>
        {
            var dto = u.Adapt<UserDto>();
            dto.DepartmentName = u.DepartmentId is not null && departments.TryGetValue(u.DepartmentId.Value, out var dept)
                ? dept.Name
                : null;
            return dto;
        }).ToList();
    }
}
