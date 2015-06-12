from django.conf.urls import url
from django.conf.urls import patterns

import rest_framework

from django_elasticsearch.views import ElasticsearchListView
from django_elasticsearch.views import ElasticsearchDetailView
from django_elasticsearch.contrib.restframework import AutoCompletionMixin
from django_elasticsearch.contrib.restframework import IndexableModelMixin

from test_app.models import TestModel


class TestDetailView(ElasticsearchDetailView):
    model = TestModel


class TestListView(ElasticsearchListView):
    model = TestModel


urlpatterns = patterns(
    '',
    url(r'^tests/(?P<pk>\d+)/$', TestDetailView.as_view()),
    url(r'^tests/$', TestListView.as_view()),
)


if int(rest_framework.VERSION.split('.')[0]) < 3:
    # TODO: make it work with rest framework 3
    from rest_framework.viewsets import ModelViewSet
    from rest_framework.routers import DefaultRouter

    class TestViewSet(AutoCompletionMixin, IndexableModelMixin, ModelViewSet):
        model = TestModel
        filter_fields = ('username',)
        ordering_fields = ('id',)
        search_param = 'q'
        paginate_by = 10
        paginate_by_param = 'page_size'

    router = DefaultRouter()
    router.register(r'rf/tests', TestViewSet)

    urlpatterns += router.urls
