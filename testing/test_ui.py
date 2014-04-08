__author__ = 'sameer'

import unittest
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import random, string

class TestSputnik(unittest.TestCase):
    def setUp(self):
        self.driver = webdriver.Chrome()
        self.driver.get('http://localhost:8888')

    def test_connect(self):
        self.assertEqual(self.driver.title, 'MexBT Trading Platform')
        self.driver.close()

    def test_register(self):
        test_username = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        test_password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        test_nickname = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        self.driver.find_element_by_id("register").click()
        self.driver.find_element_by_id("register_username").send_keys(test_username)
        self.driver.find_element_by_id("register_password").send_keys(test_password)
        self.driver.find_element_by_id("register_nickname").send_keys(test_nickname)
        self.driver.find_element_by_id("register_email").send_keys("test@m2.io")
        self.driver.find_element_by_id("register_eula").click()
        self.driver.find_element_by_id("register_button").click()
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'account_menu'))
        )
        self.driver.close()

    def test_login(self):
        self.driver.get('http://localhost:8888')
        self.driver.find_element_by_id("login").click()
        self.driver.find_element_by_id("login_username").send_keys("marketmaker")
        self.driver.find_element_by_id("login_password").send_keys("marketmaker")
        self.driver.find_element_by_id("login_button").click()
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'account_menu'))
        )
        self.driver.close()



