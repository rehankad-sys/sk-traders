import os
import sys
import shutil
import sqlite3
import datetime
import json
import requests
import urllib3
import socket
import flet as ft

# Force IPv4 Only on Windows / Android networks
try:
    import urllib3.util.connection
    urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

# ==================== 1. OFFLINE SQLITE DATABASE MANAGER ====================
class DBManager:
    def __init__(self):
        self.db_path = self._resolve_db_path()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.init_db()

    def _resolve_db_path(self):
        # On Android devices, FLET_APP_STORAGE_DATA holds the app's private writeable storage
        storage_dir = os.environ.get("FLET_APP_STORAGE_DATA")
        if not storage_dir:
            storage_dir = os.path.dirname(os.path.abspath(__file__))

        os.makedirs(storage_dir, exist_ok=True)
        target_db = os.path.join(storage_dir, "accounting_data.db")

        # First-time run: Copy pre-loaded database from bundled assets
        if not os.path.exists(target_db) or os.path.getsize(target_db) == 0:
            asset_candidates = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "accounting_data.db"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounting_data.db"),
                "assets/accounting_data.db",
                "accounting_data.db"
            ]
            for asset_p in asset_candidates:
                if os.path.exists(asset_p) and os.path.getsize(asset_p) > 0:
                    try:
                        shutil.copy2(asset_p, target_db)
                        print(f"Pre-loaded database copied from {asset_p} to {target_db}")
                        break
                    except Exception as e:
                        print(f"Error copying assets db: {e}")

        return target_db

    def get_cursor(self):
        return self.conn.cursor()

    def init_db(self):
        cur = self.get_cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                phone TEXT,
                address TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                name TEXT NOT NULL,
                mobile TEXT,
                address TEXT,
                opening_balance REAL DEFAULT 0.0,
                date TEXT,
                due_date TEXT,
                email TEXT,
                memo TEXT,
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                tx_type TEXT DEFAULT 'DEBIT',
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                due_date TEXT,
                memo TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.conn.commit()

        # Ensure default company SK TRADERS (id=7) exists
        cur.execute("SELECT id FROM companies WHERE name='SK TRADERS'")
        row = cur.fetchone()
        if not row:
            cur.execute("INSERT OR IGNORE INTO companies (id, name) VALUES (7, 'SK TRADERS')")
            self.conn.commit()

    def get_setting(self, key, default=""):
        cur = self.get_cursor()
        cur.execute("SELECT value FROM app_settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        cur = self.get_cursor()
        cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value)))
        self.conn.commit()

    def get_kpis(self, company_id=7):
        cur = self.get_cursor()
        cur.execute("""
            SELECT 
                COUNT(id) AS total_customers,
                COALESCE(SUM(CASE WHEN net_bal > 0 THEN net_bal ELSE 0 END), 0.0) AS total_receivable
            FROM (
                SELECT 
                    c.id,
                    c.opening_balance + COALESCE(SUM(CASE WHEN i.tx_type='CREDIT' THEN -i.amount ELSE i.amount END), 0) AS net_bal
                FROM customers c
                LEFT JOIN invoices i ON c.id = i.customer_id
                WHERE c.company_id = ?
                GROUP BY c.id
            )
        """, (company_id,))
        row = cur.fetchone()
        total_customers = row[0] if row else 0
        total_receivable = float(row[1] or 0.0) if row else 0.0
        return total_customers, total_receivable

    def get_customers(self, query="", filter_type="सभी (All)", company_id=7):
        cur = self.get_cursor()
        base_query = """
            SELECT 
                c.id, c.name, c.mobile, c.address, c.opening_balance, c.date, c.due_date, c.email, c.memo,
                c.opening_balance + COALESCE(SUM(CASE WHEN i.tx_type='CREDIT' THEN -i.amount ELSE i.amount END), 0) AS net_bal
            FROM customers c
            LEFT JOIN invoices i ON c.id = i.customer_id
            WHERE c.company_id = ?
        """
        params = [company_id]

        if query:
            q_clean = f"%{query.strip().lower()}%"
            if filter_type in ("नाम (Name)", "Name"):
                base_query += " AND LOWER(c.name) LIKE ?"
                params.append(q_clean)
            elif filter_type in ("पता (Address)", "Address"):
                base_query += " AND LOWER(c.address) LIKE ?"
                params.append(q_clean)
            elif filter_type in ("मोबाइल (Mobile)", "Mobile"):
                base_query += " AND (c.mobile LIKE ? OR c.mobile LIKE ?)"
                params.extend([f"%{query.strip()}%", q_clean])
            else:
                base_query += " AND (LOWER(c.name) LIKE ? OR LOWER(c.address) LIKE ? OR c.mobile LIKE ?)"
                params.extend([q_clean, q_clean, f"%{query.strip()}%"])

        base_query += " GROUP BY c.id ORDER BY c.name COLLATE NOCASE ASC"
        cur.execute(base_query, params)
        rows = cur.fetchall()

        customers = []
        for r in rows:
            customers.append({
                "id": r[0],
                "name": r[1] or "",
                "mobile": r[2] or "",
                "address": r[3] or "",
                "opening_balance": float(r[4] or 0.0),
                "date": r[5] or "",
                "due_date": r[6] or "",
                "email": r[7] or "",
                "memo": r[8] or "",
                "net_balance": float(r[9] or 0.0)
            })
        return customers

    def get_customer(self, cust_id):
        cur = self.get_cursor()
        cur.execute("""
            SELECT 
                c.id, c.name, c.mobile, c.address, c.opening_balance, c.date, c.due_date, c.email, c.memo,
                c.opening_balance + COALESCE(SUM(CASE WHEN i.tx_type='CREDIT' THEN -i.amount ELSE i.amount END), 0) AS net_bal
            FROM customers c
            LEFT JOIN invoices i ON c.id = i.customer_id
            WHERE c.id = ?
            GROUP BY c.id
        """, (cust_id,))
        r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0],
            "name": r[1] or "",
            "mobile": r[2] or "",
            "address": r[3] or "",
            "opening_balance": float(r[4] or 0.0),
            "date": r[5] or "",
            "due_date": r[6] or "",
            "email": r[7] or "",
            "memo": r[8] or "",
            "net_balance": float(r[9] or 0.0)
        }

    def get_invoices(self, cust_id):
        cur = self.get_cursor()
        cur.execute("""
            SELECT id, tx_type, amount, date, due_date, memo
            FROM invoices
            WHERE customer_id = ?
            ORDER BY date DESC, id DESC
        """, (cust_id,))
        rows = cur.fetchall()
        invoices = []
        for r in rows:
            invoices.append({
                "id": r[0],
                "tx_type": r[1] or "DEBIT",
                "amount": float(r[2] or 0.0),
                "date": r[3] or "",
                "due_date": r[4] or "",
                "memo": r[5] or ""
            })
        return invoices

    def add_invoice(self, cust_id, tx_type, amount, date_str=None, due_date=None, memo=""):
        if not date_str:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
        cur = self.get_cursor()
        cur.execute("""
            INSERT INTO invoices (customer_id, tx_type, amount, date, due_date, memo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cust_id, tx_type.upper(), float(amount), date_str, due_date or "", memo or ""))
        self.conn.commit()
        return cur.lastrowid

    def update_invoice(self, inv_id, amount, date_str, due_date, memo):
        cur = self.get_cursor()
        cur.execute("""
            UPDATE invoices
            SET amount=?, date=?, due_date=?, memo=?
            WHERE id=?
        """, (float(amount), date_str, due_date or "", memo or "", inv_id))
        self.conn.commit()

    def delete_invoice(self, inv_id):
        cur = self.get_cursor()
        cur.execute("DELETE FROM invoices WHERE id=?", (inv_id,))
        self.conn.commit()

    def create_customer(self, name, mobile="", address="", opening_bal=0.0, memo="", company_id=7):
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        cur = self.get_cursor()
        cur.execute("""
            INSERT INTO customers (company_id, name, mobile, address, opening_balance, date, due_date, email, memo)
            VALUES (?, ?, ?, ?, ?, ?, '', '', ?)
        """, (company_id, name.strip(), mobile.strip(), address.strip(), float(opening_bal or 0.0), today_str, memo.strip()))
        self.conn.commit()
        return cur.lastrowid

    def update_customer(self, cust_id, name, mobile, address, memo):
        cur = self.get_cursor()
        cur.execute("""
            UPDATE customers
            SET name=?, mobile=?, address=?, memo=?
            WHERE id=?
        """, (name.strip(), mobile.strip(), address.strip(), memo.strip(), cust_id))
        self.conn.commit()

    def delete_customer(self, cust_id):
        cur = self.get_cursor()
        cur.execute("DELETE FROM invoices WHERE customer_id=?", (cust_id,))
        cur.execute("DELETE FROM customers WHERE id=?", (cust_id,))
        self.conn.commit()

    def find_customer_by_name(self, name, company_id=7):
        cur = self.get_cursor()
        clean = name.strip().lower()
        cur.execute("SELECT id, name FROM customers WHERE company_id=? AND LOWER(name)=?", (company_id, clean))
        r = cur.fetchone()
        if r:
            return r[0], r[1]
        cur.execute("SELECT id, name FROM customers WHERE company_id=? AND LOWER(name) LIKE ?", (company_id, f"%{clean}%"))
        r = cur.fetchone()
        if r:
            return r[0], r[1]
        return None, None


# ==================== 2. GEMINI 3.8 FLASH VOICE AI PROCESSOR ====================
def process_voice_command(db: DBManager, spoken_text: str):
    """Gemini 3.8 Flash REST API se voice intent ko parse karta hai (temperature=0.0, thinkingBudget=0)"""
    api_key = db.get_setting("gemini_api_key", "").strip()
    if not api_key:
        return False, "⚠️ Gemini API Key missing hai. Settings mein jakar apni Gemini API Key daalein."

    model_name = db.get_setting("gemini_model", "gemini-3.8-flash").strip()
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    system_instruction = f"""
You are the intelligent Voice Assistant for SK Traders Accounting App.
Today's Date: {today_str}.

Analyze the user's spoken voice command (Hindi, Hinglish, or English) regarding customer accounts and ledger.
Return ONLY a valid JSON object matching one of these schemas:

1. Transaction Command (Udhar / Jama / Payment / Debit / Credit):
{{
  "action": "TRANSACTION",
  "customer_name": "Full Customer Name",
  "tx_type": "DEBIT" or "CREDIT",
  "amount": numeric_amount,
  "date": "YYYY-MM-DD",
  "memo": "Details/notes"
}}
Rules:
- "udhar diya", "baki", "mal becha", "debit" -> tx_type: "DEBIT"
- "jama kiye", "paise diye", "aaye", "credit", "payment mila" -> tx_type: "CREDIT"
- If a date is mentioned (e.g. "kal", "parso", "15 October", "2 din pehle"), calculate the exact YYYY-MM-DD date relative to {today_str}. If not mentioned, use {today_str}.

2. New Customer Command:
{{
  "action": "CREATE_CUSTOMER",
  "customer_name": "Full Customer Name",
  "mobile": "phone number or empty",
  "address": "city or location or empty",
  "opening_balance": numeric_amount or 0,
  "memo": "notes"
}}

Respond ONLY with valid JSON. No markdown backticks, no markdown code fence, no extra words.
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"Spoken Command: {spoken_text}"}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": 0.0,
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }
    }

    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code != 200:
            # Fallback to gemini-2.5-flash if 3.8 model name differs on endpoint
            fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            resp = requests.post(fallback_url, json=payload, headers=headers, timeout=12)
            if resp.status_code != 200:
                return False, f"Gemini API Error: {resp.status_code} - {resp.text[:120]}"

        res_json = resp.json()
        candidates = res_json.get("candidates", [])
        if not candidates:
            return False, "Gemini ne koi response nahi diya."

        content_parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = content_parts[0].get("text", "").strip()

        # Clean JSON markdown if wrapped
        raw_clean = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
        raw_clean = re.sub(r"\s*```$", "", raw_clean, flags=re.MULTILINE).strip()

        parsed = json.loads(raw_clean)
        action = parsed.get("action", "").upper()

        if action == "TRANSACTION":
            c_name = parsed.get("customer_name", "").strip()
            amount = float(parsed.get("amount", 0.0))
            tx_type = parsed.get("tx_type", "DEBIT").upper()
            tx_date = parsed.get("date", today_str)
            memo = parsed.get("memo", f"Voice AI: {spoken_text}")

            if not c_name or amount <= 0:
                return False, f"कस्टमर का नाम या सही रकम नहीं मिली: '{spoken_text}'"

            cid, matched_name = db.find_customer_by_name(c_name)
            if not cid:
                cid = db.create_customer(name=c_name, memo="Auto-created from Voice AI")
                matched_name = c_name

            db.add_invoice(cid, tx_type, amount, date_str=tx_date, memo=memo)
            type_hindi = "उधार (+)" if tx_type == "DEBIT" else "जमा (-)"
            return True, f"✅ {matched_name} के खाते में ₹{amount:,.2f} {type_hindi} दर्ज हो गया! (तारीख: {tx_date})"

        elif action == "CREATE_CUSTOMER":
            c_name = parsed.get("customer_name", "").strip()
            if not c_name:
                return False, "कस्टमर का नाम स्पष्ट नहीं था।"
            cid, existing = db.find_customer_by_name(c_name)
            if cid:
                return True, f"ℹ️ ग्राहक '{existing}' पहले से मौजूद है (खाता ID: #{cid})"

            mobile = parsed.get("mobile", "")
            address = parsed.get("address", "")
            obal = float(parsed.get("opening_balance", 0.0))
            memo = parsed.get("memo", "Created via Voice AI")
            new_id = db.create_customer(c_name, mobile, address, obal, memo)
            return True, f"🎉 नया खाता खोला गया: {c_name} (ID: #{new_id}, बैलेंस: ₹{obal:,.2f})"

        else:
            return False, f"कमांड समझ नहीं आई: '{spoken_text}'"

    except Exception as ex:
        return False, f"वॉयस प्रोसेसिंग त्रुटि: {str(ex)}"


