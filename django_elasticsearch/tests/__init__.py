from unittest import TestSuite
from unittest import TestLoader
from unittest import TestCase

from django_elasticsearch.tests.qs import EsQuerysetTestCase
from django_elasticsearch.tests.indexable import EsIndexableTestCase


class FakeTestCase(TestCase):
        pass

try:
    from django_elasticsearch.tests.restframework import EsRestFrameworkTestCase
except Exception, e:
    print 'Skipping test of restframework contrib, reason: ', e
    EsRestFrameworkTestCase = FakeTestCase
else:
    print 'App restframework found, testing contrib.restframework'


def suite():
    suite = TestSuite()
    loader = TestLoader()

    test_cases = [EsQuerysetTestCase,
                  EsIndexableTestCase,
                  EsRestFrameworkTestCase]

    for test_case in test_cases:
        tests = loader.loadTestsFromTestCase(test_case)
        suite.addTests(tests)

    return suite
