from flask import Blueprint, jsonify, request, session, render_template, redirect
from config import Config

payments_bp = Blueprint('payments', __name__)

# GitHub Sponsors configuration
GITHUB_SPONSORS_URL = Config.GITHUB_SPONSORS_URL
GITHUB_REPO_URL = Config.GITHUB_REPO_URL

@payments_bp.route('/github-sponsor', methods=['POST'])
def redirect_to_github_sponsor():
    """Redirect to GitHub Sponsors page."""
    return jsonify({'redirect_url': GITHUB_SPONSORS_URL})

@payments_bp.route('/github-star', methods=['POST'])
def redirect_to_github_star():
    """Redirect to GitHub repository for starring."""
    return jsonify({'redirect_url': GITHUB_REPO_URL})

@payments_bp.route('/payment-success')
def payment_success():
    """Payment success page (now for GitHub sponsors)."""
    return render_template('payment_success.html')

def inject_github_config():
    """Context processor to inject GitHub configuration."""
    return dict(
        github_sponsors_url=GITHUB_SPONSORS_URL,
        github_repo_url=GITHUB_REPO_URL
    )
