from __future__ import annotations

from apps.api.llm import build_messages


def test_passage_headers_expose_source_type_to_llm():
    messages = build_messages(
        system="rules",
        user_question="what can I do",
        passages=[
            {
                "index": 1,
                "source_type": "bare_act",
                "title": "Consumer Protection Act 2019",
                "anchor": "consumer-protection-2019/sec-35",
                "text": "A complaint may be filed with a District Commission.",
            },
            {
                "index": 2,
                "source_type": "sc_judgment",
                "title": "A versus B",
                "court": "SC",
                "citation": "2020 SCR 1",
                "text": "The Court discussed consumer complaints.",
            },
        ],
    )

    user_text = messages[1]["content"]
    assert "[1] TYPE: Bare Act | Consumer Protection Act 2019" in user_text
    assert "[2] TYPE: Supreme Court judgment | A versus B" in user_text
