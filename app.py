#from flask_socketio import SocketIO, join_room, emit
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

from collections import defaultdict

# Load environment variables from .env
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure app using environment variables
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ✅ Inject engine options to prevent idle disconnects and improve performance
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 2,
    "pool_timeout": 30
}


from datetime import timedelta

# Make sessions last longer
app.permanent_session_lifetime = timedelta(hours=5)


# Initialize database
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager(app)

login_manager.login_view = "login"               # endpoint to redirect unauthenticated users
login_manager.login_message_category = "danger" # flash message category
login_manager.session_protection = "strong"     # adds extra security to sessions


# Initialize Flask-Migrate
migrate = Migrate(app, db)

# Socket.IO initialization — must come AFTER app
#socketio = SocketIO(app)


# Register the currency filter for formatting prices
@app.template_filter('currency')
def format_currency(value):
    return f"${value:,.2f}"


# Define Product model
class Product(db.Model):
    __tablename__ = 'product'
    __table_args__ = (
        db.UniqueConstraint('identification_number', 'location', name='uq_product_identification_per_location'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    identification_number = db.Column(db.String(100), nullable=False)
    in_stock = db.Column(db.Integer, nullable=False)
    selling_price = db.Column(db.Float, nullable=True)
    location = db.Column(db.String(100), nullable=False)

    # Relationships
    inventory_items = db.relationship('Inventory', backref='product', lazy=True)
    orders = db.relationship('Order', backref='product', lazy=True)


# Define Inventory model
class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity_in_stock = db.Column(db.Integer, nullable=False, default=0)
    quantity_sold = db.Column(db.Integer, nullable=False, default=0)
    in_stock = db.Column(db.Integer, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Relationships
    seller = db.relationship('User', backref='inventory_items')



# Define Order model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    selling_price = db.Column(db.Float, nullable=True)
    amount = db.Column(db.Float, nullable=True)
    in_stock = db.Column(db.Integer, nullable=False)
    date_sold = db.Column(db.DateTime, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # ✅ NEW COLUMN
    location = db.Column(db.String(100), nullable=True)  # Added location

    # ✅ RELATIONSHIP
    seller = db.relationship('User', backref='orders')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

"""
# Define User model for authentication (admin/seller)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # "admin" or "seller"
    location = db.Column(db.String(100), nullable=True)
"""

# Define User model for authentication (admin/seller)
class User(UserMixin, db.Model):
    __tablename__ = "user"   # ✅ Force SQLAlchemy to map to "user" table

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="seller")   # seller | admin | baker
    location = db.Column(db.String(100), nullable=True)


class StockHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # who made the change
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    change_amount = db.Column(db.Integer)  # can be + or -
    reason = db.Column(db.String(255))  # optional note
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('User', foreign_keys=[admin_id])
    seller = db.relationship('User', foreign_keys=[seller_id])
    product = db.relationship('Product')


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    sender_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False
    )
    receiver_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False
    )
    
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    is_read = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', foreign_keys=[sender_id], passive_deletes=True)
    receiver = db.relationship('User', foreign_keys=[receiver_id], passive_deletes=True)



from datetime import datetime, timezone
import pytz

utc_time = datetime.now(timezone.utc)
local_tz = pytz.timezone('Africa/Lagos')  # adjust to your timezone
local_time = utc_time.astimezone(local_tz)
date_sent_str = local_time.strftime("%Y-%m-%d %H:%M:%S")

"""
class BakerInventory(db.Model):  
    __tablename__ = "baker_inventory"   # explicitly set table name

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    purchases = db.Column(db.JSON, nullable=False)   # first section (qty & cost bought)
    breads = db.Column(db.JSON, nullable=False)      # second section (qty used per bread type)
    date_sent = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')

    seller = db.relationship('User', backref='baker_inventories')
"""
import json

class BakerInventory(db.Model):
    __tablename__ = "baker_inventory"

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    purchases = db.Column(db.JSON, nullable=False)   # e.g. list/dict with cost
    breads = db.Column(db.JSON, nullable=False)      # e.g. list/dict with ingredients
    date_sent = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')

    seller = db.relationship('User', backref='baker_inventories')

    @property
    def total_purchase_cost(self):
        if not self.purchases:
            return 0
        if isinstance(self.purchases, dict):
            return sum((item.get("cost", 0) or 0) for item in self.purchases.values())
        elif isinstance(self.purchases, list):
            return sum((item.get("cost", 0) or 0) for item in self.purchases)
        return 0

    @property
    def total_usage_cost(self):
        if not self.breads:
            return 0

        total = 0
        if isinstance(self.breads, list):
            for bread in self.breads:
                # If bread has ingredients, loop through them
                ingredients = bread.get("ingredients", [])
                for ing in ingredients:
                    total += ing.get("usage_cost", ing.get("cost", 0)) or 0
        elif isinstance(self.breads, dict):
            ingredients = self.breads.get("ingredients", [])
            for ing in ingredients:
                total += ing.get("usage_cost", ing.get("cost", 0)) or 0

        return total


from datetime import datetime

class CreditSale(db.Model):
    __tablename__ = 'credit_sale'  # optional but good practice

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(150), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)  # optional
    
    bread_type = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    amount_owing = db.Column(db.Float, nullable=False)
    date_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # ForeignKey to User table (seller)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller = db.relationship('User', backref=db.backref('credit_sales', lazy=True))

    fully_paid = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<CreditSale {self.customer_name} - {self.bread_type} - ₦{self.amount_owing}>"




import pandas as pd
from io import BytesIO
from flask import send_file

from datetime import datetime, timedelta

