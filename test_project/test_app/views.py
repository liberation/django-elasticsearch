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


### contrib.restframework test viewsets
from rest_framework.viewsets import ModelViewSet
from django_elasticsearch.contrib.restframework import AutoCompletionMixin
from django_elasticsearch.contrib.restframework import IndexableModelMixin


from rest_framework import VERSION

if int(VERSION[0]) < 3:
    class TestViewSet(AutoCompletionMixin, IndexableModelMixin, ModelViewSet):
        model = TestModel
        filter_fields = ('username',)
        ordering_fields = ('id',)
        search_param = 'q'
        paginate_by = 10
        paginate_by_param = 'page_size'
else:
    from rest_framework.serializers import ModelSerializer

    class TestSerializer(ModelSerializer):
        class Meta:
            model = TestModel

    class TestViewSet(AutoCompletionMixin, IndexableModelMixin, ModelViewSet):
        model = TestModel
        queryset = TestModel.objects.all()
        serializer_class = TestSerializer
        filter_fields = ('username',)
        ordering_fields = ('id',)
        search_param = 'q'
        paginate_by = 10
        paginate_by_param = 'page_size'
