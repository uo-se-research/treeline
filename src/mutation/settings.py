"""Generic 'settings' class can be accessed by low-level modules
but can contain values set by higher-level modules that have access
to CLI and types that are not visible at a low level.
"""
import io
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    logging.info("Using pure Python version of yaml loader")
    from yaml import Loader, Dumper

class Settings:
    """Basically a key-value store, with a few bells and whistles."""
    def __init__(self):
        self.values = { }

    # Make it look like a dict, not like an object, to
    # avoid infinite recursion on getattribute (because of access to self.values,
    # which in turn calls get)
    def __getitem__(self, item: str) -> object:
        return self.values.get(item)

    def __setitem__(self, key: str, value: object):
        self.values[key] = value

    def read_yaml(self, f: io.IOBase):
        data = yaml.load(f, Loader=Loader)
        assert isinstance(data, dict), f"Configuration file {f} does not represent a table"
        for key, value in data.items():
            self.values[key] = value

    def dump_yaml(self) -> str:
        return yaml.dump(self.values, Dumper=Dumper)

    def substitute(self, substitutions: dict[str, dict[str, object]]):
        """Substitute named values, one of which must be present.
        {'k' : {'v1': s1, 'v2': s2}} means
        substitute v1 for s1 in attribute k,
        substitute v2 for s2 in attribute k,
        error if value of 'k' is not among those named values.
        """
        for attr, subs in substitutions.items():
            assert attr in self.values, f"Can't substitute for {attr}, not present in settings"
            value_name = self.values[attr]
            assert value_name in subs, f"{value_name} is not a known name for a {attr} value"
            self.values[attr] = subs[value_name]

    def convert(self, conversions: dict[str, callable]):
        for name, conversion in conversions.items:
            raw_value = self.values[name]
            self.values[name] = conversion[raw_value]
