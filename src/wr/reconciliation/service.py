from __future__ import annotations

import sqlite3

from wr.models.reconciliation import ReconciledFact
from wr.parsers import PLUGINS
from wr.parsers._schemas import parse_institution_settings
from wr.parsers.base import InstitutionOptions
from wr.reconciliation.engine import reconcile_observations
from wr.storage.reconciliation import replace_reconciled_facts, source_observations


def reconcile_facts(conn: sqlite3.Connection, institution_options: InstitutionOptions | None = None) -> None:
    observations = source_observations(conn)
    results: list[ReconciledFact] = []
    plugins = {plugin.issuer: plugin for plugin in PLUGINS}
    for issuer in sorted({row.issuer for row in observations}):
        sources = [row for row in observations if row.issuer == issuer]
        plugin = plugins.get(issuer)
        if plugin and plugin.reconcile:
            options = parse_institution_settings(issuer, (institution_options or {}).get(issuer, {}))
            results.extend(plugin.reconcile(sources, options))
        else:
            results.extend(reconcile_observations(sources))
    with conn:
        replace_reconciled_facts(conn, results)
