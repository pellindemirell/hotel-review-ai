using HotelReviewAI.Application.Commands.Categories;
using HotelReviewAI.Application.Queries.Categories;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Client: Web Panel (Angular) - Kategori Yönetimi
/// </summary>
[ApiController]
[Tags("Web Panel (Angular) - Categories")]
[Authorize]
[Route("api/categories")]
public class CategoriesController : ControllerBase
{
    private readonly IMediator _mediator;

    public CategoriesController(IMediator mediator)
    {
        _mediator = mediator;
    }

    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var result = await _mediator.Send(new GetCategoriesQuery(hotelIdHeader ?? hotelId));
        return Ok(BaseResponse<object>.Ok(result));
    }

    [HttpPost]
    [Authorize(Roles = $"{nameof(UserRole.SuperAdmin)},{nameof(UserRole.HotelAdmin)}")]
    public async Task<IActionResult> Create([FromBody] CreateCategoryCommand command)
    {
        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Kategori oluşturuldu"));
    }

    [HttpPut("{id:guid}")]
    [Authorize(Roles = $"{nameof(UserRole.SuperAdmin)},{nameof(UserRole.HotelAdmin)}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateCategoryCommand command)
    {
        if (id != command.Id)
        {
            return BadRequest(BaseResponse<object>.Fail("Id uyuşmuyor"));
        }

        var updated = await _mediator.Send(command);
        if (!updated)
        {
            return NotFound(BaseResponse<object>.Fail("Kategori bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Kategori güncellendi"));
    }
}
