from django.db.backends import BaseDatabaseIntrospection


class NonrelDatabaseIntrospection(BaseDatabaseIntrospection):

    def table_names(self, cursor=None):
        """
        Returns a list of names of all tables that exist in the
        database.
        """
        pass
