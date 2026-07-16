namespace HotelReviewAI.Persistence.Seed;

public class ReviewSeedDto
{
    public string GuestName { get; set; } = string.Empty;
    public string Comment { get; set; } = string.Empty;
    public int Rating { get; set; }
    public DateTime ReviewDate { get; set; }
    public string Source { get; set; } = "Manual";
    public string Language { get; set; } = "tr";
}
