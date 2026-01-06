#!/usr/bin/env python3
"""
Sync budget data from Actual Budget to Google Sheets.

This script connects to an Actual Budget server, extracts budget data for the current
and previous month, and updates two tabs in a Google Sheet with the budget information.
"""

import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from dateutil.relativedelta import relativedelta

from actual import Actual
from actual.queries import (
    get_accounts,
    get_budgets,
    get_categories,
    get_category_groups,
    get_transactions,
)


def get_month_dates(offset_months: int = 0) -> Tuple[datetime, datetime, str]:
    """
    Get the start and end dates for a month.
    
    Args:
        offset_months: Number of months to offset from current month (negative for past)
        
    Returns:
        Tuple of (start_date, end_date, month_label)
    """
    today = datetime.now()
    target_month = today + relativedelta(months=offset_months)
    
    start_date = target_month.replace(day=1)
    end_date = (start_date + relativedelta(months=1)) - timedelta(days=1)
    month_label = start_date.strftime("%B %Y")
    
    return start_date, end_date, month_label


def cents_to_decimal(cents: int) -> Decimal:
    """Convert cents (stored as integers in Actual) to decimal dollars."""
    return Decimal(cents) / Decimal(100)


def get_budget_data(
    session,
    month_start: datetime,
    month_end: datetime
) -> List[Dict]:
    """
    Extract budget data for a specific month from Actual Budget.
    
    Args:
        session: Actual database session
        month_start: Start date of the month
        month_end: End date of the month
        
    Returns:
        List of dictionaries containing budget data per category
    """
    # Get all category groups
    category_groups = get_category_groups(session)
    print(f"Found {len(category_groups)} category groups")
    
    # Get all budgets for the month
    budgets = get_budgets(session, month_start.date())
    
    # Create a mapping of category_id to budget data
    budget_map = {b.category_id: b for b in budgets}
    
    # Get all categories once (not in the loop)
    all_categories = get_categories(session, include_deleted=False)
    print(f"Found {len(all_categories)} total categories")
    
    # Prepare data list
    data = []
    
    # Process each category group
    for group in category_groups:
        if group.hidden or group.tombstone:
            continue
            
        # Filter categories for this group
        # Note: cat.cat_group is the foreign key field containing the group ID
        categories = [cat for cat in all_categories
                     if cat.cat_group == group.id and not cat.hidden and not cat.tombstone]
        
        if categories:
            print(f"Group '{group.name}': {len(categories)} categories")
        
        # Sort categories alphabetically
        categories.sort(key=lambda x: x.name or "")
        
        for category in categories:
            # Get budget for this category
            budget = budget_map.get(category.id)
            budgeted = cents_to_decimal(budget.amount if budget and budget.amount is not None else 0)
            
            # Calculate actual spend from transactions
            transactions = get_transactions(
                session,
                start_date=month_start.date(),
                end_date=month_end.date(),
                category=category
            )
            
            # Sum up transactions (negative for expenses, positive for income)
            # Exclude parent split transactions to avoid double-counting
            # Note: is_parent may not be set on older transaction records, 
            # so we use getattr with False as default
            actual_spend = sum(
                cents_to_decimal(t.amount) for t in transactions
                if not getattr(t, 'is_parent', False)
            )
            
            # For expense categories (not income), invert the sign for display
            # Actual Budget stores expenses as negative numbers (e.g., -$50 for grocery spend)
            # but we want to show them as positive in the sheet for better readability
            if not group.is_income:
                actual_spend = -actual_spend
            
            # Calculate running balance (budgeted - actual_spend for expenses)
            # For income categories: actual - budgeted (we want to see if we earned more than expected)
            # For expense categories: budgeted - actual (we want to see if we have budget left)
            if group.is_income:
                running_balance = actual_spend - budgeted
            else:
                running_balance = budgeted - actual_spend
            
            data.append({
                "group": group.name,
                "category": category.name,
                "budgeted": float(budgeted),
                "actual_spend": float(actual_spend),
                "running_balance": float(running_balance),
                "is_income": bool(group.is_income),
            })
    
    # Sort by group name, then by category name
    data.sort(key=lambda x: (x["group"], x["category"]))
    
    print(f"Returning {len(data)} budget entries")
    
    return data


