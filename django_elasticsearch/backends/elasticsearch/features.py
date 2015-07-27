
from django import VERSION
if VERSION < (1, 8):
    from django.db.backends import BaseDatabaseFeatures
else:
    from django.db.backends.base.features import BaseDatabaseFeatures


class ElasticsearchFeatures(BaseDatabaseFeatures):
    # TODO: check this
    # gis_enabled = False

    uses_savepoints = False
    supports_transactions = False
    can_return_id_from_insert = True
    has_bulk_insert = True
    supports_joins = False
    supports_select_related = False
    supports_deleting_related_objects = False
    distinguishes_insert_from_update = False
    uses_autocommit = True

    def _supports_transactions(self):
        # django 1.4
        return False

    def confirm(self):
        return
