from unittest import TestSuite
from unittest import TestLoader

from django_elasticsearch.tests.indexable import EsIndexableTestCase


def suite():
    suite = TestSuite()
    loader = TestLoader()

    test_cases = [EsIndexableTestCase]

    try:
        from django_elasticsearch.tests.restframework import EsRestFrameworkTestCase
    except Exception, e:
        print 'Skipping test of restframework contrib, reason: ', e
    else:
        print 'App restframework found, testing contrib.restframework'
        test_cases.append(EsRestFrameworkTestCase)

    try:
        from django_elasticsearch.tests.taggitt import EsTaggitTestCase
    except Exception, e:
        print 'Skipping test of taggit contrib, reason: ', e
    else:
        print 'App taggit found, testing contrib.taggit'
        test_cases.append(EsTaggitTestCase)

    for test_case in test_cases:
        tests = loader.loadTestsFromTestCase(test_case)
        suite.addTests(tests)

    return suite
