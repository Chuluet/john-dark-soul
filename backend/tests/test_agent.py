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
