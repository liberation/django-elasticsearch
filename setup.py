from setuptools import setup, find_packages

setup(
    name="django-elasticsearch",
    version="0.5",
    description="Simple wrapper around py-elasticsearch to index/search a django Model.",
    author="Robin Tissot",
    url="https://github.com/liberation/django_elasticsearch",
    packages=find_packages(),
)
