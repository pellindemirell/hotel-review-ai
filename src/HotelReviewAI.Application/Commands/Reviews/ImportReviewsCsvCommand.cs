using CsvHelper;
using CsvHelper.Configuration;
using ExcelDataReader;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Commands.Reviews;

public record ImportResultDto(int SuccessCount, List<string> Errors);

public record ImportReviewsCsvCommand(Stream FileStream, Guid? HotelId = null) : IRequest<ImportResultDto>;

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
    private readonly IHotelRepository _hotelRepository;
    private readonly ICurrentUserService _currentUserService;

    static ImportReviewsCsvHandler()
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
    }

    public ImportReviewsCsvHandler(
        IMediator mediator,
        IHotelRepository hotelRepository,
        ICurrentUserService currentUserService)
    {
        _mediator = mediator;
        _hotelRepository = hotelRepository;
        _currentUserService = currentUserService;
    }

    public async Task<ImportResultDto> Handle(ImportReviewsCsvCommand request, CancellationToken cancellationToken)
    {
        using var ms = new MemoryStream();
        await request.FileStream.CopyToAsync(ms, cancellationToken);
        ms.Position = 0;

        var targetHotelId = request.HotelId ?? _currentUserService.HotelId;
        if (!targetHotelId.HasValue)
        {
            var hotels = await _hotelRepository.GetAllAsync();
            targetHotelId = hotels.FirstOrDefault()?.Id;
        }

        List<CsvReviewRecord> recordsList = [];

        // Check if stream is an Excel file (.xlsx or .xls)
        byte[] headerBytes = new byte[4];
        bool isExcel = false;
        if (ms.Length >= 4)
        {
            ms.Read(headerBytes, 0, 4);
            ms.Position = 0;
            // PK.. for .xlsx or D0 CF 11 E0 for .xls
            if ((headerBytes[0] == 0x50 && headerBytes[1] == 0x4B && headerBytes[2] == 0x03 && headerBytes[3] == 0x04) ||
                (headerBytes[0] == 0xD0 && headerBytes[1] == 0xCF && headerBytes[2] == 0x11 && headerBytes[3] == 0xE0))
            {
                isExcel = true;
            }
        }

        if (isExcel)
        {
            try
            {
                using var excelReader = ExcelReaderFactory.CreateReader(ms);
                int rowNum = 0;
                int guestNameIdx = -1, commentIdx = -1, ratingIdx = -1, dateIdx = -1, sourceIdx = -1, langIdx = -1;

                while (excelReader.Read())
                {
                    rowNum++;
                    if (rowNum == 1)
                    {
                        for (int i = 0; i < excelReader.FieldCount; i++)
                        {
                            var header = excelReader.GetValue(i)?.ToString()?.ToLower().Replace("_", "").Replace(" ", "") ?? "";
                            if (header.Contains("guest") || header.Contains("misafir") || header.Contains("name") || header.Contains("ad"))
                                guestNameIdx = i;
                            else if (header.Contains("comment") || header.Contains("yorum"))
                                commentIdx = i;
                            else if (header.Contains("rating") || header.Contains("puan"))
                                ratingIdx = i;
                            else if (header.Contains("date") || header.Contains("tarih"))
                                dateIdx = i;
                            else if (header.Contains("source") || header.Contains("kaynak"))
                                sourceIdx = i;
                            else if (header.Contains("lang") || header.Contains("dil"))
                                langIdx = i;
                        }

                        if (guestNameIdx == -1 && excelReader.FieldCount > 0) guestNameIdx = 0;
                        if (commentIdx == -1 && excelReader.FieldCount > 1) commentIdx = 1;
                        if (ratingIdx == -1 && excelReader.FieldCount > 2) ratingIdx = 2;
                        if (dateIdx == -1 && excelReader.FieldCount > 3) dateIdx = 3;
                        if (sourceIdx == -1 && excelReader.FieldCount > 4) sourceIdx = 4;
                        if (langIdx == -1 && excelReader.FieldCount > 5) langIdx = 5;

                        continue;
                    }

                    var record = new CsvReviewRecord
                    {
                        GuestName = guestNameIdx >= 0 && guestNameIdx < excelReader.FieldCount ? excelReader.GetValue(guestNameIdx)?.ToString() ?? "" : "",
                        Comment = commentIdx >= 0 && commentIdx < excelReader.FieldCount ? excelReader.GetValue(commentIdx)?.ToString() ?? "" : "",
                        Rating = ratingIdx >= 0 && ratingIdx < excelReader.FieldCount ? excelReader.GetValue(ratingIdx)?.ToString() ?? "" : "",
                        ReviewDate = dateIdx >= 0 && dateIdx < excelReader.FieldCount ? excelReader.GetValue(dateIdx)?.ToString() ?? "" : "",
                        Source = sourceIdx >= 0 && sourceIdx < excelReader.FieldCount ? excelReader.GetValue(sourceIdx)?.ToString() ?? "" : "",
                        Language = langIdx >= 0 && langIdx < excelReader.FieldCount ? excelReader.GetValue(langIdx)?.ToString() ?? "" : ""
                    };

                    recordsList.Add(record);
                }
            }
            catch (Exception ex)
            {
                return new ImportResultDto(0, [$"Excel Dosyası Okuma Hatası: {ex.Message}"]);
            }
        }
        else
        {
            // Plain text CSV processing
            string delimiter = ",";
            using (var lineReader = new StreamReader(ms, Encoding.UTF8, detectEncodingFromByteOrderMarks: true, bufferSize: 1024, leaveOpen: true))
            {
                var firstLine = await lineReader.ReadLineAsync(cancellationToken);
                if (!string.IsNullOrEmpty(firstLine))
                {
                    if (firstLine.Contains(';'))
                    {
                        delimiter = ";";
                    }
                    else if (firstLine.Contains('\t'))
                    {
                        delimiter = "\t";
                    }
                }
            }

            ms.Position = 0;

            var config = new CsvConfiguration(CultureInfo.InvariantCulture)
            {
                Delimiter = delimiter,
                PrepareHeaderForMatch = args => args.Header.ToLower().Replace("_", "").Replace(" ", ""),
                HeaderValidated = null,
                MissingFieldFound = null
            };

            using var reader = new StreamReader(ms, Encoding.UTF8);
            using var csv = new CsvReader(reader, config);

            try
            {
                await foreach (var r in csv.GetRecordsAsync<CsvReviewRecord>(cancellationToken))
                {
                    recordsList.Add(r);
                }
            }
            catch (Exception ex)
            {
                return new ImportResultDto(0, [$"CSV Dosyası Okuma Hatası: {ex.Message}"]);
            }
        }

        int lineNumber = 1; // 1 is header
        int successCount = 0;
        var errors = new List<string>();

        foreach (var r in recordsList)
        {
            lineNumber++;
            var rowErrors = new List<string>();

            var guestName = string.IsNullOrWhiteSpace(r.GuestName) ? "Misafir" : r.GuestName.Trim();
            var comment = r.Comment?.Trim() ?? string.Empty;

            if (string.IsNullOrWhiteSpace(comment) || comment.Length < 10)
            {
                rowErrors.Add("Yorum boş olamaz ve en az 10 karakter olmalıdır.");
            }

            int ratingValue = 3;
            if (!string.IsNullOrWhiteSpace(r.Rating))
            {
                if (!int.TryParse(r.Rating.Trim(), out ratingValue) || ratingValue < 1 || ratingValue > 5)
                {
                    if (double.TryParse(r.Rating.Trim(), CultureInfo.InvariantCulture, out var dRating))
                    {
                        ratingValue = (int)Math.Clamp(Math.Round(dRating), 1, 5);
                    }
                    else
                    {
                        ratingValue = 3;
                    }
                }
            }

            string language = string.IsNullOrWhiteSpace(r.Language) ? "tr" : r.Language.Trim();

            ReviewSource sourceValue = ReviewSource.Import;
            if (!string.IsNullOrWhiteSpace(r.Source))
            {
                if (Enum.TryParse<ReviewSource>(r.Source.Trim(), true, out var parsedSource))
                {
                    sourceValue = parsedSource;
                }
            }

            DateTime reviewDateValue = DateTime.UtcNow;
            if (!string.IsNullOrWhiteSpace(r.ReviewDate))
            {
                if (DateTime.TryParse(r.ReviewDate.Trim(), CultureInfo.InvariantCulture, DateTimeStyles.None, out var parsedDate) ||
                    DateTime.TryParse(r.ReviewDate.Trim(), out parsedDate))
                {
                    reviewDateValue = DateTime.SpecifyKind(parsedDate, DateTimeKind.Utc);
                }
            }

            if (rowErrors.Any())
            {
                errors.Add($"{lineNumber}. satır: {string.Join(" | ", rowErrors)}");
                continue;
            }

            try
            {
                var createCommand = new CreateReviewCommand(
                    guestName,
                    comment,
                    ratingValue,
                    language,
                    sourceValue,
                    reviewDateValue,
                    targetHotelId
                );

                await _mediator.Send(createCommand, cancellationToken);
                successCount++;
            }
            catch (Exception ex)
            {
                errors.Add($"{lineNumber}. satır (Kaydetme Hatası): {ex.Message}");
            }
        }

        return new ImportResultDto(successCount, errors);
    }
}
