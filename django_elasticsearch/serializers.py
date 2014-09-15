import json
import datetime

from django.db.models import FieldDoesNotExist
from django.db.models.fields.related import ManyToManyField


class ModelJsonSerializer(object):
    """
    Default elasticsearch serializer for a django model
    """

    def __init__(self, model):
        self.model = model

    def get_es_val(self, instance, field_name):
        """
        Takes a field name and returns instance's db value converted
        for elasticsearch indexation.
        By default, if it's a related field,
        it returns a simple object {'id': X, 'value': "YYY"}
        where "YYY" is the unicode() of the related instance.
        """
        method_name = 'get_es_{0}_val'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(instance, field_name)

        try:
            field = self.model._meta.get_field(field_name)
        except FieldDoesNotExist:
            # abstract field
            raise TypeError("The serializer doesn't know how to serialize {0}, "
                            "please provide it a {1} method."
                            "".format(field_name, method_name))

        if field.rel:
            if isinstance(field, ManyToManyField):
                return [dict(id=r.pk, value=unicode(r))
                        for r in getattr(instance, field.name).all()]
            rel = getattr(instance, field.name)
            if rel:
                # Use the __unicode__ value of the related model instance.
                if not hasattr(rel, '__unicode__'):
                    raise AttributeError(
                        "You must define a get_{0}_val in the serializer class "
                        "or an __unicode__ method in the related model of an "
                        "Elasticsearch indexed related field for it to work. "
                        "The method is missing in {1}."
                        "".format(field_name, instance.__class__))
                return dict(id=rel.pk, value=unicode(rel))
        return getattr(instance, field.name)

    def get_db_val(self, source, field_name):
        method_name = 'get_db_{0}_val'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(source, field_name)
        field = self.model._meta.get_field(field_name)
        if field.rel:
            return field.rel.to.objects.get(pk=source.get(field_name)['id'])
        return source.get(field_name)

    def serialize(self, instance):
        model_fields = [f.name for f in instance._meta.fields]
        fields = instance.Elasticsearch.fields or model_fields
        return json.dumps(
            dict([(field, self.get_es_val(instance, field))
                  for field in fields]),
            default=lambda d: (
                d.isoformat() if isinstance(d, datetime.datetime)
                or isinstance(d, datetime.date) else None)
        )

    def deserialize(self, source):
        """
        Returns a dict that is suitable to pass to a Model class as kwargs,
        to instanciate it.
        """
        # obj = json.loads(payload)
        return dict([(k, self.get_db_val(source, k))
                     for k, v in source.iteritems()
                     if not isinstance(self.model._meta.get_field(k),
                                       ManyToManyField)])
