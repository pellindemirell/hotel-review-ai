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
/// Target Clients: Mobile (Flutter) & Web Panel (Angular) - Personel Listeleme / Ekleme
/// </summary>
[ApiController]
[Tags("Common (Shared) - Users")]
[Authorize]
[Route("api/users")]
public class UsersController : ControllerBase
{
    private readonly IMediator _mediator;
    private readonly ICurrentUserService _currentUserService;
    private readonly IUserRepository _userRepository;

    public UsersController(IMediator mediator, ICurrentUserService currentUserService, IUserRepository userRepository)
    {
        _mediator = mediator;
        _currentUserService = currentUserService;
        _userRepository = userRepository;
    }

    [HttpGet]
    /// <param name="allHotels">
    /// Yalnızca Personel Yönetimi ekranı için: SuperAdmin'in tüm otellerin personelini
    /// tek listede görmesini sağlar. Varsayılan olarak kapalıdır; görev atama gibi ekranlar
    /// seçili otelin dışındaki kişileri listelememelidir.
    /// </param>
    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] Guid? departmentId = null,
        [FromQuery] Guid? hotelId = null,
        [FromQuery] bool allHotels = false,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;

        // SuperAdmin yalnızca açıkça istendiğinde otel kısıtı olmadan listeler.
        if (_currentUserService.Role == UserRole.SuperAdmin && allHotels)
        {
            effectiveHotelId = null;
        }

        Guid? effectiveDepartmentId = departmentId;
        if (effectiveDepartmentId == null && _currentUserService.Role == UserRole.DepartmentManager)
        {
            effectiveDepartmentId = _currentUserService.DepartmentId;
            effectiveHotelId = effectiveHotelId ?? _currentUserService.HotelId;

            if (effectiveHotelId == null && _currentUserService.UserId.HasValue)
            {
                var currentUserEntity = await _userRepository.GetByIdAsync(_currentUserService.UserId.Value);
                effectiveHotelId = currentUserEntity?.HotelId;
            }
        }

        var result = await _mediator.Send(new GetUsersQuery(effectiveHotelId, effectiveDepartmentId, allHotels));
        return Ok(BaseResponse<object>.Ok(result));
    }

    [HttpPost]
    [Authorize(Policy = "HotelAdminOrAbove")]
    public async Task<IActionResult> Create(
        [FromBody] CreateUserCommand command,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        command = command with { HotelId = hotelIdHeader ?? command.HotelId };

        if (_currentUserService.Role == UserRole.HotelAdmin)
        {
            if (command.Role == UserRole.SuperAdmin || command.Role == UserRole.HotelAdmin)
            {
                return StatusCode(StatusCodes.Status403Forbidden, BaseResponse<object>.Fail("Otel yöneticileri yalnızca departman yöneticisi oluşturabilir."));
            }

            // HotelAdmin kendi otelinde herhangi bir departman seçebilir, ama başka bir otele
            // personel ekleyemez — HotelId her zaman kendi otelinden gelir.
            command = command with { HotelId = _currentUserService.HotelId };
        }

        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Kullanıcı oluşturuldu"));
    }
}
