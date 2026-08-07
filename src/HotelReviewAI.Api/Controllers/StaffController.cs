using HotelReviewAI.Application.Commands.Staff;
using HotelReviewAI.Application.Queries.Staff;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Departman yöneticisinin ekibi — Target Client: Web Panel (Angular)
/// </summary>
/// <remarks>
/// Buradaki kayıtların sistemde hesabı YOKTUR: giriş yapmazlar, rolleri ve
/// yetkileri yoktur. Kullanıcı hesapları ayrı bir uçtan (UsersController)
/// yönetilir. Kapsam her zaman oturumdaki yöneticinin kendi departmanıdır;
/// departman kimliği istekten değil token'dan okunur.
/// </remarks>
[ApiController]
[Authorize(Roles = "DepartmentManager")]
[Route("api/staff")]
[Tags("Web Panel (Angular) - Staff")]
public class StaffController : ControllerBase
{
    private readonly IMediator _mediator;

    public StaffController(IMediator mediator)
    {
        _mediator = mediator;
    }

    [HttpGet]
    public async Task<IActionResult> GetMyStaff()
    {
        var staff = await _mediator.Send(new GetMyStaffQuery());
        return Ok(BaseResponse<object>.Ok(staff));
    }

    /// <summary>
    /// Bir ekip üyesine not düşülmüş görevler — aktif ve geçmiş olarak ayrı.
    /// </summary>
    [HttpGet("{id:guid}/tasks")]
    public async Task<IActionResult> GetTasks(Guid id)
    {
        var tasks = await _mediator.Send(new GetStaffTasksQuery(id));
        return Ok(BaseResponse<object>.Ok(tasks));
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateStaffMemberCommand command)
    {
        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Çalışan eklendi."));
    }

    [HttpPut("{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateStaffMemberCommand command)
    {
        // Yol parametresi gövdeye üstün gelir; istemcinin iki yerde farklı
        // kimlik göndermesi sessizce başka kaydı güncellemesin.
        await _mediator.Send(command with { Id = id });
        return Ok(BaseResponse<object>.Ok(null!, "Çalışan güncellendi."));
    }

    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Delete(Guid id)
    {
        await _mediator.Send(new DeleteStaffMemberCommand(id));
        return Ok(BaseResponse<object>.Ok(null!, "Çalışan kaldırıldı."));
    }
}
