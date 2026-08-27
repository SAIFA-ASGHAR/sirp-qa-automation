from playwright.sync_api import Page, expect

class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.email_input    = page.locator("input[type='text'], input[type='email']").first
        self.password_input = page.locator("input[type='password']").first
        self.login_button   = page.get_by_role("button", name="Login")

    def open(self):
        self.page.goto("https://demo3.sirp.io/login")

    def login(self, email: str, password: str):
        self.email_input.fill(email)
        self.password_input.fill(password)
        self.login_button.click()
        expect(self.page).not_to_have_url("**/login**", timeout=15000)
