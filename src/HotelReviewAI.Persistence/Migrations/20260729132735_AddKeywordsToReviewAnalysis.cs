using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddKeywordsToReviewAnalysis : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("ALTER TABLE \"ReviewAnalyses\" ADD COLUMN IF NOT EXISTS \"Keywords\" jsonb NOT NULL DEFAULT '[]';");
            migrationBuilder.Sql("ALTER TABLE \"ReviewAnalyses\" ADD COLUMN IF NOT EXISTS \"Summary\" text NULL;");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Keywords",
                table: "ReviewAnalyses");

            migrationBuilder.DropColumn(
                name: "Summary",
                table: "ReviewAnalyses");
        }
    }
}
