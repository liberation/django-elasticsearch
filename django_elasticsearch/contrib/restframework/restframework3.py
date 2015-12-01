from django.http import Http404
from django.conf import settings

from rest_framework.response import Response
from rest_framework.serializers import OrderedDict
from rest_framework.settings import api_settings
from rest_framework.filters import OrderingFilter
from rest_framework.filters import DjangoFilterBackend

from django_elasticsearch.models import EsIndexable


try:
    from elasticsearch import ConnectionError
except ImportError:
    from urllib3.connection import ConnectionError
from elasticsearch import TransportError
from elasticsearch import NotFoundError


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
            query = request.query_params.get(search_param, '')

            # order of precedence : query params > class attribute > model Meta attribute
            ordering = self.get_ordering(request, queryset, view)
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

    def get_queryset(self):
        if self.action in ['list', 'retrieve'] and not self.es_failed:
            return self.model.es.search("")
        # db fallback
        return self.queryset or self.model.objects.all()

    def filter_queryset(self, queryset):
        if self.es_failed:
            for backend in api_settings.DEFAULT_FILTER_BACKENDS:
                queryset = backend().filter_queryset(self.request, queryset, self)
            return queryset
        else:
            return super(IndexableModelMixin, self).filter_queryset(queryset)

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

    def list(self, request, *args, **kwargs):
        if self.es_failed:
            return super(IndexableModelMixin, self).list(request, *args, **kwargs)
        else:
            # bypass serialization
            queryset = self.filter_queryset(self.get_queryset())

            # evaluates the query and cast it to list (why ?)
            page = self.paginate_queryset(queryset)

            data = OrderedDict([
                ('count', queryset.count()),
                ('results', page)
            ])

            if queryset.facets:
                data['facets'] = queryset.facets

            if queryset.suggestions:
                data['suggestions'] = queryset.suggestions

            return Response(data)
