from django.http import Http404

from rest_framework.response import Response
from rest_framework.mixins import ListModelMixin
from rest_framework.decorators import list_route


class AutoCompletionMixin(ListModelMixin):
    """
    Add a route to the ViewSet to get a list of completion suggestion.
    """

    @list_route()
    def autocomplete(self, request, **kwargs):
        try:
            qp = request.query_params
        except AttributeError:
            # restframework 2
            qp = request.QUERY_PARAMS

        field_name = qp.get('f', None)
        query = qp.get('q', '')

        try:
            data = self.model.es.complete(field_name, query)
        except ValueError:
            raise Http404("field {0} is either missing or "
                          "not in Elasticsearch.completion_fields.")

        return Response(data)
