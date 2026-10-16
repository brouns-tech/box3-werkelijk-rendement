from __future__ import annotations

from collections import defaultdict
import json

from pydantic import JsonValue

from wr.models.facts import AccountYearFact, GainMethod, Ownership
from wr.models.reconciliation import (
    AttributeField,
    EvidenceStatus,
    FieldEvidence,
    ReconciledFact,
    SourceEvidence,
)
from wr.models.storage import FactRecord, MoneyField
from wr.money import amount, subtract


def account_key(value: str) -> str:
    return value.lower().replace(" ", "")


def group_observations(observations: list[FactRecord]) -> list[list[FactRecord]]:
    groups: dict[tuple[int, str, str], list[FactRecord]] = defaultdict(list)
    for observation in observations:
        key = observation.tax_year, observation.issuer, account_key(observation.account_key)
        groups[key].append(observation)
    return [groups[key] for key in sorted(groups)]


def source_evidence(observation: FactRecord, field: MoneyField | AttributeField) -> SourceEvidence:
    value = observation.extra.box3 if field == AttributeField.BOX3 else getattr(observation, field.value)
    return SourceEvidence(
        fact_id=observation.id, document_sha256=observation.document_sha256, field=field, value=value,
    )


def reconcile_field(observations: list[FactRecord], field: MoneyField | AttributeField) -> FieldEvidence:
    sources = [source_evidence(row, field) for row in observations]
    sources = [
        source for source in sources
        if source.value is not None and source.value != [] and source.value != "unknown"
    ]
    values = {
        json.dumps(
            sorted({" ".join(name.split()).casefold() for name in source.value})
            if field == AttributeField.HOLDERS else amount(source.value)
            if isinstance(field, MoneyField) else source.value,
            sort_keys=True,
        )
        for source in sources
    }
    if len(values) > 1:
        return FieldEvidence(field=field, status=EvidenceStatus.CONFLICT, sources=sources)
    documents = {source.document_sha256 for source in sources}
    if not sources:
        status = EvidenceStatus.MISSING
    elif len(documents) > 1:
        status = EvidenceStatus.AGREEMENT
    else:
        status = EvidenceStatus.SINGLE_SOURCE
    value = sources[0].value if sources else None
    if value is not None and isinstance(field, MoneyField):
        value = amount(value)
    return FieldEvidence(
        field=field, status=status,
        value=value, sources=sources,
    )


def set_field(result: ReconciledFact, evidence: FieldEvidence) -> None:
    result.evidence = [item for item in result.evidence if item.field != evidence.field] + [evidence]
    value = evidence.value
    if evidence.field == AttributeField.BOX3:
        result.extra.box3 = value if isinstance(value, bool) else True
    elif evidence.field == AttributeField.HOLDERS:
        names = value if isinstance(value, list) else []
        result.holder_names = list({" ".join(name.split()).casefold(): name for name in names}.values())
    elif evidence.field == AttributeField.OWNERSHIP:
        result.ownership = Ownership(value) if value is not None else Ownership.UNKNOWN
    elif evidence.field == AttributeField.GAIN_METHOD:
        result.gain_method = GainMethod(value) if value is not None else GainMethod.UNKNOWN
    elif value is not None or evidence.field != AttributeField.CURRENCY:
        setattr(result, evidence.field.value, value)


def derive_field(
    result: ReconciledFact,
    field: MoneyField | AttributeField,
    value: JsonValue,
    inputs: list[FieldEvidence],
    rule: str,
) -> None:
    sources = {source.model_dump_json(): source for item in inputs for source in item.sources}
    if any(item.status == EvidenceStatus.CONFLICT for item in inputs):
        status = EvidenceStatus.CONFLICT
    else:
        status = EvidenceStatus.MISSING if value is None else EvidenceStatus.DERIVED
    set_field(result, FieldEvidence(
        field=field, status=status, value=value if status != EvidenceStatus.CONFLICT else None,
        sources=list(sources.values()), rule=rule,
    ))


