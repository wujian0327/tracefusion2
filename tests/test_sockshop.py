import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('sockshop', Path(__file__).resolve().parents[1] / 'scripts/sockshop.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ResponseValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = {'customer_id': 'a' * 24, 'firstName': 'Test',
                        'card': {'longNum': '4111111111111111', 'ccv': '123'},
                        'address': {'street': 'TestStreet'},
                        'item': {'itemId': 'fixture-item', 'quantity': 1, 'unitPrice': 5.0}}
        self.order = {'id': 'b' * 24, 'customerId': 'a' * 24,
                      'customer': {'firstName': 'Test'},
                      'address': {'street': 'TestStreet'},
                      'card': dict(self.fixture['card']),
                      'items': [dict(self.fixture['item'])], 'total': 9.99}

    def test_http_200_application_error_is_not_success(self):
        with self.assertRaises(RuntimeError):
            app.validate_payload(200, {'status_code': 500, 'error': 'database unavailable'})

    def test_wrong_customers_order_is_rejected_even_with_same_card_value(self):
        self.order['customerId'] = 'c' * 24
        with self.assertRaises(RuntimeError):
            app.verify_order(self.order, self.fixture)

    def test_wrong_cart_or_failed_order_is_not_a_negative_exposure(self):
        self.order['items'][0]['itemId'] = 'unrelated-item'
        with self.assertRaises(RuntimeError):
            app.verify_order(self.order, self.fixture)
        with self.assertRaises(RuntimeError):
            app.verify_order({'message': 'payment declined'}, self.fixture)

    def test_full_card_and_masked_card_are_distinguished(self):
        full = app.verify_order(self.order, self.fixture)['fields']
        self.assertEqual(full['card.longNum'], 'full_value_returned')
        self.assertEqual(full['card.ccv'], 'full_value_returned')
        self.order['card'] = {'longNum': '************1111'}
        masked = app.verify_order(self.order, self.fixture)['fields']
        self.assertEqual(masked['card.longNum'], 'last_four_only_or_masked')
        self.assertEqual(masked['card.ccv'], 'absent_or_empty')

    def test_other_full_card_with_same_suffix_is_not_called_masked(self):
        self.assertEqual(app.classify('5555555555551111', '4111111111111111'),
                         'different_value_needs_review')

    def test_order_save_total_and_identity_are_required(self):
        for key, value in [('id', None), ('total', 0)]:
            order = copy.deepcopy(self.order)
            order[key] = value
            with self.assertRaises(RuntimeError):
                app.verify_order(order, self.fixture)


if __name__ == '__main__':
    unittest.main()
