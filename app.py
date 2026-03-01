"""
AP Business Tools - Flask Backend
Connects your painting business tools to Google Sheets.
Supports local dev (credentials.json) and Render deployment (GOOGLE_CREDENTIALS env var).
"""

import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template
import gspread
from google.oauth2.service_account import Credentials

# ── Config ──────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1UQinb9lnBg-KpnZEjeqEQo1hSEkK2-cEGEIQS-dbmaI"

# Tab names
TAB_INQUIRIES = "Customer Inquiries"
TAB_ESTIMATES = "Detailed Estimates"
TAB_PIPELINE = "Job Pipeline Master"
TAB_JOBLIST = "Joblist"

LABOR_RATE = 560

# Joblist column order: A-U
JOBLIST_HEADERS = [
    "Job Address", "Interior/Exterior", "Status", "Priority",
    "Labor Days", "Action Needed", "Notes", "Start Date",
    "Completion Date", "Hood", "Customer Name", "Phone", "Email",
    "Date Added", "Last Updated", "Estimate Complete", "Estimator",
    "Estimated Value", "Days Since Est Sent", "Priority Sort", "Status Sort"
]

# ── App Setup ───────────────────────────────────────────────────────────────
app = Flask(__name__)


# ── Google Sheets Connection ────────────────────────────────────────────────
def get_sheet():
    """Authenticate and return the spreadsheet object.
    Uses GOOGLE_CREDENTIALS env var (Render) or falls back to credentials.json (local).
    """
    env_creds = os.environ.get("GOOGLE_CREDENTIALS")
    if env_creds:
        info = json.loads(env_creds)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)


def get_or_create_worksheet(spreadsheet, tab_name, headers):
    """Get a worksheet by name, creating it with headers if it doesn't exist."""
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


# ── Header Definitions ──────────────────────────────────────────────────────
INQUIRY_HEADERS = [
    "Timestamp", "Customer Name", "Phone", "Email", "Address",
    "Job Types", "Timeline", "Last Painted", "Previous Customer",
    "Notes", "Status"
]

ESTIMATE_HEADERS = [
    "Date", "Customer Name", "Job Address", "Estimator", "Job Type",
    "Total Hours", "Labor Days", "Estimated Value",
    "Prep Condition", "Furniture Level", "Ladder Requirement",
    "Colors/Products", "Equipment Needed", "Notes"
]

PIPELINE_HEADERS = [
    "Date Added", "Customer Name", "Address", "Phone", "Job Type",
    "Estimated Days", "Estimated Value", "Status", "Scheduled Date",
    "Estimator", "Notes"
]