@app.route('/admin/export-stock-history', methods=['GET', 'POST'])
def export_stock_history_excel():
    if not current_user.is_authenticated or current_user.role != 'admin':
        return "Unauthorized", 403

    # Get filter values from request arguments or defaults
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    admin_id = request.args.get('admin_id', '')
    product_id = request.args.get('product_id', '')
    location = request.args.get('location', '')

    query = StockHistory.query

    # Apply filters
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(StockHistory.created_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
        query = query.filter(StockHistory.created_at <= end_date)
    if admin_id:
        query = query.filter(StockHistory.admin_id == admin_id)
    if product_id:
        query = query.filter(StockHistory.product_id == product_id)
    if location:
        query = query.join(Product).filter(Product.location == location)

    # Explicitly load product and its location field
    stock_changes = query.join(Product).all()  # Ensures that the Product model is loaded

    if not stock_changes:
        return "No stock history records found to export.", 404

    # Prepare data for Excel export
    data = []
    for entry in stock_changes:
        location_name = ''
        if entry.product:  # Ensure the product is loaded
            location_name = getattr(entry.product, 'location', '')  # Get location from product
        data.append({
            'Date': entry.created_at.strftime('%Y-%m-%d %H:%M:%S') if entry.created_at else '',
            'Admin': getattr(entry.admin, 'username', entry.admin_id) if entry.admin else entry.admin_id,
            'Product': getattr(entry.product, 'name', entry.product_id) if entry.product else entry.product_id,
            'Seller': getattr(entry.seller, 'username', entry.seller_id) if entry.seller else entry.seller_id,
            'Change': entry.change_amount if entry.change_amount is not None else '',
            'Reason': entry.reason or '',
            'Location': location_name  # Ensure location is added
        })

    # Create Excel file
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Stock History')

    output.seek(0)
    return send_file(
        output,
        download_name='stock_history_filtered.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )





# Load user for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    #eturn User.query.get(int(user_id))
    return db.session.get(User, int(user_id))



@app.route('/')
def index():
    return render_template('index.html')


import os
import json
import base64
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = os.getenv('GOOGLE_SHEET_ID')
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")  # local dev only
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def authenticate_google_sheets():
    """
    Authenticate with Google Sheets API using:
    - SERVICE_ACCOUNT_JSON (Base64 encoded, Render env var)
    - SERVICE_ACCOUNT_FILE (local file for dev)
    """
    try:
        service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
        credentials = None

        # 🔹 Render: decode Base64 → JSON
        if service_account_json:
            decoded = base64.b64decode(service_account_json).decode("utf-8")
            info = json.loads(decoded)

            # Fix private key newlines
            if "private_key" in info:
                info["private_key"] = info["private_key"].replace("\\n", "\n")

            credentials = Credentials.from_service_account_info(info, scopes=SCOPES)

        # 🔹 Local: use the service_account.json file
        elif SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

        else:
            raise ValueError("No SERVICE_ACCOUNT_JSON or SERVICE_ACCOUNT_FILE found")

        return build("sheets", "v4", credentials=credentials)

    except Exception as e:
        print(f"❌ Error during Google Sheets authentication: {e}")
        return None


# Test once
if authenticate_google_sheets():
    print("✅ Google Sheets service ready")
else:
    print("❌ Google Sheets service failed to initialize")



def get_google_sheet_data_by_location(sheet_name):
    service = authenticate_google_sheets()

    # 🔹 Fetch spreadsheet metadata (list of sheet/tab names)
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    available_sheets = [s['properties']['title'] for s in spreadsheet['sheets']]

    # 🔹 Check if the requested sheet_name exists
    if sheet_name not in available_sheets:
        print(f"❌ Sheet '{sheet_name}' not found in spreadsheet. Available: {available_sheets}")
        return []

    # ✅ If sheet exists, fetch values
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A2:D"
    ).execute()

    values = result.get('values', [])
    if not values:
        print(f"No data found in sheet {sheet_name}")
        return []

    sellers = User.query.filter(
        User.location.ilike(sheet_name),
        User.role == 'seller'
    ).all()
    if not sellers:
        print(f"No sellers found for location: {sheet_name}")
        return []

    formatted_data = []
    for row in values:
        name = row[0] if len(row) > 0 else ''
        identification_number = row[1] if len(row) > 1 else ''
        price = float(row[2]) if len(row) > 2 and row[2] else 0.0
        in_stock = 0
        if len(row) > 3:
            try:
                in_stock = int(row[3]) if row[3] not in [None, '', 'null', 'None'] else 0
            except ValueError:
                in_stock = 0

        formatted_data.append({
            'name': name,
            'identification_number': identification_number,
            'price': price,
            'in_stock': in_stock,
        })

    inventory_to_add = []

    for product_data in formatted_data:
        existing = Product.query.filter_by(
            identification_number=product_data['identification_number'],
            location=sheet_name
        ).first()

        if not existing:
            # Create new product if it doesn't exist
            product = Product(
                name=product_data['name'],
                identification_number=product_data['identification_number'],
                price=product_data['price'],
                selling_price=None,
                location=sheet_name,
                in_stock=product_data['in_stock']
            )
            db.session.add(product)
            db.session.commit()

            for seller in sellers:
                if seller.location == sheet_name:
                    inventory = Inventory(
                        product_id=product.id,
                        seller_id=seller.id,
                        quantity_in_stock=product_data['in_stock'],
                        in_stock=product_data['in_stock']
                    )
                    inventory_to_add.append(inventory)

        else:
            # When updating product, only increase stock if sheet stock is higher
            existing.name = product_data['name']
            existing.price = product_data['price']
            if product_data['in_stock'] > existing.in_stock:
                existing.in_stock += (product_data['in_stock'] - existing.in_stock)
            db.session.commit()

            for seller in sellers:
                if seller.location == sheet_name:
                    existing_inventory = Inventory.query.filter_by(
                        product_id=existing.id,
                        seller_id=seller.id
                    ).first()

                    if existing_inventory:
                        # Add stock from sheet if necessary, don't overwrite reduced stock
                        if product_data['in_stock'] > existing_inventory.quantity_in_stock:
                            difference = product_data['in_stock'] - existing_inventory.quantity_in_stock
                            existing_inventory.quantity_in_stock += difference
                            existing_inventory.in_stock += difference
                    else:
                        # Create new seller inventory
                        inventory = Inventory(
                            product_id=existing.id,
                            seller_id=seller.id,
                            quantity_in_stock=product_data['in_stock'],
                            in_stock=product_data['in_stock']
                        )
                        inventory_to_add.append(inventory)

    db.session.add_all(inventory_to_add)
    db.session.commit()

    print(f"✅ Imported and updated {len(formatted_data)} products for {sheet_name}")
    return formatted_data



@app.route('/import-products', methods=['POST'])
def import_all_products():
    # Get the location from the form, or default to "Accra" if not specified
    location = request.form.get('location', 'Ikota Complex')  # Default to 'Accra' if not provided

    try:
        # Get the sheet data for the given location
        sheet_data = get_google_sheet_data_by_location(location)
        
        if not sheet_data:
            flash(f"No data found for location {location}. Please check the sheet name.", "danger")
            return redirect(url_for('admin_dashboard'))

        # Process the sheet data and update the admin dashboard
        flash(f"Successfully imported products for {location}!", "success")

    except Exception as e:
        # Handle any unexpected errors
        flash(f"An error occurred while importing data: {str(e)}", "danger")

    return redirect(url_for('admin_dashboard'))



@app.route('/products/<location>')
def get_products_by_seller_location(location):
    seller = User.query.filter_by(location=location.lower(), role='seller').first()
    if not seller:
        return jsonify([])

    products = Product.query.filter_by(seller_id=seller.id).all()
    return jsonify([
        {
            "name": p.name,
            "price": p.price,
            "stock": p.in_stock,
            "id": p.identification_number
        } for p in products
    ])


@app.route('/admin/products')
def get_all_products_for_admin():
    # Optional: Add admin-only check here if you have authentication
    products = Product.query.all()
    
    return jsonify([
        {
            "name": p.name,
            "price": p.price,
            "stock": p.in_stock,
            "id": p.identification_number,
            "seller": p.seller.username if p.seller else "Unknown",
            "location": p.seller.location if p.seller else "Unknown"
        } for p in products
    ])



def update_google_sheet_stock(sheet_name, identification_number, new_stock):
    service = authenticate_google_sheets()
    sheet = service.spreadsheets()

    try:
        # Read current data from the sheet
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!A2:D"
        ).execute()

        values = result.get('values', [])
        if not values:
            print(f"No data found in sheet {sheet_name}")
            return

        # Locate the row with matching product ID
        row_number = None
        for idx, row in enumerate(values, start=2):  # start=2 because data starts from row 2
            if len(row) > 1 and row[1] == identification_number:
                row_number = idx
                break

        if row_number:
            update_range = f"{sheet_name}!D{row_number}"
            update_body = {
                "values": [[str(new_stock)]]
            }

            sheet.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=update_range,
                valueInputOption="RAW",
                body=update_body
            ).execute()

            print(f"✅ Google Sheet updated: {sheet_name} -> Row {row_number} -> Stock: {new_stock}")
        else:
            print(f"❌ Product with ID {identification_number} not found in sheet {sheet_name}.")

    except Exception as e:
        print(f"❌ Error updating Google Sheet: {e}")