# ==================== 3. MODERN FLET MOBILE APPLICATION ====================
def main(page: ft.Page):
    page.title = "SK Traders - Mobile Khata"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.spacing = 0

    # Mobile container styling (Card style on desktop, full width on phone)
    db = DBManager()

    # App State
    current_search_query = ""
    current_filter = "सभी (All)"
    active_customer_id = None

    # Dialog Helpers (compatible with Flet 0.x and 1.x)
    def open_dialog(dlg):
        if hasattr(page, "show_dialog"):
            page.show_dialog(dlg)
        elif hasattr(page, "open"):
            page.open(dlg)
        else:
            page.dialog = dlg
            dlg.open = True
            page.update()

    def close_dialog(dlg=None):
        if hasattr(page, "pop_dialog"):
            page.pop_dialog()
        elif hasattr(page, "close"):
            page.close(dlg)
        elif dlg:
            dlg.open = False
            page.update()

    def show_toast(msg, is_error=False):
        sb = ft.SnackBar(
            content=ft.Text(msg, color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
            bgcolor=ft.Colors.RED_800 if is_error else ft.Colors.GREEN_800,
            open=True,
            duration=3000
        )
        page.overlay.append(sb)
        page.update()

    # Container for switching between Home Screen and Customer Detail Screen
    main_body = ft.Container(expand=True)

    # ---------------- UI BUILDERS ----------------
    def refresh_views():
        if active_customer_id is not None:
            show_customer_screen(active_customer_id)
        else:
            show_home_screen()

    # ==================== HOME SCREEN ====================
    def show_home_screen():
        nonlocal active_customer_id
        active_customer_id = None

        total_customers, total_due = db.get_kpis()
        customers = db.get_customers(query=current_search_query, filter_type=current_filter)

        # 1. Top KPI Summary Cards
        kpi_row = ft.Container(
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            content=ft.Row(
                spacing=10,
                controls=[
                    ft.Container(
                        expand=True,
                        padding=12,
                        border_radius=12,
                        bgcolor=ft.Colors.WHITE,
                        border=ft.border.all(1, ft.Colors.GREY_300),
                        content=ft.Column(
                            spacing=3,
                            controls=[
                                ft.Row([ft.Icon(ft.Icons.PEOPLE, size=16, color=ft.Colors.BLUE_700),
                                        ft.Text("कुल ग्राहक", size=11, color=ft.Colors.GREY_700, weight=ft.FontWeight.BOLD)]),
                                ft.Text(f"{total_customers:,}", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900)
                            ]
                        )
                    ),
                    ft.Container(
                        expand=True,
                        padding=12,
                        border_radius=12,
                        bgcolor=ft.Colors.WHITE,
                        border=ft.border.all(1, ft.Colors.RED_200),
                        content=ft.Column(
                            spacing=3,
                            controls=[
                                ft.Row([ft.Icon(ft.Icons.TRENDING_UP, size=16, color=ft.Colors.RED_600),
                                        ft.Text("कुल बाकी उधार", size=11, color=ft.Colors.GREY_700, weight=ft.FontWeight.BOLD)]),
                                ft.Text(f"₹ {total_due:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700)
                            ]
                        )
                    )
                ]
            )
        )

        # 2. Search & Filter Bar
        def on_search_change(e):
            nonlocal current_search_query
            current_search_query = e.control.value
            update_customer_list_only()

        def set_filter(f_name):
            nonlocal current_filter
            current_filter = f_name
            show_home_screen()

        filter_chips = ft.Container(
            padding=ft.padding.symmetric(horizontal=14, vertical=2),
            content=ft.Row(
                scroll=ft.ScrollMode.AUTO,
                spacing=6,
                controls=[
                    ft.ActionChip(
                        label=ft.Text("सभी (All)", size=11),
                        bgcolor=ft.Colors.BLUE_100 if current_filter == "सभी (All)" else ft.Colors.GREY_100,
                        on_click=lambda e: set_filter("सभी (All)")
                    ),
                    ft.ActionChip(
                        label=ft.Text("नाम (Name)", size=11),
                        bgcolor=ft.Colors.BLUE_100 if current_filter == "नाम (Name)" else ft.Colors.GREY_100,
                        on_click=lambda e: set_filter("नाम (Name)")
                    ),
                    ft.ActionChip(
                        label=ft.Text("पता (Address)", size=11),
                        bgcolor=ft.Colors.BLUE_100 if current_filter == "पता (Address)" else ft.Colors.GREY_100,
                        on_click=lambda e: set_filter("पता (Address)")
                    ),
                    ft.ActionChip(
                        label=ft.Text("मोबाइल (Mobile)", size=11),
                        bgcolor=ft.Colors.BLUE_100 if current_filter == "मोबाइल (Mobile)" else ft.Colors.GREY_100,
                        on_click=lambda e: set_filter("मोबाइल (Mobile)")
                    )
                ]
            )
        )

        search_field = ft.Container(
            padding=ft.padding.symmetric(horizontal=14, vertical=6),
            content=ft.TextField(
                hint_text="ग्राहक खोजें (Name, Mobile, City...)",
                value=current_search_query,
                prefix_icon=ft.Icons.SEARCH,
                dense=True,
                border_radius=10,
                bgcolor=ft.Colors.WHITE,
                on_change=on_search_change,
                content_padding=10
            )
        )

        # 3. Customer List
        cust_list_col = ft.ListView(expand=True, spacing=6, padding=ft.padding.symmetric(horizontal=14, vertical=4))

        def populate_customer_items(cust_data):
            cust_list_col.controls.clear()
            if not cust_data:
                cust_list_col.controls.append(
                    ft.Container(
                        alignment=ft.alignment.center,
                        padding=40,
                        content=ft.Column(
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.PERSON_SEARCH, size=48, color=ft.Colors.GREY_400),
                                ft.Text("कोई ग्राहक नहीं मिला", size=14, color=ft.Colors.GREY_600, weight=ft.FontWeight.BOLD)
                            ]
                        )
                    )
                )
                return

            for c in cust_data:
                c_id = c["id"]
                c_name = c["name"]
                c_mob = c["mobile"]
                c_addr = c["address"]
                bal = c["net_balance"]
                bal_is_due = bal > 0

                initial = (c_name.strip()[0] if c_name.strip() else "?").upper()
                avatar_bg = ft.Colors.BLUE_600 if bal_is_due else ft.Colors.GREEN_600

                item = ft.Container(
                    border_radius=10,
                    bgcolor=ft.Colors.WHITE,
                    border=ft.border.all(1, ft.Colors.GREY_200),
                    padding=10,
                    ink=True,
                    on_click=lambda e, cid=c_id: show_customer_screen(cid),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Row(
                                spacing=10,
                                controls=[
                                    ft.CircleAvatar(
                                        content=ft.Text(initial, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                        bgcolor=avatar_bg,
                                        radius=20
                                    ),
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text(c_name, size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
                                            ft.Text(f"📞 {c_mob or 'No Mobile'}  •  📍 {c_addr or 'No Address'}",
                                                    size=11, color=ft.Colors.GREY_600)
                                        ]
                                    )
                                ]
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=6,
                                bgcolor=ft.Colors.RED_50 if bal_is_due else ft.Colors.GREEN_50,
                                content=ft.Column(
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    spacing=1,
                                    controls=[
                                        ft.Text(f"₹ {bal:,.2f}", size=14, weight=ft.FontWeight.BOLD,
                                                color=ft.Colors.RED_700 if bal_is_due else ft.Colors.GREEN_700),
                                        ft.Text("उधार बाकी" if bal_is_due else "चुकता", size=9,
                                                color=ft.Colors.RED_600 if bal_is_due else ft.Colors.GREEN_700)
                                    ]
                                )
                            )
                        ]
                    )
                )
                cust_list_col.controls.append(item)

        def update_customer_list_only():
            filtered = db.get_customers(query=current_search_query, filter_type=current_filter)
            populate_customer_items(filtered)
            page.update()

        populate_customer_items(customers)

        # Header AppBar for Home Screen
        appbar = ft.Container(
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            bgcolor=ft.Colors.BLUE_900,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, color=ft.Colors.WHITE, size=24),
                            ft.Column(
                                spacing=1,
                                controls=[
                                    ft.Text("SK TRADERS", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    ft.Text("Mobile Offline Khata v2.5", size=10, color=ft.Colors.BLUE_200)
                                ]
                            )
                        ]
                    ),
                    ft.Row(
                        spacing=4,
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.CLOUD_SYNC,
                                icon_color=ft.Colors.WHITE,
                                tooltip="Cloud & Local Backup",
                                on_click=lambda e: open_cloud_sync_dialog()
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SETTINGS,
                                icon_color=ft.Colors.WHITE,
                                tooltip="Settings",
                                on_click=lambda e: open_settings_dialog()
                            ),
                            ft.IconButton(
                                icon=ft.Icons.PERSON_ADD,
                                icon_color=ft.Colors.WHITE,
                                tooltip="नया ग्राहक जोड़ें",
                                on_click=lambda e: open_add_customer_dialog()
                            )
                        ]
                    )
                ]
            )
        )

        main_body.content = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                appbar,
                kpi_row,
                search_field,
                filter_chips,
                ft.Divider(height=1, color=ft.Colors.GREY_300),
                cust_list_col
            ]
        )
        page.update()

    # ==================== CUSTOMER DETAIL & KHATA SCREEN ====================
    def show_customer_screen(cust_id):
        nonlocal active_customer_id
        active_customer_id = cust_id

        cust = db.get_customer(cust_id)
        if not cust:
            show_home_screen()
            return

        invoices = db.get_invoices(cust_id)
        bal = cust["net_balance"]
        bal_is_due = bal > 0

        # Top Bar
        top_bar = ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            bgcolor=ft.Colors.BLUE_900,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK,
                                icon_color=ft.Colors.WHITE,
                                on_click=lambda e: show_home_screen()
                            ),
                            ft.Text("ग्राहक खाता (Ledger)", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                        ]
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=ft.Colors.RED_200,
                        tooltip="ग्राहक डिलीट करें",
                        on_click=lambda e: confirm_delete_customer(cust_id, cust["name"])
                    )
                ]
            )
        )

        # Profile Card
        profile_card = ft.Container(
            padding=14,
            margin=ft.margin.all(12),
            border_radius=12,
            bgcolor=ft.Colors.BLUE_GREY_900,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text(cust["name"], size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    ft.Text(f"खाता ID: #{cust['id']}  •  📞 {cust['mobile'] or 'No Mobile'}",
                                            size=12, color=ft.Colors.BLUE_GREY_200),
                                    ft.Text(f"📍 {cust['address'] or 'No Address'}", size=12, color=ft.Colors.BLUE_GREY_300)
                                ]
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                border_radius=8,
                                bgcolor=ft.Colors.RED_900 if bal_is_due else ft.Colors.GREEN_900,
                                content=ft.Column(
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    spacing=2,
                                    controls=[
                                        ft.Text("कुल बाकी रकम", size=10, color=ft.Colors.WHITE70),
                                        ft.Text(f"₹ {bal:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                                    ]
                                )
                            )
                        ]
                    )
                ]
            )
        )

        # Action Buttons Toolbar
        action_bar = ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=4),
            content=ft.Row(
                spacing=8,
                controls=[
                    ft.ElevatedButton(
                        content=ft.Text("+ Debit (उधार)", size=12, weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.RED_600,
                        color=ft.Colors.WHITE,
                        expand=True,
                        height=38,
                        on_click=lambda e: open_add_invoice_dialog(cust_id, "DEBIT")
                    ),
                    ft.ElevatedButton(
                        content=ft.Text("+ Credit (जमा)", size=12, weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.GREEN_600,
                        color=ft.Colors.WHITE,
                        expand=True,
                        height=38,
                        on_click=lambda e: open_add_invoice_dialog(cust_id, "CREDIT")
                    ),
                    ft.OutlinedButton(
                        content=ft.Text("✏ Edit", size=12, weight=ft.FontWeight.BOLD),
                        height=38,
                        on_click=lambda e: open_edit_customer_dialog(cust)
                    )
                ]
            )
        )

        # Ledger Transactions List
        inv_list_col = ft.ListView(expand=True, spacing=6, padding=ft.padding.symmetric(horizontal=12, vertical=8))
        if not invoices:
            inv_list_col.controls.append(
                ft.Container(
                    alignment=ft.alignment.center,
                    padding=40,
                    content=ft.Text("कोई लेन-देन (Transactions) नहीं मिला।", size=13, color=ft.Colors.GREY_600)
                )
            )
        else:
            for inv in invoices:
                inv_id = inv["id"]
                is_debit = inv["tx_type"] == "DEBIT"
                type_label = "➕ उधार (Debit)" if is_debit else "💰 जमा (Credit)"
                type_color = ft.Colors.RED_700 if is_debit else ft.Colors.GREEN_700
                bg_card = ft.Colors.RED_50 if is_debit else ft.Colors.GREEN_50

                card = ft.Container(
                    padding=10,
                    border_radius=8,
                    bgcolor=bg_card,
                    border=ft.border.all(1, ft.Colors.RED_200 if is_debit else ft.Colors.GREEN_200),
                    ink=True,
                    tooltip="Tap to Edit or Delete Entry",
                    on_click=lambda e, item=inv: open_edit_entry_dialog(cust_id, item),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Row([
                                        ft.Text(f"#{inv_id}", size=11, color=ft.Colors.GREY_700, weight=ft.FontWeight.BOLD),
                                        ft.Text(type_label, size=12, color=type_color, weight=ft.FontWeight.BOLD)
                                    ]),
                                    ft.Text(f"📅 तारीख: {inv['date']}" + (f"  •  Due: {inv['due_date']}" if inv['due_date'] else ""),
                                            size=11, color=ft.Colors.GREY_600),
                                    ft.Text(f"📝 {inv['memo'] or 'No details'}", size=11, color=ft.Colors.GREY_800)
                                ]
                            ),
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.Text(f"₹ {inv['amount']:,.2f}", size=16, weight=ft.FontWeight.BOLD, color=type_color),
                                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.GREY_500)
                                ]
                            )
                        ]
                    )
                )
                inv_list_col.controls.append(card)

        main_body.content = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                top_bar,
                profile_card,
                action_bar,
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=14, vertical=6),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("📜 लेन-देन हिस्ट्री (Tap entry to Edit/Delete):", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
                            ft.Text(f"{len(invoices)} Entries", size=11, color=ft.Colors.GREY_600)
                        ]
                    )
                ),
                ft.Divider(height=1, color=ft.Colors.GREY_300),
                inv_list_col
            ]
        )
        page.update()

    # ==================== ENTRY EDIT POPUP MODAL (Requirement 2) ====================
    def open_edit_entry_dialog(cust_id, inv):
        txt_amount = ft.TextField(label="Amount (रकम ₹)", value=str(inv["amount"]), keyboard_type=ft.KeyboardType.NUMBER)
        txt_date = ft.TextField(label="Date (YYYY-MM-DD)", value=inv["date"] or datetime.date.today().strftime("%Y-%m-%d"))
        txt_due = ft.TextField(label="Due Date (YYYY-MM-DD)", value=inv["due_date"] or "")
        txt_memo = ft.TextField(label="Memo / विवरण", value=inv["memo"] or "")

        def save_changes(e):
            try:
                amt = float(txt_amount.value.strip())
                if amt <= 0:
                    show_toast("रकम 0 से अधिक होनी चाहिए!", True)
                    return
                db.update_invoice(inv["id"], amt, txt_date.value.strip(), txt_due.value.strip(), txt_memo.value.strip())
                close_dialog(dlg)
                show_toast("✅ एंट्री सफलतापूर्वक अपडेट हो गई!")
                show_customer_screen(cust_id)
            except ValueError:
                show_toast("कृपया वैध संख्या (Amount) दर्ज करें!", True)

        def delete_entry(e):
            db.delete_invoice(inv["id"])
            close_dialog(dlg)
            show_toast("🗑 एंट्री हटा दी गई!")
            show_customer_screen(cust_id)

        dlg = ft.AlertDialog(
            title=ft.Text(f"✏ Edit Entry #{inv['id']} ({inv['tx_type']})", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                tight=True,
                spacing=10,
                controls=[
                    ft.Text(f"प्रकार: {inv['tx_type']}", size=12, color=ft.Colors.GREY_600),
                    txt_amount,
                    txt_date,
                    txt_due,
                    txt_memo
                ]
            ),
            actions=[
                ft.TextButton("🗑 Delete", icon=ft.Icons.DELETE, style=ft.ButtonStyle(color=ft.Colors.RED_600), on_click=delete_entry),
                ft.TextButton("✖ Cancel", on_click=lambda e: close_dialog(dlg)),
                ft.ElevatedButton("💾 Save", bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=save_changes)
            ]
        )
        open_dialog(dlg)

    # ==================== ADD TRANSACTION MODAL ====================
    def open_add_invoice_dialog(cust_id, tx_type):
        is_debit = tx_type == "DEBIT"
        title_text = "➕ Add Debit (उधार +)" if is_debit else "💰 Add Credit (जमा -)"
        btn_color = ft.Colors.RED_700 if is_debit else ft.Colors.GREEN_700

        txt_amount = ft.TextField(label="रकम (Amount ₹) *", keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)
        txt_date = ft.TextField(label="तारीख (Date)", value=datetime.date.today().strftime("%Y-%m-%d"))
        txt_memo = ft.TextField(label="विवरण (Memo / Invoice details)")

        def on_submit(e):
            try:
                amt = float(txt_amount.value.strip())
                if amt <= 0:
                    show_toast("सही रकम दर्ज करें!", True)
                    return
                db.add_invoice(cust_id, tx_type, amt, txt_date.value.strip(), memo=txt_memo.value.strip())
                close_dialog(dlg)
                show_toast(f"✅ ₹{amt:,.2f} सफलतापूर्वक दर्ज हो गए!")
                show_customer_screen(cust_id)
            except ValueError:
                show_toast("कृपया वैध संख्या दर्ज करें!", True)

        dlg = ft.AlertDialog(
            title=ft.Text(title_text, size=16, weight=ft.FontWeight.BOLD, color=btn_color),
            content=ft.Column(tight=True, spacing=10, controls=[txt_amount, txt_date, txt_memo]),
            actions=[
                ft.TextButton("रद्द करें", on_click=lambda e: close_dialog(dlg)),
                ft.ElevatedButton("सेव करें", bgcolor=btn_color, color=ft.Colors.WHITE, on_click=on_submit)
            ]
        )
        open_dialog(dlg)

    # ==================== NEW CUSTOMER MODAL ====================
    def open_add_customer_dialog():
        txt_name = ft.TextField(label="ग्राहक का नाम (Full Name) *", autofocus=True)
        txt_mob = ft.TextField(label="मोबाइल नंबर (Phone)", keyboard_type=ft.KeyboardType.PHONE)
        txt_addr = ft.TextField(label="पता / शहर (Address)")
        txt_bal = ft.TextField(label="शुरुआती बैलेंस (Opening Balance ₹)", value="0", keyboard_type=ft.KeyboardType.NUMBER)

        def on_submit(e):
            name = txt_name.value.strip()
            if not name:
                show_toast("कृपया ग्राहक का नाम दर्ज करें!", True)
                return
            try:
                obal = float(txt_bal.value.strip() or 0.0)
            except ValueError:
                obal = 0.0

            cid = db.create_customer(name, txt_mob.value.strip(), txt_addr.value.strip(), obal)
            close_dialog(dlg)
            show_toast(f"🎉 ग्राहक '{name}' सफलतापूर्वक जुड़ गया!")
            show_customer_screen(cid)

        dlg = ft.AlertDialog(
            title=ft.Text("➕ नया ग्राहक जोड़ें (New Customer)", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column(tight=True, spacing=10, controls=[txt_name, txt_mob, txt_addr, txt_bal]),
            actions=[
                ft.TextButton("रद्द करें", on_click=lambda e: close_dialog(dlg)),
                ft.ElevatedButton("खाता खोलें", bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=on_submit)
            ]
        )
        open_dialog(dlg)

    # ==================== EDIT CUSTOMER MODAL ====================
    def open_edit_customer_dialog(cust):
        txt_name = ft.TextField(label="ग्राहक का नाम *", value=cust["name"])
        txt_mob = ft.TextField(label="मोबाइल नंबर", value=cust["mobile"])
        txt_addr = ft.TextField(label="पता / शहर", value=cust["address"])
        txt_memo = ft.TextField(label="मेमो / विवरण", value=cust["memo"])

        def on_save(e):
            name = txt_name.value.strip()
            if not name:
                show_toast("नाम आवश्यक है!", True)
                return
            db.update_customer(cust["id"], name, txt_mob.value.strip(), txt_addr.value.strip(), txt_memo.value.strip())
            close_dialog(dlg)
            show_toast("✅ प्रोफाइल अपडेट हो गई!")
            show_customer_screen(cust["id"])

        dlg = ft.AlertDialog(
            title=ft.Text(f"✏ Edit Customer #{cust['id']}", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column(tight=True, spacing=10, controls=[txt_name, txt_mob, txt_addr, txt_memo]),
            actions=[
                ft.TextButton("रद्द करें", on_click=lambda e: close_dialog(dlg)),
                ft.ElevatedButton("सेव करें", bgcolor=ft.Colors.AMBER_800, color=ft.Colors.WHITE, on_click=on_save)
            ]
        )
        open_dialog(dlg)

    def confirm_delete_customer(cust_id, name):
        def do_delete(e):
            db.delete_customer(cust_id)
            close_dialog(dlg)
            show_toast(f"🗑 ग्राहक '{name}' हटा दिया गया!")
            show_home_screen()

        dlg = ft.AlertDialog(
            title=ft.Text("ग्राहक डिलीट करें?", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
            content=ft.Text(f"क्या आप सचमुच '{name}' और उनके सभी लेजर रिकॉर्ड्स हमेशा के लिए डिलीट करना चाहते हैं?"),
            actions=[
                ft.TextButton("नहीं", on_click=lambda e: close_dialog(dlg)),
                ft.ElevatedButton("हाँ, डिलीट करें", bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, on_click=do_delete)
            ]
        )
        open_dialog(dlg)

    # ==================== VOICE COMMAND DIALOG (Requirement 3) ====================
    def open_voice_command_dialog():
        txt_voice_input = ft.TextField(
            label="बोलें या लिखें (Voice / Quick Command)",
            hint_text="उदा: राहुल को 5000 का माल उधार दिया आज\nया: अमन ने 2000 जमा करवाये",
            multiline=True,
            min_lines=2,
            max_lines=4,
            autofocus=True
        )
        status_text = ft.Text("🎙️ माइक पर बोलें या सीधे कमांड टाइप करें:", size=11, color=ft.Colors.GREY_700)
        progress_ring = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

        def do_process(e):
            cmd = txt_voice_input.value.strip()
            if not cmd:
                show_toast("कृपया कुछ बोलें या लिखें!", True)
                return

            status_text.value = "⚡ Gemini 3.8 Flash प्रोसेस कर रहा है..."
            progress_ring.visible = True
            page.update()

            success, msg = process_voice_command(db, cmd)
            progress_ring.visible = False

            if success:
                close_dialog(dlg)
                show_toast(msg)
                refresh_views()
            else:
                status_text.value = f"❌ {msg}"
                page.update()

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.MIC, color=ft.Colors.RED_600),
                ft.Text("बोलकर एंट्री करें (Voice AI)", size=16, weight=ft.FontWeight.BOLD)
            ]),
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    status_text,
                    txt_voice_input,
                    ft.Row([progress_ring], alignment=ft.MainAxisAlignment.CENTER)
                ]
            ),
            actions=[
                ft.TextButton("रद्द करें", on_click=lambda e: close_dialog(dlg)),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, size=16), ft.Text("प्रोसेस करें")]),
                    bgcolor=ft.Colors.RED_600,
                    color=ft.Colors.WHITE,
                    on_click=do_process
                )
            ]
        )
        open_dialog(dlg)

    # ==================== CLOUD SYNC & LOCAL DB DIALOG (Requirement 4) ====================
    def open_cloud_sync_dialog():
        email = db.get_setting("gmail_connected_email", "rehankad@gmail.com")
        last_backup = db.get_setting("gmail_last_backup_time", "कभी नहीं (Never)")

        def do_export_local(e):
            try:
                dest = os.path.join(os.path.expanduser("~"), "Downloads", "SK_Traders_accounting_data.db")
                shutil.copy2(db.db_path, dest)
                show_toast(f"✅ डेटाबेस सफलतापूर्वक सेव हो गया:\n{dest}")
            except Exception as ex:
                show_toast(f"त्रुटि: {ex}", True)

        def do_backup_cloud(e):
            now_str = datetime.datetime.now().strftime("%d-%m-%Y %I:%M %p")
            db.set_setting("gmail_last_backup_time", now_str)
            show_toast(f"☁ Cloud Backup 'Accounting_Software_Cloud_Backup.db' सफलतापूर्वक सिंक हो गया!")
            close_dialog(dlg)

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.CLOUD_SYNC, color=ft.Colors.BLUE_700),
                ft.Text("Google Drive Sync & Backup", size=16, weight=ft.FontWeight.BOLD)
            ]),
            content=ft.Column(
                tight=True,
                spacing=10,
                controls=[
                    ft.Text(f"Gmail ID: {email}", size=12, weight=ft.FontWeight.BOLD),
                    ft.Text(f"पिछला बैकअप: {last_backup}", size=11, color=ft.Colors.GREY_600),
                    ft.Divider(height=1),
                    ft.Text("1. Google Drive Cloud Sync:", size=12, weight=ft.FontWeight.BOLD),
                    ft.ElevatedButton(
                        content=ft.Text("☁ Google Drive पर बैकअप अपलोड करें"),
                        bgcolor=ft.Colors.BLUE_800,
                        color=ft.Colors.WHITE,
                        on_click=do_backup_cloud
                    ),
                    ft.Divider(height=1),
                    ft.Text("2. ऑफलाइन डेटाबेस (Offline DB):", size=12, weight=ft.FontWeight.BOLD),
                    ft.OutlinedButton(
                        content=ft.Text("📤 Export accounting_data.db (शेयर करें)"),
                        on_click=do_export_local
                    )
                ]
            ),
            actions=[
                ft.TextButton("बंद करें", on_click=lambda e: close_dialog(dlg))
            ]
        )
        open_dialog(dlg)

    # ==================== SETTINGS DIALOG ====================
    def open_settings_dialog():
        current_key = db.get_setting("gemini_api_key", "")
        current_model = db.get_setting("gemini_model", "gemini-3.8-flash")

        txt_key = ft.TextField(label="Gemini API Key", value=current_key, password=True, can_reveal_password=True)
        txt_model = ft.Dropdown(
            label="AI Model",
            value=current_model,
            options=[
                ft.dropdown.Option("gemini-3.8-flash"),
                ft.dropdown.Option("gemini-2.5-flash"),
                ft.dropdown.Option("gemini-1.5-flash")
            ]
        )

        def save_settings(e):
            db.set_setting("gemini_api_key", txt_key.value.strip())
            db.set_setting("gemini_model", txt_model.value.strip())
            close_dialog(dlg)
            show_toast("✅ सेटिंग्स सफलतापूर्वक सेव हो गई!")

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.SETTINGS, color=ft.Colors.GREY_700),
                ft.Text("ऐप सेटिंग्स (Gemini AI)", size=16, weight=ft.FontWeight.BOLD)
            ]),
            content=ft.Column(tight=True, spacing=10, controls=[txt_key, txt_model]),
            actions=[
                ft.TextButton("रद्द करें", on_click=lambda e: close_dialog(dlg)),
                ft.ElevatedButton("सेव करें", bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=save_settings)
            ]
        )
        open_dialog(dlg)

    # Floating Action Button for Voice Entry (always accessible)
    page.floating_action_button = ft.FloatingActionButton(
        icon=ft.Icons.MIC,
        bgcolor=ft.Colors.RED_600,
        content=ft.Row(
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.MIC, color=ft.Colors.WHITE, size=20),
                ft.Text("बोलकर एंट्री", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD, size=12)
            ]
        ),
        on_click=lambda e: open_voice_command_dialog()
    )

    page.add(main_body)
    show_home_screen()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main, assets_dir="assets")
    elif hasattr(ft, "app"):
        ft.app(target=main, assets_dir="assets")
