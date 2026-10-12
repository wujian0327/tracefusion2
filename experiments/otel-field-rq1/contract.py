"""Pre-registered boundary queries; no engine output is an oracle input."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMIT = '474d0f2eb73d97525234995a40d7781b7923a07d'
PRODUCT = '/hipstershop.ProductCatalogService/GetProduct'
CONVERT = '/hipstershop.CurrencyService/Convert'


def manifest(catalog_file):
    cases = json.loads((HERE/'cases.json').read_text())
    products = json.loads(catalog_file.read_text())['products']
    by_id = {p['id']:(i,p) for i,p in enumerate(products)}
    if len(by_id) != len(products):
        raise ValueError('Ambiguous catalogue IDs')
    queries = []
    for case in cases:
        ids = case['ids']
        if not ids:
            # Two query templates have no dynamic target on the empty path.
            ids = [None]
        failed = False
        for ordinal, pid in enumerate(ids):
            exists = not failed and pid in by_id
            failed |= not exists
            for field in ('units','nanos'):
                row = dict(case=case['name'],ordinal=ordinal,target='CurrencyConversionRequest.from.'+field,
                           expected_status='target' if exists else 'no_target')
                if exists:
                    index, p = by_id[pid]
                    row.update(source=dict(boundary='original GetProduct successful handler return, before protobuf encoding',
                                           catalog_index=index,product_id=pid,field='Product.price_usd.'+field,
                                           version='immutable catalog v0',rpc_occurrence=[case['name'],ordinal]),
                               expected_value=p['priceUsd'][field])
                queries.append(row)
    return dict(schema='otel-field-rq1-boundary-contract-v1',upstream_commit=COMMIT,
                source_scope='Loaded catalogue response fields; catalogue file decoding and selection control are excluded',
                target_scope='Original checkout outgoing Convert request before currency execution; NOT currency receiver or payment',
                dependency_semantics='Explicit content dependence; selection/address/object identity are separate',
                truth_basis=['Pinned catalogue input and independently enumerated workload',
                             'GetProduct returns selected catalogue Product unchanged',
                             'prepOrderItems passes Product.PriceUsd to convertCurrency; original helper sets From: from'],
                annotation_review='Pre-registered source-derived contract; second human review pending',
                cases=cases,queries=queries,
                exclusions=['Currency implementation is a test-only passthrough mock outside queried scope',
                            'No serialization byte taint inference, selective collection or external comparison yet'])