@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    product = Product.query.get(product_id)
    if product:
        try:
            # Delete all associated inventory
            inventories = Inventory.query.filter_by(product_id=product.id).all()
            for inv in inventories:
                db.session.delete(inv)

            # Delete all associated orders
            orders = Order.query.filter_by(product_id=product.id).all()
            for order in orders:
                db.session.delete(order)

            # Finally, delete the product
            db.session.delete(product)
            db.session.commit()

            flash('Product successfully deleted!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting product: {str(e)}', 'danger')
    else:
        flash('Product not found!', 'danger')

    return redirect(url_for('admin_dashboard'))


@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('login'))

    # Handle import from Google Sheets
    if request.method == 'POST' and 'import_button' in request.form:
        location = request.form.get('location', '').strip()

        if not location:
            flash("Please select a location before importing data.", "danger")
            return redirect(url_for('admin_dashboard'))

        try:
            sheet_data = get_google_sheet_data_by_location(location)
            if not sheet_data:
                flash(f"No data found for location {location}.", "danger")
                return redirect(url_for('admin_dashboard'))

            for row in sheet_data:
                name = row.get('name', '').strip()
                identification_number = row.get('identification_number', '').strip()
                price = float(row.get('price', 0.0))
                in_stock = int(row.get('in_stock', 0))

                if not name or not identification_number:
                    continue  # skip incomplete rows

                existing_product = Product.query.filter_by(
                    identification_number=identification_number
                ).first()

                if existing_product:
                    continue  # skip duplicate

                product = Product(
                    name=name,
                    identification_number=identification_number,
                    price=price,
                    selling_price=None,
                    location=location
                )
                db.session.add(product)
                db.session.commit()

                sellers = User.query.filter(
                    User.location.ilike(f"%{location}%"),
                    User.role == 'seller'
                ).all()

                if not sellers:
                    flash(f"No sellers found for location: {location}", "warning")
                    continue

                for seller in sellers:
                    inventory = Inventory(
                        product_id=product.id,
                        seller_id=seller.id,
                        quantity_in_stock=10 if in_stock else 0
                    )
                    db.session.add(inventory)

            db.session.commit()
            flash(f"Successfully imported data for location {location}!", "success")

        except Exception as e:
            flash(f"An error occurred while importing data: {str(e)}", "danger")

    # Search logic
    search_query = request.args.get('search', '').strip()
    if search_query:
        products = Product.query.filter(Product.name.ilike(f"%{search_query}%")).all()
    else:
        products = Product.query.all()

    inventories = {inv.product_id: inv for inv in Inventory.query.all()}
    orders = Order.query.all()

    # -----------------------------
    # Prepare orders for profit/loss
    # -----------------------------
    order_list = []
    for order in orders:
        product = Product.query.get(order.product_id)
        purchase_cost = getattr(product, 'purchase_cost', 0)  # cost to buy
        usage_cost = getattr(product, 'usage_cost', 0)       # other expenses
        order_list.append({
            "product_name": product.name if product else "Unknown",
            "identification_number": product.identification_number if product else "N/A",
            "in_stock": inventories.get(product.id).quantity_in_stock if product and inventories.get(product.id) else 0,
            "quantity_sold": order.quantity,
            "selling_price": order.selling_price,
            "amount": order.amount or 0,
            "purchase_cost": purchase_cost,
            "usage_cost": usage_cost,
            "profit_loss": (order.amount or 0) - (purchase_cost + usage_cost),
            "seller": order.seller.username if order.seller else "Unknown",
            "location": getattr(order, "location", "N/A"),
            "date_sold": getattr(order, "date_sold", None),
        })

    # -----------------------------
    # Financial summary
    # -----------------------------
    bakeries = BakerInventory.query.filter_by(status='approved').all()

    # fallback if model has no methods yet
    def safe_attr(obj, attr, default=0):
        return getattr(obj, attr, default) or 0

    total_purchase_cost = sum(safe_attr(b, "total_purchase_cost") for b in bakeries)
    total_usage_cost = sum(safe_attr(b, "total_usage_cost") for b in bakeries)
    total_sales = sum(order["amount"] for order in order_list)
    profit_loss = total_sales - (total_purchase_cost + total_usage_cost)

    admins = User.query.filter_by(role='admin').all()
    admin_name = current_user.username

    return render_template(
        'admin_dashboard.html',
        products=products,
        inventories=inventories,
        orders=order_list,
        user_role='admin',
        search_query=search_query,
        admins=admins,
        admin_name=admin_name,

        # ✅ pass summary values to template
        total_sales=total_sales,
        total_purchase_cost=total_purchase_cost,
        total_usage_cost=total_usage_cost,
        profit_loss=profit_loss
    )


