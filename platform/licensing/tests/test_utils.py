from decimal import Decimal

from django.test import TestCase

from licensing.utils import cents_to_dollars


class UtilsTest(TestCase):
    def test_cents_to_dollars(self):
        dollars = cents_to_dollars(1937)

        self.assertEqual(dollars, Decimal('19.37'))
