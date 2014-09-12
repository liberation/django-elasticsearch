# -*- coding: utf-8 -*-
from django.test import TestCase
from django.contrib.auth.models import User

from taggit.managers import TaggableManager

from django_elasticsearch.tests.models import TestModel
from django_elasticsearch.contrib.taggit import TaggitSerializer

User.tags = TaggableManager()  # monkey patch


class EsTaggitTestCase(TestCase):
    def test_serializer(self):
        TestModel.Elasticsearch.serializer_class = TaggitSerializer
        instance = TestModel.objects.create(username=u"1", first_name=u"woot", last_name=u"foo")
        instance.tags.add(u"tag1")
        instance.tags.add(u"tagéàèau")
        
        json = instance.es.serialize()
        self.assertIn(u'"tags": ["tag1", "tag\\u00e9\\u00e0\\u00e8au"]', json)
