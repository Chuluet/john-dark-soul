"""Idioma de las respuestas y formato del contexto del agente (sin Ollama ni Postgres)."""

from langchain_core.documents import Document

from agents.nodes import reject
from agents.prompts import REJECTION_MESSAGES, rejection_message
from agents.utils import detect_language, extract_sources, format_context, language_name, merge_results, expand_names


def test_detect_language_defaults_to_english():
    assert detect_language("Who is Knight Artorias?") == "en"
    assert detect_language("What happened to Lordran after Gwyn linked the fire") == "en"
    assert detect_language("Artorias") == "en"  # solo un nombre: idioma por defecto


def test_detect_language_spanish_with_and_without_accents():
    assert detect_language("¿Quién es Artorias?") == "es"
    assert detect_language("quien es el caballero artorias") == "es"
    assert detect_language("me cuentas sobre la historia de Lothric") == "es"


def test_detect_language_other_languages():
    assert detect_language("Qui est le chevalier Artorias ? Où est-il né ?") == "other"
    assert language_name("other") == "the same language as the question"
    assert language_name("es") == "Spanish"


def test_rejection_follows_the_question_language():
    assert reject({"language": "es"})["answer"] == REJECTION_MESSAGES["es"]
    assert reject({"language": "en"})["answer"] == REJECTION_MESSAGES["en"]
    assert rejection_message("other") == REJECTION_MESSAGES["en"]


def test_context_and_sources_use_ingest_metadata():
    docs = [
        (Document(page_content="Artorias walked the Abyss.", metadata={
            "title": "Knight Artorias", "juego": "DS1", "seccion": "Lore",
            "fuente": "knight-artorias__DS1.md", "url": "https://wiki/Artorias"}), 0.8),
        (Document(page_content="Second part.", metadata={
            "title": "Knight Artorias", "juego": "DS1", "fuente": "knight-artorias__DS1.md"}), 0.7),
        (Document(page_content="Video part.", metadata={
            "title": "lore", "juego": "general", "seccion": "01:30 - 03:00", "fuente": "lore.mp4"}), 0.6),
    ]

    context = format_context(docs)

    assert "[Fragment 1 | source: Knight Artorias, DS1, Lore]" in context
    assert "[Fragment 3 | source: lore, 01:30 - 03:00]" in context  # 'general' no se muestra
    assert extract_sources(docs) == [
        {"title": "Knight Artorias", "game": "DS1", "url": "https://wiki/Artorias"},
        {"title": "lore", "game": "general", "url": None},
    ]


def _doc(source, fragment=0):
    return Document(page_content=f"{source}-{fragment}", metadata={"fuente": source, "fragmento": fragment})


def test_merge_results_keeps_best_score_and_limits_per_source():
    original = [(_doc("chosen-undead.md", 0), 0.57), (_doc("chosen-undead.md", 1), 0.56), (_doc("sen.md"), 0.55)]
    rewritten = [(_doc("frampt.md"), 0.60), (_doc("chosen-undead.md", 0), 0.59)]

    merged = merge_results([original, rewritten], k=3, max_per_source=1)

    assert [(d.page_content, s) for d, s in merged] == [
        ("frampt.md-0", 0.60), ("chosen-undead.md-0", 0.59), ("sen.md-0", 0.55)]


TITLES = ["Kingseeker Frampt", "Great Grey Wolf Sif", "Chosen Undead", "Abyss", "Abyss Watchers", "Vendrick"]


def test_expand_names_uses_the_only_page_with_that_name():
    assert expand_names("What did Frampt ask the Chosen Undead?", TITLES) ==         "What did Kingseeker Frampt ask the Chosen Undead?"
    assert expand_names("Who is Sif?", TITLES) == "Who is Great Grey Wolf Sif?"


def test_expand_names_leaves_ambiguous_or_complete_names():
    assert expand_names("What is the Abyss?", TITLES) == "What is the Abyss?"          # está en dos títulos
    assert expand_names("Who is Kingseeker Frampt?", TITLES) == "Who is Kingseeker Frampt?"
    assert expand_names("who is frampt", TITLES) == "who is frampt"                    # solo nombres propios


