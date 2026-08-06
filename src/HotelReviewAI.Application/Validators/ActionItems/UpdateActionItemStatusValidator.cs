using FluentValidation;
using HotelReviewAI.Application.Commands.ActionItems;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Application.Validators.ActionItems;

/// <summary>
/// ActionItem durum geçiş kuralları:
///   Open      → InProgress, Resolved, Rejected
///   InProgress → Resolved, Rejected
///   Resolved   → (terminal — değiştirilemez)
///   Rejected   → (terminal — değiştirilemez)
/// </summary>
public class UpdateActionItemStatusValidator : AbstractValidator<UpdateActionItemStatusCommand>
{
    private readonly IActionItemRepository _actionItemRepository;

    public UpdateActionItemStatusValidator(IActionItemRepository actionItemRepository)
    {
        _actionItemRepository = actionItemRepository;

        RuleFor(x => x.Id)
            .NotEmpty().WithMessage("Görev Id boş olamaz.");

        RuleFor(x => x)
            .MustAsync(BeValidTransitionAsync)
            .WithMessage("Geçersiz durum geçişi. Mevcut durumdan istenen duruma geçilemez.");
    }

    private async Task<bool> BeValidTransitionAsync(
        UpdateActionItemStatusCommand command,
        CancellationToken ct)
    {
        var item = await _actionItemRepository.GetByIdAsync(command.Id);
        if (item is null)
            return true; // Entity bulunamazsa controller 404 döndürsün

        return (item.Status, command.Status) switch
        {
            // Open'dan her duruma geçilebilir
            (ActionItemStatus.Open, _) => true,
            // InProgress'ten yalnızca Resolved veya Rejected'a geçilebilir
            (ActionItemStatus.InProgress, ActionItemStatus.Resolved) => true,
            (ActionItemStatus.InProgress, ActionItemStatus.Rejected) => true,
            // Terminal durumlar değiştirilemez
            (ActionItemStatus.Resolved, _) => false,
            (ActionItemStatus.Rejected, _) => false,
            // Diğer geçersiz durumlar
            _ => false
        };
    }
}
