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
}

public class GetActionItemsHandler : IRequestHandler<GetActionItemsQuery, List<ActionItemDetailsDto>>
{
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IDepartmentRepository _departmentRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetActionItemsHandler(
        IActionItemRepository actionItemRepository,
        IDepartmentRepository departmentRepository,
        ICurrentUserService currentUserService)
    {
        _actionItemRepository = actionItemRepository;
        _departmentRepository = departmentRepository;
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

        return items.Select(x =>
        {
            var dto = x.Adapt<ActionItemDetailsDto>();
            dto.DepartmentName = departments.TryGetValue(x.DepartmentId, out var dept) ? dept.Name : "Bilinmeyen";
            return dto;
        }).ToList();
    }
}
