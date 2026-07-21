import spacy
from spacy.symbols import ORTH
from medspacy.context import ConTextRule, ConTextComponent


def test_context_scope():
    nlp = spacy.blank("en")

    # The fix I applied in context_engine.py
    for abbrev in ["s.", "l.", "r.", "n."]:
        nlp.tokenizer.add_special_case(abbrev, [{ORTH: abbrev[0]}, {ORTH: "."}])

    nlp.add_pipe("sentencizer")

    # Add ConText with the nil rule (max_scope=6)
    context = nlp.add_pipe("medspacy_context")
    rule = ConTextRule(
        literal="nil", category="NEGATED_EXISTENCE", direction="FORWARD", max_scope=6
    )
    context.add([rule])

    text = "nil #s. medial CPPD."
    doc = nlp(text)

    print(f"Text: '{text}'")
    print("Sentences:")
    for s in doc.sents:
        print(f"  '{s.text}'")

    # Check if "medial" or "CPPD" are modified
    print("\nEntities/Modifiers:")
    # We need to simulate entities since ConText modifies existing entities or creates modifiers
    # ConText usually modifies doc.ents or tokens.
    # Let's manually set entities

    # "medial" is at token 4, "CPPD" at 5
    # "nil" is at 0

    # Create a span for CPPD
    cppd_span = doc[5:6]  # CPPD
    doc.ents = [cppd_span]

    # Run context again to apply to ents (usually happens in pipeline)
    context(doc)

    print(f"CPPD assertion: {cppd_span._.is_negated}")

    if cppd_span._.is_negated:
        print("FAILURE: CPPD is negated despite sentence boundary.")
    else:
        print("SUCCESS: CPPD is NOT negated.")


if __name__ == "__main__":
    test_context_scope()
