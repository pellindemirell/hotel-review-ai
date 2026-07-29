using HotelReviewAI.Application.Interfaces;
using Mapster;
using MediatR;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Queries.ActionItems;

public record GetActionItemsQuery(Guid? DepartmentId, Guid? AssignedTo) : IRequest<List<ActionItemDetailsDto>>;

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

    public GetActionItemsHandler(
        IActionItemRepository actionItemRepository,
        IDepartmentRepository departmentRepository)
    {
        _actionItemRepository = actionItemRepository;
        _departmentRepository = departmentRepository;
    }

    public async Task<List<ActionItemDetailsDto>> Handle(GetActionItemsQuery request, CancellationToken cancellationToken)
    {
        IEnumerable<Domain.Entities.ActionItem> items;

        if (request.DepartmentId.HasValue)
        {
            items = await _actionItemRepository.GetByDepartmentIdAsync(request.DepartmentId.Value);
        }
        else if (request.AssignedTo.HasValue)
        {
            items = await _actionItemRepository.GetByUserIdAsync(request.AssignedTo.Value);
        }
        else
        {
            items = await _actionItemRepository.GetAllAsync();
        }

        var departments = (await _departmentRepository.GetAllAsync()).ToDictionary(d => d.Id);

        return items.Select(x =>
        {
            var dto = x.Adapt<ActionItemDetailsDto>();
            dto.DepartmentName = departments.TryGetValue(x.DepartmentId, out var dept) ? dept.Name : "Bilinmeyen";
            return dto;
        }).ToList();
    }
}