"""
@app.route('/baker-inventory')
@login_required
def baker_inventory_page():  # renamed function to avoid conflict
    # Pass seller info to template
    return render_template('baker_inventory.html', seller_details=current_user)
"""

@app.route("/baker-inventory")
@login_required
def baker_inventory_page():
    if current_user.role != "baker":
        flash("🚫 You don’t have permission to access the Bakery Inventory.", "error")
        return redirect(url_for("seller_dashboard"))

    # 👇 Pass current_user as seller_details
    return render_template("baker_inventory.html", seller_details=current_user)


@app.route("/credit-sales", methods=["GET", "POST"])
@login_required
def credit_sales():
    # No role restriction, allow all logged-in users
    if request.method == "POST":
        sale_id = request.form.get("sale_id")
        customer_name = request.form.get("customer_name")
        customer_phone = request.form.get("customer_phone")  # optional
        bread_type = request.form.get("bread_type")
        quantity = request.form.get("quantity")
        amount_owing = float(request.form.get("amount_owing"))

        if sale_id:  # updating existing record
            sale = CreditSale.query.get(int(sale_id))
            if sale and sale.seller_id == current_user.id:
                sale.amount_owing = amount_owing
                if customer_phone is not None:
                    sale.customer_phone = customer_phone
                sale.fully_paid = amount_owing <= 0
                db.session.commit()
                flash("Record updated successfully!", "success")
        else:  # creating new record
            new_sale = CreditSale(
                customer_name=customer_name,
                customer_phone=customer_phone,
                bread_type=bread_type,
                quantity=int(quantity),
                amount_owing=amount_owing,
                seller_id=current_user.id
            )
            db.session.add(new_sale)
            db.session.commit()
            flash("New credit record saved!", "success")

    sales = CreditSale.query.filter_by(seller_id=current_user.id).order_by(CreditSale.date_time.desc()).all()
    return render_template("credit_sales.html", sales=sales)


@app.route("/admin/credit-sales")
@login_required
def admin_credit_sales():
    # Remove admin check, allow all logged-in users to view
    sales = CreditSale.query.order_by(CreditSale.date_time.desc()).all()
    return render_template("admin_credit_sales.html", sales=sales)


@app.route("/update-credit-sale/<int:sale_id>", methods=["POST"])
@login_required
def update_credit_sale(sale_id):
    sale = CreditSale.query.get_or_404(sale_id)
    new_amount = float(request.form["amount_owing"])
    new_phone = request.form.get("customer_phone")  # optional
    sale.amount_owing = new_amount
    if new_phone is not None:
        sale.customer_phone = new_phone
    sale.fully_paid = new_amount <= 0
    db.session.commit()
    flash("Record updated successfully!", "success")
    return redirect(url_for("credit_sales"))


@app.route("/delete-credit-sale/<int:sale_id>", methods=["POST"])
@login_required
def delete_credit_sale(sale_id):
    sale = CreditSale.query.get_or_404(sale_id)

    # Only delete if fully paid
    if not sale.fully_paid:
        flash("Debt not cleared yet.", "danger")
        # Always stay on admin page
        return redirect(url_for("admin_credit_sales"))

    db.session.delete(sale)
    db.session.commit()
    flash("Cleared debt record successfully!", "success")

    # Always redirect back to admin credit sales page
    return redirect(url_for("admin_credit_sales"))




@app.route('/seller_dashboard', methods=['GET', 'POST'])
@login_required
def seller_dashboard():
    if current_user.role != 'seller':
        return redirect(url_for('/login'))

    # Fetch only products matching seller's location
    products = Product.query.filter_by(location=current_user.location).all()

    # Fetch inventories only for current seller and relevant products
    inventory_records = Inventory.query.filter(
        Inventory.seller_id == current_user.id,
        Inventory.product_id.in_([p.id for p in products])
    ).all()
    inventories = {inv.product_id: inv for inv in inventory_records}

    # Seller details
    seller_details = {
        "name": current_user.username,
        "location": current_user.location,
        "role": current_user.role
    }

    if request.method == 'POST':
        for product in products:
            selling_price = request.form.get(f'selling_price_{product.id}')
            quantity = request.form.get(f'quantity_{product.id}', 0)
            if selling_price and quantity:
                selling_price = float(selling_price)
                quantity = int(quantity)

                # Update product's selling price if not already set
                product.selling_price = selling_price
                db.session.add(product)

                # Create new order
                order = Order(
                    product_id=product.id,
                    quantity=quantity,
                    selling_price=selling_price,
                    amount=selling_price * quantity
                )
                db.session.add(order)

                # Update inventory for current seller
                inventory = inventories.get(product.id)
                if inventory:
                    inventory.quantity_in_stock = max(0, inventory.quantity_in_stock - quantity)
                    db.session.add(inventory)

        db.session.commit()
        flash('Selling Prices, Quantities, and Orders Updated!', 'success')

    return render_template(
        'seller_dashboard.html',
        products=products,
        inventories=inventories,
        seller_details=seller_details,
        user_role='seller'
    )


import time
start = time.time()
"""
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)  # keep session alive
            session.permanent = True          # make session permanent

            flash('Login successful!', 'success')

            # Redirect user based on role
            if user.role.lower() == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role.lower() == 'seller':
                return redirect(url_for('seller_dashboard'))
            elif user.role.lower() == 'baker':
                return redirect(url_for('baker_inventory_page'))

            return redirect(url_for('index'))  # fallback

        flash('Invalid login credentials', 'danger')

    return render_template('login.html')


print("Login took", time.time() - start, "seconds")
"""

import pytz
from datetime import datetime

