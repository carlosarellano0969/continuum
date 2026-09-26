from fastapi.testclient import TestClient


def test_outcome_is_immutable_record_and_scoped(seeded: TestClient) -> None:
    recommendation = seeded.post(
        "/api/recommendations", json={"scenario": "A customer asks for a refund"}
    ).json()
    response = seeded.post(
        "/api/outcomes",
        json={
            "decision_id": recommendation["decision_id"],
            "result": "failure",
            "metrics": {"quality": 0.2, "repeat_contact": True},
            "elapsed_seconds": 30,
        },
    )
    assert response.status_code == 200
    assert response.json()["result"] == "failure"
    assert response.json()["created_at"].endswith("Z")

    cross_scope = seeded.post(
        "/api/outcomes",
        headers={"X-Agent-ID": "other-agent"},
        json={"decision_id": recommendation["decision_id"], "result": "failure", "metrics": {}},
    )
    assert cross_scope.status_code == 404


def test_approval_creates_next_policy_and_repeated_transition_conflicts(seeded: TestClient) -> None:
    proposal = seeded.get("/api/proposals").json()["items"][0]
    response = seeded.post(
        f"/api/proposals/{proposal['id']}/decision",
        json={"decision": "approve", "actor": "reviewer@example.test", "note": "Evidence is sufficient."},
    )
    assert response.status_code == 200
    decided = response.json()
    assert decided["proposal"]["state"] == "approved"
    assert decided["policy"]["version"] == 2
    assert decided["policy"]["approval"]["actor"] == "reviewer@example.test"

    policies = seeded.get("/api/policies").json()
    assert policies["active"]["version"] == 2
    assert [policy["version"] for policy in policies["history"]] == [2, 1]
    assert [policy["status"] for policy in policies["history"]] == ["active", "inactive"]

    repeated = seeded.post(
        f"/api/proposals/{proposal['id']}/decision",
        json={"decision": "reject", "actor": "another-reviewer"},
    )
    assert repeated.status_code == 409
    assert "already approved" in repeated.json()["detail"]

    audit = seeded.get("/api/audit-events", params={"event_type": "proposal.approved"}).json()["items"]
    assert len(audit) == 1
    assert audit[0]["details"]["new_policy_version"] == 2


def test_rejection_does_not_change_policy(seeded: TestClient) -> None:
    proposal = seeded.get("/api/proposals").json()["items"][0]
    response = seeded.post(
        f"/api/proposals/{proposal['id']}/decision",
        json={"decision": "reject", "actor": "reviewer", "note": "Need more evidence"},
    )
    assert response.status_code == 200
    assert response.json()["proposal"]["state"] == "rejected"
    assert response.json()["policy"] is None
    policies = seeded.get("/api/policies").json()
    assert policies["active"]["version"] == 1
    assert len(policies["history"]) == 1
    assert len(
        seeded.get("/api/audit-events", params={"event_type": "proposal.rejected"}).json()["items"]
    ) == 1


def test_analyze_returns_consistent_shape_and_existing_pending(seeded: TestClient) -> None:
    response = seeded.post("/api/proposals/analyze")
    assert response.status_code == 200
    assert response.json()["proposal"]["state"] == "pending"
    assert "reason" in response.json()


def test_approved_policy_does_not_reuse_outcomes_from_prior_policy(seeded: TestClient) -> None:
    proposal = seeded.get("/api/proposals").json()["items"][0]
    approved = seeded.post(
        f"/api/proposals/{proposal['id']}/decision",
        json={"decision": "approve", "actor": "reviewer"},
    )
    assert approved.status_code == 200

    analyzed = seeded.post("/api/proposals/analyze")
    assert analyzed.status_code == 200
    assert analyzed.json()["proposal"] is None
    assert analyzed.json()["reason"] == "at least three outcomes under the active policy are required"


def test_explanation_shows_policy_before_after_and_approval(seeded: TestClient) -> None:
    recommendation = seeded.post(
        "/api/recommendations", json={"scenario": "Refund above threshold"}
    ).json()
    proposal = seeded.get("/api/proposals").json()["items"][0]
    seeded.post(
        f"/api/proposals/{proposal['id']}/decision",
        json={"decision": "approve", "actor": "human-reviewer"},
    )

    explanation = seeded.get(
        f"/api/decisions/{recommendation['decision_id']}/explanation"
    ).json()
    assert explanation["before"]["version"] == 1
    assert explanation["after"]["version"] == 2
    assert [policy["version"] for policy in explanation["policy_chain"]] == [1, 2]
    assert explanation["approval"]["actor"] == "human-reviewer"
    assert "Human approval" in explanation["summary"]


def test_explanation_for_post_approval_decision_reconstructs_the_change(seeded: TestClient) -> None:
    proposal = seeded.get("/api/proposals").json()["items"][0]
    seeded.post(
        f"/api/proposals/{proposal['id']}/decision",
        json={"decision": "approve", "actor": "human-reviewer"},
    )
    recommendation = seeded.post(
        "/api/recommendations",
        json={"scenario": "A customer asks for financing and an estimated monthly payment."},
    ).json()

    explanation = seeded.get(
        f"/api/decisions/{recommendation['decision_id']}/explanation"
    ).json()

    assert recommendation["policy_version"] == 2
    assert explanation["before"]["version"] == 1
    assert explanation["after"]["version"] == 2
    assert explanation["approval"]["actor"] == "human-reviewer"
    assert len(explanation["outcomes"]) == 3
    assert len(explanation["audit_event_ids"]) >= 1
    assert "Human approval" in explanation["summary"]
