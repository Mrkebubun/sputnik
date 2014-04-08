__author__ = 'sameer'

import unittest
from selenium import webdriver

class TestSputnik(unittest.TestCase):
    def setUp(self):
        self.driver = webdriver.Chrome()

    def test_connect(self):
        self.driver.get('http://localhost:8888')
        self.assertEqual(self.driver.title, 'MexBT Trading Platform')