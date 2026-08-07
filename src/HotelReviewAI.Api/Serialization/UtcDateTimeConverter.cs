using System.Text.Json;
using System.Text.Json.Serialization;

namespace HotelReviewAI.Api.Serialization;

/// <summary>
/// Gelen JSON tarihlerini UTC'ye normalize eder.
///
/// Neden gerekli: veritabanındaki tarih kolonları "timestamp with time zone"
/// ve Npgsql bunlara yalnızca DateTimeKind.Utc yazılmasına izin veriyor.
/// Tarayıcının &lt;input type="date"&gt; alanı ise saat dilimi olmadan
/// "2026-08-06" gönderiyor; System.Text.Json bunu Kind=Unspecified olarak
/// ayrıştırınca kayıt sırasında şu hata alınıyordu:
///
///   Cannot write DateTime with Kind=Unspecified to PostgreSQL type
///   'timestamp with time zone', only UTC is supported.
///
/// Bu dönüştürücü olmadan aynı hata her yeni tarih alanında tekrar eder
/// (önce personel kaydında, sonra görev atamada yaşandı). Tek yerde
/// çözülmesi tercih edildi.
///
/// Davranış:
/// - Saat dilimi belirtilmişse (Z ya da +03:00) gerçek an korunur, UTC'ye çevrilir.
/// - Belirtilmemişse değer takvim tarihi/saati kabul edilip UTC olarak
///   İŞARETLENİR. Yerel saate göre çevrilmez; çevrilseydi "2026-08-06"
///   saat dilimine göre bir gün kayabilirdi.
/// </summary>
public class UtcDateTimeConverter : JsonConverter<DateTime>
{
    public override DateTime Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var value = reader.GetDateTime();
        return value.Kind switch
        {
            DateTimeKind.Utc => value,
            DateTimeKind.Local => value.ToUniversalTime(),
            _ => DateTime.SpecifyKind(value, DateTimeKind.Utc),
        };
    }

    public override void Write(Utf8JsonWriter writer, DateTime value, JsonSerializerOptions options)
        => writer.WriteStringValue(value.Kind == DateTimeKind.Unspecified
            ? DateTime.SpecifyKind(value, DateTimeKind.Utc)
            : value.ToUniversalTime());
}

/// <summary>Nullable karşılığı — <see cref="UtcDateTimeConverter"/> ile aynı kurallar.</summary>
public class NullableUtcDateTimeConverter : JsonConverter<DateTime?>
{
    private static readonly UtcDateTimeConverter Inner = new();

    public override DateTime? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        => reader.TokenType == JsonTokenType.Null ? null : Inner.Read(ref reader, typeof(DateTime), options);

    public override void Write(Utf8JsonWriter writer, DateTime? value, JsonSerializerOptions options)
    {
        if (value is null)
        {
            writer.WriteNullValue();
            return;
        }

        Inner.Write(writer, value.Value, options);
    }
}
