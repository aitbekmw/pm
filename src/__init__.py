

import pathlib
from importlib import import_module
from importlib.util import find_spec

from src.database import Base


def _find_modules(postfix=""):
    src_dir = pathlib.Path(__file__).parent.parent / "src"
    modules = []
    for path in src_dir.rglob("models.py"):
        module_path = path.relative_to(src_dir.parent).with_suffix("")
        module_name = ".".join(module_path.parts)

        if find_spec(module_name):
            modules.append(import_module(module_name))
    return modules


def detect_models():
    for module in _find_modules(".models"):
        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if isinstance(attribute, type) and issubclass(attribute, Base) and attribute is not Base:
                globals()[attribute_name] = attribute


