using HotelReviewAI.Application.Commands.Departments;
using HotelReviewAI.Application.Queries.Departments;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Client: Web Panel (Angular) - Departman Yönetimi
/// </summary>
[ApiController]
[Tags("Web Panel (Angular) - Departments")]
[Authorize]
[Route("api/departments")]
public class DepartmentsController : ControllerBase
{
    private readonly IMediator _mediator;

    public DepartmentsController(IMediator mediator)
    {
        _mediator = mediator;
    }

    [HttpGet]
    public async Task<IActionResult> GetAll()
    {
        var result = await _mediator.Send(new GetDepartmentsQuery());
        return Ok(BaseResponse<object>.Ok(result));
    }

    [HttpPost]
    [Authorize(Roles = $"{Roles.Admin},{Roles.Manager}")]
    public async Task<IActionResult> Create([FromBody] CreateDepartmentCommand command)
    {
        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Departman oluşturuldu"));
    }

    [HttpPut("{id:guid}")]
    [Authorize(Roles = $"{Roles.Admin},{Roles.Manager}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateDepartmentCommand command)
    {
        if (id != command.Id)
        {
            return BadRequest(BaseResponse<object>.Fail("Id uyuşmuyor"));
        }

        var updated = await _mediator.Send(command);
        if (!updated)
        {
            return NotFound(BaseResponse<object>.Fail("Departman bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Departman güncellendi"));
    }
}
