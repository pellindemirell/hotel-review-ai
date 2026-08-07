using HotelReviewAI.Application.Interfaces;
using Mapster;
using MediatR;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Queries.ActionItems;

public record GetActionItemsQuery(Guid? DepartmentId, Guid? AssignedTo, Guid? HotelId = null) : IRequest<List<ActionItemDetailsDto>>;

public class ActionItemDetailsDto
{
    public Guid Id { get; set; }
    public Guid ReviewId { get; set; }
    public Guid DepartmentId { get; set; }
    public string DepartmentName { get; set; } = string.Empty;
    public Guid? AssignedTo { get; set; }
    public string Title { get; set; } = string.Empty;
    public string Status { get; set; } = string.Empty;
    public DateTime? DueDate { get; set; }

    /// <summary>
    /// Departman yöneticisinin bu işi verdiği ekip üyesi — yalnızca kayıt.
    /// Yetki, filtre ve durum akışını etkilemez.
    /// </summary>
    public Guid? AssignedStaffId { get; set; }
    public string? AssignedStaffName { get; set; }
}

public class GetActionItemsHandler : IRequestHandler<GetActionItemsQuery, List<ActionItemDetailsDto>>
{
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IDepartmentRepository _departmentRepository;
    private readonly IStaffMemberRepository _staffMemberRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetActionItemsHandler(
        IActionItemRepository actionItemRepository,
        IDepartmentRepository departmentRepository,
        IStaffMemberRepository staffMemberRepository,
        ICurrentUserService currentUserService)
    {
        _actionItemRepository = actionItemRepository;
        _departmentRepository = departmentRepository;
        _staffMemberRepository = staffMemberRepository;
        _currentUserService = currentUserService;
    }

    public async Task<List<ActionItemDetailsDto>> Handle(GetActionItemsQuery request, CancellationToken cancellationToken)
    {
        Guid? effectiveHotelId = request.HotelId;
        Guid? effectiveDepartmentId = request.DepartmentId;

        if (_currentUserService.Role == HotelReviewAI.Domain.Enums.UserRole.HotelAdmin)
        {
            effectiveHotelId = _currentUserService.HotelId;
        }
        else if (_currentUserService.Role == HotelReviewAI.Domain.Enums.UserRole.DepartmentManager)
        {
            effectiveHotelId = _currentUserService.HotelId;
            effectiveDepartmentId = _currentUserService.DepartmentId;
        }

        var items = await _actionItemRepository.GetFilteredAsync(
            effectiveDepartmentId,
            request.AssignedTo,
            effectiveHotelId
        );

        var departments = (await _departmentRepository.GetAllAsync()).ToDictionary(d => d.Id);

        // Adlar ayrı sorguyla çekiliyor: Include ile gelen ilişki global
        // IsActive filtresine takıldığından, ekipten çıkarılmış çalışanın adı
        // null geliyor ve "kime verdim" notu boşa düşüyordu.
        var staffNames = await _staffMemberRepository.GetNamesByIdsAsync(
            items.Where(x => x.AssignedStaffId.HasValue).Select(x => x.AssignedStaffId!.Value));

        return items.Select(x =>
        {
            var dto = x.Adapt<ActionItemDetailsDto>();
            dto.DepartmentName = departments.TryGetValue(x.DepartmentId, out var dept) ? dept.Name : "Bilinmeyen";
            dto.AssignedStaffName = x.AssignedStaffId.HasValue
                && staffNames.TryGetValue(x.AssignedStaffId.Value, out var staffName)
                    ? staffName
                    : null;
            return dto;
        }).ToList();
    }
}
