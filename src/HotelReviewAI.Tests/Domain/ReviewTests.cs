using FluentAssertions;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using System;
using Xunit;

namespace HotelReviewAI.Tests.Domain;

public class ReviewTests
{
    [Fact]
    public void Create_WithValidParameters_ShouldReturnReview()
    {
        // Arrange & Act
        var review = Review.Create(
            guestName: "Ahmet Yılmaz",
            comment: "Oda temizliği ve servis oldukça iyiydi.",
            rating: 5,
            language: "tr",
            source: ReviewSource.Manual,
            reviewDate: DateTime.UtcNow,
            createdBy: null
        );

        // Assert
        review.Should().NotBeNull();
        review.GuestName.Should().Be("Ahmet Yılmaz");
        review.Rating.Should().Be(5);
        review.Comment.Should().Be("Oda temizliği ve servis oldukça iyiydi.");
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("Kısa")] // 10 karakterden az
    public void Create_WithInvalidComment_ShouldThrowDomainException(string invalidComment)
    {
        // Arrange, Act & Assert
        Action act = () => Review.Create(
            guestName: "Ahmet Yılmaz",
            comment: invalidComment,
            rating: 5,
            language: "tr",
            source: ReviewSource.Manual,
            reviewDate: DateTime.UtcNow,
            createdBy: null
        );

        act.Should().Throw<DomainException>()
           .WithMessage("Yorum en az 10 karakter olmalıdır.");
    }

    [Theory]
    [InlineData(0)]
    [InlineData(6)]
    [InlineData(-1)]
    public void Create_WithInvalidRating_ShouldThrowDomainException(int invalidRating)
    {
        // Arrange, Act & Assert
        Action act = () => Review.Create(
            guestName: "Ahmet Yılmaz",
            comment: "Oda temizliği ve servis oldukça iyiydi.",
            rating: invalidRating,
            language: "tr",
            source: ReviewSource.Manual,
            reviewDate: DateTime.UtcNow,
            createdBy: null
        );

        act.Should().Throw<DomainException>()
           .WithMessage("Rating 1-5 aralığında olmalıdır.");
    }
}
