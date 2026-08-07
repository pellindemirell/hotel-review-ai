namespace HotelReviewAI.Application.Interfaces;

/// <summary>
/// Yorum görsellerini kalıcı depoya yazar.
/// Mobil ve web panelinin ikisi de aynı akışı kullanır; mantık tek yerde
/// durmazsa (Cloudinary + yerel yedek + doğrulama) iki kopya zamanla ayrışır.
/// </summary>
public interface IReviewPhotoStorage
{
    /// <summary>
    /// Görseli yükler ve erişilebilir adresini döndürür.
    /// Cloudinary yapılandırılmışsa mutlak https adresi, aksi hâlde yerel
    /// diske düşülüp göreli yol (/uploads/...) döner.
    /// </summary>
    Task<string> SaveAsync(byte[] content, string fileName, CancellationToken ct = default);

    /// <summary>
    /// Boyut, uzantı ve içerik türü kurallarını uygular.
    /// Geçerliyse null, değilse kullanıcıya gösterilecek hata mesajı döner.
    /// </summary>
    string? Validate(long lengthBytes, string fileName, string contentType);
}
