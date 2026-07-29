using FluentAssertions;
using HotelReviewAI.Application.Commands.Reviews;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using NSubstitute;
using System;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace HotelReviewAI.Tests.Commands;

public class CreateReviewHandlerTests
{
    private readonly IReviewRepository _reviewRepository;
    private readonly IReviewAnalysisProcessingService _analysisProcessingService;
    private readonly CreateReviewHandler _handler;

    public CreateReviewHandlerTests()
    {
        _reviewRepository = Substitute.For<IReviewRepository>();
        _analysisProcessingService = Substitute.For<IReviewAnalysisProcessingService>();

        _handler = new CreateReviewHandler(
            _reviewRepository,
            _analysisProcessingService
        );
    }

    [Fact]
    public async Task Handle_ShouldSaveReviewAndCallProcessingService()
    {
        // Arrange
        var command = new CreateReviewCommand(
            "Ahmet Yılmaz",
            "Odada sıcak su akmıyordu, temizlik çok kötüydü.",
            1,
            "tr",
            HotelReviewAI.Domain.Enums.ReviewSource.Manual,
            DateTime.UtcNow
        );

        // Act
        var result = await _handler.Handle(command, CancellationToken.None);

        // Assert
        result.Should().NotBeEmpty();

        // Yorumun veritabanına kaydedildiğini doğrula
        await _reviewRepository.Received(1).AddAsync(Arg.Any<Review>());

        // Analiz servisinin çağrıldığını doğrula
        await _analysisProcessingService.Received(1).ProcessAnalysisAsync(
            Arg.Any<Review>(),
            Arg.Is(false),
            Arg.Any<CancellationToken>()
        );
    }
}
