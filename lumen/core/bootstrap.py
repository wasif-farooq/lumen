"""Load what was saved in the data folder, once, before the server or a command runs."""


def load_saved_state() -> None:
    from ..providers import registry
    from . import preferences

    registry.load()  # model choices and providers (may override the default models)
    preferences.load()  # folders, power, what gets indexed
