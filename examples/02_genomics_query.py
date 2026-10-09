"""
02_genomics_query.py: Genomics & Target Discovery with Ligase
"""

import os
from dotenv import load_dotenv
load_dotenv(override=True)

from ligase import create_agent

def main():
    agent = create_agent(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        modules=["database", "genomics", "literature"],
    )

    query = (
        "Retrieve the chromosomal coordinates and known disease-associated mutations "
        "for the human BRCA1 gene using Ensembl and ClinVar."
    )
    print(f"Executing Genomics Workflow: {query}\n")
    response = agent.go(query)
    print("=== Analysis Result ===")
    print(response)

if __name__ == "__main__":
    main()
