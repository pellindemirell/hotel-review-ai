namespace HotelReviewAI.Shared.Responses;

public class BaseResponse<T>
{
    public bool Success { get; set; }
    public string? Message { get; set; }
    public T? Data { get; set; }
    public List<string>? Errors { get; set; }

    public BaseResponse()
    {
    }

    public BaseResponse(bool success, string? message, T? data, List<string>? errors)
    {
        Success = success;
        Message = message;
        Data = data;
        Errors = errors;
    }

    public static BaseResponse<T> Ok(T data, string? message = null)
    {
        return new BaseResponse<T>(true, message, data, null);
    }

    public static BaseResponse<T> Fail(string error, string? message = null)
    {
        return new BaseResponse<T>(false, message, default, new List<string> { error });
    }

    public static BaseResponse<T> Fail(List<string> errors, string? message = null)
    {
        return new BaseResponse<T>(false, message, default, errors);
    }
}
