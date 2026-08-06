using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Dashboard;

public record GetCategoryDistributionQuery(DateTime? DateFrom = null, DateTime? DateTo = null, Guid? HotelId = null)
    : IRequest<List<CategoryDistributionDto>>;

public class CategoryDistributionDto
{
    public string CategoryName { get; set; } = string.Empty;

    /// <summary>
    /// Bu kategoriden kaç kez bahsedildiği (clause sayısı) — yorum sayısı DEĞİL.
    /// Aynı yorumun iki cümlesi aynı kategoriye düşerse iki kez sayılır.
    /// </summary>
    public int MentionCount { get; set; }

    public double NegativeRatio { get; set; }

    public int PositiveCount { get; set; }
    public int NeutralCount { get; set; }
    public int NegativeCount { get; set; }

    /// <summary>Kategorisi çözülemeyen cümlelerin toplandığı satır.</summary>
    public bool IsUncategorized { get; set; }
}

public class GetCategoryDistributionHandler : IRequestHandler<GetCategoryDistributionQuery, List<CategoryDistributionDto>>
{
    private readonly IDashboardReadRepository _readRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetCategoryDistributionHandler(
        IDashboardReadRepository readRepository,
        ICurrentUserService currentUserService)
    {
        _readRepository = readRepository;
        _currentUserService = currentUserService;
    }

    public async Task<List<CategoryDistributionDto>> Handle(
        GetCategoryDistributionQuery request, CancellationToken cancellationToken)
    {
        var scope = DashboardScope.Resolve(_currentUserService, request.HotelId);
        if (scope.ReturnsNothing)
            return [];

        var filter = DashboardQueryFilter.Create(scope, request.DateFrom, request.DateTo);
        var rows = await _readRepository.GetCategoryStatsAsync(filter, cancellationToken);

        var distribution = rows
            .Select(r =>
            {
                var total = r.PositiveCount + r.NeutralCount + r.NegativeCount;
                var isUncategorized = string.IsNullOrWhiteSpace(r.CategoryName);

                return new CategoryDistributionDto
                {
                    CategoryName = isUncategorized ? DashboardTopicRules.UncategorizedName : r.CategoryName!,
                    MentionCount = total,
                    PositiveCount = r.PositiveCount,
                    NeutralCount = r.NeutralCount,
                    NegativeCount = r.NegativeCount,
                    NegativeRatio = total > 0 ? Math.Round((double)r.NegativeCount / total * 100, 1) : 0,
                    IsUncategorized = isUncategorized
                };
            })
            .Where(d => d.MentionCount > 0)
            .ToList();

        // Departman kapsamı varken "Sınıflandırılamayan" GİZLENİR: sınıflandırılamamış
        // bir cümleyi bir departmana atfetmenin yolu yok. Önceki kod bu satırı departman
        // filtresine rağmen otel geneli sayıyla hesaplıyordu; kova artık grafikte
        // görünür olduğu için bu gözle görülür bir hataya dönüşürdü.
        if (scope.DepartmentId.HasValue)
        {
            distribution = distribution.Where(d => !d.IsUncategorized).ToList();
        }

        // Hacme göre sıralanır; "Sınıflandırılamayan" boyutu ne olursa olsun en sonda.
        // Yatay yığılmış çubuk bir hacim sıralaması olarak okunur.
        return distribution
            .OrderBy(d => d.IsUncategorized)
            .ThenByDescending(d => d.MentionCount)
            .ThenBy(d => d.CategoryName, StringComparer.Ordinal)
            .ToList();
    }
}
