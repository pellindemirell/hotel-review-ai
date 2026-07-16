using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Commands.Reviews;

public class DeleteReviewHandler : IRequestHandler<DeleteReviewCommand, bool>
{
    private readonly IReviewRepository _reviewRepository;

    public DeleteReviewHandler(IReviewRepository reviewRepository)
    {
        _reviewRepository = reviewRepository;
    }

    public async Task<bool> Handle(DeleteReviewCommand request, CancellationToken cancellationToken)
    {
        var review = await _reviewRepository.GetByIdAsync(request.Id);
        if (review is null)
        {
            return false;
        }

        // Soft delete: kayıt fiziksel olarak silinmez, IsActive=false yapılır.
        await _reviewRepository.DeleteAsync(review);
        return true;
    }
}
