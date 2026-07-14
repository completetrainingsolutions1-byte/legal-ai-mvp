"""
Synthetic test cases for the Drafting Agent.
No real client data — see architecture doc, Section 6.
"""

SAMPLE_CASES = [
    {
        "document_type": "demand_letter",
        "client_name": "Jordan Ellis",
        "recipient_name": "Meridian Property Management",
        "matter_summary": (
            "Client's security deposit of $1,800 was not returned within "
            "the state-required timeframe after move-out."
        ),
        "requested_outcome": "Full return of the $1,800 security deposit",
        "additional_context": "Lease ended, unit was left in good condition per client.",
    },
    {
        "document_type": "client_correspondence",
        "client_name": "Priya Nair",
        "recipient_name": "Priya Nair",  # letter TO the client, about their own matter
        "matter_summary": (
            "Update regarding the status of client's pending contract dispute case."
        ),
        "requested_outcome": (
            "Inform client that mediation has been scheduled and request "
            "their availability."
        ),
        "additional_context": "",
    },
    {
        # Intentionally missing 'requested_outcome' to test validation
        "document_type": "demand_letter",
        "client_name": "Marcus Webb",
        "recipient_name": "Coastal Auto Repair",
        "matter_summary": "Vehicle repair was not completed as agreed.",
        "requested_outcome": "",
        "additional_context": "",
    },
]