def get_transaction_data(
    session,
    start_date: datetime,
    end_date: datetime
) -> List[Dict]:
    """
    Extract transaction data from Actual Budget.
    
    Args:
        session: Actual database session
        start_date: Start date for transactions
        end_date: End date for transactions
        
    Returns:
        List of dictionaries containing transaction data
    """
    # Get all transactions for the date range
    # is_parent=False ensures we get individual transactions and splits, not parent split transactions
    transactions = get_transactions(
        session,
        start_date=start_date.date(),
        end_date=end_date.date(),
        is_parent=False
    )
    
    print(f"Found {len(transactions)} transactions")
    
    # Prepare data list
    data = []
    
    for transaction in transactions:
        # Skip parent transactions and tombstoned (deleted) transactions
        if getattr(transaction, 'is_parent', False) or transaction.tombstone:
            continue
        
        # Get account name
        account_name = transaction.account.name if transaction.account else "Unknown"
        
        # Get category name
        category_name = transaction.category.name if transaction.category else "Uncategorized"
        
        # Get payee name
        payee_name = transaction.payee.name if transaction.payee else ""
        
        # Convert amount from cents to dollars
        amount = cents_to_decimal(transaction.amount)
        
        # Convert date (stored as integer YYYYMMDD) to readable format
        date_str = str(transaction.date)
        try:
            if len(date_str) == 8:
                formatted_date = f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                formatted_date = date_str
        except (ValueError, IndexError):
            formatted_date = date_str
        
        data.append({
            "date": formatted_date,
            "account": account_name,
            "payee": payee_name,
            "category": category_name,
            "description": transaction.notes or "",
            "amount": float(amount),
            "cleared": bool(transaction.cleared),
        })
    
    # Sort by date (descending - most recent first)
    data.sort(key=lambda x: x["date"], reverse=True)
    
    print(f"Returning {len(data)} transaction entries")
    
    return data


def get_account_balances(session) -> List[Dict]:
    """
    Extract account balances from Actual Budget.
    
    Args:
        session: Actual database session
        
    Returns:
        List of dictionaries containing account balance data
    """
    # Get all accounts (open and closed, on and off budget)
    accounts = get_accounts(session, include_deleted=False)
    
    print(f"Found {len(accounts)} accounts")
    
    # Prepare data list
    data = []
    
    for account in accounts:
        # Skip tombstoned (deleted) accounts
        if account.tombstone:
            continue
        
        # Get account balance (stored in cents)
        balance = cents_to_decimal(account.balance_current if account.balance_current is not None else 0)
        
        # Determine account type
        account_type = "Off Budget" if account.offbudget else "On Budget"
        account_status = "Closed" if account.closed else "Open"
        
        data.append({
            "name": account.name or "Unknown",
            "balance": float(balance),
            "type": account_type,
            "status": account_status,
        })
    
    # Sort by type (on budget first), then status (open first), then name
    data.sort(key=lambda x: (x["type"], x["status"] == "Closed", x["name"]))
    
    print(f"Returning {len(data)} account entries")
    
    return data


def format_currency(value: float) -> str:
    """Format a number as currency."""
    return f"${value:,.2f}"


def get_or_create_worksheet(spreadsheet, title: str, rows: int = 100, cols: int = 5):
    """
    Get an existing worksheet or create it if it doesn't exist.
    
    Args:
        spreadsheet: gspread spreadsheet object
        title: Title of the worksheet
        rows: Number of rows for new worksheet
        cols: Number of columns for new worksheet
        
    Returns:
        gspread worksheet object
    """
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def update_sheet_tab(
    worksheet,
    month_label: str,
    data: List[Dict]
) -> None:
    """
    Update a Google Sheets tab with budget data.
    
    Args:
        worksheet: gspread worksheet object
        month_label: Label for the month (e.g., "January 2024")
        data: List of budget data dictionaries
    """
    # Clear the sheet
    worksheet.clear()
    
    # Prepare header
    headers = ["Group", "Category", "Budgeted", "Actual Spend", "Running Balance"]
    
    # Prepare rows
    rows = [[month_label, "", "", "", ""]]  # Month label row
    rows.append(headers)
    
    # Add data rows
    for item in data:
        rows.append([
            item["group"],
            item["category"],
            format_currency(item["budgeted"]),
            format_currency(item["actual_spend"]),
            format_currency(item["running_balance"]),
        ])
    
    # Calculate totals
    total_budgeted = sum(item["budgeted"] for item in data if not item["is_income"])
    total_actual = sum(item["actual_spend"] for item in data if not item["is_income"])
    total_balance = sum(item["running_balance"] for item in data if not item["is_income"])
    
    # Add totals row
    rows.append([
        "TOTAL",
        "",
        format_currency(total_budgeted),
        format_currency(total_actual),
        format_currency(total_balance),
    ])
    
    # Update the sheet
    worksheet.update(rows, value_input_option="USER_ENTERED")
    
    # Format the sheet
    # Bold header rows
    worksheet.format("A1:E2", {
        "textFormat": {"bold": True},
        "horizontalAlignment": "CENTER",
    })
    
    # Bold totals row
    total_row = len(rows)
    worksheet.format(f"A{total_row}:E{total_row}", {
        "textFormat": {"bold": True},
    })
    
    # Auto-resize columns
    worksheet.columns_auto_resize(0, 4)


