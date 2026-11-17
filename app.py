import os, json, sqlite3, functools, hashlib
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for,
                   session, g, flash, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash
import stripe
import requests
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.path.join(os.path.dirname(__file__), "store.db")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# ---------------- Database ----------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows

def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid

def init_db():
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        country TEXT DEFAULT 'Zimbabwe',
        is_admin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        category_id INTEGER REFERENCES categories(id),
        image TEXT,
        sizes TEXT DEFAULT '',
        colors TEXT DEFAULT '',
        stock INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER REFERENCES products(id),
        author TEXT NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        guest_email TEXT,
        total REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        status TEXT DEFAULT 'pending',
        payment_method TEXT,
        shipping_name TEXT, shipping_address TEXT, shipping_city TEXT,
        shipping_country TEXT, shipping_phone TEXT,
        tracking_number TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER REFERENCES orders(id),
        product_id INTEGER REFERENCES products(id),
        product_name TEXT, size TEXT, color TEXT,
        quantity INTEGER, price REAL
    );
    CREATE TABLE IF NOT EXISTS discounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        percent REAL NOT NULL,
        active INTEGER DEFAULT 1
    );
    """)
    db.commit()

    cats = ["Women", "Men", "Street Wear", "Kids Wear", "Accessories", "Sale"]
    for c in cats:
        db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (c,))
    db.commit()

    products = [
        ("Silk Dress", "Luxurious silk dress, perfect for evenings.", 450, "Women", "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800", "XS,S,M,L,XL", "Black,Red,Navy", 12),
        ("Leather Jacket", "Premium leather jacket with silver zips.", 890, "Women", "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=800", "S,M,L", "Black,Brown", 5),
        ("Evening Gown", "Floor-length satin gown.", 1200, "Women", "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800", "S,M,L", "Gold,Black", 4),
        ("Blouse & Skirt Set", "Elegant matching set.", 340, "Women", "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=800", "S,M,L,XL", "White,Beige", 10),
        ("Maxi Dress", "Flowing summer maxi dress.", 280, "Women", "https://images.unsplash.com/photo-1591369822096-ffd140ec948f?w=800", "S,M,L", "Floral,Green", 8),
        ("Tailored Blazer", "Sharp tailored blazer.", 460, "Women", "https://images.unsplash.com/photo-1583496661160-fb5886a13d44?w=800", "S,M,L", "Navy,Black", 7),
        ("Coat", "Warm wool coat.", 520, "Women", "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=800", "S,M,L,XL", "Camel,Black", 6),
        ("Oxford Shirt", "Classic fitted oxford shirt.", 220, "Men", "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800", "S,M,L,XL,XXL", "White,Blue", 15),
        ("Cotton Blazer", "Smart casual blazer.", 540, "Men", "https://images.unsplash.com/photo-1617137968427-85924c800a22?w=800", "S,M,L,XL", "Navy,Grey", 5),
        ("Chinos", "Comfortable stretch chinos.", 130, "Men", "https://images.unsplash.com/photo-1611312449408-fcece27cdbb7?w=800", "30,32,34,36", "Khaki,Navy", 20),
        ("Polo Shirt", "Breathable piqué polo.", 90, "Men", "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800", "S,M,L,XL", "Black,White,Navy", 25),
        ("Overcoat", "Elegant wool overcoat.", 610, "Men", "https://images.unsplash.com/photo-1552374196-1ab2a1c593e8?w=800", "M,L,XL", "Camel,Charcoal", 4),
        ("Crewneck Sweater", "Soft cotton crewneck.", 145, "Men", "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=800", "M,L,XL", "Grey,Navy,Oat", 18),
        ("Baggy Cargo Pants", "Street-style cargo pants.", 120, "Street Wear", "https://images.unsplash.com/photo-1542272604-787c3835535d?w=800", "S,M,L,XL", "Black,Olive", 14),
        ("Ripped Jeans", "Distressed slim jeans.", 95, "Street Wear", "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=800", "28,30,32,34", "Blue,Black", 16),
        ("Denim Jacket", "Classic trucker denim jacket.", 160, "Street Wear", "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=800", "S,M,L,XL", "Blue,Black", 9),
        ("Graphic Tee", "Bold graphic print tee.", 45, "Street Wear", "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800", "S,M,L,XL,XXL", "White,Black", 30),
        ("Oversized Hoodie", "Heavyweight oversized hoodie.", 85, "Street Wear", "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=800", "S,M,L,XL", "Grey,Black,Navy", 22),
        ("Track Pants", "Tapered track pants.", 70, "Street Wear", "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=800", "S,M,L,XL", "Black,Grey", 19),
        ("Bomber Jacket", "Satin bomber jacket.", 210, "Street Wear", "https://images.unsplash.com/photo-1552374196-c4e7ffc6e126?w=800", "S,M,L,XL", "Black,Navy", 8),
        ("Wide-Leg Jeans", "Flared wide-leg jeans.", 110, "Street Wear", "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=800", "28,30,32,34", "Light Blue,Black", 11),
        ("Logo Tee", "Minimal logo tee.", 55, "Street Wear", "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=800", "S,M,L,XL", "White,Black", 26),
        ("Toddler Dress", "Cute toddler dress.", 65, "Kids Wear", "https://images.unsplash.com/photo-1519238263530-99bdd11df2ea?w=800", "2Y,4Y,6Y", "Pink,Blue", 10),
        ("Kids T-Shirt", "Soft cotton kids tee.", 35, "Kids Wear", "https://images.unsplash.com/photo-1503919545889-aef636e10ad4?w=800", "2Y,4Y,6Y,8Y", "Multi", 28),
        ("Kids Jacket", "Warm kids jacket.", 85, "Kids Wear", "https://images.unsplash.com/photo-1471286174890-9c112ffca5b4?w=800", "2Y,4Y,6Y,8Y", "Navy,Red", 7),
        ("Kids Hoodie", "Cozy kids hoodie.", 75, "Kids Wear", "https://images.unsplash.com/photo-1518831959646-742c3a14ebf7?w=800", "2Y,4Y,6Y,8Y", "Grey,Pink", 12),
        ("Kids Jeans", "Durable kids jeans.", 60, "Kids Wear", "https://images.unsplash.com/photo-1522771930-78848d9293e8?w=800", "2Y,4Y,6Y,8Y", "Blue", 15),
        ("Kids Skirt", "Pretty kids skirt.", 50, "Kids Wear", "https://images.unsplash.com/photo-1519237142847-92a005cc88bd?w=800", "2Y,4Y,6Y", "Pink,White", 9),
        ("Silk Scarf", "Luxurious silk scarf.", 180, "Accessories", "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800", "One Size", "Red,Gold", 13),
        ("Gold Watch", "Stainless steel gold watch.", 950, "Accessories", "https://images.unsplash.com/photo-1611085583191-a3b181a88401?w=800", "One Size", "Gold", 6),
        ("Tote Bag", "Leather tote bag.", 280, "Accessories", "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=800", "One Size", "Brown,Black", 8),
        ("Leather Handbag", "Structured leather handbag.", 620, "Accessories", "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=800", "One Size", "Black,Brown", 5),
        ("Leather Belt", "Genuine leather belt.", 60, "Accessories", "https://images.unsplash.com/photo-1624222247344-550fb60583dc?w=800", "32,34,36,38", "Brown,Black", 20),
        ("Sunglasses", "Polarized sunglasses.", 140, "Accessories", "https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=800", "One Size", "Black,Tortoise", 17),
        ("Wallet", "Slim leather wallet.", 90, "Accessories", "https://images.unsplash.com/photo-1627123424574-724758594e93?w=800", "One Size", "Brown,Black", 14),
    ]
    cat_ids = {r["name"]: r["id"] for r in db.execute("SELECT id, name FROM categories")}
    for p in products:
        db.execute("""INSERT INTO products (name, description, price, category_id, image, sizes, colors, stock)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (p[0], p[1], p[2], cat_ids[p[3]], p[4], p[5], p[6], p[7]))
    db.execute("INSERT OR IGNORE INTO discounts (code, percent) VALUES ('WELCOME10', 10)")
    db.commit()
    db.close()

