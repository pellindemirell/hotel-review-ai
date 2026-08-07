using HotelReviewAI.Application.Commands.Staff;
using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using MediatR;

namespace HotelReviewAI.Application.Queries.Staff;

/// <summary>Oturumdaki departman yöneticisinin kendi ekibi.</summary>
public record GetMyStaffQuery : IRequest<List<StaffMemberDto>>;

public class GetMyStaffHandler : IRequestHandler<GetMyStaffQuery, List<StaffMemberDto>>
{
    private readonly IStaffMemberRepository _repository;
    private readonly ICurrentUserService _currentUser;

    public GetMyStaffHandler(IStaffMemberRepository repository, ICurrentUserService currentUser)
    {
        _repository = repository;
        _currentUser = currentUser;
    }

    public async Task<List<StaffMemberDto>> Handle(GetMyStaffQuery request, CancellationToken cancellationToken)
    {
        var departmentId = StaffScope.RequireDepartment(_currentUser);
        var staff = await _repository.GetByDepartmentIdAsync(departmentId);

        return staff.Select(ToDto).ToList();
    }

    internal static StaffMemberDto ToDto(StaffMember s) => new()
    {
        Id = s.Id,
        FirstName = s.FirstName,
        LastName = s.LastName,
        FullName = s.FullName,
        Title = s.Title,
        HireDate = s.HireDate,
        BirthDate = s.BirthDate,
        Age = CalculateAge(s.BirthDate),
    };

    /// <summary>
    /// Yaş doğum tarihinden hesaplanır. Doğum günü henüz gelmediyse bir
    /// eksiltilir; aksi hâlde yıl farkı yaşı bir fazla gösterirdi.
    /// </summary>
    private static int? CalculateAge(DateTime? birthDate)
    {
        if (birthDate is null)
        {
            return null;
        }

        var today = DateTime.UtcNow.Date;
        var age = today.Year - birthDate.Value.Year;
        if (birthDate.Value.Date > today.AddYears(-age))
        {
            age--;
        }

        return age < 0 ? null : age;
    }
}
