from django.core import serializers
from django.http import HttpResponse
from django.db.models import Model
from django.views.generic.detail import SingleObjectMixin

from django_elasticsearch.views import ElasticsearchListView
from django_elasticsearch.views import ElasticsearchDetailView


from test_app.models import TestModel


class JsonViewMixin(object):
    def render_to_response(self, context):
        content = self._get_content()
        if isinstance(content, Model):
            # Note: for some reason django's serializer only eat iterables
            content = [content,]

        json = serializers.serialize('json', content)
        if isinstance(self, SingleObjectMixin):
            json = json[1:-1]  # eww
        return HttpResponse(json, content_type='application/json; charset=utf-8')


class TestDetailView(JsonViewMixin, ElasticsearchDetailView):
    model = TestModel

    def _get_content(self):
        return self.object


class TestListView(JsonViewMixin, ElasticsearchListView):
    model = TestModel

    def _get_content(self):
        return self.object_list


from rest_framework.viewsets import ModelViewSet
# from rest_framework.serializers import BaseSerializer
from django_elasticsearch.contrib.restframework import AutoCompletionMixin
from django_elasticsearch.contrib.restframework import IndexableModelMixin


class TestViewSet(AutoCompletionMixin, IndexableModelMixin, ModelViewSet):
    model = TestModel
    filter_fields = ('username',)
    ordering_fields = ('id',)
    search_param = 'q'
    paginate_by = 10
    paginate_by_param = 'page_size'
