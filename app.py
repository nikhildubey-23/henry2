import os
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'henri-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///henri.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_TYPE'] = 'filesystem'

db = SQLAlchemy(app)

@app.before_request
def load_categories():
    from flask import g
    categories = db.session.query(Product.category).distinct().all()
    g.categories = [c[0] for c in categories]

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    current_stock = db.Column(db.Float, default=0)
    minimum_stock = db.Column(db.Float, default=0)
    sale_price = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, default=0)
    demo_price = db.Column(db.Float, default=0)
    description = db.Column(db.Text, default='')
    image_url = db.Column(db.String(500), default='')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'current_stock': self.current_stock,
            'minimum_stock': self.minimum_stock,
            'sale_price': self.sale_price,
            'purchase_price': self.purchase_price,
            'demo_price': self.demo_price,
            'description': self.description,
            'image_url': self.image_url,
            'in_stock': self.current_stock > 0
        }

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), default='')
    address = db.Column(db.Text, default='')
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    shipping_address = db.Column(db.Text, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(50), default='cod')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'customer_email': self.customer_email,
            'shipping_address': self.shipping_address,
            'subtotal': self.subtotal,
            'total': self.total,
            'status': self.status,
            'payment_method': self.payment_method,
            'notes': self.notes,
            'items': [item.to_dict() for item in self.items],
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'unit_price': self.unit_price,
            'total': self.total
        }

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    review = db.Column(db.Text, default='')
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', backref='ratings')

def generate_order_number():
    last_order = Order.query.order_by(Order.id.desc()).first()
    if last_order:
        num = int(last_order.order_number.replace('ORD', '')) + 1
    else:
        num = 1
    return f'ORD{str(num).zfill(6)}'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    products = Product.query.filter_by(is_active=True).all()
    return render_template('index.html', products=products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    related_products = Product.query.filter_by(category=product.category, is_active=True).filter(Product.id != product.id).limit(4).all()
    ratings = Rating.query.filter_by(product_id=product_id, is_approved=True).order_by(Rating.created_at.desc()).all()
    avg_rating = sum(r.rating for r in ratings) / len(ratings) if ratings else 0
    return render_template('product.html', product=product, related_products=related_products, ratings=ratings, avg_rating=avg_rating)

@app.route('/product/<int:product_id>/rate', methods=['POST'])
def rate_product(product_id):
    product = Product.query.get_or_404(product_id)
    rating = int(request.form.get('rating', 5))
    review = request.form.get('review', '')
    customer_name = request.form.get('customer_name', 'Anonymous')
    
    new_rating = Rating(
        product_id=product_id,
        customer_name=customer_name,
        rating=rating,
        review=review,
        is_approved=False
    )
    db.session.add(new_rating)
    db.session.commit()
    flash('Thank you! Your rating has been submitted and is pending approval.', 'success')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/category/<category>')
def category(category):
    products = Product.query.filter_by(category=category, is_active=True).all()
    return render_template('index.html', products=products, current_category=category)

@app.route('/cart')
def cart():
    cart = session.get('cart', [])
    cart_items = []
    subtotal = 0
    for item in cart:
        product = Product.query.get(item['product_id'])
        if product:
            item_total = product.sale_price * item['quantity']
            subtotal += item_total
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'total': item_total
            })
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal, total=subtotal)

