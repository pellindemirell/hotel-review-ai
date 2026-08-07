using HotelReviewAI.Application.Commands.ActionItems;
using HotelReviewAI.Application.Queries.ActionItems;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Clients: Mobile (Flutter) & Web Panel (Angular)
/// </summary>
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

    /// <summary>
    /// Aksiyon öğelerini listele - Target Clients: Mobile (Flutter) & Web Panel (Angular)
    /// </summary>
    [HttpGet]
    [Tags("Common (Shared)")]
    public async Task<IActionResult> GetAll(
        [FromQuery] Guid? departmentId, 
        [FromQuery] Guid? assignedTo,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        // Otel/departman kısıtı GetActionItemsHandler içinde ICurrentUserService üzerinden zorunlu kılınır.
        var result = await _mediator.Send(new GetActionItemsQuery(departmentId, assignedTo, hotelIdHeader));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Aksiyon öğesi oluştur - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpPost]
    [Authorize(Roles = $"{nameof(UserRole.SuperAdmin)},{nameof(UserRole.HotelAdmin)},{nameof(UserRole.DepartmentManager)}")]
    [Tags("Web Panel (Angular) - ActionItems")]
    public async Task<IActionResult> Create([FromBody] CreateActionItemCommand command)
    {
        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Görev başarıyla oluşturuldu."));
    }

    /// <summary>
    /// Aksiyon durumu güncelle - Target Clients: Mobile (Flutter) & Web Panel (Angular)
    /// </summary>
    [HttpPatch("{id:guid}/status")]
    [Tags("Common (Shared)")]
    public async Task<IActionResult> UpdateStatus(Guid id, [FromBody] UpdateActionItemStatusCommand command)
    {
        if (id != command.Id)
        {
            return BadRequest(BaseResponse<object>.Fail("Id uyuşmuyor."));
        }

        // Otel/departman yetkisi UpdateActionItemStatusHandler içinde ICurrentUserService ile kontrol edilir;
        // durum geçiş kuralı ise UpdateActionItemStatusValidator tarafından uygulanır.
        var success = await _mediator.Send(command);
        if (!success)
        {
            return NotFound(BaseResponse<object>.Fail("Görev bulunamadı."));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Görev durumu güncellendi."));
    }

    /// <summary>
    /// Görevi ekip üyesine not düş - Target Client: Web Panel (Angular)
    /// </summary>
    /// <remarks>
    /// YALNIZCA KAYIT amaçlıdır: görev durumunu değiştirmez, bildirim
    /// göndermez, yetki ve filtreleri etkilemez. Departman yöneticisinin
    /// "bu işi kime vermiştim" sorusuna sonradan bakabilmesi içindir.
    /// Gövdede staffId null gönderilirse kayıt temizlenir.
    /// </remarks>
    [HttpPatch("{id:guid}/assign-staff")]
    [Authorize(Roles = "DepartmentManager")]
    [Tags("Web Panel (Angular) - Staff")]
    public async Task<IActionResult> AssignStaff(Guid id, [FromBody] AssignStaffRequest request)
    {
        await _mediator.Send(new AssignActionItemStaffCommand(id, request.StaffId));
        return Ok(BaseResponse<object>.Ok(null!, "Kayıt güncellendi."));
    }

    public record AssignStaffRequest(Guid? StaffId);
}
