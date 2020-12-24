import os
from datetime import datetime

from math import ceil
from sqlalchemy import Column, Integer, String, desc
from flask_sqlalchemy import SQLAlchemy


from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp

from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

import stripe

app = Flask(__name__)

DOMAIN = 'http://localhost:4242'


app.config["STRIPE_PUBLIC_KEY"] = ["YOUR_PUBLIC_KEY"]
app.config["STRIPE_SECRET_KEY"] = ["YOUR_SECRET_KEY"]
stripe.api_key = app.config["STRIPE_SECRET_KEY"]

app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///market.sqlite3'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True
db = SQLAlchemy(app)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


# Declare table users
class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True, unique=True)
    username = db.Column(db.String(100))
    hash = db.Column(db.String)
    def __init__(self, username, hash):
        self.username = username
        self.hash = hash

# Declare table items
class Items(db.Model):
    id = db.Column('id', db.Integer, primary_key=True, unique=True)
    name = db.Column(db.String(50))
    price = db.Column(db.Integer)
    link = db.Column(db.String)
    def __init__(self, name, price):
        self.name = name
        self.price = price
        self.link = link

# Declare table cart
class Cart(db.Model):
    id = db.Column('id', db.Integer, primary_key=True, unique=True)
    user_id = db.Column(db.Integer)
    item_id = db.Column(db.String)
    quantity = db.Column(db.Integer)
    def __init__(self, user_id, item_id, quantity):
        self.user_id = user_id
        self.item_id = item_id
        self.quantity = quantity

# table for buys ids
class Buys_relations(db.Model):
    id = db.Column('id', db.Integer, primary_key=True, unique=True)
    user_id = db.Column(db.Integer)
    time = db.Column(db.String)
    def __init__(self, user_id, time):
        self.user_id = user_id
        self.time = time

# Table of history for purchased items
class Buys(db.Model):
    id = db.Column('id', db.Integer, primary_key=True, unique=True)
    buy_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    name = db.Column(db.String)
    quantity = db.Column(db.Integer)
    unit_price = db.Column(db.Integer)
    total = db.Column(db.Integer)
    def __init__(self, buy_id, user_id, name, quantity, unit_price, total):
        self.buy_id = buy_id
        self.user_id = user_id
        self.name = name
        self.quantity = quantity
        self.unit_price = unit_price
        self.total = total

# Create all the tables
db.create_all()

# global variable for the checkout item list
list_of_items = []

def login_required(f):
    ''' Decorate routes to require login. '''
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# Convert to format U$0,000.00
def usd(value):
    '''Format value as USD.'''
    return (f"U${value:,.2f}")

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    if request.method == "GET":
        # Displays all items in the database
        items = Items.query.all()
        rows = ceil((len(items))/3)
        return render_template('index.html', success=0, items=items, rows=rows)
    else:
        # buying only one item
        if not request.form.get("cart"):
            # Find the item requested by the user in the db
            item = Items.query.filter_by(id=request.form.get("value_id")).first()

            # Generates the list of items to be purchased
            global list_of_items
            list_of_items.clear()

            # list with one item to send to API
            list_of_items.append (
            {
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': item.price*100,
                    'product_data': {
                        'name': item.name,
                        'images': [item.link],
                    },
                },
                'quantity': request.form.get(request.form.get("value_id")),
            })
            # Redirects to the stripe checkout page
            return render_template("checkout.html", public_key=app.config['STRIPE_PUBLIC_KEY'])
        else: # Adding to the cart
            product_id = request.form.get("cart")
            quantity = int(request.form.get(product_id))
            # If cart is empty
            if not Cart.query.filter_by(user_id=session["user_id"]).all():
                # Add the new item
                new_item = Cart(session["user_id"], request.form.get("cart"), quantity)
                db.session.add(new_item)
                db.session.commit()
                return redirect("/")
            else:
                # Search the customer's cart
                cart = Cart.query.filter_by(user_id=session["user_id"]).all()
                # Checks whether the item is already in the cart
                for item in cart:
                    # If the user have that item in the cart
                    if product_id == item.item_id:
                        if item.quantity+quantity > 100:
                            return redirect("/")
                        #Add the quantity
                        item.quantity += quantity
                        db.session.commit()
                        return redirect("/")
                # Add new item to Cart
                new_item = Cart(session["user_id"], request.form.get("cart"), quantity)
                db.session.add(new_item)
                db.session.commit()
                return redirect("/")


