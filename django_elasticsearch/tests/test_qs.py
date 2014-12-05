import mock

from django.test import TestCase
from django.test.utils import override_settings

from django_elasticsearch.client import es_client
from django_elasticsearch.managers import EsQueryset
from django_elasticsearch.tests.utils import withattrs
from django_elasticsearch.tests.models import TestModel


@override_settings(
    ELASTICSEARCH_AUTO_INDEX=False,
    ELASTICSEARCH_SETTINGS={})
class EsQuerysetTestCase(TestCase):

    def setUp(self):
        # create a bunch of documents
        TestModel.es.create_index(ignore=True)

        self.t1 = TestModel.objects.create(username=u"woot woot", first_name=u"John", last_name=u"Smith")
        self.t1.es.do_index()

        self.t2 = TestModel.objects.create(username=u"woot", first_name=u"Jack", last_name=u"Smith")
        self.t2.es.do_index()

        self.t3 = TestModel.objects.create(username=u"BigMama", first_name=u"Mama", last_name=u"Smith")
        self.t3.es.do_index()

        self.t4 = TestModel.objects.create(username=u"foo", first_name=u"Foo", last_name=u"Bar")
        self.t4.es.do_index()

        TestModel.es.do_update()

    def tearDown(self):
        es_client.indices.delete(index=TestModel.es.get_index())

    def test_all(self):
        qs = TestModel.es.search("")
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 in contents)

    def test_repr(self):
        qs = TestModel.es.queryset.order_by('id')
        contents = str(qs.deserialize())
        expected = str(TestModel.objects.all())
        self.assertEqual(contents, expected)

    def test_use_cache(self):
        # Note: we use _make_search_body because it's only called
        # if the cache store is not hit
        fake_body = {'query': {'match': {'_all': 'foo'}}}
        with mock.patch.object(EsQueryset,
                               'make_search_body') as mocked:
            mocked.return_value = fake_body
            qs = TestModel.es.search("")
            # eval
            list(qs)
            # use cache
            list(qs)
        mocked.assert_called_once()

        # same for a sliced query
        with mock.patch.object(EsQueryset,
                               'make_search_body') as mocked:
            mocked.return_value = fake_body
            # re-eval
            list(qs[0:5])
            # use cache
            list(qs[0:5])
        mocked.assert_called_once()

    def test_facets(self):
        qs = TestModel.es.queryset.facet(['last_name'])
        expected = {u'doc_count': 4,
                    u'last_name': {u'buckets': [{u'doc_count': 3,
                                                 u'key': u'smith'},
                                                {u'doc_count': 1,
                                                 u'key': u'bar'}]}}
        self.assertEqual(expected, qs.facets)

    def test_non_global_facets(self):
        qs = TestModel.es.queryset.facet(['last_name'], use_globals=False).query("Foo")
        expected = {u'last_name': {u'buckets': [{u'doc_count': 1,
                                                 u'key': u'bar'}]}}
        self.assertEqual(expected, qs.facets)

    def test_suggestions(self):
        qs = TestModel.es.search('smath').suggest(['last_name'])
        expected = {
            u'last_name': [
                {u'length': 5,
                 u'offset': 0,
                 # TODO: understand why the `freq` attribute is 6 when there is only 3 hits ?
                 u'options': [{u'freq': 6,
                               u'score': 0.8,
                               u'text': u'smith'}],
                 u'text': u'smath'}]}
        self.assertEqual(expected, qs.suggestions)

    def test_count(self):
        self.assertEqual(TestModel.es.count(), 4)
        self.assertEqual(TestModel.es.search("John").count(), 1)
        self.assertEqual(TestModel.es.search("").filter(last_name=u"Smith").count(), 3)

    def test_ordering(self):
        qs = TestModel.es.queryset.order_by('username')
        contents = qs.deserialize()
        self.assertEqual(contents[0], self.t3)
        self.assertEqual(contents[1], self.t4)
        self.assertEqual(contents[2], self.t2)
        self.assertEqual(contents[3], self.t1)

    def test_default_ordering(self):
        qs = TestModel.objects.all()
        qes = TestModel.es.all().deserialize()
        self.assertEqual(list(qs), list(qes))

    def test_filtering(self):
        qs = TestModel.es.queryset.filter(last_name=u"Smith")
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 not in contents)

    def test_multiple_filter(self):
        qs = TestModel.es.queryset.filter(last_name=u"Smith", first_name=u"jack")
        contents = qs.deserialize()
        self.assertTrue(self.t1 not in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 not in contents)
        self.assertTrue(self.t4 not in contents)

    def test_filter_range(self):
        qs = TestModel.es.queryset.filter(id__gt=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 not in contents)
        self.assertTrue(self.t2 not in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 in contents)

        qs = TestModel.es.queryset.filter(id__lt=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 not in contents)
        self.assertTrue(self.t3 not in contents)
        self.assertTrue(self.t4 not in contents)

        qs = TestModel.es.queryset.filter(id__gte=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 not in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 in contents)

        qs = TestModel.es.queryset.filter(id__lte=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 not in contents)
        self.assertTrue(self.t4 not in contents)

        qs = TestModel.es.queryset.filter(id__range=(self.t2.id, self.t3.id))
        contents = qs.deserialize()
        self.assertTrue(self.t1 not in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 not in contents)

    def test_filter_date_range(self):
        qs = TestModel.es.queryset.filter(date_joined__gte=self.t2.date_joined)
        contents = qs.deserialize()
        self.assertTrue(self.t1 not in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 in contents)

    def test_excluding(self):
        qs = TestModel.es.queryset.exclude(username=u"woot")
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 not in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 in contents)

    def test_excluding_lookups(self):
        qs = TestModel.es.queryset.exclude(id__gt=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 not in contents)
        self.assertTrue(self.t4 not in contents)

        qs = TestModel.es.queryset.exclude(id__lt=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 not in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 in contents)

        qs = TestModel.es.queryset.exclude(id__gte=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 not in contents)
        self.assertTrue(self.t3 not in contents)
        self.assertTrue(self.t4 not in contents)

        qs = TestModel.es.queryset.exclude(id__lte=self.t2.id)
        contents = qs.deserialize()
        self.assertTrue(self.t1 not in contents)
        self.assertTrue(self.t2 not in contents)
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 in contents)

    def test_chain_filter_exclude(self):
        qs = TestModel.es.queryset.filter(last_name=u"Smith").exclude(username=u"woot")
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 not in contents)  # excluded
        self.assertTrue(self.t3 in contents)
        self.assertTrue(self.t4 not in contents)  # not a Smith

    @withattrs(TestModel.Elasticsearch, 'mappings', {})
    def test_contains(self):
        TestModel.es.flush()  # update the mapping, username is analyzed
        import time
        time.sleep(2)  # flushing is not immediate :(
        qs = TestModel.es.queryset.filter(username__contains=u"woot")
        contents = qs.deserialize()
        self.assertTrue(self.t1 in contents)
        self.assertTrue(self.t2 in contents)
        self.assertTrue(self.t3 not in contents)
        self.assertTrue(self.t4 not in contents)
