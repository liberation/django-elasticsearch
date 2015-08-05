from django.http import Http404
from django.conf import settings
from django.core.paginator import Page


from rest_framework.settings import api_settings
from rest_framework.pagination import PaginationSerializer
from rest_framework.serializers import BaseSerializer
from rest_framework.filters import OrderingFilter
from rest_framework.filters import DjangoFilterBackend

from django_elasticsearch.models import EsIndexable


from elasticsearch import NotFoundError
try:
    from elasticsearch import ConnectionError
except ImportError:
    from urllib3.connection import ConnectionError
from elasticsearch import TransportError


class ElasticsearchPaginationSerializer(PaginationSerializer):
    @property
    def data(self):
        if self._data is None:
            if type(self.object) is Page:
                page = self.object
                self._data = {
                    'count': page.paginator.count,
                    'previous': self.fields['previous'].to_native(page),
                    'next': self.fields['next'].to_native(page),
                    'results': page.object_list
                }

        return super(ElasticsearchPaginationSerializer, self).data


class FakeSerializer(BaseSerializer):
    @property
    def base_fields(self):
        return {}

    @property
    def data(self):
        self._data = super(FakeSerializer, self).data
        if type(self._data) == list:  # better way ?
            self._data = {
                'count': self.object.count(),
                'results': self._data
            }
        return self._data

    def to_native(self, obj):
        return obj


class ElasticsearchFilterBackend(OrderingFilter, DjangoFilterBackend):
    def filter_queryset(self, request, queryset, view):
        model = queryset.model

        if view.action == 'list':
            if not issubclass(model, EsIndexable):
                raise ValueError("Model {0} is not indexed in Elasticsearch. "
                                 "Make it indexable by subclassing "
                                 "django_elasticsearch.models.EsIndexable."
                                 "".format(model))
            search_param = getattr(view, 'search_param', api_settings.SEARCH_PARAM)
            query = request.QUERY_PARAMS.get(search_param, '')

            # order of precedence : query params > class attribute > model Meta attribute
            ordering = self.get_ordering(request)
            if not ordering:
                ordering = self.get_default_ordering(view)

            filterable = getattr(view, 'filter_fields', [])
            filters = dict([(k, v)
                            for k, v in request.GET.iteritems()
                            if k in filterable])

            q = queryset.query(query).filter(**filters)
            if ordering:
                q = q.order_by(*ordering)

            return q
        else:
            return super(ElasticsearchFilterBackend, self).filter_queryset(
                request, queryset, view
            )


class IndexableModelMixin(object):
    """
    Use EsQueryset and ElasticsearchFilterBackend if available
    """
    filter_backends = [ElasticsearchFilterBackend,]
    FILTER_STATUS_MESSAGE_OK = 'Ok'
    FILTER_STATUS_MESSAGE_FAILED = 'Failed'

    def __init__(self, *args, **kwargs):
        self.es_failed = False
        super(IndexableModelMixin, self).__init__(*args, **kwargs)

    def get_object(self):
        try:
            return super(IndexableModelMixin, self).get_object()
        except NotFoundError:
            raise Http404

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve'] and not self.es_failed:
            # let's return the elasticsearch response as it is.
            return FakeSerializer
        return super(IndexableModelMixin, self).get_serializer_class()

    def get_pagination_serializer(self, page):
        if not self.es_failed:
            context = self.get_serializer_context()
            return ElasticsearchPaginationSerializer(instance=page, context=context)
        return super(IndexableModelMixin, self).get_pagination_serializer(page)

    def get_queryset(self):
        if self.action in ['list', 'retrieve'] and not self.es_failed:
            return self.model.es.search("")
        # db fallback
        return super(IndexableModelMixin, self).get_queryset()

    def filter_queryset(self, queryset):
        if self.es_failed:
            for backend in api_settings.DEFAULT_FILTER_BACKENDS:
                queryset = backend().filter_queryset(self.request, queryset, self)
            return queryset
        else:
            return super(IndexableModelMixin, self).filter_queryset(queryset)

    def list(self, request, *args, **kwargs):
        r = super(IndexableModelMixin, self).list(request, *args, **kwargs)
        if not self.es_failed:
            if getattr(self.object_list, 'facets', None):
                r.data['facets'] = self.object_list.facets

            if getattr(self.object_list, 'suggestions', None):
                r.data['suggestions'] = self.object_list.suggestions

        return r

    def dispatch(self, request, *args, **kwargs):
        try:
            r = super(IndexableModelMixin, self).dispatch(request, *args, **kwargs)
        except (ConnectionError, TransportError), e:
            # reset object list
            self.queryset = None
            self.es_failed = True
            # db fallback
            r = super(IndexableModelMixin, self).dispatch(request, *args, **kwargs)
            if settings.DEBUG and isinstance(r.data, dict):
                r.data["filter_fail_cause"] = str(e)

        # Add a failed message in case something went wrong with elasticsearch
        # for example if the cluster went down.
        if isinstance(r.data, dict) and self.action in ['list', 'retrieve']:
            r.data['filter_status'] = (self.es_failed
                                       and self.FILTER_STATUS_MESSAGE_FAILED
                                       or self.FILTER_STATUS_MESSAGE_OK)
        return r
