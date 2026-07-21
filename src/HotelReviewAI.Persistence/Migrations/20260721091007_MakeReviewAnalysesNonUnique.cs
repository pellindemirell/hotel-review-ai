using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class MakeReviewAnalysesNonUnique : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses");

            migrationBuilder.CreateIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses",
                column: "ReviewId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses");

            migrationBuilder.CreateIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses",
                column: "ReviewId",
                unique: true);
        }
    }
}
