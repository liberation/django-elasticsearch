from django.conf.urls import url
from django.conf.urls import patterns

from test_app.views import TestDetailView
from test_app.views import TestListView


urlpatterns = patterns(
    '',
    url(r'^tests/(?P<pk>\d+)/$', TestDetailView.as_view(), name='test_detail'),
    url(r'^tests/$', TestListView.as_view(), name='test_list'),
)

from test_app.views import TestViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'rf/tests', TestViewSet)

urlpatterns += router.urls