@app.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    ''' Send request to API '''
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items = list_of_items,
            mode="payment",
            success_url = DOMAIN + "/success",
            cancel_url = DOMAIN + "/cancel",
        )
        return jsonify({"id": checkout_session.id})
    except Exception as e:
        return jsonify(error=str(e)), 403


@app.route("/cart", methods=["GET", "POST"])
@login_required
def cart_function():
    if request.method == "GET":
        #List of cart items
        cart_item = []
        total = 0

        # Checks if the cart is empty
        if not Cart.query.filter_by(user_id=session["user_id"]).all():
            return render_template("cart_empty.html")

        # Get all the user items
        cart = Cart.query.filter_by(user_id=session["user_id"]).all()

        # Defines and clear the list of items to send to API
        global list_of_items
        if len(list_of_items) != 0:
            list_of_items.clear()

        # For each cart item
        for product in cart:

            # Search the items table for id
            product_detail = Items.query.filter_by(id=product.item_id).first()

            # Deletes the item from the cart if the quantity is 0
            if product.quantity == 0:
                db.session.delete(product)
                db.session.commit()

                # If an item is deleted, it checks whether the cart is empty
                if not Cart.query.filter_by(user_id=session["user_id"]).all():
                    return render_template("cart_empty.html")
                continue
            total_product = usd((product_detail.price) * product.quantity)

            # List of items in the cart to show in page cart
            cart_item.append (
                {
                "id": product_detail.id,
                "name": product_detail.name,
                "price": usd(product_detail.price),
                "quantity": product.quantity,
                "total_product": total_product,
                "images": product_detail.link,
                },
            )
            total += (product_detail.price) * product.quantity
            # List to send to the API
            list_of_items.append (
            {
            "price_data": {
                "currency": "usd",
                "unit_amount": product_detail.price*100,
                    "product_data":{
                        "name": product_detail.name,
                        "images": [product_detail.link],
                    },
                },
                "quantity": product.quantity,
            })
        return render_template("cart.html", item=cart_item, total=usd(total))
    else:
        # Clears user's cart
        cart = Cart.query.filter_by(user_id=session["user_id"]).all()
        for item in cart:
            db.session.delete(item)
            db.session.commit()
        # Redirects to the stripe checkout page
        return render_template("checkout.html", public_key=app.config["STRIPE_PUBLIC_KEY"])

@app.route("/cart/<action>/<product>", methods=["POST"])
@login_required
def cart_change(action, product):
    # If the user uses + or -
    if action == "push":
        # Access user's cart
        cart = Cart.query.filter_by(user_id=session["user_id"]).all()

        # Loop through all items in the cart
        for item in cart:

            # if it is the item that the user wants to change
            if item.item_id == product:

                # User wants to add one item
                if request.form.get("push") == '+':
                    # less than 100 items
                    if item.quantity < 100:
                        item.quantity += 1

                # user wants to subtract one item
                else:
                    item.quantity -= 1
                db.session.commit()
                return redirect("/cart")

    # If the user changes the number in the entry
    elif action == "input":
        cart = Cart.query.filter_by(user_id=session["user_id"]).all()
        for item in cart:
            # Check if it is the item requested by the user
            if item.item_id == product:
                # Changes the quantity with the number in the input
                item.quantity = int(request.form.get("input_qtd"))
                db.session.commit()
                return redirect("/cart")
    elif action == "empty":
        # empties all cart
        cart = Cart.query.filter_by(user_id=session["user_id"]).all()
        for item in cart:
            db.session.delete(item)
            db.session.commit()
        return redirect("/cart")
    else:
        #remove only one item from the cart
        items = Cart.query.filter_by(user_id=session["user_id"]).all()
        for item in items:
            # Check if it is the item requested by the user
            if item.item_id == product:
                db.session.delete(item)
                db.session.commit()
                return redirect("/cart")
        return redirect("/cart")


