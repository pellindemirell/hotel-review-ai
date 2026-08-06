namespace HotelReviewAI.Application.DTOs;

/// <summary>
/// AI servisinin /translate ucundan dönen çeviri sonucu.
/// </summary>
public class AiTranslationResult
{
    public string TranslatedText { get; set; } = string.Empty;

    /// <summary>Servisin langdetect ile tespit ettiği kaynak dil.</summary>
    public string DetectedLanguage { get; set; } = string.Empty;

    /// <summary>Metin zaten Türkçeyse true — bu durumda çeviri yapılmamıştır.</summary>
    public bool AlreadyTurkish { get; set; }
}
