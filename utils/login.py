import os
from pages.login_page import LoginPage

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env for local runs; no-op in CI if file is absent
except ImportError:
    pass

def login(page):
    email = os.environ.get("SIRP_EMAIL")
    password = os.environ.get("SIRP_PASSWORD")

    if not email or not password:
        raise RuntimeError(
            "Missing SIRP_EMAIL / SIRP_PASSWORD environment variables. "
            "Set them in a local .env file (see .env.example) or as "
            "GitHub Actions repository secrets for CI."
        )

    login_page = LoginPage(page)
    login_page.open()
    login_page.login(email=email, password=password)
