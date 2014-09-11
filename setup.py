from setuptools import setup, find_packages

setup(
    name = "django_elasticsearch",
    version = "0.1",
    description = "Simple wrapper around py-elasticsearch to index/search a django Model.",
    author = "Robin Tissot",
    url = "https://github.com/liberation/django_elasticsearch",
    packages = find_packages(),
)
