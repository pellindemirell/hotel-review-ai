using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddAnalysisJobIndexes : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateIndex(
                name: "IX_AnalysisJobs_ReviewId",
                table: "AnalysisJobs",
                column: "ReviewId");

            migrationBuilder.CreateIndex(
                name: "IX_AnalysisJobs_Status_CreatedAt",
                table: "AnalysisJobs",
                columns: new[] { "Status", "CreatedAt" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_AnalysisJobs_ReviewId",
                table: "AnalysisJobs");

            migrationBuilder.DropIndex(
                name: "IX_AnalysisJobs_Status_CreatedAt",
                table: "AnalysisJobs");
        }
    }
}