with app.app_context():
    init_db()

# ---------------- Helpers ----------------
def current_user():
    uid = session.get("user_id")
    return query("SELECT * FROM users WHERE id=?", (uid,), one=True) if uid else None

def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user_id"):
            flash("Please log in to continue.")
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper

def admin_required(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        u = current_user()
        if not u or not u["is_admin"]:
            abort(403)
        return f(*a, **kw)
    return wrapper

def cart():
    return session.get("cart", {})

def save_cart(c):
    session["cart"] = c

def cart_items():
    items = []
    for pid, it in cart().items():
        p = query("SELECT * FROM products WHERE id=?", (pid,), one=True)
        if p:
            items.append({"product": p, "qty": it["qty"], "size": it.get("size"), "color": it.get("color")})
    return items

def cart_total():
    return sum(i["product"]["price"] * i["qty"] for i in cart_items())

SHIPPING_RATES = {
    "Zimbabwe": 15, "South Africa": 40, "Zambia": 35, "Botswana": 45,
    "Kenya": 50, "Nigeria": 70, "Ghana": 70, "United Kingdom": 35,
    "United States": 45, "Germany": 40, "France": 40, "United Arab Emirates": 55,
    "Australia": 60, "Canada": 50, "India": 45, "Other": 80,
}

def shipping_cost(country):
    return SHIPPING_RATES.get(country, SHIPPING_RATES["Other"])

# ---------------- Storefront ----------------
@app.route("/")
def home():
    products = query("""SELECT p.*, c.name AS category_name,
        (SELECT AVG(rating) FROM reviews r WHERE r.product_id=p.id) AS avg_rating,
        (SELECT COUNT(*) FROM reviews r WHERE r.product_id=p.id) AS review_count
        FROM products p JOIN categories c ON c.id=p.category_id
        WHERE p.active=1 ORDER BY p.created_at DESC LIMIT 12""")
    return render_template("home.html", products=products, categories=query("SELECT * FROM categories"))

@app.route("/products")
def products():
    cat = request.args.get("category", "")
    q = request.args.get("q", "").strip()
    sql = """SELECT p.*, c.name AS category_name,
        (SELECT AVG(rating) FROM reviews r WHERE r.product_id=p.id) AS avg_rating,
        (SELECT COUNT(*) FROM reviews r WHERE r.product_id=p.id) AS review_count
        FROM products p JOIN categories c ON c.id=p.category_id WHERE p.active=1"""
    args = []
    if cat:
        sql += " AND c.name=?"; args.append(cat)
    if q:
        sql += " AND (p.name LIKE ? OR p.description LIKE ?)"; args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY p.name"
    return render_template("products.html", products=query(sql, args),
                           categories=query("SELECT * FROM categories"),
                           cat=cat, q=q)

@app.route("/product/<int:pid>")
def product(pid):
    p = query("""SELECT p.*, c.name AS category_name FROM products p
                 JOIN categories c ON c.id=p.category_id WHERE p.id=?""", (pid,), one=True)
    if not p:
        abort(404)
    reviews = query("SELECT * FROM reviews WHERE product_id=? ORDER BY created_at DESC", (pid,))
    avg = query("SELECT AVG(rating) a, COUNT(*) c FROM reviews WHERE product_id=?", (pid,), one=True)
    return render_template("product.html", p=p, reviews=reviews, avg=avg)

@app.route("/product/<int:pid>/review", methods=["POST"])
def add_review(pid):
    author = request.form.get("author", "Anonymous")[:80]
    rating = min(max(int(request.form.get("rating", 5)), 1), 5)
    comment = request.form.get("comment", "")[:1000]
    execute("INSERT INTO reviews (product_id, author, rating, comment) VALUES (?,?,?,?)",
            (pid, author, rating, comment))
    flash("Review submitted. Thank you!")
    return redirect(url_for("product", pid=pid))

@app.route("/cart/add/<int:pid>", methods=["POST"])
def cart_add(pid):
    p = query("SELECT * FROM products WHERE id=? AND active=1", (pid,), one=True)
    if not p:
        abort(404)
    qty = max(1, min(int(request.form.get("qty", 1)), p["stock"]))
    size = request.form.get("size", "")
    color = request.form.get("color", "")
    c = cart()
    key = f"{pid}|{size}|{color}"
    c[key] = {"pid": pid, "qty": c.get(key, {}).get("qty", 0) + qty, "size": size, "color": color}
    save_cart(c)
    flash(f"{p['name']} added to cart.")
    return redirect(request.referrer or url_for("products"))

@app.route("/cart/update", methods=["POST"])
def cart_update():
    c = cart()
    key = request.form.get("key")
    if key in c:
        qty = int(request.form.get("qty", 1))
        if qty <= 0:
            del c[key]
        else:
            c[key]["qty"] = qty
    save_cart(c)
    return redirect(url_for("cart_view"))

@app.route("/cart/remove/<key>")
def cart_remove(key):
    c = cart()
    c.pop(key, None)
    save_cart(c)
    return redirect(url_for("cart_view"))

@app.route("/cart")
def cart_view():
    return render_template("cart.html", items=cart_items(), total=cart_total())

# ---------------- Auth ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if query("SELECT id FROM users WHERE email=?", (email,), one=True):
            flash("Email already registered.")
            return redirect(url_for("register"))
        uid = execute("INSERT INTO users (email, password_hash, name, country) VALUES (?,?,?,?)",
                      (email, generate_password_hash(password), name, request.form.get("country", "Zimbabwe")))
        session["user_id"] = uid
        flash("Account created. Welcome!")
        return redirect(url_for("home"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = query("SELECT * FROM users WHERE email=?", (request.form["email"].strip().lower(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session["user_id"] = u["id"]
            nxt = request.args.get("next") or url_for("home")
            return redirect(nxt)
        flash("Invalid email or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("home"))

# ---------------- Checkout ----------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items = cart_items()
    if not items:
        flash("Your cart is empty.")
        return redirect(url_for("cart_view"))
    if request.method == "POST":
        country = request.form.get("country", "Zimbabwe")
        ship = shipping_cost(country)
        subtotal = cart_total()
        code = request.form.get("discount", "").strip().upper()
        discount = 0
        if code:
            d = query("SELECT * FROM discounts WHERE code=? AND active=1", (code,), one=True)
            if d:
                discount = subtotal * d["percent"] / 100
            else:
                flash("Invalid discount code.")
                return redirect(url_for("checkout"))
        total = round(subtotal - discount + ship, 2)
        if total <= 0:
            flash("Order total is zero.")
            return redirect(url_for("checkout"))

        method = request.form.get("payment", "stripe")
        uid = session.get("user_id")
        oid = execute("""INSERT INTO orders (user_id, guest_email, total, status, payment_method,
                        shipping_name, shipping_address, shipping_city, shipping_country, shipping_phone)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                      (uid, request.form.get("email") if not uid else None, total, "pending", method,
                       request.form.get("name"), request.form.get("address"), request.form.get("city"),
                       country, request.form.get("phone")))
        for i in items:
            execute("""INSERT INTO order_items (order_id, product_id, product_name, size, color, quantity, price)
                      VALUES (?,?,?,?,?,?,?)""",
                    (oid, i["product"]["id"], i["product"]["name"], i["size"], i["color"], i["qty"], i["product"]["price"]))
        for i in items:
            execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id=?", (i["qty"], i["product"]["id"]))

        if method == "paypal":
            return paypal_start(oid, total)
        if method == "paynow":
            return paynow_start(oid, total)
        return stripe_start(oid, total)

    user = current_user()
    return render_template("checkout.html", items=cart_items(), total=cart_total(),
                           user=user, shipping_rates=SHIPPING_RATES)

# ---------------- Stripe ----------------
def stripe_start(order_id, total):
    if not stripe.api_key:
        flash("Payments are not configured yet. Please contact the store.")
        return redirect(url_for("checkout"))
    order = query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    try:
        session_obj = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": int(total * 100),
                    "product_data": {"name": f"LLNDN.G Order #{order_id}"},
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=url_for("order_success", order_id=order_id, _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("checkout", _external=True),
            customer_email=order["guest_email"] or (current_user() or {}).get("email"),
            metadata={"order_id": order_id},
        )
        return redirect(session_obj.url)
    except stripe.error.StripeError as e:
        flash(f"Payment error: {e.user_message or e}")
        return redirect(url_for("checkout"))

@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        abort(400)
    if event["type"] == "checkout.session.completed":
        meta = event["data"]["object"].get("metadata", {})
        if meta.get("order_id"):
            execute("UPDATE orders SET status='paid' WHERE id=? AND status='pending'",
                    (int(meta["order_id"]),))
    return jsonify({"received": True})

@app.route("/order/success/<int:order_id>")
def order_success(order_id):
    order = query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    if not order:
        abort(404)
    save_cart({})
    send_order_email(order)
    items = query("SELECT * FROM order_items WHERE order_id=?", (order_id,))
    return render_template("success.html", order=order, items=items)

# ---------------- PayPal ----------------
def paypal_base():
    return "https://api-m.paypal.com" if os.environ.get("PAYPAL_MODE") == "live" else "https://api-m.sandbox.paypal.com"

def paypal_token():
    r = requests.post(f"{paypal_base()}/v1/oauth2/token",
                      auth=(os.environ.get("PAYPAL_CLIENT_ID"), os.environ.get("PAYPAL_CLIENT_SECRET")),
                      data={"grant_type": "client_credentials"}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]

def paypal_start(order_id, total):
    try:
        order = query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
        token = paypal_token()
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": str(order_id),
                "amount": {"currency_code": "USD", "value": f"{total:.2f}"},
                "description": f"LLNDN.G Order #{order_id}",
            }],
            "application_context": {
                "return_url": url_for("paypal_return", _external=True),
                "cancel_url": url_for("checkout", _external=True),
            },
        }
        r = requests.post(f"{paypal_base()}/v2/checkout/orders", json=body,
                          headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        for link in data.get("links", []):
            if link["rel"] == "payer-action":
                return redirect(link["href"])
        flash("Could not start PayPal payment.")
        return redirect(url_for("checkout"))
    except Exception as e:
        flash(f"PayPal error: {e}")
        return redirect(url_for("checkout"))

@app.route("/paypal/return")
def paypal_return():
    token_pp = request.args.get("token")
    order_id = None
    try:
        token = paypal_token()
        r = requests.get(f"{paypal_base()}/v2/checkout/orders/{token_pp}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        data = r.json()
        order_id = int(data["purchase_units"][0]["reference_id"])
        cap = requests.post(f"{paypal_base()}/v2/checkout/orders/{token_pp}/capture",
                            headers={"Authorization": f"Bearer {token}"}, timeout=15)
        cap.raise_for_status()
        status = cap.json().get("status")
        if status == "COMPLETED":
            execute("UPDATE orders SET status='paid' WHERE id=?", (order_id,))
            order = query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
            send_order_email(order)
            save_cart({})
            items = query("SELECT * FROM order_items WHERE order_id=?", (order_id,))
            return render_template("success.html", order=order, items=items)
    except Exception:
        pass
    flash("PayPal payment was not completed.")
    return redirect(url_for("checkout"))

# ---------------- Paynow (Zimbabwe) ----------------
def paynow_hash(values):
    raw = "".join(str(v) for v in values) + os.environ.get("PAYNOW_INTEGRATION_KEY", "")
    return hashlib.sha512(raw.encode()).hexdigest().upper()

def paynow_start(order_id, total):
    iid = os.environ.get("PAYNOW_INTEGRATION_ID")
    key = os.environ.get("PAYNOW_INTEGRATION_KEY")
    if not iid or not key:
        flash("Paynow is not configured yet. Please contact the store.")
        return redirect(url_for("checkout"))
    order = query("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    email = order["guest_email"] or (current_user() or {}).get("email") or "guest@llndn.g"
    txn_id = f"LG{order_id}{int(datetime.utcnow().timestamp())}"
    fields = {
        "id": txn_id,
        "reference": f"ORDER-{order_id}",
        "amount": f"{total:.2f}",
        "additionalinfo": f"LLNDN.G Order #{order_id}",
        "returnurl": url_for("paynow_return", _external=True),
        "resulturl": url_for("paynow_result", _external=True),
        "authemail": email,
        "status": "Message",
    }
    fields["hash"] = paynow_hash([fields[k] for k in
        ["id", "reference", "amount", "additionalinfo", "returnurl", "resulturl", "authemail", "status"]])
    try:
        r = requests.post("https://www.paynow.co.zw/interface/initiatetransaction",
                          data=fields, timeout=20)
        text = r.text.strip()
        if text.lower().startswith("error"):
            flash(f"Paynow error: {text}")
            return redirect(url_for("checkout"))
        params = dict(p.split("=", 1) for p in text.split("&") if "=" in p)
        url, hashv = params.get("url"), params.get("hash")
        session["paynow"] = {"order_id": order_id, "hash": hashv, "pollurl": params.get("pollurl", "")}
        return redirect(url)
    except Exception as e:
        flash(f"Paynow error: {e}")
        return redirect(url_for("checkout"))

@app.route("/paynow/return")
def paynow_return():
    pn = session.pop("paynow", {})
    oid = pn.get("order_id")
    order = query("SELECT * FROM orders WHERE id=?", (oid,), one=True) if oid else None
    if order:
        items = query("SELECT * FROM order_items WHERE order_id=?", (oid,))
        return render_template("success.html", order=order, items=items)
    flash("Order not found.")
    return redirect(url_for("home"))

@app.route("/paynow/result", methods=["POST", "GET"])
def paynow_result():
    reference = request.values.get("reference", "")
    paynow_ref = request.values.get("paynowreference", "")
    amount = request.values.get("amount", "")
    status = request.values.get("status", "")
    pollurl = request.values.get("pollurl", "")
    received_hash = request.values.get("hash", "")
    expected = paynow_hash([reference, paynow_ref, amount, status, pollurl])
    if received_hash.upper() != expected:
        abort(400)
    try:
        oid = int(reference.replace("ORDER-", ""))
    except ValueError:
        abort(400)
    # Poll Paynow to confirm the transaction actually succeeded
    try:
        poll = requests.post(pollurl, timeout=20).text
        if "Paid" in poll:
            execute("UPDATE orders SET status='paid' WHERE id=? AND status='pending'", (oid,))
            order = query("SELECT * FROM orders WHERE id=?", (oid,), one=True)
            send_order_email(order)
    except Exception as e:
        app.logger.error("Paynow poll failed: %s", e)
    return "OK", 200

# ---------------- Orders ----------------
@app.route("/orders")
@login_required
def orders():
    rows = query("""SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id=o.id) AS items_count
                    FROM orders o WHERE o.user_id=? ORDER BY o.created_at DESC""",
                 (session["user_id"],))
    return render_template("orders.html", orders=rows)

@app.route("/order/<int:oid>")
@login_required
def order_detail(oid):
    order = query("SELECT * FROM orders WHERE id=? AND user_id=?", (oid, session["user_id"]), one=True)
    if not order:
        abort(404)
    items = query("SELECT * FROM order_items WHERE order_id=?", (oid,))
    return render_template("order.html", order=order, items=items)

@app.route("/track")
def track():
    oid = request.args.get("order")
    email = request.args.get("email", "")
    order = None
    if oid:
        order = query("SELECT * FROM orders WHERE id=? AND (guest_email=? OR user_id=(SELECT id FROM users WHERE email=?))",
                      (oid, email, email), one=True)
    return render_template("track.html", order=order, items=(query("SELECT * FROM order_items WHERE order_id=?", (order["id"],)) if order else []))

# ---------------- Admin ----------------
@app.route("/admin")
@admin_required
def admin():
    stats = {
        "revenue": query("SELECT COALESCE(SUM(total),0) s FROM orders WHERE status='paid'", one=True)["s"],
        "orders": query("SELECT COUNT(*) c FROM orders", one=True)["c"],
        "products": query("SELECT COUNT(*) c FROM products WHERE active=1", one=True)["c"],
        "customers": query("SELECT COUNT(*) c FROM users", one=True)["c"],
    }
    return render_template("admin.html", stats=stats,
                           products=query("SELECT p.*, c.name AS cat FROM products p JOIN categories c ON c.id=p.category_id ORDER BY p.id DESC"),
                           orders=query("SELECT o.*, u.email FROM orders o LEFT JOIN users u ON u.id=o.user_id ORDER BY o.created_at DESC LIMIT 50"),
                           customers=query("SELECT * FROM users ORDER BY created_at DESC LIMIT 50"),
                           discounts=query("SELECT * FROM discounts ORDER BY id DESC"))

@app.route("/admin/product/add", methods=["POST"])
@admin_required
def admin_product_add():
    cat_id = query("SELECT id FROM categories WHERE name=?", (request.form["category"],), one=True)["id"]
    execute("""INSERT INTO products (name, description, price, category_id, image, sizes, colors, stock)
              VALUES (?,?,?,?,?,?,?,?)""",
            (request.form["name"], request.form["description"], float(request.form["price"]), cat_id,
             request.form["image"], request.form.get("sizes", ""), request.form.get("colors", ""),
             int(request.form["stock"])))
    flash("Product added.")
    return redirect(url_for("admin"))

@app.route("/admin/product/<int:pid>/edit", methods=["POST"])
@admin_required
def admin_product_edit(pid):
    cat_id = query("SELECT id FROM categories WHERE name=?", (request.form["category"],), one=True)
    cat_id = cat_id["id"] if cat_id else None
    execute("""UPDATE products SET name=?, description=?, price=?, category_id=?, image=?,
              sizes=?, colors=?, stock=? WHERE id=?""",
            (request.form["name"], request.form["description"], float(request.form["price"]), cat_id,
             request.form["image"], request.form.get("sizes", ""), request.form.get("colors", ""),
             int(request.form["stock"]), pid))
    flash("Product updated.")
    return redirect(url_for("admin"))

@app.route("/admin/product/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_product_delete(pid):
    execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    flash("Product removed.")
    return redirect(url_for("admin"))

@app.route("/admin/order/<int:oid>/status", methods=["POST"])
@admin_required
def admin_order_status(oid):
    status = request.form.get("status", "pending")
    tracking = request.form.get("tracking", "")
    execute("UPDATE orders SET status=?, tracking_number=COALESCE(NULLIF(?,''), tracking_number) WHERE id=?",
            (status, tracking, oid))
    flash("Order updated.")
    return redirect(url_for("admin"))

@app.route("/admin/discount/add", methods=["POST"])
@admin_required
def admin_discount_add():
    execute("INSERT INTO discounts (code, percent) VALUES (?,?)",
            (request.form["code"].strip().upper(), float(request.form["percent"])))
    flash("Discount added.")
    return redirect(url_for("admin"))

@app.route("/admin/discount/<int:did>/toggle", methods=["POST"])
@admin_required
def admin_discount_toggle(did):
    execute("UPDATE discounts SET active = 1 - active WHERE id=?", (did,))
    return redirect(url_for("admin"))

# ---------------- Email ----------------
def send_order_email(order):
    host = os.environ.get("EMAIL_HOST")
    if not host:
        app.logger.info("EMAIL not configured - order %s confirmation skipped", order["id"])
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        items = query("SELECT * FROM order_items WHERE order_id=?", (order["id"],))
        lines = "\n".join(f"- {i['product_name']} x{i['quantity']} (${i['price']})" for i in items)
        body = f"Thank you for your order #{order['id']}!\n\nItems:\n{lines}\n\nTotal: ${order['total']:.2f}\nStatus: {order['status']}\n"
        msg = MIMEText(body)
        msg["Subject"] = f"LLNDN.G Order #{order['id']} Confirmation"
        msg["From"] = os.environ.get("EMAIL_FROM", "orders@llndn.g")
        msg["To"] = order["guest_email"] or query("SELECT email FROM users WHERE id=?", (order["user_id"],), one=True)["email"]
        with smtplib.SMTP(host, int(os.environ.get("EMAIL_PORT", 587))) as s:
            s.starttls()
            s.login(os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASSWORD"))
            s.send_message(msg)
    except Exception as e:
        app.logger.error("Email failed: %s", e)

@app.context_processor
def inject():
    return {"user": current_user(), "cart_count": sum(i["qty"] for i in cart_items())}

@app.route("/api/currencies")
def currencies():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        return jsonify(r.json().get("rates", {}))
    except Exception:
        return jsonify({})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
