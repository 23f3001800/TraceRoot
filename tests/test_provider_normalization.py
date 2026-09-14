from traceroot.llms.provider import canonicalize_hypothesis_ids

def test_hypothesis_ids_are_canonicalized_without_accepting_arbitrary_text():
    decision = {"hypotheses": [{"id": "h-1"}, {"id": "H 2"}, {"id": "cause"}]}
    assert canonicalize_hypothesis_ids(decision)["hypotheses"] == [{"id": "H1"}, {"id": "H2"}, {"id": "cause"}]