# Simple in-memory login tracker
login_records = []

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            session.permanent = True

            flash('Login successful!', 'success')

            # ✅ Log login in memory with Lagos time
            lagos_tz = pytz.timezone("Africa/Lagos")
            local_time = datetime.now(lagos_tz).strftime("%Y-%m-%d %H:%M:%S")

            login_records.append({
                "username": user.username,
                "role": user.role,
                "login_time": local_time
            })

            # Redirect based on role
            if user.role.lower() == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role.lower() == 'seller':
                return redirect(url_for('seller_dashboard'))
            elif user.role.lower() == 'baker':
                return redirect(url_for('baker_inventory_page'))

            return redirect(url_for('index'))

        flash('Invalid login credentials', 'danger')

    return render_template('login.html')


@app.route('/admin/login-records')
@login_required
def admin_login_records():
    if current_user.role.lower() != 'admin':
        flash("Access denied", "danger")
        return redirect(url_for("index"))

    return render_template("admin_login_records.html", records=login_records)


@app.route('/admin/clear-login-records', methods=['POST'])
@login_required
def clear_login_records():
    if current_user.role.lower() != 'admin':
        flash("Access denied", "danger")
        return redirect(url_for("index"))

    login_records.clear()
    flash("Login records cleared!", "success")
    return redirect(url_for("admin_login_records"))




