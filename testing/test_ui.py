__author__ = 'sameer'

import unittest
from selenium import webdriver
import random, string

class TestSputnik(unittest.TestCase):
    def setUp(self):
        self.driver = webdriver.Chrome()

    def test_connect(self):
        self.driver.get('http://localhost:8888')
        self.assertEqual(self.driver.title, 'MexBT Trading Platform')

    def test_register(self):
        self.driver.get('http://localhost:8888')
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
