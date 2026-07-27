using HotelReviewAI.Application.Commands.Reviews;
using HotelReviewAI.Application.Queries.Reviews;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

using System.Security.Claims;
using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Clients: Mobile (Flutter) & Web Panel (Angular)
/// </summary>
[ApiController]
[Authorize]
[Route("api/reviews")]
public class ReviewsController : ControllerBase
{
    private readonly IMediator _mediator;

    public ReviewsController(IMediator mediator)
    {
        _mediator = mediator;
    }

    /// <summary>
    /// Masaüstünden manuel yorum girişi - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpPost]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Create(
        [FromBody] CreateReviewCommand command,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveCommand = command with { HotelId = hotelIdHeader ?? command.HotelId };
        var id = await _mediator.Send(effectiveCommand);
        return Accepted(BaseResponse<Guid>.Ok(id, "Yorum kaydedildi ve AI analizi için kuyruğa alındı."));
    }

    /// <summary>
    /// Yorum listeleme - Target Clients: Mobile (Flutter) & Web Panel (Angular)
    /// </summary>
    [HttpGet]
    [Tags("Common (Shared)")]
    public async Task<IActionResult> GetAll(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo,
        [FromQuery] Sentiment? sentiment,
        [FromQuery] Guid? categoryId,
        [FromQuery] Guid? departmentId,
        [FromQuery] ReviewSource? source,
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 20)
    {
        var role = User.FindFirstValue(System.Security.Claims.ClaimTypes.Role);
        if (role is Roles.Manager or Roles.DepartmentUser or Roles.MobileUser)
        {
            var claimDeptId = User.FindFirstValue("departmentId");
            if (Guid.TryParse(claimDeptId, out var deptId))
            {
                departmentId = deptId;
            }
        }

        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var query = new GetReviewsQuery(dateFrom, dateTo, sentiment, categoryId, departmentId, source, pageNumber, pageSize, effectiveHotelId);
        var result = await _mediator.Send(query);
        return Ok(result);
    }

    /// <summary>
    /// Yorum detay/analiz ekranı - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpGet("{id:guid}")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> GetById(Guid id)
    {
        var result = await _mediator.Send(new GetReviewByIdQuery(id));
        if (result is null)
        {
            return NotFound(BaseResponse<object>.Fail("Yorum bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Yorum silme - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpDelete("{id:guid}")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Delete(Guid id)
    {
        var deleted = await _mediator.Send(new DeleteReviewCommand(id));
        if (!deleted)
        {
            return NotFound(BaseResponse<object>.Fail("Yorum bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Yorum silindi"));
    }

    /// <summary>
    /// CSV ile toplu yorum yükleme - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpPost("import")]
    [Consumes("multipart/form-data")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Import(IFormFile file)
    {
        if (file == null || file.Length == 0)
        {
            return BadRequest(BaseResponse<object>.Fail("Lütfen geçerli bir CSV dosyası seçin."));
        }

        using var stream = file.OpenReadStream();
        var result = await _mediator.Send(new ImportReviewsCsvCommand(stream));

        return Ok(BaseResponse<ImportResultDto>.Ok(result, $"{result.SuccessCount} yorum başarıyla içe aktarıldı."));
    }

    /// <summary>
    /// Yorum yeniden analizi - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpPost("{id:guid}/reanalyze")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Reanalyze(Guid id)
    {
        var success = await _mediator.Send(new ReanalyzeReviewCommand(id));
        if (!success)
        {
            return BadRequest(BaseResponse<object>.Fail("Yorum yeniden analiz edilemedi."));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Yorum yeniden analiz edildi"));
    }
}
