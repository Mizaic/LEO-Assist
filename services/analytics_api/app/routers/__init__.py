import importlib


def __getattr__(name: str):
    if name == "cci":
        return importlib.import_module("services.analytics_api.app.routers.cci")
    if name == "benchmarks":
        return importlib.import_module("services.analytics_api.app.routers.benchmarks")
    if name == "dashboards":
        return importlib.import_module("services.analytics_api.app.routers.dashboards")
    raise AttributeError(name)
