import spacy
from spacy.symbols import ORTH

def test_tokenizer_fix():
    nlp = spacy.blank("en")
    
    # The fix I applied in context_engine.py
    for abbrev in ["s.", "l.", "r.", "n."]:
        nlp.tokenizer.add_special_case(abbrev, [{ORTH: abbrev[0]}, {ORTH: "."}])
        
    nlp.add_pipe("sentencizer")
    
    text = "nil #s. medial CPPD."
    doc = nlp(text)
    
    print(f"Text: '{text}'")
    print("Tokens:")
    for i, token in enumerate(doc):
        print(f"  {i}: '{token.text}' (is_sent_start={token.is_sent_start})")
        
    print("\nSentences:")
    sents = list(doc.sents)
    for i, sent in enumerate(sents):
        print(f"  {i}: '{sent.text}'")
        
    if len(sents) > 1 and "medial" in sents[1].text:
        print("\nSUCCESS: Sentence split correctly.")
    else:
        print("\nFAILURE: Sentence did not split.")

if __name__ == "__main__":
    test_tokenizer_fix()
