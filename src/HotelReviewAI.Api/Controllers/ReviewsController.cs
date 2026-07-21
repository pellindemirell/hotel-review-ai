using HotelReviewAI.Application.Commands.Reviews;
using HotelReviewAI.Application.Queries.Reviews;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace HotelReviewAI.Api.Controllers;

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

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateReviewCommand command)
    {
        var id = await _mediator.Send(command);
        return Ok(BaseResponse<Guid>.Ok(id, "Yorum oluşturuldu"));
    }

    [HttpGet]
    public async Task<IActionResult> GetAll(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo,
        [FromQuery] Sentiment? sentiment,
        [FromQuery] Guid? categoryId,
        [FromQuery] Guid? departmentId,
        [FromQuery] ReviewSource? source,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 20)
    {
        var query = new GetReviewsQuery(dateFrom, dateTo, sentiment, categoryId, departmentId, source, pageNumber, pageSize);
        var result = await _mediator.Send(query);
        return Ok(result);
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> GetById(Guid id)
    {
        var result = await _mediator.Send(new GetReviewByIdQuery(id));
        if (result is null)
        {
            return NotFound(BaseResponse<object>.Fail("Yorum bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(result));
    }

    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Delete(Guid id)
    {
        var deleted = await _mediator.Send(new DeleteReviewCommand(id));
        if (!deleted)
        {
            return NotFound(BaseResponse<object>.Fail("Yorum bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Yorum silindi"));
    }

    [HttpPost("import")]
    [Consumes("multipart/form-data")]
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

    [HttpPost("{id:guid}/reanalyze")]
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
