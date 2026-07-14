"""
Synthetic test requests for the Orchestrator — covers all three routing
paths (intake, drafting, unclear) plus one deliberately incomplete
drafting request to test the escalation path.
"""

SAMPLE_REQUESTS = [
    {
        "label": "Should route to Intake Triage Agent",
        "text": (
            "Hi, my landlord in Orlando, Florida won't return my $1,800 "
            "security deposit after I moved out last month. Can you help?"
        ),
    },
    {
        "label": "Should route to Drafting Agent (complete facts)",
        "text": (
            "Please draft a demand letter for client Jordan Ellis to "
            "Meridian Property Management regarding the unreturned $1,800 "
            "security deposit, requesting full return of the deposit."
        ),
    },
    {
        "label": "Should escalate — drafting request with missing facts",
        "text": "Please draft a demand letter about the deposit issue.",
    },
    {
        "label": "Should route to unclear",
        "text": "Hey, quick question about something.",
    },
]
