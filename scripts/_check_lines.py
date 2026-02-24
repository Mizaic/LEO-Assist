import json, sys

lines = open(sys.argv[1], "r", encoding="utf-8").readlines()
for idx in sys.argv[2:]:
    i = int(idx) - 1
    row = json.loads(lines[i])
    ents = [(e["text"], e["type"]) for e in row["entities"]]
    print(f"L{i+1}: {row['sentence'][:150]}")
    print(f"  entities: {ents}")
    print()
