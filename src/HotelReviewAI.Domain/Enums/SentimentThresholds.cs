namespace HotelReviewAI.Domain.Enums;

/// <summary>
/// Bir yorumun genel duygu durumu, cümle bazlı analizlerin SentimentScore ortalamasından
/// türetilir. Eşikler tek bir yerde tutulur; aksi hâlde liste filtresi ile ekrandaki rozet
/// farklı kurallara göre hesaplanıp "Olumlu" filtresinde "Olumsuz" rozetli satırlar çıkıyordu.
/// </summary>
public static class SentimentThresholds
{
    public const double Positive = 0.15;
    public const double Negative = -0.15;

    public static Sentiment FromAverageScore(double averageScore) => averageScore switch
    {
        > Positive => Enums.Sentiment.Positive,
        < Negative => Enums.Sentiment.Negative,
        _ => Enums.Sentiment.Neutral
    };
}
