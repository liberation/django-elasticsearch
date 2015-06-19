

def withattrs(kls, attr, val):
    """
    Decorator that sets given attributes as a context manager
    Usage:
    @withattr(MyClass, 'option', 42)
    def test_option(self, *args, **kwargs):
        pass

    Alternatively you can use the special keyword 'instance'
    instead of passing a class:

    @withattr('instance', 'my_attr', 53)
    def test_foo(self):
        pass

    It's basically the same as calling mock.patch('module.module.Klass.attribute',
                                                  new=val,
                                                  create=True)
    """
    def wrap(func):
        def wrapper(*args, **kwargs):
            if kls == 'instance':
                obj = args[0]
            else:
                obj = kls

            old_val = getattr(obj, attr, None)
            setattr(obj, attr, val)
            try:
                func(*args, **kwargs)
            finally:
                # Note: we don't catch the exception
                # we only 'fix' kls before going on with the normal flow.
                setattr(obj, attr, old_val)
        return wrapper
    return wrap