# ── Joblist Writer ─────────────────────────────────────────────────────────
def append_to_joblist(spreadsheet, **kwargs):
    """Append a row to the Joblist tab. Matches the Job Tracker column order (A-U).
    Pass keyword args for any fields you want to set; others default to empty.
    """
    ws = get_or_create_worksheet(spreadsheet, TAB_JOBLIST, JOBLIST_HEADERS)
    today = datetime.now().strftime("%m/%d/%Y")

    labor_days = kwargs.get("labor_days", "")
    est_value = ""
    if labor_days and str(labor_days).strip():
        try:
            est_value = float(labor_days) * LABOR_RATE
        except (ValueError, TypeError):
            pass

    row = [
        kwargs.get("address", ""),           # A: Job Address
        kwargs.get("int_ext", ""),            # B: Interior/Exterior
        kwargs.get("status", ""),             # C: Status
        kwargs.get("priority", ""),           # D: Priority
        labor_days,                           # E: Labor Days
        kwargs.get("action", ""),             # F: Action Needed
        kwargs.get("notes", ""),              # G: Notes
        kwargs.get("start_date", ""),         # H: Start Date
        kwargs.get("completion_date", ""),    # I: Completion Date
        kwargs.get("hood", ""),               # J: Hood
        kwargs.get("customer_name", ""),      # K: Customer Name
        kwargs.get("phone", ""),              # L: Phone
        kwargs.get("email", ""),              # M: Email
        kwargs.get("date_added", today),      # N: Date Added
        kwargs.get("last_updated", today),    # O: Last Updated
        kwargs.get("est_complete", ""),       # P: Estimate Complete
        kwargs.get("estimator", ""),          # Q: Estimator
        est_value,                            # R: Estimated Value
        "",                                   # S: Days Since Est Sent (formula)
        "",                                   # T: Priority Sort (formula)
        "",                                   # U: Status Sort (formula)
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")


# ── Index Route ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── API: Customer Inquiries ─────────────────────────────────────────────────
@app.route("/api/inquiry", methods=["POST"])
def save_inquiry():
    try:
        data = request.json
        spreadsheet = get_sheet()
        ws = get_or_create_worksheet(spreadsheet, TAB_INQUIRIES, INQUIRY_HEADERS)

        row = [
            data.get("timestamp", datetime.now().isoformat()),
            data.get("customerName", ""),
            data.get("phone", ""),
            data.get("email", ""),
            data.get("address", ""),
            ", ".join(data.get("jobTypes", [])),
            data.get("timeline", ""),
            data.get("lastPainted", ""),
            data.get("previousCustomer", ""),
            data.get("notes", ""),
            data.get("status", "New"),
        ]

        ws.append_row(row, value_input_option="USER_ENTERED")

        # Also add to Joblist tab
        append_to_joblist(
            spreadsheet,
            address=data.get("address", ""),
            customer_name=data.get("customerName", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            status="Need Estimate",
            hood=data.get("hood", ""),
            notes=data.get("notes", ""),
            int_ext=", ".join(data.get("jobTypes", [])),
        )

        return jsonify({"success": True, "message": "Inquiry saved to Google Sheets"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── API: Customer Inquiries (GET) ──────────────────────────────────────
@app.route("/api/inquiries", methods=["GET"])
def get_inquiries():
    try:
        spreadsheet = get_sheet()
        ws = get_or_create_worksheet(spreadsheet, TAB_INQUIRIES, INQUIRY_HEADERS)
        records = ws.get_all_records()
        return jsonify({"success": True, "inquiries": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── API: Estimates ──────────────────────────────────────────────────────────
@app.route("/api/estimate", methods=["POST"])
def save_estimate():
    try:
        data = request.json
        spreadsheet = get_sheet()
        ws = get_or_create_worksheet(spreadsheet, TAB_ESTIMATES, ESTIMATE_HEADERS)

        conditions = data.get("conditions", {})
        row = [
            data.get("date", datetime.now().strftime("%m/%d/%Y")),
            data.get("customerName", ""),
            data.get("jobAddress", ""),
            data.get("estimator", ""),
            data.get("jobType", ""),
            data.get("totalHours", 0),
            data.get("laborDays", 0),
            data.get("totalValue", 0),
            conditions.get("prep", ""),
            conditions.get("furniture", ""),
            conditions.get("ladder", ""),
            data.get("colors", ""),
            ", ".join(data.get("tools", [])),
            data.get("notes", ""),
        ]

        ws.append_row(row, value_input_option="USER_ENTERED")

        # Also add to Joblist tab
        append_to_joblist(
            spreadsheet,
            address=data.get("jobAddress", ""),
            customer_name=data.get("customerName", ""),
            status="Estimate Sent",
            labor_days=data.get("laborDays", 0),
            int_ext=data.get("jobType", ""),
            start_date=data.get("startDate", ""),
            notes=data.get("notes", ""),
            estimator=data.get("estimator", ""),
            est_complete="Yes",
        )

        return jsonify({"success": True, "message": "Estimate saved to Google Sheets"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── API: Job Pipeline ──────────────────────────────────────────────────────
@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    try:
        spreadsheet = get_sheet()
        ws = get_or_create_worksheet(spreadsheet, TAB_PIPELINE, PIPELINE_HEADERS)

        records = ws.get_all_records()
        return jsonify({"success": True, "jobs": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/job", methods=["POST"])
def add_job():
    try:
        data = request.json
        spreadsheet = get_sheet()
        ws = get_or_create_worksheet(spreadsheet, TAB_PIPELINE, PIPELINE_HEADERS)

        row = [
            data.get("dateAdded", datetime.now().strftime("%m/%d/%Y")),
            data.get("customerName", ""),
            data.get("address", ""),
            data.get("phone", ""),
            data.get("jobType", ""),
            data.get("estimatedDays", ""),
            data.get("estimatedValue", ""),
            data.get("status", "New Lead"),
            data.get("scheduledDate", ""),
            data.get("estimator", ""),
            data.get("notes", ""),
        ]

        ws.append_row(row, value_input_option="USER_ENTERED")

        return jsonify({"success": True, "message": "Job added to pipeline"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/job/<int:row_index>", methods=["PUT"])
def update_job(row_index):
    """Update a job's status. row_index is 2-based (row 2 = first data row)."""
    try:
        data = request.json
        spreadsheet = get_sheet()
        ws = get_or_create_worksheet(spreadsheet, TAB_PIPELINE, PIPELINE_HEADERS)

        if "status" in data:
            ws.update_cell(row_index, 8, data["status"])
        if "scheduledDate" in data:
            ws.update_cell(row_index, 9, data["scheduledDate"])
        if "notes" in data:
            ws.update_cell(row_index, 11, data["notes"])

        return jsonify({"success": True, "message": "Job updated"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── API: Setup (one-time) ──────────────────────────────────────────────────
@app.route("/api/setup", methods=["POST"])
def setup_sheets():
    """One-time setup: create all three tabs with headers."""
    try:
        spreadsheet = get_sheet()
        get_or_create_worksheet(spreadsheet, TAB_INQUIRIES, INQUIRY_HEADERS)
        get_or_create_worksheet(spreadsheet, TAB_ESTIMATES, ESTIMATE_HEADERS)
        get_or_create_worksheet(spreadsheet, TAB_PIPELINE, PIPELINE_HEADERS)

        return jsonify({
            "success": True,
            "message": "All three tabs created with headers!",
            "tabs": [TAB_INQUIRIES, TAB_ESTIMATES, TAB_PIPELINE]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  AP Business Tools")
    print("=" * 50)
    print(f"\n  Open in browser: http://localhost:5000")
    print(f"\n  Google Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    print("=" * 50 + "\n")

    app.run(host="0.0.0.0", port=5000, debug=True)
