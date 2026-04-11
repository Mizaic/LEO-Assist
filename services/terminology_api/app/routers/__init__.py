__all__ = [
    "search_router",
    "resolve_router",
    "writeback_router",
    "valueset_router",
    "conceptmap_router",
    "concepts_router",
    "surface_forms_router",
    "guidelines_router",
]


def __getattr__(name: str):
    if name == "search_router":
        from services.terminology_api.app.routers.search import router

        return router
    if name == "resolve_router":
        from services.terminology_api.app.routers.resolve import router

        return router
    if name == "writeback_router":
        from services.terminology_api.app.routers.writeback import router

        return router
    if name == "valueset_router":
        from services.terminology_api.app.routers.valueset import router

        return router
    if name == "conceptmap_router":
        from services.terminology_api.app.routers.conceptmap import router

        return router
    if name == "concepts_router":
        from services.terminology_api.app.routers.concepts import router

        return router
    if name == "surface_forms_router":
        from services.terminology_api.app.routers.surface_forms import router

        return router
    if name == "guidelines_router":
        from services.terminology_api.app.routers.guidelines import router

        return router
    raise AttributeError(name)
