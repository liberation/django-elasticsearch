from unittest import TestSuite
from unittest import TestLoader
from unittest import TestCase

from django_elasticsearch.tests.models import TestModel
from django_elasticsearch.tests.test_views import EsViewTestCase
from django_elasticsearch.tests.test_qs import EsQuerysetTestCase
from django_elasticsearch.tests.test_indexable import EsIndexableTestCase


try:
    from django_elasticsearch.tests.test_restframework import EsRestFrameworkTestCase
except Exception, e:
    print 'Skipping test of restframework contrib, reason: ', e

    class FakeTestCase(TestCase):
        """
        Note: have to do this, because if i append the TestCase to the suit
        dynamically i can't call it with test django_elasticsearch.MyTest
        """
        pass
    EsRestFrameworkTestCase = FakeTestCase
else:
    print 'App restframework found, testing contrib.restframework'


def suite():
    suite = TestSuite()
    loader = TestLoader()

    test_cases = [
        EsViewTestCase,
        EsQuerysetTestCase,
        EsIndexableTestCase,
        EsRestFrameworkTestCase]

    if not TestModel.es.check_cluster():
        print "Test skipped. Could not connect to elasticsearch."
    else:
        for test_case in test_cases:
            tests = loader.loadTestsFromTestCase(test_case)
            suite.addTests(tests)

    return suite
