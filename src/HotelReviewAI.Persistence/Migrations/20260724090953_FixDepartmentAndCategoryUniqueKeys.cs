using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class FixDepartmentAndCategoryUniqueKeys : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_ReviewCategories_DepartmentId",
                table: "ReviewCategories");

            migrationBuilder.DropIndex(
                name: "IX_ReviewCategories_Key",
                table: "ReviewCategories");

            migrationBuilder.DropIndex(
                name: "IX_Departments_HotelId",
                table: "Departments");

            migrationBuilder.DropIndex(
                name: "IX_Departments_Key",
                table: "Departments");

            migrationBuilder.CreateIndex(
                name: "IX_ReviewCategories_DepartmentId_Key",
                table: "ReviewCategories",
                columns: new[] { "DepartmentId", "Key" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Departments_HotelId_Key",
                table: "Departments",
                columns: new[] { "HotelId", "Key" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_ReviewCategories_DepartmentId_Key",
                table: "ReviewCategories");

            migrationBuilder.DropIndex(
                name: "IX_Departments_HotelId_Key",
                table: "Departments");

            migrationBuilder.CreateIndex(
                name: "IX_ReviewCategories_DepartmentId",
                table: "ReviewCategories",
                column: "DepartmentId");

            migrationBuilder.CreateIndex(
                name: "IX_ReviewCategories_Key",
                table: "ReviewCategories",
                column: "Key",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Departments_HotelId",
                table: "Departments",
                column: "HotelId");

            migrationBuilder.CreateIndex(
                name: "IX_Departments_Key",
                table: "Departments",
                column: "Key",
                unique: true);
        }
    }
}
