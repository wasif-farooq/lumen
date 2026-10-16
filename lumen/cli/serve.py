"""`lumen serve`: the API for the app."""


def run(a):
    from ..api.serve import run as serve

    serve(lan=a.lan, port=a.port)