@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    quantity = int(request.form.get('quantity', 1))
    cart = session.get('cart', [])
    
    existing_item = next((item for item in cart if item['product_id'] == product_id), None)
    if existing_item:
        existing_item['quantity'] += quantity
    else:
        cart.append({'product_id': product_id, 'quantity': quantity})
    
    session['cart'] = cart
    flash('Item added to cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/update-cart/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    quantity = int(request.form.get('quantity', 1))
    cart = session.get('cart', [])
    
    for item in cart:
        if item['product_id'] == product_id:
            if quantity > 0:
                item['quantity'] = quantity
            else:
                cart.remove(item)
            break
    
    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/remove-from-cart/<int:product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    cart = [item for item in cart if item['product_id'] != product_id]
    session['cart'] = cart
    flash('Item removed from cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', [])
    if not cart:
        flash('Your cart is empty!', 'error')
        return redirect(url_for('index'))
    
    cart_items = []
    subtotal = 0
    for item in cart:
        product = Product.query.get(item['product_id'])
        if product:
            item_total = product.sale_price * item['quantity']
            subtotal += item_total
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'total': item_total
            })
    
    if request.method == 'POST':
        order = Order(
            order_number=generate_order_number(),
            customer_name=request.form.get('name'),
            customer_phone=request.form.get('phone'),
            customer_email=request.form.get('email'),
            shipping_address=request.form.get('address'),
            subtotal=subtotal,
            total=subtotal,
            payment_method=request.form.get('payment_method', 'cod'),
            notes=request.form.get('notes', '')
        )
        db.session.add(order)
        db.session.flush()
        
        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item['product'].id,
                product_name=item['product'].name,
                quantity=item['quantity'],
                unit_price=item['product'].sale_price,
                total=item['total']
            )
            db.session.add(order_item)
            
            product = Product.query.get(item['product'].id)
            if product:
                product.current_stock -= item['quantity']
        
        db.session.commit()
        session['cart'] = []
        flash(f'Order placed successfully! Order number: {order.order_number}', 'success')
        return redirect(url_for('order_success', order_number=order.order_number))
    
    return render_template('checkout.html', cart_items=cart_items, subtotal=subtotal, total=subtotal)

@app.route('/order-success/<order_number>')
def order_success(order_number):
    order = Order.query.filter_by(order_number=order_number).first()
    return render_template('order_success.html', order=order)

