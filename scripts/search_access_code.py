"""Search for a Read/SNOMED code in DMWB Access databases."""

from __future__ import annotations

import sys
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "external_content" / "trud-snomed-data-migration"
READ_DB = BASE / "DMWB NHS READ.mdb"
SNOMED_DB = BASE / "DMWB NHS SNOMED.mdb"
MAP_DB = BASE / "DMWB NHS Data Migration Maps.mdb"
ODBC_DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"


def decode_access_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-16le", errors="ignore").rstrip("\x00").strip()
    return str(value).strip()


def search_read_db(conn: pyodbc.Connection, code: str) -> list[dict]:
    results = []
    cursor = conn.cursor()
    for table in ("RCT", "CTV3"):
        try:
            for row in cursor.execute(
                f"SELECT [CUI], [T30], [T60], [T198] FROM [{table}] WHERE [CUI] = ?",
                (code,),
            ):
                results.append(
                    {
                        "db": "DMWB NHS READ.mdb",
                        "table": table,
                        "CUI": decode_access_value(row[0]),
                        "T30": decode_access_value(row[1]),
                        "T60": decode_access_value(row[2]),
                        "T198": decode_access_value(row[3]),
                    }
                )
        except pyodbc.Error as e:
            results.append({"db": "DMWB NHS READ.mdb", "table": table, "error": str(e)})
    return results


def search_snomed_db(conn: pyodbc.Connection, code: str) -> list[dict]:
    results = []
    cursor = conn.cursor()
    try:
        for row in cursor.execute(
            "SELECT [CUI], [TERM], [STAT] FROM [SCT] WHERE [CUI] = ?", (code,)
        ):
            results.append(
                {
                    "db": "DMWB NHS SNOMED.mdb",
                    "table": "SCT",
                    "CUI": decode_access_value(row[0]),
                    "TERM": decode_access_value(row[1]),
                    "STAT": decode_access_value(row[2]),
                }
            )
    except pyodbc.Error as e:
        results.append({"db": "DMWB NHS SNOMED.mdb", "table": "SCT", "error": str(e)})
    return results


def search_map_db(conn: pyodbc.Connection, code: str) -> list[dict]:
    results = []
    cursor = conn.cursor()
    tables_to_try = ["RCTSCTMAP", "CTV3SCTMAP"]
    for table in tables_to_try:
        try:
            cols = cursor.execute(
                f"SELECT TOP 1 * FROM [{table}]"
            ).description
            col_names = [c[0] for c in cols]
            read_col = "RCT" if "RCT" in col_names else "CTV3"
            if read_col not in col_names:
                read_col = col_names[0] if col_names else "CUI"
            for row in cursor.execute(
                f"SELECT * FROM [{table}] WHERE [{read_col}] = ?", (code,)
            ):
                rec = {"db": "DMWB NHS Data Migration Maps.mdb", "table": table}
                for i, c in enumerate(col_names):
                    if i < len(row):
                        rec[c] = decode_access_value(row[i])
                results.append(rec)
        except pyodbc.Error as e:
            results.append(
                {"db": "DMWB NHS Data Migration Maps.mdb", "table": table, "error": str(e)}
            )
    return results


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "XaIVB"
    print(f"Searching for code: {code}\n")

    if READ_DB.exists():
        print("--- DMWB NHS READ.mdb ---")
        conn = pyodbc.connect(f"DRIVER={ODBC_DRIVER};DBQ={READ_DB.resolve()};")
        try:
            for r in search_read_db(conn, code):
                if "error" in r:
                    print(f"  {r['table']}: {r['error']}")
                else:
                    print(f"  {r['table']}: CUI={r['CUI']} T30={r['T30']} T60={r['T60']} T198={r['T198']}")
        finally:
            conn.close()
    else:
        print(f"  READ DB not found: {READ_DB}")

    if SNOMED_DB.exists():
        print("\n--- DMWB NHS SNOMED.mdb ---")
        conn = pyodbc.connect(f"DRIVER={ODBC_DRIVER};DBQ={SNOMED_DB.resolve()};")
        try:
            for r in search_snomed_db(conn, code):
                if "error" in r:
                    print(f"  SCT: {r['error']}")
                else:
                    print(f"  SCT: CUI={r['CUI']} TERM={r['TERM']} STAT={r['STAT']}")
        finally:
            conn.close()
    else:
        print(f"\n  SNOMED DB not found: {SNOMED_DB}")

    if MAP_DB.exists():
        print("\n--- DMWB NHS Data Migration Maps.mdb ---")
        conn = pyodbc.connect(f"DRIVER={ODBC_DRIVER};DBQ={MAP_DB.resolve()};")
        try:
            for r in search_map_db(conn, code):
                if "error" in r:
                    print(f"  {r['table']}: {r['error']}")
                else:
                    print(f"  {r['table']}: {r}")
        finally:
            conn.close()
    else:
        print(f"\n  MAP DB not found: {MAP_DB}")


if __name__ == "__main__":
    main()
