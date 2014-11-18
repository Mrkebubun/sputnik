import sys
import os
from test_sputnik import fix_config, TestSputnik, FakeComponent
from twisted.internet import defer, reactor, task
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

fix_config()

from sputnik import models, margin

class TestMargin(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        self.create_account("test")
        self.user = self.get_user("test")

    def create_position(self, ticker, quantity):
        from sputnik import models
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
        from sqlalchemy.orm.exc import NoResultFound
        try:
            position = self.session.query(models.Position).filter_by(user=self.user, contract=contract).one()
            position.position = quantity
            self.session.commit()
        except NoResultFound:
            position = models.Position(self.user, contract, quantity)
            self.session.add(position)

        self.session.commit()

    def create_order(self, ticker, quantity, price, side, accepted=True):
        from sputnik import models
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
        order = models.Order(self.user, contract, quantity, price, side)
        order.accepted = accepted
        self.session.add(order)
        self.session.commit()
        return order.id

    def cancel_order(self, id):
        from sputnik import models
        order = self.session.query(models.Order).filter_by(id=id).one()
        order.is_cancelled = True
        self.session.commit()

    def get_position(self, ticker):
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
        position = self.session.query(models.Position).filter_by(user=self.user, contract=contract).one()
        return position

    def test_cash_pairs_only(self):

        # We don't have to create a BTC position, because
        # the margin checking code doesn't worry about our
        # BTC position, however there is a weird hack so that if
        # the cash_spent exceeds my fiat positions, then margin
        # gets set really high, so we need a fiat position to test
        # that

        # 1 Peso
        self.create_position('MXN', 10000)

        # No orders
        from sputnik import margin
        test = self.get_user('test')
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        self.assertEqual(low_margin, 0)
        self.assertEqual(high_margin, 0)
        self.assertDictEqual(max_cash_spent, {'MXN': 0, 'BTC': 0})

        # With a BUY order
        id = self.create_order('BTC/MXN', 50000000, 5000, 'BUY')
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        self.assertEqual(low_margin, 0)
        self.assertEqual(high_margin, 0)
        # 2500 for the trade, and 100bps for the fee
        self.assertDictEqual(max_cash_spent, {'MXN': 2500 * 1.01, 'BTC': 0})
        self.cancel_order(id)

        # With a SELL order
        id = self.create_order('BTC/MXN', 50000000, 500, 'SELL')
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        # BTC cash spent gets applied to margin
        self.assertEqual(low_margin, 50000000)
        self.assertEqual(high_margin, 50000000)
        self.assertDictEqual(max_cash_spent, {'MXN': 0, 'BTC': 50000000})
        self.cancel_order(id)

        # With too big an order in terms of fiat
        # 0.5BTC for 3Pesos each for 1.5Peso total cost plus fees
        id = self.create_order('BTC/MXN', 50000000, 30000, 'BUY')
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        self.assertGreaterEqual(low_margin, 2**48)
        self.assertGreaterEqual(high_margin, 2**48)
        # 100bps fee
        self.assertDictEqual(max_cash_spent, {'MXN': 15000 * 1.01, 'BTC': 0})
        self.cancel_order(id)

        # With a big order in terms of BTC
        # Sell 2 BTC for 1.5Peos each
        id = self.create_order('BTC/MXN', 200000000, 15000, 'SELL')
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        self.assertEqual(low_margin, 200000000)
        self.assertEqual(high_margin, 200000000)
        self.assertDictEqual(max_cash_spent, {'MXN': 0, 'BTC': 200000000})
        self.cancel_order(id)

        # a bunch of random orders
        self.create_order('BTC/MXN', 50000000, 15000, 'SELL')
        self.create_order('BTC/MXN', 25000000, 15000, 'BUY')
        self.create_order('BTC/MXN', 20000000, 10000, 'BUY')
        self.create_order('BTC/MXN', 30000000,  2500, 'BUY')
        self.create_order('BTC/MXN', 20000000, 15000, 'SELL')

        BTC_spent = 50000000 + 20000000
        # 100bps fee
        MXN_spent = int((25000000 * 15000 / 100000000 ) * 1.01) + int((20000000 * 10000 / 100000000 ) * 1.01) + int((30000000 * 2500 / 100000000 ) * 1.01)
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        self.assertEqual(low_margin, BTC_spent)
        self.assertEqual(high_margin, BTC_spent)
        self.assertDictEqual(max_cash_spent, {'MXN': MXN_spent, 'BTC': BTC_spent})

        # Now a too big order in terms of MXN
        self.create_order('BTC/MXN', 50000000, 30000, 'BUY')
        # 100bps fee
        MXN_spent += (50000000 * 30000 / 100000000) * 1.01
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        self.assertGreaterEqual(low_margin, 2**48)
        self.assertGreaterEqual(high_margin, 2**48)
        self.assertDictEqual(max_cash_spent, {'MXN': MXN_spent, 'BTC': BTC_spent})

    def test_predictions_only(self):
        # Check margin given some positions
        from sputnik import margin
        test = self.get_user('test')

        # Long position, no margin needed
        self.create_position('NETS2015', 4)
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        self.assertEqual(low_margin, 0)
        self.assertEqual(high_margin, 0)
        self.assertDictEqual(max_cash_spent, {'BTC': 0})

        # Short position, fully margined
        self.create_position('NETS2015', -4)
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        # (4 x lotsize)
        self.assertEqual(low_margin, 4000000)
        self.assertEqual(high_margin, 4000000)
        self.assertDictEqual(max_cash_spent, {'BTC': 0})

        # With a long order, no position
        self.create_position('NETS2015', 0)
        id = self.create_order('NETS2015', 1, 500, 'BUY')
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        # 1x0.5x lot size plus fee (200bps)
        self.assertEqual(low_margin, round(500000 * 1.02))
        self.assertEqual(high_margin, round(500000 * 1.02))

        # Cash spent for BTC is only the fee here, the cash spent on the trade
        # is dealt with already in the margin calculation
        # 200bps fee
        self.assertDictEqual(max_cash_spent, {'BTC': round(500000 * 0.02)})
        self.cancel_order(id)

        # With a short order
        id = self.create_order('NETS2015', 1, 500, 'SELL')
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(test, self.session)
        # 1x(1 - 0.5)xlot_size (will have to pay 1 if clears at 1, but will receive 0.5 when traded)
        # Also have to pay a fee (200bps)
        self.assertEqual(low_margin, round(500000 * 1.02))
        self.assertEqual(high_margin, round(500000 * 1.02))
        self.assertDictEqual(max_cash_spent, {'BTC': round(500000 * 0.02)})
        self.cancel_order(id)

    def test_sufficient_cash(self):
        self.create_position("BTC", 100000000)
        id = self.create_order("BTC/MXN", 100000, 5500, "SELL", False)

        low, high, _ = margin.calculate_margin(self.user, self.session, {}, id)
        
        assert high < self.get_position("BTC").position

    def test_insufficient_cash(self):
        self.create_position("BTC", 100000000)
        id = self.create_order("BTC/MXN", 1000000000, 5500, "SELL", False)

        low, high, _ = margin.calculate_margin(self.user, self.session, {}, id)
        assert high > self.get_position("BTC").position
    
    def test_sufficient_cash_with_order(self):
        self.create_position("BTC", 100000000)
        self.create_order("BTC/MXN", 40000000, 5500, "SELL", True)
        id = self.create_order("BTC/MXN", 50000000, 5500, "SELL", False)

        low, high, _ = margin.calculate_margin(self.user, self.session, {}, id)
        assert high < self.get_position("BTC").position

    def test_insufficient_cash_with_order(self):
        self.create_position("BTC", 100000000)
        self.create_order("BTC/MXN", 60000000, 5500, "SELL", True)
        id = self.create_order("BTC/MXN", 50000000, 5500, "SELL", False)

        low, high, _ = margin.calculate_margin(self.user, self.session, {}, id)
        assert high > self.get_position("BTC").position

