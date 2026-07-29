using FluentAssertions;
using HotelReviewAI.Application.Commands.ActionItems;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Application.Validators.ActionItems;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using NSubstitute;
using System;
using System.Threading.Tasks;
using Xunit;

namespace HotelReviewAI.Tests.Validators;

public class UpdateActionItemStatusValidatorTests
{
    private readonly IActionItemRepository _actionItemRepository;
    private readonly UpdateActionItemStatusValidator _validator;

    public UpdateActionItemStatusValidatorTests()
    {
        _actionItemRepository = Substitute.For<IActionItemRepository>();
        _validator = new UpdateActionItemStatusValidator(_actionItemRepository);
    }

    [Theory]
    [InlineData(ActionItemStatus.Open, ActionItemStatus.InProgress)]
    [InlineData(ActionItemStatus.Open, ActionItemStatus.Resolved)]
    [InlineData(ActionItemStatus.Open, ActionItemStatus.Rejected)]
    [InlineData(ActionItemStatus.InProgress, ActionItemStatus.Resolved)]
    [InlineData(ActionItemStatus.InProgress, ActionItemStatus.Rejected)]
    public async Task Validate_WithValidTransitions_ShouldBeValid(ActionItemStatus currentStatus, ActionItemStatus targetStatus)
    {
        // Arrange
        var itemId = Guid.NewGuid();
        var actionItem = new ActionItem
        {
            Title = "Gerekli aksiyon",
            Status = currentStatus
        };

        _actionItemRepository.GetByIdAsync(itemId).Returns(actionItem);

        var command = new UpdateActionItemStatusCommand(itemId, targetStatus);

        // Act
        var result = await _validator.ValidateAsync(command);

        // Assert
        result.IsValid.Should().BeTrue();
    }

    [Theory]
    [InlineData(ActionItemStatus.Resolved, ActionItemStatus.InProgress)]
    [InlineData(ActionItemStatus.Resolved, ActionItemStatus.Open)]
    [InlineData(ActionItemStatus.Rejected, ActionItemStatus.InProgress)]
    [InlineData(ActionItemStatus.Rejected, ActionItemStatus.Open)]
    public async Task Validate_WithInvalidTransitionsFromTerminalState_ShouldBeInvalid(ActionItemStatus currentStatus, ActionItemStatus targetStatus)
    {
        // Arrange
        var itemId = Guid.NewGuid();
        var actionItem = new ActionItem
        {
            Title = "Terminal durumda görev",
            Status = currentStatus
        };

        _actionItemRepository.GetByIdAsync(itemId).Returns(actionItem);

        var command = new UpdateActionItemStatusCommand(itemId, targetStatus);

        // Act
        var result = await _validator.ValidateAsync(command);

        // Assert
        result.IsValid.Should().BeFalse();
        result.Errors.Should().Contain(e => e.ErrorMessage.Contains("Geçersiz durum geçişi."));
    }
}
