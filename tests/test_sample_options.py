from app.services.sync import MySqlMiddlewareSource


def test_id_lookup_query_joins_patient_name_and_groups_by_sample(monkeypatch):
    source = object.__new__(MySqlMiddlewareSource)
    captured = {}

    def fetch_all(query, parameters):
        captured["query"] = query
        captured["parameters"] = parameters
        return [{"sample_id": "S1", "test_date": "2026-09-03", "patient_name": "Name", "patient_id": "P1"}]

    monkeypatch.setattr(source, "_fetch_all", fetch_all)

    options = source.fetch_id_sample_ids("2026-08-28", "2026-09-03")

    assert options[0]["sample_id"] == "S1"
    assert "LEFT JOIN pinfo" in captured["query"]
    assert "patient.pnm" in captured["query"]
    assert "GROUP BY result.sid" in captured["query"]
    assert captured["parameters"] == ("2026-08-28", "2026-09-03")