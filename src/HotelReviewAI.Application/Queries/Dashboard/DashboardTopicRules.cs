namespace HotelReviewAI.Application.Queries.Dashboard;

/// <summary>
/// Şikayet konuları listesinin sınıflandırma kuralları.
/// </summary>
public static class DashboardTopicRules
{
    /// <summary>
    /// Gerçek bir konu taşımayan, ontolojinin fallback ürettiği aspect etiketleri.
    /// </summary>
    /// <remarks>
    /// "Genel Atmosfer" hem seed'lenmiş gerçek bir kategori hem de fallback kovası;
    /// canlı veride tek başına olumsuz cümlelerin yaklaşık üçte birini (504) topluyor.
    /// Listede bırakılırsa ilk sırayı kapıp asıl şikayeti ("Yemek Kalitesi", 113)
    /// gizler. "Genel Yönetim" bilinçli olarak DIŞARIDA — o gerçek bir kategori.
    /// </remarks>
    public static readonly HashSet<string> GenericAspects = new(StringComparer.OrdinalIgnoreCase)
    {
        "Genel",
        "Genel Atmosfer",
        "Genel Deneyim"
    };

    /// <summary>Birleştirilmiş genel satırın görünen adı.</summary>
    public const string GenericTopicName = "Genel / Sınıflandırılamayan";

    /// <summary>Genel satırın drill-down çağrısında kullanılan anahtarı.</summary>
    public const string GenericTopicKey = "__generic__";

    /// <summary>Kategorisi çözülemeyen cümleler için kategori dağılımında kullanılan ad.</summary>
    public const string UncategorizedName = "Sınıflandırılamayan";

    public static bool IsGeneric(string? aspectLabel) =>
        string.IsNullOrWhiteSpace(aspectLabel) || GenericAspects.Contains(aspectLabel);
}
