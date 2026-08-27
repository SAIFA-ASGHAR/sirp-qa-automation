from pages.login_page import LoginPage

def login(page):
    login_page = LoginPage(page)
    login_page.open()
    login_page.login(
        email="saifaasghar@gmail.com",
        password="S@1f@s1rp"
    )