@app.route("/success", methods=["GET"])
def successs():
    # Gets the date and time of purchase
    date = (datetime.now())
    schedule = (f"{date.strftime('%x')} {date.strftime('%X')}")

    # Generates new buy_id
    new_buy = Buys_relations(session["user_id"], schedule)
    db.session.add(new_buy)
    db.session.commit()
    for i in list_of_items:
        # Stores each item purchased on table buys
        buy = Buys(new_buy.id,
        session["user_id"],
        i["price_data"]["product_data"]["name"],
        i["quantity"],
        usd(i["price_data"]["unit_amount"]/100),
        int(i["quantity"]) * (i["price_data"]["unit_amount"]/100),
        )
        db.session.add(buy)
        db.session.commit()

    # empties the list of items
    list_of_items.clear()
    return render_template("success.html")


@app.route("/cancel")
@login_required
def cancel():
    # If the user does not complete the purchase
    return render_template("cancel.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        username =  str(request.form.get("username").strip())
        password =  str(request.form.get("password").strip())

        # Ensures that the username exists
        if not Users.query.filter_by(username=username).all():
            return render_template("login.html", msg="The username entered does not exist")

        user = Users.query.filter_by(username=username).first()

        # The password is not correct
        if not check_password_hash(user.hash, password):
            return render_template("login.html", msg="The password is incorrect")

        # Remember which user has logged in
        session["user_id"] = user.id

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html", msg='')
    else:
        # User reached route via POST (as by submitting a form via POST)
        username = str(request.form.get("username").strip())
        password = str(request.form.get("password").strip())
        confirmation = str(request.form.get("confirmation").strip())

        # Ensures the password and the confirmation are the same
        if password != confirmation:
            return render_template("register.html", msg="Passwords don't match")

        # Ensure the username it's not registred
        if not Users.query.filter_by(username=username).first():

            # Insert new user in the table Users
            user = Users(username, generate_password_hash(password))
            db.session.add(user)
            db.session.commit()

            # Assign the user id to the session
            session["user_id"] = user.id

            # Redirect to home page
            return redirect ("/")
        else:
            return render_template("register.html", msg="User already registred")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return False


@app.route("/logout")
@login_required
def logout():
    """Log user out"""
    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show all the user's buy """
    # If there was no recorded purchase
    if not Buys_relations.query.filter_by(user_id=session["user_id"]).all():
        return render_template("history_empty.html")
    # Search all user purchases
    buys_ids = Buys_relations.query.filter_by(user_id=session["user_id"]).order_by(desc(Buys_relations.id))

    # Defines the list that will be sent to the api
    list_of_buys = [] # List to send to API
    list_of_buys.clear()

    totals = [] # Dictionary with the buys ids and the totals
    ids = [] # Store each user's buy id

    # Looking for each product of the buy
    for buy in buys_ids:
        rows = Buys.query.filter_by(buy_id=buy.id).all()
        buy_total =0
        # For each product in the purchase
        for row in rows:
            buy_total += row.total # Sums the total of all items purchased
            list_of_buys.append(
                { row.buy_id: {
                    "name": row.name,
                    "quantity": row.quantity,
                    "unit_price": row.unit_price,
                    "total": usd(row.total),
                },
            },
            )
        totals.append( # Saves the total of each purchase
            { buy.id:{
            "buy_total": usd(buy_total), "time": buy.time}
            })
        # Stores the buys ids of the table Buys_relation
        ids.append (buy.id)
    return render_template("history.html", totals=totals, rows=ids, list_of_buys=list_of_buys)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


if __name__ == '__main__':
    app.run(port=4242)