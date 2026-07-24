using HotelReviewAI.Application.Commands.Users;
using HotelReviewAI.Application.Queries.Users;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Client: Web Panel (Angular) - Personel Listeleme / Ekleme
/// </summary>
[ApiController]
[Tags("Web Panel (Angular) - Users")]
[Authorize(Roles = Roles.Admin)]
[Route("api/users")]
public class UsersController : ControllerBase
{
    private readonly IMediator _mediator;

    public UsersController(IMediator mediator)
    {
        _mediator = mediator;
    }

    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var result = await _mediator.Send(new GetUsersQuery(effectiveHotelId));
        return Ok(BaseResponse<object>.Ok(result));
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateUserCommand command)
    {
        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Kullanıcı oluşturuldu"));
    }
}