@app.route('/admin/change-password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        username = request.form['username']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        user = User.query.filter_by(username=username, role='admin').first()

        if not user:
            flash('Admin user not found.', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
        else:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password changed successfully. Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('change_password.html')




# Route for user logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/order/<int:product_id>', methods=['POST'])
@login_required
def place_order(product_id):
    if current_user.role != 'seller':
        return redirect(url_for('login'))

    quantity = int(request.form['quantity'])
    selling_price = float(request.form['selling_price'])

    # Fetch the product and inventory details
    product = Product.query.get(product_id)
    inventory = Inventory.query.filter_by(product_id=product_id, seller_id=current_user.id).first()

    if not product or not inventory:
        flash('Product or inventory not found.', 'danger')
        return redirect(url_for('seller_dashboard'))

    # Check if there is enough stock
    if inventory.quantity_in_stock >= quantity:
        # Deduct stock from the seller's inventory
        inventory.quantity_in_stock -= quantity
        inventory.quantity_sold += quantity
        db.session.commit()

        # Update global product stock
        product.in_stock -= quantity
        db.session.commit()
        
        update_google_sheet_stock(product.location, product.identification_number, product.in_stock)

        total_amount = quantity * selling_price

        # Create the new order
        new_order = Order(
            product_id=product_id,
            quantity=quantity,
            status="completed",
            selling_price=selling_price,
            amount=total_amount
        )
        db.session.add(new_order)
        db.session.commit()

        # Update admin's inventory with reduced stock
        admin_inventory = Inventory.query.filter_by(product_id=product_id).all()
        for inventory in admin_inventory:
            inventory.in_stock = inventory.quantity_in_stock  # Reflect the reduced stock for admin
        db.session.commit()

        flash(f"Order placed successfully for {product.name}!", 'success')
    else:
        flash('Not enough stock available.', 'danger')

    return redirect(url_for('seller_dashboard'))

"""
@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if current_user.role != 'admin':
        flash("Access denied. Only admins can register new users.", "danger")
        return redirect(url_for('login'))

    # Full list of valid cities
    ghana_cities = [
        'Ikota', 'Ajah', 'Badore'  # Only normalized names
    ]

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        role = request.form['role'].strip().lower()
        location_input = request.form.get('location', '').strip()

        # Normalize location
        if 'ikota' in location_input.lower():
            normalized_location = 'Ikota'
        else:
            normalized_location = location_input

        # Validate location
        if normalized_location not in ghana_cities:
            flash('Invalid location specified. Please select a valid city.', 'danger')
            return redirect(url_for('register'))

        # Validate role
        if role not in ['seller', 'admin']:
            flash('Invalid role specified.', 'danger')
            return redirect(url_for('register'))

        # Check if username exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))

        # Hash password and create user
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password, role=role, location=normalized_location)
        db.session.add(new_user)
        db.session.commit()

        flash(f'{username} registered successfully as {role} in {normalized_location}!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('register.html', ghana_cities=ghana_cities)

"""
@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if current_user.role != "admin":
        flash("Access denied. Only admins can register new users.", "danger")
        return redirect(url_for("login"))

    ghana_cities = ["Ikota", "Ajah", "Badore"]

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"].strip().lower()
        location_input = request.form.get("location", "").strip()

        print("📌 DEBUG: Received data →", username, role, location_input)

        # Normalize location
        if "ikota" in location_input.lower():
            normalized_location = "Ikota"
        else:
            normalized_location = location_input

        print("📌 DEBUG: Normalized location →", normalized_location)

        if normalized_location not in ghana_cities:
            print("❌ Invalid location")
            flash("Invalid location specified.", "danger")
            return redirect(url_for("register"))

        if role not in ["seller", "admin", "baker"]:
            print("❌ Invalid role")
            flash("Invalid role specified.", "danger")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print("❌ Username exists already")
            flash("Username already exists!", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password, method="pbkdf2:sha256")
        new_user = User(username=username, password=hashed_password, role=role, location=normalized_location)
        db.session.add(new_user)
        db.session.commit()

        print("✅ User registered successfully →", username, role, normalized_location)

        flash(f"{username} registered successfully as {role} in {normalized_location}!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("register.html", ghana_cities=ghana_cities)



@app.route('/delete-sales-by-location', methods=['POST'])
@login_required
def delete_sales_by_location():
    if current_user.role != 'admin':
        flash("Access denied.", "danger")
        return redirect(url_for('admin_dashboard'))

    location = request.form.get('location')
    if not location:
        flash("Location is required.", "danger")
        return redirect(url_for('view_orders'))

    try:
        # Fetch all orders linked to products at that location
        orders_to_delete = Order.query.join(Product).filter(Product.location == location).all()
        for order in orders_to_delete:
            db.session.delete(order)
        db.session.commit()
        flash(f"All sales records for {location} deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Error deleting sales records: " + str(e), "danger")

    return redirect(url_for('view_orders'))


@app.route('/send-order', methods=['POST'])
@login_required
def send_order():
    data = request.get_json()

    product_id = data.get('product_id')
    quantity = data.get('quantity')
    selling_price = data.get('selling_price')
    amount = data.get('amount')
    date_sold = data.get('date_sold')

    # Ensure current user is a seller
    if current_user.role != 'seller':
        return jsonify({'success': False, 'error': 'Only sellers can create orders'}), 403

    # Validate required fields
    if not all([product_id, quantity, selling_price, amount, date_sold]):
        return jsonify({'success': False, 'error': 'All fields are required'}), 400

    try:
        # Convert data types
        quantity = int(quantity)
        selling_price = float(selling_price)
        amount = float(amount)
        date_sold_dt = datetime.strptime(date_sold, '%Y-%m-%dT%H:%M:%S.%fZ')

        # Get product
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404

        # Check stock availability
        if product.in_stock < quantity:
            return jsonify({'success': False, 'error': 'Not enough stock available'}), 400

        # Update stock
        product.in_stock -= quantity

        # Sync updated stock with Google Sheet
        update_google_sheet_stock(product.location, product.identification_number, product.in_stock)

        # Save full seller location for admin visibility
        full_location = current_user.location.strip()

        # Create the order
        order = Order(
            product_id=product_id,
            quantity=quantity,
            selling_price=selling_price,
            amount=amount,
            date_sold=date_sold_dt,
            in_stock=product.in_stock,
            seller_id=current_user.id,
            location=full_location  # full location saved
        )

        db.session.add(order)
        db.session.commit()

        return jsonify({'success': True, 'remaining_stock': product.in_stock}), 200

    except Exception as e:
        db.session.rollback()
        print("Error saving order:", e)
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/view_users')
@login_required
def view_users():
    if current_user.role != 'admin':
        flash("Access denied. Only admins can view users.", "danger")
        return redirect(url_for('index'))

    users = User.query.all()  # fetch all users
    return render_template("view_users.html", users=users)




# Admin: Select location to view orders
@app.route('/admin/select_order_location', methods=['GET', 'POST'])
def select_order_location():
    # ✅ Get distinct locations from existing orders
    locations = [row[0] for row in db.session.query(Order.location).distinct().all() if row[0]]

    if request.method == 'POST':
        selected_location = request.form.get('location', '').strip()
        return redirect(url_for('view_orders', location=selected_location))

    return render_template('select_order_location.html', locations=locations)





@app.route('/admin/clear-inventories', methods=['POST'])
@login_required
def clear_inventories():
    try:
        # Delete all entries from BakerInventory
        num_deleted = BakerInventory.query.delete()  # note: class name, not string
        db.session.commit()
        flash(f"✅ Cleared {num_deleted} baker inventory submissions.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error deleting inventories: {str(e)}", "error")
    return redirect(url_for('view_baker_inventory'))



# Admin: View Orders
@app.route('/admin/orders')
def view_orders():
    selected_location = request.args.get('location')
    if not selected_location:
        return redirect(url_for('select_order_location'))

    # Filter orders
    orders = (
        Order.query
        .filter(Order.location.ilike(f"%{selected_location}%"))
        .all()
    )

    # Collect data for charts and seller/product performance
    sales_data = []
    seller_performance = defaultdict(int)
    product_sales = defaultdict(int)

    for order in orders:
        sales_data.append({
            "product_name": order.product.name if order.product else "Unknown",
            "quantity_sold": order.quantity or 0,
            "total_price": order.amount or 0,
            "sale_date": order.created_at.strftime("%Y-%m-%d") if order.created_at else None
        })

        if order.seller:
            seller_performance[order.seller.id] += order.quantity or 0

        if order.product:
            product_sales[order.product.name] += order.quantity or 0

    # Best seller
    if seller_performance:
        best_seller_id = max(seller_performance.items(), key=lambda x: x[1])[0]
        best_seller_name = User.query.get(best_seller_id).username
        best_seller_sales = seller_performance[best_seller_id]
    else:
        best_seller_name = "N/A"
        best_seller_sales = 0

    # Top 5 products
    top_5_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]

    # ✅ Financial Summary (fixed)
    bakeries = BakerInventory.query.filter_by(status='approved').all()

    total_purchase_cost = sum(b.total_purchase_cost for b in bakeries)
    total_usage_cost = sum(b.total_usage_cost for b in bakeries)  # 🔑 usage cost pulled same way
    total_sales = sum(order.amount or 0 for order in orders)

    # 🔥 Profit/Loss now based ONLY on usage cost
    profit_loss = total_sales - total_usage_cost

    return render_template(
        'admin_orders.html',
        orders=orders,
        selected_location=selected_location,
        sales_data=sales_data,
        best_seller_name=best_seller_name,
        best_seller_sales=best_seller_sales,
        top_5_products=top_5_products,
        total_sales=total_sales,
        total_purchase_cost=total_purchase_cost,  # still shown separately
        total_usage_cost=total_usage_cost,        # ✅ now displayed
        profit_loss=profit_loss                   # ✅ uses usage cost only
    )




@app.route('/export/financial-summary')
def export_financial_summary():
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    import io
    from flask import send_file

    # Calculate totals
    bakeries = BakerInventory.query.filter_by(status='approved').all()
    orders = Order.query.all()

    total_sales = sum(order.amount or 0 for order in orders)
    total_purchase_cost = sum(b.total_purchase_cost for b in bakeries)
    total_usage_cost = sum(b.total_usage_cost for b in bakeries)
    profit_loss = total_sales - total_usage_cost

    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    p.setFont("Helvetica-Bold", 14)
    p.drawString(100, 750, "Financial Summary")

    p.setFont("Helvetica", 12)
    p.drawString(100, 720, f"Total Sales: ₦{total_sales:.2f}")
    p.drawString(100, 700, f"Purchase Cost: ₦{total_purchase_cost:.2f}")
    p.drawString(100, 680, f"Usage Cost: ₦{total_usage_cost:.2f}")
    p.drawString(100, 660, f"Profit/Loss: ₦{profit_loss:.2f}")

    p.showPage()
    p.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="financial_summary.pdf",
        mimetype="application/pdf"
    )


@app.route('/delete_all_products', methods=['POST'])
def delete_all_products():
    try:
        # First delete dependent inventory rows
        Inventory.query.delete()

        # Now delete products
        num_deleted = Product.query.delete()
        db.session.commit()
        flash(f"All {num_deleted} products and related inventory deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Error deleting products: " + str(e), "danger")
    return redirect(url_for('admin_dashboard'))


@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('view_users'))

    try:
        # Delete related BakerInventory
        BakerInventory.query.filter_by(seller_id=user.id).delete()

        # Delete related Orders
        Order.query.filter_by(seller_id=user.id).delete()

        # Delete related CreditSales
        CreditSale.query.filter_by(seller_id=user.id).delete()

        # Delete the user
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.username} and related data deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user: {e}", "danger")

    return redirect(url_for('view_users'))




