from django.conf.urls import url
from django.conf.urls import patterns

from django_elasticsearch.tests.models import TestModel
from django_elasticsearch.views import ElasticsearchListView
from django_elasticsearch.views import ElasticsearchDetailView


class TestDetailView(ElasticsearchDetailView):
    model = TestModel


class TestListView(ElasticsearchListView):
    model = TestModel


urlpatterns = patterns(
    '',
    url(r'^tests/(?P<pk>\d+)/$', TestDetailView.as_view()),
    url(r'^tests/$', TestListView.as_view()),
)

try:
    from rest_framework.viewsets import ModelViewSet
    from rest_framework.routers import DefaultRouter

    from django_elasticsearch.contrib.restframework import AutoCompletionMixin
    from django_elasticsearch.contrib.restframework import IndexableModelMixin
except ImportError:
    pass
else:
    class TestViewSet(AutoCompletionMixin,IndexableModelMixin, ModelViewSet):
        model = TestModel
        filter_fields = ('username',)
        ordering_fields = ('id',)
        search_param = 'q'
        paginate_by = 10
        paginate_by_param = 'page_size'

    router = DefaultRouter()
    router.register(r'rf/tests', TestViewSet)

    urlpatterns += router.urls