@app.route('/my-orders')
def my_orders():
    email = session.get('customer_email')
    if not email:
        flash('Please login to view your orders', 'error')
        return redirect(url_for('login'))
    
    orders = Order.query.filter_by(customer_email=email).order_by(Order.created_at.desc()).all()
    return render_template('my_orders.html', orders=orders)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['customer_email'] = user.email
            session['customer_name'] = user.name
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        user = User(
            email=email,
            name=name,
            phone=phone,
            address=address,
            password=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '')
    products = Product.query.filter(Product.name.ilike(f'%{query}%'), Product.is_active==True).all()
    return render_template('index.html', products=products, search_query=query)

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email, is_admin=True).first()
        if user and check_password_hash(user.password, password):
            session['admin_logged_in'] = True
            session['admin_id'] = user.id
            session['admin_email'] = user.email
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_email', None)
    flash('Logged out from admin!', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    total_products = Product.query.count()
    low_stock = Product.query.filter(Product.current_stock <= Product.minimum_stock).filter(Product.minimum_stock > 0).count()
    
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    
    orders_by_status = {
        'pending': Order.query.filter_by(status='pending').count(),
        'processing': Order.query.filter_by(status='processing').count(),
        'shipped': Order.query.filter_by(status='shipped').count(),
        'delivered': Order.query.filter_by(status='delivered').count(),
        'cancelled': Order.query.filter_by(status='cancelled').count(),
    }
    
    from sqlalchemy import func
    products_by_category = db.session.query(
        Product.category, 
        func.count(Product.id)
    ).group_by(Product.category).all()
    
    from datetime import datetime, timedelta
    last_30_days = datetime.utcnow() - timedelta(days=30)
    daily_sales = db.session.query(
        func.date(Order.created_at).label('date'),
        func.sum(Order.total).label('total'),
        func.count(Order.id).label('count')
    ).filter(Order.created_at >= last_30_days).group_by(func.date(Order.created_at)).all()
    
    top_products = db.session.query(
        OrderItem.product_name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(Order).filter(Order.status != 'cancelled').group_by(OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
    
    total_revenue = db.session.query(func.sum(Order.total)).scalar() or 0
    
    return render_template('admin/dashboard.html', 
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         total_products=total_products,
                         low_stock=low_stock,
                         recent_orders=recent_orders,
                         orders_by_status=orders_by_status,
                         products_by_category=products_by_category,
                         daily_sales=daily_sales,
                         top_products=top_products,
                         total_revenue=total_revenue)

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status = request.args.get('status', 'all')
    if status == 'all':
        orders = Order.query.order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.filter_by(status=status).order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders, current_status=status)

@app.route('/admin/order/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin/order_detail.html', order=order)

@app.route('/admin/order/<int:order_id>/update', methods=['POST'])
@admin_required
def admin_update_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = request.form.get('status')
    order.notes = request.form.get('notes', '')
    db.session.commit()
    flash('Order updated successfully!', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.name).all()
    return render_template('admin/products.html', products=products)

@app.route('/admin/product/new', methods=['GET', 'POST'])
@admin_required
def admin_product_new():
    if request.method == 'POST':
        product = Product(
            name=request.form.get('name'),
            category=request.form.get('category'),
            current_stock=float(request.form.get('current_stock', 0)),
            minimum_stock=float(request.form.get('minimum_stock', 0)),
            sale_price=float(request.form.get('sale_price')),
            purchase_price=float(request.form.get('purchase_price', 0)),
            description=request.form.get('description', ''),
            image_url=request.form.get('image_url', ''),
            is_active=request.form.get('is_active') == 'on'
        )
        db.session.add(product)
        db.session.commit()
        flash('Product created successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin/product_form.html', product=None)

@app.route('/admin/product/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.category = request.form.get('category')
        product.current_stock = float(request.form.get('current_stock', 0))
        product.minimum_stock = float(request.form.get('minimum_stock', 0))
        product.sale_price = float(request.form.get('sale_price'))
        product.purchase_price = float(request.form.get('purchase_price', 0))
        product.description = request.form.get('description', '')
        product.image_url = request.form.get('image_url', '')
        product.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin/product_form.html', product=product)

@app.route('/admin/product/<int:product_id>/delete')
@admin_required
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/ratings')
@admin_required
def admin_ratings():
    ratings = Rating.query.order_by(Rating.created_at.desc()).all()
    return render_template('admin/ratings.html', ratings=ratings)

@app.route('/admin/rating/<int:rating_id>/approve')
@admin_required
def admin_rating_approve(rating_id):
    rating = Rating.query.get_or_404(rating_id)
    rating.is_approved = True
    db.session.commit()
    flash('Rating approved successfully!', 'success')
    return redirect(url_for('admin_ratings'))

@app.route('/admin/rating/<int:rating_id>/delete')
@admin_required
def admin_rating_delete(rating_id):
    rating = Rating.query.get_or_404(rating_id)
    db.session.delete(rating)
    db.session.commit()
    flash('Rating deleted successfully!', 'success')
    return redirect(url_for('admin_ratings'))

@app.route('/admin/rating/<int:rating_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_rating_edit(rating_id):
    rating = Rating.query.get_or_404(rating_id)
    
    if request.method == 'POST':
        rating.rating = int(request.form.get('rating', 5))
        rating.review = request.form.get('review', '')
        rating.customer_name = request.form.get('customer_name', 'Anonymous')
        rating.is_approved = request.form.get('is_approved') == 'on'
        db.session.commit()
        flash('Rating updated successfully!', 'success')
        return redirect(url_for('admin_ratings'))
    
    return render_template('admin/rating_form.html', rating=rating)

@app.route('/admin/customers')
@admin_required
def admin_customers():
    customers = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    return render_template('admin/customers.html', customers=customers)

@app.route('/admin/stats')
@admin_required
def admin_stats():
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    orders_by_status = {}
    for status in ['pending', 'processing', 'shipped', 'delivered', 'cancelled']:
        count = Order.query.filter_by(status=status).count()
        orders_by_status[status] = count
    
    return render_template('admin/stats.html', total_revenue=total_revenue, orders_by_status=orders_by_status)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    products = Product.query.filter_by(is_active=True).all()
    
    product_list = "\n".join([
        f"- {p.name} ({p.category}): ₹{p.sale_price} (MRP: ₹{p.demo_price if p.demo_price else p.sale_price*2}) | Stock: {'In Stock (' + str(int(p.current_stock)) + ')' if p.current_stock > 0 else 'Out of Stock'} | {p.description[:200] if p.description else 'No description'}"
        for p in products
    ])
    
    product_purposes = """
PRODUCT PURPOSES & USES:
- LIPSTAR (Lip Care): For dry lips, lip hydration, lip shine, lip protection
- WHITOLYN (Body Care): For skin brightening, fairness, dark spots removal, body glow
- XANONICE TAB (Tablet): For skin health, glowing skin, internal skin nutrition
- Picotry Cream (Cream): For pigmentation, skin whitening, age spots, melasma
- HZEUP SOAP (Soap): For acne, oily skin, antibacterial cleansing, pimple control
- ROOFS SPF (Sunscreen): For sun protection, UV protection, SPF 50+
- Opuoxy Bright (Cream): For brightening, dull skin, dark circles, fairness
- GLOWORG (Cream): For fairness, moisturizing, SPF 20 protection, 24hr hydration
- NIDGLOW - G (Gel): For glowing skin, pores, acne marks, collagen boost
- LEUCODERM (Lotion): For vitiligo, depigmentation, skin patches
- PDRN MASK (Face Mask): For skin repair, acne scars, wound healing, damaged skin
- Scparal Mask (Face Mask): For sensitive skin, redness, calming irritated skin
- ECTOSOL SS TINT SPF 50 (Sunscreen): For tinted coverage, SPF 50, daily use
- Elight Sunscreen (Sunscreen): For sensitive skin, reef-safe, chemical-free
- Cuhair Tab (Tablet): For hair growth, hair fall control, hair thickness
"""
    
    system_prompt = f"""You are a beauty and skincare expert assistant for Henri Store. Your job is to understand customer needs and recommend the RIGHT products from our store.

CUSTOMER NEEDS MATCHING:
When a customer describes their problem, match it to the right product:

- Dry lips → LIPSTAR
- Fairness/brightening → WHITOLYN, Opuoxy Bright, GLOWORG, Picotry Cream
- Skin health from within → XANONICE TAB
- Acne/pimples → HZEUP SOAP, NIDGLOW - G
- Sun protection → ROOFS SPF, ECTOSOL SS TINT SPF 50, Elight Sunscreen
- Dark spots/pigmentation → Picotry Cream, Opuoxy Bright
- Hair growth/hair fall → Cuhair Tab
- Sensitive/irritated skin → Scparal Mask
- Skin repair/scars → PDRN MASK
- Vitiligo/depigmentation → LEUCODERM

IMPORTANT RULES:
1. Always check if product is in stock before recommending
2. Mention the price and the discount (MRP vs sale price)
3. Be friendly and helpful
4. If customer mentions a concern, suggest 1-3 relevant products
5. If out of stock, suggest alternatives
6. Ask follow-up questions to understand their needs better

{product_purposes}

AVAILABLE PRODUCTS:
{product_list}

Provide personalized recommendations with product names, prices, and why it's good for their specific need."""

    try:
        groq_api_key = os.environ.get('GROQ_API_KEY')
        if not groq_api_key:
            return jsonify({'error': 'API key not configured'}), 500
        
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'llama-3.1-8b-instant',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message}
                ],
                'temperature': 0.7,
                'max_tokens': 600
            }
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Failed to get response from AI'}), 500
        
        data = response.json()
        bot_response = data['choices'][0]['message']['content']
        
        return jsonify({'response': bot_response})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def init_db():
    with app.app_context():
        db.create_all()
        
        try:
            db.session.execute(db.text('ALTER TABLE product ADD COLUMN demo_price FLOAT DEFAULT 0'))
            db.session.commit()
            print('Added demo_price column to database')
        except:
            db.session.rollback()
        
        admin = User.query.filter_by(email='admin@henri.com', is_admin=True).first()
        if not admin:
            admin = User(
                email='admin@henri.com',
                password=generate_password_hash('admin123'),
                name='Admin',
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin@henri.com / admin123')
        
        default_descriptions = {
            'LIPSTAR': 'LIPSTAR is a premium lip care product designed to provide deep hydration and a natural shine. Formulated with vitamin E and natural oils, it helps prevent dry lips and gives a subtle, lasting gloss. Perfect for daily use, this lip care essential suits all skin types and provides protection against environmental damage.',
            'WHITOLYN': 'WHITOLYN is an advanced body care lotion that brightens and evens skin tone. Enriched with glutathione and Kojic acid, it helps reduce dark spots, blemishes, and hyperpigmentation. Regular application reveals smoother, radiant skin while providing long-lasting moisturization.',
            'XANONICE TAB': 'XANONICE TAB is a dietary supplement formulated to support overall skin health from within. Contains essential vitamins and minerals that promote collagen production, reduce inflammation, and protect against oxidative stress.',
            'Picotry Cream': 'Picotry Cream is a specialized skincare treatment targeting stubborn pigmentation and uneven skin tone. Its advanced formula combines natural extracts with proven whitening agents to deliver visible results. Effective for age spots, sun damage, and melasma.',
            'HZEUP SOAP': 'HZEUP SOAP is an antibacterial soap infused with herbal extracts for deep cleansing. Formulated with neem and tea tree oil, it effectively fights acne-causing bacteria while being gentle on skin.',
            'ROOFS SPF': 'ROOFS SPF is a broad-spectrum sunscreen providing SPF 50+ protection against UVA and UVB rays. Lightweight and non-greasy formula absorbs quickly without white cast. Enriched with antioxidants to prevent sun damage.',
            'Opuoxy Bright': 'Opuoxy Bright is a revolutionary brightening cream that targets dullness and uneven skin tone. Contains Oxyresveratrol and vitamin C for powerful antioxidant protection.',
            'GLOWORG': 'GLOWORG is an all-in-one fairness cream that works to brighten, moisturize, and protect skin. Infused with arbutin and mulberry extract for visibly lighter skin tone.',
            'NIDGLOW - G': 'NIDGLOW - G is a premium face gel designed for glowing, radiant skin. Contains glycolic acid and vitamin C to exfoliate dead skin cells and boost collagen.',
            'LEUCODERM': 'LEUCODERM is a medicated lotion specifically formulated for skin depigmentation treatment. Helps manage vitiligo and hypopigmentation by stimulating melanocyte activity.',
            'PDRN MASK': 'PDRN MASK is an advanced sheet mask infused with Polydeoxyribonucleotide (PDRN) for intensive skin repair. Helps accelerate wound healing, reduce acne scars, and improve skin texture.',
            'Scparal Mask': 'Scparal Mask is a soothing face mask enriched with centella asiatica and allantoin. Specifically designed to calm irritated skin, reduce redness, and repair skin barrier.',
            'ECTOSOL SS TINT SPF 50': 'ECTOSOL SS TINT SPF 50 is a tinted sunscreen that provides flawless coverage while protecting skin. Offers high SPF 50 protection against harmful UV rays.',
            'Elight Sunscreen': 'Elight Sunscreen is a lightweight, reef-safe sunscreen suitable for sensitive skin. Provides broad-spectrum SPF 50 protection without harsh chemicals.',
            'Cuhair Tab': 'Cuhair Tab is a hair growth supplement enriched with biotin, zinc, and essential vitamins. Supports healthy hair growth from within.',
        }
        
        default_demo_prices = {
            'LIPSTAR': 550, 'WHITOLYN': 360, 'XANONICE TAB': 360, 'Picotry Cream': 1350,
            'HZEUP SOAP': 310, 'ROOFS SPF': 999, 'Opuoxy Bright': 680, 'GLOWORG': 730,
            'NIDGLOW - G': 1380, 'LEUCODERM': 1790, 'PDRN MASK': 700, 'Scparal Mask': 300,
            'ECTOSOL SS TINT SPF 50': 1180, 'Elight Sunscreen': 850, 'Cuhair Tab': 284,
        }
        
        for name, desc in default_descriptions.items():
            product = Product.query.filter_by(name=name).first()
            if product:
                if not product.description:
                    product.description = desc
                if not product.demo_price:
                    product.demo_price = default_demo_prices.get(name, 0)
        
        db.session.commit()
        
        if Product.query.count() == 0:
            products_data = [
                {'name': 'LIPSTAR', 'category': 'Lip Care', 'current_stock': 0, 'minimum_stock': 3, 'sale_price': 275, 'purchase_price': 65.63, 'demo_price': 550, 'description': 'LIPSTAR is a premium lip care product designed to provide deep hydration and a natural shine. Formulated with vitamin E and natural oils, it helps prevent dry lips and gives a subtle, lasting gloss. Perfect for daily use, this lip care essential suits all skin types and provides protection against environmental damage.'},
                {'name': 'WHITOLYN', 'category': 'Body Care', 'current_stock': 0, 'minimum_stock': 0, 'sale_price': 180, 'purchase_price': 122.04, 'demo_price': 360, 'description': 'WHITOLYN is an advanced body care lotion that brightens and evens skin tone. Enriched with glutathione and Kojic acid, it helps reduce dark spots, blemishes, and hyperpigmentation. Regular application reveals smoother, radiant skin while providing long-lasting moisturization.'},
                {'name': 'XANONICE TAB', 'category': 'Tablet', 'current_stock': 10, 'minimum_stock': 0, 'sale_price': 180, 'purchase_price': 180, 'demo_price': 360, 'description': 'XANONICE TAB is a dietary supplement formulated to support overall skin health from within. Contains essential vitamins and minerals that promote collagen production, reduce inflammation, and protect against oxidative stress. Recommended for achieving healthy, glowing skin.'},
                {'name': 'Picotry Cream', 'category': 'Cream', 'current_stock': 0, 'minimum_stock': 0, 'sale_price': 675, 'purchase_price': 288.75, 'demo_price': 1350, 'description': 'Picotry Cream is a specialized skincare treatment targeting stubborn pigmentation and uneven skin tone. Its advanced formula combines natural extracts with proven whitening agents to deliver visible results. Effective for age spots, sun damage, and melasma. Suitable for all skin types.'},
                {'name': 'HZEUP SOAP', 'category': 'Soap', 'current_stock': 0, 'minimum_stock': 5, 'sale_price': 155, 'purchase_price': 42, 'demo_price': 310, 'description': 'HZEUP SOAP is an antibacterial soap infused with herbal extracts for deep cleansing. Formulated with neem and tea tree oil, it effectively fights acne-causing bacteria while being gentle on skin. Helps reduce breakouts, controls excess oil, and keeps skin fresh throughout the day.'},
                {'name': 'ROOFS SPF', 'category': 'Sunscreen', 'current_stock': 0, 'minimum_stock': 2, 'sale_price': 500, 'purchase_price': 260, 'demo_price': 999, 'description': 'ROOFS SPF is a broad-spectrum sunscreen providing SPF 50+ protection against UVA and UVB rays. Lightweight and non-greasy formula absorbs quickly without white cast. Enriched with antioxidants to prevent sun damage, premature aging, and skin darkening. Water-resistant for up to 80 minutes.'},
                {'name': 'Opuoxy Bright', 'category': 'Cream', 'current_stock': 14, 'minimum_stock': 0, 'sale_price': 340, 'purchase_price': 230.51, 'demo_price': 680, 'description': 'Opuoxy Bright is a revolutionary brightening cream that targets dullness and uneven skin tone. Contains Oxyresveratrol and vitamin C for powerful antioxidant protection. Reduces dark circles, blemishes, and age spots while improving skin elasticity. For best results, use twice daily.'},
                {'name': 'GLOWORG', 'category': 'Cream', 'current_stock': 0, 'minimum_stock': 3, 'sale_price': 365, 'purchase_price': 20, 'demo_price': 730, 'description': 'GLOWORG is an all-in-one fairness cream that works to brighten, moisturize, and protect skin. Infused with arbutin and mulberry extract, it helps reduce melanin production for visibly lighter skin tone. Provides SPF 20 sun protection and keeps skin hydrated for up to 24 hours.'},
                {'name': 'NIDGLOW - G', 'category': 'Gel', 'current_stock': 1, 'minimum_stock': 0, 'sale_price': 690, 'purchase_price': 198.8, 'demo_price': 1380, 'description': 'NIDGLOW - G is a premium face gel designed for glowing, radiant skin. Contains glycolic acid and vitamin C to exfoliate dead skin cells and boost collagen. Helps reduce pores, acne marks, and fine lines. Also provides cooling effect and reduces tanning. Apply on clean face before moisturizer.'},
                {'name': 'LEUCODERM', 'category': 'Lotion', 'current_stock': 0, 'minimum_stock': 2, 'sale_price': 895, 'purchase_price': 322.5, 'demo_price': 1790, 'description': 'LEUCODERM is a medicated lotion specifically formulated for skin depigmentation treatment. Helps manage vitiligo and hypopigmentation by stimulating melanocyte activity. Contains monobenzyl ether of hydroquinone. For external use only. Consult dermatologist before use.'},
                {'name': 'PDRN MASK', 'category': 'Face Mask', 'current_stock': 0, 'minimum_stock': 0, 'sale_price': 350, 'purchase_price': 0, 'demo_price': 700, 'description': 'PDRN MASK is an advanced sheet mask infused with Polydeoxyribonucleotide (PDRN) for intensive skin repair. Helps accelerate wound healing, reduce acne scars, and improve skin texture. Provides deep hydration and boosts skin elasticity. Perfect for damaged or stressed skin.'},
                {'name': 'Scparal Mask', 'category': 'Face Mask', 'current_stock': 0, 'minimum_stock': 0, 'sale_price': 150, 'purchase_price': 0, 'demo_price': 300, 'description': 'Scparal Mask is a soothing face mask enriched with centella asiatica and allantoin. Specifically designed to calm irritated skin, reduce redness, and repair skin barrier. Ideal for sensitive skin or after cosmetic procedures. Use 2-3 times per week for optimal results.'},
                {'name': 'ECTOSOL SS TINT SPF 50', 'category': 'Sunscreen', 'current_stock': 3, 'minimum_stock': 0, 'sale_price': 590, 'purchase_price': 236, 'demo_price': 1180, 'description': 'ECTOSOL SS TINT SPF 50 is a tinted sunscreen that provides flawless coverage while protecting skin. Offers high SPF 50 protection against harmful UV rays. The light tint blends seamlessly with natural skin tone. Water-based formula is non-comedogenic and suitable for daily use.'},
                {'name': 'Elight Sunscreen', 'category': 'Sunscreen', 'current_stock': 7, 'minimum_stock': 0, 'sale_price': 425, 'purchase_price': 174.6, 'demo_price': 850, 'description': 'Elight Sunscreen is a lightweight, reef-safe sunscreen suitable for sensitive skin. Provides broad-spectrum SPF 50 protection without harsh chemicals. Enriched with aloe vera and chamomile to soothe and protect. Fast-absorbing formula leaves no residue. Perfect for outdoor activities.'},
                {'name': 'Cuhair Tab', 'category': 'Tablet', 'current_stock': 30, 'minimum_stock': 0, 'sale_price': 142, 'purchase_price': 57.766, 'demo_price': 284, 'description': 'Cuhair Tab is a hair growth supplement enriched with biotin, zinc, and essential vitamins. Supports healthy hair growth from within by providing nutrients directly to hair follicles. Helps reduce hair fall, improve hair thickness, and enhance overall hair health. Take one tablet daily.'},
            ]
            
            for p in products_data:
                product = Product(**p)
                db.session.add(product)
            
            db.session.commit()
            print(f'Added {len(products_data)} products to database')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
