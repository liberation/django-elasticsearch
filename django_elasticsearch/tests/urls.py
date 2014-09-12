from rest_framework.viewsets import ModelViewSet
from rest_framework.routers import DefaultRouter

from django_elasticsearch.tests.models import TestModel
from django_elasticsearch.contrib.restframework import FacetedListModelMixin


class TestViewSet(FacetedListModelMixin, ModelViewSet):
    model = TestModel
    filter_fields = ('username',)

router = DefaultRouter()
router.register(r'tests', TestViewSet)
urlpatterns = router.urls
