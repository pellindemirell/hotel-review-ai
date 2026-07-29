using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddUserDetailView : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // FK'yı SetNull olacak şekilde güncelle (Hotel silinince user null olsun)
            migrationBuilder.DropForeignKey(
                name: "FK_Users_Hotels_HotelId",
                table: "Users");

            migrationBuilder.AddForeignKey(
                name: "FK_Users_Hotels_HotelId",
                table: "Users",
                column: "HotelId",
                principalTable: "Hotels",
                principalColumn: "Id",
                onDelete: ReferentialAction.SetNull);

            // Kullanıcı detay görünümü: Users + Hotels + Departments join
            migrationBuilder.Sql("""
                CREATE OR REPLACE VIEW public.vw_users_detail AS
                SELECT
                    u."Id"             AS "UserId",
                    u."FullName",
                    u."Email",
                    u."Role",
                    u."HotelId",
                    h."Name"           AS "HotelName",
                    h."Code"           AS "HotelCode",
                    u."DepartmentId",
                    d."Name"           AS "DepartmentName",
                    d."Key"            AS "DepartmentKey",
                    u."CreatedAt",
                    u."UpdatedAt"
                FROM public."Users" u
                LEFT JOIN public."Hotels"      h ON h."Id" = u."HotelId"
                LEFT JOIN public."Departments" d ON d."Id" = u."DepartmentId";
                """);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("DROP VIEW IF EXISTS public.vw_users_detail;");

            migrationBuilder.DropForeignKey(
                name: "FK_Users_Hotels_HotelId",
                table: "Users");

            migrationBuilder.AddForeignKey(
                name: "FK_Users_Hotels_HotelId",
                table: "Users",
                column: "HotelId",
                principalTable: "Hotels",
                principalColumn: "Id");
        }
    }
}
