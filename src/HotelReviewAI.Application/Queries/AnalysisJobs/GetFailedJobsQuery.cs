using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Queries.AnalysisJobs;

public record GetFailedJobsQuery() : IRequest<List<FailedJobDto>>;

public class FailedJobDto
{
    public Guid Id { get; set; }
    public Guid ReviewId { get; set; }
    public int RetryCount { get; set; }
    public string? ErrorMessage { get; set; }
    public DateTime CreatedAt { get; set; }
}

public class GetFailedJobsHandler : IRequestHandler<GetFailedJobsQuery, List<FailedJobDto>>
{
    private readonly IAnalysisJobRepository _repository;
    private readonly ICurrentUserService _currentUserService;

    public GetFailedJobsHandler(IAnalysisJobRepository repository, ICurrentUserService currentUserService)
    {
        _repository = repository;
        _currentUserService = currentUserService;
    }

    public async Task<List<FailedJobDto>> Handle(GetFailedJobsQuery request, CancellationToken cancellationToken)
    {
        if (_currentUserService.Role != UserRole.SuperAdmin)
        {
            throw new UnauthorizedAccessException("Only SuperAdmins can view failed jobs.");
        }

        var failedJobs = await _repository.GetFailedJobsAsync();

        return failedJobs.Select(j => new FailedJobDto
        {
            Id = j.Id,
            ReviewId = j.ReviewId,
            RetryCount = j.RetryCount,
            ErrorMessage = j.ErrorMessage,
            CreatedAt = j.CreatedAt
        }).ToList();
    }
}
