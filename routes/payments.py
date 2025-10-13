from flask import Blueprint, jsonify, request, session, render_template
import stripe
from config import Config

payments_bp = Blueprint('payments', __name__)

# Initialize Stripe
stripe.api_key = Config.STRIPE_SECRET_KEY

@payments_bp.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    if 'user_id' not in session:
        return jsonify({'error': 'You must be logged in'}), 401
    
    try:
        data = request.json
        
        # Validate amount is provided and is a positive number
        if not data or 'amount' not in data:
            return jsonify({'error': 'Amount is required'}), 400
            
        # Parse amount and ensure it's an integer
        try:
            amount = int(data.get('amount', 1))
        except (ValueError, TypeError):
            # If amount can't be parsed as an integer, default to £1
            amount = 1
        
        # Enforce minimum amount of £1
        amount = max(1, amount)
        
        # Log the request to help with debugging
        print(f"Creating checkout session for amount: £{amount}")
        
        # Create a checkout session with only the card payment method for maximum compatibility
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card', 'klarna', 'pay_by_bank', 'samsung_pay', 'afterpay_clearpay', 'revolut_pay', 'paypal'],
            line_items=[{
                'price_data': {
                    'currency': 'gbp',
                    'product_data': {
                        'name': f'Support flashcards.josh.software',
                        'description': 'Thank you so much for considering supporting! This is an indie site so any proceeds will really be appreciated. We support multiple payment methods. Please note that PayPal may apply higher transaction fees on small payments, which reduces the amount we receive.',
                    },
                    'unit_amount': int(amount * 100),  # Convert to pence
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.url_root + 'payment-success',
            cancel_url=request.url_root,
        )
        
        print(f"Checkout session created with ID: {checkout_session.id}")
        return jsonify({'id': checkout_session.id})
    except stripe.error.StripeError as e:
        # These are Stripe-specific errors
        error_msg = str(e)
        print(f"Stripe error occurred: {error_msg}")
        return jsonify({'error': error_msg}), 400
    except Exception as e:
        # For any other unexpected errors
        error_msg = str(e)
        print(f"Unexpected error creating checkout session: {error_msg}")
        return jsonify({'error': error_msg}), 500

@payments_bp.route('/payment-success')
def payment_success():
    """Payment success page."""
    return render_template('payment_success.html')

def inject_stripe_key():
    """Context processor to inject Stripe publishable key."""
    return dict(stripe_publishable_key=Config.STRIPE_PUBLISHABLE_KEY)
