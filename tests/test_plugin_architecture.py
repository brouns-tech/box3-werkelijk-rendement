import importlib
import pkgutil
from pathlib import Path

import wr.parsers
from wr.parsers import PARSER_REGISTRY, PLUGINS, classification_rules


def test_institution_plugins_own_their_rules_and_parsers():
    issuers = [plugin.issuer for plugin in PLUGINS]
    assert len(issuers) == len(set(issuers))

    expected_registry = {
        (plugin.issuer, doc_type)
        for plugin in PLUGINS
        for doc_type in plugin.parsers
    }
    assert set(PARSER_REGISTRY) == expected_registry

    for plugin in PLUGINS:
        assert plugin.parsers
        assert all(rule.issuer == plugin.issuer for rule in plugin.classification_rules)

    assert tuple(
        rule for plugin in PLUGINS for rule in plugin.classification_rules
    ) == classification_rules()


def test_every_parser_module_is_discovered_dynamically():
    infrastructure = {"base", "common"}
    module_names = {
        module.name
        for module in pkgutil.iter_modules([str(Path(wr.parsers.__file__).parent)])
        if not module.name.startswith("_") and module.name not in infrastructure
    }

    module_plugins = [
        importlib.import_module(f"wr.parsers.{module_name}").PLUGIN
        for module_name in module_names
    ]
    assert len(module_plugins) == len(PLUGINS)
    assert all(
        any(plugin is registered for registered in PLUGINS)
        for plugin in module_plugins
    )
