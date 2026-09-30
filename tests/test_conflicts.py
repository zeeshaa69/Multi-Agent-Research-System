from conftest import make_source
from researcher.agents.factcheck import check_claims, check_grounding, relation
from researcher.models import ExtractedClaim


def ec(text: str, quote: str | None = None, cid: str | None = None) -> ExtractedClaim:
    return ExtractedClaim(
        id=cid or f"c_{abs(hash(text)) % 10**6}",
        text=text,
        quote=quote or text,
        relevance={"sq1": 2.0},
    )


def src(sid: str, sentence: str, **kw):
    s = make_source(sid, sentence + " Filler sentence for context.")
    s.claims = [ec(sentence, **kw)]
    return s


def test_relation_detects_numeric_conflict_and_agreement():
    a = "The installed capacity of the plant is 12 megawatts."
    assert relation(a, "The plant's installed capacity is 15 megawatts.")[0] == "conflict"
    assert relation(a, "Installed capacity of the plant: 12 megawatts.")[0] == "agree"
    assert relation(a, "The orchard covers forty hectares of apple trees.")[0] == "unrelated"


def test_relation_ignores_numbers_with_different_units():
    a = "The plant opened after two years of construction and employs staff."
    b = "The plant opened after construction and employs 40 staff."
    assert relation(a, b)[0] == "agree"


def test_relation_detects_negation_conflict():
    a = "The pilot requires periodic dredging of the shipping channel."
    b = "The pilot does not require dredging of the shipping channel."
    assert relation(a, b) == ("conflict", "one statement negates the other")


def test_conflicting_evidence_is_recorded_on_both_sides():
    sources = [
        src("s1", "The installed capacity of the plant is 12 megawatts."),
        src("s2", "The installed capacity of the plant is 12 megawatts."),
        src("s3", "The plant's installed capacity is 15 megawatts."),
    ]
    claims = check_claims(sources)
    assert len(claims) == 2 and all(c.verification_status == "conflicting" for c in claims)
    by_support = {len(c.supporting_sources): c for c in claims}
    twelve, fifteen = by_support[2], by_support[1]
    assert {e.source_id for e in twelve.conflicting_evidence} == {"s3"}
    assert {e.source_id for e in fifteen.conflicting_evidence} == {"s1", "s2"}
    assert twelve.confidence > fifteen.confidence  # the majority side is more credible
    assert "different figures" in twelve.notes[0]


def test_corroboration_raises_confidence_and_single_source_is_noted():
    one = check_claims([src("s1", "The harbour wall is 400 metres long.")])[0]
    two = check_claims(
        [
            src("s1", "The harbour wall is 400 metres long."),
            src("s2", "The harbour wall is 400 metres long indeed."),
        ]
    )[0]
    assert one.verification_status == two.verification_status == "supported"
    assert two.confidence > one.confidence and "single source" in one.notes


def test_hedged_claim_is_uncertain():
    s = make_source("s9", "The wall may be extended next year.")
    hedged = ec("The wall may be extended next year.")
    hedged.hedged = True
    s.claims = [hedged]
    claim = check_claims([s])[0]
    assert claim.verification_status == "uncertain"
    assert claim.confidence < 0.55


def test_claim_whose_quote_is_not_in_source_is_unsupported():
    s = make_source("s1", "The harbour wall is 400 metres long.")
    s.claims = [
        ec("The harbour wall is 900 metres long.", quote="The harbour wall is 900 metres long.")
    ]
    claim = check_claims([s])[0]
    assert claim.verification_status == "unsupported" and claim.confidence == 0.0
    assert not claim.supporting_sources


def test_paraphrase_that_drifts_from_its_quote_is_unsupported():
    s = make_source("s1", "The harbour wall is 400 metres long.")
    drift = ec("The harbour wall is 900 metres long.", quote="The harbour wall is 400 metres long.")
    assert check_grounding(s, drift) == "none"
    faithful = ec("The wall is 400 metres long.", quote="The harbour wall is 400 metres long.")
    assert check_grounding(s, faithful) == "exact"
