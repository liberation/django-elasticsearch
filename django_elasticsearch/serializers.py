import json
import datetime

from django.db.models import FieldDoesNotExist
from django.db.models.fields.related import ManyToManyField


class ModelJsonSerializer(object):
    """
    Default elasticsearch serializer for a django model
    """

    def __init__(self, model, max_depth=2, cur_depth=1):
        self.model = model
        # used in case of related field on 'self' tu avoid infinite loop
        self.cur_depth = cur_depth
        self.max_depth = max_depth

    def serialize_field(self, instance, field_name):
        """
        Takes a field name and returns instance's db value converted
        for elasticsearch indexation.
        By default, if it's a related field,
        it returns a simple object {'id': X, 'value': "YYY"}
        where "YYY" is the unicode() of the related instance.
        """
        method_name = 'serialize_{0}'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(instance, field_name)

        try:
            field = self.model._meta.get_field(field_name)
        except FieldDoesNotExist:
            # abstract field: check for a model property/attribute
            if hasattr(instance, field_name):
                return getattr(instance, field_name)

            raise AttributeError("The serializer doesn't know how to serialize {0}, "
                                 "please provide it a {1} method."
                                 "".format(field_name, method_name))

        field_type_method_name = 'serialize_type_{0}'.format(
            field.__class__.__name__.lower())
        if hasattr(self, field_type_method_name):
            return getattr(self, field_type_method_name)(instance, field_name)

        if field.rel:
            # m2m
            if isinstance(field, ManyToManyField):
                return [dict(id=r.pk, value=unicode(r))
                        for r in getattr(instance, field.name).all()]
            rel = getattr(instance, field.name)
            # fk, oto
            if rel:  # should be a model instance
                # check for Elasticsearch.serializer on the related model
                if self.cur_depth >= self.max_depth:
                    return

                if hasattr(rel, 'Elasticsearch'):
                    serializer = rel.es.get_serializer(max_depth=self.max_depth,
                                                       cur_depth=self.cur_depth + 1)

                    obj = serializer.format(rel)
                    return obj

                # Use the __unicode__ value of the related model instance.
                if not hasattr(rel, '__unicode__'):
                    raise AttributeError(
                        "You must define a deserialize_{0} in the serializer class "
                        "or an __unicode__ method in the related model of an "
                        "Elasticsearch indexed related field for it to work. "
                        "The method is missing in {1}."
                        "".format(field_name, instance.__class__))
                return dict(id=rel.pk, value=unicode(rel))
        return getattr(instance, field.name)

    def deserialize_field(self, source, field_name):
        method_name = 'deserialize_{0}'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(source, field_name)
        field = self.model._meta.get_field(field_name)
        if field.rel:
            try:
                return field.rel.to.objects.get(pk=source.get(field_name)['id'])
            except TypeError:
                pass
        return source.get(field_name)

    def format(self, instance):
        fields = self.model.es.get_fields()
        obj = dict([(field, self.serialize_field(instance, field))
                    for field in fields])

        # adding auto complete fields
        completion_fields = instance.Elasticsearch.completion_fields
        for field_name in completion_fields or []:
            suggest_name = "{0}_complete".format(field_name)
            # TODO: could store the value of field_name in case it does some
            # heavy processing or db requests.
            obj[suggest_name] = self.serialize_field(instance, field_name)

        return obj

    def serialize(self, instance):
        return json.dumps(self.format(instance),
                          default=lambda d: (
                              d.isoformat() if isinstance(d, datetime.datetime)
                              or isinstance(d, datetime.date) else None))

    def deserialize(self, source):
        """
        Returns a dict that is suitable to pass to a Model class as kwargs,
        to instanciate it.
        """
        d = {}
        for k, v in source.iteritems():
            try:
                field = self.model._meta.get_field(k)
            except FieldDoesNotExist:
                # abstract field
                continue

            field_type_method_name = 'deserialize_type_{0}'.format(
                field.__class__.__name__.lower())
            if hasattr(self, field_type_method_name):
                d[k] = getattr(self, field_type_method_name)(source, field.name)
                continue

            if not isinstance(field, ManyToManyField):
                d[k] = self.deserialize_field(source, k)

        return d
