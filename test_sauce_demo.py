import time
import os
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@pytest.fixture(scope="module")
def driver():
	"""Module-scoped fixture to initialize and quit the Chrome WebDriver."""
	options = webdriver.ChromeOptions()
	# Run headless by default if CI env var is set, else interactive
	if os.getenv("CI") == "true":
		options.add_argument("--headless=new")
		options.add_argument("--no-sandbox")
		options.add_argument("--disable-dev-shm-usage")

	logger.info("Starting Chrome WebDriver")
	service = Service(ChromeDriverManager().install())
	drv = webdriver.Chrome(service=service, options=options)
	drv.maximize_window()
	yield drv
	logger.info("Quitting Chrome WebDriver")
	drv.quit()


@pytest.fixture(scope="module")
def base_url():
	return "https://www.saucedemo.com/"


def login(driver: WebDriver, base_url: str, username: str = "standard_user", password: str = "secret_sauce"):
	"""Helper to perform login on Sauce Demo."""
	driver.get(base_url)
	WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "user-name")))
	driver.find_element(By.ID, "user-name").send_keys(username)
	driver.find_element(By.ID, "password").send_keys(password)
	driver.find_element(By.ID, "login-button").click()
	# Wait for inventory page
	WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "inventory_container")))


def add_product_to_cart(driver: WebDriver, product_name: str):
	"""Find a product by name on the inventory page and add it to cart."""
	products = driver.find_elements(By.CLASS_NAME, "inventory_item")
	for p in products:
		name = p.find_element(By.CLASS_NAME, "inventory_item_name").text.strip()
		if name == product_name:
			btn = p.find_element(By.TAG_NAME, "button")
			btn.click()
			# wait for cart badge to appear or button to change to 'Remove'
			try:
				WebDriverWait(driver, 5).until(
					lambda d: any(b.text.lower() == "remove" for b in p.find_elements(By.TAG_NAME, "button"))
				)
			except Exception:
				# fallback: wait for shopping cart badge
				try:
					WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "shopping_cart_badge")))
				except Exception:
					return False
			return True
	return False


def go_to_cart_and_checkout(driver: WebDriver):
	driver.find_element(By.CLASS_NAME, "shopping_cart_link").click()
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.CLASS_NAME, "cart_list")))
	# click checkout and wait for checkout info container to appear
	checkout_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "checkout")))
	checkout_btn.click()
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "checkout_info_container")))


def go_to_cart(driver: WebDriver):
	"""Navigate to the shopping cart page and wait for it to load."""
	driver.find_element(By.CLASS_NAME, "shopping_cart_link").click()
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.CLASS_NAME, "cart_list")))


def clear_cart(driver: WebDriver):
	"""Remove any items currently in the cart to ensure test isolation."""
	# go to inventory page
	driver.get("https://www.saucedemo.com/inventory.html")
	time.sleep(0.5)
	# click burger menu -> reset app state if present
	try:
		menu = driver.find_element(By.ID, "react-burger-menu-btn")
		menu.click()
		WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.ID, "reset_sidebar_link")))
		driver.find_element(By.ID, "reset_sidebar_link").click()
		# close menu
		driver.find_element(By.ID, "react-burger-cross-btn").click()
	except Exception:
		# fallback: remove any 'Remove' buttons on inventory
		try:
			removes = driver.find_elements(By.XPATH, "//button[text()='Remove']")
			for r in removes:
				r.click()
		except Exception:
			pass


def fill_checkout_info(driver: WebDriver, first_name: str = "Test", last_name: str = "User", postal: str = "12345"):
	driver.find_element(By.ID, "first-name").send_keys(first_name)
	driver.find_element(By.ID, "last-name").send_keys(last_name)
	driver.find_element(By.ID, "postal-code").send_keys(postal)
	driver.find_element(By.ID, "continue").click()


def finish_checkout(driver: WebDriver):
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "checkout_summary_container")))
	driver.find_element(By.ID, "finish").click()
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.CLASS_NAME, "complete-header")))


@pytest.mark.order(1)
def test_order_confirmation(driver, base_url):
	"""Order Confirmation: Add an item, checkout, and verify completion message."""
	login(driver, base_url)
	clear_cart(driver)
	product = "Sauce Labs Backpack"
	assert add_product_to_cart(driver, product), f"Failed to add product {product} to cart"
	go_to_cart_and_checkout(driver)
	fill_checkout_info(driver)
	finish_checkout(driver)
	completed = driver.find_element(By.CLASS_NAME, "complete-header").text
	assert "THANK YOU FOR YOUR ORDER" in completed.upper()


@pytest.mark.order(2)
def test_order_cancellation(driver, base_url):
	"""Order Cancellation: Add an item, go to checkout, then cancel and verify cart still contains item or returned to cart page."""
	login(driver, base_url)
	clear_cart(driver)
	product = "Sauce Labs Bike Light"
	assert add_product_to_cart(driver, product), "Failed to add product to cart"
	go_to_cart_and_checkout(driver)
	# On checkout info page, cancel should return to cart
	driver.find_element(By.ID, "cancel").click()
	# We should be back on cart page with the item present
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.CLASS_NAME, "cart_list")))
	cart_items = [e.text for e in driver.find_elements(By.CLASS_NAME, "inventory_item_name")]
	assert product in cart_items, "Product not present in cart after cancellation"


@pytest.mark.order(3)
def test_checkout_details_verification(driver, base_url):
	"""Checkout Details Verification: Verify product name, price, quantity and description in the checkout summary."""
	login(driver, base_url)
	clear_cart(driver)
	product = "Sauce Labs Bolt T-Shirt"
	# Add product
	assert add_product_to_cart(driver, product), "Failed to add product to cart"
	go_to_cart(driver)
	# On cart page, verify product details exist (wait for them)
	item_name = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.CLASS_NAME, "inventory_item_name"))).text
	item_desc = driver.find_element(By.CLASS_NAME, "inventory_item_desc").text
	item_price = driver.find_element(By.CLASS_NAME, "inventory_item_price").text
	# Proceed to checkout info: click checkout on cart page then fill info
	checkout_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "checkout")))
	checkout_btn.click()
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "checkout_info_container")))
	fill_checkout_info(driver)
	WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "checkout_summary_container")))
	qty = driver.find_element(By.CLASS_NAME, "cart_quantity").text
	assert item_name == product, "Product name mismatch"
	assert item_price.startswith("$") and len(item_price) > 1, "Price appears invalid"
	assert qty == "1", f"Expected quantity 1 but found {qty}"
	assert len(item_desc) > 5, "Description is unexpectedly short"
