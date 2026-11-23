import httpx

from app.tts import TTSService, chunk_text


def test_chunk_text_respects_limit():
    text = " ".join(f"Das ist Satz Nummer {i}." for i in range(200))
    chunks = chunk_text(text, 300)
    assert all(len(c) <= 300 for c in chunks)
    assert " ".join(chunks).replace("  ", " ") == text


def test_azure_synthesis_and_cache(test_settings):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["Ocp-Apim-Subscription-Key"] == "secret"
        assert b"de-DE-FlorianMultilingualNeural" in request.content
        return httpx.Response(200, content=b"ID3fake-mp3")

    test_settings.tts_provider = "azure"
    test_settings.azure_speech_key = "secret"
    service = TTSService(test_settings, transport=httpx.MockTransport(handler))
    assert service.info()["provider"] == "azure"
    path = service.synthesize("Guten Abend. Hier sind die Nachrichten.", "de", "male")
    assert path.read_bytes() == b"ID3fake-mp3"
    service.synthesize("Guten Abend. Hier sind die Nachrichten.", "de", "male")
    assert len(calls) == 1  # zweiter Aufruf aus dem Cache


def test_no_provider_means_browser(test_settings):
    test_settings.tts_provider = "auto"
    test_settings.azure_speech_key = test_settings.openai_api_key = test_settings.elevenlabs_api_key = ""
    assert not TTSService(test_settings).available


def test_tts_api_endpoints(test_settings, feed_transport):
    from fastapi.testclient import TestClient

    from app.main import create_app

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.content.decode())
        return httpx.Response(200, content=b"ID3audio")

    test_settings.tts_provider = "azure"
    test_settings.azure_speech_key = "secret"
    app = create_app(test_settings, transport=feed_transport, tts_transport=httpx.MockTransport(handler),
                     start_scheduler=False)
    app.state.pipeline.run_cycle()
    client = TestClient(app)
    assert client.get("/api/meta").json()["tts"]["voices"]["de"]["female"] == "de-DE-SeraphinaMultilingualNeural"

    story_id = client.get("/api/stories", params={"q": "Router"}).json()["items"][0]["id"]
    res = client.get(f"/api/tts/story/{story_id}", params={"lang": "en", "voice": "male"})
    assert res.status_code == 200 and res.headers["content-type"] == "audio/mpeg"
    # Keine englische Fassung (ohne KI) → deutscher Originaltext mit deutscher Herrenstimme
    assert "de-DE-FlorianMultilingualNeural" in requests[-1] and "Router" in requests[-1]

    assert client.get("/api/tts/preview", params={"lang": "en", "voice": "female"}).status_code == 200
    assert "en-US-AvaMultilingualNeural" in requests[-1]
    assert client.get("/api/tts/digest", params={"scope": "top:day", "lang": "de"}).status_code == 200