def reconcile_group(observations: list[FactRecord]) -> ReconciledFact:
    first = observations[0]
    result = ReconciledFact(
        tax_year=first.tax_year, issuer=first.issuer, account_key=first.account_key,
        account_label=first.account_label, currency=first.currency,
        logical_group=first.logical_group, extra=first.extra.model_copy(deep=True),
    )
    for field in (*MoneyField, AttributeField.HOLDERS, AttributeField.OWNERSHIP, AttributeField.CURRENCY, AttributeField.BOX3):
        candidates = observations
        if field == MoneyField.CAPITAL_GAIN:
            candidates = [row for row in observations if row.gain_method not in {
                GainMethod.INTEREST_ONLY, GainMethod.BALANCE_FLOW, GainMethod.BALANCE_DELTA_INCOMPLETE,
            }]
        set_field(result, reconcile_field(candidates, field))
    methods = [row for row in observations if row.gain_method not in {
        GainMethod.UNKNOWN, GainMethod.BALANCE_DELTA_INCOMPLETE, None,
    }]
    method = reconcile_field(methods, AttributeField.GAIN_METHOD)
    if {row.gain_method for row in methods} == {GainMethod.EXPLICIT, GainMethod.INTEREST_ONLY}:
        if result.capital_gain is not None:
            method = FieldEvidence(
                field=AttributeField.GAIN_METHOD, status=EvidenceStatus.DERIVED,
                value=GainMethod.EXPLICIT.value, sources=method.sources,
                rule="explicit_market_gain_with_separate_interest",
            )
    set_field(result, method)
    ownership = next(item for item in result.evidence if item.field == AttributeField.OWNERSHIP)
    if ownership.status != EvidenceStatus.CONFLICT and result.ownership == Ownership.UNKNOWN and result.holder_names:
        holder_evidence = next(item for item in result.evidence if item.field == AttributeField.HOLDERS)
        derive_field(
            result, AttributeField.OWNERSHIP,
            Ownership.INDIVIDUAL.value if len(result.holder_names) == 1 else Ownership.JOINT.value,
            [holder_evidence], "ownership_from_reported_holders",
        )
    labels = [source_evidence(row, AttributeField.LABEL) for row in observations if row.account_label]
    set_field(result, FieldEvidence(
        field=AttributeField.LABEL, status=EvidenceStatus.DERIVED if labels else EvidenceStatus.MISSING,
        value=first.account_label, sources=labels, rule="display_label_only",
    ))
    derive_return(result)
    return result


def derive_return(result: ReconciledFact) -> None:
    capital = next(item for item in result.evidence if item.field == MoneyField.CAPITAL_GAIN)
    method = next(item for item in result.evidence if item.field == AttributeField.GAIN_METHOD)
    if capital.sources or capital.status == EvidenceStatus.CONFLICT or method.status == EvidenceStatus.CONFLICT:
        return
    if result.gain_method == GainMethod.INTEREST_ONLY:
        inputs = [item for item in result.evidence if item.field in {
            MoneyField.INTEREST_RECEIVED, MoneyField.INTEREST_PAID,
        }]
        value = (
            subtract(result.interest_received or 0, result.interest_paid or 0)
            if any(item.value is not None for item in inputs) else None
        )
        derive_field(result, MoneyField.CAPITAL_GAIN, value, inputs, "net_interest_only")
        return
    fields = [item for item in result.evidence if isinstance(item.field, MoneyField) and item.field != MoneyField.CAPITAL_GAIN]
    values = {item.field.value: getattr(result, item.field.value) for item in fields}
    fact = AccountYearFact(
        tax_year=result.tax_year, issuer=result.issuer, account_key=result.account_key,
        account_label=result.account_label or "", **values,
    )
    fact.compute_capital_gain()
    if fact.capital_gain is not None:
        derive_field(result, MoneyField.CAPITAL_GAIN, fact.capital_gain, fields, "capital_gain_from_reconciled_inputs")
        derive_field(result, AttributeField.GAIN_METHOD, fact.gain_method.value, fields, "capital_gain_from_reconciled_inputs")


def reconcile_observations(observations: list[FactRecord]) -> list[ReconciledFact]:
    return [reconcile_group(group) for group in group_observations(observations)]
