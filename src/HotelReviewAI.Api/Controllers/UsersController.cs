using HotelReviewAI.Application.Commands.Users;
using HotelReviewAI.Application.Interfaces;
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
[Authorize(Roles = $"{Roles.Admin},{Roles.Manager}")]
[Route("api/users")]
public class UsersController : ControllerBase
{
    private readonly IMediator _mediator;
    private readonly ICurrentUserService _currentUserService;

    public UsersController(IMediator mediator, ICurrentUserService currentUserService)
    {
        _mediator = mediator;
        _currentUserService = currentUserService;
    }

    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        
        Guid? effectiveDepartmentId = null;
        if (_currentUserService.Role == Roles.Manager)
        {
            effectiveDepartmentId = _currentUserService.DepartmentId;
        }

        var result = await _mediator.Send(new GetUsersQuery(effectiveHotelId, effectiveDepartmentId));
        return Ok(BaseResponse<object>.Ok(result));
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateUserCommand command)
    {
        if (_currentUserService.Role == Roles.Manager)
        {
            if (command.Role == Roles.Admin || command.Role == Roles.Manager)
            {
                return StatusCode(StatusCodes.Status403Forbidden, BaseResponse<object>.Fail("Managers can only create DepartmentUser or MobileUser."));
            }

            command = command with { DepartmentId = _currentUserService.DepartmentId };
        }

        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Kullanıcı oluşturuldu"));
    }
}
