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
    private readonly IReviewAttachmentRepository _reviewAttachmentRepository;
    private readonly IAnalysisJobRepository _analysisJobRepository;
    private readonly CreateReviewHandler _handler;

    public CreateReviewHandlerTests()
    {
        _reviewRepository = Substitute.For<IReviewRepository>();
        _reviewAttachmentRepository = Substitute.For<IReviewAttachmentRepository>();
        _analysisJobRepository = Substitute.For<IAnalysisJobRepository>();

        _handler = new CreateReviewHandler(
            _reviewRepository,
            _reviewAttachmentRepository,
            _analysisJobRepository
        );
    }

    [Fact]
    public async Task Handle_ShouldSaveReviewAndCallAnalysisQueue()
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
        await _analysisJobRepository.Received(1).AddAsync(Arg.Is<AnalysisJob>(j => j.ReviewId != Guid.Empty));
    }

    [Fact]
    public async Task Handle_WithPhotoUrl_ShouldCreateAttachment()
    {
        var command = new CreateReviewCommand(
            "Ayşe Demir",
            "Odanın klimasi bozuktu, fotoğrafını ekledim.",
            2,
            "tr",
            HotelReviewAI.Domain.Enums.ReviewSource.Manual,
            DateTime.UtcNow,
            HotelId: null,
            PhotoUrl: "https://res.cloudinary.com/demo/image/upload/v1/x.jpg");

        await _handler.Handle(command, CancellationToken.None);

        await _reviewAttachmentRepository.Received(1).AddAsync(
            Arg.Is<ReviewAttachment>(a =>
                a.FileUrl == "https://res.cloudinary.com/demo/image/upload/v1/x.jpg"
                && a.FileType == ".jpg"
                && a.ReviewId != Guid.Empty));
    }

    [Fact]
    public async Task Handle_WithoutPhotoUrl_ShouldNotCreateAttachment()
    {
        var command = new CreateReviewCommand(
            "Mehmet Kaya",
            "Kahvaltı gayet iyiydi, teşekkürler.",
            5,
            "tr",
            HotelReviewAI.Domain.Enums.ReviewSource.Manual,
            DateTime.UtcNow);

        await _handler.Handle(command, CancellationToken.None);

        await _reviewAttachmentRepository.DidNotReceive().AddAsync(Arg.Any<ReviewAttachment>());
    }
}
