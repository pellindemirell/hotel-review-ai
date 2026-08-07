using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using MediatR;

namespace HotelReviewAI.Application.Commands.Staff;

// Ekip üyesi kayıtları hesapsızdır: giriş yapmazlar, rolleri/yetkileri yoktur.
// Bu yüzden User akışlarından tamamen ayrı tutuluyorlar.

public record CreateStaffMemberCommand(
    string FirstName,
    string LastName,
    string? Title,
    DateTime? HireDate,
    DateTime? BirthDate) : IRequest<Guid>;

public record UpdateStaffMemberCommand(
    Guid Id,
    string FirstName,
    string LastName,
    string? Title,
    DateTime? HireDate,
    DateTime? BirthDate) : IRequest<bool>;

public record DeleteStaffMemberCommand(Guid Id) : IRequest<bool>;

/// <summary>
/// Departman yöneticisinin kendi departmanını doğrular ve döndürür.
/// Ekip kayıtları her zaman yöneticinin departmanına bağlıdır; başka
/// departmanın çalışanına dokunulamaz.
/// </summary>
internal static class StaffScope
{
    public static Guid RequireDepartment(ICurrentUserService currentUser)
    {
        if (currentUser.Role != UserRole.DepartmentManager)
        {
            throw new UnauthorizedAccessException("Bu işlem yalnızca departman yöneticileri içindir.");
        }

        return currentUser.DepartmentId
            ?? throw new DomainException("Hesabınız bir departmana bağlı değil.");
    }

    public static void EnsureOwned(StaffMember staff, Guid departmentId)
    {
        if (staff.DepartmentId != departmentId)
        {
            throw new UnauthorizedAccessException("Bu çalışan sizin departmanınıza ait değil.");
        }
    }

    /// <summary>
    /// Takvim tarihini UTC'ye sabitler.
    ///
    /// Tarayıcının &lt;input type="date"&gt; alanı saat dilimi olmadan "2026-08-06"
    /// gönderiyor; .NET bunu Kind=Unspecified olarak ayrıştırıyor ve Npgsql
    /// "timestamp with time zone" kolonuna yazmayı reddediyordu. Bunlar an
    /// değil takvim tarihi olduğu için gün kaydırmadan UTC olarak işaretlemek
    /// doğru davranış; yerel saate çevirmek tarihi bir gün oynatabilirdi.
    /// </summary>
    public static DateTime? AsUtcDate(DateTime? value) => value is null
        ? null
        : DateTime.SpecifyKind(value.Value.Date, DateTimeKind.Utc);

    /// <summary>Gelecek tarihli doğum/işe giriş kaydı anlamsızdır.</summary>
    public static void EnsureDatesAreSane(DateTime? hireDate, DateTime? birthDate)
    {
        var today = DateTime.UtcNow.Date;

        if (birthDate is { } birth && birth.Date > today)
        {
            throw new DomainException("Doğum tarihi gelecekte olamaz.");
        }

        if (hireDate is { } hire && hire.Date > today)
        {
            throw new DomainException("İşe giriş tarihi gelecekte olamaz.");
        }

        if (birthDate is { } b && hireDate is { } h && h.Date < b.Date)
        {
            throw new DomainException("İşe giriş tarihi doğum tarihinden önce olamaz.");
        }
    }
}

public class CreateStaffMemberHandler : IRequestHandler<CreateStaffMemberCommand, Guid>
{
    private readonly IStaffMemberRepository _repository;
    private readonly ICurrentUserService _currentUser;

    public CreateStaffMemberHandler(IStaffMemberRepository repository, ICurrentUserService currentUser)
    {
        _repository = repository;
        _currentUser = currentUser;
    }

    public async Task<Guid> Handle(CreateStaffMemberCommand request, CancellationToken cancellationToken)
    {
        var departmentId = StaffScope.RequireDepartment(_currentUser);
        StaffScope.EnsureDatesAreSane(request.HireDate, request.BirthDate);

        var staff = new StaffMember
        {
            FirstName = request.FirstName.Trim(),
            LastName = request.LastName.Trim(),
            Title = string.IsNullOrWhiteSpace(request.Title) ? null : request.Title.Trim(),
            HireDate = StaffScope.AsUtcDate(request.HireDate),
            BirthDate = StaffScope.AsUtcDate(request.BirthDate),
            DepartmentId = departmentId,
            HotelId = _currentUser.HotelId,
        };

        await _repository.AddAsync(staff);
        await _repository.SaveChangesAsync();

        return staff.Id;
    }
}

public class UpdateStaffMemberHandler : IRequestHandler<UpdateStaffMemberCommand, bool>
{
    private readonly IStaffMemberRepository _repository;
    private readonly ICurrentUserService _currentUser;

    public UpdateStaffMemberHandler(IStaffMemberRepository repository, ICurrentUserService currentUser)
    {
        _repository = repository;
        _currentUser = currentUser;
    }

    public async Task<bool> Handle(UpdateStaffMemberCommand request, CancellationToken cancellationToken)
    {
        var departmentId = StaffScope.RequireDepartment(_currentUser);

        StaffScope.EnsureDatesAreSane(request.HireDate, request.BirthDate);

        var staff = await _repository.GetByIdAsync(request.Id)
            ?? throw new DomainException("Çalışan bulunamadı.");
        StaffScope.EnsureOwned(staff, departmentId);

        staff.FirstName = request.FirstName.Trim();
        staff.LastName = request.LastName.Trim();
        staff.Title = string.IsNullOrWhiteSpace(request.Title) ? null : request.Title.Trim();
        staff.HireDate = StaffScope.AsUtcDate(request.HireDate);
        staff.BirthDate = StaffScope.AsUtcDate(request.BirthDate);
        staff.MarkUpdated();

        await _repository.UpdateAsync(staff);
        await _repository.SaveChangesAsync();

        return true;
    }
}

public class DeleteStaffMemberHandler : IRequestHandler<DeleteStaffMemberCommand, bool>
{
    private readonly IStaffMemberRepository _repository;
    private readonly ICurrentUserService _currentUser;

    public DeleteStaffMemberHandler(IStaffMemberRepository repository, ICurrentUserService currentUser)
    {
        _repository = repository;
        _currentUser = currentUser;
    }

    public async Task<bool> Handle(DeleteStaffMemberCommand request, CancellationToken cancellationToken)
    {
        var departmentId = StaffScope.RequireDepartment(_currentUser);

        var staff = await _repository.GetByIdAsync(request.Id)
            ?? throw new DomainException("Çalışan bulunamadı.");
        StaffScope.EnsureOwned(staff, departmentId);

        // Soft delete: geçmiş görevlerdeki atama kaydı anlamını yitirmesin.
        await _repository.SoftDeleteAsync(staff);
        await _repository.SaveChangesAsync();

        return true;
    }
}
