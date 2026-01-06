# Actual Budget to Google Sheets Sync

Automatically sync your budget data from [Actual Budget](https://actualbudget.org/) to Google Sheets. This tool creates tabs in a Google Sheet that display your budget information for the current and previous month, with optional transaction export.

## Features

- 🔄 Automatic synchronization of budget data from Actual Budget to Google Sheets
- 📊 Two tabs: "Previous Month Budget" and "Current Month Budget"
- 💳 **Optional**: Export transactions to a separate "Transactions" tab
- 📈 Shows budgeted amount, actual spend, and running balance for each category
- 🗂️ Organized by category groups with alphabetical sorting
- 📅 Includes monthly totals
- ⏰ Configurable scheduling via GitHub Actions or cron
- 🔐 Secure authentication using environment variables

## Prerequisites

Before you begin, you'll need:

1. **Actual Budget Server**: A running instance of Actual Budget with API access
   - Self-hosted Actual Budget server or a hosted solution
   - Server URL, password, and budget file name
   - Optional: Encryption password if your budget is encrypted

2. **Google Cloud Project**: Set up for Google Sheets API access
   - A Google Cloud project with Sheets API enabled
   - A service account with credentials
   - The service account email granted edit access to your Google Sheet

## Setup Instructions

### 1. Google Cloud Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click "Enable"
4. Create a service account:
   - Navigate to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "Service Account"
   - Fill in the service account details and click "Create"
   - Skip granting roles (click "Continue" then "Done")
5. Create and download credentials:
   - Click on the created service account
   - Go to the "Keys" tab
   - Click "Add Key" > "Create New Key"
   - Choose "JSON" format and click "Create"
   - Save the downloaded JSON file securely

### 2. Google Sheets Setup

1. Create a new Google Sheet or use an existing one
2. Note the Sheet ID from the URL:
   - URL format: `https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit`
3. Share the sheet with your service account:
   - Click the "Share" button in the top-right
   - Add the service account email (found in the JSON credentials file)
   - Grant "Editor" access

### 3. Local Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/latetedemelon/actual-to-gsheets.git
   cd actual-to-gsheets
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file based on `.env.example`:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` and fill in your configuration:
   ```env
   ACTUAL_SERVER_URL=https://your-actual-server.com
   ACTUAL_PASSWORD=your-actual-password
   ACTUAL_FILE=My-Budget-File
   ACTUAL_ENCRYPTION_PASSWORD=your-encryption-password-if-needed
   GOOGLE_SHEET_ID=your-google-sheet-id
   GOOGLE_CREDENTIALS_FILE=path/to/service-account-credentials.json
   
   # Optional: Export transactions to a separate sheet
   EXPORT_TRANSACTIONS=false
   TRANSACTIONS_DATE_RANGE=current_month
   ```

### 4. GitHub Actions Setup (Recommended for Automation)

1. Fork or push this repository to your GitHub account

2. Add the following secrets to your repository:
   - Go to "Settings" > "Secrets and variables" > "Actions"
   - Click "New repository secret" for each:
     - `ACTUAL_SERVER_URL`: Your Actual Budget server URL
     - `ACTUAL_PASSWORD`: Your Actual Budget password
     - `ACTUAL_FILE`: Your budget file name
     - `ACTUAL_ENCRYPTION_PASSWORD`: Your encryption password (if applicable)
     - `GOOGLE_SHEET_ID`: Your Google Sheet ID
     - `GOOGLE_CREDENTIALS_JSON`: Contents of your service account JSON file
     - `EXPORT_TRANSACTIONS` (Optional): Set to `true` to export transactions
     - `TRANSACTIONS_DATE_RANGE` (Optional): `current_month`, `previous_month`, or `both_months`

3. The workflow will run automatically daily at 6 AM UTC, or you can trigger it manually from the Actions tab

## Usage

### Manual Execution

Run the script manually:

```bash
python actual_to_gsheets.py
```

### Scheduled Execution with Cron

Add to your crontab to run daily at 6 AM:

```bash
0 6 * * * cd /path/to/actual-to-gsheets && /usr/bin/python3 actual_to_gsheets.py
```

### GitHub Actions (Automated)

The included workflow automatically runs daily. You can also trigger it manually:

1. Go to the "Actions" tab in your GitHub repository
2. Select "Sync Actual Budget to Google Sheets"
3. Click "Run workflow"

## Output Format

The script creates or updates two tabs in your Google Sheet:

### Previous Month Budget
```
January 2024
|-------|----------|----------|--------------|-----------------|
| Group | Category | Budgeted | Actual Spend | Running Balance |
|-------|----------|----------|--------------|-----------------|
| Bills | Electric | $150.00  | $145.32      | $4.68           |
| Bills | Water    | $50.00   | $48.20       | $1.80           |
| Food  | Groceries| $500.00  | $523.45      | -$23.45         |
| Food  | Dining   | $200.00  | $189.67      | $10.33          |
|-------|----------|----------|--------------|-----------------|
| TOTAL |          | $900.00  | $906.64      | -$6.64          |
```

### Current Month Budget
Same format as above, but with current month's data.

### Transactions (Optional)
When `EXPORT_TRANSACTIONS=true`, a third tab is created with detailed transaction data:

```
Transactions - January 2024
|------------|----------|-------------|----------|-------------|----------|---------|
| Date       | Account  | Payee       | Category | Description | Amount   | Cleared |
|------------|----------|-------------|----------|-------------|----------|---------|
| 2024-01-15 | Checking | Amazon      | Shopping | Books       | -$45.99  | ✓       |
| 2024-01-14 | Checking | Starbucks   | Dining   | Coffee      | -$5.75   | ✓       |
| 2024-01-13 | Checking | Salary Inc. | Income   | Paycheck    | $3000.00 |         |
|------------|----------|-------------|----------|-------------|----------|---------|
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ACTUAL_SERVER_URL` | Yes | URL of your Actual Budget server |
| `ACTUAL_PASSWORD` | Yes | Password for Actual Budget |
| `ACTUAL_FILE` | Yes | Name of your budget file |
| `ACTUAL_ENCRYPTION_PASSWORD` | No | Encryption password if budget is encrypted |
| `GOOGLE_SHEET_ID` | Yes | ID of your Google Sheet |
| `GOOGLE_CREDENTIALS_FILE` | Conditional* | Path to service account JSON credentials file |
| `GOOGLE_CREDENTIALS_JSON` | Conditional* | Service account JSON credentials as a string |
| `EXPORT_TRANSACTIONS` | No | Set to `true` to export transactions (default: `false`) |
| `TRANSACTIONS_DATE_RANGE` | No | Date range for transactions: `current_month`, `previous_month`, or `both_months` (default: `current_month`) |

\* Either `GOOGLE_CREDENTIALS_FILE` or `GOOGLE_CREDENTIALS_JSON` must be provided. Use `GOOGLE_CREDENTIALS_FILE` for local execution and `GOOGLE_CREDENTIALS_JSON` for CI/CD environments like GitHub Actions.

### Schedule Configuration

To change the schedule, edit `.github/workflows/sync.yml`:

```yaml
schedule:
  - cron: '0 6 * * *'  # Daily at 6 AM UTC
```

Common cron schedules:
- `0 */6 * * *` - Every 6 hours
- `0 0 * * 1` - Weekly on Monday at midnight
- `0 0 1 * *` - Monthly on the 1st at midnight

## Troubleshooting

### Authentication Errors

- **Actual Budget**: Verify your server URL, password, and file name are correct
- **Google Sheets**: Ensure the service account has edit access to the sheet

### Missing Data

- Check that your budget has categories and budgets set up for the current/previous month
- Verify transactions are categorized properly in Actual Budget

### Dependencies

If you encounter import errors, ensure all dependencies are installed:

```bash
pip install -r requirements.txt --upgrade
```

## Development

### Running Tests

Currently, this project doesn't include automated tests. To verify functionality:

1. Set up your `.env` file with test credentials
2. Run the script: `python actual_to_gsheets.py`
3. Check the Google Sheet for correct data

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Actual Budget](https://actualbudget.org/) - Open-source personal finance tool
- [actualpy](https://github.com/bvanelli/actualpy) - Python library for Actual Budget
- [gspread](https://github.com/burnash/gspread) - Python library for Google Sheets

## Support

For issues, questions, or suggestions:
- Open an issue on [GitHub](https://github.com/latetedemelon/actual-to-gsheets/issues)
- Check the [Actual Budget documentation](https://actualbudget.org/docs/)
- Review the [Google Sheets API documentation](https://developers.google.com/sheets/api)