from flask import send_file
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta

@app.route('/export_sales_data', methods=['GET'])
def export_sales_data():
    if not current_user.is_authenticated or current_user.role != 'admin':
        return "Unauthorized", 403

    # Fetch optional filters
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    location = request.args.get('location', '')

    query = Order.query

    # Apply filters
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(Order.created_at >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1) - timedelta(seconds=1)
        query = query.filter(Order.created_at <= end_date)
    if location:
        query = query.join(Product).filter(Product.location == location)

    orders = query.order_by(Order.created_at.desc()).all()

    # Prepare data
    data = []
    for order in orders:
        # Get the location from the related Product model
        product_location = order.product.location if order.product else 'Unknown Location'

        data.append({
            'Date Sold': order.date_sold.strftime('%Y-%m-%d %H:%M:%S') if order.date_sold else '',
            'Product Name': order.product.name if order.product else 'Unknown Product',
            'Quantity': order.quantity,
            'Amount': order.amount,
            'Seller': order.seller.username if order.seller else 'Unknown Seller',
            'Location': product_location,  # Use location here
            'Created At': order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else ''
        })

    if not data:
        data.append({
            'Date Sold': '',
            'Product Name': '',
            'Quantity': '',
            'Amount': '',
            'Seller': '',
            'Location': '',  
            'Created At': ''
        })

    # Create an Excel file
    df = pd.DataFrame(data)

    # Create an Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sales Data')

    output.seek(0)

    return send_file(
        output,
        download_name='sales_data.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )



@app.route('/admin/baker_inventory')
@login_required
def admin_baker_inventory():
    submissions = BakerInventory.query.order_by(BakerInventory.date_sent.desc()).all()
    inventory_list = []
    for sub in submissions:
        seller = sub.seller.username if sub.seller else f"ID {sub.seller_id}"
        inventory_list.append({
            "id": sub.id,  # important for approve/reject actions
            "seller_name": seller,
            "date_sent": sub.date_sent.strftime("%Y-%m-%d %H:%M"),
            "status": getattr(sub, "status", "pending"),  # optional if you add status later
            "purchases": sub.purchases,
            "breads": sub.breads
        })
    return render_template("admin_baker_inventory.html", inventory_list=inventory_list)



# 1️⃣ Admin view route (GET)

from datetime import timezone
import pytz

local_tz = pytz.timezone("Africa/Lagos")  # adjust to your timezone

@app.route('/view-baker-inventory')
@login_required
def view_baker_inventory():
    submissions = BakerInventory.query.order_by(BakerInventory.date_sent.desc()).all()
    inventory_list = []

    for sub in submissions:
        seller = sub.seller.username if sub.seller else "Unknown"
        # Convert UTC to local
        utc_dt = sub.date_sent.replace(tzinfo=timezone.utc)
        local_dt = utc_dt.astimezone(local_tz)
        
        inventory_list.append({
            "id": sub.id,
            "seller_name": seller,
            "date_sent": local_dt.strftime("%Y-%m-%d %H:%M"),  # now local time
            "purchases": sub.purchases,
            "breads": sub.breads
        })
    return render_template("admin_baker_inventory.html", inventory_list=inventory_list)



@app.route('/send-baker-inventory', methods=['POST'])
@login_required
def send_baker_inventory():
    try:
        payload = request.get_json()  # purchases + breads

        # Check if seller has a pending submission
        existing = BakerInventory.query.filter_by(seller_id=current_user.id, status='pending').first()
        if existing:
            return jsonify({
                "success": False,
                "error": "You already have a pending inventory submission. Wait for admin approval or create a new one."
            })

        # Create new entry
        new_entry = BakerInventory(
            seller_id=current_user.id,
            purchases=payload.get('purchases', []),
            breads=payload.get('breads', []),
            status='pending'  # default status
        )
        db.session.add(new_entry)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

"""

@app.route('/admin/approve_inventory', methods=['POST'])
@login_required
def approve_inventory():
    data = request.get_json()
    submission_id = data.get("submission_id")  # this will now be an integer
    entry = BakerInventory.query.get(submission_id)
    if not entry:
        return jsonify({"success": False, "error": "Entry not found"})
    entry.status = "approved"
    db.session.commit()
    return jsonify({"success": True})
"""
@app.route('/admin/approve_inventory', methods=['POST'])
@login_required
def approve_inventory():
    data = request.get_json() or {}
    try:
        submission_id = int(data.get("submission_id", 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid submission_id"}), 400

    entry = db.session.get(BakerInventory, submission_id)
    if not entry:
        return jsonify({"success": False, "error": "Entry not found"}), 404

    # ✅ Update status
    entry.status = "approved"
    db.session.commit()

    # ✅ Safely calculate costs
    try:
        purchase_cost = entry.total_purchase_cost or 0
    except Exception as e:
        print(f"⚠️ Error calculating purchase cost: {e}")
        purchase_cost = 0

    try:
        usage_cost = entry.total_usage_cost or 0
    except Exception as e:
        print(f"⚠️ Error calculating usage cost: {e}")
        usage_cost = 0

    # 🔎 Debug logging
    print(f"✅ Inventory ID {submission_id} approved")
    print(f"   Purchases: {entry.purchases}")
    print(f"   Breads: {entry.breads}")
    print(f"   Total Purchase Cost: {purchase_cost}")
    print(f"   Total Usage Cost: {usage_cost}")

    # ✅ Always return valid JSON
    return jsonify({
        "success": True,
        "id": submission_id,
        "total_purchase_cost": purchase_cost,
        "total_usage_cost": usage_cost
    })



@app.route('/admin/reject_inventory', methods=['POST'])
@login_required
def reject_inventory():
    data = request.get_json()
    submission_id = data.get("submission_id")  # this is now an integer from DB
    entry = BakerInventory.query.get(submission_id)
    if not entry:
        return jsonify({"success": False, "error": "Entry not found"})
    
    entry.status = "rejected"
    db.session.commit()
    return jsonify({"success": True})




"""
@app.route('/export_chat/<int:user_id>')
@login_required
def export_chat(user_id):
    target_user = User.query.get_or_404(user_id)
    messages = Message.query.filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id)) |
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id))
    ).order_by(Message.timestamp.asc()).all()

    # Export as JSON (or you can implement CSV/PDF later)
    export_data = [
        {
            'sender_id': m.sender_id,
            'receiver_id': m.receiver_id,
            'content': m.content,
            'timestamp': m.timestamp.isoformat()
        } for m in messages
    ]
    return jsonify(export_data)


@app.route('/chat')
@login_required
def chat():
    if current_user.role == 'seller':
        target_users = User.query.filter_by(role='admin').all()
    elif current_user.role == 'admin':
        target_users = User.query.filter_by(role='seller').all()
    else:
        target_users = []

    if not target_users:
        flash("No users available to chat with.", "warning")
        return redirect(url_for('admin_dashboard') if current_user.role == 'admin' else url_for('seller_dashboard'))

    # unread messages
    unread_counts = {user.id: Message.query.filter_by(sender_id=user.id, receiver_id=current_user.id, is_read=False).count()
                     for user in target_users}

    return render_template('chat_list.html', target_users=target_users, unread_counts=unread_counts)


@app.route('/chat/<int:user_id>')
@login_required
def chat_with_user(user_id):
    target_user = User.query.get_or_404(user_id)
    if target_user.id == current_user.id:
        flash("You cannot chat with yourself.", "warning")
        return redirect(url_for('chat'))

    messages = Message.query.filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id)) |
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id))
    ).order_by(Message.timestamp.asc()).all()

    # Mark unread messages as read
    for msg in Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False):
        msg.is_read = True
    db.session.commit()

    return render_template('chat.html', messages=messages, target_user=target_user)
  

@socketio.on('join')
def handle_join(data):
    room = data['room']
    join_room(room)
    emit('status', {'msg': f'{current_user.username} has joined the room.'}, room=room)


@socketio.on('send_message')
def handle_send_message(data):
    sender_id = current_user.id
    receiver_id = data['receiver_id']
    content = data['content'].strip()
    if not content:
        return

    # Save message
    msg = Message(sender_id=sender_id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()

    # Room name
    room = f"{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"

    # Emit to room
    emit('new_message', {
        'id': msg.id,
        'sender_id': msg.sender_id,
        'receiver_id': msg.receiver_id,
        'content': msg.content,
        'timestamp': msg.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        'sender_name': current_user.username
    }, room=room)

@app.route('/send_message/<int:user_id>', methods=['POST'])
@login_required
def send_message(user_id):
    data = request.get_json() or {}
    content = (data.get('content') or "").strip()
    if not content:
        return jsonify({"error": "Message content is required"}), 400

    receiver = User.query.get_or_404(user_id)
    new_message = Message(sender_id=current_user.id, receiver_id=receiver.id, content=content)
    db.session.add(new_message)
    db.session.commit()

    return jsonify({
        "id": new_message.id,
        "sender_id": new_message.sender_id,
        "receiver_id": new_message.receiver_id,
        "content": new_message.content,
        "created_at": new_message.timestamp.isoformat()
    })



@app.route('/send_message/<int:user_id>', methods=['POST'])
@login_required
def send_message(user_id):
    content = request.form['content'].strip()
    if not content:
        return redirect(url_for('chat_with_user', user_id=user_id))

    target_user = User.query.get_or_404(user_id)

    message = Message(
        sender_id=current_user.id,
        receiver_id=target_user.id,
        content=content
    )
    db.session.add(message)
    db.session.commit()

    # ✅ Emit the message via Socket.IO to the shared room
    room = f"{min(current_user.id, target_user.id)}_{max(current_user.id, target_user.id)}"
    socketio.emit('new_message', {
        'message_id': message.id,
        'sender_id': current_user.id,
        'sender_username': current_user.username,
        'receiver_id': target_user.id,
        'content': content,
    }, room=room)

    return redirect(url_for('chat_with_user', user_id=user_id))





@socketio.on('join')
def handle_join(room):
    join_room(room)



@app.route('/edit_message/<int:message_id>', methods=['POST'])
def edit_message(message_id):
    message = Message.query.get_or_404(message_id)

    if message.sender_id != current_user.id:
        return {'error': 'Unauthorized'}, 403

    data = request.get_json()  # ✅ Parse JSON body
    message.content = data.get('content')
    db.session.commit()
    return {'success': True}



@app.route('/delete_message/<int:message_id>', methods=['POST'])
def delete_message(message_id):
    message = Message.query.get_or_404(message_id)

    # Ensure the current user is the sender of the message
    if message.sender_id != current_user.id:
        flash("You can only delete your own messages.", 'danger')
        return redirect(url_for('chat_with_user', user_id=message.receiver_id))

    # Delete the message
    db.session.delete(message)
    db.session.commit()
    flash('Message deleted successfully!', 'success')
    return redirect(url_for('chat_with_user', user_id=message.receiver_id))


def get_chat_messages(user_id_1, user_id_2):
    return Message.query.filter(
        ((Message.sender_id == user_id_1) & (Message.receiver_id == user_id_2)) |
        ((Message.sender_id == user_id_2) & (Message.receiver_id == user_id_1))
    ).order_by(Message.timestamp.asc()).all()


@app.route('/get_messages/<int:user_id>')
@login_required
def get_messages(user_id):
    messages = get_chat_messages(current_user.id, user_id)
    return render_template('partials/message_list.html', messages=messages, current_user=current_user)

@app.route('/clear_chat/<user_id>', methods=['POST'])
def clear_chat(user_id):
    # Assuming you have a Message model and you're filtering by target user
    Message.query.filter_by(receiver_id=user_id).delete()
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/help')
def help():
    return render_template('help.html')

@app.route('/api/unread-messages')
@login_required
def get_unread_messages():
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    return jsonify({'unread_count': unread_count})



"""


@app.route("/api/unread-messages")
@login_required
def unread_messages():
    return jsonify({"unread_count": 0, "messages": []})


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
