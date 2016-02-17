from django.test import TestCase

from django_elasticsearch.utils import dict_depth
from django_elasticsearch.managers import es_client
from django_elasticsearch.tests.utils import withattrs
from django_elasticsearch.serializers import EsJsonSerializer
from django_elasticsearch.serializers import EsSimpleJsonSerializer

from test_app.models import Dummy
from test_app.models import Test2Model


class CustomSerializer(EsJsonSerializer):
    def serialize_char(self, instance, field_name):
        return u'FOO'


class EsJsonSerializerTestCase(TestCase):
    def setUp(self):
        Test2Model.es.flush()
        self.target = Dummy.objects.create(foo='test')
        self.instance = Test2Model.objects.create(fk=self.target,
                                                  oto=self.target)
        # to test for infinite nested recursion
        self.instance.fkself = self.instance
        self.instance.save()

        self.instance.mtm.add(self.target)

        # reverse relations
        self.target.reversefk = self.instance
        self.target.save()
        self.target.reversem2m.add(self.instance)

    def tearDown(self):
        super(EsJsonSerializerTestCase, self).tearDown()
        es_client.indices.delete(index=Test2Model.es.get_index())

    def test_serialize(self):
        obj = self.instance.es.serialize()
        self.assertTrue(isinstance(obj, basestring))

    @withattrs(Test2Model.Elasticsearch, 'serializer_class',
               'django_elasticsearch.serializers.EsJsonSerializer')
    def test_dynamic_serializer_import(self):
        obj = self.instance.es.serialize()
        self.assertTrue(isinstance(obj, basestring))

    def test_deserialize(self):
        instance = Test2Model.es.deserialize({'char': 'test'})
        self.assertTrue(isinstance(instance, Test2Model))
        self.assertEqual(instance.char, 'test')
        self.assertRaises(ValueError, instance.save)

    @withattrs(Test2Model.Elasticsearch, 'serializer_class', CustomSerializer)
    def test_custom_serializer(self):
        json = self.instance.es.serialize()
        self.assertIn('"char": "FOO"', json)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'fk'])
    def test_nested_fk(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'fk': {'id':1, 'foo': 'test'}}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'oto'])
    def test_nested_oto(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'oto': {'id':1, 'foo': 'test'}}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'fkself'])
    def test_self_fk_depth_test(self):
        Test2Model.es.serializer = None  # reset cache
        serializer = Test2Model.es.get_serializer(max_depth=3)
        obj = serializer.format(self.instance)
        self.assertEqual(dict_depth(obj), 3)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'mtm'])
    def test_nested_m2m(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'mtm': [{'id':1, 'foo': 'test'},]}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['abstract_prop', 'abstract_method'])
    def test_abstract_field(self):
        serializer = Test2Model.es.get_serializer()        
        obj = serializer.format(self.instance)
        expected = {'abstract_method': 'woot', 'abstract_prop': 'weez'}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['foo',])
    def test_unknown_field(self):
        with self.assertRaises(AttributeError):
            self.instance.es.serialize()

    def test_specific_field_method(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        self.assertEqual(obj["bigint"], 42)

        instance = Test2Model.es.deserialize(obj)
        self.assertEqual(instance.bigint, 45)

    def test_type_specific_field_method(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        self.assertTrue(type(obj["datetf"]) is dict)

        instance = Test2Model.es.deserialize({"datetf": obj["datetf"]})
        self.assertEqual(instance.datetf, self.instance.datetf)

    @withattrs(Test2Model.Elasticsearch, 'serializer_class', EsSimpleJsonSerializer)
    def test_simple_serializer(self):
        results = Test2Model.es.deserialize([{'id': self.instance.pk},])
        self.assertTrue(self.instance in results)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'dummies'])
    def test_reverse_fk(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'dummies': [{'id':1, 'foo': 'test'},]}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'dummiesm2m'])
    def test_reverse_m2m(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'dummiesm2m': [{'id':1, 'foo': 'test'},]}
        self.assertEqual(obj, expected)

