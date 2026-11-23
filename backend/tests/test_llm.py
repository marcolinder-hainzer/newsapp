"""Tests der KI-Anbindung mit einem simulierten Claude-Client (keine echten API-Aufrufe)."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.llm import LLMClient
from app.main import create_app

RAIL = {
    "de": {"title": "Bundestag beschließt Bahnreform mit Infrastrukturfonds",
           "summary": "Der Bundestag hat die Reform der Bahnfinanzierung beschlossen. Ein Infrastrukturfonds soll die Sanierung des Schienennetzes über zehn Jahre absichern.",
           "key_points": ["Infrastrukturfonds über zehn Jahre", "Opposition kritisiert Finanzierung"],
           "context": "Das Schienennetz gilt als stark sanierungsbedürftig."},
    "en": {"title": "German parliament approves rail reform with infrastructure fund",
           "summary": "Germany's parliament approved a rail funding reform. An infrastructure fund will finance renovation of the rail network over ten years.",
           "key_points": ["Infrastructure fund over ten years", "Opposition criticises funding"],
           "context": "The rail network is in need of major renovation."},
}
STORM = {
    "de": {"title": "Sturm Elara verwüstet Portugals Küste",
           "summary": "Sturm Elara hat an Portugals Küste schwere Schäden angerichtet. Tausende Haushalte sind ohne Strom.",
           "key_points": ["Tausende ohne Strom", "Warnung vor Überschwemmungen"], "context": ""},
    "en": {"title": "Storm Elara batters Portugal's coast, thousands without power",
           "summary": "Storm Elara caused severe damage on Portugal's coast. Thousands of homes are without power and authorities warn of flooding.",
           "key_points": ["Thousands without power", "Flood warnings issued"], "context": ""},
}


class FakeLLM(LLMClient):
    def __init__(self, settings):
        super().__init__(settings, client=object())
        self.calls = []

    def generate_json(self, system, prompt, schema, max_tokens=16000):
        self.calls.append(prompt)
        if "<stories>" in prompt:
            ids = [int(part.split('"')[0]) for part in prompt.split('<story id="')[1:]]
            item = {"story_id": ids[0], "text": "Wichtigste Meldung."}
            return {"de": {"headline": "Bahnreform und Sturm", "overview": "Überblick.", "items": [item, {"story_id": 99999, "text": "x"}]},
                    "en": {"headline": "Rail reform and storm", "overview": "Overview.", "items": [item]}}
        if "Bahn" in prompt or "rail" in prompt:
            base = RAIL
            category = "politik"
        elif "Elara" in prompt:
            base = STORM
            category = "international"
        else:
            return None  # simuliert eine Ablehnung/Fehler
        return {"category": category, **base, "trust": {"score": 85, "notes_de": ["Übereinstimmend berichtet."],
                                                         "notes_en": ["Consistently reported."]}}


def test_llm_summaries_and_cross_language_merge(test_settings, feed_transport):
    llm = FakeLLM(test_settings)
    app = create_app(test_settings, llm=llm, transport=feed_transport, start_scheduler=False)
    app.state.pipeline.run_cycle()
    client = TestClient(app)
    items = client.get("/api/stories", params={"hours": 24}).json()["items"]

    rail = [s for s in items if "rail" in s["title"]["en"].lower()]
    assert len(rail) == 1, "deutsche und englische Meldung sollten zusammengeführt sein"
    assert rail[0]["source_count"] == 4
    assert rail[0]["title"]["de"] == RAIL["de"]["title"]

    storm = [s for s in items if "elara" in s["title"]["en"].lower()]
    assert len(storm) == 1
    assert storm[0]["source_count"] == 4  # Tagesschau, BBC, Guardian, Boulevard
    assert storm[0]["category"] == "international"

    detail = client.get(f"/api/stories/{rail[0]['id']}").json()
    assert detail["summary"]["generated_by"] == "llm"
    assert detail["trust"]["content_method"] == "ai"
    assert "Übereinstimmend berichtet." in detail["trust"]["notes"]["de"]

    digest = client.get("/api/digest", params={"scope": "top:day"}).json()
    assert digest["generated_by"] == "llm"
    assert all(i["story_id"] != 99999 for i in digest["content"]["de"]["items"])

    router = next(s for s in items if "Router" in s["title"]["de"])
    assert router["summary_status"] == "extractive"  # KI hat keine Antwort geliefert


def test_llm_client_request_shape_and_refusal(test_settings):
    captured = {}

    def make_response(stop_reason, text):
        return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0))

    class FakeMessages:
        def __init__(self, stop_reason, text):
            self.stop_reason, self.text = stop_reason, text

        def create(self, **kwargs):
            captured.update(kwargs)
            return make_response(self.stop_reason, self.text)

    def fake_client(stop_reason, text):
        messages = FakeMessages(stop_reason, text)
        return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))

    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"],
              "additionalProperties": False}
    llm = LLMClient(test_settings, client=fake_client("end_turn", '{"a": 1}'))
    assert llm.generate_json("sys", "prompt", schema) == {"a": 1}
    assert captured["model"] == "claude-opus-5-5"
    assert captured["fallbacks"] == "default"
    assert captured["output_config"]["format"]["schema"] == schema
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in captured and "temperature" not in captured
    assert llm.usage["input_tokens"] == 10

    refused = LLMClient(test_settings, client=fake_client("refusal", ""))
    assert refused.generate_json("sys", "prompt", schema) is None
    assert refused.usage["refusals"] == 1

    test_settings.llm_model = "claude-haiku-5-5"
    captured.clear()
    haiku = LLMClient(test_settings, client=fake_client("end_turn", '{"a": 2}'))
    assert haiku.generate_json("sys", "prompt", schema) == {"a": 2}
    assert "fallbacks" not in captured
