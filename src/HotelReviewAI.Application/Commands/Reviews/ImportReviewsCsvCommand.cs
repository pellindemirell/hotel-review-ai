using CsvHelper;
using CsvHelper.Configuration;
using HotelReviewAI.Domain.Enums;
using MediatR;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Commands.Reviews;

public record ImportResultDto(int SuccessCount, List<string> Errors);

public record ImportReviewsCsvCommand(Stream FileStream) : IRequest<ImportResultDto>;

public class CsvReviewRecord
{
    public string GuestName { get; set; } = string.Empty;
    public string Comment { get; set; } = string.Empty;
    public string Rating { get; set; } = string.Empty;
    public string ReviewDate { get; set; } = string.Empty;
    public string Source { get; set; } = string.Empty;
    public string Language { get; set; } = string.Empty;
}

public class ImportReviewsCsvHandler : IRequestHandler<ImportReviewsCsvCommand, ImportResultDto>
{
    private readonly IMediator _mediator;

    public ImportReviewsCsvHandler(IMediator mediator)
    {
        _mediator = mediator;
    }

    public async Task<ImportResultDto> Handle(ImportReviewsCsvCommand request, CancellationToken cancellationToken)
    {
        var config = new CsvConfiguration(CultureInfo.InvariantCulture)
        {
            PrepareHeaderForMatch = args => args.Header.ToLower().Replace("_", "").Replace(" ", ""),
            HeaderValidated = null,
            MissingFieldFound = null
        };

        int lineNumber = 1; // Başlık satırı 1. satır kabul edilir. Veriler 2'den başlar.
        int successCount = 0;
        var errors = new List<string>();

        using (var reader = new StreamReader(request.FileStream))
        using (var csv = new CsvReader(reader, config))
        {
            var records = csv.GetRecordsAsync<CsvReviewRecord>(cancellationToken);
            
            try
            {
                await foreach (var r in records)
                {
                    lineNumber++;
                    var rowErrors = new List<string>();

                    if (string.IsNullOrWhiteSpace(r.GuestName))
                    {
                        rowErrors.Add("Misafir adı boş olamaz.");
                    }
                    if (string.IsNullOrWhiteSpace(r.Comment) || r.Comment.Length < 10)
                    {
                        rowErrors.Add("Yorum boş olamaz ve en az 10 karakter olmalıdır.");
                    }
                    if (!int.TryParse(r.Rating, out var ratingValue) || ratingValue < 1 || ratingValue > 5)
                    {
                        rowErrors.Add("Puan (Rating) 1 ile 5 arasında geçerli bir sayı olmalıdır.");
                    }
                    if (string.IsNullOrWhiteSpace(r.Language))
                    {
                        rowErrors.Add("Dil (Language) alanı boş olamaz.");
                    }

                    ReviewSource sourceValue = ReviewSource.Import;
                    if (!string.IsNullOrWhiteSpace(r.Source))
                    {
                        if (!Enum.TryParse<ReviewSource>(r.Source, true, out var parsedSource))
                        {
                            rowErrors.Add($"Geçersiz kaynak değeri: {r.Source}.");
                        }
                        else
                        {
                            sourceValue = parsedSource;
                        }
                    }

                    DateTime? reviewDateValue = null;
                    if (!string.IsNullOrWhiteSpace(r.ReviewDate))
                    {
                        if (DateTime.TryParse(r.ReviewDate, out var parsedDate))
                        {
                            reviewDateValue = DateTime.SpecifyKind(parsedDate, DateTimeKind.Utc);
                        }
                        else
                        {
                            rowErrors.Add("Geçersiz tarih formatı.");
                        }
                    }

                    if (rowErrors.Any())
                    {
                        errors.Add($"{lineNumber}. satır: {string.Join(" | ", rowErrors)}");
                        continue;
                    }

                    // Her bir yorumu CreateReviewCommand ile oluşturup kaydet ve AI analizini tetikle.
                    try
                    {
                        var createCommand = new CreateReviewCommand(
                            r.GuestName,
                            r.Comment,
                            ratingValue,
                            r.Language,
                            sourceValue,
                            reviewDateValue
                        );

                        await _mediator.Send(createCommand, cancellationToken);
                        successCount++;
                    }
                    catch (Exception ex)
                    {
                        errors.Add($"{lineNumber}. satır (Kaydetme Hatası): {ex.Message}");
                    }
                }
            }
            catch (Exception ex)
            {
                errors.Add($"CSV Okuma Hatası: {ex.Message}");
            }
        }

        return new ImportResultDto(successCount, errors);
    }
}
