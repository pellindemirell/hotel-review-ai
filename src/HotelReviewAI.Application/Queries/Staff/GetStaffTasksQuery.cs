using HotelReviewAI.Application.Commands.Staff;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using MediatR;

namespace HotelReviewAI.Application.Queries.Staff;

public class StaffTaskDto
{
    public Guid Id { get; set; }
    public Guid ReviewId { get; set; }
    public string Title { get; set; } = string.Empty;
    public string Status { get; set; } = string.Empty;
    public DateTime? DueDate { get; set; }
    /// <summary>Görevin kaynağı olan yorum metni (kısaltılmış) — bağlam için.</summary>
    public string? ReviewComment { get; set; }
    public DateTime CreatedAt { get; set; }
}

public class StaffTasksDto
{
    public Guid StaffId { get; set; }
    public string StaffName { get; set; } = string.Empty;

    /// <summary>Halen sürmekte olan işler (Open, InProgress).</summary>
    public List<StaffTaskDto> Active { get; set; } = [];

    /// <summary>Kapanmış işler (Resolved, Rejected).</summary>
    public List<StaffTaskDto> Past { get; set; } = [];
}

/// <summary>
/// Bir ekip üyesine not düşülmüş görevler.
/// Kapsam yöneticinin kendi departmanıdır; başka departmanın çalışanı sorulamaz.
/// </summary>
public record GetStaffTasksQuery(Guid StaffId) : IRequest<StaffTasksDto>;

public class GetStaffTasksHandler : IRequestHandler<GetStaffTasksQuery, StaffTasksDto>
{
    private const int CommentPreviewLength = 160;

    private readonly IStaffMemberRepository _staffRepository;
    private readonly IActionItemRepository _actionItemRepository;
    private readonly ICurrentUserService _currentUser;

    public GetStaffTasksHandler(
        IStaffMemberRepository staffRepository,
        IActionItemRepository actionItemRepository,
        ICurrentUserService currentUser)
    {
        _staffRepository = staffRepository;
        _actionItemRepository = actionItemRepository;
        _currentUser = currentUser;
    }

    public async Task<StaffTasksDto> Handle(GetStaffTasksQuery request, CancellationToken cancellationToken)
    {
        var departmentId = StaffScope.RequireDepartment(_currentUser);

        var staff = await _staffRepository.GetByIdAsync(request.StaffId)
            ?? throw new DomainException("Çalışan bulunamadı.");
        StaffScope.EnsureOwned(staff, departmentId);

        var items = await _actionItemRepository.GetByAssignedStaffIdAsync(request.StaffId);

        var result = new StaffTasksDto
        {
            StaffId = staff.Id,
            StaffName = staff.FullName,
        };

        foreach (var item in items)
        {
            var dto = new StaffTaskDto
            {
                Id = item.Id,
                ReviewId = item.ReviewId,
                Title = item.Title,
                Status = item.Status.ToString(),
                DueDate = item.DueDate,
                CreatedAt = item.CreatedAt,
                ReviewComment = Preview(item.Review?.Comment),
            };

            // "Geçmiş" = kapanmış işler. Yönetici açısından ayrım budur:
            // hâlâ uğraşılan iş mi, bitmiş iş mi.
            if (item.Status is ActionItemStatus.Resolved or ActionItemStatus.Rejected)
            {
                result.Past.Add(dto);
            }
            else
            {
                result.Active.Add(dto);
            }
        }

        return result;
    }

    private static string? Preview(string? comment)
    {
        if (string.IsNullOrWhiteSpace(comment))
        {
            return null;
        }

        var trimmed = comment.Trim();
        return trimmed.Length <= CommentPreviewLength
            ? trimmed
            : string.Concat(trimmed.AsSpan(0, CommentPreviewLength), "...");
    }
}
