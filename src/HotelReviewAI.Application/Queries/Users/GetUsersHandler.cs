using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
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
        var users = await _userRepository.GetAllAsync();
        var departments = (await _departmentRepository.GetAllAsync()).ToDictionary(d => d.Id);

        return users.Select(u => new UserDto
        {
            Id = u.Id,
            FullName = u.FullName,
            Email = u.Email,
            Role = u.Role,
            DepartmentId = u.DepartmentId,
            DepartmentName = u.DepartmentId is not null && departments.TryGetValue(u.DepartmentId.Value, out var dept)
                ? dept.Name
                : null
        }).ToList();
    }
}