def update_transaction_sheet(
    worksheet,
    title: str,
    data: List[Dict]
) -> None:
    """
    Update a Google Sheets tab with transaction data.
    
    Args:
        worksheet: gspread worksheet object
        title: Title for the sheet (e.g., "Transactions")
        data: List of transaction data dictionaries
    """
    # Clear the sheet
    worksheet.clear()
    
    # Prepare header
    headers = ["Date", "Account", "Payee", "Category", "Description", "Amount", "Cleared"]
    
    # Prepare rows
    rows = [[title, "", "", "", "", "", ""]]  # Title row
    rows.append(headers)
    
    # Add data rows
    for item in data:
        rows.append([
            item["date"],
            item["account"],
            item["payee"],
            item["category"],
            item["description"],
            format_currency(item["amount"]),
            "✓" if item["cleared"] else "",
        ])
    
    # Update the sheet
    worksheet.update(rows, value_input_option="USER_ENTERED")
    
    # Format the sheet
    # Bold header rows
    worksheet.format("A1:G2", {
        "textFormat": {"bold": True},
        "horizontalAlignment": "CENTER",
    })
    
    # Auto-resize columns
    worksheet.columns_auto_resize(0, 6)


def update_account_balances_sheet(
    worksheet,
    data: List[Dict]
) -> None:
    """
    Update a Google Sheets tab with account balance data.
    
    Args:
        worksheet: gspread worksheet object
        data: List of account balance data dictionaries
    """
    # Clear the sheet
    worksheet.clear()
    
    # Prepare header
    headers = ["Account Name", "Balance", "Type", "Status"]
    
    # Prepare rows
    rows = [["Account Balances", "", "", ""]]  # Title row
    rows.append(headers)
    
    # Add data rows
    for item in data:
        rows.append([
            item["name"],
            format_currency(item["balance"]),
            item["type"],
            item["status"],
        ])
    
    # Calculate totals
    total_on_budget = sum(item["balance"] for item in data if item["type"] == "On Budget" and item["status"] == "Open")
    total_off_budget = sum(item["balance"] for item in data if item["type"] == "Off Budget" and item["status"] == "Open")
    total_all = sum(item["balance"] for item in data if item["status"] == "Open")
    
    # Add blank row and totals
    rows.append(["", "", "", ""])
    rows.append(["TOTAL (On Budget)", format_currency(total_on_budget), "", ""])
    rows.append(["TOTAL (Off Budget)", format_currency(total_off_budget), "", ""])
    rows.append(["TOTAL (All Open Accounts)", format_currency(total_all), "", ""])
    
    # Update the sheet
    worksheet.update(rows, value_input_option="USER_ENTERED")
    
    # Format the sheet
    # Bold header rows
    worksheet.format("A1:D2", {
        "textFormat": {"bold": True},
        "horizontalAlignment": "CENTER",
    })
    
    # Bold totals rows
    total_start_row = len(rows) - 2
    total_end_row = len(rows)
    worksheet.format(f"A{total_start_row}:D{total_end_row}", {
        "textFormat": {"bold": True},
    })
    
    # Auto-resize columns
    worksheet.columns_auto_resize(0, 3)


