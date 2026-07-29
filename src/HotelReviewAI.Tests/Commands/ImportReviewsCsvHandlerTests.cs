using FluentAssertions;
using HotelReviewAI.Application.Commands.Reviews;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using MediatR;
using NSubstitute;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace HotelReviewAI.Tests.Commands;

public class ImportReviewsCsvHandlerTests
{
    private readonly IMediator _mediator;
    private readonly IHotelRepository _hotelRepository;
    private readonly ICurrentUserService _currentUserService;
    private readonly ImportReviewsCsvHandler _handler;

    public ImportReviewsCsvHandlerTests()
    {
        _mediator = Substitute.For<IMediator>();
        _hotelRepository = Substitute.For<IHotelRepository>();
        _currentUserService = Substitute.For<ICurrentUserService>();

        _handler = new ImportReviewsCsvHandler(_mediator, _hotelRepository, _currentUserService);
    }

    [Fact]
    public async Task Handle_WithValidCsvStream_ShouldImportReviewsSuccessfully()
    {
        // Arrange
        var hotelId = Guid.NewGuid();
        _hotelRepository.GetAllAsync().Returns(new List<Hotel> { new Hotel { Id = hotelId, Name = "Test Hotel" } });

        var csvContent = "GuestName,Comment,Rating,ReviewDate,Source,Language\n" +
                         "Ahmet Yılmaz,Resepsiyon ve odadaki hizmet harikaydı ancak klima bozuktu.,4,2026-07-20,Web,tr\n" +
                         "Eleni P,Breakfast was delicious but wifi was dropping every 5 minutes.,3,2026-07-21,Web,en";

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(csvContent));

        var command = new ImportReviewsCsvCommand(stream, hotelId);

        // Act
        var result = await _handler.Handle(command, CancellationToken.None);

        // Assert
        result.Should().NotBeNull();
        result.SuccessCount.Should().Be(2);
        result.Errors.Should().BeEmpty();

        await _mediator.Received(2).Send(Arg.Any<CreateReviewCommand>(), Arg.Any<CancellationToken>());
    }
}