# --- Rechazos decididos por el modelo, fallos de servicio e historial ---------

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from agents import nodes
from agents.graph import build_graph
from agents.prompts import SERVICE_ERROR_MESSAGES
from agents.utils import is_rejection

ARTORIAS = [(Document(page_content="Artorias walked the Abyss.", metadata={
    "title": "Knight Artorias", "juego": "DS1", "fuente": "knight-artorias__DS1.md"}), 0.8)]


def test_is_rejection_tolerates_quotes_and_missing_suggestion():
    assert is_rejection('"No tengo suficiente información en mi base de conocimiento '
                        'para responder esa pregunta."', REJECTION_MESSAGES.values())
    assert is_rejection(REJECTION_MESSAGES["en"], REJECTION_MESSAGES.values())
    assert not is_rejection("Artorias walked the Abyss (fuente: Knight Artorias, DS1).",
                            REJECTION_MESSAGES.values())


def test_generate_drops_sources_when_the_model_rejects(monkeypatch):
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=[REJECTION_MESSAGES["es"]]))

    result = nodes.generate({"question": "¿Quién mató a Artorias?", "language": "es", "docs": ARTORIAS})

    assert result == {"answer": REJECTION_MESSAGES["es"], "sources": [], "rejected": True}


def test_generate_keeps_sources_when_it_answers(monkeypatch):
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["Artorias walked the Abyss."]))

    result = nodes.generate({"question": "Who is Artorias?", "language": "en", "docs": ARTORIAS})

    assert result["rejected"] is False
    assert result["sources"] == [{"title": "Knight Artorias", "game": "DS1", "url": None}]


def _ollama_caido():
    def fallar(_):
        raise ConnectionError("Ollama no responde")
    return RunnableLambda(fallar)


def test_graph_returns_error_instead_of_raising_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr(nodes, "create_llm", _ollama_caido)
    guardados = []
    monkeypatch.setattr(nodes.db, "guardar_mensaje", lambda **kw: guardados.append(kw))

    result = build_graph().invoke({"question": "¿Quién es Artorias?", "user_id": "demo"},
                                  {"configurable": {"thread_id": "caido"}})

    assert result["error"] and "ConnectionError" in result["error"]
    assert result["answer"] == SERVICE_ERROR_MESSAGES["es"]
    assert result["sources"] == []
    assert guardados == []  # un fallo de servicio no es historial


def test_error_does_not_leak_into_the_next_question_of_the_same_thread(monkeypatch):
    graph = build_graph()
    config = {"configurable": {"thread_id": "misma-sesion"}}
    monkeypatch.setattr(nodes, "create_llm", _ollama_caido)
    graph.invoke({"question": "Who is Artorias?"}, config)

    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["NO"]))
    result = graph.invoke({"question": "How do I cook sushi?"}, config)

    assert result["error"] is None
    assert result["answer"] == REJECTION_MESSAGES["en"]


def test_save_history_stores_answers_and_rejections(monkeypatch):
    guardados = []
    monkeypatch.setattr(nodes.db, "guardar_mensaje", lambda **kw: guardados.append(kw))
    monkeypatch.setattr(nodes, "create_llm", lambda: FakeListChatModel(responses=["NO"]))

    result = build_graph().invoke({"question": "How do I cook sushi?", "user_id": "demo"},
                                  {"configurable": {"thread_id": "historial"}})

    assert result["rejected"] is True
    assert guardados == [{"user_id": "demo", "question": "How do I cook sushi?",
                          "answer": REJECTION_MESSAGES["en"], "sources": [], "rejected": True}]


def test_save_history_skips_without_user_and_survives_db_errors(monkeypatch):
    def db_caida(**_):
        raise ConnectionError("Postgres no responde")
    monkeypatch.setattr(nodes.db, "guardar_mensaje", db_caida)
    estado = {"question": "q", "answer": "a", "sources": [], "rejected": False}

    assert nodes.save_history(estado) == {}                       # sin user_id: no intenta guardar
    assert nodes.save_history(estado | {"user_id": "demo"}) == {}  # Postgres caído: no revienta
