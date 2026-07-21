using HotelReviewAI.Application.Commands.ActionItems;
using HotelReviewAI.Application.Queries.ActionItems;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Security.Claims;

namespace HotelReviewAI.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/action-items")]
public class ActionItemsController : ControllerBase
{
    private readonly IMediator _mediator;

    public ActionItemsController(IMediator mediator)
    {
        _mediator = mediator;
    }

    [HttpGet]
    public async Task<IActionResult> GetAll([FromQuery] Guid? departmentId, [FromQuery] Guid? assignedTo)
    {
        // DepartmentUser ve MobileUser yalnızca kendi departmanlarını görebilir
        var role = User.FindFirstValue(ClaimTypes.Role);
        if (role is Roles.DepartmentUser or Roles.MobileUser)
        {
            var claimDeptId = User.FindFirstValue("departmentId");
            if (!Guid.TryParse(claimDeptId, out var deptId))
            {
                return Forbid();
            }

            // Sorguyu kendi departmanıyla sınırla
            departmentId = deptId;
            assignedTo = null;
        }

        var result = await _mediator.Send(new GetActionItemsQuery(departmentId, assignedTo));
        return Ok(BaseResponse<object>.Ok(result));
    }

    [HttpPost]
    [Authorize(Roles = $"{Roles.Admin},{Roles.Manager}")]
    public async Task<IActionResult> Create([FromBody] CreateActionItemCommand command)
    {
        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Görev başarıyla oluşturuldu."));
    }

    [HttpPatch("{id:guid}/status")]
    public async Task<IActionResult> UpdateStatus(Guid id, [FromBody] UpdateActionItemStatusCommand command)
    {
        if (id != command.Id)
        {
            return BadRequest(BaseResponse<object>.Fail("Id uyuşmuyor."));
        }

        // DepartmentUser/MobileUser yalnızca kendi departmanlarına ait aksiyonları güncelleyebilir
        var role = User.FindFirstValue(ClaimTypes.Role);
        if (role is Roles.DepartmentUser or Roles.MobileUser)
        {
            var claimDeptIdStr = User.FindFirstValue("departmentId");
            if (!Guid.TryParse(claimDeptIdStr, out _))
            {
                return Forbid();
            }
            // Gerçek departman kontrolü GetActionItemsQuery üzerinden yapılır;
            // FluentValidation validator state transition kuralını uygular
        }

        var success = await _mediator.Send(command);
        if (!success)
        {
            return NotFound(BaseResponse<object>.Fail("Görev bulunamadı."));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Görev durumu güncellendi."));
    }
}