def main():
    """Main function to sync budget data from Actual to Google Sheets."""
    # Load environment variables from .env file (for local development)
    load_dotenv()
    
    # Load environment variables
    actual_server_url = os.getenv("ACTUAL_SERVER_URL")
    actual_password = os.getenv("ACTUAL_PASSWORD")
    actual_file = os.getenv("ACTUAL_FILE")
    actual_encryption_password = os.getenv("ACTUAL_ENCRYPTION_PASSWORD")
    google_sheet_id = os.getenv("GOOGLE_SHEET_ID")
    google_credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
    google_credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    export_transactions = os.getenv("EXPORT_TRANSACTIONS", "false").lower() in ("true", "1", "yes")
    transactions_date_range = os.getenv("TRANSACTIONS_DATE_RANGE", "current_month")
    
    # Validate required environment variables
    required_vars = [
        ("ACTUAL_SERVER_URL", actual_server_url),
        ("ACTUAL_PASSWORD", actual_password),
        ("ACTUAL_FILE", actual_file),
        ("GOOGLE_SHEET_ID", google_sheet_id),
    ]
    
    # Either credentials file or credentials JSON must be provided
    if not google_credentials_file and not google_credentials_json:
        print("Error: Either GOOGLE_CREDENTIALS_FILE or GOOGLE_CREDENTIALS_JSON must be set")
        sys.exit(1)
    
    missing_vars = [var_name for var_name, var_value in required_vars if not var_value]
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    
    print("Starting Actual Budget to Google Sheets sync...")
    
    try:
        # Connect to Actual Budget
        print(f"Connecting to Actual Budget at {actual_server_url}...")
        with Actual(
            base_url=actual_server_url,
            password=actual_password,
            file=actual_file,
            encryption_password=actual_encryption_password,
        ) as actual:
            # Download the budget file
            print("Downloading budget file...")
            actual.download_budget()
            
            # Get dates for current and previous month
            current_start, current_end, current_label = get_month_dates(0)
            previous_start, previous_end, previous_label = get_month_dates(-1)
            
            print(f"Extracting data for {previous_label}...")
            previous_month_data = get_budget_data(
                actual.session,
                previous_start,
                previous_end
            )
            
            print(f"Extracting data for {current_label}...")
            current_month_data = get_budget_data(
                actual.session,
                current_start,
                current_end
            )
            
            # Extract transaction data if enabled
            transaction_data = None
            if export_transactions:
                if transactions_date_range == "current_month":
                    print(f"Extracting transactions for {current_label}...")
                    transaction_data = get_transaction_data(
                        actual.session,
                        current_start,
                        current_end
                    )
                    transaction_title = f"Transactions - {current_label}"
                elif transactions_date_range == "previous_month":
                    print(f"Extracting transactions for {previous_label}...")
                    transaction_data = get_transaction_data(
                        actual.session,
                        previous_start,
                        previous_end
                    )
                    transaction_title = f"Transactions - {previous_label}"
                elif transactions_date_range == "both_months":
                    print(f"Extracting transactions for {previous_label} and {current_label}...")
                    # Combine both months
                    transaction_data = get_transaction_data(
                        actual.session,
                        previous_start,
                        current_end
                    )
                    transaction_title = f"Transactions - {previous_label} to {current_label}"
                else:
                    print(f"Warning: Unknown TRANSACTIONS_DATE_RANGE value '{transactions_date_range}'. Using 'current_month'.")
                    transaction_data = get_transaction_data(
                        actual.session,
                        current_start,
                        current_end
                    )
                    transaction_title = f"Transactions - {current_label}"
            
            # Extract account balances
            print("Extracting account balances...")
            account_balances = get_account_balances(actual.session)
        
        # Connect to Google Sheets
        print("Connecting to Google Sheets...")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        
        # Load credentials from file or JSON string
        if google_credentials_json:
            credentials_info = json.loads(google_credentials_json)
            credentials = Credentials.from_service_account_info(
                credentials_info,
                scopes=scopes
            )
        else:
            credentials = Credentials.from_service_account_file(
                google_credentials_file,
                scopes=scopes
            )
        
        client = gspread.authorize(credentials)
        
        # Open the spreadsheet
        spreadsheet = client.open_by_key(google_sheet_id)
        
        # Update Previous Month Budget tab
        print(f"Updating 'Previous Month Budget' tab with {previous_label} data...")
        previous_worksheet = get_or_create_worksheet(spreadsheet, "Previous Month Budget")
        update_sheet_tab(previous_worksheet, previous_label, previous_month_data)
        
        # Update Current Month Budget tab
        print(f"Updating 'Current Month Budget' tab with {current_label} data...")
        current_worksheet = get_or_create_worksheet(spreadsheet, "Current Month Budget")
        update_sheet_tab(current_worksheet, current_label, current_month_data)
        
        # Update Transactions tab if enabled
        if export_transactions and transaction_data:
            print(f"Updating 'Transactions' tab...")
            transactions_worksheet = get_or_create_worksheet(
                spreadsheet, 
                "Transactions",
                rows=max(1000, len(transaction_data) + 10),  # Ensure enough rows
                cols=7
            )
            update_transaction_sheet(transactions_worksheet, transaction_title, transaction_data)
        
        # Update Account Balances tab
        print(f"Updating 'Account Balances' tab...")
        account_balances_worksheet = get_or_create_worksheet(
            spreadsheet,
            "Account Balances",
            rows=max(100, len(account_balances) + 20),  # Ensure enough rows for accounts + totals
            cols=4
        )
        update_account_balances_sheet(account_balances_worksheet, account_balances)
        
        print("✓ Successfully synced budget data to Google Sheets!")
        
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
